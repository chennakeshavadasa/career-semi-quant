"""Tests for semiquant.analytics.risk: VaR/ES known answers, GPD tail recovery, backtest
statistics, stress windows, factor shocks and tail summary."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from semiquant.analytics import risk as R


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def table(out):
    return {(r["method"], r["level"], r["horizon"]): r for r in out["table"]}


def normal_returns(n=5000, mu=0.0005, sd=0.02, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mu, sd, n), index=pd.bdate_range("2000-01-03", periods=n))


# --------------------------------------------------------------------------- var_es
def test_var_es_normal_known_answers():
    r = normal_returns()
    out = R.var_es(r)
    dumps(out)
    t = table(out)
    assert out["observations"] == len(r) and out["methods"] == R.VAR_METHODS
    assert len(out["table"]) == 6 * 2 * 2
    mu, sd = r.mean(), r.std()
    for lv in (0.95, 0.99):
        z = stats.norm.ppf(1 - lv)
        nv, ne = -(mu + sd * z), -(mu - sd * stats.norm.pdf(z) / (1 - lv))
        assert t[("normal", lv, 1)]["var"] == pytest.approx(nv, rel=1e-9)
        assert t[("normal", lv, 1)]["es"] == pytest.approx(ne, rel=1e-9)
        assert t[("normal", lv, 1)]["var"] == pytest.approx(-(0.0005 + 0.02 * z), rel=0.04)
        for m, tol in (("historical", 0.07), ("cornish_fisher", 0.05), ("student_t", 0.05), ("evt", 0.10),
                       ("filtered_hs", 0.12)):
            assert t[(m, lv, 1)]["var"] == pytest.approx(nv, rel=tol), m
            assert t[(m, lv, 1)]["es"] == pytest.approx(ne, rel=tol + 0.03), m
        for m in R.VAR_METHODS:
            row = t[(m, lv, 1)]
            assert row["es"] >= row["var"] > 0, m
        for m in ("normal", "cornish_fisher", "student_t", "evt"):  # sqrt-of-time scaling
            assert t[(m, lv, 10)]["var"] == pytest.approx(t[(m, lv, 1)]["var"] * math.sqrt(10))
            assert t[(m, lv, 10)]["es"] == pytest.approx(t[(m, lv, 1)]["es"] * math.sqrt(10))
        # historical 10-day: overlapping sums of log returns
        assert t[("historical", lv, 10)]["var"] == pytest.approx(-(10 * 0.0005 + math.sqrt(10) * 0.02 * z), rel=0.1)
        assert t[("filtered_hs", lv, 10)]["var"] == pytest.approx(t[("normal", lv, 10)]["var"], rel=0.15)
    assert out["evt"]["n_exceed"] == pytest.approx(500, abs=2)
    assert abs(out["evt"]["xi"]) < 0.15  # normal tails: xi ~ 0 (slightly negative)


def test_cornish_fisher_formula():
    # with zero skew / kurtosis the modified VaR / ES reduce to the normal ones
    v, e = R._cf_var_es(0.001, 0.02, 0.0, 0.0, 0.99)
    z = stats.norm.ppf(0.01)
    assert v == pytest.approx(-(0.001 + 0.02 * z))
    assert e == pytest.approx(-(0.001 - 0.02 * stats.norm.pdf(z) / 0.01))
    # ES equals the tail average of the Cornish-Fisher quantile function (numerical check)
    S, K, lv = -0.5, 3.0, 0.975
    ps = np.linspace(1e-7, 1 - lv, 200001)
    zs = stats.norm.ppf(ps)
    q = zs + (zs ** 2 - 1) * S / 6 + (zs ** 3 - 3 * zs) * K / 24 - (2 * zs ** 3 - 5 * zs) * S ** 2 / 36
    num_es = -float(np.trapezoid(q, ps) / (1 - lv))
    assert R._cf_var_es(0.0, 1.0, S, K, lv)[1] == pytest.approx(num_es, rel=2e-3)


def test_evt_recovers_gpd_tail():
    rng = np.random.default_rng(5)
    xi, beta = 0.3, 0.01
    L = stats.genpareto.rvs(c=xi, scale=beta, size=20000, random_state=rng)
    r = pd.Series(-L, index=pd.bdate_range("1950-01-02", periods=L.size))
    out = R.var_es(r, levels=(0.99, 0.995), horizons=(1,))
    assert out["evt"]["xi"] == pytest.approx(xi, abs=0.08)
    t = table(out)
    for lv in (0.99, 0.995):
        true_var = beta / xi * ((1 - lv) ** -xi - 1)
        true_es = (true_var + beta) / (1 - xi)
        assert t[("evt", lv, 1)]["var"] == pytest.approx(true_var, rel=0.08)
        assert t[("evt", lv, 1)]["es"] == pytest.approx(true_es, rel=0.12)


def test_student_t_fat_tails():
    rng = np.random.default_rng(3)
    x = stats.t.rvs(4, size=8000, random_state=rng) * 0.01
    out = R.var_es(pd.Series(x, index=pd.bdate_range("1990-01-01", periods=x.size)), levels=(0.99,), horizons=(1,))
    t = table(out)
    true = -stats.t.ppf(0.01, 4) * 0.01
    assert t[("student_t", 0.99, 1)]["var"] == pytest.approx(true, rel=0.08)
    assert t[("normal", 0.99, 1)]["var"] < t[("student_t", 0.99, 1)]["var"]


def test_var_es_real(closes):
    r = closes["NVDA"].dropna().pct_change().dropna()
    out = R.var_es(r)
    dumps(out)
    for row in out["table"]:
        assert row["var"] is not None and 0 < row["var"] < 1, row
        assert row["es"] >= row["var"] * 0.999
    assert out["fhs_vol_next"] > 0


@pytest.mark.parametrize("r", [
    pd.Series(np.random.default_rng(1).normal(0, 0.01, 10), index=pd.bdate_range("2024-01-01", periods=10)),
    pd.Series(0.0, index=pd.bdate_range("2024-01-01", periods=300)),
    pd.Series([0.01, np.nan, -0.02, np.inf, 0.005] * 40, index=pd.bdate_range("2024-01-01", periods=200)),
    pd.Series(dtype=float),
])
def test_var_es_edge(r):
    out = R.var_es(r)
    dumps(out)
    assert len(out["table"]) == 24


# --------------------------------------------------------------------------- backtest
def test_kupiec_christoffersen_and_traffic_light():
    x, n, p = 10, 500, 0.01
    phat = x / n
    lr = -2 * ((n - x) * math.log(1 - p) + x * math.log(p)) + 2 * ((n - x) * math.log(1 - phat) + x * math.log(phat))
    assert R._kupiec(x, n, p) == pytest.approx(lr)
    assert R._kupiec(0, 250, 0.01) == pytest.approx(-2 * 250 * math.log(0.99))
    hits = np.array([0, 0, 1, 1, 0, 0, 0, 1, 0, 0])  # n00=4, n01=2, n10=2, n11=1
    pi, pi01, pi11 = 3 / 9, 2 / 6, 1 / 3
    l0 = 6 * math.log(1 - pi) + 3 * math.log(pi)
    l1 = 4 * math.log(1 - pi01) + 2 * math.log(pi01) + 2 * math.log(1 - pi11) + 1 * math.log(pi11)
    assert R._christoffersen(hits) == pytest.approx(-2 * (l0 - l1), abs=1e-12)
    assert [R._traffic_light(k, 250, 0.01) for k in (0, 4, 5, 9, 10)] == ["green", "green", "yellow", "yellow", "red"]


@pytest.mark.parametrize("method", ["historical", "normal", "ewma"])
def test_backtest_correct_model(method):
    r = normal_returns(n=3500, mu=0.0, sd=0.015, seed=21)
    out = R.var_backtest(r, level=0.99, window=500, method=method)
    dumps(out)
    assert out["n"] == 3000 and out["expected"] == pytest.approx(30)
    if method == "ewma":
        # RiskMetrics' 0.94 variance estimate is noisy (~32 effective obs), so r / sigma is t-like and
        # the expected exception rate on i.i.d. normal data is ~1.3%, not 1%
        assert 0.008 < out["rate"] < 0.02
    else:
        assert out["kupiec"]["p"] > 0.05 and out["conditional_coverage"]["p"] > 0.05
    assert out["traffic_light"] in ("green", "yellow")
    assert len(out["exception_dates"]) == out["exceptions"] and out["rate"] == pytest.approx(out["exceptions"] / 3000)
    assert len(out["series"]["t"]) == len(out["series"]["var"]) == 750
    assert all(v > 0 for v in out["series"]["var"])


def test_backtest_detects_misspecification():
    rng = np.random.default_rng(9)
    x = np.r_[rng.normal(0, 0.008, 1500), rng.normal(0, 0.03, 500)]
    r = pd.Series(x, index=pd.bdate_range("2010-01-01", periods=x.size))
    out = R.var_backtest(r, 0.99, 500, "historical")
    # the 500-day window adapts within weeks, so the excess exceptions cluster after the jump
    assert out["rate"] > 0.02 and out["kupiec"]["p"] < 1e-4 and out["traffic_light"] == "red"
    assert out["conditional_coverage"]["p"] < 1e-3
    ew = R.var_backtest(r, 0.99, 500, "ewma")  # adapts quickly
    assert ew["exceptions"] < out["exceptions"]
    # independence: a run of consecutive exceptions is rejected, scattered ones are not
    clustered = np.zeros(1000, dtype=int)
    clustered[500:510] = 1
    scattered = np.zeros(1000, dtype=int)
    scattered[::100] = 1
    assert R._lr_p(R._christoffersen(clustered), 1)["p"] < 1e-6
    assert R._lr_p(R._christoffersen(scattered), 1)["p"] > 0.3


def test_backtest_edge(closes):
    dumps(R.var_backtest(closes["NVDA"].pct_change().dropna(), 0.99, 250, "normal"))
    short = R.var_backtest(normal_returns(n=100), 0.99, 500)
    assert short["n"] == 0 and short["exceptions"] is None
    dumps(short)
    bad = R.var_backtest(normal_returns(n=800), 0.99, 500, method="nope")
    assert "error" in bad
    dumps(R.var_backtest(pd.Series(0.0, index=pd.bdate_range("2020-01-01", periods=800)), 0.99, 500))


# --------------------------------------------------------------------------- stress
def test_stress_test_synthetic():
    idx = pd.bdate_range("2019-06-03", "2021-06-30")
    s = pd.Series(100.0, index=idx)
    crash = (idx >= "2020-02-19") & (idx <= "2020-03-23")
    s[crash] = np.linspace(100, 70, crash.sum())
    s[pd.Timestamp("2020-03-16")] = 60.0
    s[idx > "2020-03-23"] = 80.0
    b = pd.Series(200.0, index=idx)
    b[idx >= "2020-03-01"] = 150.0
    out = R.stress_test(s, {"B": b})
    dumps(out)
    rows = {r["name"]: r for r in out["rows"]}
    covid = rows["COVID crash"]
    assert covid["covered"] and covid["return"] == pytest.approx(-0.30) and covid["max_drawdown"] == pytest.approx(-0.40)
    assert covid["bench"]["B"] == pytest.approx(-0.25)
    gfc = rows["Global financial crisis"]
    assert gfc["covered"] is False and gfc["return"] is None and gfc["bench"]["B"] is None
    assert rows["2022 bear market"]["covered"] is False  # data ends before the window ends
    assert [r["name"] for r in out["rows"]] == [w[0] for w in R.STRESS_WINDOWS]


def test_stress_test_real(closes):
    out = R.stress_test(closes["NVDA"], {"SPY": closes["SPY"], "SOXX": closes["SOXX"]})
    dumps(out)
    rows = {r["name"]: r for r in out["rows"]}
    assert rows["COVID crash"]["covered"] and rows["COVID crash"]["bench"]["SPY"] < -0.25
    assert rows["Q4 2018 selloff"]["covered"] is False
    c = closes["NVDA"].dropna()
    base = c[c.index < "2022-01-03"].iloc[-1]
    assert rows["2022 bear market"]["return"] == pytest.approx(c[:"2022-10-12"].iloc[-1] / base - 1)
    dumps(R.stress_test(pd.Series(dtype=float), {}))


# --------------------------------------------------------------------------- shocks
def test_hypothetical_shocks_planted_betas():
    rng = np.random.default_rng(4)
    n = 800
    idx = pd.bdate_range("2021-01-04", periods=n)
    spy = 400 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    tnx = 3.0 + np.cumsum(rng.normal(0, 0.05, n))  # percent
    vix = 20 + np.cumsum(rng.normal(0, 0.8, n))
    levels = pd.DataFrame({"SPY": spy, "^TNX": tnx, "^VIX": vix}, index=idx)
    r_spy = levels["SPY"].pct_change()
    d_bp = levels["^TNX"].diff() * 100
    asset = (1.3 * r_spy - 0.0004 * d_bp + rng.normal(0, 0.004, n)).dropna()
    out = R.hypothetical_shocks(asset, levels)
    dumps(out)
    rows = {r["name"]: r for r in out["rows"]}
    assert set(rows) == {"S&P 500 -5%", "S&P 500 -10%", "S&P 500 -20%", "10Y yield +50bp", "10Y yield +100bp",
                         "VIX +10 pts"}
    assert rows["S&P 500 -10%"]["beta"] == pytest.approx(1.3, abs=0.06)
    assert rows["S&P 500 -10%"]["impact"] == pytest.approx(-0.10 * rows["S&P 500 -10%"]["beta"])
    assert rows["10Y yield +50bp"]["unit"] == "bp" and rows["VIX +10 pts"]["unit"] == "points"
    assert rows["10Y yield +50bp"]["beta"] == pytest.approx(-0.0004, abs=0.0001)
    assert rows["10Y yield +100bp"]["impact"] == pytest.approx(100 * rows["10Y yield +100bp"]["beta"])
    assert 515 <= rows["S&P 500 -5%"]["n"] <= 525  # two years of weekday data (bdate_range has no holidays)
    custom = R.hypothetical_shocks(asset, levels, shocks=[{"name": "Crash", "factor": "SPY", "shock": -0.3},
                                                         {"name": "Missing", "factor": "XYZ", "shock": 0.1}])
    assert [r["name"] for r in custom["rows"]] == ["Crash"]


def test_hypothetical_shocks_real(closes):
    r = closes["NVDA"].dropna().pct_change().dropna()
    out = R.hypothetical_shocks(r, closes[["SPY", "SOXX", "^TNX", "^VIX", "DX-Y.NYB", "CL=F"]])
    dumps(out)
    assert len(out["rows"]) == 11
    rows = {x["name"]: x for x in out["rows"]}
    assert rows["S&P 500 -10%"]["impact"] < -0.1 and rows["VIX +10 pts"]["beta"] < 0
    dumps(R.hypothetical_shocks(r.iloc[:5], closes[["SPY"]]))
    dumps(R.hypothetical_shocks(pd.Series(dtype=float), pd.DataFrame()))


# --------------------------------------------------------------------------- tail summary
def test_tail_risk_summary():
    rng = np.random.default_rng(2)
    r = rng.normal(0, 0.01, 20000)
    idx = pd.bdate_range("1940-01-01", periods=r.size + 1)
    c = pd.Series(100 * np.cumprod(np.r_[1.0, 1 + r]), index=idx)
    out = R.tail_risk_summary(c)
    dumps(out)
    assert out["es_to_vol"] == pytest.approx(stats.norm.pdf(stats.norm.ppf(0.025)) / 0.025, rel=0.04)
    assert out["var95_1d"] == pytest.approx(1.645 * 0.01, rel=0.04)
    assert out["var99_1d"] > out["var95_1d"] and out["es975_1d"] > out["var95_1d"]
    assert out["worst_week"] == pytest.approx((c / c.shift(5) - 1).min())
    assert out["worst_month"] == pytest.approx((c / c.shift(21) - 1).min())
    assert out["worst_day"] == pytest.approx(r.min())


def test_tail_risk_summary_real_and_edge(closes):
    out = R.tail_risk_summary(closes["NVDA"])
    dumps(out)
    assert out["es_to_vol"] > 2.34  # fat tails
    for s in (pd.Series(dtype=float), pd.Series([1.0, 1.1], index=pd.bdate_range("2024-01-01", periods=2)),
              pd.Series(3.0, index=pd.bdate_range("2024-01-01", periods=50))):
        dumps(R.tail_risk_summary(s))
