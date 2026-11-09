"""Event ingestion: chunk -> cubes/leads/calls, exactly once.

Each chunk is folded in memory and written in ONE transaction together with its checkpoint row, so a crash
either keeps the whole chunk or none of it. Replaying a chunk is impossible (checkpoint) and harmless anyway
(calls are keyed by event_id).
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections import defaultdict

from .cfg import DAY, feat_key

UPSERT = {
    "eng": "INSERT INTO eng VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(wf, day, feat, wm, voice, prompt) DO UPDATE SET "
           "dials=dials+excluded.dials, connected=connected+excluded.connected, engaged=engaged+excluded.engaged, "
           "flags=flags+excluded.flags",
    "pick": "INSERT INTO pick VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(wf, day, hour, feat, did) DO UPDATE SET "
            "dials=dials+excluded.dials, connected=connected+excluded.connected, engaged=engaged+excluded.engaged",
    "ticks": "INSERT INTO ticks VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(wf, minute, did, prompt) DO UPDATE SET "
             "dials=dials+excluded.dials, connected=connected+excluded.connected, engaged=engaged+excluded.engaged, "
             "flags=flags+excluded.flags",
}
UNKNOWN = "?|?|?|?"


class Ingestor:
    def __init__(self, store, sim, epoch: dt.datetime, keep_days: int):
        self.s, self.sim, self.epoch, self.keep_days = store, sim, epoch, keep_days
        self.lead_feat: dict[str, str] = {}
        self.by_day: dict[int, list[str]] = defaultdict(list)
        self._ts: dict[str, int] = {}
        self.changed_wfs: set[str] = set()
        self.events_total = 0
        self.max_day = None

    def minute(self, ts: str) -> int:
        m = self._ts.get(ts)
        if m is None:
            if len(self._ts) > 200_000:
                self._ts.clear()
            m = int((dt.datetime.fromisoformat(ts) - self.epoch).total_seconds() // 60)
            self._ts[ts] = m
        return m

    def load_cache(self):
        """Rebuild the lead->features join for campaigns that can still be dialled (after a restart)."""
        last = self.s.one("SELECT MAX(day) FROM leads")[0]
        if last is None:
            return
        for lid, feat, day in self.s.q("SELECT lead_id, feat, day FROM leads WHERE day >= ?", (last - self.keep_days,)):
            self.lead_feat[lid] = feat
            self.by_day[day].append(lid)
        self.max_day = last

    def pending(self) -> list[dict]:
        last = self.s.one("SELECT MAX(chunk) FROM chunks")[0]
        last = -1 if last is None else last
        out = []
        for kind in ("history", "events"):
            out += self.sim.get("/events/chunks", params={"kind": kind, "after": last})
        return sorted(out, key=lambda c: c["chunk"])

    def run(self) -> int:
        n = 0
        for meta in self.pending():
            n += self.ingest(meta)
        return n

    def _prune(self, day: int):
        if self.max_day is None or day > self.max_day:
            self.max_day = day
            for d in [d for d in self.by_day if d < day - self.keep_days]:
                for lid in self.by_day.pop(d):
                    self.lead_feat.pop(lid, None)

    def ingest(self, meta: dict) -> int:
        live = meta["kind"] == "events"
        eng = defaultdict(lambda: [0, 0, 0, 0])
        pick = defaultdict(lambda: [0, 0, 0])
        ticks = defaultdict(lambda: [0, 0, 0, 0])
        calls, leads, camps, cfgs = [], [], [], []
        concluded = defaultdict(int)
        lf = self.lead_feat
        n = 0
        for line in self.sim.stream_chunk(meta["chunk"]):
            e = json.loads(line)
            n += 1
            t = e["type"]
            if t == "call":
                m = self.minute(e["ts"])
                day, hour = m // DAY, (m % DAY) // 60
                v = e["variant"]
                wf = e["workflow_id"]
                feat = lf.get(e["lead_id"], UNKNOWN)
                c, g = e["connected"], e["engaged"]
                fl = 1 if (c and e["qa"] and e["qa"].get("hallucination_flag")) else 0
                a = eng[(wf, day, feat, v["welcome_message"], v["voice"], v["prompt_version"])]
                a[0] += 1; a[1] += c; a[2] += g; a[3] += fl
                b = pick[(wf, day, hour, feat, v["caller_id"])]
                b[0] += 1; b[1] += c; b[2] += g
                k = ticks[(wf, m - m % 15, v["caller_id"], v["prompt_version"])]
                k[0] += 1; k[1] += c; k[2] += g; k[3] += fl
                if g:
                    concluded[e["campaign_id"]] += 1
                if live:
                    calls.append((e["event_id"], m, wf, e["lead_id"], e["person_id"], e["campaign_id"],
                                  e["config_version"], e["cohort_id"], v["welcome_message"], v["voice"],
                                  v["caller_id"], v["prompt_version"], e["disposition"], fl))
            elif t == "lead":
                m = self.minute(e["ts"])
                feat = feat_key(e["features"])
                lf[e["lead_id"]] = feat
                self.by_day[m // DAY].append(e["lead_id"])
                leads.append((e["lead_id"], e["workflow_id"], e["campaign_id"], e["person_id"], feat, m // DAY))
            elif t == "campaign_created":
                m = self.minute(e["ts"])
                camps.append((e["campaign_id"], e["workflow_id"], m // DAY, m, e["leads"],
                              e["config_version_at_creation"]))
                self._prune(m // DAY)
            elif t == "config_changed":
                m = self.minute(e["ts"])
                cfgs.append((e["workflow_id"], e["version"], m, e["actor"], json.dumps(e["changed_dims"]),
                             e.get("proposal_id"), e.get("approval_id")))
                self.changed_wfs.add(e["workflow_id"])
            # approval_decided: governance polls /approvals itself (one code path for decisions)
        s = self.s
        with s.tx():
            s.many("INSERT OR IGNORE INTO campaigns(campaign_id, wf, day, minute, leads, cfg_ver) VALUES(?,?,?,?,?,?)",
                   camps)
            s.many("INSERT OR IGNORE INTO leads VALUES(?,?,?,?,?,?)", leads)
            s.many(UPSERT["eng"], [(*k, *v) for k, v in eng.items()])
            s.many(UPSERT["pick"], [(*k, *v) for k, v in pick.items()])
            s.many(UPSERT["ticks"], [(*k, *v) for k, v in ticks.items()])
            s.many("UPDATE campaigns SET concluded = concluded + ? WHERE campaign_id = ?",
                   [(v, k) for k, v in concluded.items()])
            s.many("INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", calls)
            s.many("INSERT OR IGNORE INTO config_versions(wf, version, minute, actor, dims, proposal_id, approval_id)"
                   " VALUES(?,?,?,?,?,?,?)", cfgs)
            s.x("INSERT INTO chunks VALUES(?,?,?,?,?,?)", (meta["chunk"], meta["kind"], n, meta["last_event_id"],
                                                          meta["until_minute"], time.time()))
        self.events_total += n
        return n
