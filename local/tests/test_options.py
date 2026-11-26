"""Tests for semiquant.analytics.options (known answers, real NVDA snapshot, edge cases)."""
from __future__ import annotations

import json
import math
import time

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import options as O


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


# ------------------------------------------------------------------ synthetic chains
def make_chain(S, T_years, r, q, vol_fn, strikes, spread=0.02, oi_call=None, oi_put=None):
    """Two-sided BSM chain with IV = vol_fn(K) and a relative spread around the model price."""
    K = np.asarray(strikes, float)
    vols = np.array([vol_fn(k) for k in K])
    c = O.bs_price(S, K, T_years, r, q, vols, "call")
    p = O.bs_price(S, K, T_years, r, q, vols, "put")
    n = K.size
    oi_c = np.full(n, 1000.0) if oi_call is None else np.asarray(oi_call, float)
    oi_p = np.full(n, 1000.0) if oi_put is None else np.asarray(oi_put, float)

    def side(px, oi, tag):
        bid = np.round(px * (1 - spread / 2), 6)
        ask = np.round(px * (1 + spread / 2), 6)
        return pd.DataFrame({"contractSymbol": [f"TEST{tag}{k:08.0f}" for k in K * 1000], "strike": K,
                             "lastPrice": px, "bid": bid, "ask": ask, "volume": np.full(n, 50.0),
                             "openInterest": oi, "impliedVolatility": vols, "inTheMoney": False})
    return side(c, oi_c, "C"), side(p, oi_p, "P")


ASOF = "2026-01-05T10:00:00"


def expiry_after(days: int) -> str:
    return (pd.Timestamp(ASOF).normalize() + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ Black-Scholes known answers
def test_bs_price_textbook_values():
    # Hull, Options Futures and Other Derivatives, Example 15.6: S=42, K=40, r=10%, sigma=20%, T=0.5
    assert O.bs_price(42, 40, 0.5, 0.10, 0.0, 0.20, "call") == pytest.approx(4.7594, abs=1e-4)
    assert O.bs_price(42, 40, 0.5, 0.10, 0.0, 0.20, "put") == pytest.approx(0.8086, abs=1e-4)
    # ATM one-year, r = 5 %: the classic 10.4506 / 5.5735 pair
    assert O.bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call") == pytest.approx(10.4506, abs=1e-4)
    assert O.bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "p") == pytest.approx(5.5735, abs=1e-4)


def test_put_call_parity_vectorised():
    rng = np.random.default_rng(1)
    S = rng.uniform(50, 150, 200)
    K = rng.uniform(40, 160, 200)
    T = rng.uniform(0.01, 2, 200)
    r, q, sig = 0.04, rng.uniform(0, 0.05, 200), rng.uniform(0.1, 1.0, 200)
    c = O.bs_price(S, K, T, r, q, sig, "call")
    p = O.bs_price(S, K, T, r, q, sig, "put")
    assert np.allclose(c - p, S * np.exp(-q * T) - K * np.exp(-r * T), atol=1e-10)
    kinds = np.where(np.arange(200) % 2 == 0, "call", "put")
    mixed = O.bs_price(S, K, T, r, q, sig, kinds)
    assert np.allclose(mixed, np.where(kinds == "call", c, p))


