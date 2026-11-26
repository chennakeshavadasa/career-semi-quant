"""Cointegration / pairs: planted relationships are found, independent walks are not."""
import json

import numpy as np
import pandas as pd

from semiquant.analytics import pairs


def _walk(n, seed, sigma=0.01):
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(0, sigma, n))


def test_hurst_separates_random_walk_from_mean_reversion():
    rw = pd.Series(_walk(4000, 1))
    rng = np.random.default_rng(2)
    ar = np.zeros(4000)
    for t in range(1, 4000):
        ar[t] = 0.3 * ar[t - 1] + rng.normal(0, 0.01)
    assert 0.4 < pairs.hurst(rw) < 0.6
    assert pairs.hurst(pd.Series(ar)) < 0.3


def test_engle_granger_finds_planted_pair_and_half_life():
    n = 1500
    idx = pd.bdate_range("2019-01-01", periods=n)
    x = _walk(n, 3) + 4.0
    rng = np.random.default_rng(4)
    phi, e = 0.9, np.zeros(n)
    for t in range(1, n):
        e[t] = phi * e[t - 1] + rng.normal(0, 0.01)
    y = 0.5 + 1.5 * x + e
    out = pairs.engle_granger(pd.Series(np.exp(y), idx), pd.Series(np.exp(x), idx))
    assert out["pvalue"] < 0.01
    assert abs(out["hedge_ratio"] - 1.5) < 0.05
    expected_hl = -np.log(2) / np.log(phi)
    assert abs(out["half_life_days"] - expected_hl) / expected_hl < 0.35
    assert out["signal"] in ("long spread", "short spread", "exit", "hold")
    json.dumps(out, allow_nan=False)


def test_independent_walks_are_rarely_cointegrated():
    idx = pd.bdate_range("2019-01-01", periods=1000)
    rejections = 0
    for s in range(10):
        a = pd.Series(np.exp(_walk(1000, 100 + s) + 3), idx)
        b = pd.Series(np.exp(_walk(1000, 200 + s) + 3), idx)
        rejections += pairs.engle_granger(a, b)["pvalue"] < 0.05
    assert rejections <= 2  # ~5 % false-positive rate expected


def test_scan_pairs_on_real_semis(closes):
    px = closes[["NVDA", "AMD", "TSM", "AVGO", "INTC", "MU", "QCOM", "TXN", "ADI", "AMAT", "LRCX", "KLAC"]]
    out = pairs.scan_pairs(px, min_corr=0.5, lookback=504)
    json.dumps(out, allow_nan=False)
    res = out["results"]
    assert out["tested"] >= len(res)
    ps = [r["pvalue"] for r in res]
    assert ps == sorted(ps)
    for r in res:
        assert r["pvalue"] <= r["qvalue"] + 1e-12  # BH q-values are never below the p-value
        assert 2 <= r["half_life_days"] <= 60
