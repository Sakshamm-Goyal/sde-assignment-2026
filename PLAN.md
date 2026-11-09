# Build plan — Outcome-First Agent Loop

Working plan, not the submission. Everything here feeds `SUBMISSION.md`.
Numbers marked **(measured)** come from baseline runs on this laptop on 2026-11-09.

---

## 0. The thesis (what the reviewers should take away)

> A small, boring, crash-safe controller that **reads every policy from the API**, learns only from
> **randomised, realised traffic**, changes things **once a day in one batched request per workflow**,
> moves fast **only toward safety**, and can explain every decision from **one SQLite file**.

Five capabilities done properly beat fifteen sketched (README §6, CTO memo). We win on:
1. **No harmful changes.** The grader marks a change harmful if expected engagement drops more than 1% or caller-ID health drops more than 2% at apply time.
2. **Fast incident fixes**: caller-ID flagged, bad supervisor prompt.
3. **Decay rollback**: keep a holdout so decay is actually measurable.
4. **Clean governance**: no lapses, no fatigue rejections, no stale applies.
5. **A design doc that catches every wrong memo claim** and gives honest numbers.

---

## 1. Facts that drive the design

### 1.1 Volumes (measured, public_01 baseline)

| workflow | dials/day | connected/day | pickup | engagement | halluc-flag rate (P1) |
|---|---|---|---|---|---|
| nw_renewal | 3,600 | ~950 | 0.26 | 0.54 | ~1.5–1.8% |
| nw_kyc | 2,000 | ~490 | 0.25 | 0.59 | ~1.3–1.6% |
| ks_cancel | 4,800 | ~1,170 | 0.25 | 0.49 | ~1.4% |

Load scenario (measured): **~810k events/day**, 9.7M events over 12 days including 7 history days.
Simulator alone takes **~14 s per simulated day**, 655 MB RSS, and writes 4.1 GB of NDJSON.
SRE wants under 10 minutes per day, so we have roughly 9 minutes of headroom for our own work.

### 1.2 Sample sizes: what the statistics can and can't do

Engagement p ≈ 0.55, one-sided test, power 0.8. Columns: connected calls per arm, then days needed on nw_renewal.

| true lift | α=0.05 n/arm | α=0.01 n/arm | days, 50/50 whole workflow (α=.01) | days, 15% cohort (α=.01) |
|---|---|---|---|---|
| 5% | 4,047 | 6,569 | 13.8 | 92 |
| 10% | 1,012 | 1,642 | 3.5 | 23 |
| 15% | 450 | 730 | 1.5 | 10 |
| 20% | 253 | 411 | 0.9 | 5.8 |

**Consequence:** in an 8–10 day scenario we can only find **≥10% effects at workflow level** or
**≥20% effects inside a cohort**. So:
- Test **main effects at workflow level first**. Welcome and voice are sampled independently per dial, so we get a factorial design for free: every dial tests both dimensions at once.
- Use cohort-specific allocations only when a large heterogeneous effect shows up.
- **Minimum cohort size is set in connected calls, not as a share of traffic**:
  `min_connects_per_day = n_req(δ_min=20%, α=.01) × arms / window_days`. With 2 arms over 4 days that's about 205 connects/day: ~22% of renewal, ~18% of cancel, ~1.6% of a load-scenario workflow. The formula scales; a fixed percentage doesn't. This answers Product's open question.

### 1.3 Simulator mechanics we must respect (from reading the code; the controller learns them from data)

| Mechanic | Design response |
|---|---|
| Harm is judged at apply time on all active leads (engagement −1% or caller-ID health −2%) | Exploration share is capped by a harm budget (§4.3). Bundle explore and prune in one change. |
| Caller-ID health falls with that DID's recent load: `base / (1 + (load/l0)²)`, decaying over about 2 days | Spread traffic across every healthy DID. Probe unused DIDs at a small share, then widen. KYC dials one DID at 100%, which is probably its single biggest pickup lever. |
| Pickup depends on DID, hour and person. Engagement depends on welcome, voice and prompt. | Pickup experiments run on DID and schedule; engagement experiments run on welcome and voice. Check the guardrail KPI anyway. |
| `prompt_version` is one per workflow, so it can't be randomised | Prompts change **only for safety** (incidents). No proactive prompt chasing. Decline Sales' P4 request. |
| The validation gate is noisy. Failure rate ≈ 0.9·halluc + 0.005, so a 4×-hallucinating prompt passes 0.97 more often than not. | Our own acceptance bar is stricter than policy (§5.3), and we verify with live flag rates after apply. |
| Validation says nothing about engagement. The "strict" prompt is safe but costs about −14% engagement. | Prefer a fix with **live engagement evidence** (the last known-good prompt). After apply, verify engagement as well as hallucination. |
| Every auto-apply and supervisor edit bumps the version, so pending approvals go stale | One writer per workflow (§6.4). |
| Apply window is 2h after decision, otherwise the approval lapses (410) | 15-minute ticks whenever an approval is pending or approver hours are open. |
| Rejected requests still count toward `max_requests_per_24h` | Track our own rolling count and send one batched request per workflow per day. |
| `next_campaign_only`: allocations lock at campaign creation (08:00) and campaigns run for 3 days | KYC changes reach the dialler late. Evaluate by `config_version` on the call event and plan with that lag. |
| In `hour_weights`, an omitted hour gets weight 0 | Always emit every hour in the window, with a floor weight ≥ 0.2. |
| History ran only the default config (W1/V1/D1–D2) | History is used for pickup-by-hour × features, DID baselines and hallucination baselines. Never for variant effects. |
| Decay starts from a variant's **first exposure** (our exploration) | A promoted winner keeps a **holdout of the incumbent** (§4.5). |
| Controller downtime freezes sim time (time only advances when we call it) | A crash can't cause a lapse. Recovery is purely about state. |

