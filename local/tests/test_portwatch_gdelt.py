"""PortWatch and GDELT data layers: parsing the recorded answers, retries, throttling and the circuit breaker (no network)."""
import gzip
import json
import os

import pytest
import requests

from semiquant.data import cache, gdelt, portwatch

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "world")


def load(name):
    p = os.path.join(FX, name)
    if name.endswith(".gz"):
        with gzip.open(p, "rt") as f:
            return json.load(f)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def no_cache_no_sleep(monkeypatch):
    """Run the loaders directly (no memory or disk cache) and never really sleep."""
    monkeypatch.setattr(cache, "cached", lambda key, ttl, loader, **kw: loader())
    monkeypatch.setattr(portwatch.time, "sleep", lambda s: None)
    monkeypatch.setattr(gdelt.time, "sleep", lambda s: None)
    gdelt.reset()
    yield
    gdelt.reset()


# ─── PortWatch ────────────────────────────────────────────────────────────────────────────
def test_chokepoint_list_from_the_recorded_answer():
    cps = portwatch.parse_chokepoints(portwatch._rows(load("portwatch_chokepoints.json")))
    assert len(cps) == 28
    assert cps[0]["name"] == "Taiwan Strait" and cps[0]["id"] == "chokepoint11"       # busiest first
    by = {c["id"]: c for c in cps}
    assert by["chokepoint6"]["name"] == "Strait of Hormuz" and 25 < by["chokepoint6"]["lat"] < 27
    assert by["chokepoint26"]["goods"] == []                                          # "None" placeholders dropped
    assert all(a["vessels_per_year"] >= b["vessels_per_year"] for a, b in zip(cps, cps[1:]))


def test_daily_rows_become_sorted_parallel_arrays():
    rows = [r["attributes"] for r in load("portwatch_daily.json.gz")["features"]]
    import random
    random.Random(1).shuffle(rows)                          # input order must not matter
    d = portwatch.parse_daily(rows)
    assert set(d) == {"chokepoint6", "chokepoint1", "chokepoint4", "chokepoint11"}
    h = d["chokepoint6"]
    assert h["name"] == "Strait of Hormuz" and h["dates"] == sorted(h["dates"]) and h["dates"][0] >= "2023-11-01"
    assert len({len(v) for k, v in h.items() if isinstance(v, list)}) == 1
    # PortWatch: every vessel = tankers + cargo ships (container, dry bulk, general cargo, ro-ro)
    for i in range(0, len(h["total"]), 97):
        assert h["total"][i] >= h["tanker"][i] + h["container"][i] + h["dry_bulk"][i]
        assert h["other"][i] >= 0
    assert max(h["total"][-20:]) < 20 < max(h["total"][:200])      # the recorded closure


def test_events_log():
    ev = portwatch.parse_disruptions(portwatch._rows(load("portwatch_disruptions.json")))
    assert [e["start"] for e in ev] == sorted((e["start"] for e in ev), reverse=True)
    h = next(e for e in ev if e["code"] == "HORMUZ-26")
    assert h["type"] == "OT" and h["type_label"] == "Trade disruption" and h["alert"] == "RED"
    assert h["start"] == "2026-03-01" and h["end"] is None and h["ports"] == ["chokepoint6"]
    assert "Strait of Hormuz" in h["name"]
    quake = next(e for e in ev if e["type"] == "EQ")
    assert quake["end"] and quake["type_label"] == "Earthquake"
    cyc = next(e for e in ev if e["type"] == "TC" and len(e["countries"]) > 1)
    assert all(c and c != "None" for c in cyc["countries"])


def test_iso_handles_bad_dates():
    assert portwatch._iso(1772323200000) == "2026-03-01"
    assert portwatch._iso(None) is None and portwatch._iso("") is None and portwatch._iso("x") is None


class Fake:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._body, self.content = status, body, content

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_portwatch_retries_then_succeeds(monkeypatch):
    calls = []

    def get(url, **kw):
        calls.append(url)
        return Fake(503) if len(calls) < 3 else Fake(200, {"features": []})
    monkeypatch.setattr(portwatch.requests, "get", get)
    assert portwatch._query("X")["features"] == [] and len(calls) == 3


def test_portwatch_gives_up_and_reports_service_errors(monkeypatch):
    monkeypatch.setattr(portwatch.requests, "get", lambda *a, **k: Fake(500))
    with pytest.raises(RuntimeError, match="PortWatch X failed"):
        portwatch._query("X")
    monkeypatch.setattr(portwatch.requests, "get", lambda *a, **k: Fake(200, {"error": {"code": 400, "message": "bad where"}}))
    with pytest.raises(RuntimeError, match="bad where"):
        portwatch._query("X")