def test_greeks_closed_form_and_finite_differences():
    S, K, T, r, q, sig = 100.0, 105.0, 0.75, 0.03, 0.01, 0.30
    g = O.bs_greeks(S, K, T, r, q, sig, "call")
    d1 = (math.log(S / K) + (r - q + 0.5 * sig ** 2) * T) / (sig * math.sqrt(T))
    N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))  # noqa: E731
    assert g["delta"] == pytest.approx(math.exp(-q * T) * N(d1), abs=1e-12)
    h = 1e-3
    for kind in ("call", "put"):
        g = O.bs_greeks(S, K, T, r, q, sig, kind)
        f = lambda **kw: O.bs_price(kw.get("S", S), K, kw.get("T", T), kw.get("r", r), q, kw.get("sig", sig), kind)  # noqa
        assert g["delta"] == pytest.approx((f(S=S + h) - f(S=S - h)) / (2 * h), rel=1e-6)
        assert g["gamma"] == pytest.approx((f(S=S + h) - 2 * f() + f(S=S - h)) / h ** 2, rel=1e-4)
        assert g["vega"] == pytest.approx((f(sig=sig + h) - f(sig=sig - h)) / (2 * h) / 100.0, rel=1e-6)
        assert g["theta"] == pytest.approx(-(f(T=T + h) - f(T=T - h)) / (2 * h) / 365.0, rel=1e-5)
        assert g["rho"] == pytest.approx((f(r=r + h) - f(r=r - h)) / (2 * h) / 100.0, rel=1e-6)
    gc, gp = O.bs_greeks(S, K, T, r, q, sig, "call"), O.bs_greeks(S, K, T, r, q, sig, "put")
    assert gc["delta"] - gp["delta"] == pytest.approx(math.exp(-q * T))
    assert gc["gamma"] == pytest.approx(gp["gamma"]) and gc["vega"] == pytest.approx(gp["vega"])


def test_bs_edge_cases():
    assert O.bs_price(110, 100, 0.0, 0.05, 0, 0.2, "call") == pytest.approx(10.0)
    assert O.bs_price(90, 100, -1.0, 0.05, 0, 0.2, "put") == pytest.approx(10.0)
    assert O.bs_price(100, 90, 1.0, 0.05, 0, 0.0, "call") == pytest.approx(100 - 90 * math.exp(-0.05))
    assert math.isnan(O.bs_price(-1, 100, 1, 0.05, 0, 0.2, "call"))
    assert math.isnan(O.bs_price(100, 100, 1, 0.05, 0, 0.2, "straddle"))
    g = O.bs_greeks(100, 100, 0.0, 0.05, 0, 0.2, "call")
    assert g["gamma"] == 0.0 and g["vega"] == 0.0
    arr = O.bs_greeks(np.array([90.0, 100.0, 110.0]), 100, 0.5, 0.02, 0.0, 0.25, "call")
    assert arr["delta"].shape == (3,) and np.all(np.diff(arr["delta"]) > 0)


# ------------------------------------------------------------------ implied vol
def test_implied_vol_round_trip_scalar_and_vector():
    rng = np.random.default_rng(7)
    S = 100.0
    K = rng.uniform(60, 150, 300)
    T = rng.uniform(5 / 365, 2.0, 300)
    sig = rng.uniform(0.08, 2.5, 300)
    kinds = np.where(K >= S, "call", "put")  # OTM: well-conditioned
    px = O.bs_price(S, K, T, 0.04, 0.01, sig, kinds)
    iv = O.implied_vol_vec(px, S, K, T, 0.04, 0.01, kinds)
    ok = px > 1e-6
    assert np.allclose(iv[ok], sig[ok], atol=1e-6)
    for i in range(0, 300, 37):
        if ok[i]:
            assert O.implied_vol(px[i], S, K[i], T[i], 0.04, 0.01, kinds[i]) == pytest.approx(sig[i], abs=1e-7)
    # ITM calls / puts too
    px_itm = O.bs_price(S, 80.0, 0.5, 0.04, 0.0, 0.45, "call")
    assert O.implied_vol(px_itm, S, 80.0, 0.5, 0.04, 0.0, "call") == pytest.approx(0.45, abs=1e-7)


def test_implied_vol_no_arbitrage_bounds_give_nan():
    S, K, T, r = 100.0, 100.0, 0.5, 0.05
    intrinsic_fwd = S - K * math.exp(-r * T)
    assert math.isnan(O.implied_vol(intrinsic_fwd - 0.5, S, K, T, r, 0.0, "call"))   # below lower bound
    assert math.isnan(O.implied_vol(S + 1.0, S, K, T, r, 0.0, "call"))               # above S
    assert math.isnan(O.implied_vol(K, S, K, T, r, 0.0, "put"))                      # above K e^{-rT}
    assert math.isnan(O.implied_vol(5.0, S, K, 0.0, r, 0.0, "call"))                 # no time
    assert math.isnan(O.implied_vol(5.0, S, K, T, r, 0.0, "banana"))
    assert math.isnan(O.implied_vol(None, S, K, T, r, 0.0, "call"))
    # above the price at sigma = 5 -> outside the bracket
    p_hi = O.bs_price(S, K, T, r, 0.0, 6.0, "call")
    assert math.isnan(O.implied_vol(p_hi, S, K, T, r, 0.0, "call"))
    v = O.implied_vol_vec([intrinsic_fwd - 0.5, 10.0, np.nan], S, K, T, r, 0.0, "call")
    assert math.isnan(v[0]) and np.isfinite(v[1]) and math.isnan(v[2])


