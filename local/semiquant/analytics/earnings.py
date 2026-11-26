"""Earnings analytics: reaction-day mapping, a market-model event study and the options-implied
move versus the historical earnings reaction.

Method: standard short-horizon event study (Brown & Warner 1985; MacKinlay 1997, "Event Studies in
Economics and Finance"). Abnormal return AR_t = r_t - (alpha + beta * m_t) with alpha/beta estimated by
OLS of daily simple stock returns on benchmark returns over an estimation window that ends ``gap``
sessions before the reaction day and excludes every event window. CAR = sum of ARs; CAAR = cumulative
average AR across events. Fractions everywhere (0.05 = 5 %).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ._util import as_close, clean, jsonable

NY = "America/New_York"
_EST = ("EPS Estimate", "epsEstimate", "eps_estimate", "eps_est", "Estimate")
_ACT = ("Reported EPS", "epsActual", "eps_actual", "eps_act", "Actual")
_SUR = ("Surprise(%)", "surprisePercent", "Surprise %")
_COLS = ["event_time", "reaction_date", "timing", "eps_est", "eps_act", "surprise_pct"]
_MAX_GAP_DAYS = 7  # a reaction session more than a week after the event means the index does not cover it

__all__ = ["reaction_dates", "event_study", "implied_vs_history"]


# =============================================================================== event table
def _col(df: pd.DataFrame, names) -> np.ndarray:
    for n in names:
        if n in df.columns:
            return pd.to_numeric(df[n], errors="coerce").to_numpy(float)
    return np.full(len(df), np.nan)


def _ny_index(idx) -> pd.DatetimeIndex:
    if not isinstance(idx, pd.DatetimeIndex):
        try:
            idx = pd.DatetimeIndex(pd.to_datetime(idx, errors="coerce"))
        except (ValueError, TypeError):
            idx = pd.DatetimeIndex(pd.to_datetime(idx, errors="coerce", utc=True))
    return idx.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward") if idx.tz is None else idx.tz_convert(NY)


def _events(earnings) -> pd.DataFrame:
    """Earnings frame (Ticker.get_earnings_dates() shape) -> event_time (New York, tz-aware), eps_est,
    eps_act, surprise_pct (fraction), sorted oldest first, one row per event time."""
    empty = pd.DataFrame({"event_time": pd.DatetimeIndex([], tz=NY), "eps_est": [], "eps_act": [],
                          "surprise_pct": []})
    if earnings is None or not isinstance(earnings, pd.DataFrame) or len(earnings) == 0:
        return empty
    df = earnings
    if not isinstance(df.index, pd.DatetimeIndex) and "Earnings Date" in df.columns:
        df = df.set_index("Earnings Date")
    idx = _ny_index(df.index)
    est, act = _col(df, _EST), _col(df, _ACT)
    sur = _col(df, _SUR) / 100.0  # Yahoo reports percent
    with np.errstate(all="ignore"):
        calc = np.where(np.isfinite(est) & np.isfinite(act) & (est != 0), (act - est) / np.abs(est), np.nan)
    sur = np.where(np.isfinite(sur), sur, calc)
    out = pd.DataFrame({"event_time": idx, "eps_est": est, "eps_act": act, "surprise_pct": sur})
    out = out[out["event_time"].notna()]
    out = out.assign(_has=out["eps_act"].notna()).sort_values(["event_time", "_has"], ascending=[True, False])
    out = out.drop_duplicates("event_time", keep="first").drop(columns="_has")
    return out.reset_index(drop=True)


def _sessions(trading_index) -> pd.DatetimeIndex:
    try:
        tix = pd.DatetimeIndex(trading_index)
    except (ValueError, TypeError):
        return pd.DatetimeIndex([])
    if tix.tz is not None:
        tix = tix.tz_convert(NY).tz_localize(None)
    return tix.normalize().dropna().unique().sort_values()


def reaction_dates(earnings: pd.DataFrame, trading_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Map each past earnings event (Reported EPS present) to the first session whose close reflects it.

    Timing from the New York announcement time: >= 16:00 -> "AMC" (after market close; reaction = next
    trading day), < 09:30 -> "BMO" (before market open; same day, or the next session if the date is not
    a trading day), otherwise "DMH" (during market hours; same day / next session). A naive index is
    taken as New York time. Events whose reaction session would be more than 7 calendar days after the
    announcement (outside the covered history) get NaT.

    Returns a DataFrame (RangeIndex, oldest first) with columns: event_time (tz-aware New York
    Timestamp), reaction_date (naive Timestamp, NaT when beyond ``trading_index``), timing, eps_est,
    eps_act, surprise_pct (Yahoo's Surprise(%) as a fraction; computed as (act - est)/|est| if missing).
    """
    ev = _events(earnings)
    ev = ev[ev["eps_act"].notna()].reset_index(drop=True)
    if ev.empty:
        return pd.DataFrame({c: [] for c in _COLS}).astype({"reaction_date": "datetime64[ns]"})
    tix = _sessions(trading_index)
    local = pd.DatetimeIndex(ev["event_time"])
    day = local.tz_localize(None).normalize()
    minutes = local.hour * 60 + local.minute
    timing = np.where(minutes >= 16 * 60, "AMC", np.where(minutes < 9 * 60 + 30, "BMO", "DMH"))
    pos = np.where(timing == "AMC", tix.searchsorted(day, side="right"), tix.searchsorted(day, side="left"))
    # the reaction session must follow the event within a week (else the index does not cover it)
    react = pd.DatetimeIndex([tix[p] if p < len(tix) and (tix[p] - d).days <= _MAX_GAP_DAYS else pd.NaT
                              for p, d in zip(pos, day)])
    return pd.DataFrame({"event_time": local, "reaction_date": react, "timing": timing,
                         "eps_est": ev["eps_est"].to_numpy(), "eps_act": ev["eps_act"].to_numpy(),
                         "surprise_pct": ev["surprise_pct"].to_numpy()})


