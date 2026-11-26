"""Yahoo Finance access layer (via yfinance). The only module that touches the network.

Freshness (cache TTLs) is tuned for "latest data within a minute":

    quotes            10 s   one batch request (v7 quote API) for up to 50 symbols
    1-minute bars     30 s   intraday charts incl. pre/post market
    daily bars         6 h  + every read is patched with the live quote, so today's bar
                             (close, high, low, volume) is never older than the quote
    options chains     2 min
    news               5 min
    analysts           1 h,  fundamentals 12 h, ownership 6 h (also kept on disk)

Every loader goes through ``cache.cached`` (single-flight, stale-on-error) and ``_call``
(bounded concurrency + a 30 s cooldown after a Yahoo rate-limit response).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd
import yfinance as yf

from ..analytics._util import clean
from . import cache

log = logging.getLogger("semiquant.data")

TTL = {
    "quote": 10, "1m": 30, "2m": 30, "5m": 60, "15m": 60, "30m": 120, "60m": 300, "90m": 300, "1h": 300,
    "1d": 6 * 3600, "5d": 600, "1wk": 12 * 3600, "1mo": 12 * 3600, "3mo": 12 * 3600,  # daily bars are live-patched
    "info": 900, "statements": 12 * 3600, "analysts": 3600, "earnings": 6 * 3600, "holders": 6 * 3600,
    "expiries": 300, "chain": 120, "news": 300, "calendar": 3600, "filings": 6 * 3600, "actions": 12 * 3600,
    "valuation": 12 * 3600, "market": 60, "screen": 180, "search": 600, "calendars": 3600, "industry": 6 * 3600,
    "rf": 3600,
}
INTRADAY = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}

_sem = threading.BoundedSemaphore(8)
_cooldown_until = 0.0
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="yahoo")


class DataError(RuntimeError):
    """Raised when Yahoo has no data for a request (unknown symbol, empty response)."""


_crumb_bad_since: float | None = None


def _heal_crumb() -> None:
    """Work around a yfinance quirk: when Yahoo throttles the crumb endpoint (HTTP 429),
    yfinance stores the error text ("Too Many Requests") as the crumb, so every later
    crumb-protected call fails with "Invalid Crumb" until restart. While throttled we keep
    the bad crumb (so chart/history calls do not hammer the crumb endpoint) and clear it
    every 90 s so a fresh crumb is fetched once Yahoo allows it again."""
    global _crumb_bad_since
    try:
        from yfinance.data import YfData
        d = YfData()
        c = getattr(d, "_crumb", None)
        bad = c is not None and (len(c) > 24 or " " in c or "<" in c)
        if not bad:
            _crumb_bad_since = None
            return
        now = time.time()
        if _crumb_bad_since is None:
            _crumb_bad_since = now
        elif now - _crumb_bad_since > 90:
            d._crumb = None
            _crumb_bad_since = None
    except Exception:  # noqa: BLE001 - private API; never let the workaround break a request
        pass


def crumb_ok() -> bool:
    return _crumb_bad_since is None


def _call(fn: Callable[[], Any]) -> Any:
    """Run one Yahoo request with bounded concurrency and rate-limit cooldown."""
    global _cooldown_until
    if time.time() < _cooldown_until:
        raise DataError("Yahoo rate limit: cooling down, serving cached data")
    _heal_crumb()
    with _sem:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            text = f"{type(exc).__name__} {exc}"
            if "RateLimit" in text or "Too Many Requests" in text or "429" in text:
                _cooldown_until = time.time() + 30
                log.warning("Yahoo rate limit hit; cooling down 30 s")
            raise


def _parallel(fns: dict[str, Callable[[], Any]]) -> dict[str, Any]:
    """Run independent loaders concurrently; failed ones map to None."""
    futs = {k: _pool.submit(fn) for k, fn in fns.items()}
    out = {}
    for k, f in futs.items():
        try:
            out[k] = f.result()
        except Exception as exc:  # noqa: BLE001
            log.info("loader %s failed: %s", k, exc)
            out[k] = None
    return out


def norm_symbol(s: str) -> str:
    return str(s or "").strip().upper()


# ─── Quotes ──────────────────────────────────────────────────────────────────

_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"


def _epoch_iso(v: Any) -> str | None:
    v = clean(v)
    if v is None or v <= 0:
        return None
    if v > 1e11:  # milliseconds
        v /= 1000.0
    return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pct(v: Any) -> float | None:
    v = clean(v)
    return None if v is None else v / 100.0


def normalize_quote(q: dict) -> dict:
    """Yahoo quote dict -> compact quote. Percent fields become fractions."""
    g = q.get
    price = clean(g("regularMarketPrice"))
    out = {
        "symbol": g("symbol"),
        "name": g("displayName") or g("shortName") or g("longName") or g("symbol"),
        "long_name": g("longName") or g("shortName"),
        "type": g("quoteType"), "type_disp": g("typeDisp"),
        "exchange": g("fullExchangeName") or g("exchange"), "currency": g("currency"),
        "tz": g("exchangeTimezoneName"), "tz_short": g("exchangeTimezoneShortName"),
        "delay_min": clean(g("exchangeDataDelayedBy")), "market_state": g("marketState"),
        "price": price, "change": clean(g("regularMarketChange")), "change_pct": _pct(g("regularMarketChangePercent")),
        "prev_close": clean(g("regularMarketPreviousClose")), "open": clean(g("regularMarketOpen")),
        "high": clean(g("regularMarketDayHigh")), "low": clean(g("regularMarketDayLow")),
        "volume": clean(g("regularMarketVolume")), "avg_volume_3m": clean(g("averageDailyVolume3Month")),
        "avg_volume_10d": clean(g("averageDailyVolume10Day")),
        "time": _epoch_iso(g("regularMarketTime")), "time_epoch": clean(g("regularMarketTime")),
        "bid": clean(g("bid")), "ask": clean(g("ask")), "bid_size": clean(g("bidSize")), "ask_size": clean(g("askSize")),
        "market_cap": clean(g("marketCap")), "shares_out": clean(g("sharesOutstanding")),
        "pe": clean(g("trailingPE")), "fpe": clean(g("forwardPE")), "eps_ttm": clean(g("epsTrailingTwelveMonths")),
        "eps_fwd": clean(g("epsForward")), "eps_cy": clean(g("epsCurrentYear")), "pb": clean(g("priceToBook")),
        "book_value": clean(g("bookValue")),
        "dividend_yield": _pct(g("dividendYield")) if g("dividendYield") is not None else clean(g("trailingAnnualDividendYield")),
        "dividend_rate": clean(g("dividendRate")),
        "high_52w": clean(g("fiftyTwoWeekHigh")), "low_52w": clean(g("fiftyTwoWeekLow")),
        "change_52w": _pct(g("fiftyTwoWeekChangePercent")),
        "sma50": clean(g("fiftyDayAverage")), "sma200": clean(g("twoHundredDayAverage")),
        "pre_price": clean(g("preMarketPrice")), "pre_change": clean(g("preMarketChange")),
        "pre_change_pct": _pct(g("preMarketChangePercent")), "pre_time": _epoch_iso(g("preMarketTime")),
        "post_price": clean(g("postMarketPrice")), "post_change": clean(g("postMarketChange")),
        "post_change_pct": _pct(g("postMarketChangePercent")), "post_time": _epoch_iso(g("postMarketTime")),
        "earnings_time": _epoch_iso(g("earningsTimestamp") or g("earningsTimestampStart")),
        "earnings_estimated": g("isEarningsDateEstimate"),
        "analyst_rating": g("averageAnalystRating"),
        "first_trade": _epoch_iso(g("firstTradeDateMilliseconds")),
    }
    # Best "now" price: extended-hours print when it is newer than the regular close.
    state = (out["market_state"] or "").upper()
    ext = None
    if state in ("PRE", "PREPRE") and out["pre_price"]:
        ext = ("Pre-market", out["pre_price"], out["pre_change"], out["pre_change_pct"], out["pre_time"])
    elif state in ("POST", "POSTPOST", "CLOSED") and out["post_price"] and (out["post_time"] or "") >= (out["time"] or ""):
        ext = ("After hours", out["post_price"], out["post_change"], out["post_change_pct"], out["post_time"])
    if ext:
        out.update(ext_label=ext[0], ext_price=ext[1], ext_change=ext[2], ext_change_pct=ext[3], ext_time=ext[4])
    if price and out["high_52w"] and out["low_52w"] and out["high_52w"] > out["low_52w"]:
        out["pos_52w"] = (price - out["low_52w"]) / (out["high_52w"] - out["low_52w"])
        out["pct_from_high"] = price / out["high_52w"] - 1
    return out


def _remember_static(q: dict) -> None:
    """Persist slow-moving quote fields (market cap, P/E, earnings date...) for fallbacks."""
    if q.get("symbol") and q.get("source") != "chart":
        cache.put(f"qstatic:{q['symbol'].upper()}", {**{k: q.get(k) for k in _STATIC_FIELDS}, "price": q.get("price")},
                  7 * 86400, disk=True)


def _recall_static(sym: str) -> dict:
    v = cache.peek(f"qstatic:{sym}")
    if v is None:
        try:
            v = cache.cached(f"qstatic:{sym}", 7 * 86400, lambda: (_ for _ in ()).throw(KeyError(sym)), disk=True)
        except Exception:  # noqa: BLE001
            v = {}
    return v or {}


def _fetch_quotes(symbols: list[str]) -> dict[str, dict]:
    from yfinance.data import YfData  # yfinance's crumb-aware session

    out: dict[str, dict] = {}
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i + 50]
        params = {"symbols": ",".join(chunk), "formatted": "false", "lang": "en-US", "region": "US"}
        try:
            r = _call(lambda: YfData().get_raw_json(_QUOTE_URL, params=params))
        except Exception as exc:  # noqa: BLE001 - one retry: Yahoo's cookie/crumb occasionally 401s
            if "401" not in str(exc) and "Unauthorized" not in str(exc) and "Invalid Crumb" not in str(exc):
                raise
            time.sleep(0.6)
            r = _call(lambda: YfData().get_raw_json(_QUOTE_URL, params=params))
        for q in ((r or {}).get("quoteResponse") or {}).get("result") or []:
            if q.get("symbol"):
                nq = normalize_quote(q)
                _remember_static(nq)
                out[q["symbol"].upper()] = nq
    return out


_qpool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="quote")
_v7_down_until = 0.0
_STATIC_FIELDS = ("market_cap", "shares_out", "pe", "fpe", "eps_ttm", "eps_fwd", "eps_cy", "pb", "book_value",
                  "dividend_yield", "dividend_rate", "avg_volume_3m", "avg_volume_10d", "sma50", "sma200",
                  "earnings_time", "earnings_estimated", "analyst_rating", "change_52w", "type_disp", "long_name")


def _quote_from_chart(sym: str) -> dict | None:
    """Quote from the chart endpoint (no crumb needed): price, change, day range, volume,
    52-week range, market state and the latest pre/post-market print."""
    from urllib.parse import quote as urlq

    from yfinance.data import YfData

    r = _call(lambda: YfData().get_raw_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urlq(sym, safe='')}",
                                            params={"range": "1d", "interval": "1m", "includePrePost": "true"}))
    res = (((r or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    m = res.get("meta") or {}
    price = clean(m.get("regularMarketPrice"))
    if price is None:
        return None
    prev = clean(m.get("previousClose")) or clean(m.get("chartPreviousClose"))
    pct = _pct(m.get("regularMarketChangePercent"))
    if pct is None and prev:
        pct = price / prev - 1
    ctp = m.get("currentTradingPeriod") or {}
    now = time.time()

    def inside(k):
        p = ctp.get(k) or {}
        return (p.get("start") or 0) <= now < (p.get("end") or 0)

    state = "PRE" if inside("pre") else "REGULAR" if inside("regular") else "POST" if inside("post") else "CLOSED"
    q = {"symbol": sym, "name": m.get("shortName") or m.get("longName") or sym, "long_name": m.get("longName"),
         "type": m.get("instrumentType"), "exchange": m.get("fullExchangeName") or m.get("exchangeName"),
         "currency": m.get("currency"), "tz": m.get("exchangeTimezoneName"), "tz_short": m.get("timezone"),
         "market_state": state, "price": price, "prev_close": prev,
         "change": (price - prev) if prev else None, "change_pct": pct,
         "high": clean(m.get("regularMarketDayHigh")), "low": clean(m.get("regularMarketDayLow")),
         "volume": clean(m.get("regularMarketVolume")), "time": _epoch_iso(m.get("regularMarketTime")),
         "time_epoch": clean(m.get("regularMarketTime")), "high_52w": clean(m.get("fiftyTwoWeekHigh")),
         "low_52w": clean(m.get("fiftyTwoWeekLow")), "first_trade": _epoch_iso(m.get("firstTradeDate")), "source": "chart"}
    # Latest extended-hours print from the 1-minute bars.
    ts = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    reg = ctp.get("regular") or {}
    last_ext = None
    for t, c in zip(ts, closes):
        if c is not None and t >= (reg.get("end") or 9e18):
            last_ext = (t, c)
        if c is not None and state == "PRE" and t < (reg.get("start") or 0):
            last_ext = (t, c)
    if last_ext and state != "REGULAR" and m.get("hasPrePostMarketData") and abs(last_ext[1] - price) > 1e-9:
        base = price if state in ("POST", "CLOSED") else prev
        label = "Pre-market" if state == "PRE" else "After hours"
        q.update(ext_label=label, ext_price=last_ext[1], ext_time=_epoch_iso(last_ext[0]),
                 ext_change=(last_ext[1] - base) if base else None, ext_change_pct=(last_ext[1] / base - 1) if base else None)
    if q["high_52w"] and q["low_52w"] and q["high_52w"] > q["low_52w"]:
        q["pos_52w"] = (price - q["low_52w"]) / (q["high_52w"] - q["low_52w"])
        q["pct_from_high"] = price / q["high_52w"] - 1
    old = cache.peek(f"q:{sym}") or _recall_static(sym)  # keep valuation fields from the last full quote
    for k in _STATIC_FIELDS:
        if q.get(k) is None and old.get(k) is not None:
            q[k] = old[k]
    if q.get("market_cap") and old.get("price"):
        q["market_cap"] = q["market_cap"] * price / old["price"]
    return q


def _fetch_quotes_chart(symbols: list[str]) -> dict[str, dict]:
    futs = {s: _qpool.submit(_quote_from_chart, s) for s in symbols}
    out = {}
    for s, f in futs.items():
        try:
            q = f.result(timeout=30)
            if q:
                out[s] = q
        except Exception:  # noqa: BLE001
            pass
    return out


def quotes(symbols: list[str], ttl: float | None = None) -> dict[str, dict]:
    """Latest quotes for many symbols in one round trip (fresh within ``ttl`` seconds)."""
    ttl = TTL["quote"] if ttl is None else ttl
    syms = list(dict.fromkeys(norm_symbol(s) for s in symbols if s))
    out, need = {}, []
    now = time.time()
    for s in syms:
        a = cache.age(f"q:{s}")
        v = cache.peek(f"q:{s}")
        if v is not None and a is not None and a < ttl:
            out[s] = v
        elif (cache.age(f"qmiss:{s}") or 1e9) < 300:  # unknown / delisted: retry every 5 min only
            continue
        else:
            need.append(s)
    if need:
        global _v7_down_until
        batch_ok, got = True, {}
        if time.time() >= _v7_down_until:
            try:
                got = _fetch_quotes(need)
            except Exception as exc:  # noqa: BLE001
                log.warning("batch quote endpoint unavailable (%s); using the chart endpoint for 60 s", exc)
                _v7_down_until = time.time() + 60
                batch_ok = False
        else:
            batch_ok = False
        if not batch_ok:
            got = _fetch_quotes_chart(need)
            batch_ok = bool(got)
        for s, q in got.items():
            q["fetched"] = now
            te = clean(q.get("time_epoch"))
            if te and q.get("type") not in ("CURRENCY", "CRYPTOCURRENCY"):
                q["stale_days"] = (now - te) / 86400.0
                q["inactive"] = q["stale_days"] > 7  # no trade for a week: delisted / suspended
            cache.put(f"q:{s}", q, ttl)
            out[s] = q
        for s in need:  # keep serving the previous quote if this round failed
            if s not in out and cache.peek(f"q:{s}") is not None:
                out[s] = {**cache.peek(f"q:{s}"), "stale": True}
            elif s not in out and batch_ok:  # the batch worked but Yahoo has no such symbol
                cache.put(f"qmiss:{s}", True, 300)
    return {s: out[s] for s in syms if s in out}


def quote(symbol: str) -> dict | None:
    return quotes([symbol]).get(norm_symbol(symbol))


# ─── Price history ───────────────────────────────────────────────────────────

def _norm_ohlcv(df: pd.DataFrame, intraday: bool) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    d = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in d.columns]
    d = d[keep].copy()
    idx = pd.DatetimeIndex(d.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None) if intraday else idx.tz_localize(None).normalize()
    elif not intraday:
        idx = idx.normalize()
    d.index = idx
    d.index.name = "time" if intraday else "date"
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d = d.dropna(subset=["close"])
    if "volume" in d:
        d["volume"] = d["volume"].fillna(0)
    return d.astype(float)


def history(symbol: str, period: str = "10y", interval: str = "1d", prepost: bool = False) -> pd.DataFrame:
    """OHLCV (lowercase columns). Intraday index = exchange-local naive time; daily = dates."""
    sym = norm_symbol(symbol)
    intraday = interval in INTRADAY
    key = f"h:{sym}:{period}:{interval}:{int(prepost)}"

    def load():
        df = _call(lambda: yf.Ticker(sym).history(period=period, interval=interval, prepost=prepost,
                                                  auto_adjust=True, actions=False))
        d = _norm_ohlcv(df, intraday)
        if d.empty:
            raise DataError(f"no price data for {sym}")
        return d

    return cache.cached(key, TTL.get(interval, 600), load, disk=not intraday, accept=lambda d: len(d) > 0)


def _split_download(df: pd.DataFrame, sym: str) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        lv0 = df.columns.get_level_values(0)
        if sym in set(lv0):
            return df[sym]
        lv1 = df.columns.get_level_values(1)
        if sym in set(lv1):
            return df.xs(sym, axis=1, level=1)
        return None
    return df


def history_many(symbols: list[str], period: str = "10y", interval: str = "1d") -> dict[str, pd.DataFrame]:
    """OHLCV for many symbols: one threaded bulk download for whatever is not cached."""
    syms = list(dict.fromkeys(norm_symbol(s) for s in symbols if s))
    intraday = interval in INTRADAY
    ttl = TTL.get(interval, 600)
    out, need = {}, []
    for s in syms:
        key = f"h:{s}:{period}:{interval}:0"
        v, a = cache.peek(key), cache.age(key)
        if v is not None and a is not None and a < ttl:
            out[s] = v
        else:
            need.append(s)
    if need:
        try:
            df = _call(lambda: yf.download(need, period=period, interval=interval, auto_adjust=True,
                                           group_by="ticker", threads=True, progress=False))
        except Exception as exc:  # noqa: BLE001
            log.warning("bulk download failed: %s", exc)
            df = None
        for s in need:
            part = _norm_ohlcv(_split_download(df, s), intraday) if df is not None else None
            if part is not None and len(part):
                cache.put(f"h:{s}:{period}:{interval}:0", part, ttl, disk=not intraday)
                out[s] = part
        for s in [s for s in need if s not in out][:20]:  # retry stragglers one by one
            try:
                out[s] = history(s, period, interval)
            except Exception:  # noqa: BLE001
                pass
    return {s: out[s] for s in syms if s in out}


def patch_live(df: pd.DataFrame, q: dict | None) -> pd.DataFrame:
    """Overwrite / append today's daily bar from the live quote (exchange-local date)."""
    if df is None or df.empty or not q or q.get("price") is None or not q.get("time_epoch"):
        return df
    try:
        tzname = q.get("tz") or "America/New_York"
        qd = pd.Timestamp(q["time_epoch"], unit="s", tz="UTC").tz_convert(tzname).tz_localize(None).normalize()
    except Exception:  # noqa: BLE001
        return df
    last = df.index[-1]
    price = float(q["price"])
    d = df
    if qd == last:
        d = df.copy()
        d.iloc[-1, d.columns.get_loc("close")] = price
        if "high" in d and q.get("high"):
            d.iloc[-1, d.columns.get_loc("high")] = max(float(d["high"].iloc[-1]), float(q["high"]), price)
        if "low" in d and q.get("low"):
            d.iloc[-1, d.columns.get_loc("low")] = min(float(d["low"].iloc[-1]), float(q["low"]), price)
        if "volume" in d and q.get("volume"):
            d.iloc[-1, d.columns.get_loc("volume")] = max(float(d["volume"].iloc[-1]), float(q["volume"]))
    elif qd > last:
        row = {"open": q.get("open") or price, "high": max(q.get("high") or price, price),
               "low": min(q.get("low") or price, price), "close": price, "volume": q.get("volume") or 0.0}
        d = pd.concat([df, pd.DataFrame([row], index=pd.DatetimeIndex([qd], name=df.index.name))])
    return d