def test_daily_follows_the_paging(monkeypatch):
    rows = [r["attributes"] for r in load("portwatch_daily.json.gz")["features"] if r["attributes"]["portid"] == "chokepoint6"]
    monkeypatch.setattr(portwatch, "PAGE", 400)
    seen = []

    def q(service, **p):
        seen.append(p["resultOffset"])
        part = rows[p["resultOffset"]:p["resultOffset"] + 400]
        return {"features": [{"attributes": r} for r in part], "exceededTransferLimit": len(part) == 400}
    monkeypatch.setattr(portwatch, "_query", q)
    out = portwatch.daily("2023-11-01")
    assert seen == [0, 400, 800] and len(out["chokepoint6"]["dates"]) == len(rows)


# ─── GDELT ────────────────────────────────────────────────────────────────────────────────
def test_headlines_are_deduplicated_and_newest_first():
    d = load("gdelt_articles.json")
    got = gdelt.parse_articles(d, n=10)
    assert 3 <= len(got) <= 8 and all(a["title"] and a["url"].startswith("http") for a in got)
    assert [a["seen"] for a in got] == sorted((a["seen"] for a in got), reverse=True)
    assert got[0]["seen"].endswith("Z") and "T" in got[0]["seen"]
    dup = {"articles": [{"url": "https://a/1", "title": "Ships  halt in the Gulf", "seendate": "20261101T000000Z", "domain": "a"},
                        {"url": "https://b/2", "title": "SHIPS HALT IN THE GULF!", "seendate": "20261102T000000Z", "domain": "b"},
                        {"url": "https://c/3", "title": "", "seendate": "20261102T000000Z"},
                        {"title": "No link", "seendate": "20261102T000000Z"}]}
    assert [a["url"] for a in gdelt.parse_articles(dup)] == ["https://a/1"]


def test_timeline_parses_the_recorded_answer_and_averages_hourly_points():
    pts = gdelt.parse_timeline(load("gdelt_timeline.json"))
    assert len(pts) >= 50 and pts == sorted(pts) and all(isinstance(v, float) for _, v in pts)
    hourly = {"timeline": [{"series": "Volume Intensity", "data": [
        {"date": "20261101T000000Z", "value": 1.0}, {"date": "20261101T010000Z", "value": 3.0},
        {"date": "20261102T000000Z", "value": 4.0}, {"date": "bad", "value": 9.0}, {"date": "20261103T000000Z", "value": "x"}]}]}
    assert gdelt.parse_timeline(hourly) == [("2026-11-01", 2.0), ("2026-11-02", 4.0)]
    assert gdelt.parse_timeline({}) == []


def test_plain_text_errors_from_gdelt_are_reported():
    with pytest.raises(ValueError, match="too short"):
        gdelt._json(b"The specified phrase is too short.")
    assert gdelt._json(b"") == {}


def test_requests_retry_on_rate_limit(monkeypatch):
    seq = iter([Fake(429), Fake(200, content=b'{"articles": []}')])
    monkeypatch.setattr(gdelt.requests, "get", lambda *a, **k: next(seq))
    assert gdelt._request({"query": "x"}) == b'{"articles": []}'


def test_circuit_breaker_pauses_after_repeated_failures(monkeypatch):
    calls = []

    def get(*a, **k):
        calls.append(1)
        return Fake(429)
    monkeypatch.setattr(gdelt.requests, "get", get)
    for _ in range(gdelt.BLOCK_AFTER):
        with pytest.raises(gdelt.GdeltBusy):
            gdelt._request({"query": "x"})
    n = len(calls)
    with pytest.raises(gdelt.GdeltBusy, match="paused"):
        gdelt._request({"query": "x"})
    assert len(calls) == n                              # paused: no further requests
    gdelt.reset()
    with pytest.raises(gdelt.GdeltBusy, match="rate limit"):
        gdelt._request({"query": "x"})
    assert len(calls) > n


def test_a_success_clears_the_failure_streak(monkeypatch):
    seq = [Fake(429)] * 2 + [Fake(200, content=b"{}")]
    monkeypatch.setattr(gdelt.requests, "get", lambda *a, **k: seq.pop(0))
    with pytest.raises(gdelt.GdeltBusy):
        gdelt._request({"query": "x"})
    assert gdelt._state["fails"] == 1
    gdelt._request({"query": "x"})
    assert gdelt._state["fails"] == 0


def test_articles_and_timeline_end_to_end(monkeypatch):
    raw = {"artlist": json.dumps(load("gdelt_articles.json")).encode(), "timelinevol": json.dumps(load("gdelt_timeline.json")).encode()}
    sent = []

    def req(params):
        sent.append(params)
        return raw[params["mode"]]
    monkeypatch.setattr(gdelt, "_request", req)
    arts = gdelt.articles("(Iran) (strike)", hours=48, n=3)
    assert len(arts) == 3 and sent[0]["query"].endswith("sourcelang:english") and sent[0]["timespan"] == "48h"
    tl = gdelt.timeline("(Iran) (strike)", "timelinevol", 100)
    assert len(tl) > 50 and sent[1]["timespan"] == "100d"
    monkeypatch.setattr(gdelt, "_request", lambda p: b'{"timeline": [{"data": []}]}')
    with pytest.raises(ValueError, match="empty"):
        gdelt.timeline("(Iran) (strike)", "timelinevol", 100)