# =============================================================================== event study
def _mean_t(x: list[float]) -> dict:
    a = np.asarray([v for v in x if v is not None and np.isfinite(v)], dtype=float)
    if a.size == 0:
        return {"mean": None, "t": None, "n": 0}
    m = float(a.mean())
    sd = float(a.std(ddof=1)) if a.size > 1 else 0.0
    return {"mean": m, "t": (m / (sd / math.sqrt(a.size)) if sd > 0 else None), "n": int(a.size)}


def _classify(est: float, act: float, sur: float) -> str | None:
    if np.isfinite(est) and np.isfinite(act):
        return "beat" if act > est else ("miss" if act < est else "inline")
    if np.isfinite(sur):
        return "beat" if sur > 0 else ("miss" if sur < 0 else "inline")
    return None


def _empty_study(pre: int, post: int, warnings: list[str]) -> dict:
    days = list(range(-pre, post + 1))
    nones = [None] * len(days)
    return jsonable({"n_events": 0, "mean_abs_move": None, "median_abs_move": None, "std_move": None,
                     "beat_rate": None, "avg_move_beat": None, "avg_move_miss": None,
                     "drift_beat": {"mean": None, "t": None, "n": 0}, "drift_miss": {"mean": None, "t": None, "n": 0},
                     "caar": {"days": days, "all": nones, "beat": nones, "miss": nones, "n_all": 0, "n_beat": 0,
                              "n_miss": 0},
                     "events": [], "next": None, "warnings": warnings})


def _next_event(earnings, last_date) -> dict | None:
    ev = _events(earnings)
    fut = ev[ev["eps_act"].isna()]
    if last_date is not None:
        cut = pd.Timestamp(last_date).normalize()
        cut = cut.tz_localize(NY) if cut.tzinfo is None else cut.tz_convert(NY)
        fut = fut[fut["event_time"] >= cut]
    if fut.empty:
        return None
    row = fut.iloc[0]
    t = pd.Timestamp(row["event_time"])
    mins = t.hour * 60 + t.minute
    timing = "AMC" if mins >= 960 else ("BMO" if mins < 570 else "DMH")
    return {"date": t.strftime("%Y-%m-%d"), "event_time": t.strftime("%Y-%m-%dT%H:%M:%S"), "timing": timing,
            "eps_est": clean(row["eps_est"])}