def daily(symbol: str, period: str = "10y", live: bool = True) -> pd.DataFrame:
    """Daily OHLCV with today's bar patched from the live quote."""
    df = history(symbol, period, "1d")
    return patch_live(df, quote(symbol)) if live else df


def daily_many(symbols: list[str], period: str = "10y", live: bool = True) -> dict[str, pd.DataFrame]:
    h = history_many(symbols, period, "1d")
    if live and h:
        qs = quotes(list(h))
        h = {s: patch_live(df, qs.get(s)) for s, df in h.items()}
    return h


def closes(symbols: list[str], period: str = "10y", calendar: str | None = "SPY", live: bool = True,
           ffill_limit: int = 3) -> pd.DataFrame:
    """Aligned daily closes (columns = symbols). Foreign listings are forward-filled up to
    ``ffill_limit`` days onto the ``calendar`` symbol's trading days (US by default)."""
    syms = list(dict.fromkeys(norm_symbol(s) for s in symbols))
    extra = [calendar] if calendar and calendar not in syms else []
    h = daily_many(syms + extra, period, live=live)
    if not h:
        return pd.DataFrame()
    df = pd.DataFrame({s: d["close"] for s, d in h.items()}).sort_index()
    if calendar and calendar in h:
        df = df.ffill(limit=ffill_limit).reindex(h[calendar].index)
    return df[[s for s in syms if s in df.columns]]


