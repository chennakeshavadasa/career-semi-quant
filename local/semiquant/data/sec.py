"""Fresh SEC filings about a company, from EDGAR full-text search (minutes after filing, no API key).

* Form 4: a trade by an executive, a director or a 10%+ owner (due within 2 business days).
* Form 144: notice of a planned sale by an executive or a major holder (filed on or before the sale day:
  the earliest public warning of insider selling).
* Schedule 13D / 13G: a holder crossed 5% of the company. 13D = active intent (an activist), within
  5 business days; 13G = passive (index funds, big asset managers). "/A" = an amended (changed) stake.

The search gives who filed, when, and a link; the amounts of a Form 4 come from the insider table
(Yahoo). EDGAR's document archive requires a contact address in every request, the search does not.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import date, timedelta

import requests

from . import cache

EFTS = "https://efts.sec.gov/LATEST/search-index"
UA = {"User-Agent": "SemiQuant research tool (personal use)"}
# Base forms only: the search adds the amendments ("/A") itself, and listing them drops results.
STAKE_FORMS = ["SCHEDULE 13D", "SCHEDULE 13G", "SC 13D", "SC 13G"]

__all__ = ["cik", "filings", "recent", "STAKE_FORMS"]


_pace = threading.Lock()
_last = [0.0]


def _search(params: dict) -> dict:
    with _pace:  # SEC fair access: at most ~6 requests a second from this process
        wait = _last[0] + 0.16 - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    r = requests.get(EFTS, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def cik(sym: str) -> str | None:
    """The company's 10-digit CIK, or None (funds, foreign listings and indices have none)."""
    s = (sym or "").upper()

    def load():
        j = _search({"keysTyped": s})
        for h in j.get("hits", {}).get("hits", []):
            ticks = [t.strip().upper() for t in str(h.get("_source", {}).get("tickers") or "").split(",")]
            if s in ticks or s.replace("-", ".") in ticks:
                return str(h["_id"]).zfill(10)
        return ""
    return cache.cached(f"sec:cik:{s}", 30 * 86400.0, load, disk=True) or None


def _name(display: str) -> str:
    """'HUANG JEN HSUN  (CIK 0001197649)' -> 'HUANG JEN HSUN'; drops the ticker part of a company."""
    return display.split("  (")[0].strip()


def filings(sym: str, forms: list[str], days: int) -> list[dict]:
    """Filings of the given forms that involve the company in the last ``days`` days, newest first:
    form, filed date, period (the trade date of a Form 4), the other party (the insider, or the holder of a
    stake) and a link. Stake filings where the company is the holder (not the subject) are left out."""
    c = cik(sym)
    if not c:
        return []
    end, start = date.today(), date.today() - timedelta(days=days)

    def load():
        out, offset = [], 0
        while True:
            j = _search({"ciks": c, "forms": ",".join(forms), "dateRange": "custom", "startdt": start.isoformat(),
                         "enddt": end.isoformat(), "from": str(offset)})
            hits = j.get("hits", {}).get("hits", [])
            for h in hits:
                s = h["_source"]
                ciks = [x.zfill(10) for x in s.get("ciks", [])]
                names = s.get("display_names", [])
                form = s.get("form", "")
                if re.search(r"13[DG]", form) and (not ciks or ciks[0] != c):
                    continue  # a stake the company holds in another company: the first entity is the subject
                others = [_name(n) for n, k in zip(names, ciks) if k != c]
                adsh, _, doc = str(h["_id"]).partition(":")
                folder = f"https://www.sec.gov/Archives/edgar/data/{int(c)}/{adsh.replace('-', '')}"
                xsl = s.get("xsl")
                out.append({"form": form, "filed": s.get("file_date"), "period": s.get("period_ending"),
                            "party": ", ".join(others) or None,
                            "url": f"{folder}/{xsl}/{doc}" if xsl and doc.endswith(".xml") else f"{folder}/{doc}"})
            offset += len(hits)
            total = (j.get("hits", {}).get("total") or {}).get("value", 0)
            if not hits or offset >= min(total, 400):
                break
        out.sort(key=lambda f: (f["filed"] or "", f["period"] or ""), reverse=True)
        return out
    return cache.cached(f"sec:filings:{c}:{','.join(forms)}:{days}", 3600.0, load, disk=True)


def recent(sym: str) -> dict:
    """Form 4s and 144s of the last 90 days and stake filings of the last 2 years (two searches)."""
    quick = filings(sym, ["4", "144"], 90)
    return {"form4": [f for f in quick if f["form"].startswith("4")], "form144": [f for f in quick if f["form"].startswith("144")],
            "stakes": filings(sym, STAKE_FORMS, 730)}