def test_time_to_expiry():
    t = O.time_to_expiry("2026-11-27", "2026-11-26T14:47:39")
    expected = (24 * 3600 + 3600 + 12 * 60 + 21) / (365 * 86400)
    assert t == pytest.approx(expected, rel=1e-12)
    # aware asof converted to New York (19:47:39 UTC = 14:47:39 EST)
    assert O.time_to_expiry("2026-11-27", pd.Timestamp("2026-11-26T19:47:39", tz="UTC")) == pytest.approx(expected)
    # past expiry floors at one hour
    assert O.time_to_expiry("2026-11-20", "2026-11-26") == pytest.approx(1 / 8760)
    assert math.isnan(O.time_to_expiry("not a date", "2026-11-26"))


# ------------------------------------------------------------------ chain analytics: known answers
def test_chain_recovers_flat_vol_forward_and_move():
    S, r, q, vol = 100.0, 0.04, 0.01, 0.30
    exp = expiry_after(30)
    T = O.time_to_expiry(exp, ASOF)
    calls, puts = make_chain(S, T, r, q, lambda k: vol, np.arange(60, 145, 2.5))
    res = O.chain_analytics(calls, puts, S, exp, ASOF, r=r, q=q)
    dumps(res)
    assert res["T"] == pytest.approx(T)
    assert res["forward"] == pytest.approx(S * math.exp((r - q) * T), rel=1e-4)
    assert res["forward_source"] == "parity"
    assert res["atm_iv"] == pytest.approx(vol, abs=2e-3)
    assert all(abs(p["iv"] - vol) < 5e-3 for p in res["smile"])
    assert abs(res["skew"]["rr25"]) < 2e-3 and abs(res["skew"]["bf25"]) < 2e-3
    atm = next(rw for rw in res["rows"] if rw["strike"] == res["atm_strike"])
    assert res["straddle"] == pytest.approx(atm["call_mid"] + atm["put_mid"])
    assert res["implied_move"] == pytest.approx(res["straddle"] / S)
    assert res["expected_range"] == pytest.approx([S - res["straddle"], S + res["straddle"]])
    assert res["one_sigma_move"] == pytest.approx(S * res["atm_iv"] * math.sqrt(T))
    n_pos_bid = int((calls["bid"] > 0).sum() + (puts["bid"] > 0).sum())   # far wings round to a zero bid
    assert res["quality"]["n_valid"] == n_pos_bid and res["quality"]["n_quotes"] == len(calls) + len(puts)
    assert res["quality"]["median_spread_pct"] == pytest.approx(0.02, abs=1e-3)
    # sides of the smile: puts below the forward, calls above
    assert all((p["side"] == "put") == (p["moneyness"] < 1) for p in res["smile"])


def test_chain_skew_signs():
    S, r, q = 100.0, 0.04, 0.0
    exp = expiry_after(45)
    T = O.time_to_expiry(exp, ASOF)
    skewed = lambda k: 0.35 - 0.4 * math.log(k / S)  # noqa: E731  higher vol for low strikes
    calls, puts = make_chain(S, T, r, q, skewed, np.arange(50, 160, 2.5))
    res = O.chain_analytics(calls, puts, S, exp, ASOF, r=r, q=q)
    sk = res["skew"]
    assert sk["rr25"] < -0.02 and sk["put_skew_90"] > 0.02 and sk["call_skew_110"] < -0.02
    assert sk["iv_90"] == pytest.approx(0.35 - 0.4 * math.log(0.9 * res["forward"] / S), abs=0.01)


