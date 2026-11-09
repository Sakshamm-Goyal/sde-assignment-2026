# Controller runbook (for whoever is on call)

## What it is
One Python process (`python -m controller run --url SIM_URL`) and one SQLite file per scenario under `state/`.
Every 15 simulated minutes it: advances the simulator, ingests new event chunks, polls approvals and applies
approved ones, runs detectors (caller ID, hallucination, engagement after prompt change), and once a day per
workflow sends one bundled change request. No other state exists. No other services.

```
./run.sh http://127.0.0.1:8700                       # start or resume (idempotent)
python -m controller status                          # loop health, credits, alerts
python -m controller view [--wf ks_cancel]           # the supervisor screen
python -m controller why --wf ks_cancel --at "D3 14:00"   # why did it change, who approved, what happened next
python -m controller heard --person ks_cancel:p0001234    # what a customer heard, and why that variant was live
```
Add `--db state/<dir>/<scenario>.db` if there's more than one store.

## Restarting
Always safe. `kill -9` at any point, then `./run.sh URL` again. On start it:
1. reopens the store; if the simulator is a *new* world (different history or the clock went backwards), the old
   file is renamed `*.old` and a fresh one is created;
2. reconciles every proposal not in a final state against `GET /approvals` / config history (outbox);
3. resumes ingestion from the last committed chunk (each chunk + checkpoint is one transaction).
Proven by `scripts/crash_test.sh` (8 random kill -9s, see `reports/crash_test.log`) and `tests/test_controller.py`.

## Pages (act now) — `alerts` table, severity `page`
| alert | what it means | what to do |
|---|---|---|
| `approved change ... lapsed` | an approved request wasn't applied within the apply window | should be impossible (we poll every tick); check the loop was running; re-proposal happens automatically |
| `hallucination spike on Px` | CUSUM fired; fix flow started | `why --wf X` shows candidate, validation, request. Nothing to do unless it's still open after 4h |
| `no candidate prompt passed validation` | fix flow exhausted | a human picks a prompt; credits left are in the message |
| `fix blocked: approval budget for 24h used up` | policy cap reached | call the client approver |
| `simulator rejected our proposal ... as invalid_config` | a controller bug | file a bug with the detail; the controller keeps running |
| `ingest lag N sim-minutes` | chunks not arriving | check the simulator / network |
| `credits at N: below the incident reserve` | LLM/validation budget nearly gone | top up or accept manual prompt fixes |

## Don't page (morning summary)
Rejections and expiries (re-proposed with fresh data next slot), caller IDs flagged and already rotated
(`caller_id_flagged` decisions), KPI drift alerts (`info`), stale re-proposals after supervisor edits.

## Knobs (all in code, each next to its reasoning)
`controller/learn.py`: exploration shares, α, min samples, holdout, probe share. `controller/incidents.py`: CUSUM
thresholds, validation n. `controller/cfg.py`: `TENANT_PREFS` (client agreements stricter than policy).

## Where things are
`ingest.py` (events → cubes), `learn.py` (cohorts, call-time, caller ID, experiments), `incidents.py`,
`governance.py` (outbox, routing, apply, reconcile), `loop.py` (orchestration), `view.py` (read-only CLI).
