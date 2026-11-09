# Grade report — priv_aa_922

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.379 | +8.3% | 0.267 | +9.8% | 0.497 | -1.3% | 0% | 61 (54) |
| nw_kyc | 0.410 | +11.5% | 0.271 | +13.6% | 0.590 | -2.7% | 0% | 22 (15) |
| nw_renewal | 0.469 | +8.0% | 0.291 | +7.5% | 0.546 | -0.4% | 0% | 61 (36) |
| ALL | 0.416 | +8.9% | 0.276 | +9.7% | 0.532 | -1.2% | 0% | 144 (105) |

## Changes applied by the controller

20 applied — neutral: 16, beneficial: 4

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- ks_cancel v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- ks_cancel v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.000 didΔ=+0.038 → **beneficial**
- ks_cancel v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.036 → **beneficial**
- ks_cancel v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.016 → **neutral**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.045 → **beneficial**
- nw_renewal v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.017 → **neutral**
- ks_cancel v6 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v7 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v7 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.376 → **beneficial**
- nw_renewal v8 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v9 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v10 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v9 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v4 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 13,
  "decisions": {
    "approved": 12,
    "rejected": 1,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 1
  },
  "applied_via_approval": 12,
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
{}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0