def event_study(close: pd.Series, bench: pd.Series, earnings: pd.DataFrame, pre: int = 5, post: int = 20,
                est_window: int = 250, gap: int = 10) -> dict:
    """Market-model earnings event study.

    For each past event with reaction day t0 (``reaction_dates``): alpha and beta are estimated by OLS
    of daily stock returns on benchmark returns over sessions [t0 - gap - est_window, t0 - gap),
    excluding the [-pre, +post] windows of all events; with fewer than min(60, est_window/2) clean
    observations the market-adjusted model (alpha 0, beta 1) is used instead (warning).
    AR_t = r_t - alpha - beta * m_t.

    Returns {"n_events", "mean_abs_move", "median_abs_move", "std_move" (of the raw reaction-day
    return), "beat_rate" (share of events with reported > estimated EPS, among events with both),
    "avg_move_beat", "avg_move_miss" (mean raw reaction), "drift_beat": {"mean", "t", "n"},
    "drift_miss": {...} (post-earnings drift = CAR over days +2..+20; t = mean / standard error),
    "caar": {"days": [-pre..post], "all", "beat", "miss" (cumulative average AR, events with a complete
    window only), "n_all", "n_beat", "n_miss"},
    "events": [{"date", "event_time", "reaction_date", "timing", "eps_est", "eps_act", "surprise_pct",
    "result" ("beat"|"miss"|"inline"|None), "reaction" (raw close-to-close return on the reaction day),
    "abnormal" (AR on the reaction day), "car_0_1", "car_2_20" (None until 20 sessions have passed),
    "model" ("market"|"market-adjusted"), "beta"}] newest first,
    "next": {"date", "event_time", "timing", "eps_est"} or None, "warnings": [...]}.
    """
    warns: list[str] = []
    pre, post, est_window, gap = int(max(pre, 0)), int(max(post, 0)), int(max(est_window, 10)), int(max(gap, 0))
    try:
        c, b = as_close(close), as_close(bench)
    except (KeyError, TypeError, ValueError, AttributeError):
        return _empty_study(pre, post, ["invalid close/bench input"])
    if isinstance(c.index, pd.DatetimeIndex) and c.index.tz is not None:
        c = c.tz_convert(NY).tz_localize(None)
    if isinstance(b.index, pd.DatetimeIndex) and b.index.tz is not None:
        b = b.tz_convert(NY).tz_localize(None)
    px = pd.concat({"r": c, "m": b}, axis=1, join="inner").dropna()
    px = px[(px > 0).all(axis=1)]
    rets = px.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    nxt = _next_event(earnings, c.index[-1] if len(c) else None)
    if len(rets) < 30:
        out = _empty_study(pre, post, ["fewer than 30 overlapping return observations"])
        out["next"] = jsonable(nxt)
        return out
    dates = rets.index
    R, M = rets["r"].to_numpy(), rets["m"].to_numpy()
    N = R.size
    rd = reaction_dates(earnings, dates)
    if rd.empty:
        out = _empty_study(pre, post, ["no past earnings events"])
        out["next"] = jsonable(nxt)
        return out
    t0s = dates.get_indexer(pd.DatetimeIndex(rd["reaction_date"]))
    keep = t0s >= 1
    if (~keep).any():
        warns.append(f"{int((~keep).sum())} events fall outside the price history and were skipped")
    rd, t0s = rd[keep].reset_index(drop=True), t0s[keep]
    if rd.empty:
        out = _empty_study(pre, post, warns + ["no events inside the price history"])
        out["next"] = jsonable(nxt)
        return out

    in_win = np.zeros(N, dtype=bool)
    for t0 in t0s:
        in_win[max(0, t0 - pre): min(N, t0 + post + 1)] = True
    min_obs = max(20, min(60, est_window // 2))
    span = pre + post + 1
    events, paths, n_adj = [], [], 0
    for i, t0 in enumerate(t0s):
        est = np.arange(max(0, t0 - gap - est_window), max(0, t0 - gap))
        est = est[~in_win[est]]
        if est.size >= min_obs:
            x, y = M[est], R[est]
            vx = x.var()
            beta = float(((x - x.mean()) * (y - y.mean())).mean() / vx) if vx > 0 else 1.0
            alpha = float(y.mean() - beta * x.mean())
            model = "market"
        else:
            alpha, beta, model = 0.0, 1.0, "market-adjusted"
            n_adj += 1

        def ar(t, alpha=alpha, beta=beta):
            return R[t] - alpha - beta * M[t]

        path = np.full(span, np.nan)
        lo, hi = max(0, t0 - pre), min(N, t0 + post + 1)
        path[lo - (t0 - pre): hi - (t0 - pre)] = R[lo:hi] - alpha - beta * M[lo:hi]
        paths.append(path)
        row = rd.iloc[i]
        res = _classify(row["eps_est"], row["eps_act"], row["surprise_pct"])
        et = pd.Timestamp(row["event_time"])
        events.append({
            "date": et.strftime("%Y-%m-%d"), "event_time": et.strftime("%Y-%m-%dT%H:%M:%S"),
            "reaction_date": dates[t0].strftime("%Y-%m-%d"), "timing": row["timing"],
            "eps_est": clean(row["eps_est"]), "eps_act": clean(row["eps_act"]),
            "surprise_pct": clean(row["surprise_pct"]), "result": res, "reaction": float(R[t0]),
            "abnormal": float(ar(t0)), "car_0_1": float(ar(t0) + ar(t0 + 1)) if t0 + 1 < N else None,
            "car_2_20": float(sum(ar(t) for t in range(t0 + 2, t0 + 21))) if t0 + 20 < N else None,
            "model": model, "beta": beta})
    if n_adj:
        warns.append(f"{n_adj} events lack {min_obs} clean estimation days; market-adjusted model used")

    moves = np.array([e["reaction"] for e in events])
    res = np.array([e["result"] for e in events], dtype=object)
    beat, miss = res == "beat", res == "miss"
    classified = np.isin(res, ["beat", "miss", "inline"])
    P = np.vstack(paths)
    complete = np.isfinite(P).all(axis=1)

    def caar(mask):
        m = mask & complete
        return (np.cumsum(P[m].mean(axis=0)).tolist() if m.any() else [None] * span), int(m.sum())

    c_all, n_all = caar(np.ones(len(events), bool))
    c_beat, n_beat = caar(beat)
    c_miss, n_miss = caar(miss)
    out = {
        "n_events": len(events),
        "mean_abs_move": float(np.mean(np.abs(moves))),
        "median_abs_move": float(np.median(np.abs(moves))),
        "std_move": float(np.std(moves, ddof=1)) if moves.size > 1 else None,
        "beat_rate": float(beat.sum() / classified.sum()) if classified.any() else None,
        "avg_move_beat": float(moves[beat].mean()) if beat.any() else None,
        "avg_move_miss": float(moves[miss].mean()) if miss.any() else None,
        "drift_beat": _mean_t([e["car_2_20"] for e, k in zip(events, beat) if k]),
        "drift_miss": _mean_t([e["car_2_20"] for e, k in zip(events, miss) if k]),
        "caar": {"days": list(range(-pre, post + 1)), "all": c_all, "beat": c_beat, "miss": c_miss,
                 "n_all": n_all, "n_beat": n_beat, "n_miss": n_miss},
        "events": events[::-1],
        "next": nxt,
        "warnings": warns,
    }
    return jsonable(out)


def implied_vs_history(implied_move: float | None, study: dict) -> dict:
    """Options-implied earnings move versus the historical reaction-day moves of ``event_study``.

    Returns {"implied", "hist_mean_abs", "hist_median_abs", "ratio" (implied / historical mean absolute
    move; > 1 = options price a bigger move than usual), "share_exceeding_implied" (share of past
    reactions whose absolute move exceeded the implied move), "n"}.
    """
    imp = clean(implied_move)
    ev = (study or {}).get("events") or []
    moves = np.array([abs(e["reaction"]) for e in ev if isinstance(e, dict) and clean(e.get("reaction")) is not None])
    mean_abs = float(moves.mean()) if moves.size else None
    med_abs = float(np.median(moves)) if moves.size else None
    return jsonable({
        "implied": imp, "hist_mean_abs": mean_abs, "hist_median_abs": med_abs,
        "ratio": (imp / mean_abs) if imp is not None and mean_abs else None,
        "share_exceeding_implied": float((moves > imp).mean()) if imp is not None and moves.size else None,
        "n": int(moves.size)})
