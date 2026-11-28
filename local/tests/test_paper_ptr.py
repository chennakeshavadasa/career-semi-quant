"""Scanned (paper) House trade reports: grid, marks and OCR, on three real pages of a paper filing (a public
record: the House Clerk's scan of a member's periodic transaction report), plus the Congress pipeline around them."""
import io
import os
from datetime import date

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

from semiquant.data import cache, congress, paper_ptr as pp

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ptr_scan")
need_ocr = pytest.mark.skipif(not pp.available(), reason="tesseract is not installed")
LATEST = date(2026, 11, 5)   # the filing date: no trade can be later


def img(name):
    return Image.open(os.path.join(D, name))


def ink(name):
    return np.asarray(img(name).convert("L")) < 128


def scan_pdf(*names) -> bytes:
    """A scanned filing as the House publishes it: image-only pages, no text layer."""
    ims = [img(n).convert("1") for n in names]
    buf = io.BytesIO()
    ims[0].save(buf, format="PDF", save_all=True, append_images=ims[1:])
    return buf.getvalue()


# Read by eye from the two pages: (part of the asset name, type, trade date, low end of the amount band)
PAGE2 = [("TORONTO", "buy", "2026-10-08", None), ("NATIONAL BANK", "buy", "2026-10-12", 15001), ("CITIGROUP", "buy", "2026-10-14", 15001),
         ("AMERICAN EXPRESS", "buy", "2026-10-02", 15001), ("APPLE", "buy", "2026-10-02", 15001), ("AMPHENOL", "buy", "2026-10-02", 15001),
         ("JPMORGAN", "buy", "2026-10-15", 1001), ("BANK OF MONTREAL", "buy", "2026-10-19", 1001), ("TORONTO", "buy", "2026-10-21", 1001),
         ("MERCK", "buy", "2026-10-02", 1001), ("NEW YORK MELLON", "buy", "2026-10-19", 1001), ("INTUITIVE", "buy", "2026-10-02", 1001),
         ("META", "buy", "2026-10-02", 1001), ("CAPITAL ONE", "sell", "2026-10-02", 15001), ("AMERICAN TOWER", "sell", "2026-10-02", 15001)]
PAGE4 = [("ROYAL BANK", "buy", "2026-10-08", 15001), ("ZIMMER", "sell_partial", "2026-10-30", 1001), ("FACTSET", "sell_partial", "2026-10-22", 1001),
         ("GRAPHIC", "sell_partial", "2026-10-27", 1001), ("MAPLEBEAR", "sell_partial", "2026-10-14", 1001), ("GRAPHIC", "sell_partial", "2026-10-21", 1001),
         ("GRAPHIC", "sell", "2026-10-28", 1001), ("MAPLEBEAR", "sell_partial", "2026-10-21", 1001), ("TENABLE", "sell_partial", "2026-10-08", 1001),
         ("TENABLE", "sell_partial", "2026-10-26", 1001)]


def check(rows, truth, owner="Child"):
    assert len(rows) == len(truth)
    for (name, kind, traded, lo), r in zip(truth, rows):
        assert name in r["asset"].upper(), (name, r)
        assert (r["type"], r["traded"], r["amount_lo"], r["owner"]) == (kind, traded, lo, owner), (name, r)
        assert r["ocr"] is True


# ─── pure parts (no OCR needed) ───────────────────────────────────────────────

def test_dates_survive_ocr_slips_and_impossible_ones_are_rejected():
    assert pp.parse_date("10/08/26") == "2026-10-08"
    assert pp.parse_date("1O/O8/26") == "2026-10-08"            # O for 0
    assert pp.parse_date("l0/2l/2026") == "2026-10-21"          # l for 1
    assert pp.parse_date("02/05/015") is None                   # the form's printed example
    assert pp.parse_date("13/40/26") is None
    assert pp.parse_date("12/01/26", latest=LATEST) is None     # after the filing
    assert pp.parse_date("") is None and pp.parse_date("no date") is None


def test_a_misread_year_is_fixed_from_the_notification_date():
    assert pp._fix_year("2025-10-19", "2026-11-02") == "2026-10-19"
    assert pp._fix_year("2026-10-19", "2026-11-02") == "2026-10-19"
    assert pp._fix_year("2026-12-30", "2027-01-15") == "2026-12-30"
    assert pp._fix_year("2026-10-19", None) == "2026-10-19"


