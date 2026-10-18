#!/usr/bin/env python3
"""Fast first look: closure-gap regressions with per-market signs and
cluster-robust errors, plus jump counts. Minutes, not hours.

Signs come from events.csv columns sign_<ASSET> (see assign_signs.py).
Errors are clustered by closure instance (reopen timestamp).
Two sample definitions:
  all     every (market, closure) row
  dedup   one row per (event cluster, closure): ladder siblings collapsed to
          the sibling with the largest |x| that closure. Event cluster =
          category + escalation sign + first 3 words of the question.

Usage: python scripts/quick_weekend.py data/events.csv data/raw/polymarket data/raw/polygon results/quick [--regular-hours]
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from pmll import jumps, weekend
from pmll.assets import ASSET_VENUE, load_bars, to_minute_grid

ASSETS = ["SPY", "USO", "XLE", "ITA", "LMT", "RTX", "GLD", "TLT", "VIXY"]


def event_cluster(row) -> str:
    words = re.sub(r"[^a-z ]", "", row["question"].lower()).split()
    return f"{row['category']}|{int(row['escalation'])}|{' '.join(words[:3])}"


def dedup_rows(wk: pd.DataFrame) -> pd.DataFrame:
    wk = wk.reset_index(drop=True).copy()  # concat leaves duplicate labels; .loc would explode
    wk["absx"] = wk["x_logit"].abs()
    idx = wk.groupby(["cluster", "asset", "reopen"])["absx"].idxmax()
    return wk.loc[idx].drop(columns="absx")


def reg_table(wk: pd.DataFrame, label: str, horizon: int = 30, weekends_only=False):
    rows = []
    for (cat, sym), g in wk.groupby(["category", "asset"]):
        res = weekend.gap_regression(g, horizon, control_pre=True, weekends_only=weekends_only)
        rows.append({"category": cat, "asset": sym, **res})
    df = pd.DataFrame(rows)
    print(f"\n=== {label}: by category x asset, {horizon}-min horizon"
          f"{', weekends only' if weekends_only else ''} (cluster SE by closure) ===")
    cols = ["category", "asset", "n", "n_clusters", "beta", "t", "p", "t_pre", "r2"]
    print(df.sort_values(["category", "p"])[cols].round(4).to_string(index=False))
    return df


def pooled_table(wk: pd.DataFrame, label: str, horizon: int = 30, weekends_only=False):
    rows = []
    for sym, g in wk.groupby("asset"):
        res = weekend.gap_regression(g, horizon, control_pre=True, weekends_only=weekends_only)
        rows.append({"asset": sym, **res})
    df = pd.DataFrame(rows)
    print(f"\n=== {label}: pooled per asset, {horizon}-min"
          f"{', weekends only' if weekends_only else ''} ===")
    print(df[["asset", "n", "n_clusters", "beta", "t", "p", "t_pre", "r2"]].round(4).to_string(index=False))
    return df


def main(events_csv, pm_dir, bars_dir, out_dir, regular_hours_only=False):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ev = pd.read_csv(events_csv)
    ev["cluster"] = ev.apply(event_cluster, axis=1)
    pm_dir, bars_dir = Path(pm_dir), Path(bars_dir)
    assets = {}
    for f in sorted(bars_dir.glob("*.parquet")):
        sym = f.stem
        if sym in ASSET_VENUE:
            assets[sym] = to_minute_grid(load_bars(f), regular_hours_only=regular_hours_only,
                                         venue=ASSET_VENUE[sym])
    print("assets:", list(assets), "| regular hours only:", regular_hours_only)

    jump_rows, wk_rows, n_mk = [], [], 0
    for _, r in ev.iterrows():
        cid, cat = r["conditionId"], r["category"]
        gf = pm_dir / f"{cid}.grid.parquet"
        if not gf.exists():
            continue
        n_mk += 1
        pm = pd.read_parquet(gf)
        j = jumps.detect(pm)
        for sym in assets:
            sign = int(r.get(f"sign_{sym}", 0))
            if sign == 0:
                continue
            ag = assets[sym]
            if len(j):
                jj = j[(j.index >= ag.index[0]) & (j.index <= ag.index[-1])]
                opn = ag["open_mkt"].reindex(jj.index).fillna(False).astype(bool)
                for t, row in jj.iterrows():
                    jump_rows.append({"conditionId": cid, "category": cat, "asset": sym, "ts": t,
                                      "dp": row["dp"], "venue_open": bool(opn.loc[t])})
            tbl = weekend.closure_table(pm, ag, ASSET_VENUE[sym], min_minutes=120, hyp_sign=sign)
            if len(tbl):
                tbl["conditionId"], tbl["category"], tbl["asset"], tbl["cluster"] = cid, cat, sym, r["cluster"]
                wk_rows.append(tbl)
    print("markets used:", n_mk)

    jd = pd.DataFrame(jump_rows); jd.to_csv(out / "jumps.csv", index=False)
    if len(jd):
        u = jd.drop_duplicates(["conditionId", "ts"])
        js = u.groupby("category").agg(n_jumps=("ts", "size"),
                                       frac_closed=("venue_open", lambda x: 1 - x.mean()),
                                       mean_abs_dp=("dp", lambda x: x.abs().mean()))
        print("\n=== jumps per category (unique market-minutes; frac during ETF-closed hours) ===")
        print(js.round(3).to_string())

    if not wk_rows:
        return
    wk = pd.concat(wk_rows, ignore_index=True); wk.to_csv(out / "weekend.csv", index=False)
    tr, ct = wk[wk.category != "control"], wk[wk.category == "control"]
    trd = dedup_rows(tr)

    reg_table(wk, "ALL rows")
    pooled_table(tr, "ALL rows, treated")
    pooled_table(ct, "ALL rows, controls (expect null)")
    pooled_table(trd, "DEDUP (one row per event cluster per closure), treated")
    pooled_table(trd, "DEDUP, treated", weekends_only=True)
    reg_table(trd, "DEDUP", weekends_only=False)
    # 1-min open gap as well, dedup
    pooled_table(trd, "DEDUP, treated", horizon=1)

    # --- Sanity 1: shuffle placebo. Permute x within asset across closures.
    # If the real t-stats are just "both series volatile in the same era",
    # shuffling x across *different* closures of the same market keeps the
    # marginal distributions and kills the pairing. Expect ~null.
    rng = np.random.default_rng(0)
    rows = []
    for sym, g in trd.groupby("asset"):
        g = g.copy()
        for cid, gg in g.groupby("conditionId"):
            g.loc[gg.index, "x_logit"] = rng.permutation(gg["x_logit"].to_numpy())
        res = weekend.gap_regression(g, 30, control_pre=False)
        rows.append({"asset": sym, **res})
    print("\n=== PLACEBO: x shuffled across closures within market (expect null) ===")
    print(pd.DataFrame(rows)[["asset", "n", "n_clusters", "beta", "t", "p"]].round(4).to_string(index=False))

    # --- Sanity 2: reverse direction. Does the asset's move BEFORE the closure
    # (last 60 open minutes) predict the PM move DURING the closure? If PM is
    # just catching up to oil, this will be significant too.
    print("\n=== REVERSE: PM closure move ~ asset return in last 60 min before close ===")
    rows = []
    for sym, g in trd.groupby("asset"):
        ag = assets[sym]
        pre = []
        for _, r in g.iterrows():
            lo = pd.Timestamp(r["last_open"])
            c = ag.loc[:lo, "close"].dropna()
            o = ag.loc[:lo]; o = o[o["open_mkt"]]
            if len(o) < 61:
                pre.append(np.nan); continue
            pre.append(float(np.log(o["close"].iloc[-1] / o["close"].iloc[-61])))
        g = g.assign(asset_pre=pre).dropna(subset=["asset_pre"])
        if len(g) < 20:
            continue
        X = sm.add_constant(g[["asset_pre"]])
        groups = pd.factorize(g["reopen"])[0]
        res = sm.OLS(g["x_logit"].to_numpy(), X.to_numpy()).fit(cov_type="cluster", cov_kwds={"groups": groups})
        rows.append({"asset": sym, "n": len(g), "beta": res.params[1], "t": res.tvalues[1], "p": res.pvalues[1]})
    print(pd.DataFrame(rows).round(4).to_string(index=False))


if __name__ == "__main__":
    rh = "--regular-hours" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*args[:4], regular_hours_only=rh)
