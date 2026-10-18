"""Align a Polymarket probability series with an asset bar series.

The core object downstream is a DataFrame on a common UTC minute grid:

    pm_p        Polymarket probability (forward-filled)
    pm_logit    log-odds of pm_p
    pm_stale    minutes since last PM observation
    pm_n_obs    PM observations in the minute
    close       asset close (ffilled across closures)
    open_mkt    asset bar existed this minute
    r_asset     1-min asset log return (NaN when closed)
    d_logit     1-min change in PM log-odds

`overlap(df)` returns only minutes where the asset is open and the PM
series is fresh enough to be informative. Lead-lag tests run on that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .assets import log_returns
from .polymarket import logit


def align(pm_grid: pd.DataFrame, asset_grid: pd.DataFrame) -> pd.DataFrame:
    start = max(pm_grid.index[0], asset_grid.index[0])
    end = min(pm_grid.index[-1], asset_grid.index[-1])
    idx = pd.date_range(start, end, freq="min", tz="UTC", name="ts")
    df = pd.DataFrame(index=idx)
    df["pm_p"] = pm_grid["p"].reindex(idx)
    df["pm_logit"] = logit(df["pm_p"])
    df["pm_stale"] = pm_grid["stale"].reindex(idx)
    df["pm_n_obs"] = pm_grid["n_obs"].reindex(idx).fillna(0).astype(int)
    df["close"] = asset_grid["close"].reindex(idx)
    df["open_mkt"] = asset_grid["open_mkt"].reindex(idx).fillna(False).astype(bool)
    df["r_asset"] = log_returns(asset_grid).reindex(idx)
    df["d_logit"] = df["pm_logit"].diff()
    return df


def overlap(df: pd.DataFrame, max_stale: int = 30) -> pd.DataFrame:
    """Minutes where the asset is open and PM quote is at most `max_stale` old."""
    m = df["open_mkt"] & (df["pm_stale"] <= max_stale)
    return df.loc[m]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate to k-minute bars (sum of returns / log-odds changes).

    Only open minutes are aggregated; a bar with fewer than half its minutes
    open is dropped.
    """
    if minutes == 1:
        return df
    o = df[df["open_mkt"]]
    g = o.groupby(o.index.floor(f"{minutes}min"))
    out = pd.DataFrame({
        "r_asset": g["r_asset"].sum(min_count=1),
        "d_logit": g["d_logit"].sum(min_count=1),
        "n_open": g.size(),
        "pm_p": g["pm_p"].last(),
        "close": g["close"].last(),
    })
    out = out[out["n_open"] >= minutes / 2]
    out.index.name = "ts"
    return out
