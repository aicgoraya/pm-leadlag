#!/usr/bin/env python3
"""Run the full battery for every (market, asset) pair and write result tables.

Usage:
    python scripts/run_analysis.py data/events.csv data/raw/polymarket data/raw/databento results/

Inputs
  events.csv      from scripts/build_events (columns incl. conditionId, category, is_control)
  polymarket dir  <conditionId>.grid.parquet from pull_polymarket.py
  bars dir        <SYMBOL>.parquet from pull_databento.py / pull_polygon.py

Asset hypotheses (sign of asset response to P(event) rising) live in
HYPOTHESES below. Edit per category. Controls get all assets with sign +1 and
are expected to show nothing.

Outputs (CSV)
  results/jumps.csv            every detected jump, with venue-open flag
  results/eventstudy.csv       CAR summary per (market, asset)
  results/leadlag.csv          Granger/TE/xcorr per (market, asset) and pooled
  results/weekend.csv          closure table per (market, asset)
  results/weekend_reg.csv      gap regressions pooled by category x asset
  results/backtest.csv         tradability summary per (category, asset)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from pmll import align, backtest, eventstudy, jumps, leadlag, weekend
from pmll import calendar as cal
from pmll.assets import ASSET_VENUE, load_bars, to_minute_grid

# +1: asset rises when P(event) rises. -1: falls.
HYPOTHESES = {
    "iran":           {"CL": +1, "BZ": +1, "USO": +1, "GC": +1, "GLD": +1, "ES": -1, "SPY": -1,
                       "ZN": +1, "TLT": +1, "ITA": +1, "LMT": +1, "RTX": +1, "XLE": +1, "VIXY": +1},
    "oil":            {"CL": +1, "BZ": +1, "USO": +1, "XLE": +1, "ES": -1, "SPY": -1},
    "russia_ukraine": {"CL": -1, "BZ": -1, "USO": -1, "ES": +1, "SPY": +1, "ITA": -1, "LMT": -1,
                       "RTX": -1, "GC": -1, "GLD": -1},  # ceasefire = de-escalation
    "israel":         {"CL": +1, "USO": +1, "GC": +1, "GLD": +1, "ITA": +1, "ES": -1, "SPY": -1},
    "china_taiwan":   {"ES": -1, "SPY": -1, "GC": +1, "GLD": +1, "ITA": +1, "ZN": +1, "TLT": +1},
    "venezuela":      {"CL": +1, "USO": +1, "ES": -1, "SPY": -1},
    "tariffs":        {"ES": -1, "SPY": -1, "ZN": +1, "TLT": +1, "GC": +1},
    "other_military": {"ITA": +1, "LMT": +1, "RTX": +1, "GC": +1, "GLD": +1, "ES": -1, "SPY": -1},
    "control":        {},  # filled with +1 for every available asset at runtime
}


def main(events_csv, pm_dir, bars_dir, out_dir, regular_hours_only=False):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ev = pd.read_csv(events_csv)
    pm_dir, bars_dir = Path(pm_dir), Path(bars_dir)

    # load all asset grids once
    assets = {}
    for f in sorted(bars_dir.glob("*.parquet")):
        sym = f.stem
        if sym not in ASSET_VENUE:
            print("unknown symbol, skipping:", sym); continue
        assets[sym] = to_minute_grid(load_bars(f), regular_hours_only=regular_hours_only,
                                     venue=ASSET_VENUE[sym])
        print(f"asset {sym}: {assets[sym]['open_mkt'].sum():,} open minutes"
              + (" (regular hours only)" if regular_hours_only else " (incl. extended hours)"))

    jump_rows, es_rows, ll_rows, wk_rows, bt_trades = [], [], [], [], []

    for _, r in ev.iterrows():
        cid, cat = r["conditionId"], r["category"]
        gf = pm_dir / f"{cid}.grid.parquet"
        if not gf.exists():
            continue
        pm = pd.read_parquet(gf)
        j = jumps.detect(pm)
        if j.empty:
            continue
        hyp = HYPOTHESES.get(cat, {}) or {s: +1 for s in assets}
        for sym, sign in hyp.items():
            if sym not in assets:
                continue
            venue = ASSET_VENUE[sym]
            ag = assets[sym]
            df = align.align(pm, ag)
            if df.empty:
                continue
            jj = j[(j.index >= df.index[0]) & (j.index <= df.index[-1])]
            om = cal.open_mask(jj.index, venue)
            for t, row in jj.iterrows():
                jump_rows.append({"conditionId": cid, "category": cat, "asset": sym, "ts": t,
                                  "dp": row["dp"], "lm": row["lm_flag"], "thr": row["thr_flag"],
                                  "venue_open": bool(cal.is_open(t, venue))})
            # event study
            cars = eventstudy.event_cars(df, jj, sign)
            if len(cars) >= 3:
                plc = eventstudy.placebo_cars(df, n=1000, exclude=jj.index)
                summ = eventstudy.summarize(cars, plc)
                for h, s in summ.iterrows():
                    es_rows.append({"conditionId": cid, "category": cat, "asset": sym, "horizon": h, **s})
            # lead-lag on overlap
            ov = align.overlap(df, max_stale=30)
            if len(ov) > 500:
                b = leadlag.battery(ov)
                ll_rows.append({"conditionId": cid, "category": cat, "asset": sym, **b})
            # weekend design
            tbl = weekend.closure_table(pm, ag, venue, min_minutes=24 * 60, hyp_sign=sign)
            if len(tbl):
                tbl["conditionId"], tbl["category"], tbl["asset"] = cid, cat, sym
                wk_rows.append(tbl)
            # backtest
            tr = backtest.trades_from_jumps(df, jj, sign, venue, min_dp=0.05)
            if len(tr):
                tr["conditionId"], tr["category"], tr["asset"] = cid, cat, sym
                bt_trades.append(tr)

    pd.DataFrame(jump_rows).to_csv(out / "jumps.csv", index=False)
    pd.DataFrame(es_rows).to_csv(out / "eventstudy.csv", index=False)
    pd.DataFrame(ll_rows).to_csv(out / "leadlag.csv", index=False)
    if wk_rows:
        wk = pd.concat(wk_rows)
        wk.to_csv(out / "weekend.csv", index=False)
        regs = []
        for (cat, sym), g in wk.groupby(["category", "asset"]):
            for h in (1, 5, 30, 60):
                res = weekend.gap_regression(g, h)
                regs.append({"category": cat, "asset": sym, **res})
        pd.DataFrame(regs).to_csv(out / "weekend_reg.csv", index=False)
    if bt_trades:
        bt = pd.concat(bt_trades)
        bt.to_csv(out / "backtest_trades.csv", index=False)
        summ = [{"category": c, "asset": s, **backtest.summarize_trades(g)}
                for (c, s), g in bt.groupby(["category", "asset"])]
        pd.DataFrame(summ).to_csv(out / "backtest.csv", index=False)
    print("done ->", out)


if __name__ == "__main__":
    rh = "--regular-hours" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*args[:4], regular_hours_only=rh)
