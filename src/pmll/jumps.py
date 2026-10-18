"""Jump detection on Polymarket probability series.

Two detectors, used together:

1. Lee-Mykland (2008) style test on log-odds changes. At minute t the
   statistic is |d_logit_t| / sigma_hat_t where sigma_hat_t is a local
   bipower-variation estimate from the previous K minutes. A jump is flagged
   when the statistic exceeds a Gumbel-based critical value. This is the
   standard detector in the microstructure literature and is what a
   referee will expect.

2. Threshold on absolute probability change over a short window
   (|p_t - p_{t-w}| >= delta). Simple, robust to the thin-book noise that
   inflates Lee-Mykland on illiquid markets, and easier to explain.

`detect` returns the union with both flags so robustness tables can show
each separately. Jumps within `merge_minutes` of each other are merged into
one event (first minute kept) to avoid double-counting a multi-minute
repricing.

Both detectors run on the *raw* PM series (24/7), not on overlap minutes,
because the whole point of the weekend design is jumps that happen while
conventional markets are closed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class JumpConfig:
    window: int = 240          # minutes for local volatility (Lee-Mykland K)
    alpha: float = 0.01        # significance for LM critical value
    delta: float = 0.10        # probability-change threshold
    delta_window: int = 5      # minutes over which delta is measured
    min_n_obs: int = 1         # require at least this many raw obs in the jump minute
    merge_minutes: int = 30    # merge jumps closer than this
    min_sigma: float = 0.02    # floor on local sigma (log-odds/min); dead markets have ~0 BV
    min_abs_dp: float = 0.02   # LM flag also requires this much absolute prob change
    p_interior: float = 0.02   # ignore minutes where p is within this of 0 or 1 (resolved markets)


def bipower_sigma(d: pd.Series, window: int) -> pd.Series:
    """Rolling bipower variation -> local sigma (per minute).

    BV_t = (pi/2) * (1/(K-2)) * sum |d_{i}| |d_{i-1}| over the window.
    """
    a = d.abs()
    bv = (a * a.shift(1)).rolling(window, min_periods=max(10, window // 4)).mean() * (np.pi / 2)
    return np.sqrt(bv)


def lee_mykland_critical(window: int, alpha: float) -> float:
    """Critical value for max of |L| over n=window stats (Lee & Mykland 2008)."""
    n = window
    c = np.sqrt(2 / np.pi)
    Cn = np.sqrt(2 * np.log(n)) / c - (np.log(np.pi) + np.log(np.log(n))) / (2 * c * np.sqrt(2 * np.log(n)))
    Sn = 1 / (c * np.sqrt(2 * np.log(n)))
    beta_star = -np.log(-np.log(1 - alpha))
    return Cn + beta_star * Sn


def detect(pm_grid: pd.DataFrame, cfg: JumpConfig | None = None) -> pd.DataFrame:
    """Flag jump minutes on a PM minute grid (needs columns p, n_obs).

    Returns DataFrame indexed by jump minute with columns:
      p_before, p_after, dp, d_logit, lm_stat, lm_flag, thr_flag, direction
    """
    cfg = cfg or JumpConfig()
    p = pm_grid["p"].astype(float)
    eps = 1e-3
    q = p.clip(eps, 1 - eps)
    lo = np.log(q / (1 - q))
    d = lo.diff()
    # only count minutes with fresh observations as candidate jump minutes
    fresh = pm_grid["n_obs"] >= cfg.min_n_obs

    sigma = bipower_sigma(d, cfg.window).shift(1).clip(lower=cfg.min_sigma)  # past-only, floored
    lm = (d.abs() / sigma).replace([np.inf, -np.inf], np.nan)
    crit = lee_mykland_critical(cfg.window, cfg.alpha)
    interior = (p.shift(1) > cfg.p_interior) & (p.shift(1) < 1 - cfg.p_interior)
    dp1 = (p - p.shift(1)).abs()
    lm_flag = (lm > crit) & fresh & interior & (dp1 >= cfg.min_abs_dp)

    dp = p - p.shift(cfg.delta_window)
    thr_flag = (dp.abs() >= cfg.delta) & fresh & interior

    cand = pm_grid.index[(lm_flag | thr_flag).to_numpy()]
    rows = []
    last_kept = None
    for t in cand:
        if last_kept is not None and (t - last_kept) < pd.Timedelta(minutes=cfg.merge_minutes):
            continue
        last_kept = t
        i = pm_grid.index.get_loc(t)
        p_before = p.iloc[max(0, i - cfg.delta_window)]
        p_after = p.iloc[min(len(p) - 1, i + cfg.delta_window)]
        rows.append({
            "ts": t,
            "p_before": p_before,
            "p_after": p_after,
            "dp": p_after - p_before,
            "d_logit": d.loc[t],
            "lm_stat": lm.loc[t],
            "lm_flag": bool(lm_flag.loc[t]),
            "thr_flag": bool(thr_flag.loc[t]),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["direction"] = np.sign(out["dp"]).astype(int)
    return out.set_index("ts")


def flag_artifacts(all_jumps: pd.DataFrame, min_markets: int = 3,
                   half_tol: float = 1e-9) -> pd.Series:
    """Flag jump rows that are data artifacts rather than repricing.

    all_jumps: concatenated jumps across markets with columns conditionId, ts,
    p_after. Two rules, observed in the Oct-2026 pull:
      1. >= `min_markets` distinct markets jump in the same minute. Real news
         rarely moves 3+ unrelated contracts in one minute; a feed outage or
         book reset does. (2025-12-27 01:01 UTC: 13 markets at once.)
      2. p_after is exactly 0.50: Polymarket's empty-book default.
    Returns boolean Series aligned to all_jumps.index (True = artifact).
    """
    m = all_jumps["ts"].dt.floor("min")
    n_mk = all_jumps.groupby(m)["conditionId"].transform("nunique")
    simul = n_mk >= min_markets
    half = (all_jumps["p_after"] - 0.5).abs() < half_tol
    return (simul | half).rename("artifact")


def jump_summary(jumps: pd.DataFrame, venue_open_mask: pd.Series | None = None) -> dict:
    s = {
        "n_jumps": int(len(jumps)),
        "n_lm": int(jumps["lm_flag"].sum()) if len(jumps) else 0,
        "n_thr": int(jumps["thr_flag"].sum()) if len(jumps) else 0,
        "mean_abs_dp": float(jumps["dp"].abs().mean()) if len(jumps) else np.nan,
    }
    if venue_open_mask is not None and len(jumps):
        m = venue_open_mask.reindex(jumps.index).fillna(False).astype(bool)
        s["n_during_open"] = int(m.sum())
        s["n_during_closed"] = int((~m).sum())
    return s
