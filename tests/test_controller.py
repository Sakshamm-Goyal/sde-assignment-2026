"""Controller tests: only where logic can silently break. Run: python -m pytest -q tests

The tests may import `sim` (they are not the controller); the controller itself never does.
"""
import copy
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from controller import cfg as C
from controller import stats
from controller.governance import Gov
from controller.loop import Controller
from controller.store import Store
from sim import server
from sim.scenario import FEATURES, load_scenario
from sim.world import World, changed_dims as sim_changed_dims, normalise_config


def test_stats():
    assert stats.holm([0.001, 0.02, 0.04], 0.05) == [True, True, True]
    assert stats.holm([0.03, 0.02, 0.5], 0.05) == [False, False, False]
    d, se, *_ = stats.strat_diff([(1000, 600, 1000, 500)])
    assert abs(d - 0.1) < 1e-9 and 0.02 < se < 0.025
    # stratification: a mix shift between strata must not create an arm effect
    d, *_ = stats.strat_diff([(900, 90, 100, 10), (100, 50, 900, 450)])
    assert abs(d) < 1e-9


def test_per_mille_round_trip_never_invents_a_change(tmp_path):
    sc = load_scenario("scenarios/public_01_dev.yaml")
    wf = next(w for t in sc["tenants"] for w in t["workflows"] if w["id"] == "nw_renewal")
    cur = normalise_config(wf, wf["default_config"] | {"cohorts": [], "schedule": {}})
    for weights in ({"V1": 0.7, "V2": 0.1, "V3": 0.1, "V4": 0.1}, {"V1": 1, "V2": 1, "V3": 1}, {"V2": 0.123456, "V4": 0.9}):
        new = Gov.build(cur, [{"type": "explore", "scope": "all", "dim": "voice", "dist": weights}])
        applied = normalise_config(wf, new)                      # what the simulator stores
        again = normalise_config(wf, Gov.build(applied, []))    # we re-send it unchanged
        assert sim_changed_dims(applied, again) == []
        assert C.changed_dims(cur, new) == sim_changed_dims(cur, normalise_config(wf, new)) == ["voice"]


def test_cohort_match_parity_with_simulator(tmp_path):
    sc = load_scenario("scenarios/public_01_dev.yaml")
    sc["days"], sc["history_days"] = 1, 1
    w = World(sc, tmp_path / "run").wfs["nw_renewal"]
    cohorts = [{"id": "sen_ta", "where": {"age_band": ["60+"], "lang": ["ta"]}},
               {"id": "young", "where": {"age_band": ["18-30"]}},
               {"id": "rich", "where": {"value_band": ["high"], "city_tier": ["1", "2"]}}]
    conf = normalise_config(w.spec, {"cohorts": cohorts, "allocations": w.current["config"]["allocations"],
                                     "prompt_version": "P1"})
    import numpy as np
    idx = np.arange(min(w.persons.n, 3000))
    sim_ids = w.cohort_of(conf, idx)
    names = ["default"] + [c["id"] for c in cohorts]
    for i, p in enumerate(idx):
        feats = {f: FEATURES[f][int(w.persons.c[f][p])] for f in FEATURES}
        assert C.match(cohorts, C.feat_key(feats)) == names[sim_ids[i]]


def test_toward_respects_max_shift():
    t = C.toward({"D1": 0.5, "D2": 0.5}, {"D1": 0.5, "D3": 0.5}, 0.2)
    assert C.tv({"D1": 0.5, "D2": 0.5}, C.norm(C.per_mille(t))) <= 0.2


# ----------------------------------------------------------------------------- end to end, in process
def _tiny(tmp_path, days=2):
    sc = yaml.safe_load(open("scenarios/public_02_incidents.yaml"))
    sc["days"], sc["history_days"] = days, 3
    sc["incidents"] = [i for i in sc["incidents"] if i["at"].startswith(("D0", "D1"))] + [
        {"type": "did_flagged", "workflow": "ks_cancel", "did": "D1", "at": "D0 12:00", "base_health": 0.3}]
    p = tmp_path / "sc.yaml"
    yaml.safe_dump(sc, open(p, "w"))
    server._world = None
    world = server.init_world(str(p), str(tmp_path / "run"))
    return world, TestClient(server.app)


class Crash(Exception):
    pass


def test_crash_between_apply_and_record_resumes_without_double_apply(tmp_path, monkeypatch):
    world, http = _tiny(tmp_path, days=2)
    state = tmp_path / "state"
    orig = Gov.on_applied
    crashed = {"n": 0}

    def flaky(self, pid, version):
        # the simulator applied the change, but we die before writing it down
        if crashed["n"] == 0 and self.s.one("SELECT path FROM proposals WHERE proposal_id=?", (pid,))[0] == "approval":
            crashed["n"] += 1
            raise Crash()
        return orig(self, pid, version)

    monkeypatch.setattr(Gov, "on_applied", flaky)
    with pytest.raises(Crash):
        Controller(state_dir=str(state), http=http, verbose=False).run()
    assert crashed["n"] == 1
    monkeypatch.setattr(Gov, "on_applied", orig)
    Controller(state_dir=str(state), http=http, verbose=False).run()   # restart: reconcile + finish
    assert world.state()["finished"]
    s = Store(str(next(state.glob("*.db"))))
    # every simulator-side version we caused is recorded exactly once, and nothing is left in flight
    for wid, w in world.wfs.items():
        ours = [v for v in w.versions if v["actor"].startswith("controller")]
        assert len({v["proposal_id"] for v in ours}) == len(ours)
        recorded = {r[0] for r in s.q("SELECT applied_version FROM proposals WHERE wf=? AND status='applied'", (wid,))}
        assert {v["version"] for v in ours} == recorded
    assert not s.q("SELECT 1 FROM proposals WHERE status IN ('submitting','applying')")
    # exactly-once ingestion
    assert s.one("SELECT SUM(events) FROM chunks")[0] == world.event_seq
    # the flagged caller ID was moved off
    flagged = s.one("SELECT status FROM dids WHERE wf='ks_cancel' AND did='D1'")[0]
    assert flagged in ("flagged", "rested")
    # audit: every applied controller change can be explained
    from controller import view
    v = max(r[0] for r in s.q("SELECT applied_version FROM proposals WHERE status='applied' AND wf='ks_cancel'"))
    m = s.one("SELECT applied_minute FROM proposals WHERE wf='ks_cancel' AND applied_version=?", (v,))[0]
    out = view.why(s, "ks_cancel", m)
    assert f"v{v}" in out and "decision trail" in out
