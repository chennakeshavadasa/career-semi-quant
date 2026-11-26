"""Options analytics on yfinance-shaped option chains.

Model
    Black-Scholes-Merton (Black & Scholes 1973, Merton 1973) with a continuous dividend yield
    ``q``. Listed US single-stock options are American; European BSM implied vols are the market
    convention for them (the early-exercise premium only matters for deep in-the-money options,
    which is why the smile, skew and surface are built from out-of-the-money quotes only).
Time
    ACT/365 calendar time to 16:00 America/New_York on the expiry date (``time_to_expiry``).
Units
    Fractions everywhere (0.25 = 25 % vol, 0.04 = 4 % rate). Greeks: delta and gamma per 1.00 move
    of the underlying, vega per 1 vol point (0.01), theta per calendar day, rho per 1 % rate move.
    Dollar figures (GEX, max pain) use the standard 100-share contract multiplier.
Quotes
    mid = (bid + ask) / 2 when both are > 0 and ask >= bid; otherwise the last trade price is used
    and the quote is flagged stale (holiday / after-hours snapshots have many zero or crossed quotes).
"""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import ndtr

from ._util import clean, jsonable, safe

NY = "America/New_York"
YEAR_SECONDS = 365.0 * 86400.0
MIN_T = 1.0 / (365.0 * 24.0)          # floor: one hour
IV_LO, IV_HI = 1e-4, 5.0              # implied-vol search bracket
MULTIPLIER = 100.0                    # shares per contract
_SQRT2PI = math.sqrt(2.0 * math.pi)
_SQRT2 = math.sqrt(2.0)
_NAN = float("nan")

__all__ = ["bs_price", "bs_greeks", "implied_vol", "implied_vol_vec", "time_to_expiry", "chain_analytics",
           "term_structure", "iv_surface"]


# =============================================================================== BSM core
def _npdf(x):
    return np.exp(-0.5 * x * x) / _SQRT2PI


def _kind_mask(kind, shape):
    """(is_call, valid) boolean arrays of ``shape`` from 'call'/'put' ('c'/'p'), bools (True = call)
    or arrays of either."""
    if isinstance(kind, str):
        k = kind.strip().lower()
        return np.full(shape, k in ("call", "c")), np.full(shape, k in ("call", "c", "put", "p"))
    a = np.asarray(kind)
    if a.dtype == bool:
        ic, ok = a, np.ones(a.shape, dtype=bool)
    elif np.issubdtype(a.dtype, np.number):
        af = a.astype(float)
        ic, ok = af > 0.5, np.isfinite(af)
    else:
        s = np.char.lower(np.char.strip(a.astype(str)))
        ic = (s == "call") | (s == "c")
        ok = ic | (s == "put") | (s == "p")
    return np.broadcast_to(ic, shape), np.broadcast_to(ok, shape)


def _bcast(kind, *xs):
    arrs = [np.asarray(x, dtype=float) for x in xs]
    kshape = () if isinstance(kind, str) else np.shape(kind)
    shape = np.broadcast_shapes(kshape, *(a.shape for a in arrs))
    arrs = [np.broadcast_to(a, shape) for a in arrs]
    ic, ok = _kind_mask(kind, shape)
    return shape, arrs, ic, ok


def _out(a):
    a = np.asarray(a, dtype=float)
    return float(a) if a.ndim == 0 else np.array(a)


def _bs_arrays(S, K, T, r, q, sigma, ic):
    """BSM price plus d1, d2, e^{-qT}, e^{-rT}, sqrt(T) for broadcastable float arrays (no edge cases)."""
    with np.errstate(all="ignore"):
        sq = np.sqrt(T)
        vs = sigma * sq
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vs
        d2 = d1 - vs
        dq = np.exp(-q * T)
        dr = np.exp(-r * T)
        call = S * dq * ndtr(d1) - K * dr * ndtr(d2)
        put = K * dr * ndtr(-d2) - S * dq * ndtr(-d1)
    return np.where(ic, call, put), d1, d2, dq, dr, sq


def _bad(ok, S, K, T, r, q, sigma):
    return (~ok | ~(S > 0) | ~(K > 0) | ~np.isfinite(T) | ~np.isfinite(sigma)
            | ~np.isfinite(r) | ~np.isfinite(q))


