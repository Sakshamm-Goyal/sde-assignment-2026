#!/usr/bin/env bash
# Controller entrypoint. Contract: ./run.sh <SIM_URL> runs until the scenario finishes, no manual steps.
# Plain Python (no Docker): needs python3 >= 3.10 with httpx (already in requirements.txt for the simulator).
# State: one SQLite file per scenario under $CTL_STATE_DIR (default ./state). Re-running resumes after a crash;
# a fresh simulator world is detected and gets a fresh store (the old one is kept as *.old).
set -euo pipefail
SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" -c "import httpx" 2>/dev/null || "$PY" -m pip install -q -r requirements.txt
exec "$PY" -m controller run --url "$SIM_URL" --state-dir "${CTL_STATE_DIR:-state}"
