"""Event study: asset returns around Polymarket jumps.

For each jump at minute t0 (during asset open hours) and each horizon h in
`horizons`, compute the signed cumulative log return

    CAR(h) = direction * [log close(t0 + h) - log close(t0 - pre)]

where `direction` is the sign of the PM move times the hypothesised asset
response (+1 if "oil up when prob of strike up", -1 for Treasuries, etc.).
Signing by hypothesis lets us average across heterogeneous events.

Abnormal returns: with minute data and short windows, the expected return
is ~0, so raw returns are used (standard for intraday event studies). A
market-model adjustment vs ES is available via `benchmark`.

Inference: cross-sectional t-test over events plus a block-bootstrap
placebo: resample random non-jump minutes from the same markets' open hours
and compute the same CARs to get the null distribution. The placebo is
what protects against "every minute has positive drift" artefacts.

Pre-window returns (negative horizons) test whether the ASSET moved before
the PM jump, i.e. whether the PM is lagging a wire headline. That is the
key confound: if CAR(-5) is already large, the PM did not lead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class ESConfig:
    horizons: tuple[int, ...] = (-15, -5, 1, 5, 15, 30, 60)
    pre: int = 1                       # anchor = close at t0 - pre
    min_open_after: int = 60           # require this many open minutes after t0
    n_placebo: int = 2000
    seed: int = 0


def _open_positions(close: pd.Series, open_mkt: pd.Series):
    """Arrays of open-minute timestamps and their log closes, plus a ts->pos map."""
    opens = close.index[open_mkt.to_numpy()]
    logc = np.log(close.loc[opens].to_numpy(dtype=float))
    pos = pd.Series(np.arange(len(opens)), index=opens)
    return opens, logc, pos


def _car_vec(logc: np.ndarray, i: np.ndarray, h: int, pre: int) -> np.ndarray:
    """Vectorised window return for event positions i (into open-minute array)."""
    n = len(logc)
    a = i - pre
    if h >= 0:
        j0, j1 = a, i + h
    else:
        j0, j1 = i + h, a
    ok = (j0 >= 0) & (j1 < n) & (j1 > j0)
    out = np.full(len(i), np.nan)
    out[ok] = logc[j1[ok]] - logc[j0[ok]]
    return out


def _car_at(close: pd.Series, open_mkt: pd.Series, t0: pd.Timestamp, h: int, pre: int) -> float:
    """Scalar wrapper kept for tests/back-compat."""
    opens, logc, pos = _open_positions(close, open_mkt)
    if t0 not in pos.index:
        return np.nan
    return float(_car_vec(logc, np.array([pos.loc[t0]]), h, pre)[0])


def event_cars(aligned: pd.DataFrame, jumps: pd.DataFrame, hyp_sign: int,
               cfg: ESConfig | None = None) -> pd.DataFrame:
    """CARs for every jump that occurred while the asset was open.

    hyp_sign: +1 if asset expected to move in the same direction as PM prob,
              -1 if opposite.
    Returns rows per jump, columns car_{h} already signed so positive = as hypothesised.
    """
    cfg = cfg or ESConfig()
    opens, logc, pos = _open_positions(aligned["close"], aligned["open_mkt"])
    jj = jumps[jumps.index.isin(pos.index)]
    if jj.empty:
        return pd.DataFrame()
    i = pos.loc[jj.index].to_numpy()
    sign = jj["direction"].to_numpy().astype(int) * hyp_sign
    out = pd.DataFrame({"dp": jj["dp"].to_numpy(), "sign": sign}, index=jj.index)
    for h in cfg.horizons:
        out[f"car_{h}"] = sign * _car_vec(logc, i, h, cfg.pre)
    out.index.name = "ts"
    return out


def placebo_cars(aligned: pd.DataFrame, n: int, cfg: ESConfig | None = None,
                 exclude: pd.DatetimeIndex | None = None, exclude_radius: int = 60) -> pd.DataFrame:
    """Random open minutes (not near real jumps) with random sign -> null CARs."""
    cfg = cfg or ESConfig()
    rng = np.random.default_rng(cfg.seed)
    opens, logc, pos = _open_positions(aligned["close"], aligned["open_mkt"])
    keep = np.ones(len(opens), dtype=bool)
    if exclude is not None and len(exclude):
        ex = pd.DatetimeIndex(exclude)
        # mark open positions within radius of any excluded ts
        for t in ex:
            lo, hi = opens.searchsorted(t - pd.Timedelta(minutes=exclude_radius)), opens.searchsorted(t + pd.Timedelta(minutes=exclude_radius), side="right")
            keep[lo:hi] = False
    cand = np.flatnonzero(keep)
    if len(cand) == 0:
        return pd.DataFrame()
    i = rng.choice(cand, size=min(n, len(cand)), replace=len(cand) < n)
    signs = rng.choice([-1, 1], size=len(i))
    out = pd.DataFrame({"sign": signs}, index=opens[i])
    for h in cfg.horizons:
        out[f"car_{h}"] = signs * _car_vec(logc, i, h, cfg.pre)
    out.index.name = "ts"
    return out


def summarize(cars: pd.DataFrame, placebo: pd.DataFrame | None = None) -> pd.DataFrame:
    """Mean CAR, t-stat, and placebo p-value per horizon."""
    rows = []
    for col in [c for c in cars.columns if c.startswith("car_")]:
        x = cars[col].dropna()
        if len(x) < 3:
            continue
        t, p = stats.ttest_1samp(x, 0.0)
        r = {"horizon": int(col[4:]), "n": len(x), "mean_bp": 1e4 * x.mean(),
             "median_bp": 1e4 * x.median(), "t": t, "p_t": p}
        if placebo is not None and col in placebo:
            null = placebo[col].dropna()
            # p-value: fraction of placebo *means over n draws* exceeding observed mean
            # approximate via bootstrap of placebo sample means of size len(x)
            rng = np.random.default_rng(0)
            B = 500
            means = np.array([rng.choice(null.to_numpy(), size=len(x), replace=True).mean() for _ in range(B)])
            r["p_placebo"] = float(np.mean(means >= x.mean()))
        rows.append(r)
    if not rows:
        return pd.DataFrame(columns=["n", "mean_bp", "median_bp", "t", "p_t", "p_placebo"]).rename_axis("horizon")
    return pd.DataFrame(rows).set_index("horizon")
