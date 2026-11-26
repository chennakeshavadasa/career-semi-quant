"""Cross-sectional universe metrics, market breadth and the composite quant score.

Windows are in trading sessions: 1d = 1, 5d = 5, 1m = 21, 3m = 63, 6m = 126, 1y = 252. Returns are
simple, volatilities annualised with sqrt(252), all values fractions. Everything is vectorised over the
universe (numpy on the sessions x tickers matrix).

Session cleaning: all-NaN columns and non-positive prices are dropped; rows where fewer than half of
the tickers that have started trading have a price are treated as non-sessions (e.g. US holidays when
only futures / FX / VIX columns print) and removed; gaps of up to 5 sessions are forward-filled.

Composite score: each component is the average percentile rank (0-100, 50 = median) of its inputs
within the universe, inverted where lower is better; a missing input scores 50. The composite is the
weighted mean of the components (``default_weights``).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ._util import TRADING_DAYS, clean, jsonable, ser

__all__ = ["universe_metrics", "breadth", "quant_score", "default_weights", "score_explain"]

METRIC_COLS = ["last", "ret_1d", "ret_5d", "ret_1m", "ret_3m", "ret_6m", "ret_ytd", "ret_1y", "mom_12_1", "vol_1m",
               "vol_3m", "vol_1y", "beta_1y", "corr_1y", "rsi14", "pct_from_52w_high", "pct_from_52w_low", "pos_52w",
               "above_sma50", "above_sma200", "sma50_over_200", "max_dd_1y", "sharpe_1y", "rel_strength_3m", "trend"]

COMPONENTS: dict[str, list[tuple[str, int]]] = {
    "momentum": [("mom_12_1", 1), ("ret_6m", 1)],
    "trend": [("sma50_over_200", 1), ("above_sma200", 1)],
    "value": [("earnings_yield", 1), ("fcf_yield", 1), ("ev_sales", -1)],
    "quality": [("gross_margin", 1), ("operating_margin", 1), ("roe", 1)],
    "growth": [("rev_growth", 1), ("eps_growth", 1)],
    "revisions": [("eps_rev_30d", 1)],
    "analyst": [("target_upside", 1), ("rec_mean", -1)],
    "low_vol": [("vol_3m", -1)],
}
LABELS = {"momentum": "Momentum", "trend": "Trend", "value": "Value", "quality": "Quality", "growth": "Growth",
          "revisions": "Estimate revisions", "analyst": "Analyst view", "low_vol": "Low volatility"}
_GOOD_BAD = {"momentum": ("Strong momentum", "Weak momentum"), "trend": ("Uptrend", "Downtrend"),
             "value": ("Attractive valuation", "Expensive valuation"), "quality": ("High quality", "Low quality"),
             "growth": ("Strong growth", "Weak growth"), "revisions": ("Rising estimates", "Falling estimates"),
             "analyst": ("Positive analyst view", "Negative analyst view"),
             "low_vol": ("Low volatility", "High volatility")}


def default_weights() -> dict:
    """Composite weights (sum 1): momentum .20, trend .10, value .15, quality .15, growth .10,
    revisions .15, analyst .05, low_vol .10."""
    return {"momentum": 0.20, "trend": 0.10, "value": 0.15, "quality": 0.15, "growth": 0.10, "revisions": 0.15,
            "analyst": 0.05, "low_vol": 0.10}


# =============================================================================== cleaning
def _sessions(prices: pd.DataFrame) -> pd.DataFrame:
    if prices is None or not isinstance(prices, pd.DataFrame) or prices.empty:
        return pd.DataFrame()
    P = prices
    try:
        P = P.astype(float)
    except (ValueError, TypeError):
        P = P.apply(pd.to_numeric, errors="coerce")
    P = P[~P.index.duplicated(keep="last")].sort_index()
    P = P.where(P > 0)
    P = P.loc[:, P.notna().any()]
    if P.empty:
        return P
    valid = P.notna().to_numpy()
    alive = np.maximum.accumulate(valid, axis=0).sum(axis=1)
    keep = (valid.sum(axis=1) >= 0.5 * alive) & (alive > 0)
    return P[keep].ffill(limit=5)


def _bench(b, index: pd.DatetimeIndex) -> np.ndarray | None:
    if b is None:
        return None
    s = pd.to_numeric(pd.Series(b), errors="coerce")
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s = s.where(s > 0).dropna()
    if s.empty:
        return None
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
        s = s.tz_localize(None)
    return s.reindex(index, method="ffill", limit=5).to_numpy(float)


def _ret(X: np.ndarray, k: int) -> np.ndarray:
    n = X.shape[0]
    if n <= k:
        return np.full(X.shape[1], np.nan)
    with np.errstate(all="ignore"):
        return X[-1] / X[-1 - k] - 1.0


def _win(A: np.ndarray, k: int, min_frac: float = 0.8):
    """Last k rows plus a per-column 'enough data' mask (>= min_frac finite)."""
    W = A[-k:] if A.shape[0] >= k else A
    enough = (np.isfinite(W).sum(axis=0) >= min_frac * k) & (A.shape[0] >= k)
    return W, enough


def _colwise(func, W: np.ndarray, min_count: int = 1, **kw) -> np.ndarray:
    """``func(W, axis=0)`` on columns with at least ``min_count`` finite values (NaN elsewhere), which
    avoids numpy's all-NaN warnings."""
    out = np.full(W.shape[1], np.nan)
    ok = np.isfinite(W).sum(axis=0) >= min_count
    if ok.any():
        out[ok] = func(W[:, ok], axis=0, **kw)
    return out


