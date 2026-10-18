"""Validation on synthetic data with known ground truth.

Run: pytest -q
"""
import numpy as np
import pandas as pd
import pytest

from pmll import calendar as cal
from pmll import align, backtest, eventstudy, jumps, leadlag, weekend
from pmll.synthetic import SynthConfig, generate


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------
def test_cme_calendar_weekend_and_break():
    # Saturday noon ET is closed; Sunday 18:30 ET is open; Wed 17:30 ET closed
    sat = pd.Timestamp("2025-03-08 17:00", tz="UTC")       # Sat 12:00 ET (EST)
    sun_open = pd.Timestamp("2025-03-09 22:30", tz="UTC")  # Sun 18:30 EDT (DST started 3/9)
    wed_break = pd.Timestamp("2025-03-12 21:30", tz="UTC") # Wed 17:30 EDT
    wed_open = pd.Timestamp("2025-03-12 20:30", tz="UTC")  # Wed 16:30 EDT
    assert not cal.cme_is_open(sat)
    assert cal.cme_is_open(sun_open)
    assert not cal.cme_is_open(wed_break)
    assert cal.cme_is_open(wed_open)


def test_closed_windows_finds_weekends():
    start = pd.Timestamp("2025-03-03", tz="UTC")
    end = pd.Timestamp("2025-03-24", tz="UTC")
    w = cal.closed_windows(start, end, "cme", min_minutes=24 * 60)
    assert len(w) == 3  # three weekends
    for a, b in w:
        assert (b - a) > pd.Timedelta(hours=40)


def test_open_mask_matches_scalar():
    idx = pd.date_range("2025-03-07", periods=3 * 24 * 60, freq="min", tz="UTC")
    m = cal.open_mask(idx, "cme")
    for i in range(0, len(idx), 97):
        assert m[i] == cal.cme_is_open(idx[i])


# --------------------------------------------------------------------------
# Jumps
# --------------------------------------------------------------------------
def test_jump_detector_recovers_planted_jumps():
    cfg = SynthConfig(days=40, jump_rate_per_day=0.5, jump_scale=1.0, seed=1)
    pm, asset, truth = generate(cfg)
    found = jumps.detect(pm, jumps.JumpConfig(delta=0.08))
    assert len(found) > 0
    # each true jump of size > 0.8 (log-odds) should have a detected jump within 10 min
    big = truth[truth["size"].abs() > 0.8]
    hits = 0
    for t in big.index:
        if (np.abs((found.index - t).total_seconds()) <= 10 * 60).any():
            hits += 1
    assert hits / max(1, len(big)) >= 0.7, f"recall {hits}/{len(big)}"


# --------------------------------------------------------------------------
# Lead-lag direction
# --------------------------------------------------------------------------
def _overlap_frame(cfg):
    pm, asset, truth = generate(cfg)
    df = align.align(pm, asset)
    return align.overlap(df, max_stale=10), truth, pm, asset


def test_granger_direction_pm_leads():
    cfg = SynthConfig(days=60, pm_lag=0, asset_lag=3, beta=0.01, jump_rate_per_day=2.0,
                      diffusion=0.03, asset_vol=0.0002, seed=2)
    ov, *_ = _overlap_frame(cfg)
    g = leadlag.granger_both(ov["d_logit"], ov["r_asset"], maxlag=5)
    assert g.loc["p", "pm_to_asset"] < 0.01
    assert g.loc["p", "asset_to_pm"] > g.loc["p", "pm_to_asset"]


def test_granger_direction_asset_leads():
    cfg = SynthConfig(days=60, pm_lag=3, asset_lag=0, beta=0.01, jump_rate_per_day=2.0,
                      diffusion=0.03, asset_vol=0.0002, pm_noise=0.005, seed=3)
    ov, *_ = _overlap_frame(cfg)
    g = leadlag.granger_both(ov["d_logit"], ov["r_asset"], maxlag=5)
    assert g.loc["p", "asset_to_pm"] < 0.01
    assert g.loc["p", "pm_to_asset"] > 0.01, "false PM-leads signal"


def test_xcorr_peak_lag():
    cfg = SynthConfig(days=60, pm_lag=0, asset_lag=4, beta=0.01, jump_rate_per_day=2.0,
                      diffusion=0.03, asset_vol=0.0002, pm_update_prob=0.9, seed=4)
    ov, *_ = _overlap_frame(cfg)
    xc = leadlag.cross_correlation(ov["d_logit"], ov["r_asset"], lags=10)
    assert xc.idxmax() == 4


