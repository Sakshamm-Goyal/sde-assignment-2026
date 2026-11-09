"""Learning: cohorts + call-time from history, caller-ID health, welcome/voice experiments.

Everything here reads the store and returns *intents* (dicts describing a change and why). Nothing here talks
to the simulator or decides how a change is routed; that is governance's job.
"""
from __future__ import annotations

import math
from collections import defaultdict

from . import stats
from .cfg import DAY, ENG_DIMS, FEATS, dist, match, tv

REST_MIN = 2 * DAY
# Harm budget: a change may cost at most ~2% caller-ID health / ~1% engagement even if what we try is bad.
PROBE_SHARE = 0.045         # untested caller ID: 4.5% x (0.86 - 0.5 health) / 0.86 ~ 1.9%
PROBE_MIN_DIALS = 200
EPS_TOTAL, EPS_ARM = 0.20, 0.10   # exploration: all challengers / one challenger (10% x a 0.88x arm = 1.2%)
ALPHA = 0.02                # family-wise (Holm) per daily look, one-sided; ~5 looks -> ~0.1 overall; SUBMISSION §5
MIN_N_PROMOTE, MIN_N_PRUNE = 400, 200
MIN_LIFT = 0.03
HOLDOUT = 0.20              # incumbent share kept after promotion, so decay stays measurable
MAX_EXPLORE_DAYS = 6
PROMISING_SHARE, EXPLORE_CAP = 0.25, 0.60   # arms already looking better (z>=1) earn more traffic


# ----------------------------------------------------------------------------- cohorts + call time
def propose_cohorts(store, wf) -> dict | None:
    """Pick the one lead feature whose hourly pickup profile differs most (chi-square on history), merge levels
    with similar profiles, and derive per-cohort hour weights by comparative advantage."""
    hours = list(range(wf.window[0], wf.window[1]))
    rows = store.q("SELECT hour, feat, SUM(dials), SUM(connected) FROM pick WHERE wf=? AND day<0 GROUP BY hour, feat",
                   (wf.id,))
    tot = defaultdict(lambda: [0, 0])
    for h, _, d, c in rows:
        tot[h][0] += d
        tot[h][1] += c
    D = sum(v[0] for v in tot.values())
    if D < 3000:
        return None
    P = sum(v[1] for v in tot.values()) / D
    ph = {h: (tot[h][1] / tot[h][0]) if tot[h][0] else P for h in hours}
    best = None
    for fi, fname in enumerate(FEATS):
        lv = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for h, feat, d, c in rows:
            x = lv[feat.split("|")[fi]][h]
            x[0] += d
            x[1] += c
        levels = [l for l in lv if l != "?" and sum(v[0] for v in lv[l].values()) >= 300]
        if len(levels) < 2:
            continue
        chi = 0.0
        for l in levels:
            dl = sum(v[0] for v in lv[l].values())
            pl = sum(v[1] for v in lv[l].values()) / dl
            for h in hours:
                d, c = lv[l][h]
                if d == 0:
                    continue
                e = min(d * pl * ph[h] / P, d - 1e-6)
                chi += (c - e) ** 2 / max(e * (1 - e / d), 1e-9)
        z = stats.chi2_z(chi, (len(levels) - 1) * (len(hours) - 1))
        if best is None or z > best[0]:
            best = (z, fi, fname, lv, levels, round(chi, 1))
    if best is None or best[0] < 3.0:
        return None
    z, fi, fname, lv, levels, chi = best

    def group(levs):
        hd = {h: [sum(lv[l][h][0] for l in levs), sum(lv[l][h][1] for l in levs)] for h in hours}
        d = sum(v[0] for v in hd.values())
        return {"levels": sorted(levs), "h": hd, "d": d, "p": sum(v[1] for v in hd.values()) / max(d, 1)}

    def smooth(g, h):
        d, c = g["h"][h]
        return (c + 50 * g["p"]) / (d + 50)

    def gap(a, b):
        return math.sqrt(sum((smooth(a, h) / a["p"] - smooth(b, h) / b["p"]) ** 2 for h in hours) / len(hours))

    groups = [group([l]) for l in levels]
    while len(groups) > 1:
        pairs = sorted(((gap(a, b), i, j) for i, a in enumerate(groups) for j, b in enumerate(groups) if i < j))
        small = min(range(len(groups)), key=lambda i: groups[i]["d"])
        if len(groups) > 4 or pairs[0][0] < 0.08:
            _, i, j = pairs[0]
        elif groups[small]["d"] / D < 0.12:
            _, i, j = min((p for p in pairs if small in p[1:]), key=lambda p: p[0])
        else:
            break
        merged = group(groups[i]["levels"] + groups[j]["levels"])
        groups = [g for k, g in enumerate(groups) if k not in (i, j)] + [merged]
    if len(groups) < 2:
        return None
    groups.sort(key=lambda g: -g["d"])
    cohorts, weights, gain, prof = [], {}, 0.0, {}
    for gi, g in enumerate(groups):
        cid = "default" if gi == 0 else f"{fname}:{'/'.join(g['levels'])}"
        if gi:
            cohorts.append({"id": cid, "where": {fname: g["levels"]}})
        w = {str(h): round(min(max((smooth(g, h) / ph[h]) ** 2, 0.2), 5.0), 3) for h in hours}
        weights[cid] = w
        u = {h: g["h"][h][0] / max(g["d"], 1) for h in hours}
        q = {h: u[h] * w[str(h)] for h in hours}
        qs = sum(q.values()) or 1
        base = sum(u[h] * smooth(g, h) for h in hours)
        gain += (g["d"] / D) * (sum(q[h] / qs * smooth(g, h) for h in hours) / base - 1)
        prof[cid] = {"levels": g["levels"], "dial_share": round(g["d"] / D, 3), "pickup": round(g["p"], 4),
                     "best_hours": sorted(hours, key=lambda h: -smooth(g, h))[:3]}
    return {"cohorts": cohorts, "hour_weights": weights, "feature": fname,
            "evidence": {"chi2": chi, "z": round(z, 2), "groups": prof, "history_dials": D},
            # ponytail: ignores capacity competition between cohorts in the same hour, so halve it
            "pred_pickup_gain": round(0.5 * gain, 4)}


