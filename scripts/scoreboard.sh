#!/usr/bin/env bash
# Summarise every grade report in reports/ into reports/scoreboard.md (run the scenarios first).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-.venv/bin/python}
{
echo "# Scoreboard — public and private scenarios (final code)"; echo
echo "Private scenarios come from scripts/make_private_scenarios.py (different truth / policy / incidents). The controller never reads any scenario file. A/A false winners: reports/aa_false_winners.md."; echo
echo "| scenario | conclusion Δ | pickup Δ | engagement Δ | changes (harmful) | approval requests | rejected | expired | lapsed | apply conflicts | prompt-incident MTTR (min) | credits |"
echo "|---|---|---|---|---|---|---|---|---|---|---|---|"
for n in public_01_dev public_02_incidents public_03_load_grade priv_aa priv_policy priv_incidents priv_opposite; do
  [ -f reports/$n.md ] || continue
  $PY - "reports/$n.md" "$n" <<'PY'
import re, sys, json
t = open(sys.argv[1]).read(); n = sys.argv[2].replace("_grade", "")
c = [x.strip() for x in next(l for l in t.splitlines() if l.startswith("| ALL")).split("|")]
ch = re.search(r"(\d+) applied — (.*)", t)
harm = re.search(r"harmful: (\d+)", ch.group(2)); harm = harm.group(1) if harm else "0"
g = json.loads(t.split("## Governance")[1].split("```")[1])
mttr = ",".join(re.findall(r'"mttr_minutes": (\w+)', t)) or "—"
print(f"| {n} | {c[3]} | {c[5]} | {c[7]} | {ch.group(1)} ({harm}) | {g['approval_requests']} | {g['decisions'].get('rejected',0)} | "
      f"{g['decisions'].get('expired',0)} | {g['lapsed']} | {g['apply_conflicts']} | {mttr} | {re.search(r'Credits used: (\d+)', t).group(1)} |")
PY
done
} > reports/scoreboard.md
cat reports/scoreboard.md
