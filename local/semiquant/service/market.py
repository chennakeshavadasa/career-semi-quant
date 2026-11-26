"""Market dashboard: global strip, VIX term structure, yield curve, sector rotation,
semiconductor heatmap and breadth, movers, upcoming earnings, regime, news."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from ..analytics._util import clean, jsonable, safe
from ..data import yahoo
from ..universe import MARKET_GROUPS, SECTOR_ETFS, SEMIS, SEMI_TICKERS, VIX_TERM, YIELD_CURVE
from .common import memo, returns, universe_closes


def _spark(h: dict[str, pd.DataFrame], sym: str, n: int = 30) -> list[float]:
    d = h.get(sym)
    if d is None or d.empty:
        return []
    return [round(float(v), 6) for v in d["close"].tail(n).to_numpy()]


def _row(q: dict | None, sym: str, label: str, h: dict | None = None) -> dict:
    q = q or {}
    return {"symbol": sym, "label": label, "name": q.get("name"), "price": q.get("price"), "change": q.get("change"),
            "change_pct": q.get("change_pct"), "market_state": q.get("market_state"), "time": q.get("time"),
            "currency": q.get("currency"), "ext_price": q.get("ext_price"), "ext_change_pct": q.get("ext_change_pct"),
            "ext_label": q.get("ext_label"), "spark": _spark(h or {}, sym)}


def _ret(close: pd.Series, days: int) -> float | None:
    c = close.dropna()
    if len(c) <= days:
        return None
    return clean(c.iloc[-1] / c.iloc[-1 - days] - 1)


def _ytd(close: pd.Series) -> float | None:
    c = close.dropna()
    if c.empty:
        return None
    prior = c[c.index < pd.Timestamp(year=c.index[-1].year, month=1, day=1)]
    return clean(c.iloc[-1] / prior.iloc[-1] - 1) if len(prior) else None


def strip() -> dict:
    """Live quotes for every market group, the VIX curve and sector ETFs (fast; polled)."""
    syms = [s for g in MARKET_GROUPS.values() for s, _ in g] + [s for s, _ in VIX_TERM] + [s for s, _ in SECTOR_ETFS]
    q = yahoo.quotes(syms)
    h = memo("mkt:spark", 600, lambda: yahoo.history_many(syms, "3mo", "1d"))
    groups = {g: [_row(q.get(s), s, lbl, h) for s, lbl in items] for g, items in MARKET_GROUPS.items()}
    vix = [{"label": lbl, "symbol": s, "value": (q.get(s) or {}).get("price"), "change": (q.get(s) or {}).get("change")}
           for s, lbl in VIX_TERM]
    v30 = clean((q.get("^VIX") or {}).get("price"))
    v3m = clean((q.get("^VIX3M") or {}).get("price"))
    curve = [{"label": lbl, "symbol": s, "tenor": t, "value": (q.get(s) or {}).get("price"),
              "change": (q.get(s) or {}).get("change")} for s, lbl, t in YIELD_CURVE]
    y10 = clean((q.get("^TNX") or {}).get("price"))
    y3m = clean((q.get("^IRX") or {}).get("price"))
    sectors = []
    for s, lbl in SECTOR_ETFS:
        d = h.get(s)
        c = d["close"] if d is not None and not d.empty else pd.Series(dtype=float)
        sectors.append({"symbol": s, "label": lbl, "change_pct": (q.get(s) or {}).get("change_pct"),
                        "ret_5d": _ret(c, 5), "ret_1m": _ret(c, 21), "ret_3m": _ret(c, 62), "price": (q.get(s) or {}).get("price")})
    return jsonable({
        "groups": groups,
        "vix_term": vix,
        "vix_ratio": (v30 / v3m) if v30 and v3m else None,  # > 1 = backwardation (stress)
        "yield_curve": curve,
        "spread_10y_3m": (y10 - y3m) if y10 is not None and y3m is not None else None,
        "sectors": sectors,
        "status": yahoo.market_status("US"),
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


def heatmap() -> dict:
    """Semiconductor universe tiles: market cap (USD) and today's move, plus movers."""
    from .common import fx_to_usd

    q = yahoo.quotes(SEMI_TICKERS)
    fx = fx_to_usd([x.get("currency") for x in q.values()])
    tiles = []
    for t, name, sector, tier in SEMIS:
        if sector == "Market":
            continue
        x = q.get(t) or {}
        mc = clean(x.get("market_cap"))
        rate = fx.get(x.get("currency"), 1.0)
        tiles.append({"ticker": t, "name": name, "sector": sector, "tier": tier, "price": x.get("price"),
                      "change_pct": x.get("change_pct"), "ext_change_pct": x.get("ext_change_pct"),
                      "market_cap_usd": mc * rate if mc and rate and np.isfinite(rate) else None,
                      "currency": x.get("currency"), "market_state": x.get("market_state"),
                      "missing": not x or bool(x.get("inactive"))})
    live = [t for t in tiles if t["change_pct"] is not None and not t["missing"]]
    gainers = sorted(live, key=lambda t: t["change_pct"], reverse=True)[:6]
    losers = sorted(live, key=lambda t: t["change_pct"])[:6]
    by_sector = {}
    for t in live:
        if t["market_cap_usd"]:
            s = by_sector.setdefault(t["sector"], [0.0, 0.0])
            s[0] += t["market_cap_usd"] * t["change_pct"]
            s[1] += t["market_cap_usd"]
    sector_moves = sorted(({"sector": k, "change_pct": v[0] / v[1], "market_cap_usd": v[1]}
                           for k, v in by_sector.items() if v[1]), key=lambda r: r["change_pct"], reverse=True)
    return jsonable({"tiles": tiles, "gainers": gainers, "losers": losers, "sectors": sector_moves,
                     "advancers": sum(1 for t in live if t["change_pct"] > 0),
                     "decliners": sum(1 for t in live if t["change_pct"] < 0),
                     "missing": [t["ticker"] for t in tiles if t["missing"]]})


