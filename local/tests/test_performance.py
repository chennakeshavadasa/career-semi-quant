"""Tests for semiquant.analytics.performance (offline; synthetic known answers + real fixtures)."""
from __future__ import annotations

import json
import math
import time

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import performance as P


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def exp_series(a: float = 0.0005, days: int = 4000, start: str = "2010-01-01") -> pd.Series:
    """Calendar-daily series growing exactly exp(a) per calendar day (closed-form returns)."""
    idx = pd.date_range(start, periods=days, freq="D")
    return pd.Series(100.0 * np.exp(a * np.arange(days)), index=idx)


# --------------------------------------------------------------------------- returns_table
def test_returns_table_known_answers():
    a = 0.0005
    s = exp_series(a)
    out = P.returns_table(s)
    vals = out["rows"][0]["values"]
    assert out["horizons"] == P.HORIZONS
    assert out["annualized"] == ["3Y", "5Y", "10Y", "MAX"]
    assert out["asof"] == s.index[-1].strftime("%Y-%m-%d")
    assert vals["1D"] == pytest.approx(math.exp(a) - 1, rel=1e-9)
    assert vals["5D"] == pytest.approx(math.exp(5 * a) - 1, rel=1e-9)
    last = s.index[-1]
    days_1y = (last - (last - pd.DateOffset(months=12))).days
    assert vals["1Y"] == pytest.approx(math.exp(a * days_1y) - 1, rel=1e-9)
    ytd_days = (last - pd.Timestamp(last.year - 1, 12, 31)).days
    assert vals["YTD"] == pytest.approx(math.exp(a * ytd_days) - 1, rel=1e-9)
    # CAGR of an exponential is exp(a * 365.25) - 1 whatever the window
    cagr = math.exp(a * 365.25) - 1
    for h in ("3Y", "5Y", "10Y", "MAX"):  # 4000 days ~ 10.95 years, so 10Y exists
        assert vals[h] == pytest.approx(cagr, rel=1e-9)
    assert out["base_dates"]["10Y"] == (last - pd.DateOffset(years=10)).strftime("%Y-%m-%d")
    dumps(out)


def test_returns_table_too_short_and_benchmark_alignment():
    s = exp_series(0.001, days=200, start="2024-01-01")
    bench = exp_series(0.0002, days=260, start="2024-01-01")  # extends beyond the asset
    out = P.returns_table(s, {"B": bench})
    v, b = out["rows"][0]["values"], out["rows"][1]["values"]
    assert out["rows"][1]["name"] == "B"
    assert v["1Y"] is None and v["3Y"] is None and b["1Y"] is None
    assert "MAX" not in out["annualized"]  # < 1 year: MAX is cumulative
    assert v["MAX"] == pytest.approx(math.exp(0.001 * 199) - 1, rel=1e-9)
    # benchmark measured over the asset's window (ends at the asset's last date)
    assert b["1M"] == pytest.approx(math.exp(0.0002 * (s.index[-1] - (s.index[-1] - pd.DateOffset(months=1))).days) - 1,
                                    rel=1e-9)
    assert b["MAX"] == pytest.approx(math.exp(0.0002 * 199) - 1, rel=1e-9)


def test_returns_table_real(closes):
    out = P.returns_table(closes["NVDA"], {"SPY": closes["SPY"], "SOXX": closes["SOXX"]})
    dumps(out)
    assert [r["name"] for r in out["rows"]] == ["Asset", "SPY", "SOXX"]
    nv = closes["NVDA"].dropna()
    assert out["asof"] == nv.index[-1].strftime("%Y-%m-%d")
    assert out["rows"][0]["values"]["1D"] == pytest.approx(nv.iloc[-1] / nv.iloc[-2] - 1)
    assert out["rows"][0]["values"]["10Y"] is None
    for row in out["rows"]:
        for h, val in row["values"].items():
            assert val is None or -1 < val < 100


