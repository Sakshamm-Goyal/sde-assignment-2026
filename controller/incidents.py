"""Hallucination incidents: detect -> pick a fix -> validate -> propose with evidence -> verify after apply.

Credit-frugal by design: the first candidate is the last *known-good* prompt (live evidence of both a normal
hallucination-flag rate and normal engagement). The LLM is only asked when no known-good prompt exists.
Validation measures safety only, so every applied fix is also checked for engagement afterwards.
"""
from __future__ import annotations

import json
import math

from . import stats
from .cfg import DAY
from .client import ApiError

MIN_CONN = 200          # connected calls in the detection window
WINDOW = 8 * 60         # minutes of history the detector may look back
VERIFY_CONN = 300
VAL_N = 400
MAX_CREDITS_PER_INCIDENT = 25


def baseline(store, wf_id) -> tuple[float, float]:
    r = store.one("SELECT SUM(connected), SUM(flags), SUM(engaged) FROM eng WHERE wf=? AND day<0", (wf_id,))
    if not r or not r[0]:
        return 0.015, 0.5
    return max(r[1] / r[0], 0.002), r[2] / r[0]


def recent(store, wf_id, prompt, since, until=None):
    """Most recent ticks under `prompt` until MIN_CONN connected calls are covered."""
    n = x = g = 0
    for m, c, f, e in store.q("SELECT minute, SUM(connected), SUM(flags), SUM(engaged) FROM ticks WHERE wf=? AND "
                              "prompt=? AND minute>=? AND minute<? GROUP BY minute ORDER BY minute DESC",
                              (wf_id, prompt, since, until if until is not None else 10 ** 9)):
        n, x, g = n + c, x + f, g + e
        if n >= MIN_CONN:
            break
    return n, x, g


def known_good(store, wf_id, base_flag, base_eng, exclude) -> list[tuple]:
    out = []
    for p, n, f, g in store.q("SELECT prompt, SUM(connected), SUM(flags), SUM(engaged) FROM eng WHERE wf=? "
                              "GROUP BY prompt", (wf_id,)):
        if p in exclude or n < 500:
            continue
        flag_ok = stats.binom_upper_z(f, n, base_flag) < 2.0
        eng_ok = (g / n) >= base_eng * 0.95
        if flag_ok and eng_ok:
            out.append((p, n, round(f / n, 4), round(g / n, 4)))
    return sorted(out, key=lambda r: -r[3])


CUSUM_R, CUSUM_H = 3.0, 11.5   # detect a 3x flag rate; h=11.5 gives roughly one false alarm per ~1e5 calls
CUSUM_H_WATCH = 7.0            # first 24h after any prompt change: a spike is far more likely, so a lower bar


def check(ctl, wf, cfg):
    """Every tick: one-sided Bernoulli CUSUM on the flag rate of the *current* prompt vs the workflow baseline.

    A CUSUM accumulates evidence across ticks instead of re-testing overlapping windows, so the false-alarm rate
    is controlled even though we look every 15 minutes. It resets whenever the prompt changes."""
    s, now = ctl.store, ctl.now
    if s.one("SELECT 1 FROM incidents WHERE wf=? AND kind='hallucination' AND status NOT IN ('closed','failed')",
             (wf.id,)):
        return
    base, _ = baseline(s, wf.id)
    prompt = cfg["prompt_version"]
    key = f"cusum:{wf.id}"
    st = s.meta(key)
    if not st or st["prompt"] != prompt:
        st = {"prompt": prompt, "S": 0.0, "last": now - 30, "n": 0, "x": 0, "since": now}
    h = CUSUM_H_WATCH if now - st.get("since", -10 ** 9) < DAY and st.get("since", 0) > 0 else CUSUM_H
    a, b = math.log(CUSUM_R), math.log((1 - CUSUM_R * base) / (1 - base))
    for m, n, x in s.q("SELECT minute, SUM(connected), SUM(flags) FROM ticks WHERE wf=? AND prompt=? AND minute>? "
                       "AND minute<? GROUP BY minute ORDER BY minute", (wf.id, prompt, st["last"], now)):
        st["S"] = max(0.0, st["S"] + x * a + (n - x) * b)
        st["n"], st["x"] = (0, 0) if st["S"] == 0 else (st["n"] + n, st["x"] + x)
        st["last"] = m
        if st["S"] > h and st["n"] >= 100:
            rate = st["x"] / st["n"]
            data = {"bad_prompt": prompt, "rate": round(rate, 4), "baseline": round(base, 4), "n": st["n"],
                    "cusum": round(st["S"], 2), "threshold": h, "tried": [], "credits": 0}
            with s.tx():
                s.x("INSERT INTO incidents(wf, kind, status, opened_minute, data) VALUES(?,?,?,?,?)",
                    (wf.id, "hallucination", "open", now, json.dumps(data)))
                s.decide(now, wf.id, "incident_opened",
                         f"hallucination flags {rate:.1%} on {prompt} vs baseline {base:.1%} over {st['n']} connected "
                         f"calls (CUSUM {st['S']:.1f} > {h})", data)
                s.alert(now, "page", wf.id, f"hallucination spike on {prompt}: {rate:.1%} vs {base:.1%}; fix flow "
                                            f"started, see `python -m controller why --wf {wf.id}`")
            st = {"prompt": prompt, "S": 0.0, "last": m, "n": 0, "x": 0, "since": st.get("since", 0)}
            break
    s.set_meta(key, st)


