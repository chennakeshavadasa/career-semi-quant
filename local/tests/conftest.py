"""Shared pytest fixtures: real Yahoo data snapshots from tests/fixtures (no network).

Regenerate with ``python tests/make_fixtures.py``. Frames are returned in the same shape
the data layer produces, so tests exercise the exact production code path:

* ``closes``           daily closes, columns = tickers (NVDA ... CL=F), DatetimeIndex (tz-naive)
* ``nvda_ohlcv``       daily OHLCV, lowercase columns open/high/low/close/volume
* ``nvda_intraday``    1-minute OHLCV incl. pre/post market, naive New York time
* ``*_statements``     dict of yfinance-shaped frames: rows = line items, columns = period
                       Timestamps, newest first. Keys income_a, balance_a, cashflow_a,
                       income_q, balance_q, cashflow_q
* ``*_info``           Ticker.info dict
* ``*_earnings``       frame shaped like Ticker.get_earnings_dates(): tz-aware index
                       "Earnings Date", columns "EPS Estimate", "Reported EPS", "Surprise(%)"
* ``*_analysts``       dict of analyst blocks (price_targets, recommendations, upgrades, ...)
* ``nvda_options``     {"spot", "asof", "expiries", "dividend_yield",
                        "chains": {expiry: {"calls": DataFrame, "puts": DataFrame}}}
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_json(name: str):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


def statement_frames(name: str) -> dict[str, pd.DataFrame]:
    raw = load_json(name)
    out = {}
    for key, periods in raw.items():
        df = pd.DataFrame(periods)  # items x periods
        df.columns = pd.to_datetime(df.columns)
        out[key] = df[sorted(df.columns, reverse=True)].apply(pd.to_numeric, errors="coerce")
    return out


def earnings_frame(name: str) -> pd.DataFrame:
    rows = load_json(name)
    # Offsets mix -05:00 / -04:00 (daylight saving): parse via UTC, then back to New York.
    idx = pd.DatetimeIndex(pd.to_datetime([r["date"] for r in rows], utc=True).tz_convert("America/New_York"),
                           name="Earnings Date")
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "date"} for r in rows], index=idx)
    return df.apply(pd.to_numeric, errors="coerce")


def gbm(n: int = 1500, mu: float = 0.10, sigma: float = 0.30, seed: int = 0, start: str = "2019-01-02",
        s0: float = 100.0) -> pd.Series:
    """Synthetic daily GBM closes on a business-day calendar (known drift / vol)."""
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    r = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * rng.standard_normal(n)
    idx = pd.bdate_range(start, periods=n + 1)
    return pd.Series(s0 * np.exp(np.concatenate([[0.0], np.cumsum(r)])), index=idx, name="GBM")


@pytest.fixture(scope="session")
def closes() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(FX, "prices_daily.csv"), index_col=0, parse_dates=True)
    return df.sort_index()


@pytest.fixture(scope="session")
def nvda_ohlcv() -> pd.DataFrame:
    return pd.read_csv(os.path.join(FX, "nvda_ohlcv.csv"), index_col=0, parse_dates=True).sort_index()


@pytest.fixture(scope="session")
def nvda_intraday() -> pd.DataFrame:
    return pd.read_csv(os.path.join(FX, "nvda_intraday_1m.csv"), index_col=0, parse_dates=True).sort_index()


@pytest.fixture(scope="session")
def nvda_statements():
    return statement_frames("nvda_statements.json")


@pytest.fixture(scope="session")
def intc_statements():
    return statement_frames("intc_statements.json")


@pytest.fixture(scope="session")
def nvda_info():
    return load_json("nvda_info.json")


@pytest.fixture(scope="session")
def intc_info():
    return load_json("intc_info.json")


@pytest.fixture(scope="session")
def nvda_earnings():
    return earnings_frame("nvda_earnings.json")


@pytest.fixture(scope="session")
def intc_earnings():
    return earnings_frame("intc_earnings.json")


@pytest.fixture(scope="session")
def nvda_analysts():
    return load_json("nvda_analysts.json")


@pytest.fixture(scope="session")
def nvda_options():
    raw = load_json("nvda_options.json")
    chains = {e: {"calls": pd.DataFrame(c["calls"]), "puts": pd.DataFrame(c["puts"])} for e, c in raw["chains"].items()}
    return {**raw, "chains": chains}


@pytest.fixture
def synthetic():
    """Factory for synthetic GBM closes: synthetic(n=..., mu=..., sigma=..., seed=...)."""
    return gbm
