"""Portfolio construction and risk: known answers + robustness on real closes."""
import json

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import portfolio as pf


def _iid_returns(vols, n=4000, seed=1, corr=None):
    rng = np.random.default_rng(seed)
    k = len(vols)
    c = np.eye(k) if corr is None else np.asarray(corr)
    cov = np.outer(vols, vols) * c / 252
    x = rng.multivariate_normal(np.zeros(k), cov, size=n)
    idx = pd.bdate_range("2015-01-02", periods=n)
    return pd.DataFrame(x, index=idx, columns=[f"A{i}" for i in range(k)])


def _diag_cov(vols, names):
    return pd.DataFrame(np.diag(np.square(vols)), index=names, columns=names)


def test_shrink_cov_sample_matches_pandas_and_lw_shrinks_offdiagonals():
    r = _iid_returns([0.2, 0.3, 0.4], corr=[[1, .6, .3], [.6, 1, .5], [.3, .5, 1]])
    s = pf.shrink_cov(r, "sample")
    np.testing.assert_allclose(s.values, r.cov().values * 252, rtol=1e-10)
    lw = pf.shrink_cov(r, "ledoit_wolf")
    assert np.allclose(lw.values, lw.values.T)
    assert np.all(np.linalg.eigvalsh(lw.values) > 0)
    off = ~np.eye(3, dtype=bool)
    assert np.all(np.abs(lw.values[off]) <= np.abs(s.values[off]) + 1e-12)  # shrunk towards scaled identity
    n = len(r)  # Ledoit-Wolf (as in scikit-learn) shrinks the MLE covariance: S * (n - 1) / n
    assert np.trace(lw.values) == pytest.approx(np.trace(s.values) * (n - 1) / n, rel=1e-6)


def test_min_var_is_inverse_variance_for_diagonal_covariance():
    vols = np.array([0.1, 0.2, 0.4])
    r = _iid_returns(vols)
    cov = _diag_cov(vols, r.columns)
    out = pf.optimize(r, "min_var", max_weight=1.0, cov=cov)
    w = np.array([out["weights"][c] for c in r.columns])
    expected = (1 / vols**2) / (1 / vols**2).sum()
    np.testing.assert_allclose(w, expected, atol=1e-4)
    assert sum(out["weights"].values()) == pytest.approx(1.0, abs=1e-8)


def test_erc_equalises_risk_contributions_and_hrp_is_valid():
    r = _iid_returns([0.15, 0.25, 0.35, 0.5], corr=np.full((4, 4), 0.3) + np.eye(4) * 0.7)
    erc = pf.optimize(r, "erc", max_weight=1.0)
    rc = np.array(list(erc["risk_contrib"].values()))
    np.testing.assert_allclose(rc, np.full(4, 0.25), atol=2e-3)
    hrp = pf.optimize(r, "hrp", max_weight=1.0)
    w = np.array(list(hrp["weights"].values()))
    assert np.all(w > 0) and w.sum() == pytest.approx(1.0, abs=1e-8)
    assert hrp["weights"]["A0"] > hrp["weights"]["A3"]  # the low-vol asset gets more


def test_max_sharpe_matches_tangency_when_interior():
    names = ["X", "Y"]
    mu = pd.Series([0.10, 0.14], index=names)
    cov = pd.DataFrame([[0.04, 0.006], [0.006, 0.09]], index=names, columns=names)
    r = _iid_returns([0.2, 0.3])
    r.columns = names
    out = pf.optimize(r, "max_sharpe", max_weight=1.0, rf=0.02, mu=mu, cov=cov)
    raw = np.linalg.solve(cov.values, mu.values - 0.02)
    tang = raw / raw.sum()
    np.testing.assert_allclose([out["weights"]["X"], out["weights"]["Y"]], tang, atol=2e-3)


def test_bounds_respected_and_frontier_is_sane():
    r = _iid_returns([0.15, 0.2, 0.25, 0.3, 0.35], seed=3)
    for m in ("equal", "inverse_vol", "min_var", "max_sharpe", "erc", "max_div"):
        w = pf.optimize(r, m, max_weight=0.3)["weights"]
        assert max(w.values()) <= 0.3 + 1e-6, m
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-6), m
    fr = pf.efficient_frontier(r, n_points=15, max_weight=0.4)
    vols = [p["vol"] for p in fr["points"]]
    assert min(vols) >= fr["min_var"]["vol"] - 1e-6
    assert len(fr["assets"]) == 5


def test_portfolio_risk_euler_decomposition_adds_up():
    r = _iid_returns([0.2, 0.3, 0.25], corr=[[1, .5, .2], [.5, 1, .4], [.2, .4, 1]])
    w = {"A0": 0.5, "A1": 0.3, "A2": 0.2}
    out = pf.portfolio_risk(w, r, r["A0"], rf=0.0, value=1_000_000)
    rc = sum(h["risk_contrib"] for h in out["holdings"])
    assert rc == pytest.approx(1.0, abs=1e-6)
    comp = sum(h["component_var"] for h in out["holdings"])
    assert comp == pytest.approx(out["var95_param"], rel=1e-3)
    assert out["var95_value"] == pytest.approx(out["var95"] * 1_000_000, rel=1e-9)
    assert 0 < out["vol"] < 0.3


def test_backtest_single_asset_without_costs_tracks_the_price():
    idx = pd.bdate_range("2020-01-01", periods=300)
    p = pd.DataFrame({"A": 100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 0.01, 300)))}, index=idx)
    out = pf.backtest(p, {"A": 1.0}, rebalance="M", cost_bps=0)
    eq = pd.Series(out["equity"]["v"], index=pd.to_datetime(out["equity"]["t"]))
    rel = (p["A"] / p["A"].iloc[0]).reindex(eq.index)
    np.testing.assert_allclose(eq.values / eq.values[0], rel.values / rel.values[0], rtol=1e-8)


def test_black_litterman_moves_towards_views():
    names = ["X", "Y", "Z"]
    cov = pd.DataFrame(np.diag([0.04, 0.06, 0.09]), index=names, columns=names)
    mw = {"X": 0.5, "Y": 0.3, "Z": 0.2}
    base = pf.black_litterman(cov, mw, {}, 0.5)
    view = pf.black_litterman(cov, mw, {"Z": 0.30}, 0.9)
    assert view["posterior"]["Z"] > base["posterior"]["Z"]
    assert view["weights"]["Z"] >= base["weights"]["Z"] - 1e-9
    assert abs(sum(view["weights"].values()) - 1) < 1e-6


def test_real_semis_all_methods_json_safe(closes):
    px = closes[["NVDA", "AMD", "TSM", "AVGO", "INTC", "MU", "QCOM", "TXN"]].dropna()
    r = px.pct_change().dropna().tail(756)
    for m in ("equal", "inverse_vol", "min_var", "max_sharpe", "erc", "hrp", "max_div"):
        json.dumps(pf.optimize(r, m), allow_nan=False)
    json.dumps(pf.efficient_frontier(r, 20), allow_nan=False)
    w = {t: 1 / 8 for t in px.columns}
    json.dumps(pf.portfolio_risk(w, r, closes["SPY"].pct_change().dropna()), allow_nan=False)
    json.dumps(pf.backtest(px.tail(1000), w, "Q", 10, closes["SPY"]), allow_nan=False)
