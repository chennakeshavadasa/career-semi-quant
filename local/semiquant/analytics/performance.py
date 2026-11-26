"""Performance analytics: trailing returns, the ratio suite, drawdowns, rolling metrics,
calendar (monthly) returns and the return distribution.

Conventions (see ``_util``): inputs are close Series or OHLCV frames on a sorted tz-naive
DatetimeIndex; NaN, non-finite and non-positive prices are dropped; returns are fractions
(0.05 = 5%); annualisation uses ``periods_per_year`` (252 for daily data). Durations named
``*_days`` are calendar days; ``*_bars`` are counts of observations. Every public function
returns a JSON-ready dict (passed through ``jsonable``) and never raises on short, constant
or NaN-laden inputs: unavailable values are ``None``.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from ._util import TRADING_DAYS, as_close, clean, iso, jsonable, periods_per_year, ser

__all__ = ["returns_table", "summary_stats", "drawdowns", "rolling_metrics", "monthly_returns",
           "return_distribution"]

HORIZONS = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "10Y", "MAX"]
ANNUALIZED = ["3Y", "5Y", "10Y", "MAX"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_BARS = {"1D": 1, "5D": 5}
_CAL_MONTHS = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60, "10Y": 120}
_DAYS_PER_YEAR = 365.25


# --------------------------------------------------------------------------- helpers
def _naive_index(idx: pd.Index) -> pd.DatetimeIndex:
    di = pd.DatetimeIndex(idx)
    return di.tz_localize(None) if di.tz is not None else di


def _prep(x) -> pd.Series:
    """Clean close Series: numeric, finite, > 0, unique sorted tz-naive DatetimeIndex.

    Accepts a close Series or an OHLCV frame (lowercase or Title-case). Returns an empty
    float Series when nothing usable is left (never raises)."""
    if x is None:
        return pd.Series(dtype=float)
    try:
        s = as_close(x)
        s.index = _naive_index(s.index)
    except Exception:  # noqa: BLE001
        return pd.Series(dtype=float)
    v = s.to_numpy(dtype=float)
    s = s[np.isfinite(v) & (v > 0)]
    if not s.index.is_monotonic_increasing or s.index.has_duplicates:
        s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.astype(float)


def _simple_returns(c: pd.Series) -> pd.Series:
    return c.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def _years(t0: pd.Timestamp, t1: pd.Timestamp) -> float:
    return (pd.Timestamp(t1) - pd.Timestamp(t0)).total_seconds() / 86400.0 / _DAYS_PER_YEAR


def _cagr(total_return: float | None, years: float) -> float | None:
    if total_return is None or not years or years <= 0 or total_return <= -1:
        return None
    with np.errstate(over="ignore"):
        try:
            return float((1.0 + total_return) ** (1.0 / years) - 1.0)
        except OverflowError:
            return None


def _on_or_before(s: pd.Series, t: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """(date, value) of the last observation on or before ``t`` (None if there is none)."""
    if len(s) == 0:
        return None
    i = int(s.index.searchsorted(pd.Timestamp(t), side="right")) - 1
    if i < 0:
        return None
    return s.index[i], float(s.iloc[i])


def _std(x: np.ndarray) -> float | None:
    if x.size < 2:
        return None
    sd = float(np.std(x, ddof=1))
    return sd if sd > 1e-14 else None


def _t_mle(x: np.ndarray) -> tuple[float, float, float] | None:
    """Student-t maximum likelihood (df, loc, scale).

    L-BFGS-B with the analytic gradient on standardised data, parameterised as (ln df, loc,
    ln scale) with df in [0.5, 1000]; started from the method-of-moments df. Same estimator as
    ``scipy.stats.t.fit`` (MLE) but ~20x faster. None when it fails or the data are degenerate."""
    from scipy.optimize import minimize
    from scipy.special import digamma, gammaln

    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 20:
        return None
    m0, s0 = float(np.median(x)), float(np.std(x))
    if s0 <= 1e-14:
        return None
    y = (x - m0) / s0
    k = float(pd.Series(y).kurt())
    df0 = min(max(6.0 / k + 4.0, 2.5), 50.0) if k > 0 else 30.0
    sc0 = math.sqrt((df0 - 2.0) / df0) if df0 > 2 else 0.7

    def f(p):
        nu, mu, s = math.exp(p[0]), p[1], math.exp(p[2])
        z = (y - mu) / s
        q = nu + z * z
        ll = n * (gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * math.log(nu * math.pi) - math.log(s)) \
            - 0.5 * (nu + 1) * float(np.log1p(z * z / nu).sum())
        d_mu = float(((nu + 1) * z / (s * q)).sum())
        d_s = -n / s + float(((nu + 1) * z * z / (s * q)).sum())
        d_nu = n * 0.5 * (digamma((nu + 1) / 2) - digamma(nu / 2) - 1.0 / nu) \
            - 0.5 * float(np.log1p(z * z / nu).sum()) + float(((nu + 1) * z * z / (2 * nu * q)).sum())
        return -ll, -np.array([d_nu * nu, d_mu, d_s * s])

    try:
        res = minimize(f, np.array([math.log(df0), 0.0, math.log(sc0)]), jac=True, method="L-BFGS-B",
                       bounds=[(math.log(0.5), math.log(1000.0)), (None, None), (math.log(1e-6), math.log(1e3))])
    except Exception:  # noqa: BLE001
        return None
    if not np.all(np.isfinite(res.x)):
        return None
    nu, mu, s = math.exp(res.x[0]), res.x[1], math.exp(res.x[2])
    return nu, m0 + s0 * mu, s0 * s


def _month_returns(c: pd.Series) -> pd.Series:
    """Calendar-month returns (month-end closes; the first month measured from the first close)."""
    m = c.resample("ME").last().dropna()
    if len(m) == 0:
        return m
    prev = m.shift(1)
    prev.iloc[0] = c.iloc[0]
    return (m / prev - 1.0).dropna()


def _episodes(c: pd.Series) -> list[dict]:
    """Underwater episodes: peak (last high before the drop), trough, recovery (first close
    back at or above the peak) or None if still under water. Non-overlapping by construction."""
    if len(c) < 2:
        return []
    v = c.to_numpy(dtype=float)
    dd = v / np.maximum.accumulate(v) - 1.0
    under = dd < -1e-12
    if not under.any():
        return []
    d = np.diff(np.concatenate([[0], under.astype(np.int8), [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)  # exclusive: first index back at the high (or n)
    idx = c.index
    n = len(v)
    out = []
    for s0, e0 in zip(starts, ends):
        peak_i = max(s0 - 1, 0)
        trough_i = s0 + int(np.argmin(dd[s0:e0]))
        rec_i = e0 if e0 < n else None
        peak_t, trough_t = idx[peak_i], idx[trough_i]
        rec_t = idx[rec_i] if rec_i is not None else None
        end_t = rec_t if rec_t is not None else idx[-1]
        out.append({
            "peak": peak_t, "trough": trough_t, "recovery": rec_t,
            "depth": float(dd[trough_i]),
            "days_to_trough": int((trough_t - peak_t).days),
            "days_to_recover": int((rec_t - trough_t).days) if rec_t is not None else None,
            "length": int((end_t - peak_t).days),
            "length_bars": int((rec_i if rec_i is not None else n - 1) - peak_i),
            "recovered": rec_t is not None,
        })
    return out


# --------------------------------------------------------------------------- returns table
def returns_table(close, benchmarks: dict[str, pd.Series] | None = None) -> dict:
    """Trailing returns over standard horizons for the asset and optional benchmarks.

    Horizons: ``1D``/``5D`` are 1 and 5 trading bars back; ``1M``..``10Y`` are calendar offsets
    from the last date, using the last close on or before the target date (None when the history
    starts after the target); ``YTD`` is measured from the last close on or before 31 December of
    the previous year; ``MAX`` from the first close. ``3Y``, ``5Y``, ``10Y`` and ``MAX`` are
    reported as CAGR ((end/start)^(1/years) - 1, years = calendar days / 365.25). If the whole
    history is shorter than one year, ``MAX`` is the cumulative return and is dropped from the
    ``annualized`` list (annualising sub-year returns is misleading).

    Benchmarks (close Series) are aligned to the asset: each benchmark return uses the
    benchmark's last close on or before the asset's base date and on or before the asset's last
    date, so every row covers the same window.

    Returns keys: ``horizons`` (list), ``annualized`` (horizons reported as CAGR), ``asof``
    (ISO last date), ``rows`` ([{"name": "Asset", "values": {horizon: fraction|None}}, then one
    row per benchmark name]), ``base_dates`` ({horizon: ISO date of the base close|None}).
    """
    c = _prep(close)
    if len(c) == 0:
        rows = [{"name": "Asset", "values": {h: None for h in HORIZONS}}]
        rows += [{"name": str(k), "values": {h: None for h in HORIZONS}} for k in (benchmarks or {})]
        return jsonable({"horizons": HORIZONS, "annualized": list(ANNUALIZED), "asof": None, "rows": rows,
                         "base_dates": {h: None for h in HORIZONS}})
    last_t = c.index[-1]
    first_t = c.index[0]
    bases: dict[str, pd.Timestamp | None] = {}
    for h in HORIZONS:
        base = None
        if h in _BARS:
            n = _BARS[h]
            if len(c) > n:
                base = c.index[-1 - n]
        elif h in _CAL_MONTHS:
            target = last_t - pd.DateOffset(months=_CAL_MONTHS[h])
            if target >= first_t:
                hit = _on_or_before(c, target)
                base = hit[0] if hit else None
        elif h == "YTD":
            hit = _on_or_before(c, pd.Timestamp(year=last_t.year - 1, month=12, day=31, hour=23, minute=59))
            base = hit[0] if hit else None
        elif h == "MAX":
            base = first_t if len(c) > 1 else None
        bases[h] = base
    max_years = _years(first_t, last_t)
    annualized = [h for h in ANNUALIZED if h != "MAX" or max_years >= 1.0]

    def row_values(s: pd.Series) -> dict:
        vals = {}
        end = _on_or_before(s, last_t)
        for h in HORIZONS:
            b = bases[h]
            if b is None or end is None:
                vals[h] = None
                continue
            start = _on_or_before(s, b)
            if start is None or start[1] <= 0:
                vals[h] = None
                continue
            tr = end[1] / start[1] - 1.0
            if h in annualized:
                vals[h] = _cagr(tr, _years(b, last_t))
            else:
                vals[h] = tr
        return vals

    rows = [{"name": "Asset", "values": row_values(c)}]
    for name, b in (benchmarks or {}).items():
        bs = _prep(b)
        bs = bs[bs.index <= last_t]
        rows.append({"name": str(name), "values": row_values(bs) if len(bs) else {h: None for h in HORIZONS}})
    return jsonable({"horizons": HORIZONS, "annualized": annualized, "asof": iso(last_t), "rows": rows,
                     "base_dates": {h: (iso(v) if v is not None else None) for h, v in bases.items()}})


# --------------------------------------------------------------------------- ratio suite
_STAT_KEYS = ["start", "end", "years", "observations", "total_return", "cagr", "vol", "sharpe", "sortino",
              "calmar", "max_drawdown", "max_dd_days", "current_drawdown", "ulcer_index", "omega", "skew",
              "kurtosis", "best_day", "worst_day", "pct_up_days", "var95", "cvar95", "tail_ratio",
              "gain_to_pain", "autocorr1"]
_BENCH_KEYS = ["beta", "alpha", "correlation", "r2", "tracking_error", "information_ratio", "up_capture",
               "down_capture", "bench_cagr", "bench_vol", "bench_sharpe", "bench_max_drawdown"]


def _core_stats(c: pd.Series, rf: float) -> dict:
    out = {k: None for k in _STAT_KEYS}
    if len(c) == 0:
        return out
    out["start"], out["end"] = iso(c.index[0]), iso(c.index[-1])
    out["observations"] = 0
    if len(c) < 2:
        return out
    ppy = periods_per_year(c.index)
    r = _simple_returns(c)
    x = r.to_numpy(dtype=float)
    n = x.size
    out["observations"] = int(n)
    years = _years(c.index[0], c.index[-1])
    out["years"] = years
    total = float(c.iloc[-1] / c.iloc[0] - 1.0)
    out["total_return"] = total
    out["cagr"] = _cagr(total, years)
    dd = c / c.cummax() - 1.0
    mdd = float(dd.min())
    out["max_drawdown"] = mdd
    out["current_drawdown"] = float(dd.iloc[-1])
    out["ulcer_index"] = float(np.sqrt(np.mean(np.square(dd.to_numpy()))))
    eps = _episodes(c)
    out["max_dd_days"] = max((e["length"] for e in eps), default=0)
    if out["cagr"] is not None and mdd < 0:
        out["calmar"] = out["cagr"] / abs(mdd)
    if n == 0:
        return out
    rf_p = (1.0 + rf) ** (1.0 / ppy) - 1.0 if rf else 0.0
    sd = _std(x)
    if sd is not None:
        out["vol"] = sd * math.sqrt(ppy)
        out["sharpe"] = (x.mean() - rf_p) / sd * math.sqrt(ppy)
    elif n >= 2:
        out["vol"] = 0.0
    downside = np.minimum(x - rf_p, 0.0)
    tdd = float(np.sqrt(np.mean(downside ** 2)))
    if tdd > 1e-14:
        out["sortino"] = (x.mean() - rf_p) / tdd * math.sqrt(ppy)
    losses = -x[x < 0].sum()
    gains = x[x > 0].sum()
    if losses > 0:
        out["omega"] = float(gains / losses)
    if n >= 3 and sd is not None:
        out["skew"] = float(r.skew())
    if n >= 4 and sd is not None:
        out["kurtosis"] = float(r.kurt())
    out["best_day"] = float(x.max())
    out["worst_day"] = float(x.min())
    out["pct_up_days"] = float((x > 0).mean())
    q05, q95 = np.quantile(x, [0.05, 0.95])
    out["var95"] = float(-q05)
    out["cvar95"] = float(-x[x <= q05].mean())
    if abs(q05) > 1e-14:
        out["tail_ratio"] = float(abs(q95) / abs(q05))
    # Schwager gain-to-pain: sum of monthly returns / |sum of monthly losses|
    mr = _month_returns(c)
    if len(mr) >= 3:
        pain = -mr[mr < 0].sum()
        if pain > 0:
            out["gain_to_pain"] = float(mr.sum() / pain)
    if n >= 3 and sd is not None:
        out["autocorr1"] = clean(r.autocorr(1))
    return out


def summary_stats(close, benchmark=None, rf: float = 0.0) -> dict:
    """Ratio suite for one asset (optionally relative to a benchmark close series).

    Asset keys (on the asset's full history, simple returns, ``ppy`` from the index):
    ``start``, ``end`` (ISO), ``years`` (calendar), ``observations`` (number of returns),
    ``total_return``, ``cagr``, ``vol`` (sample std x sqrt(ppy)), ``sharpe`` ((mean - rf) / std,
    annualised; rf is an annual rate converted to per period), ``sortino`` (target downside
    deviation at rf, Sortino & Price 1994), ``calmar`` (CAGR / |max drawdown|, full period),
    ``max_drawdown`` (negative), ``max_dd_days`` (longest underwater spell, peak to recovery or to
    the last date, calendar days), ``current_drawdown``, ``ulcer_index`` (Martin 1987, RMS of
    drawdowns, as a fraction), ``omega`` (Keating-Shadwick at threshold 0: sum of gains / sum of
    losses), ``skew``, ``kurtosis`` (excess, bias-corrected), ``best_day``, ``worst_day``,
    ``pct_up_days`` (fraction of positive returns), ``var95`` / ``cvar95`` (1-period historical,
    positive losses), ``tail_ratio`` (|p95| / |p5|), ``gain_to_pain`` (Schwager: sum of monthly
    returns / |sum of negative monthly returns|), ``autocorr1`` (lag-1 autocorrelation).

    With ``benchmark`` (closes aligned on common dates; returns over identical intervals):
    ``beta``, ``alpha`` (annualised Jensen alpha: (mean excess asset - beta x mean excess bench)
    x ppy), ``correlation``, ``r2``, ``tracking_error`` (std of active returns, annualised),
    ``information_ratio`` (annualised mean active return / tracking error), ``up_capture`` /
    ``down_capture`` (Morningstar-style ratio of geometric mean returns in periods where the
    benchmark is up / down, on the aligned return frequency), ``bench_cagr``, ``bench_vol``,
    ``bench_sharpe``, ``bench_max_drawdown`` (benchmark over the common dates).
    """
    try:
        c = _prep(close)
        out = _core_stats(c, rf)
        if benchmark is None:
            return jsonable(out)
        out.update({k: None for k in _BENCH_KEYS})
        b = _prep(benchmark)
        if len(c) < 3 or len(b) < 3:
            return jsonable(out)
        both = pd.concat({"a": c, "b": b}, axis=1, join="inner").dropna()
        if len(both) < 3:
            return jsonable(out)
        ppy = periods_per_year(both.index)
        rf_p = (1.0 + rf) ** (1.0 / ppy) - 1.0 if rf else 0.0
        rets = both.pct_change().dropna()
        ra, rb = rets["a"].to_numpy(), rets["b"].to_numpy()
        bstats = _core_stats(both["b"], rf)
        out["bench_cagr"], out["bench_vol"] = bstats["cagr"], bstats["vol"]
        out["bench_sharpe"], out["bench_max_drawdown"] = bstats["sharpe"], bstats["max_drawdown"]
        if len(ra) >= 3:
            var_b = float(np.var(rb, ddof=1))
            sa = _std(ra)
            if var_b > 1e-14:
                cov = float(np.cov(ra, rb, ddof=1)[0, 1])
                beta = cov / var_b
                out["beta"] = beta
                out["alpha"] = ((ra.mean() - rf_p) - beta * (rb.mean() - rf_p)) * ppy
                if sa is not None:
                    rho = cov / (sa * math.sqrt(var_b))
                    out["correlation"] = rho
                    out["r2"] = rho * rho
            active = ra - rb
            te = _std(active)
            if te is not None:
                out["tracking_error"] = te * math.sqrt(ppy)
                out["information_ratio"] = active.mean() * ppy / out["tracking_error"]
            elif len(active) >= 2:
                out["tracking_error"] = 0.0
            up, dn = rb > 0, rb < 0

            def geo(x):
                return float(np.exp(np.mean(np.log1p(x))) - 1.0) if x.size else None

            if up.any():
                ga, gb = geo(ra[up]), geo(rb[up])
                out["up_capture"] = ga / gb if gb else None
            if dn.any():
                ga, gb = geo(ra[dn]), geo(rb[dn])
                out["down_capture"] = ga / gb if gb else None
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001 - never raise from a result function
        out = {k: None for k in _STAT_KEYS + (_BENCH_KEYS if benchmark is not None else [])}
        out["error"] = str(exc)
        return jsonable(out)


# --------------------------------------------------------------------------- drawdowns
def drawdowns(close, top: int = 5) -> dict:
    """Underwater curve and the deepest drawdown episodes.

    Returns keys: ``underwater`` (ser of close / running max - 1, <= 0) and ``table``: list of the
    ``top`` deepest non-overlapping episodes, deepest first, each {"peak", "trough", "recovery"
    (ISO or None if not yet recovered), "depth" (negative fraction), "days_to_trough",
    "days_to_recover" (int or None), "length" (peak to recovery, or to the last date when not
    recovered), "length_bars", "recovered"}. Day counts are calendar days.
    """
    c = _prep(close)
    uw = c / c.cummax() - 1.0
    if len(c) < 2:
        return jsonable({"underwater": ser(uw), "table": []})
    eps = sorted(_episodes(c), key=lambda e: e["depth"])[: max(int(top), 0)]
    return jsonable({"underwater": ser(uw), "table": eps})


# --------------------------------------------------------------------------- rolling
def rolling_metrics(close, benchmark=None, window: int = 63) -> dict:
    """Rolling-window metrics on simple returns.

    Returns keys: ``window``; ``vol`` (annualised rolling std), ``sharpe`` (rolling mean / std x
    sqrt(ppy), rf = 0), ``return`` (cumulative return over the window: close / close ``window``
    bars earlier - 1), ``beta`` and ``correlation`` (rolling OLS beta / Pearson correlation versus
    the benchmark on common dates; empty ser without a benchmark). All are ser dicts with the
    warm-up period dropped.
    """
    w = max(int(window), 2)
    empty = {"t": [], "v": []}
    out = {"window": w, "vol": empty, "sharpe": empty, "return": empty, "beta": empty, "correlation": empty}
    c = _prep(close)
    if len(c) <= w:
        return jsonable(out)
    ppy = periods_per_year(c.index)
    r = c.pct_change()
    roll = r.rolling(w, min_periods=w)
    sd = roll.std()
    out["vol"] = ser((sd * math.sqrt(ppy)).dropna())
    sd_pos = sd.where(sd > 1e-14)
    out["sharpe"] = ser((roll.mean() / sd_pos * math.sqrt(ppy)).dropna())
    out["return"] = ser((c / c.shift(w) - 1.0).dropna())
    if benchmark is not None:
        b = _prep(benchmark)
        both = pd.concat({"a": c, "b": b}, axis=1, join="inner").dropna()
        if len(both) > w:
            rets = both.pct_change()
            ra, rb = rets["a"], rets["b"]
            var_b = rb.rolling(w, min_periods=w).var()
            beta = ra.rolling(w, min_periods=w).cov(rb) / var_b.where(var_b > 1e-14)
            corr = ra.rolling(w, min_periods=w).corr(rb)
            out["beta"] = ser(beta.replace([np.inf, -np.inf], np.nan).dropna())
            out["correlation"] = ser(corr.replace([np.inf, -np.inf], np.nan).dropna())
    return jsonable(out)


# --------------------------------------------------------------------------- calendar returns
def monthly_returns(close) -> dict:
    """Calendar-month return matrix and month-of-year seasonality.

    Monthly return = month-end close / previous month-end close - 1; the first month is measured
    from the first close and the last month runs to the last close (both may be partial).
    ``year_total`` compounds the year (year-end close / previous year-end close - 1, first year
    from the first close). ``seasonality`` uses complete months only (the first month and an
    unfinished last month are excluded).

    Returns keys: ``years`` (ints, ascending), ``months`` (["Jan".."Dec"]), ``matrix`` (one list
    of 12 fractions|None per year), ``year_total`` (fraction|None per year), ``seasonality``
    ([{"month", "mean", "median", "hit_rate" (fraction of months > 0), "n"}] for Jan..Dec).
    """
    c = _prep(close)
    empty_seas = [{"month": m, "mean": None, "median": None, "hit_rate": None, "n": 0} for m in MONTHS]
    if len(c) < 2:
        return jsonable({"years": [], "months": MONTHS, "matrix": [], "year_total": [], "seasonality": empty_seas})
    mret = _month_returns(c)
    m = mret
    y = c.resample("YE").last().dropna()
    yprev = y.shift(1)
    yprev.iloc[0] = c.iloc[0]
    yret = y / yprev - 1.0
    years = sorted({int(t.year) for t in m.index})
    matrix = []
    for yr in years:
        row = [None] * 12
        sub = mret[mret.index.year == yr]
        for t, v in sub.items():
            row[t.month - 1] = clean(v)
        matrix.append(row)
    ytot = {int(t.year): clean(v) for t, v in yret.items()}
    year_total = [ytot.get(yr) for yr in years]
    complete = mret.iloc[1:]
    last_t = c.index[-1]
    if len(complete) and (last_t + pd.offsets.BDay(1)).month == last_t.month:
        complete = complete.iloc[:-1]  # last month not finished
    seas = []
    for k, name in enumerate(MONTHS, start=1):
        v = complete[complete.index.month == k].to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        if v.size:
            seas.append({"month": name, "mean": float(v.mean()), "median": float(np.median(v)),
                         "hit_rate": float((v > 0).mean()), "n": int(v.size)})
        else:
            seas.append({"month": name, "mean": None, "median": None, "hit_rate": None, "n": 0})
    return jsonable({"years": years, "months": MONTHS, "matrix": matrix, "year_total": year_total,
                     "seasonality": seas})


# --------------------------------------------------------------------------- distribution
_Q_LEVELS = {"1%": 0.01, "5%": 0.05, "25%": 0.25, "50%": 0.50, "75%": 0.75, "95%": 0.95, "99%": 0.99}


def return_distribution(close, bins: int = 60, horizon: int = 1) -> dict:
    """Histogram of overlapping ``horizon``-bar simple returns with fitted normal and Student-t.

    The Student-t (df, loc, scale) is fitted by maximum likelihood (L-BFGS-B, analytic gradient;
    the same estimator as scipy.stats.t.fit) on at least 20 returns. Note that
    overlapping returns (horizon > 1) are autocorrelated, so the Jarque-Bera p-value is only
    indicative there.

    Returns keys: ``horizon``, ``n``, ``edges`` (bins + 1), ``counts``, ``density`` (counts /
    (n x bin width)), ``normal_pdf`` {"x", "y"} and ``t_pdf`` {"x", "y"} (200-point grid over the
    histogram range), ``t_df``, ``t_loc``, ``t_scale``, ``mean``, ``std``, ``skew``, ``kurtosis``
    (excess), ``jarque_bera`` {"stat", "p"}, ``quantiles`` {"1%", "5%", "25%", "50%", "75%",
    "95%", "99%"}.
    """
    h = max(int(horizon), 1)
    nb = max(int(bins), 1)
    out = {"horizon": h, "n": 0, "edges": [], "counts": [], "density": [], "normal_pdf": {"x": [], "y": []},
           "t_pdf": {"x": [], "y": []}, "t_df": None, "t_loc": None, "t_scale": None, "mean": None, "std": None,
           "skew": None, "kurtosis": None, "jarque_bera": {"stat": None, "p": None},
           "quantiles": {k: None for k in _Q_LEVELS}}
    c = _prep(close)
    if len(c) <= h:
        return jsonable(out)
    r = (c / c.shift(h) - 1.0).dropna()
    x = r.to_numpy(dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return jsonable(out)
    out["n"] = int(x.size)
    out["mean"] = float(x.mean())
    out["quantiles"] = {k: float(np.quantile(x, q)) for k, q in _Q_LEVELS.items()}
    sd = _std(x)
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-14:
        lo, hi = lo - 1e-3, hi + 1e-3
    counts, edges = np.histogram(x, bins=nb, range=(lo, hi))
    width = np.diff(edges)
    out["edges"], out["counts"] = edges, counts
    out["density"] = counts / (x.size * width)
    if sd is None:
        out["std"] = 0.0 if x.size >= 2 else None
        return jsonable(out)
    out["std"] = sd
    rs = pd.Series(x)
    if x.size >= 3:
        out["skew"] = float(rs.skew())
    if x.size >= 4:
        out["kurtosis"] = float(rs.kurt())
    grid = np.linspace(edges[0], edges[-1], 200)
    out["normal_pdf"] = {"x": grid, "y": stats.norm.pdf(grid, out["mean"], sd)}
    if x.size >= 8:
        jb = stats.jarque_bera(x)
        out["jarque_bera"] = {"stat": float(jb.statistic), "p": float(jb.pvalue)}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = _t_mle(x)
    if fit is not None:
        df_, loc, scale = fit
        out["t_df"], out["t_loc"], out["t_scale"] = df_, loc, scale
        out["t_pdf"] = {"x": grid, "y": stats.t.pdf(grid, df_, loc, scale)}
    return jsonable(out)
