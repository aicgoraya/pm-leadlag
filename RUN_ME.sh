#!/bin/bash
# Run this in Terminal from ~/Documents/pm-leadlag  (the Claude sandbox can't reach Polymarket; your Mac can)
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install -q -e ".[dev]"
pytest -q                                   # expect: 13 passed
python scripts/pull_polymarket.py data/events.csv data/raw/polymarket   # ~1-2 h, no key needed
echo "Polymarket pull done. Next: asset bars (see README 'Getting the data'), then scripts/run_analysis.py"
