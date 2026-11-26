"""Helpers shared by the service modules: chart ranges, time encoding, memoised
heavy computations, universe price matrices and FX conversion."""
from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..analytics._util import clean, jsonable
from ..data import cache, yahoo
from ..universe import ALL_META, get_universe, universe_tickers

# Chart ranges -> how to fetch them. Daily ranges are sliced from the cached 10-year
# daily series (indicators are computed on the full series first, so a 200-day average
# is valid from the first visible bar).
RANGES: dict[str, dict] = {
    "1D": {"period": "1d", "interval": "1m", "prepost": True},
    "5D": {"period": "5d", "interval": "5m", "prepost": True},
    "1M": {"period": "1mo", "interval": "30m", "prepost": False},
    "3M": {"days": 92}, "6M": {"days": 183}, "YTD": {"ytd": True}, "1Y": {"days": 366},
    "2Y": {"days": 731}, "5Y": {"days": 1827}, "10Y": {"days": 3653},
    "MAX": {"period": "max", "interval": "1wk"},
}


def memo(key: str, ttl: float, fn: Callable[[], Any]) -> Any:
    """Cache a computed (JSON-ready) result for ``ttl`` seconds."""
    return cache.cached(f"svc:{key}", ttl, fn)


def epoch_local(idx: pd.DatetimeIndex) -> list[int]:
    """Naive exchange-local timestamps -> epoch seconds as if UTC (charts then show local time)."""
    i = pd.DatetimeIndex(idx)
    if i.tz is not None:
        i = i.tz_localize(None)
    return [int(x) for x in ((i - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))]


def time_axis(idx: pd.DatetimeIndex, intraday: bool) -> list:
    return epoch_local(idx) if intraday else [d.strftime("%Y-%m-%d") for d in pd.DatetimeIndex(idx)]


def slice_range(df: pd.DataFrame, rng: str) -> pd.DataFrame:
    spec = RANGES.get(rng, {})
    if df is None or df.empty:
        return df
    last = df.index[-1]
    if spec.get("ytd"):
        start = pd.Timestamp(year=last.year, month=1, day=1)
    elif spec.get("days"):
        start = last - pd.Timedelta(days=spec["days"])
    else:
        return df
    return df[df.index >= start]


def returns(close: pd.Series) -> pd.Series:
    return close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def universe_closes(period: str = "2y", universe: str = "semis") -> pd.DataFrame:
    """Daily closes for a universe plus its benchmarks (live-patched)."""
    u = get_universe(universe)
    extra = list(dict.fromkeys(["SPY", u["bench"], u["sector_bench"], u["regime"]]))

    def load():
        return yahoo.closes(universe_tickers(universe) + extra, period=period)
    return cache.cached(f"svc:ucloses:{period}:{universe}", 60, load)


def bench_closes(period: str = "10y", symbols: tuple[str, ...] = ("SPY", "SOXX", "QQQ")) -> dict[str, pd.Series]:
    h = yahoo.daily_many(list(symbols), period)
    return {s: d["close"] for s, d in h.items()}


def meta(sym: str) -> dict:
    return ALL_META.get(sym, {"ticker": sym, "name": None, "sector": None, "tier": None, "universe": None})


# ─── FX ──────────────────────────────────────────────────────────────────────

_SUBUNIT = {"GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0), "ILA": ("ILS", 100.0), "ZAc": ("ZAR", 100.0)}


def fx_to_usd(currencies: list[str | None]) -> dict[str, float]:
    """Multiplier converting an amount in each currency into USD."""
    out: dict[str, float] = {"USD": 1.0, None: 1.0}  # type: ignore[dict-item]
    need = {}
    for c in set(currencies):
        if not c or c == "USD":
            continue
        base, div = _SUBUNIT.get(c, (c, 1.0))
        need[c] = (base, div)
    if need:
        qs = yahoo.quotes([f"{b}=X" for b, _ in need.values()])
        for c, (b, div) in need.items():
            px = clean((qs.get(f"{b}=X") or {}).get("price"))  # units of b per 1 USD
            out[c] = 1.0 / (px * div) if px else float("nan")
    return out


def num(x: Any) -> float | None:
    return clean(x)


def j(x: Any) -> Any:
    return jsonable(x)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
