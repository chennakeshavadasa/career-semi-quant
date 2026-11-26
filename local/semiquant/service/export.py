"""Exports: Excel workbooks (ticker, screener, portfolio), CSV, and the shareable
snapshot: ONE self-contained HTML file containing the dashboard UI (CSS, fonts, JS,
chart libraries inlined) plus the data of the pages it covers. A friend can open it
in any browser, offline, without installing anything."""
from __future__ import annotations

import base64
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from urllib.parse import quote

import pandas as pd

from .. import __version__, config
from ..analytics._util import clean, jsonable
from ..data import yahoo
from . import market as mkt
from . import screener as scr
from . import ticker as tk
from . import tools

WEB = Path(__file__).resolve().parent.parent / "web"
SNAP_CHART_RANGES = ("1D", "5D", "1M", "10Y", "MAX")  # daily ranges are sliced from 10Y in the browser
SNAP_IND = "sma20,sma50,sma200,ema21,bb,vwap,rsi,macd"


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M")


# ─── Excel helpers ───────────────────────────────────────────────────────────

def _df(rows: list[dict] | None, cols: list[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rows or [])
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    return df


def _write(xw: pd.ExcelWriter, name: str, df: pd.DataFrame | None, index: bool = False, pct_cols: tuple = ()) -> None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return
    name = re.sub(r"[\[\]\*\?/\\:]", "-", name)[:31]
    d = df.copy()
    for c in d.columns:  # Excel cannot store tz-aware datetimes
        if pd.api.types.is_datetime64_any_dtype(d[c]) and getattr(d[c].dt, "tz", None) is not None:
            d[c] = d[c].dt.tz_localize(None)
    if isinstance(d.index, pd.DatetimeIndex) and d.index.tz is not None:
        d.index = d.index.tz_localize(None)
    d.to_excel(xw, sheet_name=name, index=index)
    ws = xw.sheets[name]
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    hdr = Font(bold=True)
    fill = PatternFill("solid", fgColor="EEF1F6")
    for cell in ws[1]:
        cell.font = hdr
        cell.fill = fill
    ws.freeze_panes = "B2" if index or len(d.columns) > 1 else "A2"
    cols = ([d.index.name or ""] if index else []) + [str(c) for c in d.columns]
    for i, c in enumerate(cols, start=1):
        width = min(46, max(10, len(str(c)) + 2, *(len(str(v)) + 2 for v in (d.index if index and i == 1 else d.iloc[:, i - 1 - (1 if index else 0)]).astype(str).head(200))))
        ws.column_dimensions[get_column_letter(i)].width = width
        if str(c) in pct_cols:
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                for cell in row:
                    cell.number_format = "0.00%"


def _kv(d: dict | None) -> pd.DataFrame:
    return pd.DataFrame([{"field": k, "value": v if not isinstance(v, (dict, list)) else json.dumps(v)[:200]}
                         for k, v in (d or {}).items()])


def _safe(fn: Callable, *a, **k):
    try:
        return fn(*a, **k)
    except Exception:  # noqa: BLE001 - one failing section never blocks an export
        return None


# ─── Ticker workbook ─────────────────────────────────────────────────────────

def ticker_xlsx(sym: str) -> tuple[bytes, str]:
    sym = yahoo.norm_symbol(sym)
    buf = io.BytesIO()
    ov = _safe(tk.overview, sym) or {}
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        q = ov.get("quote") or {}
        _write(xw, "Summary", pd.concat([_kv({"symbol": sym, "exported": datetime.now().isoformat(timespec="seconds"),
                                                "source": "Yahoo Finance via semiquant " + __version__}),
                                           _kv(q), _kv(ov.get("key_stats")), _kv({k: v for k, v in (ov.get("profile") or {}).items() if k != "officers"})]))
        px = _safe(yahoo.daily, sym, "max")
        if px is not None:
            _write(xw, "Prices daily", px.rename_axis("date"), index=True)
        r = ov.get("returns") or {}
        if r.get("rows"):
            _write(xw, "Returns", pd.DataFrame([{"series": x["name"], **x["values"]} for x in r["rows"]]), pct_cols=tuple(r.get("horizons", [])))
        risk = _safe(tk.risk, sym) or {}
        stats = []
        for w, v in (risk.get("stats") or {}).items():
            for b, s in (v or {}).items():
                if s:
                    stats.append({"window": w, "benchmark": b.replace("vs_", "").upper(), **s})
        _write(xw, "Risk stats", pd.DataFrame(stats))
        _write(xw, "Drawdowns", _df((risk.get("drawdowns") or {}).get("table")), pct_cols=("depth",))
        mo = risk.get("monthly") or {}
        if mo.get("matrix"):
            _write(xw, "Monthly returns", pd.DataFrame(mo["matrix"], index=mo["years"], columns=mo["months"]).assign(Year=mo["year_total"]),
                   index=True, pct_cols=tuple(mo["months"]) + ("Year",))
        tail = _safe(tk.tail, sym) or {}
        _write(xw, "VaR-ES", _df((tail.get("var_es") or {}).get("table")), pct_cols=("var", "es"))
        _write(xw, "VaR backtests", _df([{k: (v.get("p") if isinstance(v, dict) and "p" in v else v) for k, v in b.items()
                                          if k not in ("series", "exception_dates")} for b in tail.get("backtests") or []]))
        _write(xw, "Stress tests", _df([{**{k: v for k, v in s.items() if k != "bench"}, **(s.get("bench") or {})}
                                        for s in (tail.get("stress") or {}).get("rows") or []]))
        _write(xw, "Shock scenarios", _df((tail.get("shocks") or {}).get("rows")))
        vol = _safe(tk.volatility, sym) or {}
        rv = (vol.get("realized") or {}).get("table") or {}
        _write(xw, "Realized vol", pd.DataFrame(rv).T.rename_axis("estimator"), index=True)
        g = vol.get("garch") or {}
        _write(xw, "GARCH", _kv({**(g.get("params") or {}), **{k: g.get(k) for k in ("model", "persistence", "half_life_days", "long_run_vol", "current_vol", "aic", "bic", "ljung_box_sq_p")}}))
        opt = _safe(tk.options, sym, None, False) or {}
        if opt.get("available"):
            ch = opt.get("chain") or {}
            _write(xw, f"Options {opt.get('expiry')}", _df(ch.get("rows")))
            _write(xw, "Term structure", _df((opt.get("term") or {}).get("rows")))
        st = _safe(yahoo.statements, sym) or {}
        for key, label in (("income_a", "Income annual"), ("income_q", "Income quarterly"), ("balance_a", "Balance annual"),
                           ("balance_q", "Balance quarterly"), ("cashflow_a", "Cash flow annual"), ("cashflow_q", "Cash flow quarterly")):
            df = st.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                d2 = df.copy()
                d2.columns = [pd.Timestamp(c).strftime("%Y-%m-%d") for c in d2.columns]
                _write(xw, label, d2.rename_axis("item"), index=True)
        fu = _safe(tk.fundamentals, sym) or {}
        _write(xw, "Valuation & scores", pd.concat([_kv(fu.get("valuation")), _kv({"piotroski": (fu.get("piotroski") or {}).get("score"),
                                                     "altman_z": (fu.get("altman_z") or {}).get("z")}), _kv(fu.get("dcf")), _kv(fu.get("reverse_dcf"))]))
        an = _safe(tk.analysts, sym) or {}
        _write(xw, "Price targets", _kv(an.get("targets")))
        _write(xw, "EPS estimates", _df(an.get("earnings_estimate")))
        _write(xw, "Revenue estimates", _df(an.get("revenue_estimate")))
        _write(xw, "EPS trend", _df(an.get("eps_trend")))
        _write(xw, "Rating changes", _df(an.get("upgrades")))
        _write(xw, "Earnings history", _df(an.get("history")))
        _write(xw, "Earnings reactions", _df((an.get("event_study") or {}).get("events")), pct_cols=("reaction", "abnormal", "car_0_1", "car_2_20"))
        ow = _safe(tk.ownership, sym) or {}
        _write(xw, "Institutions", _df(ow.get("institutional")))
        _write(xw, "Funds", _df(ow.get("mutualfund")))
        _write(xw, "Insider trades", _df(ow.get("insider_transactions")))
        fa = _safe(tk.factors, sym) or {}
        _write(xw, "Style factors", _df((fa.get("style") or {}).get("factors")))
        _write(xw, "Macro factors", _df((fa.get("macro") or {}).get("factors")))
    return buf.getvalue(), f"{sym}_{_stamp()}.xlsx"


# ─── Screener / portfolio ────────────────────────────────────────────────────

def screener_file(tickers: list[str] | None, fmt: str = "xlsx", name: str | None = None) -> tuple[bytes, str, str]:
    t = scr.table(tickers, name)
    cols = [c["key"] for c in t["columns"]]
    extra = ["momentum", "trend_score", "value", "quality", "growth", "revisions", "analyst", "low_vol"]
    df = pd.DataFrame(t["rows"])
    keep = [c for c in cols + [c for c in extra if c in df.columns] if c in df.columns]
    df = df[keep].rename(columns={c["key"]: c["label"] for c in t["columns"]})
    base = f"screener_{_stamp()}"
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8"), base + ".csv", "text/csv"
    buf = io.BytesIO()
    pct = tuple(c["label"] for c in t["columns"] if c["format"] == "pct")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _write(xw, "Screener", df, pct_cols=pct)
        _write(xw, "About", _kv({"universe": t["name"], "rows": len(df), "exported": datetime.now().isoformat(timespec="seconds"),
                                 "scores": "percentile ranks within the list, 100 = best"}))
    return buf.getvalue(), base + ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def portfolio_xlsx(p: dict) -> tuple[bytes, str]:
    d = tools.portfolio(p)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _write(xw, "Holdings", _df(d.get("rows")), pct_cols=("weight", "day_change_pct", "pnl_pct"))
        r = d.get("risk") or {}
        _write(xw, "Risk", _kv({k: v for k, v in r.items() if k != "holdings"}))
        _write(xw, "Risk by holding", _df(r.get("holdings")), pct_cols=("weight", "risk_contrib"))
        opt = d.get("optimizers") or {}
        if opt:
            w = pd.DataFrame({k: (v or {}).get("weights", {}) for k, v in opt.items()})
            w.insert(0, "current", pd.Series(d.get("weights")))
            _write(xw, "Optimizer weights", w.rename_axis("ticker"), index=True, pct_cols=tuple(w.columns))
        _write(xw, "Stress tests", _df([{**{k: v for k, v in s.items() if k != "bench"}, **(s.get("bench") or {})}
                                        for s in (d.get("stress") or {}).get("rows") or []]))
        bt = d.get("backtest") or {}
        if (bt.get("equity") or {}).get("t"):
            _write(xw, "Backtest", pd.DataFrame({"date": bt["equity"]["t"], "portfolio": bt["equity"]["v"]}))
    return buf.getvalue(), f"portfolio_{_stamp()}.xlsx"


# ─── Shareable snapshot (single HTML file) ───────────────────────────────────

def snap_key(path: str) -> str:
    """Same normalisation as SQ.snapKey in core.js: sorted query parameters, no 'ind'."""
    from urllib.parse import parse_qsl, urlsplit

    u = urlsplit(path)
    qs = sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k != "ind")
    return u.path + ("?" + "&".join(f"{k}={v}" for k, v in qs) if qs else "")