def _nanstd(W: np.ndarray) -> np.ndarray:
    return _colwise(np.nanstd, W, 2, ddof=1)


def _sma(X: np.ndarray, k: int) -> np.ndarray:
    if X.shape[0] < k:
        return np.full(X.shape[1], np.nan)
    W = X[-k:]
    ok = np.isfinite(W).all(axis=0)
    with np.errstate(all="ignore"):
        return np.where(ok, W.mean(axis=0), np.nan)


# =============================================================================== metrics
def universe_metrics(prices: pd.DataFrame, bench: pd.Series | None = None, sector_bench: pd.Series | None = None,
                     rf: float = 0.04) -> pd.DataFrame:
    """One row per ticker (index "ticker") of price-based metrics, computed vectorised.

    Columns: last; ret_1d, ret_5d, ret_1m (21), ret_3m (63), ret_6m (126), ret_1y (252); ret_ytd (vs the
    last close of the previous calendar year); mom_12_1 (P[t-21] / P[t-252] - 1, Jegadeesh-Titman
    12-1 momentum); vol_1m, vol_3m, vol_1y (annualised std of daily returns); beta_1y, corr_1y (vs
    ``bench`` prices, 252 daily returns, pairwise complete); rsi14 (Wilder); pct_from_52w_high (<= 0) and
    pct_from_52w_low (>= 0) vs the 252-session closing range, pos_52w (0 = at the low, 1 = at the high);
    above_sma50, above_sma200 (bool); sma50_over_200 (SMA50 / SMA200 - 1); max_dd_1y (worst drawdown in
    the last 252 sessions, <= 0); sharpe_1y ((mean daily return x 252 - rf) / vol_1y); rel_strength_3m
    ((1 + ret_3m) / (1 + sector_bench 3m return) - 1); trend ("up" if price > SMA50 > SMA200, "down" if
    price < SMA50 < SMA200, else "range"). Windows need >= 80 % valid prices, else NaN / None.
    """
    P = _sessions(prices)
    if P.empty:
        return pd.DataFrame(columns=METRIC_COLS, index=pd.Index([], name="ticker"))
    X = P.to_numpy(float)
    n, k = X.shape
    with np.errstate(all="ignore"):
        R = X[1:] / X[:-1] - 1.0
    last = X[-1]
    out: dict[str, np.ndarray] = {"last": last}
    for name, w in (("ret_1d", 1), ("ret_5d", 5), ("ret_1m", 21), ("ret_3m", 63), ("ret_6m", 126), ("ret_1y", 252)):
        out[name] = _ret(X, w)
    yr0 = pd.Timestamp(year=P.index[-1].year, month=1, day=1)
    pos = int(P.index.searchsorted(yr0, side="left")) - 1
    with np.errstate(all="ignore"):
        out["ret_ytd"] = last / X[pos] - 1.0 if pos >= 0 else np.full(k, np.nan)
        out["mom_12_1"] = X[-22] / X[-253] - 1.0 if n >= 253 else np.full(k, np.nan)
    for name, w in (("vol_1m", 21), ("vol_3m", 63), ("vol_1y", 252)):
        W, ok = _win(R, w)
        out[name] = np.where(ok, _nanstd(W) * math.sqrt(TRADING_DAYS), np.nan)

    # beta / correlation vs bench over the last 252 daily returns
    b = _bench(bench, P.index)
    beta = corr = np.full(k, np.nan)
    if b is not None and n > 30:
        with np.errstate(all="ignore"):
            rb = b[1:] / b[:-1] - 1.0
        W, Wb = R[-252:], rb[-252:]
        M = np.isfinite(W) & np.isfinite(Wb)[:, None]
        cnt = M.sum(axis=0)
        Wz, Bz = np.where(M, W, 0.0), np.where(M, Wb[:, None], 0.0)
        with np.errstate(all="ignore"):
            mx, mb = Wz.sum(0) / cnt, Bz.sum(0) / cnt
            dx, db = np.where(M, W - mx, 0.0), np.where(M, Wb[:, None] - mb, 0.0)
            cxy, vx, vb = (dx * db).sum(0), (dx * dx).sum(0), (db * db).sum(0)
            ok = cnt >= 0.8 * min(252, R.shape[0])
            beta = np.where(ok & (vb > 0), cxy / vb, np.nan)
            corr = np.where(ok & (vb > 0) & (vx > 0), cxy / np.sqrt(vx * vb), np.nan)
    out["beta_1y"], out["corr_1y"] = beta, corr

    # Wilder RSI(14)
    d = P.diff()
    up = d.clip(lower=0.0).ewm(alpha=1.0 / 14, adjust=False, min_periods=14).mean().iloc[-1].to_numpy()
    dn = (-d).clip(lower=0.0).ewm(alpha=1.0 / 14, adjust=False, min_periods=14).mean().iloc[-1].to_numpy()
    with np.errstate(all="ignore"):
        rsi = np.where(dn > 0, 100.0 - 100.0 / (1.0 + up / dn), np.where(up > 0, 100.0, 50.0))
    out["rsi14"] = np.where(np.isfinite(up) & np.isfinite(dn), rsi, np.nan)

    W, ok = _win(X, 252)
    hi, lo = _colwise(np.nanmax, W), _colwise(np.nanmin, W)
    with np.errstate(all="ignore"):
        out["pct_from_52w_high"] = np.where(ok, last / hi - 1.0, np.nan)
        out["pct_from_52w_low"] = np.where(ok, last / lo - 1.0, np.nan)
        out["pos_52w"] = np.where(ok & (hi > lo), (last - lo) / (hi - lo), np.where(ok, 0.5, np.nan))
        dd = W / np.fmax.accumulate(W, axis=0) - 1.0
    out["max_dd_1y"] = np.where(ok, _colwise(np.nanmin, dd), np.nan)
    s50, s200 = _sma(X, 50), _sma(X, 200)
    with np.errstate(all="ignore"):
        out["above_sma50"] = np.where(np.isfinite(s50) & np.isfinite(last), last > s50, None)
        out["above_sma200"] = np.where(np.isfinite(s200) & np.isfinite(last), last > s200, None)
        out["sma50_over_200"] = s50 / s200 - 1.0
    Wr, okr = _win(R, 252)
    mu, sd = _colwise(np.nanmean, Wr) * TRADING_DAYS, _nanstd(Wr) * math.sqrt(TRADING_DAYS)
    with np.errstate(all="ignore"):
        out["sharpe_1y"] = np.where(okr & (sd > 0), (mu - (clean(rf) or 0.0)) / sd, np.nan)
    sb = _bench(sector_bench, P.index)
    if sb is not None and n > 63 and np.isfinite(sb[-1]) and np.isfinite(sb[-64]):
        with np.errstate(all="ignore"):
            out["rel_strength_3m"] = (1.0 + out["ret_3m"]) / (sb[-1] / sb[-64]) - 1.0
    else:
        out["rel_strength_3m"] = np.full(k, np.nan)
    fin = np.isfinite(last) & np.isfinite(s50) & np.isfinite(s200)
    up_t = fin & (last > s50) & (s50 > s200)
    dn_t = fin & (last < s50) & (s50 < s200)
    out["trend"] = np.where(up_t, "up", np.where(dn_t, "down", np.where(fin, "range", None))).astype(object)
    df = pd.DataFrame({c: out[c] for c in METRIC_COLS}, index=pd.Index([str(c) for c in P.columns], name="ticker"))
    for c in ("above_sma50", "above_sma200"):
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def breadth(prices: pd.DataFrame) -> dict:
    """Market breadth of a universe.

    Returns {"n" (tickers with a current price), "pct_above_sma20", "pct_above_sma50",
    "pct_above_sma200" (fractions of tickers above the moving average, among those with enough history),
    "advancers", "decliners" (1-day), "new_highs_52w", "new_lows_52w" (last close at the 252-session
    closing high / low), "avg_corr_63d" (mean pairwise correlation of daily returns over 63 sessions),
    "dispersion_1m" (cross-sectional std of 1-month returns), "pct_above_sma50_series": ser (daily share
    above the 50-day SMA, last 252 sessions), "asof"}.
    """
    out = {"n": 0, "pct_above_sma20": None, "pct_above_sma50": None, "pct_above_sma200": None, "advancers": 0,
           "decliners": 0, "new_highs_52w": 0, "new_lows_52w": 0, "avg_corr_63d": None, "dispersion_1m": None,
           "pct_above_sma50_series": ser(None), "asof": None}
    P = _sessions(prices)
    if P.empty:
        return jsonable(out)
    X = P.to_numpy(float)
    last = X[-1]
    live = np.isfinite(last)
    out["n"] = int(live.sum())
    out["asof"] = P.index[-1]
    for k in (20, 50, 200):
        s = _sma(X, k)
        ok = live & np.isfinite(s)
        out[f"pct_above_sma{k}"] = float((last[ok] > s[ok]).mean()) if ok.any() else None
    r1 = _ret(X, 1)
    out["advancers"], out["decliners"] = int((r1 > 0).sum()), int((r1 < 0).sum())
    W, ok = _win(X, 252)
    hi, lo = _colwise(np.nanmax, W), _colwise(np.nanmin, W)
    out["new_highs_52w"] = int((ok & live & (last >= hi)).sum())
    out["new_lows_52w"] = int((ok & live & (last <= lo)).sum())
    rets = P.pct_change(fill_method=None).iloc[-63:]
    if P.shape[1] > 1 and len(rets) >= 20:
        cm = rets.corr(min_periods=40).to_numpy()
        off = cm[~np.eye(cm.shape[0], dtype=bool)]
        off = off[np.isfinite(off)]
        out["avg_corr_63d"] = float(off.mean()) if off.size else None
    r21 = _ret(X, 21)
    r21 = r21[np.isfinite(r21)]
    out["dispersion_1m"] = float(np.std(r21, ddof=1)) if r21.size > 1 else None
    sma50 = P.rolling(50, min_periods=50).mean()
    valid = sma50.notna() & P.notna()
    above = (P > sma50) & valid
    cnt = valid.sum(axis=1)
    share = (above.sum(axis=1) / cnt).where(cnt > 0).iloc[-252:].dropna()
    out["pct_above_sma50_series"] = ser(share)
    return jsonable(out)