def step(ctl, wf, cfg):
    """Advance every open incident on this workflow by one state."""
    s, now = ctl.store, ctl.now
    for iid, status, opened, raw in s.q("SELECT id, status, opened_minute, data FROM incidents WHERE wf=? AND "
                                        "kind='hallucination' AND status NOT IN ('closed','failed')", (wf.id,)):
        d = json.loads(raw)
        new = _step(ctl, wf, cfg, iid, status, d)
        s.x("UPDATE incidents SET status=?, data=?, closed_minute=? WHERE id=?",
                (new, json.dumps(d), now if new in ("closed", "failed") else None, iid))


def _spend_ok(ctl, d, cost):
    return ctl.credits >= cost and d["credits"] + cost <= MAX_CREDITS_PER_INCIDENT


def _step(ctl, wf, cfg, iid, status, d):
    s, now = ctl.store, ctl.now
    base, base_eng = baseline(s, wf.id)
    if status == "open":
        if cfg["prompt_version"] != d["bad_prompt"]:
            # someone (a supervisor) already changed the prompt: verify that instead of proposing
            d["candidate"], d["applied_minute"] = cfg["prompt_version"], now
            return "verifying"
        cands = [p for p, *_ in known_good(s, wf.id, base, base_eng, {d["bad_prompt"], *d["tried"]})]
        d["known_good"] = cands
        if not cands and not d.get("llm") and _spend_ok(ctl, d, 3):
            try:
                r = ctl.sim.post("/llm/suggest-fixes", {"workflow_id": wf.id, "problem":
                                 f"hallucination flag rate {d['rate']:.1%} on prompt {d['bad_prompt']} "
                                 f"vs {base:.1%} baseline"}, retries=1)
                d["llm"] = [x["prompt_version"] for x in r["suggestions"]]
                ctl.spent(wf.id, "llm_suggest_fixes", 3, f"incident {iid}")
                d["credits"] += 3
                s.decide(now, wf.id, "llm_suggestions", f"LLM suggested {d['llm']} (3 credits)", r)
            except ApiError as e:
                d["llm"] = []
                s.decide(now, wf.id, "llm_failed", str(e))
        cands += [p for p in d.get("llm", []) if p not in d["tried"] and p != d["bad_prompt"] and p not in cands]
        for p in cands:
            if not _spend_ok(ctl, d, math.ceil(VAL_N / 100)):
                break
            try:
                v = ctl.sim.post("/validation/runs", {"workflow_id": wf.id, "prompt_version": p, "n": VAL_N}, retries=1)
            except ApiError as e:
                s.decide(now, wf.id, "validation_failed", str(e))
                break
            cost = math.ceil(VAL_N / 100)
            ctl.spent(wf.id, "validation_run", cost, v["validation_run_id"])
            d["credits"] += cost
            d["tried"].append(p)
            fails = round((1 - v["pass_rate"]) * v["n"])
            lb = stats.wilson_lower(v["n"] - fails, v["n"])
            ok = v["pass_rate"] >= wf.min_val and lb >= wf.min_val
            s.decide(now, wf.id, "validation", f"{p}: pass {v['pass_rate']:.3f} on n={v['n']} "
                                               f"(90% lower bound {lb:.3f}, policy {wf.min_val}) -> "
                                               f"{'accept' if ok else 'reject'}", v)
            if ok:
                d["candidate"], d["validation"] = p, v
                d["live_evidence"] = p in d.get("known_good", [])
                return "ready"
        if not d.get("candidate"):
            s.alert(now, "page", wf.id, f"hallucination incident {iid}: no candidate prompt passed validation; "
                                        f"credits left {ctl.credits:.0f}. Needs a human.")
            s.decide(now, wf.id, "incident_failed", "no validated candidate", d)
            return "failed"
        return "ready"
    if status == "ready":
        if cfg["prompt_version"] != d["bad_prompt"]:
            d["candidate"], d["applied_minute"] = cfg["prompt_version"], now
            return "verifying"
        pid = ctl.gov.propose_incident(wf, cfg, d)
        if pid:
            d["proposal_id"] = pid
            return "fixing"
        return "ready"
    if status == "fixing":
        st = s.one("SELECT status, applied_minute FROM proposals WHERE proposal_id=?", (d["proposal_id"],))
        if st and st[0] == "applied":
            d["applied_minute"] = st[1]
            return "verifying"
        if st and st[0] in ("rejected", "expired", "superseded", "lapsed", "abandoned", "stale", "invalid"):
            s.decide(now, wf.id, "incident_retry", f"fix proposal {d['proposal_id']} {st[0]}; re-proposing")
            return "ready"
        return "fixing"
    if status == "verifying":
        p = d["candidate"]
        n, x, g = recent(s, wf.id, p, d["applied_minute"])
        if n < VERIFY_CONN:
            # recent() stops at MIN_CONN; extend to the whole post-apply period for verification
            r = s.one("SELECT SUM(connected), SUM(flags), SUM(engaged) FROM ticks WHERE wf=? AND prompt=? AND minute>=?",
                      (wf.id, p, d["applied_minute"]))
            n, x, g = (r[0] or 0, r[1] or 0, r[2] or 0)
        if n < VERIFY_CONN:
            return "verifying"
        thr = base + 2 * math.sqrt(base * (1 - base) / n)
        eng_drop_z = (g / n - base_eng) / math.sqrt(base_eng * (1 - base_eng) / n)
        safe, engaged = x / n <= thr, not (g / n < base_eng * 0.95 and eng_drop_z < -2.33)
        s.decide(now, wf.id, "incident_verify", f"{p} after fix: flags {x / n:.1%} (limit {thr:.1%}), engagement "
                                                f"{g / n:.1%} vs baseline {base_eng:.1%} on {n} connected",
                 {"safe": safe, "engagement_ok": engaged})
        if safe and engaged:
            s.alert(now, "info", wf.id, f"hallucination incident {iid} resolved by {p}")
            return "closed"
        d["bad_prompt"] = p
        d.pop("candidate", None)
        return "open"
    return status