def test_owner_codes_are_read_from_their_ocr_shapes():
    w = lambda t: [{"t": t}]   # noqa: E731
    for t in ("oc", "ac", "bc", "be", "0C", "DC"):
        assert pp._owner(w(t)) == "Child", t
    for t in ("SP", "sp", "5P"):
        assert pp._owner(w(t)) == "Spouse", t
    assert pp._owner(w("JT")) == "Joint"
    assert pp._owner(w("Grandchildren")) is None and pp._owner([]) is None


def test_asset_names_map_to_tickers():
    assert pp.match_ticker("NVIDIA CORPORATION CMN") == ("NVDA", "Stock")
    assert pp.match_ticker("Apple Inc Cmn") == ("AAPL", "Stock")
    assert pp.match_ticker("CALL/META FLEX EURO PM 690 EXP 10/02/2026") == ("META", "Option")
    assert pp.match_ticker("TORONTO DOMINION BANK LINKED TO S&P 500 INDEX")[0] is None   # a structured note, not the bank's stock
    assert pp.match_ticker("BANK OF NEW YORK MELLON CORPOR HYBRID PERPETUAL")[0] is None
    assert pp.match_ticker("Some Private Partnership Units")[0] is None


def test_the_grid_of_an_attachment_page_has_the_forms_twenty_columns():
    cells = pp.cells_of(pp.rules(ink("page2.png"))[0])
    assert len(cells) == 20                                   # owner, asset, P S E, gains, partial, 2 dates, 11 amounts
    assert all(b - a >= 25 for a, b in cells)
    assert len(pp.cells_of(pp.rules(ink("cover.png"))[0])) >= 18


def test_marks_x_yes_empty_box_no_dashed_line_no():
    blank = np.zeros((60, 60), bool)
    x = blank.copy()
    for i in range(14):
        x[28 + i, 22 + i] = x[28 + i, 35 - i] = True
        x[28 + i, 23 + i] = x[28 + i, 34 - i] = True
    box = blank.copy()
    box[10:50, 10] = box[10:50, 49] = box[10, 10:50] = box[49, 10:50] = True
    box[11:49, 11] = box[11:49, 48] = box[11, 11:49] = box[48, 11:49] = True
    dash = blank.copy()
    for k in range(5, 55, 10):
        dash[40:42, k:k + 5] = True
    assert pp.mark(x, 0, 60, 0, 60)
    assert not pp.mark(box, 0, 60, 0, 60)
    assert not pp.mark(dash, 0, 60, 0, 60)
    assert not pp.mark(blank, 0, 60, 0, 60)
    box_x = box | x
    assert pp.mark(box_x, 0, 60, 0, 60)                       # an x inside a printed checkbox


def test_marks_on_the_real_page():
    d = ink("page2.png")
    cells = pp.cells_of(pp.rules(d)[0])
    y0, y1 = 520, 558                                         # the first trade's line on this page
    purchase, sale = cells[2], cells[3]
    assert pp.mark(d, purchase[0], purchase[1], y0, y1) and not pp.mark(d, sale[0], sale[1], y0, y1)


# ─── OCR ─────────────────────────────────────────────────────────────────────

@need_ocr
def test_every_row_of_two_real_pages_is_read_correctly():
    layout = pp.cells_of(pp.rules(ink("page2.png"))[0])
    check(pp.read_page(img("page2.png"), LATEST), PAGE2)
    check(pp.read_page(img("page4.png"), LATEST, layout), PAGE4)   # faint, broken lines: the filing's layout


@need_ocr
def test_a_whole_scanned_filing():
    from pypdf import PdfReader
    rows = pp.read_pdf(PdfReader(io.BytesIO(scan_pdf("cover.png", "page2.png", "page4.png"))), LATEST)
    check(rows, PAGE2 + PAGE4)                               # the cover (an empty form and its example row) adds nothing
    by = {r["asset"].upper()[:15]: r for r in rows}
    assert by["APPLE INC CMN"]["ticker"] == "AAPL"


# ─── the Congress pipeline around it ─────────────────────────────────────────

class Resp:
    def __init__(self, content):
        self.content = content


@pytest.fixture
def no_cache(monkeypatch):
    stored = {}
    monkeypatch.setattr(cache, "cached", lambda key, ttl, loader, **kw: stored[key] if key in stored else stored.setdefault(key, loader()))
    monkeypatch.setattr(cache, "put", lambda key, value, ttl, disk=False: stored.__setitem__(key, value))
    return stored


