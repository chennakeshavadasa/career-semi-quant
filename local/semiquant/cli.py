"""Command line: ``semiquant`` opens the dashboard; subcommands give quick answers in the terminal.

    semiquant                         start the local dashboard and open the browser
    semiquant quote NVDA AMD TSM      live quotes
    semiquant watch [--list NAME]     live-updating quote board (Ctrl-C to stop)
    semiquant analyze NVDA            one-page tear sheet in the terminal
    semiquant options NVDA            implied vol, skew, expected move, chain near the money
    semiquant screen -u us_large      rank a universe: semis, us_large, global, etfs (or --list)
    semiquant market                  indices, rates, FX, commodities, VIX curve
    semiquant offer NVDA --value 100000 --years 4    value an RSU grant
    semiquant report NVDA AMD         shareable single-file HTML snapshot (send it to anyone)
    semiquant export NVDA             Excel workbook with everything
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
import webbrowser

from . import APP_NAME, __version__


def _console():
    from rich.console import Console
    return Console(highlight=False)


def _pct(x, d=2, sign=True):
    if x is None:
        return "[dim]–[/]"
    color = "green" if x > 0 else "red" if x < 0 else "white"
    return f"[{color}]{'+' if sign and x > 0 else ''}{x * 100:.{d}f}%[/]"


def _num(x, d=2):
    return "[dim]–[/]" if x is None else f"{x:,.{d}f}"


def _big(x):
    if x is None:
        return "[dim]–[/]"
    a = abs(x)
    for div, s in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{x / div:,.2f}{s}"
    return f"{x:,.0f}"


def _syms(args_syms):
    return [s.upper() for s in args_syms]


# ─── serve ───────────────────────────────────────────────────────────────────

def cmd_serve(a) -> None:
    import uvicorn

    from .server.app import create_app

    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '127.0.0.1') else a.host}:{a.port}/"
    c = _console()
    c.print(f"[bold]{APP_NAME}[/] {__version__} · local edition")
    c.print(f"Dashboard: [link={url}]{url}[/link]   (Ctrl-C to stop)")
    c.print("[dim]Data: Yahoo Finance via yfinance. Everything runs on this computer.[/]")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host=a.host, port=a.port, log_level="warning")


# ─── quote / watch ───────────────────────────────────────────────────────────

def _quote_table(qs: dict, order: list[str]):
    from rich.table import Table

    t = Table(box=None, header_style="dim", pad_edge=False)
    for col, j in (("Symbol", "left"), ("Name", "left"), ("Price", "right"), ("Change", "right"), ("%", "right"),
                   ("Ext. hours", "right"), ("Day range", "right"), ("52W pos", "right"), ("Volume", "right"),
                   ("Mkt cap", "right"), ("P/E fwd", "right"), ("State", "left")):
        t.add_column(col, justify=j, no_wrap=True)
    for s in order:
        q = qs.get(s)
        if not q:
            t.add_row(f"[cyan]{s}[/]", "[dim]no data[/]", *[""] * 10)
            continue
        ext = f"{_num(q.get('ext_price'))} {_pct(q.get('ext_change_pct'))}" if q.get("ext_price") else ""
        rng = f"{_num(q.get('low'))}–{_num(q.get('high'))}" if q.get("low") else ""
        pos = q.get("pos_52w")
        t.add_row(f"[cyan]{s}[/]", (q.get("name") or "")[:26], _num(q.get("price")), _num(q.get("change")),
                  _pct(q.get("change_pct")), ext, rng, f"{pos * 100:.0f}%" if pos is not None else "–", _big(q.get("volume")),
                  _big(q.get("market_cap")), _num(q.get("fpe"), 1), (q.get("market_state") or "").lower())
    return t


def cmd_quote(a) -> None:
    from .data import yahoo

    syms = _syms(a.symbols)
    _console().print(_quote_table(yahoo.quotes(syms), syms))


def cmd_watch(a) -> None:
    from rich.live import Live

    from . import config
    from .data import yahoo

    syms = _syms(a.symbols) or config.watchlists().get(a.list or "My watchlist") or ["NVDA", "AMD", "SPY"]
    c = _console()
    every = max(5, a.every)
    try:
        with Live(console=c, refresh_per_second=2, screen=False) as live:
            while True:
                qs = yahoo.quotes(syms, ttl=every - 1)
                from rich.panel import Panel
                live.update(Panel(_quote_table(qs, syms), title=f"{APP_NAME} · live · refresh {every}s · {time.strftime('%H:%M:%S')}",
                                  border_style="blue"))
                time.sleep(every)
    except KeyboardInterrupt:
        pass


# ─── analyze ─────────────────────────────────────────────────────────────────

def cmd_analyze(a) -> None:
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.table import Table

    from .service import ticker as tk

    c = _console()
    sym = a.symbol.upper()
    with c.status(f"Analyzing {sym}…"):
        ov = tk.overview(sym)
        ov["score"] = (tk.score(sym) or {}).get("score")
        risk = tk.risk(sym)
        opt = tk.options(sym, None, False)
    q, ks, pr = ov["quote"], ov.get("key_stats") or {}, ov.get("profile") or {}
    head = (f"[bold]{pr.get('name') or q.get('name')}[/] ({sym}) · {q.get('exchange') or ''} · {q.get('currency') or ''}\n"
            f"[bold]{_num(q.get('price'))}[/]  {_num(q.get('change'))}  {_pct(q.get('change_pct'))}"
            + (f"   {q.get('ext_label')}: {_num(q.get('ext_price'))} {_pct(q.get('ext_change_pct'))}" if q.get("ext_price") else ""))
    c.print(Panel(head, border_style="blue"))
    r = ov.get("returns") or {}
    if r.get("rows"):
        t = Table(title="Returns", box=None, header_style="dim")
        t.add_column("")
        for hz in r["horizons"]:
            t.add_column(hz + ("*" if hz in r.get("annualized", []) else ""), justify="right")
        for row in r["rows"]:
            t.add_row(sym if row["name"] == "Asset" else row["name"], *[_pct(row["values"].get(hz), 1) for hz in r["horizons"]])
        c.print(t)
        c.print("[dim]* annualised[/]")
    s3 = ((risk.get("stats") or {}).get("3Y") or {}).get("vs_spy") or {}
    sig = ov.get("signals") or {}
    sc = ov.get("score") or {}

    def kv(title, rows):
        t = Table(title=title, box=None, show_header=False, title_justify="left")
        t.add_column(style="dim")
        t.add_column(justify="right")
        for k, v in rows:
            t.add_row(k, v)
        return t

    blocks = [
        kv("Risk (3Y vs S&P 500)", [("CAGR", _pct(s3.get("cagr"), 1)), ("Volatility", _pct(s3.get("vol"), 1, False)),
                                    ("Sharpe", _num(s3.get("sharpe"))), ("Max drawdown", _pct(s3.get("max_drawdown"), 1)),
                                    ("Beta", _num(s3.get("beta"))), ("Alpha (ann.)", _pct(s3.get("alpha"), 1)),
                                    ("VaR 95% 1d", _pct(s3.get("var95"), 2, False))]),
        kv("Valuation", [("Market cap", _big(ks.get("market_cap"))), ("P/E / fwd", f"{_num(ks.get('pe'), 1)} / {_num(ks.get('fpe'), 1)}"),
                         ("EV/EBITDA", _num(ks.get("ev_ebitda"), 1)), ("Gross margin", _pct(ks.get("gross_margin"), 1, False)),
                         ("Rev growth", _pct(ks.get("revenue_growth"), 1)), ("Short % float", _pct(ks.get("short_pct_float"), 1, False))]),
        kv("Signals", [("Quant score", f"{sc.get('score', 0):.0f}/100 (rank {sc.get('rank')}/{sc.get('of')})" if sc.get("score") is not None else "–"),
                       ("Technical rating", sig.get("rating") or "–"),
                       ("Analyst target", f"{_num(ks.get('target_mean'))} ({_pct(ks.get('upside'), 1)})"),
                       ("Recommendation", (ks.get("rec_key") or "–").replace("_", " ")),
                       ("Options ATM IV 30d", _pct(opt.get("atm_iv_30d"), 1, False) if opt.get("available") else "–"),
                       ("Implied move", "±" + _pct(((opt.get("chain") or {}).get("implied_move")), 1, False).replace("[green]", "").replace("[/]", "") if opt.get("available") else "–")]),
    ]
    c.print(Columns(blocks, padding=(0, 6)))
    if ov.get("news"):
        c.print("\n[bold]Latest news[/]")
        for n in ov["news"][:6]:
            c.print(f"  • {n['title']} [dim]({n.get('publisher')}, {(n.get('time') or '')[:10]})[/]")
    c.print(f"\n[dim]Full interactive view: semiquant  →  search {sym}   ·   share: semiquant report {sym}[/]")


# ─── options ─────────────────────────────────────────────────────────────────

def cmd_options(a) -> None:
    from rich.table import Table

    from .service import ticker as tk

    c = _console()
    sym = a.symbol.upper()
    with c.status(f"Loading {sym} options…"):
        d = tk.options(sym, a.expiry, False)
    if not d.get("available"):
        c.print(d.get("message"))
        return
    ch = d.get("chain") or {}
    pc = ch.get("put_call") or {}
    sk = ch.get("skew") or {}
    c.print(f"[bold]{sym}[/] spot {_num(d['spot'])} · expiry {d['expiry']} ({ch.get('dte')}d) · ATM IV {_pct(ch.get('atm_iv'), 1, False)}"
            f" · 30d IV {_pct(d.get('atm_iv_30d'), 1, False)} vs realized {_pct(d.get('rv_21d'), 1, False)}")
    c.print(f"Implied move ±{(ch.get('implied_move') or 0) * 100:.1f}% · put/call OI {_num(pc.get('oi_ratio'))} · max pain {_num(ch.get('max_pain'))}"
            f" · 25Δ RR {_pct(sk.get('rr25'), 1)} · net GEX {_big((ch.get('gex') or {}).get('total'))}")
    t = Table(box=None, header_style="dim")
    for col in ("C OI", "C IV", "C Δ", "C bid", "C ask", "Strike", "P bid", "P ask", "P Δ", "P IV", "P OI"):
        t.add_column(col, justify="right")
    spot = d["spot"]
    rows = [r for r in ch.get("rows") or [] if abs(r["strike"] / spot - 1) < a.width]
    for r in rows:
        atm = abs(r["strike"] - (ch.get("atm_strike") or 0)) < 1e-9
        t.add_row(_big(r.get("call_oi")), _pct(r.get("call_iv"), 0, False), _num(r.get("call_delta")), _num(r.get("call_bid")),
                  _num(r.get("call_ask")), f"[bold]{r['strike']:,.2f}[/]" if atm else f"{r['strike']:,.2f}", _num(r.get("put_bid")),
                  _num(r.get("put_ask")), _num(r.get("put_delta")), _pct(r.get("put_iv"), 0, False), _big(r.get("put_oi")))
    c.print(t)
    c.print("[dim]Expiries: " + ", ".join(f"{e['expiry']}({e['dte']}d)" for e in d["expiries"][:14]) + "[/]")


# ─── screen / market ─────────────────────────────────────────────────────────

def cmd_screen(a) -> None:
    from rich.table import Table

    from . import config
    from .service import screener as scr

    c = _console()
    tick = config.watchlists().get(a.list) if a.list else None
    with c.status("Scoring the universe (first run fetches fundamentals: ~10-60 s)…"):
        d = scr.table(tick, a.list, a.universe)
    rows = sorted(d["rows"], key=lambda r: (r.get(a.sort) is None, -(r.get(a.sort) or 0) if not a.asc else (r.get(a.sort) or 0)))
    t = Table(title=f"{d['name']} · sorted by {a.sort}", box=None, header_style="dim")
    cols = [("ticker", "Ticker"), ("name", "Name"), ("score", "Score"), ("change_pct", "Day"), ("ret_1m", "1M"), ("ret_ytd", "YTD"),
            ("ret_1y", "1Y"), ("fpe", "Fwd P/E"), ("target_upside", "Upside"), ("vol_3m", "Vol 3M"), ("rsi14", "RSI"), ("trend", "Trend")]
    for k, lbl in cols:
        t.add_column(lbl, justify="left" if k in ("ticker", "name", "trend") else "right", no_wrap=True)
    for r in rows[: a.top]:
        cells = []
        for k, _ in cols:
            v = r.get(k)
            if k == "ticker":
                cells.append(f"[cyan]{v}[/]")
            elif k == "name":
                cells.append((v or "")[:24])
            elif k in ("change_pct", "ret_1m", "ret_ytd", "ret_1y", "target_upside"):
                cells.append(_pct(v, 1))
            elif k == "vol_3m":
                cells.append(_pct(v, 0, False))
            elif k == "score":
                cells.append("–" if v is None else f"[{'green' if v >= 67 else 'yellow' if v >= 40 else 'red'}]{v:.0f}[/]")
            elif k in ("fpe", "rsi14"):
                cells.append(_num(v, 1))
            else:
                cells.append(str(v or "–"))
        t.add_row(*cells)
    c.print(t)


def cmd_market(a) -> None:
    from rich.columns import Columns
    from rich.table import Table

    from .service import market as mkt

    c = _console()
    with c.status("Loading markets…"):
        s = mkt.strip()
    tables = []
    for g, rows in s["groups"].items():
        t = Table(title=g, box=None, show_header=False, title_justify="left")
        t.add_column()
        t.add_column(justify="right")
        t.add_column(justify="right")
        for r in rows:
            t.add_row(r["label"], _num(r.get("price")), _pct(r.get("change_pct")))
        tables.append(t)
    c.print(Columns(tables, padding=(0, 4)))
    st = s.get("status") or {}
    c.print(f"[dim]{st.get('message') or ''} · VIX/VIX3M {_num(s.get('vix_ratio'))} · 10Y-3M {_num(s.get('spread_10y_3m'))} pp[/]")


# ─── offer / exports ─────────────────────────────────────────────────────────

def cmd_offer(a) -> None:
    from rich.table import Table

    from .service import ticker as tk

    c = _console()
    p = {"ticker": a.symbol, "kind": "option" if a.strike else "rsu", "grant_value": a.value, "units": a.units, "strike": a.strike,
         "years": a.years, "cliff_months": a.cliff, "frequency": a.frequency, "method": a.method, "drift": a.drift}
    with c.status("Simulating 10,000 price paths…"):
        d = tk.offer(p)
    r, tot = d["result"], d["result"].get("total") or {}
    c.print(f"[bold]{d['context']['ticker']}[/] {p['kind'].upper()} grant · model {a.method}, drift {a.drift}")
    c.print(f"Expected total {_big(tot.get('mean'))} · median {_big(tot.get('p50'))} · 5%-95% {_big(tot.get('p5'))}–{_big(tot.get('p95'))}"
            + (f" · P(below grant) {(tot.get('prob_below_grant_value') or 0) * 100:.0f}%" if p["kind"] == "rsu" else ""))
    t = Table(box=None, header_style="dim")
    for col in ("Vest date", "Share", "Median", "P5", "P95"):
        t.add_column(col, justify="right")
    for v in r.get("vests") or []:
        t.add_row(v["date"], f"{v['fraction'] * 100:.1f}%", _big(v.get("p50")), _big(v.get("p5")), _big(v.get("p95")))
    c.print(t)


def cmd_report(a) -> None:
    from .service import export

    c = _console()
    syms = _syms(a.symbols)
    with c.status("Building the shareable snapshot (all tabs, ~10-40 s per ticker)…"):
        html, name = export.snapshot_html(syms, include_market=a.market or not syms)
        p = export.save(html, name, a.out)
    c.print(f"Saved [bold]{p}[/] ({p.stat().st_size / 1e6:.1f} MB). Send this one file to anyone: it opens in any browser, offline.")
    if not a.no_open:
        webbrowser.open(p.resolve().as_uri())


def cmd_export(a) -> None:
    from .service import export

    c = _console()
    sym = a.symbol.upper()
    with c.status(f"Building the {sym} workbook…"):
        data, name = export.ticker_xlsx(sym)
        p = export.save(data, name, a.out)
    c.print(f"Saved [bold]{p}[/]")


# ─── main ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="semiquant", description=f"{APP_NAME} (local edition): live Yahoo Finance data and quant analytics.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 2)[2])
    ap.add_argument("--version", action="version", version=f"semiquant {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="start the dashboard (default command)")
    s.add_argument("--port", type=int, default=int(os.environ.get("SEMIQUANT_PORT", 8050)))
    s.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it to your local network")
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("quote", help="live quotes")
    s.add_argument("symbols", nargs="+")
    s.set_defaults(fn=cmd_quote)

    s = sub.add_parser("watch", help="live-updating quote board")
    s.add_argument("symbols", nargs="*")
    s.add_argument("--list", help="watchlist name (default: My watchlist)")
    s.add_argument("--every", type=int, default=30, help="refresh seconds (default 30)")
    s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("analyze", help="tear sheet for one ticker")
    s.add_argument("symbol")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("options", help="options analytics for one ticker")
    s.add_argument("symbol")
    s.add_argument("--expiry")
    s.add_argument("--width", type=float, default=0.12, help="show strikes within ±width of spot (default 0.12)")
    s.set_defaults(fn=cmd_options)

    s = sub.add_parser("screen", help="rank a universe or a watchlist")
    s.add_argument("--universe", "-u", default="semis", choices=["semis", "us_large", "global", "etfs"],
                   help="semis (default), us_large (all sectors), global, etfs")
    s.add_argument("--list", help="a saved watchlist instead of a universe")
    s.add_argument("--sort", default="score")
    s.add_argument("--asc", action="store_true")
    s.add_argument("--top", type=int, default=30)
    s.set_defaults(fn=cmd_screen)

    s = sub.add_parser("market", help="global market snapshot")
    s.set_defaults(fn=cmd_market)

    s = sub.add_parser("offer", help="value an RSU or stock-option grant")
    s.add_argument("symbol")
    s.add_argument("--value", type=float, help="grant value in $ (RSUs)")
    s.add_argument("--units", type=float, help="number of RSUs / options")
    s.add_argument("--strike", type=float, help="option strike (makes it an option grant)")
    s.add_argument("--years", type=float, default=4)
    s.add_argument("--cliff", type=int, default=12, help="cliff in months")
    s.add_argument("--frequency", default="quarterly", choices=["monthly", "quarterly", "semiannual", "annual"])
    s.add_argument("--method", default="bootstrap", choices=["bootstrap", "garch", "gbm"])
    s.add_argument("--drift", default="zero", choices=["zero", "riskfree", "historical"])
    s.set_defaults(fn=cmd_offer)

    s = sub.add_parser("report", help="shareable single-file HTML snapshot")
    s.add_argument("symbols", nargs="*")
    s.add_argument("--market", action="store_true", help="also include the market dashboard and screener")
    s.add_argument("--out", help="output file or folder (default ~/.semiquant/exports)")
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("export", help="Excel workbook for one ticker")
    s.add_argument("symbol")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_export)

    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        a = ap.parse_args(["serve"] + (argv if argv is not None else sys.argv[1:]))
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    try:
        a.fn(a)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        _console().print(f"[red]Error:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
