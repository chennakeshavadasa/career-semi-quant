"""Single-ticker workspace: overview, chart, risk, volatility, tail risk, options,
fundamentals, analysts & earnings, ownership, factors & regimes, events, RSU/offer."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..analytics._util import clean, jsonable, records, safe, ser
from ..data import yahoo
from ..data.yahoo import DataError, frame_rows
from ..universe import ALL_META, FACTOR_ETFS, UNIVERSES, home_universe, universe_meta
from .common import RANGES, bench_closes, memo, meta, returns, slice_range, time_axis, universe_closes

NY = ZoneInfo("America/New_York")


def _quote(sym: str) -> dict:
    q = yahoo.quote(sym)
    if not q or q.get("price") is None:
        raise DataError(f"No live quote for '{sym}'. Check the symbol (Yahoo format, e.g. 005930.KS, 8035.T, BTC-USD).")
    return q


def _daily(sym: str, period: str = "max") -> pd.DataFrame:
    df = yahoo.daily(sym, period)
    if df is None or df.empty:
        raise DataError(f"No price history for {sym}")
    return df


def _epoch_iso(v) -> str | None:
    v = clean(v)
    if not v:
        return None
    return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%d")


def _div_yield(info: dict, q: dict) -> float:
    # yfinance >= 0.2.5x reports info["dividendYield"] in percent (0.03 = 0.03 %).
    dy = clean(info.get("dividendYield"))
    if dy is not None:
        return dy / 100.0
    dy = clean(info.get("trailingAnnualDividendYield")) or clean(q.get("dividend_yield"))
    return dy or 0.0


# ─── Overview ────────────────────────────────────────────────────────────────

def key_stats(info: dict, q: dict) -> dict:
    g = info.get
    de = clean(g("debtToEquity"))
    return {
        "market_cap": clean(g("marketCap")) or q.get("market_cap"), "enterprise_value": clean(g("enterpriseValue")),
        "pe": clean(g("trailingPE")) or q.get("pe"), "fpe": clean(g("forwardPE")) or q.get("fpe"),
        "peg": clean(g("trailingPegRatio")) or clean(g("pegRatio")), "ps": clean(g("priceToSalesTrailing12Months")),
        "pb": clean(g("priceToBook")) or q.get("pb"), "ev_revenue": clean(g("enterpriseToRevenue")),
        "ev_ebitda": clean(g("enterpriseToEbitda")), "beta": clean(g("beta")),
        "eps_ttm": clean(g("trailingEps")) or q.get("eps_ttm"), "eps_fwd": clean(g("forwardEps")) or q.get("eps_fwd"),
        "revenue": clean(g("totalRevenue")), "revenue_growth": clean(g("revenueGrowth")),
        "earnings_growth": clean(g("earningsGrowth")), "gross_margin": clean(g("grossMargins")),
        "operating_margin": clean(g("operatingMargins")), "net_margin": clean(g("profitMargins")),
        "ebitda_margin": clean(g("ebitdaMargins")), "roe": clean(g("returnOnEquity")), "roa": clean(g("returnOnAssets")),
        "cash": clean(g("totalCash")), "debt": clean(g("totalDebt")), "fcf": clean(g("freeCashflow")),
        "ocf": clean(g("operatingCashflow")), "current_ratio": clean(g("currentRatio")),
        "debt_to_equity": de / 100.0 if de is not None else None,
        "dividend_yield": _div_yield(info, q) if (g("dividendYield") or q.get("dividend_yield")) else None,
        "payout_ratio": clean(g("payoutRatio")), "ex_dividend": _epoch_iso(g("exDividendDate")),
        "shares_out": clean(g("sharesOutstanding")) or q.get("shares_out"), "float": clean(g("floatShares")),
        "short_pct_float": clean(g("shortPercentOfFloat")), "short_ratio": clean(g("shortRatio")),
        "shares_short": clean(g("sharesShort")), "shares_short_prior": clean(g("sharesShortPriorMonth")),
        "insiders": clean(g("heldPercentInsiders")), "institutions": clean(g("heldPercentInstitutions")),
        "avg_volume": clean(g("averageVolume")) or q.get("avg_volume_3m"), "avg_volume_10d": q.get("avg_volume_10d"),
        "change_52w": clean(g("52WeekChange")) or q.get("change_52w"), "sp500_change_52w": clean(g("SandP52WeekChange")),
        "target_mean": clean(g("targetMeanPrice")), "target_median": clean(g("targetMedianPrice")),
        "target_high": clean(g("targetHighPrice")), "target_low": clean(g("targetLowPrice")),
        "rec_mean": clean(g("recommendationMean")), "rec_key": g("recommendationKey"),
        "n_analysts": clean(g("numberOfAnalystOpinions")),
        "upside": (clean(g("targetMeanPrice")) / q["price"] - 1) if clean(g("targetMeanPrice")) and q.get("price") else None,
    }


def profile(info: dict) -> dict:
    g = info.get
    officers = [{"name": o.get("name"), "title": o.get("title"), "pay": clean(o.get("totalPay")), "age": o.get("age")}
                for o in (g("companyOfficers") or [])[:6]]
    return {"name": g("longName") or g("shortName"), "summary": g("longBusinessSummary"), "sector": g("sector"),
            "industry": g("industry"), "website": g("website"), "ir_website": g("irWebsite"),
            "employees": g("fullTimeEmployees"), "country": g("country"), "city": g("city"), "state": g("state"),
            "exchange": g("fullExchangeName") or g("exchange"), "currency": g("currency"),
            "financial_currency": g("financialCurrency"), "quote_type": g("quoteType"), "officers": officers,
            "fund_family": g("fundFamily"), "category": g("category"), "total_assets": clean(g("totalAssets")),
            "expense_ratio": clean(g("netExpenseRatio")), "ipo": _epoch_iso(g("firstTradeDateEpochUtc"))}


def _overview_heavy(sym: str) -> dict:
    from ..analytics import performance, risk, technicals

    df = _daily(sym)
    close = df["close"]
    b = bench_closes("max", ("SPY", "SOXX"))
    rf = yahoo.risk_free()
    info = safe(yahoo.info, sym, default={}) or {}
    bench = {k: v for k, v in (("S&P 500 (SPY)", b.get("SPY")), ("Semis (SOXX)", b.get("SOXX"))) if v is not None and k}
    out = {
        "profile": profile(info),
        "info_ok": bool(info),
        "returns": safe(performance.returns_table, close, bench, default=None),
        "stats_1y": safe(performance.summary_stats, close.tail(253), b.get("SPY"), rf, default=None),
        "signals": safe(technicals.signal_summary, df.tail(500), default=None),
        "trend": safe(technicals.trend_state, close, default=None),
        "levels": safe(technicals.levels, df.tail(400), default=None),
        "tail": safe(risk.tail_risk_summary, close.tail(1260), default=None),
        "spark_1y": [round(float(v), 4) for v in close.tail(252).to_numpy()],
        "rf": rf,
    }
    return jsonable(out)


def overview(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)
    q = _quote(sym)
    heavy = memo(f"ov:{sym}", 60, lambda: _overview_heavy(sym))
    info = safe(yahoo.info, sym, default={}) or {}
    cal = safe(yahoo.calendar, sym, default={}) or {}
    nxt = None
    if cal.get("Earnings Date"):
        ed = cal["Earnings Date"]
        nxt = {"date": str(ed[0]) if isinstance(ed, list) and ed else str(ed),
               "eps_avg": clean(cal.get("Earnings Average")), "eps_low": clean(cal.get("Earnings Low")),
               "eps_high": clean(cal.get("Earnings High")), "rev_avg": clean(cal.get("Revenue Average"))}
    if q.get("earnings_time"):
        nxt = {**(nxt or {}), "time": q["earnings_time"], "estimated": q.get("earnings_estimated")}
    return jsonable({"symbol": sym, "quote": q, "meta": meta(sym), "key_stats": key_stats(info, q),
                     "next_earnings": nxt, "news": yahoo.news(sym, 12), **heavy})


def score(sym: str) -> dict:
    """Composite quant score vs the semiconductor universe (needs universe fundamentals,
    so it is served separately and the overview never waits for it)."""
    from .screener import score_for

    sym = yahoo.norm_symbol(sym)
    return memo(f"score:{sym}", 120, lambda: jsonable({"symbol": sym, "score": score_for(sym)}))


def next_earnings(sym: str, q: dict | None = None) -> str | None:
    """Next earnings date (YYYY-MM-DD): calendar first, then future rows of the earnings dates."""
    today = datetime.now(NY).strftime("%Y-%m-%d")
    cal = safe(yahoo.calendar, sym, default={}) or {}
    ed = cal.get("Earnings Date")
    for d in (ed if isinstance(ed, list) else [ed]):
        if d is not None and str(d)[:10] >= today:
            return str(d)[:10]
    q = q or {}
    if (q.get("earnings_time") or "")[:10] >= today:
        return q["earnings_time"][:10]
    df = safe(yahoo.earnings_dates, sym, default=None)
    if isinstance(df, pd.DataFrame) and not df.empty:
        fut = sorted(pd.Timestamp(i).strftime("%Y-%m-%d") for i in df.index if pd.Timestamp(i).strftime("%Y-%m-%d") >= today)
        if fut:
            return fut[0]
    return None


# ─── Chart ───────────────────────────────────────────────────────────────────

DEFAULT_IND = ("sma20", "sma50", "sma200", "bb", "vwap", "rsi", "macd")


def _indicators(full: pd.DataFrame, idx: pd.DatetimeIndex, names: list[str]) -> dict:
    from ..analytics import technicals as ta

    out = {}
    c = full["close"]

    def put(name, obj):
        if isinstance(obj, pd.Series):
            out[name] = {"v": [clean(v) for v in obj.reindex(idx).to_numpy()]}
        elif isinstance(obj, pd.DataFrame):
            o = obj.reindex(idx)
            out[name] = {str(col): [clean(v) for v in o[col].to_numpy()] for col in o.columns}

    for n in names:
        n = n.strip().lower()
        try:
            if n.startswith("sma") and n[3:].isdigit():
                put(n, ta.sma(c, int(n[3:])))
            elif n.startswith("ema") and n[3:].isdigit():
                put(n, ta.ema(c, int(n[3:])))
            elif n == "bb":
                put(n, ta.bollinger(c, 20, 2)[["upper", "mid", "lower"]])
            elif n == "vwap":
                put(n, ta.vwap(full))
            elif n == "rsi":
                put(n, ta.rsi(c, 14))
            elif n == "macd":
                put(n, ta.macd(c, 12, 26, 9))
            elif n == "atr":
                put(n, ta.atr(full, 14))
            elif n == "adx":
                put(n, ta.adx(full, 14))
            elif n == "stoch":
                put(n, ta.stochastic(full, 14, 3))
            elif n == "obv":
                put(n, ta.obv(full))
            elif n == "ichimoku":
                put(n, ta.ichimoku(full))
            elif n == "supertrend":
                put(n, ta.supertrend(full, 10, 3))
            elif n == "donchian":
                put(n, ta.donchian(full, 20))
            elif n == "keltner":
                put(n, ta.keltner(full, 20, 2))
            elif n == "cci":
                put(n, ta.cci(full, 20))
            elif n == "mfi":
                put(n, ta.mfi(full, 14))
        except Exception:  # noqa: BLE001 - one bad indicator never breaks the chart
            continue
    return out


def chart(sym: str, rng: str = "6M", ind: list[str] | None = None) -> dict:
    sym = yahoo.norm_symbol(sym)
    rng = rng.upper() if rng and rng.upper() in RANGES else "6M"
    spec = RANGES[rng]
    names = list(ind) if ind is not None else list(DEFAULT_IND)
    q = yahoo.quote(sym) or {}
    if "period" in spec and spec.get("interval") != "1wk":
        df = full = yahoo.history(sym, spec["period"], spec["interval"], spec.get("prepost", False))
        if rng == "1D":  # earlier sessions as warm-up so intraday indicators start valid
            prev = safe(yahoo.history, sym, "5d", "1m", True, default=None)
            if prev is not None and not prev.empty:
                full = pd.concat([prev[prev.index < df.index[0]], df])
        intraday = True
    elif spec.get("interval") == "1wk":
        full = df = yahoo.history(sym, "max", "1wk")
        intraday = False
    else:
        full = _daily(sym)
        df = slice_range(full, rng)
        full = full.tail(len(df) + 400)  # warm-up for long averages without crunching decades
        intraday = False
    if df is None or df.empty:
        raise DataError(f"No chart data for {sym} ({rng})")
    bars = {"t": time_axis(df.index, intraday), "o": [clean(v) for v in df["open"]], "h": [clean(v) for v in df["high"]],
            "l": [clean(v) for v in df["low"]], "c": [clean(v) for v in df["close"]],
            "v": [clean(v) for v in df["volume"]] if "volume" in df else []}
    session = None
    if intraday and (q.get("tz") or "").startswith("America/"):
        session = {"open": "09:30", "close": "16:00"}
    return jsonable({"symbol": sym, "range": rng, "interval": spec.get("interval", "1d"), "intraday": intraday,
                     "tz": q.get("tz"), "currency": q.get("currency"), "prev_close": q.get("prev_close"),
                     "session": session, "bars": bars, "indicators": _indicators(full, df.index, names),
                     "last": {k: q.get(k) for k in ("price", "change", "change_pct", "time", "market_state",
                                                    "ext_price", "ext_change_pct", "ext_label")}})


# ─── Risk / volatility / tail ────────────────────────────────────────────────

def _thin_dd(dd: dict | None, max_points: int = 3000) -> dict | None:
    """Keep long underwater curves light: every k-th point plus the deepest ones."""
    if not dd or not (dd.get("underwater") or {}).get("t"):
        return dd
    t, v = dd["underwater"]["t"], dd["underwater"]["v"]
    if len(t) <= max_points:
        return dd
    k = -(-len(t) // max_points)
    keep = set(range(0, len(t), k)) | {len(t) - 1}
    vals = [x if x is not None else 0 for x in v]
    for i in sorted(range(len(vals)), key=lambda i: vals[i])[:50]:
        keep.add(i)
    idx = sorted(keep)
    return {**dd, "underwater": {"t": [t[i] for i in idx], "v": [v[i] for i in idx]}}


def risk(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import performance as pf

        df = _daily(sym)
        close = df["close"]
        b = bench_closes("max", ("SPY", "SOXX", "QQQ"))
        rf = yahoo.risk_free()
        spy, soxx = b.get("SPY"), b.get("SOXX")
        stats = {}
        for w, n in (("1Y", 252), ("3Y", 756), ("5Y", 1260), ("10Y", 2520), ("Max", None)):
            c = close.tail(n + 1) if n else close
            if len(c) < 30 or (n and len(close) < n * 0.9) or (not n and len(close) <= 2600):
                continue
            stats[w] = {"vs_spy": safe(pf.summary_stats, c, spy, rf, default=None),
                        "vs_soxx": safe(pf.summary_stats, c, soxx, rf, default=None)}
        bench = {k: v for k, v in (("S&P 500 (SPY)", spy), ("Semis (SOXX)", soxx), ("Nasdaq 100 (QQQ)", b.get("QQQ")))
                 if v is not None}
        return jsonable({
            "symbol": sym, "rf": rf, "stats": stats,
            "returns": safe(pf.returns_table, close, bench, default=None),
            "drawdowns": _thin_dd(safe(pf.drawdowns, close, 8, default=None)),
            "rolling_spy": safe(pf.rolling_metrics, close.tail(1323), spy, 63, default=None),
            "rolling_soxx": safe(pf.rolling_metrics, close.tail(1323), soxx, 63, default=None),
            "distribution": safe(pf.return_distribution, close.tail(1260), 60, 1, default=None),
            "distribution_week": safe(pf.return_distribution, close.tail(1260), 40, 5, default=None),
            "monthly": safe(pf.monthly_returns, close[close.index >= close.index[-1] - pd.DateOffset(years=15)], default=None),
        })

    return memo(f"risk:{sym}", 600, build)


def _atm_iv_30d(sym: str) -> float | None:
    """30-day ATM implied vol from the option term structure (None if no options)."""
    o = safe(options, sym, None, False, default=None)
    if not o or not o.get("available"):
        return None
    return o.get("atm_iv_30d")


def volatility(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import volatility as vol

        df = _daily(sym)
        atm = safe(_atm_iv_30d, sym, default=None)
        ew = safe(vol.ewma_vol, df["close"], 0.94, default=None)
        return jsonable({
            "symbol": sym,
            "summary": safe(vol.vol_summary, df, atm, default=None),
            "realized": safe(vol.realized_vol_summary, df.tail(1600), default=None),
            "cone": safe(vol.vol_cone, df.tail(1260), default=None),
            "garch": safe(vol.garch, df["close"], "gjr", "t", 63, 10, default=None),
            "ewma": ser(ew.tail(756)) if isinstance(ew, pd.Series) else None,
            "atm_iv_30d": atm,
        })

    return memo(f"vol:{sym}", 600, build)


def tail(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import risk as rk

        df = _daily(sym)
        r = returns(df["close"])
        full_close = df["close"]  # _daily is already the full history
        bmax = {}
        for s in ("SPY", "SOXX"):
            h = safe(yahoo.history, s, "max", "1d", default=None)
            if h is not None and not h.empty:
                bmax[s] = yahoo.patch_live(h, yahoo.quote(s))["close"]
        levels = yahoo.closes(["SPY", "SOXX", "^TNX", "^VIX", "DX-Y.NYB", "CL=F"], "2y", calendar="SPY")
        return jsonable({
            "symbol": sym,
            "var_es": safe(rk.var_es, r.tail(1260), (0.95, 0.99), (1, 10), default=None),
            "backtests": [x for x in (safe(rk.var_backtest, r.tail(2520), 0.99, 500, m, default=None)
                                      for m in ("historical", "normal", "ewma")) if x],
            "stress": safe(rk.stress_test, full_close, bmax, default=None),
            "shocks": safe(rk.hypothetical_shocks, r.tail(504), levels, None, default=None),
            "summary": safe(rk.tail_risk_summary, df["close"].tail(1260), default=None),
            "first_date": str(full_close.index[0].date()) if len(full_close) else None,
        })

    return memo(f"tail:{sym}", 600, build)


# ─── Options ─────────────────────────────────────────────────────────────────

def _now_ny() -> datetime:
    return datetime.now(NY).replace(tzinfo=None)


def _pick_term_expiries(exps: list[str], asof: datetime, n: int = 12) -> list[str]:
    dte = [(e, (pd.Timestamp(e) - pd.Timestamp(asof.date())).days) for e in exps]
    near = [e for e, d in dte if d <= 60][:7]
    far = [e for e, d in dte if d > 60]
    step = max(1, len(far) // max(1, n - len(near)))
    return near + far[::step][: max(0, n - len(near))]


def options(sym: str, expiry: str | None = None, full: bool = True) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import options as op
        from ..analytics import volatility as vol

        exps = yahoo.option_expiries(sym)
        if not exps:
            return {"symbol": sym, "available": False, "message": "No listed options for this symbol on Yahoo."}
        q = _quote(sym)
        info = safe(yahoo.info, sym, default={}) or {}
        spot = float(q["price"])
        r = yahoo.risk_free()
        qy = _div_yield(info, q)
        asof = _now_ny()
        dtes = {e: (pd.Timestamp(e) - pd.Timestamp(asof.date())).days for e in exps}
        sel = expiry if expiry in exps else next((e for e in exps if dtes[e] >= 7), exps[0])
        term_exps = _pick_term_expiries(exps, asof)
        if sel not in term_exps:
            term_exps.append(sel)
        chains = yahoo.option_chains(sym, term_exps)
        pairs = {e: (c["calls"], c["puts"]) for e, c in chains.items()}
        ch = chains.get(sel) or yahoo.option_chain(sym, sel)
        earn = next_earnings(sym, q)
        ts = safe(op.term_structure, pairs, spot, asof, r, qy, earn, default=None)
        atm30 = None
        if ts and ts.get("rows"):
            pts = [(row["dte"], row["atm_iv"]) for row in ts["rows"] if row.get("atm_iv") and row.get("dte") is not None]
            if pts:
                d, v = zip(*sorted(pts))
                atm30 = float(np.interp(30, d, v))
        df = safe(_daily, sym, default=None)
        rv21 = None
        if df is not None:
            rvs = safe(vol.realized_vol, df.tail(300), 21, "yang_zhang", default=None)
            rv21 = clean(rvs.dropna().iloc[-1]) if isinstance(rvs, pd.Series) and rvs.notna().any() else None
        out = {
            "symbol": sym, "available": True, "spot": spot, "rate": r, "dividend_yield": qy,
            "asof": asof.strftime("%Y-%m-%dT%H:%M:%S"), "market_state": q.get("market_state"),
            "expiries": [{"expiry": e, "dte": dtes[e]} for e in exps], "expiry": sel,
            "chain": safe(op.chain_analytics, ch["calls"], ch["puts"], spot, sel, asof, r, qy, default=None),
            "term": ts, "atm_iv_30d": atm30, "rv_21d": rv21,
            "vrp": (atm30 - rv21) if atm30 is not None and rv21 is not None else None,
            "earnings_date": earn,
        }
        if full:
            out["surface"] = safe(op.iv_surface, pairs, spot, asof, r, qy, default=None)
        return jsonable(out)

    return memo(f"opt:{sym}:{expiry}:{int(full)}", 120, build)


# ─── Fundamentals ────────────────────────────────────────────────────────────

def fundamentals(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import fundamentals as fa

        info = safe(yahoo.info, sym, default={}) or {}
        st = safe(yahoo.statements, sym, default=None)
        if not st:
            return {"symbol": sym, "available": False, "message": "No financial statements on Yahoo for this symbol."}
        q = yahoo.quote(sym) or {}
        summary = safe(fa.fundamental_summary, st, info, yahoo.risk_free(), default=None) or {}
        vh = safe(yahoo.valuation_history, sym, default=None)
        valuation_hist = None
        if isinstance(vh, pd.DataFrame) and not vh.empty:
            valuation_hist = {"columns": [str(c) for c in vh.columns],
                              "rows": [{"metric": str(i), "values": [clean(v) for v in r.to_numpy()]} for i, r in vh.iterrows()]}
        # Sector peers from live quotes (cheap): relative valuation context.
        hu = home_universe(sym)
        um = universe_meta(hu) if hu else {}
        m = um.get(sym)
        peers = []
        if m:
            sec = [t for t, x in um.items() if x["sector"] == m["sector"] and t != sym][:25]
            pq = yahoo.quotes([sym] + sec)
            for t in [sym] + sec:
                x = pq.get(t) or {}
                peers.append({"ticker": t, "name": um.get(t, {}).get("name"), "pe": x.get("pe"), "fpe": x.get("fpe"),
                              "pb": x.get("pb"), "market_cap": x.get("market_cap"), "currency": x.get("currency"),
                              "change_52w": x.get("change_52w"), "dividend_yield": x.get("dividend_yield"), "self": t == sym})
        return jsonable({"symbol": sym, "available": True, **summary, "valuation_history": valuation_hist,
                         "peers": peers, "sector": (m or {}).get("sector"), "currency": q.get("currency"),
                         "financial_currency": info.get("financialCurrency")})

    return memo(f"fund:{sym}", 3600, build)


# ─── Analysts & earnings ─────────────────────────────────────────────────────

def _est_table(df) -> list[dict]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    labels = {"0q": "Current qtr", "+1q": "Next qtr", "0y": "Current year", "+1y": "Next year"}
    rows = []
    for idx, r in df.iterrows():
        d = {"period": str(idx), "label": labels.get(str(idx), str(idx))}
        for k, v in r.items():
            d[str(k)] = v if isinstance(v, str) else clean(v)
        rows.append(d)
    return rows


def earnings_study(sym: str) -> dict | None:
    def build():
        from ..analytics import earnings as er

        ed = yahoo.earnings_dates(sym, 40)
        if ed is None or ed.empty:
            return None
        df = _daily(sym)
        spy = bench_closes("max", ("SPY",)).get("SPY")
        return safe(er.event_study, df["close"], spy, ed, default=None)

    return memo(f"estudy:{sym}", 3600, build)


def analysts(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import earnings as er

        a = yahoo.analysts(sym) or {}
        q = yahoo.quote(sym) or {}
        price = q.get("price")
        pt = a.get("price_targets") or {}
        targets = {k: clean(v) for k, v in pt.items()} if isinstance(pt, dict) else {}
        if price and targets.get("mean"):
            targets["upside_mean"] = targets["mean"] / price - 1
        if price and targets.get("median"):
            targets["upside_median"] = targets["median"] / price - 1
        if price and targets.get("high"):
            targets["upside_high"] = targets["high"] / price - 1
        if price and targets.get("low"):
            targets["upside_low"] = targets["low"] / price - 1
        recs = frame_rows(a.get("recommendations"))
        up = a.get("upgrades")
        upgrades = frame_rows(up.head(60)) if isinstance(up, pd.DataFrame) else []
        ed = yahoo.earnings_dates(sym, 40)
        hist = frame_rows(ed) if isinstance(ed, pd.DataFrame) else []
        study = earnings_study(sym)
        implied = None
        o = safe(options, sym, None, False, default=None)
        if o and o.get("available") and o.get("term") and (o["term"].get("earnings") or {}):
            implied = o["term"]["earnings"].get("implied_event_move")
        ivh = safe(er.implied_vs_history, implied, study, default=None) if study else None
        trend = _est_table(a.get("eps_trend"))
        for row in trend:  # revision drift of the consensus
            cur, d30, d90 = row.get("current"), row.get("30daysAgo"), row.get("90daysAgo")
            row["rev_30d"] = (cur / d30 - 1) if cur and d30 else None
            row["rev_90d"] = (cur / d90 - 1) if cur and d90 else None
        return jsonable({
            "symbol": sym, "price": price, "targets": targets, "recommendations": recs, "upgrades": upgrades,
            "earnings_estimate": _est_table(a.get("earnings_estimate")),
            "revenue_estimate": _est_table(a.get("revenue_estimate")),
            "eps_trend": trend, "eps_revisions": _est_table(a.get("eps_revisions")),
            "growth": _est_table(a.get("growth_estimates")),
            "history": hist, "event_study": study, "implied_vs_history": ivh, "implied_event_move": implied,
        })

    return memo(f"anl:{sym}", 1800, build)


# ─── Ownership ───────────────────────────────────────────────────────────────

def _classify_insider(text: str) -> str:
    t = (text or "").lower()
    if "sale" in t or "sold" in t:
        return "sell"
    if "purchase" in t or "buy" in t or "bought" in t:
        return "buy"
    if "gift" in t:
        return "gift"
    if "award" in t or "grant" in t:
        return "award"
    if "exercise" in t or "conversion" in t:
        return "exercise"
    return "other"


def ownership(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        h = yahoo.holders(sym) or {}
        info = safe(yahoo.info, sym, default={}) or {}
        major = {}
        mj = h.get("major")
        if isinstance(mj, pd.DataFrame) and not mj.empty:
            col = mj.columns[0]
            major = {str(k): clean(v) for k, v in mj[col].items()}
        tx = h.get("insider_transactions")
        txs, agg = [], {}
        if isinstance(tx, pd.DataFrame) and not tx.empty:
            now = pd.Timestamp.now()
            for _, r in tx.iterrows():
                kind = _classify_insider(str(r.get("Text") or r.get("Transaction") or ""))
                d = pd.Timestamp(r.get("Start Date")) if r.get("Start Date") is not None else None
                txs.append({"date": d.strftime("%Y-%m-%d") if d is not None and not pd.isna(d) else None,
                            "insider": r.get("Insider"), "position": r.get("Position"), "text": r.get("Text"),
                            "shares": clean(r.get("Shares")), "value": clean(r.get("Value")), "kind": kind,
                            "ownership": r.get("Ownership")})
            for label, months in (("3M", 3), ("6M", 6), ("12M", 12)):
                cut = (now - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
                rows = [t for t in txs if t["date"] and t["date"] >= cut]
                buy_v = sum(t["value"] or 0 for t in rows if t["kind"] == "buy")
                sell_v = sum(t["value"] or 0 for t in rows if t["kind"] == "sell")
                agg[label] = {"buys": sum(1 for t in rows if t["kind"] == "buy"),
                              "sells": sum(1 for t in rows if t["kind"] == "sell"),
                              "buy_value": buy_v, "sell_value": sell_v, "net_value": buy_v - sell_v}
        g = info.get
        short = {"shares_short": clean(g("sharesShort")), "prior_month": clean(g("sharesShortPriorMonth")),
                 "pct_float": clean(g("shortPercentOfFloat")), "pct_shares_out": clean(g("sharesPercentSharesOut")),
                 "days_to_cover": clean(g("shortRatio")), "date": _epoch_iso(g("dateShortInterest")),
                 "float": clean(g("floatShares")), "shares_out": clean(g("sharesOutstanding"))}
        if short["shares_short"] and short["prior_month"]:
            short["change_mom"] = short["shares_short"] / short["prior_month"] - 1
        return jsonable({"symbol": sym, "major": major,
                         "institutional": frame_rows(h.get("institutional")),
                         "mutualfund": frame_rows(h.get("mutualfund")),
                         "insider_transactions": txs[:80], "insider_summary": agg,
                         "insider_purchases": frame_rows(h.get("insider_purchases")),
                         "insider_roster": frame_rows(h.get("insider_roster")), "short": short})

    return memo(f"own:{sym}", 3600, build)


# ─── Factors & regimes ───────────────────────────────────────────────────────

def factors(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        from ..analytics import factors as fx
        from ..analytics import regimes

        px = yahoo.closes(list(FACTOR_ETFS) + [sym], "5y", calendar="SPY")
        if sym not in px.columns:
            raise DataError(f"No price history for {sym}")
        r = returns(px[sym].dropna())
        style = fx.build_factor_returns(px)
        macro = fx.build_macro_factors(px)
        r2y = r.tail(504)
        uc = universe_closes("2y", home_universe(sym) or "us_large")
        peers_px = uc.drop(columns=[c for c in ("SPY", "SOXX", "ACWI") if c in uc.columns and c != sym])
        if sym not in peers_px.columns:
            peers_px = peers_px.join(px[[sym]], how="left")
        return jsonable({
            "symbol": sym,
            "style": safe(fx.factor_regression, r2y, style, 5, default=None),
            "macro": safe(fx.factor_regression, r2y, macro, 5, default=None),
            "rolling": safe(fx.rolling_betas, r.tail(756), style, 126, 5, default=None),
            "regime": safe(regimes.hmm_fit, r.tail(1260), 2, default=None),
            "regime3": safe(regimes.hmm_fit, r.tail(1260), 3, default=None),
            "peers": safe(fx.peer_correlation, peers_px.pct_change(), sym, 12, 252, default=None),
        })

    return memo(f"fac:{sym}", 1800, build)


# ─── Events ──────────────────────────────────────────────────────────────────

def events(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        act = yahoo.actions(sym)
        filings = []
        for f in yahoo.sec_filings(sym)[:40]:
            ex = f.get("exhibits") or {}
            filings.append({"date": str(f.get("date")), "type": f.get("type"), "title": f.get("title"),
                            "url": f.get("edgarUrl"), "exhibits": [{"name": k, "url": v} for k, v in ex.items()][:6]})
        div = act.get("dividends")
        spl = act.get("splits")
        return jsonable({"symbol": sym, "filings": filings,
                         "dividends": ser(div.tail(60)) if isinstance(div, pd.Series) else None,
                         "splits": ser(spl) if isinstance(spl, pd.Series) else None,
                         "calendar": {str(k): (str(v) if not isinstance(v, (int, float)) else v)
                                      for k, v in (yahoo.calendar(sym) or {}).items()}})

    return memo(f"evt:{sym}", 3600, build)


def news(sym: str, count: int = 30) -> list[dict]:
    return yahoo.news(yahoo.norm_symbol(sym), count)


# ─── RSU / stock-option offer simulator ─────────────────────────────────────

def offer(p: dict) -> dict:
    """Value an equity grant: RSUs or stock options, Monte Carlo over the vest schedule."""
    from ..analytics import montecarlo as mc
    from ..analytics import volatility as vol

    sym = yahoo.norm_symbol(p.get("ticker") or "NVDA")
    df = _daily(sym)
    close = df["close"]
    start = p.get("start") or datetime.now().strftime("%Y-%m-%d")
    sched = p.get("schedule") or mc.vest_schedule(start, float(p.get("years", 4)), int(p.get("cliff_months", 12)),
                                                  p.get("frequency", "quarterly"))
    kw = dict(n_paths=int(min(max(int(p.get("n_paths", 10000)), 1000), 50000)), method=p.get("method", "bootstrap"),
              drift=p.get("drift", "zero"), seed=int(p.get("seed", 7)))
    q = yahoo.quote(sym) or {}
    if (p.get("kind") or "rsu") == "option":
        res = mc.option_grant(close, float(p.get("units") or 1000), float(p.get("strike") or q.get("price") or close.iloc[-1]),
                              sched, float(p.get("expiry_years", 10)), yahoo.risk_free(), 0.0, None, **kw)
    else:
        res = mc.rsu_grant(close, sched, units=clean(p.get("units")), grant_value=clean(p.get("grant_value")),
                           grant_price=clean(p.get("grant_price")), **kw)
    g = safe(vol.garch, close, "gjr", "t", 21, 10, default=None) or {}
    ctx = {"ticker": sym, "name": q.get("name"), "price": q.get("price"), "currency": q.get("currency"),
           "vol_1y": clean(returns(close.tail(253)).std() * np.sqrt(252)), "garch_long_run": g.get("long_run_vol"),
           "max_drawdown_5y": clean((close.tail(1260) / close.tail(1260).cummax() - 1).min())}
    return jsonable({"input": {**p, "ticker": sym}, "schedule": sched, "result": res, "context": ctx})
