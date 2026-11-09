"""Workflow policy wrapper and config arithmetic.

Config semantics mirror docs/SIMULATOR.md §3: cohorts are first-match, a cohort that omits a dimension uses
`default`, weights are normalised. We always write allocation weights as integer per-mille so the simulator's
normalisation is exact and re-sending an unchanged dimension never shows up as a change.
"""
from __future__ import annotations

import copy

FEATS = ("lang", "city_tier", "age_band", "value_band")
AGENT_DIMS = ("welcome_message", "voice", "caller_id")
ENG_DIMS = ("welcome_message", "voice")
CHANGE_DIMS = ("cohorts", "welcome_message", "voice", "caller_id", "prompt_version", "schedule")
DAY = 1440

# Client agreements that are stricter than the simulator's policy (stakeholders/04). Business config, not
# simulator truth: if a tenant isn't listed, the API policy is all we use.
TENANT_PREFS = {
    "kestrel_finance": {"earliest_hour": 11, "max_requests_per_day": 2},
}


def feat_key(features: dict) -> str:
    return "|".join(str(features.get(f, "?")) for f in FEATS)


def feat_dict(key: str) -> dict:
    return dict(zip(FEATS, key.split("|")))


def match(cohorts: list[dict], key: str) -> str:
    fd = feat_dict(key)
    for c in cohorts:
        if all(fd.get(f) in vals for f, vals in c["where"].items()):
            return c["id"]
    return "default"


def norm(d: dict) -> dict:
    s = float(sum(d.values()))
    return {k: float(v) / s for k, v in d.items() if v > 0}


def per_mille(d: dict) -> dict:
    """Largest-remainder rounding to integers summing to 1000 (zeros dropped)."""
    d = {k: v for k, v in d.items() if v > 0}
    s = sum(d.values())
    raw = {k: 1000 * v / s for k, v in d.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: 1000 - sum(out.values())]:
        out[k] += 1
    return {k: v for k, v in sorted(out.items()) if v > 0}


def dist(cfg: dict, scope: str, dim: str) -> dict:
    return norm((cfg["allocations"].get(scope) or {}).get(dim) or cfg["allocations"]["default"][dim])


def tv(a: dict, b: dict) -> float:
    return 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b))


def set_dist(cfg: dict, scope: str, dim: str, d: dict):
    cfg["allocations"].setdefault(scope, {})[dim] = per_mille(d)


def changed_dims(old: dict, new: dict) -> list[str]:
    ch = set()
    if old["cohorts"] != new["cohorts"]:
        ch.add("cohorts")
    keys = set(old["allocations"]) | set(new["allocations"])
    for dim in AGENT_DIMS:
        if any(dist(old, k, dim) != dist(new, k, dim) for k in keys):
            ch.add(dim)
    if old["prompt_version"] != new["prompt_version"]:
        ch.add("prompt_version")
    if old.get("schedule") != new.get("schedule"):
        ch.add("schedule")
    return [d for d in CHANGE_DIMS if d in ch]


def max_shift(old: dict, new: dict) -> float:
    keys = {"default"} | {c["id"] for c in old["cohorts"]} | {c["id"] for c in new["cohorts"]}
    return max(tv(dist(old, k, d), dist(new, k, d)) for k in keys for d in AGENT_DIMS)


def toward(cur: dict, target: dict, max_tv: float) -> dict:
    """Move a distribution toward target by at most max_tv total-variation distance."""
    gap = tv(cur, target)
    if gap <= max_tv + 1e-9:
        return dict(target)
    a = (max_tv - 0.002) / gap  # stay strictly inside the policy cap after per-mille rounding
    keys = set(cur) | set(target)
    return {k: cur.get(k, 0) + a * (target.get(k, 0) - cur.get(k, 0)) for k in keys}