def test_max_pain_hand_built():
    # strikes 90 / 100 / 110, call OI 10 / 200 / 50, put OI 100 / 20 / 300
    # payout at 90 = 20*10 + 300*20 = 6200, at 100 = 10*10 + 300*10 = 3100, at 110 = 10*20 + 200*10 = 2200
    calls, puts = make_chain(100.0, 0.1, 0.0, 0.0, lambda k: 0.3, [90, 100, 110],
                             oi_call=[10, 200, 50], oi_put=[100, 20, 300])
    res = O.chain_analytics(calls, puts, 100.0, expiry_after(36), ASOF, r=0.0)
    assert res["max_pain"] == 110.0
    assert res["put_call"]["oi_ratio"] == pytest.approx(420 / 260)


def test_gex_sign_conventions_and_formula():
    S = 100.0
    exp = expiry_after(20)
    T = O.time_to_expiry(exp, ASOF)
    strikes = np.arange(80, 121, 5.0)
    zeros = np.zeros(strikes.size)
    c_only = O.chain_analytics(*make_chain(S, T, 0.0, 0.0, lambda k: 0.4, strikes, oi_put=zeros), S, exp, ASOF, r=0.0)
    p_only = O.chain_analytics(*make_chain(S, T, 0.0, 0.0, lambda k: 0.4, strikes, oi_call=zeros), S, exp, ASOF, r=0.0)
    assert c_only["gex"]["total"] > 0 and p_only["gex"]["total"] < 0
    assert all(b["call"] >= 0 for b in c_only["gex"]["by_strike"])
    assert all(b["put"] <= 0 for b in p_only["gex"]["by_strike"])
    row = next(b for b in c_only["gex"]["by_strike"] if b["strike"] == 100.0)
    r100 = next(rw for rw in c_only["rows"] if rw["strike"] == 100.0)
    assert row["call"] == pytest.approx(r100["call_gamma"] * 1000 * 100 * S ** 2 * 0.01, rel=1e-9)
    # balanced book: calls above spot, puts below -> GEX changes sign somewhere -> flip level found
    oi_c = np.where(strikes >= 100, 2000.0, 0.0)
    oi_p = np.where(strikes <= 95, 3000.0, 0.0)
    mix = O.chain_analytics(*make_chain(S, T, 0.0, 0.0, lambda k: 0.4, strikes, oi_call=oi_c, oi_put=oi_p),
                            S, exp, ASOF, r=0.0)
    assert mix["gex"]["flip"] is not None and 70 < mix["gex"]["flip"] < 130


def test_unusual_activity_filter():
    calls, puts = make_chain(100.0, 0.1, 0.0, 0.0, lambda k: 0.3, [95, 100, 105])
    calls.loc[:, "volume"] = [5000, 150, 90]          # 150 < 2 x OI 100; 90 < the 100 floor
    calls.loc[:, "openInterest"] = [1000, 100, 0]
    puts.loc[:, "volume"] = [50, 250, 120]
    puts.loc[:, "openInterest"] = [1000, 100, 0]
    res = O.chain_analytics(calls, puts, 100.0, expiry_after(36), ASOF, r=0.0)
    got = [(u["strike"], u["side"]) for u in res["unusual"]]
    assert got == [(95.0, "call"), (100.0, "put"), (105.0, "put")]      # sorted by volume
    assert res["unusual"][0]["vol_oi"] == pytest.approx(5.0) and res["unusual"][2]["vol_oi"] is None
    assert res["unusual"][0]["contract"].startswith("TESTC")


