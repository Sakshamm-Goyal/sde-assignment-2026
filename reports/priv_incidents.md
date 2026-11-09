# Grade report — priv_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.375 | +14.8% | 0.263 | +6.9% | 0.499 | +6.5% | 35% | 47 (36) |
| nw_kyc | 0.435 | +13.5% | 0.271 | +11.5% | 0.625 | +1.5% | 22% | 20 (26) |
| nw_renewal | 0.449 | +51.1% | 0.274 | +44.3% | 0.559 | +0.5% | 7% | 90 (133) |
| ALL | 0.412 | +25.4% | 0.268 | +18.7% | 0.545 | +3.8% | 24% | 157 (195) |

## Changes applied by the controller

21 applied — neutral: 8, beneficial: 12, harmful: 1

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- ks_cancel v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- ks_cancel v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.021 didΔ=+0.000 → **beneficial**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.042 → **beneficial**
- ks_cancel v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.036 → **beneficial**
- ks_cancel v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.016 → **neutral**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- nw_renewal v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.305 → **beneficial**
- ks_cancel v6 (controller_auto) dims=['welcome_message'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nw_renewal v6 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- ks_cancel v7 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.003 didΔ=+0.000 → **neutral**
- nw_renewal v8 (controller_approved) dims=['welcome_message'] engageΔ=+0.028 didΔ=+0.000 → **beneficial**
- nw_renewal v9 (controller_approved) dims=['prompt_version'] engageΔ=-0.040 didΔ=+0.000 → **harmful**
- ks_cancel v9 (controller_approved) dims=['voice'] engageΔ=+0.016 didΔ=+0.000 → **beneficial**
- nw_renewal v10 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.019 didΔ=+0.000 → **beneficial**
- ks_cancel v10 (controller_approved) dims=['prompt_version'] engageΔ=+0.161 didΔ=+0.000 → **beneficial**
- nw_kyc v4 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.340 → **beneficial**
- ks_cancel v11 (controller_approved) dims=['voice'] engageΔ=+0.047 didΔ=+0.000 → **beneficial**
- nw_renewal v11 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v5 (controller_approved) dims=['welcome_message'] engageΔ=+0.011 didΔ=+0.000 → **beneficial**

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
  "applied_via_approval": 13,
  "auto_applied": 8,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 2,
    "nw_kyc": 1,
    "ks_cancel": 3
  }
}
```

## Incidents

```
[
  {
    "type": "did_flagged",
    "workflow": "nw_renewal",
    "at": "D1 18:00",
    "flagged_did_share_by_day": {
      "1": 0.351,
      "2": 0.0,
      "3": 0.0,
      "4": 0.0,
      "5": 0.0,
      "6": 0.0,
      "7": 0.0
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "nw_renewal",
    "at": "D2 22:00",
    "mttr_minutes": 2280,
    "fixed_by": "controller_approved"
  },
  {
    "type": "supervisor_edit",
    "workflow": "nw_kyc",
    "at": "D3 09:00"
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D4 12:00"
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:welcome_message=W3": {
    "3": 0.236,
    "4": 0.15,
    "5": 0.0,
    "6": 0.0,
    "7": 0.0
  }
}
```

Credits used: 8 · validation runs: 2 · LLM fix calls: 0