def intraday(symbol: str, interval: str = "1m", period: str = "1d", prepost: bool = True) -> pd.DataFrame:
    return history(symbol, period, interval, prepost)


# ─── Company data ────────────────────────────────────────────────────────────

def _ticker(sym: str) -> yf.Ticker:
    return yf.Ticker(norm_symbol(sym))


def info(symbol: str, ttl: float | None = None) -> dict:
    """Ticker.info (profile, fundamentals, ratios). ``ttl`` lets universe-wide callers
    accept an older copy (e.g. 6 h) while a single ticker page wants it fresh (15 min)."""
    sym = norm_symbol(symbol)
    return cache.cached(f"info:{sym}", TTL["info"] if ttl is None else ttl,
                        lambda: _call(lambda: _ticker(sym).info) or {},
                        disk=True, accept=lambda d: isinstance(d, dict) and len(d) > 3)


def statements(symbol: str) -> dict[str, pd.DataFrame]:
    sym = norm_symbol(symbol)

    def load():
        t = _ticker(sym)
        res = _parallel({
            "income_a": lambda: _call(lambda: t.income_stmt), "balance_a": lambda: _call(lambda: t.balance_sheet),
            "cashflow_a": lambda: _call(lambda: t.cashflow), "income_q": lambda: _call(lambda: t.quarterly_income_stmt),
            "balance_q": lambda: _call(lambda: t.quarterly_balance_sheet),
            "cashflow_q": lambda: _call(lambda: t.quarterly_cashflow),
            "income_ttm": lambda: _call(lambda: t.ttm_income_stmt), "cashflow_ttm": lambda: _call(lambda: t.ttm_cashflow),
        })
        out = {k: (v if isinstance(v, pd.DataFrame) else pd.DataFrame()) for k, v in res.items()}
        if all(v.empty for v in out.values()):
            raise DataError(f"no statements for {sym}")
        return out

    return cache.cached(f"stmts:{sym}", TTL["statements"], load, disk=True)


