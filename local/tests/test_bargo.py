"""Bargo cross-check: Bargo's free Congress API (a recorded real answer) against our own reading of the filings."""
import json
import os

import pytest

from semiquant.data import bargo, cache, congress

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def recorded():
    with open(os.path.join(D, "bargo_nvda.json"), encoding="utf-8") as f:
        return json.load(f)


def member(bioguide, name, last, state, district=None, chamber="House", party="R"):
    return {"bioguide": bioguide, "name": name, "last": last, "first": name.split()[0], "state": state, "district": district,
            "chamber": chamber, "party": party}


PEOPLE = {"by_id": {}, "house": {}, "senate": []}
for m in (member("R000610", "Michael A. Rulli", "Rulli", "OH", 6), member("C001123", "Gilbert Ray Cisneros, Jr.", "Cisneros", "CA", 31, party="D"),
          member("M001204", "Daniel Meuser", "Meuser", "PA", 9), member("S000168", "Maria Elvira Salazar", "Salazar", "FL", 27),
          member("H001096", "Harriet M. Hageman", "Hageman", "WY", 0), member("S000250", "Pete Sessions", "Sessions", "TX", 17),
          member("F000110", "Cleo Fields", "Fields", "LA", 6, party="D")):
    PEOPLE["by_id"][m["bioguide"]] = m
    PEOPLE["house"][(m["state"], m["district"])] = m


def test_bargo_rows_take_our_shape():
    rows = bargo.parse(recorded())
    assert len(rows) == 11 and all(r["source"] == "bargo" and r["ticker"] == "NVDA" for r in rows)
    r = rows[0]
    assert (r["member"], r["chamber"], r["state_dst"], r["type"], r["traded"], r["disclosed"]) == (
        "Michael Rulli", "House", "OH06", "sell", "2026-10-28", "2026-11-18")
    assert (r["amount_lo"], r["amount_hi"]) == (1001, 15000)
    assert {x["type"] for x in rows} == {"buy", "sell"}
    assert bargo.parse({"trades": [{"ticker": None, "transaction_date": "2026-10-01"}, {"ticker": "AAPL"}]}) == []
    assert bargo.parse({"trades": [{"ticker": "BRK.B", "transaction_date": "2026-10-01", "type": "Sale (Partial)", "chamber": "senate"}]})[0][
        "type"] == "sell_partial"


def test_names_match_across_spellings():
    assert congress._last_name("Gilbert Ray Cisneros, Jr.") == congress._last_name("Gilbert Cisneros") == "cisneros"
    assert congress._last_name("Hon. Michael A. Rulli") == congress._last_name("Michael Rulli") == "rulli"
    assert congress._last_name("María Elvira Salazar") == "salazar"
    ours = {"traded": "2026-10-28", "ticker": "NVDA", "type": "sell_partial", "member": "Michael A. Rulli"}
    theirs = {"traded": "2026-10-28", "ticker": "nvda", "type": "sell", "member": "Michael Rulli"}
    assert congress._trade_key(ours) == congress._trade_key(theirs)


def test_cross_check_counts_matches_and_adds_only_what_we_missed(monkeypatch):
    theirs = bargo.parse(recorded())
    monkeypatch.setattr(bargo, "recent", lambda days=21, limit=100: theirs)
    # we already have every trade except Cleo Fields' three and Meuser's 2026-09-25 sale
    ours = [{"traded": t["traded"], "ticker": "NVDA", "type": t["type"], "member": t["member"] + " Jr."} for t in theirs
            if not (t["member"] == "Cleo Fields" or (t["member"] == "Daniel Meuser" and t["traded"] == "2026-09-25"))]
    extra, st = congress.cross_check(ours, PEOPLE)
    assert st == {"checked": 11, "matched": 7, "added": 4, "source": "Bargo", "url": bargo.HOME}
    assert sorted((x["member"], x["traded"]) for x in extra) == [("Cleo Fields", "2026-10-01")] * 3 + [("Daniel Meuser", "2026-09-25")]
    f = next(x for x in extra if x["member"] == "Cleo Fields")
    assert f["source"] == "bargo" and f["bioguide"] == "F000110" and f["party"] == "D" and f["state"] == "LA" and "state_dst" not in f


def test_a_failing_bargo_never_breaks_the_congress_data(monkeypatch):
    def down(days=21, limit=100):
        raise RuntimeError("Bargo free limit reached for today")
    monkeypatch.setattr(bargo, "recent", down)
    extra, st = congress.cross_check([{"traded": "2026-10-01", "ticker": "NVDA", "type": "buy", "member": "X"}], PEOPLE)
    assert extra == [] and "limit" in st["error"]


def test_recent_asks_once_and_respects_the_rate_limit(monkeypatch):
    monkeypatch.setattr(cache, "cached", lambda key, ttl, loader, **kw: loader())
    calls = []

    class R:
        def __init__(self, code, body=None):
            self.status_code, self._b = code, body

        def json(self):
            return self._b

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)
    monkeypatch.setattr(bargo.requests, "get", lambda url, params=None, **kw: calls.append(params) or R(200, recorded()))
    assert len(bargo.recent(days=21)) == 11 and calls[0]["limit"] == 100 and "from" in calls[0]
    monkeypatch.setattr(bargo.requests, "get", lambda *a, **k: R(429))
    with pytest.raises(RuntimeError, match="limit"):
        bargo.recent()
