"""Technical indicators, a TradingView-style technical rating, price levels and trend state.

Indicator helpers (``sma`` ... ``supertrend``) return **pandas objects** (Series or DataFrame)
aligned to the input index (NaN during warm-up and on input rows that had no usable close).
They accept a close Series or an OHLCV frame (lowercase or Title-case columns); indicators that
need high/low/volume fall back to the close (high = low = close) when those columns are
missing, and volume-based ones return NaN without volume.

Result functions (``indicator_series``, ``signal_summary``, ``levels``, ``trend_state``) return
JSON-ready dicts (``jsonable``) and never raise.

Smoothing conventions (TradingView Pine definitions):
* ``ema``: recursive EMA, alpha = 2/(n+1), started at the first observation (pandas
  ``adjust=False``); the first n-1 values are masked (NaN).
* Wilder's RMA (RSI, ATR, ADX): alpha = 1/n, seeded with the simple mean of the first n values.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from ._util import clean, iso, jsonable, ohlcv

__all__ = ["sma", "ema", "rsi", "macd", "bollinger", "atr", "adx", "stochastic", "obv", "vwap", "williams_r",
           "cci", "mfi", "donchian", "keltner", "ichimoku", "supertrend", "indicator_series", "signal_summary",
           "levels", "trend_state"]


# --------------------------------------------------------------------------- input handling
def _naive(idx: pd.Index) -> pd.DatetimeIndex:
    di = pd.DatetimeIndex(idx)
    return di.tz_localize(None) if di.tz is not None else di


def _frame(df) -> pd.DataFrame:
    """Float OHLCV frame: sorted unique tz-naive DatetimeIndex, rows without a positive close
    dropped, missing/NaN open/high/low filled from the close, high/low widened to contain
    open and close. Volume is NaN when absent."""
    if isinstance(df, pd.Series):
        s = pd.to_numeric(df, errors="coerce")
        d = pd.DataFrame({"close": s})
    elif isinstance(df, pd.DataFrame):
        d = df.rename(columns={c: str(c).lower().replace("adj close", "adjclose") for c in df.columns})
        if "close" not in d.columns and "adjclose" in d.columns:
            d = d.rename(columns={"adjclose": "close"})
        if "close" not in d.columns:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
        d = ohlcv(d)
    else:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
    try:
        idx = _naive(d.index)
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
    out = pd.DataFrame(index=idx)
    close = pd.to_numeric(d["close"], errors="coerce").to_numpy(dtype=float)
    out["close"] = close
    for col in ("open", "high", "low"):
        if col in d.columns:
            v = pd.to_numeric(d[col], errors="coerce").to_numpy(dtype=float)
            v = np.where(np.isfinite(v) & (v > 0), v, close)
        else:
            v = close.copy()
        out[col] = v
    out["volume"] = pd.to_numeric(d["volume"], errors="coerce").to_numpy(dtype=float) if "volume" in d.columns \
        else np.nan
    out = out[np.isfinite(out["close"].to_numpy()) & (out["close"].to_numpy() > 0)]
    if out.index.has_duplicates or not out.index.is_monotonic_increasing:
        out = out[~out.index.duplicated(keep="last")].sort_index()
    o, h, l, c = (out[k].to_numpy() for k in ("open", "high", "low", "close"))
    out["high"] = np.maximum.reduce([h, o, c, l])
    out["low"] = np.minimum.reduce([l, o, c, h])
    return out[["open", "high", "low", "close", "volume"]]


def _restore(obj, src):
    """Reindex a result computed on cleaned data back onto the caller's index (when possible)."""
    try:
        idx = src.index
        if not isinstance(idx, pd.DatetimeIndex) or idx.has_duplicates or idx.tz is not None:
            return obj
        if len(idx) == len(obj.index) and idx.equals(obj.index):
            return obj
        return obj.reindex(idx)
    except Exception:  # noqa: BLE001
        return obj


def _close(x) -> pd.Series:
    return _frame(x)["close"]


def _rma(x: pd.Series, n: int) -> pd.Series:
    """Wilder's running moving average (alpha = 1/n) seeded with the SMA of the first n valid
    values (TradingView ``ta.rma``). Leading NaNs are skipped."""
    v = x.to_numpy(dtype=float)
    out = np.full(v.shape, np.nan)
    n = int(n)
    ok = np.flatnonzero(np.isfinite(v))
    if n < 1 or ok.size < n:
        return pd.Series(out, index=x.index)
    i0 = int(ok[0])
    seg = v[i0:]
    y = seg[n - 1:].copy()
    y[0] = np.nanmean(seg[:n])
    out[i0 + n - 1:] = pd.Series(y).ewm(alpha=1.0 / n, adjust=False, ignore_na=True).mean().to_numpy()
    return pd.Series(out, index=x.index)


def _ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(den) > 1e-300, num / np.where(den == 0, 1.0, den), np.nan)


# --------------------------------------------------------------------------- indicators
def sma(close, n: int) -> pd.Series:
    """Simple moving average over ``n`` bars (Series)."""
    c = _close(close)
    return _restore(c.rolling(int(n), min_periods=int(n)).mean().rename(f"sma{n}"), close)


