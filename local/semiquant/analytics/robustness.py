"""Crash risk and how much to trust a track record.

* ``asymmetric_risk``: how a stock behaves when the market falls. Downside vs upside beta (Ang, Chen
  & Xing 2006), co-skewness and co-kurtosis (Harvey & Siddique 2000), crash beta (average move on the
  market's worst days relative to the market's), and empirical lower / upper tail dependence: how
  often the stock is in its own worst (best) q-tail on the days the market is.
* ``sharpe_confidence``: is the Sharpe ratio skill or luck? Probabilistic Sharpe Ratio and Minimum
  Track Record Length (Bailey & Lopez de Prado 2012) with the non-normal standard error of the Sharpe
  ratio (Mertens 2002): negative skew and fat tails make the same Sharpe ratio less certain.
* ``drawdown_risk``: drawdown-at-risk and conditional drawdown-at-risk (Chekhlov, Uryasev &
  Zabarankin 2005), pain index and time under water.

All functions take price series (closes), return JSON-ready dicts and never raise on short or
degenerate data (fields become None).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from ._util import TRADING_DAYS, as_close, clean, jsonable

__all__ = ["asymmetric_risk", "sharpe_confidence", "drawdown_risk"]


def _rets(prices, freq: str = "D") -> pd.Series:
    s = as_close(prices)
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]
    if freq.upper().startswith("W") and len(s) > 10:
        s = s.resample("W-FRI").last().dropna()
    return s.pct_change().dropna()


def asymmetric_risk(prices, market, freq: str = "D", tails=(0.05, 0.10)) -> dict:
    """Downside/upside beta, co-skewness, co-kurtosis, crash beta and tail dependence vs ``market``.

    ``freq`` "D" (daily) or "W" (weekly, for listings that close at a different time than the market
    proxy). Downside beta uses the observations where the market return is below its mean, upside beta
    those above (Ang, Chen & Xing). Co-skewness = E[(r-mu)(m-mu_m)^2] / (sd * sd_m^2), co-kurtosis =
    E[(r-mu)(m-mu_m)^3] / (sd * sd_m^3) (standardised; a normal pair with correlation rho has
    co-skewness 0 and co-kurtosis 3 rho). Crash beta = mean stock return / mean market return over the
    market's worst ``tails[0]`` share of periods. Tail dependence lambda_L(q) = P(r <= Q_r(q) | m <=
    Q_m(q)) (independence: q; comonotone: 1); lambda_U likewise for the upper tail.
    """
    r, m = _rets(prices, freq), _rets(market, freq)
    df = pd.concat([r.rename("r"), m.rename("m")], axis=1, join="inner").dropna()
    out = {"freq": "weekly" if freq.upper().startswith("W") else "daily", "n": int(len(df)), "beta": None,
           "downside_beta": None, "upside_beta": None, "beta_asymmetry": None, "coskewness": None,
           "cokurtosis": None, "crash_beta": None, "tail_dependence": []}
    if len(df) < 40:
        return out
    x, y = df["m"].to_numpy(float), df["r"].to_numpy(float)

    def beta(mask):
        if mask.sum() < 15:
            return None
        xv, yv = x[mask], y[mask]
        v = np.var(xv, ddof=1)
        return float(np.cov(yv, xv, ddof=1)[0, 1] / v) if v > 0 else None

    mu_m, mu_r = x.mean(), y.mean()
    sd_m, sd_r = x.std(ddof=1), y.std(ddof=1)
    out["beta"] = beta(np.ones_like(x, bool))
    out["downside_beta"] = beta(x < mu_m)
    out["upside_beta"] = beta(x > mu_m)
    if out["downside_beta"] is not None and out["upside_beta"] is not None:
        out["beta_asymmetry"] = out["downside_beta"] - out["upside_beta"]
    if sd_m > 0 and sd_r > 0:
        dm, dr = x - mu_m, y - mu_r
        out["coskewness"] = float(np.mean(dr * dm ** 2) / (sd_r * sd_m ** 2))
        out["cokurtosis"] = float(np.mean(dr * dm ** 3) / (sd_r * sd_m ** 3))
    q0 = tails[0]
    worst = x <= np.quantile(x, q0)
    if worst.sum() >= 5 and x[worst].mean() != 0:
        out["crash_beta"] = float(y[worst].mean() / x[worst].mean())
        out["crash_avg_stock"] = float(y[worst].mean())
        out["crash_avg_market"] = float(x[worst].mean())
    for q in tails:
        lo_m, lo_r = x <= np.quantile(x, q), y <= np.quantile(y, q)
        hi_m, hi_r = x >= np.quantile(x, 1 - q), y >= np.quantile(y, 1 - q)
        out["tail_dependence"].append({
            "q": q, "independent": q,
            "lower": float((lo_m & lo_r).sum() / lo_m.sum()) if lo_m.sum() else None,
            "upper": float((hi_m & hi_r).sum() / hi_m.sum()) if hi_m.sum() else None,
            "n_tail": int(lo_m.sum())})
    return jsonable(out)


def sharpe_confidence(prices, rf: float = 0.0, benchmark_sharpe: float = 0.0, periods: int = TRADING_DAYS,
                      confidence: float = 0.95) -> dict:
    """Sharpe ratio with its uncertainty, Probabilistic Sharpe Ratio and Minimum Track Record Length.

    Per-period excess returns e_t = r_t - rf/periods; SR = mean(e)/sd(e). With skewness g3 and
    (non-excess) kurtosis g4 of e, the standard error of SR is sqrt((1 - g3 SR + (g4 - 1)/4 SR^2) /
    (n - 1)) (Mertens). PSR(SR*) = Phi((SR - SR*) / se): the probability that the true Sharpe ratio
    exceeds the benchmark SR* (``benchmark_sharpe``, annualised). MinTRL = 1 + (1 - g3 SR + (g4 - 1)/4
    SR^2) (z / (SR - SR*))^2 periods: the history needed for PSR to reach ``confidence`` (None when SR
    <= SR*). Annualised figures scale by sqrt(periods).
    """
    r = _rets(prices)
    n = int(len(r))
    out = {"n": n, "years": n / periods if n else None, "sharpe": None, "se": None, "ci_low": None, "ci_high": None,
           "psr": None, "psr_vs": benchmark_sharpe, "min_track_record_years": None, "skew": None, "kurtosis": None}
    if n < 60:
        return out
    e = r.to_numpy(float) - (rf or 0.0) / periods
    sd = e.std(ddof=1)
    if not sd > 0:
        return out
    sr = e.mean() / sd
    z = (e - e.mean()) / e.std(ddof=0)
    g3, g4 = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    var_term = max(1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr, 1e-12)
    se = math.sqrt(var_term / (n - 1))
    sr_star = benchmark_sharpe / math.sqrt(periods)
    k = math.sqrt(periods)
    zc = norm.ppf(0.5 + confidence / 2)
    out.update(sharpe=sr * k, se=se * k, ci_low=(sr - zc * se) * k, ci_high=(sr + zc * se) * k,
               psr=float(norm.cdf((sr - sr_star) / se)), skew=g3, kurtosis=g4)
    if sr > sr_star:
        z1 = norm.ppf(confidence)
        out["min_track_record_years"] = (1.0 + var_term * (z1 / (sr - sr_star)) ** 2) / periods
    return jsonable(out)


def drawdown_risk(prices, alpha: float = 0.95) -> dict:
    """Drawdown-at-risk (the ``alpha`` quantile of the daily drawdown depth), conditional
    drawdown-at-risk (mean depth beyond it), pain index (mean depth), share of days under water,
    longest and current time under water (trading days)."""
    s = as_close(prices)
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]
    out = {"alpha": alpha, "dar": None, "cdar": None, "pain_index": None, "max_drawdown": None,
           "underwater_share": None, "longest_underwater_days": None, "current_underwater_days": None, "n": int(len(s))}
    if len(s) < 30:
        return out
    v = s.to_numpy(float)
    peak = np.maximum.accumulate(v)
    loss = 1.0 - v / peak  # drawdown depth >= 0
    dar = float(np.quantile(loss, alpha))
    tail = loss[loss >= dar]
    under = loss > 1e-12
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    out.update(dar=dar, cdar=float(tail.mean()) if tail.size else dar, pain_index=float(loss.mean()),
               max_drawdown=float(loss.max()), underwater_share=float(under.mean()),
               longest_underwater_days=int(longest), current_underwater_days=int(cur))
    return jsonable({k: (clean(x) if isinstance(x, float) else x) for k, x in out.items()})
