#!/usr/bin/env python3
"""Pull 1-minute OHLCV bars from DataBento for the conventional assets.

Usage:
    export DATABENTO_API_KEY=db-...
    python scripts/pull_databento.py 2024-01-01 2026-10-01 data/raw/databento

Pulls, per symbol, the continuous front-month (`.c.0`) for CME futures from
GLBX.MDP3, and the ETFs/equities from XNAS.ITCH (or DBEQ.BASIC if you have
it). Writes one parquet per symbol with columns ts_event, open, high, low,
close, volume, symbol.

Cost: check the estimate first with --estimate; ohlcv-1m is cheap. The free
signup credit is usually enough for 2-3 years of ~10 symbols at 1-minute
bars, but confirm with the printed estimate before running.

If you don't have DataBento, the ETF side (USO, ITA, LMT, RTX, GLD, TLT,
SPY) can come from Polygon.io (free tier: 2 years of minute aggregates,
5 req/min) — see pull_polygon.py. The futures side has no free minute
source; use ETFs as proxies (USO≈CL, GLD≈GC, TLT≈ZB, SPY≈ES, VIXY≈VX) and
say so in the paper.
"""
import os
import sys
from pathlib import Path

import pandas as pd

FUTURES = {"CL": "CL.c.0", "ES": "ES.c.0", "ZN": "ZN.c.0", "GC": "GC.c.0", "BZ": "BZ.c.0"}
EQUITIES = ["ITA", "LMT", "RTX", "USO", "GLD", "TLT", "SPY", "XLE"]


def main(start: str, end: str, out_dir: str, estimate_only: bool):
    import databento as db  # pip install databento

    client = db.Historical(os.environ["DATABENTO_API_KEY"])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    jobs = [("GLBX.MDP3", sym, name, "continuous") for name, sym in FUTURES.items()]
    jobs += [("XNAS.ITCH", sym, sym, "raw_symbol") for sym in EQUITIES]

    for dataset, sym, name, stype in jobs:
        f = out / f"{name}.parquet"
        if f.exists():
            print("skip", name)
            continue
        kw = dict(dataset=dataset, symbols=[sym], schema="ohlcv-1m", start=start, end=end,
                  stype_in=stype)
        cost = client.metadata.get_cost(**kw)
        print(f"{name:5s} {dataset} {sym:10s} est. cost ${cost:.2f}")
        if estimate_only:
            continue
        data = client.timeseries.get_range(**kw)
        df = data.to_df().reset_index()
        df["symbol"] = name
        df.to_parquet(f)
        print(f"  wrote {len(df)} bars")


if __name__ == "__main__":
    est = "--estimate" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], args[1], args[2] if len(args) > 2 else "data/raw/databento", est)