# ------------------------------------------------------------------ term structure / surface
def test_term_structure_recovers_event_vol():
    S, r = 100.0, 0.0
    e1, e2, e3 = expiry_after(10), expiry_after(31), expiry_after(59)
    T1, T2, T3 = (O.time_to_expiry(e, ASOF) for e in (e1, e2, e3))
    base, sig_e = 0.40, 0.08                      # 8 % one-day event standard deviation
    v2 = math.sqrt(base ** 2 + sig_e ** 2 / T2)
    v3 = math.sqrt(base ** 2 + sig_e ** 2 / T3)
    strikes = np.arange(60, 141, 2.5)
    chains = {e1: make_chain(S, T1, r, 0, lambda k: base, strikes), e2: make_chain(S, T2, r, 0, lambda k: v2, strikes),
              e3: make_chain(S, T3, r, 0, lambda k: v3, strikes)}
    earn = expiry_after(20)
    ts = O.term_structure(chains, S, ASOF, r=r, earnings_date=earn)
    dumps(ts)
    assert [rw["expiry"] for rw in ts["rows"]] == [e1, e2, e3]
    ev = ts["earnings"]
    assert ev["pre_expiry"] == e1 and ev["post_expiry"] == e2 and ev["method"] == "kink"
    assert ev["event_vol"] == pytest.approx(sig_e, rel=0.03)
    assert ev["implied_event_move"] == pytest.approx(sig_e * math.sqrt(2 / math.pi), rel=0.03)
    # forward vol between the two post-event expiries is the base vol
    fv = ts["forward_vols"][1]
    assert fv["from"] == e2 and fv["fwd_vol"] == pytest.approx(base, rel=0.02)
    # no expiry before the event: base vol backed out of the two post-event expiries
    post_only = {e2: chains[e2], e3: chains[e3]}
    ev2 = O.term_structure(post_only, S, ASOF, r=r, earnings_date=earn)["earnings"]
    assert ev2["method"] == "two_post" and ev2["pre_expiry"] is None
    assert ev2["event_vol"] == pytest.approx(sig_e, rel=0.03)
    # BMO time on an expiry day counts as before that expiry's close
    ev3 = O.term_structure(chains, S, ASOF, r=r, earnings_date=f"{e2}T08:00:00")["earnings"]
    assert ev3["pre_expiry"] == e1 and ev3["post_expiry"] == e2
    ev4 = O.term_structure(chains, S, ASOF, r=r, earnings_date=e2)["earnings"]   # date only = after the close
    assert ev4["pre_expiry"] == e2 and ev4["post_expiry"] == e3


def test_iv_surface_flat():
    S = 100.0
    exps = [expiry_after(d) for d in (14, 45, 120)]
    chains = {e: dict(zip(("calls", "puts"), make_chain(S, O.time_to_expiry(e, ASOF), 0.03, 0.0, lambda k: 0.25,
                                                        np.arange(75, 126, 2.5)))) for e in exps}
    surf = O.iv_surface(chains, S, ASOF, r=0.03)
    dumps(surf)
    assert len(surf["moneyness"]) == 25 and surf["moneyness"][0] == 0.7 and surf["moneyness"][-1] == 1.3
    assert surf["expiries"] == exps and len(surf["iv"]) == 3 and len(surf["dte"]) == 3
    for row in surf["iv"]:
        assert len(row) == 25
        assert row[0] is None and row[-1] is None            # strikes only span 0.75-1.25
        vals = [v for v in row if v is not None]
        assert vals and all(abs(v - 0.25) < 3e-3 for v in vals)


# ------------------------------------------------------------------ real NVDA snapshot
def test_real_chains(nvda_options):
    S, asof = nvda_options["spot"], nvda_options["asof"]
    for exp, ch in nvda_options["chains"].items():
        t0 = time.perf_counter()
        res = O.chain_analytics(ch["calls"], ch["puts"], S, exp, asof, r=0.04, q=0.0067)
        assert time.perf_counter() - t0 < 0.3
        dumps(res)
        assert res["expiry"] == exp and res["T"] > 0
        assert abs(res["forward"] / S - 1) < 0.03
        assert 0.1 < res["atm_iv"] < 2.0
        assert 0 < res["implied_move"] < 0.6
        assert res["atm_strike"] in {rw["strike"] for rw in res["rows"]}
        assert len(res["rows"]) == len(res["oi_by_strike"]) == len(res["gex"]["by_strike"])
        assert 0 <= res["quality"]["stale_share"] < 1 and res["quality"]["n_valid"] > 0
        assert len(res["smile"]) > 10 and all(p["iv"] > 0 for p in res["smile"])
        assert res["max_pain"] is not None and res["put_call"]["oi_ratio"] > 0
        assert len(res["unusual"]) <= 15
        assert all(u["volume"] >= 100 and u["volume"] >= 2 * (u["oi"] or 0) for u in res["unusual"])
        for rw in res["rows"]:
            if rw["call_delta"] is not None:
                assert -1e-9 <= rw["call_delta"] <= 1.001
            if rw["put_delta"] is not None:
                assert -1.001 <= rw["put_delta"] <= 1e-9
    # crossed quote (150C: bid 2.88 > ask 2.74) is flagged stale and priced off the last trade
    ch = nvda_options["chains"]["2026-11-27"]
    res = O.chain_analytics(ch["calls"], ch["puts"], S, "2026-11-27", asof)
    r150 = next(rw for rw in res["rows"] if rw["strike"] == 150.0)
    assert r150["call_stale"] is True and r150["call_mid"] == pytest.approx(2.95)


