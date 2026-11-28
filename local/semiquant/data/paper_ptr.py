"""Scanned (paper) House periodic transaction reports, read with OCR.

Some members file the House's paper PTR form. The Clerk publishes those as scanned, image-only PDFs with no text
layer, so the text reader finds nothing: about one House filing in eight, and every report of some of the most
active traders. This module reads the official form, and the extended layout many brokers attach (with "capital
gains" and "partial sale" columns):

1. find the table from its ruled lines (rows and columns);
2. read the purchase / sale / exchange and amount columns from the marks in their cells (no OCR needed, and
   an empty printed checkbox is not a mark);
3. OCR only the owner, asset and date columns with Tesseract, and map the asset name to a ticker.

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

VERSION = 1  # bump to re-read every scanned filing after an improvement
# Amount columns A-K of the form: $1,001-$15,000 ... Over $50,000,000, and K = a spouse's or child's asset over $1M
AMOUNTS: list[tuple[int, int | None]] = [(1001, 15000), (15001, 50000), (50001, 100000), (100001, 250000), (250001, 500000),
                                         (500001, 1000000), (1000001, 5000000), (5000001, 25000000), (25000001, 50000000),
                                         (50000001, None), (1000001, None)]

__all__ = ["available", "read_pdf", "read_page", "match_ticker", "VERSION"]

_have: bool | None = None


def available() -> bool:
    global _have
    if _have is None:
        _have = shutil.which("tesseract") is not None
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


def mark(dark: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> bool:
    """True if the cell holds a mark (an x or a tick). Printed checkbox outlines and ruled lines don't count:
    rows and columns that are mostly ink (box edges) are removed before counting."""
    a = dark[max(0, y0):y1, x0 + 5:x1 - 4]
    if a.size == 0:
        return False
    a = a.copy()
    a[a.mean(axis=1) > 0.5, :] = False
    a[:, a.mean(axis=0) > 0.5] = False
    if int(a.sum()) < max(25, int(0.012 * a.size)):
        return False
    rows, cols = np.nonzero(a)
    return len(np.unique(rows)) >= 8 and len(np.unique(cols)) >= 8   # an x has height and width; a dashed line has not


# ─── text ────────────────────────────────────────────────────────────────────

def _ocr(img: Any, psm: str = "11") -> list[dict]:
    """Words with their boxes (Tesseract TSV). psm 11: scattered text (a table); 6: one block (a single column)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}  # one thread per page: pages already run in parallel
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", psm, "tsv"], input=buf.getvalue(), capture_output=True,
                       timeout=180, env=env)
    words = []
    for line in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
        p = line.split("\t")
        if len(p) == 12 and p[11].strip() and p[10] != "-1":
            x, y, w, h = map(int, p[6:10])
            words.append({"t": p[11].strip(), "x": x, "y": y, "cx": x + w / 2, "cy": y + h / 2})
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


def parse_date(text: str, latest: date | None = None) -> str | None:
    """'10/08/26' -> '2026-10-08'. OCR slips (O for 0, l for 1) are fixed; impossible dates give None."""
    t = (text or "").translate(_DIGITS)
    m = re.search(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})(?!\d)", t)
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

_SUFFIX = {"CMN", "COM", "COMMON", "STOCK", "STK", "SHS", "SH", "CL", "CLASS", "A", "B", "C", "NEW", "INC", "INCORPORATED",
           "CORP", "CORPORATION", "CORPOR", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "NV", "SA", "AG", "SE", "ADR", "ADS",
           "SPONSORED", "SPON", "ORD", "ORDINARY", "HLDGS", "HOLDINGS", "HOLDING", "GROUP", "THE", "AND", "DEL", "DE",
           "USD", "PAR", "REGISTERED", "REG", "TECHNOLOGIES", "TECHNOLOGY", "INTERNATIONAL", "INTL"}
_NOT_A_STOCK = re.compile(r"LINKED TO|\bNOTES?\b|\bBONDS?\b|PERPETUAL|\bDUE\b|%|\bTREAS|\bMUNI|\bCD\b|CERTIFICATE|\bFUND\b|"
                          r"\bETF\b|\bTRUST\b|\bLP\b|\bLLC\b|MONEY MARKET|DEPOSIT", re.I)


def _norm(name: str) -> str:
    t = re.sub(r"\([^)]*\)", " ", (name or "").upper().replace("&", " AND "))
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in _SUFFIX)


_index: dict[str, str] | None = None


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


def match_ticker(asset: str) -> tuple[str | None, str]:
    """(ticker or None, asset type) for an asset name as written on the form."""
    a = (asset or "").upper()
    m = re.search(r"\b(CALL|PUT)\s*/\s*([A-Z]{1,5})\b", a)
    if m:
        return m.group(2), "Option"
    if _NOT_A_STOCK.search(a):
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