---

## 2. Scope decision

| # | Capability | Decision | Why |
|---|---|---|---|
| C1 | Ingestion at load scale | **Build** | Floor plus SRE requirement; everything depends on it |
| C2 | Lead joins and one shared cohort object | **Build** | Product non-negotiable; it's the backbone of analysis |
| C3 | Bootstrap from history | **Build (narrow)** | Baselines only: pickup×hour×features, DID, flag rate |
| C4 | Call-time optimisation | **Partial: per-cohort `hour_weights`** | Per-person data is too sparse (≤8 attempts per lead); see the Sales/Product replies |
| C5 | Caller-ID health | **Build** | Graded incident, auto-appliable, and the biggest pickup lever |
| C6 | Welcome × voice experiments | **Build** | Core of the engagement lift |
| C7 | Promotion, decay detection, rollback | **Build** | Graded explicitly |
| C8 | Hallucination incident response | **Build** | Graded time-to-fix; compliance story |
| C9 | Governance client | **Build** | Graded hygiene; crash safety lives here |
| C10 | Honest impact, affected leads, dry run | **Build (simple, honest)** | Required fields; Product ranks by impact |
| C11 | Supervisor view | **Partial: one CLI screen plus a read-only JSON/HTML endpoint** | Anita's "one screen"; no frontend framework |
| C12 | Audit store | **Build** | Floor; live in the review |
| C13 | Crash recovery demo | **Build** | SRE non-negotiable; a deliverable |
| C14 | Loop observability | **Partial: metrics table, `status` command, alert rules** | Cheap once the store exists |
| C15 | Fair credits and attention across tenants | **Cut (one rule only)** | Per-workflow credit cap plus a global incident reserve. Write it down. |

**Principle:** build what is graded on hidden scenarios or required to never break a hard constraint. Everything else gets the cheapest honest version, and each cut has a reply ready.

---

## 3. Architecture

```
            ┌──────────────── simulator (HTTP) ────────────────┐
            │ /sim/advance  /events/chunks  /workflows  /approvals │
            └───────▲───────────────┬──────────────────▲───────┘
                    │ advance       │ NDJSON chunks     │ POST/PUT/GET
┌───────────────────┴───────────────▼──────────────────┴────────────────┐
│ loop.py  (single process, single writer)                             │
│  1 reconcile (startup)   2 advance   3 ingest   4 governance tick     │
│  5 detectors (every tick)   6 daily planner (per workflow)   7 metrics │
└──┬──────────┬─────────────┬───────────────┬───────────────┬──────────┘
   │ ingest   │ cohorts     │ detect/exp    │ planner       │ governance
   ▼          ▼             ▼               ▼               ▼
┌──────────────────────── SQLite (WAL) state/ctl.db ───────────────────┐
│ checkpoint · leads · cube · calls · config_versions · cohorts         │
│ experiments · proposals(outbox) · decisions · llm/validation · metrics│
└──────────────────────────────────────────────────────────────────────┘
          ▲ read-only: view.py (supervisor screen), why.py (audit query)
```

