#!/usr/bin/env bash
# False-winner rate: run every A/A private scenario (no true effects) and count promotions per experiment.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-.venv/bin/python}; OUT=reports/aa_false_winners.md
echo "# A/A false-winner rate (no true effects anywhere)" > $OUT; echo >> $OUT
echo "| scenario | experiments (wf x dim) | promotions (= false winners) | harmful | conclusion Δ |" >> $OUT; echo "|---|---|---|---|---|" >> $OUT
TOT=0; FW=0
for f in scenarios/private/priv_aa*.yaml; do
  n=$(basename $f .yaml); scripts/run_scenario.sh $f 8712 >/dev/null 2>&1
  e=$(sqlite3 state/$n/$n.db "select count(*) from experiments where scope='all'")
  p=$(sqlite3 state/$n/$n.db "select count(*) from proposals where status='applied' and intents like '%\"type\": \"promote\"%'")
  h=$(grep -o 'harmful: [0-9]*' reports/$n.md | head -1 | grep -o '[0-9]*' || echo 0)
  echo "| $n | $e | $p | ${h:-0} | $(grep '^| ALL' reports/$n.md | cut -d'|' -f4) |" >> $OUT
  TOT=$((TOT+e)); FW=$((FW+p))
done
echo >> $OUT; echo "Total: $FW false winners in $TOT experiments." >> $OUT
cat $OUT
