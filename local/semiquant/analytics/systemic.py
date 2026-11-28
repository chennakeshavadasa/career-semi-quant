"""Market-wide fragility, as institutional risk desks monitor it, computed on a stock universe.

* Absorption ratio (Kritzman, Li, Page & Rigobon 2011): the share of the universe's variance that
  its top eigenvectors (a fifth of the number of stocks) absorb, from the 1-year correlation matrix
  of daily returns. High = the stocks move as one, so shocks spread fast ("fragile market"). The
  standardised shift (3-week mean minus 1-year mean, in 1-year standard deviations) above +1 has
  historically preceded drawdowns. ``pc1`` is the first eigenvector's share (the market factor).
* Turbulence index (Kritzman & Li 2010; Chow, Jacquier, Kritzman & Lowry 1999): the Mahalanobis
  distance of a day's returns from their trailing mean using the trailing covariance (Ledoit-Wolf
  shrunk, refitted monthly), divided by the number of stocks so a typical day is about 1. High =
  unusual moves or unusual combinations of moves (correlations breaking), even on a flat index day.
  ``contributors`` splits the latest value by stock (x_i * (Sigma^-1 x)_i).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ._util import iso, jsonable, pct_rank

__all__ = ["absorption_ratio", "turbulence"]


def _returns(closes: pd.DataFrame, min_coverage: float = 0.9) -> pd.DataFrame:
    c = closes.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    raw = c.where(c > 0)
    traded = raw.notna().mean(axis=1)
    c = raw.ffill(limit=3)  # a holiday on one exchange: no move for those stocks
    c = c.loc[:, c.notna().mean() >= min_coverage]
    r = np.log(c).diff().iloc[1:]
    return r[traded.iloc[1:] >= 0.5]  # drop days most of the universe did not trade


def absorption_ratio(closes: pd.DataFrame, window: int = 252, frac: float = 0.2, step: int = 5,
                     history: int = 1260) -> dict:
    """Absorption ratio and first-eigenvector share every ``step`` days over the last ``history``
    days, the current values, their percentile in that history and the standardised shift."""
    r = _returns(closes).tail(history + window)
    out = {"available": False, "n_assets": int(r.shape[1]), "window": window}
    if r.shape[1] < 10 or len(r) < window + 2 * step:
        return out
    ts, ar, pc1, used = [], [], [], 0
    for end in range(window, len(r) + 1, step):
        R = r.iloc[end - window:end].dropna(axis=1)
        if R.shape[1] < 10:
            continue
        sd = R.std(ddof=1)
        R = R.loc[:, sd > 0]
        corr = np.corrcoef(R.to_numpy(float), rowvar=False)
        ev = np.sort(np.clip(np.linalg.eigvalsh(corr), 0, None))[::-1]
        tot = ev.sum()
        if not tot > 0:
            continue
        k = max(1, int(round(frac * len(ev))))
        used = len(ev)
        ts.append(r.index[end - 1])
        ar.append(float(ev[:k].sum() / tot))
        pc1.append(float(ev[0] / tot))
    if len(ar) < 10:
        return out
    a = np.asarray(ar)
    yr = a[-max(2, 252 // step):]
    shift = float((a[-3:].mean() - yr.mean()) / yr.std(ddof=1)) if yr.std(ddof=1) > 0 else None
    out.update(available=True, n_assets=used, n_top=max(1, int(round(frac * used))), current=float(a[-1]), pc1=float(pc1[-1]),
               percentile=pct_rank(a, float(a[-1])), shift=shift,
               series={"t": [iso(t) for t in ts], "ar": ar, "pc1": pc1})
    return jsonable(out)


def _shrunk_cov(R: pd.DataFrame) -> np.ndarray:
    """Daily covariance, Ledoit-Wolf shrinkage towards the scaled identity."""
    X = R.to_numpy(float)
    X = X - X.mean(axis=0)
    n, p = X.shape
    S = X.T @ X / n
    mu = np.trace(S) / p
    F = mu * np.eye(p)
    d2 = float(((S - F) ** 2).sum())
    # sum_i ||x_i x_i' - S||_F^2 = sum_i ||x_i||^4 - 2 sum_i x_i' S x_i + n ||S||_F^2
    nrm = (X ** 2).sum(axis=1)
    b2 = float((nrm ** 2).sum() - 2 * ((X @ S) * X).sum() + n * (S ** 2).sum())
    b2 = min(b2 / n ** 2, d2)
    delta = b2 / d2 if d2 > 0 else 1.0
    return delta * F + (1 - delta) * S


def turbulence(closes: pd.DataFrame, window: int = 252, refit: int = 21, history: int = 756, smooth: int = 10) -> dict:
    """Daily turbulence over the last ``history`` days (and its ``smooth``-day mean), the current
    value, its percentile, the 95th-percentile threshold, turbulent days in the last month and the
    stocks driving the latest reading."""
    r = _returns(closes).tail(history + window)
    out = {"available": False, "n_assets": int(r.shape[1]), "window": window}
    if r.shape[1] < 10 or len(r) < window + 21:
        return out
    days, vals, last_contrib = [], [], None
    start = window
    while start < len(r):
        est = r.iloc[start - window:start].dropna(axis=1, thresh=int(0.9 * window))
        est = est.fillna(0.0)
        cols = list(est.columns)
        if len(cols) < 10:
            start += refit
            continue
        mu = est.mean().to_numpy(float)
        inv = np.linalg.pinv(_shrunk_cov(est))
        block = r.iloc[start:start + refit][cols].fillna(0.0)
        for t, row in block.iterrows():
            x = row.to_numpy(float) - mu
            ix = inv @ x
            days.append(t)
            vals.append(float(x @ ix) / len(cols))
            last_contrib = (cols, x * ix)
        start += refit
    if len(vals) < 30:
        return out
    v = pd.Series(vals, index=pd.DatetimeIndex(days))
    sm = v.rolling(smooth, min_periods=1).mean()
    thr = float(v.quantile(0.95))
    contrib = []
    if last_contrib:
        cols, c = last_contrib
        tot = float(np.sum(c))
        order = np.argsort(c)[::-1][:6]
        contrib = [{"ticker": cols[i], "share": float(c[i] / tot) if tot > 0 else None} for i in order]
    out.update(available=True, current=float(v.iloc[-1]), current_smooth=float(sm.iloc[-1]),
               percentile=pct_rank(v.to_numpy(), float(v.iloc[-1])), percentile_smooth=pct_rank(sm.to_numpy(), float(sm.iloc[-1])),
               threshold_95=thr, turbulent_days_21=int((v.tail(21) > thr).sum()), contributors=contrib,
               series={"t": [iso(t) for t in v.index], "d": [float(x) for x in v], "smooth": [float(x) for x in sm]})
    return jsonable(out)
