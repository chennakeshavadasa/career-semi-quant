"""Tests for the quant-pack analytics (offline, fixed seeds, known answers on synthetic data plus
sanity checks on the real fixtures):

robustness   asymmetric_risk, sharpe_confidence, drawdown_risk
liquidity    liquidity_profile, typical_spread, corwin_schultz, roll_spread
volatility   har_rv (and its _daily_rv proxy)
randomwalk   variance_ratios, random_walk_tests
options      risk_neutral_density, model_free_iv
systemic     absorption_ratio, turbulence (and the Ledoit-Wolf _shrunk_cov)
factorlab    signal_frames, factor_lab

Several tests here first exposed bugs (since fixed) and now guard against them; their names
say which defect they cover.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from semiquant.analytics import factorlab as FL
from semiquant.analytics import liquidity as LQ
from semiquant.analytics import options as O
from semiquant.analytics import randomwalk as RW
from semiquant.analytics import robustness as RB
from semiquant.analytics import systemic as SY
from semiquant.analytics import volatility as V


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


# ============================================================================== synthetic data
def from_simple(r, start: str = "2010-01-04", s0: float = 100.0) -> pd.Series:
    """Business-day closes whose simple returns are exactly ``r``."""
    r = np.asarray(r, float)
    return pd.Series(s0 * np.concatenate([[1.0], np.cumprod(1.0 + r)]), index=pd.bdate_range(start, periods=r.size + 1))


def ar1_closes(n: int = 1500, phi: float = 0.0, sigma: float = 0.01, seed: int = 1) -> pd.Series:
    """Closes whose daily log returns follow an AR(1) with coefficient ``phi`` (0: a random walk)."""
    rng = np.random.default_rng(seed)
    e = rng.standard_normal(n) * sigma
    x = np.empty(n)
    x[0] = e[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return pd.Series(100.0 * np.exp(np.concatenate([[0.0], np.cumsum(x)])),
                     index=pd.bdate_range("2015-01-02", periods=n + 1))


def ohlc_from_vols(vols, steps: int = 100, overnight_frac: float = 0.2, seed: int = 0) -> pd.DataFrame:
    """Daily OHLC of a Brownian log price with annualised vol ``vols[i]`` on day i: an overnight gap
    carries ``overnight_frac`` of the day's variance, a ``steps``-point intraday path the rest."""
    vols = np.asarray(vols, float)
    rng = np.random.default_rng(seed)
    sd = vols / math.sqrt(252)
    gap = rng.standard_normal(vols.size) * sd * math.sqrt(overnight_frac)
    path = np.cumsum(rng.standard_normal((vols.size, steps)), axis=1) * (sd * math.sqrt((1 - overnight_frac) / steps))[:, None]
    log_close = np.cumsum(gap + path[:, -1])
    log_open = log_close - path[:, -1]
    hi = log_open + np.maximum(path.max(axis=1), 0.0)
    lo = log_open + np.minimum(path.min(axis=1), 0.0)
    return pd.DataFrame({"open": 100 * np.exp(log_open), "high": 100 * np.exp(hi), "low": 100 * np.exp(lo),
                         "close": 100 * np.exp(log_close), "volume": 1e6},
                        index=pd.bdate_range("2020-01-01", periods=vols.size))


def ohlcv_frame(n: int = 120, seed: int = 3, px: float = 50.0, vol: float = 0.02, volume=2e6) -> pd.DataFrame:
    """Random-walk daily OHLCV with ~1 % intraday ranges; ``volume`` is a scalar or an array."""
    rng = np.random.default_rng(seed)
    close = px * np.exp(np.cumsum(rng.standard_normal(n) * vol))
    high = close * (1 + np.abs(rng.standard_normal(n)) * 0.01)
    low = close * (1 - np.abs(rng.standard_normal(n)) * 0.01)
    open_ = np.clip(close * (1 + rng.standard_normal(n) * 0.002), low, high)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": np.broadcast_to(np.asarray(volume, float), (n,)).copy()},
                        index=pd.bdate_range("2024-01-01", periods=n))


def factor_universe(n_days: int = 400, n_assets: int = 20, loading: float = 0.0, seed: int = 0,
                    idio: float = 0.01, factor: float = 0.01) -> np.ndarray:
    """Daily log returns = loading * common factor + independent noise (rows = days)."""
    rng = np.random.default_rng(seed)
    f = rng.standard_normal(n_days) * factor
    return loading * f[:, None] + rng.standard_normal((n_days, n_assets)) * idio


def closes_from_log(R: np.ndarray, start: str = "2021-01-04") -> pd.DataFrame:
    return pd.DataFrame(100.0 * np.exp(np.cumsum(R, axis=0)), index=pd.bdate_range(start, periods=R.shape[0]),
                        columns=[f"S{i:02d}" for i in range(R.shape[1])])


def drift_universe(n_stocks: int = 30, years: int = 5, seed: int = 0, drift_sd: float = 0.35,
                   vol: float = 0.25) -> pd.DataFrame:
    """Stocks with persistent, stock-specific drifts: past winners keep winning, so 12-1 momentum
    predicts next month's return across the universe."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=252 * years)
    mu = rng.standard_normal(n_stocks) * drift_sd
    R = mu / 252 + rng.standard_normal((idx.size, n_stocks)) * vol / math.sqrt(252)
    return pd.DataFrame(50.0 * np.exp(np.cumsum(R, axis=0)), index=idx, columns=[f"T{i:02d}" for i in range(n_stocks)])


# synthetic option chains (copied from tests/test_options.py)
def make_chain(S, T_years, r, q, vol_fn, strikes, spread=0.02, oi_call=None, oi_put=None):
    """Two-sided BSM chain with IV = vol_fn(K) and a relative spread around the model price."""
    K = np.asarray(strikes, float)
    vols = np.array([vol_fn(k) for k in K])
    c = O.bs_price(S, K, T_years, r, q, vols, "call")
    p = O.bs_price(S, K, T_years, r, q, vols, "put")
    n = K.size
    oi_c = np.full(n, 1000.0) if oi_call is None else np.asarray(oi_call, float)
    oi_p = np.full(n, 1000.0) if oi_put is None else np.asarray(oi_put, float)

    def side(px, oi, tag):
        bid = np.round(px * (1 - spread / 2), 6)
        ask = np.round(px * (1 + spread / 2), 6)
        return pd.DataFrame({"contractSymbol": [f"TEST{tag}{k:08.0f}" for k in K * 1000], "strike": K,
                             "lastPrice": px, "bid": bid, "ask": ask, "volume": np.full(n, 50.0),
                             "openInterest": oi, "impliedVolatility": vols, "inTheMoney": False})
    return side(c, oi_c, "C"), side(p, oi_p, "P")


ASOF = "2026-01-05T10:00:00"


def expiry_after(days: int) -> str:
    return (pd.Timestamp(ASOF).normalize() + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


S0, R0, Q0, VOL0 = 100.0, 0.04, 0.01, 0.30
EXP60 = expiry_after(60)
T60 = O.time_to_expiry(EXP60, ASOF)
F60 = S0 * math.exp((R0 - Q0) * T60)          # forward
SD60 = VOL0 * math.sqrt(T60)                   # lognormal sigma * sqrt(T)
STRIKES = np.arange(40, 200.5, 1.0)


def skewed_vol(k: float) -> float:
    return 0.30 - 0.30 * math.log(k / S0)      # put skew: higher vol at low strikes, 30 % at the money


def lognormal_below(level: float) -> float:
    """P(S_T < level) for a lognormal S_T with forward F60 and total vol SD60."""
    return float(stats.norm.cdf((math.log(level / F60) + 0.5 * SD60 ** 2) / SD60))


@pytest.fixture(scope="module")
def flat_chain():
    return make_chain(S0, T60, R0, Q0, lambda k: VOL0, STRIKES)


@pytest.fixture(scope="module")
def skew_chain():
    return make_chain(S0, T60, R0, Q0, skewed_vol, STRIKES)


def nearest_expiry(opts: dict, min_days: float = 7.0) -> str:
    return min(e for e in opts["chains"] if O.time_to_expiry(e, opts["asof"]) * 365.0 >= min_days)


# ============================================================================== robustness
def test_asymmetric_risk_leveraged_stock():
    """stock = 1.5 x market + small noise: overall, downside, upside and crash betas are all 1.5 and
    the stock is in its own tails on the market's tail days (lambda close to 1)."""
    rng = np.random.default_rng(42)
    n = 5000
    m = 0.0003 + 0.01 * rng.standard_normal(n)
    s = 1.5 * m + 0.001 * rng.standard_normal(n)
    out = RB.asymmetric_risk(from_simple(s), from_simple(m))
    dumps(out)
    assert out["freq"] == "daily" and out["n"] == n
    for k in ("beta", "downside_beta", "upside_beta", "crash_beta"):
        assert out[k] == pytest.approx(1.5, abs=0.03), k
    assert out["beta_asymmetry"] == pytest.approx(out["downside_beta"] - out["upside_beta"])
    assert abs(out["beta_asymmetry"]) < 0.03
    assert out["crash_beta"] == pytest.approx(out["crash_avg_stock"] / out["crash_avg_market"])
    rho = np.corrcoef(s, m)[0, 1]
    assert abs(out["coskewness"]) < 0.1
    assert out["cokurtosis"] == pytest.approx(3 * rho, abs=0.15)
    assert [t["q"] for t in out["tail_dependence"]] == [0.05, 0.10]
    for t in out["tail_dependence"]:
        assert t["independent"] == t["q"] and t["n_tail"] == round(t["q"] * n)
        assert t["lower"] > 0.9 and t["upper"] > 0.9


