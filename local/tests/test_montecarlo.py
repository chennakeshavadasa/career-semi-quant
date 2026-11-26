"""Tests for semiquant.analytics.montecarlo: drift / volatility calibration, the stationary
bootstrap mechanics, speed and memory, vesting schedules, RSU and option grant valuation."""
from __future__ import annotations

import json
import math
import time
import tracemalloc

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import montecarlo as MC


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def flat(price=100.0, n=600, start="2023-01-02"):
    return pd.Series(price, index=pd.bdate_range(start, periods=n))


# --------------------------------------------------------------------------- simulate
def test_gbm_calibration(synthetic):
    s = synthetic(n=1500, mu=0.1, sigma=0.3, seed=2)
    out = MC.simulate(s, horizon_days=252, n_paths=20000, method="gbm", drift="custom", mu=0.10, seed=3)
    dumps(out)
    x = np.log(s).diff().dropna()
    x = x[x.index >= s.index[-1] - pd.DateOffset(years=5)]
    assert out["ann_vol_used"] == pytest.approx(x.std() * math.sqrt(252), rel=0.02)
    assert out["ann_drift_used"] == pytest.approx(0.10)
    assert out["terminal"]["mean"] / out["spot"] == pytest.approx(1.10, abs=0.01)
    z = MC.simulate(s, 252, 20000, "gbm", "zero", seed=4)
    assert z["terminal"]["mean"] / z["spot"] == pytest.approx(1.0, abs=0.01)
    rf = MC.simulate(s, 252, 20000, "gbm", "riskfree", rf=0.05, seed=5)
    assert rf["terminal"]["mean"] / rf["spot"] == pytest.approx(1.05, abs=0.01)
    hist = MC.simulate(s, 252, 20000, "gbm", "historical", seed=6)
    assert hist["terminal"]["median"] / hist["spot"] == pytest.approx(math.exp(x.mean() * 252), rel=0.02)


@pytest.mark.parametrize("method", ["gbm", "bootstrap", "garch"])
def test_zero_drift_is_martingale_on_real_data(closes, method):
    out = MC.simulate(closes["NVDA"], 252, 20000, method, "zero", seed=11)
    dumps(out)
    assert out["method"] == method and out["note"] is None
    # NVDA vol ~50%: standard error of the mean ~0.5%; heavy GARCH tails get more room
    assert out["terminal"]["mean"] / out["spot"] == pytest.approx(1.0, abs=0.02 if method != "garch" else 0.03)


def test_output_shape_and_consistency(closes):
    H = 300
    out = MC.simulate(closes["AMD"], H, 5000, "bootstrap", "historical", seed=1)
    dumps(out)
    p = out["percentiles"]
    days = p["days"]
    assert days[0] == 0 and days[-1] == H and len(days) <= 121 and days == sorted(set(days))
    assert len(p["dates"]) == len(days) and p["dates"][0] == closes["AMD"].dropna().index[-1].strftime("%Y-%m-%d")
    for i in range(len(days)):
        assert p["p5"][i] <= p["p25"][i] <= p["p50"][i] <= p["p75"][i] <= p["p95"][i]
    assert p["p50"][0] == pytest.approx(out["spot"]) and p["mean"][0] == pytest.approx(out["spot"])
    assert len(out["sample_paths"]) == 25 and all(len(sp) == len(days) for sp in out["sample_paths"])
    t = out["terminal"]
    assert t["p5"] <= t["median"] <= t["p95"] and 0 <= t["prob_loss"] <= 1
    assert t["prob_loss_20"] <= t["prob_loss"] and 0 <= t["prob_gain_20"] <= 1 - t["prob_loss"]
    assert 0.98 * 5000 <= sum(t["hist"]["counts"]) <= 5000 and len(t["hist"]["edges"]) == 51
    assert t["median"] == pytest.approx(p["p50"][-1], rel=1e-4)
    again = MC.simulate(closes["AMD"], H, 5000, "bootstrap", "historical", seed=1)
    assert again["terminal"] == out["terminal"]
    assert MC.simulate(closes["AMD"], H, 5000, "bootstrap", "historical", seed=2)["terminal"] != out["terminal"]


def test_stationary_bootstrap_mechanics():
    x = np.arange(10, dtype=float) / 1000.0
    e = x - x.mean()
    rec = np.arange(31)
    rng = np.random.default_rng(0)
    # zero drift and var_d = 0 make each increment exactly e[idx] = (idx - 4.5) / 1000
    paths, _ = MC._engine(x, 1.0, 30, 4, "bootstrap", 0.0, 0.0, 1e12, rng, rec)  # one block per path
    inc = np.diff(np.log(paths.astype(np.float64)), axis=0)
    for j in range(4):
        idx = np.rint(inc[:, j] * 1000 + 4.5).astype(int)
        assert set(idx) <= set(range(10)) and np.allclose(inc[:, j], e[idx], atol=1e-6)
        assert set(np.mod(np.diff(idx), 10)) == {1}, idx  # consecutive (circular) original returns
    paths1, _ = MC._engine(x, 1.0, 2000, 2, "bootstrap", 0.0, 0.0, 1.0, np.random.default_rng(1), np.arange(2001))
    inc1 = np.rint(np.diff(np.log(paths1.astype(np.float64)), axis=0)[:, 0] * 1000 + 4.5).astype(int)
    frac_next = np.mean(np.mod(np.diff(inc1), 10) == 1)
    assert frac_next < 0.2  # block = 1: i.i.d. resampling, consecutive only by chance (~10%)