def read_page(img: Any, latest: date | None = None, cells: list[tuple[int, int]] | None = None,
              owner: str | None = None) -> list[dict]:
    """Trades on one scanned page. Rows are anchored on the dates in the transaction-date column, so broken or
    faint row lines don't matter. ``cells``: the filing's column layout (see ``read_pdf``); found here if not given."""
    dark = np.asarray(img.convert("L")) < 128
    xs, ys = rules(dark)
    if cells is None:
        cells = cells_of(xs)
    if len(cells) < 18:
        return []
    amt = cells[-11:]
    di, ni = len(cells) - 13, len(cells) - 12          # date of transaction, date notified
    kinds_at = cells[di - 5:di - 2] if len(cells) >= 20 else cells[di - 3:di]
    partial = cells[di - 1] if len(cells) >= 20 else None
    # OCR the owner..date-notified columns, with the ruled lines erased so letters touching them survive
    x0, x1 = cells[0][0], cells[ni][1]
    clean = ~dark
    for x in xs:
        clean[:, max(0, x - 3):x + 4] = True
    for y in ys:
        clean[max(0, y - 2):y + 3, :] = True
    from PIL import Image
    words = [{**w, "cx": w["cx"] + x0, "cy": w["cy"], "x": w["x"] + x0}
             for w in _ocr(Image.fromarray((clean[:, x0:x1] * 255).astype("uint8")))]
    c0 = cells[0]   # the owner codes are small: read that column on its own, as one block
    owner_words = [{**w, "cx": w["cx"] + c0[0], "x": w["x"] + c0[0]}
                   for w in _ocr(Image.fromarray((clean[:, c0[0]:c0[1]] * 255).astype("uint8")), "6")]
    dates = sorted((w for w in words if cells[di][0] <= w["cx"] < cells[di][1] and parse_date(w["t"], latest)), key=lambda w: w["cy"])
    if not dates:
        return []
    gaps = [b["cy"] - a["cy"] for a, b in zip(dates, dates[1:]) if b["cy"] - a["cy"] > 20]
    step = float(np.median(gaps)) if gaps else 58.0
    out, last_owner = [], owner
    for k, d in enumerate(dates):
        top = max(d["cy"] - 0.85 * step, (dates[k - 1]["cy"] + 0.3 * step) if k else 0)
        bot = d["cy"] + 0.3 * step

        def cell_text(c: tuple[int, int], t0: float = top, t1: float = bot) -> str:
            return _text([w for w in words if c[0] <= w["cx"] < c[1] and t0 <= w["cy"] < t1])
        asset = cell_text(cells[1])
        if not asset or "EXAMPLE" in asset.upper():
            continue
        my0, my1 = int(d["cy"] - 0.45 * step), int(d["cy"] + 0.35 * step)   # marks sit on the date's line
        kinds = [k2 for k2, c in zip(("buy", "sell", "exchange"), kinds_at) if mark(dark, c[0], c[1], my0, my1)]
        amounts = [i for i, c in enumerate(amt) if mark(dark, c[0], c[1], my0, my1)]
        if not kinds and not amounts:
            continue
        kind = kinds[0] if kinds else None
        if kind == "sell" and partial and mark(dark, partial[0], partial[1], my0, my1):
            kind = "sell_partial"
        lo, hi = AMOUNTS[amounts[0]] if amounts else (None, None)
        who = _owner([w for w in owner_words if top <= w["cy"] < bot]) or last_owner or "Self"
        last_owner = who
        notified = parse_date(cell_text(cells[ni]), latest)
        traded = _fix_year(parse_date(d["t"], latest), notified)
        ticker, atype = match_ticker(asset)
        out.append({"owner": who, "asset": asset.title() if asset.isupper() else asset, "ticker": ticker, "asset_type": atype,
                    "type": kind, "traded": traded, "notified": notified, "amount_lo": lo, "amount_hi": hi, "ocr": True})
    return out


def upright(im: Any) -> Any:
    """The landscape form, the right way up. Some filers scan it sideways (a portrait page): turn it so the
    wide asset-name column is on the left, which tells the two directions apart without OCR."""
    if im.size[1] <= im.size[0]:
        return im
    fallback = None
    for deg in (90, 270):
        r = im.rotate(deg, expand=True)
        cells = cells_of(rules(np.asarray(r.convert("L")) < 128)[0])
        if len(cells) >= 18:
            widest = max(range(len(cells)), key=lambda i: cells[i][1] - cells[i][0])
            if widest < len(cells) / 3:
                return r
            fallback = fallback or r
    return fallback or im


def read_pdf(pdf: Any, latest: date | None = None) -> list[dict]:
    """Trades in a scanned filing (a pypdf PdfReader). The attachment pages of a filing share one layout, so the
    layout found on most pages is used for all of them; a page with faint or broken column lines (or an extra
    line) then reads like the others. Pages that aren't the transaction table give nothing."""
    imgs = []
    for page in pdf.pages:
        try:
            im = [i.image for i in page.images]
        except Exception:  # noqa: BLE001 - an image this pypdf can't decode: skip the page
            continue
        if im:
            imgs.append(upright(max(im, key=lambda m: m.size[0] * m.size[1])))
    found = [cells_of(rules(np.asarray(im.convert("L")) < 128)[0]) for im in imgs]
    counts = [len(c) for c in found if len(c) >= 18]
    if not counts:
        return []
    usual = max(set(counts), key=lambda n: (counts.count(n), n))
    layout = next(c for c in found if len(c) == usual)
    rows: list[dict] = []
    for im, c in zip(imgs, found):
        rows += read_page(im, latest, c if len(c) == usual else layout, rows[-1]["owner"] if rows else None)
    return rows