def bs_price(S, K, T, r, q, sigma, kind="call"):
    """Black-Scholes-Merton price with continuous dividend yield (vectorised, numpy broadcasting).

    ``kind`` is "call"/"put" ("c"/"p"), a bool (True = call) or an array of either. T <= 0 returns
    intrinsic value, sigma <= 0 the discounted forward intrinsic value; invalid inputs give NaN.
    Returns a float for scalar inputs, else an ndarray.
    """
    try:
        shape, (S, K, T, r, q, sigma), ic, ok = _bcast(kind, S, K, T, r, q, sigma)
    except (ValueError, TypeError):
        return _NAN
    price, d1, d2, dq, dr, sq = _bs_arrays(S, K, T, r, q, sigma, ic)
    with np.errstate(all="ignore"):
        intrinsic = np.where(ic, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
        fwd = np.where(ic, np.maximum(S * dq - K * dr, 0.0), np.maximum(K * dr - S * dq, 0.0))
    price = np.where(T <= 0, intrinsic, np.where(sigma <= 0, fwd, price))
    return _out(np.where(_bad(ok, S, K, T, r, q, sigma), np.nan, price))


def bs_greeks(S, K, T, r, q, sigma, kind="call") -> dict:
    """Black-Scholes-Merton greeks (vectorised).

    Returns {"price", "delta", "gamma", "vega", "theta", "rho"}: delta and gamma per 1.00 move in the
    underlying, vega per 1 vol point (0.01), theta per calendar day (annual theta / 365), rho per 1 %
    (0.01) move in r. Values are floats for scalar inputs, else ndarrays; invalid inputs give NaN.
    """
    keys = ("price", "delta", "gamma", "vega", "theta", "rho")
    try:
        shape, (S, K, T, r, q, sigma), ic, ok = _bcast(kind, S, K, T, r, q, sigma)
    except (ValueError, TypeError):
        return {k: _NAN for k in keys}
    price, d1, d2, dq, dr, sq = _bs_arrays(S, K, T, r, q, sigma, ic)
    with np.errstate(all="ignore"):
        pdf = _npdf(d1)
        nd1, nd2 = ndtr(d1), ndtr(d2)
        delta = np.where(ic, dq * nd1, dq * (nd1 - 1.0))
        gamma = dq * pdf / (S * sigma * sq)
        vega = S * dq * pdf * sq / 100.0
        common = -S * dq * pdf * sigma / (2.0 * sq)
        theta = np.where(ic, common - r * K * dr * nd2 + q * S * dq * nd1,
                         common + r * K * dr * ndtr(-d2) - q * S * dq * ndtr(-d1)) / 365.0
        rho = np.where(ic, K * T * dr * nd2, -K * T * dr * ndtr(-d2)) / 100.0
        # degenerate cases: expired (intrinsic) and zero vol (deterministic forward)
        expired = T <= 0
        flat = (sigma <= 0) & ~expired
        itm_c, itm_p = (S * dq > K * dr), (K * dr > S * dq)
        intrinsic = np.where(ic, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
        fwd = np.where(ic, np.maximum(S * dq - K * dr, 0.0), np.maximum(K * dr - S * dq, 0.0))
        price = np.where(expired, intrinsic, np.where(flat, fwd, price))
        delta = np.where(expired, np.where(ic, 1.0 * (S > K), -1.0 * (S < K)),
                         np.where(flat, np.where(ic, dq * itm_c, -dq * itm_p), delta))
        zero = expired | flat
        gamma = np.where(zero, 0.0, gamma)
        vega = np.where(zero, 0.0, vega)
        theta = np.where(expired, 0.0, np.where(
            flat, np.where(ic, itm_c * (q * S * dq - r * K * dr), itm_p * (r * K * dr - q * S * dq)) / 365.0, theta))
        rho = np.where(expired, 0.0, np.where(flat, np.where(ic, K * T * dr * itm_c, -K * T * dr * itm_p) / 100.0, rho))
    bad = _bad(ok, S, K, T, r, q, sigma)
    vals = (price, delta, gamma, vega, theta, rho)
    return {k: _out(np.where(bad, np.nan, v)) for k, v in zip(keys, vals)}


# =============================================================================== implied vol
def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / _SQRT2)


def _bs_scalar(S, K, T, r, q, sig, is_call):
    vs = sig * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sig * sig) * T) / vs
    d2 = d1 - vs
    if is_call:
        return S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1)


def implied_vol(price, S, K, T, r, q, kind="call") -> float:
    """Black-Scholes-Merton implied volatility by Brent's method (scipy ``brentq``) on [1e-4, 5].

    Returns NaN when the price is outside the no-arbitrage bounds
    (call: max(S e^{-qT} - K e^{-rT}, 0) < C < S e^{-qT}; put: max(K e^{-rT} - S e^{-qT}, 0) < P < K e^{-rT}),
    when no root lies in the bracket, or for invalid inputs.
    """
    try:
        p, S, K, T, r, q = (float(x) for x in (price, S, K, T, r, q))
        ic, ok = _kind_mask(kind, ())
        if not bool(ok):
            return _NAN
        is_call = bool(ic)
        if not all(math.isfinite(v) for v in (p, S, K, T, r, q)) or S <= 0 or K <= 0 or T <= 0:
            return _NAN
        dq, dr = math.exp(-q * T), math.exp(-r * T)
        lo_b, hi_b = ((max(S * dq - K * dr, 0.0), S * dq) if is_call else (max(K * dr - S * dq, 0.0), K * dr))
        if not (lo_b < p < hi_b):
            return _NAN

        def f(s):
            return _bs_scalar(S, K, T, r, q, s, is_call) - p

        flo, fhi = f(IV_LO), f(IV_HI)
        if flo > 0 or fhi < 0:
            return _NAN
        if flo == 0:
            return IV_LO
        if fhi == 0:
            return IV_HI
        return float(brentq(f, IV_LO, IV_HI, xtol=1e-12, rtol=1e-12, maxiter=200))
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return _NAN