# =============================================================================== composite score
def _pct(x: pd.Series) -> pd.Series:
    """Percentile rank 0..100 among valid values: (rank - 1) / (n - 1) x 100 (average ranks for ties); a
    single valid value scores 50; NaN stays NaN."""
    v = pd.to_numeric(x.map(lambda a: float(a) if isinstance(a, (bool, np.bool_)) else a), errors="coerce")
    v = v.replace([np.inf, -np.inf], np.nan)
    n = int(v.notna().sum())
    if n == 0:
        return v * np.nan
    if n == 1:
        return v.where(v.isna(), 50.0)
    return (v.rank(method="average") - 1.0) / (n - 1.0) * 100.0


def quant_score(metrics: pd.DataFrame, fundamentals: pd.DataFrame | None = None, weights: dict | None = None) -> pd.DataFrame:
    """Composite quant score (0-100) per ticker from cross-sectional percentile ranks.

    Components and inputs (``-`` = lower is better, so the percentile is inverted):
    momentum: mom_12_1, ret_6m; trend: sma50_over_200, above_sma200; low_vol: -vol_3m;
    value: earnings_yield, fcf_yield, -ev_sales; quality: gross_margin, operating_margin, roe;
    growth: rev_growth, eps_growth; revisions: eps_rev_30d; analyst: target_upside, -rec_mean
    (1 = strong buy). Inputs come from ``metrics`` (``universe_metrics`` output) and the optional
    ``fundamentals`` frame (index = ticker; it wins for overlapping columns). Each component = mean of
    its available input percentiles; a missing input scores 50, so a component with no data is 50.
    score = weighted mean of the components with ``weights`` (``default_weights()`` when None; a given
    dict is the full specification, normalised to sum 1; unknown names are ignored).

    Returns a DataFrame indexed by ticker, sorted by score (best first): score, rank, the eight
    components, then the raw input columns that were present (used by ``score_explain``).
    """
    comps = list(COMPONENTS)
    if metrics is None or not isinstance(metrics, pd.DataFrame) or metrics.empty:
        base = metrics.index if isinstance(metrics, pd.DataFrame) else pd.Index([], name="ticker")
        return pd.DataFrame(columns=["score", "rank", *comps], index=base)
    df = metrics.copy()
    df.index = df.index.map(str)
    if isinstance(fundamentals, pd.DataFrame) and not fundamentals.empty:
        f = fundamentals.copy()
        f.index = f.index.map(str)
        f = f[~f.index.duplicated(keep="last")].reindex(df.index)
        df = df.drop(columns=[c for c in f.columns if c in df.columns]).join(f)
    w = default_weights() if not weights else {k: float(v) for k, v in weights.items() if k in COMPONENTS
                                               and clean(v) is not None and float(v) >= 0}
    tot = sum(w.values())
    w = {k: v / tot for k, v in w.items()} if tot > 0 else default_weights()
    res = pd.DataFrame(index=df.index)
    used: list[str] = []
    for c, inputs in COMPONENTS.items():
        parts = []
        for col, sign in inputs:
            if col in df.columns:
                p = _pct(df[col])
                parts.append(p if sign > 0 else 100.0 - p)
                used.append(col)
        if parts:
            res[c] = pd.concat(parts, axis=1).fillna(50.0).mean(axis=1)
        else:
            res[c] = 50.0
    res["score"] = sum(res[c] * w.get(c, 0.0) for c in comps)
    res = res.sort_values("score", ascending=False, kind="stable")
    res["rank"] = np.arange(1, len(res) + 1)
    raw = df.loc[res.index, list(dict.fromkeys(used))]
    out = pd.concat([res[["score", "rank", *comps]], raw], axis=1)
    out.index.name = "ticker"
    out.attrs["weights"] = w
    return out