def ema(close, n: int) -> pd.Series:
    """Exponential moving average, alpha = 2/(n+1), started at the first bar; first n-1 masked."""
    c = _close(close)
    return _restore(c.ewm(span=int(n), adjust=False, min_periods=int(n)).mean().rename(f"ema{n}"), close)


def _rsi_core(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0.0).iloc[1:]
    dn = (-d).clip(lower=0.0).iloc[1:]
    au = _rma(up, n).to_numpy()
    ad = _rma(dn, n).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - 100.0 / (1.0 + au / ad)
    r = np.where(ad == 0, np.where(au == 0, 50.0, 100.0), r)
    r = np.where(np.isfinite(au) & np.isfinite(ad), r, np.nan)
    return pd.Series(np.concatenate([[np.nan], r]) if len(c) else r, index=c.index, name=f"rsi{n}")


def rsi(close, n: int = 14) -> pd.Series:
    """Wilder's RSI (Wilder 1978): RMA of gains / RMA of losses, 0-100. A flat window (no gains
    and no losses) gives 50; no losses gives 100. First value at bar n."""
    return _restore(_rsi_core(_close(close), int(n)), close)


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD (Appel): ``macd`` = EMA(fast) - EMA(slow), ``signal`` = EMA(signal) of the MACD line
    (started at its first valid value), ``hist`` = macd - signal. DataFrame."""
    c = _close(close)
    line = c.ewm(span=int(fast), adjust=False, min_periods=int(fast)).mean() - \
        c.ewm(span=int(slow), adjust=False, min_periods=int(slow)).mean()
    valid = line.dropna()
    sig = valid.ewm(span=int(signal), adjust=False, min_periods=int(signal)).mean().reindex(c.index)
    out = pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig}, index=c.index)
    return _restore(out, close)


def bollinger(close, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Bollinger bands: ``mid`` = SMA(n), ``upper``/``lower`` = mid +/- k x population std (ddof 0),
    ``pctb`` = (close - lower) / (upper - lower), ``bandwidth`` = (upper - lower) / mid."""
    c = _close(close)
    n = int(n)
    mid = c.rolling(n, min_periods=n).mean()
    sd = c.rolling(n, min_periods=n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    width = (up - lo).to_numpy()
    pctb = _ratio((c - lo).to_numpy(), np.where(width > 1e-12 * np.abs(mid.to_numpy()), width, 0.0))
    out = pd.DataFrame({"mid": mid, "upper": up, "lower": lo, "pctb": pctb,
                        "bandwidth": (up - lo) / mid}, index=c.index)
    return _restore(out, close)


def _true_range(d: pd.DataFrame, first_bar_hl: bool = True) -> pd.Series:
    h, l, c = d["high"], d["low"], d["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1, skipna=False)
    if len(tr):
        tr.iloc[0] = (h.iloc[0] - l.iloc[0]) if first_bar_hl else np.nan
    return tr


def atr(df, n: int = 14) -> pd.Series:
    """Average true range (Wilder): RMA(n) of the true range; the first bar's TR is high - low."""
    d = _frame(df)
    return _restore(_rma(_true_range(d), int(n)).rename(f"atr{n}"), df)


def _adx_core(d: pd.DataFrame, n: int) -> pd.DataFrame:
    h, l = d["high"], d["low"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where(up.isna(), np.nan, np.where((up > dn) & (up > 0), up, 0.0))
    minus_dm = np.where(dn.isna(), np.nan, np.where((dn > up) & (dn > 0), dn, 0.0))
    tr = _rma(_true_range(d, first_bar_hl=False), n).to_numpy()
    pdi = 100.0 * _ratio(_rma(pd.Series(plus_dm, index=d.index), n).to_numpy(), tr)
    mdi = 100.0 * _ratio(_rma(pd.Series(minus_dm, index=d.index), n).to_numpy(), tr)
    s = pdi + mdi
    dx = np.abs(pdi - mdi) / np.where(s == 0, 1.0, s)
    adx_ = 100.0 * _rma(pd.Series(dx, index=d.index), n).to_numpy()
    return pd.DataFrame({"adx": adx_, "plus_di": pdi, "minus_di": mdi}, index=d.index)


def adx(df, n: int = 14) -> pd.DataFrame:
    """Wilder's directional movement system: ``plus_di``/``minus_di`` = 100 x RMA(+DM / -DM) /
    RMA(TR); ``adx`` = 100 x RMA(|+DI - -DI| / (+DI + -DI)). DataFrame (first ADX at bar 2n-1)."""
    return _restore(_adx_core(_frame(df), int(n)), df)


def _stoch_core(d: pd.DataFrame, n: int, d_n: int, smooth_k: int) -> pd.DataFrame:
    hh = d["high"].rolling(n, min_periods=n).max()
    ll = d["low"].rolling(n, min_periods=n).min()
    rng = (hh - ll).to_numpy()
    raw = 100.0 * _ratio((d["close"] - ll).to_numpy(), rng)
    raw = np.where(np.isfinite(hh.to_numpy()) & (rng <= 0), 50.0, raw)
    k = pd.Series(raw, index=d.index)
    if smooth_k > 1:
        k = k.rolling(smooth_k, min_periods=smooth_k).mean()
    return pd.DataFrame({"k": k, "d": k.rolling(d_n, min_periods=d_n).mean()}, index=d.index)


def stochastic(df, n: int = 14, d_n: int = 3, smooth_k: int = 1) -> pd.DataFrame:
    """Stochastic oscillator (Lane): ``k`` = 100 x (close - LL(n)) / (HH(n) - LL(n)) (smoothed by an
    SMA of ``smooth_k``; 1 = fast %K, TradingView default), ``d`` = SMA(d_n) of k. A flat range
    gives 50. DataFrame."""
    return _restore(_stoch_core(_frame(df), int(n), int(d_n), int(smooth_k)), df)


def obv(df) -> pd.Series:
    """On-balance volume (Granville): cumulative sum of sign(close change) x volume, starting at 0.
    NaN when there is no volume column."""
    d = _frame(df)
    vol = d["volume"]
    step = np.sign(d["close"].diff()).fillna(0.0) * vol.fillna(0.0)
    out = step.cumsum()
    if vol.isna().all():
        out[:] = np.nan
    return _restore(out.rename("obv"), df)


def _is_intraday(idx: pd.DatetimeIndex) -> bool:
    if len(idx) < 2:
        return bool(len(idx) and (idx[0] != idx[0].normalize()))
    step = pd.Series(idx).diff().dt.total_seconds().dropna().median()
    return bool(step < 0.5 * 86400)


def vwap(df, n: int = 20) -> pd.Series:
    """Volume-weighted average price of the typical price (h+l+c)/3.

    Intraday data: session VWAP that resets each calendar day (cumulative within the day; NaN
    until the day has traded volume). Daily or slower data: rolling ``n``-bar (default 20) VWAP.
    NaN without volume."""
    d = _frame(df)
    tp = (d["high"] + d["low"] + d["close"]) / 3.0
    vol = d["volume"].fillna(0.0).clip(lower=0.0)
    pv = tp * vol
    if _is_intraday(d.index):
        day = d.index.normalize()
        num = pv.groupby(day).cumsum()
        den = vol.groupby(day).cumsum()
    else:
        num = pv.rolling(int(n), min_periods=int(n)).sum()
        den = vol.rolling(int(n), min_periods=int(n)).sum()
    out = pd.Series(_ratio(num.to_numpy(), np.where(den.to_numpy() > 0, den.to_numpy(), 0.0)), index=d.index,
                    name="vwap")
    return _restore(out, df)


def williams_r(df, n: int = 14) -> pd.Series:
    """Williams %R: -100 x (HH(n) - close) / (HH(n) - LL(n)), in [-100, 0]; a flat range gives -50."""
    d = _frame(df)
    hh = d["high"].rolling(int(n), min_periods=int(n)).max()
    ll = d["low"].rolling(int(n), min_periods=int(n)).min()
    rng = (hh - ll).to_numpy()
    r = -100.0 * _ratio((hh - d["close"]).to_numpy(), rng)
    r = np.where(np.isfinite(hh.to_numpy()) & (rng <= 0), -50.0, r)
    return _restore(pd.Series(r, index=d.index, name="williams_r"), df)


def _cci_core(d: pd.DataFrame, n: int) -> pd.Series:
    tp = ((d["high"] + d["low"] + d["close"]) / 3.0).to_numpy()
    out = np.full(tp.shape, np.nan)
    if tp.size >= n:
        w = sliding_window_view(tp, n)
        m = w.mean(axis=1)
        mad = np.abs(w - m[:, None]).mean(axis=1)
        out[n - 1:] = _ratio(tp[n - 1:] - m, 0.015 * mad)
    return pd.Series(out, index=d.index, name="cci")


def cci(df, n: int = 20) -> pd.Series:
    """Commodity channel index (Lambert 1980): (TP - SMA(TP, n)) / (0.015 x mean absolute deviation)."""
    return _restore(_cci_core(_frame(df), int(n)), df)


def mfi(df, n: int = 14) -> pd.Series:
    """Money flow index: 100 - 100 / (1 + positive flow / negative flow) over n bars, flow = typical
    price x volume signed by the change in typical price. No negative flow gives 100, no flow 50."""
    d = _frame(df)
    n = int(n)
    tp = (d["high"] + d["low"] + d["close"]) / 3.0
    flow = tp * d["volume"]
    ch = tp.diff()
    pos = flow.where(ch > 0, 0.0).where(ch.notna())
    neg = flow.where(ch < 0, 0.0).where(ch.notna())
    sp = pos.rolling(n, min_periods=n).sum().to_numpy()
    sn = neg.rolling(n, min_periods=n).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - 100.0 / (1.0 + sp / sn)
    r = np.where(sn == 0, np.where(sp == 0, 50.0, 100.0), r)
    r = np.where(np.isfinite(sp) & np.isfinite(sn), r, np.nan)
    return _restore(pd.Series(r, index=d.index, name="mfi"), df)


def donchian(df, n: int = 20) -> pd.DataFrame:
    """Donchian channel: ``upper`` = highest high(n), ``lower`` = lowest low(n), ``mid`` = average."""
    d = _frame(df)
    up = d["high"].rolling(int(n), min_periods=int(n)).max()
    lo = d["low"].rolling(int(n), min_periods=int(n)).min()
    return _restore(pd.DataFrame({"upper": up, "mid": (up + lo) / 2.0, "lower": lo}, index=d.index), df)


def keltner(df, n: int = 20, mult: float = 2.0, atr_n: int = 10) -> pd.DataFrame:
    """Keltner channel (Raschke variant, TradingView default): ``mid`` = EMA(n) of the close,
    ``upper``/``lower`` = mid +/- mult x ATR(atr_n, Wilder)."""
    d = _frame(df)
    mid = d["close"].ewm(span=int(n), adjust=False, min_periods=int(n)).mean()
    a = _rma(_true_range(d), int(atr_n))
    return _restore(pd.DataFrame({"upper": mid + mult * a, "mid": mid, "lower": mid - mult * a}, index=d.index), df)


def _mid(d: pd.DataFrame, n: int) -> pd.Series:
    return (d["high"].rolling(n, min_periods=n).max() + d["low"].rolling(n, min_periods=n).min()) / 2.0


def ichimoku(df, tenkan: int = 9, kijun: int = 26, senkou: int = 52, displacement: int = 26) -> pd.DataFrame:
    """Ichimoku Kinko Hyo (Hosoda). ``tenkan`` = (HH9 + LL9)/2, ``kijun`` = (HH26 + LL26)/2,
    ``senkou_a`` = (tenkan + kijun)/2 and ``senkou_b`` = (HH52 + LL52)/2, both shifted forward by
    ``displacement`` bars on the existing index (pandas ``shift(26)``: the value shown at bar t was
    computed at bar t-26; the index is NOT extended into the future, so the last 26 projected
    cloud values are not returned), ``chikou`` = close shifted back (``shift(-26)``: bar t shows
    the close of bar t+26; NaN for the last 26 bars). Note TradingView plots with offsets of
    displacement - 1 = 25 bars."""
    d = _frame(df)
    t = _mid(d, int(tenkan))
    k = _mid(d, int(kijun))
    out = pd.DataFrame({"tenkan": t, "kijun": k, "senkou_a": ((t + k) / 2.0).shift(int(displacement)),
                        "senkou_b": _mid(d, int(senkou)).shift(int(displacement)),
                        "chikou": d["close"].shift(-int(displacement))}, index=d.index)
    return _restore(out, df)


def _supertrend_core(d: pd.DataFrame, n: int, mult: float) -> pd.DataFrame:
    h, l, c = (d[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    a = _rma(_true_range(d), n).to_numpy()
    hl2 = (h + l) / 2.0
    ub, lb = hl2 + mult * a, hl2 - mult * a
    N = c.size
    line = np.full(N, np.nan)
    dirn = np.full(N, np.nan)
    fu = fl = 0.0
    prev_dir = 0
    started = False
    for i in range(N):
        if not np.isfinite(a[i]):
            continue
        if not started:
            fu, fl, cur = ub[i], lb[i], -1  # TradingView starts a new series in a downtrend
            started = True
        else:
            pc = c[i - 1]
            nl = lb[i] if (lb[i] > fl or pc < fl) else fl
            nu = ub[i] if (ub[i] < fu or pc > fu) else fu
            if prev_dir == -1:
                cur = 1 if c[i] > nu else -1
            else:
                cur = -1 if c[i] < nl else 1
            fu, fl = nu, nl
        line[i] = fl if cur == 1 else fu
        dirn[i] = cur
        prev_dir = cur
    return pd.DataFrame({"line": line, "direction": dirn}, index=d.index)


def supertrend(df, n: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """SuperTrend (Seban): ATR(n) bands around (high + low)/2 with ratcheting final bands.
    ``line`` = lower band in an uptrend / upper band in a downtrend; ``direction`` = +1 uptrend
    (bullish), -1 downtrend (note: TradingView's ``ta.supertrend`` uses the opposite sign)."""
    return _restore(_supertrend_core(_frame(df), int(n), float(mult)), df)


# --------------------------------------------------------------------------- series for charts
_MULTI = {
    "bb": ("bollinger", ["mid", "upper", "lower", "pctb", "bandwidth"]),
    "macd": ("macd", ["macd", "signal", "hist"]),
    "adx": ("adx", ["adx", "plus_di", "minus_di"]),
    "stoch": ("stochastic", ["k", "d"]),
    "ichimoku": ("ichimoku", ["tenkan", "kijun", "senkou_a", "senkou_b", "chikou"]),
    "supertrend": ("supertrend", ["line", "direction"]),
    "donchian": ("donchian", ["upper", "mid", "lower"]),
    "keltner": ("keltner", ["upper", "mid", "lower"]),
}
_ALIASES = {"bollinger": "bb", "stochastic": "stoch", "williams_r": "williams", "willr": "williams",
            "%r": "williams", "st": "supertrend"}


def _vals(a) -> list:
    arr = np.asarray(a, dtype=float)
    return [v if v == v and v not in (np.inf, -np.inf) else None for v in arr.tolist()]


def _compute(d: pd.DataFrame, key: str):
    m = re.fullmatch(r"(sma|ema)(\d+)", key)
    if m:
        n = int(m.group(2))
        if n < 1:
            return None
        c = d["close"]
        return c.rolling(n, min_periods=n).mean() if m.group(1) == "sma" else \
            c.ewm(span=n, adjust=False, min_periods=n).mean()
    if key == "rsi":
        return _rsi_core(d["close"], 14)
    if key == "atr":
        return _rma(_true_range(d), 14)
    if key == "obv":
        return obv(d)
    if key == "vwap":
        return vwap(d)
    if key == "cci":
        return _cci_core(d, 20)
    if key == "mfi":
        return mfi(d)
    if key == "williams":
        return williams_r(d)
    if key in _MULTI:
        fn = {"bollinger": bollinger, "macd": macd, "adx": adx, "stochastic": stochastic, "ichimoku": ichimoku,
              "supertrend": supertrend, "donchian": donchian, "keltner": keltner}[_MULTI[key][0]]
        return fn(d)
    return None


def indicator_series(df, names: list[str]) -> dict:
    """Chart-ready indicator series for the requested ``names``.

    Names (case-insensitive): ``sma{N}``, ``ema{N}`` (any N, e.g. "sma20", "ema200"), "bb"
    (Bollinger 20, 2), "vwap" (session VWAP intraday, rolling 20-bar VWAP on daily data), "rsi"
    (14), "macd" (12, 26, 9), "atr" (14), "adx" (14), "stoch" (14, 3), "obv", "ichimoku" (9, 26,
    52), "supertrend" (10, 3), "donchian" (20), "keltner" (EMA 20 +/- 2 ATR 10), "cci" (20),
    "mfi" (14), "williams" (14). Unknown names are skipped.

    Returns {name: {"t": [...], "v": [...]}} for single lines and {name: {"t": [...], <field>:
    [...], ...}} for multi-line indicators: bb mid/upper/lower/pctb/bandwidth, macd
    macd/signal/hist, adx adx/plus_di/minus_di, stoch k/d, ichimoku
    tenkan/kijun/senkou_a/senkou_b/chikou, supertrend line/direction, donchian and keltner
    upper/mid/lower. ``t`` holds every bar (ISO dates, or ISO date-times for intraday data);
    warm-up values are None.
    """
    out: dict = {}
    try:
        d = _frame(df)
    except Exception:  # noqa: BLE001
        return out
    if len(d) == 0:
        return out
    t = [iso(x) for x in d.index]
    for raw in names or []:
        name = str(raw).strip()
        key = _ALIASES.get(name.lower(), name.lower())
        try:
            res = _compute(d, key)
        except Exception:  # noqa: BLE001
            continue
        if res is None:
            continue
        if isinstance(res, pd.DataFrame):
            fields = _MULTI[key][1]
            out[name] = {"t": list(t), **{f: _vals(res[f].to_numpy()) for f in fields}}
        else:
            out[name] = {"t": list(t), "v": _vals(res.to_numpy())}
    return jsonable(out)


# --------------------------------------------------------------------------- technical rating
def _rating(score: float | None) -> str:
    if score is None:
        return "Neutral"
    if score > 0.5:
        return "Strong buy"
    if score > 0.1:
        return "Buy"
    if score >= -0.1:
        return "Neutral"
    if score >= -0.5:
        return "Sell"
    return "Strong sell"


def _last2(s: pd.Series) -> tuple[float | None, float | None]:
    v = s.to_numpy(dtype=float)
    if v.size == 0:
        return None, None
    cur = clean(v[-1])
    prev = clean(v[-2]) if v.size >= 2 else None
    return cur, prev


def signal_summary(df) -> dict:
    """TradingView-style technical rating from the last bar.

    Moving averages group (+1 buy / -1 sell): price above / below SMA and EMA 10, 20, 50, 100,
    200; SMA50 above / below SMA200 (golden / death cross regime; the note gives the date of the
    last cross); price above / below the Ichimoku base line (kijun 26); SuperTrend(10, 3)
    direction up / down.

    Oscillators group:
    * RSI(14): buy if < 30 and rising, sell if > 70 and falling.
    * Stochastic %K(14, 3): buy if %K < 20 and %K > %D, sell if %K > 80 and %K < %D.
    * MACD(12, 26, 9): buy if MACD > signal, sell if MACD < signal.
    * ADX(14): buy if ADX > 20 and +DI > -DI, sell if ADX > 20 and +DI < -DI (else neutral).
    * CCI(20): buy if < -100 and rising, sell if > 100 and falling.
    * Williams %R(14): buy if < -80 and rising, sell if > -20 and falling.
    * Bollinger %B(20, 2): buy if < 0 (close below the lower band), sell if > 1.
    * Momentum(10) (close - close 10 bars ago): buy if rising, sell if falling.
    Anything else is neutral; indicators without enough history are omitted.

    Score: each group's score is the mean of its signals (+1 / 0 / -1); the overall ``score`` is
    the mean of the two group scores (TradingView). Rating: > 0.5 "Strong buy", (0.1, 0.5] "Buy",
    [-0.1, 0.1] "Neutral", [-0.5, -0.1) "Sell", < -0.5 "Strong sell".

    Returns keys: ``rating``, ``score``, ``counts`` {"buy", "neutral", "sell"}, ``groups``
    {"Moving averages": {"rating", "score", "counts"}, "Oscillators": {...}}, ``signals``
    [{"name", "group", "value", "signal", "note"}], ``asof``, ``close``.
    """
    MA, OSC = "Moving averages", "Oscillators"
    signals: list[dict] = []

    def add(name, group, value, sig, note=""):
        signals.append({"name": name, "group": group, "value": clean(value), "signal": sig, "note": note})

    def finish(asof=None, close=None):
        groups = {}
        g_scores = []
        for g in (MA, OSC):
            sub = [s for s in signals if s["group"] == g]
            cnt = {k: sum(1 for s in sub if s["signal"] == k) for k in ("buy", "neutral", "sell")}
            sc = (cnt["buy"] - cnt["sell"]) / len(sub) if sub else None
            if sc is not None:
                g_scores.append(sc)
            groups[g] = {"rating": _rating(sc), "score": sc, "counts": cnt}
        score = float(np.mean(g_scores)) if g_scores else None
        counts = {k: sum(1 for s in signals if s["signal"] == k) for k in ("buy", "neutral", "sell")}
        return jsonable({"rating": _rating(score), "score": score, "counts": counts, "groups": groups,
                         "signals": signals, "asof": asof, "close": close})

    try:
        d = _frame(df)
        if len(d) < 2:
            return finish(iso(d.index[-1]) if len(d) else None, clean(d["close"].iloc[-1]) if len(d) else None)
        c = d["close"]
        last = float(c.iloc[-1])

        def vs(name, v):
            if v is None:
                return
            sig = "buy" if last > v else "sell" if last < v else "neutral"
            where = "above" if last > v else "below" if last < v else "at"
            add(name, MA, v, sig, f"Price {where} {name}")

        for n in (10, 20, 50, 100, 200):
            vs(f"SMA {n}", _last2(c.rolling(n, min_periods=n).mean())[0])
            vs(f"EMA {n}", _last2(c.ewm(span=n, adjust=False, min_periods=n).mean())[0])
        s50 = c.rolling(50, min_periods=50).mean()
        s200 = c.rolling(200, min_periods=200).mean()
        spread = (s50 / s200 - 1.0).dropna()
        if len(spread):
            sign = np.sign(spread.to_numpy())
            flips = np.flatnonzero((sign[1:] != sign[:-1]) & (sign[1:] != 0))
            cur = spread.iloc[-1]
            if flips.size:
                when = iso(spread.index[flips[-1] + 1])
                kind = "Golden cross" if sign[flips[-1] + 1] > 0 else "Death cross"
                note = f"{kind} on {when}"
            else:
                note = "SMA50 above SMA200 (no cross in sample)" if cur > 0 else \
                    "SMA50 below SMA200 (no cross in sample)"
            add("SMA50 vs SMA200", MA, cur, "buy" if cur > 0 else "sell" if cur < 0 else "neutral", note)
        kij = _last2(_mid(d, 26))[0]
        if kij is not None:
            add("Ichimoku base line (26)", MA, kij, "buy" if last > kij else "sell" if last < kij else "neutral",
                f"Price {'above' if last > kij else 'below' if last < kij else 'at'} kijun-sen")
        st = _supertrend_core(d, 10, 3.0)
        st_dir, _ = _last2(st["direction"])
        if st_dir is not None:
            add("SuperTrend (10, 3)", MA, _last2(st["line"])[0], "buy" if st_dir > 0 else "sell",
                "Uptrend (line below price)" if st_dir > 0 else "Downtrend (line above price)")

        r, rp = _last2(_rsi_core(c, 14))
        if r is not None:
            sig = "buy" if (r < 30 and rp is not None and r > rp) else \
                "sell" if (r > 70 and rp is not None and r < rp) else "neutral"
            note = "Oversold" if r < 30 else "Overbought" if r > 70 else "Between 30 and 70"
            add("RSI (14)", OSC, r, sig, note)
        stc = _stoch_core(d, 14, 3, 1)
        k, _ = _last2(stc["k"])
        dd, _ = _last2(stc["d"])
        if k is not None and dd is not None:
            sig = "buy" if (k < 20 and k > dd) else "sell" if (k > 80 and k < dd) else "neutral"
            add("Stochastic %K (14, 3)", OSC, k, sig, f"%K {k:.1f} vs %D {dd:.1f}")
        mc = macd(c)
        m_, _ = _last2(mc["macd"])
        s_, _ = _last2(mc["signal"])
        if m_ is not None and s_ is not None:
            add("MACD (12, 26, 9)", OSC, m_, "buy" if m_ > s_ else "sell" if m_ < s_ else "neutral",
                f"MACD {'above' if m_ > s_ else 'below' if m_ < s_ else 'at'} signal ({s_:.4g})")
        ax = _adx_core(d, 14)
        a_, _ = _last2(ax["adx"])
        p_, _ = _last2(ax["plus_di"])
        n_, _ = _last2(ax["minus_di"])
        if a_ is not None and p_ is not None and n_ is not None:
            sig = "neutral" if a_ <= 20 else "buy" if p_ > n_ else "sell" if p_ < n_ else "neutral"
            add("ADX (14)", OSC, a_, sig, f"+DI {p_:.1f} / -DI {n_:.1f}" + (" (weak trend)" if a_ <= 20 else ""))
        cc, ccp = _last2(_cci_core(d, 20))
        if cc is not None:
            sig = "buy" if (cc < -100 and ccp is not None and cc > ccp) else \
                "sell" if (cc > 100 and ccp is not None and cc < ccp) else "neutral"
            add("CCI (20)", OSC, cc, sig, "Below -100" if cc < -100 else "Above 100" if cc > 100 else "Inside +/-100")
        w, wp = _last2(williams_r(d, 14))
        if w is not None:
            sig = "buy" if (w < -80 and wp is not None and w > wp) else \
                "sell" if (w > -20 and wp is not None and w < wp) else "neutral"
            add("Williams %R (14)", OSC, w, sig, "Oversold" if w < -80 else "Overbought" if w > -20 else "Mid-range")
        bb, _ = _last2(bollinger(c)["pctb"])
        if bb is not None:
            add("Bollinger %B (20, 2)", OSC, bb, "buy" if bb < 0 else "sell" if bb > 1 else "neutral",
                "Below lower band" if bb < 0 else "Above upper band" if bb > 1 else "Inside the bands")
        mom = c - c.shift(10)
        mo, mop = _last2(mom)
        if mo is not None and mop is not None:
            add("Momentum (10)", OSC, mo, "buy" if mo > mop else "sell" if mo < mop else "neutral",
                "Rising" if mo > mop else "Falling" if mo < mop else "Flat")
        return finish(iso(d.index[-1]), last)
    except Exception:  # noqa: BLE001
        return finish()


# --------------------------------------------------------------------------- levels
_FIBS = {"23.6%": 0.236, "38.2%": 0.382, "50%": 0.5, "61.8%": 0.618, "78.6%": 0.786}


def _daily_bars(d: pd.DataFrame) -> pd.DataFrame:
    g = d.groupby(d.index.normalize())
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last()})


def _cluster(points: list[tuple[float, pd.Timestamp]], tol: float) -> list[list[tuple[float, pd.Timestamp]]]:
    pts = sorted(points, key=lambda p: p[0])
    clusters: list[list[tuple[float, pd.Timestamp]]] = []
    for p in pts:
        if clusters:
            mean = float(np.mean([q[0] for q in clusters[-1]]))
            if p[0] <= mean * (1.0 + tol):
                clusters[-1].append(p)
                continue
        clusters.append([p])
    return clusters


def levels(df, exclude_last: bool = False, swing_bars: int = 120, tol: float = 0.015) -> dict:
    """Support / resistance levels.

    * ``pivots``: classic floor-trader pivots from the last complete bar: P = (H + L + C)/3,
      R1 = 2P - L, S1 = 2P - H, R2 = P + (H - L), S2 = P - (H - L), R3 = H + 2(P - L),
      S3 = L - 2(H - P). Daily (or slower) data uses the last bar (pass ``exclude_last=True`` when
      the last bar is still in progress); intraday data is aggregated per calendar day and the
      previous day's bar is used. ``pivot_basis`` gives the bar used.
    * ``fibonacci``: retracements of the 52-week (365 calendar days) high-low range; ``direction``
      "up" when the low came before the high (levels measured down from the high), else "down".
    * ``high_52w``, ``low_52w`` (bar highs / lows), ``pct_from_high`` / ``pct_from_low`` (last close
      versus them, fractions).
    * ``swing``: fractal swing highs / lows (Williams 5-bar fractals) over the last ``swing_bars``
      bars, clustered when within ``tol`` (1.5%) of the cluster mean: [{"price", "kind":
      "support"|"resistance" (below / above the last close), "touches", "last" (ISO date of the
      latest swing), "distance" (price / close - 1)}], highest price first.

    Returns keys: ``pivots``, ``pivot_basis``, ``fibonacci``, ``high_52w``, ``low_52w``,
    ``pct_from_high``, ``pct_from_low``, ``swing``, ``close``, ``asof``.
    """
    out = {"pivots": {k: None for k in ("P", "R1", "R2", "R3", "S1", "S2", "S3")}, "pivot_basis": None,
           "fibonacci": {"high": None, "low": None, "direction": None, "levels": {k: None for k in _FIBS}},
           "high_52w": None, "low_52w": None, "pct_from_high": None, "pct_from_low": None, "swing": [],
           "close": None, "asof": None}
    try:
        d = _frame(df)
        if len(d) == 0:
            return jsonable(out)
        last = float(d["close"].iloc[-1])
        out["close"], out["asof"] = last, iso(d.index[-1])
        intraday = _is_intraday(d.index)
        daily = _daily_bars(d) if intraday else d
        basis = None
        if intraday:
            basis = daily.iloc[-2] if len(daily) >= 2 else None
            bdate = daily.index[-2] if len(daily) >= 2 else None
        else:
            k = 2 if exclude_last else 1
            basis = daily.iloc[-k] if len(daily) >= k else None
            bdate = daily.index[-k] if len(daily) >= k else None
        if basis is not None:
            H, L, C = float(basis["high"]), float(basis["low"]), float(basis["close"])
            P = (H + L + C) / 3.0
            out["pivots"] = {"P": P, "R1": 2 * P - L, "R2": P + (H - L), "R3": H + 2 * (P - L),
                             "S1": 2 * P - H, "S2": P - (H - L), "S3": L - 2 * (H - P)}
            out["pivot_basis"] = {"date": iso(bdate), "high": H, "low": L, "close": C}
        yr = d[d.index > d.index[-1] - pd.Timedelta(days=365)]
        hi_t, lo_t = yr["high"].idxmax(), yr["low"].idxmin()
        hi, lo = float(yr["high"].max()), float(yr["low"].min())
        out["high_52w"], out["low_52w"] = hi, lo
        out["pct_from_high"], out["pct_from_low"] = last / hi - 1.0, last / lo - 1.0
        up = lo_t <= hi_t
        rng = hi - lo
        out["fibonacci"] = {"high": hi, "low": lo, "high_date": iso(hi_t), "low_date": iso(lo_t),
                            "direction": "up" if up else "down",
                            "levels": {k: (hi - r * rng) if up else (lo + r * rng) for k, r in _FIBS.items()}}
        sw = d.iloc[-int(swing_bars):]
        h, l = sw["high"].to_numpy(), sw["low"].to_numpy()
        pts = []
        for i in range(2, len(sw) - 2):
            if h[i] > max(h[i - 2], h[i - 1]) and h[i] >= max(h[i + 1], h[i + 2]):
                pts.append((float(h[i]), sw.index[i]))
            if l[i] < min(l[i - 2], l[i - 1]) and l[i] <= min(l[i + 1], l[i + 2]):
                pts.append((float(l[i]), sw.index[i]))
        swings = []
        for cl in _cluster(pts, tol):
            price = float(np.mean([p[0] for p in cl]))
            swings.append({"price": price, "kind": "resistance" if price > last else "support",
                           "touches": len(cl), "last": iso(max(p[1] for p in cl)), "distance": price / last - 1.0})
        out["swing"] = sorted(swings, key=lambda s: -s["price"])
        return jsonable(out)
    except Exception:  # noqa: BLE001
        return jsonable(out)


# --------------------------------------------------------------------------- trend state
def trend_state(close) -> dict:
    """Trend snapshot from closes.

    Returns keys: ``above_sma50``, ``above_sma200`` (bool|None), ``sma50_slope_20d`` (SMA50 now /
    SMA50 20 bars ago - 1), ``regime`` ("uptrend": close > SMA50 > SMA200 and SMA50 rising;
    "downtrend": close < SMA50 < SMA200 and SMA50 falling; else "range"; with fewer than 200 bars
    the SMA200 condition is dropped; None with fewer than 70 bars), ``pct_from_52w_high`` /
    ``pct_from_52w_low`` (last close versus the 365-calendar-day max / min close),
    ``momentum_12_1`` (Jegadeesh-Titman: close 21 bars ago / close 252 bars ago - 1),
    ``momentum_6m`` (close / close 126 bars ago - 1), ``days_since_52w_high`` (calendar days),
    ``close``, ``sma50``, ``sma200``, ``asof``.
    """
    keys = ["above_sma50", "above_sma200", "sma50_slope_20d", "regime", "pct_from_52w_high", "pct_from_52w_low",
            "momentum_12_1", "momentum_6m", "days_since_52w_high", "close", "sma50", "sma200", "asof"]
    out = {k: None for k in keys}
    try:
        c = _close(close)
        if len(c) == 0:
            return jsonable(out)
        v = c.to_numpy(dtype=float)
        last = float(v[-1])
        out["close"], out["asof"] = last, iso(c.index[-1])
        s50 = c.rolling(50, min_periods=50).mean()
        s200 = c.rolling(200, min_periods=200).mean()
        m50, m200 = clean(s50.iloc[-1]), clean(s200.iloc[-1])
        out["sma50"], out["sma200"] = m50, m200
        if m50 is not None:
            out["above_sma50"] = bool(last > m50)
        if m200 is not None:
            out["above_sma200"] = bool(last > m200)
        slope = None
        if len(c) >= 70 and m50 is not None:
            prev = clean(s50.iloc[-21])
            if prev:
                slope = m50 / prev - 1.0
        out["sma50_slope_20d"] = slope
        if slope is not None:
            up = last > m50 and slope > 0 and (m200 is None or m50 > m200)
            down = last < m50 and slope < 0 and (m200 is None or m50 < m200)
            out["regime"] = "uptrend" if up else "downtrend" if down else "range"
        yr = c[c.index > c.index[-1] - pd.Timedelta(days=365)]
        hi, lo = float(yr.max()), float(yr.min())
        out["pct_from_52w_high"], out["pct_from_52w_low"] = last / hi - 1.0, last / lo - 1.0
        out["days_since_52w_high"] = int((c.index[-1] - yr.idxmax()).days)
        if len(v) > 252:
            out["momentum_12_1"] = v[-22] / v[-253] - 1.0
        if len(v) > 126:
            out["momentum_6m"] = last / v[-127] - 1.0
        return jsonable(out)
    except Exception:  # noqa: BLE001
        return jsonable(out)