def analysts(symbol: str, ttl: float | None = None) -> dict[str, Any]:
    sym = norm_symbol(symbol)

    def load():
        t = _ticker(sym)
        return _parallel({
            "price_targets": lambda: _call(lambda: t.analyst_price_targets),
            "recommendations": lambda: _call(lambda: t.recommendations_summary),
            "upgrades": lambda: _call(lambda: t.upgrades_downgrades),
            "earnings_estimate": lambda: _call(lambda: t.earnings_estimate),
            "revenue_estimate": lambda: _call(lambda: t.revenue_estimate),
            "eps_trend": lambda: _call(lambda: t.eps_trend),
            "eps_revisions": lambda: _call(lambda: t.eps_revisions),
            "growth_estimates": lambda: _call(lambda: t.growth_estimates),
            "earnings_history": lambda: _call(lambda: t.earnings_history),
        })

    return cache.cached(f"analysts:{sym}", TTL["analysts"] if ttl is None else ttl, load, disk=True)


def eps_trend(symbol: str, ttl: float | None = None) -> pd.DataFrame:
    """Consensus EPS now vs 7/30/60/90 days ago (one request; used for universe revisions)."""
    sym = norm_symbol(symbol)
    full = cache.peek(f"analysts:{sym}")
    if isinstance(full, dict) and isinstance(full.get("eps_trend"), pd.DataFrame):
        return full["eps_trend"]
    try:
        return cache.cached(f"epstrend:{sym}", TTL["analysts"] if ttl is None else ttl,
                            lambda: _call(lambda: _ticker(sym).eps_trend), disk=True)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def earnings_dates(symbol: str, limit: int = 40) -> pd.DataFrame:
    sym = norm_symbol(symbol)

    def load():
        df = _call(lambda: _ticker(sym).get_earnings_dates(limit=limit))
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    try:
        return cache.cached(f"earn:{sym}:{limit}", TTL["earnings"], load, disk=True)
    except Exception:  # noqa: BLE001 - ETFs / indices have no earnings
        return pd.DataFrame()


