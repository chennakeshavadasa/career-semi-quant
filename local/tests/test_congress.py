"""Congress trades, SEC filings and the 'who else is trading' service: parsers on real filings (saved in
tests/data), member matching, committee oversight, highlights and the Congress feed (no network)."""
from datetime import date, timedelta
from pathlib import Path

import pytest

from semiquant.data import congress
from semiquant.service import smartmoney as sm

DATA = Path(__file__).parent / "data"


# ─── small parsers ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,lo,hi", [
    ("$1,001 - $15,000", 1001, 15000), ("$50,001 -\n$100,000", 50001, 100000), ("$1,000,001 - $5,000,000", 1000001, 5000000),
    ("Over $50,000,000", 50000001, None), ("Spouse/DC Over $1,000,000", 1000001, None), ("$50,000,001 +", 50000001, None),
    ("--", None, None),
])
def test_parse_amount(text, lo, hi):
    assert congress.parse_amount(text) == (lo, hi)


@pytest.mark.parametrize("raw,want", [("AAPL", "AAPL"), ("BRK.B", "BRK-B"), (" nvda ", "NVDA"), ("--", None), ("", None),
                                      ("NASDAQ: MSFT", "MSFT"), ("N/A", None), ("Common Stock", None)])
def test_yahoo_ticker(raw, want):
    assert congress.yahoo_ticker(raw) == want


def test_house_report_multipage():
    """A three-page electronic report: purchases, full and partial sales, a share class, a table header repeated
    on page 2 and the heading font's missing glyphs (NULs) around every row."""
    rows = congress.parse_house_text((DATA / "house_ptr_multipage.txt").read_text(encoding="utf-8"))
    assert len(rows) == 12
    first = rows[0]
    assert first["ticker"] == "BRK-B" and first["type"] == "buy" and first["traded"] == "2026-08-07"
    assert (first["amount_lo"], first["amount_hi"]) == (1001, 15000) and first["owner"] == "Self"
    assert first["asset"] == "Berkshire Hathaway Inc. New Common Stock"  # no label debris, no ticker suffix
    assert {r["type"] for r in rows} == {"buy", "sell", "sell_partial"}
    assert {r["ticker"] for r in rows} >= {"CB", "IBM", "MRK", "MRNA", "QCOM"}
    assert all(r["notified"] == "2026-09-01" for r in rows)
    assert not any("\x00" in r["asset"] or ": New" in r["asset"] for r in rows)


