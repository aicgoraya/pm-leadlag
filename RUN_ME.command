#!/bin/bash
# Double-click me. Sets up the environment, runs tests, pulls Polymarket minute data for all 91 markets.
cd "$(dirname "$0")"
echo "== pm-leadlag: setup + Polymarket pull =="
python3 --version || { echo "python3 missing"; read -p "press enter"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e ".[dev]"
echo "== running tests (expect 13 passed) =="
pytest -q 2>&1 | tail -3
echo "== pulling Polymarket price history (1-2 hours; safe to rerun, skips done markets) =="
python scripts/pull_polymarket.py data/events.csv data/raw/polymarket 2>&1 | tee -a data/raw/pull_polymarket.log
echo "== DONE. Leave this window; Claude reads data/raw/polymarket next. =="
