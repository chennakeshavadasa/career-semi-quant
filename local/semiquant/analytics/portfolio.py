"""Portfolio construction and risk on daily data.

Inputs are daily simple returns (DataFrame, columns = tickers) unless stated otherwise (``backtest``
takes prices). Complete cases are used for covariance and optimisation (rows with any NaN dropped).
Everything is annualised with 252 trading days; weights, returns and risk are fractions.

Methods: Ledoit & Wolf (2004) linear shrinkage towards a scaled identity; RiskMetrics (1996) EWMA
covariance; James-Stein (Efron & Morris 1973) shrinkage of mean returns; mean-variance optimisation
(Markowitz 1952) with SLSQP; equal risk contribution (Maillard, Roncalli & Teiletche 2010, solved by
cyclical coordinate descent, Griveau-Billion, Richard & Roncalli 2013); hierarchical risk parity
(Lopez de Prado 2016); maximum diversification (Choueifaty & Coignard 2008); Euler risk
decomposition; Black & Litterman (1992) with He & Litterman (1999) / Idzorek (2005) view confidence.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import minimize
from scipy.spatial.distance import pdist

from ._util import TRADING_DAYS, clean, jsonable, ser

__all__ = ["shrink_cov", "expected_returns", "optimize", "efficient_frontier", "portfolio_risk", "backtest",
           "black_litterman"]

Z95, Z99 = 1.6448536269514722, 2.3263478740408408
METHODS = ("equal", "inverse_vol", "min_var", "max_sharpe", "erc", "hrp", "max_div")
EWMA_LAMBDA = 0.97


# =============================================================================== helpers
def _clean_returns(returns) -> pd.DataFrame:
    """Numeric returns, inf -> NaN, all-NaN columns dropped, then complete cases only."""
    if returns is None:
        return pd.DataFrame()
    R = returns.to_frame() if isinstance(returns, pd.Series) else pd.DataFrame(returns)
    if R.empty:
        return pd.DataFrame()
    try:
        R = R.astype(float)
    except (ValueError, TypeError):
        R = R.apply(pd.to_numeric, errors="coerce")
    R = R.replace([np.inf, -np.inf], np.nan)
    R = R.loc[:, R.notna().any()]
    return R.dropna(how="any")


def _to_returns(s) -> pd.Series:
    """Daily returns from a Series of returns or prices (prices detected: all positive, median > 0.5)."""
    if s is None:
        return pd.Series(dtype=float)
    x = pd.to_numeric(pd.Series(s), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    x = x[~x.index.duplicated(keep="last")].sort_index()
    if len(x) and (x > 0).all() and x.abs().median() > 0.5:
        x = x.pct_change().dropna()
    return x


def _ledoit_wolf(X: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit & Wolf (2004) shrinkage of the (1/n) sample covariance towards mu * I, mu = tr(S)/p.

    d^2 = ||S - mu I||^2 / p, b_bar^2 = (1/n^2) sum_k ||x_k x_k' - S||^2 / p, b^2 = min(b_bar^2, d^2),
    delta = b^2 / d^2, Sigma = delta mu I + (1 - delta) S (Frobenius norms; x_k demeaned rows).
    """
    Xc = X - X.mean(axis=0)
    n, p = Xc.shape
    S = Xc.T @ Xc / n
    mu = np.trace(S) / p
    eye = np.eye(p)
    d2 = ((S - mu * eye) ** 2).sum() / p
    b_bar2 = (((Xc ** 2).sum(axis=1) ** 2).sum() / n ** 2 - (S ** 2).sum() / n) / p
    b2 = min(b_bar2, d2)
    delta = float(b2 / d2) if d2 > 0 else 1.0
    return delta * mu * eye + (1.0 - delta) * S, delta


def _ewma_cov(X: np.ndarray, lam: float = EWMA_LAMBDA) -> np.ndarray:
    """RiskMetrics exponentially weighted covariance (zero-mean convention), weights ~ lam^(age)."""
    n = X.shape[0]
    w = lam ** np.arange(n - 1, -1, -1, dtype=float)
    w /= w.sum()
    return (X * w[:, None]).T @ X


def shrink_cov(returns: pd.DataFrame, method: str = "ledoit_wolf") -> pd.DataFrame:
    """Annualised covariance matrix (x252) of daily returns.

    method: "sample" (unbiased sample covariance), "ledoit_wolf" (Ledoit & Wolf 2004 shrinkage towards
    the scaled identity, own implementation; the intensity is in ``.attrs["shrinkage"]``) or "ewma"
    (RiskMetrics, lambda = 0.97, zero mean). Unknown methods fall back to "ledoit_wolf". Complete cases
    only; fewer than two observations give an all-NaN matrix.
    """
    R = _clean_returns(returns)
    cols = R.columns
    m = str(method).lower().replace("-", "_")
    if m not in ("sample", "ledoit_wolf", "lw", "ewma"):
        m = "ledoit_wolf"
    if len(R) < 2 or len(cols) == 0:
        out = pd.DataFrame(np.nan, index=cols, columns=cols)
        out.attrs.update(method=m, shrinkage=None, n_obs=len(R))
        return out
    X = R.to_numpy()
    shrink = None
    if m == "sample":
        S = np.atleast_2d(np.cov(X, rowvar=False, ddof=1))
    elif m == "ewma":
        S = _ewma_cov(X)
    else:
        S, shrink = _ledoit_wolf(X)
        m = "ledoit_wolf"
    out = pd.DataFrame(S * TRADING_DAYS, index=cols, columns=cols)
    out.attrs.update(method=m, shrinkage=shrink, n_obs=len(R))
    return out


