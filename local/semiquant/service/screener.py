"""Universe screener and quant scores: live quotes + daily metrics + cached fundamentals."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from ..analytics._util import clean, jsonable, safe
from ..data import yahoo
from ..universe import ALL_META, UNIVERSES, get_universe, home_universe, universe_key, universe_meta, universe_tickers
from .common import fx_to_usd, memo

FUND_TTL = 6 * 3600  # universe-wide fundamentals may be up to 6 h old (one request per ticker)


def _rating_num(s) -> float | None:
    m = re.match(r"\s*([\d.]+)", str(s or ""))
    return float(m.group(1)) if m else None


def _eps_rev_30d(t: str) -> float | None:
    df = yahoo.eps_trend(t, ttl=12 * 3600)
    try:
        cur, ago = clean(df.loc["0y", "current"]), clean(df.loc["0y", "30daysAgo"])
        if cur is not None and ago:
            return (cur - ago) / abs(ago)  # signed revision, valid for negative EPS too
    except Exception:  # noqa: BLE001
        pass
    return None


def fundamentals_frame(tickers: list[str], revisions: bool = True) -> pd.DataFrame:
    """Per-ticker fundamental inputs for scoring (info fields, analyst targets, revisions)."""
    q = yahoo.quotes(tickers)

    def one(t: str) -> dict:
        i = safe(yahoo.info, t, FUND_TTL, default={}) or {}
        g = i.get
        price = clean((q.get(t) or {}).get("price")) or clean(g("currentPrice"))
        mc = clean(g("marketCap"))
        fcf = clean(g("freeCashflow"))
        same_ccy = (g("financialCurrency") or g("currency")) == g("currency")
        pe = clean(g("trailingPE"))
        tgt = clean(g("targetMeanPrice"))
        de = clean(g("debtToEquity"))
        return {
            "ticker": t, "sector_yf": g("sector"), "industry": g("industry"),
            "earnings_yield": (1.0 / pe) if pe and pe > 0 else None,
            "fcf_yield": (fcf / mc) if fcf is not None and mc and same_ccy else None,
            "ev_sales": clean(g("enterpriseToRevenue")), "ev_ebitda": clean(g("enterpriseToEbitda")),
            "gross_margin": clean(g("grossMargins")), "operating_margin": clean(g("operatingMargins")),
            "net_margin": clean(g("profitMargins")), "roe": clean(g("returnOnEquity")),
            "rev_growth": clean(g("revenueGrowth")), "eps_growth": clean(g("earningsGrowth")),
            "target_upside": (tgt / price - 1) if tgt and price else None,
            "rec_mean": clean(g("recommendationMean")) or _rating_num((q.get(t) or {}).get("analyst_rating")),
            "n_analysts": clean(g("numberOfAnalystOpinions")), "short_pct": clean(g("shortPercentOfFloat")),
            "debt_to_equity": de / 100.0 if de is not None else None, "beta_yf": clean(g("beta")),
            "eps_rev_30d": safe(_eps_rev_30d, t, default=None) if revisions else None,
        }

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, tickers))
    return pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()


def _score_universe(tickers: tuple[str, ...], bench: str = "SPY", sector_bench: str = "SOXX"):
    from ..analytics import scoring

    c = yahoo.closes(list(tickers) + list(dict.fromkeys(["SPY", bench, sector_bench])), "2y", calendar="SPY")
    present = [t for t in tickers if t in c.columns and c[t].notna().sum() > 30]
    m = scoring.universe_metrics(c[present], c.get(bench), c.get(sector_bench))
    f = fundamentals_frame(present)
    s = scoring.quant_score(m, f)
    return m, f, s


def scored(tickers: tuple[str, ...] | None = None, bench: str = "SPY", sector_bench: str = "SOXX"):
    tickers = tuple(tickers or universe_tickers("semis"))
    return memo(f"scored:{hash(tickers)}:{bench}:{sector_bench}", 120, lambda: _score_universe(tickers, bench, sector_bench))


def score_for(sym: str) -> dict | None:
    """Composite quant score for one ticker, ranked against its home universe (US large caps
    for any ticker that is not in a built-in universe)."""
    from ..analytics import scoring

    sym = yahoo.norm_symbol(sym)
    key = home_universe(sym) or "us_large"
    u = UNIVERSES[key]
    base = tuple(universe_tickers(key))
    m, f, s = scored(base if sym in base else base + (sym,), u["bench"], u["sector_bench"])
    if sym not in s.index:
        return None
    row = s.loc[sym]
    out = safe(scoring.score_explain, row, default={}) or {}
    out["rank"] = int((s["score"] > row["score"]).sum() + 1)
    out["of"] = int(s["score"].notna().sum())
    out["universe"] = u["label"]
    return jsonable(out)


COLUMNS = [  # (key, label, group, format)
    ("ticker", "Ticker", "Info", "text"), ("name", "Name", "Info", "text"), ("sector", "Sector", "Info", "text"),
    ("tier", "Tier", "Info", "text"), ("price", "Price", "Info", "price"), ("change_pct", "Day", "Performance", "pct"),
    ("ext_change_pct", "Ext.", "Performance", "pct"), ("score", "Score", "Score", "score"),
    ("ret_5d", "1W", "Performance", "pct"), ("ret_1m", "1M", "Performance", "pct"), ("ret_3m", "3M", "Performance", "pct"),
    ("ret_6m", "6M", "Performance", "pct"), ("ret_ytd", "YTD", "Performance", "pct"), ("ret_1y", "1Y", "Performance", "pct"),
    ("mom_12_1", "Mom 12-1", "Performance", "pct"), ("rel_strength_3m", "Rel. strength 3M", "Performance", "pct"),
    ("market_cap_usd", "Mkt cap $", "Valuation", "big"), ("pe", "P/E", "Valuation", "x"), ("fpe", "Fwd P/E", "Valuation", "x"),
    ("ev_sales", "EV/Sales", "Valuation", "x"), ("ev_ebitda", "EV/EBITDA", "Valuation", "x"),
    ("fcf_yield", "FCF yield", "Valuation", "pct"), ("dividend_yield", "Div yield", "Valuation", "pct"),
    ("gross_margin", "Gross mgn", "Quality", "pct"), ("operating_margin", "Op mgn", "Quality", "pct"),
    ("roe", "ROE", "Quality", "pct"), ("rev_growth", "Rev growth", "Growth", "pct"), ("eps_growth", "EPS growth", "Growth", "pct"),
    ("eps_rev_30d", "EPS rev 30d", "Growth", "pct"), ("target_upside", "Target upside", "Analysts", "pct"),
    ("rec_mean", "Rating (1=buy)", "Analysts", "num"), ("vol_3m", "Vol 3M", "Risk", "pct"), ("beta_1y", "Beta 1Y", "Risk", "num"),
    ("max_dd_1y", "Max DD 1Y", "Risk", "pct"), ("sharpe_1y", "Sharpe 1Y", "Risk", "num"), ("short_pct", "Short % float", "Risk", "pct"),
    ("rsi14", "RSI", "Technical", "num"), ("pct_from_52w_high", "From 52W high", "Technical", "pct"),
    ("pos_52w", "52W position", "Technical", "pct"), ("trend", "Trend", "Technical", "text"),
    ("rel_volume", "Rel. volume", "Technical", "num"), ("earnings", "Next earnings", "Info", "date"),
]


def table(tickers: list[str] | None = None, name: str | None = None, universe: str | None = None) -> dict:
    """Screener rows (one per ticker) with ~40 columns; scores are ranked within the list.
    ``universe`` picks a built-in universe when no explicit ``tickers`` are given."""
    key = universe_key(universe) if not tickers else None
    u = get_universe(key) if key else {"label": name or "Watchlist", "bench": "SPY", "sector_bench": "SPY"}
    metas = universe_meta(key) if key else {}
    tickers = [yahoo.norm_symbol(t) for t in (tickers or list(metas))]
    m, f, s = scored(tuple(tickers), u["bench"], u["sector_bench"])
    q = yahoo.quotes(tickers)
    fx = fx_to_usd([x.get("currency") for x in q.values()])
    rows = []
    for t in tickers:
        x = q.get(t) or {}
        mt = metas.get(t) or ALL_META.get(t, {})
        row = {"ticker": t, "name": mt.get("name") or x.get("name"), "sector": mt.get("sector") or
               (f.loc[t, "sector_yf"] if t in f.index else None), "tier": mt.get("tier"),
               "price": x.get("price"), "currency": x.get("currency"), "change_pct": x.get("change_pct"),
               "ext_change_pct": x.get("ext_change_pct"), "market_state": x.get("market_state"),
               "pe": x.get("pe"), "fpe": x.get("fpe"), "dividend_yield": x.get("dividend_yield"),
               "earnings": (x.get("earnings_time") or "")[:10] or None,
               "rel_volume": (x["volume"] / x["avg_volume_10d"]) if x.get("volume") and x.get("avg_volume_10d") else None}
        mc, rate = clean(x.get("market_cap")), fx.get(x.get("currency"), 1.0)
        row["market_cap_usd"] = mc * rate if mc and rate and np.isfinite(rate) else None
        if t in m.index:
            row.update({k: v for k, v in m.loc[t].items() if k != "last"})
        if t in f.index:
            row.update({k: v for k, v in f.loc[t].items() if k not in ("sector_yf",)})
        if t in s.index:  # score components; "trend" is renamed so the up/down/range label survives
            row.update({("trend_score" if k == "trend" else k): v for k, v in s.loc[t].items()})
        row["missing"] = not x or bool(x.get("inactive"))
        rows.append(row)
    return jsonable({"name": name or u["label"], "universe": key, "rel_bench": u["sector_bench"], "columns": [
        {"key": k, "label": lbl, "group": g, "format": fm} for k, lbl, g, fm in COLUMNS],
        "rows": rows, "n": len(rows)})
