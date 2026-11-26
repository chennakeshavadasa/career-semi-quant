"""Tests for semiquant.analytics.volatility: range estimators on synthetic OHLC with known vol,
EWMA, vol cone, and the GARCH wrapper cross-checked against the arch package."""
from __future__ import annotations

import json
import math
import warnings

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import volatility as V


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def synth_ohlc(n_days=1200, sigma=0.30, overnight_frac=0.2, steps=390, seed=0) -> pd.DataFrame:
    """Daily OHLC from a discretely sampled Brownian log price: overnight jump with variance
    overnight_frac x sigma^2/252, intraday Brownian path with the rest (total daily vol sigma)."""
    rng = np.random.default_rng(seed)
    var_day = sigma ** 2 / 252
    v_on, v_id = overnight_frac * var_day, (1 - overnight_frac) * var_day
    on = rng.normal(0.0, math.sqrt(v_on), n_days) if v_on > 0 else np.zeros(n_days)
    path = np.cumsum(rng.normal(0.0, math.sqrt(v_id / steps), (n_days, steps)), axis=1)
    log_close = np.cumsum(on + path[:, -1])
    log_open = log_close - path[:, -1]
    hi = log_open + np.maximum(path.max(axis=1), 0.0)
    lo = log_open + np.minimum(path.min(axis=1), 0.0)
    idx = pd.bdate_range("2018-01-01", periods=n_days)
    return pd.DataFrame({"open": 100 * np.exp(log_open), "high": 100 * np.exp(hi), "low": 100 * np.exp(lo),
                         "close": 100 * np.exp(log_close), "volume": 1e6}, index=idx)


def test_close_to_close_gbm(synthetic):
    s = synthetic(n=2520, sigma=0.30, seed=2)
    rv = V.realized_vol(s, 21, "close_to_close")
    assert isinstance(rv, pd.Series) and rv.index.equals(s.index)
    assert rv.dropna().median() == pytest.approx(0.30, rel=0.06)
    full = V.realized_vol(s, len(s) - 1, "close_to_close").iloc[-1]
    assert full == pytest.approx(np.log(s).diff().std() * math.sqrt(252))
    # non close-to-close methods on a close Series fall back to close-to-close
    np.testing.assert_allclose(V.realized_vol(s, 21, "yang_zhang").dropna(), rv.dropna())


def test_yang_zhang_recovers_sigma():
    d = synth_ohlc(sigma=0.30, overnight_frac=0.25, seed=1)
    yz = V.realized_vol(d, 63, "yang_zhang").dropna()
    assert yz.median() == pytest.approx(0.30, rel=0.08)
    whole = V.realized_vol(d, len(d) - 1, "yang_zhang").iloc[-1]
    assert whole == pytest.approx(0.30, rel=0.05)
    # range estimators ignore the overnight gap: they see only the intraday 75% of the variance
    for m in ("parkinson", "garman_klass", "rogers_satchell"):
        est = V.realized_vol(d, len(d) - 1, m).iloc[-1]
        assert est == pytest.approx(0.30 * math.sqrt(0.75), rel=0.08), m
        assert est < whole


def test_range_estimators_without_gaps():
    d = synth_ohlc(sigma=0.25, overnight_frac=0.0, seed=4)
    for m in V.METHODS:
        est = V.realized_vol(d, len(d) - 1, m).iloc[-1]
        assert est == pytest.approx(0.25, rel=0.07), m
    # Yang-Zhang weight k on the open-to-close variance
    n = 21
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    o, h, l, c = (np.log(d[x]) for x in ("open", "high", "low", "close"))
    on = (o - c.shift()).iloc[1:22]
    oc = (c - o).iloc[1:22]
    rs = ((h - c) * (h - o) + (l - c) * (l - o)).iloc[1:22]
    manual = math.sqrt((on.var() + k * oc.var() + (1 - k) * rs.mean()) * 252)
    assert V.realized_vol(d, 21, "yang_zhang").iloc[21] == pytest.approx(manual)


def test_realized_vol_summary_and_cone(nvda_ohlcv):
    out = V.realized_vol_summary(nvda_ohlcv)
    dumps(out)
    assert out["methods"] == V.METHODS and out["windows"] == [10, 21, 63, 126, 252]
    for m in V.METHODS:
        assert all(0.05 < v < 3 for v in out["table"][m].values())
        assert len(out["series"][m]["t"]) == len(out["series"][m]["v"]) > 1000
    only_close = V.realized_vol_summary(nvda_ohlcv["close"])
    assert only_close["ohlc"] is False and only_close["table"]["parkinson"]["21"] is None
    assert only_close["table"]["close_to_close"]["21"] == pytest.approx(out["table"]["close_to_close"]["21"])
    cone = V.vol_cone(nvda_ohlcv)
    dumps(cone)
    for i in range(len(cone["windows"])):
        seq = [cone[k][i] for k in ("min", "p10", "p25", "median", "p75", "p90", "max")]
        assert seq == sorted(seq)
        assert seq[0] <= cone["current"][i] <= seq[-1] and 0 <= cone["percentile_now"][i] <= 100
    yz_cone = V.vol_cone(nvda_ohlcv, windows=(21,), method="yang_zhang")
    assert yz_cone["current"][0] == pytest.approx(V.realized_vol(nvda_ohlcv, 21, "yang_zhang").iloc[-1])


def test_ewma(synthetic):
    s = synthetic(n=2000, sigma=0.20, seed=6)
    e = V.ewma_vol(s)
    assert e.dropna().mean() == pytest.approx(0.20, rel=0.06)
    r = np.log(s).diff().dropna()
    w = 0.94 ** np.arange(len(r))[::-1]
    assert e.iloc[-1] == pytest.approx(math.sqrt((w * r.to_numpy() ** 2).sum() / w.sum() * 252))