def test_house_report_spouse_bonds_split_amounts():
    rows = congress.parse_house_text((DATA / "house_ptr_spouse_bonds.txt").read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert all(r["owner"] == "Spouse" and r["ticker"] is None and r["asset_type"] == "Government bond" for r in rows)
    assert all((r["amount_lo"], r["amount_hi"]) == (50001, 100000) for r in rows)  # "$50,001 -" / "$100,000" on two lines
    assert rows[0]["type"] == "sell" and rows[0]["traded"] == "2026-08-17"


def test_senate_report():
    rows = congress.parse_senate_html((DATA / "senate_ptr.html").read_text(encoding="utf-8"))
    assert len(rows) == 3
    assert {r["ticker"] for r in rows} == {"NVDA"} and {r["type"] for r in rows} == {"buy"}
    assert sorted(r["traded"] for r in rows) == ["2026-11-05", "2026-11-07", "2026-11-09"]
    assert rows[0]["asset"] == "NVIDIA Corporation - Common Stock" and rows[0]["owner"] == "Self"


def test_empty_inputs():
    assert congress.parse_house_text("") == [] and congress.parse_senate_html("<html></html>") == []


# ─── member matching ─────────────────────────────────────────────────────────

def _people():
    m = lambda bid, first, last, ch, st, dist=None, nick=None: {"bioguide": bid, "name": f"{first} {last}", "first": first, "last": last,
                                                              "nickname": nick, "chamber": ch, "state": st, "district": dist, "party": "R", "committees": []}
    house = [m("A1", "Lloyd", "Doggett", "House", "TX", 37), m("A2", "Mike", "Kelly", "House", "PA", 16), m("A3", "Trent", "Kelly", "House", "MS", 1)]
    senate = [m("S1", "Rafael", "Cruz", "Senate", "TX", nick="Ted"), m("S2", "Rand", "Paul", "Senate", "KY"),
              m("S3", "Mark", "Kelly", "Senate", "AZ"), m("S4", "John", "Kennedy", "Senate", "LA")]
    by_id = {x["bioguide"]: x for x in house + senate}
    return {"by_id": by_id, "house": {(x["state"], x["district"]): x for x in house}, "senate": senate}


def test_match_house_by_seat_then_name():
    p = _people()
    assert congress._match_house(p, "Doggett", "Lloyd", "TX37")["bioguide"] == "A1"
    assert congress._match_house(p, "Kelly", "Mike", "PA16")["bioguide"] == "A2"  # two House Kellys: the seat decides
    assert congress._match_house(p, "Nobody", "X", "ZZ01") is None


def test_match_senate_by_name_and_nickname():
    p = _people()
    assert congress._match_senate(p, "Cruz", "Ted")["bioguide"] == "S1"  # filed as "Cruz, Ted"
    assert congress._match_senate(p, "Paul", "Rand")["bioguide"] == "S2"
    assert congress._match_senate(p, "Kelly", "Mark")["bioguide"] == "S3"


# ─── service ─────────────────────────────────────────────────────────────────

def test_role_of():
    assert sm.role_of("Chief Executive Officer") == "top" and sm.role_of("Chairman of the Board") == "top"
    assert sm.role_of("Beneficial Owner of more than 10% of a Class of Security") == "owner"
    assert sm.role_of("Director") == "director" and sm.role_of("General Counsel") == "officer"


def test_oversight_industry_beats_sector():
    semis = sm.oversight_committees("Technology", "Semiconductors")
    assert {"HSIF", "SSCM", "HSZS"} <= semis and "HSJU" not in semis  # chips: commerce/China, not antitrust
    assert {"HSJU", "SSJU"} <= sm.oversight_committees("Communication Services", "Internet Content & Information")
    assert sm.oversight_committees("Financial Services", "Banks - Diversified") == {"HSBA", "SSBK"}
    assert {"HSAS", "SSAS"} <= sm.oversight_committees("Industrials", "Aerospace & Defense")
    assert sm.oversight_committees("Technology", None) == {"HSIF", "HSSY", "SSCM"}
    assert sm.oversight_committees(None, None) == set()


def test_issuer_name():
    assert sm._issuer("Snowflake Inc. - Class A Common Stock") == "Snowflake Inc."
    assert sm._issuer("General Mills, Inc. Common Stock") == "General Mills, Inc."
    assert sm._issuer(None) is None


def _d(n):
    return str(date.today() - timedelta(days=n))


def _trade(member, bioguide, side, traded, disclosed, lo=1001, hi=15000, ticker="NVDA"):
    return {"chamber": "House", "member": member, "bioguide": bioguide, "party": "R", "state": "OH", "ticker": ticker,
            "asset": "NVIDIA Corporation - Common Stock", "asset_type": "Stock", "type": side, "amount_lo": lo, "amount_hi": hi,
            "traded": traded, "disclosed": disclosed, "owner": "Self", "url": "https://example/filing"}


@pytest.fixture
def sources(monkeypatch):
    seats = {"B1": [{"code": "HSIF", "name": "House Committee on Energy and Commerce", "title": "Chair"}],
             "B2": [{"code": "HSAG", "name": "House Committee on Agriculture", "title": None}]}
    rows = [_trade("Big Seller", "B1", "sell", _d(80), _d(10), 250001, 500000), _trade("Big Seller", "B1", "sell", _d(70), _d(9), 1001, 15000),
            _trade("Farm Member", "B2", "buy", _d(40), _d(5)), _trade("Late Buyer", "B1", "buy", _d(200), _d(20)),
            _trade("Other", None, "buy", _d(30), _d(3), ticker="AAPL")]
    monkeypatch.setattr(congress, "trades", lambda days=730, read_new=True: {"rows": rows, "committees": seats, "stats": {}, "as_of": "now"})
    monkeypatch.setattr(sm.sec, "recent", lambda sym: {
        "form4": [{"form": "4", "filed": _d(1), "period": _d(3), "party": "Doe Jane", "url": "u4"}],
        "form144": [{"form": "144", "filed": _d(2), "period": None, "party": "Doe Jane", "url": "u144"}],
        "stakes": [{"form": "SCHEDULE 13D", "filed": _d(30), "period": None, "party": "Activist Capital LP", "url": "u13d"}]})
    monkeypatch.setattr(sm.yahoo, "info", lambda sym: {"sector": "Technology", "industry": "Semiconductors", "shortName": "NVIDIA"})
    monkeypatch.setattr(sm.tk, "ownership", lambda sym: {
        "insider_transactions": [
            {"date": _d(20), "insider": "HUANG JEN", "position": "Chief Executive Officer", "kind": "sell", "value": 5e7, "shares": 1e5, "text": "Sale"},
            {"date": _d(25), "insider": "CFO PERSON", "position": "Chief Financial Officer", "kind": "sell", "value": 1e7, "shares": 2e4, "text": "Sale"}],
        "insider_summary": {"6M": {"buys": 0, "sells": 2, "net_value": -6e7}},
        "institutional": [{"Holder": "Big Index", "pctHeld": 0.08, "pctChange": 0.03, "Shares": 1, "Value": 1, "Date Reported": "2026-09-30"},
                          {"Holder": "Tiny Fund", "pctHeld": 0.001, "pctChange": -0.5, "Shares": 1, "Value": 1, "Date Reported": "2026-09-30"}],
        "mutualfund": [{"Holder": "Growth Fund", "pctHeld": 0.006, "pctChange": -0.12, "Shares": 1, "Value": 1, "Date Reported": "2026-06-30"}],
        "short": {"change_mom": 0.2, "pct_float": 0.02, "days_to_cover": 2, "date": _d(15)}})
    from semiquant.data import cache
    cache.invalidate("svc:smart:")
    cache.invalidate("svc:congress-feed:")
    yield


def test_ticker_highlights(sources):
    d = sm.ticker("NVDA")
    kinds = [h["kind"] for h in d["highlights"]]
    assert {"planned_sale", "exec_selling", "activist", "congress_committee", "congress", "funds", "short"} <= set(kinds)
    assert [h["level"] for h in d["highlights"]] == sorted((h["level"] for h in d["highlights"]), key=["red", "amber", "green", "info"].index)
    committee = [h for h in d["highlights"] if h["kind"] == "congress_committee"]
    assert len(committee) == 2  # Big Seller once (two sales), Late Buyer; the Agriculture member is not linked to chips
    big = next(h for h in committee if "Big Seller" in h["title"])
    assert big["level"] == "red" and "Energy and Commerce (Chair)" in big["title"] and "$250K" in big["title"]
    late = next(h for h in committee if "Late Buyer" in h["title"])
    assert "Late" in late["detail"] and late["level"] == "amber"
    assert next(h for h in d["highlights"] if h["kind"] == "planned_sale")["new"] is True
    assert [f["holder"] for f in d["funds"]] == ["Big Index", "Growth Fund"]  # under 0.5% left out
    assert len(d["congress"]) == 4 and all(r["lag_days"] is not None for r in d["congress"])
    assert any(r["relevant"] for r in d["congress"]) and d["links"]


def test_congress_feed(sources):
    f = sm.congress_feed(90)
    assert f["totals"]["trades"] == 5 and f["totals"]["buys"] == 3 and f["totals"]["sells"] == 2
    assert f["most_bought"][0]["ticker"] in ("NVDA", "AAPL")
    assert next(r for r in f["rows"] if r["member"] == "Big Seller")["committee"] == "House Committee on Energy and Commerce"
    year = sm.congress_feed(365)
    assert year["totals"]["trades"] == 5  # the totals count every trade ...
    assert len(year["rows"]) == 3 and all(r["committee"] or (r["lo"] or 0) >= 100001 for r in year["rows"])  # ... rows: notable ones