def test_bootstrap_variance_correction():
    rng = np.random.default_rng(0)
    iid = rng.normal(0, 0.02, 5000)
    assert MC._bootstrap_var(iid - iid.mean(), 5) == pytest.approx(iid.var(), rel=0.1)
    alt = np.tile([1.0, -1.0], 500) * 0.01  # lag-k autocorrelation (-1)^k
    q = 0.8
    assert MC._bootstrap_var(alt, 5) == pytest.approx(alt.var() * (1 - q) / (1 + q), rel=1e-3)
    # strongly mean-reverting returns: the corrected drift keeps E[S_T] = S_0
    idx = pd.bdate_range("2015-01-01", periods=1501)
    eps = rng.normal(0, 0.02, 1501)
    r = eps - 0.6 * np.r_[0.0, eps[:-1]]
    s = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
    out = MC.simulate(s, 252, 20000, "bootstrap", "zero", block=10, seed=3)
    assert out["terminal"]["mean"] / out["spot"] == pytest.approx(1.0, abs=0.01)


def test_speed_and_memory(closes):
    s = closes["NVDA"]
    MC.simulate(s, 10, 100, "garch")  # warm imports
    for method in ("gbm", "bootstrap", "garch"):
        t0 = time.perf_counter()
        out = MC.simulate(s, 1008, 10000, method, "historical", seed=0)
        assert time.perf_counter() - t0 < 2.0, method
        assert out["method"] == method
    tracemalloc.start()
    try:
        MC.simulate(s, 1008, 10000, "bootstrap", "historical", seed=0)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 150e6


def test_simulate_edge_cases(closes):
    out = MC.simulate(closes["NVDA"].iloc[:120], 50, 2000, "garch", seed=0)
    dumps(out)
    assert out["method"] == "bootstrap" and "GARCH" in out["note"]
    const = MC.simulate(flat(n=10), 20, 500, "bootstrap", "historical")
    dumps(const)
    assert const["terminal"]["p5"] == pytest.approx(100.0) and const["terminal"]["p95"] == pytest.approx(100.0)
    assert const["ann_vol_used"] == pytest.approx(0.0, abs=1e-9)
    for bad in (flat(n=2), pd.Series(dtype=float)):
        o = MC.simulate(bad)
        dumps(o)
        assert "error" in o and o["percentiles"]["days"] == []
    assert "error" in MC.simulate(closes["NVDA"], method="nope")
    assert "error" in MC.simulate(closes["NVDA"], drift="custom")  # mu missing
    gaps = closes["NVDA"].copy()
    gaps.iloc[::7] = np.nan
    dumps(MC.simulate(gaps, 30, 1000, "gbm"))


# --------------------------------------------------------------------------- vesting
def test_vest_schedule_standard():
    v = MC.vest_schedule("2025-03-15", years=4, cliff_months=12, frequency="quarterly")
    assert len(v) == 13 and v[0] == {"date": "2026-03-15", "fraction": 0.25}
    assert all(x["fraction"] == pytest.approx(0.0625) for x in v[1:])
    assert v[-1]["date"] == "2029-03-15" and sum(x["fraction"] for x in v) == pytest.approx(1.0, abs=1e-15)
    m = MC.vest_schedule("2025-01-31", years=3, cliff_months=12, frequency="monthly")
    assert len(m) == 25 and m[0]["fraction"] == pytest.approx(1 / 3) and m[1]["date"] == "2026-02-28"
    assert sum(x["fraction"] for x in m) == pytest.approx(1.0, abs=1e-12)
    no_cliff = MC.vest_schedule("2025-01-01", 1, 0, "quarterly")
    assert [x["fraction"] for x in no_cliff] == [0.25] * 4
    odd = MC.vest_schedule("2025-01-01", 1, 4, "quarterly")  # cliff off the grid
    assert [x["date"] for x in odd] == ["2025-05-01", "2025-07-01", "2025-10-01", "2026-01-01"]
    assert odd[0]["fraction"] == pytest.approx(4 / 12) and sum(x["fraction"] for x in odd) == pytest.approx(1.0)
    ann = MC.vest_schedule("2025-01-01", 4, 12, "annual")
    assert [x["fraction"] for x in ann] == [0.25] * 4
    assert MC.vest_schedule("not a date") == [] and MC.vest_schedule("2025-01-01", frequency="weekly") == []
    dumps(v)