def breadth() -> dict:
    """Breadth and regime of the semiconductor universe (daily, cached 10 min)."""
    def build():
        from ..analytics import regimes, scoring

        c = universe_closes("2y")
        semis = c[[t for t in SEMI_TICKERS if t in c.columns]]
        b = safe(scoring.breadth, semis, default={}) or {}
        reg = {}
        if "SOXX" in c.columns:
            r = returns(yahoo.daily("SOXX", "10y")["close"].tail(1260))
            reg = safe(regimes.hmm_fit, r, 2, default={}) or {}
            reg = {k: reg.get(k) for k in ("states", "current_label", "current_probs", "transition", "n_states")}
        return jsonable({"breadth": b, "regime": reg})
    return memo("mkt:breadth", 600, build)


def movers() -> dict:
    """US-wide movers from Yahoo's predefined screens."""
    def pick(rows):
        return [{k: r.get(k) for k in ("symbol", "name", "price", "change_pct", "volume", "market_cap")} for r in rows[:8]]
    return jsonable({"gainers": pick(yahoo.screen("day_gainers", 10)), "losers": pick(yahoo.screen("day_losers", 10)),
                     "active": pick(yahoo.screen("most_actives", 10))})


def upcoming_earnings(days: int = 30) -> list[dict]:
    """Universe companies reporting within ``days`` (from live quotes)."""
    q = yahoo.quotes(SEMI_TICKERS)
    now = datetime.now(timezone.utc)
    out = []
    for t, name, sector, tier in SEMIS:
        x = q.get(t) or {}
        et = x.get("earnings_time")
        if not et:
            continue
        when = datetime.strptime(et, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if now - timedelta(days=1) <= when <= now + timedelta(days=days):
            out.append({"ticker": t, "name": name, "sector": sector, "time": et,
                        "estimated": x.get("earnings_estimated"), "days": (when - now).total_seconds() / 86400})
    return jsonable(sorted(out, key=lambda r: r["time"]))


def market_news() -> list[dict]:
    items = yahoo.search_news("semiconductor stocks", 12) + yahoo.search_news("stock market today", 12)
    seen, out = set(), []
    for n in sorted(items, key=lambda x: x.get("time") or "", reverse=True):
        if n["title"] in seen:
            continue
        seen.add(n["title"])
        out.append(n)
    return out[:16]


def overview() -> dict:
    """Everything the market page needs, in one call (the page also polls ``strip``)."""
    return {"strip": strip(), "heatmap": heatmap(), "breadth": breadth(), "movers": safe(movers, default={}),
            "earnings": safe(upcoming_earnings, default=[]), "news": safe(market_news, default=[])}
