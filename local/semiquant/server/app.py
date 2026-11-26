"""FastAPI app: JSON API under /api, the dashboard UI at /.

Run with ``semiquant`` (opens the browser) or ``semiquant serve --port 8050``.
Endpoints are thin wrappers over ``semiquant.service`` so the CLI, the exports and
the UI always show the same numbers.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__, config
from ..analytics._util import jsonable
from ..data import yahoo
from ..data.yahoo import DataError
from ..service import market as mkt
from ..service import screener as scr
from ..service import ticker as tk
from ..service import tools

log = logging.getLogger("semiquant.server")
WEB = Path(__file__).resolve().parent.parent / "web"


class SafeJSON(JSONResponse):
    """JSON response that never fails on NaN/inf or numpy values."""

    def render(self, content) -> bytes:
        try:
            return json.dumps(content, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            return json.dumps(jsonable(content), ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")


def _warmup() -> None:
    """Preload what the first screens need, gently (Yahoo-friendly pacing)."""
    from ..universe import FACTOR_ETFS, universe_tickers

    t0 = time.time()
    try:
        names = list(dict.fromkeys(universe_tickers("semis") + universe_tickers("us_large")))
        yahoo.quotes(names + ["SPY", "SOXX", "QQQ", "ACWI"])
        yahoo.history_many(names + ["SPY", "SOXX", "QQQ", "ACWI"], "2y", "1d")  # screener, heatmap, breadth
        yahoo.history_many(list(FACTOR_ETFS), "5y", "1d")  # factor models
        mkt.strip()
        for t in names:  # fundamentals for scores, ~4 per second
            try:
                yahoo.info(t, ttl=scr.FUND_TTL)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
        for t in names:  # consensus revisions
            try:
                yahoo.eps_trend(t, ttl=12 * 3600)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
        log.info("warm-up finished in %.0f s", time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        log.warning("warm-up stopped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    if os.environ.get("SEMIQUANT_NO_WARMUP") != "1":
        threading.Thread(target=_warmup, name="warmup", daemon=True).start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Semi Quant Terminal", version=__version__, default_response_class=SafeJSON,
                  lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=1500)

    @app.exception_handler(DataError)
    async def _data_error(request: Request, exc: DataError):
        return SafeJSON({"error": str(exc)}, status_code=404)

    @app.exception_handler(Exception)
    async def _any_error(request: Request, exc: Exception):
        log.error("%s %s failed: %s", request.method, request.url.path, exc)
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        return SafeJSON({"error": f"{type(exc).__name__}: {exc}", "trace": "".join(tb[-3:])[-1500:]}, status_code=500)

    def syms(s: str | None) -> list[str]:
        return [x.strip().upper() for x in (s or "").split(",") if x.strip()]

    # ── meta ──────────────────────────────────────────────────────────────
    @app.get("/api/status")
    def status():
        return {"version": __version__, "data": yahoo.status(), "market": yahoo.market_status("US"),
                "settings": config.settings(), "home": str(config.HOME)}

    @app.get("/api/settings")
    def get_settings():
        return config.settings()

    @app.put("/api/settings")
    def put_settings(body: dict = Body(...)):
        return config.save_settings(body)

    @app.get("/api/watchlists")
    def get_watchlists():
        return config.watchlists()

    @app.put("/api/watchlists")
    def put_watchlists(body: dict = Body(...)):
        return config.save_watchlists(body)

    @app.get("/api/portfolio")
    def get_portfolio():
        return config.portfolio()

    @app.put("/api/portfolio")
    def put_portfolio(body: dict = Body(...)):
        return config.save_portfolio(body)

    @app.post("/api/portfolio/analyze")
    def analyze_portfolio(body: dict = Body(...)):
        return tools.portfolio(body)

    # ── market-wide ───────────────────────────────────────────────────────
    @app.get("/api/quotes")
    def get_quotes(symbols: str = Query(...)):
        return yahoo.quotes(syms(symbols)[:250])

    @app.get("/api/market")
    def market():
        return mkt.overview()

    @app.get("/api/market/strip")
    def market_strip():
        return mkt.strip()

    @app.get("/api/market/heatmap")
    def market_heatmap(u: str = "semis"):
        return mkt.heatmap(u)

    @app.get("/api/market/breadth")
    def market_breadth(u: str = "semis"):
        return mkt.breadth(u)

    @app.get("/api/universes")
    def universes():
        from ..universe import UNIVERSES
        return [{"key": k, "label": v["label"], "count": len(v["rows"]), "group_label": v["group_label"]}
                for k, v in UNIVERSES.items()]

    @app.get("/api/market/movers")
    def market_movers():
        return mkt.movers()

    @app.get("/api/market/earnings")
    def market_earnings():
        return mkt.upcoming_earnings(30)

    @app.get("/api/market/news")
    def market_news():
        return mkt.market_news()

    @app.get("/api/search")
    def search(q: str = ""):
        return tools.search(q)

    @app.get("/api/screener")
    def screener(list: str | None = None, symbols: str | None = None, u: str = "semis"):  # noqa: A002 - query name
        tick = syms(symbols) or (config.watchlists().get(list or "") if list else None)
        return scr.table(tick, name=list, universe=u)

    @app.get("/api/compare")
    def compare(symbols: str = Query(...), range: str = "1Y", bench: str = "SPY"):  # noqa: A002
        return tools.compare(syms(symbols), range, bench.upper())

    @app.get("/api/calendar")
    def calendar():
        return tools.calendar()

    @app.post("/api/offer")
    def offer(body: dict = Body(...)):
        return tk.offer(body)

    # ── single ticker ─────────────────────────────────────────────────────
    @app.get("/api/ticker/{sym}/overview")
    def t_overview(sym: str):
        return tk.overview(sym)

    @app.get("/api/ticker/{sym}/score")
    def t_score(sym: str):
        return tk.score(sym)

    @app.get("/api/ticker/{sym}/chart")
    def t_chart(sym: str, range: str = "6M", ind: str | None = None):  # noqa: A002
        return tk.chart(sym, range, [x for x in (ind or "").split(",") if x] if ind is not None else None)

    @app.get("/api/ticker/{sym}/risk")
    def t_risk(sym: str):
        return tk.risk(sym)

    @app.get("/api/ticker/{sym}/volatility")
    def t_vol(sym: str):
        return tk.volatility(sym)

    @app.get("/api/ticker/{sym}/tail")
    def t_tail(sym: str):
        return tk.tail(sym)

    @app.get("/api/ticker/{sym}/options")
    def t_options(sym: str, expiry: str | None = None):
        return tk.options(sym, expiry)

    @app.get("/api/ticker/{sym}/fundamentals")
    def t_fund(sym: str):
        return tk.fundamentals(sym)

    @app.get("/api/ticker/{sym}/analysts")
    def t_analysts(sym: str):
        return tk.analysts(sym)

    @app.get("/api/ticker/{sym}/ownership")
    def t_owner(sym: str):
        return tk.ownership(sym)

    @app.get("/api/ticker/{sym}/factors")
    def t_factors(sym: str):
        return tk.factors(sym)

    @app.get("/api/ticker/{sym}/events")
    def t_events(sym: str):
        return tk.events(sym)

    @app.get("/api/ticker/{sym}/news")
    def t_news(sym: str, count: int = 30):
        return tk.news(sym, count)

    # ── exports ───────────────────────────────────────────────────────────
    @app.get("/api/export/ticker/{sym}.xlsx")
    def x_ticker(sym: str):
        from ..service import export
        data, name = export.ticker_xlsx(sym)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/export/screener.{fmt}")
    def x_screener(fmt: str, list: str | None = None, symbols: str | None = None, u: str = "semis"):  # noqa: A002
        from ..service import export
        tick = syms(symbols) or (config.watchlists().get(list or "") if list else None)
        data, name, mime = export.screener_file(tick, fmt, list, u)
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/export/portfolio.xlsx")
    def x_portfolio(body: dict = Body(...)):
        from ..service import export
        data, name = export.portfolio_xlsx(body)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/export/snapshot.html")
    def x_snapshot(symbols: str = "", market: bool = True):
        from ..service import export
        html, name = export.snapshot_html(syms(symbols), include_market=market)
        return HTMLResponse(html, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ── static UI ─────────────────────────────────────────────────────────
    @app.get("/vendor/plotly.min.js")
    def plotly_js():
        import plotly
        p = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
        return FileResponse(p, media_type="application/javascript", headers={"Cache-Control": "max-age=86400"})

    @app.get("/healthz", response_class=PlainTextResponse)
    def health():
        return "ok"

    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
    return app


app = create_app()
