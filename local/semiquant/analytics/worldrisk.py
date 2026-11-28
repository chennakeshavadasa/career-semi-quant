"""World-risk statistics (pure functions, no network).

* ``transit_stats``: how far a chokepoint's daily ship count is from normal, how long it has been
  disrupted, and which ship types are missing.
* ``world_summary``: how much of the tracked cargo capacity is currently missing.
* ``attention``: how far a news topic's coverage is above its recent norm.

"Normal" is taken two ways and the more cautious answer wins, so a strait is only flagged when it is low
against its own last three years *and* against the same weeks of earlier years (shipping is seasonal):

1. the median of up to 156 weekly means, ending four weeks ago (robust to a few odd weeks);
2. the median, over the previous 1-3 years, of the same four-week window of the year.

The status blends the last 7 days (reacts fast to a new closure) and the last 28 days (ignores a one-week dip).
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median, pstdev

RECENT = 7
HOLDOUT = 28           # days kept out of the baseline so a disruption doesn't become "normal" in its first month
MAX_BLOCKS = 156       # three years of weekly means
MIN_BASE = 5.0         # ships per day; below this, percentages are noise
BLEND = 0.6            # weight of the 7-day change (the 28-day change gets 1 - BLEND)
LEVELS = [("severe", -0.60), ("disrupted", -0.30), ("watch", -0.15)]
SURGE = 0.30
STATUS_RANK = {"severe": 4, "disrupted": 3, "watch": 2, "surge": 1, "normal": 0, "low": -1}
TYPES = ("tanker", "container", "dry_bulk", "other")


def rolling_mean(x: list[float], k: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= k:
            s -= x[i - k]
        if i >= k - 1:
            out[i] = s / k
    return out


def weekly_means(x: list[float], end: int, n: int) -> list[float]:
    """Up to ``n`` non-overlapping 7-day means going back from index ``end`` (exclusive), newest first."""
    out, i = [], end
    while i - 7 >= 0 and len(out) < n:
        out.append(mean(x[i - 7:i]))
        i -= 7
    return out


def _seasonal(dates: list[str], x: list[float]) -> float | None:
    """Median over the previous three years of the mean count in the same four weeks of the year."""
    try:
        last = date.fromisoformat(dates[-1])
    except (ValueError, IndexError):
        return None
    pos = {d: i for i, d in enumerate(dates)}
    vals = []
    for y in (1, 2, 3):
        centre = last - timedelta(days=364 * y)
        window = [x[pos[k]] for k in ((centre + timedelta(days=j)).isoformat() for j in range(-24, 4)) if k in pos]
        if len(window) >= 20:
            vals.append(mean(window))
    return median(vals) if vals else None


def _change(now: float, a: float | None, b: float | None) -> float:
    """Relative change against the more cautious of two baselines (0 if they disagree on direction)."""
    ch = [now / v - 1 for v in (a, b) if v and v > 0]
    if not ch:
        return 0.0
    if all(c < 0 for c in ch):
        return max(ch)
    if all(c > 0 for c in ch):
        return min(ch)
    return 0.0


def classify(change: float, base: float) -> str:
    if base < MIN_BASE:
        return "low"
    for name, thr in LEVELS:
        if change <= thr:
            return name
    return "surge" if change >= SURGE else "normal"


def episode_start(dates: list[str], x: list[float], base: float, below: bool = True, frac: float = 0.7) -> str | None:
    """Start of the current run in which the 7-day mean is below (or above) ``frac`` of normal.

    The 7-day mean crosses the line about three days after the real start, so the answer is moved back
    three days. None if the whole series is in the run (start unknown)."""
    r = rolling_mean(x, RECENT)
    line = base * (frac if below else 2 - frac)
    inside = [(v is not None and (v < line if below else v > line)) for v in r]
    if not inside or not inside[-1]:
        return None
    j = len(inside) - 1
    while j > 0 and inside[j - 1]:
        j -= 1
    if j <= RECENT:
        return None
    return dates[max(0, j - 3)]


def _type_stats(series: list[float]) -> dict | None:
    if len(series) < 60:
        return None
    base = median(weekly_means(series, len(series) - HOLDOUT, MAX_BLOCKS) or [0])
    now = mean(series[-RECENT:])
    return {"avg7": now, "base": base, "chg": (now / base - 1) if base > 0.5 else None}


def transit_stats(dates: list[str], total: list[float], tonnes: list[float] | None = None,
                  types: dict[str, list[float]] | None = None) -> dict | None:
    """Everything the page shows about one chokepoint. None if there is too little history to judge."""
    n = len(total)
    if n < 120 or len(dates) != n:
        return None
    blocks = weekly_means(total, n - HOLDOUT, MAX_BLOCKS)
    if len(blocks) < 8:
        return None
    base_a = median(blocks)
    base_b = _seasonal(dates, total)
    avg7, avg28 = mean(total[-RECENT:]), mean(total[-HOLDOUT:])
    chg7, chg28 = _change(avg7, base_a, base_b), _change(avg28, base_a, base_b)
    chg = BLEND * chg7 + (1 - BLEND) * chg28
    base = min(v for v in (base_a, base_b) if v is not None) if chg < 0 else max(v for v in (base_a, base_b) if v is not None)
    status = classify(chg, base_a)  # "low traffic" is judged on the three-year level, not the seasonal one
    out = {"last_date": dates[-1], "avg7": avg7, "avg28": avg28, "base": base_a, "base_seasonal": base_b,
           "chg7": chg7, "chg28": chg28, "chg": chg, "status": status, "since": None, "days": None}
    # year over year, same seven days a year earlier
    try:
        last = date.fromisoformat(dates[-1])
        pos = {d: i for i, d in enumerate(dates)}
        ago = [total[pos[k]] for k in ((last - timedelta(days=364 + j)).isoformat() for j in range(7)) if k in pos]
        out["yoy"] = avg7 / mean(ago) - 1 if len(ago) >= 5 and mean(ago) > 0 else None
    except ValueError:
        out["yoy"] = None
    if status in ("severe", "disrupted", "watch", "surge"):
        s = episode_start(dates, total, min(base_a, base_b) if (base_b and status != "surge") else base_a, below=status != "surge")
        if s:
            out["since"] = s
            out["days"] = (date.fromisoformat(dates[-1]) - date.fromisoformat(s)).days
    if types:
        out["types"] = {k: ts for k, v in types.items() if (ts := _type_stats(v))}
    if tonnes and len(tonnes) == n:
        tb = median(weekly_means(tonnes, n - HOLDOUT, MAX_BLOCKS) or [0])
        out["tonnes_base"], out["tonnes_avg7"] = tb, mean(tonnes[-RECENT:])
    # weekly means for the last year (sparkline), oldest first
    out["weekly"] = list(reversed(weekly_means(total, n, 52)))
    return out


def world_summary(stats: dict[str, dict]) -> dict:
    """Roll the per-chokepoint results up: how many are disrupted and how much cargo capacity is missing."""
    ok = {k: v for k, v in stats.items() if v}
    base = sum(v.get("tonnes_base") or 0 for v in ok.values())
    missing = sum(max(0.0, (v.get("tonnes_base") or 0) - (v.get("tonnes_avg7") or 0)) for v in ok.values()
                  if v["status"] in ("severe", "disrupted", "watch"))
    counts = {s: sum(1 for v in ok.values() if v["status"] == s) for s in STATUS_RANK}
    for k, v in ok.items():
        v["share"] = (v.get("tonnes_base") or 0) / base if base else None
    return {"counts": counts, "tracked": len(ok), "missing_capacity": (missing / base) if base else None}


def attention(values: list[float], recent: int = 7, base_days: int = 83) -> dict | None:
    """Coverage now vs its recent norm. ``values`` is a daily series (newest last)."""
    v = [x for x in values if x is not None]
    if len(v) < recent + 20:
        return None
    now, hist = mean(v[-recent:]), v[-(recent + base_days):-recent]
    base, sd = mean(hist), pstdev(hist)
    sd = max(sd, 0.1 * base, 1e-9)
    return {"recent": now, "base": base, "ratio": now / base if base > 0 else None, "z": (now - base) / sd}
