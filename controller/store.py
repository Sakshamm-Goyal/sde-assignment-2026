"""SQLite store: the controller's only state. One file, WAL, single writer.

Analysis never reads raw calls: it reads three small aggregate cubes
  eng   (wf, day, feat, welcome, voice, prompt)      -> welcome/voice experiments, dry runs
  pick  (wf, day, hour, feat, caller_id)              -> call-time, cohorts
  ticks (wf, 15-min bucket, caller_id, prompt)        -> caller-ID health, hallucination, before/after
`calls` keeps one row per live dial so "what did customer X hear on day D, and why" is answerable.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS chunks(chunk INTEGER PRIMARY KEY, kind TEXT, events INTEGER, last_event_id INTEGER,
  until_minute INTEGER, wall REAL);
CREATE TABLE IF NOT EXISTS workflows(wf TEXT PRIMARY KEY, tenant TEXT, spec TEXT);
CREATE TABLE IF NOT EXISTS campaigns(campaign_id TEXT PRIMARY KEY, wf TEXT, day INTEGER, minute INTEGER,
  leads INTEGER, concluded INTEGER DEFAULT 0, cfg_ver INTEGER);
CREATE TABLE IF NOT EXISTS leads(lead_id TEXT PRIMARY KEY, wf TEXT, campaign_id TEXT, person_id TEXT, feat TEXT,
  day INTEGER);
CREATE INDEX IF NOT EXISTS leads_day ON leads(day);
CREATE TABLE IF NOT EXISTS eng(wf TEXT, day INTEGER, feat TEXT, wm TEXT, voice TEXT, prompt TEXT,
  dials INTEGER, connected INTEGER, engaged INTEGER, flags INTEGER, PRIMARY KEY(wf, day, feat, wm, voice, prompt));
CREATE TABLE IF NOT EXISTS pick(wf TEXT, day INTEGER, hour INTEGER, feat TEXT, did TEXT,
  dials INTEGER, connected INTEGER, engaged INTEGER, PRIMARY KEY(wf, day, hour, feat, did));
CREATE TABLE IF NOT EXISTS ticks(wf TEXT, minute INTEGER, did TEXT, prompt TEXT,
  dials INTEGER, connected INTEGER, engaged INTEGER, flags INTEGER, PRIMARY KEY(wf, minute, did, prompt));
CREATE TABLE IF NOT EXISTS calls(event_id INTEGER PRIMARY KEY, minute INTEGER, wf TEXT, lead_id TEXT,
  person_id TEXT, campaign_id TEXT, cfg_ver INTEGER, cohort TEXT, wm TEXT, voice TEXT, did TEXT, prompt TEXT,
  outcome TEXT, halluc_flag INTEGER);
CREATE INDEX IF NOT EXISTS calls_person ON calls(person_id);
CREATE TABLE IF NOT EXISTS config_versions(wf TEXT, version INTEGER, minute INTEGER, actor TEXT, dims TEXT,
  proposal_id TEXT, approval_id TEXT, config TEXT, handled INTEGER DEFAULT 0, PRIMARY KEY(wf, version));
CREATE TABLE IF NOT EXISTS cohorts(wf TEXT, cohort_id TEXT, where_json TEXT, status TEXT, minute INTEGER,
  source TEXT, reason TEXT, PRIMARY KEY(wf, cohort_id));
CREATE TABLE IF NOT EXISTS experiments(wf TEXT, scope TEXT, dim TEXT, status TEXT, incumbent TEXT, arms TEXT,
  winner TEXT, start_minute INTEGER, promoted_minute INTEGER, promo_lift REAL, updated_minute INTEGER,
  PRIMARY KEY(wf, scope, dim));
CREATE TABLE IF NOT EXISTS dids(wf TEXT, did TEXT, status TEXT, since_minute INTEGER, ratio REAL, dials INTEGER,
  PRIMARY KEY(wf, did));
CREATE TABLE IF NOT EXISTS proposals(proposal_id TEXT PRIMARY KEY, wf TEXT, kind TEXT, path TEXT, status TEXT,
  base_version INTEGER, config TEXT, body TEXT, intents TEXT, approval_id TEXT, created_minute INTEGER,
  decided_minute INTEGER, applied_version INTEGER, applied_minute INTEGER, reasons TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, minute INTEGER, wf TEXT, type TEXT,
  summary TEXT, data TEXT, proposal_id TEXT);
CREATE INDEX IF NOT EXISTS decisions_wf ON decisions(wf, minute);
CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY AUTOINCREMENT, wf TEXT, kind TEXT, status TEXT,
  opened_minute INTEGER, closed_minute INTEGER, data TEXT);
CREATE TABLE IF NOT EXISTS spend(id INTEGER PRIMARY KEY AUTOINCREMENT, minute INTEGER, wf TEXT, what TEXT,
  cost REAL, ref TEXT);
CREATE TABLE IF NOT EXISTS metrics(minute INTEGER PRIMARY KEY, wall REAL, events INTEGER, ingest_s REAL,
  decide_s REAL, advance_s REAL, credits REAL, pending INTEGER, rss_mb REAL);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, minute INTEGER, severity TEXT, wf TEXT,
  message TEXT);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript(SCHEMA)
        self._depth = 0

    @contextmanager
    def tx(self):
        """Nested-safe transaction: only the outermost level commits."""
        if self._depth == 0:
            self.db.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.db.execute("ROLLBACK")
            raise
        self._depth -= 1
        if self._depth == 0:
            self.db.execute("COMMIT")

    def x(self, sql, args=()):
        return self.db.execute(sql, args)

    def many(self, sql, rows):
        self.db.executemany(sql, rows)

    def q(self, sql, args=()):
        return self.db.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.db.execute(sql, args).fetchone()

    def meta(self, k, default=None):
        r = self.one("SELECT v FROM meta WHERE k=?", (k,))
        return json.loads(r[0]) if r else default

    def set_meta(self, k, v):
        self.x("INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))

    def decide(self, minute, wf, type_, summary, data=None, proposal_id=None):
        self.x("INSERT INTO decisions(minute, wf, type, summary, data, proposal_id) VALUES(?,?,?,?,?,?)",
               (minute, wf, type_, summary, json.dumps(data or {}, default=str), proposal_id))

    def alert(self, minute, severity, wf, message):
        self.x("INSERT INTO alerts(minute, severity, wf, message) VALUES(?,?,?,?)", (minute, severity, wf, message))