def implied_vol_vec(price, S, K, T, r, q, kind="call", tol: float = 1e-12, maxiter: int = 100) -> np.ndarray:
    """Vectorised implied volatility (same bracket [1e-4, 5], bounds and NaN rules as ``implied_vol``).

    Safeguarded Newton-Raphson (Numerical Recipes ``rtsafe``): every element keeps a bracket that
    contains the root; Newton steps that leave it are replaced by bisection, so it converges for every
    element that has a root, to |d sigma| < ``tol``. Returns an ndarray shaped like the broadcast inputs.
    """
    try:
        shape, (P, S, K, T, r, q), ic, ok = _bcast(kind, price, S, K, T, r, q)
    except (ValueError, TypeError):
        return np.array(_NAN)
    P, S, K, T, r, q = (np.ravel(np.array(a, dtype=float)) for a in (P, S, K, T, r, q))
    ic, ok = np.ravel(np.array(ic)), np.ravel(np.array(ok))
    out = np.full(P.size, np.nan)
    with np.errstate(all="ignore"):
        dq, dr = np.exp(-q * T), np.exp(-r * T)
        lo_b = np.where(ic, np.maximum(S * dq - K * dr, 0.0), np.maximum(K * dr - S * dq, 0.0))
        hi_b = np.where(ic, S * dq, K * dr)
        good = (ok & np.isfinite(P) & (S > 0) & (K > 0) & (T > 0) & np.isfinite(T) & np.isfinite(r)
                & np.isfinite(q) & (P > lo_b) & (P < hi_b))
    idx = np.flatnonzero(good)
    if idx.size == 0:
        return out.reshape(shape)
    p, s, k, t, rr, qq, c = P[idx], S[idx], K[idx], T[idx], r[idx], q[idx], ic[idx]
    m = idx.size
    a, b = np.full(m, IV_LO), np.full(m, IV_HI)
    fa = _bs_arrays(s, k, t, rr, qq, a, c)[0] - p
    fb = _bs_arrays(s, k, t, rr, qq, b, c)[0] - p
    solvable = (fa <= 0) & (fb >= 0)
    with np.errstate(all="ignore"):
        lfk = np.abs(np.log(s * np.exp((rr - qq) * t) / k))
        x = np.clip(np.sqrt(2.0 * lfk / t), 0.05, 3.0)      # Manaster-Koehler style start
    x = np.where(fa == 0, IV_LO, np.where(fb == 0, IV_HI, x))
    active = solvable & (fa != 0) & (fb != 0)
    for _ in range(maxiter):
        ia = np.flatnonzero(active)
        if ia.size == 0:
            break
        xa = x[ia]
        pr, d1, _d2, dqa, _dra, sqa = _bs_arrays(s[ia], k[ia], t[ia], rr[ia], qq[ia], xa, c[ia])
        fx = pr - p[ia]
        with np.errstate(all="ignore"):
            vega = s[ia] * dqa * _npdf(d1) * sqa
            hi_side = fx > 0
            b[ia] = np.where(hi_side, xa, b[ia])
            a[ia] = np.where(hi_side, a[ia], xa)
            newton = xa - fx / vega
            use = np.isfinite(newton) & (newton >= a[ia]) & (newton <= b[ia])
            xn = np.where(fx == 0, xa, np.where(use, newton, 0.5 * (a[ia] + b[ia])))
        x[ia] = xn
        done = (np.abs(xn - xa) <= tol) | ((b[ia] - a[ia]) <= tol) | (fx == 0)
        active[ia[done]] = False
    res = np.where(solvable, x, np.nan)
    out[idx] = res
    return out.reshape(shape)


# =============================================================================== time
def _ny(ts: Any) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize(NY, ambiguous=False, nonexistent="shift_forward") if t.tzinfo is None else t.tz_convert(NY)


def _expiry_ts(expiry: Any) -> pd.Timestamp:
    d = pd.Timestamp(expiry)
    if d.tzinfo is not None:
        d = d.tz_convert(NY)
    return pd.Timestamp(datetime.combine(d.date(), dtime(16, 0))).tz_localize(NY)


def time_to_expiry(expiry: str, asof: datetime | str) -> float:
    """Years (ACT/365, calendar time) from ``asof`` to 16:00 America/New_York on the expiry date,
    floored at one hour (1/8760). A naive ``asof`` is New York time; aware ones are converted.
    Returns NaN for unparseable input."""
    try:
        a = pd.Timestamp.now(tz=NY) if asof is None else _ny(asof)
        t = (_expiry_ts(expiry) - a).total_seconds() / YEAR_SECONDS
        return float(max(t, MIN_T))
    except (ValueError, TypeError, OverflowError):
        return _NAN


# =============================================================================== chain core
_NUM = ("strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility")


def _prep_side(df) -> pd.DataFrame:
    """yfinance option_chain side -> frame indexed by strike (unique, sorted) with numeric columns."""
    if df is None:
        df = pd.DataFrame()
    elif not isinstance(df, pd.DataFrame):
        df = safe(pd.DataFrame, df, default=pd.DataFrame())
    cols = {c: (pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index))
            for c in _NUM}
    out = pd.DataFrame(cols, index=df.index).astype(float)
    out["contract"] = df["contractSymbol"].astype(str) if "contractSymbol" in df.columns else ""
    out = out[np.isfinite(out["strike"].to_numpy()) & (out["strike"].to_numpy() > 0)]
    out = out.sort_values("strike", kind="stable").drop_duplicates("strike", keep="first")
    return out.set_index("strike")


def _side_arrays(D: pd.DataFrame, present: np.ndarray) -> dict:
    bid, ask, last = (D[c].to_numpy(float) for c in ("bid", "ask", "lastPrice"))
    with np.errstate(invalid="ignore"):
        valid = present & (bid > 0) & (ask > 0) & (ask >= bid)
        mid = np.where(valid, 0.5 * (bid + ask), np.where(present & (last > 0), last, np.nan))
    stale = present & ~valid & np.isfinite(mid)
    return {"bid": bid, "ask": ask, "last": last, "vol": D["volume"].to_numpy(float),
            "oi": D["openInterest"].to_numpy(float), "yiv": D["impliedVolatility"].to_numpy(float),
            "contract": D["contract"].to_numpy(object), "present": present, "valid": valid, "mid": mid,
            "stale": stale}


def _yahoo_iv_ok(iv: np.ndarray) -> np.ndarray:
    """Usable Yahoo IVs: finite, inside the solver bracket and not one of Yahoo's failed-solve
    placeholders (1e-5 or 2^k * 1.00001, e.g. 0.500005, 0.2500025, 1.00001)."""
    with np.errstate(all="ignore"):
        k = np.round(np.log2(iv))
        ratio = iv / np.power(2.0, k)
        placeholder = np.abs(ratio - 1.00001) < 2e-6
        return np.isfinite(iv) & (iv >= 0.01) & (iv <= IV_HI) & ~placeholder


def _interp(x: np.ndarray, y: np.ndarray, at: float) -> float:
    """Linear interpolation without extrapolation (x ascending); NaN outside [x0, xn]."""
    if x.size == 0 or not np.isfinite(at):
        return _NAN
    if at < x[0] - 1e-12 or at > x[-1] + 1e-12:
        return _NAN
    return float(np.interp(at, x, y))


