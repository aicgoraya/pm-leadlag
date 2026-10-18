"""Conventional-asset minute bars.

Supported inputs
----------------
* DataBento OHLCV-1m exports (CSV or parquet), schema `ohlcv-1m`, columns
  ts_event, open, high, low, close, volume, symbol. Front-month continuous
  contracts via `symbols=CL.c.0` etc.
* Generic CSV with columns ts, open, high, low, close, volume (UTC).

Everything is normalised to a UTC minute index with columns
open, high, low, close, volume, and a boolean `open_mkt` marking minutes that
had a bar (empirical session mask, which handles holidays and early closes
without a hard-coded calendar).

Returns are log returns on close-to-close. For event studies we use
`close` at minute t relative to the pre-event anchor.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import calendar as cal

ASSET_VENUE = {
    # CME futures
    "CL": "cme", "BZ": "cme", "ES": "cme", "ZN": "cme", "ZB": "cme", "GC": "cme", "VX": "cme",
    # NYSE/ARCA equities & ETFs
    "ITA": "nyse", "LMT": "nyse", "RTX": "nyse", "NOC": "nyse", "GD": "nyse",
    "USO": "nyse", "GLD": "nyse", "TLT": "nyse", "SPY": "nyse", "XLE": "nyse",
}


def load_bars(path: str | Path, symbol: str | None = None) -> pd.DataFrame:
    """Load minute bars from CSV/parquet into the normalised schema."""
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p)
    if symbol is not None and "symbol" in df.columns:
        df = df[df["symbol"] == symbol]
    tcol = next(c for c in ("ts_event", "ts", "timestamp", "datetime", "time") if c in df.columns)
    ts = pd.to_datetime(df[tcol], utc=True)
    out = pd.DataFrame({
        "open": df["open"].astype(float).to_numpy(),
        "high": df["high"].astype(float).to_numpy(),
        "low": df["low"].astype(float).to_numpy(),
        "close": df["close"].astype(float).to_numpy(),
        "volume": df["volume"].astype(float).to_numpy() if "volume" in df.columns else np.nan,
    }, index=ts.dt.floor("min"))
    out.index.name = "ts"
    out = out[~out.index.duplicated(keep="last")].sort_index()
    # DataBento prices for futures are in units already scaled; nothing to do.
    return out


def to_minute_grid(bars: pd.DataFrame, start=None, end=None,
                   regular_hours_only: bool = False, venue: str | None = None) -> pd.DataFrame:
    """Reindex to a full minute grid; `open_mkt` is True where a bar existed.

    Closes are forward-filled across closed minutes so that `close.shift`
    arithmetic is well-defined, but returns should be computed only across
    consecutive *open* minutes (see `log_returns`).

    Massive/Polygon equity bars include pre-market (04:00 ET) and after-hours
    (to 20:00 ET). By default those count as open (empirical mask). With
    regular_hours_only=True and venue="nyse", bars outside 09:30-16:00 ET are
    dropped so only regular-session prices are used; the weekend/closure
    design then sees overnight gaps too. Run both as a robustness pair.
    """
    start = (start or bars.index[0]).floor("min")
    end = (end or bars.index[-1]).floor("min")
    if regular_hours_only:
        if venue is None:
            raise ValueError("venue required for regular_hours_only")
        bars = bars[cal.open_mask(bars.index, venue)]
    grid = pd.date_range(start, end, freq="min", tz="UTC", name="ts")
    out = bars.reindex(grid)
    out["open_mkt"] = out["close"].notna()
    out["close"] = out["close"].ffill()
    return out


def log_returns(grid: pd.DataFrame, k: int = 1) -> pd.Series:
    """k-minute log return over open minutes only.

    Within a session, return at t is log(close_t / close_{t-k}) using only
    open minutes. Across a closure, the first open minute's return is the
    gap return vs the last close (this is what the weekend design uses).
    """
    c = grid.loc[grid["open_mkt"], "close"]
    r = np.log(c).diff(k)
    return r.reindex(grid.index)


def gap_return(grid: pd.DataFrame, last_open: pd.Timestamp, first_reopen: pd.Timestamp,
               horizon_min: int = 1) -> float:
    """Log return from last pre-closure close to `horizon_min` after reopen.

    horizon_min=1 gives the open-gap; 30 gives the first-half-hour move.
    """
    c0 = grid.loc[:last_open, "close"].dropna()
    if c0.empty:
        return np.nan
    c0 = c0.iloc[-1]
    post = grid.loc[first_reopen:, :]
    post = post[post["open_mkt"]]
    if len(post) < horizon_min:
        return np.nan
    c1 = post["close"].iloc[horizon_min - 1]
    return float(np.log(c1 / c0))
