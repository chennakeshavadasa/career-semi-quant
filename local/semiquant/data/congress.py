"""Stock trades by members of Congress (STOCK Act Periodic Transaction Reports), from the official sources.

* House: the Clerk's yearly index of filings (``<year>FD.zip``, filing type "P" = periodic transaction
  report) and each electronic report's PDF, read with pypdf. Paper filings are scanned images: they are
  counted and linked, but their trades can't be read.
* Senate: the eFD search (after accepting its terms of use, as a browser does), report type 11 = periodic
  transaction report, and each electronic report's HTML table. Paper filings are linked, not read.
* Members, parties, states and committee seats: the @unitedstates congress-legislators dataset.

Members must report a trade within 45 days (30 days after they learn of it), so the newest trades are always
weeks old. Amounts are reported as ranges ($1,001 - $15,000, ...). Every filing is read once and kept on disk:
filings never change (an amendment is a new filing).
"""
from __future__ import annotations

import io
import re
import threading
import time
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any

import requests

from . import bargo, cache, paper_ptr

HOUSE = "https://disclosures-clerk.house.gov/public_disc"
SENATE = "https://efdsearch.senate.gov"
LEGISLATORS = "https://unitedstates.github.io/congress-legislators"
UA = {"User-Agent": "Mozilla/5.0 (compatible; SemiQuant personal research tool)"}
DAY = 86400.0
FOREVER = 3650 * DAY  # a filing never changes
READ_BUDGET_S: float | None = None  # the publisher caps how long one run spends reading new filings

__all__ = ["members", "trades", "trades_for", "refresh", "parse_house_text", "parse_senate_html", "parse_amount",
           "yahoo_ticker", "COMMITTEE_NAMES"]


# ─── small parsers (pure, tested) ─────────────────────────────────────────────

def parse_amount(text: str) -> tuple[int | None, int | None]:
    """'$1,001 - $15,000' -> (1001, 15000); 'Over $50,000,000' / '$50,000,001 +' -> (50000001, None)."""
    t = (text or "").replace(",", "").replace("–", "-")
    m = re.search(r"\$\s*(\d+)\s*-\s*\$\s*(\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?:over|>)\s*\$\s*(\d+)", t, re.I)
    if m:
        return int(m.group(1)) + 1, None
    m = re.search(r"\$\s*(\d+)\s*\+", t)
    if m:
        return int(m.group(1)), None
    return None, None


def yahoo_ticker(raw: str | None) -> str | None:
    """A disclosed ticker as Yahoo spells it ('BRK.B' -> 'BRK-B'); None for '--', blanks and non-tickers."""
    t = (raw or "").strip().upper().replace("$", "")
    t = re.sub(r"^(?:NYSE|NASDAQ|NYSEARCA|AMEX|OTC)\s*[:\-]\s*", "", t)
    if t in ("N/A", "NA", "NONE", "TBD"):
        return None
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,5}(?:[.\-/][A-Z0-9]{1,2})?", t):
        return None
    return re.sub(r"[./]", "-", t)