def holders(symbol: str) -> dict[str, Any]:
    sym = norm_symbol(symbol)

    def load():
        t = _ticker(sym)
        return _parallel({
            "major": lambda: _call(lambda: t.major_holders),
            "institutional": lambda: _call(lambda: t.institutional_holders),
            "mutualfund": lambda: _call(lambda: t.mutualfund_holders),
            "insider_transactions": lambda: _call(lambda: t.insider_transactions),
            "insider_purchases": lambda: _call(lambda: t.insider_purchases),
            "insider_roster": lambda: _call(lambda: t.insider_roster_holders),
        })

    return cache.cached(f"holders:{sym}", TTL["holders"], load, disk=True)


def option_expiries(symbol: str) -> list[str]:
    sym = norm_symbol(symbol)
    try:
        return list(cache.cached(f"exp:{sym}", TTL["expiries"], lambda: tuple(_call(lambda: _ticker(sym).options) or ())))
    except Exception:  # noqa: BLE001
        return []


def option_chain(symbol: str, expiry: str) -> dict[str, Any]:
    sym = norm_symbol(symbol)

    def load():
        c = _call(lambda: _ticker(sym).option_chain(expiry))
        return {"calls": c.calls, "puts": c.puts, "underlying": dict(c.underlying or {})}

    return cache.cached(f"chain:{sym}:{expiry}", TTL["chain"], load)