def _fmt(v, kind: str) -> str | None:
    x = clean(v) if not isinstance(v, (bool, np.bool_)) else float(v)
    if x is None:
        return None
    if kind == "pct":
        return f"{x:+.1%}"
    if kind == "pct0":
        return f"{x:.0%}"
    if kind == "x":
        return f"{x:.1f}x"
    return f"{x:.2f}"


def _phrase(comp: str, row: pd.Series) -> str:
    g = row.get
    bits = []
    if comp == "momentum":
        bits = [("12-1 month return", _fmt(g("mom_12_1"), "pct")), ("6-month return", _fmt(g("ret_6m"), "pct"))]
    elif comp == "trend":
        s = _fmt(g("sma50_over_200"), "pct")
        bits = [("50-day vs 200-day average", s)]
        a = g("above_sma200")
        if a is not None and not (isinstance(a, float) and math.isnan(a)):
            bits.append(("price", "above the 200-day average" if bool(a) else "below the 200-day average"))
    elif comp == "low_vol":
        bits = [("3-month volatility", _fmt(g("vol_3m"), "pct0"))]
    elif comp == "value":
        bits = [("earnings yield", _fmt(g("earnings_yield"), "pct")), ("FCF yield", _fmt(g("fcf_yield"), "pct")),
                ("EV/sales", _fmt(g("ev_sales"), "x"))]
    elif comp == "quality":
        bits = [("gross margin", _fmt(g("gross_margin"), "pct0")), ("operating margin", _fmt(g("operating_margin"), "pct0")),
                ("ROE", _fmt(g("roe"), "pct0"))]
    elif comp == "growth":
        bits = [("revenue growth", _fmt(g("rev_growth"), "pct")), ("EPS growth", _fmt(g("eps_growth"), "pct"))]
    elif comp == "revisions":
        bits = [("30-day EPS estimate revision", _fmt(g("eps_rev_30d"), "pct"))]
    elif comp == "analyst":
        bits = [("target upside", _fmt(g("target_upside"), "pct")), ("mean rating (1 = strong buy)", _fmt(g("rec_mean"), "f"))]
    return ", ".join(f"{k} {v}" if k != "price" else v for k, v in bits if v is not None)