def _core(calls, puts, spot, expiry, asof, r, q) -> dict:
    """Shared per-expiry analysis: quotes, implied forward, IVs, greeks, smile, ATM, skew, totals."""
    warns: list[str] = []
    S = clean(spot)
    r = clean(r)
    r = 0.0 if r is None else r
    q = clean(q)
    q = 0.0 if q is None else q
    T = time_to_expiry(expiry, asof)
    try:
        exp_s = pd.Timestamp(expiry).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        exp_s = str(expiry)
    expired = False
    if not np.isfinite(T):
        warns.append("could not parse expiry/asof; time to expiry unknown")
    else:
        expired = bool(safe(lambda: _expiry_ts(expiry) <= (_ny(asof) if asof is not None
                                                             else pd.Timestamp.now(tz=NY)), default=False))
        if expired:
            warns.append(f"expiry {exp_s} has passed; T floored at one hour")
    if S is None or S <= 0:
        warns.append("spot price missing or non-positive; IVs and greeks unavailable")
        S = _NAN

    cs, ps = _prep_side(calls), _prep_side(puts)
    K = np.union1d(cs.index.to_numpy(float), ps.index.to_numpy(float))
    c = _side_arrays(cs.reindex(K), np.isin(K, cs.index.to_numpy(float)))
    p = _side_arrays(ps.reindex(K), np.isin(K, ps.index.to_numpy(float)))
    n = K.size
    if n == 0:
        warns.append("empty option chain")

    # ---- implied forward from put-call parity at the strikes nearest spot
    F_carry = S * math.exp((r - q) * T) if np.isfinite(S) and np.isfinite(T) else _NAN
    F, f_src = F_carry, "carry"
    both = c["valid"] & p["valid"]
    if both.any() and np.isfinite(F_carry):
        ib = np.flatnonzero(both)
        near = ib[np.argsort(np.abs(K[ib] - S), kind="stable")[:4]]
        f_k = K[near] + math.exp(r * T) * (c["mid"][near] - p["mid"][near])
        f_par = float(np.median(f_k))
        tol = max(0.01, 0.10 * math.sqrt(T))
        if np.isfinite(f_par) and f_par > 0 and abs(f_par / F_carry - 1.0) <= tol:
            F, f_src = f_par, "parity"
        else:
            warns.append(f"put-call parity forward {f_par:.4g} is more than {tol:.1%} from the carry forward; "
                         "using S*exp((r-q)T)")
    elif n:
        warns.append("no strike with valid call and put quotes; forward = S*exp((r-q)T)")
    q_eff = (r - math.log(F / S) / T) if (np.isfinite(F) and F > 0 and np.isfinite(S) and np.isfinite(T)) else q

    # ---- implied vols (calls and puts in one vectorised solve)
    price = np.concatenate([c["mid"], p["mid"]])
    kind = np.concatenate([np.ones(n, bool), np.zeros(n, bool)])
    KK = np.concatenate([K, K])
    iv = implied_vol_vec(price, S, KK, T, r, q_eff, kind) if n else np.zeros(0)
    valid2 = np.concatenate([c["valid"], p["valid"]])
    present2 = np.concatenate([c["present"], p["present"]])
    yiv = np.concatenate([c["yiv"], p["yiv"]])
    src = np.where(np.isfinite(iv), np.where(valid2, "mid", "last"), None).astype(object)
    fb = ~np.isfinite(iv) & present2 & _yahoo_iv_ok(yiv)
    if fb.any():
        iv = np.where(fb, yiv, iv)
        src[fb] = "yahoo"
        warns.append(f"{int(fb.sum())} contracts use Yahoo's impliedVolatility (no solution from the quote)")
    g = bs_greeks(S, KK, T, r, q_eff, iv, kind) if n else {k: np.zeros(0) for k in
                                                           ("price", "delta", "gamma", "vega", "theta", "rho")}
    for side, sl in (("c", slice(0, n)), ("p", slice(n, 2 * n))):
        d = c if side == "c" else p
        d["iv"] = iv[sl]
        d["iv_src"] = src[sl]
        for gk in ("delta", "gamma", "vega", "theta"):
            d[gk] = np.asarray(g[gk])[sl]

    # ---- smile: OTM options with valid two-sided quotes and an IV solved from the mid
    lm_all = np.log(K / F) if np.isfinite(F) else np.full(n, np.nan)
    use_put = (K < F) & p["valid"] & (p["iv_src"] == "mid")
    use_call = (K >= F) & c["valid"] & (c["iv_src"] == "mid")
    sm_k = np.concatenate([K[use_put], K[use_call]])
    sm_iv = np.concatenate([p["iv"][use_put], c["iv"][use_call]])
    sm_side = np.array(["put"] * int(use_put.sum()) + ["call"] * int(use_call.sum()), dtype=object)
    sm_delta = np.concatenate([p["delta"][use_put], c["delta"][use_call]])
    order = np.argsort(sm_k, kind="stable")
    sm_k, sm_iv, sm_side, sm_delta = sm_k[order], sm_iv[order], sm_side[order], sm_delta[order]
    sm_lm = np.log(sm_k / F) if np.isfinite(F) else np.full(sm_k.size, np.nan)
    if n and sm_k.size < 3:
        warns.append("fewer than 3 valid OTM quotes; smile and skew unavailable or unreliable")

    # ---- ATM strike / IV / straddle
    priced = np.isfinite(c["mid"]) & np.isfinite(p["mid"])
    atm_i = None
    if n and np.isfinite(F):
        pool = np.flatnonzero(priced) if priced.any() else np.arange(n)
        atm_i = int(pool[np.argmin(np.abs(K[pool] - F))])
    atm_iv = _interp(sm_lm, sm_iv, 0.0)
    if not np.isfinite(atm_iv) and sm_lm.size:
        j = int(np.argmin(np.abs(sm_lm)))
        if abs(sm_lm[j]) <= 0.03:
            atm_iv = float(sm_iv[j])
    if not np.isfinite(atm_iv) and atm_i is not None:
        v = [x for x in (c["iv"][atm_i], p["iv"][atm_i]) if np.isfinite(x)]
        atm_iv = float(np.mean(v)) if v else _NAN
    straddle = _NAN
    if atm_i is not None and priced[atm_i]:
        straddle = float(c["mid"][atm_i] + p["mid"][atm_i])
        if c["stale"][atm_i] or p["stale"][atm_i]:
            warns.append("ATM straddle uses a stale last price (no valid two-sided quote)")

    # ---- skew: 25-delta risk reversal / butterfly, 90 % and 110 % moneyness vs ATM
    cm = sm_side == "call"
    pm = sm_side == "put"
    iv25c = iv25p = _NAN
    if cm.sum() >= 2:
        o = np.argsort(sm_delta[cm])
        iv25c = _interp(sm_delta[cm][o], sm_iv[cm][o], 0.25)
    if pm.sum() >= 2:
        o = np.argsort(sm_delta[pm])
        iv25p = _interp(sm_delta[pm][o], sm_iv[pm][o], -0.25)
    iv90 = _interp(sm_lm, sm_iv, math.log(0.90))
    iv110 = _interp(sm_lm, sm_iv, math.log(1.10))
    skew = {"rr25": iv25c - iv25p, "bf25": 0.5 * (iv25c + iv25p) - atm_iv,
            "put_skew_90": iv90 - atm_iv, "call_skew_110": iv110 - atm_iv,
            "iv_25d_call": iv25c, "iv_25d_put": iv25p, "iv_90": iv90, "iv_110": iv110}

    cvol, pvol = float(np.nansum(c["vol"])), float(np.nansum(p["vol"]))
    coi, poi = float(np.nansum(c["oi"])), float(np.nansum(p["oi"]))
    return {"expiry": exp_s, "expired": expired, "S": S, "r": r, "q": q, "q_eff": q_eff, "T": T, "K": K, "c": c,
            "p": p, "n": n,
            "F": F, "F_src": f_src, "lm": lm_all, "sm_k": sm_k, "sm_lm": sm_lm, "sm_iv": sm_iv, "sm_side": sm_side,
            "sm_delta": sm_delta, "atm_i": atm_i, "atm_iv": atm_iv, "straddle": straddle, "skew": skew,
            "call_volume": cvol, "put_volume": pvol, "call_oi": coi, "put_oi": poi, "warnings": warns}


