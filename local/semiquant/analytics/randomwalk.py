"""Is this price a random walk, trending or mean-reverting? The diagnostics a quant runs before
choosing a momentum or a mean-reversion model.

* Variance ratios (Lo & MacKinlay 1988): VR(q) = variance of q-day returns / (q x variance of daily
  returns). 1 for a random walk; > 1 when returns are positively autocorrelated (trends persist),
  < 1 when they reverse. z* is the heteroskedasticity-robust statistic (valid under volatility
  clustering), with a two-sided p-value.
* Hurst exponent of log prices (variance of lagged differences): ~0.5 random walk, > 0.5 trending,
  < 0.5 mean-reverting.
* Augmented Dickey-Fuller test (statsmodels) on log prices: a high p-value means a unit root (prices
  wander, no fixed level to revert to).
* Ljung-Box tests on returns (any linear predictability) and on squared returns (volatility
  clustering, i.e. ARCH effects), and the return autocorrelations at lags 1-10.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm

from ._util import as_close, jsonable
from .pairs import hurst

__all__ = ["variance_ratios", "random_walk_tests"]


def _logp(prices) -> np.ndarray:
    if isinstance(prices, np.ndarray):
        prices = pd.Series(prices)
    s = pd.to_numeric(as_close(prices), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]
    return np.log(s.to_numpy(float))


def variance_ratios(prices, qs=(2, 5, 10, 20)) -> list[dict]:
    """Lo-MacKinlay variance ratios with overlapping q-period returns and the robust z* statistic."""
    x = _logp(prices)
    n = x.size - 1
    out = []
    if n < 60:
        return out
    r = np.diff(x)
    mu = (x[-1] - x[0]) / n
    d = r - mu
    s2a = float((d ** 2).sum() / (n - 1))
    if not s2a > 0:
        return out
    d2 = d ** 2
    denom = float(d2.sum()) ** 2
    for q in qs:
        if q >= n // 2:
            continue
        m = q * (n - q + 1) * (1 - q / n)
        rq = x[q:] - x[:-q] - q * mu
        vr = float((rq ** 2).sum() / m) / s2a
        theta = 0.0
        for j in range(1, q):
            delta = n * float((d2[j:] * d2[:-j]).sum()) / denom
            theta += (2 * (q - j) / q) ** 2 * delta
        z = math.sqrt(n) * (vr - 1) / math.sqrt(theta) if theta > 0 else None  # Lo & MacKinlay z*(q)
        out.append({"q": q, "vr": vr, "z": z, "p": float(2 * norm.sf(abs(z))) if z is not None and np.isfinite(z) else None})
    return jsonable(out)


def random_walk_tests(prices, alpha: float = 0.05) -> dict:
    """Variance ratios, Hurst, ADF, Ljung-Box and autocorrelations of daily log returns, plus a plain
    verdict ("trending", "mean-reverting" or "random walk") from the 5- and 10-day variance ratios."""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.tsa.stattools import acf, adfuller

    x = _logp(prices)
    out = {"n": int(x.size), "variance_ratios": [], "hurst": None, "adf": None, "ljung_box": None,
           "ljung_box_sq": None, "acf": None, "verdict": None, "verdict_detail": None}
    if x.size < 120:
        return out
    r = np.diff(x)
    out["variance_ratios"] = variance_ratios(np.exp(x))
    h = hurst(x)
    out["hurst"] = h if np.isfinite(h) else None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            a = adfuller(x, autolag="AIC", regression="c")
            out["adf"] = {"stat": float(a[0]), "p": float(a[1]), "crit_5": float(a[4]["5%"]), "lags": int(a[2])}
        except Exception:  # noqa: BLE001
            pass
        try:
            lb = acorr_ljungbox(r, lags=[5, 10], return_df=True)
            out["ljung_box"] = [{"lag": int(k), "q": float(v.lb_stat), "p": float(v.lb_pvalue)} for k, v in lb.iterrows()]
            lb2 = acorr_ljungbox(r ** 2, lags=[5, 10], return_df=True)
            out["ljung_box_sq"] = [{"lag": int(k), "q": float(v.lb_stat), "p": float(v.lb_pvalue)} for k, v in lb2.iterrows()]
        except Exception:  # noqa: BLE001
            pass
        try:
            ac = acf(r, nlags=10, fft=True)
            out["acf"] = {"lags": list(range(1, 11)), "v": [float(v) for v in ac[1:11]], "band": 1.96 / math.sqrt(r.size)}
        except Exception:  # noqa: BLE001
            pass
    key = [v for v in out["variance_ratios"] if v["q"] in (5, 10) and v.get("p") is not None]
    sig = [v for v in key if v["p"] < alpha]
    if sig and all(v["vr"] > 1 for v in sig):
        out["verdict"] = "trending"
        out["verdict_detail"] = "multi-day returns vary more than a random walk: moves tend to persist (momentum)"
    elif sig and all(v["vr"] < 1 for v in sig):
        out["verdict"] = "mean-reverting"
        out["verdict_detail"] = "multi-day returns vary less than a random walk: moves tend to reverse"
    else:
        out["verdict"] = "random walk"
        out["verdict_detail"] = "no significant persistence or reversal at 5-10 days: past moves do not predict the next"
    return jsonable(out)
