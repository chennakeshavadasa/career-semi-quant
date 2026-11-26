"""Pairs-trading analytics: Engle-Granger cointegration, mean-reversion half-life, Hurst exponent,
spread z-scores and universe scans with false-discovery-rate control.

Methods: Engle & Granger (1987) two-step cointegration test on log prices with MacKinnon (1994, 2010)
p-values (statsmodels ``coint`` / ``mackinnonp``); half-life of mean reversion from an AR(1) fit of the
spread, HL = -ln 2 / ln(phi); Hurst exponent by the variance-of-lagged-differences method
(std(x_{t+k} - x_t) ~ k^H); Benjamini & Hochberg (1995) q-values across all tested pairs.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.adfvalues import mackinnonp
from statsmodels.tsa.stattools import adfuller, coint

from ._util import clean, jsonable, ser

__all__ = ["hurst", "engle_granger", "scan_pairs"]

SERIES_DAYS = 504  # spread / z series returned: about two years


def hurst(series) -> float:
    """Hurst exponent by the variance-of-lagged-differences method: the slope of log std(x_{t+k} - x_t)
    on log k for k = 2 .. min(100, n/2). ~0.5 random walk, < 0.5 mean-reverting, > 0.5 trending.
    Apply it to log prices or a spread. NaN for fewer than 20 observations."""
    x = pd.to_numeric(pd.Series(series), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    n = x.size
    if n < 20:
        return float("nan")
    lags = np.arange(2, max(min(100, n // 2), 4))
    sd = np.array([np.std(x[k:] - x[:-k]) for k in lags])
    ok = sd > 0
    if ok.sum() < 3:
        return float("nan")
    return float(np.polyfit(np.log(lags[ok]), np.log(sd[ok]), 1)[0])


def _ols(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """Intercept and slope of y on [1, x]."""
    xm, ym = x.mean(), y.mean()
    vx = ((x - xm) ** 2).sum()
    b = float(((x - xm) * (y - ym)).sum() / vx) if vx > 0 else float("nan")
    return float(ym - b * xm), b


def _half_life(s: np.ndarray) -> float | None:
    """Half-life (in observations) from s_t = c + phi s_{t-1} + e: -ln 2 / ln phi for 0 < phi < 1."""
    if s.size < 10:
        return None
    _c, phi = _ols(s[1:], s[:-1])
    if not np.isfinite(phi) or phi <= 0 or phi >= 1:
        return None
    return float(-math.log(2.0) / math.log(phi))


def _eg_fast(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float, float]:
    """Fast Engle-Granger: OLS y = a + b x, ADF regression without constant and one augmentation lag on
    the residuals (as statsmodels ``coint(..., maxlag=1, autolag=None)``), MacKinnon p-value with
    N = 2 variables and a constant. Returns (t, p, a, b)."""
    a, b = _ols(y, x)
    if not np.isfinite(b):
        return float("nan"), 1.0, a, b
    e = y - a - b * x
    de = np.diff(e)
    z = de[1:]
    Z = np.column_stack([e[1:-1], de[:-1]])
    ztz = Z.T @ Z
    try:
        coef = np.linalg.solve(ztz, Z.T @ z)
        resid = z - Z @ coef
        dof = z.size - 2
        s2 = float(resid @ resid) / dof
        se = math.sqrt(s2 * np.linalg.inv(ztz)[0, 0])
        t = float(coef[0] / se) if se > 0 else float("nan")
    except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
        return float("nan"), 1.0, a, b
    p = float(mackinnonp(t, regression="c", N=2)) if np.isfinite(t) else 1.0
    return t, p, a, b


def _signal(z: float | None) -> str | None:
    if z is None or not np.isfinite(z):
        return None
    if z < -2.0:
        return "long spread"
    if z > 2.0:
        return "short spread"
    if abs(z) < 0.5:
        return "exit"
    return "hold"


def _log_pair(y: pd.Series, x: pd.Series) -> pd.DataFrame:
    df = pd.concat({"y": pd.to_numeric(y, errors="coerce"), "x": pd.to_numeric(x, errors="coerce")}, axis=1,
                   join="inner")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[(df > 0).all(axis=1)].dropna()
    return np.log(df)


def engle_granger(y: pd.Series, x: pd.Series, z_window: int = 60) -> dict:
    """Engle-Granger cointegration analysis of a pair of price series (log prices, aligned dates).

    pvalue: statsmodels ``coint`` (ADF on the OLS residuals with AIC lag selection, MacKinnon
    p-value); hedge_ratio / intercept: OLS log y = intercept + hedge_ratio x log x; spread = residual;
    half_life_days from an AR(1) fit of the spread; adf_p: ADF test of the spread with a constant
    (standard Dickey-Fuller tables, optimistic for an estimated spread, hence ``pvalue`` is the test to
    use); hurst of the spread; zscore = (spread - rolling mean) / rolling std over ``z_window`` sessions;
    signal: "long spread" (buy y, sell hedge_ratio x) if z < -2, "short spread" if z > 2, "exit" if
    |z| < 0.5, else "hold"; corr = correlation of daily log returns.

    Returns {"y", "x", "n", "pvalue", "coint_t", "adf_p", "hedge_ratio", "intercept", "half_life_days",
    "hurst", "zscore", "signal", "corr", "spread": ser, "z": ser (last ~2 years), "warnings": [...]}.
    """
    yn = str(getattr(y, "name", None) or "y")
    xn = str(getattr(x, "name", None) or "x")
    out = {"y": yn, "x": xn, "n": 0, "pvalue": None, "coint_t": None, "adf_p": None, "hedge_ratio": None,
           "intercept": None, "half_life_days": None, "hurst": None, "zscore": None, "signal": None, "corr": None,
           "spread": ser(None), "z": ser(None), "warnings": []}
    try:
        L = _log_pair(y, x)
    except (TypeError, ValueError):
        out["warnings"].append("invalid price input")
        return jsonable(out)
    n = len(L)
    out["n"] = n
    zw = max(int(z_window or 60), 5)
    if n < max(60, zw + 10):
        out["warnings"].append(f"only {n} overlapping positive prices (need {max(60, zw + 10)})")
        return jsonable(out)
    ly, lx = L["y"].to_numpy(), L["x"].to_numpy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            t, p, _crit = coint(ly, lx)
            out["coint_t"], out["pvalue"] = float(t), float(p)
        except (ValueError, np.linalg.LinAlgError) as exc:
            out["warnings"].append(f"coint failed: {exc}")
        a, b = _ols(ly, lx)
        spread = pd.Series(ly - a - b * lx, index=L.index)
        try:
            out["adf_p"] = float(adfuller(spread.to_numpy(), regression="c", autolag="AIC", result_object=False)[1])
        except (ValueError, np.linalg.LinAlgError, TypeError):
            pass
    m = spread.rolling(zw, min_periods=zw).mean()
    sd = spread.rolling(zw, min_periods=zw).std(ddof=1)
    z = ((spread - m) / sd).replace([np.inf, -np.inf], np.nan)
    zl = clean(z.iloc[-1])
    rets = L.diff().dropna()
    out.update({"hedge_ratio": b, "intercept": a, "half_life_days": _half_life(spread.to_numpy()),
                "hurst": hurst(spread), "zscore": zl, "signal": _signal(zl),
                "corr": float(rets["y"].corr(rets["x"])) if len(rets) > 2 else None,
                "spread": ser(spread.iloc[-SERIES_DAYS:]), "z": ser(z.iloc[-SERIES_DAYS:].dropna())})
    return jsonable(out)


def _bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg (1995) adjusted p-values (q-values), monotone in p, capped at 1."""
    p = np.asarray(p, float)
    m = p.size
    if m == 0:
        return p
    order = np.argsort(p, kind="stable")
    ranked = p[order] * m / np.arange(1, m + 1)
    q = np.minimum(np.minimum.accumulate(ranked[::-1])[::-1], 1.0)
    out = np.empty(m)
    out[order] = q
    return out