def option_chains(symbol: str, expiries: list[str]) -> dict[str, dict]:
    res = _parallel({e: (lambda e=e: option_chain(symbol, e)) for e in expiries})
    return {e: v for e, v in res.items() if v is not None}


def _norm_news_item(n: dict) -> dict | None:
    c = n.get("content") if isinstance(n.get("content"), dict) else None
    if c:
        thumbs = (c.get("thumbnail") or {}).get("resolutions") or []
        small = sorted([t for t in thumbs if t.get("url")], key=lambda t: t.get("width") or 9999)
        url = (c.get("clickThroughUrl") or {}).get("url") or (c.get("canonicalUrl") or {}).get("url")
        return {"id": c.get("id") or n.get("id"), "title": c.get("title"), "summary": c.get("summary") or c.get("description"),
                "publisher": (c.get("provider") or {}).get("displayName"), "url": url, "time": c.get("pubDate"),
                "type": c.get("contentType"), "thumbnail": small[0]["url"] if small else None,
                "tickers": [x.get("symbol") for x in ((c.get("finance") or {}).get("stockTickers") or []) if x.get("symbol")]}
    if n.get("title"):
        thumbs = (n.get("thumbnail") or {}).get("resolutions") or []
        small = sorted([t for t in thumbs if t.get("url")], key=lambda t: t.get("width") or 9999)
        return {"id": n.get("uuid"), "title": n.get("title"), "summary": None, "publisher": n.get("publisher"),
                "url": n.get("link"), "time": _epoch_iso(n.get("providerPublishTime")), "type": n.get("type"),
                "thumbnail": small[0]["url"] if small else None, "tickers": n.get("relatedTickers") or []}
    return None


