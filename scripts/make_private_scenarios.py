"""Generate private test scenarios from public_01 (same schema, different truth/policy/incidents).

These exist only to evaluate the controller away from the public truth. The controller never reads them.
    python scripts/make_private_scenarios.py   -> scenarios/private/*.yaml
"""
import copy
from pathlib import Path

import yaml

src = yaml.safe_load(open("scenarios/public_01_dev.yaml"))
out = Path("scenarios/private")
out.mkdir(parents=True, exist_ok=True)


def wf(sc, wid):
    return next(w for t in sc["tenants"] for w in t["workflows"] if w["id"] == wid)


def save(name, sc):
    sc["name"] = name
    yaml.safe_dump(sc, open(out / f"{name}.yaml", "w"), sort_keys=False)


# 1. A/A: nothing works better than anything else. Every promotion is a false winner.
aa = copy.deepcopy(src)
aa["seed"], aa["effects"] = 911, []
for t in aa["tenants"]:
    for w in t["workflows"]:
        w["did_base_health"] = {}
save("priv_aa", aa)
for seed in range(921, 927):  # more A/A worlds: the false-winner rate needs more than one run
    aa["seed"] = seed
    save(f"priv_aa_{seed}", copy.deepcopy(aa))
aa["seed"] = 911

# 2. Policy flip: tighter governance everywhere.
pf = copy.deepcopy(src)
pf["seed"] = 912
k = wf(pf, "ks_cancel")["governance"]
k.update(auto_apply={"enabled": False, "allowed_dims": [], "max_shift": 0}, approver_hours=[12, 16],
         proposal_ttl_hours=6, max_requests_per_24h=2)
r = wf(pf, "nw_renewal")
r["mid_flight"] = "next_campaign_only"
r["governance"].update(max_requests_per_24h=1, approver_latency_minutes=[60, 300])
save("priv_policy", pf)

# 3. Incidents shuffled: caller ID flagged in the evening, a night-time persuasive prompt, a strict-script edit.
inc = copy.deepcopy(src)
inc["seed"] = 913
wf(inc, "ks_cancel")["options"]["prompt_version"] = ["P1", "P3", "P4", "P5"]
inc["incidents"] = [
    {"type": "did_flagged", "workflow": "nw_renewal", "did": "D1", "at": "D1 18:00", "base_health": 0.3},
    {"type": "supervisor_edit", "workflow": "nw_renewal", "at": "D2 22:00", "patch": {"prompt_version": "P4"},
     "note": "night-time persuasive prompt"},
    {"type": "supervisor_edit", "workflow": "ks_cancel", "at": "D4 12:00", "patch": {"prompt_version": "P5"},
     "note": "strict script: safe but kills engagement"},
    {"type": "supervisor_edit", "workflow": "nw_kyc", "at": "D3 09:00",
     "patch": {"allocations": {"default": {"voice": {"V2": 1}}}}, "note": "supervisor picks a voice"},
]
inc["prompts"]["P4"]["halluc"] = 0.04
save("priv_incidents", inc)

# 4. Opposite truth: last scenario's winners lose, a voice decays, effects live in other cohorts.
op = copy.deepcopy(src)
op["seed"] = 914
op["effects"] = [
    {"workflow": "nw_renewal", "dim": "voice", "value": "V3", "mult": 0.85},
    {"workflow": "nw_renewal", "dim": "voice", "value": "V2", "mult": 1.2,
     "decay": {"after_exposure_days": 2, "to_mult": 0.9, "over_days": 1}},
    {"workflow": "nw_renewal", "dim": "welcome_message", "value": "W3", "mult": 0.88},
    {"workflow": "nw_kyc", "dim": "voice", "value": "V2", "mult": 0.9},
    {"workflow": "ks_cancel", "dim": "welcome_message", "value": "W3", "mult": 1.15, "where": {"value_band": ["high", "mid"]}},
    {"workflow": "ks_cancel", "dim": "voice", "value": "V4", "mult": 0.85},
]
for t in op["tenants"]:
    for w in t["workflows"]:
        w["did_base_health"] = {"D3": 0.5} if w["id"] != "nw_kyc" else {"D2": 0.45}
save("priv_opposite", op)
print("wrote", sorted(p.name for p in out.glob("*.yaml")))