def _ratio(a: float, b: float) -> float | None:
    return a / b if b and np.isfinite(a) and np.isfinite(b) and b > 0 else None


def _summary(core: dict) -> dict:
    S, T, atm_iv, straddle = core["S"], core["T"], core["atm_iv"], core["straddle"]
    implied_move = straddle / S if np.isfinite(straddle) and np.isfinite(S) and S > 0 else _NAN
    return {
        "expiry": core["expiry"], "dte": round(T * 365.0, 4) if np.isfinite(T) else None, "T": T, "spot": S,
        "forward": core["F"], "atm_strike": float(core["K"][core["atm_i"]]) if core["atm_i"] is not None else None,
        "atm_iv": atm_iv, "implied_move": implied_move, "straddle": straddle,
        "expected_range": ([S - straddle, S + straddle] if np.isfinite(straddle) else [None, None]),
        "one_sigma_move": S * atm_iv * math.sqrt(T) if np.isfinite(atm_iv) and np.isfinite(T) else None,
    }


def _clean_list(a) -> list:
    return [None if (v is None or (isinstance(v, float) and not math.isfinite(v))) else v for v in
            (a.tolist() if isinstance(a, np.ndarray) else list(a))]


def _max_pain(K, oi_c, oi_p) -> float | None:
    oc, op = np.nan_to_num(oi_c), np.nan_to_num(oi_p)
    if K.size == 0 or (oc.sum() + op.sum()) <= 0:
        return None
    pay = (np.maximum(K[:, None] - K[None, :], 0.0) * oc[None, :]).sum(1) + \
          (np.maximum(K[None, :] - K[:, None], 0.0) * op[None, :]).sum(1)
    return float(K[int(np.argmin(pay))])


def _gex(core: dict) -> dict:
    """Dealer gamma exposure, naive convention: dealers long calls / short puts.
    GEX = gamma * OI * 100 * S^2 * 0.01 ($ change in dealer delta per 1 % move), puts negative."""
    S, T, r, qe, K, c, p = core["S"], core["T"], core["r"], core["q_eff"], core["K"], core["c"], core["p"]
    scale = MULTIPLIER * S * S * 0.01
    gc = c["gamma"] * np.nan_to_num(c["oi"]) * scale
    gp = -p["gamma"] * np.nan_to_num(p["oi"]) * scale
    net = np.nan_to_num(gc) + np.nan_to_num(gp)
    by = [{"strike": float(K[i]),
           "call": (float(gc[i]) if c["present"][i] and np.isfinite(gc[i]) else None),
           "put": (float(gp[i]) if p["present"][i] and np.isfinite(gp[i]) else None),
           "net": float(net[i])} for i in range(K.size)]
    flip = None
    if np.isfinite(S) and np.isfinite(T) and K.size:
        mc = np.isfinite(c["iv"]) & (np.nan_to_num(c["oi"]) > 0)
        mp = np.isfinite(p["iv"]) & (np.nan_to_num(p["oi"]) > 0)
        if mc.any() or mp.any():
            grid = S * np.linspace(0.7, 1.3, 241)
            kk = np.concatenate([K[mc], K[mp]])
            vv = np.concatenate([c["iv"][mc], p["iv"][mp]])
            ww = np.concatenate([c["oi"][mc], -p["oi"][mp]])
            with np.errstate(all="ignore"):
                sq = math.sqrt(T)
                d1 = (np.log(grid[:, None] / kk[None, :]) + (r - qe + 0.5 * vv * vv) * T) / (vv * sq)
                gam = math.exp(-qe * T) * _npdf(d1) / (grid[:, None] * vv * sq)
                tot = np.nansum(gam * ww[None, :], axis=1) * MULTIPLIER * grid * grid * 0.01
            sg = np.sign(tot)
            idx = np.flatnonzero(sg[:-1] * sg[1:] < 0)
            if idx.size:
                roots = grid[idx] - tot[idx] * (grid[idx + 1] - grid[idx]) / (tot[idx + 1] - tot[idx])
                flip = float(roots[np.argmin(np.abs(roots - S))])
    return {"by_strike": by, "total": float(net.sum()) if K.size else None, "flip": flip}