# ----------------------------------------------------------------------------- caller ID health
def did_ratios(store, wf_id: str, since: int) -> dict:
    """Pickup of each caller ID vs the pooled others *in the same 15-min ticks* (same hour, same people pool;
    caller IDs are randomised per dial so the comparison is unbiased). -> {did: (dials, conn, ratio, z)}"""
    by_t = defaultdict(dict)
    for m, did, d, c in store.q("SELECT minute, did, SUM(dials), SUM(connected) FROM ticks WHERE wf=? AND minute>=? "
                                "GROUP BY minute, did", (wf_id, since)):
        by_t[m][did] = (d, c)
    acc = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for t, row in by_t.items():
        D = sum(v[0] for v in row.values())
        C = sum(v[1] for v in row.values())
        for did, (d, c) in row.items():
            do, co = D - d, C - c
            if do <= 0:
                continue
            po = co / do
            a = acc[did]
            a[0] += d
            a[1] += c
            a[2] += d * po
            a[3] += d * po * (1 - po) * (1 + d / do)  # includes the noise in the peers' own rate
    return {did: (a[0], a[1], a[1] / a[2] if a[2] else 1.0, (a[1] - a[2]) / math.sqrt(a[3]) if a[3] else 0.0)
            for did, a in acc.items()}


def did_plan(ctl, wf, cfg) -> tuple[dict | None, bool, list]:
    """Update caller-ID states and return (target distribution or None, urgent, notes)."""
    s, now = ctl.store, ctl.now
    st = {d: (status, since) for d, status, since in s.q("SELECT did, status, since_minute FROM dids WHERE wf=?",
                                                          (wf.id,))}
    cur = dist(cfg, "default", "caller_id")
    urgent, notes = False, []

    def setst(did, status, ratio, dials, why):
        s.x("INSERT INTO dids VALUES(?,?,?,?,?,?) ON CONFLICT(wf, did) DO UPDATE SET status=excluded.status, "
            "since_minute=excluded.since_minute, ratio=excluded.ratio, dials=excluded.dials",
            (wf.id, did, status, now, round(ratio, 3), dials))
        st[did] = (status, now)
        s.decide(now, wf.id, f"caller_id_{status}", f"{did} -> {status}: {why}",
                 {"did": did, "ratio": round(ratio, 3), "dials": dials})
        notes.append(f"{did} {status} ({why})")

    # checked every tick for every caller ID, so the bar is high (z < -4) to keep false flags rare
    recent = did_ratios(s, wf.id, now - 180)
    tot = sum(v[0] for v in recent.values()) or 1
    for did, (d, c, ratio, z) in recent.items():
        if st.get(did, ("",))[0] in ("active", "probe") and d >= 300 and ratio < 0.7 and z < -4:
            # overloaded (well above a fair share of the dials it actually got) is fatigue, not a spam flag:
            # rest it and re-probe later. Realised share, not config share: campaign-locked workflows lag.
            share, fair = d / tot, 1 / len(recent)
            tired = share > 1.5 * fair
            setst(did, "rested" if tired else "flagged", ratio, d,
                  f"pickup {ratio:.0%} of other caller IDs over last 3h, z={z:.1f}"
                  + (f", while carrying {share:.0%} of dials" if tired else ""))
            urgent = urgent or cur.get(did, 0) > 0.1
    for did, (status, since) in list(st.items()):
        if status == "rested" and now - since >= REST_MIN:
            day = did_ratios(s, wf.id, now - DAY)
            if day.get(did, (0,))[0] < 0.05 * (sum(v[0] for v in day.values()) or 1):
                setst(did, "unused", 1.0, 0, "rested 2 days with almost no dials; load has decayed, probe again")
        if status != "probe":
            continue
        d, c, ratio, z = did_ratios(s, wf.id, since).get(did, (0, 0, 1.0, 0.0))
        if d >= PROBE_MIN_DIALS and ratio >= 0.85 and z > -2:
            setst(did, "active", ratio, d, f"probe passed: pickup {ratio:.0%} of peers on {d} dials")
        elif d >= PROBE_MIN_DIALS and ratio < 0.75 and z < -2.5:
            setst(did, "flagged", ratio, d, f"probe failed: pickup {ratio:.0%} of peers on {d} dials")
        elif d >= 1500:
            setst(did, "active" if ratio >= 0.8 else "flagged", ratio, d, f"probe inconclusive after {d} dials")
    if ctl.cooling(wf.id, "caller_id") and not urgent:
        return None, False, notes
    active = [d for d in wf.options["caller_id"] if st.get(d, ("",))[0] == "active"]
    # one untested caller ID at a time: if it turns out to be spam-flagged, the damage stays small
    # where caller-ID changes need an approval (slow), probe all untested IDs together at a smaller share
    probes = [d for d in wf.options["caller_id"] if st.get(d, ("",))[0] == "probe"]
    fresh = [d for d in wf.options["caller_id"] if st.get(d, ("unused",))[0] == "unused"]
    one = wf.auto.get("enabled") and "caller_id" in wf.auto.get("allowed_dims", [])
    probes = probes or (fresh[:1] if one else fresh)
    if not active:
        return None, urgent, notes
    share = PROBE_SHARE if len(probes) <= 1 else min(PROBE_SHARE, 0.2 / len(probes))
    target = {a: (1 - share * len(probes)) / len(active) for a in active}
    target.update({d: share for d in probes})
    if tv(cur, target) < 0.03:
        return None, urgent, notes
    return target, urgent, notes