def test_asymmetric_risk_independent_stock_tail_dependence_is_q():
    rng = np.random.default_rng(7)
    n = 5000
    m = 0.01 * rng.standard_normal(n)
    s = 0.015 * rng.standard_normal(n)
    out = RB.asymmetric_risk(from_simple(s), from_simple(m))
    dumps(out)
    assert abs(out["beta"]) < 0.1
    for t in out["tail_dependence"]:
        assert t["lower"] == pytest.approx(t["q"], abs=0.05)
        assert t["upper"] == pytest.approx(t["q"], abs=0.05)


def test_asymmetric_risk_kinked_stock():
    """Beta 2 when the market falls, 0.5 when it rises: a concave, crash-prone profile."""
    rng = np.random.default_rng(3)
    n = 5000
    m = 0.0003 + 0.01 * rng.standard_normal(n)
    s = np.where(m < 0, 2.0 * m, 0.5 * m) + 0.001 * rng.standard_normal(n)
    out = RB.asymmetric_risk(from_simple(s), from_simple(m))
    assert out["downside_beta"] == pytest.approx(2.0, abs=0.05)
    assert out["upside_beta"] == pytest.approx(0.5, abs=0.05)
    assert out["beta_asymmetry"] == pytest.approx(1.5, abs=0.1)
    assert out["downside_beta"] > out["beta"] > out["upside_beta"]
    assert out["crash_beta"] == pytest.approx(2.0, abs=0.1)
    assert out["coskewness"] < -0.2               # loses most when the market's moves are large


def test_asymmetric_risk_bivariate_normal_moments():
    """Docstring known answer: a normal pair with correlation rho has co-skewness 0, co-kurtosis 3 rho."""
    rng = np.random.default_rng(11)
    n, rho = 20000, 0.6
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + math.sqrt(1 - rho ** 2) * rng.standard_normal(n)
    out = RB.asymmetric_risk(from_simple(0.01 * z2), from_simple(0.01 * z1))
    assert out["coskewness"] == pytest.approx(0.0, abs=0.05)
    assert out["cokurtosis"] == pytest.approx(3 * rho, abs=0.12)
    assert out["beta"] == pytest.approx(rho, abs=0.03)


def test_asymmetric_risk_weekly_and_short_history():
    rng = np.random.default_rng(5)
    n = 2500
    m = 0.0003 + 0.01 * rng.standard_normal(n)
    s = 1.5 * m + 0.001 * rng.standard_normal(n)
    wk = RB.asymmetric_risk(from_simple(s), from_simple(m), freq="W")
    dumps(wk)
    assert wk["freq"] == "weekly"
    assert wk["n"] == pytest.approx(n / 5, rel=0.02)
    assert wk["beta"] == pytest.approx(1.5, abs=0.05)
    short = RB.asymmetric_risk(from_simple(s[:30]), from_simple(m[:30]))
    dumps(short)
    assert short["n"] == 30 and short["tail_dependence"] == []
    assert all(short[k] is None for k in ("beta", "downside_beta", "upside_beta", "beta_asymmetry",
                                           "coskewness", "cokurtosis", "crash_beta"))


def test_sharpe_confidence_normal_returns_known_se():
    """i.i.d. normal returns: se ~ sqrt((1 + SR^2 / 2) / (n - 1)) per period, x sqrt(252) annualised."""
    rng = np.random.default_rng(1)
    n = 2520
    r = 0.001 + 0.01 * rng.standard_normal(n)
    out = RB.sharpe_confidence(from_simple(r))
    dumps(out)
    sr = r.mean() / r.std(ddof=1)
    assert out["n"] == n and out["years"] == pytest.approx(10.0) and out["psr_vs"] == 0.0
    assert out["sharpe"] == pytest.approx(sr * math.sqrt(252), rel=1e-9)
    assert out["se"] == pytest.approx(math.sqrt((1 + sr ** 2 / 2) / (n - 1)) * math.sqrt(252), rel=0.01)
    z = stats.norm.ppf(0.975)
    assert out["ci_low"] == pytest.approx(out["sharpe"] - z * out["se"])
    assert out["ci_high"] == pytest.approx(out["sharpe"] + z * out["se"])
    assert out["skew"] == pytest.approx(0.0, abs=0.2) and out["kurtosis"] == pytest.approx(3.0, abs=0.3)
    assert out["psr"] > 0.95
    assert 0 < out["min_track_record_years"] < out["years"]


def test_sharpe_confidence_negative_drift():
    rng = np.random.default_rng(2)
    out = RB.sharpe_confidence(from_simple(-0.0005 + 0.01 * rng.standard_normal(2520)))
    dumps(out)
    assert out["sharpe"] < 0 and out["psr"] < 0.5
    assert out["min_track_record_years"] is None          # Sharpe <= benchmark: no history is enough