def chain_analytics(calls: pd.DataFrame, puts: pd.DataFrame, spot: float, expiry: str, asof,
                    r: float = 0.04, q: float = 0.0) -> dict:
    """Full analytics for one expiry of a yfinance option chain.

    Method: quotes are cleaned (mid = (bid+ask)/2 when bid > 0, ask > 0 and ask >= bid, else the last
    price, flagged ``stale``); the forward is implied from put-call parity, F = K + e^{rT}(C - P), as the
    median over the (up to) four strikes nearest spot with valid two-sided quotes on both sides
    (rejected if more than max(1 %, 10 % * sqrt(T)) away from S e^{(r-q)T}, which is then used). IVs
    are re-solved from the mids with the carry implied by that forward (q_eff = r - ln(F/S)/T), so call
    and put IVs agree at a strike; when a solve fails Yahoo's impliedVolatility is used (flagged
    ``yahoo``; Yahoo's failed-solve placeholders such as 0.500005 are rejected).

    Returns {"expiry", "dte" (calendar days, fractional), "T" (years), "spot", "forward",
    "forward_source" ("parity"|"carry"), "q_implied", "atm_strike" (strike nearest the forward with
    both sides priced), "atm_iv" (OTM smile interpolated at K = F),
    "rows": [per strike: strike, call_bid, call_ask, call_mid, call_last, call_volume, call_oi, call_iv,
    call_delta, call_gamma, call_theta, call_vega, call_itm, call_stale, call_iv_source, call_contract,
    put_... same],
    "smile": [{"strike", "moneyness" (K/F), "log_moneyness", "iv", "side", "delta"}] (OTM, valid quotes),
    "skew": {"rr25" (IV 25d call - IV 25d put), "bf25" ((IV25c + IV25p)/2 - ATM), "put_skew_90"
    (IV at K/F = 0.90 minus ATM), "call_skew_110" (IV at K/F = 1.10 minus ATM), "iv_25d_call",
    "iv_25d_put", "iv_90", "iv_110"},
    "implied_move" (ATM straddle mid / spot), "straddle", "expected_range" ([spot - straddle,
    spot + straddle]), "one_sigma_move" (S * atm_iv * sqrt(T)),
    "put_call": {"volume_ratio", "oi_ratio", "call_volume", "put_volume", "call_oi", "put_oi"},
    "max_pain" (strike minimising the intrinsic value paid to holders at expiry),
    "gex": {"by_strike": [{"strike", "call", "put", "net"}], "total", "flip"} (naive dealer convention:
    dealers long calls / short puts, GEX = gamma * OI * 100 * S^2 * 0.01 in $ per 1 % move; ``flip`` is
    the spot level where total GEX, re-evaluated on a 0.7S-1.3S grid at fixed IVs, changes sign),
    "oi_by_strike": [{"strike", "call_oi", "put_oi", "call_volume", "put_volume"}],
    "unusual": [{"contract", "side", "strike", "volume", "oi", "vol_oi", "iv", "mid"}] (volume >= 2 * OI
    and volume >= 100, top 15 by volume),
    "quality": {"n_quotes", "n_valid", "median_spread_pct", "stale_share"}, "warnings": [...]}.
    """
    core = _core(calls, puts, spot, expiry, asof, r, q)
    K, c, p, n, S = core["K"], core["c"], core["p"], core["n"], core["S"]
    out = _summary(core)
    out["forward_source"] = core["F_src"]
    out["q_implied"] = core["q_eff"] if core["F_src"] == "parity" else None

    # ---- per-strike rows (columnar build, then zipped)
    cols: dict[str, list] = {"strike": K.tolist()}
    with np.errstate(invalid="ignore"):
        itm = {"c": np.where(c["present"], K < S, None), "p": np.where(p["present"], K > S, None)}
    for side, d, name in (("c", c, "call"), ("p", p, "put")):
        pres = d["present"]

        def col(a, pres=pres):
            return _clean_list(np.where(pres, a, np.nan))

        cols[f"{name}_bid"] = col(d["bid"])
        cols[f"{name}_ask"] = col(d["ask"])
        cols[f"{name}_mid"] = col(d["mid"])
        cols[f"{name}_last"] = col(d["last"])
        cols[f"{name}_volume"] = col(d["vol"])
        cols[f"{name}_oi"] = col(d["oi"])
        cols[f"{name}_iv"] = col(d["iv"])
        cols[f"{name}_delta"] = col(d["delta"])
        cols[f"{name}_gamma"] = col(d["gamma"])
        cols[f"{name}_theta"] = col(d["theta"])
        cols[f"{name}_vega"] = col(d["vega"])
        cols[f"{name}_itm"] = [None if v is None else bool(v) for v in itm[side].tolist()]
        cols[f"{name}_stale"] = [bool(s) if pr else None for s, pr in zip(d["stale"].tolist(), pres.tolist())]
        cols[f"{name}_iv_source"] = d["iv_src"].tolist()
        cols[f"{name}_contract"] = [ct if pr else None for ct, pr in zip(d["contract"].tolist(), pres.tolist())]
    names = list(cols)
    out["rows"] = [dict(zip(names, vals)) for vals in zip(*(cols[k] for k in names))] if n else []

    out["smile"] = [{"strike": float(k), "moneyness": float(k / core["F"]), "log_moneyness": float(lm),
                     "iv": float(v), "side": sd, "delta": float(dl)}
                    for k, lm, v, sd, dl in zip(core["sm_k"], core["sm_lm"], core["sm_iv"], core["sm_side"],
                                                core["sm_delta"])]
    out["skew"] = core["skew"]
    out["put_call"] = {"volume_ratio": _ratio(core["put_volume"], core["call_volume"]),
                       "oi_ratio": _ratio(core["put_oi"], core["call_oi"]),
                       "call_volume": core["call_volume"], "put_volume": core["put_volume"],
                       "call_oi": core["call_oi"], "put_oi": core["put_oi"]}
    out["max_pain"] = _max_pain(K, c["oi"], p["oi"])
    if n and out["max_pain"] is None:
        core["warnings"].append("no open interest; max pain unavailable")
    out["gex"] = safe(_gex, core, default={"by_strike": [], "total": None, "flip": None})
    out["oi_by_strike"] = [{"strike": k, "call_oi": co, "put_oi": po, "call_volume": cv, "put_volume": pv}
                           for k, co, po, cv, pv in zip(K.tolist(), _clean_list(c["oi"]), _clean_list(p["oi"]),
                                                        _clean_list(c["vol"]), _clean_list(p["vol"]))]

    # ---- unusual activity
    vol = np.concatenate([c["vol"], p["vol"]])
    oi = np.concatenate([c["oi"], p["oi"]])
    pres = np.concatenate([c["present"], p["present"]])
    with np.errstate(invalid="ignore"):
        mask = pres & (vol >= 100) & (vol >= 2.0 * np.nan_to_num(oi))
    idx = np.flatnonzero(mask)
    idx = idx[np.argsort(-vol[idx], kind="stable")][:15]
    ivs = np.concatenate([c["iv"], p["iv"]])
    mids = np.concatenate([c["mid"], p["mid"]])
    contracts = np.concatenate([c["contract"], p["contract"]])
    out["unusual"] = [{"contract": contracts[i], "side": "call" if i < n else "put", "strike": float(K[i % n]),
                       "volume": float(vol[i]), "oi": clean(oi[i]),
                       "vol_oi": (float(vol[i] / oi[i]) if np.isfinite(oi[i]) and oi[i] > 0 else None),
                       "iv": clean(ivs[i]), "mid": clean(mids[i])} for i in idx]

    # ---- quote quality
    n_quotes = int(c["present"].sum() + p["present"].sum())
    n_valid = int(c["valid"].sum() + p["valid"].sum())
    bid = np.concatenate([c["bid"], p["bid"]])
    ask = np.concatenate([c["ask"], p["ask"]])
    v2 = np.concatenate([c["valid"], p["valid"]])
    spreads = (ask[v2] - bid[v2]) / (0.5 * (ask[v2] + bid[v2]))
    out["quality"] = {"n_quotes": n_quotes, "n_valid": n_valid,
                      "median_spread_pct": float(np.median(spreads)) if spreads.size else None,
                      "stale_share": (1.0 - n_valid / n_quotes) if n_quotes else None}
    if n_quotes and n_valid < n_quotes:
        core["warnings"].append(f"{n_quotes - n_valid} of {n_quotes} contracts lack a valid two-sided quote "
                                "(mid = last trade, flagged stale)")
    out["warnings"] = core["warnings"]
    return jsonable(out)


