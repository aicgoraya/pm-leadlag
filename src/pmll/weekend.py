"""Closed-hours (weekend) design.

For each scheduled closure of the asset's venue (weekends; optionally the
CME daily break and holidays inferred from missing bars), measure

    x_c = PM log-odds change accumulated over the closure
          = logit(p at reopen) - logit(p at last close)
    y_c = asset log return from last close to h minutes after reopen

and regress y on x across closures, signed by the asset hypothesis.

This is the cleanest test in the paper: during the closure the asset
*cannot* react, so any relation between x and the reopen gap cannot be
simultaneity. It generalises the election-night observation in Aktug &
Torul (2026) to many events and many assets.

Controls / robustness:
  * Include closures with |x| small as the comparison group (they are the
    "no news" weekends).
  * Add the pre-closure PM move (Friday) as a regressor to check the asset
    had not already priced it.
  * Report results excluding the daily 1-hour break (noisy) and separately
    for weekends only.
  * Winsorise x at 1/99 pct because thin weekend PM books produce outliers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import calendar as cal
from .assets import gap_return
from .polymarket import logit


def empirical_closed_windows(asset_grid: pd.DataFrame, start, end, min_minutes: int):
    """Closures from the bars themselves (open_mkt mask), not the scheduled calendar.

    Handles extended-hours ETF data (closure = 20:00-04:00 ET + weekends),
    holidays, and early closes without hard-coding any of them.
    """
    g = asset_grid.loc[start:end, "open_mkt"].to_numpy()
    idx = asset_grid.loc[start:end].index
    out, i, n = [], 0, len(idx)
    while i < n:
        if g[i]:
            i += 1; continue
        j = i
        while j < n and not g[j]:
            j += 1
        if j - i >= min_minutes and i > 0 and j < n:
            out.append((idx[i - 1], idx[j]))
        i = j
    return out


def closure_table(pm_grid: pd.DataFrame, asset_grid: pd.DataFrame, venue: str,
                  horizons=(1, 5, 30, 60), min_minutes: int = 120,
                  hyp_sign: int = 1, max_stale: int = 720,
                  use_scheduled: bool = False) -> pd.DataFrame:
    """One row per closure with PM move during closure and asset reopen returns.

    Closures come from the bars' own open mask by default; use_scheduled=True
    uses the scheduled CME/NYSE calendar instead (useful for synthetic data).
    """
    start, end = max(pm_grid.index[0], asset_grid.index[0]), min(pm_grid.index[-1], asset_grid.index[-1])
    if use_scheduled:
        wins = cal.closed_windows(start, end, venue, min_minutes=min_minutes)
    else:
        wins = empirical_closed_windows(asset_grid, start, end, min_minutes)
    p = pm_grid["p"]
    stale = pm_grid["stale"]
    rows = []
    for last_open, reopen in wins:
        if last_open not in p.index or reopen not in p.index:
            continue
        p0, p1 = p.loc[last_open], p.loc[reopen]
        if np.isnan(p0) or np.isnan(p1):
            continue
        if stale.loc[reopen] > max_stale:
            continue  # PM dead during closure -> uninformative
        x = float(logit(pd.Series([p1])).iloc[0] - logit(pd.Series([p0])).iloc[0])
        # pre-closure PM move: last 6 open hours before close
        pre_t = last_open - pd.Timedelta(hours=6)
        x_pre = np.nan
        if pre_t in p.index and not np.isnan(p.loc[pre_t]):
            x_pre = float(logit(pd.Series([p0])).iloc[0] - logit(pd.Series([p.loc[pre_t]])).iloc[0])
        row = {"last_open": last_open, "reopen": reopen,
               "closure_minutes": int((reopen - last_open).total_seconds() // 60),
               "p0": p0, "p1": p1, "x_logit": x, "x_dp": p1 - p0, "x_pre_logit": x_pre}
        for h in horizons:
            row[f"y_{h}"] = hyp_sign * gap_return(asset_grid, last_open, reopen, h)
        rows.append(row)
    return pd.DataFrame(rows)


def winsorize(s: pd.Series, lo=0.01, hi=0.99) -> pd.Series:
    a, b = s.quantile(lo), s.quantile(hi)
    return s.clip(a, b)


def gap_regression(tbl: pd.DataFrame, horizon: int = 1, control_pre: bool = True,
                   weekends_only: bool = False, cluster: str | None = "reopen") -> dict:
    """OLS of signed reopen return on PM closure move.

    Errors: cluster-robust by `cluster` column (default "reopen", i.e. the
    closure instance, because every market shares the same weekends and the
    same reopen return of a given asset; treating 29 Iran rungs on one Sunday
    as 29 observations would be wrong). Falls back to HC3 when there are
    fewer than 10 clusters or cluster=None.
    """
    d = tbl.copy()
    if weekends_only:
        d = d[d["closure_minutes"] >= 24 * 60]
    ycol = f"y_{horizon}"
    d = d.dropna(subset=["x_logit", ycol])
    if len(d) < 8:
        return {"beta": np.nan, "t": np.nan, "p": np.nan, "r2": np.nan, "n": len(d),
                "n_clusters": 0, "horizon": horizon}
    X = pd.DataFrame({"x": winsorize(d["x_logit"])})
    if control_pre and d["x_pre_logit"].notna().sum() >= 8:
        X["x_pre"] = winsorize(d["x_pre_logit"].fillna(0))
    X = sm.add_constant(X)
    n_cl = int(d[cluster].nunique()) if cluster and cluster in d else 0
    if cluster and n_cl >= 10:
        groups = pd.factorize(d[cluster])[0]
        res = sm.OLS(d[ycol].to_numpy(), X.to_numpy()).fit(cov_type="cluster", cov_kwds={"groups": groups})
        cols = list(X.columns)
        bi = cols.index("x")
        out = {"beta": float(res.params[bi]), "t": float(res.tvalues[bi]), "p": float(res.pvalues[bi])}
        out["beta_pre"] = float(res.params[cols.index("x_pre")]) if "x_pre" in cols else np.nan
        out["t_pre"] = float(res.tvalues[cols.index("x_pre")]) if "x_pre" in cols else np.nan
        out["se_type"] = "cluster"
    else:
        res = sm.OLS(d[ycol], X).fit(cov_type="HC3")
        out = {"beta": float(res.params["x"]), "t": float(res.tvalues["x"]), "p": float(res.pvalues["x"]),
               "beta_pre": float(res.params.get("x_pre", np.nan)),
               "t_pre": float(res.tvalues.get("x_pre", np.nan)), "se_type": "HC3"}
    out.update({"r2": float(res.rsquared), "n": int(len(d)), "n_clusters": n_cl, "horizon": horizon})
    return out


def gap_regression_table(tbl: pd.DataFrame, horizons=(1, 5, 30, 60)) -> pd.DataFrame:
    rows = [gap_regression(tbl, h) for h in horizons]
    return pd.DataFrame(rows).set_index("horizon")
