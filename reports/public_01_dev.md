# Grade report — public_01_dev

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.390 | +14.1% | 0.262 | +7.0% | 0.516 | +5.0% | 19% | 50 (57) |
| nw_kyc | 0.414 | +12.9% | 0.268 | +10.9% | 0.600 | +0.5% | 6% | 26 (21) |
| nw_renewal | 0.459 | +10.3% | 0.286 | +8.3% | 0.549 | +1.4% | 6% | 47 (54) |
| ALL | 0.418 | +12.4% | 0.271 | +8.2% | 0.544 | +2.8% | 11% | 123 (132) |

## Changes applied by the controller

14 applied — neutral: 8, beneficial: 6

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- ks_cancel v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.021 didΔ=+0.000 → **beneficial**
- ks_cancel v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- ks_cancel v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.023 → **beneficial**
- ks_cancel v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.010 → **neutral**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.018 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.033 → **beneficial**
- ks_cancel v6 (controller_auto) dims=['welcome_message'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- nw_renewal v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- ks_cancel v7 (controller_approved) dims=['voice'] engageΔ=+0.016 didΔ=+0.000 → **beneficial**
- ks_cancel v8 (controller_approved) dims=['voice'] engageΔ=+0.046 didΔ=+0.000 → **beneficial**
- nw_renewal v6 (controller_approved) dims=['voice'] engageΔ=+0.001 didΔ=+0.000 → **neutral**
- nw_kyc v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.372 → **beneficial**

## Governance

```
{
  "approval_requests": 13,
  "decisions": {
    "approved": 7,
    "rejected": 6,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 6
  },
  "applied_via_approval": 7,
  "auto_applied": 7,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 1,
    "nw_kyc": 1,
    "ks_cancel": 1
  }
}
```

## Incidents

```
[]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:welcome_message=W3": {
    "3": 0.098,
    "4": 0.102,
    "5": 0.101,
    "6": 0.106,
    "7": 0.101
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0