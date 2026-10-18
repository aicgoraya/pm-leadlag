#!/bin/bash
# Step 2: pull ETF minute bars from Massive (formerly Polygon.io), free tier.
# Before double-clicking: sign up at https://massive.com (free Basic plan), copy your API key,
# and paste it into the file  data/POLYGON_API_KEY.txt  (just the key, nothing else).
cd "$(dirname "$0")"
source .venv/bin/activate
KEYFILE=data/POLYGON_API_KEY.txt
if [ ! -s "$KEYFILE" ]; then
  echo "Missing $KEYFILE. Sign up at https://massive.com, then save your API key in that file."
  read -p "press enter to close"; exit 1
fi
export POLYGON_API_KEY="$(tr -d '[:space:]' < "$KEYFILE")"
echo "== pulling ETF minute bars 2024-10-01 .. 2026-10-16 (about 25 min at 5 req/min) =="
python scripts/pull_polygon.py 2024-10-01 2026-10-16 data/raw/polygon 2>&1 | tee -a data/raw/pull_polygon.log
echo "== DONE. Next: RUN_ME_3_analysis.command =="
read -p "press enter to close"
