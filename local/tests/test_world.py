"""World risk page: the curated map's integrity, the service with its three sources faked, the server API and the publisher."""
import gzip
import json
import os
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from semiquant import world as W
from semiquant.data import cache, gdelt, portwatch, yahoo
from semiquant.publish import Publisher, file_key
from semiquant.service import world as sw
from semiquant.universe import ALL_META

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "world")


def load(name):
    p = os.path.join(FX, name)
    if name.endswith(".gz"):
        with gzip.open(p, "rt") as f:
            return json.load(f)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


CHOKEPOINTS = portwatch.parse_chokepoints(portwatch._rows(load("portwatch_chokepoints.json")))
DAILY = portwatch.parse_daily([r["attributes"] for r in load("portwatch_daily.json.gz")["features"]])
EVENTS = portwatch.parse_disruptions(portwatch._rows(load("portwatch_disruptions.json")))


# ─── the curated map ──────────────────────────────────────────────────────────────────────
def test_every_chokepoint_has_notes_and_every_note_belongs_to_a_chokepoint():
    ids = {c["id"] for c in CHOKEPOINTS}
    assert set(W.CHOKEPOINTS) == ids
    for cid, info in W.CHOKEPOINTS.items():
        assert all(info[k] for k in ("role", "carries", "if_closed")), cid


def test_links_between_chokepoints_flashpoints_assets_and_chip_items_resolve():
    th = {t["id"] for t in W.THEATRES}
    assert len(th) == len(W.THEATRES)
    for cid, info in W.CHOKEPOINTS.items():
        assert set(info["theatres"]) <= th, cid
        assert set(info["assets"]) <= set(W.ASSETS), cid
    for t in W.THEATRES:
        assert set(t["chokepoints"]) <= set(W.CHOKEPOINTS), t["id"]
        assert set(t["assets"]) <= set(W.ASSETS), t["id"]
        assert t["affects"] and t["name"] and t["region"]
    for x in W.SEMIS:
        assert set(x["chokepoints"]) <= set(W.CHOKEPOINTS), x["id"]
        assert set(x["theatres"]) <= th, x["id"]
        assert x["why"] and x["label"]
    assert {a["group"] for a in W.ASSETS.values()} == set(W.ASSET_GROUPS)


def test_chip_tickers_are_in_the_universe():
    missing = sorted({t for x in W.SEMIS for t in x["tickers"]} - set(ALL_META))
    assert not missing, f"not in the semiconductor universe: {missing}"


def test_gdelt_queries_are_well_formed():
    for t in W.THEATRES:
        q = t["query"]
        assert q.count("(") == q.count(")") and q.count('"') % 2 == 0, t["id"]
        assert re.match(r"\s*\(?[\w\"]", q) and len(q) < 400
        assert sw._terms(q), t["id"]                          # a relevance filter can be built from it
    assert sw._terms('("Strait of Hormuz" OR Hormuz OR Iran) (blockade OR strike)') == ["strait of hormuz", "hormuz", "iran"]
    assert sw._terms("India Pakistan (border OR strike)") == ["india", "pakistan"] or sw._terms("India Pakistan (border OR strike)")


def test_headline_relevance_filter_drops_junk():
    terms = ["strait of hormuz", "hormuz", "persian gulf", "iran"]
    assert sw._relevant("US disables merchant vessel trying to evade Iran blockade", terms)
    assert not sw._relevant("newsroomamerica . com", terms)
    assert not sw._relevant("AP News Summary at 5 : 15 a . m . EST", terms)
    assert not sw._relevant("Stocks rise as markets await jobs report data", terms)


