"""Shared helpers for the analytics modules.

Conventions (every analytics module follows them):

* Prices come in as a ``pd.Series`` of closes, or a ``pd.DataFrame`` with lowercase
  columns ``open, high, low, close, volume``, indexed by a sorted, tz-naive
  ``DatetimeIndex``. Functions drop NaNs themselves and never mutate their inputs.
* Daily data is annualised with ``TRADING_DAYS`` (252); ``periods_per_year`` infers the
  factor from the index spacing so weekly / monthly inputs also work.
* Results are plain dicts / lists. A time series is returned as ``ser(s)`` =
  ``{"t": [iso dates], "v": [values]}``. Call ``jsonable`` on anything that may still
  contain numpy scalars, NaN/inf (-> None), Timestamps (-> ISO strings) or pandas objects.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def clean(x: Any) -> float | None:
    """Float, or None for None / NaN / inf / non-numeric."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def iso(ts: Any) -> str:
    """ISO string: 'YYYY-MM-DD' for midnight timestamps, else 'YYYY-MM-DDTHH:MM:SS'."""
    if isinstance(ts, str):
        return ts
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    if t.hour == 0 and t.minute == 0 and t.second == 0:
        return t.strftime("%Y-%m-%d")
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def jsonable(obj: Any, digits: int | None = None) -> Any:
    """Recursively convert to JSON-safe Python types (NaN/inf -> None)."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = clean(obj)
        if f is None:
            return None
        return round(f, digits) if digits is not None else f
    if isinstance(obj, (pd.Timestamp, datetime, date, np.datetime64)):
        return iso(obj)
    if isinstance(obj, pd.Series):
        return ser(obj, digits)
    if isinstance(obj, pd.DataFrame):
        return records(obj, digits)
    if isinstance(obj, np.ndarray):
        return [jsonable(v, digits) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): jsonable(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v, digits) for v in obj]
    if obj is pd.NaT:
        return None
    try:
        return clean(obj)
    except Exception:  # noqa: BLE001
        return str(obj)


def ser(s: pd.Series | None, digits: int | None = None) -> dict:
    """Series -> {"t": [iso dates], "v": [values]} (NaN -> None)."""
    if s is None or len(s) == 0:
        return {"t": [], "v": []}
    return {"t": [iso(t) for t in s.index], "v": [jsonable(v, digits) for v in s.to_numpy()]}


def records(df: pd.DataFrame | None, digits: int | None = None, index: str | None = None) -> list[dict]:
    """DataFrame -> list of row dicts; include the index under ``index`` if given."""
    if df is None or len(df) == 0:
        return []
    out = []
    for idx, row in df.iterrows():
        d = {str(k): jsonable(v, digits) for k, v in row.items()}
        if index:
            d = {index: jsonable(idx, digits), **d}
        out.append(d)
    return out


def as_close(x: pd.Series | pd.DataFrame) -> pd.Series:
    """Close series from a Series or an OHLCV frame (lowercase or Title-case columns)."""
    if isinstance(x, pd.DataFrame):
        for c in ("close", "Close", "adjclose", "Adj Close"):
            if c in x.columns:
                x = x[c]
                break
        else:
            raise KeyError("no close column")
    s = pd.to_numeric(x, errors="coerce").dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.astype(float)


def ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise an OHLCV frame to lowercase columns, sorted, NaN closes dropped."""
    d = df.rename(columns={c: str(c).lower().replace("adj close", "adjclose") for c in df.columns})
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d.dropna(subset=["close"])


def to_returns(close: pd.Series, log: bool = False) -> pd.Series:
    """Simple (default) or log returns, first NaN dropped."""
    c = as_close(close)
    r = np.log(c).diff() if log else c.pct_change()
    return r.replace([np.inf, -np.inf], np.nan).dropna()


def periods_per_year(index: pd.Index) -> float:
    """Annualisation factor inferred from median spacing: daily 252, weekly 52, monthly 12."""
    if len(index) < 3:
        return float(TRADING_DAYS)
    d = pd.Series(pd.DatetimeIndex(index)).diff().dt.total_seconds().dropna().median() / 86400.0
    if d <= 0.2:  # intraday: 6.5h session
        return float(TRADING_DAYS * max(1.0, round(6.5 / (d * 24))))
    if d <= 1.6:
        return float(TRADING_DAYS)
    if d <= 8:
        return 52.0
    if d <= 35:
        return 12.0
    if d <= 100:
        return 4.0
    return 1.0


def align(*series: pd.Series, how: str = "inner") -> pd.DataFrame:
    """Align several series on their common dates (columns 0..n-1 unless named)."""
    cols = {}
    for i, s in enumerate(series):
        name = s.name if s.name is not None and s.name not in cols else i
        cols[name] = s
    return pd.concat(cols, axis=1, join=how).dropna()


def window(close: pd.Series, start: str | pd.Timestamp | None = None, end: str | pd.Timestamp | None = None) -> pd.Series:
    """Slice by dates, tolerant of tz-aware indexes."""
    s = close
    if start is not None:
        s = s[s.index >= pd.Timestamp(start)]
    if end is not None:
        s = s[s.index <= pd.Timestamp(end)]
    return s


def safe(fn, *args, default=None, **kwargs):
    """Call fn and return default on any exception (for optional sub-results)."""
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        return default


def pct_rank(values: Iterable[float], x: float) -> float | None:
    """Percentile rank (0-100) of x within values (NaNs ignored)."""
    v = np.asarray([clean(a) for a in values if clean(a) is not None], dtype=float)
    if v.size == 0 or clean(x) is None:
        return None
    return float((v <= x).mean() * 100.0)
