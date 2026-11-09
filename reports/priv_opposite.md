# Grade report — priv_opposite

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.353 | +3.5% | 0.246 | +0.2% | 0.503 | +2.4% | 3% | 49 (69) |
| nw_kyc | 0.393 | +7.9% | 0.261 | +8.8% | 0.589 | -1.1% | -24% | 37 (21) |
| nw_renewal | 0.444 | +7.1% | 0.283 | +9.0% | 0.537 | -2.3% | -13% | 50 (39) |
| ALL | 0.392 | +5.7% | 0.261 | +5.0% | 0.532 | +0.1% | -6% | 136 (129) |

## Changes applied by the controller

18 applied — neutral: 10, harmful: 1, beneficial: 7

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.020 → **neutral**
- ks_cancel v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.020 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.009 didΔ=+0.000 → **neutral**
- ks_cancel v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=-0.010 didΔ=+0.003 → **harmful**
- ks_cancel v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.026 → **beneficial**
- nw_renewal v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.043 → **beneficial**
- ks_cancel v5 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- nw_renewal v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.012 didΔ=+0.000 → **beneficial**
- nw_renewal v7 (controller_approved) dims=['voice'] engageΔ=-0.008 didΔ=+0.000 → **neutral**
- nw_kyc v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.199 → **beneficial**
- ks_cancel v6 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v4 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.022 → **beneficial**
- nw_renewal v8 (controller_approved) dims=['voice'] engageΔ=+0.026 didΔ=+0.000 → **beneficial**
- ks_cancel v7 (controller_auto) dims=['welcome_message'] engageΔ=-0.007 didΔ=+0.000 → **neutral**
- nw_kyc v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nw_renewal v9 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 12,
  "decisions": {
    "approved": 10,
    "rejected": 2,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 10,
  "auto_applied": 8,
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
  "nw_renewal:voice=V2": {
    "2": 0.061,
    "3": 0.061,
    "4": 0.172,
    "5": 0.259,
    "6": 0.045,
    "7": 0.0
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0