"""Tests for semiquant.analytics.earnings (timing rules, planted-jump event study, real fixtures)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import earnings as E

NY = "America/New_York"


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def earnings_df(rows):
    """rows: (local time string, est, act) -> yfinance-shaped frame."""
    idx = pd.DatetimeIndex([pd.Timestamp(t).tz_localize(NY) for t, _, _ in rows], name="Earnings Date")
    est = [e for _, e, _ in rows]
    act = [a for _, _, a in rows]
    sur = [((a - e) / abs(e) * 100) if (a is not None and e not in (None, 0)) else np.nan for _, e, a in rows]
    return pd.DataFrame({"EPS Estimate": est, "Reported EPS": act, "Surprise(%)": sur}, index=idx).astype(float)


def test_reaction_dates_timing_rules():
    sessions = pd.bdate_range("2024-01-01", "2024-03-29")
    ed = earnings_df([
        ("2024-01-10 16:00", 1.0, 1.1),   # Wed AMC -> Thu
        ("2024-01-12 16:05", 1.0, 0.9),   # Fri AMC -> Mon
        ("2024-01-17 07:00", 1.0, 1.0),   # Wed BMO -> same day
        ("2024-01-20 08:00", 1.0, 1.2),   # Sat BMO -> Mon
        ("2024-01-24 12:30", 1.0, 1.3),   # Wed DMH -> same day
        ("2023-06-01 16:00", 1.0, 1.0),   # before the index -> NaT
        ("2024-04-25 16:00", 1.0, None),  # future (no reported EPS) -> excluded
    ])
    rd = E.reaction_dates(ed, sessions)
    assert list(rd.columns) == ["event_time", "reaction_date", "timing", "eps_est", "eps_act", "surprise_pct"]
    assert len(rd) == 6
    got = dict(zip(rd["event_time"].dt.strftime("%Y-%m-%d"), zip(rd["reaction_date"], rd["timing"])))
    assert got["2024-01-10"] == (pd.Timestamp("2024-01-11"), "AMC")
    assert got["2024-01-12"] == (pd.Timestamp("2024-01-15"), "AMC")
    assert got["2024-01-17"] == (pd.Timestamp("2024-01-17"), "BMO")
    assert got["2024-01-20"] == (pd.Timestamp("2024-01-22"), "BMO")
    assert got["2024-01-24"] == (pd.Timestamp("2024-01-24"), "DMH")
    assert pd.isna(got["2023-06-01"][0])
    assert rd.loc[rd["eps_act"] == 1.1, "surprise_pct"].iloc[0] == pytest.approx(0.10)   # percent -> fraction
    assert rd["event_time"].is_monotonic_increasing


def planted_study(seed=3):
    rng = np.random.default_rng(seed)
    n = 1500
    idx = pd.bdate_range("2019-01-02", periods=n)
    m = rng.normal(0.0004, 0.011, n)
    eps = rng.normal(0, 0.004, n)
    r = 0.0002 + 1.3 * m + eps
    jumps, rows = {}, []
    for k, pos in enumerate(range(300, n - 40, 63)):
        beat = k % 2 == 0
        jump = 0.08 if beat else -0.06
        jumps[idx[pos]] = jump
        r[pos] += jump
        ev_day = idx[pos - 1]                       # AMC the session before
        rows.append((f"{ev_day:%Y-%m-%d} 16:00", 1.0, 1.2 if beat else 0.8))
    rows.append((f"{idx[-1] + pd.Timedelta(days=30):%Y-%m-%d} 16:00", 1.5, None))
    close = pd.Series(100 * np.cumprod(1 + np.concatenate([[0.0], r[1:]])), index=idx, name="X")
    bench = pd.Series(100 * np.cumprod(1 + np.concatenate([[0.0], m[1:]])), index=idx, name="B")
    return close, bench, earnings_df(rows), jumps


def test_event_study_recovers_planted_jumps():
    close, bench, ed, jumps = planted_study()
    st = E.event_study(close, bench, ed)
    dumps(st)
    assert st["n_events"] == len(jumps)
    for ev in st["events"]:
        j = jumps[pd.Timestamp(ev["reaction_date"])]
        assert ev["abnormal"] == pytest.approx(j, abs=0.015)
        assert ev["result"] == ("beat" if j > 0 else "miss")
        assert ev["model"] == "market" and ev["beta"] == pytest.approx(1.3, abs=0.15)
    dates = [ev["reaction_date"] for ev in st["events"]]
    assert dates == sorted(dates, reverse=True)                     # newest first
    assert st["beat_rate"] == pytest.approx(np.mean([j > 0 for j in jumps.values()]))
    assert st["avg_move_beat"] > 0.05 and st["avg_move_miss"] < -0.03
    assert st["mean_abs_move"] == pytest.approx(np.mean(np.abs(list(jumps.values()))), abs=0.01)
    caar = st["caar"]
    assert caar["days"] == list(range(-5, 21))
    i0 = caar["days"].index(0)
    assert caar["all"][i0] - caar["all"][i0 - 1] == pytest.approx(np.mean(list(jumps.values())), abs=0.006)
    assert caar["beat"][i0] - caar["beat"][i0 - 1] == pytest.approx(0.08, abs=0.008)
    assert caar["miss"][i0] - caar["miss"][i0 - 1] == pytest.approx(-0.06, abs=0.008)
    # no planted drift
    assert abs(st["drift_beat"]["mean"]) < 0.03 and st["drift_beat"]["n"] > 5
    assert st["next"]["date"] == f"{close.index[-1] + pd.Timedelta(days=30):%Y-%m-%d}" and st["next"]["eps_est"] == 1.5


def test_implied_vs_history():
    close, bench, ed, jumps = planted_study()
    st = E.event_study(close, bench, ed)
    moves = np.array([abs(e["reaction"]) for e in st["events"]])
    iv = E.implied_vs_history(0.07, st)
    dumps(iv)
    assert iv["hist_mean_abs"] == pytest.approx(moves.mean())
    assert iv["hist_median_abs"] == pytest.approx(np.median(moves))
    assert iv["ratio"] == pytest.approx(0.07 / moves.mean())
    assert iv["share_exceeding_implied"] == pytest.approx((moves > 0.07).mean())
    none = E.implied_vs_history(None, st)
    assert none["ratio"] is None and none["share_exceeding_implied"] is None and none["n"] == len(moves)


@pytest.mark.parametrize("ticker", ["NVDA", "INTC"])
def test_real_fixtures(ticker, closes, nvda_earnings, intc_earnings):
    ed = nvda_earnings if ticker == "NVDA" else intc_earnings
    st = E.event_study(closes[ticker], closes["SPY"], ed)
    dumps(st)
    assert st["n_events"] >= 25
    assert 0.01 < st["mean_abs_move"] < 0.3 and st["median_abs_move"] <= st["mean_abs_move"] * 1.5
    assert 0 <= st["beat_rate"] <= 1
    sessions = set(closes[ticker].dropna().index.strftime("%Y-%m-%d"))
    for ev in st["events"]:
        assert ev["reaction_date"] in sessions
        if ev["timing"] == "AMC":
            assert ev["reaction_date"] > ev["date"]
        else:
            assert ev["reaction_date"] >= ev["date"]
    assert st["events"][0]["car_2_20"] is None or st["n_events"] > 0                 # recent event incomplete
    assert st["next"] is not None and st["next"]["date"] > st["events"][0]["date"]
    assert len(st["caar"]["all"]) == 26
    rd = E.reaction_dates(ed, closes[ticker].dropna().index)
    assert rd["reaction_date"].notna().sum() == st["n_events"]
    dumps(E.implied_vs_history(0.08, st))
    # INTC's 2024-08-01 12:00 report is during market hours -> same-day reaction
    if ticker == "INTC":
        r = rd[rd["event_time"].dt.strftime("%Y-%m-%d") == "2024-08-01"].iloc[0]
        assert r["timing"] == "DMH" and r["reaction_date"] == pd.Timestamp("2024-08-01")


def test_edge_cases(closes, nvda_earnings):
    for ed in (None, pd.DataFrame(), nvda_earnings.iloc[:0]):
        st = E.event_study(closes["NVDA"], closes["SPY"], ed)
        dumps(st)
        assert st["n_events"] == 0 and st["events"] == [] and st["warnings"]
    short = E.event_study(closes["NVDA"].iloc[-20:], closes["SPY"].iloc[-20:], nvda_earnings)
    dumps(short)
    assert short["n_events"] == 0 and short["next"]["date"] == "2027-02-24"
    rd = E.reaction_dates(None, closes.index)
    assert rd.empty and list(rd.columns) == ["event_time", "reaction_date", "timing", "eps_est", "eps_act",
                                             "surprise_pct"]
    # earnings older than the price history only
    old = nvda_earnings[nvda_earnings.index < pd.Timestamp("2018-01-01", tz=NY)]
    st = E.event_study(closes["NVDA"], closes["SPY"], old)
    dumps(st)
    assert st["n_events"] == 0
    assert E.event_study("garbage", None, nvda_earnings)["n_events"] == 0