FILING = {"id": "9116399", "year": 2026, "last": "Khanna", "first": "Rohit", "state_dst": "CA17", "filed": "2026-11-05"}


@need_ocr
def test_a_scanned_house_report_is_read_with_ocr(no_cache, monkeypatch):
    monkeypatch.setattr(congress, "_get", lambda url, timeout=30, **kw: Resp(scan_pdf("cover.png", "page2.png")))
    got = congress._house_filing(FILING)
    assert got["readable"] and got["scan"] and got["ocr"] == pp.VERSION and len(got["rows"]) == len(PAGE2)
    assert not congress._stale_scan(got)


def test_scans_read_before_ocr_are_read_again_once_it_is_available(no_cache, monkeypatch):
    calls = []
    monkeypatch.setattr(congress, "_get", lambda url, timeout=30, **kw: calls.append(url) or Resp(scan_pdf("cover.png")))
    monkeypatch.setattr(pp, "_have", False)
    got = congress._house_filing(FILING)
    assert got == {"rows": [], "readable": False, "scan": True, "ocr": 0} and len(calls) == 1
    assert not congress._stale_scan(got)                       # no OCR here: nothing to retry
    monkeypatch.setattr(pp, "_have", True)
    assert congress._stale_scan(got)
    assert congress._stale_scan({"rows": [], "readable": False})                 # stored by the old reader
    assert not congress._stale_scan({"rows": [], "readable": False, "scan": False})   # not a scan: never retried
    assert not congress._stale_scan({"rows": [{"x": 1}], "readable": True})
    monkeypatch.setattr(pp, "read", lambda pdf, latest=None: {"rows": [{"asset": "Nvidia Corporation Cmn", "ocr": True}],
                                                             "nothing": False, "skipped": 0})
    again = congress._house_filing(FILING)
    assert again["readable"] and again["ocr"] == pp.VERSION and len(calls) == 2   # read again, and stored


def test_refresh_reads_the_newest_reports_first(monkeypatch):
    order = []
    monkeypatch.setattr(congress, "_filings", lambda days: [("House", {"id": i, "filed": d}) for i, d in
                                                            (("a", "2026-01-05"), ("b", "2026-11-05"), ("c", "2026-06-01"))])
    monkeypatch.setattr(congress, "_house_filing", lambda f: order.append(f["id"]))
    congress.refresh(400, workers=1)
    assert order == ["b", "c", "a"]


def test_a_page_scanned_sideways_is_turned_upright():
    page = img("page2.png")
    for turned in (page.rotate(90, expand=True), page.rotate(270, expand=True)):
        up = pp.upright(turned)
        assert up.size == page.size
        assert len(pp.cells_of(pp.rules(np.asarray(up.convert("L")) < 128)[0])) == 20
        cells = pp.cells_of(pp.rules(np.asarray(up.convert("L")) < 128)[0])
        assert max(range(20), key=lambda i: cells[i][1] - cells[i][0]) == 1     # the asset column is on the left
    assert pp.upright(page) is page                          # landscape pages are left alone


@need_ocr
def test_a_sideways_page_reads_like_the_upright_one():
    check(pp.read_page(pp.upright(img("page2.png").rotate(90, expand=True)), LATEST), PAGE2)


