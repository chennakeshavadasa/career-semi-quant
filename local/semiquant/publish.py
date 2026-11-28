"""Publish the dashboard as a static website with precomputed data (e.g. GitHub Pages).

    semiquant publish --out dist/quant-terminal

Writes the same UI as the local edition plus ``data/<path>.json`` files holding exactly
what the local API would return, so every page works without a server. A scheduled job
(see the site's deploy workflow) re-runs this every ~15 minutes. Payloads refresh on
tiers, and anything not yet due is reused from the previous output, so a run only does
the work that is due:

    live    every run   quotes, market strip, heatmaps, movers, news, screeners,
                        upcoming earnings, ticker overviews, 1-day and 5-day charts
    hourly  60 min      1-month / 10-year charts, quant scores, breadth, calendar, ticker news
    slow    3 h         risk, volatility, tail risk, options, factors, analysts
    daily   20 h        fundamentals, ownership, filings, all-history chart, universes

Keep both the output folder and ~/.semiquant/cache between runs (actions/cache) so the
reuse works. Charts ship raw OHLCV bars; the browser computes indicators.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote as urlq

from . import __version__, config
from .analytics._util import jsonable
from .data import yahoo
from .service import market as mkt
from .service import screener as scr
from .service import ticker as tk
from .service import tools
from .service.export import snap_key
from .universe import (MARKET_GROUPS, SECTOR_ETFS, UNIVERSES, VIX_TERM, YIELD_CURVE, ALL_META, universe_tickers)

log = logging.getLogger("semiquant.publish")
WEB = Path(__file__).resolve().parent / "web"
TIERS = {"live": 0, "hourly": 3600, "slow": 3 * 3600, "daily": 20 * 3600}
QUOTE_FIELDS = ("price", "change", "change_pct", "prev_close", "market_state", "time", "high", "low", "volume",
                "ext_label", "ext_price", "ext_change_pct", "high_52w", "low_52w", "market_cap", "currency",
                "pe", "fpe", "inactive")
DEFAULT_FULL = ("semis", "mega", "us_large")
MEGA = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "V", "WMT", "XOM",
        "SPY", "QQQ", "SOXX")


def file_key(path: str) -> str:
    """API path -> data file name. Must match SQ.fileKey in core.js."""
    k = snap_key(path)
    k = k[len("/api/"):] if k.startswith("/api/") else k.lstrip("/")
    return k.replace("?", "__").replace("&", "__").replace("=", "-").replace("%", "_") + ".json"


def _round(o: Any) -> Any:
    """6 significant digits: halves the JSON size, far below display precision."""
    if isinstance(o, float):
        return float(f"{o:.6g}") if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v) for v in o]
    return o


def _dump(obj: Any) -> str:
    return json.dumps(_round(jsonable(obj)), separators=(",", ":"), allow_nan=False)


def _trim(kind: str, data: Any) -> Any:
    """Drop parts of a payload the dashboard does not show (keeps files small)."""
    if not isinstance(data, dict):
        return data
    if kind == "factors":
        data.pop("regime3", None)
    elif kind == "volatility":
        rs = (data.get("realized") or {}).get("series")
        if isinstance(rs, dict):
            data["realized"]["series"] = {k: v for k, v in rs.items() if k in ("yang_zhang", "close_to_close")}
    elif kind == "chart":
        data["indicators"] = {}  # computed in the browser from the bars
    return data


def _ser_tail(s: dict | None, n: int) -> dict | None:
    if not s or not s.get("t"):
        return s
    return {"t": s["t"][-n:], "v": s["v"][-n:]}


class Publisher:
    def __init__(self, out: str | Path, full: list[str] | None = None, force: bool = False, workers: int = 6,
                 budget: float | None = None):
        self.out = Path(out)
        self.data = self.out / "data"
        self.force = force
        self.workers = workers
        self.full = full or self._default_full()
        self.index_path = self.data / "index.json"
        try:
            self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.index = {}
        self.now = time.time()
        # Stop starting heavy work after `budget` seconds; the next run continues (tiers).
        self.deadline = self.now + budget if budget else None
        self.stats = {"written": 0, "reused": 0, "failed": 0, "deferred": 0}
        self.errors: list[str] = []
        self._lock = threading.Lock()
        self._unsaved = 0

    @staticmethod
    def _default_full() -> list[str]:
        syms = list(universe_tickers("semis")) + list(MEGA) + list(universe_tickers("us_large"))
        return list(dict.fromkeys(syms))

    # ── bookkeeping ─────────────────────────────────────────────────────
    def due(self, path: str, tier: str) -> bool:
        if self.force:
            return True
        key = file_key(path)
        built = self.index.get(key)
        if built is None or not (self.data / key).exists() or self.now - built >= TIERS[tier] - 60:
            return True
        return self._empty_answer(key)

    def _empty_answer(self, key: str) -> bool:
        """A published 'not available' answer is retried every run (it is often a Yahoo hiccup)."""
        try:
            with open(self.data / key, "rb") as f:
                head = f.read(160)
        except OSError:
            return True
        return b'"available":false' in head.replace(b" ", b"") or b'"unavailable":true' in head.replace(b" ", b"")

    def put(self, path: str, tier: str, fn: Callable[[], Any], kind: str | None = None) -> None:
        if not self.due(path, tier):
            self.stats["reused"] += 1
            return
        key = file_key(path)
        try:
            payload = fn()
            if kind:
                payload = _trim(kind, payload)
            text = _dump(payload)
        except Exception as exc:  # noqa: BLE001 - keep the previous file, report, continue
            self.stats["failed"] += 1
            self.errors.append(f"{path}: {type(exc).__name__}: {str(exc)[:160]}")
            if (self.data / key).exists():
                return
            # First time and nothing to show (e.g. an ETF has no analysts): publish an explicit
            # empty state so the page explains it instead of failing; retried next run.
            text = json.dumps({"unavailable": True, "message": "Not available yet: Yahoo did not return this section at the last "
                               "refresh; it is retried at every refresh (about every 15 minutes). ETFs and indices have "
                               "no analysts, statements or insiders."})
            p = self.data / key
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            return
        p = self.data / key
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
        with self._lock:
            self.index[key] = self.now
            self.stats["written"] += 1
            self._unsaved += 1
            if self._unsaved >= 20:  # a killed run keeps its progress
                self.save_index()

    def save_index(self) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.index, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, self.index_path)
        self._unsaved = 0

    def over_budget(self) -> bool:
        return bool(self.deadline and time.time() > self.deadline)

    # ── static app ──────────────────────────────────────────────────────
    def copy_app(self) -> str:
        """Copy the UI and return a short build hash (used for cache-busting)."""
        for sub in ("css", "js", "fonts", "vendor", "icons"):
            src = WEB / sub
            if src.exists():
                shutil.copytree(src, self.out / sub, dirs_exist_ok=True)
        import plotly
        shutil.copy2(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", self.out / "vendor" / "plotly.min.js")
        h = hashlib.sha1()
        for f in sorted((self.out).rglob("*")):
            if f.is_file() and "data" not in f.relative_to(self.out).parts and f.suffix in (".js", ".css", ".html"):
                h.update(f.read_bytes())
        build = h.hexdigest()[:10]
        cfg = {"base": "data/", "build": build, "version": __version__}
        html = (WEB / "index.html").read_text(encoding="utf-8")
        html = html.replace("<title>Semi Quant Terminal · Local</title>", "<title>Semi Quant Terminal</title>", 1)
        html = html.replace("<!--SNAPSHOT-->", "<script>window.SQ_STATIC=" + json.dumps(cfg) + ";</script>", 1)
        html = re.sub(r'(src|href)="((?:css|js)/[^"]+)"', lambda m: f'{m.group(1)}="{m.group(2)}?v={build}"', html)
        (self.out / "index.html").write_text(html, encoding="utf-8")
        sw = (WEB / "sw.js").read_text(encoding="utf-8").replace("__BUILD__", build)
        (self.out / "sw.js").write_text(sw, encoding="utf-8")
        shutil.copy2(WEB / "manifest.webmanifest", self.out / "manifest.webmanifest")
        return build

    # ── data ────────────────────────────────────────────────────────────
    def quotes(self) -> None:
        """quotes.json: lean live quotes for every symbol the dashboard can show."""
        strip = [s for g in MARKET_GROUPS.values() for s, _ in g] + [s for s, _ in VIX_TERM] + [s for s, _ in SECTOR_ETFS]
        strip += [s for s, _, _ in YIELD_CURVE]
        fx = [f"{c}=X" for c in ("EUR", "JPY", "KRW", "TWD", "GBP", "CHF", "HKD", "INR", "AUD", "CAD", "CNY", "BRL", "SGD")]
        syms = list(dict.fromkeys(strip + self.full + list(ALL_META) + fx))
        try:
            prev = json.loads((self.data / "quotes.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
        q = yahoo.quotes(syms)
        out = {}
        for s in syms:
            x = q.get(s)
            if x:
                out[s] = {k: x.get(k) for k in QUOTE_FIELDS if x.get(k) is not None}
            elif s in prev:
                out[s] = {**prev[s], "stale": True}
        (self.data / "quotes.json").write_text(_dump(out), encoding="utf-8")

    def market(self) -> None:
        self.put("/api/market/strip", "live", mkt.strip)
        self.put("/api/market/movers", "live", mkt.movers)
        self.put("/api/market/news", "live", mkt.market_news)
        self.put("/api/market/earnings", "hourly", lambda: mkt.upcoming_earnings(30))
        self.put("/api/calendar", "hourly", tools.calendar)
        self.put("/api/universes", "daily", lambda: [{"key": k, "label": v["label"], "count": len(v["rows"]),
                                                      "group_label": v["group_label"]} for k, v in UNIVERSES.items()])
        for u in UNIVERSES:
            self.put(f"/api/market/heatmap?u={u}", "live", lambda u=u: mkt.heatmap(u))
            self.put(f"/api/screener?u={u}", "live", lambda u=u: scr.table(None, None, u))
            self.put(f"/api/market/breadth?u={u}", "hourly", lambda u=u: mkt.breadth(u))
            self.put(f"/api/market/systemic?u={u}", "slow", lambda u=u: mkt.systemic(u))
            self.put(f"/api/factorlab?u={u}", "daily", lambda u=u: mkt.factorlab(u))

    def ticker(self, sym: str) -> None:
        """Quick pass: everything that changes intraday (always done)."""
        enc = urlq(sym, safe="")
        base = f"/api/ticker/{enc}"
        self.put(f"{base}/overview", "live", lambda: tk.overview(sym))
        self.put(f"{base}/chart?range=1D", "live", lambda: tk.chart(sym, "1D", []), "chart")
        self.put(f"{base}/chart?range=5D", "live", lambda: tk.chart(sym, "5D", []), "chart")
        self.put(f"{base}/chart?range=1M", "hourly", lambda: tk.chart(sym, "1M", []), "chart")
        self.put(f"{base}/chart?range=10Y", "hourly", lambda: tk.chart(sym, "10Y", []), "chart")
        self.put(f"{base}/chart?range=MAX", "daily", lambda: tk.chart(sym, "MAX", []), "chart")
        self.put(f"{base}/score", "hourly", lambda: tk.score(sym))
        self.put(f"{base}/news?count=40", "hourly", lambda: tk.news(sym, 40))

    def ticker_slow(self, sym: str) -> None:
        """Heavy pass (risk models, options, statements): stops at the time budget."""
        if self.over_budget():
            self.stats["deferred"] += 1
            return
        base = f"/api/ticker/{urlq(sym, safe='')}"
        for tab, fn in (("risk", tk.risk), ("volatility", tk.volatility), ("tail", tk.tail), ("options", tk.options),
                        ("factors", tk.factors), ("analysts", tk.analysts)):
            self.put(f"{base}/{tab}", "slow", lambda fn=fn: fn(sym), tab)
        for tab, fn in (("fundamentals", tk.fundamentals), ("ownership", tk.ownership), ("events", tk.events)):
            self.put(f"{base}/{tab}", "daily", lambda fn=fn: fn(sym), tab)

    def published(self) -> list[str]:
        """Tickers with a full page = those whose overview file exists (robust to partial runs)."""
        from urllib.parse import unquote
        root = self.data / "ticker"
        if not root.exists():
            return []
        return sorted(unquote(d.name.replace("_", "%")) for d in root.iterdir() if (d / "overview.json").exists())

    def meta(self, build: str) -> None:
        built = datetime.fromtimestamp(self.now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = {"built_at": built, "build": build, "version": __version__, "full": self.published(),
                "stats": self.stats, "errors": self.errors[:40], "market": yahoo.market_status("US")}
        (self.data / "meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")
        search = [[t, m["name"], UNIVERSES[m["universe"]]["label"], m["sector"]] for t, m in ALL_META.items()]
        strip = {s: lbl for g in MARKET_GROUPS.values() for s, lbl in g}
        search += [[s, lbl, "Market", "Index / macro"] for s, lbl in strip.items() if s not in ALL_META]
        (self.data / "search.json").write_text(json.dumps(search, separators=(",", ":")), encoding="utf-8")
        with self._lock:
            self.save_index()

    def run(self, tickers: list[str] | None = None, market: bool = True) -> dict:
        t0 = time.time()
        self.data.mkdir(parents=True, exist_ok=True)
        build = self.copy_app()
        self.quotes()
        if market:
            self.market()
        names = tickers if tickers is not None else self.full
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(self.ticker, names))  # quick pass for every ticker first
        self.meta(build)  # publish what is ready before the heavy pass
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(self.ticker_slow, names))
        self.meta(build)
        size = sum(f.stat().st_size for f in self.data.rglob("*.json")) / 1e6
        return {"seconds": round(time.time() - t0, 1), "data_mb": round(size, 1), "build": build, **self.stats,
                "errors": self.errors[:10], "tickers": len(names)}


def publish(out: str, full: list[str] | None = None, tickers: list[str] | None = None, force: bool = False,
            market: bool = True, budget_minutes: float | None = None) -> dict:
    config.ensure_dirs()
    budget = budget_minutes * 60 if budget_minutes else None
    return Publisher(out, full=full, force=force, budget=budget).run(tickers=tickers, market=market)
