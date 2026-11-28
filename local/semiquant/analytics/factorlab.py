"""Factor lab: do classic price signals predict next month's returns in this universe? The research
loop of a systematic equity desk (Alphalens-style): rank information coefficients, quintile
spreads, decay and turnover, plus today's ranking.

Signals, computed at each month-end from prices up to that day only (no look-ahead), all signed so
that a higher value is the side the signal favours:
  momentum 12-1 (return from 12 to 1 month ago), short-term reversal (minus the last month's return),
  low volatility (minus the 3-month daily volatility), 52-week-high proximity (price / 1-year high),
  trend (price / 200-day average - 1), low beta (minus the 1-year beta to the equal-weight universe).

For each signal and month: the Spearman rank correlation (IC) between the signal and the next
month's returns across the universe; mean IC, t-statistic, annualised IC information ratio, hit
rate; equal-weight quintile portfolios rebalanced monthly and the top-minus-bottom spread
(annualised return, volatility, Sharpe, max drawdown, cumulative path); top-quintile turnover; the
mean IC at 1, 3 and 6 months (decay); and the average correlation between signals.

Caveats (shown to the user): today's members only (survivorship bias), no trading costs, local
currencies, few dozen stocks per month (noisy ICs).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ._util import iso, jsonable

__all__ = ["SIGNALS", "signal_frames", "factor_lab"]

SIGNALS = [
    ("mom_12_1", "Momentum 12-1", "Return from 12 months to 1 month ago (the last month is skipped)."),
    ("reversal_1m", "Short-term reversal", "Minus the last month's return: last month's losers tend to bounce."),
    ("low_vol", "Low volatility", "Minus the 3-month volatility of daily returns."),
    ("high_52w", "52-week-high proximity", "Price divided by the 1-year high (George & Hwang 2004)."),
    ("trend_200", "Trend", "Price relative to its 200-day average."),
    ("low_beta", "Low beta", "Minus the 1-year beta to the equal-weight universe (betting against beta)."),
]


def signal_frames(closes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Daily signal values for every stock (rows = dates, columns = tickers)."""
    c = closes.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    c = c.where(c > 0).ffill(limit=5)
    r = c.pct_change(fill_method=None)
    ew = r.mean(axis=1)
    beta = r.rolling(252, min_periods=200).cov(ew).div(ew.rolling(252, min_periods=200).var(), axis=0)
    return {
        "mom_12_1": c.shift(21) / c.shift(252) - 1,
        "reversal_1m": -(c / c.shift(21) - 1),
        "low_vol": -r.rolling(63, min_periods=50).std(),
        "high_52w": c / c.rolling(252, min_periods=200).max(),
        "trend_200": c / c.rolling(200, min_periods=180).mean() - 1,
        "low_beta": -beta,
    }


def _rank_ic(a: pd.Series, b: pd.Series, min_names: int) -> float | None:
    m = a.notna() & b.notna()
    if m.sum() < min_names:
        return None
    x, y = a[m].rank(), b[m].rank()
    if x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _max_dd(cum: np.ndarray) -> float:
    peak = np.maximum.accumulate(cum)
    return float((cum / peak - 1).min())