def clean(cfg: dict) -> dict:
    """Deep copy with every allocation rewritten in per-mille integers."""
    c = copy.deepcopy(cfg)
    for scope, dims in c["allocations"].items():
        for dim, w in list(dims.items()):
            dims[dim] = per_mille(w)
    c.setdefault("schedule", {"hour_weights": {}, "lead_preferred_hour": {}})
    c["schedule"].setdefault("hour_weights", {})
    c["schedule"].setdefault("lead_preferred_hour", {})
    return c


class WF:
    """Read-only view of one workflow's public spec and policy (GET /workflows/{id})."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.id = spec["workflow_id"]
        self.tenant = spec["tenant_id"]
        self.options = spec["options"]
        self.window = spec["dialling_window"]
        self.gov = spec["governance"]
        self.auto = self.gov.get("auto_apply") or {"enabled": False, "allowed_dims": [], "max_shift": 0}
        self.approver = self.gov["approver_hours"]
        self.ttl_h = self.gov["proposal_ttl_hours"]
        self.lat = self.gov["approver_latency_minutes"]
        self.min_val = self.gov.get("min_validation_pass_rate", 0.97)
        self.mid_flight = spec.get("mid_flight", "allowed")
        self.cadence_days = len(spec["cadence"])
        self.batch = spec["daily_batch"]["size"]
        obj = spec["objective"]
        self.primary = obj["primary"]
        g = obj.get("guardrail") or {}
        self.guard_kpi, self.guard_drop = next(iter(g.items()), ("", 0.02))
        self.prefs = TENANT_PREFS.get(self.tenant, {})

    # --- policy
    def auto_ok(self, dims, shift) -> bool:
        a = self.auto
        return bool(a.get("enabled")) and bool(dims) and all(d in a.get("allowed_dims", []) for d in dims) \
            and shift <= a.get("max_shift", 0) + 1e-9

    def policy_cap(self) -> int:
        return int(self.gov["max_requests_per_24h"])

    def bundle_cap(self) -> int:
        """Daily courtesy budget for routine bundles; one policy slot is always kept back for incidents."""
        cap = min(self.policy_cap(), self.prefs.get("max_requests_per_day", 99))
        return max(1, min(cap, self.policy_cap() - 1))

    def plan_hour(self) -> int:
        return max(self.approver[0], self.prefs.get("earliest_hour", 0))

    # --- clock
    def in_window(self, minute: int) -> bool:
        h = (minute % DAY) // 60
        return self.window[0] <= h < self.window[1]

    def in_approver(self, minute: int, routine: bool = True) -> bool:
        h = (minute % DAY) // 60
        lo = self.plan_hour() if routine else self.approver[0]
        return lo <= h < self.approver[1]

    def decision_before_expiry(self, minute: int, worst: bool = True) -> bool:
        """Will the approver decide before the request's TTL runs out? Routine requests assume the slowest
        approver; incidents accept the median (an expired request only costs one slot)."""
        mod = minute % DAY
        lat = self.lat[1] if worst else (self.lat[0] + self.lat[1]) / 2
        if mod + lat < self.approver[1] * 60:
            return True
        next_open = (minute // DAY + 1) * DAY + self.approver[0] * 60
        return next_open <= minute + self.ttl_h * 60


if __name__ == "__main__":
    assert per_mille({"a": 1, "b": 1, "c": 1}) == {"a": 334, "b": 333, "c": 333}
    assert norm(per_mille({"x": 0.7, "y": 0.3})) == norm(per_mille(norm(per_mille({"x": 0.7, "y": 0.3}))))
    c = [{"id": "sen", "where": {"age_band": ["60+"], "lang": ["ta"]}}, {"id": "young", "where": {"age_band": ["18-30"]}}]
    assert match(c, "ta|1|60+|low") == "sen" and match(c, "hi|1|60+|low") == "default"
    assert match(c, "ta|1|18-30|low") == "young"
    t = toward({"D1": 0.5, "D2": 0.5}, {"D1": 0.5, "D3": 0.5}, 0.2)
    assert tv({"D1": 0.5, "D2": 0.5}, t) <= 0.2
    print("cfg ok")
