"""The World risk page: wars and flashpoints, shipping chokepoints, the markets that react, and what it all means
for chip supply.

Three live sources, each optional (a failing source leaves its section empty instead of failing the page):

* IMF PortWatch: ships per day through 28 straits and canals, and its disruption log;
* GDELT: headlines and coverage trends per flashpoint (one call per flashpoint, see ``news``);
* Yahoo Finance: prices of the assets that transmit a shock (oil, gas, freight, havens, Asian chip markets).

Plus ``semiquant.world``: the curated map of what flows through each strait and what each flashpoint can touch.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from .. import world as W
from ..analytics import worldrisk as wr
from ..analytics._util import clean, jsonable
from ..data import gdelt, portwatch, yahoo
from ..universe import ALL_META
from .common import memo

HISTORY_DAYS = 1200          # three years of baseline + the same weeks of earlier years + a month of holdout
DETAIL_DAYS = 760            # daily chart on a chokepoint's page
STATUS_TEXT = {"severe": "Severe disruption", "disrupted": "Disrupted", "watch": "Below normal", "surge": "Above normal",
               "normal": "Normal", "low": "Little traffic"}
THEATRES = {t["id"]: t for t in W.THEATRES}


def _since() -> str:
    return (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()


def _r(v, nd: int = 1):
    return None if v is None else round(float(v), nd)


# ─── chokepoints ─────────────────────────────────────────────────────────────────────────────
def _stats_all() -> tuple[list[dict], dict, dict[str, dict]]:
    """(chokepoint list, per-chokepoint daily arrays, per-chokepoint statistics)."""
    meta = portwatch.chokepoints()
    daily = portwatch.daily(_since())
    stats: dict[str, dict] = {}
    for c in meta:
        d = daily.get(c["id"])
        if not d:
            continue
        s = wr.transit_stats(d["dates"], d["total"], d["tonnes"], {k: d[k] for k in wr.TYPES})
        if s:
            stats[c["id"]] = s
    return meta, daily, stats


def _row(c: dict, s: dict, events: list[dict]) -> dict:
    info = W.CHOKEPOINTS.get(c["id"], {})
    since, source = s.get("since"), ("estimate" if s.get("since") else None)
    # PortWatch logs big closures as events with an exact start date: prefer it over the estimate from the counts
    for e in events:
        if c["id"] in e["ports"] and e["end"] is None and s["status"] in ("severe", "disrupted"):
            since, source = e["start"], "portwatch"
            break
    days = (date.fromisoformat(s["last_date"]) - date.fromisoformat(since)).days if since else None
    return {"id": c["id"], "name": c["name"], "lat": c["lat"], "lon": c["lon"], "vessels_per_year": c["vessels_per_year"],
            "goods": c["goods"], "status": s["status"], "status_text": STATUS_TEXT[s["status"]], "last_date": s["last_date"],
            "avg7": _r(s["avg7"]), "avg28": _r(s["avg28"]), "base": _r(s["base"]), "chg7": _r(s["chg7"], 3), "chg28": _r(s["chg28"], 3),
            "chg": _r(s["chg"], 3), "yoy": _r(s.get("yoy"), 3), "since": since, "since_source": source, "days": days, "share": _r(s.get("share"), 4),
            "types": {k: {"avg7": _r(v["avg7"]), "base": _r(v["base"]), "chg": _r(v["chg"], 3)} for k, v in (s.get("types") or {}).items()},
            "weekly": [_r(x) for x in s["weekly"]], "role": info.get("role", ""), "carries": info.get("carries", ""),
            "if_closed": info.get("if_closed", ""), "theatres": info.get("theatres", []), "assets": info.get("assets", [])}


def _events(limit: int = 40) -> list[dict]:
    """Ongoing events, and those that ended within the last six months."""
    cut = (date.today() - timedelta(days=180)).isoformat()
    keep = [e for e in portwatch.disruptions() if e["end"] is None or e["end"] >= cut]
    return keep[:limit]


def _headline(rows: list[dict]) -> str | None:
    bad = [r for r in rows if r["status"] in ("severe", "disrupted")]
    if not bad:
        return None
    r = max(bad, key=lambda x: (wr.STATUS_RANK[x["status"]], x["days"] or 0))
    since = f", since {datetime.fromisoformat(r['since']).strftime('%-d %b %Y')}" if r["since"] else ""
    return (f"{r['name']}: {r['avg7']:.0f} ships a day against about {r['base']:.0f} normally "
            f"({r['chg'] * 100:+.0f}%){since}.")


# ─── markets ─────────────────────────────────────────────────────────────────────────────────
def _ret(c: pd.Series, n: int) -> float | None:
    return float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n and c.iloc[-1 - n] else None


def markets() -> list[dict]:
    h = yahoo.daily_many(list(W.ASSETS), "1y")
    out = []
    for sym, meta in W.ASSETS.items():
        d = h.get(sym)
        if d is None or d.empty:
            continue
        c = d["close"].dropna()
        if len(c) < 30:
            continue
        r5 = c.pct_change(5).dropna()
        sd = float(r5.std()) if len(r5) > 20 else None
        last5 = _ret(c, 5)
        out.append({"symbol": sym, "label": meta["label"], "group": meta["group"], "price": _r(c.iloc[-1], 4),
                    "chg1d": _r(_ret(c, 1), 4), "chg5d": _r(last5, 4), "chg1m": _r(_ret(c, 21), 4), "chg3m": _r(_ret(c, 63), 4),
                    "z5": _r(last5 / sd, 2) if (sd and last5 is not None) else None, "spark": [_r(x, 4) for x in c.iloc[-60:]]})
    return out


# ─── flashpoints ─────────────────────────────────────────────────────────────────────────────
def _terms(query: str) -> list[str]:
    """The words a headline must contain one of: the first parenthesised group of the GDELT query."""
    import re
    grp = re.match(r"\s*\(([^)]*)\)", query)
    body = grp.group(1) if grp else query
    parts = re.findall(r'"([^"]+)"|(\S+)', body)
    return [(a or b).lower() for a, b in parts if (a or b).upper() != "OR" and len(a or b) > 2]


def _relevant(title: str, terms: list[str]) -> bool:
    t = title.lower()
    return len(t) >= 25 and len(t.split()) >= 4 and (not terms or any(w in t for w in terms))


def _warm_trend(query: str) -> None:
    try:
        gdelt.timeline(query, "timelinevol", 100)
    except Exception:  # noqa: BLE001 - best effort; the next page load tries again
        pass


def news(theatre_id: str, quick: bool = False) -> dict:
    """Headlines and the coverage trend for one flashpoint. Raises if GDELT gave neither.

    ``quick`` (the local server): use the trend only if it is cached and fetch it in the background otherwise, so
    every card gets its headlines after one GDELT call instead of two."""
    t = THEATRES.get(theatre_id)
    if not t:
        raise KeyError(theatre_id)
    errors: list[str] = []
    heads: list[dict] = []
    try:
        terms = _terms(t["query"])
        heads = [a for a in gdelt.articles(t["query"], hours=72, n=30) if _relevant(a["title"], terms)][:8]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"headlines: {type(exc).__name__}: {str(exc)[:100]}")
    attn, series = None, None
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if quick:
            raw = gdelt.cached_timeline(t["query"], "timelinevol", 100)
            if raw is None:
                threading.Thread(target=_warm_trend, args=(t["query"],), daemon=True).start()
                raise LookupError("coverage trend is loading")
        else:
            raw = gdelt.timeline(t["query"], "timelinevol", 100)
        tl = [(d, v) for d, v in raw if d < today]  # today is a partial day
        vals = [v for _, v in tl]
        attn = wr.attention(vals)
        series = [[d, _r(v, 4)] for d, v in tl[-60:]]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"trend: {type(exc).__name__}: {str(exc)[:100]}")
    if not heads and attn is None:
        raise RuntimeError("; ".join(errors) or "no news")
    # "available": false (near the start of the file) makes the publisher retry a partial answer at every refresh
    return jsonable({"id": theatre_id, "available": not errors, "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "headlines": heads,
                     "attention": {k: _r(v, 3) for k, v in attn.items()} if attn else None, "series": series, "errors": errors})


def _cached_attention(theatre_id: str) -> float | None:
    """Coverage z-score from the cache only (never triggers a GDELT call)."""
    tl = gdelt.cached_timeline(THEATRES[theatre_id]["query"], "timelinevol", 100)
    a = wr.attention([v for _, v in tl]) if tl else None
    return a["z"] if a else None


# ─── chip supply ─────────────────────────────────────────────────────────────────────────────
def _semis(rows: list[dict]) -> list[dict]:
    by = {r["id"]: r for r in rows}
    syms = sorted({s for x in W.SEMIS for s in x["tickers"]})
    try:
        q = yahoo.quotes(syms) if syms else {}
    except Exception:  # noqa: BLE001 - quotes are decoration here
        q = {}
    out = []
    for x in W.SEMIS:
        sig = []
        level = "calm"
        for cid in x["chokepoints"]:
            r = by.get(cid)
            if not r:
                continue
            sig.append({"kind": "chokepoint", "id": cid, "name": r["name"], "status": r["status"], "status_text": r["status_text"],
                        "avg7": r["avg7"], "base": r["base"], "chg": r["chg"]})
            if r["status"] in ("severe", "disrupted"):
                level = "alert"
            elif r["status"] == "watch" and level != "alert":   # above-normal traffic is shown but is not a warning
                level = "watch"
        for tid in x["theatres"]:
            z = _cached_attention(tid)
            sig.append({"kind": "theatre", "id": tid, "name": THEATRES[tid]["name"], "z": _r(z, 2)})
            if z is not None and z >= 2 and level == "calm":
                level = "watch"
        out.append({"id": x["id"], "label": x["label"], "why": x["why"], "level": level, "signals": sig,
                    "tickers": [{"symbol": s, "name": (ALL_META.get(s) or {}).get("name", s),
                                 "change_pct": clean((q.get(s) or {}).get("change_pct")), "price": clean((q.get(s) or {}).get("price"))}
                                for s in x["tickers"]]})
    order = {"alert": 0, "watch": 1, "calm": 2}
    out.sort(key=lambda x: order[x["level"]])
    return out


# ─── the page ────────────────────────────────────────────────────────────────────────────────
def overview() -> dict:
    return memo("world:overview", 20 * 60, _overview)


def _overview() -> dict:
    t0 = time.time()
    errors: list[str] = []
    src = {"portwatch": {"ok": False}, "yahoo": {"ok": False}, "gdelt": {"ok": None}}
    rows: list[dict] = []
    events: list[dict] = []
    summary: dict = {}
    try:
        events = _events()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"events: {type(exc).__name__}: {str(exc)[:120]}")
    try:
        meta, _daily, stats = _stats_all()
        rows = [_row(c, stats[c["id"]], events) for c in meta if c["id"] in stats]
        rows.sort(key=lambda r: (-wr.STATUS_RANK[r["status"]], r["chg"] if r["status"] != "surge" else -r["chg"]))
        summary = wr.world_summary(stats)
        src["portwatch"] = {"ok": True, "last_date": max(r["last_date"] for r in rows) if rows else None}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"chokepoints: {type(exc).__name__}: {str(exc)[:120]}")
    mk: list[dict] = []
    try:
        mk = markets()
        src["yahoo"] = {"ok": bool(mk)}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"markets: {type(exc).__name__}: {str(exc)[:120]}")
    if not rows and not mk:
        raise RuntimeError("; ".join(errors) or "no data")
    longest = max((r for r in rows if r["status"] in ("severe", "disrupted") and r["days"] is not None), key=lambda r: r["days"], default=None)
    ev_names = {c["id"]: c["name"] for c in rows}
    ev = [{**e, "chokepoints": [{"id": p, "name": ev_names.get(p, p)} for p in e["ports"] if p.startswith("chokepoint")],
           "ongoing": e["end"] is None} for e in events]
    theatres = [{"id": t["id"], "name": t["name"], "region": t["region"], "chokepoints": [{"id": c, "name": ev_names.get(c, c)} for c in t["chokepoints"]],
                 "assets": t["assets"], "affects": t["affects"]} for t in W.THEATRES]
    return jsonable({
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sources": src, "errors": errors,
        "summary": {**summary, "headline": _headline(rows), "longest": ({"id": longest["id"], "name": longest["name"], "days": longest["days"],
                                                                         "since": longest["since"], "chg": longest["chg"]} if longest else None),
                    "markets_stressed": sum(1 for m in mk if m["z5"] is not None and abs(m["z5"]) >= 2)},
        "chokepoints": rows, "events": ev, "theatres": theatres, "markets": mk, "semis": _semis(rows) if rows else [],
        "asset_groups": W.ASSET_GROUPS, "seconds": round(time.time() - t0, 1)})


def chokepoint(cid: str) -> dict:
    """One chokepoint's daily series (about two years) for the detail chart."""
    def build() -> dict:
        meta, daily, stats = _stats_all()
        c = next((m for m in meta if m["id"] == cid), None)
        d = daily.get(cid)
        if not c or not d or cid not in stats:
            raise KeyError(cid)
        n = min(DETAIL_DAYS, len(d["dates"]))
        s = stats[cid]
        return jsonable({"id": cid, "name": c["name"], "dates": d["dates"][-n:], **{k: d[k][-n:] for k in ("total", "tanker", "container", "dry_bulk", "other")},
                         "base": _r(s["base"]), "base_seasonal": _r(s.get("base_seasonal")), "status": s["status"], "avg7": _r(s["avg7"])})
    return memo(f"world:chokepoint:{cid}", 3 * 3600, build)
