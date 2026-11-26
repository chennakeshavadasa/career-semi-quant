"""Tests for semiquant.analytics.fundamentals (hand-checked ratios, DCF maths, real NVDA / INTC data)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from semiquant.analytics import fundamentals as F

M = 1e6


def dumps(obj):
    return json.dumps(obj, allow_nan=False)


def col(result: dict, name: str) -> dict:
    """metric name -> {period: value} from a derived_metrics result."""
    return dict(zip(result["periods"], result["metrics"][name]))


# ------------------------------------------------------------------ statement tables
def test_statement_table_curated(nvda_statements):
    tb = F.statement_table(nvda_statements["income_a"], "income")
    dumps(tb)
    # 2022-01-31 has no revenue (yfinance padding column) and is dropped; oldest -> newest
    assert tb["periods"] == ["2023-01-31", "2024-01-31", "2025-01-31", "2026-01-31"]
    rows = {r["item"]: r for r in tb["rows"]}
    assert rows["Total Revenue"]["values"] == [26974 * M, 60922 * M, 130497 * M, 215938 * M]
    assert rows["Net Income"]["source"] == "Net Income Common Stockholders"
    assert {"Gross Profit", "Operating Income", "EBITDA", "Diluted EPS"} <= set(rows)
    bal = F.statement_table(nvda_statements["balance_q"], "balance")
    assert "Total Liabilities" in {r["item"] for r in bal["rows"]}
    cf = F.statement_table(nvda_statements["cashflow_q"], "cashflow")
    assert {"Free Cash Flow", "Share Repurchases", "Capital Expenditure"} <= {r["item"] for r in cf["rows"]}
    assert all(len(r["values"]) == len(cf["periods"]) for r in cf["rows"])


def test_statement_table_unrecognised_and_empty(nvda_statements):
    raw = nvda_statements["income_a"]
    tb = F.statement_table(raw, "segments")
    assert len(tb["rows"]) == raw.shape[0] and tb["rows"][0]["item"] == raw.index[0]
    weird = pd.DataFrame({pd.Timestamp("2025-12-31"): [1.0, 2.0]}, index=["Widgets", "Gadgets"])
    tb2 = F.statement_table(weird, "income")
    assert [r["item"] for r in tb2["rows"]] == ["Widgets", "Gadgets"]
    assert F.statement_table(None, "income") == {"kind": "income", "periods": [], "rows": []}
    assert F.statement_table(pd.DataFrame(), "balance")["rows"] == []


# ------------------------------------------------------------------ derived metrics
def test_derived_metrics_hand_checked(nvda_statements, nvda_info):
    a = F.derived_metrics(nvda_statements, nvda_info, "a")
    dumps(a)
    p = "2026-01-31"
    assert col(a, "gross_margin")[p] == pytest.approx(153463 / 215938)
    assert col(a, "revenue_growth_yoy")[p] == pytest.approx(215938 / 130497 - 1)
    assert col(a, "current_ratio")[p] == pytest.approx(125605 / 32163)
    assert col(a, "roe")[p] == pytest.approx(120067 / ((157293 + 79327) / 2))
    assert col(a, "debt_to_equity")[p] == pytest.approx(11040 / 157293)
    assert col(a, "fcf_conversion")[p] == pytest.approx(96676 / 120067)
    assert col(a, "inventory_days")[p] == pytest.approx(21403 / 62475 * 365)
    assert col(a, "share_change_yoy")[p] == pytest.approx(24514 / 24804 - 1)
    tax = 0.15117
    assert col(a, "roic")[p] == pytest.approx(141709 * (1 - tax) / ((165761 + 87790) / 2))
    assert a["latest"]["gross_margin"] == pytest.approx(153463 / 215938) and a["latest_period"]["gross_margin"] == p
    q = F.derived_metrics(nvda_statements, nvda_info, "q")
    dumps(q)
    pq = "2026-07-31"
    # quarterly flows x4 against average balances
    assert col(q, "roe")[pq] == pytest.approx(59688 * 4 / ((228984 + 195474) / 2))
    assert col(q, "dso")[pq] == pytest.approx(63059 / (96221 * 4) * 365)
    assert col(q, "revenue_growth_yoy")[pq] == pytest.approx(96221 / 46743 - 1)   # same quarter a year earlier
    assert col(q, "revenue_growth_yoy")["2026-04-30"] is None                      # no year-ago quarter
    assert set(q["metrics"]) == {"revenue_growth_yoy", "gross_margin", "operating_margin", "net_margin", "fcf_margin",
                                 "rnd_pct_revenue", "sbc_pct_revenue", "capex_pct_revenue", "roe", "roa", "roic",
                                 "asset_turnover", "inventory_days", "dso", "current_ratio", "quick_ratio",
                                 "debt_to_equity", "net_debt_to_ebitda", "interest_coverage", "fcf_conversion",
                                 "share_change_yoy"}


def test_derived_metrics_loss_maker(intc_statements, intc_info):
    a = F.derived_metrics(intc_statements, intc_info, "a")
    dumps(a)
    p = "2025-12-31"
    assert col(a, "net_margin")[p] == pytest.approx(-267 / 52853)
    assert col(a, "fcf_margin")[p] == pytest.approx(-4949 / 52853)
    assert col(a, "fcf_conversion")[p] is None                    # undefined for a net loss
    assert col(a, "roe")["2024-12-31"] < 0


# ------------------------------------------------------------------ Piotroski / Altman
def test_piotroski(nvda_statements, intc_statements):
    for st in (nvda_statements, intc_statements):
        pf = F.piotroski(st)
        dumps(pf)
        assert pf["max"] == 9 and len(pf["criteria"]) == 9 and 0 <= pf["score"] <= 9
        assert pf["score"] == sum(c["pass"] is True for c in pf["criteria"])
    pf = {c["name"]: c for c in F.piotroski(nvda_statements)["criteria"]}
    assert pf["roa_positive"]["pass"] is True and pf["roa_positive"]["value"] == pytest.approx(120067 / 111601)
    assert pf["no_dilution"]["pass"] is True and pf["no_dilution"]["value"] == 24304 * M
    assert pf["accruals"]["pass"] is False                         # FY26 CFO 102.7bn < net income 120.1bn
    assert pf["gross_margin_rising"]["pass"] is False
    intc = {c["name"]: c for c in F.piotroski(intc_statements)["criteria"]}
    assert intc["roa_positive"]["pass"] is False and intc["no_dilution"]["pass"] is False
    assert F.piotroski({})["n_available"] == 0


def test_altman_z(nvda_statements, nvda_info, intc_statements, intc_info):
    for st, info in ((nvda_statements, nvda_info), (intc_statements, intc_info)):
        az = F.altman_z(st, info)
        dumps(az)
        c = az["components"]
        z = (1.2 * c["working_capital_to_assets"] + 1.4 * c["retained_earnings_to_assets"] + 3.3 * c["ebit_to_assets"]
             + 0.6 * c["market_equity_to_liabilities"] + 1.0 * c["sales_to_assets"])
        assert az["z"] == pytest.approx(z) and az["basis"] == "ttm"
        assert az["zone"] == ("safe" if z > 2.99 else "grey" if z >= 1.81 else "distress")
    nv = F.altman_z(nvda_statements, nvda_info)
    assert nv["zone"] == "safe"
    # latest quarterly balance (2026-07-31): market cap / total liabilities
    assert nv["components"]["market_equity_to_liabilities"] == pytest.approx(nvda_info["marketCap"] / (91288 * M))
    adr = F.altman_z(nvda_statements, {**nvda_info, "financialCurrency": "TWD"})
    assert adr["z"] is None and adr["z_double_prime"] is not None and adr["warnings"]


# ------------------------------------------------------------------ valuation
def test_valuation_nvda(nvda_statements, nvda_info):
    v = F.valuation(nvda_info, nvda_statements)
    dumps(v)
    assert v["dividend_yield"] == pytest.approx(0.0067)            # info 0.67 is percent
    assert v["pe_ttm"] == pytest.approx(nvda_info["trailingPE"]) and v["peg"] == pytest.approx(0.19)
    # info reports a newer quarter than the statements -> Yahoo TTM aggregates are used (and flagged)
    assert v["ps"] == pytest.approx(nvda_info["marketCap"] / nvda_info["totalRevenue"])
    assert v["sources"]["revenue"] == "info" and any("newer quarter" in w for w in v["warnings"])
    ev = nvda_info["marketCap"] + nvda_info["totalDebt"] - nvda_info["totalCash"]
    assert v["enterprise_value"] == pytest.approx(ev)
    assert v["ev_ebitda"] == pytest.approx(ev / nvda_info["ebitda"])
    assert v["earnings_yield"] == pytest.approx(9.31 / 149.3)
    assert v["buyback_yield"] > 0 and v["shareholder_yield"] == pytest.approx(v["dividend_yield"] + v["buyback_yield"])
    for k in ("market_cap", "enterprise_value", "pe_ttm", "pe_fwd", "peg", "ps", "ev_sales", "ev_ebitda", "ev_ebit",
              "p_fcf", "fcf_yield", "earnings_yield", "pb", "dividend_yield", "buyback_yield", "shareholder_yield"):
        assert k in v


def test_valuation_loss_maker_and_adr(intc_statements, intc_info, nvda_statements, nvda_info):
    v = F.valuation(intc_info, intc_statements)
    dumps(v)
    assert v["pe_ttm"] is None and v["earnings_yield"] == pytest.approx(-2.35 / 54.47)
    assert v["ev_ebit"] is None                                    # negative TTM EBIT
    assert v["ps"] == pytest.approx(intc_info["marketCap"] / ((13674 + 13577 + 16128 + 16513) * M))
    assert v["fcf_yield"] == pytest.approx((800 - 2540 + 4450 + 1058) * M / intc_info["marketCap"])
    assert v["dividend_yield"] == 0.0 and v["sources"]["revenue"] == "statements_ttm"
    adr = F.valuation({**nvda_info, "financialCurrency": "TWD"}, nvda_statements)
    assert adr["ps"] is None and adr["ev_sales"] is None and adr["pb"] is None and adr["enterprise_value"] is None
    assert adr["pe_ttm"] is not None and any("currency" in w for w in adr["warnings"])
    # dividendYield convention cross-check
    assert F._dividend_yield({"dividendYield": 0.0067, "dividendRate": 1.0}, 149.3)[0] == pytest.approx(0.0067)
    assert F._dividend_yield({"dividendYield": 0.67, "dividendRate": 1.0}, 149.3)[0] == pytest.approx(0.0067)
    assert F._dividend_yield({"trailingAnnualDividendYield": 0.012}, 50.0)[0] == pytest.approx(0.012)


# ------------------------------------------------------------------ DCF
def test_dcf_hand_calculation():
    d = F.dcf(100.0, 0.10, years=3, wacc=0.10, terminal_growth=0.02, net_debt=50.0, shares=10.0)
    dumps(d)
    g = [0.10, 0.06, 0.02]                                       # linear fade over three years
    fcf = [100 * 1.10, 100 * 1.10 * 1.06, 100 * 1.10 * 1.06 * 1.02]
    pv = [fcf[0] / 1.1, fcf[1] / 1.1 ** 2, fcf[2] / 1.1 ** 3]
    tv = fcf[2] * 1.02 / (0.10 - 0.02)
    ev = sum(pv) + tv / 1.1 ** 3
    assert d["growth_path"] == pytest.approx(g)
    assert d["fcf"] == pytest.approx(fcf) and d["pv_fcf"] == pytest.approx(pv)
    assert d["terminal_value"] == pytest.approx(tv) and d["pv_terminal"] == pytest.approx(tv / 1.1 ** 3)
    assert d["enterprise_value"] == pytest.approx(ev) and d["equity_value"] == pytest.approx(ev - 50)
    assert d["per_share"] == pytest.approx((ev - 50) / 10) and d["terminal_share"] == pytest.approx(tv / 1.1 ** 3 / ev)
    bad = F.dcf(100.0, 0.1, wacc=0.02, terminal_growth=0.03)
    assert bad["per_share"] is None and bad["warnings"]


def test_reverse_dcf_inverts_dcf():
    for g in (-0.05, 0.08, 0.35, 1.2):
        price = F.dcf(5e9, g, 10, 0.095, 0.025, 2e9, 1e9)["per_share"]
        r = F.reverse_dcf(price, 5e9, 2e9, 1e9, 0.095, 0.025, 10)
        dumps(r)
        assert r["implied_growth"] == pytest.approx(g, abs=1e-8)
    assert F.reverse_dcf(100.0, -1e9, 0.0, 1e9)["implied_growth"] is None
    assert "negative" in F.reverse_dcf(100.0, -1e9, 0.0, 1e9)["note"]
    assert F.reverse_dcf(100.0, None, 0.0, 1e9)["implied_growth"] is None
    assert F.reverse_dcf(1e6, 1e9, 0.0, 1e9)["implied_growth"] is None        # beyond +150 %


def test_dcf_sensitivity():
    s = F.dcf_sensitivity(1e9, 0.1, 0.0, 1e8, [0.08, 0.10, 0.12], [0.02, 0.03, 0.09])
    dumps(s)
    m = np.array([[np.nan if v is None else v for v in row] for row in s["matrix"]])
    assert m.shape == (3, 3)
    assert np.all(np.diff(m[:, 0]) < 0) and np.all(np.diff(m[0, :2]) > 0)   # value falls with WACC, rises with g
    assert s["matrix"][0][2] is None                                        # wacc 8 % <= g 9 %
    assert m[1, 1] == pytest.approx(F.dcf(1e9, 0.1, 10, 0.10, 0.03, 0.0, 1e8)["per_share"])


# ------------------------------------------------------------------ summary + robustness
@pytest.mark.parametrize("which", ["nvda", "intc"])
def test_fundamental_summary(which, nvda_statements, nvda_info, intc_statements, intc_info):
    st, info = (nvda_statements, nvda_info) if which == "nvda" else (intc_statements, intc_info)
    s = F.fundamental_summary(st, info)
    dumps(s)
    assert set(s) >= {"tables", "derived_q", "derived_a", "piotroski", "altman_z", "valuation", "dcf", "reverse_dcf",
                      "sensitivity", "assumptions", "warnings"}
    assert set(s["tables"]) == {"income_a", "balance_a", "cashflow_a", "income_q", "balance_q", "cashflow_q"}
    a = s["assumptions"]
    assert 0.07 <= a["wacc"] <= 0.14 and -0.10 <= a["growth"] <= 0.40
    assert a["wacc"] == pytest.approx(min(max(0.043 + info["beta"] * 0.055, 0.07), 0.14))
    assert a["fcf0_basis"].startswith("ttm")
    assert s["dcf"]["per_share"] is not None and s["reverse_dcf"]["implied_growth"] is not None
    assert len(s["sensitivity"]["matrix"]) == 5 and len(s["sensitivity"]["matrix"][0]) == 5
    if which == "nvda":
        assert a["fcf0"] == pytest.approx((22115 + 34904 + 48587 + 21400) * M)
        assert a["growth"] == 0.40 and a["growth_unclamped"] > 0.4
    else:
        assert a["fcf0"] == pytest.approx((800 - 2540 + 4450 + 1058) * M)
        assert a["growth"] == pytest.approx(0.209)


def test_missing_rows_and_empty_inputs(nvda_statements, nvda_info):
    drop = ["Free Cash Flow", "Total Revenue", "Operating Revenue", "Total Debt", "EBIT", "Retained Earnings",
            "Stockholders Equity", "Common Stock Equity"]
    st = {k: v.drop(index=[r for r in drop if r in v.index]) for k, v in nvda_statements.items()}
    s = F.fundamental_summary(st, nvda_info)
    dumps(s)
    assert s["derived_a"]["latest"]["gross_margin"] is None and s["altman_z"]["z"] is None
    assert s["dcf"]["per_share"] is not None                       # FCF rebuilt from OCF + capex
    for stmts, info in (({}, {}), (None, None), ({"income_a": pd.DataFrame()}, {"marketCap": 1e9})):
        e = F.fundamental_summary(stmts, info)
        dumps(e)
        assert e["dcf"]["per_share"] is None and e["reverse_dcf"]["implied_growth"] is None
        assert e["piotroski"]["score"] == 0 and e["altman_z"]["z"] is None and e["warnings"]
    neg = F.dcf(-1e9, 0.1, shares=1e6)
    assert neg["warnings"] and neg["per_share"] < 0
