"""Synthetic data with a known lead-lag, for validating the pipeline.

Generates a PM probability series and an asset price series on a UTC
minute grid where:

  * A latent "information" process arrives as Poisson jumps (plus small
    diffusion noise) 24/7.
  * The PM reacts to information with lag `pm_lag` minutes (and noise).
  * The asset reacts with lag `asset_lag` minutes, but ONLY while its venue
    is open; information arriving during closure is impounded at reopen.
  * beta controls the asset's sensitivity to information in log-return units
    per unit of log-odds information.

So with pm_lag=0 and asset_lag=3, the truth is "PM leads asset by 3 minutes"
and the weekend design should recover a positive gap beta.
With asset_lag=0 and pm_lag=3, the truth is "asset leads PM", and the
pipeline must NOT report PM leadership.

Everything is returned in the same shapes the real loaders produce, so
tests exercise the real code paths.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import calendar as cal


@dataclass
class SynthConfig:
    start: str = "2025-03-01"
    days: int = 60
    jump_rate_per_day: float = 0.5     # information jumps per day
    jump_scale: float = 0.6            # std of jump size in log-odds
    diffusion: float = 0.01            # per-minute log-odds diffusion std
    pm_lag: int = 0
    asset_lag: int = 3
    beta: float = 0.004                # asset log-return per unit log-odds info
    asset_vol: float = 0.0004          # per-minute idiosyncratic asset vol (~0.6%/day)
    pm_noise: float = 0.02             # extra PM quote noise (log-odds)
    pm_update_prob: float = 0.3        # prob PM quote updates in a minute (sparsity)
    mean_revert: float = 0.0005        # per-minute OU pull of latent log-odds toward lo0 (keeps p interior)
    venue: str = "cme"
    p0: float = 0.3
    seed: int = 0


def generate(cfg: SynthConfig | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (pm_grid, asset_grid, truth) in loader schemas.

    truth: DataFrame of information arrival minutes and sizes.
    """
    cfg = cfg or SynthConfig()
    rng = np.random.default_rng(cfg.seed)
    idx = pd.date_range(cfg.start, periods=cfg.days * 24 * 60, freq="min", tz="UTC", name="ts")
    n = len(idx)

    # latent information in log-odds units
    info = rng.normal(0, cfg.diffusion, n)
    n_jumps = rng.poisson(cfg.jump_rate_per_day * cfg.days)
    jump_pos = rng.choice(np.arange(60, n - 60), size=n_jumps, replace=False)
    jump_size = rng.normal(0, cfg.jump_scale, n_jumps)
    info[jump_pos] += jump_size
    truth = pd.DataFrame({"ts": idx[jump_pos], "size": jump_size}).set_index("ts").sort_index()

    # Latent cumulative information as an OU process in log-odds (so p stays
    # interior over long samples). `info` are the innovations; `latent` the level.
    lo0 = np.log(cfg.p0 / (1 - cfg.p0))
    latent = np.zeros(n)
    lvl = 0.0
    for i in range(n):
        lvl += info[i] - cfg.mean_revert * lvl
        latent[i] = lvl
    # the innovation the asset should respond to includes the OU pull
    info = np.diff(np.concatenate([[0.0], latent]))

    # PM: latent with lag, plus noise, sparse updates
    pm_info = np.roll(latent, cfg.pm_lag)
    pm_info[:cfg.pm_lag] = 0
    pm_logit = lo0 + pm_info + rng.normal(0, cfg.pm_noise, n)
    updates = rng.random(n) < cfg.pm_update_prob
    updates[0] = True
    pm_p_sparse = pd.Series(np.where(updates, 1 / (1 + np.exp(-pm_logit)), np.nan), index=idx)
    pm_grid = pd.DataFrame(index=idx)
    pm_grid["p"] = pm_p_sparse.ffill()
    pm_grid["n_obs"] = updates.astype(int)
    obs_pos = np.where(updates, np.arange(n), np.nan)
    obs_pos = pd.Series(obs_pos, index=idx).ffill()
    pm_grid["stale"] = (np.arange(n) - obs_pos).fillna(0)

    # Asset: impounds info with lag, only when open
    open_m = cal.open_mask(idx, cfg.venue)
    asset_info_flow = np.roll(info, cfg.asset_lag)
    asset_info_flow[:cfg.asset_lag] = 0
    logp = np.zeros(n)
    acc = 0.0  # info accumulated while closed
    level = np.log(100.0)
    for i in range(n):
        acc += cfg.beta * asset_info_flow[i]
        if open_m[i]:
            level += acc + rng.normal(0, cfg.asset_vol)
            acc = 0.0
        logp[i] = level
    close = np.exp(logp)
    asset_grid = pd.DataFrame(index=idx)
    asset_grid["close"] = np.where(open_m, close, np.nan)
    asset_grid["open"] = asset_grid["close"]
    asset_grid["high"] = asset_grid["close"]
    asset_grid["low"] = asset_grid["close"]
    asset_grid["volume"] = np.where(open_m, 1.0, np.nan)
    asset_grid["open_mkt"] = open_m
    asset_grid["close"] = asset_grid["close"].ffill()
    return pm_grid, asset_grid, truth
