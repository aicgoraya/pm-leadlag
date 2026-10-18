#!/usr/bin/env python3
"""Paper figures from results/. Writes paper/fig*.pdf and .png.

Fig 1  Binned scatter: USO 30-min reopen return vs PM closure log-odds move
       (Iran + Hormuz contracts, dedup, clean), with OLS line and 95% CI.
Fig 2  CAR path -15..+60 min around open-hours PM jumps, USO and XLE,
       treated vs control, with placebo band. The pre-window is the point.
Fig 3  Histogram of cross-correlation peak lag, treated USO pairs.

Palette: two series max per panel, slot 1 blue / slot 2 orange from the
reference palette; placebo/controls in neutral gray; thin marks; direct labels.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

BLUE, ORANGE, GRAY, INK, MUTED = "#2a78d6", "#eb6834", "#9a9893", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.grid": True, "grid.color": "#e6e5e1",
                     "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.dpi": 150})


def fig1(res: Path, out: Path):
    wk = pd.read_csv(res / "quick" / "weekend_clean_dedup.csv")
    d = wk[(wk.category.isin(["iran", "oil"])) & (wk.asset == "USO")].dropna(subset=["x_logit", "y_30"])
    x, y = d["x_logit"].clip(d["x_logit"].quantile(.01), d["x_logit"].quantile(.99)), d["y_30"] * 1e4
    X = sm.add_constant(x); res_ = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["reopen"])[0]})
    # binned means (20 equal-count bins)
    bins = pd.qcut(x, 20, duplicates="drop")
    g = pd.DataFrame({"x": x, "y": y}).groupby(bins, observed=True).agg(x=("x", "mean"), y=("y", "mean"), n=("y", "size"), se=("y", lambda v: v.std() / np.sqrt(len(v))))
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    ax.scatter(x, y, s=6, color=GRAY, alpha=.35, linewidths=0, label="closure")
    ax.errorbar(g["x"], g["y"], yerr=1.96 * g["se"], fmt="o", ms=5, color=BLUE, ecolor=BLUE, elinewidth=1, capsize=0, label="bin mean (20 bins)")
    xs = np.linspace(x.min(), x.max(), 50); pred = res_.get_prediction(sm.add_constant(xs)).summary_frame(alpha=.05)
    ax.plot(xs, pred["mean"], color=BLUE, lw=2)
    ax.fill_between(xs, pred["mean_ci_lower"], pred["mean_ci_upper"], color=BLUE, alpha=.12, lw=0)
    ax.axhline(0, color=MUTED, lw=.6); ax.axvline(0, color=MUTED, lw=.6)
    ax.set_xlabel("Polymarket log-odds change during ETF closure (signed by hypothesis)")
    ax.set_ylabel("USO return, close to 30 min after reopen (bp)")
    ax.set_title("Oil ETF reopen move vs. prediction-market move while closed\nIran and Strait-of-Hormuz contracts", loc="left", fontsize=10, color=INK)
    b, t, n, nc = res_.params.iloc[1], res_.tvalues.iloc[1], len(d), d["reopen"].nunique()
    ax.text(.02, .97, f"slope = {b*1e-4:.4f} log-ret per log-odds\nt = {t:.1f} (clustered by closure)\nn = {n} rows, {nc} closures", transform=ax.transAxes, va="top", fontsize=8, color=MUTED)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(out / "fig1_closure_scatter.pdf"); fig.savefig(out / "fig1_closure_scatter.png"); plt.close(fig)


def fig2(res: Path, out: Path):
    """Pre-window values are returns OVER the window ending at the jump
    (e.g. -15 = return from t-15 to t-1); post-window values are cumulative
    from t-1. Drawn as separate bars (pre) and a path (post) so the pre
    values are not read as a time path."""
    es = pd.read_csv(res / "full" / "eventstudy.csv")
    PRE, POST = [-15, -5], [1, 5, 15, 30, 60]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4), sharey=True)
    for ax, sym in zip(axes, ["USO", "XLE"]):
        for lab, m, col, off in [("Iran + oil contracts", es.category.isin(["iran", "oil"]), BLUE, -0.9),
                                 ("control contracts", es.category == "control", GRAY, 0.9)]:
            g = es[m & (es.asset == sym)]
            prof = g.groupby("horizon").apply(lambda d: np.average(d["mean_bp"], weights=d["n"]))
            se = g.groupby("horizon")["mean_bp"].sem()
            # pre-window bars at x = -15, -5 (offset so two series sit side by side)
            ax.bar([h + off for h in PRE], prof.reindex(PRE).values, width=1.8, color=col, alpha=.9, linewidth=0)
            ax.errorbar([h + off for h in PRE], prof.reindex(PRE).values, yerr=1.96 * se.reindex(PRE).values, fmt="none", ecolor=col, elinewidth=1)
            # post-window path
            ax.plot(POST, prof.reindex(POST).values, color=col, lw=2, marker="o", ms=4, label=lab)
            ax.fill_between(POST, (prof - 1.96 * se).reindex(POST).values, (prof + 1.96 * se).reindex(POST).values, color=col, alpha=.12, lw=0)
        ax.axvline(0, color=MUTED, lw=.8, ls="--"); ax.axhline(0, color=MUTED, lw=.6)
        ax.set_title(sym, loc="left", fontsize=10, color=INK)
        ax.set_xlabel("minutes relative to Polymarket jump")
        ax.set_xticks(PRE + POST); ax.set_xticklabels(["[-15,-1]", "[-5,-1]", "+1", "+5", "+15", "+30", "+60"], fontsize=8)
    axes[0].set_ylabel("signed return (bp)")
    axes[0].text(-15, axes[0].get_ylim()[1] * .95, "return over the\nwindow before the jump", fontsize=7.5, color=MUTED, va="top", ha="left")
    axes[0].text(22, axes[0].get_ylim()[1] * .95, "post-jump: cumulative from t-1", fontsize=7.5, color=MUTED, va="top", ha="left")
    axes[1].legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle("Around prediction-market jumps during ETF trading hours, oil has already moved", x=.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(); fig.savefig(out / "fig2_car_path.pdf"); fig.savefig(out / "fig2_car_path.png"); plt.close(fig)


def fig3(res: Path, out: Path):
    ll = pd.read_csv(res / "full" / "leadlag.csv")
    g = ll[(ll.category != "control") & (ll.asset == "USO")]["xcorr_peak_lag"]
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    bins = np.arange(-15.5, 16.5, 1)
    ax.hist(g, bins=bins, color=BLUE, edgecolor="white", linewidth=.8)
    ax.axvline(0, color=MUTED, lw=.8, ls="--")
    ax.set_xlabel("cross-correlation peak lag (minutes); negative = oil leads Polymarket")
    ax.set_ylabel("contracts")
    ax.set_title(f"Peak lag between 1-min oil returns and Polymarket log-odds changes\nmedian {g.median():+.0f} min, n = {len(g)} geopolitical contracts", loc="left", fontsize=10, color=INK)
    fig.tight_layout(); fig.savefig(out / "fig3_xcorr_lag.pdf"); fig.savefig(out / "fig3_xcorr_lag.png"); plt.close(fig)


if __name__ == "__main__":
    res = Path(sys.argv[1] if len(sys.argv) > 1 else "results"); out = Path(sys.argv[2] if len(sys.argv) > 2 else "paper"); out.mkdir(exist_ok=True)
    fig1(res, out); fig2(res, out); fig3(res, out); print("figures ->", out)
