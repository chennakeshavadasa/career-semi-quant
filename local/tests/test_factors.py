"""Tests for semiquant.analytics.factors: factor construction, planted-beta recovery with
Newey-West errors, Euler attribution, rolling betas, peers, clustering and PCA structure."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import factors as F
from semiquant.universe import MACRO_FACTORS, STYLE_FACTORS


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def planted(n=1500, seed=0, betas=(1.2, -0.5, 0.0), alpha=0.0002, noise=0.008):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    f = pd.DataFrame(rng.normal(0, 0.01, (n, len(betas))), index=idx, columns=[f"f{i}" for i in range(len(betas))])
    y = alpha + f.to_numpy() @ np.asarray(betas) + rng.normal(0, noise, n)
    return pd.Series(y, index=idx, name="asset"), f


# --------------------------------------------------------------------------- construction
def test_build_factor_returns(closes):
    fr = F.build_factor_returns(closes)
    assert list(fr.columns) == list(STYLE_FACTORS)
    d = fr.index[500]
    spy = closes["SPY"].dropna()
    soxx = closes["SOXX"].dropna()
    exp_semis = soxx.pct_change()[d] - spy.pct_change()[d]
    assert fr.loc[d, "Semis"] == pytest.approx(exp_semis)
    assert fr.loc[d, "Market"] == pytest.approx(spy.pct_change()[d])
    assert np.isfinite(fr.to_numpy()).all() and len(fr) > 1500
    missing = F.build_factor_returns(closes.drop(columns=["MTUM", "IWD"]))
    assert "Momentum" not in missing.columns and "Value" not in missing.columns and "Semis" in missing.columns
    assert F.build_factor_returns(pd.DataFrame()).empty


def test_build_macro_factors(closes):
    mf = F.build_macro_factors(closes)
    assert list(mf.columns) == list(MACRO_FACTORS)
    tnx = closes["^TNX"].dropna()
    d = mf["10Y yield"].dropna().index[300]
    assert mf.loc[d, "10Y yield"] == pytest.approx((tnx.diff() * 100)[d])  # basis points
    vix = closes["^VIX"].dropna()
    dv = mf["VIX"].dropna().index[300]
    assert mf.loc[dv, "VIX"] == pytest.approx(vix.diff()[dv])  # points
    assert np.isfinite(mf.to_numpy()[~np.isnan(mf.to_numpy())]).all()
    oil = closes["CL=F"].dropna()
    if (oil <= 0).any():  # WTI settled below zero in April 2020: returns undefined there
        bad = oil.index[oil <= 0][0]
        nxt = oil.index[oil.index.get_loc(bad) + 1]
        assert pd.isna(mf["Oil"].get(bad)) and pd.isna(mf["Oil"].get(nxt))
    assert mf["Oil"].abs().max() < 1.0


# --------------------------------------------------------------------------- regression
def test_factor_regression_recovers_betas():
    y, f = planted()
    out = F.factor_regression(y, f, nw_lags=5)
    dumps(out)
    b = {x["name"]: x for x in out["factors"]}
    assert b["f0"]["beta"] == pytest.approx(1.2, abs=0.05) and b["f1"]["beta"] == pytest.approx(-0.5, abs=0.05)
    assert abs(b["f2"]["beta"]) < 0.06 and b["f0"]["p"] < 1e-10 and b["f2"]["p"] > 0.01
    assert out["alpha_ann"] == pytest.approx(0.0002 * 252, abs=0.06)
    assert out["n"] == 1500 and out["start"] == "2015-01-01"
    assert sum(x["contribution"] for x in out["factors"]) == pytest.approx(out["systematic_share"])
    assert out["systematic_share"] == pytest.approx(out["r2"])
    assert out["idio_share"] == pytest.approx(1 - out["r2"])
    assert out["idio_vol_ann"] == pytest.approx(0.008 * math.sqrt(252), rel=0.05)
    assert b["f0"]["factor_vol_ann"] == pytest.approx(0.01 * math.sqrt(252), rel=0.05)
    # Newey-West t-statistics match statsmodels directly
    import statsmodels.api as sm

    ref = sm.OLS(y.to_numpy(), sm.add_constant(f.to_numpy())).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    np.testing.assert_allclose([out["alpha_t"]] + [x["t"] for x in out["factors"]], ref.tvalues, rtol=1e-8)


def test_factor_regression_real(closes):
    r = closes["NVDA"].dropna().pct_change().dropna()
    out = F.factor_regression(r, F.build_factor_returns(closes))
    dumps(out)
    assert 0.3 < out["r2"] < 0.95 and len(out["factors"]) == 7
    mkt = next(x for x in out["factors"] if x["name"] == "Market")
    assert 0.5 < mkt["beta"] < 3
    macro = F.factor_regression(r, F.build_macro_factors(closes))
    dumps(macro)
    assert macro["n"] > 1500


def test_factor_regression_edge():
    y, f = planted(n=12)
    dumps(F.factor_regression(y, f))
    assert F.factor_regression(y, f)["error"]
    flat = pd.Series(0.0, index=f.index)
    dumps(F.factor_regression(flat, f))
    dumps(F.factor_regression(pd.Series(dtype=float), pd.DataFrame()))
    y2, f2 = planted(n=300)
    f2.iloc[10:20, 0] = np.nan
    out = F.factor_regression(y2, f2)
    assert out["n"] == 290


# --------------------------------------------------------------------------- rolling
def test_rolling_betas():
    y, f = planted(n=800, noise=0.002)
    out = F.rolling_betas(y, f, window=126, step=5)
    dumps(out)
    assert out["t"][-1] == y.index[-1].strftime("%Y-%m-%d")
    assert len(out["t"]) == len(out["f0"]) == len(range(799, 124, -5))
    # per-window beta standard error ~ 0.002 / (0.01 sqrt(126)) = 0.018: allow ~4 SE
    np.testing.assert_allclose(out["f0"], 1.2, atol=0.075)
    np.testing.assert_allclose(out["f1"], -0.5, atol=0.075)
    # each window equals a direct OLS on that window
    import statsmodels.api as sm

    last = sm.OLS(y.iloc[-126:].to_numpy(), sm.add_constant(f.iloc[-126:].to_numpy())).fit()
    np.testing.assert_allclose([out["alpha_ann"][-1] / 252, out["f0"][-1], out["f1"][-1], out["f2"][-1]], last.params,
                               rtol=1e-7, atol=1e-10)
    assert out["r2"][-1] == pytest.approx(last.rsquared)


def test_rolling_betas_real_and_edge(closes):
    r = closes["AMD"].dropna().pct_change().dropna()
    out = F.rolling_betas(r, F.build_factor_returns(closes))
    dumps(out)
    assert len(out["t"]) > 250 and "Market" in out
    short = F.rolling_betas(r.iloc[:50], F.build_factor_returns(closes))
    assert short["t"] == []
    dumps(short)


# --------------------------------------------------------------------------- cross-section
def test_peer_correlation(closes):
    rets = closes.drop(columns=["^TNX", "^VIX", "DX-Y.NYB", "CL=F"]).pct_change(fill_method=None)
    out = F.peer_correlation(rets, "NVDA", top=5, window=252)
    dumps(out)
    corrs = [p["corr"] for p in out["peers"]]
    assert len(corrs) == 5 and corrs == sorted(corrs, reverse=True) and all(-1 <= c <= 1 for c in corrs)
    p0 = out["peers"][0]
    pair = rets[["NVDA", p0["ticker"]]].dropna(how="all").iloc[-252:].dropna()
    assert p0["corr"] == pytest.approx(pair.corr().iloc[0, 1])
    assert p0["beta"] == pytest.approx(pair.cov().iloc[0, 1] / pair[p0["ticker"]].var())
    assert "NVDA" not in [p["ticker"] for p in out["peers"]]
    assert "error" in F.peer_correlation(rets, "ZZZZ")


def test_correlation_matrix_clusters_blocks():
    rng = np.random.default_rng(3)
    n = 1000
    f1, f2 = rng.normal(0, 1, n), rng.normal(0, 1, n)
    cols = {}
    for i in range(3):
        cols[f"A{i}"] = f1 + 0.5 * rng.normal(0, 1, n)
        cols[f"B{i}"] = f2 + 0.5 * rng.normal(0, 1, n)
    R = pd.DataFrame(cols, index=pd.bdate_range("2020-01-01", periods=n))[["A0", "B0", "A1", "B1", "A2", "B2"]]
    out = F.correlation_matrix(R)
    dumps(out)
    order = "".join(t[0] for t in out["tickers"])
    assert order in ("AAABBB", "BBBAAA")
    M = np.array(out["matrix"])
    np.testing.assert_allclose(M, M.T)
    np.testing.assert_allclose(np.diag(M), 1.0)
    assert out["avg_corr"] == pytest.approx(M[~np.eye(6, dtype=bool)].mean())
    plain = F.correlation_matrix(R, cluster=False)
    assert plain["tickers"] == list(R.columns)


def test_correlation_matrix_real_and_edge(closes):
    rets = closes.pct_change(fill_method=None)
    out = F.correlation_matrix(rets)
    dumps(out)
    assert sorted(out["tickers"]) == sorted(closes.columns) and 0 < out["avg_corr"] < 1
    with_const = rets.iloc[:, :4].copy()
    with_const["FLAT"] = 0.0
    dumps(F.correlation_matrix(with_const))
    dumps(F.correlation_matrix(pd.DataFrame()))


def test_pca_structure_planted_factor():
    rng = np.random.default_rng(8)
    T, N = 1000, 20
    m = rng.normal(0, 1, T)
    R = pd.DataFrame(m[:, None] * 0.8 + rng.normal(0, 0.6, (T, N)), index=pd.bdate_range("2020-01-01", periods=T),
                     columns=[f"S{i}" for i in range(N)])
    out = F.pca_structure(R)
    dumps(out)
    rho = 0.64 / (0.64 + 0.36)
    assert out["explained"][0] == pytest.approx((1 + (N - 1) * rho) / N, abs=0.03)
    assert out["mp_edge"] == pytest.approx((1 + math.sqrt(N / T)) ** 2)
    assert out["n_signal"] == 1 and out["n_obs"] == T and out["n_assets"] == N
    assert out["absorption_ratio"] == pytest.approx(sum(out["explained"][:4]))
    assert all(v > 0 for v in out["pc1_loadings"].values())
    assert sum(out["explained"][:10]) <= 1 + 1e-12 and len(out["explained"]) == 10


def test_pca_structure_real_and_edge(closes):
    out = F.pca_structure(closes.drop(columns=["^TNX", "^VIX", "DX-Y.NYB", "CL=F"]).pct_change(fill_method=None))
    dumps(out)
    assert out["explained"][0] > 0.4 and out["n_signal"] >= 1 and 0 < out["absorption_ratio"] <= 1
    dumps(F.pca_structure(pd.DataFrame({"a": [0.01, 0.02]})))
    dumps(F.pca_structure(pd.DataFrame()))
