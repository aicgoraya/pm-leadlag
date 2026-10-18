#!/bin/bash
# Step 3: run the full battery and write results/*.csv
cd "$(dirname "$0")"
source .venv/bin/activate
BARS=data/raw/databento; [ -d "$BARS" ] || BARS=data/raw/polygon
echo "== running analysis with bars from $BARS =="
python scripts/run_analysis.py data/events.csv data/raw/polymarket "$BARS" results 2>&1 | tee results_run.log
echo "== DONE. Results in results/ =="
read -p "press enter to close"