def factor_lab(closes: pd.DataFrame, years: int = 10, quantiles: int = 5, min_names: int = 15,
               names: dict[str, str] | None = None) -> dict:
    """Run the factor research loop on daily ``closes`` (columns = the universe's stocks)."""
    c = closes.apply(pd.to_numeric, errors="coerce")
    c = c.loc[c.index >= c.index[-1] - pd.DateOffset(years=years + 1)] if len(c) else c
    c = c.loc[:, c.notna().sum() >= 260]
    out = {"available": False, "n_assets": int(c.shape[1])}
    if c.shape[1] < min_names or len(c) < 300:
        return {**out, "message": "Not enough stocks with a year of history for cross-sectional research."}
    sig = signal_frames(c)
    month_end = c.groupby(c.index.to_period("M")).tail(1).index
    month_end = month_end[month_end <= c.index[-1]]
    M = c.ffill(limit=5).loc[month_end]
    fwd = {h: M.shift(-h) / M - 1 for h in (1, 3, 6)}
    first = c.index[0] + pd.DateOffset(months=13)
    months = [t for t in month_end[:-1] if t >= first and t >= c.index[-1] - pd.DateOffset(years=years)]
    if len(months) < 24:
        return {**out, "message": "Fewer than 24 months of signal history."}
    res = []
    for key, label, desc in SIGNALS:
        S = sig[key].loc[month_end]
        ics, ic3, ic6, qrets, spread, tops, prev_top = [], [], [], [], [], [], None
        for t in months:
            s_t, f_t = S.loc[t], fwd[1].loc[t]
            ic = _rank_ic(s_t, f_t, min_names)
            ics.append(ic)
            ic3.append(_rank_ic(s_t, fwd[3].loc[t], min_names))
            ic6.append(_rank_ic(s_t, fwd[6].loc[t], min_names))
            m = s_t.notna() & f_t.notna()
            if m.sum() >= min_names:
                bins = pd.qcut(s_t[m].rank(method="first"), quantiles, labels=False)
                qr = f_t[m].groupby(bins).mean().reindex(range(quantiles))
                qrets.append(qr.to_numpy(float))
                spread.append(float(qr.iloc[-1] - qr.iloc[0]))
                top = set(bins[bins == quantiles - 1].index)
                if prev_top is not None and top:
                    tops.append(1 - len(top & prev_top) / len(top))
                prev_top = top
            else:
                qrets.append(np.full(quantiles, np.nan))
                spread.append(np.nan)
        icv = np.array([x for x in ics if x is not None], float)
        sp = np.array(spread, float)
        spv = sp[np.isfinite(sp)]
        Q = np.vstack(qrets)
        cum = np.cumprod(1 + np.nan_to_num(sp))
        n = icv.size
        ic_mean = float(icv.mean()) if n else None
        ic_sd = float(icv.std(ddof=1)) if n > 2 else None
        ann = float((1 + spv).prod() ** (12 / spv.size) - 1) if spv.size else None
        vol = float(spv.std(ddof=1) * np.sqrt(12)) if spv.size > 2 else None
        res.append({
            "key": key, "label": label, "desc": desc, "months": n,
            "ic_mean": ic_mean, "ic_sd": ic_sd,
            "ic_t": ic_mean / ic_sd * np.sqrt(n) if ic_sd else None,
            "ic_ir": ic_mean / ic_sd * np.sqrt(12) if ic_sd else None,
            "hit_rate": float((icv > 0).mean()) if n else None,
            "decay": {str(h): (float(np.nanmean([x for x in v if x is not None])) if any(x is not None for x in v) else None)
                      for h, v in ((1, ics), (3, ic3), (6, ic6))},
            "spread": {"ann": ann, "vol": vol, "sharpe": ann / vol if ann is not None and vol else None,
                       "max_dd": _max_dd(cum) if cum.size else None, "hit": float((spv > 0).mean()) if spv.size else None},
            "quintiles": [float((1 + Q[:, i][np.isfinite(Q[:, i])]).prod() ** (12 / max(1, np.isfinite(Q[:, i]).sum())) - 1)
                          for i in range(quantiles)],
            "turnover": float(np.mean(tops)) if tops else None,
            "ic_series": {"t": [iso(t) for t in months], "v": ics},
            "spread_cum": {"t": [iso(t) for t in months], "v": (cum - 1).tolist()},
        })
    # how alike the signals are: mean cross-sectional rank correlation over the sampled months
    keys = [k for k, *_ in SIGNALS]
    corr = np.full((len(keys), len(keys)), np.nan)
    for i, a in enumerate(keys):
        for j, b in enumerate(keys):
            if j < i:
                corr[i, j] = corr[j, i]
                continue
            vals = [_rank_ic(sig[a].loc[t], sig[b].loc[t], min_names) for t in months[::3]]
            vals = [v for v in vals if v is not None]
            corr[i, j] = float(np.mean(vals)) if vals else np.nan
    # today's ranking: z-score of each signal across stocks, composite = mean z
    last = pd.DataFrame({k: sig[k].iloc[-1] for k in keys})
    z = (last - last.mean()) / last.std(ddof=0)
    comp = z.mean(axis=1, skipna=True).dropna().sort_values(ascending=False)

    def row(tk):
        return {"ticker": tk, "name": (names or {}).get(tk), "composite": float(comp[tk]),
                **{k: (float(z.at[tk, k]) if pd.notna(z.at[tk, k]) else None) for k in keys}}
    out.update(available=True, start=iso(months[0]), end=iso(months[-1]), months=len(months), signals=res,
               signal_corr={"labels": [lbl for _, lbl, _ in SIGNALS], "z": corr.tolist()},
               current={"asof": iso(c.index[-1]), "top": [row(t) for t in comp.index[:10]], "bottom": [row(t) for t in comp.index[-10:][::-1]]},
               caveats=["Today's members only: stocks that dropped out (bankruptcies, delistings) are missing, which flatters results.",
                        "No trading costs; equal-weight monthly rebalancing.",
                        "Each month ranks a few dozen to a few hundred stocks, so single-month ICs are noisy: judge the averages and t-statistics."])
    return jsonable(out)