def test_ocr_needs_both_tesseract_and_pillow(monkeypatch):
    import importlib.util
    monkeypatch.setattr(pp, "_have", None)
    monkeypatch.setattr(pp.shutil, "which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert pp.available() is False
    monkeypatch.setattr(pp, "_have", None)
    monkeypatch.setattr(pp.shutil, "which", lambda name: None)
    assert pp.available() is False
    monkeypatch.setattr(pp, "_have", None)


def test_a_missing_imaging_library_fails_the_read_instead_of_storing_an_empty_one():
    class Page:
        @property
        def images(self):
            raise ImportError("pillow is required to do image extraction")

    class Pdf:
        pages = [Page()]
    with pytest.raises(ImportError):
        pp.read_pdf(Pdf())


def test_reports_read_by_an_older_reader_are_read_again(monkeypatch):
    monkeypatch.setattr(pp, "_have", True)
    assert congress._stale_scan({"rows": [], "readable": False, "scan": True, "ocr": pp.VERSION - 1})
    assert not congress._stale_scan({"rows": [], "readable": False, "scan": True, "ocr": pp.VERSION})
    # a scan read by an older reader is read again even if it found trades (the old reader misread the current form)
    assert congress._stale_scan({"rows": [{"x": 1}], "readable": True, "scan": True, "ocr": pp.VERSION - 1})
    assert not congress._stale_scan({"rows": [{"x": 1}], "readable": True})       # an electronic report: never


# ─── the form's other versions ───────────────────────────────────────────────

def _cells(n, asset_at=1):
    out, x = [], 100
    for i in range(n):
        w = 400 if i == asset_at else 70
        out.append((x, x + w))
        x += w
    return out


def _word(t, c, y=500):
    return {"t": t, "cx": (c[0] + c[1]) / 2, "cy": y}


def test_the_columns_of_each_version_of_the_form():
    """Which column is which, from the printed "(MM/DD/YY)" headings (as OCR reads them) or else from the dates."""
    c = _cells(17)                                            # older form: owner, asset, P S E, 2 dates, A-J
    lay = pp.layout(c, [_word("(MM/DD/YY)", c[5]), _word("(MMIDDIYY)", c[6])])
    assert [k for k, _ in lay["kinds"]] == ["buy", "sell", "exchange"] and lay["date"] == c[5] and lay["notified"] == c[6]
    assert len(lay["amounts"]) == 10 and lay["known"] and lay["owner"] == c[0] and lay["asset"] == c[1]
    c = _cells(19)                                            # current form: + partial sale, + K
    lay = pp.layout(c, [_word("(MM/ODIYY}", c[6])])
    assert [k for k, _ in lay["kinds"]] == ["buy", "sell", "sell_partial", "exchange"] and lay["notified"] == c[7]
    assert len(lay["amounts"]) == 11 and lay["body"] == 500
    c = _cells(20)                                            # brokers' layout: + capital gains (a heading misread
    lay = pp.layout(c, [_word("(MM/DD/YY)", c[8])])          # in the notified column changes nothing)
    assert lay["date"] == c[7] and [k for k, _ in lay["kinds"]] == ["buy", "sell", "exchange", None, "sell_partial"]
    assert lay["body"] == 500 and lay["known"]
    c = _cells(22)                                            # an unknown layout: placed by the dates in it
    ws = [_word("07-01-2025", c[1], 600)] + [_word(t, c[i], y) for i, t in ((5, "10/08/26"), (6, "11/02/26")) for y in (600, 660)]
    lay = pp.layout(c, ws, date(2026, 11, 5))
    assert lay["date"] == c[5] and len(lay["kinds"]) == 3 and len(lay["amounts"]) == 11 and lay["body"] is None
    assert pp.layout(_cells(22), []) is None and pp.layout(_cells(12), [_word("(MM/DD/YY)", c[5])]) is None


def test_one_type_per_row_in_the_forms_order():
    assert pp._kind(["sell", "exchange", "sell_partial"]) == "sell_partial"   # brokers: sale + partial, a stray mark between
    assert pp._kind(["sell_partial"]) == "sell_partial"                      # the House form's own column
    assert pp._kind(["buy", "sell_partial"]) == "buy" and pp._kind(["exchange"]) == "exchange" and pp._kind([]) is None


def test_more_ocr_slips_in_dates_and_headings():
    assert pp.parse_date("7/1(2025", loose=True) == "2025-07-01" and pp.parse_date("7/1(2025") is None   # "/" read as "("
    assert all(pp._date_head(t) for t in ("(MM/DD/YY)", "(MMIDDIYY)", "(MM/ODIYY}", "(MMUDDIYY)", "iMMIODYY)", "(MM/DO/YY)"))
    assert not any(pp._date_head(t) for t in ("Common", "COMMUNITY", "MMM"))
    assert pp._NOTHING.search("NOTHING FO REPORT FOR FEBRUARY 2025") and pp._NOTHING.search("NOTHING CIO] OO | TO REPORT")


def test_tickers_written_on_the_form_and_names_learned_from_electronic_reports():
    assert pp.match_ticker("Zoetis Inc ZTS") == ("ZTS", "Stock")
    assert pp.match_ticker("Paypal Hldgs Inc Com (PYPL)") == ("PYPL", "Stock")
    assert pp.match_ticker("Select Sector Spdr Tr - XLE") == ("XLE", "ETF")
    assert pp.match_ticker("Massachusetts ST FOR ISS SR C BER") == (None, "Other")   # a municipal bond's series, not a ticker
    assert pp.match_ticker("AMZN") == ("AMZN", "Stock") and pp.match_ticker("Sell AT&T Inc @ 25.51")[0] == "T"
    assert pp.name_key("Advanced Micro Devices, Inc. - Common Stock (AMD) [ST]") == "ADVANCED MICRO DEVICES"
    assert pp.name_key("Sell AT&T Inc @ 25.51") == pp.name_key("AT&T Inc. - Common Stock (T) [ST]")
    rows = [{"asset": "Advanced Micro Devices, Inc. - Common Stock (AMD) [ST]", "ticker": "AMD", "asset_type": "Stock"},
            {"asset": "Amazon.com, Inc. - Common Stock (AMZN) [ST]", "ticker": "AMZN", "asset_type": "Stock"},
            {"asset": "Advanced Micro Devic", "ticker": None, "asset_type": "Stock", "ocr": True},
            {"asset": "Amzn", "ticker": None, "asset_type": "Stock", "ocr": True},
            {"asset": "Advanced Drainage Systems", "ticker": None, "asset_type": "Stock", "ocr": True},
            {"asset": "US Treasury Bill", "ticker": None, "asset_type": "Other", "ocr": True}]
    assert congress._fill_tickers(rows) == 2
    assert [r["ticker"] for r in rows[2:]] == ["AMD", "AMZN", None, None]


@need_ocr
def test_the_older_form_is_read():
    """The House form before 2024 (17 columns: purchase, sale, exchange; amounts A-J), typed, with big drawn X's."""
    rows = pp.read_page(img("older_form.png"), date(2026, 11, 10))
    assert [(r["ticker"], r["asset_type"], r["type"]) for r in rows] == [("SPMD", "ETF", "buy"), ("XLE", "ETF", "sell")]
    assert all((r["traded"], r["notified"], r["amount_lo"], r["owner"]) == ("2026-10-22", "2026-11-01", 1001, "Joint") for r in rows)


@need_ocr
def test_the_current_form_is_read():
    """The current House form (19 columns: + partial sale and K, a printed box per mark), typed, with a check mark."""
    rows = pp.read_page(img("current_form.png"), date(2025, 8, 6))
    assert len(rows) == 1 and "AMERICAN EXPRESS BOND" in rows[0]["asset"].upper()
    r = rows[0]
    assert (r["type"], r["traded"], r["notified"], r["amount_lo"], r["owner"], r["ticker"]) == ("sell", "2025-07-01", "2025-08-06", 15001, "Joint", None)


@need_ocr
def test_handwriting_is_read_where_it_can_be_and_never_guessed():
    """Four handwritten rows, all dated 01/10/25 with amount A: the spouse's AT&T, Genuine Parts, Merck and NVIDIA
    trades. A row whose date OCR can't read is counted as skipped, never guessed; what is read must be right."""
    got = pp.read(PdfReader(io.BytesIO(scan_pdf("handwritten.png"))), date(2026, 6, 30))
    assert len(got["rows"]) + got["skipped"] == 4 and not got["nothing"]
    assert all((r["traded"], r["amount_lo"]) == ("2025-01-10", 1001) and r["type"] in ("buy", "sell") for r in got["rows"])


@need_ocr
def test_a_report_of_no_trades_is_read_as_such():
    got = pp.read(PdfReader(io.BytesIO(scan_pdf("nothing.png"))), date(2025, 3, 6))   # "Nothing to report for February 2025"
    assert got == {"rows": [], "nothing": True, "skipped": 0}


def test_a_faint_page_keeps_the_filings_layout_but_another_version_of_the_form_does_not():
    cells = {n: pp.cells_of(pp.rules(ink(n + ".png"))[0]) for n in ("page2", "page4", "cover", "current_form", "older_form")}
    assert pp._same_form(cells["page4"], cells["page2"])                 # broken lines: 18 columns found of 20
    missing = cells["page2"][:10] + [(cells["page2"][10][0], cells["page2"][11][1])] + cells["page2"][12:]
    assert pp._same_form(missing, cells["page2"])
    wider = [(int(a * 1.04) + 20, int(b * 1.04) + 20) for a, b in cells["page2"]]   # scanned a little larger
    assert pp._same_form(wider, cells["page2"])
    assert not pp._same_form(cells["cover"], cells["page2"])             # the House form before brokers' pages
    assert not pp._same_form(cells["current_form"], cells["older_form"])