# --------------------------------------------------------------------------- RSU
def test_rsu_zero_vol_is_deterministic():
    s = flat(80.0, n=600)
    sched = MC.vest_schedule("2025-06-01")  # vests in the future relative to the data
    out = MC.rsu_grant(s, sched, units=400, n_paths=2000)
    dumps(out)
    assert out["grant_price"] == pytest.approx(80.0) and out["current_value"] == pytest.approx(32000.0)
    for k in ("mean", "p5", "p25", "p50", "p75", "p95"):
        assert out["total"][k] == pytest.approx(400 * 80.0)
    assert out["total"]["prob_below_grant_value"] == 0.0 and out["total"]["expected_vs_grant"] == pytest.approx(0.0)
    assert all(v["mean"] == pytest.approx(v["units"] * 80.0) and v["p5"] == pytest.approx(v["p95"])
               for v in out["vests"])
    assert out["cumulative"]["p50"][-1] == pytest.approx(32000.0)
    for drift in ("historical", "riskfree"):
        o = MC.rsu_grant(s, sched, units=400, drift=drift, n_paths=2000)
        # zero vol: historical drift is zero; risk-free drift compounds deterministically
        if drift == "historical":
            assert o["total"]["p5"] == pytest.approx(32000.0)
        else:
            assert o["total"]["p5"] == pytest.approx(o["total"]["p95"]) and o["total"]["mean"] > 32000.0


def test_rsu_units_past_vests_and_distribution(closes):
    c = closes["NVDA"].dropna()
    sched = MC.vest_schedule("2024-06-01")
    out = MC.rsu_grant(c, sched, grant_value=100000.0, grant_price=50.0, n_paths=5000)
    dumps(out)
    assert out["units"] == pytest.approx(2000.0) and out["grant_value"] == pytest.approx(100000.0)
    first = out["vests"][0]
    assert first["past"] is True and first["date"] == "2025-06-01"
    close_then = c[c.index <= "2025-06-01"].iloc[-1]
    assert first["mean"] == pytest.approx(first["units"] * close_then) and first["p5"] == pytest.approx(first["p95"])
    assert first["prob_below_grant"] == float(close_then < 50.0)
    fut = [v for v in out["vests"] if not v["past"]]
    assert fut and all(v["p5"] < v["p50"] < v["p95"] for v in fut)
    assert out["cumulative"]["p50"] == sorted(out["cumulative"]["p50"])
    assert out["total"]["p5"] < out["total"]["p50"] < out["total"]["p95"]
    default_gp = MC.rsu_grant(c, sched, grant_value=100000.0, n_paths=1000)
    assert default_gp["grant_price"] == pytest.approx(c.iloc[-30:].mean())
    err = MC.rsu_grant(c, sched)
    assert "error" in err
    dumps(err)
    dumps(MC.rsu_grant(c, []))


# --------------------------------------------------------------------------- options
def test_black_scholes_known_value():
    assert MC._bs_call(100, 100, 1.0, 0.05, 0.0, 0.2) == pytest.approx(10.4506, abs=1e-4)
    assert MC._bs_call(100, 90, 0.0, 0.05, 0.0, 0.2) == pytest.approx(10.0)
    assert MC._bs_call(100, 90, 1.0, 0.0, 0.0, 0.0) == pytest.approx(10.0)
    s = flat(100.0, n=300)
    out = MC.option_grant(s, units=1000, strike=100.0, schedule=MC.vest_schedule("2024-01-01"), expiry_years=1,
                          rf=0.05, vol=0.2)
    dumps(out)
    assert out["bs_value_per_option"] == pytest.approx(10.4506, abs=1e-4)
    assert out["bs_value_total"] == pytest.approx(10450.6, abs=0.1)
    assert out["breakeven"] == pytest.approx(100 + out["bs_value_per_option"])
    assert out["intrinsic_now"] == 0.0


def test_option_grant_deterministic_and_real(closes):
    s = flat(100.0, n=600)
    sched = MC.vest_schedule("2025-06-01")
    itm = MC.option_grant(s, 100, 90.0, sched)
    assert itm["vol"] == pytest.approx(0.0) and itm["intrinsic_now"] == pytest.approx(10.0)
    assert itm["total"]["mean"] == pytest.approx(1000.0) and itm["total"]["prob_all_underwater"] == 0.0
    assert all(v["prob_underwater"] == 0.0 for v in itm["vests"])
    otm = MC.option_grant(s, 100, 120.0, sched)
    assert otm["total"]["p95"] == 0.0 and otm["total"]["prob_all_underwater"] == 1.0
    real = MC.option_grant(closes["NVDA"], 1000, 180.0, MC.vest_schedule("2024-06-01"), n_paths=5000)
    dumps(real)
    assert 0.2 < real["vol"] < 1.5 and real["bs_value_per_option"] > 0
    assert all(0 <= v["prob_underwater"] <= 1 for v in real["vests"])
    assert real["vests"][0]["past"] and real["vests"][-1]["past"] is False
    bad = MC.option_grant(closes["NVDA"], 1000, -5.0, MC.vest_schedule("2024-06-01"))
    assert "error" in bad
    dumps(bad)
