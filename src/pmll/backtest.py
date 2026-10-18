"""Tradability check.

Rule: when a Polymarket jump of size >= `min_dp` is detected at minute t0
while the asset is open, enter at the close of t0 + `entry_delay` in the
hypothesised direction, exit at t0 + `entry_delay` + `hold` minutes.
For jumps during closure, enter at the first reopen minute's close.

Costs: half-spread per side in basis points (`cost_bp`), applied twice.
Default 1 bp per side for CL/ES front month, 2 bp for ETFs, which is
conservative for minute-level trading.

Output: per-trade net log return, Sharpe-like t-stat of mean, hit rate,
and the cost level at which mean net return hits zero (breakeven cost).

This is NOT a strategy claim. It is the paper's way of saying "the lead,
if present, is / is not large enough to survive transaction costs", which
is the economic-significance check a referee will demand.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import calendar as cal


def trades_from_jumps(aligned: pd.DataFrame, jumps: pd.DataFrame, hyp_sign: int,
                      venue: str, min_dp: float = 0.05, entry_delay: int = 1,
                      hold: int = 30, cost_bp: float = 1.0) -> pd.DataFrame:
    close, open_mkt = aligned["close"], aligned["open_mkt"]
    opens = aligned.index[open_mkt.to_numpy()]
    rows = []
    for t0, j in jumps.iterrows():
        if abs(j["dp"]) < min_dp:
            continue
        direction = int(j["direction"]) * hyp_sign
        # entry minute: next open minute at/after t0 + delay
        t_entry = cal.next_open(t0 + pd.Timedelta(minutes=entry_delay), venue)
        if t_entry not in opens:
            # empirical session may differ (holiday); find next actual bar
            pos = opens.searchsorted(t_entry)
            if pos >= len(opens):
                continue
            t_entry = opens[pos]
        i = opens.get_loc(t_entry)
        if i + hold >= len(opens):
            continue
        t_exit = opens[i + hold]
        gross = direction * float(np.log(close.loc[t_exit] / close.loc[t_entry]))
        net = gross - 2 * cost_bp * 1e-4
        rows.append({"jump_ts": t0, "entry": t_entry, "exit": t_exit, "direction": direction,
                     "dp": j["dp"], "closed_at_jump": not bool(open_mkt.loc[t0]) if t0 in open_mkt.index else True,
                     "gross": gross, "net": net})
    return pd.DataFrame(rows)


def summarize_trades(tr: pd.DataFrame) -> dict:
    if tr.empty:
        return {"n": 0}
    net = tr["net"]
    t, p = stats.ttest_1samp(net, 0.0) if len(net) > 2 else (np.nan, np.nan)
    gross = tr["gross"]
    breakeven_bp = 1e4 * gross.mean() / 2 if gross.mean() > 0 else 0.0
    return {
        "n": int(len(tr)),
        "mean_net_bp": float(1e4 * net.mean()),
        "median_net_bp": float(1e4 * net.median()),
        "hit_rate": float((net > 0).mean()),
        "t": float(t), "p": float(p),
        "mean_gross_bp": float(1e4 * gross.mean()),
        "breakeven_cost_bp_per_side": float(breakeven_bp),
        "n_closed_at_jump": int(tr["closed_at_jump"].sum()),
    }