def news(symbol: str, count: int = 20) -> list[dict]:
    sym = norm_symbol(symbol)

    def load():
        raw = _call(lambda: _ticker(sym).get_news(count=count)) or []
        items = [x for x in (_norm_news_item(n) for n in raw) if x and x.get("title")]
        return sorted(items, key=lambda x: x.get("time") or "", reverse=True)

    try:
        return cache.cached(f"news:{sym}:{count}", TTL["news"], load)
    except Exception:  # noqa: BLE001
        return []


def search_news(query: str, count: int = 20) -> list[dict]:
    def load():
        s = _call(lambda: yf.Search(query, max_results=1, news_count=count))
        items = [x for x in (_norm_news_item(n) for n in (s.news or [])) if x and x.get("title")]
        return sorted(items, key=lambda x: x.get("time") or "", reverse=True)

    try:
        return cache.cached(f"snews:{query}:{count}", TTL["news"], load)
    except Exception:  # noqa: BLE001
        return []


def calendar(symbol: str) -> dict:
    sym = norm_symbol(symbol)
    try:
        return cache.cached(f"cal:{sym}", TTL["calendar"], lambda: _call(lambda: _ticker(sym).calendar) or {})
    except Exception:  # noqa: BLE001
        return {}


def sec_filings(symbol: str) -> list[dict]:
    sym = norm_symbol(symbol)
    try:
        return cache.cached(f"sec:{sym}", TTL["filings"], lambda: list(_call(lambda: _ticker(sym).sec_filings) or []),
                            disk=True)
    except Exception:  # noqa: BLE001
        return []


