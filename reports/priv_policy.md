# Grade report — priv_policy

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.376 | +11.2% | 0.260 | +7.5% | 0.502 | +1.9% | 4% | 58 (60) |
| nw_kyc | 0.427 | +14.1% | 0.274 | +13.1% | 0.600 | -1.6% | 6% | 43 (26) |
| nw_renewal | 0.437 | +7.6% | 0.272 | +4.3% | 0.548 | +2.3% | 3% | 47 (50) |
| ALL | 0.407 | +10.5% | 0.267 | +7.4% | 0.538 | +1.4% | 4% | 148 (136) |

## Changes applied by the controller

17 applied — neutral: 10, beneficial: 7

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.032 → **beneficial**
- ks_cancel v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=-0.001 didΔ=+0.007 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- ks_cancel v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.041 → **beneficial**
- ks_cancel v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.017 → **neutral**
- ks_cancel v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.005 didΔ=+0.000 → **neutral**
- nw_renewal v5 (controller_approved) dims=['welcome_message'] engageΔ=+0.019 didΔ=+0.000 → **beneficial**
- nw_kyc v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.382 → **beneficial**
- nw_renewal v6 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v6 (controller_approved) dims=['voice'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- nw_kyc v4 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- nw_renewal v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- nw_kyc v5 (controller_approved) dims=['voice'] engageΔ=-0.007 didΔ=+0.000 → **neutral**
- nw_renewal v8 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.018 didΔ=+0.000 → **beneficial**
- ks_cancel v7 (controller_approved) dims=['welcome_message'] engageΔ=-0.003 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 15,
  "decisions": {
    "approved": 14,
    "rejected": 1,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 1
  },
  "applied_via_approval": 14,
  "auto_applied": 3,
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
    "4": 0.094,
    "5": 0.158,
    "6": 0.21,
    "7": 0.257
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0