def score_explain(row: pd.Series, weights: dict | None = None) -> dict:
    """Plain-English breakdown of one ``quant_score`` row (e.g. ``scores.loc["NVDA"]``).

    Returns {"ticker", "score", "rank", "components": [{"name", "label", "score", "weight", "inputs":
    {input: raw value}}], "strengths": [...], "weaknesses": [...]}: components scoring >= 70 with data are
    strengths, <= 30 weaknesses (strongest / weakest first), each a one-line sentence such as
    "Strong momentum: 12-1 month return +45.2%, 6-month return +20.1% (percentile 91 in the universe)".
    ``weights`` defaults to ``default_weights()``.
    """
    if row is None:
        row = pd.Series(dtype=object)
    if isinstance(row, dict):
        row = pd.Series(row)
    w = default_weights() if not weights else {k: float(v) for k, v in weights.items() if k in COMPONENTS}
    tot = sum(w.values()) or 1.0
    comps, strengths, weaknesses = [], [], []
    for c, inputs in COMPONENTS.items():
        sc = clean(row.get(c))
        ins = {col: (bool(row.get(col)) if isinstance(row.get(col), (bool, np.bool_)) else clean(row.get(col)))
               for col, _ in inputs if col in row.index}
        comps.append({"name": c, "label": LABELS[c], "score": sc, "weight": w.get(c, 0.0) / tot, "inputs": ins})
        has_data = any(v is not None for v in ins.values())
        if sc is None or not has_data:
            continue
        detail = _phrase(c, row)
        detail = f": {detail}" if detail else ""
        if sc >= 70:
            strengths.append((sc, f"{_GOOD_BAD[c][0]}{detail} (percentile {sc:.0f} in the universe)"))
        elif sc <= 30:
            weaknesses.append((sc, f"{_GOOD_BAD[c][1]}{detail} (percentile {sc:.0f} in the universe)"))
    strengths.sort(key=lambda t: -t[0])
    weaknesses.sort(key=lambda t: t[0])
    rank = clean(row.get("rank"))
    return jsonable({"ticker": None if row.name is None else str(row.name), "score": clean(row.get("score")),
                     "rank": int(rank) if rank is not None else None, "components": comps, "strengths": [s for _, s in strengths],
                     "weaknesses": [s for _, s in weaknesses]})
