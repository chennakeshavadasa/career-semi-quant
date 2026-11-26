"""Market regimes: Gaussian hidden Markov model on daily returns.

Estimation is Baum-Welch EM (Baum et al. 1970) with the scaled forward-backward recursions
(Rabiner 1989), run in log-depth blocks: the forward (backward) products of the per-step
matrices M_t = A diag(b_t) are formed within blocks of ~sqrt(T) steps in parallel and chained
across blocks, with per-step normalisation. This is algebraically the scaled forward-backward,
just with ~2 sqrt(T) instead of 2T sequential numpy steps. Several random starts are run
jointly for a few EM iterations and the best one is iterated to convergence ("short-run EM"
initialisation, Biernacki, Celeux & Govaert 2003). The most likely state path is the Viterbi
path (log space).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ._util import iso, jsonable, periods_per_year, ser

__all__ = ["hmm_fit"]

_LABELS = {1: ["All"], 2: ["Calm", "Turbulent"], 3: ["Calm", "Normal", "Turbulent"],
           4: ["Calm", "Normal", "Elevated", "Turbulent"]}
_VAR_FLOOR = 1e-3  # in units of the sample variance (vol floor ~3% of the sample vol)


def _forward_backward(M: np.ndarray, a0: np.ndarray):
    """Blocked scaled forward-backward.

    M: (I, T-1, K, K) with M[:, t-1, i, j] = A_ij b_t(j) (emissions already rescaled per step);
    a0: (I, K) = pi * b_0. Returns (gamma (I, T, K), xi summed over t (I, K, K), log-likelihood
    (I,) of the rescaled emissions)."""
    I, T1, K, _ = M.shape
    a0n = a0 / a0.sum(-1, keepdims=True)
    loglik = np.log(a0.sum(-1))
    if T1 == 0:
        return a0n[:, None, :].copy(), np.zeros((I, K, K)), loglik
    B = max(4, int(math.sqrt(T1)))
    nb = -(-T1 // B)
    pad = nb * B - T1
    if pad:
        M_p = np.concatenate([M, np.broadcast_to(np.eye(K), (I, pad, K, K))], axis=1)
    else:
        M_p = M
    Mp = M_p.reshape(I, nb, B, K, K)
    # forward: normalised prefix products inside each block, with their log scales
    L = np.empty_like(Mp)
    ls = np.empty((I, nb, B))
    s = Mp[:, :, 0].sum(axis=(-2, -1))
    L[:, :, 0] = Mp[:, :, 0] / s[..., None, None]
    ls[:, :, 0] = np.log(s)
    for j in range(1, B):
        P = L[:, :, j - 1] @ Mp[:, :, j]
        s = P.sum(axis=(-2, -1))
        L[:, :, j] = P / s[..., None, None]
        ls[:, :, j] = ls[:, :, j - 1] + np.log(s)
    v = np.empty((I, nb, K))
    v[:, 0] = a0n
    for k in range(nb):
        w = (v[:, k, None, :] @ L[:, k, B - 1])[:, 0]
        sw = w.sum(-1)
        loglik = loglik + np.log(sw) + ls[:, k, B - 1]
        if k + 1 < nb:
            v[:, k + 1] = w / sw[:, None]
    al = np.einsum("ibk,ibjkl->ibjl", v, L).reshape(I, nb * B, K)[:, :T1]
    alpha = np.concatenate([a0n[:, None, :], al / al.sum(-1, keepdims=True)], axis=1)  # (I, T, K)
    # backward: normalised suffix products inside each block, chained from the right
    R = np.empty_like(Mp)
    s = Mp[:, :, B - 1].sum(axis=(-2, -1))
    R[:, :, B - 1] = Mp[:, :, B - 1] / s[..., None, None]
    for j in range(B - 2, -1, -1):
        P = Mp[:, :, j] @ R[:, :, j + 1]
        R[:, :, j] = P / P.sum(axis=(-2, -1))[..., None, None]
    u = np.empty((I, nb, K))
    u[:, nb - 1] = 1.0 / K
    for k in range(nb - 2, -1, -1):
        w = (R[:, k + 1, 0] @ u[:, k + 1, :, None])[..., 0]
        u[:, k] = w / w.sum(-1, keepdims=True)
    be = np.einsum("ibjkl,ibl->ibjk", R, u).reshape(I, nb * B, K)[:, :T1]
    beta = np.empty_like(alpha)
    beta[:, :T1] = be / be.sum(-1, keepdims=True)
    beta[:, T1] = 1.0 / K
    g = alpha * beta
    g /= g.sum(-1, keepdims=True)
    X = alpha[:, :-1, :, None] * M * beta[:, 1:, None, :]
    X /= X.sum(axis=(-2, -1), keepdims=True)
    return g, X.sum(axis=1), loglik


def _log_emissions(x: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    """(I, T, K) Gaussian log densities."""
    return -0.5 * (np.log(2 * np.pi * var)[:, None, :] + (x[None, :, None] - mu[:, None, :]) ** 2 / var[:, None, :])


def _e_step(x, mu, var, A, pi):
    lb = _log_emissions(x, mu, var)
    m = lb.max(-1, keepdims=True)
    b = np.exp(lb - m)
    M = A[:, None, :, :] * b[:, 1:, None, :]
    g, xs, ll = _forward_backward(M, pi * b[:, 0, :])
    return g, xs, ll + m.sum(axis=(1, 2))


def _m_step(x, g, xs, mu, var, A):
    w = g.sum(axis=1)
    ok = w > 1e-8
    safe_w = np.where(ok, w, 1.0)
    mu_n = np.where(ok, (g * x[None, :, None]).sum(axis=1) / safe_w, mu)
    var_n = np.where(ok, (g * (x[None, :, None] - mu_n[:, None, :]) ** 2).sum(axis=1) / safe_w, var)
    var_n = np.maximum(var_n, _VAR_FLOOR)
    rs = xs.sum(-1, keepdims=True)
    A_n = np.where(rs > 1e-12, xs / np.where(rs > 1e-12, rs, 1.0), A)
    A_n = np.maximum(A_n, 1e-12)
    A_n /= A_n.sum(-1, keepdims=True)
    pi_n = np.maximum(g[:, 0, :], 1e-12)
    pi_n /= pi_n.sum(-1, keepdims=True)
    return mu_n, var_n, A_n, pi_n


def _em(x, mu, var, A, pi, n_iter: int, tol: float):
    """Batched EM; returns parameters, log-likelihoods, iterations used and convergence flags."""
    ll_old = np.full(mu.shape[0], -np.inf)
    conv = np.zeros(mu.shape[0], dtype=bool)
    it = 0
    for it in range(1, n_iter + 1):
        g, xs, ll = _e_step(x, mu, var, A, pi)
        conv = np.abs(ll - ll_old) < tol
        ll_old = ll
        if conv.all():
            break
        mu, var, A, pi = _m_step(x, g, xs, mu, var, A)
    return mu, var, A, pi, ll_old, it, conv


def _viterbi(x, mu, var, A, pi) -> np.ndarray:
    lb = _log_emissions(x, mu[None], var[None])[0]
    with np.errstate(divide="ignore"):
        logA = np.log(A)
        delta = np.log(pi) + lb[0]
    T, K = lb.shape
    psi = np.empty((T, K), dtype=np.int64)
    psi[0] = 0
    for t in range(1, T):
        s = delta[:, None] + logA
        psi[t] = s.argmax(axis=0)
        delta = s.max(axis=0) + lb[t]
    path = np.empty(T, dtype=np.int64)
    path[-1] = int(delta.argmax())
    for t in range(T - 1, 0, -1):
        path[t - 1] = psi[t, path[t]]
    return path


def _inits(x: np.ndarray, K: int, n_init: int, rng: np.random.Generator):
    """Start 0: split by 21-bar rolling volatility quantiles; others random."""
    I = max(int(n_init), 1)
    mu = np.empty((I, K))
    var = np.empty((I, K))
    A = np.empty((I, K, K))
    roll = pd.Series(x).rolling(21, min_periods=5).std().bfill().to_numpy()
    qs = np.quantile(roll, np.linspace(0, 1, K + 1))
    for k in range(K):
        sel = (roll >= qs[k]) & (roll <= qs[k + 1])
        xs = x[sel] if sel.sum() >= 2 else x
        mu[0, k], var[0, k] = xs.mean(), max(xs.var(), _VAR_FLOOR)
    for i in range(1, I):
        mu[i] = rng.normal(0.0, 0.25, K)
        var[i] = np.sort(np.exp(rng.uniform(np.log(0.15), np.log(4.0), K)))
    for i in range(I):
        if K == 1:
            A[i] = 1.0
            continue
        d = rng.uniform(0.85, 0.99, K) if i else np.full(K, 0.95)
        off = rng.dirichlet(np.ones(K - 1), K) if i else np.full((K, K - 1), 1.0 / (K - 1))
        for k in range(K):
            row = np.empty(K)
            row[k] = d[k]
            row[np.arange(K) != k] = (1 - d[k]) * off[k]
            A[i, k] = row
    pi = np.full((I, K), 1.0 / K)
    return mu, var, A, pi


def _empty(n_states: int, error: str | None = None) -> dict:
    out = {"n_states": int(n_states), "states": [], "transition": [], "current_state": None, "current_label": None,
           "current_probs": [], "viterbi": {"t": [], "v": []}, "probs": {"t": [], "p": []}, "loglik": None,
           "bic": None, "n": 0, "iterations": None, "converged": None}
    if error:
        out["error"] = error
    return jsonable(out)


def hmm_fit(returns: pd.Series, n_states: int = 2, n_iter: int = 200, seed: int = 0, n_init: int = 5) -> dict:
    """Gaussian hidden Markov model of daily returns (one mean and variance per state).

    ``n_init`` starts (one volatility-quantile start, the rest random from ``seed``) are run
    jointly for up to 25 EM iterations, the best by likelihood is iterated to convergence
    (|change in log-likelihood| < 1e-7 x T on standardised data) or ``n_iter`` iterations. States
    are sorted by volatility ascending and labelled ["Calm", "Turbulent"] (2), ["Calm", "Normal",
    "Turbulent"] (3), ["Calm", "Normal", "Elevated", "Turbulent"] (4), else "State i".

    Returns keys: ``n_states``, ``states`` [{"label", "mean_ann" (mean x ppy), "vol_ann" (std x
    sqrt(ppy)), "share" (average smoothed probability), "expected_duration_days" (1 / (1 -
    A_kk), in bars)}], ``transition`` (K x K, rows = from), ``current_state`` (index of the most
    likely state on the last date, smoothed = filtered there), ``current_label``,
    ``current_probs``, ``viterbi`` (ser of state indices), ``probs`` {"t", "p": [[p_state0, ...]
    per date]} (smoothed, 4 decimals), ``loglik`` (on the returns' scale), ``bic`` (-2 loglik +
    (K^2 + 2K - 1) ln T), ``n``, ``iterations``, ``converged``.
    """
    K = max(int(n_states), 1)
    try:
        s = pd.to_numeric(pd.Series(returns), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        if s.index.has_duplicates or not s.index.is_monotonic_increasing:
            s = s[~s.index.duplicated(keep="last")].sort_index()
        T = len(s)
        if T < max(30, 10 * K):
            return _empty(K, "insufficient history")
        r = s.to_numpy(dtype=float)
        m0, sd0 = float(r.mean()), float(r.std())
        if sd0 < 1e-12:
            return _empty(K, "zero variance")
        x = (r - m0) / sd0
        rng = np.random.default_rng(seed)
        mu, var, A, pi = _inits(x, K, n_init, rng)
        tol = 1e-7 * T
        n_iter = max(int(n_iter), 1)
        warm = min(25, n_iter)
        mu, var, A, pi, ll, it1, conv = _em(x, mu, var, A, pi, warm, tol)
        b = int(np.nanargmax(np.where(np.isfinite(ll), ll, -np.inf)))
        mu, var, A, pi = mu[b:b + 1], var[b:b + 1], A[b:b + 1], pi[b:b + 1]
        it2, conv_b = 0, bool(conv[b])
        if not conv_b and n_iter > warm:
            mu, var, A, pi, ll2, it2, conv2 = _em(x, mu, var, A, pi, n_iter - warm, tol)
            conv_b = bool(conv2[0])
        g, _, llf = _e_step(x, mu, var, A, pi)
        mu, var, A, pi, g, llf = mu[0], var[0], A[0], pi[0], g[0], float(llf[0])
        order = np.argsort(np.sqrt(var))
        mu, var, pi, g = mu[order], var[order], pi[order], g[:, order]
        A = A[np.ix_(order, order)]
        path = _viterbi(x, mu, var, A, pi)
        ppy = periods_per_year(s.index) if isinstance(s.index, pd.DatetimeIndex) else 252.0
        mean_r = m0 + sd0 * mu
        vol_r = sd0 * np.sqrt(var)
        labels = _LABELS.get(K, [f"State {i + 1}" for i in range(K)])
        loglik = llf - T * math.log(sd0)
        npar = K * K + 2 * K - 1
        states = []
        for k in range(K):
            stay = A[k, k]
            states.append({"label": labels[k], "mean_ann": mean_r[k] * ppy, "vol_ann": vol_r[k] * math.sqrt(ppy),
                           "share": float(g[:, k].mean()),
                           "expected_duration_days": 1.0 / (1.0 - stay) if stay < 1 else None})
        cur = int(np.argmax(g[-1]))
        idx = s.index
        t = [iso(v) for v in idx] if isinstance(idx, pd.DatetimeIndex) else [str(v) for v in idx]
        out = {"n_states": K, "states": states, "transition": A, "current_state": cur, "current_label": labels[cur],
               "current_probs": g[-1], "viterbi": ser(pd.Series(path, index=idx)) if isinstance(idx, pd.DatetimeIndex)
               else {"t": t, "v": path}, "probs": {"t": t, "p": np.round(g, 4)},
               "loglik": loglik, "bic": -2.0 * loglik + npar * math.log(T), "n": T, "iterations": int(it1 + it2),
               "converged": conv_b}
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        return _empty(K, str(exc))