def expected_returns(returns: pd.DataFrame, method: str = "shrunk", rf: float = 0.04, bench=None,
                     erp: float = 0.055) -> pd.Series:
    """Annualised expected returns (x252, arithmetic).

    method: "historical" (mean daily return x 252); "shrunk" (positive-part James-Stein shrinkage of the
    mean vector towards its cross-sectional average: weight w = min(1, (p - 3) / (T d' S^-1 d)),
    d = deviations from the average, S = Ledoit-Wolf daily covariance, T observations; no shrinkage for
    p <= 3; w in ``.attrs["shrinkage"]``. With a few years of daily data mean differences are usually
    within estimation noise and w = 1, i.e. all assets get the same expected return); "bayes_stein"
    (Jorion 1986: w = (p + 2) / ((p + 2) + T d' S^-1 d) with d measured from the global minimum-variance
    portfolio's mean; never shrinks completely; the default ``mu`` of ``optimize`` and
    ``efficient_frontier``); "capm" (rf + beta x erp, beta vs ``bench`` returns or prices, else vs the
    equal-weighted average of the assets). Unknown methods fall back to "historical".
    """
    R = _clean_returns(returns)
    if R.empty:
        return pd.Series(dtype=float)
    m = str(method).lower()
    mu = R.mean()
    if m == "shrunk":
        p, T = R.shape[1], len(R)
        w = 0.0
        if p > 3 and T > p:
            S, _ = _ledoit_wolf(R.to_numpy())
            d = (mu - mu.mean()).to_numpy()
            try:
                q = float(T * d @ np.linalg.solve(S, d))
            except np.linalg.LinAlgError:
                q = float("nan")
            w = float(min(1.0, max(0.0, (p - 3) / q))) if np.isfinite(q) and q > 0 else 1.0
        out = (mu.mean() + (1.0 - w) * (mu - mu.mean())) * TRADING_DAYS
        out.attrs.update(method="shrunk", shrinkage=w)
        return out
    if m == "bayes_stein":
        X = R.to_numpy()
        T, p = X.shape
        S, _ = _ledoit_wolf(X)
        one = np.ones(p)
        try:
            si1 = np.linalg.solve(S, one)
            mu0 = float(si1 @ mu.to_numpy() / si1.sum())
            d = mu.to_numpy() - mu0
            q = float(T * d @ np.linalg.solve(S, d))
        except np.linalg.LinAlgError:
            mu0, q = float(mu.mean()), float("nan")
        w = (p + 2.0) / ((p + 2.0) + q) if np.isfinite(q) and q >= 0 else 1.0
        out = ((1.0 - w) * mu + w * mu0) * TRADING_DAYS
        out.attrs.update(method="bayes_stein", shrinkage=w, target=mu0 * TRADING_DAYS)
        return out
    if m == "capm":
        b = _to_returns(bench) if bench is not None else R.mean(axis=1)
        J = pd.concat([R, b.rename("__b__")], axis=1, join="inner").dropna()
        if len(J) < 20:
            out = mu * TRADING_DAYS
            out.attrs.update(method="historical", note="too little overlap with the benchmark for CAPM")
            return out
        bb = J.pop("__b__")
        beta = J.apply(lambda c: np.cov(c, bb, ddof=1)[0, 1]) / bb.var(ddof=1)
        out = (clean(rf) or 0.0) + beta * erp
        out.attrs.update(method="capm", proxy="bench" if bench is not None else "equal-weight average")
        return out
    out = mu * TRADING_DAYS
    out.attrs.update(method="historical")
    return out


# =============================================================================== optimisation
def _inputs(returns, mu, cov, rf):
    warns: list[str] = []
    R = _clean_returns(returns) if returns is not None else pd.DataFrame()
    if cov is not None:
        C = cov if isinstance(cov, pd.DataFrame) else pd.DataFrame(np.asarray(cov, float), index=R.columns,
                                                                    columns=R.columns)
        C = C.astype(float)
    else:
        C = shrink_cov(R, "ledoit_wolf")
    tickers = [t for t in C.index if t in C.columns]
    C = C.loc[tickers, tickers]
    if mu is None:
        m = expected_returns(R, "bayes_stein", rf) if not R.empty else pd.Series(np.nan, index=tickers)
    elif isinstance(mu, (pd.Series, dict)):
        m = pd.Series(mu, dtype=float)
    else:
        m = pd.Series(np.asarray(mu, float).ravel(), index=tickers[:len(np.asarray(mu).ravel())])
    m = m.reindex(tickers)
    if m.isna().any() and not R.empty:
        fill = expected_returns(R, "historical").reindex(tickers)
        miss = m.index[m.isna()].tolist()
        m = m.fillna(fill)
        warns.append(f"expected returns missing for {miss}; historical means used")
    diag = np.diag(C.to_numpy()) if len(tickers) else np.array([])
    good = [t for t, v, mv in zip(tickers, diag, m.to_numpy()) if np.isfinite(v) and v > 0 and np.isfinite(mv)]
    if len(good) < len(tickers):
        warns.append(f"dropped {sorted(set(tickers) - set(good))}: missing variance or expected return")
    C = C.loc[good, good]
    return good, m.reindex(good).to_numpy(float), C.to_numpy(float), warns