def scan_pairs(prices: pd.DataFrame, min_corr: float = 0.6, lookback: int = 504, max_results: int = 25,
               z_window: int = 60) -> dict:
    """Scan every pair of a price universe for cointegration.

    Over the last ``lookback`` sessions: pairs whose daily log-return correlation is >= ``min_corr`` are
    tested both ways with a fast Engle-Granger test (ADF with one augmentation lag on the OLS residuals,
    MacKinnon p-value) and the ordering with the lower p-value is kept (y = dependent leg). Benjamini-
    Hochberg q-values are computed over all tested pairs. ``stable`` = p < 0.10 in both halves of the
    window (split-sample stability). Results keep pairs whose half-life is within 2-60 days, sorted by
    p-value (best first), at most ``max_results``.

    Returns {"tested" (pairs that passed the correlation filter and were tested), "n_pairs" (all pairs),
    "n_significant" (q < 0.05), "lookback", "results": [{"y", "x", "pvalue", "qvalue", "stable",
    "p_first_half", "p_second_half", "half_life_days", "zscore", "hedge_ratio", "corr", "signal"}],
    "warnings": [...]}.
    """
    out = {"tested": 0, "n_pairs": 0, "n_significant": 0, "lookback": lookback, "results": [], "warnings": []}
    if prices is None or not isinstance(prices, pd.DataFrame) or prices.shape[1] < 2:
        out["warnings"].append("need a price frame with at least two tickers")
        return jsonable(out)
    P = prices.apply(pd.to_numeric, errors="coerce")
    P = P[~P.index.duplicated(keep="last")].sort_index()
    P = P.loc[:, P.notna().any()]
    P = P.where(P > 0).iloc[-int(max(lookback, 60)):]
    P = P.loc[:, P.notna().sum() >= 100]
    cols = list(P.columns)
    k = len(cols)
    out["n_pairs"] = k * (k - 1) // 2
    if k < 2:
        out["warnings"].append("fewer than two tickers with 100+ prices in the lookback window")
        return jsonable(out)
    L = np.log(P)
    corr = L.diff().corr(min_periods=60).to_numpy()
    A = L.to_numpy()
    fin = np.isfinite(A)
    zw = max(int(z_window or 60), 5)
    rows = []
    for i in range(k):
        for j in range(i + 1, k):
            c = corr[i, j]
            if not np.isfinite(c) or c < min_corr:
                continue
            msk = fin[:, i] & fin[:, j]
            if msk.sum() < 100:
                continue
            yi, xj = A[msk, i], A[msk, j]
            t1, p1, a1, b1 = _eg_fast(yi, xj)
            t2, p2, a2, b2 = _eg_fast(xj, yi)
            if p2 < p1:
                yy, xx, p, a, b, yn, xn = xj, yi, p2, a2, b2, cols[j], cols[i]
            else:
                yy, xx, p, a, b, yn, xn = yi, xj, p1, a1, b1, cols[i], cols[j]
            h = yy.size // 2
            ph1 = _eg_fast(yy[:h], xx[:h])[1]
            ph2 = _eg_fast(yy[h:], xx[h:])[1]
            s = yy - a - b * xx
            tail = s[-zw:]
            sd = tail.std(ddof=1)
            z = float((s[-1] - tail.mean()) / sd) if sd > 0 else None
            rows.append({"y": yn, "x": xn, "pvalue": p, "stable": bool(ph1 < 0.10 and ph2 < 0.10),
                         "p_first_half": ph1, "p_second_half": ph2, "half_life_days": _half_life(s), "zscore": z,
                         "hedge_ratio": b, "corr": float(c), "signal": _signal(z)})
    out["tested"] = len(rows)
    if not rows:
        out["warnings"].append(f"no pair with return correlation >= {min_corr}")
        return jsonable(out)
    q = _bh(np.array([r["pvalue"] for r in rows]))
    for r, qv in zip(rows, q):
        r["qvalue"] = float(qv)
    out["n_significant"] = int((q < 0.05).sum())
    keep = [r for r in rows if r["half_life_days"] is not None and 2.0 <= r["half_life_days"] <= 60.0]
    keep.sort(key=lambda r: (r["pvalue"], r["qvalue"]))
    out["results"] = keep[:max(int(max_results), 0)]
    return jsonable(out)