def test_sharpe_confidence_mertens_formula_psr_and_min_track_record():
    """Negatively skewed, fat-tailed excess returns: se follows Mertens with the sample skewness and
    kurtosis and exceeds the normal-theory se; PSR at the minimum track record is the confidence."""
    rng = np.random.default_rng(11)
    n, rf = 1500, 0.02
    r = 0.0035 + 0.01 * rng.standard_normal(n) - np.where(rng.random(n) < 0.03, 0.06, 0.0)
    out = RB.sharpe_confidence(from_simple(r), rf=rf)
    dumps(out)
    e = r - rf / 252
    sr = e.mean() / e.std(ddof=1)
    g3, g4 = stats.skew(e), stats.kurtosis(e, fisher=False)
    var_term = 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2
    assert g3 < -1 and g4 > 5 and sr > 0                  # the sample really is skewed and fat-tailed
    assert out["sharpe"] == pytest.approx(sr * math.sqrt(252), rel=1e-9)     # excess over rf
    assert out["skew"] == pytest.approx(g3, rel=1e-9) and out["kurtosis"] == pytest.approx(g4, rel=1e-9)
    assert out["se"] == pytest.approx(math.sqrt(var_term / (n - 1)) * math.sqrt(252), rel=1e-9)
    assert out["se"] > 1.05 * math.sqrt((1 + sr ** 2 / 2) / (n - 1)) * math.sqrt(252)
    assert out["psr"] == pytest.approx(stats.norm.cdf(sr / math.sqrt(var_term / (n - 1))), rel=1e-9)
    n_min = out["min_track_record_years"] * 252
    assert n_min == pytest.approx(1 + var_term * (stats.norm.ppf(0.95) / sr) ** 2, rel=1e-9)
    assert stats.norm.cdf(sr * math.sqrt(n_min - 1) / math.sqrt(var_term)) == pytest.approx(0.95, abs=1e-9)
    # benchmark Sharpe ratio (annualised)
    sr_b = 0.5 / math.sqrt(252)
    vs = RB.sharpe_confidence(from_simple(r), rf=rf, benchmark_sharpe=0.5)
    assert vs["psr_vs"] == 0.5
    assert vs["psr"] == pytest.approx(stats.norm.cdf((sr - sr_b) / math.sqrt(var_term / (n - 1))), rel=1e-9)
    assert vs["min_track_record_years"] * 252 == pytest.approx(
        1 + var_term * (stats.norm.ppf(0.95) / (sr - sr_b)) ** 2, rel=1e-9)
    above = RB.sharpe_confidence(from_simple(r), rf=rf, benchmark_sharpe=out["sharpe"] + 0.5)
    assert above["psr"] < 0.5 and above["min_track_record_years"] is None
    c90 = RB.sharpe_confidence(from_simple(r), rf=rf, confidence=0.90)
    assert c90["ci_high"] - c90["sharpe"] == pytest.approx(stats.norm.ppf(0.95) * c90["se"], rel=1e-9)


def test_sharpe_confidence_short_or_flat_history():
    rng = np.random.default_rng(3)
    short = RB.sharpe_confidence(from_simple(0.01 * rng.standard_normal(50)))
    flat = RB.sharpe_confidence(pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=300)))
    for out in (short, flat):
        dumps(out)
        assert all(out[k] is None for k in ("sharpe", "se", "ci_low", "ci_high", "psr", "min_track_record_years",
                                            "skew", "kurtosis"))
    assert short["n"] == 50 and flat["n"] == 299


DD_PATH = ([100, 95, 90, 85, 80, 75, 80, 85, 90, 95, 95, 95, 95, 100] + list(range(101, 121))
           + [114, 108, 108, 114, 114, 114, 114])


def test_drawdown_risk_hand_made_path():
    """41 closes: a 12-day drawdown to -25 % that recovers, 20 new highs, then a 7-day drawdown that is
    still open. Depths: 22 zeros, 0.05 x 10, 0.10 x 4, 0.15 x 2, 0.20 x 2, 0.25 x 1 (sum 1.85)."""
    s = pd.Series(np.array(DD_PATH, float), index=pd.bdate_range("2024-01-01", periods=len(DD_PATH)))
    out = RB.drawdown_risk(s)
    dumps(out)
    assert out["n"] == 41 and out["alpha"] == 0.95
    assert out["max_drawdown"] == pytest.approx(0.25)
    assert out["dar"] == pytest.approx(0.20)            # 95 % quantile of 41 depths: the 3rd largest
    assert out["cdar"] == pytest.approx((0.25 + 0.20 + 0.20) / 3)
    assert out["pain_index"] == pytest.approx(1.85 / 41)
    assert out["underwater_share"] == pytest.approx(19 / 41)
    assert out["longest_underwater_days"] == 12 and out["current_underwater_days"] == 7
    med = RB.drawdown_risk(s, alpha=0.5)                 # median depth 0: CDaR = mean depth = pain index
    assert med["dar"] == 0.0 and med["cdar"] == pytest.approx(out["pain_index"])


def test_drawdown_risk_rising_and_short():
    up = RB.drawdown_risk(pd.Series(np.linspace(100, 140, 50), index=pd.bdate_range("2024-01-01", periods=50)))
    dumps(up)
    assert up["max_drawdown"] == 0 and up["dar"] == 0 and up["cdar"] == 0 and up["pain_index"] == 0
    assert up["underwater_share"] == 0 and up["longest_underwater_days"] == 0 and up["current_underwater_days"] == 0
    short = RB.drawdown_risk(pd.Series(np.linspace(100, 90, 29), index=pd.bdate_range("2024-01-01", periods=29)))
    dumps(short)
    assert short["n"] == 29 and short["dar"] is None and short["max_drawdown"] is None


# ============================================================================== liquidity
def test_typical_spread_buckets():
    b = LQ.SPREAD_BUCKETS
    assert [lo for lo, _ in b] == sorted((lo for lo, _ in b), reverse=True) and b[-1][0] == 0
    assert LQ.typical_spread(0) == LQ.typical_spread(None) == b[-1][1]       # no volume: widest bucket
    for (lo, s), (_, s_wider) in zip(b, b[1:]):
        assert s < s_wider                                                   # more volume, tighter spread
        assert LQ.typical_spread(lo) == s                                    # buckets include their floor
        assert LQ.typical_spread(math.nextafter(lo, 0.0)) == s_wider
    sweep = [LQ.typical_spread(a) for a in np.logspace(4, 11, 300)]
    assert all(y <= x for x, y in zip(sweep, sweep[1:])) and len(set(sweep)) == len(b)
    assert LQ.typical_spread(5e9) <= 0.0005 and LQ.typical_spread(1e5) >= 0.005   # mega cap vs micro cap


def test_typical_spread_one_cent_floor():
    top = LQ.SPREAD_BUCKETS[0][1]
    assert LQ.typical_spread(2e9, price=2.0) == pytest.approx(0.01 / 2.0)    # one cent on a $2 stock
    assert LQ.typical_spread(2e9, price=2.0, usd_listing=False) == top       # no cent tick abroad
    assert LQ.typical_spread(2e9, price=500.0) == top                        # floor 2 bp does not bind
    assert LQ.typical_spread(2e9) == top                                     # price unknown
    assert LQ.typical_spread(5e5, price=0.5) == pytest.approx(0.02)          # floor above the widest bucket


def test_liquidity_profile_spread_source():
    df = ohlcv_frame()
    base = LQ.liquidity_profile(df)
    dumps(base)
    typical = LQ.typical_spread(base["adv_usd_20d"], base["price"])
    assert base["spread_source"] == "typical" and base["spread_quoted"] is None
    assert base["spread_used"] == pytest.approx(typical)
    # Corwin-Schultz and Roll are still reported, for reference only
    assert base["spread_cs"] > 0 and base["spread_cs"] != pytest.approx(base["spread_used"])
    assert "spread_roll" in base
    # a quote counts only while the market is open (quote_live) ...
    assert LQ.liquidity_profile(df, bid=49.9, ask=50.1)["spread_source"] == "typical"
    live = LQ.liquidity_profile(df, bid=49.9, ask=50.1, quote_live=True)
    dumps(live)
    assert live["spread_source"] == "quoted"
    assert live["spread_quoted"] == pytest.approx(0.2 / 50.0) and live["spread_used"] == live["spread_quoted"]
    assert LQ.liquidity_profile(df, bid=49.3, ask=50.7, quote_live=True)["spread_used"] == pytest.approx(0.028)
    # ... two-sided, not crossed and under 3 % wide (5 %, exactly 3 %, crossed, one-sided: typical)
    for bid, ask in ((48.75, 51.25), (49.25, 50.75), (50.1, 49.9), (None, 50.1), (0.0, 50.1), (49.9, None)):
        out = LQ.liquidity_profile(df, bid=bid, ask=ask, quote_live=True)
        assert out["spread_source"] == "typical" and out["spread_quoted"] is None, (bid, ask)
        assert out["spread_used"] == pytest.approx(typical), (bid, ask)
    # the spread used enters every order's cost as a half spread
    for q_row, t_row in zip(live["orders"], base["orders"]):
        assert q_row["cost"] - t_row["cost"] == pytest.approx(0.5 * (live["spread_used"] - base["spread_used"]))


