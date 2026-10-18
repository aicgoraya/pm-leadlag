#!/usr/bin/env python3
"""Closed-hours tables for the paper from a quick_weekend.py weekend.csv.

Steps
  1. Artifact filter: drop closures that span the 2025-12-27 01:01 UTC book
     reset, and rows where p0 or p1 is exactly 0.50 (reset value).
  2. Dedup: one row per (event cluster, asset, closure), keeping the sibling
     with the largest |x_logit|.
  3. Regressions with closure-clustered SE: all closures, overnight only
     (closure < 24 h), weekends only, controls; 30-min and 1-min horizons.

Writes weekend_clean.csv, weekend_clean_dedup.csv, closure_tables.csv to
the results dir and prints the tables.

Usage: python scripts/closure_tables.py results/quick
"""
import sys
from pathlib import Path

import pandas as pd

from pmll import weekend

sys.path.insert(0, str(Path(__file__).parent))
from quick_weekend import dedup_rows  # noqa: E402

RESET = pd.Timestamp("2025-12-27 01:01", tz="UTC")


def clean(wk: pd.DataFrame) -> pd.DataFrame:
    lo = pd.to_datetime(wk["last_open"], utc=True)
    ro = pd.to_datetime(wk["reopen"], utc=True)
    bad = ((lo <= RESET) & (ro >= RESET)) | (wk["p0"] == 0.5) | (wk["p1"] == 0.5)
    return wk[~bad].reset_index(drop=True)


def main(res_dir):
    res = Path(res_dir)
    wk = pd.read_csv(res / "weekend.csv")
    wc = clean(wk); wc.to_csv(res / "weekend_clean.csv", index=False)
    tr, ct = wc[wc.category != "control"], wc[wc.category == "control"]
    trd, ctd = dedup_rows(tr), dedup_rows(ct)
    pd.concat([trd, ctd], ignore_index=True).to_csv(res / "weekend_clean_dedup.csv", index=False)
    on = trd[trd["closure_minutes"] < 24 * 60]
    rows = []
    specs = [("all closures", trd, 30, False), ("all closures, 1-min gap", trd, 1, False),
             ("overnight only", on, 30, False), ("weekends only", trd, 30, True),
             ("controls", ctd, 30, False)]
    for label, g, h, wo in specs:
        for sym, gg in g.groupby("asset"):
            if len(gg) < 30:
                continue
            r = weekend.gap_regression(gg, h, control_pre=True, weekends_only=wo)
            rows.append({"sample": label, "asset": sym, **r})
    for cat, g in trd.groupby("category"):
        for sym, gg in g.groupby("asset"):
            if len(gg) < 30:
                continue
            r = weekend.gap_regression(gg, 30, control_pre=True)
            rows.append({"sample": f"category {cat}", "asset": sym, **r})
    df = pd.DataFrame(rows)
    df.to_csv(res / "closure_tables.csv", index=False)
    cols = ["sample", "asset", "n", "n_clusters", "beta", "t", "p", "t_pre"]
    print(f"rows: {len(wk)} raw, {len(wc)} clean, {len(trd)} treated dedup, {len(ctd)} control dedup")
    print("event clusters (treated):", trd["cluster"].nunique(), "| markets:", trd["conditionId"].nunique())
    print(df[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/quick")