def actions(symbol: str) -> dict[str, pd.Series]:
    sym = norm_symbol(symbol)

    def load():
        t = _ticker(sym)
        r = _parallel({"dividends": lambda: _call(lambda: t.dividends), "splits": lambda: _call(lambda: t.splits)})
        return {k: (v if isinstance(v, pd.Series) else pd.Series(dtype=float)) for k, v in r.items()}

    try:
        return cache.cached(f"act:{sym}", TTL["actions"], load, disk=True)
    except Exception:  # noqa: BLE001
        return {"dividends": pd.Series(dtype=float), "splits": pd.Series(dtype=float)}


def valuation_history(symbol: str) -> pd.DataFrame:
    sym = norm_symbol(symbol)
    try:
        return cache.cached(f"val:{sym}", TTL["valuation"], lambda: _call(lambda: _ticker(sym).valuation), disk=True)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


# ─── Market-wide ─────────────────────────────────────────────────────────────

def market_status(region: str = "US") -> dict:
    def load():
        s = dict(_call(lambda: yf.Market(region).status) or {})
        tzinfo = s.get("timezone") or {}
        return {"region": region, "status": s.get("status"), "message": s.get("message"),
                "open": s["open"].strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(s.get("open"), datetime) else None,
                "close": s["close"].strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(s.get("close"), datetime) else None,
                "tz": tzinfo.get("$text") if isinstance(tzinfo, dict) else None}

    try:
        return cache.cached(f"mstatus:{region}", TTL["market"], load)
    except Exception:  # noqa: BLE001
        return {"region": region, "status": None, "message": "Market status unavailable"}


def screen(name: str, count: int = 25) -> list[dict]:
    def load():
        r = _call(lambda: yf.screen(name, count=count)) or {}
        return [normalize_quote(q) for q in r.get("quotes") or []]

    try:
        return cache.cached(f"screen:{name}:{count}", TTL["screen"], load)
    except Exception:  # noqa: BLE001
        return []


def search(query: str, n: int = 8) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []

    def load():
        s = _call(lambda: yf.Search(q, max_results=n, news_count=0))
        return [{"symbol": x.get("symbol"), "name": x.get("shortname") or x.get("longname"), "type": x.get("typeDisp") or x.get("quoteType"),
                 "exchange": x.get("exchDisp") or x.get("exchange"), "sector": x.get("sectorDisp") or x.get("sector"),
                 "industry": x.get("industryDisp") or x.get("industry")} for x in (s.quotes or []) if x.get("symbol")]

    try:
        return cache.cached(f"search:{q.lower()}:{n}", TTL["search"], load)
    except Exception:  # noqa: BLE001
        return []


def _frame_rows(df: pd.DataFrame | None) -> list[dict]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    d = df.reset_index()
    rows = []
    for _, r in d.iterrows():
        row = {}
        for k, v in r.items():
            if isinstance(v, (pd.Timestamp, datetime)):
                v = pd.Timestamp(v).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") if pd.Timestamp(v).tzinfo else pd.Timestamp(v).isoformat()
            elif isinstance(v, (float, np.floating)):
                v = clean(v)
            elif isinstance(v, (np.integer,)):
                v = int(v)
            row[str(k)] = v
        rows.append(row)
    return rows


def earnings_calendar(days: int = 14, limit: int = 100, most_active: bool = False) -> list[dict]:
    def load():
        start = date.today()
        c = yf.Calendars(start=start, end=start + timedelta(days=days))
        return _frame_rows(_call(lambda: c.get_earnings_calendar(filter_most_active=most_active, limit=limit)))

    try:
        return cache.cached(f"ecal:{days}:{limit}:{int(most_active)}", TTL["calendars"], load)
    except Exception:  # noqa: BLE001
        return []


def economic_calendar(days: int = 7, limit: int = 100) -> list[dict]:
    def load():
        start = date.today()
        c = yf.Calendars(start=start, end=start + timedelta(days=days))
        return _frame_rows(_call(lambda: c.get_economic_events_calendar(limit=limit)))

    try:
        return cache.cached(f"econ:{days}:{limit}", TTL["calendars"], load)
    except Exception:  # noqa: BLE001
        return []


def risk_free() -> float:
    """13-week T-bill yield (^IRX) as a decimal; 4% if unavailable."""
    q = quotes(["^IRX"]).get("^IRX") or {}
    v = clean(q.get("price"))
    return v / 100.0 if v and 0 < v < 20 else 0.04


def frame_rows(df: pd.DataFrame | None) -> list[dict]:
    """Public: DataFrame (any index) -> JSON-ready row dicts (index included)."""
    return _frame_rows(df)


def status() -> dict:
    return {"yfinance": yf.__version__, "cache": dict(cache.stats),
            "cooldown": max(0.0, _cooldown_until - time.time())}
