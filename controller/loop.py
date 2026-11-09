"""The controller loop: advance -> ingest -> governance -> detect -> plan, one simulated tick at a time.

Single process, single writer. All state is in SQLite; kill -9 at any line and `run` again resumes.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import resource
import sys
import time

from . import incidents, learn
from .cfg import AGENT_DIMS, DAY, WF, dist, toward, tv
from .client import Sim
from .governance import Gov
from .ingest import Ingestor
from .store import Store

ORDER = ["rollback", "promote", "prune", "reallocate", "end", "explore"]
COOL = {"welcome_message": 2 * DAY, "voice": 2 * DAY, "caller_id": DAY, "prompt_version": DAY,
        "schedule": DAY, "cohorts": DAY}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3


class Controller:
    def __init__(self, url=None, state_dir="state", http=None, verbose=True):
        self.sim = Sim(url, http)
        self.state_dir = state_dir
        self.verbose = verbose
        self.now = 0
        self.credits = 0.0
        self.cfgs: dict[str, dict] = {}

    # ------------------------------------------------------------------ setup
    def setup(self):
        self.sim.wait_ready()
        st = self.sim.get("/sim/state")
        os.makedirs(self.state_dir, exist_ok=True)
        path = os.path.join(self.state_dir, f"{st['scenario']}.db")
        hist = self.sim.get("/events/chunks", params={"kind": "history"})
        world = f"{st['scenario']}:{hist[-1]['last_event_id'] if hist else 0}"
        if os.path.exists(path):
            old = Store(path)
            same = old.meta("world") == world and old.meta("last_minute", -10 ** 9) <= st["sim_minute"]
            old.db.close()
            if not same:  # a fresh simulator world: keep the old store for forensics, start clean
                os.replace(path, f"{path}.{int(time.time())}.old")
                for ext in ("-wal", "-shm"):
                    if os.path.exists(path + ext):
                        os.remove(path + ext)
        self.store = Store(path)
        self.store.set_meta("world", world)
        self.now = st["sim_minute"]
        self.tick = st["tick_minutes"]
        self.end = st["end_minute"]
        epoch = dt.datetime.fromisoformat(st["ts"]) - dt.timedelta(minutes=st["sim_minute"])
        self.wfs = {w["workflow_id"]: WF(w) for w in self.sim.get("/workflows")}
        with self.store.tx():
            for w in self.wfs.values():
                self.store.x("INSERT OR REPLACE INTO workflows VALUES(?,?,?)", (w.id, w.tenant, json.dumps(w.spec)))
        self.ingest = Ingestor(self.store, self.sim, epoch, max(w.cadence_days for w in self.wfs.values()) + 1)
        self.ingest.load_cache()
        self.gov = Gov(self)
        for wid in self.wfs:
            self.refresh_config(wid)
            self.store.x("INSERT OR IGNORE INTO config_versions(wf, version, minute, actor, dims, config, handled) "
                         "VALUES(?,?,?,?,?,?,1)", (wid, self.cfgs[wid]["version"], self.now, self.cfgs[wid]["actor"],
                                                   "[]", json.dumps(self.cfgs[wid]["config"])))
        log(f"[ctl] {st['scenario']} at {st['ts']} — {len(self.wfs)} workflows, store {path}")

    def refresh_config(self, wf_id) -> dict:
        c = self.sim.get(f"/workflows/{wf_id}/config")
        self.cfgs[wf_id] = c
        self.store.x("UPDATE config_versions SET config=? WHERE wf=? AND version=? AND config IS NULL",
                     (json.dumps(c["config"]), wf_id, c["version"]))
        return c

    # ------------------------------------------------------------------ helpers used by modules
    def cooling(self, wf_id, dim) -> bool:
        return self.store.meta(f"cool:{wf_id}:{dim}", -1) > self.now

    def spent(self, wf_id, what, cost, ref):
        self.credits -= cost
        self.store.x("INSERT INTO spend(minute, wf, what, cost, ref) VALUES(?,?,?,?,?)", (self.now, wf_id, what, cost, ref))

    def replan(self, wf_id):
        self.store.set_meta(f"plan_day:{wf_id}", None)

    # ------------------------------------------------------------------ main loop
    def run(self):
        self.setup()
        self.gov.reconcile()
        t_adv = 0.0
        while True:
            st = self.sim.get("/sim/state")
            self.now, self.credits = st["sim_minute"], st["credits_remaining"]
            t0 = time.time()
            n = self.ingest.run()
            t1 = time.time()
            for wid in sorted(self.ingest.changed_wfs):
                self.refresh_config(wid)
            self.ingest.changed_wfs.clear()
            self.handle_config_changes()
            if not self.store.meta("bootstrapped"):
                self.bootstrap()
            self.gov.poll()
            for wf in self.wfs.values():
                self.decide(wf)
            t2 = time.time()
            self.health(n, t1 - t0, t2 - t1, t_adv)
            if st["finished"]:
                break
            step = self.next_step()
            t3 = time.time()
            self.sim.advance(step)
            t_adv = time.time() - t3
        self.store.decide(self.now, None, "finished", "scenario finished", {"credits_remaining": self.credits})
        log(f"[ctl] finished at minute {self.now}; credits left {self.credits}")

    def next_step(self) -> int:
        mod = self.now % DAY
        busy = any(w.in_window(self.now) or w.approver[0] * 60 <= mod < w.approver[1] * 60 for w in self.wfs.values())
        if busy:
            return self.tick
        bounds = sorted({h * 60 for w in self.wfs.values() for h in (w.window[0], w.approver[0])})
        nxt = next((b for b in bounds if b > mod), bounds[0] + DAY)
        step = nxt - mod
        return max(self.tick, step - step % self.tick)

    # ------------------------------------------------------------------ bootstrap from history
    def bootstrap(self):
        s = self.store
        with s.tx():
            for wf in self.wfs.values():
                used = {d for (d,) in s.q("SELECT DISTINCT did FROM ticks WHERE wf=? AND minute<0", (wf.id,))}
                for d in wf.options["caller_id"]:
                    s.x("INSERT OR IGNORE INTO dids VALUES(?,?,?,?,?,?)",
                        (wf.id, d, "active" if d in used else "unused", self.now, None, None))
                plan = learn.propose_cohorts(s, wf)
                if plan:
                    for c in plan["cohorts"]:
                        s.x("INSERT OR IGNORE INTO cohorts VALUES(?,?,?,?,?,?,?)",
                            (wf.id, c["id"], json.dumps(c["where"]), "candidate", self.now, "history",
                             f"hourly pickup differs by {plan['feature']} (z={plan['evidence']['z']})"))
                    s.set_meta(f"cohort_plan:{wf.id}", plan)
                base, eng = incidents.baseline(s, wf.id)
                s.decide(self.now, wf.id, "bootstrap",
                         f"history: flag rate {base:.2%}, engagement {eng:.1%}, caller IDs used {sorted(used)}, "
                         + (f"cohorts by {plan['feature']}: {[c['id'] for c in plan['cohorts']]}" if plan
                            else "no cohort structure found"), {"cohort_plan": plan})
            s.set_meta("bootstrapped", True)

    # ------------------------------------------------------------------ supervisor edits
    def handle_config_changes(self):
        s = self.store
        for wf_id, version, actor, dims in s.q("SELECT wf, version, actor, dims FROM config_versions WHERE handled=0 "
                                               "ORDER BY minute"):
            dims = json.loads(dims or "[]")
            with s.tx():
                s.x("UPDATE config_versions SET handled=1 WHERE wf=? AND version=?", (wf_id, version))
                if actor != "supervisor":
                    continue
                cfg = self.cfgs[wf_id]["config"]
                for d in dims:
                    s.set_meta(f"cool:{wf_id}:{d}", self.now + COOL.get(d, DAY))
                hit = s.q("SELECT scope, dim FROM experiments WHERE wf=? AND status IN ('exploring','promoted')",
                          (wf_id,))
                sup = [(sc, d) for sc, d in hit if d in dims]
                for sc, d in sup:
                    s.x("UPDATE experiments SET status='superseded', updated_minute=? WHERE wf=? AND scope=? AND dim=?",
                        (self.now, wf_id, sc, d))
                # our cohort-level overrides would hide the supervisor's new default: ask, never silently pick
                masked = [{"dim": d, "cohorts": [c["id"] for c in cfg["cohorts"]
                                                 if d in (cfg["allocations"].get(c["id"]) or {})]}
                          for d in dims if d in AGENT_DIMS]
                masked = [m for m in masked if m["cohorts"]]
                if masked:
                    s.set_meta(f"pending_align:{wf_id}", masked)
                s.decide(self.now, wf_id, "supervisor_edit",
                         f"supervisor changed {dims} (v{version}); our experiments on those dims stopped "
                         f"{sup}; no proposal touches them for the cool-down period"
                         + (f"; cohort overrides mask the edit: {masked}" if masked else ""),
                         {"version": version, "dims": dims, "config": cfg})
                self.replan(wf_id)

    # ------------------------------------------------------------------ per-workflow decisions
    def decide(self, wf: WF):
        s, now = self.store, self.now
        c = self.cfgs[wf.id]
        cfg, ver = c["config"], c["version"]
        if wf.in_window(now) or wf.in_window(now - 60):
            incidents.check(self, wf, cfg)
        incidents.step(self, wf, cfg)
        cfg, ver = self.cfgs[wf.id]["config"], self.cfgs[wf.id]["version"]
        if wf.in_window(now):
            self.caller_id(wf, cfg, ver)
            cfg, ver = self.cfgs[wf.id]["config"], self.cfgs[wf.id]["version"]
            if (now % 120) == 0 and self._auto_allowed(wf):
                its = learn.evaluate(self, wf, cfg, intraday=True)
                if its:
                    self.gov.submit(wf, cfg, ver, its, "safety")
        today = now // DAY
        if (wf.in_approver(now) and s.meta(f"plan_day:{wf.id}") != today and not self.gov.open_approval(wf.id)
                and not s.one("SELECT 1 FROM incidents WHERE wf=? AND status IN ('ready','fixing')", (wf.id,))
                and self.gov.requests_24h(wf.id) < wf.bundle_cap() and wf.decision_before_expiry(now)):
            self.plan(wf, *[self.cfgs[wf.id][k] for k in ("config", "version")])

    def _auto_allowed(self, wf) -> bool:
        return not self.gov.open_approval(wf.id) and self.store.meta(f"auto_refused:{wf.id}", -1) < self.now

    def caller_id(self, wf, cfg, ver):
        target, urgent, notes = learn.did_plan(self, wf, cfg)
        if not target:
            return
        it = self._did_intent(wf, cfg, target, urgent)
        if urgent or self._auto_allowed(wf):
            # move toward the target in policy-sized steps; an urgent move may stale a pending request (logged)
            step = dict(it)
            if wf.auto.get("enabled") and "caller_id" in wf.auto.get("allowed_dims", []):
                step["dist"] = toward(dist(cfg, "default", "caller_id"), target, wf.auto.get("max_shift", 0))
                if wf.auto_ok(["caller_id"], tv(dist(cfg, "default", "caller_id"), step["dist"])):
                    pid = self.gov.submit(wf, cfg, ver, [step], "caller_id")
                    st = self.store.one("SELECT status FROM proposals WHERE proposal_id=?", (pid,)) if pid else None
                    if st and st[0] == "refused":
                        self.store.set_meta(f"auto_refused:{wf.id}", self.now + 6 * 60)
                    return
            if urgent and wf.in_approver(self.now, routine=False) and self.gov.requests_24h(wf.id) < wf.policy_cap() \
                    and not self.store.meta(f"did_urgent_sent:{wf.id}") == self.now // DAY:
                self.store.set_meta(f"did_urgent_sent:{wf.id}", self.now // DAY)
                self.gov.submit(wf, cfg, ver, [it], "incident", force_approval=True)

    def _did_intent(self, wf, cfg, target, urgent):
        ratios = learn.did_ratios(self.store, wf.id, self.now - DAY)
        cur = dist(cfg, "default", "caller_id")
        rel = lambda d: sum(w * ratios.get(k, (0, 0, 1.0, 0))[2] for k, w in d.items())
        gain = rel(target) / max(rel(cur), 1e-9) - 1
        weight = 1.0 if wf.primary == "pickup_rate" else 0.5
        desc = ", ".join(f"{k} {w:.0%}" for k, w in sorted(target.items()))
        st = dict(self.store.q("SELECT did, status FROM dids WHERE wf=?", (wf.id,)))
        return {"type": "did", "dist": target, "auto_eligible": True, "impact": max(gain, 0) * weight,
                "summary": f"caller IDs -> {desc}",
                "rationale": ("caller ID flagged: " if urgent else "") +
                             f"states {st}; spreading dials over healthy caller IDs keeps each one's load (and spam "
                             f"risk) low; untested IDs get a small probe share first. Expected relative pickup "
                             f"{gain:+.1%} from last-24h caller-ID ratios"}

    def plan(self, wf, cfg, ver):
        """Once per day per workflow: one bundled request with everything we want to change."""
        s, now = self.store, self.now
        intents = []
        plan = s.meta(f"cohort_plan:{wf.id}")
        if plan and not s.meta(f"cohorts_adopted:{wf.id}") and not self.cooling(wf.id, "cohorts") \
                and not self.cooling(wf.id, "schedule"):
            intents.append({"type": "cohorts", "cohorts": plan["cohorts"], "hour_weights": plan["hour_weights"],
                            "evidence": plan["evidence"], "pred_gain": plan["pred_pickup_gain"],
                            "auto_eligible": False, "impact": plan["pred_pickup_gain"] * (1.0 if wf.primary ==
                                                                                       "pickup_rate" else 0.5),
                            "summary": f"add cohorts {[c['id'] for c in plan['cohorts']]} (no change to what they hear) "
                                       f"and call each cohort in its better hours",
                            "rationale": f"history ({plan['evidence']['history_dials']} dials) shows pickup-by-hour "
                                         f"differs by {plan['feature']} (chi2 z={plan['evidence']['z']}); weights by "
                                         f"comparative advantage, floor 0.2 so nobody is starved; predicted pickup "
                                         f"{plan['pred_pickup_gain']:+.1%} (conservative)"})
        target, urgent, _ = learn.did_plan(self, wf, cfg)
        if target:
            intents.append(self._did_intent(wf, cfg, target, urgent))
        intents += learn.evaluate(self, wf, cfg)
        for m in s.meta(f"pending_align:{wf.id}", []) or []:
            intents.append({"type": "align", "dim": m["dim"], "cohorts": m["cohorts"], "auto_eligible": False,
                            "impact": 0.0, "summary": f"apply your new default {m['dim']} to cohorts {m['cohorts']} too",
                            "rationale": "a supervisor changed the default; our cohort-level settings would otherwise "
                                         "keep those cohorts on the old choice. Reject to keep the cohort settings."})
        self.drift(wf)
        if not intents:
            s.decide(now, wf.id, "plan", "nothing worth changing today")
            s.set_meta(f"plan_day:{wf.id}", now // DAY)
            return
        # keep promotions/rollbacks of a dimension from colliding with its own prune/explore in one bundle
        seen, uniq = set(), []
        for it in sorted(intents, key=lambda i: ORDER.index(i["type"]) if i["type"] in ORDER else -1):
            key = (it.get("scope"), it.get("dim")) if it.get("dim") else (it["type"], id(it))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        pid = self.gov.submit(wf, cfg, ver, uniq, "bundle")
        s.set_meta(f"plan_day:{wf.id}", now // DAY)
        if pid is None:
            s.decide(now, wf.id, "plan", "intents produced no config change")

    def drift(self, wf):
        """Alert-only: yesterday's pickup/engagement vs the 3 days before (population level, z > 4)."""
        s, today = self.store, self.now // DAY
        if today < 2:
            return
        rows = {d: (x, c, g) for d, x, c, g in s.q(
            "SELECT minute/1440, SUM(dials), SUM(connected), SUM(engaged) FROM ticks WHERE wf=? AND minute>=? AND "
            "minute<? GROUP BY minute/1440", (wf.id, (today - 4) * DAY, today * DAY))}
        y = rows.get(today - 1)
        prev = [rows[d] for d in range(today - 4, today - 1) if d in rows]
        if not y or not prev:
            return
        for name, (a, b) in {"pickup": (0, 1), "engagement": (1, 2)}.items():
            n0, x0 = sum(p[a] for p in prev), sum(p[b] for p in prev)
            n1, x1 = y[a], y[b]
            if not n0 or not n1:
                continue
            p0, p1 = x0 / n0, x1 / n1
            z = (p1 - p0) / math.sqrt(max(p0 * (1 - p0), 1e-6) * (1 / n0 + 1 / n1))
            if abs(z) > 4:
                s.decide(self.now, wf.id, "kpi_drift", f"{name} {p1:.3f} yesterday vs {p0:.3f} prior 3 days (z={z:.1f})")
                s.alert(self.now, "info", wf.id, f"{name} drift {p0:.3f} -> {p1:.3f} (z={z:.1f}); morning review")

    # ------------------------------------------------------------------ loop health
    def health(self, n, ingest_s, decide_s, adv_s):
        s = self.store
        pending = s.one("SELECT COUNT(*) FROM proposals WHERE status IN ('pending','approved','applying')")[0]
        s.x("INSERT OR REPLACE INTO metrics VALUES(?,?,?,?,?,?,?,?,?)",
            (self.now, time.time(), n, round(ingest_s, 3), round(decide_s, 3), round(adv_s, 3), self.credits,
             pending, round(rss_mb(), 1)))
        s.set_meta("last_minute", self.now)
        last = s.one("SELECT MAX(until_minute) FROM chunks WHERE kind='events'")[0]
        if last is not None and self.now - last > 60 and n == 0 and self.now > 0:
            s.alert(self.now, "page", None, f"ingest lag {self.now - last} sim-minutes: chunks not arriving")
        if self.credits < 8 and not s.meta("alert_credits"):
            s.set_meta("alert_credits", True)
            s.alert(self.now, "page", None, f"credits at {self.credits}: below the incident reserve")
        if self.verbose and self.now % (6 * 60) == 0:
            d, mod = divmod(self.now, DAY)
            log(f"[ctl] D{d} {mod // 60:02d}:{mod % 60:02d} events+{n} ingest {ingest_s:.2f}s decide {decide_s:.2f}s "
                f"credits {self.credits:.0f} pending {pending} rss {rss_mb():.0f}MB")
