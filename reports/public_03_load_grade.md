# Grade report — public_03_load

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| arav_cancel_2 | 0.391 | +16.0% | 0.265 | +8.9% | 0.523 | +5.3% | 33% | 410 (409) |
| arav_kyc_1 | 0.458 | +27.5% | 0.256 | +19.1% | 0.617 | +2.7% | 22% | 431 (352) |
| arav_renewal_0 | 0.473 | +16.8% | 0.287 | +8.9% | 0.582 | +6.3% | 36% | 476 (408) |
| kest_cancel_2 | 0.396 | +17.8% | 0.266 | +9.6% | 0.528 | +5.8% | 44% | 397 (418) |
| kest_kyc_1 | 0.435 | +22.2% | 0.252 | +17.6% | 0.600 | +0.4% | 4% | 429 (370) |
| kest_renewal_0 | 0.471 | +17.2% | 0.285 | +7.7% | 0.584 | +7.2% | 39% | 443 (403) |
| nort_cancel_2 | 0.393 | +15.9% | 0.266 | +8.9% | 0.523 | +5.0% | 32% | 455 (368) |
| nort_kyc_1 | 0.451 | +26.7% | 0.256 | +19.0% | 0.610 | +2.5% | 13% | 425 (318) |
| nort_renewal_0 | 0.464 | +14.5% | 0.286 | +8.3% | 0.574 | +4.9% | 29% | 471 (419) |
| tide_cancel_2 | 0.393 | +14.5% | 0.265 | +8.5% | 0.526 | +5.0% | 39% | 424 (401) |
| tide_kyc_1 | 0.451 | +26.7% | 0.255 | +18.9% | 0.612 | +2.4% | 16% | 409 (376) |
| tide_renewal_0 | 0.478 | +18.1% | 0.287 | +8.7% | 0.588 | +7.6% | 43% | 503 (425) |
| ALL | 0.438 | +19.4% | 0.269 | +11.6% | 0.572 | +4.8% | 29% | 5273 (4667) |

## Changes applied by the controller

63 applied — neutral: 30, beneficial: 33

- nort_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- nort_cancel_2 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- kest_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- kest_cancel_2 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- arav_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- arav_cancel_2 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- tide_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- tide_cancel_2 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.005 → **neutral**
- nort_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.015 → **neutral**
- kest_cancel_2 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.023 → **beneficial**
- arav_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.015 → **neutral**
- tide_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.015 → **neutral**
- tide_cancel_2 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.023 → **beneficial**
- kest_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.015 → **neutral**
- kest_cancel_2 v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.010 → **neutral**
- arav_cancel_2 v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- arav_cancel_2 v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.025 → **beneficial**
- arav_cancel_2 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- nort_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.046 → **beneficial**
- nort_cancel_2 v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- nort_cancel_2 v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.025 → **beneficial**
- tide_renewal_0 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- tide_renewal_0 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- tide_cancel_2 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=-0.001 didΔ=+0.011 → **neutral**
- kest_cancel_2 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- arav_renewal_0 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- nort_renewal_0 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- kest_renewal_0 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.018 → **neutral**
- arav_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.056 → **beneficial**
- tide_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.057 → **beneficial**
- kest_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.015 didΔ=+0.044 → **beneficial**
- nort_cancel_2 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.078 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.079 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.096 didΔ=+0.000 → **beneficial**
- tide_renewal_0 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.097 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.096 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v7 (controller_approved) dims=['voice'] engageΔ=+0.046 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.096 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v7 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.042 didΔ=+0.000 → **beneficial**
- tide_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.023 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v7 (controller_approved) dims=['welcome_message'] engageΔ=+0.017 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v3 (controller_approved) dims=['welcome_message', 'caller_id'] engageΔ=+0.012 didΔ=+0.479 → **beneficial**
- kest_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=-0.000 didΔ=+0.000 → **neutral**
- tide_kyc_1 v3 (controller_approved) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.060 didΔ=+0.559 → **beneficial**
- kest_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.589 → **beneficial**
- arav_kyc_1 v3 (controller_approved) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.104 didΔ=+0.578 → **beneficial**
- tide_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v8 (controller_approved) dims=['welcome_message'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- kest_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.021 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.091 didΔ=+0.000 → **beneficial**
- tide_kyc_1 v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- tide_cancel_2 v6 (controller_auto) dims=['welcome_message'] engageΔ=-0.005 didΔ=+0.000 → **neutral**
- kest_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.103 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.025 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v9 (controller_approved) dims=['voice'] engageΔ=+0.002 didΔ=+0.000 → **neutral**
- tide_kyc_1 v5 (controller_approved) dims=['welcome_message'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**

## Governance

```
{
  "approval_requests": 41,
  "decisions": {
    "approved": 39,
    "rejected": 2,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 39,
  "auto_applied": 24,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nort_renewal_0": 1,
    "nort_kyc_1": 1,
    "nort_cancel_2": 1,
    "arav_renewal_0": 1,
    "arav_kyc_1": 1,
    "arav_cancel_2": 1,
    "tide_renewal_0": 1,
    "tide_kyc_1": 1,
    "tide_cancel_2": 1,
    "kest_renewal_0": 1,
    "kest_kyc_1": 1,
    "kest_cancel_2": 1
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
  "nort_renewal_0:welcome_message=W3": {
    "3": 0.803,
    "4": 0.801
  },
  "kest_renewal_0:welcome_message=W3": {
    "3": 0.801,
    "4": 0.803
  },
  "arav_renewal_0:welcome_message=W3": {
    "3": 0.799,
    "4": 0.798
  },
  "tide_renewal_0:welcome_message=W3": {
    "3": 0.803,
    "4": 0.799
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0