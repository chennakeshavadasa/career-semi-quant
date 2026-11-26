"""Monte Carlo price cones and equity-compensation valuation (RSU and stock-option grants).

Simulation engine (daily steps, ``ppy`` = 252 trading days per year):
* ``gbm``: i.i.d. normal daily log returns with the lookback volatility.
* ``bootstrap``: stationary block bootstrap (Politis & Romano 1994; geometric block lengths with
  mean ``block``) of the DEMEANED daily log returns of the lookback window, plus the chosen drift.
* ``garch``: a GJR-GARCH(1,1) with Student-t innovations fitted on the lookback (``arch``),
  simulated forward from the next-day conditional variance.

Drift (``ann_drift_used`` is the annual expected simple return, E[S_1y] / S_0 - 1):
"historical" = lookback mean log return x 252 + sigma^2 / 2 (the median path follows the
historical log growth); "zero" = E[S_t] = S_0 (martingale); "riskfree" = ``rf``; "custom" =
``mu``. Each daily log return gets the drift mu_c / 252 - sigma_t^2 / 2 (mu_c = ln(1 + annual
drift)), so the expected price grows at the chosen rate whatever the volatility.

Paths are generated in float32 chunks and only the reported days are kept, so memory stays
small (10,000 paths x 1,008 days uses well under 100 MB). Results are reproducible for a
given ``seed``. Every public function returns JSON-ready values and never raises.
"""
from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pandas as pd
from scipy import stats

from ._util import iso, jsonable
from .performance import _on_or_before, _prep

__all__ = ["simulate", "vest_schedule", "rsu_grant", "option_grant"]

PPY = 252
_FREQ = {"monthly": 1, "quarterly": 3, "semiannual": 6, "semi-annual": 6, "semiannually": 6, "annual": 12,
         "annually": 12, "yearly": 12}


# --------------------------------------------------------------------------- engine
def _lookback(close, lookback_years: float) -> tuple[pd.Series, np.ndarray]:
    c = _prep(close)
    if len(c) and lookback_years:
        c = c[c.index >= c.index[-1] - pd.DateOffset(months=int(round(12 * float(lookback_years))))]
    x = np.log(c).diff().dropna().to_numpy(dtype=float)
    return c, x[np.isfinite(x)]


def _drift(drift: str, x: np.ndarray, var_d: float, mu: float | None, rf: float) -> float:
    """Annual expected simple return implied by the drift choice (``var_d``: per-day variance of
    the simulated log returns relevant for multi-day sums)."""
    d = (drift or "historical").lower()
    if d == "zero":
        return 0.0
    if d == "riskfree":
        return float(rf)
    if d == "custom":
        if mu is None:
            raise ValueError("drift='custom' needs mu (annual expected return)")
        return float(mu)
    if d == "historical":
        return math.expm1(float(x.mean()) * PPY + 0.5 * var_d * PPY) if x.size else 0.0
    raise ValueError(f"unknown drift {drift!r} (historical, zero, riskfree, custom)")


def _bootstrap_var(e: np.ndarray, block: float) -> float:
    """Per-step long-run variance of stationary-bootstrap sums: gamma_0 + 2 sum_k (1 - 1/b)^k
    gamma_k with circular autocovariances gamma_k of the demeaned returns (a pair k steps apart
    lies in the same block with probability (1 - 1/b)^k). Using it in the -sigma^2/2 drift
    correction keeps E[S_t] at the chosen drift even when returns are autocorrelated."""
    n = e.size
    g0 = float(e @ e) / n
    q = 1.0 - 1.0 / max(float(block), 1.0)
    s, w, k = g0, q, 1
    while w > 1e-6 and k < n:
        s += 2.0 * w * float(e @ np.roll(e, k)) / n
        w *= q
        k += 1
    return max(s, 0.05 * g0)


def _garch_params(x: np.ndarray):
    from .volatility import _fit_arch

    res = _fit_arch(pd.Series(x * 100.0), "gjr", "t")
    p = res.params
    pars = {k: float(p.get(k, 0.0)) for k in ("omega", "alpha[1]", "gamma[1]", "beta[1]", "nu")}
    if not all(np.isfinite(v) for v in pars.values()) or pars["nu"] <= 2:
        raise ValueError("GJR-GARCH fit failed")
    pars["h0"] = float(res.forecast(horizon=1, reindex=False).variance.iloc[-1, 0])
    return pars