# ----------------------------------------------------------------------------- experiments
def arm_table(store, wf_id, dim, since_day, cohorts, scope, overridden):
    """arm -> stratum(day, cohort, config version) -> [dials, connected, engaged], from realised traffic only.

    Config version is part of the stratum: within one version the allocation is fixed, so per-dial randomisation
    holds. Without it, a mid-day allocation change confounds arm with hour of day (Simpson's paradox: the old
    arm's dials sit in the morning, the new arm's in the afternoon)."""
    col = "wm" if dim == "welcome_message" else "voice"
    T = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    cache = {}
    for day, ver, feat, arm, d, c, g in store.q(
            f"SELECT day, cfg_ver, feat, {col}, SUM(dials), SUM(connected), SUM(engaged) FROM eng WHERE wf=? AND "
            f"day>=? GROUP BY day, cfg_ver, feat, {col}", (wf_id, since_day)):
        coh = cache.get(feat)
        if coh is None:
            coh = cache[feat] = match(cohorts, feat)
        if (scope == "all" and coh in overridden) or (scope != "all" and coh != scope):
            continue
        x = T[arm][(day, coh, ver)]
        x[0] += d
        x[1] += c
        x[2] += g
    return T


def compare(T, a, b, metric="eng"):
    i, j = (1, 2) if metric == "eng" else (0, 1)
    keys = set(T.get(a, {})) & set(T.get(b, {}))
    return stats.strat_diff((T[a][k][i], T[a][k][j], T[b][k][i], T[b][k][j]) for k in keys)