def _bounds(n, lo, hi, warns):
    hi = 1.0 if clean(hi) is None else float(min(max(hi, 0.0), 1.0))
    lo = 0.0 if clean(lo) is None else float(max(lo, 0.0))
    if n and hi * n < 1.0 - 1e-12:
        warns.append(f"max_weight {hi:.2%} x {n} assets < 100%: raised to {1.0 / n:.2%}")
        hi = 1.0 / n
    if n and lo * n > 1.0 + 1e-12:
        warns.append(f"min_weight {lo:.2%} x {n} assets > 100%: set to 0")
        lo = 0.0
    if lo > hi:
        lo = 0.0
    return lo, hi


def _cap(w: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Project weights into [lo, hi] (sum 1) by iterative capping and proportional redistribution."""
    w = np.clip(np.asarray(w, float), 0.0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(w.size, 1.0 / w.size)
    for _ in range(200):
        over, under = w > hi + 1e-12, w < lo - 1e-12
        if not over.any() and not under.any():
            break
        fixed = over | under
        w[over], w[under] = hi, lo
        free = ~fixed & (w > lo) & (w < hi)
        rest = 1.0 - w[fixed].sum() - w[~fixed & ~free].sum()
        if not free.any() or w[free].sum() <= 0:
            break
        w[free] = w[free] / w[free].sum() * rest
    return w


def _slsqp(f, grad, x0, lo, hi, extra=()):
    n = len(x0)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones_like(w)}] + list(extra)
    try:
        res = minimize(f, x0, jac=grad, method="SLSQP", bounds=[(lo, hi)] * n, constraints=cons,
                       options={"maxiter": 500, "ftol": 1e-12})
        w, ok = res.x, bool(res.success)
    except (ValueError, np.linalg.LinAlgError):
        w, ok = np.asarray(x0, float), False
    w = np.clip(np.nan_to_num(w, nan=1.0 / n), lo, hi)
    return w / w.sum(), ok


def _min_var(C, lo, hi, x0=None):
    n = len(C)
    x0 = np.full(n, 1.0 / n) if x0 is None else x0
    return _slsqp(lambda w: w @ C @ w, lambda w: 2.0 * C @ w, x0, lo, hi)


def _neg_ratio(v):
    """-(w'v - 0) / sqrt(w'Cw) objective/gradient factory for Sharpe (v = excess mu) and DR (v = vols)."""
    def make(C):
        def f(w):
            s = math.sqrt(max(w @ C @ w, 1e-300))
            return -(w @ v) / s

        def g(w):
            Cw = C @ w
            s = math.sqrt(max(w @ Cw, 1e-300))
            return -(v / s - (w @ v) * Cw / s ** 3)
        return f, g
    return make


def _erc(C: np.ndarray, tol: float = 1e-12, maxiter: int = 5000) -> np.ndarray:
    """Equal risk contribution by cyclical coordinate descent on y_i (C y)_i = 1/n (then w = y / sum y)."""
    n = len(C)
    b = np.full(n, 1.0 / n)
    d = np.diag(C).copy()
    y = 1.0 / np.sqrt(d)
    y /= y.sum()
    for _ in range(maxiter):
        prev = y.copy()
        for i in range(n):
            c = C[i] @ y - d[i] * y[i]
            y[i] = (-c + math.sqrt(c * c + 4.0 * d[i] * b[i])) / (2.0 * d[i])
        if np.max(np.abs(y - prev)) <= tol * np.max(np.abs(y)):
            break
    return y / y.sum()


def _hrp(C: np.ndarray) -> np.ndarray:
    """Hierarchical risk parity (Lopez de Prado 2016): correlation distance sqrt((1 - rho) / 2), single-
    linkage clustering on the Euclidean distance between distance columns, quasi-diagonal ordering, then
    recursive bisection with inverse-variance cluster weights."""
    n = len(C)
    if n == 1:
        return np.ones(1)
    sd = np.sqrt(np.diag(C))
    corr = np.clip(C / np.outer(sd, sd), -1.0, 1.0)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    order = leaves_list(linkage(pdist(dist), method="single"))
    w = np.ones(n)

    def cvar(idx):
        sub = C[np.ix_(idx, idx)]
        iv = 1.0 / np.diag(sub)
        iv /= iv.sum()
        return float(iv @ sub @ iv)

    clusters = [list(order)]
    while clusters:
        nxt = []
        for c in clusters:
            if len(c) < 2:
                continue
            h = len(c) // 2
            c1, c2 = c[:h], c[h:]
            v1, v2 = cvar(c1), cvar(c2)
            a = 1.0 - v1 / (v1 + v2)
            w[c1] *= a
            w[c2] *= 1.0 - a
            nxt += [c1, c2]
        clusters = nxt
    return w / w.sum()


def _stats(w: np.ndarray, mu: np.ndarray, C: np.ndarray, rf: float) -> dict:
    var = float(w @ C @ w)
    vol = math.sqrt(max(var, 0.0))
    ret = float(w @ mu) if mu is not None and np.isfinite(mu).all() else None
    sd = np.sqrt(np.diag(C))
    rc = w * (C @ w) / var if var > 0 else np.full(w.size, np.nan)
    return {"exp_return": ret, "vol": vol, "sharpe": (ret - rf) / vol if ret is not None and vol > 0 else None,
            "risk_contrib_arr": rc, "diversification_ratio": float(w @ sd) / vol if vol > 0 else None,
            "effective_n": 1.0 / float((w ** 2).sum())}


def _solve(method, mu, C, lo, hi, rf, warns):
    n = len(C)
    eq = np.full(n, 1.0 / n)
    ok = True
    if method == "equal":
        w = eq
    elif method == "inverse_vol":
        w = _cap(1.0 / np.sqrt(np.diag(C)), lo, hi)
    elif method == "min_var":
        w, ok = _min_var(C, lo, hi)
    elif method == "max_sharpe":
        ex = mu - rf
        if not (ex > 0).any():
            warns.append("no asset has expected return above rf: max_sharpe falls back to min_var")
            w, ok = _min_var(C, lo, hi)
        else:
            f, g = _neg_ratio(ex)(C)
            wmv, _ = _min_var(C, lo, hi)
            best = None
            for x0 in (eq, wmv, _cap(np.clip(ex, 1e-9, None), lo, hi)):
                cand, ok_c = _slsqp(f, g, x0, lo, hi)
                if best is None or f(cand) < f(best[0]) - 1e-12:
                    best = (cand, ok_c)
            w, ok = best
    elif method == "max_div":
        f, g = _neg_ratio(np.sqrt(np.diag(C)))(C)
        w, ok = _slsqp(f, g, eq, lo, hi)
    elif method == "erc":
        w = _erc(C)
        if w.max() > hi + 1e-9 or w.min() < lo - 1e-9:
            warns.append("weight bounds bind: ERC solved as least-squares risk-parity under the bounds")

            def f(x):
                v = x @ C @ x
                rc = x * (C @ x) / v
                return float(((rc - 1.0 / n) ** 2).sum()) * 1e4
            w, ok = _slsqp(f, None, _cap(w, lo, hi), lo, hi)
    elif method == "hrp":
        w = _hrp(C)
        if w.max() > hi + 1e-9 or w.min() < lo - 1e-9:
            warns.append("HRP weights capped to the bounds (excess redistributed proportionally)")
            w = _cap(w, lo, hi)
    else:
        warns.append(f"unknown method {method!r}: max_sharpe used")
        return _solve("max_sharpe", mu, C, lo, hi, rf, warns)
    w = np.where(np.abs(w) < 1e-10, 0.0, w)
    return w / w.sum(), ok


def optimize(returns: pd.DataFrame, method: str = "max_sharpe", max_weight: float = 0.35, min_weight: float = 0.0,
             rf: float = 0.04, mu=None, cov=None) -> dict:
    """Long-only portfolio weights (sum 1, min_weight <= w <= max_weight).

    Methods: "equal"; "inverse_vol" (w ~ 1/sigma, capped); "min_var" (min w'Cw); "max_sharpe" (max
    (w'mu - rf)/sqrt(w'Cw), best of three SLSQP starts; min_var if no asset beats rf); "erc" (equal risk
    contribution, exact by coordinate descent, least-squares under binding bounds); "hrp" (hierarchical
    risk parity, capped); "max_div" (max w'sigma / sqrt(w'Cw)). SLSQP with bounds and the budget
    constraint. Defaults: cov = Ledoit-Wolf shrunk covariance, mu = Bayes-Stein shrunk means (Jorion
    1986; both annualised). The James-Stein "shrunk" means often collapse to one value, which would make
    max_sharpe identical to min_var; pass ``mu`` (Series/dict, e.g. ``expected_returns(r, "shrunk")`` or
    Black-Litterman posteriors) and/or ``cov`` (DataFrame) to override. Infeasible bounds are relaxed
    with a warning.

    Returns {"method", "weights": {ticker: w}, "exp_return", "vol", "sharpe", "risk_contrib": {ticker:
    share of variance}, "diversification_ratio" (w'sigma / vol), "effective_n" (1 / sum w^2),
    "converged", "max_weight", "min_weight", "warnings": [...]}.
    """
    m = str(method).lower()
    rf = clean(rf) or 0.0
    try:
        tickers, mu_v, C, warns = _inputs(returns, mu, cov, rf)
    except (ValueError, TypeError, KeyError) as exc:
        tickers, mu_v, C, warns = [], np.array([]), np.zeros((0, 0)), [f"invalid inputs: {exc}"]
    base = {"method": m, "weights": {}, "exp_return": None, "vol": None, "sharpe": None, "risk_contrib": {},
            "diversification_ratio": None, "effective_n": None, "converged": False, "max_weight": max_weight,
            "min_weight": min_weight, "warnings": warns}
    n = len(tickers)
    if n == 0:
        warns.append("no usable assets")
        return jsonable(base)
    lo, hi = _bounds(n, min_weight, max_weight, warns)
    w, ok = _solve(m, mu_v, C, lo, hi, rf, warns)
    st = _stats(w, mu_v, C, rf)
    base.update({"weights": dict(zip(tickers, w.tolist())), "exp_return": st["exp_return"], "vol": st["vol"],
                 "sharpe": st["sharpe"], "risk_contrib": dict(zip(tickers, st["risk_contrib_arr"].tolist())),
                 "diversification_ratio": st["diversification_ratio"], "effective_n": st["effective_n"],
                 "converged": ok, "max_weight": hi, "min_weight": lo})
    return jsonable(base)


def efficient_frontier(returns: pd.DataFrame, n_points: int = 30, max_weight: float = 0.35, rf: float = 0.04,
                       mu=None, cov=None) -> dict:
    """Long-only efficient frontier under the weight cap.

    Target returns are spaced evenly from the minimum-variance portfolio's return to the highest return
    attainable under the bounds (greedy fill of the highest-mu assets); each point minimises variance
    subject to w'mu >= target (SLSQP, warm-started from the previous point). Defaults for mu / cov as in
    ``optimize`` (Bayes-Stein means, Ledoit-Wolf covariance); identical expected returns give a single
    point (warning).

    Returns {"points": [{"vol", "ret", "sharpe", "weights": {ticker: w}}], "assets": [{"ticker", "vol",
    "ret"}], "min_var": {point}, "max_sharpe": {point}, "warnings": [...]}.
    """
    rf = clean(rf) or 0.0
    try:
        tickers, mu_v, C, warns = _inputs(returns, mu, cov, rf)
    except (ValueError, TypeError, KeyError) as exc:
        tickers, mu_v, C, warns = [], np.array([]), np.zeros((0, 0)), [f"invalid inputs: {exc}"]
    out = {"points": [], "assets": [], "min_var": None, "max_sharpe": None, "warnings": warns}
    n = len(tickers)
    if n == 0:
        warns.append("no usable assets")
        return jsonable(out)
    lo, hi = _bounds(n, 0.0, max_weight, warns)

    def point(w):
        st = _stats(w, mu_v, C, rf)
        return {"vol": st["vol"], "ret": st["exp_return"], "sharpe": st["sharpe"], "weights": dict(zip(tickers, w.tolist()))}

    out["assets"] = [{"ticker": t, "vol": math.sqrt(C[i, i]), "ret": float(mu_v[i])} for i, t in enumerate(tickers)]
    w_mv, _ = _min_var(C, lo, hi)
    w_ms, _ = _solve("max_sharpe", mu_v, C, lo, hi, rf, warns)
    out["min_var"], out["max_sharpe"] = point(w_mv), point(w_ms)
    # highest attainable return under the bounds: fill the best assets up to the cap
    w_top = np.full(n, lo)
    room = 1.0 - w_top.sum()
    for i in np.argsort(-mu_v):
        add = min(hi - lo, room)
        w_top[i] += add
        room -= add
        if room <= 1e-15:
            break
    r_lo, r_hi = float(w_mv @ mu_v), float(w_top @ mu_v)
    k = max(int(n_points), 2)
    targets = np.linspace(r_lo, r_hi, k) if r_hi > r_lo + 1e-12 else np.array([r_lo])
    if targets.size == 1:
        warns.append("all expected returns are equal: the frontier is the minimum-variance portfolio")
    x0 = w_mv
    for tgt in targets:
        cons = [{"type": "ineq", "fun": lambda w, t=tgt: w @ mu_v - t, "jac": lambda w: mu_v}]
        w, _ok = _slsqp(lambda w: w @ C @ w, lambda w: 2.0 * C @ w, x0, lo, hi, cons)
        out["points"].append(point(w))
        x0 = w
    return jsonable(out)


# =============================================================================== risk
def portfolio_risk(weights: dict, returns: pd.DataFrame, benchmark: pd.Series | None = None, rf: float = 0.04,
                   value: float = 1.0) -> dict:
    """Ex-post risk of a constant-weight (daily rebalanced) portfolio.

    Weights are normalised to sum 1 when all are non-negative (warning if they summed to something else);
    tickers missing from ``returns`` are dropped. ``benchmark`` may be daily returns or prices.
    exp_return = mean daily return x 252; vol = std x sqrt(252); sharpe = (exp_return - rf) / vol;
    sortino uses the downside deviation below rf/252; max_drawdown from the compounded path.
    VaR / ES are 1-day, historical (empirical quantile and tail mean), reported as positive loss
    fractions; ``*_param`` are zero-mean normal VaR (z x daily vol); ``*_value`` multiply by ``value``.
    Euler decomposition on the sample covariance: risk_contrib = w_i (C w)_i / w'Cw (sums to 1),
    marginal_var = z95 (C_d w)_i / sigma_d (1-day 95 % parametric VaR per unit weight), component_var =
    w_i x marginal_var (sums to var95_param). Holding "beta" is vs the benchmark when given, else vs the
    portfolio.

    Returns {"exp_return", "vol", "sharpe", "sortino", "max_drawdown", "beta", "tracking_error",
    "information_ratio", "var95", "var99", "es95", "es99", "var95_param", "var99_param", "var95_value",
    "var99_value", "es95_value", "es99_value", "diversification_ratio", "effective_n", "avg_corr",
    "n_obs", "holdings": [{"ticker", "weight", "vol", "beta", "beta_to_portfolio", "risk_contrib",
    "marginal_var", "component_var"}], "warnings": [...]}.
    """
    warns: list[str] = []
    keys = ["exp_return", "vol", "sharpe", "sortino", "max_drawdown", "beta", "tracking_error", "information_ratio",
            "var95", "var99", "es95", "es99", "var95_param", "var99_param", "var95_value", "var99_value",
            "es95_value", "es99_value", "diversification_ratio", "effective_n", "avg_corr"]
    out = {k: None for k in keys}
    out.update(n_obs=0, holdings=[], warnings=warns)
    rf = clean(rf) or 0.0
    value = clean(value) or 1.0
    if isinstance(returns, pd.Series):
        returns = returns.to_frame()
    cols = returns.columns if isinstance(returns, pd.DataFrame) else []
    w = pd.Series({str(k): clean(v) for k, v in (weights or {}).items()}, dtype=float).dropna()
    missing = [t for t in w.index if t not in cols]
    if missing:
        warns.append(f"no return data for {missing}; dropped")
    w = w[[t for t in w.index if t in cols]]
    w = w[w != 0]
    R = _clean_returns(returns[list(w.index)]) if len(w) else pd.DataFrame()
    if w.empty or R.empty:
        warns.append("no holdings with return data")
        return jsonable(out)
    w = w[[t for t in w.index if t in R.columns]]
    total = float(w.sum())
    if (w >= 0).all() and total > 0 and abs(total - 1.0) > 1e-9:
        if abs(total - 1.0) > 0.01:
            warns.append(f"weights summed to {total:.4f}; normalised to 1")
        w = w / total
    if len(R) < 20:
        warns.append(f"only {len(R)} observations")
        if len(R) < 3:
            return jsonable(out)
    wv = w.to_numpy()
    rp = pd.Series(R.to_numpy() @ wv, index=R.index)
    mu_d, sd_d = float(rp.mean()), float(rp.std(ddof=1))
    exp_ret, vol = mu_d * TRADING_DAYS, sd_d * math.sqrt(TRADING_DAYS)
    downside = math.sqrt(float((np.minimum(rp - rf / TRADING_DAYS, 0.0) ** 2).mean())) * math.sqrt(TRADING_DAYS)
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + rp.to_numpy())])
    mdd = float((wealth / np.maximum.accumulate(wealth) - 1.0).min())
    x = rp.to_numpy()
    q05, q01 = np.quantile(x, 0.05), np.quantile(x, 0.01)
    out.update({"exp_return": exp_ret, "vol": vol, "sharpe": (exp_ret - rf) / vol if vol > 0 else None,
                "sortino": (exp_ret - rf) / downside if downside > 0 else None, "max_drawdown": mdd,
                "var95": -float(q05), "var99": -float(q01), "es95": -float(x[x <= q05].mean()),
                "es99": -float(x[x <= q01].mean()), "var95_param": Z95 * sd_d, "var99_param": Z99 * sd_d,
                "n_obs": int(len(x))})
    for k in ("var95", "var99", "es95", "es99"):
        out[f"{k}_value"] = out[k] * value
    Cd = np.atleast_2d(np.cov(R.to_numpy(), rowvar=False, ddof=1))
    Ca = Cd * TRADING_DAYS
    Cw_d = Cd @ wv
    var_p = float(wv @ Cw_d)
    sd = np.sqrt(np.diag(Ca))
    out["diversification_ratio"] = float(wv @ sd) / vol if vol > 0 else None
    out["effective_n"] = 1.0 / float((wv ** 2).sum())
    if len(wv) > 1:
        corr = np.corrcoef(R.to_numpy(), rowvar=False)
        out["avg_corr"] = float(corr[~np.eye(len(wv), dtype=bool)].mean())
    beta_port = Cw_d / var_p if var_p > 0 else np.full(len(wv), np.nan)
    asset_beta = beta_port
    if benchmark is not None:
        b = _to_returns(benchmark)
        if isinstance(b.index, pd.DatetimeIndex) and b.index.tz is not None:
            b = b.tz_localize(None)
        J = pd.concat([rp.rename("p"), b.rename("b"), R], axis=1, join="inner").dropna()
        if len(J) >= 20 and J["b"].var() > 0:
            vb = float(J["b"].var(ddof=1))
            out["beta"] = float(np.cov(J["p"], J["b"], ddof=1)[0, 1] / vb)
            act = J["p"] - J["b"]
            te = float(act.std(ddof=1)) * math.sqrt(TRADING_DAYS)
            out["tracking_error"] = te
            out["information_ratio"] = float(act.mean()) * TRADING_DAYS / te if te > 0 else None
            asset_beta = np.array([np.cov(J[t], J["b"], ddof=1)[0, 1] / vb for t in w.index])
        else:
            warns.append("benchmark has fewer than 20 overlapping observations")
    mvar = Z95 * Cw_d / math.sqrt(var_p) if var_p > 0 else np.full(len(wv), np.nan)
    rc = wv * Cw_d / var_p if var_p > 0 else np.full(len(wv), np.nan)
    out["holdings"] = [{"ticker": t, "weight": float(wv[i]), "vol": float(sd[i]), "beta": float(asset_beta[i]),
                        "beta_to_portfolio": float(beta_port[i]), "risk_contrib": float(rc[i]),
                        "marginal_var": float(mvar[i]), "component_var": float(wv[i] * mvar[i])}
                       for i, t in enumerate(w.index)]
    return jsonable(out)


# =============================================================================== backtest
def _period_ends(idx: pd.DatetimeIndex, freq: str) -> np.ndarray:
    """Positions of the last session of each month ("M") or calendar quarter ("Q"), excluding the end."""
    if freq not in ("M", "Q") or len(idx) < 2:
        return np.array([], dtype=int)
    key = idx.year * 12 + idx.month - 1 if freq == "M" else idx.year * 4 + (idx.month - 1) // 3
    key = np.asarray(key)
    return np.flatnonzero(key[:-1] != key[1:])


def _perf(eq: pd.Series, rf: float) -> dict:
    r = eq.pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25 if len(eq) > 1 else 0.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 and eq.iloc[0] > 0 else None
    vol = float(r.std(ddof=1)) * math.sqrt(TRADING_DAYS) if len(r) > 1 else None
    sharpe = (float(r.mean()) * TRADING_DAYS - rf) / vol if vol else None
    mdd = float((eq / eq.cummax() - 1.0).min()) if len(eq) else None
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}


def backtest(prices: pd.DataFrame, weights: dict, rebalance: str = "M", cost_bps: float = 10, benchmark=None,
             start=None, rf: float = 0.04) -> dict:
    """Daily backtest of a target-weight portfolio from closes.

    The portfolio is bought at the first close on/after ``start`` (all held tickers priced) and
    rebalanced back to the target weights at the last close of each month ("M") or calendar quarter
    ("Q"), or held ("none" = buy and hold). Trading costs = cost_bps / 1e4 x traded notional (sum of
    |delta w| x value), charged at each rebalance and on the initial purchase. Weights are normalised to
    sum 1 when all are non-negative. Short gaps (<= 5 days) in prices are forward-filled.
    ``benchmark`` is a price Series or a column name of ``prices``.

    Returns {"equity": ser (growth of 1), "benchmark": ser (growth of 1, aligned) , "drawdown": ser,
    "stats": {"cagr", "vol", "sharpe" ((mean x 252 - rf) / vol), "max_drawdown", "turnover_ann"
    (one-way: half the sum of |delta w| per year, excluding the initial purchase), "n_rebalances",
    "bench_cagr", "bench_vol", "bench_sharpe", "bench_max_drawdown"}, "weights", "warnings": [...]}.
    """
    warns: list[str] = []
    stats_keys = ["cagr", "vol", "sharpe", "max_drawdown", "turnover_ann", "n_rebalances", "bench_cagr", "bench_vol",
                  "bench_sharpe", "bench_max_drawdown"]
    out = {"equity": ser(None), "benchmark": ser(None), "drawdown": ser(None), "stats": {k: None for k in stats_keys},
           "weights": {}, "warnings": warns}
    rf = clean(rf) or 0.0
    if prices is None or not isinstance(prices, pd.DataFrame) or prices.empty:
        warns.append("no prices")
        return jsonable(out)
    w = pd.Series({str(k): clean(v) for k, v in (weights or {}).items()}, dtype=float).dropna()
    w = w[w != 0]
    cols = [t for t in w.index if t in prices.columns]
    if len(cols) < len(w):
        warns.append(f"no prices for {[t for t in w.index if t not in prices.columns]}; dropped")
    w = w[cols]
    if w.empty:
        warns.append("no holdings with prices")
        return jsonable(out)
    if (w >= 0).all() and w.sum() > 0:
        w = w / w.sum()
    P = prices[cols].apply(pd.to_numeric, errors="coerce")
    P = P[~P.index.duplicated(keep="last")].sort_index()
    P = P.where(P > 0).ffill(limit=5)
    if start is not None:
        P = P[P.index >= pd.Timestamp(start)]
    P = P.dropna(how="any")
    if len(P) < 2:
        warns.append("fewer than two dates with prices for all holdings")
        return jsonable(out)
    freq = str(rebalance).upper()[:1] if rebalance else "N"
    freq = freq if freq in ("M", "Q") else "N"
    X = P.to_numpy()
    tw = w.to_numpy()
    cost = (clean(cost_bps) or 0.0) / 1e4
    reb = _period_ends(P.index, freq)
    bounds = [0, *reb.tolist(), len(P) - 1]
    eq = np.empty(len(P))
    V = 1.0 - cost * float(np.abs(tw).sum())
    h = tw.copy()
    turnover = 0.0
    eq[0] = V
    for s, e in zip(bounds[:-1], bounds[1:]):
        if e <= s:
            continue
        rel = X[s:e + 1] / X[s]
        path = V * (rel @ h)
        eq[s:e + 1] = path
        V = float(path[-1])
        if e in reb:
            drift = h * rel[-1] / float(rel[-1] @ h)
            trade = float(np.abs(tw - drift).sum())
            turnover += trade
            V *= 1.0 - cost * trade
            eq[e] = V
            h = tw.copy()
        else:
            h = h * rel[-1] / float(rel[-1] @ h)
    equity = pd.Series(eq, index=P.index)
    years = (P.index[-1] - P.index[0]).days / 365.25
    st = _perf(equity, rf)
    st.update(turnover_ann=(0.5 * turnover / years) if years > 0 else None, n_rebalances=int(len(reb)))
    bench_s = None
    if benchmark is not None:
        b = prices[benchmark] if isinstance(benchmark, str) and benchmark in prices.columns else benchmark
        if isinstance(b, pd.Series):
            b = pd.to_numeric(b, errors="coerce")
            b = b[~b.index.duplicated(keep="last")].sort_index()
            b = b.where(b > 0).dropna()
            if isinstance(b.index, pd.DatetimeIndex) and b.index.tz is not None:
                b = b.tz_localize(None)
            b = b.reindex(P.index, method="ffill", limit=5)
            if b.notna().sum() > 1:
                b = b.dropna()
                bench_s = b / b.iloc[0]
                bs = _perf(bench_s, rf)
                st.update({f"bench_{k}": v for k, v in bs.items()})
        if bench_s is None:
            warns.append("benchmark unusable")
    for k in stats_keys:
        st.setdefault(k, None)
    dd = equity / equity.cummax() - 1.0
    out.update(equity=ser(equity), benchmark=ser(bench_s), drawdown=ser(dd), stats=st,
               weights=dict(zip(cols, tw.tolist())))
    return jsonable(out)


# =============================================================================== Black-Litterman
def black_litterman(cov: pd.DataFrame, market_weights: dict, views: dict, confidence=0.5, delta: float = 2.5,
                    tau: float = 0.05, rf: float = 0.04, max_weight: float = 0.35) -> dict:
    """Black-Litterman posterior returns and constrained weights with absolute views.

    Prior: equilibrium excess returns Pi = delta x Cov x w_mkt (reverse optimisation; market weights
    normalised to sum 1, missing tickers 0). Views: absolute annual expected (total) returns per ticker,
    e.g. analyst-target upside; P = picking rows, Q = view - rf. View uncertainty (Idzorek 2005,
    simplified closed form as in PyPortfolioOpt): omega_k = tau x p_k Cov p_k' x (1 - c_k) / c_k for
    confidence c_k in (0, 1] (c = 1: view held exactly; c = 0.5: omega = tau p Cov p', the He-Litterman
    default; c -> 0: view ignored), clamped to [1e-4, 1]. Posterior (He & Litterman 1999):
    mu_BL = Pi + tau Cov P' (P tau Cov P' + Omega)^-1 (Q - P Pi).
    Weights maximise w'mu_BL - delta/2 w'Cov w, long-only, sum 1, w <= max_weight (SLSQP); without views
    and binding caps this returns the market weights.

    Returns {"prior": {t: rf + Pi}, "posterior": {t: rf + mu_BL}, "weights": {t: w}, "market_weights",
    "views_used": {t: view}, "omega": {t: omega}, "tau", "delta", "warnings": [...]}.
    """
    warns: list[str] = []
    out = {"prior": {}, "posterior": {}, "weights": {}, "market_weights": {}, "views_used": {}, "omega": {},
           "tau": tau, "delta": delta, "warnings": warns}
    if cov is None or not isinstance(cov, pd.DataFrame) or cov.empty:
        warns.append("covariance missing")
        return jsonable(out)
    C = cov.astype(float)
    tickers = [t for t in C.index if t in C.columns and np.isfinite(C.loc[t, t]) and C.loc[t, t] > 0]
    C = C.loc[tickers, tickers]
    S = C.to_numpy()
    n = len(tickers)
    if n == 0:
        warns.append("covariance has no usable assets")
        return jsonable(out)
    rf = clean(rf) or 0.0
    tau = clean(tau) or 0.05
    delta = clean(delta) or 2.5
    mw = pd.Series({str(k): clean(v) for k, v in (market_weights or {}).items()}, dtype=float).reindex(tickers)
    if mw.isna().all() or mw.fillna(0).sum() <= 0:
        warns.append("market weights missing; equal weights used")
        mw = pd.Series(1.0 / n, index=tickers)
    mw = mw.fillna(0.0).clip(lower=0.0)
    mw = mw / mw.sum()
    pi = delta * S @ mw.to_numpy()
    vw = {str(k): clean(v) for k, v in (views or {}).items()}
    vt = [t for t in tickers if vw.get(t) is not None]
    ignored = [k for k, v in vw.items() if k not in tickers or v is None]
    if ignored:
        warns.append(f"views ignored (unknown ticker or invalid value): {ignored}")
    post = pi.copy()
    omega = {}
    if vt:
        P = np.zeros((len(vt), n))
        for i, t in enumerate(vt):
            P[i, tickers.index(t)] = 1.0
        Q = np.array([vw[t] - rf for t in vt])
        conf = {t: (confidence.get(t, 0.5) if isinstance(confidence, dict) else confidence) for t in vt}
        cvec = np.array([min(max(clean(conf[t]) if clean(conf[t]) is not None else 0.5, 1e-4), 1.0) for t in vt])
        tS = tau * S
        PSP = P @ tS @ P.T
        Om = np.diag(np.diag(PSP) * (1.0 - cvec) / cvec)
        post = pi + tS @ P.T @ np.linalg.solve(PSP + Om, Q - P @ pi)
        omega = dict(zip(vt, np.diag(Om).tolist()))
    else:
        warns.append("no usable views: posterior equals the prior")
    lo, hi = _bounds(n, 0.0, max_weight, warns)
    f = lambda w: -(w @ post) + 0.5 * delta * (w @ S @ w)  # noqa: E731
    g = lambda w: -post + delta * (S @ w)  # noqa: E731
    x0 = _cap(mw.to_numpy(), lo, hi)
    wts, ok = _slsqp(f, g, x0, lo, hi)
    if not ok:
        warns.append("optimiser did not fully converge")
    out.update(prior=dict(zip(tickers, (rf + pi).tolist())), posterior=dict(zip(tickers, (rf + post).tolist())),
               weights=dict(zip(tickers, wts.tolist())), market_weights=dict(zip(tickers, mw.tolist())),
               views_used={t: vw[t] for t in vt}, omega=omega, tau=tau, delta=delta)
    return jsonable(out)
