"""Regenerate the real-data test fixtures from Yahoo Finance (needs network).

    python tests/make_fixtures.py

Writes tests/fixtures/: daily closes for stocks/benchmarks/factor ETFs, NVDA OHLCV
(daily + 1-minute), statements / info / analyst / earnings / options snapshots for NVDA
and INTC (a loss-making company, for edge cases). Tests only read these files.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "fixtures")
CLOSES = ["NVDA", "AMD", "TSM", "AVGO", "INTC", "MU", "QCOM", "TXN", "ADI", "AMAT", "LRCX", "KLAC",
          "SPY", "SOXX", "QQQ", "IWM", "IWD", "IWF", "MTUM", "QUAL", "USMV", "^TNX", "^VIX", "DX-Y.NYB", "CL=F"]


def _j(o):
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return str(o)


def dump(name, obj):
    with open(os.path.join(FX, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, default=_j, separators=(",", ":"))
    print("wrote", name, os.path.getsize(os.path.join(FX, name)) // 1024, "KB")


def frame_json(df):
    """yfinance statement frame (items x period columns) -> {period_iso: {item: value}}."""
    if df is None or df.empty:
        return {}
    return {pd.Timestamp(c).strftime("%Y-%m-%d"): {str(k): _j(v) for k, v in df[c].items()} for c in df.columns}


def statements(t):
    tk = yf.Ticker(t)
    return {
        "income_a": frame_json(tk.income_stmt), "balance_a": frame_json(tk.balance_sheet), "cashflow_a": frame_json(tk.cashflow),
        "income_q": frame_json(tk.quarterly_income_stmt), "balance_q": frame_json(tk.quarterly_balance_sheet),
        "cashflow_q": frame_json(tk.quarterly_cashflow),
    }


def main():
    os.makedirs(FX, exist_ok=True)
    df = yf.download(CLOSES, period="7y", interval="1d", auto_adjust=True, progress=False, group_by="ticker", threads=True)
    closes = pd.DataFrame({t: df[t]["Close"] for t in CLOSES}).round(4)
    closes.index.name = "date"
    closes.to_csv(os.path.join(FX, "prices_daily.csv"))
    print("prices_daily.csv", closes.shape)

    o = df["NVDA"][["Open", "High", "Low", "Close", "Volume"]].dropna().round(4)
    o.columns = ["open", "high", "low", "close", "volume"]
    o.index.name = "date"
    o.to_csv(os.path.join(FX, "nvda_ohlcv.csv"))
    m = yf.Ticker("NVDA").history(period="5d", interval="1m", prepost=True)[["Open", "High", "Low", "Close", "Volume"]]
    m.index = m.index.tz_convert("America/New_York").tz_localize(None)
    m.columns = ["open", "high", "low", "close", "volume"]
    m.index.name = "time"
    m.round(4).to_csv(os.path.join(FX, "nvda_intraday_1m.csv"))
    print("intraday", m.shape)

    for t in ["NVDA", "INTC"]:
        tk = yf.Ticker(t)
        low = t.lower()
        dump(f"{low}_statements.json", statements(t))
        dump(f"{low}_info.json", tk.info)
        ed = tk.get_earnings_dates(limit=40)
        dump(f"{low}_earnings.json", [{"date": i.isoformat(), **{k: _j(v) for k, v in r.items()}} for i, r in ed.iterrows()])
        dump(f"{low}_analysts.json", {
            "price_targets": tk.analyst_price_targets,
            "recommendations": tk.recommendations_summary.to_dict("records"),
            "upgrades": [{"date": i.isoformat(), **{k: _j(v) for k, v in r.items()}} for i, r in tk.upgrades_downgrades.head(40).iterrows()],
            "earnings_estimate": tk.earnings_estimate.to_dict(), "revenue_estimate": tk.revenue_estimate.to_dict(),
            "eps_trend": tk.eps_trend.to_dict(), "eps_revisions": tk.eps_revisions.to_dict(),
            "growth_estimates": tk.growth_estimates.to_dict(),
        })

    tk = yf.Ticker("NVDA")
    spot = float(tk.fast_info["lastPrice"])
    exps = list(tk.options)
    chains = {}
    picks = [exps[i] for i in (0, 2, 4, 7, 10, 14) if i < len(exps)]
    for e in picks:
        c = tk.option_chain(e)
        chains[e] = {"calls": c.calls.to_dict("records"), "puts": c.puts.to_dict("records")}
    dump("nvda_options.json", {"spot": spot, "asof": datetime.now().isoformat(timespec="seconds"),
                               "expiries": exps, "chains": chains, "dividend_yield": tk.info.get("dividendYield")})


if __name__ == "__main__":
    main()
