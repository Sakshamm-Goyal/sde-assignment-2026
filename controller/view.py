"""Read-only views over the store: supervisor screen, `why` audit query, loop health. Never calls the simulator."""
from __future__ import annotations

import json

from .cfg import AGENT_DIMS, DAY, dist


def fmt(m) -> str:
    if m is None:
        return "-"
    d, mod = divmod(int(m), DAY)
    return f"D{d} {mod // 60:02d}:{mod % 60:02d}"


def parse_at(s: str) -> int:
    day, hm = s.strip().split()
    h, m = hm.split(":")
    return int(day.lstrip("Dd")) * DAY + int(h) * 60 + int(m)


def kpis(s, wf, a, b):
    r = s.one("SELECT SUM(dials), SUM(connected), SUM(engaged), SUM(flags) FROM ticks WHERE wf=? AND minute>=? AND "
              "minute<?", (wf, a, b))
    d, c, g, f = (x or 0 for x in r)
    return {"dials": d, "pickup": round(c / d, 4) if d else None, "engagement": round(g / c, 4) if c else None,
            "halluc_flag_rate": round(f / c, 4) if c else None}


def _alloc(cfg, scope):
    return " | ".join(f"{d}: " + " ".join(f"{o} {w:.0%}" for o, w in sorted(dist(cfg, scope, d).items()))
                      for d in AGENT_DIMS)


def supervisor(s, wf_filter=None) -> str:
    now = s.meta("last_minute", 0)
    today = now // DAY
    L = [f"# Supervisor view — {fmt(now)}", ""]
    for wf, tenant, spec in s.q("SELECT wf, tenant, spec FROM workflows ORDER BY wf"):
        if wf_filter and wf != wf_filter:
            continue
        spec = json.loads(spec)
        ver = s.one("SELECT version, actor, minute, config FROM config_versions WHERE wf=? AND config IS NOT NULL "
                    "ORDER BY version DESC LIMIT 1", (wf,))
        cfg = json.loads(ver[3])
        L += [f"## {wf} ({tenant}) — primary {spec['objective']['primary']}, guardrail "
              f"{spec['objective'].get('guardrail')}",
              f"config v{ver[0]} by {ver[1]} at {fmt(ver[2])}; prompt {cfg['prompt_version']}; "
              f"cohorts {[c['id'] for c in cfg['cohorts']] or 'none'}",
              f"- default: {_alloc(cfg, 'default')}"]
        for c in cfg["cohorts"]:
            if cfg["allocations"].get(c["id"]):
                L.append(f"- {c['id']}: {_alloc(cfg, c['id'])}")
        t, y = kpis(s, wf, today * DAY, now), kpis(s, wf, (today - 1) * DAY, today * DAY)
        L.append(f"- today: pickup {t['pickup']} engagement {t['engagement']} flags {t['halluc_flag_rate']} "
                 f"({t['dials']} dials) · yesterday: pickup {y['pickup']} engagement {y['engagement']}")
        L.append("**What's being tested / what's winning**")
        look = s.one("SELECT data, minute FROM decisions WHERE wf=? AND type='daily_look' ORDER BY id DESC LIMIT 1", (wf,))
        looks = {(x["scope"], x["dim"], x["arm"]): x for x in json.loads(look[0])["looks"]} if look else {}
        for scope, dim, status, inc, arms, winner, start, prom, lift in s.q(
                "SELECT scope, dim, status, incumbent, arms, winner, start_minute, promoted_minute, promo_lift "
                "FROM experiments WHERE wf=?", (wf,)):
            line = f"- {dim} [{scope}] {status}: incumbent {inc}"
            if winner:
                line += f", winner {winner} ({lift:+.1%} at promotion {fmt(prom)})"
            arms_s = [f"{a}: {x['rel_lift']:+.1%} (n={x['n_arm']}, z={x['z']})"
                      for (sc, d, a), x in looks.items() if sc == scope and d == dim]
            L.append(line + (f" — latest look {fmt(look[1])}: " + "; ".join(arms_s) if arms_s else ""))
        dids = s.q("SELECT did, status, ratio, dials FROM dids WHERE wf=?", (wf,))
        L.append("- caller IDs: " + ", ".join(f"{d} {st}" + (f" ({r:.0%} of peers)" if r else "") for d, st, r, _ in dids))
        L.append("**Waiting on you**")
        for pid, aid, body, created in s.q("SELECT proposal_id, approval_id, body, created_minute FROM proposals WHERE "
                                           "wf=? AND status IN ('pending','approved')", (wf,)):
            b = json.loads(body)
            L.append(f"- {aid} ({fmt(created)}, impact {b.get('impact_score')}, {b.get('affected_leads')} leads): "
                     f"{b.get('change_summary')}")
        L.append("**Changed today**")
        for v, actor, m in s.q("SELECT version, actor, minute FROM config_versions WHERE wf=? AND minute>=? "
                               "ORDER BY version", (wf, today * DAY)):
            why = s.one("SELECT summary FROM decisions WHERE wf=? AND type IN ('applied','supervisor_edit') AND "
                        "summary LIKE ? ORDER BY id DESC LIMIT 1", (wf, f"%v{v}%"))
            L.append(f"- v{v} {fmt(m)} by {actor}: {why[0] if why else ''}")
        for iid, kind, st, o, c, data in s.q("SELECT id, kind, status, opened_minute, closed_minute, data FROM incidents "
                                             "WHERE wf=? AND (closed_minute IS NULL OR closed_minute>=?)", (wf, now - DAY)):
            d = json.loads(data)
            L.append(f"- incident #{iid} {kind} {st}: opened {fmt(o)} ({d.get('bad_prompt')} flags {d.get('rate')} vs "
                     f"{d.get('baseline')}), closed {fmt(c)}")
        L.append("")
    return "\n".join(L)


