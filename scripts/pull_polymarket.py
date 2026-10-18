#!/usr/bin/env python3
"""Pull minute-fidelity Polymarket price history for every market in the event list.

Usage:
    python scripts/pull_polymarket.py data/events.csv data/raw/polymarket

For each row, fetches the YES token's price history from startDate to
endDate (+1 day) in 24-hour chunks and writes data/raw/polymarket/<conditionId>.parquet
with columns p (raw points, UTC index). Also writes <conditionId>.grid.parquet
on a 1-minute grid (p, n_obs, stale).

Rate limits: the CLOB endpoint is unauthenticated; 4 req/s is fine. A 2-year
market at 24h chunks is ~730 requests (~3-4 min). 40 markets ≈ 1-2 hours.
Rerunning skips files that already exist.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from pmll.polymarket import fetch_price_history, to_minute_grid


def main(events_csv: str, out_dir: str):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ev = pd.read_csv(events_csv)
    s = requests.Session()
    for _, r in ev.iterrows():
        cid = r["conditionId"]
        f = out / f"{cid}.parquet"
        if f.exists():
            print("skip", cid[:10], r["question"][:60])
            continue
        start = pd.Timestamp(r["startDate"], tz="UTC")
        end = pd.Timestamp(r["endDate"], tz="UTC") + pd.Timedelta(days=1)
        print("pull", cid[:10], r["question"][:60], start.date(), "->", end.date())
        try:
            raw = fetch_price_history(str(r["yes_token_id"]), start, end, fidelity=1,
                                      chunk_hours=24, pause=0.25, session=s)
        except Exception as e:  # noqa: BLE001
            print("  FAILED", e)
            time.sleep(5)
            continue
        if raw.empty:
            print("  empty history")
            continue
        raw.to_parquet(f)
        grid = to_minute_grid(raw)
        grid.to_parquet(out / f"{cid}.grid.parquet")
        print(f"  {len(raw)} points, {grid['n_obs'].gt(0).mean():.1%} minutes with quotes")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data/raw/polymarket")
