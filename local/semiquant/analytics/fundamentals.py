"""Fundamental analytics from yfinance-shaped financial statements.

Inputs
    ``stmts``: dict of yfinance statement frames (rows = line items such as "Total Revenue", columns =
    period Timestamps, newest first) under keys income_a, balance_a, cashflow_a, income_q, balance_q,
    cashflow_q (any may be missing). ``info``: the Ticker.info dict.
Conventions
    Row names differ between companies, so every item is looked up through a list of synonyms (first
    match with data wins, then a case/punctuation-insensitive match). Periods that yfinance pads with a
    mostly-empty column (no revenue / total assets / operating cash flow) are ignored. TTM = sum of the
    last four consecutive reported quarters; the latest annual period is the fallback. Ratios are
    fractions (0.25 = 25 %); a ratio whose denominator is zero or (where it makes the ratio meaningless)
    negative is None. Money values are in the statements' currency (``info["financialCurrency"]``).
Methods
    Piotroski (2000) F-score; Altman (1968) Z-score, original manufacturing model (plus Altman's 1995
    Z'' for reference); two-stage DCF with a linear growth fade and a Gordon-growth terminal value;
    reverse DCF by Brent's method.
"""
from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ._util import clean, iso, jsonable

__all__ = ["statement_table", "derived_metrics", "piotroski", "altman_z", "valuation", "dcf", "reverse_dcf",
           "dcf_sensitivity", "fundamental_summary"]

KEYS = ("income_a", "balance_a", "cashflow_a", "income_q", "balance_q", "cashflow_q")

ITEMS: dict[str, tuple[str, ...]] = {
    # income statement
    "revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
    "cogs": ("Cost Of Revenue", "Reconciled Cost Of Revenue"),
    "gross_profit": ("Gross Profit",),
    "rnd": ("Research And Development",),
    "sga": ("Selling General And Administration",),
    "opex": ("Operating Expense",),
    "operating_income": ("Operating Income", "Total Operating Income As Reported"),
    "ebit": ("EBIT",),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
    "pretax_income": ("Pretax Income",),
    "tax": ("Tax Provision",),
    "tax_rate": ("Tax Rate For Calcs",),
    "net_income": ("Net Income Common Stockholders", "Net Income",
                   "Net Income From Continuing Operation Net Minority Interest"),
    "diluted_eps": ("Diluted EPS", "Basic EPS"),
    "diluted_shares": ("Diluted Average Shares", "Basic Average Shares"),
    "d_and_a_is": ("Reconciled Depreciation",),
    # balance sheet
    "total_assets": ("Total Assets",),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "cash_sti": ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
    "cash": ("Cash And Cash Equivalents", "Cash Financial"),
    "receivables": ("Accounts Receivable", "Receivables"),
    "inventory": ("Inventory",),
    "net_ppe": ("Net PPE",),
    "goodwill_intangibles": ("Goodwill And Other Intangible Assets", "Goodwill"),
    "accounts_payable": ("Accounts Payable", "Payables"),
    "total_debt": ("Total Debt",),
    "long_term_debt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
    "current_debt": ("Current Debt", "Current Debt And Capital Lease Obligation"),
    "total_liabilities": ("Total Liabilities Net Minority Interest",),
    "equity": ("Stockholders Equity", "Common Stock Equity"),
    "total_equity": ("Total Equity Gross Minority Interest",),
    "minority_interest": ("Minority Interest",),
    "preferred": ("Preferred Stock",),
    "retained_earnings": ("Retained Earnings",),
    "working_capital": ("Working Capital",),
    "invested_capital": ("Invested Capital",),
    "shares_out": ("Ordinary Shares Number", "Share Issued"),
    # cash flow statement
    "ocf": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    "capex": ("Capital Expenditure", "Purchase Of PPE", "Net PPE Purchase And Sale"),
    "fcf": ("Free Cash Flow",),
    "sbc": ("Stock Based Compensation",),
    "d_and_a": ("Depreciation And Amortization", "Depreciation Amortization Depletion", "Reconciled Depreciation"),
    "buybacks": ("Repurchase Of Capital Stock", "Common Stock Payments"),
    "issuance": ("Issuance Of Capital Stock", "Common Stock Issuance"),
    "net_issuance": ("Net Common Stock Issuance",),
    "dividends": ("Cash Dividends Paid", "Common Stock Dividend Paid"),
    "change_wc": ("Change In Working Capital",),
    "investing_cf": ("Investing Cash Flow", "Cash Flow From Continuing Investing Activities"),
    "financing_cf": ("Financing Cash Flow", "Cash Flow From Continuing Financing Activities"),
    "debt_issuance": ("Issuance Of Debt", "Long Term Debt Issuance"),
    "debt_repayment": ("Repayment Of Debt", "Long Term Debt Payments"),
}

TABLE_ITEMS: dict[str, list[tuple[str, str]]] = {
    "income": [("Total Revenue", "revenue"), ("Cost of Revenue", "cogs"), ("Gross Profit", "gross_profit"),
               ("Research & Development", "rnd"), ("Selling, General & Admin", "sga"),
               ("Operating Expense", "opex"), ("Operating Income", "operating_income"), ("EBITDA", "ebitda"),
               ("EBIT", "ebit"), ("Interest Expense", "interest_expense"), ("Pretax Income", "pretax_income"),
               ("Tax Provision", "tax"), ("Net Income", "net_income"), ("Diluted EPS", "diluted_eps"),
               ("Diluted Shares", "diluted_shares")],
    "balance": [("Cash & Short-Term Investments", "cash_sti"), ("Cash & Equivalents", "cash"),
                ("Receivables", "receivables"), ("Inventory", "inventory"), ("Current Assets", "current_assets"),
                ("Net PP&E", "net_ppe"), ("Goodwill & Intangibles", "goodwill_intangibles"),
                ("Total Assets", "total_assets"), ("Accounts Payable", "accounts_payable"),
                ("Current Liabilities", "current_liabilities"), ("Total Debt", "total_debt"),
                ("Long-Term Debt", "long_term_debt"), ("Total Liabilities", "total_liabilities"),
                ("Stockholders' Equity", "equity"), ("Retained Earnings", "retained_earnings"),
                ("Working Capital", "working_capital"), ("Shares Outstanding", "shares_out")],
    "cashflow": [("Operating Cash Flow", "ocf"), ("Capital Expenditure", "capex"), ("Free Cash Flow", "fcf"),
                 ("Stock-Based Compensation", "sbc"), ("Depreciation & Amortization", "d_and_a"),
                 ("Change in Working Capital", "change_wc"), ("Share Repurchases", "buybacks"),
                 ("Share Issuance", "issuance"), ("Dividends Paid", "dividends"),
                 ("Debt Issuance", "debt_issuance"), ("Debt Repayment", "debt_repayment"),
                 ("Investing Cash Flow", "investing_cf"), ("Financing Cash Flow", "financing_cf")],
}
ANCHOR = {"income": "revenue", "balance": "total_assets", "cashflow": "ocf"}
_FLOW_KIND = {"revenue": "income", "ebitda": "income", "ebit": "income", "operating_income": "income",
              "net_income": "income", "d_and_a_is": "income", "interest_expense": "income", "cogs": "income",
              "gross_profit": "income", "ocf": "cashflow", "capex": "cashflow", "fcf": "cashflow",
              "buybacks": "cashflow", "issuance": "cashflow", "net_issuance": "cashflow", "dividends": "cashflow",
              "sbc": "cashflow", "d_and_a": "cashflow"}