def test_real_term_structure_and_surface(nvda_options):
    S, asof = nvda_options["spot"], nvda_options["asof"]
    chains = {e: (c["calls"], c["puts"]) for e, c in nvda_options["chains"].items()}
    ts = O.term_structure(chains, S, asof, earnings_date="2027-02-24")
    dumps(ts)
    dtes = [rw["dte"] for rw in ts["rows"]]
    assert dtes == sorted(dtes) and len(dtes) == len(chains)
    assert all(0.1 < rw["atm_iv"] < 2.0 for rw in ts["rows"])
    assert ts["earnings"]["pre_expiry"] == "2027-01-15" and ts["earnings"]["post_expiry"] == "2027-05-21"
    surf = O.iv_surface(nvda_options["chains"], S, asof)
    dumps(surf)
    assert len(surf["iv"]) == len(surf["dte"]) == len(surf["expiries"]) > 0
    # 20 expiries within 2 s
    big = {}
    src = list(nvda_options["chains"].values())
    for i, e in enumerate(nvda_options["expiries"][:20]):
        big[e] = (src[i % len(src)]["calls"], src[i % len(src)]["puts"])
    t0 = time.perf_counter()
    ts20 = O.term_structure(big, S, asof)
    assert time.perf_counter() - t0 < 2.0
    assert len(ts20["rows"]) == 20


# ------------------------------------------------------------------ edge cases
def test_empty_and_degenerate_chains():
    empty = pd.DataFrame(columns=["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"])
    for calls, puts in ((empty, empty), (None, None), ([], [])):
        res = O.chain_analytics(calls, puts, 100.0, expiry_after(30), ASOF)
        dumps(res)
        assert res["rows"] == [] and res["atm_iv"] is None and res["max_pain"] is None
        assert res["warnings"]
    assert O.term_structure({}, 100.0, ASOF) == {"rows": [], "forward_vols": [], "earnings": None, "warnings": []}
    assert O.iv_surface({"2026-02-20": (empty, empty)}, 100.0, ASOF)["iv"] == []


def test_all_zero_bids_and_missing_columns():
    calls, puts = make_chain(100.0, 30 / 365, 0.04, 0.0, lambda k: 0.3, np.arange(80, 121, 5.0))
    calls["bid"] = 0.0
    puts["bid"] = 0.0
    res = O.chain_analytics(calls, puts, 100.0, expiry_after(30), ASOF)
    dumps(res)
    assert res["quality"]["n_valid"] == 0 and res["quality"]["stale_share"] == 1.0
    assert res["smile"] == [] and res["forward_source"] == "carry"
    assert all(rw["call_stale"] for rw in res["rows"])
    assert res["straddle"] is not None          # last prices still give a (stale) straddle
    # only strikes and last prices
    bare = calls[["strike", "lastPrice"]]
    res2 = O.chain_analytics(bare, None, 100.0, expiry_after(30), ASOF)
    dumps(res2)
    assert len(res2["rows"]) == len(bare) and res2["put_call"]["put_oi"] == 0
    # expired chain and missing spot do not raise
    dumps(O.chain_analytics(calls, puts, None, "2025-01-01", ASOF))