def _inline_css() -> str:
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")

    def font(m: re.Match) -> str:
        p = (WEB / "css" / m.group(1)).resolve()
        try:
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return f'url("data:font/woff2;base64,{b64}")'
        except OSError:
            return m.group(0)
    return re.sub(r'url\("(\.\./fonts/[^"]+)"\)', font, css)


def _script(src: str) -> str:
    if src == "vendor/plotly.min.js":
        import plotly
        text = (Path(plotly.__file__).parent / "package_data" / "plotly.min.js").read_text(encoding="utf-8")
    else:
        text = (WEB / src).read_text(encoding="utf-8")
    return "<script>" + text.replace("</script", "<\\/script") + "</script>"


def snapshot_html(symbols: list[str], include_market: bool = True) -> tuple[str, str]:
    """Build the single-file snapshot for the given tickers (and optionally the market pages)."""
    data: dict[str, Any] = {}
    quotes: dict[str, Any] = {}

    def put(path: str, fn: Callable[[], Any]) -> None:
        try:
            data[snap_key(path)] = jsonable(fn())
        except Exception as exc:  # noqa: BLE001 - keep going: the page shows "not included"
            data[snap_key(path)] = {"error": str(exc)}

    syms = [yahoo.norm_symbol(s) for s in symbols if s][:8]
    t0 = time.time()
    if include_market:
        for path, fn in (("/api/market/strip", mkt.strip), ("/api/market/heatmap", mkt.heatmap), ("/api/market/breadth", mkt.breadth),
                         ("/api/market/movers", mkt.movers), ("/api/market/earnings", lambda: mkt.upcoming_earnings(30)),
                         ("/api/market/news", mkt.market_news), ("/api/screener", lambda: scr.table(None, None)),
                         ("/api/calendar", tools.calendar)):
            put(path, fn)
    for s in syms:
        enc = quote(s, safe="")  # same as the browser's encodeURIComponent for ticker symbols
        put(f"/api/quotes?symbols={s}", lambda s=s: yahoo.quotes([s]))
        put(f"/api/ticker/{enc}/overview", lambda s=s: tk.overview(s))
        for rng in SNAP_CHART_RANGES:
            put(f"/api/ticker/{enc}/chart?range={rng}", lambda s=s, rng=rng: tk.chart(s, rng, SNAP_IND.split(",")))
        for tab, fn in (("risk", tk.risk), ("volatility", tk.volatility), ("tail", tk.tail), ("options", tk.options),
                        ("fundamentals", tk.fundamentals), ("analysts", tk.analysts), ("ownership", tk.ownership),
                        ("factors", tk.factors), ("events", tk.events)):
            put(f"/api/ticker/{enc}/{tab}", lambda s=s, fn=fn: fn(s))
        put(f"/api/ticker/{enc}/news?count=40", lambda s=s: tk.news(s, 40))
    all_syms = set(syms)
    strip = data.get(snap_key("/api/market/strip")) or {}
    for g in (strip.get("groups") or {}).values():
        for r in g:
            all_syms.add(r["symbol"])
    quotes = jsonable(yahoo.quotes(sorted(all_syms))) if all_syms else {}
    data[snap_key("/api/settings")] = config.settings()
    data[snap_key("/api/watchlists")] = {"Snapshot": syms or ["SPY"]}
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = {"created": created, "version": __version__, "home": (f"t/{syms[0]}" if syms and not include_market else "market"),
            "symbols": syms, "data": data, "quotes": quotes, "build_seconds": round(time.time() - t0, 1)}

    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="css/app.css">', "<style>" + _inline_css() + "</style>")
    html = re.sub(r'<script src="([^"]+)"></script>', lambda m: _script(m.group(1)), html)
    payload = json.dumps(snap, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    html = html.replace("<!--SNAPSHOT-->", "<script>window.SQ_SNAPSHOT=" + payload + ";</script>", 1)
    title = ", ".join(syms) if syms else "Market"
    html = re.sub(r"<title>.*?</title>", f"<title>{title} · Semi Quant snapshot {created[:10]}</title>", html, count=1)
    name = f"semiquant_{'_'.join(syms) if syms else 'market'}_{_stamp()}.html"
    return html, name


def save(data: bytes | str, name: str, out: str | None = None) -> Path:
    """Write an export to ``out`` (file or folder) or ~/.semiquant/exports."""
    config.ensure_dirs()
    p = Path(out).expanduser() if out else config.EXPORT_DIR / name
    if p.is_dir():
        p = p / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_bytes(data)
    return p