def test_liquidity_profile_square_root_costs():
    n = 100
    df = ohlcv_frame(n=n, seed=2, px=20.0, vol=0.015, volume=np.where(np.arange(n) < 60, 1e6, 3e6))
    out = LQ.liquidity_profile(df, shares_outstanding=5e8)
    dumps(out)
    close, r = df["close"], df["close"].pct_change()
    dv = close * df["volume"]
    assert out["available"] is True and out["price"] == pytest.approx(close.iloc[-1])
    assert out["adv_shares_20d"] == pytest.approx(3e6) and out["adv_shares_60d"] == pytest.approx(7e6 / 3)
    assert out["adv_usd_20d"] == pytest.approx(dv.tail(20).mean())
    assert out["adv_usd_60d"] == pytest.approx(dv.tail(60).mean())
    assert out["turnover_daily"] == pytest.approx((7e6 / 3) / 5e8)
    assert out["volume_trend"] == pytest.approx(3e6 / (7e6 / 3) - 1)
    assert out["daily_vol"] == pytest.approx(r.tail(60).std(ddof=1))
    assert out["amihud"] == pytest.approx((r.abs() / (dv / 1e6)).tail(60).mean())
    assert out["impact_y"] == LQ.IMPACT_Y == 1.0
    rows = out["orders"]
    assert [row["usd"] for row in rows] == list(LQ.ORDER_SIZES)
    spread, sigma, px, adv20 = out["spread_used"], out["daily_vol"], out["price"], out["adv_shares_20d"]
    for row in rows:
        assert set(row) == {"usd", "shares", "pct_adv", "cost", "cost_usd", "days_10", "risk_10", "days_20", "risk_20"}
        assert row["shares"] == pytest.approx(row["usd"] / px)
        assert row["pct_adv"] == pytest.approx(row["shares"] / adv20)
        assert row["cost"] == pytest.approx(0.5 * spread + sigma * math.sqrt(row["pct_adv"]))
        assert row["cost_usd"] == pytest.approx(row["cost"] * row["usd"])
        assert row["days_10"] == pytest.approx(max(row["pct_adv"] / 0.10, 1.0))
        assert row["days_20"] == pytest.approx(max(row["pct_adv"] / 0.20, 1.0))
        assert row["risk_10"] == pytest.approx(sigma * math.sqrt(row["days_10"] / 3))
        assert row["risk_20"] == pytest.approx(sigma * math.sqrt(row["days_20"] / 3))
    costs = [row["cost"] for row in rows]
    assert all(b > a for a, b in zip(costs, costs[1:]))                 # bigger orders cost more
    assert rows[0]["days_10"] == 1.0 and rows[-1]["days_10"] > rows[-1]["days_20"] > 1.0


def test_liquidity_profile_fx_and_cent_floor():
    df = ohlcv_frame(n=100, seed=2, px=20.0, vol=0.015, volume=3e6)
    usd, eur = LQ.liquidity_profile(df), LQ.liquidity_profile(df, fx_to_usd=1.25)
    dumps(eur)
    assert eur["adv_usd_20d"] == pytest.approx(1.25 * usd["adv_usd_20d"])
    assert eur["adv_shares_20d"] == usd["adv_shares_20d"]
    assert eur["orders"][0]["shares"] == pytest.approx(1e5 / (eur["price"] * 1.25))
    assert eur["spread_used"] == pytest.approx(LQ.typical_spread(eur["adv_usd_20d"], eur["price"], usd_listing=False))
    # a $2 stock trading $2bn a day: the one-cent tick (50 bp) binds on a US listing, not abroad
    cheap = df.assign(open=2.0, high=2.02, low=1.98, close=2.0, volume=1e9)
    assert LQ.liquidity_profile(cheap)["spread_used"] == pytest.approx(0.005)
    assert LQ.liquidity_profile(cheap, fx_to_usd=1.1)["spread_used"] == LQ.SPREAD_BUCKETS[0][1]


def test_liquidity_profile_needs_volume_and_history():
    df = ohlcv_frame()
    for bad in (df.assign(volume=0.0), df.drop(columns="volume"), df.iloc[:29]):
        out = LQ.liquidity_profile(bad)
        dumps(out)
        assert out["available"] is False and out["message"]


def test_liquidity_profile_real_nvda(nvda_ohlcv):
    out = LQ.liquidity_profile(nvda_ohlcv.tail(260), shares_outstanding=24.3e9)
    dumps(out)
    assert out["available"] and out["price"] == pytest.approx(nvda_ohlcv["close"].iloc[-1])
    assert out["adv_usd_20d"] > 1e9 and out["spread_source"] == "typical"
    assert out["spread_used"] == pytest.approx(LQ.typical_spread(out["adv_usd_20d"], out["price"]))
    assert out["spread_used"] < 0.001 < out["spread_cs"]       # CS reads a mega cap's volatility as spread
    assert 0 < out["turnover_daily"] < 0.05 and 0.005 < out["daily_vol"] < 0.15
    costs = [row["cost"] for row in out["orders"]]
    assert all(b > a for a, b in zip(costs, costs[1:])) and costs[0] < 0.005


def test_corwin_schultz_known_answers():
    idx = pd.bdate_range("2024-01-01", periods=80)
    rng = np.random.default_rng(5)
    bounce = np.where(rng.random(80) < 0.5, 99.5, 100.5)
    # constant mid 100 and the same 1 % range every day: S = 2 (H - L) / (H + L) = 0.01 exactly
    const = pd.DataFrame({"open": bounce[::-1], "high": 100.5, "low": 99.5, "close": bounce}, index=idx)
    assert LQ.corwin_schultz(const) == pytest.approx(0.01, rel=1e-9)
    assert LQ.corwin_schultz(const.drop(columns="open")) == pytest.approx(0.01, rel=1e-9)
    # high == low == close: no spread, whatever the price path
    c = 100 * np.exp(np.cumsum(rng.standard_normal(80) * 0.02))
    assert LQ.corwin_schultz(pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)) == 0.0
    assert LQ.corwin_schultz(const.iloc[:9]) is None


def test_corwin_schultz_overnight_gap_adjustment():
    """Each day spans 1 % and closes at its low (high); the next opens 2 % higher (lower). Unadjusted,
    the gap would read as volatility (two-day estimate negative, set to 0); adjusted, ~1 %."""
    n, s = 40, 0.01
    idx = pd.bdate_range("2024-01-01", periods=n)
    up, down = 100 * 1.02 ** np.arange(n), 100 * 0.98 ** np.arange(n)
    gap_up = pd.DataFrame({"open": up, "high": up * (1 + s / 2), "low": up * (1 - s / 2), "close": up * (1 - s / 2)}, index=idx)
    gap_dn = pd.DataFrame({"open": down, "high": down * (1 + s / 2), "low": down * (1 - s / 2),
                           "close": down * (1 + s / 2)}, index=idx)
    assert LQ.corwin_schultz(gap_up) == pytest.approx(s, rel=0.05)
    assert LQ.corwin_schultz(gap_dn) == pytest.approx(s, rel=0.05)


def test_roll_spread_known_answers():
    rng = np.random.default_rng(8)
    n = 3000
    # trades bounce between bid 49.75 and ask 50.25 around a constant mid: spread 0.5 / 50 = 1 %
    bounce = pd.DataFrame({"close": 50 + 0.25 * np.where(rng.random(n) < 0.5, -1.0, 1.0)},
                          index=pd.bdate_range("2010-01-01", periods=n))
    assert LQ.roll_spread(bounce, window=n - 100) == pytest.approx(0.01, rel=0.1)
    assert 0.005 < LQ.roll_spread(bounce) < 0.02              # default 60-day window: noisy but positive
    # positively autocorrelated price changes (a trend): covariance >= 0, no estimate
    e = rng.standard_normal(200) * 0.5
    dp = np.zeros(200)
    for t in range(1, 200):
        dp[t] = 0.6 * dp[t - 1] + e[t]
    trend = pd.DataFrame({"close": 100 + np.cumsum(dp)}, index=pd.bdate_range("2020-01-01", periods=200))
    assert LQ.roll_spread(trend) is None
    assert LQ.roll_spread(bounce.iloc[:19]) is None


