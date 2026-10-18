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


def _car_at(close: pd.Series, open_mkt: pd.Series, t0: pd.Timestamp, h: int, pre: int) -> float:
    """Signed window return around the jump, counting only open minutes.

    h >= 0: return from anchor (t0 - pre) forward to t0 + h   [post-window]
    h <  0: return from t0 + h forward to anchor (t0 - pre)   [pre-window]
    Both are forward-in-time returns, so a positive value always means the
    asset rose over that window.
    """
    opens = close.index[open_mkt.to_numpy()]
    if t0 not in opens:
        return np.nan
    i = opens.get_loc(t0)
    a = i - pre
    if h >= 0:
        j0, j1 = a, i + h
    else:
        j0, j1 = i + h, a
    if j0 < 0 or j1 >= len(opens) or j1 <= j0:
        return np.nan
    return float(np.log(close.loc[opens[j1]]) - np.log(close.loc[opens[j0]]))


def event_cars(aligned: pd.DataFrame, jumps: pd.DataFrame, hyp_sign: int,
               cfg: ESConfig | None = None) -> pd.DataFrame:
    """CARs for every jump that occurred while the asset was open.

    hyp_sign: +1 if asset expected to move in the same direction as PM prob,
              -1 if opposite.
    Returns rows per jump, columns car_{h} already signed so positive = as hypothesised.
    """
    cfg = cfg or ESConfig()
    close, open_mkt = aligned["close"], aligned["open_mkt"]
    rows = []
    for t0, j in jumps.iterrows():
        if t0 not in aligned.index or not bool(open_mkt.loc[t0]):
            continue
        sign = int(j["direction"]) * hyp_sign
        row = {"ts": t0, "dp": j["dp"], "sign": sign}
        for h in cfg.horizons:
            row[f"car_{h}"] = sign * _car_at(close, open_mkt, t0, h, cfg.pre)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ts") if rows else pd.DataFrame()


def placebo_cars(aligned: pd.DataFrame, n: int, cfg: ESConfig | None = None,
                 exclude: pd.DatetimeIndex | None = None, exclude_radius: int = 60) -> pd.DataFrame:
    """Random open minutes (not near real jumps) with random sign -> null CARs."""
    cfg = cfg or ESConfig()
    rng = np.random.default_rng(cfg.seed)
    opens = aligned.index[aligned["open_mkt"].to_numpy()]
    if exclude is not None and len(exclude):
        bad = np.zeros(len(opens), dtype=bool)
        for t in exclude:
            bad |= (np.abs((opens - t).total_seconds()) <= exclude_radius * 60)
        opens = opens[~bad]
    if len(opens) == 0:
        return pd.DataFrame()
    picks = rng.choice(opens, size=min(n, len(opens)), replace=len(opens) < n)
    signs = rng.choice([-1, 1], size=len(picks))
    close, open_mkt = aligned["close"], aligned["open_mkt"]
    rows = []
    for t0, s in zip(picks, signs):
        row = {"ts": t0, "sign": s}
        for h in cfg.horizons:
            row[f"car_{h}"] = s * _car_at(close, open_mkt, pd.Timestamp(t0), h, cfg.pre)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ts")


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
            B = 2000
            means = np.array([rng.choice(null.to_numpy(), size=len(x), replace=True).mean() for _ in range(B)])
            r["p_placebo"] = float(np.mean(means >= x.mean()))
        rows.append(r)
    return pd.DataFrame(rows).set_index("horizon")
