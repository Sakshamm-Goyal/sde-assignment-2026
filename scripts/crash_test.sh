#!/usr/bin/env bash
# Crash-recovery test: kill -9 the controller at random moments, restart it, let it finish, then verify.
# usage: scripts/crash_test.sh [scenario] [kills] [port]     -> reports/crash_test.log
set -uo pipefail
cd "$(dirname "$0")/.."
SC=${1:-scenarios/public_02_incidents.yaml}; KILLS=${2:-8}; PORT=${3:-8740}
NAME=$(basename "$SC" .yaml); PY=${PYTHON:-.venv/bin/python}; RUN=runs/crash_$NAME; ST=state/crash_$NAME
LOG=reports/crash_test.log; mkdir -p reports logs; : > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }
$PY -m sim serve --scenario "$SC" --run-dir "$RUN" --port "$PORT" --force > logs/sim_crash.log 2>&1 &
SIM=$!; trap 'kill $SIM 2>/dev/null || true' EXIT
until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null; do sleep 1; done
rm -rf "$ST"
say "crash test on $NAME: $KILLS x kill -9 at random times, then run to completion"
for i in $(seq 1 "$KILLS"); do
  CTL_STATE_DIR=$ST ./run.sh "http://127.0.0.1:$PORT" 2>> logs/ctl_crash.log &
  CTL=$!
  sleep "$($PY -c "import random; print(round(random.uniform(0.4, 2.5), 2))")"
  # kill the python process (run.sh execs into it)
  kill -9 $CTL 2>/dev/null; wait $CTL 2>/dev/null
  say "kill #$i at sim $(curl -s http://127.0.0.1:$PORT/sim/state | $PY -c 'import json,sys; print(json.load(sys.stdin)["ts"])')"
done
CTL_STATE_DIR=$ST ./run.sh "http://127.0.0.1:$PORT" 2>> logs/ctl_crash.log
say "final run exited with $?"
$PY - "$PORT" "$ST/$NAME.db" <<'PY' | tee -a "$LOG"
import json, sqlite3, sys, httpx
port, db = sys.argv[1], sys.argv[2]
c = httpx.Client(base_url=f"http://127.0.0.1:{port}")
st = c.get("/sim/state").json()
s = sqlite3.connect(db)
ok = True
def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
check("scenario finished", st["finished"], st["ts"])
ing = s.execute("SELECT SUM(events) FROM chunks").fetchone()[0]
check("every event ingested exactly once", ing == st["last_event_id"], f"(store {ing} vs sim {st['last_event_id']})")
dup = 0
for w in c.get("/workflows").json():
    hist = c.get(f"/workflows/{w['workflow_id']}/config/history").json()
    pids = [v["proposal_id"] for v in hist if v["proposal_id"]]
    dup += len(pids) - len(set(pids))
    ours = {v["version"] for v in hist if v["actor"].startswith("controller")}
    rec = {r[0] for r in s.execute("SELECT applied_version FROM proposals WHERE wf=? AND status='applied'", (w["workflow_id"],))}
    check(f"{w['workflow_id']}: store records every applied change", ours == rec, f"sim {sorted(ours)} store {sorted(rec)}")
check("no change applied twice", dup == 0)
inflight = s.execute("SELECT COUNT(*) FROM proposals WHERE status IN ('submitting','applying')").fetchone()[0]
check("nothing left half-sent", inflight == 0)
appr = {a["approval_id"]: a["status"] for a in c.get("/approvals").json()}
mine = dict(s.execute("SELECT approval_id, status FROM proposals WHERE approval_id IS NOT NULL").fetchall())
lost = [a for a in appr if a not in mine]
check("no approval lost", not lost, str(lost))
lapsed = [a for a, v in appr.items() if v == "lapsed"]
check("no approval lapsed", not lapsed, str(lapsed))
recon = s.execute("SELECT COUNT(*) FROM decisions WHERE type='reconcile'").fetchone()[0]
print(f"reconcile decisions: {recon}; restarts survived; proposals by status: "
      f"{dict(s.execute('SELECT status, COUNT(*) FROM proposals GROUP BY status').fetchall())}")
print("RESULT:", "PASS" if ok else "FAIL")
PY
[ -f "runs/base_$NAME/_truth/aggregates.json" ] && $PY -m sim grade --run "$RUN" --baseline "runs/base_$NAME" --out reports/crash_test_grade.md >/dev/null && \
  say "grade after crashes: $(grep '^| ALL' reports/crash_test_grade.md)"