_ZERO_IF_MISSING = {"buybacks", "issuance", "net_issuance", "dividends"}
STATUTORY_TAX = 0.21


# =============================================================================== statement access
def _norm(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _std(frame) -> pd.DataFrame | None:
    """yfinance statement (items x periods) -> periods x items, ascending tz-naive dates, numeric."""
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    t = frame.T
    idx = pd.to_datetime(pd.Index(t.index), errors="coerce")
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    t = t.set_axis(idx, axis=0)
    t = t[~t.index.isna()]
    t = t.loc[:, ~pd.Index(t.columns).duplicated()]
    try:
        t = t.astype(float)
    except (ValueError, TypeError):
        t = t.apply(pd.to_numeric, errors="coerce").astype(float)
    t = t[~t.index.duplicated(keep="first")].sort_index()
    return t if len(t) else None


def _day(d) -> int:
    """Day number (days since 1970-01-01) of a date-like."""
    return int(np.datetime64(pd.Timestamp(d).to_datetime64(), "D").astype(np.int64))


def _val(o: tuple[np.ndarray, np.ndarray] | None, d, tol_days: int = 15) -> float:
    """Observation nearest to ``d`` within ``tol_days`` from (day numbers, values); NaN otherwise."""
    if o is None or d is None:
        return np.nan
    days, vals = o
    t = _day(d)
    j = int(np.abs(days - t).argmin())
    return float(vals[j]) if abs(int(days[j]) - t) <= tol_days else np.nan


def _find(df: pd.DataFrame | None, names) -> str | None:
    """First synonym that exists with at least one value (exact, then case/punctuation-insensitive)."""
    if df is None:
        return None
    for n in names:
        if n in df.columns and df[n].notna().any():
            return n
    lookup = {_norm(c): c for c in df.columns}
    for n in names:
        c = lookup.get(_norm(n))
        if c is not None and df[c].notna().any():
            return c
    return None


class _Book:
    """Standardised statement frames with cached synonym lookups (built once per request)."""

    def __init__(self, stmts):
        if isinstance(stmts, _Book):
            self.f, self._s, self._o, self._a = stmts.f, stmts._s, stmts._o, stmts._a
            return
        stmts = stmts if isinstance(stmts, dict) else {}
        self.f = {k: _std(stmts.get(k)) for k in KEYS}
        self._s: dict = {}
        self._o: dict = {}
        self._a: dict = {}

    def frame(self, key: str) -> pd.DataFrame | None:
        return self.f.get(key)

    def s(self, key: str, item: str) -> pd.Series | None:
        k = (key, item)
        if k not in self._s:
            df = self.f.get(key)
            name = _find(df, ITEMS[item])
            self._s[k] = None if name is None else df[name]
        return self._s[k]

    def obs(self, key: str, item: str) -> tuple[np.ndarray, np.ndarray] | None:
        """(day numbers, values) of the item's non-missing observations, or None."""
        k = (key, item)
        if k not in self._o:
            s = self.s(key, item)
            v = s.dropna() if s is not None else None
            self._o[k] = None if v is None or v.empty else (
                v.index.values.astype("datetime64[D]").astype(np.int64), v.to_numpy(float))
        return self._o[k]

    def at(self, key: str, item: str, d, tol_days: int = 15) -> float:
        return _val(self.obs(key, item), d, tol_days)

    def align(self, key: str, item: str, periods: pd.DatetimeIndex, shift_days: int = 0,
              tol_days: int = 15) -> pd.Series:
        """Item sampled at ``periods - shift_days`` (nearest observation within ``tol_days``)."""
        o = self.obs(key, item)
        if o is None or len(periods) == 0:
            return pd.Series(np.nan, index=periods, dtype=float)
        days, vals = o
        tgt = periods.values.astype("datetime64[D]").astype(np.int64) - int(shift_days)
        dist = np.abs(days[None, :] - tgt[:, None])
        j = dist.argmin(axis=1)
        ok = dist[np.arange(tgt.size), j] <= tol_days
        return pd.Series(np.where(ok, vals[j], np.nan), index=periods, dtype=float)

    def anchored(self, key: str) -> pd.DatetimeIndex:
        """Periods of ``key`` with data for the statement's anchor item (revenue / assets / OCF)."""
        if key not in self._a:
            df = self.f.get(key)
            if df is None:
                self._a[key] = pd.DatetimeIndex([])
            else:
                s = self.s(key, ANCHOR[key.split("_")[0]])
                self._a[key] = df.index[df.notna().any(axis=1)] if s is None else s.dropna().index
        return self._a[key]


def _book(stmts) -> _Book:
    return stmts if isinstance(stmts, _Book) else _Book(stmts)


def _div(a, b, pos: bool = True):
    """a / b with NaN where b is 0 / NaN (or <= 0 when ``pos``)."""
    a = pd.Series(a, dtype=float) if not isinstance(a, pd.Series) else a.astype(float)
    b = pd.Series(b, dtype=float) if not isinstance(b, pd.Series) else b.astype(float)
    ok = (b > 0) if pos else (b != 0)
    with np.errstate(all="ignore"):
        return (a / b).where(ok)


def _sdiv(a, b, pos: bool = True) -> float | None:
    a, b = clean(a), clean(b)
    if a is None or b is None or b == 0 or (pos and b < 0):
        return None
    return a / b


def _avg(cur: pd.Series, prev: pd.Series) -> pd.Series:
    """Average of opening and closing balances when both exist, else the closing balance."""
    return ((cur + prev) / 2.0).where(prev.notna(), cur)


def _currency_mismatch(info: dict) -> bool:
    fc, qc = (info or {}).get("financialCurrency"), (info or {}).get("currency")
    return bool(fc and qc and str(fc).upper() != str(qc).upper())


# =============================================================================== tables
def statement_table(frame: pd.DataFrame, kind: str = "income") -> dict:
    """Curated statement table for display.

    ``kind`` is "income", "balance" or "cashflow": key items (revenue, margins' building blocks, cash,
    debt, equity, free cash flow, buybacks, ...) are picked by synonym (first matching row name with
    data; missing rows are skipped). An unrecognised kind or frame returns all rows. Periods without the
    statement's anchor item (revenue / total assets / operating cash flow) are dropped.

    Returns {"kind", "periods": [iso dates, oldest -> newest], "rows": [{"item" (display label),
    "source" (yfinance row name), "values": [... aligned to periods]}]}.
    """
    return _table(_std(frame), kind)


def _table(df: pd.DataFrame | None, kind: str) -> dict:
    kind = str(kind).lower()
    if df is None:
        return {"kind": kind, "periods": [], "rows": []}
    rows, used = [], set()
    for label, key in TABLE_ITEMS.get(kind, []):
        name = _find(df, ITEMS[key])
        if name is None or name in used:
            continue
        used.add(name)
        rows.append((label, name))
    if rows and kind in ANCHOR and _find(df, ITEMS[ANCHOR[kind]]):
        keep = df[_find(df, ITEMS[ANCHOR[kind]])].notna()
    else:
        if not rows:
            rows = [(str(c), c) for c in df.columns]
        keep = df[[n for _, n in rows]].notna().any(axis=1)
    sub = df[keep]
    return jsonable({"kind": kind, "periods": [iso(p) for p in sub.index],
                     "rows": [{"item": label, "source": str(name), "values": sub[name].tolist()}
                              for label, name in rows]})


# =============================================================================== derived metrics
def _tax_rate(rate: pd.Series, tax: pd.Series, pretax: pd.Series) -> pd.Series:
    with np.errstate(all="ignore"):
        eff = (tax / pretax).where(pretax > 0)
    out = rate.where((rate >= 0) & (rate <= 0.5))
    out = out.fillna(eff.where((eff >= 0) & (eff <= 0.5)))
    return out.fillna(STATUTORY_TAX)


def derived_metrics(stmts: dict, info: dict | None = None, freq: str = "q") -> dict:
    """Ratio panel per reported period (quarterly ``freq="q"`` or annual ``"a"``).

    Periods are the income-statement periods with revenue; balance-sheet and cash-flow values are taken
    at the same period end (nearest within 15 days). Quarterly flows are annualised by x4 (run-rate) in
    ratios against balance-sheet stocks (roe, roa, roic, asset_turnover, inventory_days, dso,
    net_debt_to_ebitda); pure flow ratios (margins, coverage, conversion) need no annualisation. Averages
    use opening and closing balances (prior quarter / prior year) when both exist, else the closing
    balance. Growth rates are year over year (the same quarter a year earlier for quarterly data).

    Definitions: gross/operating/net/fcf margin = item / revenue; rnd, sbc, capex _pct_revenue =
    R&D, stock comp, |capex| / revenue; roe = net income / avg equity; roa = net income / avg total
    assets; roic = NOPAT / avg invested capital with NOPAT = EBIT x (1 - tax rate) (yfinance "Tax Rate
    For Calcs", else provision / pretax income, else 21 %) and invested capital = yfinance "Invested
    Capital" (else debt + equity); asset_turnover = revenue / avg assets; inventory_days = inventory /
    COGS x 365; dso = receivables / revenue x 365; current_ratio = current assets / current liabilities;
    quick_ratio = (cash + short-term investments + receivables) / current liabilities; debt_to_equity =
    total debt / equity; net_debt_to_ebitda = (total debt - cash & ST investments) / EBITDA;
    interest_coverage = EBIT / interest expense; fcf_conversion = FCF / net income; share_change_yoy =
    change in diluted average shares (else shares outstanding).

    Returns {"freq", "periods": [iso], "metrics": {name: [values aligned to periods]}, "latest":
    {name: latest non-null value}, "latest_period": {name: iso}, "currency", "warnings": [...]}.
    """
    fq = "q" if str(freq).lower().startswith("q") else "a"
    B = _book(stmts)
    names = ["revenue_growth_yoy", "gross_margin", "operating_margin", "net_margin", "fcf_margin", "rnd_pct_revenue",
             "sbc_pct_revenue", "capex_pct_revenue", "roe", "roa", "roic", "asset_turnover", "inventory_days", "dso",
             "current_ratio", "quick_ratio", "debt_to_equity", "net_debt_to_ebitda", "interest_coverage",
             "fcf_conversion", "share_change_yoy"]
    warns: list[str] = []
    ccy = (info or {}).get("financialCurrency") if isinstance(info, dict) else None
    ik, bk, ck = f"income_{fq}", f"balance_{fq}", f"cashflow_{fq}"
    periods = B.anchored(ik) if B.frame(ik) is not None else pd.DatetimeIndex([])
    if len(periods) == 0:
        return jsonable({"freq": fq, "periods": [], "metrics": {k: [] for k in names}, "latest": {k: None for k in names},
                         "latest_period": {k: None for k in names}, "currency": ccy,
                         "warnings": [f"no {'quarterly' if fq == 'q' else 'annual'} income statement with revenue"]})
    for k in (bk, ck):
        if B.frame(k) is None:
            warns.append(f"{k} missing: balance-sheet / cash-flow ratios unavailable")
    ann = 4.0 if fq == "q" else 1.0
    lag = 91 if fq == "q" else 365

    def inc(item):
        return B.align(ik, item, periods, 0, 5)

    def bal(item, shift=0):
        return B.align(bk, item, periods, shift, 20 if shift else 15)

    def cfl(item):
        return B.align(ck, item, periods, 0, 15)

    rev = inc("revenue")
    rev_ly = B.align(ik, "revenue", periods, 365, 20)
    cogs = inc("cogs")
    gp = inc("gross_profit").fillna(rev - cogs)
    opinc = inc("operating_income")
    ebit = inc("ebit").fillna(opinc)
    da = inc("d_and_a_is").fillna(cfl("d_and_a"))
    ebitda = inc("ebitda").fillna(ebit + da)
    ni = inc("net_income")
    tax_rate = _tax_rate(inc("tax_rate"), inc("tax"), inc("pretax_income"))
    nopat = ebit * (1.0 - tax_rate)
    interest = inc("interest_expense")
    shares = inc("diluted_shares")
    shares_ly = B.align(ik, "diluted_shares", periods, 365, 20)
    if shares.isna().all():
        shares, shares_ly = bal("shares_out"), bal("shares_out", 365)

    ta, ta0 = bal("total_assets"), bal("total_assets", lag)
    eq, eq0 = bal("equity"), bal("equity", lag)
    debt = bal("total_debt").fillna(bal("long_term_debt").add(bal("current_debt"), fill_value=0.0))
    debt0 = bal("total_debt", lag).fillna(bal("long_term_debt", lag).add(bal("current_debt", lag), fill_value=0.0))
    ic = bal("invested_capital").fillna(debt + eq)
    ic0 = bal("invested_capital", lag).fillna(debt0 + eq0)
    cash_sti = bal("cash_sti")
    recv, inv = bal("receivables"), bal("inventory")
    ca, cl = bal("current_assets"), bal("current_liabilities")
    ocf, capex = cfl("ocf"), cfl("capex")
    fcf = cfl("fcf").fillna(ocf + capex)
    sbc, rnd = cfl("sbc"), inc("rnd")

    m = {
        "revenue_growth_yoy": _div(rev, rev_ly) - 1.0,
        "gross_margin": _div(gp, rev),
        "operating_margin": _div(opinc, rev),
        "net_margin": _div(ni, rev),
        "fcf_margin": _div(fcf, rev),
        "rnd_pct_revenue": _div(rnd, rev),
        "sbc_pct_revenue": _div(sbc, rev),
        "capex_pct_revenue": _div(capex.abs(), rev),
        "roe": _div(ni * ann, _avg(eq, eq0)),
        "roa": _div(ni * ann, _avg(ta, ta0)),
        "roic": _div(nopat * ann, _avg(ic, ic0)),
        "asset_turnover": _div(rev * ann, _avg(ta, ta0)),
        "inventory_days": _div(inv, cogs * ann) * 365.0,
        "dso": _div(recv, rev * ann) * 365.0,
        "current_ratio": _div(ca, cl),
        "quick_ratio": _div(cash_sti + recv.fillna(0.0), cl),
        "debt_to_equity": _div(debt, eq),
        "net_debt_to_ebitda": _div(debt - cash_sti, ebitda * ann),
        "interest_coverage": _div(ebit, interest),
        "fcf_conversion": _div(fcf, ni),
        "share_change_yoy": _div(shares, shares_ly) - 1.0,
    }
    latest, latest_p = {}, {}
    for k, s in m.items():
        v = s.dropna()
        latest[k] = float(v.iloc[-1]) if len(v) else None
        latest_p[k] = iso(v.index[-1]) if len(v) else None
    return jsonable({"freq": fq, "periods": [iso(p) for p in periods], "metrics": {k: s.tolist() for k, s in m.items()},
                     "latest": latest, "latest_period": latest_p, "currency": ccy,
                     "annualisation": "quarterly flows x4 in ratios against balance-sheet stocks" if fq == "q" else None,
                     "warnings": warns})


# =============================================================================== Piotroski F
def piotroski(stmts: dict) -> dict:
    """Piotroski (2000) F-score from the two latest annual periods (t and t-1; t-2 for opening assets).

    Criteria (pass = 1): roa_positive (net income / opening total assets > 0); cfo_positive (operating
    cash flow > 0); roa_improving (ROA_t > ROA_t-1); accruals (CFO > net income, i.e. accrual
    (NI - CFO) / opening assets < 0); leverage_falling (long-term debt / average total assets did not
    rise); current_ratio_rising; no_dilution (shares outstanding did not rise); gross_margin_rising;
    asset_turnover_rising (revenue / opening total assets). Opening (beginning-of-year) assets fall back
    to closing assets when the earlier balance sheet is missing. A criterion without data has
    "pass": None and is not counted.

    Returns {"score", "max": 9, "n_available", "period", "prior_period", "criteria": [{"name", "label",
    "pass", "value" (year t), "prior" (year t-1)}], "warnings": [...]}.
    """
    B = _book(stmts)
    warns: list[str] = []
    labels = {"roa_positive": "Positive return on assets", "cfo_positive": "Positive operating cash flow",
              "roa_improving": "Improving return on assets", "accruals": "Cash flow exceeds net income (low accruals)",
              "leverage_falling": "Long-term leverage not rising", "current_ratio_rising": "Improving current ratio",
              "no_dilution": "No new shares issued", "gross_margin_rising": "Improving gross margin",
              "asset_turnover_rising": "Improving asset turnover"}
    ni_s = B.s("income_a", "net_income")
    per = B.anchored("income_a")
    if ni_s is not None:
        per = per[per.isin(ni_s.dropna().index)]
    crit = []
    if len(per) < 2:
        warns.append("need two annual periods with revenue and net income")
        crit = [{"name": k, "label": v, "pass": None, "value": None, "prior": None} for k, v in labels.items()]
        return jsonable({"score": 0, "max": 9, "n_available": 0, "period": None, "prior_period": None,
                         "criteria": crit, "warnings": warns})
    t, t1 = per[-1], per[-2]

    def I(item, d):
        return B.at("income_a", item, d, 5)

    def Bl(item, d, tol=20):
        return B.at("balance_a", item, d, tol)

    def C(item, d):
        return B.at("cashflow_a", item, d, 15)

    def ta_open(d):
        v = Bl("total_assets", d - pd.Timedelta(days=365))
        return v if np.isfinite(v) else Bl("total_assets", d)

    def avg_ta(d):
        a, b = Bl("total_assets", d), Bl("total_assets", d - pd.Timedelta(days=365))
        return (a + b) / 2.0 if np.isfinite(b) else a

    def roa(d):
        return _sdiv(I("net_income", d), ta_open(d))

    def accrual(d):
        n, c = I("net_income", d), C("ocf", d)
        return _sdiv(n - c, ta_open(d)) if np.isfinite(n) and np.isfinite(c) else None

    def lever(d):
        ltd = Bl("long_term_debt", d)
        return _sdiv(ltd, avg_ta(d))

    def cr(d):
        return _sdiv(Bl("current_assets", d), Bl("current_liabilities", d))

    def shares(d):
        v = Bl("shares_out", d)
        return v if np.isfinite(v) else I("diluted_shares", d)

    def gm(d):
        rv = I("revenue", d)
        g = I("gross_profit", d)
        g = g if np.isfinite(g) else rv - I("cogs", d)
        return _sdiv(g, rv)

    def turn(d):
        return _sdiv(I("revenue", d), ta_open(d))

    def cmp(a, b, op):
        if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
            return None
        return bool(op(a, b))

    roa_t, roa_1 = roa(t), roa(t1)
    cfo_t, cfo_1 = clean(C("ocf", t)), clean(C("ocf", t1))
    acc_t, acc_1 = accrual(t), accrual(t1)
    lev_t, lev_1 = lever(t), lever(t1)
    cr_t, cr_1 = cr(t), cr(t1)
    sh_t, sh_1 = clean(shares(t)), clean(shares(t1))
    gm_t, gm_1 = gm(t), gm(t1)
    tu_t, tu_1 = turn(t), turn(t1)
    rows = [
        ("roa_positive", None if roa_t is None else roa_t > 0, roa_t, roa_1),
        ("cfo_positive", None if cfo_t is None else cfo_t > 0, cfo_t, cfo_1),
        ("roa_improving", cmp(roa_t, roa_1, lambda a, b: a > b), roa_t, roa_1),
        ("accruals", None if acc_t is None else acc_t < 0, acc_t, acc_1),
        ("leverage_falling", cmp(lev_t, lev_1, lambda a, b: a <= b), lev_t, lev_1),
        ("current_ratio_rising", cmp(cr_t, cr_1, lambda a, b: a > b), cr_t, cr_1),
        ("no_dilution", cmp(sh_t, sh_1, lambda a, b: a <= b), sh_t, sh_1),
        ("gross_margin_rising", cmp(gm_t, gm_1, lambda a, b: a > b), gm_t, gm_1),
        ("asset_turnover_rising", cmp(tu_t, tu_1, lambda a, b: a > b), tu_t, tu_1),
    ]
    crit = [{"name": k, "label": labels[k], "pass": (None if p is None else bool(p)), "value": v, "prior": pr}
            for k, p, v, pr in rows]
    n_av = sum(c["pass"] is not None for c in crit)
    if n_av < 9:
        warns.append(f"{9 - n_av} criteria lack data and are not scored")
    return jsonable({"score": int(sum(c["pass"] is True for c in crit)), "max": 9, "n_available": n_av,
                     "period": iso(t), "prior_period": iso(t1), "criteria": crit, "warnings": warns})


# =============================================================================== TTM snapshot
def _ttm_flow(B: _Book, item: str) -> tuple[float | None, pd.Timestamp | None, str | None]:
    """TTM (last four consecutive anchored quarters) else the latest anchored annual value."""
    kind = _FLOW_KIND[item]
    q_per = B.anchored(f"{kind}_q")
    s = B.s(f"{kind}_q", item)
    if len(q_per) >= 4 and s is not None:
        last4 = q_per[-4:]
        span = (last4[-1] - last4[0]).days
        if 240 <= span <= 310:
            vals = np.array([B.at(f"{kind}_q", item, d, 5) for d in last4])
            if item in _ZERO_IF_MISSING:  # yfinance leaves no-activity quarters empty
                vals = np.nan_to_num(vals)
            if np.isfinite(vals).all():
                return float(vals.sum()), last4[-1], "ttm"
    a_per = B.anchored(f"{kind}_a")
    sa = B.s(f"{kind}_a", item)
    if len(a_per) and sa is not None:
        v = B.at(f"{kind}_a", item, a_per[-1], 5)
        if item in _ZERO_IF_MISSING and not np.isfinite(v):
            v = 0.0
        if np.isfinite(v):
            return float(v), a_per[-1], "annual"
    return None, None, None


def _point(B: _Book, item: str) -> tuple[float | None, pd.Timestamp | None]:
    """Latest balance-sheet value (latest anchored quarter, else latest anchored year)."""
    for key in ("balance_q", "balance_a"):
        per = B.anchored(key)
        if len(per):
            v = B.at(key, item, per[-1], 5)
            return (float(v) if np.isfinite(v) else None), per[-1]
    return None, None


def _epoch(v) -> pd.Timestamp | None:
    x = clean(v)
    if x is None:
        return None
    try:
        return pd.Timestamp(int(x), unit="s")
    except (ValueError, OverflowError):
        return None


def _snapshot(stmts: dict, info: dict) -> dict:
    """TTM flows and latest balances with their sources.

    Statements are the base; when Yahoo's ``info`` reports a more recent quarter (``mostRecentQuarter``
    more than 45 days after the last statement quarter) its TTM aggregates (totalRevenue, ebitda,
    netIncomeToCommon, operatingCashflow), latest totalDebt / totalCash and bookValue x sharesOutstanding
    replace the statement values, FCF becomes OCF(info) + capex(statements) and EBIT = EBITDA(info) -
    D&A(statements). When statements are missing entirely the same info fields are the fallback.
    """
    B = _book(stmts)
    info = info if isinstance(info, dict) else {}
    snap: dict[str, Any] = {}
    src: dict[str, str] = {}
    warns: list[str] = []
    for item in ("revenue", "ebitda", "ebit", "operating_income", "net_income", "ocf", "capex", "fcf", "d_and_a",
                 "interest_expense", "buybacks", "issuance", "net_issuance", "dividends", "sbc"):
        v, end, basis = _ttm_flow(B, item)
        snap[item] = v
        if basis:
            src[item] = f"statements_{basis}"
        snap[f"{item}_end"] = end
    if snap["ebit"] is None and snap["operating_income"] is not None:
        snap["ebit"], src["ebit"] = snap["operating_income"], src["operating_income"]
    if snap["fcf"] is None and snap["ocf"] is not None and snap["capex"] is not None:
        snap["fcf"], src["fcf"] = snap["ocf"] + snap["capex"], src["ocf"]
    if snap["ebitda"] is None and snap["ebit"] is not None and snap["d_and_a"] is not None:
        snap["ebitda"], src["ebitda"] = snap["ebit"] + snap["d_and_a"], src["ebit"]
    for item in ("total_debt", "cash_sti", "equity", "minority_interest", "preferred", "total_assets",
                 "total_liabilities", "shares_out", "long_term_debt", "current_debt"):
        v, end = _point(B, item)
        snap[item] = v
        if v is not None:
            src[item] = "statements"
        snap["balance_end"] = snap.get("balance_end") or end
    if snap["total_debt"] is None and (snap["long_term_debt"] is not None or snap["current_debt"] is not None):
        snap["total_debt"] = (snap["long_term_debt"] or 0.0) + (snap["current_debt"] or 0.0)
        src["total_debt"] = "statements"

    last_q = snap.get("revenue_end") if src.get("revenue") == "statements_ttm" else None
    mrq = _epoch(info.get("mostRecentQuarter"))
    fresher = bool(mrq is not None and last_q is not None and mrq > last_q + pd.Timedelta(days=45))
    info_map = {"revenue": "totalRevenue", "ebitda": "ebitda", "net_income": "netIncomeToCommon",
                "ocf": "operatingCashflow", "total_debt": "totalDebt", "cash_sti": "totalCash"}
    for k, ik in info_map.items():
        v = clean(info.get(ik))
        if v is None:
            continue
        if fresher or snap.get(k) is None:
            if fresher and k in ("ocf",) and snap.get("capex") is not None:
                snap["fcf"], src["fcf"] = v + snap["capex"], "info_ocf+statements_capex"
            if fresher and k == "ebitda" and snap.get("d_and_a") is not None:
                snap["ebit"], src["ebit"] = v - snap["d_and_a"], "info_ebitda-statements_da"
            snap[k], src[k] = v, "info"
    book_ps, sh_info = clean(info.get("bookValue")), clean(info.get("sharesOutstanding"))
    if book_ps is not None and sh_info and (fresher or snap.get("equity") is None):
        snap["equity"], src["equity"] = book_ps * sh_info, "info_bookValue"
    if snap.get("fcf") is None and clean(info.get("freeCashflow")) is not None:
        snap["fcf"], src["fcf"] = clean(info.get("freeCashflow")), "info_levered"
    if fresher:
        warns.append(f"statements end {last_q:%Y-%m-%d} but Yahoo reports a newer quarter ({mrq:%Y-%m-%d}); "
                     "revenue, EBITDA, net income, OCF, debt and cash use Yahoo's TTM figures, other items lag")
    snap["sources"], snap["warnings"], snap["info_fresher"] = src, warns, fresher
    return snap


# =============================================================================== Altman Z
def altman_z(stmts: dict, info: dict) -> dict:
    """Altman (1968) Z-score, original public-manufacturer model:
    Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5 with X1 = working capital / total assets,
    X2 = retained earnings / TA, X3 = EBIT / TA, X4 = market value of equity (info marketCap) / total
    liabilities, X5 = sales / TA. Zones: Z > 2.99 safe, 1.81-2.99 grey, < 1.81 distress.

    Flows are TTM (last four quarters) with the latest quarterly balance sheet when available, else the
    latest annual statements. When the quote and statement currencies differ (ADRs) X4 is undefined and
    z is None. ``z_double_prime`` is Altman's (1995) Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4'' with
    X4'' = book equity / total liabilities (no market data; zones > 2.6 safe, 1.1-2.6 grey).

    Returns {"z", "zone", "components": {"working_capital_to_assets", "retained_earnings_to_assets",
    "ebit_to_assets", "market_equity_to_liabilities", "sales_to_assets"}, "inputs": {...}, "basis",
    "z_double_prime", "zone_double_prime", "warnings": [...]}.
    """
    B = _book(stmts)
    info = info if isinstance(info, dict) else {}
    warns: list[str] = []
    basis = None
    ebit, rev = None, None
    for item in ("ebit", "operating_income"):
        v, _end, b = _ttm_flow(B, item)
        if v is not None:
            ebit, basis = v, b
            break
    rev, _end, b2 = _ttm_flow(B, "revenue")
    basis = basis or b2
    key = None
    for k in ("balance_q", "balance_a"):
        if len(B.anchored(k)):
            key = k
            break
    d = B.anchored(key)[-1] if key else None

    def bl(item):
        return clean(B.at(key, item, d, 5)) if key else None

    ta = bl("total_assets")
    ca, cl = bl("current_assets"), bl("current_liabilities")
    wc = bl("working_capital")
    if wc is None and ca is not None and cl is not None:
        wc = ca - cl
    re_ = bl("retained_earnings")
    tl = bl("total_liabilities")
    if tl is None and ta is not None:
        te = bl("total_equity") or bl("equity")
        tl = ta - te if te is not None else None
    book = bl("equity")
    mcap = clean(info.get("marketCap"))
    if _currency_mismatch(info):
        warns.append(f"quote currency {info.get('currency')} differs from statement currency "
                     f"{info.get('financialCurrency')}: market-value ratio X4 skipped")
        mcap = None
    x1, x2, x3 = _sdiv(wc, ta), _sdiv(re_, ta), _sdiv(ebit, ta)
    x4, x5 = _sdiv(mcap, tl), _sdiv(rev, ta)
    comps = {"working_capital_to_assets": x1, "retained_earnings_to_assets": x2, "ebit_to_assets": x3,
             "market_equity_to_liabilities": x4, "sales_to_assets": x5}
    z = None
    if all(v is not None for v in comps.values()):
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    else:
        missing = [k for k, v in comps.items() if v is None]
        warns.append("Z-score unavailable, missing: " + ", ".join(missing))
    zone = None if z is None else ("safe" if z > 2.99 else ("grey" if z >= 1.81 else "distress"))
    x4b = _sdiv(book, tl)
    z2 = (6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4b) if None not in (x1, x2, x3, x4b) else None
    zone2 = None if z2 is None else ("safe" if z2 > 2.6 else ("grey" if z2 >= 1.1 else "distress"))
    return jsonable({"z": z, "zone": zone, "components": comps,
                     "inputs": {"working_capital": wc, "retained_earnings": re_, "ebit": ebit, "market_cap": mcap,
                                "total_liabilities": tl, "sales": rev, "total_assets": ta, "book_equity": book},
                     "basis": basis, "balance_date": iso(d) if d is not None else None,
                     "z_double_prime": z2, "zone_double_prime": zone2, "warnings": warns})


# =============================================================================== valuation
def _price(info: dict) -> float | None:
    for k in ("currentPrice", "regularMarketPrice", "previousClose", "regularMarketPreviousClose"):
        v = clean(info.get(k))
        if v is not None and v > 0:
            return v
    return None


def _dividend_yield(info: dict, price: float | None) -> tuple[float | None, str | None]:
    """Fractional dividend yield. Recent yfinance returns ``dividendYield`` in PERCENT (0.67 = 0.67 %);
    older versions returned a fraction. The raw value is read both ways and the reading closer (in log
    terms) to dividendRate / price (else trailingAnnualDividendYield, a fraction) is kept; with no
    reference the percent convention is assumed."""
    raw = clean(info.get("dividendYield"))
    rate = clean(info.get("dividendRate"))
    trailing = clean(info.get("trailingAnnualDividendYield"))
    ref = rate / price if (rate is not None and rate > 0 and price) else (trailing if trailing and trailing > 0 else None)
    if raw is None:
        if ref is not None:
            return ref, "dividendRate/price" if rate else "trailingAnnualDividendYield"
        return (0.0, "dividendRate=0") if rate == 0 or trailing == 0 else (None, None)
    if raw <= 0:
        return 0.0, "dividendYield"
    pct, frac = raw / 100.0, raw
    if ref is not None:
        best = min((pct, "dividendYield/100"), (frac, "dividendYield"), key=lambda c: abs(math.log(c[0] / ref)))
        return best
    return pct, "dividendYield/100"


def valuation(info: dict, stmts: dict) -> dict:
    """Valuation multiples and yields.

    Market data from ``info`` (price, marketCap, shares); TTM flows and balances from ``_snapshot``
    (statements, or Yahoo's fresher TTM aggregates when info reports a newer quarter; see ``sources``).
    EV = market cap + total debt + minority interest + preferred - cash & short-term investments.
    pe_ttm / pe_fwd / peg prefer Yahoo's trailingPE / forwardPE / pegRatio (trailingPegRatio); P/E is
    None for non-positive earnings, EV multiples for non-positive denominators, while yields
    (earnings_yield = trailing EPS / price, fcf_yield = FCF / market cap) stay signed. dividend_yield
    normalises yfinance's ``dividendYield`` (now in PERCENT, 0.03 = 0.03 %) to a fraction, cross-checked
    against dividendRate / price and trailingAnnualDividendYield. buyback_yield = TTM net repurchases
    (repurchases - issuance; negative = dilution) / market cap; shareholder_yield = dividend_yield +
    buyback_yield (Faber's version without debt paydown). For ADRs whose statement currency
    (``financialCurrency``) differs from the quote currency, ratios mixing statement values with market
    cap are None and a warning is added.

    Returns {"market_cap", "enterprise_value", "pe_ttm", "pe_fwd", "peg", "ps", "ev_sales", "ev_ebitda",
    "ev_ebit", "p_fcf", "fcf_yield", "earnings_yield", "pb", "dividend_yield", "buyback_yield",
    "shareholder_yield", "price", "currency", "ttm": {...}, "sources": {...}, "warnings": [...]}.
    """
    info = info if isinstance(info, dict) else {}
    snap = _snapshot(_book(stmts), info)
    warns = list(snap["warnings"])
    price = _price(info)
    shares = clean(info.get("sharesOutstanding")) or clean(info.get("impliedSharesOutstanding")) or snap.get("shares_out")
    mcap = clean(info.get("marketCap")) or (price * shares if price and shares else None)
    mismatch = _currency_mismatch(info)
    if mismatch:
        warns.append(f"quote currency {info.get('currency')} differs from statement currency "
                     f"{info.get('financialCurrency')}: statement-based multiples skipped")
    ev = None
    if mcap is not None and not mismatch and (snap.get("total_debt") is not None or snap.get("cash_sti") is not None):
        ev = (mcap + (snap.get("total_debt") or 0.0) + (snap.get("minority_interest") or 0.0)
              + (snap.get("preferred") or 0.0) - (snap.get("cash_sti") or 0.0))
    elif not mismatch:
        ev = clean(info.get("enterpriseValue"))
    rev, ebitda, ebit, fcf, ni = (snap.get(k) for k in ("revenue", "ebitda", "ebit", "fcf", "net_income"))
    eps_t, eps_f = clean(info.get("trailingEps")), clean(info.get("forwardEps"))

    pe_ttm = clean(info.get("trailingPE"))
    if pe_ttm is None and price and eps_t and eps_t > 0:
        pe_ttm = price / eps_t
    if pe_ttm is None and not mismatch and mcap and ni and ni > 0:
        pe_ttm = mcap / ni
    pe_fwd = clean(info.get("forwardPE"))
    if pe_fwd is None and price and eps_f and eps_f > 0:
        pe_fwd = price / eps_f
    if pe_ttm is not None and pe_ttm <= 0:
        pe_ttm = None
    if pe_fwd is not None and pe_fwd <= 0:
        pe_fwd = None
    peg = clean(info.get("pegRatio")) or clean(info.get("trailingPegRatio"))
    if peg is None and pe_ttm is not None:
        g = clean(info.get("earningsGrowth"))
        peg = pe_ttm / (100.0 * g) if g and g > 0 else None
    earnings_yield = (eps_t / price) if (eps_t is not None and price) else (
        (ni / mcap) if (ni is not None and mcap and not mismatch) else None)

    div_y, div_src = _dividend_yield(info, price)
    net_buy = None
    if snap.get("net_issuance") is not None and snap["sources"].get("net_issuance"):
        net_buy = 0.0 - snap["net_issuance"]
    elif snap.get("buybacks") is not None:
        net_buy = 0.0 - (snap["buybacks"] or 0.0) - (snap.get("issuance") or 0.0)
    ok = not mismatch
    out = {
        "market_cap": mcap, "enterprise_value": ev, "pe_ttm": pe_ttm, "pe_fwd": pe_fwd, "peg": peg,
        "ps": _sdiv(mcap, rev) if ok else None,
        "ev_sales": _sdiv(ev, rev) if ok else None,
        "ev_ebitda": _sdiv(ev, ebitda) if ok else None,
        "ev_ebit": _sdiv(ev, ebit) if ok else None,
        "p_fcf": _sdiv(mcap, fcf) if ok else None,
        "fcf_yield": _sdiv(fcf, mcap) if ok else None,
        "earnings_yield": earnings_yield,
        "pb": (_sdiv(mcap, snap.get("equity")) if ok else None),
        "dividend_yield": div_y,
        "buyback_yield": _sdiv(net_buy, mcap) if ok else None,
    }
    out["shareholder_yield"] = (out["dividend_yield"] + out["buyback_yield"]
                                if out["dividend_yield"] is not None and out["buyback_yield"] is not None else None)
    if not ok and clean(info.get("priceToBook")) is not None:
        warns.append("Yahoo's own priceToBook / EV ratios are not used for ADRs (currency mismatch)")
    out.update({
        "price": price, "shares": shares, "currency": info.get("currency"),
        "financial_currency": info.get("financialCurrency"),
        "ttm": {k: snap.get(k) for k in ("revenue", "ebitda", "ebit", "net_income", "ocf", "capex", "fcf",
                                          "buybacks", "issuance", "dividends", "total_debt", "cash_sti", "equity")},
        "ttm_end": iso(snap["revenue_end"]) if snap.get("revenue_end") is not None else None,
        "sources": {**snap["sources"], "dividend_yield": div_src}, "warnings": warns})
    return jsonable(out)


# =============================================================================== DCF
def _dcf_core(fcf0: float, growth: float, years: int, wacc: float, tg: float):
    n = int(years)
    g = np.array([growth]) if n == 1 else growth + (tg - growth) * np.arange(n) / (n - 1)
    fcf = fcf0 * np.cumprod(1.0 + g)
    disc = (1.0 + wacc) ** -np.arange(1, n + 1)
    pv = fcf * disc
    tv = fcf[-1] * (1.0 + tg) / (wacc - tg)
    pv_tv = tv * disc[-1]
    return g, fcf, pv, tv, pv_tv, float(pv.sum() + pv_tv)


def dcf(fcf0: float, growth: float, years: int = 10, wacc: float = 0.10, terminal_growth: float = 0.03,
        net_debt: float = 0.0, shares: float = 1.0) -> dict:
    """Two-stage discounted free cash flow model.

    Stage 1: FCF_t = FCF_{t-1} (1 + g_t) for t = 1..years, with g_t fading linearly from ``growth``
    (year 1) to ``terminal_growth`` (final year). Stage 2: Gordon terminal value TV = FCF_N (1 + g_T) /
    (wacc - g_T). Enterprise value = sum FCF_t / (1 + wacc)^t + TV / (1 + wacc)^N; equity value = EV -
    net_debt; per_share = equity value / shares. Requires wacc > terminal_growth and shares > 0.

    Returns {"per_share", "enterprise_value", "equity_value", "pv_fcf": [...], "fcf": [...],
    "growth_path": [...], "pv_terminal", "terminal_value", "terminal_share" (PV of TV / EV), "wacc",
    "terminal_growth", "years", "warnings": [...]}.
    """
    base = {"per_share": None, "enterprise_value": None, "equity_value": None, "pv_fcf": [], "fcf": [],
            "growth_path": [], "pv_terminal": None, "terminal_value": None, "terminal_share": None,
            "wacc": clean(wacc), "terminal_growth": clean(terminal_growth), "years": years, "warnings": []}
    f0, g0, w, tg = clean(fcf0), clean(growth), clean(wacc), clean(terminal_growth)
    nd, sh = clean(net_debt), clean(shares)
    nd = 0.0 if nd is None else nd
    try:
        n = int(years)
    except (TypeError, ValueError):
        n = 0
    if None in (f0, g0, w, tg) or n < 1 or g0 <= -1.0 or w <= -1.0:
        base["warnings"].append("invalid DCF inputs")
        return jsonable(base)
    if w <= tg:
        base["warnings"].append("wacc must exceed terminal growth")
        return jsonable(base)
    g, fcf, pv, tv, pv_tv, ev = _dcf_core(f0, g0, n, w, tg)
    eq = ev - nd
    if f0 <= 0:
        base["warnings"].append("non-positive starting FCF: the DCF value is not meaningful")
    out = {**base, "enterprise_value": ev, "equity_value": eq,
           "per_share": eq / sh if sh and sh > 0 else None, "pv_fcf": pv.tolist(), "fcf": fcf.tolist(),
           "growth_path": g.tolist(), "pv_terminal": pv_tv, "terminal_value": tv,
           "terminal_share": pv_tv / ev if ev else None, "years": n}
    if not sh or sh <= 0:
        out["warnings"].append("shares missing or non-positive: per-share value unavailable")
    return jsonable(out)


def reverse_dcf(price: float, fcf0: float, net_debt: float, shares: float, wacc: float = 0.10,
                terminal_growth: float = 0.03, years: int = 10) -> dict:
    """Reverse DCF: the year-1 FCF growth (fading linearly to ``terminal_growth`` as in ``dcf``) that makes
    the DCF value per share equal ``price``. Solved with Brent's method on growth in [-50 %, +150 %];
    the per-share value increases monotonically in growth for positive FCF.

    Returns {"implied_growth" (None when FCF <= 0 or the price is outside the bracket), "wacc",
    "terminal_growth", "years", "fcf0", "note"}.
    """
    out = {"implied_growth": None, "wacc": clean(wacc), "terminal_growth": clean(terminal_growth), "years": years,
           "fcf0": clean(fcf0), "note": None}
    p, f0, nd, sh = clean(price), clean(fcf0), clean(net_debt), clean(shares)
    w, tg = clean(wacc), clean(terminal_growth)
    nd = 0.0 if nd is None else nd
    try:
        n = int(years)
    except (TypeError, ValueError):
        n = 0
    if f0 is None:
        out["note"] = "free cash flow unavailable: a reverse DCF is undefined"
        return jsonable(out)
    if f0 <= 0:
        out["note"] = "free cash flow is zero or negative: a reverse DCF is undefined"
        return jsonable(out)
    if p is None or p <= 0 or sh is None or sh <= 0 or w is None or tg is None or n < 1:
        out["note"] = "price, shares, wacc, terminal growth and years must be valid"
        return jsonable(out)
    if w <= tg:
        out["note"] = "wacc must exceed terminal growth"
        return jsonable(out)

    def f(g):
        return (_dcf_core(f0, g, n, w, tg)[5] - nd) / sh - p

    lo, hi = -0.5, 1.5
    flo, fhi = f(lo), f(hi)
    if flo > 0:
        out["note"] = "price is below the value implied by -50% growth"
        return jsonable(out)
    if fhi < 0:
        out["note"] = "price implies more than 150% initial growth"
        return jsonable(out)
    out["implied_growth"] = float(brentq(f, lo, hi, xtol=1e-12, maxiter=200))
    out["note"] = (f"initial FCF growth that, fading linearly to {tg:.1%} over {n} years, justifies the price "
                   f"at a {w:.1%} discount rate")
    return jsonable(out)


def dcf_sensitivity(fcf0: float, growth: float, net_debt: float, shares: float, waccs, tgs, years: int = 10) -> dict:
    """DCF value per share over a grid of discount rates (rows) and terminal growth rates (columns).

    Returns {"waccs", "tgs", "matrix": [[per_share]]}; cells with wacc <= terminal growth are None.
    """
    ws = [clean(w) for w in (waccs or [])]
    ts = [clean(t) for t in (tgs or [])]
    mat = []
    for w in ws:
        row = []
        for t in ts:
            row.append(dcf(fcf0, growth, years, w, t, net_debt, shares)["per_share"] if w is not None and t is not None
                       else None)
        mat.append(row)
    return jsonable({"waccs": ws, "tgs": ts, "matrix": mat})


# =============================================================================== summary
def _fcf0(B: _Book) -> tuple[float | None, str | None]:
    v, end, basis = _ttm_flow(B, "fcf")
    if v is None:
        o, e1, b1 = _ttm_flow(B, "ocf")
        c, e2, b2 = _ttm_flow(B, "capex")
        if o is not None and c is not None and b1 == b2:
            v, end, basis = o + c, e1, b1
    if v is None:
        return None, None
    return v, f"{'ttm (last 4 quarters)' if basis == 'ttm' else 'latest annual'} to {end:%Y-%m-%d}"


def fundamental_summary(stmts: dict, info: dict, rf: float = 0.043, erp: float = 0.055) -> dict:
    """Everything fundamental for one ticker in one call.

    DCF defaults: WACC = rf + beta x erp (CAPM cost of equity used as the discount rate; beta from info,
    1.0 if missing) clamped to [7 %, 14 %]; FCF0 = TTM free cash flow from the last four quarters when
    available, else the latest annual FCF; initial growth = analyst-implied EPS growth (forwardEps /
    trailingEps - 1, both positive), else Yahoo's revenueGrowth, else the latest annual revenue growth,
    clamped to [-10 %, 40 %]; terminal growth 3 %; 10 years; net debt = total debt - cash & short-term
    investments (latest balance); shares = info sharesOutstanding. The sensitivity grid is WACC +/- 2 pp
    (1 pp steps) x terminal growth 2-4 % (0.5 pp steps). With a currency mismatch (ADRs) the DCF is in
    the statement currency and the reverse DCF is skipped.

    Returns {"tables": {"income_a", "balance_a", "cashflow_a", "income_q", "balance_q", "cashflow_q"},
    "derived_q", "derived_a", "piotroski", "altman_z", "valuation", "dcf", "reverse_dcf", "sensitivity",
    "assumptions": {...}, "warnings": [...]}.
    """
    info = info if isinstance(info, dict) else {}
    warns: list[str] = []
    B = _Book(stmts if isinstance(stmts, dict) else {})
    tables = {k: _table(B.frame(k), k.split("_")[0]) for k in KEYS}
    derived_q = derived_metrics(B, info, "q")
    derived_a = derived_metrics(B, info, "a")
    pf = piotroski(B)
    az = altman_z(B, info)
    val = valuation(info, B)
    snap = _snapshot(B, info)

    beta = clean(info.get("beta"))
    if beta is None:
        warns.append("beta missing; 1.0 assumed")
        beta = 1.0
    rf_, erp_ = clean(rf) or 0.0, clean(erp) or 0.0
    wacc = min(max(rf_ + beta * erp_, 0.07), 0.14)
    tg, years = 0.03, 10
    fcf0, fcf_basis = _fcf0(B)
    if fcf0 is None and clean(info.get("freeCashflow")) is not None:
        fcf0, fcf_basis = clean(info.get("freeCashflow")), "info freeCashflow (Yahoo levered FCF)"
    growth, g_src = None, None
    eps_t, eps_f = clean(info.get("trailingEps")), clean(info.get("forwardEps"))
    if eps_t and eps_f and eps_t > 0 and eps_f > 0:
        growth, g_src = eps_f / eps_t - 1.0, "analyst EPS growth (forwardEps / trailingEps - 1)"
    elif clean(info.get("revenueGrowth")) is not None:
        growth, g_src = clean(info.get("revenueGrowth")), "Yahoo revenueGrowth (latest quarter, YoY)"
    elif derived_a["latest"].get("revenue_growth_yoy") is not None:
        growth, g_src = derived_a["latest"]["revenue_growth_yoy"], "latest annual revenue growth"
    else:
        growth, g_src = 0.05, "default 5% (no growth data)"
        warns.append("no growth data; 5% assumed")
    growth_raw = growth
    growth = min(max(growth, -0.10), 0.40)
    debt, cash = snap.get("total_debt"), snap.get("cash_sti")
    net_debt = (debt or 0.0) - (cash or 0.0) if (debt is not None or cash is not None) else 0.0
    shares = clean(info.get("sharesOutstanding")) or clean(info.get("impliedSharesOutstanding")) or snap.get("shares_out")
    price = _price(info)
    mismatch = _currency_mismatch(info)

    if fcf0 is None:
        warns.append("no free cash flow data; DCF unavailable")
        d = dcf(None, growth, years, wacc, tg, net_debt, shares)
        rd = reverse_dcf(price, None, net_debt, shares, wacc, tg, years)
    else:
        d = dcf(fcf0, growth, years, wacc, tg, net_debt, shares)
        if fcf0 <= 0:
            warns.append("negative free cash flow: DCF value not meaningful")
        if mismatch:
            rd = {"implied_growth": None, "wacc": wacc, "terminal_growth": tg, "years": years, "fcf0": fcf0,
                  "note": "statement and quote currencies differ; reverse DCF skipped"}
            warns.append("DCF per-share value is in the statement currency "
                         f"({info.get('financialCurrency')}), not the quote currency")
        else:
            rd = reverse_dcf(price, fcf0, net_debt, shares, wacc, tg, years)
    waccs = [round(wacc + dw, 6) for dw in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    tgs = [0.02, 0.025, 0.03, 0.035, 0.04]
    sens = dcf_sensitivity(fcf0, growth, net_debt, shares, waccs, tgs, years) if fcf0 is not None else \
        jsonable({"waccs": waccs, "tgs": tgs, "matrix": [[None] * len(tgs) for _ in waccs]})
    for part in (val, az, pf):
        for w in part.get("warnings", []):
            if w not in warns:
                warns.append(w)
    assumptions = {"rf": rf_, "erp": erp_, "beta": beta, "wacc": wacc, "wacc_method": "rf + beta * erp, clamped 7-14%",
                   "terminal_growth": tg, "years": years, "growth": growth, "growth_unclamped": growth_raw,
                   "growth_source": g_src, "fcf0": fcf0, "fcf0_basis": fcf_basis, "net_debt": net_debt,
                   "shares": shares, "price": price, "currency": info.get("financialCurrency") or info.get("currency")}
    return jsonable({"tables": tables, "derived_q": derived_q, "derived_a": derived_a, "piotroski": pf,
                     "altman_z": az, "valuation": val, "dcf": d, "reverse_dcf": rd, "sensitivity": sens,
                     "assumptions": assumptions, "warnings": warns})
