"""Universe metrics, breadth and the composite quant score."""
import json

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import scoring
from semiquant.analytics._util import jsonable


def _universe(n=400, k=6, seed=0, betas=None):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n)
    m = rng.normal(0.0004, 0.01, n)
    betas = betas or [0.5, 0.8, 1.0, 1.2, 1.5, 2.0][:k]
    cols = {}
    for i, b in enumerate(betas):
        r = b * m + rng.normal(0, 0.008, n)
        cols[f"S{i}"] = 100 * np.exp(np.cumsum(r))
    bench = pd.Series(100 * np.exp(np.cumsum(m)), idx, name="SPY")
    return pd.DataFrame(cols, index=idx), bench, betas


def test_universe_metrics_known_values():
    px, bench, betas = _universe()
    m = scoring.universe_metrics(px, bench, bench)
    for c in px.columns:
        p = px[c]
        assert m.loc[c, "ret_1m"] == pytest.approx(p.iloc[-1] / p.iloc[-22] - 1, rel=1e-9)
        assert m.loc[c, "mom_12_1"] == pytest.approx(p.iloc[-22] / p.iloc[-253] - 1, rel=1e-9)
        assert 0 <= m.loc[c, "rsi14"] <= 100
        assert 0 <= m.loc[c, "pos_52w"] <= 1
        assert m.loc[c, "pct_from_52w_high"] <= 0
    est = m.loc[[f"S{i}" for i in range(6)], "beta_1y"].to_numpy()
    np.testing.assert_allclose(est, betas, atol=0.15)


def test_breadth_all_rising():
    idx = pd.bdate_range("2024-01-02", periods=300)
    px = pd.DataFrame({f"S{i}": np.linspace(100, 200 + i, 300) for i in range(5)}, index=idx)
    b = scoring.breadth(px)
    assert b["pct_above_sma50"] == pytest.approx(1.0)
    assert b["pct_above_sma200"] == pytest.approx(1.0)
    assert b["new_highs_52w"] == 5 and b["new_lows_52w"] == 0
    json.dumps(jsonable(b), allow_nan=False)


def test_quant_score_ranks_the_better_company_first():
    px, bench, _ = _universe()
    m = scoring.universe_metrics(px, bench)
    f = pd.DataFrame({"earnings_yield": [0.01, 0.02, 0.03, 0.04, 0.05, 0.08], "gross_margin": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
                      "rev_growth": [0.0, 0.05, 0.1, 0.15, 0.2, 0.3], "eps_rev_30d": [-0.02, -0.01, 0, 0.01, 0.02, 0.05],
                      "target_upside": [0.0, 0.05, 0.1, 0.15, 0.2, 0.3], "rec_mean": [3.5, 3, 2.5, 2.2, 2, 1.5]},
                     index=[f"S{i}" for i in range(6)])
    s = scoring.quant_score(m, f)
    assert s["score"].between(0, 100).all()
    assert s.loc["S5", "value"] > s.loc["S0", "value"]
    assert s.loc["S5", "quality"] > s.loc["S0", "quality"]
    assert s.loc["S5", "analyst"] > s.loc["S0", "analyst"]
    assert sum(scoring.default_weights().values()) == pytest.approx(1.0)
    ex = scoring.score_explain(s.loc["S5"])
    assert ex["components"] and isinstance(ex["strengths"], list)
    json.dumps(jsonable(ex), allow_nan=False)


def test_missing_fundamentals_score_neutral():
    px, bench, _ = _universe()
    s = scoring.quant_score(scoring.universe_metrics(px, bench))
    for comp in ("value", "quality", "growth", "revisions", "analyst"):
        assert (s[comp] == 50).all(), comp


def test_real_universe_runs(closes):
    semis = closes[["NVDA", "AMD", "TSM", "AVGO", "INTC", "MU", "QCOM", "TXN", "ADI", "AMAT", "LRCX", "KLAC"]]
    m = scoring.universe_metrics(semis, closes["SPY"], closes["SOXX"])
    s = scoring.quant_score(m)
    assert list(s.index)[:1] and s["score"].notna().all()
    json.dumps(jsonable(scoring.breadth(semis)), allow_nan=False)
