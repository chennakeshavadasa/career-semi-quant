"""Multi-ticker tools: compare, portfolio analytics & optimizer, calendar, search."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..analytics._util import clean, jsonable, safe, ser
from ..data import yahoo
from ..data.yahoo import DataError
from ..universe import ALL_META, UNIVERSES
from .common import RANGES, fx_to_usd, memo, returns


def _range_start(idx: pd.DatetimeIndex, rng: str) -> pd.Timestamp:
    spec = RANGES.get(rng, {"days": 366})
    last = idx[-1]
    if spec.get("ytd"):
        return pd.Timestamp(year=last.year, month=1, day=1)
    if spec.get("days"):
        return last - pd.Timedelta(days=spec["days"])
    return idx[0]


# ─── Compare ─────────────────────────────────────────────────────────────────

def compare(symbols: list[str], rng: str = "1Y", bench: str = "SPY") -> dict:
    from ..analytics import factors, performance

    syms = list(dict.fromkeys(yahoo.norm_symbol(s) for s in symbols if s))[:12]
    if not syms:
        raise DataError("Give at least one symbol")
    rng = rng.upper() if rng.upper() in RANGES else "1Y"
    if rng in ("1D", "5D", "1M"):
        rng = "3M"
    c = yahoo.closes(syms + [bench], "10y" if rng != "MAX" else "max", calendar=bench)
    start = _range_start(c.index, rng)
    w = c[c.index >= start]
    rf = yahoo.risk_free()
    q = yahoo.quotes(syms)
    series, stats, dd = {}, [], {}
    for s in syms + [bench]:
        if s not in w.columns or w[s].notna().sum() < 5:
            continue
        x = w[s].dropna()
        series[s] = ser(100 * x / x.iloc[0])
        dd[s] = ser(x / x.cummax() - 1)
        if s == bench:
            continue
        st = safe(performance.summary_stats, x, w[bench].dropna(), rf, default={}) or {}
        info = safe(yahoo.info, s, 6 * 3600, default={}) or {}
        tgt = clean(info.get("targetMeanPrice"))
        price = (q.get(s) or {}).get("price")
        stats.append({"symbol": s, "name": (q.get(s) or {}).get("name"), "price": price,
                      "change_pct": (q.get(s) or {}).get("change_pct"), **{k: st.get(k) for k in (
                          "total_return", "cagr", "vol", "sharpe", "sortino", "max_drawdown", "beta", "alpha",
                          "correlation", "information_ratio", "up_capture", "down_capture", "calmar")},
                      "pe": clean(info.get("trailingPE")), "fpe": clean(info.get("forwardPE")),
                      "ev_sales": clean(info.get("enterpriseToRevenue")), "gross_margin": clean(info.get("grossMargins")),
                      "operating_margin": clean(info.get("operatingMargins")), "rev_growth": clean(info.get("revenueGrowth")),
                      "target_upside": (tgt / price - 1) if tgt and price else None,
                      "market_cap": clean(info.get("marketCap"))})
    rets = w[[s for s in syms if s in w.columns]].pct_change().dropna(how="all")
    corr = safe(factors.correlation_matrix, rets, False, default=None) if rets.shape[1] > 1 else None
    return jsonable({"symbols": syms, "bench": bench, "range": rng, "start": str(start.date()),
                     "normalized": series, "drawdowns": dd, "stats": stats, "correlation": corr})


# ─── Portfolio ───────────────────────────────────────────────────────────────

def portfolio(p: dict) -> dict:
    """Live valuation, risk decomposition, stress tests, optimizers and a backtest."""
    from ..analytics import factors, montecarlo, portfolio as pf, risk

    holdings = [h for h in (p.get("holdings") or []) if h.get("ticker") and clean(h.get("shares"))]
    if not holdings:
        raise DataError("Add at least one holding (ticker and number of shares).")
    bench = yahoo.norm_symbol(p.get("benchmark") or "SPY")
    max_w = float(p.get("max_weight") or 0.35)
    tick = list(dict.fromkeys(yahoo.norm_symbol(h["ticker"]) for h in holdings))
    q = yahoo.quotes(tick + [bench])
    fx = fx_to_usd([x.get("currency") for x in q.values()])
    rows, total = [], 0.0
    for h in holdings:
        t = yahoo.norm_symbol(h["ticker"])
        x = q.get(t) or {}
        px, rate = clean(x.get("price")), fx.get(x.get("currency"), 1.0)
        sh = float(h["shares"])
        val = px * sh * rate if px and rate and np.isfinite(rate) else None
        day = (x.get("change") or 0) * sh * rate if val is not None else None
        cost = clean(h.get("cost"))
        rows.append({"ticker": t, "name": x.get("name"), "shares": sh, "price": px, "currency": x.get("currency"),
                     "value": val, "day_change": day, "day_change_pct": x.get("change_pct"), "cost": cost,
                     "pnl": (val - cost * sh * rate) if val is not None and cost else None,
                     "pnl_pct": (px / cost - 1) if px and cost else None, "missing": not x})
        total += val or 0.0
    cash = float(p.get("cash") or 0.0)
    nav = total + cash
    for r in rows:
        r["weight"] = (r["value"] / total) if r["value"] and total else 0.0
    weights = {r["ticker"]: r["weight"] for r in rows if r["weight"] > 0}
    if not weights:
        raise DataError("None of the holdings has a live price.")
    c = yahoo.closes(list(weights) + [bench], "5y", calendar=bench)
    rets = c.pct_change().iloc[1:]
    hold_rets = rets[list(weights)].dropna(how="any").tail(756)
    rf = yahoo.risk_free()
    out = {"name": p.get("name") or "Portfolio", "benchmark": bench, "rows": rows, "total": total, "cash": cash,
           "nav": nav, "day_change": sum(r["day_change"] or 0 for r in rows), "weights": weights, "rf": rf,
           "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out["day_change_pct"] = out["day_change"] / (total - out["day_change"]) if total else None
    out["risk"] = safe(pf.portfolio_risk, weights, hold_rets.tail(504), rets[bench].tail(504), rf, nav, default=None)
    out["correlation"] = safe(factors.correlation_matrix, hold_rets.tail(252), True, default=None) if len(weights) > 1 else None
    if len(weights) > 1:
        out["optimizers"] = {m: safe(pf.optimize, hold_rets, m, max_w, 0.0, rf, default=None)
                             for m in ("equal", "inverse_vol", "min_var", "max_sharpe", "erc", "hrp", "max_div")}
        out["frontier"] = safe(pf.efficient_frontier, hold_rets, 30, max_w, rf, default=None)
    out["backtest"] = safe(pf.backtest, c[list(weights)].dropna(how="any"), weights, "M", 10, c[bench], default=None)
    # Constant-weight NAV on each holding's full history, for crisis replays and Monte Carlo.
    try:
        hmax = yahoo.daily_many(list(weights) + ["SPY", "SOXX"], "max")
        rmax = pd.DataFrame({t: hmax[t]["close"] for t in weights if t in hmax}).pct_change()
        rmax = rmax.dropna(how="any")
        nav_series = (1 + (rmax * pd.Series(weights)).sum(axis=1)).cumprod()
        out["stress"] = safe(risk.stress_test, nav_series, {k: hmax[k]["close"] for k in ("SPY", "SOXX") if k in hmax},
                             default=None)
        out["montecarlo"] = safe(montecarlo.simulate, nav_series.tail(1260) * nav, 252, 10000, "bootstrap",
                                 "historical", default=None)
        out["history_start"] = str(nav_series.index[0].date()) if len(nav_series) else None
    except Exception as exc:  # noqa: BLE001
        out["stress_error"] = str(exc)
    return jsonable(out)


# ─── Calendar & search ───────────────────────────────────────────────────────

def calendar() -> dict:
    from .market import upcoming_earnings

    def build():
        ec = yahoo.earnings_calendar(21, 100, most_active=False)
        uni = set(ALL_META)
        for r in ec:
            r["in_universe"] = r.get("Symbol") in uni
        return {"earnings": ec, "economic": yahoo.economic_calendar(10, 100)}

    data = memo("calendar", 1800, build)
    return jsonable({**data, "universe": upcoming_earnings(90)})


def search(qs: str) -> list[dict]:
    s = (qs or "").strip()
    if not s:
        return []
    up, low = s.upper(), s.lower()
    hits = [m for t, m in ALL_META.items() if t.startswith(up) or low in (m["name"] or "").lower()]
    hits.sort(key=lambda m: (m["ticker"] != up, not m["ticker"].startswith(up), len(m["ticker"])))
    local = [{"symbol": m["ticker"], "name": m["name"], "type": "ETF" if m["universe"] == "etfs" else "Equity",
              "exchange": None, "sector": m["sector"], "universe": UNIVERSES[m["universe"]]["label"]} for m in hits[:6]]
    seen = {x["symbol"] for x in local}
    remote = [x for x in yahoo.search(s, 8) if x["symbol"] not in seen]
    return jsonable(local + remote)[:12]
