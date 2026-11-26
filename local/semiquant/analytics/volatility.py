"""Volatility: realized-volatility estimators, volatility cone, EWMA (RiskMetrics) and
GARCH-family forecasts (``arch`` package).

``realized_vol`` and ``ewma_vol`` return **pandas Series** (annualised fractions, aligned to the
input dates). The other public functions return JSON-ready dicts and never raise.
Annualisation uses ``periods_per_year`` of the input index (252 for daily bars).
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy.special import gammaln

from ._util import iso, jsonable, pct_rank, periods_per_year, ser
from .performance import _prep
from .technicals import _frame

__all__ = ["realized_vol", "realized_vol_summary", "vol_cone", "ewma_vol", "garch", "vol_summary", "METHODS"]

METHODS = ["close_to_close", "parkinson", "garman_klass", "rogers_satchell", "yang_zhang"]
_LN2 = math.log(2.0)


def _has_ohlc(df) -> bool:
    if not isinstance(df, pd.DataFrame):
        return False
    cols = {str(c).lower() for c in df.columns}
    return {"open", "high", "low", "close"} <= cols


def _ppy(idx: pd.Index) -> float:
    return periods_per_year(idx)


# --------------------------------------------------------------------------- realized vol
def realized_vol(df, window: int = 21, method: str = "yang_zhang") -> pd.Series:
    """Rolling realized volatility, annualised (Series named ``method``).

    Methods (n = ``window`` bars, variances averaged over the window, then x ppy):
    * ``close_to_close``: sample std (ddof 1) of log close-to-close returns.
    * ``parkinson`` (Parkinson 1980): sigma^2 = mean(ln(H/L)^2) / (4 ln 2).
    * ``garman_klass`` (Garman & Klass 1980): mean(0.5 ln(H/L)^2 - (2 ln 2 - 1) ln(C/O)^2).
    * ``rogers_satchell`` (Rogers & Satchell 1991): mean(ln(H/C) ln(H/O) + ln(L/C) ln(L/O)).
    * ``yang_zhang`` (Yang & Zhang 2000): var(overnight ln(O/C_prev)) + k var(open-to-close ln(C/O))
      + (1 - k) RS, with k = 0.34 / (1.34 + (n + 1) / (n - 1)).
    A close Series (or a frame without open/high/low) always uses close_to_close.
    """
    return _rv(_frame(df), int(window), method, _has_ohlc(df))


def _rv(d: pd.DataFrame, window: int, method: str, ohlc: bool) -> pd.Series:
    n = max(int(window), 2)
    method = (method or "yang_zhang").lower()
    if len(d) == 0:
        return pd.Series(dtype=float, name=method)
    ppy = _ppy(d.index)
    o, h, l, c = (np.log(d[k]) for k in ("open", "high", "low", "close"))
    if method == "close_to_close" or not ohlc or method not in METHODS:
        var = c.diff().rolling(n, min_periods=n).var(ddof=1)
    elif method == "parkinson":
        var = ((h - l) ** 2).rolling(n, min_periods=n).mean() / (4.0 * _LN2)
    elif method == "garman_klass":
        var = (0.5 * (h - l) ** 2 - (2.0 * _LN2 - 1.0) * (c - o) ** 2).rolling(n, min_periods=n).mean()
    elif method == "rogers_satchell":
        var = ((h - c) * (h - o) + (l - c) * (l - o)).rolling(n, min_periods=n).mean()
    else:  # yang_zhang
        k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))
        overnight = o - c.shift(1)
        oc = c - o
        rs = ((h - c) * (h - o) + (l - c) * (l - o)).where(overnight.notna())
        var = (overnight.rolling(n, min_periods=n).var(ddof=1) + k * oc.where(overnight.notna())
               .rolling(n, min_periods=n).var(ddof=1) + (1.0 - k) * rs.rolling(n, min_periods=n).mean())
    vol = np.sqrt(var.clip(lower=0.0) * ppy)
    return vol.rename(method if method in METHODS else "close_to_close")


def realized_vol_summary(df, windows=(10, 21, 63, 126, 252)) -> dict:
    """Latest realized vol for every estimator and window.

    Returns keys: ``windows``, ``methods``, ``table`` ({method: {str(window): latest annualised
    vol|None}}), ``series`` ({method: ser of the 21-bar estimator}), ``ohlc`` (False when only
    closes were available: range-based estimators are then None / empty).
    """
    wins = [int(w) for w in windows]
    out = {"windows": wins, "methods": METHODS, "table": {m: {str(w): None for w in wins} for m in METHODS},
           "series": {m: {"t": [], "v": []} for m in METHODS}, "ohlc": _has_ohlc(df)}
    try:
        d = _frame(df)
        for m in METHODS:
            if m != "close_to_close" and not out["ohlc"]:
                continue
            for w in wins:
                s = _rv(d, w, m, out["ohlc"])
                out["table"][m][str(w)] = s.iloc[-1] if len(s) else None
            out["series"][m] = ser(_rv(d, 21, m, out["ohlc"]).dropna())
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return jsonable(out)


def vol_cone(df, windows=(10, 21, 42, 63, 126, 252), method: str = "close_to_close") -> dict:
    """Volatility cone (Burghardt & Lane 1990) from overlapping rolling windows over the history.

    Returns keys (lists aligned with ``windows``): ``windows``, ``min``, ``p10``, ``p25``,
    ``median``, ``p75``, ``p90``, ``max``, ``current`` (latest value), ``percentile_now``
    (percentile rank 0-100 of the latest value within that window's history), ``method``.
    """
    wins = [int(w) for w in windows]
    keys = ["min", "p10", "p25", "median", "p75", "p90", "max", "current", "percentile_now"]
    out = {"windows": wins, "method": method, **{k: [] for k in keys}}
    qs = {"min": 0.0, "p10": 0.10, "p25": 0.25, "median": 0.5, "p75": 0.75, "p90": 0.90, "max": 1.0}
    try:
        d, ohlc = _frame(df), _has_ohlc(df)
    except Exception:  # noqa: BLE001
        d, ohlc = pd.DataFrame(), False
    for w in wins:
        try:
            s = _rv(d, w, method, ohlc).dropna().to_numpy()
        except Exception:  # noqa: BLE001
            s = np.array([])
        if s.size == 0:
            for k in keys:
                out[k].append(None)
            continue
        for k, q in qs.items():
            out[k].append(float(np.quantile(s, q)))
        out["current"].append(float(s[-1]))
        out["percentile_now"].append(pct_rank(s, s[-1]))
    return jsonable(out)


def ewma_vol(close, lam: float = 0.94) -> pd.Series:
    """RiskMetrics EWMA volatility (J.P. Morgan 1996), annualised Series.

    sigma^2_t = lambda sigma^2_{t-1} + (1 - lambda) r_t^2 on zero-mean daily log returns, computed
    as the normalised exponentially weighted mean of r^2 (pandas ``adjust=True``, so there is no
    seed). The value at date t uses returns up to and including t, i.e. it is the forecast for
    the next bar. First 10 returns are masked."""
    c = _prep(close)
    if len(c) < 2:
        return pd.Series(dtype=float, name="ewma")
    r = np.log(c).diff().dropna()
    var = (r ** 2).ewm(alpha=1.0 - float(lam), adjust=True, min_periods=min(10, len(r))).mean()
    return np.sqrt(var * _ppy(c.index)).rename("ewma")


# --------------------------------------------------------------------------- GARCH
_GARCH_KEYS = ["model", "dist", "params", "persistence", "half_life_days", "long_run_vol", "current_vol",
               "cond_vol", "forecast", "aic", "bic", "loglik", "ljung_box_sq_p", "n", "converged", "start", "end"]


def _fit_arch(x_pct: pd.Series, model: str = "gjr", dist: str = "t"):
    """Fit a constant-mean GARCH(1,1) / GJR-GARCH(1,1) / EGARCH(1,1) with ``arch`` on returns
    already scaled to percent. Returns the ARCHModelResult."""
    from arch import arch_model

    model = (model or "gjr").lower()
    spec = {"garch": dict(vol="GARCH", p=1, o=0, q=1), "gjr": dict(vol="GARCH", p=1, o=1, q=1),
            "egarch": dict(vol="EGARCH", p=1, o=1, q=1)}
    if model not in spec:
        raise ValueError(f"unknown model {model!r} (garch, gjr, egarch)")
    dist = {"normal": "normal", "gaussian": "normal", "t": "t", "studentst": "t", "skewt": "skewt",
            "skewstudent": "skewt", "ged": "ged"}.get((dist or "t").lower())
    if dist is None:
        raise ValueError("unknown dist (normal, t, skewt, ged)")
    am = arch_model(x_pct, mean="Constant", dist=dist, rescale=False, **spec[model])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return am.fit(disp="off", show_warning=False)


def _persistence(res, model: str) -> float | None:
    p = res.params
    if model == "egarch":
        return float(p.get("beta[1]", np.nan))
    return float(p.get("alpha[1]", 0.0) + p.get("beta[1]", 0.0) + 0.5 * p.get("gamma[1]", 0.0))


def _dist_name(res) -> str:
    return type(res.model.distribution).__name__


def _abs_moment(res) -> float:
    """E|z| of the fitted standardised innovations (exact for Student-t; the normal value
    sqrt(2/pi) is used for the other distributions)."""
    nu = res.params.get("nu")
    if _dist_name(res) == "StudentsT" and nu is not None and np.isfinite(nu) and nu > 2:
        return float(2.0 * math.sqrt(nu - 2.0) * math.exp(gammaln((nu + 1) / 2) - gammaln(nu / 2))
                     / ((nu - 1.0) * math.sqrt(math.pi)))
    return math.sqrt(2.0 / math.pi)


def _innovation_rng(res, seed: int = 0):
    """Seeded sampler of the fitted standardised innovations (for simulation forecasts)."""
    g = np.random.default_rng(seed)
    name = _dist_name(res)
    if name == "Normal":
        return lambda size: g.standard_normal(size)
    if name == "StudentsT":
        nu = float(res.params["nu"])
        return lambda size: g.standard_t(nu, size) * math.sqrt((nu - 2.0) / nu)
    dist = res.model.distribution
    k = int(dist.num_params)
    return type(dist)(seed=g).simulate(res.params.iloc[-k:].to_numpy())


def _variance_forecast(res, model: str, horizon: int, seed: int = 0) -> np.ndarray:
    """Variance forecasts (percent^2) for 1..horizon steps after the last observation."""
    if model == "egarch" and horizon > 1:
        f = res.forecast(horizon=horizon, method="simulation", simulations=1000, reindex=False,
                         rng=_innovation_rng(res, seed))
    else:
        f = res.forecast(horizon=horizon, reindex=False)
    return np.asarray(f.variance.iloc[-1].to_numpy(), dtype=float)


def garch(close, model: str = "gjr", dist: str = "t", horizon: int = 21, years: int = 10) -> dict:
    """GARCH-family volatility model fitted with the ``arch`` package (Sheppard) on 100 x daily
    log returns over the last ``years`` years, constant mean, (1,1) orders.

    Models: "garch" (Bollerslev 1986), "gjr" (Glosten-Jagannathan-Runkle 1993), "egarch" (Nelson
    1991); dist "t" (Student-t), "normal", "skewt", "ged".

    Returns keys: ``model``, ``dist``, ``params`` (arch names: mu, omega, alpha[1], gamma[1],
    beta[1], nu ...; on the percent scale), ``persistence`` (alpha + beta + gamma/2 for GJR,
    alpha + beta for GARCH, beta for EGARCH), ``half_life_days`` (ln 0.5 / ln persistence),
    ``long_run_vol`` (annualised unconditional vol; for EGARCH exp of the unconditional mean
    log-variance, an approximation), ``current_vol`` (one-step-ahead forecast, annualised),
    ``cond_vol`` (ser of the in-sample conditional vol, annualised), ``forecast`` {"days":
    [1..h], "vol": [annualised vol of each future day], "avg_vol": annualised vol over the next h
    days (sqrt of the mean variance)}, ``aic``, ``bic``, ``loglik`` (on the percent scale),
    ``ljung_box_sq_p`` (Ljung-Box p-value, lag 10, squared standardised residuals: small values
    mean ARCH effects remain), ``n``, ``converged``, ``start``, ``end``. EGARCH multi-step
    forecasts are simulated (1,000 paths, fixed seed). On failure: {"error": message} plus the
    same keys set to None.
    """
    model = (model or "gjr").lower()
    try:
        c = _prep(close)
        if len(c) and years:
            c = c[c.index >= c.index[-1] - pd.DateOffset(years=int(years))]
        r = (np.log(c).diff().dropna() * 100.0)
        if len(r) < 100:
            raise ValueError("insufficient history (need at least 100 returns)")
        if float(r.std()) < 1e-8:
            raise ValueError("zero variance")
        ppy = _ppy(c.index)
        res = _fit_arch(r, model, dist)
        p = res.params
        if not np.all(np.isfinite(p.to_numpy())):
            raise ValueError("non-finite parameter estimates")
        pers = _persistence(res, model)
        half = math.log(0.5) / math.log(pers) if pers is not None and 0 < pers < 1 else None
        if model == "egarch":
            beta = p.get("beta[1]", np.nan)
            mlog = (p["omega"] + p.get("alpha[1]", 0.0) * (_abs_moment(res) - math.sqrt(2 / math.pi))) / (1 - beta) \
                if beta < 1 else np.nan
            lr = math.sqrt(math.exp(mlog)) if np.isfinite(mlog) else None
        else:
            lr = math.sqrt(p["omega"] / (1.0 - pers)) if pers is not None and pers < 1 else None
        h = max(int(horizon), 1)
        fv = _variance_forecast(res, model, h)
        scale = math.sqrt(ppy) / 100.0
        cv = res.conditional_volatility * scale
        std_resid = (res.resid / res.conditional_volatility).dropna().to_numpy()
        lb_p = None
        try:
            from statsmodels.stats.diagnostic import acorr_ljungbox
            lb_p = float(acorr_ljungbox(std_resid ** 2, lags=[10])["lb_pvalue"].iloc[0])
        except Exception:  # noqa: BLE001
            pass
        out = {
            "model": model, "dist": dist, "params": {k: float(v) for k, v in p.items()},
            "persistence": pers, "half_life_days": half,
            "long_run_vol": lr * scale if lr is not None else None,
            "current_vol": math.sqrt(fv[0]) * scale,
            "cond_vol": ser(cv.dropna()),
            "forecast": {"days": list(range(1, h + 1)), "vol": np.sqrt(fv) * scale,
                         "avg_vol": math.sqrt(float(np.mean(fv))) * scale},
            "aic": float(res.aic), "bic": float(res.bic), "loglik": float(res.loglikelihood),
            "ljung_box_sq_p": lb_p, "n": int(res.nobs), "converged": bool(res.convergence_flag == 0),
            "start": iso(r.index[0]), "end": iso(r.index[-1]),
        }
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out = {k: None for k in _GARCH_KEYS}
        out.update({"model": model, "dist": dist, "error": str(exc)})
        return jsonable(out)


# --------------------------------------------------------------------------- summary
def vol_summary(df, atm_iv: float | None = None) -> dict:
    """Headline volatility numbers (annualised fractions).

    Returns keys: ``rv_21d_yz`` (21-bar Yang-Zhang; close-to-close if only closes are given),
    ``rv_63d_cc``, ``ewma`` (RiskMetrics 0.94), ``garch_avg_21d`` (GJR-GARCH(1,1)-t average vol
    over the next 21 days), ``rv_percentile_1y`` / ``rv_percentile_5y`` (percentile rank 0-100 of
    the current 21-bar Yang-Zhang vol within its last 252 / 1260 values), ``atm_iv`` (as given,
    a fraction, e.g. 0.45), ``vrp`` (atm_iv - rv_21d_yz), ``iv_rv_ratio`` (atm_iv / rv_21d_yz).
    """
    keys = ["rv_21d_yz", "rv_63d_cc", "ewma", "garch_avg_21d", "rv_percentile_1y", "rv_percentile_5y", "atm_iv",
            "vrp", "iv_rv_ratio"]
    out = {k: None for k in keys}
    iv = None
    try:
        iv = float(atm_iv) if atm_iv is not None and np.isfinite(float(atm_iv)) else None
    except (TypeError, ValueError):
        iv = None
    out["atm_iv"] = iv
    try:
        yz = realized_vol(df, 21, "yang_zhang").dropna()
        if len(yz):
            cur = float(yz.iloc[-1])
            out["rv_21d_yz"] = cur
            out["rv_percentile_1y"] = pct_rank(yz.iloc[-252:].to_numpy(), cur)
            out["rv_percentile_5y"] = pct_rank(yz.iloc[-1260:].to_numpy(), cur)
        cc = realized_vol(df, 63, "close_to_close").dropna()
        if len(cc):
            out["rv_63d_cc"] = float(cc.iloc[-1])
        ew = ewma_vol(df).dropna()
        if len(ew):
            out["ewma"] = float(ew.iloc[-1])
        g = garch(df, "gjr", "t", 21)
        out["garch_avg_21d"] = (g.get("forecast") or {}).get("avg_vol")
        if iv is not None and out["rv_21d_yz"]:
            out["vrp"] = iv - out["rv_21d_yz"]
            out["iv_rv_ratio"] = iv / out["rv_21d_yz"]
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return jsonable(out)