def _engine(x: np.ndarray, spot: float, horizon: int, n_paths: int, method: str, mu_ann: float, var_d: float,
            block: float, rng: np.random.Generator, record: np.ndarray, garch: dict | None = None):
    """Simulate log-price paths in time-major float32 chunks; return prices at the ``record``
    days (sorted unique ints in [0, horizon]) as float32 (len(record), n_paths) and the realised
    annualised volatility of the simulated daily log returns."""
    H = int(horizon)
    out = np.empty((record.size, n_paths), dtype=np.float32)
    pos = {int(dd): j for j, dd in enumerate(record)}
    if 0 in pos:
        out[pos[0]] = spot
    mu_c = math.log1p(mu_ann)
    drift_d = np.float32(mu_c / PPY - 0.5 * var_d)
    sd = np.float32(math.sqrt(max(var_d, 0.0)))
    logS = np.zeros(n_paths)
    s1 = s2 = 0.0
    cnt = 0
    chunk = max(1, min(H, 1_000_000 // max(n_paths, 1)))
    e = (x - x.mean()).astype(np.float32) if x.size else np.zeros(1, np.float32)
    nobs = e.size
    p_new = 1.0 / max(float(block), 1.0)
    cur = np.zeros(n_paths, dtype=np.int64)
    if garch is not None:
        h = np.full(n_paths, garch["h0"])
        nu = garch["nu"]
        tscale = math.sqrt((nu - 2.0) / nu)
        om, a, g, b = garch["omega"], garch["alpha[1]"], garch["gamma[1]"], garch["beta[1]"]
    t = 0
    while t < H:
        c = min(chunk, H - t)
        if method == "gbm":
            inc = rng.standard_normal((c, n_paths), dtype=np.float32)
            inc *= sd
            inc += drift_d
        elif method == "bootstrap":
            new = rng.random((c, n_paths), dtype=np.float32) < p_new
            if t == 0:
                new[0] = True
            starts = rng.integers(0, nobs, (c, n_paths))
            j = np.arange(c)[:, None]
            last = np.maximum.accumulate(np.where(new, j, -1), axis=0)
            has = last >= 0
            lastc = np.where(has, last, 0)
            idx = np.where(has, np.take_along_axis(starts, lastc, axis=0) + (j - lastc), cur[None, :] + 1 + j)
            idx %= nobs
            cur = idx[-1]
            inc = e[idx]
            inc += drift_d
        else:  # garch: percent units inside the recursion, -h/2 drift correction per step
            z = rng.standard_t(nu, (c, n_paths))
            z *= tscale
            inc = np.empty((c, n_paths), dtype=np.float32)
            for k in range(c):
                eps = np.sqrt(h) * z[k]
                inc[k] = mu_c / PPY - 0.5e-4 * h + 0.01 * eps
                h = om + (a + g * (eps < 0)) * eps * eps + b * h
        cs = np.cumsum(inc, axis=0, dtype=np.float64)
        cs += logS
        for dd in range(t + 1, t + c + 1):
            if dd in pos:
                out[pos[dd]] = spot * np.exp(cs[dd - t - 1])
        logS = cs[-1]
        s1 += float(inc.sum(dtype=np.float64))
        s2 += float(np.square(inc, dtype=np.float64).sum())
        cnt += inc.size
        t += c
    var = (s2 - s1 * s1 / cnt) / max(cnt - 1, 1) if cnt else 0.0
    return out, math.sqrt(max(var, 0.0) * PPY)


def _run(close, horizon: int, n_paths: int, method: str, drift: str, mu, rf, block, seed, lookback_years,
         record: np.ndarray):
    """Shared setup: returns (prices at record days, info dict)."""
    c, x = _lookback(close, lookback_years)
    if len(c) == 0:
        raise ValueError("no price data")
    spot = float(c.iloc[-1])
    if x.size < 2:
        raise ValueError("insufficient history (need at least 3 closes)")
    method = (method or "bootstrap").lower()
    if method not in ("gbm", "bootstrap", "garch"):
        raise ValueError(f"unknown method {method!r} (gbm, bootstrap, garch)")
    sd = float(np.std(x, ddof=1))
    note = None
    garch = None
    if method == "garch":
        try:
            if x.size < 250 or sd < 1e-10:
                raise ValueError("insufficient history for GARCH (need 250 returns)")
            garch = _garch_params(x)
        except Exception as exc:  # noqa: BLE001
            note = f"GARCH unavailable ({exc}); used bootstrap"
            method = "bootstrap"
    var_d = _bootstrap_var(x - x.mean(), block) if method == "bootstrap" else sd * sd
    mu_ann = _drift(drift, x, var_d, mu, rf)
    rng = np.random.default_rng(seed)
    paths, vol_used = _engine(x, spot, horizon, int(n_paths), method, mu_ann, var_d, block, rng, record, garch)
    info = {"spot": spot, "asof": c.index[-1], "method": method, "drift": (drift or "historical").lower(),
            "ann_vol_used": vol_used, "ann_drift_used": mu_ann, "lookback": {"start": iso(c.index[0]),
            "end": iso(c.index[-1]), "n": int(x.size)}, "note": note}
    return paths, info


def _pct(a: np.ndarray, qs=(5, 25, 50, 75, 95), axis=0):
    return np.percentile(a, qs, axis=axis)


# --------------------------------------------------------------------------- price cone
def simulate(close, horizon_days: int = 252, n_paths: int = 10000, method: str = "bootstrap",
             drift: str = "historical", mu: float | None = None, rf: float = 0.04, block: int = 5, seed: int = 0,
             lookback_years: float = 5) -> dict:
    """Monte Carlo price paths from the last close (see the module docstring for methods / drift).

    Returns keys: ``spot``, ``asof``, ``horizon_days``, ``n_paths``, ``method`` (the method used;
    a failed GARCH fit falls back to bootstrap with a ``note``), ``drift``, ``ann_vol_used``
    (annualised std of the simulated daily log returns), ``ann_drift_used`` (annual expected
    simple return), ``lookback`` {"start", "end", "n"}, ``percentiles`` {"days" (<= 121 sampled
    trading days incl. 0 and H), "dates" (business-day calendar dates of those days), "p5",
    "p25", "p50", "p75", "p95", "mean"} (prices), ``terminal`` {"mean", "median", "p5", "p95",
    "prob_loss" (P(S_H < spot)), "prob_gain_20" (P(S_H > 1.2 spot)), "prob_loss_20" (P(S_H <
    0.8 spot)), "hist" {"edges", "counts"} (50 bins between the 0.5% and 99.5% quantiles; the
    outer 1% of paths is not counted)}, ``sample_paths`` (25 paths on the sampled days).
    """
    H = max(int(horizon_days), 1)
    n_paths = max(int(n_paths), 1)
    days = np.unique(np.round(np.linspace(0, H, min(H, 120) + 1)).astype(np.int64))
    try:
        paths, info = _run(close, H, n_paths, method, drift, mu, rf, block, seed, lookback_years, days)
        spot = info["spot"]
        p = _pct(paths, axis=1)
        term = paths[-1].astype(np.float64)
        lo, hi = np.quantile(term, [0.005, 0.995])
        if hi - lo < 1e-9 * max(abs(spot), 1.0):
            lo, hi = lo - 0.01 * spot, hi + 0.01 * spot
        counts, edges = np.histogram(term, bins=50, range=(lo, hi))
        dates = pd.bdate_range(info["asof"], periods=H + 1)
        out = {**info, "horizon_days": H, "n_paths": n_paths,
               "percentiles": {"days": days, "dates": [iso(dates[int(d)]) for d in days], "p5": p[0], "p25": p[1],
                               "p50": p[2], "p75": p[3], "p95": p[4], "mean": paths.mean(axis=1, dtype=np.float64)},
               "terminal": {"mean": term.mean(), "median": float(np.median(term)),
                            "p5": float(np.percentile(term, 5)), "p95": float(np.percentile(term, 95)),
                            "prob_loss": float((term < spot).mean()), "prob_gain_20": float((term > 1.2 * spot).mean()),
                            "prob_loss_20": float((term < 0.8 * spot).mean()),
                            "hist": {"edges": edges, "counts": counts}},
               "sample_paths": paths[:, :25].T.astype(np.float64)}
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        return jsonable({"spot": None, "asof": None, "horizon_days": H, "n_paths": n_paths, "method": method,
                         "drift": drift, "ann_vol_used": None, "ann_drift_used": None, "lookback": None,
                         "percentiles": {"days": [], "dates": [], "p5": [], "p25": [], "p50": [], "p75": [], "p95": [],
                                         "mean": []},
                         "terminal": {"mean": None, "median": None, "p5": None, "p95": None, "prob_loss": None,
                                      "prob_gain_20": None, "prob_loss_20": None, "hist": {"edges": [], "counts": []}},
                         "sample_paths": [], "error": str(exc)})


# --------------------------------------------------------------------------- vesting
def vest_schedule(start: str, years: float = 4, cliff_months: int = 12, frequency: str = "quarterly") -> list[dict]:
    """Standard time-based vesting schedule from the grant date ``start``.

    Vests every ``frequency`` (monthly / quarterly / semiannual / annual) over ``years``; nothing
    vests before the cliff, and the cliff date releases everything accrued up to it (e.g. 25% at
    12 months for a 4-year grant). If the term is not a whole number of periods the last vest is
    at the end of the term. Fractions are exact (they sum to 1).

    Returns [{"date": ISO, "fraction"}], in date order ([] for invalid inputs).
    """
    try:
        t0 = pd.Timestamp(start).normalize()
        total = int(round(float(years) * 12))
        step = _FREQ.get(str(frequency).lower().strip())
        if step is None or total <= 0:
            return []
        cliff = min(max(int(cliff_months or 0), 0), total)
        months = list(range(step, total + 1, step))
        if not months or months[-1] != total:
            months.append(total)
        if cliff > 0:
            months = [cliff] + [m for m in months if m > cliff]
        fr = [Fraction(m - p, total) for p, m in zip([0] + months[:-1], months)]
        out = []
        acc = 0.0
        for k, (m, f) in enumerate(zip(months, fr)):
            val = float(f) if k < len(months) - 1 else 1.0 - acc
            acc += float(f)
            out.append({"date": iso(t0 + pd.DateOffset(months=m)), "fraction": val})
        return jsonable(out)
    except Exception:  # noqa: BLE001
        return []


def _parse_schedule(schedule) -> list[tuple[pd.Timestamp, float]]:
    items = []
    for v in schedule or []:
        try:
            items.append((pd.Timestamp(v["date"]).normalize(), float(v["fraction"])))
        except Exception:  # noqa: BLE001
            continue
    return sorted(items, key=lambda z: z[0])


def _stats(a: np.ndarray) -> dict:
    q = np.percentile(a, [5, 25, 50, 75, 95])
    return {"mean": float(a.mean()), "p5": q[0], "p25": q[1], "p50": q[2], "p75": q[3], "p95": q[4]}


def _vest_prices(close, vests, n_paths, method, drift, seed, rf=0.04, lookback_years=5):
    """Price at each vest date: actual close on or before past dates; simulated (n_paths) for
    future dates (trading days ahead = calendar days x 252 / 365.25, at least 1)."""
    c = _prep(close)
    if len(c) == 0:
        raise ValueError("no price data")
    last = c.index[-1]
    fut = [(i, max(1, int(round((d - last).days * PPY / 365.25)))) for i, (d, _) in enumerate(vests) if d > last]
    prices = [None] * len(vests)
    past = [d <= last for d, _ in vests]
    info = {"spot": float(c.iloc[-1]), "asof": last, "method": (method or "bootstrap").lower(),
            "drift": (drift or "zero").lower(), "ann_vol_used": None, "ann_drift_used": None, "note": None}
    for i, (d, _) in enumerate(vests):
        if past[i]:
            hit = _on_or_before(c, d)
            prices[i] = np.full(n_paths, hit[1] if hit else np.nan)
    if fut:
        rec = np.unique([h for _, h in fut])
        paths, info2 = _run(c, int(rec.max()), n_paths, method, drift, None, rf, 5, seed, lookback_years, rec)
        info.update({k: info2[k] for k in ("method", "drift", "ann_vol_used", "ann_drift_used", "note")})
        col = {int(h): j for j, h in enumerate(rec)}
        for i, h in fut:
            prices[i] = paths[col[h]].astype(np.float64)
    return prices, past, info


def rsu_grant(close, schedule: list[dict], units: float | None = None, grant_value: float | None = None,
              grant_price: float | None = None, n_paths: int = 10000, method: str = "bootstrap", drift: str = "zero",
              seed: int = 0) -> dict:
    """Value distribution of a restricted-stock-unit grant over its vesting schedule.

    ``grant_price`` defaults to the average of the last 30 trading-day closes; ``units`` defaults
    to grant_value / grant_price (one of units or grant_value is required). Each vest delivers
    units x fraction shares (fractions are used as given). Past vest dates use the actual close
    on or before the date; future ones are simulated jointly (one path set, see ``simulate``;
    default drift "zero" = no expected price change).

    Returns keys: ``units``, ``grant_price``, ``grant_value``, ``spot``, ``current_value`` (units x
    spot), ``method``, ``drift``, ``ann_vol_used``, ``vests`` [{"date", "fraction", "units",
    "past" (bool), "mean", "p5", "p25", "p50", "p75", "p95" (value of the vest, currency),
    "prob_below_grant" (P(price at vest < grant_price))}], ``total`` {"mean", "p5", "p25", "p50",
    "p75", "p95" (path-wise sum over vests), "prob_below_grant_value" (P(total < grant price x
    scheduled units)), "expected_vs_grant" (mean / that - 1)}, ``cumulative`` {"dates", "p5",
    "p50", "p95"} (cumulative vested value).
    """
    keys_total = ["mean", "p5", "p25", "p50", "p75", "p95", "prob_below_grant_value", "expected_vs_grant"]
    try:
        n_paths = max(int(n_paths), 1)
        vests = _parse_schedule(schedule)
        if not vests:
            raise ValueError("empty or invalid schedule")
        c = _prep(close)
        if len(c) == 0:
            raise ValueError("no price data")
        gp = float(grant_price) if grant_price is not None else float(c.iloc[-30:].mean())
        if units is None:
            if grant_value is None:
                raise ValueError("units or grant_value is required")
            units = float(grant_value) / gp
        units = float(units)
        gv = float(grant_value) if grant_value is not None else units * gp
        prices, past, info = _vest_prices(c, vests, n_paths, method, drift, seed)
        rows, tot = [], np.zeros(n_paths)
        cum = {"dates": [], "p5": [], "p50": [], "p95": []}
        sched_units = 0.0
        for (d, f), px, ps in zip(vests, prices, past):
            u = units * f
            sched_units += u
            val = u * px
            tot = tot + val
            rows.append({"date": iso(d), "fraction": f, "units": u, "past": bool(ps), **_stats(val),
                         "prob_below_grant": float((px < gp).mean())})
            q = np.percentile(tot, [5, 50, 95])
            cum["dates"].append(iso(d))
            cum["p5"].append(q[0])
            cum["p50"].append(q[1])
            cum["p95"].append(q[2])
        ref = gp * sched_units
        total = {**_stats(tot), "prob_below_grant_value": float((tot < ref).mean()),
                 "expected_vs_grant": float(tot.mean() / ref - 1.0) if ref > 0 else None}
        out = {"units": units, "grant_price": gp, "grant_value": gv, "spot": info["spot"],
               "current_value": units * info["spot"], "method": info["method"], "drift": info["drift"],
               "ann_vol_used": info["ann_vol_used"], "vests": rows, "total": total, "cumulative": cum}
        if info.get("note"):
            out["note"] = info["note"]
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        return jsonable({"units": units, "grant_price": grant_price, "grant_value": grant_value, "spot": None,
                         "current_value": None, "method": method, "drift": drift, "ann_vol_used": None, "vests": [],
                         "total": {k: None for k in keys_total}, "cumulative": {"dates": [], "p5": [], "p50": [], "p95": []},
                         "error": str(exc)})


def _bs_call(S: float, K: float, T: float, r: float, q: float, vol: float) -> float:
    """Black-Scholes(-Merton) European call with continuous rate r and dividend yield q."""
    if T <= 0:
        return max(S - K, 0.0)
    if vol <= 0:
        return max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0)
    sq = vol * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * vol * vol) * T) / sq
    return S * math.exp(-q * T) * stats.norm.cdf(d1) - K * math.exp(-r * T) * stats.norm.cdf(d1 - sq)