def test_liquidity_profile_close_and_volume_only():
    df = ohlcv_frame()[["close", "volume"]]
    assert LQ.corwin_schultz(df) is None
    out = LQ.liquidity_profile(df)
    assert out["available"] is True and out["spread_cs"] is None and out["spread_source"] == "typical"


def test_typical_spread_nan_dollar_volume():
    assert LQ.typical_spread(float("nan"), 50.0) == LQ.typical_spread(None, 50.0)


# ============================================================================== HAR-RV
def test_daily_rv_proxy():
    d = ohlc_from_vols(np.full(300, 0.30), seed=1)
    rv = V._daily_rv(d)
    gap2 = np.log(d["open"] / d["close"].shift(1)) ** 2
    gk = 0.5 * np.log(d["high"] / d["low"]) ** 2 - (2 * math.log(2) - 1) * np.log(d["close"] / d["open"]) ** 2
    pd.testing.assert_series_equal(rv, (gap2 + gk.clip(lower=0)).iloc[1:], check_names=False)
    assert rv.mean() * 252 == pytest.approx(0.30 ** 2, rel=0.2)
    c = d["close"]                                             # closes only: squared log returns
    pd.testing.assert_series_equal(V._daily_rv(c), (np.log(c / c.shift(1)) ** 2).iloc[1:], check_names=False)


def test_har_rv_constant_volatility():
    sigma = 0.30
    d = ohlc_from_vols(np.full(700, sigma), seed=4)
    out = V.har_rv(d)
    dumps(out)
    assert out["n"] == 699
    fc = {f["h"]: f for f in out["forecasts"]}
    assert list(fc) == [1, 5, 21, 63]
    assert fc[21]["vol"] == pytest.approx(sigma, rel=0.2)
    vols = [f["vol"] for f in out["forecasts"]]
    assert max(vols) / min(vols) < 1.1                         # constant vol: flat forecast term structure
    for f in out["forecasts"]:
        assert set(f["coef"]) == {"const", "day", "week", "month"}
        assert 0 <= f["r2"] < 0.3                              # nothing persistent to explain
    assert set(out["current"]) == {"day", "week", "month"} and all(0.1 < v < 0.6 for v in out["current"].values())
    fit = out["fit"]
    assert len(fit["t"]) == len(fit["actual"]) == len(fit["fitted"]) == 504
    assert fit["t"] == sorted(fit["t"]) and fit["t"][-1] < d.index[-1].strftime("%Y-%m-%d")
    assert all(v > 0 for v in fit["actual"] + fit["fitted"])
    # the same shocks at twice the vol: every forecast doubles (log-HAR is scale-equivariant)
    twice = V.har_rv(ohlc_from_vols(np.full(700, 2 * sigma), seed=4))
    for f1, f2 in zip(out["forecasts"], twice["forecasts"]):
        assert f2["vol"] == pytest.approx(2 * f1["vol"], rel=1e-9)
        assert f2["coef"]["day"] == pytest.approx(f1["coef"]["day"], abs=1e-9)


def test_har_rv_volatility_regimes_mean_revert():
    """Vol alternates between 15 % and 50 % in 63-day blocks: the fit learns persistence, so the
    1-day forecast follows the current regime while the 63-day one reverts towards the average."""
    blocks = np.repeat([0.15, 0.50] * 6, 63)
    high = V.har_rv(ohlc_from_vols(blocks[:-40], seed=11))      # ends 23 days into a 50 % block
    low = V.har_rv(ohlc_from_vols(blocks[:-103], seed=12))      # ends 23 days into a 15 % block
    for out in (high, low):
        dumps(out)
        assert [f["h"] for f in out["forecasts"]] == [1, 5, 21, 63]
        assert out["forecasts"][0]["r2"] > 0.3
    hv = [f["vol"] for f in high["forecasts"]]
    lv = [f["vol"] for f in low["forecasts"]]
    assert hv[0] > hv[-1] + 0.05 and lv[0] < lv[-1] - 0.05
    assert hv[0] > 2 * lv[0]


def test_har_rv_short_history():
    assert V.har_rv(ohlc_from_vols(np.full(140, 0.30))) == {"forecasts": [], "current": None, "fit": None, "n": 139}
    dumps(V.har_rv(pd.Series(dtype=float)))


def test_har_rv_real_nvda(nvda_ohlcv):
    out = V.har_rv(nvda_ohlcv.tail(1600))
    dumps(out)
    assert [f["h"] for f in out["forecasts"]] == [1, 5, 21, 63]
    assert all(0.15 < f["vol"] < 1.5 and 0 <= f["r2"] < 1 for f in out["forecasts"])
    assert len(out["fit"]["t"]) == 504


def test_har_rv_close_only_forecasts_unbiased(synthetic):
    sigma = 0.30
    out = V.har_rv(synthetic(n=1500, mu=0.05, sigma=sigma, seed=2))
    assert [f["h"] for f in out["forecasts"]] == [1, 5, 21, 63]
    for f in out["forecasts"]:
        assert f["vol"] == pytest.approx(sigma, rel=0.3), f["h"]


# ============================================================================== random-walk tests
@pytest.mark.parametrize("phi", [0.0, 0.3, -0.3])
def test_variance_ratios_match_arch_reference(phi):
    VarianceRatio = pytest.importorskip("arch.unitroot").VarianceRatio
    p = ar1_closes(phi=phi)
    out = RW.variance_ratios(p)
    dumps(out)
    assert [o["q"] for o in out] == [2, 5, 10, 20]
    x = np.log(p.to_numpy())
    for o in out:
        ref = VarianceRatio(x, lags=o["q"], trend="c", debiased=True, robust=True, overlap=True)
        assert o["vr"] == pytest.approx(ref.vr, rel=1e-9)


def test_variance_ratios_direction_of_autocorrelation():
    def rho1(s):
        return pd.Series(np.diff(np.log(s.to_numpy()))).autocorr(1)

    up, down = ar1_closes(phi=0.3), ar1_closes(phi=-0.3)
    vu, vd = RW.variance_ratios(up), RW.variance_ratios(down)
    assert vu[0]["vr"] == pytest.approx(1 + rho1(up), abs=0.03)      # VR(2) = 1 + first autocorrelation
    assert vd[0]["vr"] == pytest.approx(1 + rho1(down), abs=0.03)
    assert all(o["vr"] > 1.2 for o in vu) and all(o["vr"] < 0.8 for o in vd)
    assert [o["vr"] for o in vu] == sorted(o["vr"] for o in vu)       # rises towards (1 + phi) / (1 - phi)


def test_variance_ratios_random_walk_not_rejected():
    out = RW.variance_ratios(ar1_closes(phi=0.0))
    for o in out:
        assert abs(o["vr"] - 1) < 0.1 and abs(o["z"]) < 2 and o["p"] > 0.05
    assert RW.variance_ratios(ar1_closes(n=50)) == []
    assert [o["q"] for o in RW.variance_ratios(ar1_closes(n=70), qs=(2, 40))] == [2]   # q >= n/2 skipped