def test_returns_table_edge_cases():
    assert P.returns_table(pd.Series(dtype=float))["rows"][0]["values"]["1D"] is None
    s = pd.Series([1.0, np.nan, 2.0, np.nan], index=pd.bdate_range("2024-01-01", periods=4))
    out = P.returns_table(s)
    assert out["rows"][0]["values"]["1D"] == pytest.approx(1.0)
    dumps(out)


# --------------------------------------------------------------------------- summary_stats
def test_summary_stats_gbm(synthetic):
    s = synthetic(n=2520, mu=0.10, sigma=0.30, seed=3)
    out = P.summary_stats(s, rf=0.0)
    dumps(out)
    assert out["vol"] == pytest.approx(0.30, abs=0.015)
    assert out["observations"] == 2520
    r = s.pct_change().dropna()
    assert out["sharpe"] == pytest.approx(r.mean() / r.std() * math.sqrt(252), rel=1e-9)
    assert out["total_return"] == pytest.approx(s.iloc[-1] / s.iloc[0] - 1)
    assert out["max_drawdown"] < 0 and out["current_drawdown"] <= 0
    assert out["var95"] == pytest.approx(-np.quantile(r, 0.05))
    assert out["cvar95"] >= out["var95"]
    assert abs(out["skew"]) < 0.3 and abs(out["kurtosis"]) < 0.5
    assert 0.4 < out["pct_up_days"] < 0.6
    assert out["omega"] == pytest.approx(r[r > 0].sum() / -r[r < 0].sum())


def test_summary_stats_benchmark_planted_beta():
    rng = np.random.default_rng(7)
    n = 2000
    idx = pd.bdate_range("2015-01-01", periods=n + 1)
    rb = rng.normal(0.0004, 0.01, n)
    ra = 0.0001 + 1.5 * rb + rng.normal(0, 0.005, n)
    b = pd.Series(100 * np.cumprod(np.r_[1.0, 1 + rb]), index=idx)
    a = pd.Series(100 * np.cumprod(np.r_[1.0, 1 + ra]), index=idx)
    out = P.summary_stats(a, b)
    dumps(out)
    assert out["beta"] == pytest.approx(1.5, abs=0.05)
    assert out["alpha"] == pytest.approx(0.0001 * 252, abs=0.03)
    assert out["correlation"] == pytest.approx(1.5 * 0.01 / math.sqrt((1.5 * 0.01) ** 2 + 0.005 ** 2), abs=0.02)
    assert out["r2"] == pytest.approx(out["correlation"] ** 2)
    assert out["up_capture"] > 1 and out["down_capture"] > 1
    # against itself: beta 1, correlation 1, tracking error 0
    same = P.summary_stats(b, b)
    assert same["beta"] == pytest.approx(1.0) and same["correlation"] == pytest.approx(1.0)
    assert same["tracking_error"] == pytest.approx(0.0, abs=1e-12)
    assert same["up_capture"] == pytest.approx(1.0) and same["down_capture"] == pytest.approx(1.0)


def test_summary_stats_drawdown_hand_series():
    idx = pd.bdate_range("2024-01-01", periods=6)
    s = pd.Series([100, 120, 90, 130, 65, 70], index=idx, dtype=float)
    out = P.summary_stats(s)
    assert out["max_drawdown"] == pytest.approx(-0.5)
    assert out["current_drawdown"] == pytest.approx(70 / 130 - 1)
    assert out["calmar"] == pytest.approx(out["cagr"] / 0.5) if out["cagr"] is not None else True


def test_summary_stats_real(closes):
    out = P.summary_stats(closes["NVDA"], closes["SPY"], rf=0.04)
    dumps(out)
    for k in P._STAT_KEYS + P._BENCH_KEYS:
        assert k in out
    assert 0.3 < out["vol"] < 0.8 and 1.0 < out["beta"] < 3.0 and -1 < out["max_drawdown"] < 0
    assert 0 < out["bench_vol"] < out["vol"]