def test_garch_matches_arch(closes):
    from arch import arch_model

    c = closes["NVDA"].dropna()
    r = np.log(c).diff().dropna() * 100
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = arch_model(r, mean="Constant", vol="GARCH", p=1, o=1, q=1, dist="t", rescale=False).fit(disp="off")
    out = V.garch(c, "gjr", "t", horizon=21, years=10)
    dumps(out)
    np.testing.assert_allclose([out["params"][k] for k in res.params.index], res.params.to_numpy(), rtol=1e-6)
    fv = res.forecast(horizon=21, reindex=False).variance.iloc[-1].to_numpy()
    np.testing.assert_allclose(out["forecast"]["vol"], np.sqrt(fv) / 100 * math.sqrt(252), rtol=1e-6)
    assert out["forecast"]["avg_vol"] == pytest.approx(math.sqrt(fv.mean()) / 100 * math.sqrt(252), rel=1e-6)
    assert out["current_vol"] == pytest.approx(out["forecast"]["vol"][0])
    p = res.params
    pers = p["alpha[1]"] + p["beta[1]"] + p["gamma[1]"] / 2
    assert out["persistence"] == pytest.approx(pers, rel=1e-6)
    assert out["half_life_days"] == pytest.approx(math.log(0.5) / math.log(pers), rel=1e-6)
    assert out["long_run_vol"] == pytest.approx(math.sqrt(p["omega"] / (1 - pers)) / 100 * math.sqrt(252), rel=1e-6)
    assert out["aic"] == pytest.approx(res.aic) and out["loglik"] == pytest.approx(res.loglikelihood)
    assert out["cond_vol"]["v"][-1] == pytest.approx(res.conditional_volatility.iloc[-1] / 100 * math.sqrt(252))
    assert out["n"] == len(r) and 0 <= out["ljung_box_sq_p"] <= 1 and out["converged"]


def test_garch_recovers_simulated_params():
    rng = np.random.default_rng(12)
    mu, om, a, g, b = 0.05, 0.05, 0.03, 0.10, 0.88
    n, burn = 4000, 500
    h = om / (1 - a - g / 2 - b)
    x = np.empty(n + burn)
    for t in range(n + burn):
        eps = math.sqrt(h) * rng.standard_normal()
        x[t] = mu + eps
        h = om + (a + g * (eps < 0)) * eps * eps + b * h
    data = x[burn:]
    idx = pd.bdate_range("2008-01-01", periods=n + 1)
    close = pd.Series(100 * np.exp(np.r_[0.0, np.cumsum(data / 100)]), index=idx)
    out = V.garch(close, "gjr", "normal", horizon=10, years=30)
    assert out["persistence"] == pytest.approx(a + b + g / 2, abs=0.03)
    assert out["params"]["gamma[1]"] == pytest.approx(g, abs=0.05)
    assert out["params"]["beta[1]"] == pytest.approx(b, abs=0.05)
    assert out["long_run_vol"] == pytest.approx(math.sqrt(om / (1 - a - g / 2 - b) * 252) / 100, rel=0.2)


@pytest.mark.parametrize("model", ["garch", "gjr", "egarch"])
def test_garch_models_real(closes, model):
    out = V.garch(closes["AMD"], model, "t", horizon=21)
    dumps(out)
    assert "error" not in out
    assert 0.5 < out["persistence"] < 1 and 0.1 < out["long_run_vol"] < 2
    assert len(out["forecast"]["vol"]) == 21 and out["forecast"]["days"] == list(range(1, 22))
    if model == "egarch":  # simulated forecasts are reproducible
        assert V.garch(closes["AMD"], model, "t", horizon=21)["forecast"] == out["forecast"]


def test_garch_failures():
    short = pd.Series(np.linspace(10, 11, 50), index=pd.bdate_range("2024-01-01", periods=50))
    out = V.garch(short)
    dumps(out)
    assert "error" in out and out["params"] is None and out["forecast"] is None
    flat = V.garch(pd.Series(10.0, index=pd.bdate_range("2020-01-01", periods=600)))
    assert "error" in flat
    assert "error" in V.garch(short, model="bogus")


def test_vol_summary(nvda_ohlcv):
    out = V.vol_summary(nvda_ohlcv, atm_iv=0.55)
    dumps(out)
    assert out["vrp"] == pytest.approx(0.55 - out["rv_21d_yz"])
    assert out["iv_rv_ratio"] == pytest.approx(0.55 / out["rv_21d_yz"])
    assert 0 <= out["rv_percentile_1y"] <= 100 and 0 <= out["rv_percentile_5y"] <= 100
    assert 0.05 < out["garch_avg_21d"] < 3 and 0.05 < out["ewma"] < 3
    none_iv = V.vol_summary(nvda_ohlcv)
    assert none_iv["atm_iv"] is None and none_iv["vrp"] is None


@pytest.mark.parametrize("data", [
    pd.Series(np.linspace(10, 11, 10), index=pd.bdate_range("2024-01-01", periods=10)),
    pd.Series(5.0, index=pd.bdate_range("2024-01-01", periods=400)),
    pd.DataFrame(),
])
def test_edge_cases(data):
    dumps(V.vol_summary(data, atm_iv=0.3))
    dumps(V.realized_vol_summary(data))
    dumps(V.vol_cone(data))
    assert isinstance(V.realized_vol(data, 21), pd.Series)
    assert isinstance(V.ewma_vol(data), pd.Series)


def test_intraday_runs(nvda_intraday):
    dumps(V.realized_vol_summary(nvda_intraday, windows=(30, 60)))
    rv = V.realized_vol(nvda_intraday, 60, "yang_zhang").dropna()
    assert len(rv) > 1000 and (rv > 0).all()
