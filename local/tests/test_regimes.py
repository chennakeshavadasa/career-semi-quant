"""Tests for semiquant.analytics.regimes: blocked forward-backward vs the textbook recursion,
planted-regime recovery, real-data robustness and speed."""
from __future__ import annotations

import json
import math
import time

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import regimes as H


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def markov_returns(A, mus, sigs, T=2000, seed=1):
    rng = np.random.default_rng(seed)
    A = np.asarray(A)
    st = np.zeros(T, dtype=int)
    for t in range(1, T):
        st[t] = rng.choice(len(A), p=A[st[t - 1]])
    x = np.asarray(mus)[st] + np.asarray(sigs)[st] * rng.standard_normal(T)
    return pd.Series(x, index=pd.bdate_range("2012-01-02", periods=T)), st


def sequential_fb(M, a0):
    """Rabiner's scaled forward-backward, one step at a time (reference)."""
    I, T1, K, _ = M.shape
    alpha = np.empty((I, T1 + 1, K))
    c = np.empty((I, T1 + 1))
    c[:, 0] = a0.sum(-1)
    alpha[:, 0] = a0 / c[:, 0, None]
    for t in range(T1):
        a = np.einsum("ik,ikj->ij", alpha[:, t], M[:, t])
        c[:, t + 1] = a.sum(-1)
        alpha[:, t + 1] = a / c[:, t + 1, None]
    beta = np.empty_like(alpha)
    beta[:, -1] = 1.0
    for t in range(T1 - 1, -1, -1):
        beta[:, t] = np.einsum("ikj,ij->ik", M[:, t], beta[:, t + 1]) / c[:, t + 1, None]
    g = alpha * beta
    g /= g.sum(-1, keepdims=True)
    X = alpha[:, :-1, :, None] * M * beta[:, 1:, None, :]
    X /= X.sum(axis=(-2, -1), keepdims=True)
    return g, X.sum(axis=1), np.log(c).sum(-1)


