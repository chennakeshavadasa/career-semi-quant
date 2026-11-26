"""User-level settings and storage: ~/.semiquant (override with SEMIQUANT_HOME).

Holds the disk cache, saved watchlists, the portfolio and exports. Nothing here is
ever sent anywhere: the only network traffic is to Yahoo Finance.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .universe import SEMIS

HOME = Path(os.environ.get("SEMIQUANT_HOME") or Path.home() / ".semiquant")
CACHE_DIR = HOME / "cache"
EXPORT_DIR = HOME / "exports"

DEFAULT_SETTINGS = {
    "quote_refresh_seconds": 30,     # browser polling of live quotes while a market is open
    "closed_refresh_seconds": 300,   # ... and while every market shown is closed
    "intraday_refresh_seconds": 60,  # 1-minute chart refresh
    "default_range": "6M",
    "risk_free_fallback": 0.04,
    "theme": "auto",
}

DEFAULT_WATCHLISTS = {
    "Tier A semis": [t for t, _, s, tier in SEMIS if tier == "A" and s != "Market"],
    "Tier B semis": [t for t, _, s, tier in SEMIS if tier == "B"],
    "My watchlist": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "SPY", "QQQ"],
    "US mega caps": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "V", "WMT", "XOM"],
}

_lock = threading.Lock()


def ensure_dirs() -> None:
    for d in (HOME, CACHE_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _read(name: str, default):
    p = HOME / name
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(name: str, obj) -> None:
    ensure_dirs()
    p = HOME / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, p)


def settings() -> dict:
    with _lock:
        return {**DEFAULT_SETTINGS, **(_read("settings.json", {}) or {})}


def save_settings(new: dict) -> dict:
    with _lock:
        cur = {**DEFAULT_SETTINGS, **(_read("settings.json", {}) or {})}
        cur.update({k: v for k, v in (new or {}).items() if k in DEFAULT_SETTINGS})
        _write("settings.json", cur)
        return cur


def watchlists() -> dict[str, list[str]]:
    with _lock:
        w = _read("watchlists.json", None)
        return w if isinstance(w, dict) and w else dict(DEFAULT_WATCHLISTS)


def save_watchlists(w: dict[str, list[str]]) -> dict[str, list[str]]:
    clean = {str(k)[:60]: [str(s).upper().strip()[:20] for s in v if str(s).strip()][:200]
             for k, v in (w or {}).items() if isinstance(v, list)}
    with _lock:
        _write("watchlists.json", clean)
    return clean


def portfolio() -> dict:
    with _lock:
        p = _read("portfolio.json", None)
    if not isinstance(p, dict):
        p = {"name": "My portfolio", "benchmark": "SPY", "cash": 0.0,
             "holdings": [{"ticker": "NVDA", "shares": 10, "cost": None},
                          {"ticker": "AVGO", "shares": 5, "cost": None},
                          {"ticker": "TSM", "shares": 8, "cost": None},
                          {"ticker": "ASML", "shares": 2, "cost": None}]}
    return p


def save_portfolio(p: dict) -> dict:
    with _lock:
        _write("portfolio.json", p)
    return p
