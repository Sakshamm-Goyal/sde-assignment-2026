#!/usr/bin/env bash
# Load test on public_03: run the controller end to end and record throughput, lag, memory, wall-clock per day.
# usage: scripts/load_test.sh [port]   -> reports/public_03_load.md
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=${1:-8730}; NAME=public_03_load; PY=${PYTHON:-.venv/bin/python}
mkdir -p logs reports
$PY -m sim serve --scenario scenarios/$NAME.yaml --run-dir runs/mine_$NAME --port "$PORT" --force > logs/sim_$NAME.log 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null || true' EXIT
until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null; do sleep 2; done
rm -rf state/$NAME
T0=$(date +%s)
/usr/bin/time -l env CTL_STATE_DIR=state/$NAME ./run.sh "http://127.0.0.1:$PORT" 2> logs/ctl_$NAME.log || \
  /usr/bin/time -v env CTL_STATE_DIR=state/$NAME ./run.sh "http://127.0.0.1:$PORT" 2> logs/ctl_$NAME.log
WALL=$(( $(date +%s) - T0 ))
SIMRSS=$(ps -o rss= -p $SIM | awk '{print int($1/1024)}')
{
  echo "# Load test — public_03_load (12 workflows, ~650k dials/day)"; echo
  echo "Machine: $(uname -sm), $(sysctl -n hw.ncpu 2>/dev/null || nproc) CPUs. Controller and simulator on the same box."; echo
  echo "Controller total wall-clock (after simulator was ready, incl. 7 history days ingest + 5 live days): ${WALL}s"
  echo "Simulator RSS at end: ${SIMRSS} MB"; echo
  echo '```'; $PY -m controller status --db state/$NAME/$NAME.db; echo '```'
  echo; echo "Per-day breakdown (wall seconds spent per simulated day, from the metrics table):"; echo; echo '```'
  sqlite3 state/$NAME/$NAME.db "select 'D'||(minute/1440) day, sum(events) events, round(sum(ingest_s),1) ingest_s, round(sum(decide_s),1) decide_s, round(sum(advance_s),1) sim_advance_s, round(max(rss_mb)) rss_mb, round(sum(events)/max(sum(ingest_s),0.001)) ev_per_s from metrics group by minute/1440 order by minute/1440"
  echo '```'
  echo; echo "Decision lag per tick (ingest + decide, seconds): p50/p95/max"; echo '```'
  sqlite3 state/$NAME/$NAME.db "with t as (select ingest_s+decide_s x from metrics where minute>=0 order by x) select round((select x from t limit 1 offset (select count(*)/2 from t)),3), round((select x from t limit 1 offset (select count(*)*95/100 from t)),3), round((select max(x) from t),3)"
  echo '```'
} > reports/$NAME.md
grep -E "rss|maximum resident" logs/ctl_$NAME.log | tail -2 >> reports/$NAME.md || true
$PY -m sim grade --run runs/mine_$NAME --baseline runs/base_$NAME --out reports/${NAME}_grade.md > /dev/null || true
cat reports/$NAME.md
