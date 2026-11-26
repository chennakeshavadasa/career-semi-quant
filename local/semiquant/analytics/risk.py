"""Risk: Value-at-Risk / Expected Shortfall (six methods), VaR backtests (Kupiec,
Christoffersen, Basel traffic light), historical stress windows, hypothetical factor shocks and
a tail-risk summary.

Inputs: ``returns`` are daily SIMPLE returns (fractions) indexed by date; ``close`` arguments are
close Series / OHLCV frames. VaR and ES are reported as POSITIVE fractions of value lost (simple
returns). Every public function returns a JSON-ready dict and never raises.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import xlogy

from ..universe import STRESS_WINDOWS
from ._util import clean, iso, jsonable
from .performance import _naive_index, _on_or_before, _prep, _t_mle

__all__ = ["var_es", "var_backtest", "stress_test", "hypothetical_shocks", "tail_risk_summary", "VAR_METHODS",
           "DEFAULT_SHOCKS"]

VAR_METHODS = ["historical", "normal", "cornish_fisher", "student_t", "evt", "filtered_hs"]


def _returns(returns) -> pd.Series:
    """Clean simple-return Series: numeric, finite, > -1, sorted unique tz-naive index."""
    if returns is None:
        return pd.Series(dtype=float)
    try:
        s = pd.to_numeric(pd.Series(returns), errors="coerce")
        if isinstance(s.index, pd.DatetimeIndex) or len(s) == 0:
            s.index = _naive_index(s.index) if len(s) else s.index
        v = s.to_numpy(dtype=float)
        s = s[np.isfinite(v) & (v > -1.0)]
        if s.index.has_duplicates or not s.index.is_monotonic_increasing:
            s = s[~s.index.duplicated(keep="last")].sort_index()
        return s.astype(float)
    except Exception:  # noqa: BLE001
        return pd.Series(dtype=float)


def _hist_var_es(x: np.ndarray, level: float) -> tuple[float | None, float | None]:
    """Historical VaR (-quantile) and ES (-mean of returns at or below the quantile)."""
    x = x[np.isfinite(x)]
    if x.size < 10:
        return None, None
    q = float(np.quantile(x, 1.0 - level))
    tail = x[x <= q]
    return -q, float(-tail.mean()) if tail.size else -q


def _cf_var_es(mu, sd, S, K, level) -> tuple[float, float]:
    """Cornish-Fisher VaR (Zangari 1996) and the matching ES obtained by integrating the
    Cornish-Fisher quantile function over the tail (Boudt, Peterson & Croux 2008): with
    M_k = int_{-inf}^{z} u^k phi(u) du, E[Z_cf | U <= z] = (M1 + S/6 (M2 - M0) + K/24 (M3 - 3 M1)
    - S^2/36 (2 M3 - 5 M1)) / p."""
    p = 1.0 - level
    z = stats.norm.ppf(p)
    zcf = z + (z * z - 1) * S / 6 + (z ** 3 - 3 * z) * K / 24 - (2 * z ** 3 - 5 * z) * S * S / 36
    phi = stats.norm.pdf(z)
    M0, M1, M2, M3 = p, -phi, p - z * phi, -(z * z + 2) * phi
    ez = (M1 + S / 6 * (M2 - M0) + K / 24 * (M3 - 3 * M1) - S * S / 36 * (2 * M3 - 5 * M1)) / p
    return -(mu + sd * zcf), -(mu + sd * ez)


def _gpd_fit(r: np.ndarray, q_threshold: float = 0.90) -> dict | None:
    """Peaks-over-threshold: GPD fitted (MLE, scipy genpareto, floc=0) to losses above the
    ``q_threshold`` quantile of losses (losses = -simple returns)."""
    L = -r[np.isfinite(r)]
    if L.size < 100:
        return None
    u = float(np.quantile(L, q_threshold))
    y = L[L > u] - u
    if y.size < 10 or float(np.std(y)) <= 0:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        xi, _, beta = stats.genpareto.fit(y, floc=0)
    if not (np.isfinite(xi) and np.isfinite(beta) and beta > 0):
        return None
    return {"xi": float(xi), "beta": float(beta), "threshold": u, "n_exceed": int(y.size), "n": int(L.size)}


def _evt_var_es(g: dict, level: float) -> tuple[float | None, float | None]:
    """McNeil & Frey (2000) closed forms: VaR = u + beta/xi (((n/N_u)(1 - level))^-xi - 1),
    ES = (VaR + beta - xi u) / (1 - xi) (xi < 1); xi -> 0 uses the exponential limit."""
    xi, beta, u, nu, n = g["xi"], g["beta"], g["threshold"], g["n_exceed"], g["n"]
    tail = n / nu * (1.0 - level)
    if tail >= 1.0:  # level below the threshold's own level: outside the POT model
        return None, None
    if abs(xi) < 1e-8:
        var = u - beta * math.log(tail)
    else:
        var = u + beta / xi * (tail ** (-xi) - 1.0)
    es = (var + beta - xi * u) / (1.0 - xi) if xi < 1 else None
    return var, es


def _fhs(x_log: pd.Series, levels, horizons, n_sims: int = 10000, seed: int = 0) -> dict:
    """Filtered historical simulation (Barone-Adesi, Giannopoulos & Vosper 1999) on a
    GJR-GARCH(1,1)-t fitted to 100 x daily log returns: 1-day losses use mu + sigma_{T+1} z_t
    over all standardised residuals z_t; h-day losses bootstrap the residuals through the GJR
    variance recursion (``n_sims`` paths, fixed seed)."""
    from .volatility import _fit_arch

    res = _fit_arch(x_log * 100.0, "gjr", "t")
    p = res.params
    mu, om, a, g, b = (float(p.get(k, 0.0)) for k in ("mu", "omega", "alpha[1]", "gamma[1]", "beta[1]"))
    z = (res.resid / res.conditional_volatility).dropna().to_numpy()
    z = z[np.isfinite(z)]
    s2 = float(res.forecast(horizon=1, reindex=False).variance.iloc[-1, 0])
    out = {}
    rng = np.random.default_rng(seed)
    for h in horizons:
        if h == 1:
            sims = np.expm1((mu + math.sqrt(s2) * z) / 100.0)
        else:
            var_t = np.full(n_sims, s2)
            tot = np.zeros(n_sims)
            for _ in range(int(h)):
                eps = np.sqrt(var_t) * z[rng.integers(0, z.size, n_sims)]
                tot += mu + eps
                var_t = om + (a + g * (eps < 0)) * eps * eps + b * var_t
            sims = np.expm1(tot / 100.0)
        for lv in levels:
            out[(lv, h)] = _hist_var_es(sims, lv)
    out["sigma_next"] = math.sqrt(s2) / 100.0
    return out


# --------------------------------------------------------------------------- VaR / ES
def var_es(returns: pd.Series, levels=(0.95, 0.99), horizons=(1, 10)) -> dict:
    """Value-at-Risk and Expected Shortfall by six methods, as positive loss fractions.

    * ``historical``: empirical quantile of daily simple returns; for h > 1, of overlapping h-day
      returns exp(sum of h daily log returns) - 1.
    * ``normal``: VaR = -(mu + sigma z_p), ES = -(mu - sigma phi(z_p)/p), p = 1 - level.
    * ``cornish_fisher``: modified VaR (Zangari 1996) with sample skew / excess kurtosis and the
      matching modified ES (Boudt, Peterson & Croux 2008).
    * ``student_t``: Student-t fitted by MLE (df, loc, scale; ``performance._t_mle``); closed-form ES.
    * ``evt``: GPD peaks-over-threshold on losses above their 90th percentile (scipy genpareto,
      floc=0) with the McNeil-Frey closed-form VaR / ES.
    * ``filtered_hs``: GJR-GARCH(1,1)-t standardised residuals x next-day forecast vol
      (Barone-Adesi et al. 1999); h-day by bootstrapping residuals through the GARCH recursion.
    Parametric methods (normal, cornish_fisher, student_t, evt) are computed for one day from
    daily simple returns (mean included) and scaled by sqrt(h).

    Returns keys: ``levels``, ``horizons``, ``observations``, ``methods``, ``table``
    ([{"method", "level", "horizon", "var", "es"}], methods x levels x horizons), ``evt`` {"xi",
    "beta", "threshold" (loss threshold, fraction), "n_exceed"}, ``fhs_vol_next`` (annualised
    next-day GARCH vol used by filtered_hs).
    """
    lv = [float(v) for v in levels]
    hz = [max(int(h), 1) for h in horizons]
    r = _returns(returns)
    x = r.to_numpy(dtype=float)
    n = int(x.size)
    res: dict[tuple[str, float, int], tuple] = {}
    evt_info = {"xi": None, "beta": None, "threshold": None, "n_exceed": None}
    fhs_vol = None
    try:
        xl = np.log1p(x)
        for h in hz:
            if h == 1:
                sample = x
            elif n >= h:
                sample = np.expm1(np.convolve(xl, np.ones(h), mode="valid"))
            else:
                sample = np.array([])
            for v in lv:
                res[("historical", v, h)] = _hist_var_es(sample, v)
        sd = float(np.std(x, ddof=1)) if n >= 2 else 0.0
        if n >= 10 and sd > 1e-12:
            mu = float(x.mean())
            S = float(pd.Series(x).skew())
            K = float(pd.Series(x).kurt())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tfit = _t_mle(x)
            gpd = _gpd_fit(x)
            if gpd:
                evt_info = {k: gpd[k] for k in ("xi", "beta", "threshold", "n_exceed")}
            for v in lv:
                p = 1.0 - v
                z = stats.norm.ppf(p)
                one = {
                    "normal": (-(mu + sd * z), -(mu - sd * stats.norm.pdf(z) / p)),
                    "cornish_fisher": _cf_var_es(mu, sd, S, K, v),
                }
                if tfit is not None and np.isfinite(tfit[0]) and tfit[2] > 0:
                    nu, loc, sc = tfit
                    q = stats.t.ppf(p, nu)
                    es = -(loc - sc * (nu + q * q) / (nu - 1.0) * stats.t.pdf(q, nu) / p) if nu > 1 else None
                    one["student_t"] = (-(loc + sc * q), es)
                else:
                    one["student_t"] = (None, None)
                one["evt"] = _evt_var_es(gpd, v) if gpd else (None, None)
                for m, (vv, ee) in one.items():
                    for h in hz:
                        f = math.sqrt(h)
                        res[(m, v, h)] = (vv * f if vv is not None else None, ee * f if ee is not None else None)
        if n >= 250 and sd > 1e-12:
            try:
                f = _fhs(pd.Series(np.log1p(x), index=r.index), lv, hz)
                fhs_vol = f.pop("sigma_next") * math.sqrt(252)
                for (v, h), val in f.items():
                    res[("filtered_hs", v, h)] = val
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    table = []
    for m in VAR_METHODS:
        for v in lv:
            for h in hz:
                vv, ee = res.get((m, v, h), (None, None))
                table.append({"method": m, "level": v, "horizon": h, "var": vv, "es": ee})
    return jsonable({"levels": lv, "horizons": hz, "observations": n, "methods": VAR_METHODS, "table": table,
                     "evt": evt_info, "fhs_vol_next": fhs_vol})


# --------------------------------------------------------------------------- backtest
def _lr_p(lr: float | None, df: int) -> dict:
    if lr is None or not np.isfinite(lr):
        return {"lr": None, "p": None}
    lr = max(float(lr), 0.0)
    return {"lr": lr, "p": float(stats.chi2.sf(lr, df))}


def _kupiec(x: int, n: int, p: float) -> float | None:
    """Kupiec (1995) proportion-of-failures LR statistic (chi2, 1 df)."""
    if n <= 0:
        return None
    phat = x / n
    return float(-2.0 * (xlogy(n - x, 1 - p) + xlogy(x, p)) + 2.0 * (xlogy(n - x, 1 - phat) + xlogy(x, phat)))


def _christoffersen(hits: np.ndarray) -> float | None:
    """Christoffersen (1998) independence LR statistic (chi2, 1 df) from the first-order Markov
    transition counts of the exception indicator."""
    if hits.size < 2:
        return None
    a, b = hits[:-1].astype(int), hits[1:].astype(int)
    n00 = int(np.sum((a == 0) & (b == 0)))
    n01 = int(np.sum((a == 0) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    n11 = int(np.sum((a == 1) & (b == 1)))
    tot = n00 + n01 + n10 + n11
    pi = (n01 + n11) / tot if tot else 0.0
    pi01 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    l0 = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    l1 = xlogy(n00, 1 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1 - pi11) + xlogy(n11, pi11)
    return float(-2.0 * (l0 - l1))


def _traffic_light(x: int, n: int, p: float) -> str | None:
    """Basel (1996) zones scaled to the sample: green while the binomial CDF of the exception count
    is below 95%, yellow below 99.99%, red otherwise (250 days at 99%: 0-4 / 5-9 / 10+)."""
    if n <= 0:
        return None
    cdf = float(stats.binom.cdf(x, n, p))
    return "green" if cdf < 0.95 else "yellow" if cdf < 0.9999 else "red"


def var_backtest(returns, level: float = 0.99, window: int = 500, method: str = "historical") -> dict:
    """Rolling one-step-ahead VaR backtest.

    VaR for day t uses only returns before t: ``historical`` = empirical quantile of the previous
    ``window`` returns (pandas rolling quantile, linear interpolation); ``normal`` = rolling mean
    and std over ``window``; ``ewma`` = RiskMetrics (lambda 0.94) zero-mean volatility. The test
    sample starts after the first ``window`` returns for every method. An exception is a return
    below -VaR.

    Returns keys: ``level``, ``window``, ``method``, ``n`` (test days), ``exceptions``,
    ``expected`` (n x (1 - level)), ``rate``, ``kupiec`` {"lr", "p"} (unconditional coverage),
    ``christoffersen`` {"lr", "p"} (independence), ``conditional_coverage`` {"lr", "p"} (sum, 2
    df), ``traffic_light`` ("green" | "yellow" | "red"), ``series`` {"t", "ret", "var"} (last 750
    test days, VaR positive), ``exception_dates`` (ISO, all).
    """
    method = (method or "historical").lower()
    level = float(level)
    w = max(int(window), 20)
    out = {"level": level, "window": w, "method": method, "n": 0, "exceptions": None, "expected": None,
           "rate": None, "kupiec": {"lr": None, "p": None}, "christoffersen": {"lr": None, "p": None},
           "conditional_coverage": {"lr": None, "p": None}, "traffic_light": None,
           "series": {"t": [], "ret": [], "var": []}, "exception_dates": []}
    try:
        r = _returns(returns)
        if len(r) < w + 20:
            out["error"] = "insufficient history"
            return jsonable(out)
        p = 1.0 - level
        z = stats.norm.ppf(p)
        if method == "historical":
            var = -r.rolling(w, min_periods=w).quantile(p).shift(1)
        elif method == "normal":
            roll = r.rolling(w, min_periods=w)
            var = -(roll.mean() + roll.std() * z).shift(1)
        elif method == "ewma":
            sig = np.sqrt((r ** 2).ewm(alpha=0.06, adjust=True).mean())
            var = (-sig * z).shift(1)
        else:
            raise ValueError(f"unknown method {method!r} (historical, normal, ewma)")
        test = pd.DataFrame({"ret": r, "var": var}).iloc[w:].dropna()
        n = len(test)
        if n == 0:
            return jsonable(out)
        hits = (test["ret"] < -test["var"]).to_numpy()
        x = int(hits.sum())
        lr_pof = _kupiec(x, n, p)
        lr_ind = _christoffersen(hits)
        out.update({
            "n": n, "exceptions": x, "expected": n * p, "rate": x / n,
            "kupiec": _lr_p(lr_pof, 1), "christoffersen": _lr_p(lr_ind, 1),
            "conditional_coverage": _lr_p(lr_pof + lr_ind if lr_pof is not None and lr_ind is not None else None, 2),
            "traffic_light": _traffic_light(x, n, p),
            "exception_dates": [iso(t) for t in test.index[hits]],
        })
        tail = test.iloc[-750:]
        out["series"] = {"t": [iso(t) for t in tail.index], "ret": tail["ret"].to_numpy(),
                         "var": tail["var"].to_numpy()}
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return jsonable(out)


# --------------------------------------------------------------------------- stress
def _window_stats(s: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> tuple[bool, float | None, float | None]:
    if len(s) < 2 or s.index[0] >= start or s.index[-1] < end:
        return False, None, None
    i0 = int(s.index.searchsorted(start, side="left")) - 1  # last close strictly before start
    hit = _on_or_before(s, end)
    if i0 < 0 or hit is None:
        return False, None, None
    path = s.iloc[i0: int(s.index.searchsorted(end, side="right"))]
    ret = float(path.iloc[-1] / path.iloc[0] - 1.0)
    mdd = float((path / path.cummax() - 1.0).min())
    return True, ret, mdd


def stress_test(close, benchmarks: dict[str, pd.Series] | None = None, windows=STRESS_WINDOWS) -> dict:
    """Historical stress windows replayed on daily closes.

    Each window's return uses the close on the last trading day before ``start`` and the last close
    on or before ``end``; ``max_drawdown`` is the worst peak-to-trough fall along that path. A
    window is ``covered`` when the data has a close before ``start`` and extends to ``end``.

    Returns keys: ``rows`` [{"name", "start", "end", "covered" (bool), "return", "max_drawdown"
    (negative), "bench": {name: return|None}}]; uncovered rows have None values.
    """
    rows = []
    try:
        c = _prep(close)
        bmk = {str(k): _prep(v) for k, v in (benchmarks or {}).items()}
        for name, start, end in windows:
            s, e = pd.Timestamp(start), pd.Timestamp(end)
            cov, ret, mdd = _window_stats(c, s, e)
            bench = {}
            for bn, bs in bmk.items():
                bc, br, _ = _window_stats(bs, s, e)
                bench[bn] = br if (bc and cov) else None
            rows.append({"name": name, "start": iso(s), "end": iso(e), "covered": cov, "return": ret,
                         "max_drawdown": mdd, "bench": bench})
    except Exception as exc:  # noqa: BLE001
        return jsonable({"rows": rows, "error": str(exc)})
    return jsonable({"rows": rows})


# --------------------------------------------------------------------------- hypothetical shocks
DEFAULT_SHOCKS = [
    {"name": "S&P 500 -5%", "factor": "SPY", "shock": -0.05},
    {"name": "S&P 500 -10%", "factor": "SPY", "shock": -0.10},
    {"name": "S&P 500 -20%", "factor": "SPY", "shock": -0.20},
    {"name": "Semis (SOXX) -10%", "factor": "SOXX", "shock": -0.10},
    {"name": "Semis (SOXX) -20%", "factor": "SOXX", "shock": -0.20},
    {"name": "Semis (SOXX) -30%", "factor": "SOXX", "shock": -0.30},
    {"name": "10Y yield +50bp", "factor": "^TNX", "shock": 50.0},
    {"name": "10Y yield +100bp", "factor": "^TNX", "shock": 100.0},
    {"name": "VIX +10 pts", "factor": "^VIX", "shock": 10.0},
    {"name": "USD +5%", "factor": "DX-Y.NYB", "shock": 0.05},
    {"name": "Oil +20%", "factor": "CL=F", "shock": 0.20},
]
_YIELDS = {"^TNX", "^IRX", "^FVX", "^TYX"}


def _factor_unit(ticker: str) -> str:
    t = str(ticker).upper()
    if t in _YIELDS:
        return "bp"
    if t.startswith("^VIX") or t in {"^VXN", "^VVIX", "^MOVE"}:
        return "points"
    return "return"


def _factor_change(level: pd.Series, unit: str) -> pd.Series:
    """Level -> daily change: simple return (undefined when either price <= 0), yield change in
    bp (Yahoo yield indices are quoted in percent, so diff x 100), or index points."""
    if unit == "bp":
        return level.diff() * 100.0
    if unit == "points":
        return level.diff()
    prev = level.shift(1)
    return (level / prev - 1.0).where((prev > 0) & (level > 0))


def hypothetical_shocks(asset_returns: pd.Series, factor_levels: pd.DataFrame, shocks: list[dict] | None = None,
                        years: float = 2.0) -> dict:
    """Linear factor-shock scenarios from single-factor betas.

    For each shock the asset's daily simple returns are regressed (OLS, one factor at a time) on
    the factor's daily change over the last ``years`` (2) years of common dates: returns for
    price factors (SPY, SOXX, DX-Y.NYB, CL=F, ...), change in yield in basis points for ^TNX (and
    other Yahoo yield indices), change in points for ^VIX. impact = beta x shock (a linear
    extrapolation of daily sensitivities). Default shocks: S&P -5/-10/-20%, SOXX -10/-20/-30%,
    10Y +50/+100bp, VIX +10 pts, USD +5%, Oil +20%. Custom shocks: [{"name", "factor" (column
    in factor_levels), "shock" (fraction for price factors, bp for yields, points for VIX)}].
    Shocks whose factor is not in ``factor_levels`` are skipped.

    Returns keys: ``rows`` [{"name", "factor", "shock", "unit", "beta", "r2", "impact", "n"}],
    ``start``, ``end`` (estimation window).
    """
    rows = []
    start = end = None
    try:
        r = _returns(asset_returns)
        fl = factor_levels if isinstance(factor_levels, pd.DataFrame) else pd.DataFrame(factor_levels)
        fl = fl.copy()
        fl.index = _naive_index(fl.index)
        fl = fl[~fl.index.duplicated(keep="last")].sort_index()
        if len(r):
            r = r[r.index >= r.index[-1] - pd.DateOffset(months=int(round(12 * float(years))))]
        cache: dict[str, tuple] = {}
        for sh in (shocks if shocks is not None else DEFAULT_SHOCKS):
            fac = sh.get("factor")
            if fac not in fl.columns:
                continue
            unit = _factor_unit(fac)
            if fac not in cache:
                lv = pd.to_numeric(fl[fac], errors="coerce").reindex(r.index)
                chg = _factor_change(lv, unit)
                both = pd.concat({"y": r, "x": chg}, axis=1).replace([np.inf, -np.inf], np.nan).dropna()
                beta = r2 = None
                if len(both) >= 30:
                    xv, yv = both["x"].to_numpy(), both["y"].to_numpy()
                    vx = float(np.var(xv, ddof=1))
                    if vx > 1e-14:
                        cov = float(np.cov(xv, yv, ddof=1)[0, 1])
                        beta = cov / vx
                        vy = float(np.var(yv, ddof=1))
                        r2 = cov * cov / (vx * vy) if vy > 1e-14 else None
                    if start is None or both.index[0] < pd.Timestamp(start):
                        start = iso(both.index[0])
                    if end is None or both.index[-1] > pd.Timestamp(end):
                        end = iso(both.index[-1])
                cache[fac] = (beta, r2, len(both))
            beta, r2, nobs = cache[fac]
            shock = clean(sh.get("shock"))
            rows.append({"name": sh.get("name", f"{fac} {shock}"), "factor": fac, "shock": shock, "unit": unit,
                         "beta": beta, "r2": r2,
                         "impact": beta * shock if beta is not None and shock is not None else None, "n": nobs})
    except Exception as exc:  # noqa: BLE001
        return jsonable({"rows": rows, "start": start, "end": end, "error": str(exc)})
    return jsonable({"rows": rows, "start": start, "end": end})


# --------------------------------------------------------------------------- tail summary
def tail_risk_summary(close) -> dict:
    """Historical tail-risk snapshot from daily closes (simple returns).

    Returns keys: ``var95_1d``, ``var99_1d`` (positive losses), ``es975_1d`` (mean loss beyond the
    2.5% quantile, the FRTB measure), ``worst_day``, ``worst_week``, ``worst_month`` (worst
    overlapping 1 / 5 / 21-bar returns, negative), ``es_to_vol`` (es975_1d / daily std; 2.34 for a
    normal distribution, larger means fatter tails), ``observations``.
    """
    keys = ["var95_1d", "var99_1d", "es975_1d", "worst_day", "worst_week", "worst_month", "es_to_vol",
            "observations"]
    out = {k: None for k in keys}
    try:
        c = _prep(close)
        if len(c) < 2:
            out["observations"] = 0
            return jsonable(out)
        r = c.pct_change().dropna().to_numpy()
        out["observations"] = int(r.size)
        out["worst_day"] = float(r.min())
        if len(c) > 5:
            out["worst_week"] = float((c / c.shift(5) - 1.0).min())
        if len(c) > 21:
            out["worst_month"] = float((c / c.shift(21) - 1.0).min())
        out["var95_1d"] = _hist_var_es(r, 0.95)[0]
        out["var99_1d"] = _hist_var_es(r, 0.99)[0]
        es = _hist_var_es(r, 0.975)[1]
        out["es975_1d"] = es
        sd = float(np.std(r, ddof=1)) if r.size >= 2 else 0.0
        if es is not None and sd > 1e-14:
            out["es_to_vol"] = es / sd
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return jsonable(out)
