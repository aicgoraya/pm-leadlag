"""Lead-lag tests between PM log-odds changes and asset returns.

All functions take two aligned return-like series over OVERLAP minutes
(asset open, PM fresh) and return a dict of statistics.

granger(x, y, maxlag)
    Does x Granger-cause y? Wald/F test on y_t = a + sum b_i y_{t-i} + sum c_i x_{t-i}.
    Run both directions; the paper's claim is "PM -> asset" significant and
    "asset -> PM" not, or at least asymmetric. Uses HAC (Newey-West) errors.

cross_correlation(x, y, lags)
    corr(x_{t-k}, y_t) for k in -lags..lags. Positive k = x leads y.

transfer_entropy(x, y, lag, bins)
    TE_{x->y} = I(y_t ; x_{t-lag} | y_{t-lag}) on binned data, with a
    surrogate-shuffle p-value. Captures nonlinear dependence that Granger
    misses, which matters because PM moves are discrete and skewed.

hasbrouck_info_share(p1, p2)
    Hasbrouck (1995) information share from a VECM of two cointegrated
    *price levels*. Here the "prices" are the PM log-odds and the asset log
    price, which are NOT cointegrated in general (different units, different
    long-run). So we only apply it to event-window segments where both are
    responding to one shock, or report it as a robustness curiosity. The
    primary tests are Granger/TE/event-study. Implemented because referees
    will ask for it; see the caveat in the docstring.

Interpretation discipline (write this in the paper):
  Significance in "PM -> asset" at 1-5 minute lags during overlapping hours
  is consistent with (a) PM aggregating information first, OR (b) both
  responding to the same headline with PM updating a few seconds faster, OR
  (c) PM noise that happens to correlate. The event study's pre-window and
  the headline-timestamp conditioning in `headlines.py` address (b); the
  placebo addresses (c).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen


# --------------------------------------------------------------------------
# Granger causality with HAC errors
# --------------------------------------------------------------------------
def _lagmat(s: pd.Series, lags: int, prefix: str) -> pd.DataFrame:
    return pd.concat({f"{prefix}_l{i}": s.shift(i) for i in range(1, lags + 1)}, axis=1)


def granger(x: pd.Series, y: pd.Series, maxlag: int = 5, hac_lags: int | None = None) -> dict:
    """Test x -> y. Returns F-stat (Wald, HAC), p-value, sum of x-coefficients, n."""
    df = pd.concat({"y": y, "x": x}, axis=1).dropna()
    X = pd.concat([_lagmat(df["y"], maxlag, "y"), _lagmat(df["x"], maxlag, "x")], axis=1)
    data = pd.concat([df["y"], X], axis=1).dropna()
    if len(data) < 10 * maxlag + 10:
        return {"F": np.nan, "p": np.nan, "sum_coef": np.nan, "n": len(data)}
    Y = data["y"]
    Xm = sm.add_constant(data.drop(columns="y"))
    hac = hac_lags if hac_lags is not None else int(np.floor(4 * (len(data) / 100) ** (2 / 9)))
    res = sm.OLS(Y, Xm).fit(cov_type="HAC", cov_kwds={"maxlags": hac})
    xcols = [c for c in Xm.columns if c.startswith("x_l")]
    R = np.zeros((len(xcols), len(Xm.columns)))
    for i, c in enumerate(xcols):
        R[i, list(Xm.columns).index(c)] = 1.0
    w = res.wald_test(R, use_f=True, scalar=True)
    return {
        "F": float(w.statistic), "p": float(w.pvalue),
        "sum_coef": float(res.params[xcols].sum()),
        "n": int(len(data)), "maxlag": maxlag,
    }


def granger_both(d_logit: pd.Series, r_asset: pd.Series, maxlag: int = 5) -> pd.DataFrame:
    a = granger(d_logit, r_asset, maxlag)
    b = granger(r_asset, d_logit, maxlag)
    return pd.DataFrame({"pm_to_asset": a, "asset_to_pm": b})


# --------------------------------------------------------------------------
# Cross-correlation function
# --------------------------------------------------------------------------
def cross_correlation(x: pd.Series, y: pd.Series, lags: int = 15) -> pd.Series:
    """corr(x_{t-k}, y_t); index k>0 means x leads y by k minutes."""
    df = pd.concat({"x": x, "y": y}, axis=1).dropna()
    out = {}
    for k in range(-lags, lags + 1):
        out[k] = df["x"].shift(k).corr(df["y"])
    return pd.Series(out, name="xcorr")


# --------------------------------------------------------------------------
# Transfer entropy
# --------------------------------------------------------------------------
def _discretise(s: np.ndarray, bins: int) -> np.ndarray:
    # quantile bins so skewed PM changes don't collapse into one cell;
    # exact zeros (no PM update) get their own cell.
    out = np.zeros_like(s, dtype=int)
    nz = s != 0
    if nz.sum() > bins:
        qs = np.quantile(s[nz], np.linspace(0, 1, bins + 1)[1:-1])
        out[nz] = np.digitize(s[nz], qs) + 1
    else:
        out[nz] = 1
    return out


def _entropy_counts(keys: np.ndarray) -> float:
    counts = np.bincount(keys)
    counts = counts[counts > 0]
    p = counts / counts.sum()
    return float(-(p * np.log(p)).sum())


def _te(xd: np.ndarray, yd: np.ndarray, lag: int, nb: int | None = None) -> float:
    """TE_{x->y} = H(y_t,y_{t-lag}) - H(y_{t-lag}) - H(y_t,y_{t-lag},x_{t-lag}) + H(y_{t-lag},x_{t-lag}).

    Symbols are small ints; joint states are encoded as a single int so each
    entropy is one bincount. ~100x faster than np.unique(axis=0).
    """
    nb = nb or int(max(xd.max(), yd.max()) + 1)
    yt, yp, xp = yd[lag:], yd[:-lag], xd[:-lag]
    H_yt_yp = _entropy_counts(yt * nb + yp)
    H_yp = _entropy_counts(yp)
    H_yt_yp_xp = _entropy_counts((yt * nb + yp) * nb + xp)
    H_yp_xp = _entropy_counts(yp * nb + xp)
    return H_yt_yp - H_yp - (H_yt_yp_xp - H_yp_xp)


def transfer_entropy(x: pd.Series, y: pd.Series, lag: int = 1, bins: int = 4,
                     n_surrogates: int = 200, seed: int = 0) -> dict:
    """TE x->y with shuffle-surrogate p-value (shuffling x destroys timing)."""
    df = pd.concat({"x": x, "y": y}, axis=1).dropna()
    if len(df) < 200:
        return {"te": np.nan, "p": np.nan, "n": len(df)}
    xd = _discretise(df["x"].to_numpy(), bins)
    yd = _discretise(df["y"].to_numpy(), bins)
    nb = int(max(xd.max(), yd.max()) + 1)
    te = _te(xd, yd, lag, nb)
    rng = np.random.default_rng(seed)
    null = np.array([_te(rng.permutation(xd), yd, lag, nb) for _ in range(n_surrogates)])
    return {"te": float(te), "p": float(np.mean(null >= te)), "te_null_mean": float(null.mean()),
            "n": int(len(df)), "lag": lag}


def transfer_entropy_both(d_logit: pd.Series, r_asset: pd.Series, lag: int = 1, **kw) -> pd.DataFrame:
    a = transfer_entropy(d_logit, r_asset, lag, **kw)
    b = transfer_entropy(r_asset, d_logit, lag, **kw)
    return pd.DataFrame({"pm_to_asset": a, "asset_to_pm": b})


# --------------------------------------------------------------------------
# Hasbrouck information share (segment-wise, with caveat)
# --------------------------------------------------------------------------
def hasbrouck_info_share(p1: pd.Series, p2: pd.Series, k_ar_diff: int = 5) -> dict:
    """Information shares (upper/lower bounds) of p1 and p2 from a 2-variable VECM.

    p1, p2: price *levels* (e.g. PM log-odds and asset log price) over one
    segment. Checks Johansen cointegration first; if not cointegrated at 10%,
    returns NaNs with a flag rather than a meaningless number.
    """
    df = pd.concat({"p1": p1, "p2": p2}, axis=1).dropna()
    if len(df) < 100:
        return {"is_p1_lower": np.nan, "is_p1_upper": np.nan, "cointegrated": False, "n": len(df)}
    jres = coint_johansen(df.to_numpy(), det_order=0, k_ar_diff=k_ar_diff)
    # trace stat for r=0 vs 10% critical value (index 0 of cvt row 0)
    coint = bool(jres.lr1[0] > jres.cvt[0, 0])
    if not coint:
        return {"is_p1_lower": np.nan, "is_p1_upper": np.nan, "cointegrated": False, "n": len(df)}
    vecm = VECM(df.to_numpy(), k_ar_diff=k_ar_diff, coint_rank=1, deterministic="n").fit()
    # Common-trend weights: orthogonal complement of alpha (adjustment coeffs).
    alpha = vecm.alpha.ravel()
    psi = np.array([alpha[1], -alpha[0]])  # alpha_perp for 2 vars
    psi = psi / psi.sum() if psi.sum() != 0 else psi
    Omega = np.cov(vecm.resid.T)

    def share(order):
        P = np.array(Omega)[np.ix_(order, order)]
        L = np.linalg.cholesky(P)
        pw = psi[order]
        contrib = (pw @ L) ** 2
        return contrib / contrib.sum()

    s12 = share([0, 1])  # p1 first (upper bound for p1)
    s21 = share([1, 0])  # p2 first (lower bound for p1)
    return {
        "is_p1_upper": float(s12[0]),
        "is_p1_lower": float(s21[1]),
        "cointegrated": True,
        "n": int(len(df)),
    }


# --------------------------------------------------------------------------
# Convenience: run the standard battery on one aligned overlap frame
# --------------------------------------------------------------------------
def battery(ov: pd.DataFrame, maxlag: int = 5, te_lag: int = 1, te_kw: dict | None = None) -> dict:
    g = granger_both(ov["d_logit"], ov["r_asset"], maxlag)
    te = transfer_entropy_both(ov["d_logit"], ov["r_asset"], te_lag, **(te_kw or {}))
    xc = cross_correlation(ov["d_logit"], ov["r_asset"], lags=15)
    return {
        "granger_pm_to_asset_p": g.loc["p", "pm_to_asset"],
        "granger_asset_to_pm_p": g.loc["p", "asset_to_pm"],
        "granger_pm_to_asset_F": g.loc["F", "pm_to_asset"],
        "granger_asset_to_pm_F": g.loc["F", "asset_to_pm"],
        "te_pm_to_asset": te.loc["te", "pm_to_asset"],
        "te_pm_to_asset_p": te.loc["p", "pm_to_asset"],
        "te_asset_to_pm": te.loc["te", "asset_to_pm"],
        "te_asset_to_pm_p": te.loc["p", "asset_to_pm"],
        "xcorr_peak_lag": int(xc.abs().idxmax()),
        "xcorr_peak": float(xc.loc[xc.abs().idxmax()]),
        "n": int(len(ov)),
    }