**Code layout.** Python, stdlib plus the existing `numpy` and `httpx`. **No new dependencies.**
```
controller/
  __main__.py     python -m controller --url URL [--db state/ctl.db]
  client.py       httpx wrapper: retry/backoff on 5xx/conn errors, typed ApiError on 4xx
  store.py        schema, migrations, tx helper, small query helpers
  ingest.py       chunk → leads/cube/calls/config/approval rows + checkpoint, one transaction
  cohorts.py      shared Cohort registry; `match()` uses the same semantics as the sim (first match, AND/OR)
  stats.py        pure functions: two-proportion z, posterior P(better), Holm, n_req, EWMA/CUSUM
  detect.py       DID health, hallucination spike, KPI drift, supervisor-edit handler
  experiments.py  lifecycle: explore → prune → promote(holdout) → watch → rollback
  schedule.py     per-cohort hour weights from history
  incidents.py    hallucination fix flow (credits, validation, choice, verify)
  planner.py      merges intents into one config per workflow; impact, affected leads, dry run
  governance.py   proposal state machine, outbox, path choice (auto vs approval), timing
  view.py         supervisor screen + `why` audit query + loop status
tests/test_controller.py   stats, state machine, idempotent ingest, cohort match parity
scripts/crash_test.sh      kill -9 at random points, restart, verify
scripts/load_test.sh       public_03 with timing and RSS capture
scenarios/private/*.yaml   our own anti-overfitting scenarios (never read by the controller)
```

### 3.1 Store schema (SQLite, WAL, one file)

| table | key | purpose |
|---|---|---|
| `checkpoint` | kind | last chunk ingested per kind, last event_id |
| `leads` | lead_id | person_id, workflow, campaign, lang, tier, age, value, uploaded_ts |
| `cube` | (wf, day, hour, lang, tier, age, value, wm, voice, did, prompt, cfg_ver, campaign_day) | dials, connected, engaged, halluc_flags. **All analysis is GROUP BY on this.** |
| `calls` | event_id | live days only: lead, person, ts, cfg_ver, cohort_id, variant, outcome. Answers "what did customer X hear on day D" (Compliance memo) |
| `config_versions` | (wf, version) | actor, ts, changed_dims, proposal_id, approval_id, full config |
| `cohorts` | (wf, cohort_id) | where, status (candidate/active/retired), created_by decision |
| `experiments` | id | wf, scope (cohort), dim, arms, incumbent, status, start_version, holdout |
| `proposals` | proposal_id | outbox: kind, path, base_version, config, request body, status, approval_id, timestamps, applied_version, superseded_by, reasons |
| `decisions` | id | ts, wf, type (detect/explore/prune/promote/rollback/skip/incident/re-propose), **inputs (stats snapshot)**, reason text, linked proposal |
| `llm_calls`, `validations` | id | credits spent, results |
| `metrics` | (ts, name) | ingest lag, events/s, decisions/h, credits, pending approvals |

The cube is small (≤ a few hundred feature combos × arms × hours) and makes detection, experiments,
dry runs and the supervisor view the same SQL. At 10× it's still small. The `calls` table is the only large table.

---

## 4. The learning loop

### 4.1 Cohorts (one shared object)

- **Registry** holds id, workflow, `where`, status and provenance. Config cohorts are always registry cohorts, so detection, experiments and the view use the same id (Product memo).
- **v1 at D0 from history.** For each feature, test the interaction between segment and hour on pickup (chi-square on the cube). Pick the most significant feature, then merge levels with similar hourly profiles until every group meets the minimum connects. Expect about 3–4 cohorts, typically age-driven, but **this is chosen from data, not hard-coded**.
- **Adopting v1 is a zero-behaviour-change proposal** (cohorts added, allocations identical to default), plus the schedule. It's the first request each workflow gets. Low risk, high approval odds, and it unlocks per-cohort schedule and caller-ID auto-apply on workflows that allow them.
- **Heterogeneity scan at each daily look.** For every arm with a significant workflow-level effect, test arm × feature (each of the 4 features) with Holm correction. A segment with an effect ≥20% that meets the minimum size becomes a `candidate` cohort, and is adopted only inside the next daily bundle. Cap ~6 cohorts per workflow to avoid fragmentation.
- Analysis always runs on the cube's raw features, so changing the config cohorts never invalidates past data.

### 4.2 Experiment design

- **Factorial for free:** welcome and voice are sampled independently per dial, so one exploration change tests both dimensions at full traffic each. Analyse main effects by marginalising the other dimension. Check welcome × voice interaction with a 2-way table when n allows; if it's significant, decide on the combination instead.
- **Arms:** the incumbent plus all allowed challengers in a dimension (2–4 arms).
- **Evidence = realised traffic only:** arms are counted from `variant` on call events, never from what we asked for (Product memo). Arms that never ran have no data, show as "no evidence" and never count as zero lift.
- **Pickup-side experiments** (DID, schedule) use pickup. **Engagement-side** (welcome, voice) use engagement. The other KPI is always checked as the guardrail.

### 4.3 Exploration budget (harm-aware)

