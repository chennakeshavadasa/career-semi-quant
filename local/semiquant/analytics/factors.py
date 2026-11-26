"""Factor analytics: ETF style-factor and macro factor construction, multi-factor regression
with Newey-West standard errors and Euler risk attribution, rolling betas, peer correlations,
clustered correlation matrices and PCA market structure.

``build_factor_returns`` / ``build_macro_factors`` return **pandas DataFrames** (daily factor
returns / changes). The other public functions return JSON-ready dicts and never raise.
Returns are daily simple returns (fractions); annualisation uses ``periods_per_year`` (252).
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from ..universe import MACRO_FACTORS, STYLE_FACTORS
from ._util import iso, jsonable, periods_per_year
from .performance import _naive_index
from .risk import _factor_change, _factor_unit

__all__ = ["build_factor_returns", "build_macro_factors", "factor_regression", "rolling_betas", "peer_correlation",
           "correlation_matrix", "pca_structure"]


def _frame_numeric(df) -> pd.DataFrame:
    """Numeric copy with a sorted, unique, tz-naive DatetimeIndex (when the index is datetime-like)."""
    if isinstance(df, pd.Series):
        df = df.to_frame()
    d = df.apply(pd.to_numeric, errors="coerce")
    try:
        d.index = _naive_index(d.index)
    except Exception:  # noqa: BLE001
        pass
    if d.index.has_duplicates or not d.index.is_monotonic_increasing:
        d = d[~d.index.duplicated(keep="last")].sort_index()
    return d.replace([np.inf, -np.inf], np.nan)


def _col_returns(px: pd.DataFrame, ticker: str) -> pd.Series:
    """Simple returns of one price column on its own trading days (NaN rows dropped first;
    undefined when either price is <= 0)."""
    s = px[ticker].dropna()
    prev = s.shift(1)
    return (s / prev - 1.0).where((prev > 0) & (s > 0)).dropna()


def build_factor_returns(prices: pd.DataFrame, spec=STYLE_FACTORS) -> pd.DataFrame:
    """Daily style-factor returns from ETF closes: long return minus short return (``short`` None
    = long only), e.g. Semis = SOXX - SPY, Value = IWD - IWF. Each ETF's returns are computed on
    its own trading days; factors whose ETFs are missing from ``prices`` are skipped.

    Returns a DataFrame (columns = factor names in ``spec`` order, rows with no factor data
    dropped; a row can hold NaN for factors whose ETFs did not trade that day)."""
    try:
        px = _frame_numeric(prices)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    cache: dict[str, pd.Series] = {}

    def ret(t: str) -> pd.Series:
        if t not in cache:
            cache[t] = _col_returns(px, t)
        return cache[t]

    cols = {}
    for name, (long, short) in spec.items():
        if long not in px.columns or (short is not None and short not in px.columns):
            continue
        cols[name] = ret(long) if short is None else ret(long).sub(ret(short))
    if not cols:
        return pd.DataFrame(index=pd.DatetimeIndex([]))
    return pd.DataFrame(cols).dropna(how="all")


def build_macro_factors(prices: pd.DataFrame, spec=MACRO_FACTORS) -> pd.DataFrame:
    """Daily macro factor changes. kind "ret": simple return (pct change; undefined when a price is
    <= 0, e.g. WTI in April 2020); kind "chg": level change, where Yahoo yield indices (^TNX,
    ^IRX, ^FVX, ^TYX, quoted in percent) are converted to basis points (diff x 100) and other
    levels (e.g. ^VIX) are in points. Each series uses its own trading days.

    Returns a DataFrame with columns = ``spec`` keys (missing tickers skipped)."""
    try:
        px = _frame_numeric(prices)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    cols = {}
    for name, (ticker, kind) in spec.items():
        if ticker not in px.columns:
            continue
        s = px[ticker].dropna()
        if kind == "ret":
            cols[name] = _factor_change(s, "return").dropna()
        else:
            unit = "bp" if _factor_unit(ticker) == "bp" else "points"
            cols[name] = _factor_change(s, unit).dropna()
    if not cols:
        return pd.DataFrame(index=pd.DatetimeIndex([]))
    return pd.DataFrame(cols).dropna(how="all")


def _y(asset_returns) -> pd.Series:
    s = asset_returns.iloc[:, 0] if isinstance(asset_returns, pd.DataFrame) else pd.Series(asset_returns)
    s = pd.to_numeric(s, errors="coerce")
    try:
        s.index = _naive_index(s.index)
    except Exception:  # noqa: BLE001
        pass
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _aligned(asset_returns, factors) -> pd.DataFrame:
    y = _y(asset_returns).rename("__y__")
    f = _frame_numeric(factors)
    f = f.loc[:, [c for c in f.columns if f[c].notna().any()]]
    return pd.concat([y, f], axis=1, join="inner").dropna()


# --------------------------------------------------------------------------- regression
def factor_regression(asset_returns: pd.Series, factors: pd.DataFrame, nw_lags: int = 5) -> dict:
    """Multi-factor OLS of asset returns on factor returns with Newey-West (HAC, Bartlett kernel,
    ``nw_lags`` lags) standard errors (statsmodels), on common dates.

    Returns keys: ``n``, ``start``, ``end``, ``alpha_ann`` (intercept x ppy), ``alpha_t`` (HAC),
    ``r2``, ``adj_r2``, ``idio_vol_ann`` (residual std, df-adjusted, annualised),
    ``systematic_share`` (Var(B'F) / Var(r)), ``idio_share`` (1 - systematic_share), ``factors``
    [{"name", "beta", "t", "p" (HAC), "contribution" (Euler share of total variance:
    beta_i Cov(f_i, B'F) / Var(r); the contributions sum to systematic_share), "factor_vol_ann"}].
    """
    keys = ["n", "start", "end", "alpha_ann", "alpha_t", "r2", "adj_r2", "idio_vol_ann", "systematic_share",
            "idio_share"]
    out = {k: None for k in keys}
    out["factors"] = []
    try:
        import statsmodels.api as sm

        d = _aligned(asset_returns, factors)
        names = [c for c in d.columns if c != "__y__"]
        n, k = len(d), len(names)
        out["n"] = n
        if n:
            out["start"], out["end"] = iso(d.index[0]), iso(d.index[-1])
        if k == 0 or n < k + 10:
            out["error"] = "insufficient data"
            return jsonable(out)
        y = d["__y__"].to_numpy(dtype=float)
        F = d[names].to_numpy(dtype=float)
        var_y = float(np.var(y, ddof=1))
        if var_y < 1e-16:
            out["error"] = "zero variance in asset returns"
            return jsonable(out)
        ppy = periods_per_year(d.index)
        X = sm.add_constant(F, has_constant="add")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": int(nw_lags)})
        beta = np.asarray(fit.params, dtype=float)
        tv = np.asarray(fit.tvalues, dtype=float)
        pv = np.asarray(fit.pvalues, dtype=float)
        b = beta[1:]
        cov_f = np.atleast_2d(np.cov(F, rowvar=False, ddof=1))
        cov_fb = cov_f @ b
        sys_var = float(b @ cov_fb)
        out.update({
            "alpha_ann": beta[0] * ppy, "alpha_t": tv[0], "r2": float(fit.rsquared), "adj_r2": float(fit.rsquared_adj),
            "idio_vol_ann": math.sqrt(float(fit.mse_resid) * ppy),
            "systematic_share": sys_var / var_y, "idio_share": 1.0 - sys_var / var_y,
        })
        sd_f = np.sqrt(np.diag(cov_f))
        out["factors"] = [{"name": str(nm), "beta": b[i], "t": tv[i + 1], "p": pv[i + 1],
                           "contribution": b[i] * cov_fb[i] / var_y, "factor_vol_ann": sd_f[i] * math.sqrt(ppy)}
                          for i, nm in enumerate(names)]
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return jsonable(out)


def rolling_betas(asset_returns, factors, window: int = 126, step: int = 5) -> dict:
    """Rolling multivariate OLS betas (with intercept) over ``window`` bars, evaluated every
    ``step`` bars, anchored so that the last window ends on the last common date.

    Returns keys: ``window``, ``step``, ``t`` (ISO end date of each window), one list per factor
    name (betas), ``alpha_ann`` (annualised intercepts), ``r2``.
    """
    w, st = max(int(window), 3), max(int(step), 1)
    out: dict = {"window": w, "step": st, "t": []}
    try:
        from numpy.lib.stride_tricks import sliding_window_view

        d = _aligned(asset_returns, factors)
        names = [c for c in d.columns if c != "__y__"]
        for nm in names:
            out[str(nm)] = []
        out["alpha_ann"], out["r2"] = [], []
        n = len(d)
        if not names or n < max(w, len(names) + 3):
            return jsonable(out)
        ppy = periods_per_year(d.index)
        y = d["__y__"].to_numpy(dtype=float)
        X = np.column_stack([np.ones(n), d[names].to_numpy(dtype=float)])
        ends = np.arange(n - 1, w - 2, -st)[::-1]
        starts = ends - (w - 1)
        Xw = sliding_window_view(X, w, axis=0)[starts]  # (m, k+1, w)
        Yw = sliding_window_view(y, w)[starts]  # (m, w)
        XtX = Xw @ np.transpose(Xw, (0, 2, 1))
        Xty = (Xw @ Yw[..., None])[..., 0]
        B = (np.linalg.pinv(XtX) @ Xty[..., None])[..., 0]  # (m, k+1)
        fitted = np.einsum("mkw,mk->mw", Xw, B)
        resid = Yw - fitted
        sst = ((Yw - Yw.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            r2 = np.where(sst > 0, 1.0 - (resid ** 2).sum(axis=1) / sst, np.nan)
        out["t"] = [iso(t) for t in d.index[ends]]
        for i, nm in enumerate(names):
            out[str(nm)] = B[:, i + 1]
        out["alpha_ann"] = B[:, 0] * ppy
        out["r2"] = r2
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return jsonable(out)


# --------------------------------------------------------------------------- cross-section
def peer_correlation(returns: pd.DataFrame, ticker: str, top: int = 10, window: int = 252) -> dict:
    """Most correlated peers of ``ticker`` over the last ``window`` rows of a returns frame
    (pairwise complete observations, at least 20).

    Returns keys: ``ticker``, ``window``, ``peers`` [{"ticker", "corr", "beta", "n"}] sorted by
    correlation, highest first; ``beta`` is the ticker's beta to the peer (Cov(ticker, peer) /
    Var(peer), i.e. the hedge ratio in units of the peer).
    """
    out = {"ticker": ticker, "window": int(window), "peers": []}
    try:
        R = _frame_numeric(returns)
        if ticker not in R.columns:
            out["error"] = f"{ticker} not in returns"
            return jsonable(out)
        R = R.dropna(how="all").iloc[-int(window):]
        peers = []
        for col in R.columns:
            if col == ticker:
                continue
            pair = R[[ticker, col]].dropna()
            if len(pair) < 20:
                continue
            a, b = pair[ticker].to_numpy(), pair[col].to_numpy()
            va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
            if va < 1e-16 or vb < 1e-16:
                continue
            cov = float(np.cov(a, b, ddof=1)[0, 1])
            peers.append({"ticker": str(col), "corr": cov / math.sqrt(va * vb), "beta": cov / vb, "n": len(pair)})
        peers.sort(key=lambda p: -p["corr"])
        out["peers"] = peers[: max(int(top), 0)]
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return jsonable(out)


def correlation_matrix(returns: pd.DataFrame, cluster: bool = True) -> dict:
    """Pearson correlation matrix (pairwise complete observations, at least 20), optionally ordered
    by average-linkage hierarchical clustering on the distance 1 - rho with optimal leaf ordering
    (scipy). Undefined correlations (constant series) are None and treated as distance 1.

    Returns keys: ``tickers`` (row / column order), ``matrix`` (list of rows), ``avg_corr`` (mean
    off-diagonal correlation), ``n`` (rows of data).
    """
    out = {"tickers": [], "matrix": [], "avg_corr": None, "n": 0}
    try:
        R = _frame_numeric(returns).dropna(how="all")
        R = R.loc[:, [c for c in R.columns if R[c].notna().sum() >= 2]]
        out["n"] = len(R)
        if R.shape[1] == 0:
            return jsonable(out)
        C = R.corr(min_periods=20)
        cols = list(C.columns)
        order = list(range(len(cols)))
        if cluster and len(cols) >= 3:
            from scipy.cluster.hierarchy import leaves_list, linkage, optimal_leaf_ordering
            from scipy.spatial.distance import squareform

            D = (1.0 - C.to_numpy(dtype=float))
            D = np.where(np.isfinite(D), D, 1.0)
            D = np.clip((D + D.T) / 2.0, 0.0, 2.0)
            np.fill_diagonal(D, 0.0)
            cond = squareform(D, checks=False)
            Z = linkage(cond, method="average")
            order = list(leaves_list(optimal_leaf_ordering(Z, cond)))
        tick = [cols[i] for i in order]
        M = C.loc[tick, tick].to_numpy(dtype=float)
        off = M[~np.eye(len(tick), dtype=bool)]
        off = off[np.isfinite(off)]
        out.update({"tickers": [str(t) for t in tick], "matrix": M, "avg_corr": float(off.mean()) if off.size else None})
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return jsonable(out)


def pca_structure(returns: pd.DataFrame) -> dict:
    """Principal components of standardised returns (eigen-decomposition of the correlation
    matrix on dates where every series has data; constant series dropped).

    Returns keys: ``explained`` (variance share of the top 10 components), ``eigenvalues`` (top
    10), ``absorption_ratio`` (Kritzman et al. 2011: share of variance in the top round(N/5)
    components, at least 1), ``mp_edge`` (Marchenko-Pastur upper edge (1 + sqrt(N/T))^2 for
    Q = T/N and unit variance), ``n_signal`` (eigenvalues above the edge), ``pc1_loadings``
    ({ticker: loading}, signed so that the loadings sum to a positive number), ``n_obs`` (T),
    ``n_assets`` (N).
    """
    out = {"explained": [], "eigenvalues": [], "absorption_ratio": None, "mp_edge": None, "n_signal": None,
           "pc1_loadings": {}, "n_obs": 0, "n_assets": 0}
    try:
        R = _frame_numeric(returns).dropna(how="all")
        R = R.loc[:, [c for c in R.columns if R[c].notna().sum() >= 3]].dropna(how="any")
        if R.shape[0] >= 3:
            sd = R.std(ddof=1)
            R = R.loc[:, sd[sd > 1e-14].index]
        T, N = R.shape
        out["n_obs"], out["n_assets"] = int(T), int(N)
        if N < 2 or T < 3:
            return jsonable(out)
        Z = ((R - R.mean()) / R.std(ddof=1)).to_numpy(dtype=float)
        C = Z.T @ Z / (T - 1)
        vals, vecs = np.linalg.eigh(C)
        order = np.argsort(vals)[::-1]
        vals, vecs = np.clip(vals[order], 0.0, None), vecs[:, order]
        total = float(vals.sum())
        k = max(1, int(math.floor(N / 5.0 + 0.5)))
        edge = (1.0 + math.sqrt(N / T)) ** 2
        pc1 = vecs[:, 0]
        if pc1.sum() < 0:
            pc1 = -pc1
        out.update({"explained": vals[:10] / total, "eigenvalues": vals[:10],
                    "absorption_ratio": float(vals[:k].sum() / total), "mp_edge": edge,
                    "n_signal": int((vals > edge).sum()),
                    "pc1_loadings": {str(t): float(v) for t, v in zip(R.columns, pc1)}})
        return jsonable(out)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return jsonable(out)