def why(s, wf, at: int) -> str:
    v = s.one("SELECT version, minute, actor, dims, proposal_id, approval_id FROM config_versions WHERE wf=? AND "
              "minute<=? ORDER BY version DESC LIMIT 1", (wf, at))
    if not v:
        return f"no config change on {wf} at or before {fmt(at)}"
    version, m, actor, dims, pid, aid = v
    L = [f"{wf} at {fmt(at)} was running config v{version}, applied {fmt(m)} by {actor}"]
    if actor == "supervisor":
        d = s.one("SELECT summary FROM decisions WHERE wf=? AND type='supervisor_edit' AND minute>=? ORDER BY id LIMIT 1",
                  (wf, m))
        L.append(f"  supervisor edit (bypasses governance): {d[0] if d else dims}")
    if pid:
        p = s.one("SELECT kind, path, approval_id, created_minute, decided_minute, applied_minute, body, intents "
                  "FROM proposals WHERE proposal_id=?", (pid,))
        if p:
            kind, path, aid, cm, dm, am, body, intents = p
            b = json.loads(body)
            L += [f"  proposal {pid} ({kind}) via {'auto-apply within policy' if path == 'auto' else 'approval ' + str(aid)}",
                  f"  requested {fmt(cm)}, decided {fmt(dm)}, applied {fmt(am)}",
                  f"  what: {b.get('change_summary') or '; '.join(i['summary'] for i in json.loads(intents))}",
                  f"  why: {b.get('rationale')}",
                  f"  impact {b.get('impact_score')}, affected leads {b.get('affected_leads')}"]
            if path == "approval":
                L.append(f"  approved by: the {wf} client approver (simulated) — decision {aid}")
        L.append("  decision trail:")
        for dm, typ, summ in s.q("SELECT minute, type, summary FROM decisions WHERE proposal_id=? ORDER BY id", (pid,)):
            L.append(f"    {fmt(dm)} {typ}: {summ}")
    ctx = s.q("SELECT minute, type, summary FROM decisions WHERE wf=? AND minute BETWEEN ? AND ? AND type IN "
              "('daily_look','incident_opened','caller_id_flagged','validation','supervisor_edit','incident_verify')"
              " ORDER BY id", (wf, m - DAY, m))
    if ctx:
        L.append("  evidence in the 24h before:")
        L += [f"    {fmt(dm)} {typ}: {summ}" for dm, typ, summ in ctx[-8:]]
    nxt = s.one("SELECT version, minute, actor FROM config_versions WHERE wf=? AND version>? ORDER BY version LIMIT 1",
                (wf, version))
    end = nxt[1] if nxt else m + DAY
    before, after = kpis(s, wf, m - DAY, m), kpis(s, wf, m, min(end, m + DAY))
    L += [f"  what happened next (24h before vs after, or until the next change):",
          f"    before: {before}", f"    after:  {after}"]
    if nxt:
        L.append(f"  next change: v{nxt[0]} at {fmt(nxt[1])} by {nxt[2]}")
    return "\n".join(L)