def test_transfer_entropy_direction():
    cfg = SynthConfig(days=60, pm_lag=0, asset_lag=1, beta=0.02, jump_rate_per_day=3.0,
                      diffusion=0.04, asset_vol=0.0002, pm_update_prob=0.9, seed=5)
    ov, *_ = _overlap_frame(cfg)
    te = leadlag.transfer_entropy_both(ov["d_logit"], ov["r_asset"], lag=1, n_surrogates=100)
    assert te.loc["p", "pm_to_asset"] < 0.05
    assert te.loc["te", "pm_to_asset"] > te.loc["te", "asset_to_pm"]


# --------------------------------------------------------------------------
# Event study
# --------------------------------------------------------------------------
def test_event_study_car_positive_when_pm_leads():
    # pm_update_prob high so the detected jump minute ~= information minute.
    # With sparse quotes (0.3) detection lags information by ~2-3 min and the
    # pre-window picks up asset moves that are really post-information: a
    # bias AGAINST finding PM leadership on thin books. Documented in README.
    cfg = SynthConfig(days=90, pm_lag=0, asset_lag=3, beta=0.01, jump_scale=1.0,
                      jump_rate_per_day=2.0, pm_update_prob=0.9, seed=6)
    pm, asset, truth = generate(cfg)
    df = align.align(pm, asset)
    j = jumps.detect(pm, jumps.JumpConfig(delta=0.08))
    cars = eventstudy.event_cars(df, j, hyp_sign=+1)
    assert len(cars) >= 10
    placebo = eventstudy.placebo_cars(df, n=500, exclude=j.index)
    summ = eventstudy.summarize(cars, placebo)
    assert summ.loc[15, "mean_bp"] > 0
    assert summ.loc[15, "t"] > 2
    assert summ.loc[15, "p_placebo"] < 0.05
    # pre-window: asset did not move before the PM jump -> insignificant
    assert abs(summ.loc[-5, "t"]) < 2


def test_event_study_pre_window_flags_asset_leading():
    # asset leads PM by 3 min -> CAR(-5) should be significantly positive
    cfg = SynthConfig(days=90, pm_lag=3, asset_lag=0, beta=0.01, jump_scale=1.0,
                      jump_rate_per_day=2.0, pm_noise=0.005, seed=10)
    pm, asset, truth = generate(cfg)
    df = align.align(pm, asset)
    j = jumps.detect(pm, jumps.JumpConfig(delta=0.08))
    cars = eventstudy.event_cars(df, j, hyp_sign=+1)
    summ = eventstudy.summarize(cars)
    assert summ.loc[-5, "t"] > 2, "pre-window should catch asset-leads case"


# --------------------------------------------------------------------------
# Weekend design
# --------------------------------------------------------------------------
def test_weekend_gap_beta_recovers_sign():
    cfg = SynthConfig(days=120, pm_lag=0, asset_lag=0, beta=0.01, jump_scale=0.8,
                      jump_rate_per_day=1.0, diffusion=0.02, seed=7)
    pm, asset, truth = generate(cfg)
    tbl = weekend.closure_table(pm, asset, "cme", min_minutes=24 * 60, hyp_sign=+1)
    assert len(tbl) >= 10
    res = weekend.gap_regression(tbl, horizon=1, control_pre=False)
    # true beta in log-return per log-odds unit = cfg.beta
    assert res["p"] < 0.01
    assert abs(res["beta"] - cfg.beta) / cfg.beta < 0.5


def test_weekend_gap_null_when_asset_ignores_pm():
    cfg = SynthConfig(days=120, beta=0.0, jump_scale=0.8, jump_rate_per_day=1.0, seed=8)
    pm, asset, truth = generate(cfg)
    tbl = weekend.closure_table(pm, asset, "cme", min_minutes=24 * 60, hyp_sign=+1)
    res = weekend.gap_regression(tbl, horizon=1, control_pre=False)
    assert res["p"] > 0.05


# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------
def test_backtest_profitable_when_lead_is_large():
    cfg = SynthConfig(days=90, pm_lag=0, asset_lag=5, beta=0.02, jump_scale=1.0,
                      jump_rate_per_day=1.0, seed=9)
    pm, asset, truth = generate(cfg)
    df = align.align(pm, asset)
    j = jumps.detect(pm, jumps.JumpConfig(delta=0.08))
    tr = backtest.trades_from_jumps(df, j, hyp_sign=+1, venue="cme", min_dp=0.08,
                                    entry_delay=1, hold=30, cost_bp=1.0)
    s = backtest.summarize_trades(tr)
    assert s["n"] >= 10
    assert s["mean_net_bp"] > 0
    assert s["hit_rate"] > 0.6
