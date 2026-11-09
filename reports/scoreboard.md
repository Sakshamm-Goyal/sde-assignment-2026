# Scoreboard — public and private scenarios (final code)

Private scenarios come from scripts/make_private_scenarios.py (different truth / policy / incidents). The controller never reads any scenario file. A/A false winners: reports/aa_false_winners.md.

| scenario | conclusion Δ | pickup Δ | engagement Δ | changes (harmful) | approval requests | rejected | expired | lapsed | apply conflicts | prompt-incident MTTR (min) | credits |
|---|---|---|---|---|---|---|---|---|---|---|---|
| public_01_dev | +12.4% | +8.2% | +2.8% | 14 (0) | 13 | 6 | 0 | 0 | 0 | — | 0 |
| public_02_incidents | +28.1% | +24.4% | +0.7% | 27 (0) | 23 | 2 | 0 | 0 | 0 | 255 | 4 |
| public_03_load | +19.4% | +11.6% | +4.8% | 63 (0) | 41 | 2 | 0 | 0 | 0 | — | 0 |
| priv_aa | +10.3% | +9.9% | -0.3% | 18 (0) | 12 | 0 | 0 | 0 | 0 | — | 0 |
| priv_policy | +10.5% | +7.4% | +1.4% | 17 (0) | 15 | 1 | 0 | 0 | 0 | — | 0 |
| priv_incidents | +25.4% | +18.7% | +3.8% | 21 (1) | 15 | 1 | 0 | 0 | 0 | 2280 | 8 |
| priv_opposite | +5.7% | +5.0% | +0.1% | 18 (1) | 12 | 2 | 0 | 0 | 0 | — | 0 |