def heard(s, person_id: str) -> str:
    """Compliance question: what did this customer hear, when, and why was that variant live?"""
    L = []
    for m, wf, ver, coh, wm, voice, did, prompt, out in s.q(
            "SELECT minute, wf, cfg_ver, cohort, wm, voice, did, prompt, outcome FROM calls WHERE person_id=? "
            "ORDER BY minute", (person_id,)):
        v = s.one("SELECT actor, proposal_id FROM config_versions WHERE wf=? AND version=?", (wf, ver))
        L.append(f"{fmt(m)} {wf} cfg v{ver} cohort {coh}: welcome {wm}, voice {voice}, caller {did}, prompt {prompt} "
                 f"-> {out}; config by {v[0] if v else '?'} ({v[1] if v and v[1] else 'no proposal'})")
    return "\n".join(L) or "no calls for that person"


def status(s) -> str:
    rows = s.q("SELECT minute, events, ingest_s, decide_s, advance_s, credits, pending, rss_mb FROM metrics ORDER BY minute")
    if not rows:
        return "no metrics yet"
    ev = sum(r[1] for r in rows)
    ing = sum(r[2] for r in rows) or 1e-9
    dec = sorted(r[3] for r in rows)
    first, last = rows[0], rows[-1]
    days = max((last[0] - max(first[0], 0)) / DAY, 1e-9)
    wall = s.one("SELECT MAX(wall) - MIN(wall) FROM metrics WHERE minute >= 0")[0] or 0
    L = [f"sim time {fmt(last[0])}; ticks {len(rows)}; events ingested {ev:,} at {ev / ing:,.0f} events/s",
         f"decide time per tick p50 {dec[len(dec) // 2]:.3f}s p95 {dec[int(len(dec) * .95)]:.3f}s max {dec[-1]:.3f}s",
         f"wall-clock per simulated day {wall / days / 60:.2f} min (incl. simulator); peak RSS {max(r[7] for r in rows):.0f} MB",
         f"credits remaining {last[5]}; spent {s.one('SELECT COALESCE(SUM(cost),0) FROM spend')[0]}",
         f"pending approvals {last[6]}; decisions/sim-hour {s.one('SELECT COUNT(*) FROM decisions')[0] / max(last[0] / 60, 1):.1f}",
         "proposals: " + ", ".join(f"{st} {n}" for st, n in s.q("SELECT status, COUNT(*) FROM proposals GROUP BY status"))]
    al = s.q("SELECT minute, severity, wf, message FROM alerts ORDER BY id DESC LIMIT 15")
    if al:
        L.append("alerts (latest first):")
        L += [f"  {fmt(m)} [{sev}] {wf or '-'}: {msg}" for m, sev, wf, msg in al]
    return "\n".join(L)