- Incumbent keeps ≥ 70% of each dimension; challengers split the remaining ε = 30% (where auto-apply allows, ε is capped by `max_shift`).
- Rationale: worst-case loss ≈ ε × (1 − worst plausible arm multiplier). At ε = 30% spread over 3 challengers (10% each), one arm at ×0.85 costs 1.5%. That's acceptable only because of **fast pruning**, which also reads as "beneficial" at apply time.
- **Intraday safety stop**, checked every hour: drop any arm with P(arm < incumbent by ≥10%) > 0.99. This is an urgent intent; auto-apply where policy allows, otherwise use the next approval slot.
- Tune ε on **private scenarios** (§9), never on public truth.

### 4.4 Deciding a winner

- **Daily looks only**, once per workflow at the planning hour. That's ≤10 looks per scenario, which limits the peeking problem.
- Test: two-proportion z (equivalently a Beta posterior with a normal approximation, so it's deterministic). **Promote** when one-sided p < 0.01 after **Holm** across all (arm × dimension × scope) tests that day, **and** the arm has ≥ 400 connects, **and** the point lift ≥ 5%, **and** the guardrail passes.
- **Prune** (drop to 0): P(arm worse than incumbent) > 0.95 with ≥ 200 connects. Pruning is asymmetric (looser) because moving toward the incumbent is moving toward known-safe.
- Expected false-winner rate: α ≈ 0.01 per test per look, Holm-adjusted, over ≤10 looks, comes to under ~5% family-wise per workflow. We verify this empirically with an **A/A private scenario** (no effects): count promotions; the target is ≤1 across all runs.
- An LLM never decides. The LLM is used only to suggest prompt candidates (§5).

### 4.5 Promotion, decay and rollback

- Promote to **80% winner / 20% incumbent holdout**, not 100%. Without a concurrent control, decay can't be told apart from day-to-day drift. The holdout costs ~20% of the lift, and we say so in the doc.
- Decay detector: EWMA (half-life 1 day) of the winner-minus-holdout lift, plus a one-sided CUSUM on daily lift relative to the lift measured at promotion. **Rollback** when P(lift < 0) > 0.8 over the last 1–2 days, which is again asymmetric. Rollback goes back to the incumbent (or the next-best surviving arm).
- Rollback path: auto-apply if the policy permits it (it moves toward safety), otherwise an expedited approval at the next approver hour, outside the daily bundle cadence.
- After ~3 stable days with no decay, the holdout may shrink to 10%. It never drops to 0 while a variant is promoted.

### 4.6 Call time (C4, per cohort)

- From history, compute pickup p[cohort][hour]. Set weights as **comparative advantage**: w = (p_c(h)/p̄(h))^k with k = 2 and floor 0.2. Every hour in the window is present.
- Weights only change *who* is dialled each hour (capacity is fixed). The gain comes from reaching seniors in the morning and the young in the evening.
- Evaluation isn't randomised, so it's pre/post against a **history-based expected pickup** given the hour × cohort mix. Labelled "observational" in the view. Auto-applied where the policy allows `schedule`; otherwise it rides the daily bundle.
- Per-person (`lead_preferred_hour`) is **cut**. Most people have fewer than 3 connected attempts, so per-person estimates are noise. The future design is a person-level randomised test (assign preferred hours to a random half), and it's documented.

### 4.7 Caller ID (C5)

- **Health estimate:** pickup of DID d divided by pickup of the other DIDs in the same workflow, hour and cohort window (concurrent and randomised, so it's unbiased). Rolling 2h and 24h windows.
- **Flag:** ratio < 0.75 with z-test p < 0.001 and ≥ 150 dials on d. That's about 1h on ks_cancel for a DID at health ~0.35. Response: **auto-apply** a shift off d where allowed, in `max_shift` steps on consecutive ticks; otherwise an urgent approval.
- **Load spreading:** steady-state target weight ∝ estimated health over all non-flagged DIDs. Unused DIDs are **probed at 5–10%** first, because they could be pre-flagged (cost ≈ share × health gap, kept under the 2% health threshold). Expand when the probe's ratio ≥ 0.95 with ≥ 300 dials.
- **Re-probe** flagged DIDs every 2 days at 5% (they recover as load decays).

### 4.8 Guardrail

- For every change: estimate the guardrail KPI delta on affected traffic (arm-level where randomised, pre/post otherwise).
- **Veto** if the point drop exceeds the policy's `*_max_drop` or P(drop > max_drop) > 0.2. Assumption A3: `max_drop` is absolute, in rate points.
- After apply, a guardrail breach found by the post-apply watch triggers rollback just like decay does.

---

## 5. Incidents

### 5.1 Hallucination detector (C8)
- Baseline flag rate per workflow comes from history (~1.5% on P1). The detector is imperfect (≈80% true-positive, ≈1% false-positive), so we act on rates, never on single calls.
- Trigger: rolling flag rate over the last ≥200 connected calls exceeds baseline + 3.1σ (α=1e-3; that's ~4.2% at n=200), **and** rate > 2× baseline, sustained on two consecutive ticks. Expected false-positive rate is about once per 1,000 windows, which we report.
- An extra prior: a `config_changed` that changed `prompt_version` (any actor) puts the workflow on 15-minute watch. We never act on the change alone, only on data.

### 5.2 Fix selection (credit-frugal: "best compute is no compute")
1. Candidates = **last known-good prompt** (live flag rate at baseline **and** live engagement evidence), plus `/llm/suggest-fixes` (3 credits) **only if** no known-good prompt exists or it isn't in the options.
2. Validate each candidate at n=400 (4 credits). Accept if `pass_rate ≥ policy_min` **and** the lower bound of a 90% interval ≥ policy_min **and** pass_rate ≥ the best historical pass rate − 0.01. Ambiguous cases get one top-up run at n=1000.
3. Rank: has live engagement evidence > no evidence. Among candidates without it, prefer the higher pass rate, and flag "engagement unknown" in the proposal and the view (the Anita/P5 trap).
4. Propose immediately if inside approver hours, otherwise at window open. Incidents bypass the courtesy limits (Kestrel "2/day, after 11:00") but never the policy limits. The rationale says plainly: "your supervisor's change at 11:30 raised flagged calls from 1.4% to 5.3%; reverting to P1 (validated 0.99, n=400)". It goes through the client's approver, so nothing changes behind their back.
5. **Verify** after apply: the flag rate returns under baseline + 2σ within 300 connected calls, **and** engagement isn't significantly below the pre-incident level. Otherwise, next candidate.

### 5.3 Credits
- Budget split: a 40% **incident reserve** that's never spent on anything else, and a per-workflow cap of (60% / #workflows) for everything else. That's the whole of C15, written down.
- A `402` disables LLM calls; validation spends from the reserve only. Credit burn goes in the metrics.

### 5.4 Supervisor edits
- `config_changed` with actor=supervisor: record it, rebase. Pending approvals will go stale, so mark them superseded and **re-propose with fresh data** next slot, without contradicting the edited dimension.
- **Cool-down**: no proposal touching a supervisor-edited dimension for 24h unless it's a safety incident.
- If the edit is **masked** by our cohort-level overrides (e.g. supervisor sets default voice V2 while our cohorts carry their own voice), freeze our experiments on that dimension, show the conflict in the view, and put the question in the next approval ("align cohorts to your V2, or keep evidence-backed cohort voices?"). Never silently revert either way.

---

## 6. Governance (C9)

### 6.1 State machine (our `proposals` table)
```
draft → submitting → pending ─┬→ approved → applying → applied → watching → (kept | rolled_back)
                               ├→ rejected  (back off 24h on that intent; re-propose only with new evidence)
                               ├→ expired   (= rejection, per Product; rebuild from fresh data)
                               └→ superseded (base moved: supervisor edit or our own auto-apply)
approved ─→ lapsed (missed apply_by; should never happen, alert if it does) → re-propose fresh
applying ─→ stale (409) → re-propose fresh next slot
auto: draft → submitting → applied | refused(403, logged, falls back to the approval path)
```

### 6.2 Timing and batching
- **One bundled request per workflow per day**, at `approver_hours.start` (Kestrel: 11:00, per Anita), carrying every pending intent (prune, promote, rollback, schedule, cohort, DID). Combined `change_summary` with one line per intent, and a `diff` keyed by intent.
- Hard cap = min(policy `max_requests_per_24h`, stated client preference) − 1 slot kept back for incidents.
- Only submit if the expected decision lands before TTL: latency max + time to approver close < TTL. Otherwise wait for the next window open.
- Never submit outside approver hours, except to queue an incident request that will be decided at window open.
- Poll each tick while anything is pending. Apply on the first tick after `approved`.

### 6.3 When we auto-apply, and when we voluntarily don't
- **Auto-apply (where the policy allows):** DID rotation and spreading, schedule, safety prunes and rollbacks that move toward the incumbent.
- **Voluntarily via approval even when auto-apply is allowed:** any increase of a customer-facing variant (welcome or voice exploration and promotion). Reasons: Northwind Compliance #1, Anita's "tell me before anything changes", CTO's "explainable beats bigger". The cost is a slower ramp on ks_cancel, and we say so.
- Every auto-apply still writes a decision row and shows up in the daily "what changed today" view and the weekly summary (Compliance #1).

### 6.4 One writer per workflow
- Any version bump stales every pending approval on that workflow. So: no non-urgent auto-apply while an approval on that workflow is `pending` or `approved`. Non-urgent auto-applies get folded into the bundle instead.
- Urgent auto-applies (DID flag, safety stop) proceed. The pending one is marked `superseded`, and re-proposed fresh. Each such collision is logged and counted.

### 6.5 Proposal content (honest by construction)
- **impact_score** = clip(LCB80(expected Δ primary KPI, relative) × share of workflow traffic affected / 0.10, 0, 1). It uses the **lower confidence bound**, not the point estimate. 1.0 means "+10% primary KPI workflow-wide, at 80% confidence". Incidents: expected hallucinated calls avoided per day, scaled to the same 0–1 (documented). Rollbacks: expected loss avoided.
- **affected_leads** = active leads (status still dialling) whose cohort's distribution changes, plus the expected next 24h of uploads in those cohorts. Only future campaigns for `next_campaign_only`.
- **dry_run** = replay the proposed config's cohort mapping over the last 3 days of leads from our store: leads per cohort, expected dials per arm, and predicted KPI with intervals from **observed arm data only**. Arms with no data are marked "no evidence".
- **rationale** = generated from the decision's stats snapshot (n, rates, p, test, look number). The same text lands in `decisions`.

---

## 7. Reliability (C13) and idempotency

- **Ingest exactly-once:** each chunk is processed in one SQLite transaction (rows + checkpoint). A replayed chunk is skipped by checkpoint, and `calls` has `event_id` as primary key as a second guard.
- **Outbox:** a proposal row is written (`submitting`, deterministic `proposal_id = {wf}-{seq}`) **before** the POST. On restart, for each row in `submitting`/`pending`/`approved`/`applying`:
  - `GET /approvals?workflow_id=` and match by proposal_id. `409 duplicate_proposal_id` means it exists, so reconcile.
  - Auto-apply: `GET /workflows/{id}/config/history` and match by proposal_id before any retry.
  - Apply: re-read the approval. If it's `applied`, record the version; never call apply twice.
- **Learned state** (cube, experiments, cohorts, holdouts) is all in the DB. Nothing important lives only in memory; caches are rebuilt from the DB on start.
- **HTTP errors:** 5xx and connection errors get exponential backoff (cap 30s) and retry. Safe because GETs are pure and POST/PUTs carry idempotency keys. 4xx maps per code: 409 stale goes to re-propose; 409 duplicate goes to reconcile; 410 records lapsed and re-proposes; 402 disables LLM; 403 auto-apply refusal falls back to approval; 422 is a bug, so it's logged with the body and alerts.
- **Crash test** (`scripts/crash_test.sh`): start the sim; loop `run.sh &`, then sleep a random 5–40s, then `kill -9`, ×6 (including once mid-ingest and once between approve and apply), then let it finish. Verify that (a) the run finishes, (b) no duplicate proposal_ids or double applies appear in config history, (c) DB event count equals the sim's `last_event_id`, (d) the grade is close to an uninterrupted run. Commit the log to `reports/crash_test.log`.

---

## 8. Scale (public_03) and observability

- **Targets:** ingest ≥ 50k events/s; decision lag (chunk available to decisions done) < 2s per tick; RSS < 1.5 GB; < 10 min wall-clock per simulated day **including** the sim's ~14s.
- **Tactics:** stream the NDJSON response line by line; aggregate the cube in a Python dict and flush with `executemany` once per chunk; `calls` inserted in batches; history isn't kept in `calls` (cube only); `PRAGMA journal_mode=WAL, synchronous=NORMAL`. If profiling shows `json.loads` dominating, the escape hatch is `orjson` (it would be the one new dependency, justified with numbers) or column-pruned parsing.
- **Measure** with `scripts/load_test.sh`: events/s, per-tick lag p50/p95, peak RSS (`resource.getrusage`), wall-clock per simulated day, DB size. Write the results to `reports/public_03_load.md`.
- **What breaks at 10×** (~8M events/day): the single-writer SQLite and single-process JSON parse go first, then `calls` table growth (~650M rows/month). Fix: partition by workflow (workflow hash → worker; the cube is per-workflow and governance is per-workflow, so there's no cross-workflow state except credits and tenant fairness), move to the existing Postgres (cube → partitioned table, calls → time-partitioned, or object storage plus aggregates only), and switch ingestion to a stream consumer. No Redis needed.
- **Loop health** (`python -m controller status`): ingest lag (sim minute minus last ingested), events/s, decisions/h, credits remaining and burn rate, pending approvals with time to `apply_by`, open incidents.
- **Page:** approved change near `apply_by` and not applied; ingest lag > 1h; credits < incident reserve; open hallucination incident unresolved past 4h; a 422 from our own proposal (a bug). **Don't page:** rejections, expiries, a DID flag that auto-rotated successfully, stale re-proposals. Those go in the morning summary.

---

## 9. Testing and anti-overfitting

- **Unit tests** (only where logic can silently break): stats functions against known values; Holm; the proposal state machine transitions; cohort `match()` parity with the sim's first-match semantics (table-driven); ingest idempotency (feed the same chunk twice, same DB); hour-weights always cover the window.
- **Private scenarios** in `scenarios/private/`, written by us. The controller never reads them; they're for our own evaluation only:
  1. **A/A**: no effects, measures the false-winner rate.
  2. **Policy flip**: auto-apply disabled on cancel, different approver hours (e.g. 12–16), TTL 6h, max 1 request/day.
  3. **Incidents shuffled**: DID flagged on renewal at 18:00, supervisor ships P5 (safe, engagement killer), supervisor edit at night, two incidents on one workflow.
  4. **Opposite truth**: winners become losers per cohort; decay on a voice.
  5. **Different options/features mix**: other languages, 2 DIDs only.
- Run `make baseline`/`grade` across public plus private after each milestone, and keep a scoreboard in `reports/scoreboard.md`: lift, harmful count, MTTR, decay share, lapses, credits.

---

## 10. Milestones (commit at each; small honest commits)

| # | Milestone | Done when |
|---|---|---|
| M0 | Skeleton: client, store, loop with smart advance step, `run.sh` | Runs public_01 to the end doing nothing; resumes after kill |
| M1 | Ingest + cube + leads + config/approval events + checkpoint | Event count matches; replaying a chunk is a no-op; load ingest timed |
| M2 | Governance client: outbox, state machine, bundling, timing, reconcile | Scripted no-op proposals: no lapses or fatigue rejections; kill-between-approve-and-apply test passes |
| M3 | Audit `decisions` + `why` query + supervisor screen (thin) | "Why did X change at T" answered from the DB |
| M4 | Cohorts v1 from history + schedule weights | First zero-risk proposal approved; pickup by hour moves |
| M5 | Caller ID: health, flag, rotate, probe, spread | public_02 D2 flag share → ~0 within hours; KYC spread proposal |
| M6 | Hallucination incident flow | public_02 P2 fixed same day; credits < 20 |
| M7 | Experiments: explore → prune → promote(holdout) → decay → rollback | public_01 positive lift, 0 harmful promotions, W3 rolled back after decay |
| M8 | Supervisor-edit handling + guardrail veto + impact/dry run honesty | public_02 D5 edit handled with no silent overwrite |
| M9 | Load test + 10× analysis; crash test script and log | `reports/` complete |
| M10 | Private scenarios + tuning ε/thresholds (on private only) | Scoreboard stable across all scenarios |
| M11 | SUBMISSION.md, README for the on-call engineer, optional video | Every template section filled |

Rough effort: M0–M3 ~5h, M4–M8 ~8h, M9–M11 ~5h. Front-load M0–M3: they're the floor.

---

## 11. Stakeholders: accept / push back / wrong claims / draft reply

**01 Sales (Nikhil).**
Accept: a per-client lift figure, shown as **two numbers** (pickup and engagement) with a conclusion-rate headline.
Decline: a blended score; "live for everyone by evening"; P4 rollout.
Wrong claims: Kestrel's auto-apply doesn't cover prompts or cohorts and caps shifts at 0.2. Northwind KYC auto-apply is **disabled**. P4 isn't available on KYC.

> Draft reply: "Nikhil, you'll get one lift number per client: conclusions per lead, with pickup and engagement shown beside it (Product won't let us blend them, and our regulated clients wouldn't trust a blended score). Speed: we promote as soon as the evidence clears, typically 1–3 days for a 10% effect, because a lunchtime winner is usually noise. Two corrections: Kestrel's auto-apply excludes prompts and limits each step to 20%, and Northwind KYC has auto-apply off, so those go to their approvers in one daily request. The 'persuasive' prompt hallucinates far more; I won't roll it out. Happy to build the summit slide from real numbers."

**02 Northwind Compliance (Meera).**
Accept all five, with welcome, voice and prompt **always** via named approval.
Wrong claim: timing and caller-ID latitude exists only on **renewal**. KYC has no auto-apply, so every KYC change goes to their approver.
Deliver: per-call variant records plus decision reasons, answerable in minutes; a weekly summary of auto-applied changes.

> Draft reply: "Meera, agreed on all five points. Customer-facing changes (opening line, voice, script) always go to your approvers with a dry run and evidence; script changes carry a validation run, plus live hallucination and engagement checks after the change goes in. One correction: the operational latitude you mention covers renewal only. KYC has auto-apply off, so even caller-ID or timing changes there go to your KYC approver (10:00–18:00). We store which variant each customer heard and why it was live, queryable in minutes, not 24 hours. Auto-applied operational changes appear in your weekly summary."

**03 SRE (Kabir).**
Accept all. SQLite file → maps to your Postgres. No Redis needed. Kill test, idempotency keys, loop health command, a paging list.

> Draft reply: "Kabir, kill/restart test is in `scripts/crash_test.sh` with logs: kill -9 at random points including between approval and apply, no double applies, no lost approvals (outbox plus reconcile on start). No new infrastructure: one SQLite file locally that maps onto your Postgres; no Redis needed. Load: [X] min wall-clock per simulated day on public_03, [Y] events/s, peak [Z] GB. At 10× the single-writer ingest breaks first; the fix is to shard by workflow, since nothing but credits is shared. Paging list attached; everything else lands in a morning summary."

**04 Kestrel Ops (Anita).**
Accept: ≤2 requests a day, none before 11:00, bundled; one screen; never silently undo her edits; reject strict-script fixes that kill engagement (post-apply engagement check).
Push back: safety incidents get a request even if it's the third that day. Wrong-ish: the policy allows 4/day from 10:00; we honour her stricter preference.

> Draft reply: "Anita, done: at most two requests a day, never before 11:00, each one bundling everything we want to change with a one-line reason per item. Customer-facing changes always come to you first, even where your policy would let us auto-apply them. Your prompt edits stay unless the data shows a problem; then you'll get a request with the numbers, never a silent revert. Exception: a hallucination spike can trigger a request outside the two-per-day budget. Your one screen shows what's being tested, what's winning, what we need from you and what changed today. And any 'safer' script is checked for engagement after it goes in."

**05 Product (Tara).**
Accept: separate KPIs, one cohort object, proposals as a product surface, expiry = rejection, realised-only evidence, workflow-scoped winners. Min cohort size and window: the formula plus the cost table in §1.2.
Push back: three P0s. Caller-ID health is built (it's the biggest lever); the supervisor view is partial; per-person call-time is cut for per-cohort, with a randomised per-person design written up.

> Draft reply: "Tara, all definitions held: separate KPIs, one cohort registry used everywhere, expired = rejected and rebuilt from fresh data, only realised traffic counts. Minimum cohort size: I size cohorts by connected calls (enough to detect a 20% effect in 4 days at α=0.01), not by %. That's ~22% of a small workflow but ~2% at load scale; table attached with the speed/false-winner trade-off. Of your three P0s: caller-ID health is built (largest pickup lever), the supervisor view is one screen, and per-person call time is per-cohort for now. Per-person data is too sparse to be honest, but I've written up the randomised design for it."

**06 CTO (Aryamann).**
Accept the framing. Show the choices and the cut list, credits spent only where they change a decision (validation over LLM, known-good revert first), what breaks first at 10×, and the on-call README.

> Draft reply: "Aryamann, I chose depth over breadth: caller-ID health, welcome/voice experiments with holdouts for decay, hallucination response, governance, and an audit trail anyone can query. I cut fair-share allocation (one rule only) and per-person call time, and said no to a blended score and auto-promoting a high-hallucination prompt. Credits: [N] used, mostly validation runs; the LLM is only called when no known-good prompt exists. The first thing to break at 10× is single-writer ingestion; the plan is to shard by workflow on the existing Postgres. The on-call runbook is in the README."

---

## 12. Assumptions to state (draft list for SUBMISSION §1)

1. Guardrail `*_max_drop` is absolute in rate points.
2. "Approver" preferences in memos are soft limits we honour when stricter than policy; safety incidents may exceed courtesy limits but never policy.
3. History is representative of the default config only; it carries no information about variant effects.
4. Hallucination flags are noisy (FP and FN); baselines are per workflow and per prompt.
5. Engagement is per connected call; repeat attempts on the same lead are treated as independent (a mild violation, stated).
6. A workflow's winner never propagates to other workflows (Product).
7. Credits are only replenished per scenario; the reserve is sized for ~3 incidents.
8. The grader box has Python ≥3.10 with `requirements.txt` installed; `run.sh` creates a venv if imports fail.

---

## 13. Review prep (60-minute live session)

- `python -m controller why --workflow X --at "D3 14:00"` prints the decision, its stats snapshot, the proposal, approval id and approver timestamp, the applied version, and the 24h KPI before/after per arm.
- **"Change a constraint, what breaks?"** Every policy value is read from `/workflows`. Know the answer for: TTL shorter than latency, max_requests=1, auto-apply off everywhere, approver hours 12–14, mid_flight lock everywhere, credits=20.
- **"The thing you cut":** per-person call time. Have the randomised design and its interference caveat ready.