def test_random_walk_tests_on_a_random_walk():
    out = RW.random_walk_tests(ar1_closes(phi=0.0))
    dumps(out)
    assert out["n"] == 1501 and out["verdict"] == "random walk" and out["verdict_detail"]
    assert [v["q"] for v in out["variance_ratios"]] == [2, 5, 10, 20]
    assert 0.4 < out["hurst"] < 0.6
    assert out["adf"]["p"] > 0.1 and out["adf"]["stat"] > out["adf"]["crit_5"]          # unit root kept
    assert [lb["lag"] for lb in out["ljung_box"]] == [5, 10] and min(lb["p"] for lb in out["ljung_box"]) > 0.05
    assert min(lb["p"] for lb in out["ljung_box_sq"]) > 0.05                              # no ARCH effects
    acf = out["acf"]
    assert acf["lags"] == list(range(1, 11)) and len(acf["v"]) == 10
    assert acf["band"] == pytest.approx(1.96 / math.sqrt(1500))
    assert all(abs(v) < 2 * acf["band"] for v in acf["v"])


def test_random_walk_tests_diagnostics_see_autocorrelation():
    """Ljung-Box, the ACF and Hurst pick up AR(1) returns (independently of the variance ratios)."""
    out = RW.random_walk_tests(ar1_closes(phi=0.3))
    dumps(out)
    assert all(lb["p"] < 1e-6 for lb in out["ljung_box"])
    assert out["acf"]["v"][0] == pytest.approx(0.3, abs=0.06)
    assert out["hurst"] > RW.random_walk_tests(ar1_closes(phi=0.0))["hurst"]
    short = RW.random_walk_tests(ar1_closes(n=100))
    dumps(short)
    assert short["n"] == 101 and short["verdict"] is None and short["variance_ratios"] == [] and short["hurst"] is None




def test_variance_ratio_z_matches_lo_mackinlay():
    VarianceRatio = pytest.importorskip("arch.unitroot").VarianceRatio
    p = ar1_closes(phi=0.3)
    x = np.log(p.to_numpy())
    for o in RW.variance_ratios(p):
        ref = VarianceRatio(x, lags=o["q"], trend="c", debiased=True, robust=True, overlap=True)
        assert o["z"] == pytest.approx(ref.stat, rel=1e-6), o["q"]
        assert o["p"] == pytest.approx(ref.pvalue, rel=1e-6, abs=1e-12), o["q"]


def test_variance_ratios_significant_for_autocorrelated_returns():
    for phi in (0.3, -0.3):
        for o in RW.variance_ratios(ar1_closes(phi=phi)):
            if o["q"] <= 10:
                assert o["p"] < 0.001, (phi, o)


def test_random_walk_tests_verdicts():
    assert RW.random_walk_tests(ar1_closes(phi=0.3))["verdict"] == "trending"
    assert RW.random_walk_tests(ar1_closes(phi=-0.3))["verdict"] == "mean-reverting"


def test_variance_ratios_json_safe_for_stale_prices():
    p = np.full(100, 100.0)
    p[30:70] = 110.0
    out = RW.variance_ratios(pd.Series(p, index=pd.bdate_range("2020-01-01", periods=100)))
    assert [o["q"] for o in out] == [2, 5, 10, 20]
    dumps(out)


