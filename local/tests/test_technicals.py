"""Tests for semiquant.analytics.technicals: hand-computed indicator values (loop references of
the Wilder / Pine definitions), chart series, the technical rating, levels and trend state."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import technicals as T

NAN = float("nan")


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def frame(close, spread=0.01, seed=0, volume=True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = np.asarray(close, dtype=float)
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, spread / 4, c.size))
    hi = np.maximum(o, c) * (1 + np.abs(rng.normal(0, spread, c.size)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, spread, c.size)))
    d = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c}, index=pd.bdate_range("2020-01-01", periods=c.size))
    if volume:
        d["volume"] = rng.integers(1_000, 10_000, c.size).astype(float)
    return d


def trend(n=400, slope=0.002, seed=1, noise=0.01):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(slope + rng.normal(0, noise, n)))


# ------------------------------------------------------------------------- references
def ref_rma(x, n, start):
    out = [NAN] * len(x)
    if len(x) - start < n:
        return out
    out[start + n - 1] = float(np.mean(x[start:start + n]))
    for i in range(start + n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def ref_rsi(c, n):
    gains = [NAN] + [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    losses = [NAN] + [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    ag, al = ref_rma(gains, n, 1), ref_rma(losses, n, 1)
    return [NAN if math.isnan(g) else (100.0 if l == 0 else 100 - 100 / (1 + g / l)) for g, l in zip(ag, al)]


def ref_ema(x, n, start=0):
    a = 2 / (n + 1)
    out = [NAN] * len(x)
    e = None
    for i in range(start, len(x)):
        e = x[i] if e is None else a * x[i] + (1 - a) * e
        out[i] = e if i - start >= n - 1 else NAN
    return out


def ref_tr(h, l, c, first_hl=True):
    tr = [h[0] - l[0] if first_hl else NAN]
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def ref_adx(h, l, c, n):
    N = len(c)
    pdm, mdm = [NAN] * N, [NAN] * N
    for i in range(1, N):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    tr = ref_rma(ref_tr(h, l, c, first_hl=False), n, 1)
    sp, sm = ref_rma(pdm, n, 1), ref_rma(mdm, n, 1)
    pdi = [100 * a / b if not math.isnan(b) else NAN for a, b in zip(sp, tr)]
    mdi = [100 * a / b if not math.isnan(b) else NAN for a, b in zip(sm, tr)]
    dx = [abs(p - m) / ((p + m) or 1.0) if not math.isnan(p) else NAN for p, m in zip(pdi, mdi)]
    adx = [100 * v if not math.isnan(v) else NAN for v in ref_rma(dx, n, n)]
    return adx, pdi, mdi


def ref_supertrend(h, l, c, n, mult):
    """Pine ta.supertrend transcription (direction -1 = up there; returned as +1 = up here)."""
    atr = ref_rma(ref_tr(h, l, c), n, 0)
    line, dirs = [NAN] * len(c), [NAN] * len(c)
    prev_lb = prev_ub = 0.0
    prev_st = NAN
    for i in range(len(c)):
        if math.isnan(atr[i]):
            continue
        src = (h[i] + l[i]) / 2
        ub, lb = src + mult * atr[i], src - mult * atr[i]
        pc = c[i - 1] if i > 0 else NAN
        lb = lb if (lb > prev_lb or pc < prev_lb) else prev_lb
        ub = ub if (ub < prev_ub or pc > prev_ub) else prev_ub
        if i == 0 or math.isnan(atr[i - 1]):
            d = 1
        elif prev_st == prev_ub:
            d = -1 if c[i] > ub else 1
        else:
            d = 1 if c[i] < lb else -1
        st = lb if d == -1 else ub
        line[i], dirs[i] = st, -d
        prev_lb, prev_ub, prev_st = lb, ub, st
    return line, dirs


def close_enough(a, b, tol=1e-9):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    assert a.shape == b.shape
    assert np.array_equal(np.isnan(a), np.isnan(b)), (a, b)
    m = ~np.isnan(a)
    np.testing.assert_allclose(a[m], b[m], rtol=tol, atol=tol)


# ------------------------------------------------------------------------- indicators
C10 = [44.0, 44.5, 43.5, 44.5, 45.0, 46.0, 45.5, 46.5, 47.0, 46.0, 45.0, 46.25]


def test_sma_ema_hand():
    s = pd.Series(np.arange(1, 11, dtype=float), index=pd.bdate_range("2024-01-01", periods=10))
    close_enough(T.sma(s, 3), [NAN, NAN] + [float(i) for i in range(2, 10)])
    # alpha = 0.5: 1, 1.5, 2.25, 3.125, ...
    e = T.ema(s, 3)
    assert math.isnan(e.iloc[1]) and e.iloc[2] == pytest.approx(2.25) and e.iloc[3] == pytest.approx(3.125)
    close_enough(e, ref_ema(list(s), 3))


def test_rsi_hand():
    s = pd.Series(C10, index=pd.bdate_range("2024-01-01", periods=len(C10)))
    close_enough(T.rsi(s, 3), ref_rsi(C10, 3))
    # first value by hand: changes +0.5, -1.0, +1.0 -> avg gain 0.5, avg loss 1/3 -> RSI 60
    assert T.rsi(s, 3).iloc[3] == pytest.approx(100 - 100 / (1 + 0.5 / (1 / 3)))
    assert T.rsi(pd.Series(5.0, index=s.index), 3).dropna().eq(50.0).all()
    assert T.rsi(pd.Series(np.arange(12.0) + 1, index=s.index), 3).dropna().eq(100.0).all()


def test_macd_hand():
    s = pd.Series(C10, index=pd.bdate_range("2024-01-01", periods=len(C10)))
    m = T.macd(s, 3, 5, 2)
    line = [a - b if not (math.isnan(a) or math.isnan(b)) else NAN for a, b in zip(ref_ema(C10, 3), ref_ema(C10, 5))]
    close_enough(m["macd"], line)
    sig = ref_ema([0.0] * 4 + line[4:], 2, start=4)
    close_enough(m["signal"], sig)
    close_enough(m["hist"], [a - b for a, b in zip(line, sig)])


def test_bollinger():
    s = pd.Series(C10, index=pd.bdate_range("2024-01-01", periods=len(C10)))
    b = T.bollinger(s, 5, 2)
    w = np.array(C10[-5:])
    assert b["mid"].iloc[-1] == pytest.approx(w.mean())
    assert b["upper"].iloc[-1] - b["mid"].iloc[-1] == pytest.approx(2 * w.std(ddof=0))
    assert b["pctb"].iloc[-1] == pytest.approx((C10[-1] - b["lower"].iloc[-1]) / (b["upper"].iloc[-1] - b["lower"].iloc[-1]))
    flat = T.bollinger(pd.Series(3.0, index=s.index), 5)
    assert flat["pctb"].isna().all() and (flat["bandwidth"].dropna() == 0).all()


def test_atr_adx_supertrend_reference():
    d = frame(trend(300, 0.001, seed=4, noise=0.015), seed=4)
    h, l, c = (list(d[k]) for k in ("high", "low", "close"))
    close_enough(T.atr(d, 14), ref_rma(ref_tr(h, l, c), 14, 0))
    adx, pdi, mdi = ref_adx(h, l, c, 14)
    a = T.adx(d, 14)
    close_enough(a["plus_di"], pdi, 1e-8)
    close_enough(a["minus_di"], mdi, 1e-8)
    close_enough(a["adx"], adx, 1e-8)
    assert a["adx"].first_valid_index() == d.index[27]
    line, dirs = ref_supertrend(h, l, c, 10, 3.0)
    st = T.supertrend(d, 10, 3)
    close_enough(st["line"], line, 1e-8)
    close_enough(st["direction"], dirs)


def test_trend_direction_indicators():
    up = frame(trend(300, 0.004, seed=2, noise=0.008), seed=2)
    a = T.adx(up).iloc[-1]
    assert a["plus_di"] > a["minus_di"] and a["adx"] > 25
    assert T.supertrend(up)["direction"].iloc[-1] == 1
    st = T.supertrend(up).iloc[-1]
    assert st["line"] < up["close"].iloc[-1]
    down = frame(trend(300, -0.004, seed=2, noise=0.008), seed=2)
    assert T.supertrend(down)["direction"].iloc[-1] == -1


def test_stochastic_williams_cci_mfi_obv():
    d = frame(trend(120, 0.0, seed=5, noise=0.02), seed=5)
    st = T.stochastic(d, 14, 3)
    hh = d["high"].rolling(14).max()
    ll = d["low"].rolling(14).min()
    np.testing.assert_allclose(st["k"].dropna(), (100 * (d["close"] - ll) / (hh - ll)).dropna())
    np.testing.assert_allclose(st["d"].dropna(), st["k"].rolling(3).mean().dropna())
    w = T.williams_r(d, 14).dropna()
    assert ((w >= -100) & (w <= 0)).all()
    np.testing.assert_allclose(w, (st["k"].dropna() - 100), atol=1e-9)
    tp = (d["high"] + d["low"] + d["close"]) / 3
    md = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    np.testing.assert_allclose(T.cci(d, 20).dropna(), ((tp - tp.rolling(20).mean()) / (0.015 * md)).dropna())
    m = T.mfi(d, 14).dropna()
    assert ((m >= 0) & (m <= 100)).all() and len(m) == len(d) - 14
    idx = pd.bdate_range("2024-01-01", periods=5)
    o = pd.DataFrame({"close": [10, 11, 10, 10, 12.0], "volume": [100, 200, 300, 400, 500.0]}, index=idx)
    assert list(T.obv(o)) == [0, 200, -100, -100, 400]
    assert T.obv(o[["close"]]).isna().all()


def test_vwap_daily_and_intraday(nvda_intraday, nvda_ohlcv):
    v = T.vwap(nvda_intraday)
    d = T._frame(nvda_intraday)
    tp = (d["high"] + d["low"] + d["close"]) / 3
    for day, g in d.groupby(d.index.normalize()):
        traded = g[g["volume"] > 0]
        first = traded.index[0]
        assert v[first] == pytest.approx(tp[first])  # resets every day
        assert v[g.index[-1]] == pytest.approx((tp[g.index] * g["volume"]).sum() / g["volume"].sum())
    vd = T.vwap(nvda_ohlcv)
    tpd = (nvda_ohlcv["high"] + nvda_ohlcv["low"] + nvda_ohlcv["close"]) / 3
    w = nvda_ohlcv["volume"]
    assert vd.iloc[-1] == pytest.approx((tpd * w).iloc[-20:].sum() / w.iloc[-20:].sum())


def test_ichimoku_shifts(nvda_ohlcv):
    ic = T.ichimoku(nvda_ohlcv)
    i = 300
    assert ic["senkou_a"].iloc[i] == pytest.approx((ic["tenkan"].iloc[i - 26] + ic["kijun"].iloc[i - 26]) / 2)
    assert ic["chikou"].iloc[i] == pytest.approx(nvda_ohlcv["close"].iloc[i + 26])
    assert ic["chikou"].iloc[-26:].isna().all()
    assert len(ic) == len(nvda_ohlcv)
    hh, ll = nvda_ohlcv["high"].iloc[i - 8:i + 1].max(), nvda_ohlcv["low"].iloc[i - 8:i + 1].min()
    assert ic["tenkan"].iloc[i] == pytest.approx((hh + ll) / 2)


def test_channels(nvda_ohlcv):
    dc = T.donchian(nvda_ohlcv, 20).dropna()
    assert (dc["upper"] >= dc["mid"]).all() and (dc["mid"] >= dc["lower"]).all()
    kc = T.keltner(nvda_ohlcv).dropna()
    assert (kc["upper"] > kc["lower"]).all()
    np.testing.assert_allclose(kc["mid"], T.ema(nvda_ohlcv, 20).loc[kc.index])


def test_alignment_with_nans():
    s = pd.Series(np.linspace(10, 20, 30), index=pd.bdate_range("2024-01-01", periods=30))
    s.iloc[5] = np.nan
    out = T.sma(s, 3)
    assert out.index.equals(s.index) and math.isnan(out.iloc[5])
    assert out.iloc[8] == pytest.approx(s.iloc[[4, 6, 7, 8]].iloc[1:].mean())


# ------------------------------------------------------------------------- chart series
NAMES = ["sma20", "EMA50", "ema200", "bb", "vwap", "rsi", "macd", "atr", "adx", "stoch", "obv", "ichimoku",
         "supertrend", "donchian", "keltner", "cci", "mfi", "williams", "nonsense", "sma"]


def test_indicator_series_daily(nvda_ohlcv):
    out = T.indicator_series(nvda_ohlcv, NAMES)
    dumps(out)
    assert "nonsense" not in out and "sma" not in out
    assert set(out) == set(NAMES) - {"nonsense", "sma"}
    n = len(nvda_ohlcv)
    assert len(out["sma20"]["t"]) == len(out["sma20"]["v"]) == n
    assert set(out["macd"]) == {"t", "macd", "signal", "hist"}
    assert set(out["ichimoku"]) == {"t", "tenkan", "kijun", "senkou_a", "senkou_b", "chikou"}
    assert set(out["bb"]) == {"t", "mid", "upper", "lower", "pctb", "bandwidth"}
    assert out["sma20"]["v"][-1] == pytest.approx(nvda_ohlcv["close"].iloc[-20:].mean())
    assert out["sma20"]["v"][0] is None
    assert out["sma20"]["t"][-1] == nvda_ohlcv.index[-1].strftime("%Y-%m-%d")


def test_indicator_series_intraday(nvda_intraday):
    out = T.indicator_series(nvda_intraday, NAMES)
    dumps(out)
    assert "T" in out["vwap"]["t"][0]
    assert len(out["rsi"]["v"]) == len(nvda_intraday)


def test_indicator_series_edge():
    assert T.indicator_series(pd.DataFrame(), ["sma20"]) == {}
    tiny = frame([10.0, 10.5, 10.2])
    out = T.indicator_series(tiny, NAMES)
    dumps(out)
    assert all(v is None for v in out["sma20"]["v"])
    titled = tiny.rename(columns=str.title)
    assert T.indicator_series(titled, ["sma2"])["sma2"]["v"][-1] == pytest.approx((10.5 + 10.2) / 2)


# ------------------------------------------------------------------------- rating
def test_signal_summary_trends():
    up = T.signal_summary(frame(trend(400, 0.003, seed=8, noise=0.01), seed=8))
    dn = T.signal_summary(frame(trend(400, -0.003, seed=8, noise=0.01), seed=8))
    dumps(up)
    dumps(dn)
    assert up["rating"] in ("Buy", "Strong buy") and up["score"] > 0.1
    assert dn["rating"] in ("Sell", "Strong sell") and dn["score"] < -0.1
    for o in (up, dn):
        assert -1 <= o["score"] <= 1
        assert sum(o["counts"].values()) == len(o["signals"])
        assert set(o["groups"]) == {"Moving averages", "Oscillators"}
        assert {s["signal"] for s in o["signals"]} <= {"buy", "neutral", "sell"}
    names = {s["name"] for s in up["signals"]}
    for want in ("SMA 200", "EMA 10", "SMA50 vs SMA200", "RSI (14)", "MACD (12, 26, 9)", "ADX (14)", "CCI (20)",
                 "Williams %R (14)", "Bollinger %B (20, 2)", "Momentum (10)", "Ichimoku base line (26)",
                 "SuperTrend (10, 3)", "Stochastic %K (14, 3)"):
        assert want in names
    cross = next(s for s in up["signals"] if s["name"] == "SMA50 vs SMA200")
    assert cross["signal"] == "buy"


def test_signal_summary_cross_date():
    c = np.r_[np.linspace(200, 100, 300), np.linspace(100, 220, 200)]
    out = T.signal_summary(frame(c, seed=1))
    cross = next(s for s in out["signals"] if s["name"] == "SMA50 vs SMA200")
    s50 = pd.Series(c).rolling(50).mean()
    s200 = pd.Series(c).rolling(200).mean()
    first_up = int(((s50 > s200) & (s50.shift() <= s200.shift())).to_numpy().nonzero()[0][-1])
    assert "Golden cross" in cross["note"]
    assert pd.bdate_range("2020-01-01", periods=len(c))[first_up].strftime("%Y-%m-%d") in cross["note"]


def test_signal_summary_real_and_edge(nvda_ohlcv, nvda_intraday):
    for df in (nvda_ohlcv, nvda_intraday, nvda_ohlcv["close"]):
        out = T.signal_summary(df)
        dumps(out)
        assert out["rating"] in ("Strong buy", "Buy", "Neutral", "Sell", "Strong sell")
    flat = T.signal_summary(pd.Series(10.0, index=pd.bdate_range("2024-01-01", periods=300)))
    dumps(flat)
    assert flat["rating"] == "Neutral"
    short = T.signal_summary(frame([1.0, 1.1, 1.2, 1.15, 1.3, 1.2, 1.25, 1.3, 1.4, 1.35]))
    dumps(short)
    assert all(s["name"] not in ("SMA 200", "SMA50 vs SMA200") for s in short["signals"])
    dumps(T.signal_summary(pd.DataFrame()))


# ------------------------------------------------------------------------- levels
def test_levels_daily(nvda_ohlcv):
    out = T.levels(nvda_ohlcv)
    dumps(out)
    last = nvda_ohlcv.iloc[-1]
    P = (last["high"] + last["low"] + last["close"]) / 3
    pv = out["pivots"]
    assert pv["P"] == pytest.approx(P)
    assert pv["R1"] == pytest.approx(2 * P - last["low"]) and pv["S1"] == pytest.approx(2 * P - last["high"])
    assert pv["R2"] == pytest.approx(P + last["high"] - last["low"]) and pv["S3"] < pv["S2"] < pv["S1"] < P
    assert pv["R3"] > pv["R2"] > pv["R1"] > P
    assert out["pivot_basis"]["date"] == nvda_ohlcv.index[-1].strftime("%Y-%m-%d")
    yr = nvda_ohlcv[nvda_ohlcv.index > nvda_ohlcv.index[-1] - pd.Timedelta(days=365)]
    assert out["high_52w"] == pytest.approx(yr["high"].max()) and out["low_52w"] == pytest.approx(yr["low"].min())
    fib = out["fibonacci"]
    assert set(fib["levels"]) == {"23.6%", "38.2%", "50%", "61.8%", "78.6%"}
    assert all(fib["low"] <= v <= fib["high"] for v in fib["levels"].values())
    assert fib["levels"]["50%"] == pytest.approx((fib["high"] + fib["low"]) / 2)
    assert out["pct_from_high"] <= 0 <= out["pct_from_low"]
    prices = [s["price"] for s in out["swing"]]
    assert prices == sorted(prices, reverse=True)
    for s in out["swing"]:
        assert s["kind"] == ("resistance" if s["price"] > last["close"] else "support") and s["touches"] >= 1
    prev = T.levels(nvda_ohlcv, exclude_last=True)
    assert prev["pivot_basis"]["date"] == nvda_ohlcv.index[-2].strftime("%Y-%m-%d")


def test_levels_intraday_and_edge(nvda_intraday):
    out = T.levels(nvda_intraday)
    dumps(out)
    days = sorted({t.normalize() for t in nvda_intraday.index})
    assert out["pivot_basis"]["date"] == days[-2].strftime("%Y-%m-%d")
    g = nvda_intraday[nvda_intraday.index.normalize() == days[-2]]
    assert out["pivot_basis"]["high"] == pytest.approx(T._frame(g)["high"].max())
    for df in (pd.DataFrame(), frame([5.0]), frame([5.0, 5.0, 5.0])):
        dumps(T.levels(df))


def test_levels_swing_clusters():
    # a zig-zag between 100 and 120: two clusters (support ~100, resistance ~120) with several touches
    c = np.tile(np.r_[np.linspace(100, 120, 6), np.linspace(120, 100, 6)[1:-1]], 12)
    d = pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=pd.bdate_range("2023-01-02", periods=c.size))
    d.iloc[-1, :] = 110.0
    out = T.levels(d)
    kinds = {s["kind"]: s for s in out["swing"]}
    assert kinds["resistance"]["price"] == pytest.approx(120) and kinds["resistance"]["touches"] >= 5
    assert kinds["support"]["price"] == pytest.approx(100) and kinds["support"]["touches"] >= 5


# ------------------------------------------------------------------------- trend state
def test_trend_state():
    up = T.trend_state(pd.Series(trend(400, 0.003, seed=3), index=pd.bdate_range("2020-01-01", periods=400)))
    dumps(up)
    assert up["regime"] == "uptrend" and up["above_sma50"] and up["above_sma200"] and up["sma50_slope_20d"] > 0
    dn = T.trend_state(pd.Series(trend(400, -0.003, seed=3), index=pd.bdate_range("2020-01-01", periods=400)))
    assert dn["regime"] == "downtrend" and dn["pct_from_52w_high"] < -0.3
    s = pd.Series(trend(300, 0.001, seed=9), index=pd.bdate_range("2020-01-01", periods=300))
    out = T.trend_state(s)
    assert out["momentum_12_1"] == pytest.approx(s.iloc[-22] / s.iloc[-253] - 1)
    assert out["momentum_6m"] == pytest.approx(s.iloc[-1] / s.iloc[-127] - 1)
    yr = s[s.index > s.index[-1] - pd.Timedelta(days=365)]
    assert out["days_since_52w_high"] == (s.index[-1] - yr.idxmax()).days


def test_trend_state_real_and_edge(closes):
    dumps(T.trend_state(closes["NVDA"]))
    short = T.trend_state(pd.Series([1.0, 2.0, 3.0], index=pd.bdate_range("2024-01-01", periods=3)))
    assert short["regime"] is None and short["above_sma50"] is None and short["momentum_6m"] is None
    dumps(short)
    dumps(T.trend_state(pd.Series(dtype=float)))