# ─── the service, with sources faked ──────────────────────────────────────────────────────
def frame(seed, drift=0.0, spike=0.0, n=260):
    rnd = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rnd.normal(drift, 0.01, n)))
    if spike:
        px[-5:] *= np.linspace(1.0, 1 + spike, 5)
    return pd.DataFrame({"close": px}, index=pd.bdate_range(end="2026-11-27", periods=n))


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(cache, "cached", lambda key, ttl, loader, **kw: loader())
    monkeypatch.setattr(portwatch, "chokepoints", lambda: CHOKEPOINTS)
    monkeypatch.setattr(portwatch, "daily", lambda since: DAILY)
    monkeypatch.setattr(portwatch, "disruptions", lambda: EVENTS)
    frames = {s: frame(i) for i, s in enumerate(W.ASSETS)}
    frames["BZ=F"] = frame(99, spike=0.25)                                   # an oil spike
    monkeypatch.setattr(yahoo, "daily_many", lambda syms, period="10y", live=True: {s: frames[s] for s in syms if s in frames})
    monkeypatch.setattr(yahoo, "quotes", lambda syms: {s: {"change_pct": 1.5, "price": 100.0} for s in syms})
    return monkeypatch


def test_overview_reports_the_hormuz_closure(fake):
    d = sw._overview()
    rows = {r["id"]: r for r in d["chokepoints"]}
    assert d["chokepoints"][0]["id"] == "chokepoint6"                        # worst first
    h = rows["chokepoint6"]
    assert h["status"] == "severe" and h["status_text"] == "Severe disruption" and h["chg"] < -0.9
    assert h["since"] == "2026-03-01" and h["since_source"] == "portwatch" and h["days"] > 250    # the date PortWatch logged
    assert h["types"]["tanker"]["chg"] < -0.9 and len(h["weekly"]) == 52
    assert "Strait of Hormuz" in h["role"] or "Persian Gulf" in h["role"]
    assert rows["chokepoint11"]["status"] == "normal"
    s = d["summary"]
    assert s["counts"]["severe"] == 1 and s["tracked"] == 4 and 0 < s["missing_capacity"] < 1
    assert d["summary"]["headline"].startswith("Strait of Hormuz:") and "since 1 Mar 2026" in d["summary"]["headline"]
    assert s["longest"]["id"] == "chokepoint6" and s["longest"]["days"] > 250
    assert d["sources"]["portwatch"]["ok"] and d["sources"]["yahoo"]["ok"] and d["errors"] == []
    ev = next(e for e in d["events"] if e["code"] == "HORMUZ-26")
    assert ev["ongoing"] and ev["chokepoints"] == [{"id": "chokepoint6", "name": "Strait of Hormuz"}]
    json.dumps(d, allow_nan=False)                                           # publishable as is


def test_overview_markets_flag_a_spike(fake):
    d = sw._overview()
    m = {x["symbol"]: x for x in d["markets"]}
    assert len(m) == len(W.ASSETS)
    assert m["BZ=F"]["z5"] > 2 and m["BZ=F"]["chg5d"] > 0.1 and len(m["BZ=F"]["spark"]) == 60
    assert d["summary"]["markets_stressed"] >= 1
    assert abs(m["GC=F"]["z5"]) < 4 and m["GC=F"]["group"] == "Havens & defense"


def test_chip_supply_items_light_up_from_the_straits(fake):
    d = sw._overview()
    items = {x["id"]: x for x in d["semis"]}
    assert items["gulf_helium_lng"]["level"] == "alert"
    assert any(s["kind"] == "chokepoint" and s["status"] == "severe" for s in items["gulf_helium_lng"]["signals"])
    assert items["taiwan_fabs"]["level"] == "calm"
    assert items["battery_metals"]["level"] == "calm" and items["battery_metals"]["tickers"] == []
    assert d["semis"][0]["level"] == "alert"                                # alerts first
    t = items["gulf_helium_lng"]["tickers"][0]
    assert t["symbol"] and t["change_pct"] == 1.5