# ============================================================================== risk-neutral density
def test_risk_neutral_density_flat_smile_is_lognormal(flat_chain):
    out = O.risk_neutral_density(*flat_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    dumps(out)
    assert out["available"] is True and out["method"] in ("svi", "quadratic") and out["expiry"] == EXP60
    assert out["T"] == pytest.approx(T60) and out["dte"] == pytest.approx(T60 * 365)
    assert out["spot"] == S0 and out["forward"] == pytest.approx(F60, rel=1e-4)
    assert out["atm_iv"] == pytest.approx(VOL0, abs=2e-3) and out["n_quotes"] > 100
    assert out["mass_in_grid"] > 0.95 and out["negative_mass"] < 1e-6
    for key, p in (("p5", 0.05), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p95", 0.95)):
        expected = F60 * math.exp(-0.5 * SD60 ** 2 + SD60 * stats.norm.ppf(p))
        assert out["quantiles"][key] == pytest.approx(expected, rel=0.01), key
    # moments of S_T / S - 1: mean F / S - 1 (a martingale), lognormal sd, skewness and kurtosis
    w = math.exp(SD60 ** 2)
    assert out["mean"] == pytest.approx(F60 / S0 - 1, abs=1e-4)
    assert out["sd"] == pytest.approx(F60 / S0 * math.sqrt(w - 1), rel=0.01)
    assert out["skew"] == pytest.approx((w + 2) * math.sqrt(w - 1), abs=0.02)
    assert out["kurtosis"] == pytest.approx(w ** 4 + 2 * w ** 3 + 3 * w ** 2 - 3, abs=0.05)
    pr = out["prob"]
    assert pr["up"] == pytest.approx(1 - lognormal_below(S0), abs=0.01)      # 0.5 adjusted for drift
    assert pr["down_10"] == pytest.approx(lognormal_below(0.9 * S0), abs=0.01)
    assert pr["down_20"] == pytest.approx(lognormal_below(0.8 * S0), abs=0.01)
    assert pr["up_10"] == pytest.approx(1 - lognormal_below(1.1 * S0), abs=0.01)
    assert pr["up_20"] == pytest.approx(1 - lognormal_below(1.2 * S0), abs=0.01)
    k, pdf, ln = (np.array(out["curve"][c]) for c in ("k", "pdf", "lognormal"))
    assert k.size == pdf.size == ln.size > 100 and np.all(np.diff(k) > 0) and np.all(pdf >= 0)
    assert np.max(np.abs(pdf - ln)) < 0.01 * ln.max()                       # Breeden-Litzenberger = lognormal
    assert np.trapezoid(pdf, k) == pytest.approx(1.0, abs=0.01)


def test_risk_neutral_density_put_skew(flat_chain, skew_chain):
    flat = O.risk_neutral_density(*flat_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    skew = O.risk_neutral_density(*skew_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    dumps(skew)
    assert skew["available"] and skew["atm_iv"] == pytest.approx(VOL0, abs=0.01)
    assert skew["skew"] < 0 < flat["skew"] and skew["skew"] < flat["skew"] - 0.3
    assert skew["prob"]["down_20"] > flat["prob"]["down_20"] and skew["prob"]["up_20"] < flat["prob"]["up_20"]
    assert skew["quantiles"]["p5"] < flat["quantiles"]["p5"]
    assert skew["mean"] == pytest.approx(F60 / S0 - 1, abs=1e-4)          # still a martingale


def test_risk_neutral_density_thin_chain():
    thin = make_chain(S0, T60, R0, Q0, lambda k: VOL0, [95, 100, 105])
    out = O.risk_neutral_density(*thin, S0, EXP60, ASOF, r=R0, q=Q0)
    dumps(out)
    assert out["available"] is False and out["message"]
    assert O.risk_neutral_density(None, None, S0, EXP60, ASOF)["available"] is False


def test_risk_neutral_density_real_nvda(nvda_options):
    S, asof = nvda_options["spot"], nvda_options["asof"]
    e = nearest_expiry(nvda_options)
    ch = nvda_options["chains"][e]
    out = O.risk_neutral_density(ch["calls"], ch["puts"], S, e, asof, r=0.04, q=0.0067)
    dumps(out)
    assert out["available"] and out["expiry"] == e and out["dte"] >= 7
    qs = [out["quantiles"][k] for k in ("p5", "p25", "p50", "p75", "p95")]
    assert all(a < b for a, b in zip(qs, qs[1:])) and qs[0] < S < qs[-1]
    pr = out["prob"]
    assert all(0 <= v <= 1 for v in pr.values())
    assert pr["down_20"] <= pr["down_10"] <= 1 - pr["up"] and pr["up_20"] <= pr["up_10"] <= pr["up"]
    assert 0.9 < out["mass_in_grid"] < 1.05 and abs(out["forward"] / S - 1) < 0.03 and 0.1 < out["atm_iv"] < 2
    assert all(v >= 0 for v in out["curve"]["pdf"])
    for exp, c in nvda_options["chains"].items():            # every expiry of the snapshot gives a density
        res = O.risk_neutral_density(c["calls"], c["puts"], S, exp, asof, r=0.04, q=0.0067)
        dumps(res)
        assert res["available"] and 0.9 < res["mass_in_grid"] < 1.05, exp


def test_risk_neutral_density_cdf_has_no_half_step_offset(flat_chain):
    out = O.risk_neutral_density(*flat_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    assert out["prob"]["up"] == pytest.approx(1 - lognormal_below(S0), abs=0.002)
    assert out["quantiles"]["p50"] == pytest.approx(F60 * math.exp(-0.5 * SD60 ** 2), rel=5e-4)


# ============================================================================== model-free IV
def test_model_free_iv_flat_smile(flat_chain):
    out = O.model_free_iv(*flat_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    dumps(out)
    assert out["expiry"] == EXP60 and out["T"] == pytest.approx(T60) and out["dte"] == pytest.approx(T60 * 365)
    assert out["mfiv"] == pytest.approx(VOL0, rel=0.01)
    assert out["variance"] == pytest.approx(out["mfiv"] ** 2)
    assert out["forward"] == pytest.approx(F60, rel=1e-4)
    assert out["k_min"] < F60 < out["k_max"] and out["n_strikes"] > 100
    coarse = make_chain(S0, T60, R0, Q0, lambda k: VOL0, np.arange(70, 135, 5.0))
    c = O.model_free_iv(*coarse, S0, EXP60, ASOF, r=R0, q=Q0)
    assert c["mfiv"] == pytest.approx(VOL0, rel=0.05)
    assert c["n_strikes"] == 13 and (c["k_min"], c["k_max"]) == (70.0, 130.0)


def test_model_free_iv_vix_strike_truncation(flat_chain):
    """VIX rule: the strip stops after two consecutive strikes without a bid; a single gap is skipped."""
    calls, puts = (x.copy() for x in flat_chain)
    puts.loc[puts["strike"].isin([70.0, 71.0, 80.0]), "bid"] = 0.0
    calls.loc[calls["strike"].isin([130.0, 150.0, 151.0]), "bid"] = 0.0
    out = O.model_free_iv(calls, puts, S0, EXP60, ASOF, r=R0, q=Q0)
    full = O.model_free_iv(*flat_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    assert full["k_min"] < 70 and full["k_max"] > 151
    assert (out["k_min"], out["k_max"]) == (72.0, 149.0)
    assert out["n_strikes"] == (149 - 72 + 1) - 2                  # 80 and 130 skipped, not stopping the strip
    assert out["mfiv"] == pytest.approx(VOL0, rel=0.01)


def test_model_free_iv_exceeds_atm_iv_under_skew(skew_chain):
    out = O.model_free_iv(*skew_chain, S0, EXP60, ASOF, r=R0, q=Q0)
    dumps(out)
    atm = O.chain_analytics(*skew_chain, S0, EXP60, ASOF, r=R0, q=Q0)["atm_iv"]
    assert out["mfiv"] > atm + 0.005


def test_model_free_iv_real_nvda(nvda_options):
    S, asof = nvda_options["spot"], nvda_options["asof"]
    for e, ch in nvda_options["chains"].items():
        out = O.model_free_iv(ch["calls"], ch["puts"], S, e, asof, r=0.04, q=0.0067)
        dumps(out)
        assert out["expiry"] == e and 0.1 < out["mfiv"] < 2.0 and out["n_strikes"] >= 4, e
        assert out["k_min"] < out["forward"] < out["k_max"], e
        if out["dte"] >= 7:                     # wide strips under NVDA's smile: above the ATM vol
            atm = O.chain_analytics(ch["calls"], ch["puts"], S, e, asof, r=0.04, q=0.0067)["atm_iv"]
            assert out["mfiv"] > atm, e


def test_model_free_iv_thin_chain_keeps_documented_keys():
    thin = make_chain(S0, T60, R0, Q0, lambda k: VOL0, [95, 100, 105])
    out = O.model_free_iv(*thin, S0, EXP60, ASOF, r=R0, q=Q0)
    dumps(out)
    assert out["mfiv"] is None and out["n_strikes"] == 0
    assert {"expiry", "T", "dte", "mfiv", "variance", "n_strikes", "k_min", "k_max", "forward"} <= set(out)


# ============================================================================== systemic risk
def test_absorption_ratio_one_factor_vs_independent():
    one = SY.absorption_ratio(closes_from_log(factor_universe(loading=2.0, seed=1)))
    ind = SY.absorption_ratio(closes_from_log(factor_universe(loading=0.0, seed=2)))
    for out in (one, ind):
        dumps(out)
        assert out["available"] is True and out["n_assets"] == 20 and out["n_top"] == 4 and out["window"] == 252
        ser = out["series"]
        assert len(ser["t"]) == len(ser["ar"]) == len(ser["pc1"]) >= 10 and ser["t"] == sorted(ser["t"])
        assert out["current"] == ser["ar"][-1] and out["pc1"] == ser["pc1"][-1]
        assert 0 <= out["percentile"] <= 100 and all(p <= a <= 1 for p, a in zip(ser["pc1"], ser["ar"]))
    # equal loadings, correlation 0.8: eigenvalues 1 + 19 x 0.8 and 0.2, so AR = (16.2 + 3 x 0.2) / 20
    assert one["current"] == pytest.approx(0.84, abs=0.04) and one["pc1"] == pytest.approx(0.81, abs=0.05)
    assert ind["current"] < 0.35 and ind["pc1"] < 0.15


def test_absorption_ratio_shift_after_correlated_selloff():
    """Three weeks of large common moves at the end: the standardised shift jumps above +1."""
    rng = np.random.default_rng(3)
    R = factor_universe(n_days=600, loading=0.3, seed=3)
    R[-15:] = (rng.standard_normal(15) * 0.05)[:, None] + rng.standard_normal((15, 20)) * 0.005
    out = SY.absorption_ratio(closes_from_log(R))
    dumps(out)
    assert out["shift"] > 1 and out["percentile"] == 100.0


def test_absorption_ratio_needs_assets_and_history():
    R = factor_universe(loading=2.0, seed=1)
    assert SY.absorption_ratio(closes_from_log(R[:200]))["available"] is False
    assert SY.absorption_ratio(closes_from_log(R[:, :8])) == {"available": False, "n_assets": 8, "window": 252}


def test_turbulence_iid_returns_and_injected_shocks():
    R = factor_universe(n_days=600, loading=0.0, seed=4)
    calm = SY.turbulence(closes_from_log(R))
    dumps(calm)
    assert calm["available"] is True and calm["n_assets"] == 20
    d = np.array(calm["series"]["d"])
    assert 0.6 < d.mean() < 1.6                                # Mahalanobis distance / N: ~1 on a normal day
    assert calm["threshold_95"] == pytest.approx(np.quantile(d, 0.95))
    assert calm["current"] == pytest.approx(d[-1]) and calm["current_smooth"] == pytest.approx(d[-10:].mean())
    assert len(calm["series"]["t"]) == d.size == len(calm["series"]["smooth"])
    shocked = R.copy()
    shocked[-10] = np.where(np.arange(20) % 2 == 0, 0.05, -0.05)   # correlations break: half +5 %, half -5 %
    shocked[-1, 7] = 0.12                                            # one stock jumps 12 % on the last day
    cs = closes_from_log(shocked)
    out = SY.turbulence(cs)
    dumps(out)
    t, v = out["series"]["t"], out["series"]["d"]
    i = t.index(cs.index[-10].strftime("%Y-%m-%d"))
    assert v[i] > max(5.0, out["threshold_95"])
    assert out["current"] > out["threshold_95"] and out["turbulent_days_21"] >= 2 and out["percentile"] > 95
    top = out["contributors"]
    assert len(top) == 6 and top[0]["ticker"] == "S07" and top[0]["share"] > 0.5
    assert t == calm["series"]["t"] and v[:i] == pytest.approx(calm["series"]["d"][:i])   # no look-ahead


def test_turbulence_needs_assets_and_history():
    R = factor_universe(n_days=600, seed=4)
    assert SY.turbulence(closes_from_log(R[:260]))["available"] is False
    assert SY.turbulence(closes_from_log(R[:, :9]))["available"] is False


def test_systemic_real_closes(closes):
    ar, tb = SY.absorption_ratio(closes), SY.turbulence(closes)
    dumps(ar)
    dumps(tb)
    assert ar["available"] and 0 < ar["pc1"] <= ar["current"] <= 1 and 0 <= ar["percentile"] <= 100
    assert tb["available"] and tb["current"] >= 0 and tb["threshold_95"] > 0 and 0 <= tb["percentile"] <= 100
    assert len(tb["contributors"]) == 6 and {c["ticker"] for c in tb["contributors"]} <= set(closes.columns)


def test_shrunk_cov_matches_sklearn_ledoit_wolf():
    LedoitWolf = pytest.importorskip("sklearn.covariance").LedoitWolf
    rng = np.random.default_rng(0)
    X = rng.standard_normal((120, 15)) * np.linspace(0.5, 2.0, 15) + 0.3 * rng.standard_normal((120, 1))
    np.testing.assert_allclose(SY._shrunk_cov(pd.DataFrame(X)), LedoitWolf().fit(X).covariance_, rtol=1e-10, atol=1e-14)


# ============================================================================== factor lab
def test_signal_frames_values_and_no_lookahead():
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2019-01-01", periods=400)
    c = pd.DataFrame(50 * np.exp(np.cumsum(0.0005 + 0.02 * rng.standard_normal((400, 6)), axis=0)),
                     index=idx, columns=list("ABCDEF"))
    sig = FL.signal_frames(c)
    assert set(sig) == {k for k, *_ in FL.SIGNALS}
    for k, frame in sig.items():
        assert frame.index.equals(c.index) and list(frame.columns) == list(c.columns), k
        assert frame.iloc[:252].notna().sum().sum() < frame.size and frame.iloc[252:].notna().all().all(), k
    assert sig["mom_12_1"].iloc[:252].isna().all().all()      # needs 12 months of history
    i, col = 330, "C"
    v = c[col].to_numpy()
    r = c.pct_change()
    ew, ri = r.mean(axis=1).to_numpy(), r[col].to_numpy()
    expected = {
        "mom_12_1": v[i - 21] / v[i - 252] - 1,
        "reversal_1m": -(v[i] / v[i - 21] - 1),
        "low_vol": -np.std(ri[i - 62:i + 1], ddof=1),
        "high_52w": v[i] / v[i - 251:i + 1].max(),
        "trend_200": v[i] / v[i - 199:i + 1].mean() - 1,
        "low_beta": -np.cov(ri[i - 251:i + 1], ew[i - 251:i + 1])[0, 1] / np.var(ew[i - 251:i + 1], ddof=1),
    }
    for k, e in expected.items():
        assert sig[k][col].iloc[i] == pytest.approx(e, rel=1e-9), k
    # no look-ahead: changing prices after day i leaves every signal up to day i unchanged
    moved = c.copy()
    moved.iloc[i + 1:] *= np.exp(0.3 * rng.standard_normal((400 - i - 1, 6)))
    sig2 = FL.signal_frames(moved)
    for k in sig:
        pd.testing.assert_frame_equal(sig[k].iloc[:i + 1], sig2[k].iloc[:i + 1])
        assert not sig[k].iloc[i + 1:].equals(sig2[k].iloc[i + 1:]), k


@pytest.fixture(scope="module")
def momentum_lab():
    c = drift_universe()
    return c, FL.factor_lab(c, years=5, names={t: f"Name {t}" for t in c.columns})


def test_factor_lab_detects_momentum(momentum_lab):
    c, out = momentum_lab
    dumps(out)
    assert out["available"] is True and out["n_assets"] == 30 and out["months"] >= 24
    assert out["start"] < out["end"] and out["caveats"]
    assert [s["key"] for s in out["signals"]] == [k for k, *_ in FL.SIGNALS]
    sig = {s["key"]: s for s in out["signals"]}
    mom = sig["mom_12_1"]
    assert mom["ic_mean"] > 0.1 and mom["ic_t"] > 3 and mom["hit_rate"] > 0.7
    assert mom["spread"]["ann"] > 0 and mom["spread"]["sharpe"] > 0 and mom["spread"]["hit"] > 0.5
    assert mom["quintiles"][-1] > mom["quintiles"][0]
    assert sig["reversal_1m"]["ic_mean"] < 0           # minus last month's return bets against the drift
    for s in out["signals"]:
        n = s["months"]
        assert n == out["months"] and len(s["ic_series"]["t"]) == len(s["ic_series"]["v"]) == n
        assert len(s["spread_cum"]["v"]) == n and len(s["quintiles"]) == 5 and s["label"] and s["desc"]
        assert s["ic_mean"] == pytest.approx(np.mean([x for x in s["ic_series"]["v"] if x is not None]))
        assert s["ic_t"] == pytest.approx(s["ic_mean"] / s["ic_sd"] * math.sqrt(n))
        assert s["ic_ir"] == pytest.approx(s["ic_mean"] / s["ic_sd"] * math.sqrt(12))
        assert set(s["decay"]) == {"1", "3", "6"} and s["decay"]["1"] == pytest.approx(s["ic_mean"])
        assert 0 <= s["hit_rate"] <= 1 and 0 <= s["turnover"] <= 1 and s["spread"]["max_dd"] <= 0
    corr = np.array(out["signal_corr"]["z"], float)
    assert out["signal_corr"]["labels"] == [label for _, label, _ in FL.SIGNALS]
    assert corr.shape == (6, 6) and np.allclose(corr, corr.T) and np.allclose(np.diag(corr), 1.0)
    cur = out["current"]
    assert cur["asof"] == c.index[-1].strftime("%Y-%m-%d") and len(cur["top"]) == len(cur["bottom"]) == 10
    top = [row["composite"] for row in cur["top"]]
    bottom = [row["composite"] for row in cur["bottom"]]
    assert top == sorted(top, reverse=True) and bottom == sorted(bottom) and top[-1] > bottom[-1]
    for row in cur["top"] + cur["bottom"]:
        assert row["name"] == f"Name {row['ticker']}" and set(sig) <= set(row)


def test_factor_lab_insufficient_data(momentum_lab):
    c, _ = momentum_lab
    few = FL.factor_lab(c.iloc[:, :10], years=5)
    short = FL.factor_lab(c.iloc[:400], years=5)
    for out in (few, short):
        dumps(out)
        assert out["available"] is False and out["message"]
    assert few["n_assets"] == 10 and short["n_assets"] == 30


def test_factor_lab_real_closes(closes):
    semis = ["NVDA", "AMD", "TSM", "AVGO", "INTC", "MU", "QCOM", "TXN", "ADI", "AMAT", "LRCX", "KLAC"]
    out = FL.factor_lab(closes[semis], years=3, min_names=8)
    dumps(out)
    assert out["available"] and out["n_assets"] == 12 and out["months"] >= 24
    for s in out["signals"]:
        assert -1 <= s["ic_mean"] <= 1 and 0 <= s["hit_rate"] <= 1 and s["months"] == out["months"]
    assert {row["ticker"] for row in out["current"]["top"]} <= set(semis)


def test_factor_lab_max_drawdown_counts_first_month(momentum_lab):
    _, out = momentum_lab
    for s in out["signals"]:
        wealth = np.concatenate([[1.0], 1.0 + np.array(s["spread_cum"]["v"], float)])
        expected = float((wealth / np.maximum.accumulate(wealth) - 1.0).min())
        assert s["spread"]["max_dd"] == pytest.approx(expected, abs=1e-12), s["key"]
