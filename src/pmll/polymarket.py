"""Polymarket data access.

Two sources:

1. CLOB price history (REST, no auth):
   https://clob.polymarket.com/prices-history?market=<token_id>&startTs=..&endTs=..&fidelity=1
   Returns {"history": [{"t": unix_sec, "p": prob}, ...]} at ~1-minute fidelity.
   The endpoint silently caps the number of points per call, so we fetch in
   chunks of `chunk_hours` and concatenate. This is the series used for
   lead-lag tests. It is a *mid/last* probability, not a trade print.

2. Gamma metadata (REST, no auth):
   https://gamma-api.polymarket.com/markets?...
   Gives conditionId, clobTokenIds, start/end dates, volume.

Trade-level data (for aggressor flags / volume-weighted jumps) comes from
the Polymarket-v1 on-chain database (arXiv 2606.04217) and is loaded by
`load_trades_parquet`; this module does not download it.

Timestamps: Polymarket's price-history `t` is unix seconds UTC. We floor to
the minute and forward-fill onto a regular minute grid; the `n_obs` column
records how many raw points fell in each minute so sparse intervals can be
down-weighted or excluded.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:  # requests is only needed on the machine that pulls data
    import requests
except ImportError:  # pragma: no cover
    requests = None

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------
def fetch_market_by_slug(slug: str, session=None) -> dict:
    s = session or requests.Session()
    r = s.get(f"{GAMMA}/markets", params={"slug": slug, "limit": 1}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise KeyError(f"no market with slug {slug!r}")
    return data[0]


def fetch_market_by_condition(condition_id: str, session=None) -> dict:
    s = session or requests.Session()
    r = s.get(f"{GAMMA}/markets", params={"condition_ids": condition_id, "limit": 1},
              timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise KeyError(f"no market with conditionId {condition_id!r}")
    return data[0]


def token_ids(market: dict) -> tuple[str, str]:
    """(yes_token_id, no_token_id) from a Gamma market record."""
    ids = market["clobTokenIds"]
    if isinstance(ids, str):
        ids = json.loads(ids)
    return str(ids[0]), str(ids[1])


# --------------------------------------------------------------------------
# Price history
# --------------------------------------------------------------------------
def _fetch_chunk(token_id: str, start_ts: int, end_ts: int, fidelity: int,
                 session, retries: int = 4) -> list[dict]:
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(
                f"{CLOB}/prices-history",
                params={"market": token_id, "startTs": start_ts, "endTs": end_ts,
                        "fidelity": fidelity},
                timeout=120,
            )
            r.raise_for_status()
            return r.json().get("history", [])
        except Exception as e:  # noqa: BLE001 - network flakiness; retry with backoff
            last_err = e
            time.sleep(2 ** attempt * 2)
    raise last_err


def fetch_price_history(token_id: str, start: pd.Timestamp, end: pd.Timestamp,
                        fidelity: int = 1, chunk_hours: int = 24,
                        pause: float = 0.25, session=None) -> pd.DataFrame:
    """Minute-fidelity price history for one outcome token.

    Returns a DataFrame indexed by UTC timestamp (raw, not gridded) with
    column `p`. Duplicate timestamps keep the last value.
    """
    if requests is None:
        raise RuntimeError("requests not installed")
    s = session or requests.Session()
    start = pd.Timestamp(start).tz_convert("UTC") if pd.Timestamp(start).tzinfo else pd.Timestamp(start, tz="UTC")
    end = pd.Timestamp(end).tz_convert("UTC") if pd.Timestamp(end).tzinfo else pd.Timestamp(end, tz="UTC")
    rows: list[dict] = []
    t0 = start
    step = pd.Timedelta(hours=chunk_hours)
    while t0 < end:
        t1 = min(t0 + step, end)
        pts = _fetch_chunk(token_id, int(t0.timestamp()), int(t1.timestamp()), fidelity, s)
        rows.extend(pts)
        t0 = t1
        time.sleep(pause)
    if not rows:
        return pd.DataFrame(columns=["p"], index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df = df.drop(columns="t").drop_duplicates("ts", keep="last").set_index("ts").sort_index()
    return df[["p"]]


def to_minute_grid(raw: pd.DataFrame, start: pd.Timestamp | None = None,
                   end: pd.Timestamp | None = None,
                   max_ffill_minutes: int | None = None) -> pd.DataFrame:
    """Place raw {ts: p} points on a regular 1-minute UTC grid.

    Columns: p (forward-filled), n_obs (raw points in that minute), stale
    (minutes since last raw observation). Polymarket quotes only change on
    trades/quote updates, so forward-fill is the correct interpretation of
    "price at minute t"; `stale` lets downstream code drop long gaps.
    """
    if raw.empty:
        raise ValueError("empty price history")
    r = raw.copy()
    r.index = r.index.floor("min")
    n_obs = r.groupby(level=0).size().rename("n_obs")
    last = r.groupby(level=0)["p"].last()
    start = (start or last.index[0]).floor("min")
    end = (end or last.index[-1]).floor("min")
    grid = pd.date_range(start, end, freq="min", tz="UTC", name="ts")
    out = pd.DataFrame(index=grid)
    out["p"] = last.reindex(grid)
    out["n_obs"] = n_obs.reindex(grid).fillna(0).astype(int)
    # staleness: minutes since last observed point
    obs_pos = np.where(out["n_obs"].to_numpy() > 0, np.arange(len(out)), np.nan)
    obs_pos = pd.Series(obs_pos, index=grid).ffill()
    out["stale"] = (np.arange(len(out)) - obs_pos).fillna(np.inf)
    out["p"] = out["p"].ffill()
    if max_ffill_minutes is not None:
        out.loc[out["stale"] > max_ffill_minutes, "p"] = np.nan
    return out


def logit(p: pd.Series, eps: float = 1e-3) -> pd.Series:
    """Log-odds transform; clips to avoid infinities at 0/1."""
    q = p.clip(eps, 1 - eps)
    return np.log(q / (1 - q))


# --------------------------------------------------------------------------
# Trade-level data (on-chain database)
# --------------------------------------------------------------------------
def load_trades_parquet(path: str | Path, condition_id: str | None = None) -> pd.DataFrame:
    """Load trades from the Polymarket-v1 database parquet export.

    Expected columns (names may differ by release; adapt here): ts, condition_id,
    token_id, price, size, side, aggressor. Returns UTC-indexed DataFrame.
    """
    df = pd.read_parquet(path)
    if condition_id is not None and "condition_id" in df.columns:
        df = df[df["condition_id"] == condition_id]
    tcol = next(c for c in ("ts", "timestamp", "block_time") if c in df.columns)
    df["ts"] = pd.to_datetime(df[tcol], utc=True)
    return df.set_index("ts").sort_index()


def trades_to_minute(trades: pd.DataFrame) -> pd.DataFrame:
    """VWAP price, volume and net aggressor flow per minute from trades."""
    g = trades.groupby(trades.index.floor("min"))
    out = pd.DataFrame({
        "vwap": g.apply(lambda x: np.average(x["price"], weights=x["size"]) if x["size"].sum() > 0 else np.nan),
        "volume": g["size"].sum(),
        "n_trades": g.size(),
    })
    if "aggressor" in trades.columns:
        sign = np.where(trades["aggressor"].astype(str).str.lower().str.startswith("b"), 1, -1)
        out["net_flow"] = (pd.Series(sign * trades["size"].to_numpy(), index=trades.index)
                           .groupby(trades.index.floor("min")).sum())
    out.index.name = "ts"
    return out
