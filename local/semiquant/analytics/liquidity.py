"""Liquidity and execution cost from daily bars (what an execution desk checks before trading).

* Average daily volume in shares and dollars (20 and 60 days), turnover.
* Amihud (2002) illiquidity: mean |daily return| per $1M traded (price move a $1M order day causes).
* Bid-ask spread estimates without quotes: Corwin & Schultz (2012) high-low estimator (two-day
  ranges, overnight-adjusted) and Roll (1984) from the serial covariance of price changes.
* Market impact by the square-root law (Almgren et al. 2005; Toth et al. 2011): the expected cost
  of a parent order of Q shares is about half the spread plus Y * daily vol * sqrt(Q / ADV), Y ~ 1.
  Empirically this depends on the order's size relative to volume, not on how slowly it is worked,
  so the table shows one expected cost per order size, the days needed to stay under 10 % / 20 % of
  daily volume (the usual desk limit) and the extra price risk of that longer schedule (1 sd of the
  drift over a linear schedule, daily vol * sqrt(days / 3), Almgren & Chriss 2000).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ._util import clean, jsonable

__all__ = ["liquidity_profile", "corwin_schultz", "roll_spread", "typical_spread"]

IMPACT_Y = 1.0  # square-root-law coefficient (literature: ~0.5-1.5)
# Typical quoted spread of US equities by average daily dollar volume (fraction of price).
SPREAD_BUCKETS = ((1e9, 0.00015), (2.5e8, 0.0003), (5e7, 0.0006), (1e7, 0.0015), (2e6, 0.0035), (0, 0.008))


def typical_spread(adv_usd: float, price: float | None = None, usd_listing: bool = True) -> float:
    """Typical bid-ask spread for a stock trading ``adv_usd`` a day (bucket table above), never below
    one cent on a US-dollar listing. Daily-bar estimators (Corwin-Schultz, Roll, Abdi-Ranaldo) read
    volatility as spread for liquid stocks, so they are not used for large caps."""
    adv = adv_usd if isinstance(adv_usd, (int, float)) and math.isfinite(adv_usd) else 0.0
    s = next(v for lo, v in SPREAD_BUCKETS if adv >= lo)
    if usd_listing and price and price > 0:
        s = max(s, 0.01 / price)
    return s
ORDER_SIZES = (1e5, 1e6, 1e7, 5e7, 2.5e8)


def _frame(df) -> pd.DataFrame:
    d = df.rename(columns=str.lower)
    d = d[[c for c in ("open", "high", "low", "close", "volume") if c in d.columns]].apply(pd.to_numeric, errors="coerce")
    return d.replace([np.inf, -np.inf], np.nan).dropna(subset=["close"])


def corwin_schultz(df, window: int = 60) -> float | None:
    """Mean Corwin-Schultz spread estimate (fraction of price) over the last ``window`` days.

    beta = ln(H_t/L_t)^2 + ln(H_t+1/L_t+1)^2, gamma = ln(max H / min L over the two days)^2,
    alpha = (sqrt(2 beta) - sqrt(beta)) / (3 - 2 sqrt 2) - sqrt(gamma / (3 - 2 sqrt 2)),
    S = 2 (e^alpha - 1) / (1 + e^alpha); negative two-day estimates are set to 0. Highs and lows of
    day t+1 are shifted by the overnight gap when the open is outside day t's range (the paper's
    adjustment), so a gap is not mistaken for a spread.
    """
    d = _frame(df)
    if not {"high", "low"} <= set(d.columns):
        return None
    d = d.dropna(subset=["high", "low"]).tail(window + 1)
    if len(d) < 10:
        return None
    h, lo, c = d["high"].to_numpy(float), d["low"].to_numpy(float), d["close"].to_numpy(float)
    o = d["open"].to_numpy(float) if "open" in d else c
    k = 3 - 2 * math.sqrt(2)
    est = []
    for t in range(len(d) - 1):
        h1, l1 = h[t + 1], lo[t + 1]
        if o[t + 1] > c[t] and l1 > c[t]:  # gap up: move day t+1 down
            g = l1 - c[t]
            h1, l1 = h1 - g, l1 - g
        elif o[t + 1] < c[t] and h1 < c[t]:  # gap down
            g = c[t] - h1
            h1, l1 = h1 + g, l1 + g
        if min(h[t], lo[t], h1, l1) <= 0 or h[t] < lo[t] or h1 < l1:
            continue
        beta = math.log(h[t] / lo[t]) ** 2 + math.log(h1 / l1) ** 2
        gamma = math.log(max(h[t], h1) / min(lo[t], l1)) ** 2
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        est.append(max(s, 0.0))
    return float(np.mean(est)) if est else None


def roll_spread(df, window: int = 60) -> float | None:
    """Roll (1984) spread 2 sqrt(-cov(dp_t, dp_t-1)) / price (None when the covariance is >= 0)."""
    c = _frame(df)["close"].tail(window + 2)
    if len(c) < 20:
        return None
    dp = c.diff().dropna().to_numpy(float)
    cov = np.cov(dp[1:], dp[:-1], ddof=1)[0, 1]
    if not np.isfinite(cov) or cov >= -1e-12 * max(float(np.var(dp)), 1e-300):  # >= 0 up to rounding
        return None
    return float(2 * math.sqrt(-cov) / c.iloc[-1])


def liquidity_profile(df, shares_outstanding: float | None = None, fx_to_usd: float = 1.0,
                      order_sizes=ORDER_SIZES, bid: float | None = None, ask: float | None = None,
                      quote_live: bool = False) -> dict:
    """Liquidity snapshot and square-root-law execution costs for ``order_sizes`` (in USD).

    ``df``: daily OHLCV (lowercase columns). ``fx_to_usd`` converts the listing currency to USD so
    order sizes and dollar volumes are in USD. Spread used for costs: the quoted bid/ask spread when
    the market is open (``quote_live``) and the quote is two-sided and under 3 % (outside the session
    Yahoo's bid/ask are stale), else ``typical_spread`` for the stock's dollar volume. The
    Corwin-Schultz and Roll estimates are reported for reference (meaningful for illiquid stocks).
    """
    d = _frame(df)
    out = {"available": False}
    if len(d) < 30 or "volume" not in d or d["volume"].tail(60).fillna(0).sum() <= 0:
        return {**out, "message": "No volume data for this symbol (indices and FX have no traded volume)."}
    px = float(d["close"].iloc[-1])
    vol = d["volume"].fillna(0)
    dv = d["close"] * vol * fx_to_usd
    r = d["close"].pct_change()
    adv20, adv60 = float(vol.tail(20).mean()), float(vol.tail(60).mean())
    dv20, dv60 = float(dv.tail(20).mean()), float(dv.tail(60).mean())
    sigma = float(r.tail(60).std(ddof=1))
    amihud = (r.abs() / (dv / 1e6)).replace([np.inf, -np.inf], np.nan).tail(60)
    cs, rl = corwin_schultz(d, 60), roll_spread(d, 60)
    quoted = None
    if quote_live and bid and ask and bid > 0 and ask >= bid:
        quoted = (ask - bid) / (0.5 * (ask + bid))
        if not 0 <= quoted < 0.03:
            quoted = None
    typical = typical_spread(dv20, px, abs(fx_to_usd - 1.0) < 1e-9)
    spread = quoted if quoted is not None else typical
    source = "quoted" if quoted is not None else "typical"
    rows = []
    for usd in order_sizes:
        q = usd / (px * fx_to_usd) if px > 0 else float("nan")
        part = q / adv20 if adv20 > 0 else float("nan")
        cost = 0.5 * spread + IMPACT_Y * sigma * math.sqrt(part) if np.isfinite(part) else None
        row = {"usd": usd, "shares": q, "pct_adv": part, "cost": cost, "cost_usd": cost * usd if cost is not None else None}
        for p in (0.10, 0.20):
            days = max(part / p, 1.0) if np.isfinite(part) else None
            key = f"{int(p * 100)}"
            row[f"days_{key}"] = days
            row[f"risk_{key}"] = sigma * math.sqrt(days / 3.0) if days else None  # 1 sd drift over the schedule
        rows.append(row)
    out.update(available=True, price=px, adv_shares_20d=adv20, adv_shares_60d=adv60, adv_usd_20d=dv20, adv_usd_60d=dv60,
               turnover_daily=(adv60 / shares_outstanding) if shares_outstanding else None,
               amihud=clean(amihud.mean()), daily_vol=sigma, spread_quoted=quoted, spread_cs=cs, spread_roll=rl, spread_used=spread,
               spread_source=source,
               impact_y=IMPACT_Y, orders=rows,
               volume_trend=(adv20 / adv60 - 1.0) if adv60 > 0 else None)
    return jsonable(out)