def option_grant(close, units: float, strike: float, schedule: list[dict], expiry_years: float = 10, rf: float = 0.04,
                 q: float = 0.0, vol: float | None = None, n_paths: int = 10000, method: str = "bootstrap",
                 drift: str = "zero", seed: int = 0) -> dict:
    """Employee stock-option grant: Black-Scholes value today and the distribution of intrinsic
    value at each vest date.

    Black-Scholes-Merton European call (continuous ``rf`` and dividend yield ``q``) with
    ``expiry_years`` remaining and ``vol`` (default: 1-year realized close-to-close vol, last 252
    log returns). ``intrinsic_now`` = max(spot - strike, 0) per option; ``breakeven`` = strike +
    Black-Scholes value per option (the price at which intrinsic value equals today's value).
    Vest values are units x fraction x max(S - strike, 0) with S the actual close (past vests)
    or simulated (future vests, as in ``rsu_grant``).

    Returns keys: ``strike``, ``spot``, ``vol``, ``expiry_years``, ``units``,
    ``bs_value_per_option``, ``bs_value_total``, ``intrinsic_now``, ``intrinsic_now_total``,
    ``breakeven``, ``method``, ``drift``, ``vests`` [{"date", "fraction", "units", "past",
    "mean_intrinsic", "p5", "p50", "p95", "prob_underwater" (P(S < strike))}], ``total`` {"mean",
    "p5", "p25", "p50", "p75", "p95" (sum of intrinsic values at vest), "prob_below_grant_value"
    (P(total < Black-Scholes value of the scheduled options)), "expected_vs_grant",
    "prob_all_underwater"}.
    """
    keys_total = ["mean", "p5", "p25", "p50", "p75", "p95", "prob_below_grant_value", "expected_vs_grant",
                  "prob_all_underwater"]
    try:
        n_paths = max(int(n_paths), 1)
        c = _prep(close)
        if len(c) == 0:
            raise ValueError("no price data")
        S, K = float(c.iloc[-1]), float(strike)
        if K <= 0:
            raise ValueError("strike must be positive")
        if vol is None:
            x = np.log(c.iloc[-253:]).diff().dropna().to_numpy()
            vol = float(np.std(x, ddof=1) * math.sqrt(PPY)) if x.size >= 2 else 0.0
        vol = float(vol)
        units = float(units)
        bs = _bs_call(S, K, float(expiry_years), float(rf), float(q), vol)
        vests = _parse_schedule(schedule)
        rows, tot, sched = [], np.zeros(n_paths), 0.0
        allwater = np.ones(n_paths, dtype=bool)
        info = {"method": method, "drift": drift}
        if vests:
            prices, past, info = _vest_prices(c, vests, n_paths, method, drift, seed, rf=rf)
            for (d, f), px, ps in zip(vests, prices, past):
                u = units * f
                sched += u
                iv = u * np.maximum(px - K, 0.0)
                tot = tot + iv
                allwater &= px <= K
                qv = np.percentile(iv, [5, 50, 95])
                rows.append({"date": iso(d), "fraction": f, "units": u, "past": bool(ps), "mean_intrinsic": iv.mean(),
                             "p5": qv[0], "p50": qv[1], "p95": qv[2], "prob_underwater": float((px < K).mean())})
        ref = bs * sched
        total = ({**_stats(tot), "prob_below_grant_value": float((tot < ref).mean()),
                  "expected_vs_grant": float(tot.mean() / ref - 1.0) if ref > 0 else None,
                  "prob_all_underwater": float(allwater.mean())} if vests else {k: None for k in keys_total})
        out = {"strike": K, "spot": S, "vol": vol, "expiry_years": float(expiry_years), "units": units,
               "bs_value_per_option": bs, "bs_value_total": bs * units, "intrinsic_now": max(S - K, 0.0),
               "intrinsic_now_total": max(S - K, 0.0) * units, "breakeven": K + bs,
               "method": info.get("method"), "drift": info.get("drift"), "vests": rows, "total": total}
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        return jsonable({"strike": strike, "spot": None, "vol": vol, "expiry_years": expiry_years, "units": units,
                         "bs_value_per_option": None, "bs_value_total": None, "intrinsic_now": None,
                         "intrinsic_now_total": None, "breakeven": None, "method": method, "drift": drift, "vests": [],
                         "total": {k: None for k in keys_total}, "error": str(exc)})