@pytest.mark.parametrize("T,K", [(1, 2), (2, 2), (7, 3), (50, 2), (333, 3), (1750, 2)])
def test_blocked_forward_backward_matches_reference(T, K):
    rng = np.random.default_rng(T + K)
    I = 3
    x = rng.standard_normal(T + 1)
    mu = rng.normal(0, 0.3, (I, K))
    var = np.exp(rng.uniform(-1, 1, (I, K)))
    A = rng.dirichlet(np.ones(K) * 3, (I, K)) * 0.3 + np.eye(K) * 0.7
    pi = rng.dirichlet(np.ones(K), I)
    lb = H._log_emissions(x, mu, var)
    b = np.exp(lb - lb.max(-1, keepdims=True))
    M = A[:, None] * b[:, 1:, None, :]
    g1, x1, l1 = H._forward_backward(M, pi * b[:, 0])
    g2, x2, l2 = sequential_fb(M, pi * b[:, 0])
    np.testing.assert_allclose(g1, g2, atol=1e-12)
    np.testing.assert_allclose(x1, x2, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(l1, l2, rtol=1e-12, atol=1e-9)


def test_recovers_planted_two_regimes():
    A = [[0.98, 0.02], [0.04, 0.96]]
    r, st = markov_returns(A, [0.0006, -0.001], np.array([0.10, 0.45]) / math.sqrt(252), T=2000, seed=1)
    t0 = time.perf_counter()
    out = H.hmm_fit(r, n_states=2)
    assert time.perf_counter() - t0 < 2.0
    dumps(out)
    acc = (np.array(out["viterbi"]["v"]) == st).mean()
    assert acc > 0.85
    s0, s1 = out["states"]
    assert (s0["label"], s1["label"]) == ("Calm", "Turbulent")
    assert s0["vol_ann"] == pytest.approx(0.10, rel=0.1) and s1["vol_ann"] == pytest.approx(0.45, rel=0.1)
    P = np.array(out["transition"])
    np.testing.assert_allclose(P, A, atol=0.02)
    np.testing.assert_allclose(P.sum(1), 1.0)
    assert s0["expected_duration_days"] == pytest.approx(1 / (1 - P[0, 0]))
    shares = [s["share"] for s in out["states"]]
    assert sum(shares) == pytest.approx(1.0) and shares[0] == pytest.approx((st == 0).mean(), abs=0.05)
    assert out["bic"] == pytest.approx(-2 * out["loglik"] + (4 + 4 - 1) * math.log(len(r)))
    probs = np.array(out["probs"]["p"])
    np.testing.assert_allclose(probs.sum(1), 1.0, atol=5e-4)
    assert out["current_state"] == int(np.argmax(out["current_probs"]))
    assert out["current_label"] == out["states"][out["current_state"]]["label"]


def test_recovers_planted_three_regimes():
    A = [[0.97, 0.02, 0.01], [0.02, 0.96, 0.02], [0.02, 0.05, 0.93]]
    r, st = markov_returns(A, [0.0005, 0.0, -0.002], np.array([0.08, 0.25, 0.70]) / math.sqrt(252), T=3000, seed=4)
    out = H.hmm_fit(r, n_states=3, seed=1)
    dumps(out)
    assert [s["label"] for s in out["states"]] == ["Calm", "Normal", "Turbulent"]
    assert (np.array(out["viterbi"]["v"]) == st).mean() > 0.85
    vols = [s["vol_ann"] for s in out["states"]]
    assert vols == sorted(vols) and vols[2] == pytest.approx(0.70, rel=0.15)


def test_loglik_on_returns_scale():
    """The reported log-likelihood is that of the raw returns (standardisation Jacobian included)."""
    r, _ = markov_returns([[0.95, 0.05], [0.1, 0.9]], [0.0, 0.0], [0.01, 0.03], T=600, seed=7)
    out = H.hmm_fit(r * 3.0, n_states=2)
    base = H.hmm_fit(r, n_states=2)
    assert out["loglik"] == pytest.approx(base["loglik"] - len(r) * math.log(3.0), rel=1e-6)


def test_real_data(closes):
    r = closes["NVDA"].dropna().pct_change().dropna()
    t0 = time.perf_counter()
    out = H.hmm_fit(r, 2)
    assert time.perf_counter() - t0 < 2.0
    dumps(out)
    assert out["n"] == len(r) and out["states"][0]["vol_ann"] < out["states"][1]["vol_ann"]
    assert len(out["probs"]["t"]) == len(out["probs"]["p"]) == len(out["viterbi"]["v"]) == len(r)
    assert set(out["viterbi"]["v"]) <= {0, 1}
    three = H.hmm_fit(closes["SPY"].dropna().pct_change().dropna(), 3)
    dumps(three)
    assert len(three["transition"]) == 3


@pytest.mark.parametrize("returns", [
    pd.Series(np.random.default_rng(0).normal(0, 0.01, 10), index=pd.bdate_range("2024-01-01", periods=10)),
    pd.Series(0.0, index=pd.bdate_range("2024-01-01", periods=300)),
    pd.Series(dtype=float),
])
def test_edge_cases(returns):
    out = H.hmm_fit(returns)
    dumps(out)
    assert out["states"] == [] and "error" in out


def test_nans_and_other_state_counts():
    r, _ = markov_returns([[0.97, 0.03], [0.05, 0.95]], [0.0, 0.0], [0.01, 0.03], T=500, seed=2)
    r.iloc[[5, 50, 300]] = np.nan
    out = H.hmm_fit(r, 2)
    dumps(out)
    assert out["n"] == 497
    one = H.hmm_fit(r, 1)
    dumps(one)
    assert one["states"][0]["vol_ann"] == pytest.approx(r.std(ddof=0) * math.sqrt(252), rel=1e-6)
    four = H.hmm_fit(r, 4, n_iter=50)
    dumps(four)
    assert [s["label"] for s in four["states"]] == ["Calm", "Normal", "Elevated", "Turbulent"]
