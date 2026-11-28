"""World-risk statistics: known answers on synthetic series, then the recorded PortWatch data."""
import gzip
import json
import math
import os
import random
from datetime import date, timedelta

import pytest

from semiquant.analytics import worldrisk as wr
from semiquant.data import portwatch

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "world")
END = date(2026, 11, 22)


def series(n=1200, level=100.0, noise=0.05, seed=3, amp=0.0, phase=0.0, tweak=None):
    """n daily counts ending at END; optional yearly seasonality (amp) and a hook to edit the tail."""
    rnd = random.Random(seed)
    dates = [(END - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    x = []
    for i in range(n):
        season = 1 + amp * math.sin(2 * math.pi * (i / 364.0) + phase)
        x.append(max(0, round(level * season * (1 + rnd.gauss(0, noise)))))
    if tweak:
        tweak(x)
    return dates, x


def test_rolling_and_weekly_means():
    assert wr.rolling_mean([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    assert wr.weekly_means(list(range(14)), 14, 5) == [10.0, 3.0]  # newest block first, partial blocks dropped
    assert wr.weekly_means([1] * 10, 3, 5) == []


def test_steady_traffic_is_normal():
    d, x = series()
    s = wr.transit_stats(d, x)
    assert s["status"] == "normal" and abs(s["chg"]) < 0.08 and s["since"] is None


def test_a_new_closure_is_severe_and_dated():
    def close(x):
        for i in range(-10, 0):
            x[i] = 3
    d, x = series(tweak=close)
    s = wr.transit_stats(d, x)
    start = END - timedelta(days=9)
    assert s["status"] == "severe", s
    assert s["chg7"] < -0.9
    assert abs((date.fromisoformat(s["since"]) - start).days) <= 3 and 5 <= s["days"] <= 14


def test_a_week_long_dip_is_never_severe():
    def dip(x):
        for i in range(-7, 0):
            x[i] = round(x[i] * 0.55)
    d, x = series(tweak=dip)
    assert wr.transit_stats(d, x)["status"] in ("watch", "disrupted")


def test_a_lasting_halving_is_disrupted_and_dated():
    def half(x):
        for i in range(-120, 0):
            x[i] = round(x[i] * 0.5)
    d, x = series(tweak=half)
    s = wr.transit_stats(d, x)
    assert s["status"] == "disrupted"
    assert abs(s["days"] - 120) <= 6


def test_seasonal_swings_are_not_flagged():
    # a +-35% yearly cycle; the last week sits at the bottom of the cycle
    for phase in (0.0, 1.3, 2.6, 4.0, 5.2):
        d, x = series(n=1300, amp=0.35, phase=phase)
        assert wr.transit_stats(d, x)["status"] in ("normal", "watch"), phase
    # ...and a seasonal trough with the cycle's low point exactly at the end
    d, x = series(n=1300, amp=0.35, phase=math.pi / 2 - 2 * math.pi * (1299 / 364.0) + math.pi)
    assert wr.transit_stats(d, x)["status"] == "normal"


def test_a_sustained_surge_is_flagged():
    def up(x):
        for i in range(-21, 0):
            x[i] = round(x[i] * 1.7)
    d, x = series(tweak=up)
    assert wr.transit_stats(d, x)["status"] == "surge"


def test_low_traffic_is_not_judged_by_percentages():
    d, x = series(level=1.5, noise=0.3)
    assert wr.transit_stats(d, x)["status"] == "low"


def test_too_little_history_gives_nothing():
    d, x = series(n=100)
    assert wr.transit_stats(d, x) is None
    assert wr.transit_stats(d[:-1], x) is None  # mismatched lengths


def test_ship_types_and_tonnage():
    def close(x):
        for i in range(-30, 0):
            x[i] = round(x[i] * 0.2)
    d, tot = series(tweak=close)
    tank = [round(v * 0.4) for v in tot]
    cont = [round(v * 0.1) for v in tot]
    tonnes = [v * 1000 for v in tot]
    s = wr.transit_stats(d, tot, tonnes, {"tanker": tank, "container": cont})
    assert s["types"]["tanker"]["chg"] < -0.7 and s["types"]["container"]["chg"] < -0.7
    assert s["tonnes_avg7"] < 0.3 * s["tonnes_base"]
    assert len(s["weekly"]) == 52 and s["weekly"][-1] < s["weekly"][0] * 0.5


def test_world_summary_counts_and_missing_capacity():
    d, ok = series()
    d, closed = series(tweak=lambda x: [x.__setitem__(i, 2) for i in range(-60, 0)])
    stats = {"a": wr.transit_stats(d, ok, [v * 10 for v in ok]), "b": wr.transit_stats(d, closed, [v * 10 for v in closed]),
             "c": None}
    sm = wr.world_summary(stats)
    assert sm["tracked"] == 2 and sm["counts"]["severe"] == 1 and sm["counts"]["normal"] == 1
    # b normally carries half the cargo and is now ~empty: about half the tracked capacity is missing
    assert 0.4 < sm["missing_capacity"] < 0.55
    assert abs(stats["a"]["share"] + stats["b"]["share"] - 1) < 1e-9


def test_attention_flags_a_surge_in_coverage():
    rnd = random.Random(5)
    calm = [1 + rnd.gauss(0, 0.1) for _ in range(90)]
    assert abs(wr.attention(calm)["z"]) < 2
    spike = calm[:-7] + [2.5] * 7
    a = wr.attention(spike)
    assert a["z"] > 5 and a["ratio"] > 2
    assert wr.attention(calm[:20]) is None


# ─── the recorded PortWatch data ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def recorded():
    with gzip.open(os.path.join(FX, "portwatch_daily.json.gz"), "rt") as f:
        rows = [r["attributes"] for r in json.load(f)["features"]]
    out = {}
    for cid, d in portwatch.parse_daily(rows).items():
        out[cid] = wr.transit_stats(d["dates"], d["total"], d["tonnes"], {k: d[k] for k in wr.TYPES})
    return out


def test_recorded_hormuz_is_a_severe_closure_since_march(recorded):
    h = recorded["chokepoint6"]
    assert h["status"] == "severe" and h["chg"] < -0.9 and h["base"] > 50
    assert "2026-02-25" <= h["since"] <= "2026-03-06"
    assert h["types"]["tanker"]["chg"] < -0.9


def test_recorded_busy_lanes_are_normal(recorded):
    assert recorded["chokepoint11"]["status"] == "normal"   # Taiwan Strait
    assert recorded["chokepoint1"]["status"] == "normal"    # Suez Canal
    bab = recorded["chokepoint4"]
    assert bab["status"] in ("watch", "normal") and bab["chg"] < 0