@pytest.mark.parametrize("series", [
    pd.Series(50.0, index=pd.bdate_range("2024-01-01", periods=300)),
    pd.Series(np.linspace(10, 11, 10), index=pd.bdate_range("2024-01-01", periods=10)),
    pd.Series([1.0], index=pd.bdate_range("2024-01-01", periods=1)),
    pd.Series(dtype=float),
])
def test_summary_stats_edge(series):
    out = P.summary_stats(series, series)
    dumps(out)
    if len(series) == 300:
        assert out["vol"] == 0.0 and out["sharpe"] is None and out["max_drawdown"] == 0.0


def test_summary_stats_with_nans(closes):
    s = closes["NVDA"].copy()
    s.iloc[100:110] = np.nan
    dumps(P.summary_stats(s, closes["SPY"]))


# --------------------------------------------------------------------------- drawdowns
def test_drawdowns_hand_series():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    s = pd.Series([100, 110, 99, 88, 110, 120, 60, 90, 100, 95], index=idx, dtype=float)
    out = P.drawdowns(s, top=5)
    dumps(out)
    t = out["table"]
    assert len(t) == 2
    assert t[0]["depth"] == pytest.approx(-0.5) and t[0]["peak"] == "2024-01-06" and t[0]["trough"] == "2024-01-07"
    assert t[0]["recovery"] is None and t[0]["days_to_recover"] is None and t[0]["length"] == 4
    assert t[1]["depth"] == pytest.approx(-0.2) and t[1]["peak"] == "2024-01-02"
    assert t[1]["trough"] == "2024-01-04" and t[1]["recovery"] == "2024-01-05"
    assert t[1]["days_to_trough"] == 2 and t[1]["days_to_recover"] == 1 and t[1]["length"] == 3
    assert out["underwater"]["v"][6] == pytest.approx(-0.5)
    assert max(out["underwater"]["v"]) <= 0


def test_drawdowns_real(closes):
    out = P.drawdowns(closes["NVDA"], top=5)
    dumps(out)
    depths = [e["depth"] for e in out["table"]]
    assert depths == sorted(depths) and len(depths) == 5
    spans = sorted((e["peak"], e["recovery"] or "9999") for e in out["table"])
    for (p1, r1), (p2, _) in zip(spans, spans[1:]):
        assert r1 <= p2  # non-overlapping


def test_drawdowns_edge():
    dumps(P.drawdowns(pd.Series(dtype=float)))
    out = P.drawdowns(pd.Series(5.0, index=pd.bdate_range("2024-01-01", periods=20)))
    assert out["table"] == []


# --------------------------------------------------------------------------- rolling
def test_rolling_metrics(synthetic):
    s = synthetic(n=2000, sigma=0.25, seed=5)
    out = P.rolling_metrics(s, s, window=63)
    dumps(out)
    assert out["window"] == 63
    assert np.median(out["vol"]["v"]) == pytest.approx(0.25, abs=0.02)
    assert np.allclose(out["beta"]["v"], 1.0) and np.allclose(out["correlation"]["v"], 1.0)
    assert len(out["vol"]["t"]) == len(s) - 63
    assert out["return"]["v"][-1] == pytest.approx(s.iloc[-1] / s.iloc[-64] - 1)
    no_b = P.rolling_metrics(s)
    assert no_b["beta"] == {"t": [], "v": []}


def test_rolling_metrics_edge():
    dumps(P.rolling_metrics(pd.Series(np.arange(1, 11, dtype=float), index=pd.bdate_range("2024-01-01", periods=10))))
    out = P.rolling_metrics(pd.Series(3.0, index=pd.bdate_range("2024-01-01", periods=100)), window=20)
    dumps(out)
    assert all(v == 0.0 for v in out["vol"]["v"])