def test_a_failing_source_leaves_its_section_empty_not_the_page(fake):
    fake.setattr(yahoo, "daily_many", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    d = sw._overview()
    assert d["markets"] == [] and d["chokepoints"] and any("markets" in e for e in d["errors"]) and not d["sources"]["yahoo"]["ok"]
    fake.setattr(portwatch, "daily", lambda since: (_ for _ in ()).throw(RuntimeError("portwatch down")))
    fake.setattr(yahoo, "daily_many", lambda syms, period="10y", live=True: {s: frame(1) for s in syms})
    d = sw._overview()
    assert d["chokepoints"] == [] and d["markets"] and d["semis"] == []
    fake.setattr(yahoo, "daily_many", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    with pytest.raises(RuntimeError):
        sw._overview()


def test_chokepoint_detail_series(fake):
    d = sw.chokepoint("chokepoint6")
    n = len(d["dates"])
    assert n == sw.DETAIL_DAYS and all(len(d[k]) == n for k in ("total", "tanker", "container", "dry_bulk", "other"))
    assert d["status"] == "severe" and d["base"] > 50 and d["total"][-1] < 20
    with pytest.raises(KeyError):
        sw.chokepoint("chokepoint99")


def test_news_filters_headlines_and_drops_today(fake):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tl = [(f"2026-0{m}-{d:02d}", 0.5) for m in (8, 9, 10) for d in range(1, 28)] + [(today, 99.0)]
    fake.setattr(gdelt, "articles", lambda q, hours=72, n=8: [
        {"title": "US disables merchant vessel trying to evade Iran blockade", "url": "https://a", "domain": "a.com", "seen": "2026-11-28T10:45:00Z", "country": ""},
        {"title": "newsroomamerica . com", "url": "https://b", "domain": "b", "seen": "2026-11-28T10:45:00Z", "country": ""}])
    fake.setattr(gdelt, "timeline", lambda q, mode="timelinevol", days=100: tl)
    d = sw.news("iran_gulf")
    assert [h["domain"] for h in d["headlines"]] == ["a.com"]
    assert d["attention"]["z"] < 1 and d["series"][-1][0] != today and d["errors"] == [] and d["available"] is True
    # headlines survive a rate-limited trend, and the other way round
    fake.setattr(gdelt, "timeline", lambda *a, **k: (_ for _ in ()).throw(gdelt.GdeltBusy("rate limit")))
    d = sw.news("iran_gulf")
    assert d["headlines"] and d["attention"] is None and "trend" in d["errors"][0] and d["available"] is False
    fake.setattr(gdelt, "articles", lambda *a, **k: (_ for _ in ()).throw(gdelt.GdeltBusy("rate limit")))
    with pytest.raises(RuntimeError):
        sw.news("iran_gulf")
    with pytest.raises(KeyError):
        sw.news("atlantis")


# ─── API and publisher ────────────────────────────────────────────────────────────────────
def test_static_file_names_match_the_browser():
    assert file_key("/api/world") == "world.json"
    assert file_key("/api/world/chokepoint/chokepoint6") == "world/chokepoint/chokepoint6.json"
    assert file_key("/api/world/news?theatre=iran_gulf") == "world/news__theatre-iran_gulf.json"


def test_api_routes(fake):
    from fastapi.testclient import TestClient
    from semiquant.server.app import create_app
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/api/world")
    assert r.status_code == 200 and r.json()["chokepoints"][0]["id"] == "chokepoint6"
    assert c.get("/api/world/chokepoint/chokepoint6").json()["name"] == "Strait of Hormuz"
    assert c.get("/api/world/chokepoint/nope").status_code == 404
    assert c.get("/api/world/news?theatre=nope").status_code == 404


def test_publisher_writes_the_world_files_and_keeps_going_when_news_fails(fake, tmp_path):
    fake.setattr(gdelt, "articles", lambda *a, **k: (_ for _ in ()).throw(gdelt.GdeltBusy("rate limit")))
    fake.setattr(gdelt, "timeline", lambda *a, **k: (_ for _ in ()).throw(gdelt.GdeltBusy("rate limit")))
    pub = Publisher(tmp_path)
    pub.data.mkdir(parents=True)
    pub.world()
    assert json.loads((pub.data / "world.json").read_text())["chokepoints"][0]["id"] == "chokepoint6"
    assert json.loads((pub.data / "world/chokepoint/chokepoint6.json").read_text())["status"] == "severe"
    # the news could not be fetched: an explicit empty answer the page can explain, retried at every refresh
    n = json.loads((pub.data / "world/news__theatre-iran_gulf.json").read_text())
    assert n["unavailable"] is True and "PortWatch, GDELT or Yahoo" in n["message"]
    assert pub.due("/api/world/news?theatre=iran_gulf", "hourly")
    assert len(list((pub.data / "world").glob("news__*.json"))) == len(W.THEATRES)


def test_a_partial_news_answer_is_retried_at_every_refresh(fake, tmp_path):
    fake.setattr(gdelt, "articles", lambda q, hours=72, n=8: [
        {"title": "US disables merchant vessel trying to evade Iran blockade", "url": "https://a", "domain": "a.com", "seen": "2026-11-28T10:45:00Z", "country": ""}])
    fake.setattr(gdelt, "timeline", lambda *a, **k: (_ for _ in ()).throw(gdelt.GdeltBusy("rate limit")))
    pub = Publisher(tmp_path)
    pub.data.mkdir(parents=True)
    pub.world()
    path = "/api/world/news?theatre=iran_gulf"
    f = json.loads((pub.data / file_key(path)).read_text())
    assert f["headlines"] and f["available"] is False
    assert pub.due(path, "hourly")                     # headlines are kept, the missing trend is fetched again next time


def test_the_publisher_stops_asking_gdelt_once_it_has_paused_itself(fake, tmp_path):
    import time
    asked = []
    fake.setattr(gdelt, "articles", lambda *a, **k: asked.append(1) or [])
    fake.setitem(gdelt._state, "blocked_until", time.time() + 100)
    try:
        pub = Publisher(tmp_path)
        pub.data.mkdir(parents=True)
        pub.world()
    finally:
        gdelt.reset()
    assert not asked and pub.stats["deferred"] == len(W.THEATRES)
    assert (pub.data / "world.json").exists()          # everything that does not need GDELT is still published


def test_quick_news_uses_a_cached_trend_and_warms_a_missing_one(fake):
    calls = []
    fake.setattr(gdelt, "articles", lambda q, hours=72, n=8: [
        {"title": "US disables merchant vessel trying to evade Iran blockade", "url": "https://a", "domain": "a.com", "seen": "2026-11-28T10:45:00Z", "country": ""}])
    fake.setattr(gdelt, "timeline", lambda *a, **k: calls.append(1) or [("2026-10-01", 1.0)] * 40)
    fake.setattr(gdelt, "cached_timeline", lambda *a, **k: None)
    d = sw.news("iran_gulf", quick=True)
    assert d["headlines"] and d["attention"] is None and "loading" in d["errors"][0]
    import time
    for _ in range(50):
        if calls:
            break
        time.sleep(0.02)
    assert calls == [1]                                    # fetched in the background for the next load
    fake.setattr(gdelt, "cached_timeline", lambda *a, **k: [(f"2026-10-{d:02d}", 1.0) for d in range(1, 31)] * 3)
    assert sw.news("iran_gulf", quick=True)["attention"] is not None


def test_no_platform_specific_date_formats():
    # "%-d" (no leading zero) is a glibc extension: Windows' strftime raises "Invalid format string"
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "semiquant"
    bad = [f"{p.name}:{i + 1}" for p in root.rglob("*.py") for i, line in enumerate(p.read_text(encoding="utf-8").splitlines())
           if re.search(r"strftime\([^)]*%-", line)]
    assert not bad, bad