# =============================================================================== term structure
def _unpack(v) -> tuple[Any, Any]:
    if isinstance(v, dict):
        return v.get("calls"), v.get("puts")
    if isinstance(v, (tuple, list)) and len(v) == 2:
        return v[0], v[1]
    return None, None


def _sorted_chains(chains) -> list[tuple[str, Any, Any]]:
    items = []
    for e, v in (chains or {}).items():
        ts = safe(pd.Timestamp, e)
        if ts is None or ts is pd.NaT:
            continue
        cl, pt = _unpack(v)
        items.append((ts, str(pd.Timestamp(e).strftime("%Y-%m-%d")), cl, pt))
    items.sort(key=lambda x: x[0])
    return [(e, cl, pt) for _, e, cl, pt in items]


def _event_ts(earnings_date) -> pd.Timestamp | None:
    """Earnings time in New York; a date without a time (or midnight) is taken as after the close."""
    if earnings_date is None:
        return None
    t = pd.Timestamp(earnings_date)
    t = _ny(t)
    no_time = (isinstance(earnings_date, date) and not isinstance(earnings_date, datetime)) or \
              (isinstance(earnings_date, str) and len(earnings_date.strip()) <= 10) or \
              (t.hour == 0 and t.minute == 0 and t.second == 0)
    if no_time:
        t = pd.Timestamp(datetime.combine(t.date(), dtime(16, 0))).tz_localize(NY)
    return t