def _stat(T, arm, inc):
    diff, se, na, ni, pi = compare(T, arm, inc)
    z = diff / se if se and math.isfinite(se) else 0.0
    pd, pse, *_ = compare(T, arm, inc, "pick")
    return {"arm": arm, "vs": inc, "n_arm": na, "n_inc": ni, "rate_inc": round(pi, 4), "diff": round(diff, 4),
            "se": round(se, 4) if math.isfinite(se) else None, "z": round(z, 2), "rel_lift": round(diff / pi, 4) if pi else 0,
            "p": 1 - stats.cdf(z), "pickup_diff": round(pd, 4),
            "pickup_se": round(pse, 4) if math.isfinite(pse) else None}


def _guard_ok(s, drop) -> bool:
    if s["pickup_se"] is None:
        return True
    return s["pickup_diff"] > -drop and (s["pickup_diff"] + drop) / max(s["pickup_se"], 1e-9) > -0.84


def explore_dist(inc, opts):
    k = len(opts)
    eps = min(EPS_TOTAL, EPS_ARM * (k - 1))
    return {o: (1 - eps if o == inc else eps / (k - 1)) for o in opts}


def evaluate(ctl, wf, cfg, intraday=False) -> list[dict]:
    """Daily look (or intraday safety look): returns experiment intents for one workflow."""
    s, now = ctl.store, ctl.now
    today = now // DAY
    cohorts = cfg["cohorts"]
    intents, tests, looks = [], [], []
    exps = {(r[0], r[1]): r for r in s.q(
        "SELECT scope, dim, status, incumbent, arms, winner, start_minute, promoted_minute, promo_lift "
        "FROM experiments WHERE wf=?", (wf.id,))}
    for dim in ENG_DIMS:
        opts = wf.options[dim]
        if len(opts) < 2 or ctl.cooling(wf.id, dim):
            continue
        overridden = {c["id"] for c in cohorts if dim in (cfg["allocations"].get(c["id"]) or {})}
        if ("all", dim) not in exps:  # a supervisor's choice ends an experiment for good: we never re-open it
            if intraday:
                continue
            cur = dist(cfg, "default", dim)
            inc = max(cur, key=cur.get)
            intents.append({"type": "explore", "scope": "all", "dim": dim, "incumbent": inc, "arms": list(opts),
                            "dist": explore_dist(inc, opts), "impact": 0.0, "auto_eligible": False,
                            "summary": f"start testing {dim} {'/'.join(o for o in opts if o != inc)} against {inc} "
                                       f"on {round(100 * min(EPS_TOTAL, EPS_ARM * (len(opts) - 1)))}% of calls",
                            "rationale": f"no realised evidence yet for {dim} alternatives; exploration share capped so "
                                         f"one bad option costs < ~1.5% engagement before it is pruned"})
            continue
        for (scope, d2), r in exps.items():
            if d2 != dim:
                continue
            _, _, status, inc, arms, winner, start, promoted, promo_lift = r
            arms = arms.split(",") if arms else []
            if status == "exploring":
                T = arm_table(s, wf.id, dim, start // DAY, cohorts, scope, overridden)
                Tr = arm_table(s, wf.id, dim, max(start // DAY, today - 2), cohorts, scope, overridden)
                for arm in arms:
                    if arm == inc:
                        continue
                    st = _stat(T, arm, inc)
                    rec = _stat(Tr, arm, inc)
                    # novelty guard: a winner must still be winning in the last ~2 days, not just on average
                    st.update(scope=scope, dim=dim, recent_lift=rec["rel_lift"], recent_n=rec["n_arm"])
                    looks.append(st)
                    if intraday:
                        if st["n_arm"] >= 150 and st["se"] and (st["diff"] + 0.10 * st["rate_inc"]) / st["se"] < -2.33:
                            st["action"] = "prune"
                        continue
                    # prune early (P(worse) > 0.84): moving traffic back to the incumbent is always safe
                    if st["n_arm"] >= MIN_N_PRUNE and st["z"] < -1.0:
                        st["action"] = "prune"
                    elif rec["n_arm"] >= 150 and rec["z"] < -1.0:  # stopped working (decay while still exploring)
                        st["action"] = "prune"
                    elif (now - start) / DAY >= MAX_EXPLORE_DAYS and st["z"] < 0.5:
                        st["action"] = "prune"
                    if st["n_arm"] >= MIN_N_PROMOTE:
                        tests.append(st)
                if scope == "all" and not intraday:
                    for c in [c["id"] for c in cohorts if c["id"] not in overridden]:
                        Tc = arm_table(s, wf.id, dim, start // DAY, cohorts, c, overridden)
                        for arm in arms:
                            if arm != inc:
                                st = _stat(Tc, arm, inc)
                                st.update(scope=c, dim=dim, parent="all")
                                if st["n_arm"] >= MIN_N_PROMOTE:
                                    tests.append(st)
            elif status == "promoted" and not intraday:
                T = arm_table(s, wf.id, dim, max(promoted // DAY, today - 2), cohorts, scope, overridden)
                st = _stat(T, winner, inc)
                st.update(scope=scope, dim=dim, promo_lift=promo_lift)
                looks.append(st)
                se_rel = (st["se"] or 1) / max(st["rate_inc"], 1e-9)
                # decayed: either now likely worse than the holdout, or clearly below its promotion-time lift
                fell = (st["rel_lift"] - (promo_lift or 0)) / (se_rel * 1.41) < -2 and st["rel_lift"] < 0
                decayed = st["n_inc"] >= 150 and (st["z"] < -1.28 or fell)
                # after promotion, roll back on the guardrail only when we're confident the drop exceeds the limit
                guard = st["n_inc"] >= 150 and st["pickup_se"] and \
                    (st["pickup_diff"] + wf.guard_drop) / max(st["pickup_se"], 1e-9) < -2.33
                if decayed or guard:
                    why = (f"{winner} now {st['rel_lift']:+.1%} vs holdout {inc} over the last 2 days "
                           f"(z={st['z']}, promoted at {promo_lift:+.1%})") if decayed else \
                        f"{winner} breaks the pickup guardrail ({st['pickup_diff']:+.3f})"
                    intents.append({"type": "rollback", "scope": scope, "dim": dim, "winner": winner,
                                    "incumbent": inc, "dist": {inc: 1.0}, "stats": st, "auto_eligible": True,
                                    "impact": max(-st["rel_lift"], 0) * (1 - HOLDOUT),
                                    "summary": f"roll back {dim} {winner} -> {inc}" + (f" in {scope}" if scope != "all" else ""),
                                    "rationale": why})
    if intraday:
        for st in looks:
            if st.get("action") == "prune":
                r = exps[(st["scope"], st["dim"])]
                arms = [a for a in r[4].split(",") if a != st["arm"]]
                intents.append(_prune_intent(wf, st["scope"], st["dim"], r[3], arms, [st], safety=True))
        return intents
    # two Holm families: workflow-level tests, and cohort-level tests (so cohort scans don't dilute the main test)
    sig = [False] * len(tests)
    for fam in (lambda t: "parent" not in t, lambda t: "parent" in t):
        idx = [i for i, t in enumerate(tests) if fam(t)]
        for i, ok in zip(idx, stats.holm([tests[i]["p"] for i in idx], ALPHA) if idx else []):
            sig[i] = ok
    winners = defaultdict(list)
    for t, ok in zip(tests, sig):
        t["significant"] = ok
        fresh = t.get("recent_n", 0) < 100 or t.get("recent_lift", 1) > 0
        if ok and t["rel_lift"] >= MIN_LIFT and _guard_ok(t, wf.guard_drop) and fresh:
            winners[(t.get("parent", t["scope"]), t["dim"])].append(t)
    for (scope, dim), r in exps.items():
        if r[2] != "exploring":
            continue
        inc, arms, start = r[3], r[4].split(","), r[6]
        mine = [t for t in winners.get((scope, dim), [])]
        pooled = [t for t in mine if t["scope"] == scope]
        if pooled:
            best = max(pooled, key=lambda t: t["diff"] - 1.28 * (t["se"] or 1))
            intents.append(_promote_intent(wf, scope, dim, inc, best))
            continue
        for t in {t["scope"]: t for t in sorted(mine, key=lambda t: t["diff"])}.values():
            intents.append(_promote_intent(wf, t["scope"], dim, inc, t))
        mylooks = [st for st in looks if st["scope"] == scope and st["dim"] == dim]
        pruned = [st for st in mylooks if st.get("action") == "prune"]
        keep = [a for a in arms if a not in {p["arm"] for p in pruned}]
        if pruned:
            intents.append(_prune_intent(wf, scope, dim, inc, keep, pruned, looks=mylooks))
            continue
        cur = dist(cfg, "default" if scope == "all" else scope, dim)
        d = shares(inc, keep, mylooks)
        if tv(cur, d) > 0.04:
            up = [a for a in d if a != inc and d[a] > cur.get(a, 0) + 1e-9]
            intents.append({"type": "reallocate", "scope": scope, "dim": dim, "incumbent": inc, "arms": keep,
                            "dist": d, "auto_eligible": not up, "impact": 0.0,
                            "summary": f"test {dim} harder on the promising options: "
                                       + ", ".join(f"{a} {w:.0%}" for a, w in sorted(d.items())),
                            "rationale": "options with z>=1 so far get more traffic to reach a decision sooner; "
                                         + "; ".join(f"{x['arm']} {x['rel_lift']:+.1%} (n={x['n_arm']}, z={x['z']})"
                                                     for x in mylooks)})
    s.decide(now, wf.id, "daily_look", f"{len(looks)} arm comparisons, {len(tests)} eligible tests, "
                                        f"{sum(sig)} significant after Holm (alpha={ALPHA})",
             {"looks": looks, "tests": tests})
    return intents


def _promote_intent(wf, scope, dim, inc, t):
    lcb = (t["diff"] - 1.28 * (t["se"] or 0)) / t["rate_inc"] if t["rate_inc"] else 0
    return {"type": "promote", "scope": scope, "dim": dim, "winner": t["arm"], "incumbent": inc,
            "dist": {t["arm"]: 1 - HOLDOUT, inc: HOLDOUT}, "stats": t, "auto_eligible": False,
            "impact": max(lcb, 0) * 0.7, "lift": t["rel_lift"],
            "summary": f"promote {dim} {t['arm']} to {round(100 * (1 - HOLDOUT))}% "
                       f"({t['rel_lift']:+.1%} engagement vs {inc})" + (f" for cohort {scope}" if scope != "all" else ""),
            "rationale": f"{t['arm']} {t['rel_lift']:+.1%} engagement vs {inc} on {t['n_arm']} vs {t['n_inc']} "
                         f"connected calls, z={t['z']}, significant after Holm at alpha={ALPHA}; still ahead over the last 2 days "
                         f"({t.get('recent_lift', 0):+.1%}); pickup guardrail ok "
                         f"({t['pickup_diff']:+.3f}). {inc} keeps {round(100 * HOLDOUT)}% as a holdout to catch decay."}


def shares(inc, keep, looks) -> dict:
    """Incumbent plus surviving challengers: base share each, promising (z >= 1, n >= 200) ones get more."""
    ch = [a for a in keep if a != inc]
    if not ch:
        return {inc: 1.0}
    z = {x["arm"]: x for x in looks}
    good = [a for a in ch if a in z and z[a]["z"] >= 1 and z[a]["n_arm"] >= MIN_N_PRUNE
            and z[a].get("recent_lift", 1) > 0]
    base = min(EPS_ARM, EPS_TOTAL / len(ch))
    w = {a: (PROMISING_SHARE if a in good else base) for a in ch}
    tot = sum(w.values())
    if tot > EXPLORE_CAP:
        w = {a: v * EXPLORE_CAP / tot for a, v in w.items()}
    w[inc] = 1 - sum(w.values())
    return w


def _prune_intent(wf, scope, dim, inc, keep, pruned, safety=False, looks=()):
    d = shares(inc, keep, [x for x in looks if x["arm"] in keep])
    names = ", ".join(f"{p['arm']} ({p['rel_lift']:+.1%}, n={p['n_arm']}, z={p['z']})" for p in pruned)
    return {"type": "prune", "scope": scope, "dim": dim, "incumbent": inc, "arms": keep, "dist": d,
            "stats": pruned, "auto_eligible": not any(d.get(a, 0) > EPS_ARM for a in keep if a != inc),
            "safety": safety,
            "impact": sum(max(-p["rel_lift"], 0) for p in pruned) * EPS_ARM,
            "summary": f"stop {dim} {', '.join(p['arm'] for p in pruned)} (worse than {inc})",
            "rationale": f"{names} vs {inc}: " + ("safety stop, >10% worse with 99% confidence" if safety else
                                                  "likely worse (z < -1) or no sign of a lift after "
                                                  f"{MAX_EXPLORE_DAYS} days; its traffic goes back to the known-good "
                                                  "option")}
