"""IMF PortWatch: daily ship traffic through 28 maritime chokepoints, and its log of disruption events.

PortWatch (portwatch.imf.org, with Oxford's Global Systems Institute) counts ships from satellite AIS
signals, one row per chokepoint per day: how many vessels passed (by type) and an estimate of the cargo
they carry. It is free and needs no key; the data lags about a week and is updated weekly. Licence:
CC BY 4.0, so the page credits it.

* ``chokepoints()``: the 28 chokepoints (name, position, yearly vessel count, main goods).
* ``daily(since)``: daily series per chokepoint, as parallel arrays.
* ``disruptions()``: PortWatch's event log (storms, quakes, and "trade disruptions" such as a closed strait).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from . import cache

BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
UA = {"User-Agent": "SemiQuant research tool (personal use)"}
HOUR = 3600
PAGE = 4000  # the service allows 10,000 rows per answer; smaller pages are kinder to it

# Event types in the disruptions database
EVENT_TYPES = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano", "DR": "Drought",
               "WF": "Wildfire", "OT": "Trade disruption"}

__all__ = ["chokepoints", "daily", "disruptions", "EVENT_TYPES"]


def _query(service: str, **params: Any) -> dict:
    """One query against a PortWatch feature service, with a few retries (the service is occasionally slow)."""
    p = {"f": "json", "returnGeometry": "false", **params}
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE}/{service}/FeatureServer/0/query", params=p, headers=UA, timeout=60)
            r.raise_for_status()
            d = r.json()
            if "error" in d:
                raise RuntimeError(f"PortWatch {service}: {str(d['error'])[:160]}")
            return d
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"PortWatch {service} failed: {type(last).__name__}: {str(last)[:160]}")


def _rows(d: dict) -> list[dict]:
    return [f.get("attributes") or {} for f in d.get("features", [])]


def _iso(ms: Any) -> str | None:
    """ArcGIS dates are epoch milliseconds (UTC)."""
    if ms in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000, timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_chokepoints(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if not r.get("portid") or not r.get("portname"):
            continue
        top = [t for t in (r.get("industry_top1"), r.get("industry_top2"), r.get("industry_top3")) if t and t != "None"]
        out.append({"id": r["portid"], "name": r["portname"], "lat": r.get("lat"), "lon": r.get("lon"),
                    "vessels_per_year": r.get("vessel_count_total"), "goods": top})
    out.sort(key=lambda c: -(c["vessels_per_year"] or 0))
    return out


def chokepoints() -> list[dict]:
    def load() -> list[dict]:
        d = _query("PortWatch_chokepoints_database", where="1=1", orderByFields="vessel_count_total DESC",
                   outFields="portid,portname,lat,lon,vessel_count_total,industry_top1,industry_top2,industry_top3")
        out = parse_chokepoints(_rows(d))
        if not out:
            raise ValueError("no chokepoints returned")
        return out
    return cache.cached("portwatch:chokepoints", 7 * 24 * HOUR, load, disk=True, accept=bool)


def parse_daily(rows: list[dict]) -> dict[str, dict]:
    """Rows (any order) -> {chokepoint id: parallel arrays sorted by date}.

    ``total`` = every vessel; ``tanker``, ``container``, ``dry_bulk`` by type; ``other`` = general cargo and
    ro-ro; ``tonnes`` = PortWatch's estimate of the cargo carried that day (metric tons).
    """
    by: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("portid") and r.get("date"):
            by.setdefault(r["portid"], []).append(r)
    out: dict[str, dict] = {}
    for cid, rs in by.items():
        rs.sort(key=lambda r: r["date"])
        n = lambda r, k: int(r.get(k) or 0)  # noqa: E731
        out[cid] = {
            "name": rs[-1].get("portname") or cid,
            "dates": [r["date"] for r in rs],
            "total": [n(r, "n_total") for r in rs],
            "tanker": [n(r, "n_tanker") for r in rs],
            "container": [n(r, "n_container") for r in rs],
            "dry_bulk": [n(r, "n_dry_bulk") for r in rs],
            "other": [max(0, n(r, "n_cargo") - n(r, "n_container") - n(r, "n_dry_bulk")) for r in rs],
            "tonnes": [n(r, "capacity") for r in rs],
        }
    return out


def daily(since: str) -> dict[str, dict]:
    """Daily traffic for every chokepoint from ``since`` (YYYY-MM-DD) to the latest published day."""
    def load() -> dict[str, dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            d = _query("Daily_Chokepoints_Data", where=f"date >= '{since}'", orderByFields="portid,date",
                       outFields="date,portid,portname,n_total,n_tanker,n_container,n_dry_bulk,n_cargo,capacity",
                       resultOffset=offset, resultRecordCount=PAGE)
            got = _rows(d)
            rows += got
            if len(got) < PAGE and not d.get("exceededTransferLimit"):
                break
            offset += len(got)
            if offset > 200_000:  # runaway guard
                break
        out = parse_daily(rows)
        if not out:
            raise ValueError("no daily chokepoint data returned")
        return out
    # PortWatch publishes weekly; refresh a few times a day at most
    return cache.cached(f"portwatch:daily:{since}", 6 * HOUR, load, disk=True, accept=bool)


def parse_disruptions(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        start = _iso(r.get("fromdate"))
        if not start:
            continue
        countries = [c.strip() for c in str(r.get("country") or "").replace(",", ";").split(";") if c.strip() and c.strip() != "None"]
        ports = [p.strip() for p in str(r.get("affectedports") or "").replace(",", ";").split(";") if p.strip()]
        kind = r.get("eventtype") or "OT"
        out.append({"id": r.get("eventid"), "type": kind, "type_label": EVENT_TYPES.get(kind, kind),
                    "name": r.get("htmlname") or r.get("eventname") or "", "code": r.get("eventname") or "",
                    "alert": (r.get("alertlevel") or "").upper(), "countries": countries,
                    "start": start, "end": _iso(r.get("todate")), "ports": ports, "n_ports": r.get("n_affectedports") or 0,
                    "severity": (r.get("severitytext") or "").strip(), "updated": _iso(r.get("editdate"))})
    out.sort(key=lambda e: e["start"], reverse=True)
    return out


def disruptions() -> list[dict]:
    """Every logged event, newest first. ``end`` is None while it is ongoing."""
    def load() -> list[dict]:
        d = _query("portwatch_disruptions_database", where="1=1", orderByFields="fromdate DESC", resultRecordCount=2000,
                   outFields="eventid,eventtype,eventname,htmlname,alertlevel,country,fromdate,todate,severitytext,"
                             "affectedports,n_affectedports,editdate")
        return parse_disruptions(_rows(d))
    return cache.cached("portwatch:disruptions", 3 * HOUR, load, disk=True)