def term_structure(chains: dict, spot: float, asof, r: float = 0.04, q: float = 0.0,
                   earnings_date: str | None = None) -> dict:
    """ATM term structure across expiries, forward vols and the earnings-implied event move.

    ``chains`` maps expiry -> (calls, puts) or {"calls": df, "puts": df}. Expired or empty expiries
    are skipped (warning).

    Forward vol between expiries T1 < T2: sqrt((s2^2 T2 - s1^2 T1) / (T2 - T1)); None (with a warning)
    when negative total variance makes it undefined (calendar arbitrage / inverted term structure).

    Earnings event variance (term-structure kink): with ``pre`` the last expiry before the
    announcement and ``post`` the first after it, and a flat base vol s1 (the pre-event ATM vol),
    the post expiry's total variance is s2^2 T2 = s1^2 T2 + sigma_E^2, so
    sigma_E^2 = T2 (s2^2 - s1^2): the variance of a one-day event move. The expected absolute event
    move of a normal jump is sigma_E * sqrt(2/pi). When no expiry precedes the event but two follow
    it, the base vol is backed out from those two (method "two_post"). A date without a time (or a
    midnight time) is treated as after the close (16:00 New York); pass an ISO datetime before
    09:30 for a pre-market report.

    Returns {"rows": [{"expiry", "dte", "atm_iv", "implied_move", "straddle", "rr25", "pc_oi_ratio",
    "total_oi", "total_volume", "T", "forward"}], "forward_vols": [{"from", "to", "fwd_vol"}],
    "earnings": {"date", "pre_expiry", "post_expiry", "event_vol" (sigma_E, one-day standard deviation
    as a fraction), "event_vol_annualized" (sigma_E * sqrt(252)), "implied_event_move", "method",
    "note"} or None (no earnings_date), "warnings": [...]}.
    """
    warns: list[str] = []
    rows = []
    for exp, cl, pt in _sorted_chains(chains):
        core = safe(_core, cl, pt, spot, exp, asof, r, q)
        if core is None or core["n"] == 0:
            warns.append(f"{exp}: empty or unreadable chain skipped")
            continue
        if core["expired"]:
            warns.append(f"{exp}: expired, skipped")
            continue
        sm = _summary(core)
        rows.append({"expiry": exp, "dte": sm["dte"], "atm_iv": sm["atm_iv"], "implied_move": sm["implied_move"],
                     "straddle": sm["straddle"], "rr25": core["skew"]["rr25"],
                     "pc_oi_ratio": _ratio(core["put_oi"], core["call_oi"]),
                     "total_oi": core["call_oi"] + core["put_oi"],
                     "total_volume": core["call_volume"] + core["put_volume"], "T": core["T"], "forward": core["F"]})

    good = [rw for rw in rows if rw["atm_iv"] is not None and np.isfinite(rw["atm_iv"])]
    fwd = []
    for a, b in zip(good[:-1], good[1:]):
        dT = b["T"] - a["T"]
        var = (b["atm_iv"] ** 2 * b["T"] - a["atm_iv"] ** 2 * a["T"]) / dT if dT > 0 else _NAN
        fv = math.sqrt(var) if np.isfinite(var) and var > 0 else None
        if fv is None:
            warns.append(f"negative forward variance between {a['expiry']} and {b['expiry']} (calendar arbitrage)")
        fwd.append({"from": a["expiry"], "to": b["expiry"], "fwd_vol": fv})

    earnings = None
    if earnings_date is not None:
        earnings = {"date": None, "pre_expiry": None, "post_expiry": None, "event_vol": None,
                    "event_vol_annualized": None, "implied_event_move": None, "method": None, "note": None}
        ev = safe(_event_ts, earnings_date)
        if ev is None:
            earnings["note"] = "unparseable earnings date"
        else:
            earnings["date"] = ev.strftime("%Y-%m-%dT%H:%M:%S")
            pre = [rw for rw in good if _expiry_ts(rw["expiry"]) <= ev]
            post = [rw for rw in good if _expiry_ts(rw["expiry"]) > ev]
            var_e, method = None, None
            if pre and post:
                a, b = pre[-1], post[0]
                earnings["pre_expiry"], earnings["post_expiry"] = a["expiry"], b["expiry"]
                var_e, method = b["T"] * (b["atm_iv"] ** 2 - a["atm_iv"] ** 2), "kink"
            elif len(post) >= 2:
                a, b = post[0], post[1]
                earnings["post_expiry"] = a["expiry"]
                base = (b["atm_iv"] ** 2 * b["T"] - a["atm_iv"] ** 2 * a["T"]) / (b["T"] - a["T"])
                var_e, method = a["atm_iv"] ** 2 * a["T"] - base * a["T"], "two_post"
            else:
                earnings["note"] = "no expiry after the earnings date" if not post else \
                    "need an expiry before the event or two after it"
            if var_e is not None:
                earnings["method"] = method
                if var_e > 0:
                    se = math.sqrt(var_e)
                    earnings.update(event_vol=se, event_vol_annualized=se * math.sqrt(252.0),
                                    implied_event_move=se * math.sqrt(2.0 / math.pi))
                else:
                    earnings["note"] = "post-event ATM variance is not above the base variance; no event premium"
    return jsonable({"rows": rows, "forward_vols": fwd, "earnings": earnings, "warnings": warns})


def iv_surface(chains: dict, spot: float, asof, r: float = 0.04, q: float = 0.0, moneyness=None) -> dict:
    """Implied-volatility surface on a moneyness (K/F) x expiry grid from each expiry's OTM smile.

    Each expiry's smile (OTM puts below the forward, OTM calls above, valid two-sided quotes only) is
    interpolated linearly in log-moneyness ln(K/F); no extrapolation, so grid points outside a smile's
    strike range are None. Expiries with fewer than two smile points are skipped (warning).

    Returns {"moneyness": [...] (default 0.70..1.30, 25 points), "dte": [...], "expiries": [...],
    "iv": [[...]] (rows = expiries, columns = moneyness), "warnings": [...]}.
    """
    m = np.round(np.linspace(0.7, 1.3, 25), 6) if moneyness is None else np.asarray(moneyness, dtype=float).ravel()
    lm = np.log(np.where(m > 0, m, np.nan))
    warns, dtes, exps, grid = [], [], [], []
    for exp, cl, pt in _sorted_chains(chains):
        core = safe(_core, cl, pt, spot, exp, asof, r, q)
        if core is None or core["sm_k"].size < 2:
            warns.append(f"{exp}: fewer than two OTM smile points, skipped")
            continue
        if core["expired"]:
            warns.append(f"{exp}: expired, skipped")
            continue
        x, y = core["sm_lm"], core["sm_iv"]
        ux, inv = np.unique(x, return_inverse=True)
        uy = np.bincount(inv, weights=y) / np.bincount(inv)
        row = [_interp(ux, uy, v) for v in lm]
        exps.append(exp)
        dtes.append(round(core["T"] * 365.0, 4))
        grid.append(row)
    return jsonable({"moneyness": m.tolist(), "dte": dtes, "expiries": exps, "iv": grid, "warnings": warns})
