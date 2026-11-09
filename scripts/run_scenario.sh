#!/usr/bin/env bash
# Run one scenario end to end: baseline (cached), simulator, controller via ./run.sh, grade.
# usage: scripts/run_scenario.sh scenarios/public_01_dev.yaml [port]
set -euo pipefail
cd "$(dirname "$0")/.."
SC=$1; PORT=${2:-8700}; NAME=$(basename "$SC" .yaml)
PY=${PYTHON:-.venv/bin/python}
mkdir -p runs reports logs
[ -f "runs/base_$NAME/_truth/aggregates.json" ] || $PY -m sim baseline --scenario "$SC" --run-dir "runs/base_$NAME"
$PY -m sim serve --scenario "$SC" --run-dir "runs/mine_$NAME" --port "$PORT" --force > "logs/sim_$NAME.log" 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null || true' EXIT
rm -rf "state/$NAME"
T0=$(date +%s)
CTL_STATE_DIR="state/$NAME" ./run.sh "http://127.0.0.1:$PORT" 2> "logs/ctl_$NAME.log"
echo "controller wall-clock: $(( $(date +%s) - T0 ))s"
$PY -m sim grade --run "runs/mine_$NAME" --baseline "runs/base_$NAME" --out "reports/$NAME.md" > /dev/null
sed -n '1,40p' "reports/$NAME.md"