# --------------------------------------------------------------------------- monthly
def test_monthly_returns_known():
    a = 0.001
    s = exp_series(a, days=800, start="2021-01-01")
    out = P.monthly_returns(s)
    dumps(out)
    assert out["years"] == [2021, 2022, 2023]
    assert out["months"][0] == "Jan" and len(out["matrix"][0]) == 12
    # February 2022: 28 days of growth from Jan 31 to Feb 28
    assert out["matrix"][1][1] == pytest.approx(math.exp(28 * a) - 1, rel=1e-9)
    assert out["year_total"][1] == pytest.approx(math.exp(365 * a) - 1, rel=1e-9)
    # first month is measured from the first close (30 days in Jan 2021)
    assert out["matrix"][0][0] == pytest.approx(math.exp(30 * a) - 1, rel=1e-9)
    seas = {r["month"]: r for r in out["seasonality"]}
    # data runs 2021-01-01 .. 2023-03-11: Jan 2021 (first, partial) and Mar 2023 (unfinished) excluded
    assert (seas["Jan"]["n"], seas["Feb"]["n"], seas["Mar"]["n"], seas["Apr"]["n"]) == (2, 3, 2, 2)
    assert seas["Feb"]["hit_rate"] == 1.0
    assert seas["Feb"]["mean"] == pytest.approx(np.mean([math.exp(28 * a) - 1] * 3), rel=1e-9)


def test_monthly_returns_real(closes):
    out = P.monthly_returns(closes["SPY"])
    dumps(out)
    assert len(out["matrix"]) == len(out["years"]) == len(out["year_total"])
    assert sum(r["n"] for r in out["seasonality"]) > 70


# --------------------------------------------------------------------------- distribution
def test_return_distribution_gbm(synthetic):
    s = synthetic(n=3000, sigma=0.2, seed=11)
    out = P.return_distribution(s, bins=40)
    dumps(out)
    assert len(out["edges"]) == 41 and sum(out["counts"]) == out["n"] == 3000
    width = np.diff(out["edges"])
    assert float(np.sum(np.array(out["density"]) * width)) == pytest.approx(1.0)
    assert out["std"] == pytest.approx(0.2 / math.sqrt(252), rel=0.05)
    assert abs(out["kurtosis"]) < 0.4
    assert out["t_df"] > 15  # near-normal data -> large df
    q = out["quantiles"]
    assert q["1%"] < q["5%"] < q["25%"] < q["50%"] < q["75%"] < q["95%"] < q["99%"]
    assert len(out["normal_pdf"]["x"]) == len(out["t_pdf"]["y"]) == 200


def test_return_distribution_real_and_horizon(closes):
    out = P.return_distribution(closes["NVDA"])
    dumps(out)
    assert out["t_df"] < 8 and out["kurtosis"] > 2 and out["jarque_bera"]["p"] < 0.01
    o5 = P.return_distribution(closes["NVDA"], horizon=5)
    assert o5["horizon"] == 5 and o5["std"] > out["std"]


def test_t_mle_matches_scipy():
    from scipy import stats

    x = stats.t.rvs(3.5, size=3000, random_state=4) * 0.012 + 0.001
    mine = P._t_mle(x)
    ref = stats.t.fit(x)
    assert mine == pytest.approx(ref, rel=1e-3)
    assert stats.t.logpdf(x, *mine).sum() >= stats.t.logpdf(x, *ref).sum() - 1e-6
    assert P._t_mle(np.ones(50)) is None and P._t_mle(np.arange(5.0)) is None


def test_return_distribution_edge():
    dumps(P.return_distribution(pd.Series(7.0, index=pd.bdate_range("2024-01-01", periods=50))))
    dumps(P.return_distribution(pd.Series([1.0, 1.1], index=pd.bdate_range("2024-01-01", periods=2)), horizon=5))


def test_speed(closes):
    s = closes["NVDA"]
    t = time.perf_counter()
    P.summary_stats(s, closes["SPY"])
    P.returns_table(s, {"SPY": closes["SPY"]})
    P.drawdowns(s)
    assert time.perf_counter() - t < 0.5
