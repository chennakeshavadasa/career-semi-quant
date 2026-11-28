"""Scanned (paper) House periodic transaction reports, read with OCR.

Some members file the House's paper PTR form. The Clerk publishes those as scanned, image-only PDFs with no text
layer, so the text reader finds nothing: about one House filing in eight, and every report of some of the most
active traders. This module reads every version of the form: the older one (purchase / sale / exchange, amounts
A-J), the current one (adds partial sale and K, with a printed box per mark) and the layout many brokers attach
(adds "capital gains" and "partial sale" columns):

1. find the table from its ruled lines (rows and columns) and which column is which;
2. read the transaction-type and amount columns from the marks in their cells (no OCR needed, and an empty
   printed box is not a mark);
3. OCR only the owner, asset and date columns with Tesseract, and map the asset name to a ticker.

Typed rows read reliably. Handwriting mostly does not (Tesseract reads print): a handwritten row whose trade
date can't be read is counted ("skipped") and left out, never guessed. A filing that says "nothing to report"
is read as such.

Needs the ``tesseract`` program (Linux: ``apt install tesseract-ocr``, macOS: ``brew install tesseract``). Without
it scanned filings stay "unreadable" and are read once it is installed.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
from datetime import date
from difflib import get_close_matches
from typing import Any

import numpy as np

VERSION = 3  # bump to re-read the unread scanned filings after an improvement (3: all versions of the form)
# Amount columns A-K of the form: $1,001-$15,000 ... Over $50,000,000, and K = a spouse's or child's asset over $1M
AMOUNTS: list[tuple[int, int | None]] = [(1001, 15000), (15001, 50000), (50001, 100000), (100001, 250000), (250001, 500000),
                                         (500001, 1000000), (1000001, 5000000), (5000001, 25000000), (25000001, 50000000),
                                         (50000001, None), (1000001, None)]

__all__ = ["available", "read", "read_pdf", "read_page", "match_ticker", "name_key", "VERSION"]

_have: bool | None = None


def available() -> bool:
    """Tesseract (the OCR program) and Pillow (to decode the page images) are both installed."""
    global _have
    if _have is None:
        import importlib.util
        _have = shutil.which("tesseract") is not None and importlib.util.find_spec("PIL") is not None
    return _have


# ─── table geometry ──────────────────────────────────────────────────────────

def _runs(ratio: np.ndarray, thr: float, gap: int) -> list[tuple[int, int]]:
    """Index ranges where ``ratio`` exceeds ``thr`` (ranges closer than ``gap`` merge)."""
    out: list[list[int]] = []
    for i in np.where(ratio > thr)[0]:
        if out and i - out[-1][1] <= gap:
            out[-1][1] = int(i)
        else:
            out.append([int(i), int(i)])
    return [(a, b) for a, b in out]


def _long_runs(mask: np.ndarray, min_len: int) -> np.ndarray:
    """Per column: total length of the vertical ink runs at least ``min_len`` pixels long. Ruled lines, even
    dashed or broken ones, add up; letters (short strokes) don't."""
    m = mask.astype(np.int8)
    pad = np.zeros((1, m.shape[1]), np.int8)
    d = np.diff(np.vstack([pad, m, pad]), axis=0)
    st, en = np.argwhere(d == 1), np.argwhere(d == -1)
    st, en = st[np.lexsort((st[:, 0], st[:, 1]))], en[np.lexsort((en[:, 0], en[:, 1]))]
    lens, cols = en[:, 0] - st[:, 0], st[:, 1]
    out = np.zeros(m.shape[1])
    keep = lens >= min_len
    np.add.at(out, cols[keep], lens[keep])
    return out


