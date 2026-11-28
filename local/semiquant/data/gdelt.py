"""GDELT: news coverage of the world's conflicts, from the free GDELT DOC 2.0 API (no key).

GDELT reads news in 100+ languages every 15 minutes. Two things are used here:

* ``articles(query)``: the newest headlines for a search (title, link, outlet, time);
* ``timeline(query)``: how much of all coverage the search matches each day, so a surge stands out.

The API allows one request every 5 seconds, so every call goes through one throttle, retries once or twice on
"too many requests" and connection resets, and after repeated failures the module stops asking for ten minutes
(``GdeltBusy``) so a bad run costs seconds, not minutes. Results are cached on disk.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

from . import cache

API = "https://api.gdeltproject.org/api/v2/doc/doc"
UA = {"User-Agent": "SemiQuant research tool (personal use)"}
GAP = 5.5               # seconds between requests (the API asks for at least 5)
BLOCK_AFTER = 4         # consecutive failures before pausing
BLOCK_FOR = 600.0       # seconds to pause
HOUR = 3600

_lock = threading.Lock()
_state = {"last": 0.0, "fails": 0, "blocked_until": 0.0}

__all__ = ["articles", "timeline", "cached_timeline", "GdeltBusy", "paused", "reset"]


class GdeltBusy(RuntimeError):
    """GDELT is rate-limiting or unreachable; try again later."""


def paused() -> bool:
    """True while the module is backing off after repeated failures."""
    return time.time() < _state["blocked_until"]


def reset() -> None:
    """Forget the failure streak (tests, and a manual refresh)."""
    with _lock:
        _state.update({"last": 0.0, "fails": 0, "blocked_until": 0.0})


def _request(params: dict[str, Any]) -> bytes:
    with _lock:
        if time.time() < _state["blocked_until"]:
            raise GdeltBusy("GDELT is paused after repeated errors")
        last: Exception | None = None
        for attempt in range(2):                # one retry: a throttled address rarely recovers within seconds
            wait = _state["last"] + GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            _state["last"] = time.time()
            try:
                r = requests.get(API, params={"format": "json", **params}, headers=UA, timeout=30)
                if r.status_code == 429:
                    last = GdeltBusy("GDELT rate limit")
                    time.sleep(8)
                    continue
                r.raise_for_status()
                _state["fails"] = 0
                return r.content
            except requests.RequestException as exc:
                last = exc
                time.sleep(5)
        _state["fails"] += 1
        if _state["fails"] >= BLOCK_AFTER:
            _state["blocked_until"] = time.time() + BLOCK_FOR
        raise GdeltBusy(f"GDELT request failed: {type(last).__name__}: {str(last)[:120]}")


def _json(raw: bytes) -> dict:
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return {}
    import json
    try:
        d = json.loads(text)
    except ValueError as exc:
        # GDELT answers a bad query with plain text, e.g. "The specified phrase is too short."
        raise ValueError(f"GDELT: {text[:120]}") from exc
    return d if isinstance(d, dict) else {}


def _when(s: str | None) -> str | None:
    """'20261128T104500Z' -> '2026-11-28T10:45:00Z'."""
    try:
        return datetime.strptime(s or "", "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def parse_articles(d: dict, n: int = 10) -> list[dict]:
    """Headlines, newest first, one per distinct title (syndicated copies are dropped)."""
    seen: set[str] = set()
    out = []
    for a in d.get("articles") or []:
        title = " ".join(str(a.get("title") or "").split())
        key = "".join(ch for ch in title.lower() if ch.isalnum())[:80]
        if not title or not a.get("url") or key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "url": a["url"], "domain": a.get("domain") or "", "seen": _when(a.get("seendate")),
                    "country": a.get("sourcecountry") or ""})
    out.sort(key=lambda x: x["seen"] or "", reverse=True)
    return out[:n]


def articles(query: str, hours: int = 72, n: int = 8) -> list[dict]:
    """Newest English-language headlines matching ``query`` (GDELT syntax) in the last ``hours``."""
    q = f"{query} sourcelang:english"

    def load() -> list[dict]:
        d = _json(_request({"query": q, "mode": "artlist", "maxrecords": 75, "sort": "datedesc", "timespan": f"{int(hours)}h"}))
        return parse_articles(d, n)
    return cache.cached(f"gdelt:art:{hours}:{n}:{q}", 90 * 60, load, disk=True)


def parse_timeline(d: dict) -> list[tuple[str, float]]:
    """GDELT timeline -> [(YYYY-MM-DD, value)], hourly points averaged per day."""
    series = (d.get("timeline") or [{}])[0].get("data") or []
    days: dict[str, list[float]] = {}
    for p in series:
        w = _when(p.get("date"))
        v = p.get("value")
        if w and isinstance(v, (int, float)):
            days.setdefault(w[:10], []).append(float(v))
    return [(k, sum(v) / len(v)) for k, v in sorted(days.items())]


def _tl_key(query: str, mode: str, days: int) -> str:
    return f"gdelt:tl:{mode}:{days}:{query} sourcelang:english"


def cached_timeline(query: str, mode: str = "timelinevol", days: int = 100) -> list[tuple[str, float]] | None:
    """The timeline if it is already cached (never calls GDELT)."""
    return cache.peek(_tl_key(query, mode, days))


def timeline(query: str, mode: str = "timelinevol", days: int = 100) -> list[tuple[str, float]]:
    """Daily share of all news coverage (``timelinevol``, in %) or its average tone (``timelinetone``)."""
    q = f"{query} sourcelang:english"

    def load() -> list[tuple[str, float]]:
        pts = parse_timeline(_json(_request({"query": q, "mode": mode, "timespan": f"{int(days)}d"})))
        if not pts:
            raise ValueError("empty timeline")
        return pts
    return cache.cached(_tl_key(query, mode, days), 6 * HOUR, load, disk=True)
