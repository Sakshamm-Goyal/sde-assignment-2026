"""Governance client: every config change goes through here.

Proposal lifecycle (proposals.status):
  submitting -> pending -> approved -> applying -> applied
                        -> rejected | expired              (rebuilt from fresh data at the next planning slot)
             approved   -> superseded (base moved before apply) | lapsed (should never happen: alert)
  auto:   submitting -> applied | refused (403) | stale (409)
  crash:  submitting with no trace at the simulator -> abandoned (never blindly re-sent)

Outbox rule: the row is written (status 'submitting', deterministic id) BEFORE the HTTP call, so a restart can
always find out what happened via GET /approvals or GET /workflows/{id}/config/history.
"""
from __future__ import annotations

import json

from . import learn
from .cfg import AGENT_DIMS, DAY, ENG_DIMS, changed_dims, clean, dist, match, max_shift, set_dist
from .client import ApiError

OPEN = ("submitting", "pending", "approved", "applying")


class Gov:
    def __init__(self, ctl):
        self.ctl = ctl
        self.s = ctl.store

    # ------------------------------------------------------------------ queries
    def open_approval(self, wf_id) -> bool:
        return bool(self.s.one(f"SELECT 1 FROM proposals WHERE wf=? AND path='approval' AND status IN {OPEN}",
                               (wf_id,)))

    def requests_24h(self, wf_id) -> int:
        return self.s.one("SELECT COUNT(*) FROM proposals WHERE wf=? AND path='approval' AND approval_id IS NOT NULL "
                          "AND created_minute > ?", (wf_id, self.ctl.now - DAY))[0]

    def _new_id(self, wf_id) -> str:
        seq = self.s.meta("seq", 0) + 1
        self.s.set_meta("seq", seq)
        return f"{wf_id}-{seq:05d}"

    # ------------------------------------------------------------------ building
    @staticmethod
    def build(cfg: dict, intents: list[dict]) -> dict:
        new = clean(cfg)
        for it in intents:
            t = it["type"]
            if t in ("explore", "prune", "reallocate", "promote", "rollback", "end"):
                set_dist(new, "default" if it["scope"] == "all" else it["scope"], it["dim"], it["dist"])
            elif t == "did":
                set_dist(new, "default", "caller_id", it["dist"])
            elif t == "cohorts":
                ours = {c["id"] for c in it["cohorts"]}
                new["cohorts"] = [c for c in new["cohorts"] if c["id"] not in ours][: 20 - len(ours)] + it["cohorts"]
                new["schedule"]["hour_weights"].update(it["hour_weights"])
            elif t == "prompt":
                new["prompt_version"] = it["to"]
            elif t == "align":
                for c in it["cohorts"]:
                    (new["allocations"].get(c) or {}).pop(it["dim"], None)
                    if c in new["allocations"] and not new["allocations"][c]:
                        del new["allocations"][c]
        return new

    def _diff(self, old, new, dims):
        ch = []
        keys = {"default"} | {c["id"] for c in new["cohorts"]}
        for k in sorted(keys):
            for d in AGENT_DIMS:
                a, b = dist(old, k, d), dist(new, k, d)
                if a != b:
                    ch.append({"scope": k, "dim": d, "from": {o: round(w, 3) for o, w in a.items()},
                               "to": {o: round(w, 3) for o, w in b.items()}})
        out = {"changed_dims": dims, "allocations": ch}
        if "cohorts" in dims:
            out["cohorts"] = {"from": old["cohorts"], "to": new["cohorts"]}
        if "schedule" in dims:
            out["schedule_hour_weights"] = new["schedule"]["hour_weights"]
        if "prompt_version" in dims:
            out["prompt_version"] = {"from": old["prompt_version"], "to": new["prompt_version"]}
        return out

    def _affected(self, wf, old, new, dims) -> int:
        """Leads that will hear a different agent: still-dialable leads (+ tomorrow's batch), restricted to the
        cohorts whose distribution changed. next_campaign_only locks allocations, so only new campaigns count."""
        today = self.ctl.now // DAY
        active = self.s.one("SELECT COALESCE(SUM(leads - concluded), 0) FROM campaigns WHERE wf=? AND day > ?",
                            (wf.id, today - wf.cadence_days))[0]
        alloc_only = set(dims) <= set(AGENT_DIMS) | {"cohorts"}
        if alloc_only and wf.mid_flight == "next_campaign_only":
            active = 0
        if set(dims) & {"prompt_version", "schedule"}:
            return int(active + wf.batch)
        scopes = {k for k in {"default"} | {c["id"] for c in new["cohorts"]}
                  if any(dist(old, k, d) != dist(new, k, d) for d in AGENT_DIMS)}
        feats = self.s.q("SELECT feat, COUNT(*) FROM leads WHERE wf=? AND day >= ? GROUP BY feat",
                         (wf.id, today - 2))
        tot = sum(n for _, n in feats) or 1
        frac = sum(n for f, n in feats if match(new["cohorts"], f) in scopes) / tot if "cohorts" not in dims else 1.0
        return int(round((active + wf.batch) * frac))

    def _dry_run(self, wf, old, new, intents) -> dict:
        """Replay the last 3 days of realised traffic under old vs proposed allocation. Arms are scored only with
        evidence they actually collected; arms without it are listed, never assumed to be zero or positive."""
        s, today = self.s, self.ctl.now // DAY
        since = max(today - 3, 0)
        out = {"method": "replay of last 3 days of realised calls from the controller store; per-arm rates "
                         "relative to each dimension's pooled rate; arms with <100 connected calls count as 1.0",
               "window_days": [since, today]}
        tot = s.one("SELECT SUM(dials), SUM(connected), SUM(engaged) FROM eng WHERE wf=? AND day>=?", (wf.id, since))
        if not tot or not tot[0]:
            tot = s.one("SELECT SUM(dials), SUM(connected), SUM(engaged) FROM eng WHERE wf=? AND day<0", (wf.id,))
            out["window_days"] = "history (no live data yet)"
        D, C, G = (x or 0 for x in tot)
        out["calls"] = {"dials": D, "connected": C}
        base_eng = G / C if C else 0
        f_old = f_new = 1.0
        no_ev = []
        for dim in ENG_DIMS:
            col = "wm" if dim == "welcome_message" else "voice"
            rows = s.q(f"SELECT {col}, SUM(connected), SUM(engaged) FROM eng WHERE wf=? AND day>=0 GROUP BY {col}",
                       (wf.id,))
            pc = sum(r[1] for r in rows)
            pool = sum(r[2] for r in rows) / pc if pc else 0
            rel = {a: (g / c) / pool for a, c, g in rows if c >= 100 and pool}
            no_ev += [f"{dim}={a}" for a in dist(new, "default", dim) if a not in rel]
            f_old *= sum(w * rel.get(a, 1.0) for a, w in dist(old, "default", dim).items())
            f_new *= sum(w * rel.get(a, 1.0) for a, w in dist(new, "default", dim).items())
        out["engagement"] = {"recent": round(base_eng, 4), "predicted_current": round(base_eng * f_old, 4),
                             "predicted_proposed": round(base_eng * f_new, 4)}
        ratios = learn.did_ratios(s, wf.id, self.ctl.now - DAY)
        p_old = sum(w * ratios.get(d, (0, 0, 1.0, 0))[2] for d, w in dist(old, "default", "caller_id").items())
        p_new = sum(w * ratios.get(d, (0, 0, 1.0, 0))[2] for d, w in dist(new, "default", "caller_id").items())
        no_ev += [f"caller_id={d}" for d in dist(new, "default", "caller_id") if d not in ratios]
        out["pickup_relative"] = {"current": round(p_old, 3), "proposed": round(p_new, 3),
                                  "note": "caller-ID pickup relative to peers over the last 24h"}
        out["arms_without_evidence"] = sorted(set(no_ev))
        for it in intents:
            if it["type"] == "cohorts":
                out["call_time"] = {"history_model": it["evidence"], "predicted_pickup_gain": it["pred_gain"]}
            if it["type"] == "prompt":
                out["prompt"] = {"validation": it["validation"], "live_evidence": it.get("live")}
        feats = s.q("SELECT feat, COUNT(*) FROM leads WHERE wf=? AND day >= ? GROUP BY feat", (wf.id, since))
        sizes = {}
        for f, n in feats:
            k = match(new["cohorts"], f)
            sizes[k] = sizes.get(k, 0) + n
        out["leads_by_cohort_proposed"] = sizes
        return out

    # ------------------------------------------------------------------ submitting
    def submit(self, wf, cfg, version, intents, kind, evidence=None, force_approval=False):
        """Route and send one change. Returns proposal_id or None if there was nothing to change."""
        ctl = self.ctl
        new = self.build(cfg, intents)
        dims = changed_dims(cfg, new)
        if not dims:
            return None
        shift = max_shift(cfg, new)
        auto = (not force_approval and all(it.get("auto_eligible") for it in intents) and wf.auto_ok(dims, shift))
        summary = "; ".join(it["summary"] for it in intents)
        rationale = " | ".join(f"[{it['type']}] {it['rationale']}" for it in intents)
        impact = 1.0 if kind == "incident" else min(max(sum(it.get("impact", 0) for it in intents) / 0.10, 0), 1)
        with self.s.tx():
            pid = self._new_id(wf.id)
            if auto:
                body = {"proposal_id": pid, "base_version": version, "proposed_config": new, "rationale": rationale,
                        "evidence": evidence or {"summary": summary}}
            else:
                body = {"proposal_id": pid, "workflow_id": wf.id, "base_version": version, "proposed_config": new,
                        "change_summary": summary, "diff": self._diff(cfg, new, dims),
                        "affected_leads": self._affected(wf, cfg, new, dims),
                        "dry_run": self._dry_run(wf, cfg, new, intents), "impact_score": round(impact, 3),
                        "rationale": rationale, "evidence": evidence or {"stats": "see decisions for " + pid},
                        "expires_in_hours": wf.ttl_h}
            self.s.x("INSERT INTO proposals(proposal_id, wf, kind, path, status, base_version, config, body, intents, "
                     "created_minute) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (pid, wf.id, kind, "auto" if auto else "approval", "submitting", version, json.dumps(new),
                      json.dumps({k: v for k, v in body.items() if k != "proposed_config"}, default=str),
                      json.dumps(intents, default=str), ctl.now))
            self.s.decide(ctl.now, wf.id, "propose", f"{'auto-apply' if auto else 'approval request'}: {summary}",
                          {"dims": dims, "max_shift": round(shift, 3), "impact": impact, "intents": intents}, pid)
        try:
            if auto:
                r = ctl.sim.put(f"/workflows/{wf.id}/config", body)
                self.on_applied(pid, r["version"])
            else:
                r = ctl.sim.post("/approvals", body)
                self.s.x("UPDATE proposals SET status='pending', approval_id=? WHERE proposal_id=?",
                         (r["approval_id"], pid))
        except ApiError as e:
            self._submit_error(pid, wf.id, e, auto)
        return pid

    def _submit_error(self, pid, wf_id, e: ApiError, auto: bool):
        status = {"stale_base_version": "stale", "auto_apply_not_permitted": "refused",
                  "no_change": "invalid", "invalid_config": "invalid", "missing_fields": "invalid"}.get(e.code)
        if e.code == "duplicate_proposal_id":
            self.reconcile_one(pid)
            return
        if status is None:
            raise e
        self.s.x("UPDATE proposals SET status=?, reasons=? WHERE proposal_id=?", (status, json.dumps(e.detail), pid))
        self.s.decide(self.ctl.now, wf_id, f"proposal_{status}", f"{pid}: {e.code}", {"detail": e.detail}, pid)
        if status == "invalid":
            self.s.alert(self.ctl.now, "page", wf_id, f"simulator rejected our proposal {pid} as {e.code}: this is a "
                                                      f"controller bug. detail={e.detail}")

    def propose_incident(self, wf, cfg, d) -> str | None:
        ctl = self.ctl
        if not wf.auto_ok(["prompt_version"], 0) and not (wf.in_approver(ctl.now, routine=False)
                                                           and wf.decision_before_expiry(ctl.now, worst=False)):
            return None  # a request the approver can't see before it expires is wasted: wait for the window
        if self.requests_24h(wf.id) >= wf.policy_cap():
            ctl.store.alert(ctl.now, "page", wf.id, "hallucination fix blocked: approval budget for 24h used up")
            return None
        v = d["validation"]
        live = d.get("live_evidence")
        it = {"type": "prompt", "from": d["bad_prompt"], "to": d["candidate"], "auto_eligible": True,
              "validation": v, "live": live, "impact": 1.0,
              "summary": f"switch prompt {d['bad_prompt']} -> {d['candidate']} ({d.get('reason', 'hallucination')} incident)",
              "rationale": (f"engagement fell to {d['rate']:.1%} from {d['baseline']:.1%} on {d['bad_prompt']} "
                            if d.get("reason") == "engagement" else
                            f"hallucination flags at {d['rate']:.1%} on {d['bad_prompt']} vs {d['baseline']:.1%} baseline ")
                           + f"over {d['n']} connected calls. {d['candidate']} validated "
                           f"{v['pass_rate']:.3f} on n={v['n']} ({v['validation_run_id']}); "
                           + ("it ran live before with normal hallucination and engagement rates."
                              if live else "engagement will be verified after the change.")}
        return self.submit(wf, cfg, ctl.cfgs[wf.id]["version"], [it], "incident",
                           evidence={"validation_run_id": v["validation_run_id"]})

    # ------------------------------------------------------------------ deciding and applying
    def poll(self):
        ctl = self.ctl
        for pid, wf_id, status, aid in self.s.q(
                f"SELECT proposal_id, wf, status, approval_id FROM proposals WHERE path='approval' AND status IN "
                f"('pending','approved','applying')"):
            if status == "pending":
                a = ctl.sim.get(f"/approvals/{aid}")
                if a["status"] == "pending":
                    continue
                with self.s.tx():
                    self.s.x("UPDATE proposals SET status=?, reasons=?, decided_minute=? WHERE proposal_id=?",
                             (a["status"], json.dumps(a.get("reasons") or []), ctl.now, pid))
                    self.s.decide(ctl.now, wf_id, f"approval_{a['status']}",
                                  f"{aid} {a['status']}" + (f": {a.get('reasons')}" if a.get("reasons") else ""), a, pid)
                    if any("fatigue" in r for r in a.get("reasons") or []):
                        self.s.alert(ctl.now, "warn", wf_id, f"approver fatigue rejection on {aid}: batching bug")
                    kinds = {i["type"] for i in json.loads(self.s.one(
                        "SELECT intents FROM proposals WHERE proposal_id=?", (pid,))[0])}
                    if a["status"] in ("rejected", "expired") and kinds & {"rollback", "did"}:
                        ctl.replan(wf_id)  # protective changes are re-asked with fresh data the same day
                status = a["status"]
            if status in ("approved", "applying"):
                self.apply(pid, wf_id, aid)

    def apply(self, pid, wf_id, aid):
        ctl = self.ctl
        base = self.s.one("SELECT base_version FROM proposals WHERE proposal_id=?", (pid,))[0]
        cur = ctl.refresh_config(wf_id)
        if cur["version"] != base:
            self.s.x("UPDATE proposals SET status='superseded', note=? WHERE proposal_id=?",
                     (f"config moved to v{cur['version']} ({cur['actor']}) before apply", pid))
            self.s.decide(ctl.now, wf_id, "proposal_superseded", f"{pid} approved but base v{base} is now "
                                                                 f"v{cur['version']} ({cur['actor']}); will re-propose",
                          None, pid)
            ctl.replan(wf_id)
            return
        self.s.x("UPDATE proposals SET status='applying' WHERE proposal_id=?", (pid,))
        try:
            r = ctl.sim.post(f"/workflows/{wf_id}/apply", {"approval_id": aid})
        except ApiError as e:
            if e.code == "stale_base_version":
                self.s.x("UPDATE proposals SET status='superseded' WHERE proposal_id=?", (pid,))
                ctl.replan(wf_id)
            elif e.code == "approval_lapsed":
                self.s.x("UPDATE proposals SET status='lapsed' WHERE proposal_id=?", (pid,))
                self.s.alert(ctl.now, "page", wf_id, f"approved change {aid} lapsed before we applied it")
            elif e.code == "not_approved":
                self.reconcile_one(pid)
            else:
                raise
            return
        self.on_applied(pid, r["version"])

    def on_applied(self, pid, version):
        ctl, s = self.ctl, self.s
        wf_id, kind, path, aid, intents, cfg = s.one(
            "SELECT wf, kind, path, approval_id, intents, config FROM proposals WHERE proposal_id=?", (pid,))
        intents = json.loads(intents)
        now = ctl.now
        with s.tx():
            s.x("UPDATE proposals SET status='applied', applied_version=?, applied_minute=? WHERE proposal_id=?",
                (version, now, pid))
            for it in intents:
                self._effect(wf_id, it, now)
            s.x("INSERT INTO config_versions(wf, version, minute, actor, dims, proposal_id, approval_id, config, handled) "
                "VALUES(?,?,?,?,?,?,?,?,1) ON CONFLICT(wf, version) DO UPDATE SET config=excluded.config, handled=1",
                (wf_id, version, now, "controller_auto" if path == "auto" else "controller_approved",
                 json.dumps([]), pid, aid, cfg))
            s.decide(now, wf_id, "applied", f"v{version} via {'auto-apply' if path == 'auto' else aid}: "
                                            + "; ".join(it["summary"] for it in intents), {"version": version}, pid)
        ctl.refresh_config(wf_id)

    def _effect(self, wf_id, it, now):
        s, t = self.s, it["type"]
        if t == "explore":
            s.x("INSERT OR REPLACE INTO experiments VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (wf_id, "all", it["dim"], "exploring", it["incumbent"], ",".join(it["arms"]), None, now, None, None, now))
        elif t in ("prune", "reallocate"):
            s.x("UPDATE experiments SET arms=?, status=?, updated_minute=? WHERE wf=? AND scope=? AND dim=?",
                (",".join(it["arms"]), "exploring" if len(it["arms"]) > 1 else "done", now, wf_id, it["scope"], it["dim"]))
        elif t == "promote":
            s.x("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(wf, scope, dim) DO UPDATE SET "
                "status='promoted', winner=excluded.winner, promoted_minute=excluded.promoted_minute, "
                "promo_lift=excluded.promo_lift, updated_minute=excluded.updated_minute",
                (wf_id, it["scope"], it["dim"], "promoted", it["incumbent"], f"{it['winner']},{it['incumbent']}",
                 it["winner"], now, now, it.get("lift"), now))
        elif t in ("rollback", "end"):
            s.x("UPDATE experiments SET status=?, updated_minute=? WHERE wf=? AND scope=? AND dim=?",
                ("rolled_back" if t == "rollback" else "inconclusive", now, wf_id, it["scope"], it["dim"]))
        elif t == "did":
            for d, w in it["dist"].items():
                if w > 0:
                    s.x("INSERT INTO dids VALUES(?,?,?,?,?,?) ON CONFLICT(wf, did) DO UPDATE SET "
                        "status=CASE WHEN status='unused' THEN 'probe' ELSE status END, "
                        "since_minute=CASE WHEN status='unused' THEN excluded.since_minute ELSE since_minute END",
                        (wf_id, d, "probe", now, None, 0))
        elif t == "cohorts":
            for c in it["cohorts"]:
                s.x("INSERT OR REPLACE INTO cohorts VALUES(?,?,?,?,?,?,?)",
                    (wf_id, c["id"], json.dumps(c["where"]), "active", now, "controller", it["rationale"]))
            s.set_meta(f"cohorts_adopted:{wf_id}", True)
        elif t == "align":
            for c in it["cohorts"]:
                s.x("UPDATE experiments SET status='superseded', updated_minute=? WHERE wf=? AND scope=? AND dim=?",
                    (now, wf_id, c, it["dim"]))
            s.set_meta(f"pending_align:{wf_id}", [])

    # ------------------------------------------------------------------ crash recovery
    def reconcile(self):
        for (pid,) in self.s.q(f"SELECT proposal_id FROM proposals WHERE status IN {OPEN}"):
            self.reconcile_one(pid)

    def reconcile_one(self, pid):
        ctl, s = self.ctl, self.s
        wf_id, path, status, aid = s.one("SELECT wf, path, status, approval_id FROM proposals WHERE proposal_id=?", (pid,))
        if path == "auto":
            if status != "submitting":
                return
            hit = [v for v in ctl.sim.get(f"/workflows/{wf_id}/config/history") if v["proposal_id"] == pid]
            if hit:
                self.on_applied(pid, hit[0]["version"])
            else:
                s.x("UPDATE proposals SET status='abandoned' WHERE proposal_id=?", (pid,))
            s.decide(ctl.now, wf_id, "reconcile", f"{pid} auto-apply {'found applied' if hit else 'never arrived'}",
                     None, pid)
            return
        if aid is None:
            hit = [a for a in ctl.sim.get("/approvals", params={"workflow_id": wf_id}) if a["proposal_id"] == pid]
            if not hit:
                s.x("UPDATE proposals SET status='abandoned' WHERE proposal_id=?", (pid,))
                s.decide(ctl.now, wf_id, "reconcile", f"{pid} never reached the approver; abandoned", None, pid)
                return
            aid = hit[0]["approval_id"]
            s.x("UPDATE proposals SET approval_id=? WHERE proposal_id=?", (aid, pid))
        a = ctl.sim.get(f"/approvals/{aid}")
        if a["status"] == "applied":
            hit = [v for v in ctl.sim.get(f"/workflows/{wf_id}/config/history") if v["approval_id"] == aid]
            self.on_applied(pid, hit[0]["version"])
        elif a["status"] in ("approved", "pending"):
            s.x("UPDATE proposals SET status=? WHERE proposal_id=?", (a["status"], pid))
        else:
            s.x("UPDATE proposals SET status=?, reasons=? WHERE proposal_id=?",
                (a["status"], json.dumps(a.get("reasons") or []), pid))
        s.decide(ctl.now, wf_id, "reconcile", f"{pid} ({aid}) is {a['status']} at the simulator", a, pid)
