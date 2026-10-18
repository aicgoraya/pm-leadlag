#!/usr/bin/env python3
"""Free fallback: minute bars for ETFs/equities from Massive (formerly Polygon.io).

Sign up at https://massive.com (free Basic plan: 2 years of minute aggregates,
5 requests/min). The API host is still api.polygon.io as of Oct 2026; if that
stops working, set POLYGON_BASE to the new host.

Usage:
    export POLYGON_API_KEY=...
    python scripts/pull_polygon.py 2024-10-01 2026-10-01 data/raw/polygon

Free tier: 5 requests/minute, 2 years of history, 50k bars per request
(so ~35 trading days per request at 1-min for regular hours). The script
sleeps to stay under the limit; 8 symbols x 2 years ≈ 25 min.
Writes one parquet per symbol in the generic schema (ts, open, high, low,
close, volume) that pmll.assets.load_bars reads.
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

SYMBOLS = ["USO", "ITA", "LMT", "RTX", "GLD", "TLT", "SPY", "XLE", "VIXY"]


def main(start: str, end: str, out_dir: str):
    key = os.environ["POLYGON_API_KEY"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    for sym in SYMBOLS:
        f = out / f"{sym}.parquet"
        if f.exists():
            print("skip", sym)
            continue
        base = os.environ.get("POLYGON_BASE", "https://api.polygon.io")
        url = f"{base}/v2/aggs/ticker/{sym}/range/1/minute/{start}/{end}"
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": key}
        rows = []
        while url:
            r = s.get(url, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(15)
                continue
            r.raise_for_status()
            js = r.json()
            rows.extend(js.get("results", []))
            url = js.get("next_url")
            params = {"apiKey": key}
            time.sleep(13)  # 5 req/min
        if not rows:
            print("no data", sym)
            continue
        df = pd.DataFrame(rows).rename(columns={"t": "ts", "o": "open", "h": "high",
                                                "l": "low", "c": "close", "v": "volume"})
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df[["ts", "open", "high", "low", "close", "volume"]].to_parquet(f)
        print(sym, len(df), "bars")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "data/raw/polygon")