def rules(dark: np.ndarray) -> tuple[list[int], list[int]]:
    """(x of the vertical rules, y of the horizontal rules) of the table."""
    v = _long_runs(dark, 25)
    h = _long_runs(dark.T, 80)
    xs = [(a + b) // 2 for a, b in _runs(v, 0.25 * v.max(), 8)] if v.max() > 0 else []
    ys = [(a + b) // 2 for a, b in _runs(h, 0.25 * h.max(), 4)] if h.max() > 0 else []
    return xs, ys


def cells_of(xs: list[int]) -> list[tuple[int, int]]:
    return [(a, b) for a, b in zip(xs, xs[1:]) if b - a >= 25]


def mark(dark: np.ndarray, x0: int, x1: int, y0: int, y1: int, edge: int = 0) -> bool:
    """True if the cell holds a mark (an x or a tick). Printed checkbox outlines and ruled lines don't count:
    rows and columns that are mostly ink (box edges) are removed before counting."""
    a = dark[max(0, y0):y1, x0 + 5:x1 - 4]
    if a.size == 0:
        return False
    a = a.copy()
    k = np.ones(2 * edge + 1)   # edge: also the fainter pixels along a printed box's edges
    a[np.convolve(a.mean(axis=1) > 0.5, k, "same") > 0, :] = False
    a[:, np.convolve(a.mean(axis=0) > 0.5, k, "same") > 0] = False
    if int(a.sum()) < max(25, int(0.012 * a.size)):
        return False
    rows, cols = np.nonzero(a)
    return len(np.unique(rows)) >= 8 and len(np.unique(cols)) >= 8   # an x has height and width; a dashed line has not


# ─── text ────────────────────────────────────────────────────────────────────

def _ocr(img: Any, psm: str = "11", only: str | None = None) -> list[dict]:
    """Words with their boxes (Tesseract TSV). psm 11: scattered text (a table); 6: one block (a single column);
    7: one line. ``only``: the characters allowed (digits and slashes for a handwritten date)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}  # one thread per page: pages already run in parallel
    cmd = ["tesseract", "stdin", "stdout", "--psm", psm] + (["-c", f"tessedit_char_whitelist={only}"] if only else []) + ["tsv"]
    r = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, timeout=180, env=env)
    words = []
    for line in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
        p = line.split("\t")
        if len(p) == 12 and p[11].strip() and p[10] != "-1":
            x, y, w, h = map(int, p[6:10])
            words.append({"t": p[11].strip(), "x": x, "y": y, "cx": x + w / 2, "cy": y + h / 2, "conf": float(p[10])})
    return words


def _text(words: list[dict]) -> str:
    """Words in reading order (lines by height, then left to right)."""
    out, line, last = [], [], None
    for w in sorted(words, key=lambda w: (w["cy"], w["x"])):
        if last is not None and w["cy"] - last > 12:
            out.append(" ".join(x["t"] for x in sorted(line, key=lambda x: x["x"])))
            line = []
        line.append(w)
        last = w["cy"]
    if line:
        out.append(" ".join(x["t"] for x in sorted(line, key=lambda x: x["x"])))
    return re.sub(r"\s+", " ", " ".join(out)).strip(" |_-—.,")


_DIGITS = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "i": "1", "S": "5", "s": "5", "B": "8", "Z": "2"})


def parse_date(text: str, latest: date | None = None, loose: bool = False) -> str | None:
    """'10/08/26' -> '2026-10-08'. OCR slips (O for 0, l for 1) are fixed; impossible dates give None.
    ``loose``: a "/" read as "(" or ")" counts too (for a date read on its own, in its cell)."""
    t = (text or "").translate(_DIGITS)
    sep = r"[/\-.()\\]" if loose else r"[/\-.]"
    m = re.search(rf"(\d{{1,2}})\s*{sep}\s*(\d{{1,2}})\s*{sep}\s*(\d{{2}}|\d{{4}})(?!\d)", t)
    if not m:
        return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = 2000 + y if y < 100 else y
    try:
        out = date(y, mo, d)
    except ValueError:
        return None
    if out.year < 2012 or (latest and out > latest):
        return None
    return out.isoformat()


# ─── asset name -> ticker ────────────────────────────────────────────────────

# A ticker the filer wrote after the name: "(PYPL)", "- XLE", or a capitalised last word of a mixed-case name
_WRITTEN = re.compile(r"(?:\(([A-Z]{1,5})\)|\s[-\u2013\u2014]\s*([A-Z]{1,5})|\s([A-Z]{2,5}))\s*$")
_NOT_TICKERS = {"ETF", "TR", "FD", "FDS", "BD", "SER", "SPDR", "MSCI", "REIT", "USA", "US", "INDEX", "BOND", "PORT", "INTL", "II", "III",
                "IV", "VI", "VII", "LP", "LLC", "MUNI", "DUE", "CALL", "PUT", "CMN", "COM", "FTSE", "SP", "JT", "DC", "OTC"}
_FUNDISH = re.compile(r"\bETF\b|SPDR|ISHARES|INVESCO|VANGUARD|PROSHARES|VANECK|SELECT SECTOR|\bTR\b|\bFUND\b|\bFDS?\b", re.I)
_BONDISH = re.compile(r"BE/R|MUNICIPAL|\bAUTH\b|\bCNTY\b|\bREV\b|\bRV\b|\bSR\s+[A-Z]\b|\bBONDS?\b|\bNOTES?\b|\bDUE\b|%|\bTREAS")
_SUFFIX = {"CMN", "COM", "COMMON", "STOCK", "STK", "SHS", "SH", "CL", "CLASS", "A", "B", "C", "NEW", "INC", "INCORPORATED",
           "CORP", "CORPORATION", "CORPOR", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "NV", "SA", "AG", "SE", "ADR", "ADS",
           "SPONSORED", "SPON", "ORD", "ORDINARY", "HLDGS", "HOLDINGS", "HOLDING", "GROUP", "THE", "AND", "DEL", "DE",
           "USD", "PAR", "REGISTERED", "REG", "TECHNOLOGIES", "TECHNOLOGY", "INTERNATIONAL", "INTL"}
_NOT_A_STOCK = re.compile(r"LINKED TO|\bNOTES?\b|\bBONDS?\b|PERPETUAL|\bDUE\b|%|\bTREAS|\bMUNI|\bCD\b|CERTIFICATE|\bFUND\b|"
                          r"\bETF\b|\bTRUST\b|\bLP\b|\bLLC\b|MONEY MARKET|DEPOSIT", re.I)


def name_key(asset: str) -> str:
    """An asset name reduced to the company: no trade words or prices ("Sell AT&T Inc @ 25.51"), no ticker,
    type code or share class ("Advanced Micro Devices, Inc. - Common Stock (AMD) [ST]" -> "ADVANCED MICRO
    DEVICES"). Paper and electronic reports of the same company give the same key."""
    t = re.sub(r"^\W*(?:SELL|SOLD|BUY|BOUGHT|REDEEMED|PURCHASED?)\s+", "", asset or "", flags=re.I)
    return _norm(re.sub(r"\s*@.*$|\[[A-Z]{2}\]|\s-\s.*$", " ", t))


def _norm(name: str) -> str:
    t = re.sub(r"\([^)]*\)", " ", (name or "").upper().replace("&", " AND "))
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in _SUFFIX)


_index: dict[str, str] | None = None


def _tickers() -> set[str]:
    from ..universe import ALL_META
    return set(ALL_META)


def _names() -> dict[str, str]:
    global _index
    if _index is None:
        from ..universe import ALL_META
        _index = {}
        for tick, meta in ALL_META.items():
            k = _norm(meta.get("name") or "")
            if k and k not in _index:
                _index[k] = tick
    return _index


def match_ticker(asset: str, bare: bool = True) -> tuple[str | None, str]:
    """(ticker or None, asset type) for an asset name as written on the form. ``bare``: a capitalised last word
    may be the ticker ("Zoetis Inc ZTS"), as filers write it on the House form (not on brokers' pages)."""
    asset = re.sub(r"\s*@.*$", "", re.sub(r"^\W*(?:SELL|SOLD|BUY|BOUGHT|REDEEMED|PURCHASED?)\s+", "", asset or "", flags=re.I))
    a = asset.upper()   # "Sell AT&T Inc @ 25.51" -> "AT&T INC"
    if re.fullmatch(r"[A-Z]{1,5}", a.strip()) and a.strip() in _tickers():
        return a.strip(), "Stock"   # the filer wrote just the ticker: "AMZN"
    m = re.search(r"\b(CALL|PUT)\s*/\s*([A-Z]{1,5})\b", a)
    if m:
        return m.group(2), "Option"
    m = _WRITTEN.search(asset or "")
    if m:
        t = next(g for g in m.groups() if g)
        last = m.group(3) is not None
        if t not in _SUFFIX and t not in _NOT_TICKERS and (not last or (bare and re.search(r"[a-z]", asset) and (
                not _BONDISH.search(a) or re.search(r"\bETF\b", a)))):
            return t, "ETF" if _FUNDISH.search(a) else "Stock"
    if _NOT_A_STOCK.search(a) or _BONDISH.search(a):
        return None, "Other"
    k = _norm(a)
    if not k:
        return None, "Stock"
    idx = _names()
    if k in idx:
        return idx[k], "Stock"
    hit = get_close_matches(k, list(idx), n=1, cutoff=0.9)
    if hit and hit[0].split()[0] == k.split()[0]:
        return idx[hit[0]], "Stock"
    return None, "Stock"


# ─── pages and filings ───────────────────────────────────────────────────────

def _owner(words: list[dict]) -> str | None:
    """The owner code in the first column: SP (spouse), DC (dependent child), JT (joint). The only codes are those
    three, so OCR's reading is classified by shape: 'oc', 'ac', 'bc', 'be', '0C' are DC; 'sp', '5P' are SP."""
    for w in words:
        t = re.sub(r"[^A-Z0-9]", "", w["t"].upper()).replace("0", "O").replace("5", "S")
        if len(t) != 2:
            continue
        if t[1] in "CEG":
            return "Child"
        if t[1] in "PF" or t[0] == "S":
            return "Spouse"
        if t[1] == "T" or t[0] == "J":
            return "Joint"
    return None


def _fix_year(traded: str | None, notified: str | None) -> str | None:
    """OCR sometimes misreads one digit of a two-digit year ('26' as '25'). A trade must come before its
    notification and within a year of it; if only the year is off, take the notification's year."""
    if not traded or not notified:
        return traded
    t, n = date.fromisoformat(traded), date.fromisoformat(notified)
    if 0 <= (n - t).days <= 366:
        return traded
    for y in (n.year, n.year - 1):
        try:
            c = t.replace(year=y)
        except ValueError:
            continue
        if 0 <= (n - c).days <= 366:
            return c.isoformat()
    return traded


MIN_CELLS = 16   # the narrowest version of the form has 17 columns
# The transaction-type columns between the asset name and the dates, by how many there are
_KINDS: dict[int, tuple[str | None, ...]] = {
    3: ("buy", "sell", "exchange"),                        # the older House form (amounts A-J), and with K
    4: ("buy", "sell", "sell_partial", "exchange"),        # the current House form
    5: ("buy", "sell", "exchange", None, "sell_partial"),  # brokers' attachments: + "capital gains over $200?"
}
_KNOWN = {(3, 10), (3, 11), (4, 11), (5, 11)}              # (type columns, amount columns) of those versions
_DATE_HEAD = re.compile(r"MM\w{0,2}?[DO0]{1,2}\w{0,2}?YY")   # "(MM/DD/YY)" as OCR reads it: MMIDDIYY, MMODIYY, MM/DO/YY


def _date_head(t: str) -> bool:
    return bool(_DATE_HEAD.search(re.sub(r"[^A-Z0-9]", "", t.upper())))


def layout(cells: list[tuple[int, int]], words: list[dict], latest: date | None = None) -> dict | None:
    """Which column is which, or None if this is not the transaction table. The House form has had a few
    versions: the older one (purchase, sale, exchange; amounts A-J), the current one (adds partial sale, and K: a
    spouse's or child's asset over $1M) and the layout brokers attach (adds capital gains). The amounts are the
    last 11 columns (10 on the older form, 17 columns in all) and the two dates come just before them; the asset
    name is the widest column before the dates and the owner code the one before that; the transaction types
    sit in between. Another layout is placed by its printed "(MM/DD/YY)" headings, or else by the dates in it."""
    if len(cells) < MIN_CELLS:
        return None
    asset = max(range(len(cells) // 2), key=lambda i: cells[i][1] - cells[i][0])
    di = len(cells) - (13 if len(cells) >= 18 else 12)

    def per_cell(pred) -> list[int]:
        return [sum(1 for w in words if a <= w["cx"] < b and pred(w["t"])) for a, b in cells]
    if not 3 <= di - asset - 1 <= 5:
        head = per_cell(_date_head)
        found = next((i for i in range(asset + 1, len(cells) - 1) if head[i]), None)
        if found is None:
            n = per_cell(lambda t: parse_date(t, latest) is not None)
            top = max(n[asset + 1:-1], default=0)
            if not top:
                return None
            found = next(i for i in range(asset + 1, len(cells) - 1) if n[i] >= max(1, top / 2))
        di = found
    amounts, kinds = cells[di + 2:di + 13], cells[asset + 1:di]
    if len(amounts) < 10 or not kinds:
        return None
    heads = [w["cy"] for w in words if cells[di][0] <= w["cx"] < cells[di + 1][1] and _date_head(w["t"])]
    return {"owner": cells[asset - 1] if asset else None, "asset": cells[asset],
            "kinds": list(zip(_KINDS.get(len(kinds), ("buy", "sell", "exchange")), kinds)),
            "date": cells[di], "notified": cells[di + 1], "amounts": amounts,
            "known": (len(kinds), len(amounts)) in _KNOWN, "body": max(heads) if heads else None}


def _marks(dark: np.ndarray, lay: dict, y0: int, y1: int, edge: int = 0) -> tuple[list[str], list[int]]:
    """The transaction types and the amount columns marked between y0 and y1."""
    kinds = [k for k, c in lay["kinds"] if k and mark(dark, c[0], c[1], y0, y1, edge)]
    return kinds, [i for i, c in enumerate(lay["amounts"]) if mark(dark, c[0], c[1], y0, y1, edge)]


def _kind(kinds: list[str]) -> str | None:
    """One transaction type from the marked columns, the first in the form's order. A partial sale is marked
    alone (the House form has a column for it) or as a sale plus "partial" (brokers' layouts)."""
    first = next((k for k in kinds if k != "sell_partial"), None)
    return "sell_partial" if "sell_partial" in kinds and first in (None, "sell") else first


def _bands(dark: np.ndarray, cell: tuple[int, int], below: float) -> list[tuple[int, int]]:
    """The rows of the table body below y = ``below``, from the ruled lines across one narrow column (there even
    a slightly skewed scan has level lines). A line spans the column; large typed digits never do."""
    f = dark[:, cell[0] + 4:cell[1] - 4].mean(axis=1)
    lines = _runs(f, 0.85, 3)
    return [(e0 + 1, s1) for (_, e0), (s1, _) in zip(lines, lines[1:]) if 25 <= s1 - e0 <= 200 and e0 > below]


def _ruled(dark: np.ndarray, xs: list[int], y0: int, y1: int) -> bool:
    """The table's column lines run through rows y0..y1: a row of the table, not of the notes under it. ``xs``:
    the lines across the amount columns; on a boxed form some are the boxes' own edges (as tall as the box, not
    the row), so the better-covered half of them decides."""
    if not xs or y1 <= y0:
        return False
    seen = sorted(float(dark[y0:y1, max(0, x - 3):x + 4].any(axis=1).mean()) for x in xs)
    return float(np.mean(seen[len(seen) // 2:])) >= 0.8


def _crop(clean: np.ndarray, cell: tuple[int, int], y0: float, y1: float) -> Any:
    from PIL import Image
    return Image.fromarray((clean[max(0, int(y0)):max(0, int(y1)), cell[0] + 3:cell[1] - 3] * 255).astype("uint8"))


def _cell_date(gray: Any, clean: np.ndarray, cell: tuple[int, int], y0: float, y1: float, latest: date | None) -> str | None:
    """The date in one cell, read on its own as one line: from the grey scan (thin slashes survive), else from
    the black-and-white one as digits and slashes only. Neat typing reads; most handwriting does not."""
    from PIL import ImageOps
    box = (cell[0] + 6, max(0, int(y0)), cell[1] - 6, max(1, int(y1)))
    got = parse_date(" ".join(w["t"] for w in _ocr(ImageOps.expand(gray.crop(box), 15, fill=255), "7")), latest, True)
    return got or parse_date(" ".join(w["t"] for w in _ocr(_crop(clean, cell, y0, y1), "7", "0123456789/-.")), latest, True)


_NOTHING = re.compile(r"NOTHING\W+(?:\S+\W+){0,3}?REPORT|NO\s+TRANSACTIONS|NO\s+REPORTABLE")   # "to" read as "fo", specks


def _same_form(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> bool:
    """Two pages' columns are one form, one page with a line missing or extra (faint or broken): most lines of
    one are where the other has lines too, allowing for the page sitting a little to one side or scanned a
    little larger. A different version of the form (the House's own cover before brokers' pages) has its lines
    elsewhere."""
    xa = np.array([c[0] for c in a] + [a[-1][1]], float)
    xb = np.array([c[0] for c in b] + [b[-1][1]], float)
    best = max(int((np.abs(xb[None, :] - (k * xa[:, None] + d)).min(axis=1) <= 12).sum())
               for k in np.arange(0.94, 1.065, 0.01) for d in range(-90, 91, 3))
    return best >= 0.9 * min(len(xa), len(xb))   # same form: all lines but one or two; other versions: ~3/4


def _read_page(img: Any, latest: date | None = None, cells: list[tuple[int, int]] | None = None,
               owner: str | None = None, usual: list[tuple[int, int]] | None = None) -> tuple[list[dict], bool, int]:
    """(trades on one scanned page, whether it says it has nothing to report, rows with marks but no readable
    trade date: handwritten ones). See ``read_page``."""
    from PIL import Image
    gray = img.convert("L")
    dark = np.asarray(gray) < 128
    xs, ys = rules(dark)
    if cells is None:
        cells = cells_of(xs)
    if usual and len(usual) != len(cells) and (len(cells) < MIN_CELLS or _same_form(cells, usual)):
        cells = usual   # this page's lines came out differently (faint or broken): the filing's layout
    if len(cells) < MIN_CELLS:
        return [], False, 0
    # OCR the owner..date-notified columns, with the ruled lines erased so letters touching them survive
    x0, x1 = cells[0][0], cells[len(cells) - 12][1]
    clean = ~dark
    for x in xs:
        clean[:, max(0, x - 3):x + 4] = True
    for y in ys:
        clean[max(0, y - 2):y + 3, :] = True
    words = [{**w, "cx": w["cx"] + x0, "x": w["x"] + x0}
             for w in _ocr(Image.fromarray((clean[:, x0:x1] * 255).astype("uint8")))]
    lay = layout(cells, words, latest)
    if lay is None and usual and usual is not cells:
        lay = layout(usual, words, latest)
    if lay is None:   # not the table as far as OCR can tell, but it may still say "nothing to report"
        return [], bool(_NOTHING.search(_text(words).upper())), 0
    ac, dc, nc, oc = lay["asset"], lay["date"], lay["notified"], lay["owner"]
    nothing = bool(_NOTHING.search(" ".join(w["t"] for w in words if ac[0] <= w["cx"] < ac[1]).upper()))
    # the owner codes are small: read that column on its own, as one block
    owner_words = [{**w, "cx": w["cx"] + oc[0], "x": w["x"] + oc[0]}
                   for w in _ocr(Image.fromarray((clean[:, oc[0]:oc[1]] * 255).astype("uint8")), "6")] if oc else []
    # the House's own form, older (17 columns) or current (19), read row by row; brokers' pages (and the
    # 18-column layout) by their typed dates
    house_form = (len(lay["kinds"]), len(lay["amounts"])) in ((3, 10), (4, 11))
    dates = sorted((w for w in words if dc[0] <= w["cx"] < dc[1] and parse_date(w["t"], latest, house_form)), key=lambda w: w["cy"])
    found: list[tuple[float, dict]] = []
    last_owner = owner
    skipped = 0

    def text_in(c: tuple[int, int], t0: float, t1: float) -> str:
        return _text([w for w in words if c[0] <= w["cx"] < c[1] and t0 <= w["cy"] < t1])

    def trade(y: float, asset: str, kinds: list[str], amounts: list[int], who: str | None, traded: str | None,
              notified: str | None) -> None:
        nonlocal last_owner
        asset = re.sub(r"^(?:[\W_]+|[a-z]{1,2}\W+)+", "", asset)   # OCR's specks before the name: "ee. |", "= ---"
        if not asset or re.search(r"EXAMPLE|MEGA CORP", asset.upper()) or not (kinds or amounts) or (
                not house_form and not amounts and set(kinds) <= {"sell_partial"}):
            return   # the form's printed example row, an empty one, or a stray mark in a broker's "partial" column
        lo, hi = AMOUNTS[amounts[0]] if amounts else (None, None)
        who = who or last_owner or "Self"
        last_owner = who
        ticker, atype = match_ticker(asset, bare=house_form)
        found.append((y, {"owner": who, "asset": asset.title() if asset.isupper() and " " in asset else asset, "ticker": ticker,
                          "asset_type": atype, "type": _kind(kinds), "traded": _fix_year(traded, notified),
                          "notified": notified, "amount_lo": lo, "amount_hi": hi, "ocr": True}))

    bands = _bands(dark, dc, lay["body"]) if lay["body"] is not None and house_form else []
    if bands:   # the House form: one ruled row per trade, typed or handwritten
        seps = [x for x in xs if lay["amounts"][0][0] - 5 <= x <= lay["amounts"][-1][1] + 5]
        for y0, y1 in bands:
            kinds, amounts = _marks(dark, lay, y0 + 2, y1 - 2, edge=2)
            if not (kinds or amounts) or len(kinds) > 2 or len(amounts) > 2 or not _ruled(dark, seps, y0, y1):
                continue
            typed = [d for d in dates if y0 <= d["cy"] <= y1]
            t0, t1 = y0 - 0.15 * (y1 - y0), y1 + 0.15 * (y1 - y0)   # handwriting strays over the lines
            traded = parse_date(typed[0]["t"], latest, True) if typed else _cell_date(gray, clean, dc, t0, t1, latest)
            asset = text_in(ac, y0, y1) if typed else _text(_ocr(_crop(clean, ac, t0, t1), "6"))
            if not traded:
                if not re.search(r"EXAMPLE|MEGA CORP", asset.upper()):
                    skipped += 1   # no readable trade date (handwritten): left out rather than guessed
                continue
            notified = parse_date(text_in(nc, y0, y1), latest, True) or _cell_date(gray, clean, nc, t0, t1, latest)
            trade((y0 + y1) / 2, asset, kinds, amounts, _owner([w for w in owner_words if t0 <= w["cy"] < t1]),
                  traded, notified)
        return [r for _, r in sorted(found, key=lambda t: t[0])], nothing, skipped
    # brokers' attachments: rows anchored on the typed dates, so broken or faint row lines don't matter
    gaps = [b["cy"] - a["cy"] for a, b in zip(dates, dates[1:]) if b["cy"] - a["cy"] > 20]
    step = float(np.median(gaps)) if gaps else 58.0
    for k, d in enumerate(dates):
        top = max(d["cy"] - 0.85 * step, (dates[k - 1]["cy"] + 0.3 * step) if k else 0)
        bot = d["cy"] + 0.3 * step
        kinds, amounts = _marks(dark, lay, int(d["cy"] - 0.45 * step), int(d["cy"] + 0.35 * step))  # on the date's line
        trade(d["cy"], text_in(ac, top, bot), kinds, amounts, _owner([w for w in owner_words if top <= w["cy"] < bot]),
              parse_date(d["t"], latest), parse_date(text_in(nc, top, bot), latest))
    return [r for _, r in sorted(found, key=lambda t: t[0])], nothing, skipped


def read_page(img: Any, latest: date | None = None, cells: list[tuple[int, int]] | None = None,
              owner: str | None = None, usual: list[tuple[int, int]] | None = None) -> list[dict]:
    """Trades on one scanned page. On the House form each trade has its ruled row, found from the lines of the
    date column (typed or handwritten); on brokers' attachments rows are anchored on the typed dates, so broken
    or faint row lines don't matter. A row whose trade date can't be read is left out. ``cells``: this page's
    columns (found here if not given). ``usual``: the filing's usual columns, used instead when this page's
    lines came out differently (faint or broken), unless its own printed date headings show it is another
    version of the form."""
    return _read_page(img, latest, cells, owner, usual)[0]


def upright(im: Any) -> Any:
    """The landscape form, the right way up. Some filers scan it sideways (a portrait page): turn it so the
    wide asset-name column is on the left, which tells the two directions apart without OCR."""
    if im.size[1] <= im.size[0]:
        return im
    fallback = None
    for deg in (90, 270):
        r = im.rotate(deg, expand=True)
        cells = cells_of(rules(np.asarray(r.convert("L")) < 128)[0])
        if len(cells) >= MIN_CELLS:
            widest = max(range(len(cells)), key=lambda i: cells[i][1] - cells[i][0])
            if widest < len(cells) / 3:
                return r
            fallback = fallback or r
    return fallback or im


def read(pdf: Any, latest: date | None = None) -> dict:
    """A scanned filing (a pypdf PdfReader): ``{"rows": trades, "nothing": the form says "nothing to report",
    "skipped": rows with marks whose trade date could not be read (handwritten)}``.
    The pages of a filing usually share one layout, so the layout found on most pages also reads a page whose
    column lines are faint or broken (or have an extra line). Pages that aren't the transaction table give
    nothing."""
    imgs = []
    for page in pdf.pages:
        try:
            im = [i.image for i in page.images]
        except ImportError:
            raise   # a missing library: fail, so the report is read again later instead of being stored as empty
        except Exception:  # noqa: BLE001 - an image this pypdf can't decode: skip the page
            continue
        if im:
            imgs.append(upright(max(im, key=lambda m: m.size[0] * m.size[1])))
    found = [cells_of(rules(np.asarray(im.convert("L")) < 128)[0]) for im in imgs]
    counts = [len(c) for c in found if len(c) >= MIN_CELLS]
    if not counts:
        return {"rows": [], "nothing": False, "skipped": 0}
    n = max(set(counts), key=lambda k: (counts.count(k), k))
    usual = next(c for c in found if len(c) == n)
    rows: list[dict] = []
    nothing, skipped = False, 0
    for im, c in zip(imgs, found):
        got, none, missed = _read_page(im, latest, c, rows[-1]["owner"] if rows else None, usual)
        rows += got
        nothing, skipped = nothing or none, skipped + missed
    return {"rows": rows, "nothing": nothing and not rows, "skipped": skipped}


def read_pdf(pdf: Any, latest: date | None = None) -> list[dict]:
    """The trades in a scanned filing (see ``read``)."""
    return read(pdf, latest)["rows"]