def _kind(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t.startswith(("p", "purchase")):
        return "buy"
    if "partial" in t:
        return "sell_partial"
    if t.startswith(("s", "sale")):
        return "sell"
    if t.startswith(("e", "exchange")):
        return "exchange"
    return None


def _iso(d: str) -> str | None:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return None


_TICKER_IN_ASSET = re.compile(r"\(([A-Z][A-Z0-9]{0,5}(?:[.\-/][A-Z0-9]{1,2})?)\)")
# Lines of the House form that are labels, not trades. The PDF's heading font drops most letters, so a
# label like "Filing Status: New" comes out as "F      S     : New".
_HOUSE_NOISE = re.compile(
    r"^(?:[A-Z](?:\s{2,}[A-Z]?)*\s*(?::.*)?|ID Owner Asset Transaction|Type|Date Notification|Date|Amount Cap\.|"
    r"Gains >|\$200\?|Filing ID #\d+|Clerk of the House.*|Name:.*|Status:.*|State/District:.*|Yes\s+No)$")
_HOUSE_END = re.compile(r"^\* For the complete list|^I\s{2,}P\s{2,}O|^C\s{2,}S\s*$|^I CERTIFY")
_HOUSE_ENTRY = re.compile(
    r"(?:^|\n)(?:(?P<owner>SP|JT|DC)\s+)?(?P<asset>[^\n][^\[]*?)\s*\[(?P<atype>[A-Z]{2})\]\s*"
    r"(?P<type>P|S\s*\(partial\)|S|E)\s+(?P<traded>\d{1,2}/\d{1,2}/\d{4})\s+(?P<notified>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<amount>(?:Spouse/DC\s+)?Over\s+\$[\d,]+|\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+\s*\+)")


def parse_house_text(text: str) -> list[dict]:
    """Trades in the text of an electronic House periodic transaction report (all pages)."""
    keep, on = [], True
    # pypdf turns the glyphs the heading font lacks into NULs: "F\x00\x00 S\x00: New" is "Filing Status: New"
    for raw in (text or "").replace("\x00", " ").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("ID Owner Asset Transaction"):
            on = True  # the table header, repeated on every page
            continue
        if _HOUSE_END.search(line):
            on = False
            continue
        if on and not _HOUSE_NOISE.match(line):
            keep.append(line)
    out = []
    for m in _HOUSE_ENTRY.finditer("\n".join(keep)):
        asset = re.sub(r"\s+", " ", m.group("asset")).strip(" -")
        tick = _TICKER_IN_ASSET.findall(asset)
        lo, hi = parse_amount(m.group("amount"))
        out.append({"owner": {"SP": "Spouse", "JT": "Joint", "DC": "Child"}.get(m.group("owner") or "", "Self"),
                    "asset": re.sub(r"\s*\([A-Z0-9.\-/]+\)\s*$", "", asset) or asset,
                    "ticker": yahoo_ticker(tick[-1]) if tick else None,
                    "asset_type": {"ST": "Stock", "OP": "Option", "EF": "ETF", "MF": "Mutual fund", "GS": "Government bond",
                                   "CS": "Corporate bond", "PS": "Stock", "CT": "Crypto"}.get(m.group("atype"), m.group("atype")),
                    "type": _kind(m.group("type")), "traded": _iso(m.group("traded")),
                    "notified": _iso(m.group("notified")), "amount_lo": lo, "amount_hi": hi})
    return out


def _cell(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def parse_senate_html(html: str) -> list[dict]:
    """Trades in an electronic Senate periodic transaction report page."""
    body = re.search(r"<tbody>(.*?)</tbody>", html or "", re.S)
    if not body:
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
        cells = [_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 8:
            continue
        _, traded, owner, ticker, asset, atype, kind, amount = cells[:8]
        lo, hi = parse_amount(amount)
        asset = re.sub(r"\s*(?:Company|Description|Rate/Coupon|Matures):.*$", "", asset).strip()
        out.append({"owner": owner if owner and owner != "--" else "Self", "asset": asset,
                    "ticker": yahoo_ticker(ticker), "asset_type": atype, "type": _kind(kind),
                    "traded": _iso(traded), "notified": None, "amount_lo": lo, "amount_hi": hi,
                    "comment": cells[8] if len(cells) > 8 and cells[8] != "--" else None})
    return out


# ─── members and committees ──────────────────────────────────────────────────

def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower().strip()


COMMITTEE_NAMES: dict[str, str] = {}


def _get(url: str, timeout: float = 30, **kw) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def members() -> dict:
    """{'by_id': {bioguide: member}, 'house': {(state, district): member}, 'senate': [member]} with each member's
    party (D/R/I), state, chamber and committee seats (top-level committees, with Chair / Ranking titles)."""

    def load():
        people = _get(f"{LEGISLATORS}/legislators-current.json").json()
        comms = _get(f"{LEGISLATORS}/committees-current.json").json()
        seats = _get(f"{LEGISLATORS}/committee-membership-current.json").json()
        names = {c["thomas_id"]: c["name"] for c in comms}
        by_id = {}
        for p in people:
            t = p["terms"][-1]
            n = p["name"]
            by_id[p["id"]["bioguide"]] = {
                "bioguide": p["id"]["bioguide"], "name": n.get("official_full") or f"{n['first']} {n['last']}",
                "first": n["first"], "last": n["last"], "nickname": n.get("nickname"),
                "chamber": "Senate" if t["type"] == "sen" else "House", "state": t["state"],
                "district": t.get("district"), "party": (t.get("party") or "?")[0], "committees": []}
        for code, rows in seats.items():
            if len(code) != 4 or code not in names:  # subcommittees have longer codes
                continue
            for r in rows:
                m = by_id.get(r.get("bioguide"))
                if m:
                    m["committees"].append({"code": code, "name": names[code], "title": r.get("title")})
        house = {(m["state"], int(m["district"] or 0)): m for m in by_id.values() if m["chamber"] == "House"}
        senate = [m for m in by_id.values() if m["chamber"] == "Senate"]
        return {"by_id": by_id, "house": house, "senate": senate, "committee_names": names}

    data = cache.cached("congress:members", DAY, load, disk=True)
    COMMITTEE_NAMES.update(data["committee_names"])
    return data


def _match_house(people: dict, last: str, first: str, state_dst: str) -> dict | None:
    m = re.match(r"([A-Z]{2})(\d+)", state_dst or "")
    if m:
        hit = people["house"].get((m.group(1), int(m.group(2))))
        if hit and _fold(hit["last"]).split()[-1] in _fold(last):
            return hit
    cands = [x for x in people["by_id"].values() if x["chamber"] == "House" and _fold(x["last"]) == _fold(last)]
    if m:
        cands = [x for x in cands if x["state"] == m.group(1)] or cands
    return cands[0] if len(cands) == 1 else None


def _match_senate(people: dict, last: str, first: str) -> dict | None:
    cands = [x for x in people["senate"] if _fold(x["last"]) == _fold(last)]
    if len(cands) > 1:
        f = _fold(first).split()[0] if first else ""
        cands = [x for x in cands if f and (_fold(x["first"]).startswith(f) or _fold(x.get("nickname") or "").startswith(f))]
    return cands[0] if len(cands) == 1 else None


# ─── House ───────────────────────────────────────────────────────────────────

def _house_index(year: int) -> list[dict]:
    def load():
        z = zipfile.ZipFile(io.BytesIO(_get(f"{HOUSE}/financial-pdfs/{year}FD.zip", timeout=60).content))
        root = ET.fromstring(z.read(f"{year}FD.xml"))
        out = []
        for m in root:
            d = {c.tag: (c.text or "").strip() for c in m}
            if d.get("FilingType") != "P":
                continue
            out.append({"id": d["DocID"], "year": year, "last": d.get("Last", ""), "first": d.get("First", ""),
                        "state_dst": d.get("StateDst", ""), "filed": _iso(d.get("FilingDate", ""))})
        return out
    fresh = year >= date.today().year
    return cache.cached(f"congress:house-index:{year}", 3 * 3600 if fresh else 7 * DAY, load, disk=True)


def _house_url(f: dict) -> str:
    return f"{HOUSE}/ptr-pdfs/{f['year']}/{f['id']}.pdf"


def _house_filing(f: dict) -> dict:
    """One House report, read once and kept. Electronic reports have a text layer; paper reports are scanned
    images, read with OCR (``paper_ptr``) when Tesseract is installed. A scan stored as unreadable before OCR was
    available (or by an older reader) is read again."""
    key = f"congress:house:{f['id']}"

    def load():
        from pypdf import PdfReader
        pdf = PdfReader(io.BytesIO(_get(_house_url(f), timeout=60).content))
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        rows = parse_house_text(text)
        if rows or "Notification" in text:
            return {"rows": rows, "readable": True}
        if len(text.strip()) < 40:                      # no text layer: a scanned paper report
            if not paper_ptr.available():
                return {"rows": [], "readable": False, "scan": True, "ocr": 0}
            filed = date.fromisoformat(f["filed"]) if f.get("filed") else None
            rows = paper_ptr.read_pdf(pdf, latest=filed)
            return {"rows": rows, "readable": bool(rows), "scan": True, "ocr": paper_ptr.VERSION}
        return {"rows": [], "readable": False, "scan": False}
    got = cache.cached(key, FOREVER, load, disk=True)
    if _stale_scan(got):
        got = load()
        cache.put(key, got, FOREVER, disk=True)
    return got


def _stale_scan(got: dict | None) -> bool:
    """A stored report that is a scan read without OCR, or by an older version of the reader, while OCR works now."""
    return bool(got) and not got.get("readable") and paper_ptr.available() and (
        got.get("ocr", 0) < paper_ptr.VERSION) and got.get("scan", "ocr" not in got)


# ─── Senate ──────────────────────────────────────────────────────────────────

_senate_lock = threading.Lock()
_senate: dict[str, Any] = {"session": None, "at": 0.0}


def _senate_session() -> requests.Session:
    """A session that has accepted the eFD terms of use (renewed every 20 minutes)."""
    with _senate_lock:
        if _senate["session"] is not None and time.time() - _senate["at"] < 1200:
            return _senate["session"]
        s = requests.Session()
        s.headers.update(UA)
        home = s.get(f"{SENATE}/search/home/", timeout=30)
        home.raise_for_status()
        tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', home.text)
        if not tok:
            raise RuntimeError("Senate eFD: the terms-of-use form changed")
        s.post(f"{SENATE}/search/home/", data={"prohibition_agreement": "1", "csrfmiddlewaretoken": tok.group(1)},
               headers={"Referer": f"{SENATE}/search/home/"}, timeout=30).raise_for_status()
        _senate.update(session=s, at=time.time())
        return s


def _senate_index(since: date) -> list[dict]:
    def load():
        s = _senate_session()
        csrf = s.cookies.get("csrftoken") or ""
        out, start = [], 0
        while True:
            q = {"start": str(start), "length": "100", "report_types": "[11]", "filer_types": "[]",
                 "submitted_start_date": since.strftime("%m/%d/%Y 00:00:00"), "submitted_end_date": "",
                 "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "", "last_name": "",
                 "csrfmiddlewaretoken": csrf}
            r = s.post(f"{SENATE}/search/report/data/", data=q, timeout=60,
                       headers={"Referer": f"{SENATE}/search/", "X-CSRFToken": csrf})
            r.raise_for_status()
            j = r.json()
            for first, last, display, link, filed in j.get("data", []):
                href = re.search(r'href="([^"]+)"', link)
                if not href:
                    continue
                disp = re.match(r"\s*([^,]+),\s*([^(]+)", display or "")
                out.append({"id": href.group(1).rstrip("/").split("/")[-1], "url": SENATE + href.group(1),
                            "paper": "/paper/" in href.group(1), "first": (disp.group(2) if disp else first).strip(),
                            "last": (disp.group(1) if disp else last).strip(), "filed": _iso(filed),
                            "title": _cell(link)})
            start += 100
            if start >= int(j.get("recordsFiltered") or 0) or not j.get("data"):
                return out
    return cache.cached(f"congress:senate-index:{since.isoformat()}", 3 * 3600, load, disk=True)


def _senate_filing(f: dict) -> dict:
    def load():
        if f["paper"]:
            return {"rows": [], "readable": False}
        r = _senate_session().get(f["url"], timeout=60)
        r.raise_for_status()
        if "prohibition_agreement" in r.text:  # the session expired: accept the terms again
            _senate["session"] = None
            r = _senate_session().get(f["url"], timeout=60)
        return {"rows": parse_senate_html(r.text), "readable": True}
    return cache.cached(f"congress:senate:{f['id']}", FOREVER, load, disk=True)


# ─── all trades ──────────────────────────────────────────────────────────────

ERRORS: dict[str, str] = {}  # source -> last failure (a chamber's site down must not hide the other chamber)


def _filings(days: int) -> list[tuple[str, dict]]:
    since = date.today() - timedelta(days=days)
    out: list[tuple[str, dict]] = []
    for y in range(since.year, date.today().year + 1):
        try:
            out += [("House", f) for f in _house_index(y) if (f["filed"] or "") >= since.isoformat()]
            ERRORS.pop(f"house-{y}", None)
        except Exception as exc:  # noqa: BLE001
            ERRORS[f"house-{y}"] = f"House Clerk index {y}: {type(exc).__name__}: {str(exc)[:120]}"
    try:
        out += [("Senate", f) for f in _senate_index(since)]
        ERRORS.pop("senate", None)
    except Exception as exc:  # noqa: BLE001
        ERRORS["senate"] = f"Senate eFD: {type(exc).__name__}: {str(exc)[:120]}"
    return out


def refresh(days: int = 400, budget_s: float | None = None, workers: int = 6) -> dict:
    """Read every filing of the last ``days`` days that isn't on disk yet (stops starting new ones after
    ``budget_s`` seconds). Returns counts; the rest is read next time."""
    t0, todo = time.time(), _filings(days)
    todo.sort(key=lambda it: it[1].get("filed") or "", reverse=True)   # newest first: the freshest trades appear first
    stats = {"filings": len(todo), "read": 0, "failed": 0, "skipped": 0}

    def one(item):
        chamber, f = item
        if budget_s is not None and time.time() - t0 > budget_s and _unread(chamber, f):
            stats["skipped"] += 1
            return
        try:
            (_house_filing if chamber == "House" else _senate_filing)(f)
            stats["read"] += 1
        except Exception:  # noqa: BLE001 - a missing or broken filing is retried next time
            stats["failed"] += 1

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def _stored(chamber: str, f: dict) -> dict | None:
    key = f"congress:{chamber.lower()}:{f['id']}"
    got = cache.peek(key)
    if got is None:
        from .cache import _disk_load  # filings read by an earlier process
        d = _disk_load(key)
        got = d[1] if d else None
    return got


def _unread(chamber: str, f: dict) -> bool:
    got = _stored(chamber, f)
    return got is None or (chamber == "House" and _stale_scan(got))


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "md", "phd", "hon"}


def _last_name(name: str) -> str:
    """'Gilbert Ray Cisneros, Jr.' -> 'cisneros'; 'Hon. Michael A. Rulli' -> 'rulli'."""
    words = [w for w in re.findall(r"[a-z]+", _fold(name or "")) if w not in _SUFFIXES]
    return words[-1] if words else ""


def _trade_key(r: dict) -> tuple:
    side = "sell" if str(r.get("type") or "").startswith("sell") else r.get("type")
    return (r.get("traded"), (r.get("ticker") or "").upper(), side, _last_name(r.get("member") or ""))


def cross_check(rows: list[dict], people: dict) -> tuple[list[dict], dict]:
    """Compare our trades with Bargo's latest (an independent copy of the same filings). Returns (the trades Bargo
    has and we don't, stats). Those trades are shown with a credit to Bargo; a failure just skips the check."""
    try:
        theirs = bargo.recent()
    except Exception as exc:  # noqa: BLE001 - the check is optional
        return [], {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
    ours = {_trade_key(r) for r in rows}
    extra, matched = [], 0
    for b in theirs:
        if _trade_key(b) in ours:
            matched += 1
            continue
        last = _last_name(b["member"])
        first = (b["member"] or "").split(" ")[0]
        who = (_match_house(people, last, first, b["state_dst"]) if b["chamber"] == "House" else _match_senate(people, last, first))
        extra.append({**{k: v for k, v in b.items() if k != "state_dst"}, "member": who["name"] if who else b["member"],
                      "bioguide": who["bioguide"] if who else None, "party": who["party"] if who else None,
                      "state": who["state"] if who else (b["state_dst"] or "")[:2] or None})
    return extra, {"checked": len(theirs), "matched": matched, "added": len(extra), "source": "Bargo", "url": bargo.HOME}


def trades(days: int = 400, read_new: bool = True) -> dict:
    """Every disclosed transaction filed in the last ``days`` days, newest first, with the member's party, state
    and committees. ``read_new`` reads filings that aren't on disk yet (slow the first time: about 1,000 filings
    a year); otherwise only filings already read are used and the rest are counted as pending."""

    def build():
        people = members()
        if read_new:
            refresh(days, budget_s=READ_BUDGET_S)
        rows, stats = [], {"filings": 0, "unreadable": 0, "pending": 0, "scanned": 0}
        for chamber, f in _filings(days):
            stats["filings"] += 1
            got = _stored(chamber, f)
            if got is None or (chamber == "House" and _stale_scan(got)):
                stats["pending"] += 1
                continue
            if not got["readable"]:
                stats["unreadable"] += 1
            elif got.get("scan"):
                stats["scanned"] += 1                   # a paper report read with OCR
            if chamber == "House":
                who = _match_house(people, f["last"], f["first"], f["state_dst"])
                url = _house_url(f)
            else:
                who = _match_senate(people, f["last"], f["first"])
                url = f["url"]
            name = who["name"] if who else f"{f['first']} {f['last']}".strip()
            for r in got["rows"]:
                rows.append({**r, "chamber": chamber, "member": name, "bioguide": who["bioguide"] if who else None,
                             "party": who["party"] if who else None, "state": who["state"] if who else f.get("state_dst", "")[:2] or None,
                             "disclosed": f["filed"] or r.get("notified"), "url": url})
        extra, stats["bargo"] = cross_check(rows, people)   # trades in Bargo's copy that our reading missed
        rows += extra
        rows.sort(key=lambda r: (r["disclosed"] or "", r["traded"] or ""), reverse=True)
        stats["errors"] = sorted(ERRORS.values())
        if not rows and ERRORS:
            raise RuntimeError("; ".join(sorted(ERRORS.values())))  # keep the last good data instead
        return {"rows": rows, "stats": stats, "as_of": datetime.now().strftime("%Y-%m-%dT%H:%M"),
                "committees": {m["bioguide"]: m["committees"] for m in people["by_id"].values()}}

    return cache.cached(f"congress:trades:{days}:{int(read_new)}", 3 * 3600, build)


def trades_for(sym: str, days: int = 730) -> list[dict]:
    """The trades of one ticker (Yahoo spelling)."""
    s = (sym or "").upper()
    return [r for r in trades(days)["rows"] if r.get("ticker") == s]
