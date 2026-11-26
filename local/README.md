# Semi Quant Terminal: local edition

A quant terminal that runs on your own computer. It pulls **live data from Yahoo Finance** (quotes refreshed every 30 s, 1-minute intraday bars, option chains, statements, analyst estimates, insider trades, earnings and economic calendars) and computes **institutional-style analytics locally**: risk and tail models, volatility forecasting, options positioning, factor exposures, regime detection, valuation, portfolio optimization and an RSU / stock-option offer simulator.

It opens as a dashboard in your browser and also works from the terminal. Everything stays on your machine; the only network traffic is to Yahoo Finance.

The website edition ([nithinpuru.github.io/quant-terminal](https://nithinpuru.github.io/quant-terminal/)) runs on weekly data refreshed twice a day. This edition is the live, deeper version.

## Start it

You need Python 3.10 or newer ([python.org/downloads](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH").

**Option 1, one click.** Download this folder (on GitHub: *Code → Download ZIP*, then open `local/`), then double-click:

| System | File |
|---|---|
| Windows | `start-windows.bat` |
| macOS | `start-mac.command` (first time: right-click → Open) |
| Linux | `start-linux.sh` |

The first run installs everything into a private `.venv` folder (1-3 minutes). Your browser then opens at `http://127.0.0.1:8050`.

**Option 2, one command** (with [pipx](https://pipx.pypa.io)):

```bash
pipx install "git+https://github.com/chennakeshavadasa/career-semi-quant.git#subdirectory=local"
```

```bash
semiquant
```

**Option 3, from a clone of this repository:**

```bash
cd local && ./start-linux.sh
```

Stop the dashboard with Ctrl-C in the terminal window.

## What is inside

**Market dashboard.** US indices and futures, Treasury yields (curve and 10Y-3M spread), FX and crypto, commodities, global indices, VIX term structure (contango or backwardation), sector ETF rotation, a market-cap heatmap of the 70-name semiconductor universe, breadth (share above the 20/50/200-day averages, new highs and lows, correlation, dispersion), a hidden Markov model regime for SOXX, US movers, upcoming earnings and headlines.

**Company workspace** (any Yahoo symbol: `NVDA`, `005930.KS`, `8035.T`, `ASML.AS`, `^GSPC`, `BTC-USD`, `ES=F`):

| Tab | What it shows |
|---|---|
| Overview | Interactive price chart (1 minute to all history, candles, 18 indicators incl. VWAP, Bollinger, Ichimoku, RSI, MACD, ADX), live price incl. pre/after-hours, key statistics, quant score with its drivers, technical rating, pivot and swing levels, 52-week range, risk snapshot, analyst consensus, next earnings, news |
| Risk & returns | Ratio suite over 1/3/5/10 years vs S&P 500 or SOXX (Sharpe, Sortino, Calmar, alpha, beta, information ratio, capture ratios, Omega, Ulcer), trailing returns, underwater curve and worst drawdowns, rolling volatility, Sharpe, beta and correlation, return distribution vs normal and Student-t, monthly-return heatmap and seasonality |
| Volatility | Yang-Zhang, Garman-Klass, Rogers-Satchell, Parkinson and close-to-close realized vol, volatility cone, GJR-GARCH(1,1) with Student-t errors and its forecast path, EWMA, 30-day implied vs realized (volatility risk premium) |
| Tail risk & stress | VaR and Expected Shortfall: historical, normal, Cornish-Fisher, Student-t, extreme-value (GPD) and GARCH-filtered historical simulation; rolling backtests with Kupiec and Christoffersen tests and the Basel traffic light; actual moves in twelve past crises since 2008; beta-implied shocks to stocks, rates, the dollar, oil and VIX |
| Options | Chain with Black-Scholes greeks, IV recomputed from bid/ask, smile, 25-delta risk reversal and butterfly, term structure, IV surface, straddle-implied move, earnings move implied by the term structure, put/call ratios, max pain, dealer gamma exposure (GEX) and gamma flip, unusual activity |
| Fundamentals | Statements (annual and quarterly), margins, ROE/ROIC, R&D and stock-based-compensation intensity, dilution, Piotroski F-score, Altman Z, multiples, an interactive DCF with sensitivity grid, reverse DCF (the growth the price implies), valuation history, sector peers |
| Analysts & earnings | Price targets, rating trend, every upgrade/downgrade with target changes, EPS and revenue consensus, estimate revisions (7/30/60/90 days), earnings history, an event study of every report (abnormal returns, post-earnings drift after beats vs misses) |
| Ownership | Insider buying and selling (Form 4), largest institutions and funds, short interest, days to cover |
| Factors & regimes | Style-factor regression on ETF spreads (market, semis, size, value, momentum, quality, low vol) with Newey-West t-stats and variance attribution, macro sensitivities (yields, dollar, oil, VIX), rolling betas, hidden Markov volatility regimes, closest peers |
| Filings & news | SEC filings with links, dividends, splits, news |

**Tools.** A screener over the universe or any watchlist (about 40 columns, ranked by a composite quant score: momentum, trend, value, quality, growth, estimate revisions, analyst view, low volatility; plus a scatter map), Compare (up to 12 tickers), Portfolio (live value in USD, Euler risk contributions, VaR, seven optimizers incl. risk parity and hierarchical risk parity, efficient frontier, backtest, crisis replay, 12-month Monte Carlo), Offer & RSU value (Monte Carlo of a grant over its vesting schedule, RSUs or options, up to three offers side by side), Calendar (earnings and economic events).

## Terminal commands

```text
semiquant                          start the dashboard (same as: semiquant serve)
semiquant quote NVDA AMD TSM       live quotes incl. pre/after-hours
semiquant watch --list "My watchlist"   live-updating board (Ctrl-C to stop)
semiquant analyze NVDA             one-page tear sheet
semiquant options NVDA             implied vol, skew, expected move, chain near the money
semiquant screen --sort score      rank the semiconductor universe
semiquant market                   global market snapshot
semiquant offer NVDA --value 100000 --years 4      value an RSU grant
semiquant report NVDA AVGO         shareable HTML snapshot (see below)
semiquant export NVDA              Excel workbook with everything
```

With the one-click launchers, put the command after the file name, for example `./start-linux.sh quote NVDA`.

## Share with a friend

* **A result.** Every company page has a **Share** button (or run `semiquant report NVDA`). It saves **one HTML file** with every tab, interactive charts and the data at that moment. Anyone can open it in a browser: no install, works offline. The market page has its own **Share snapshot** button.
* **The data.** **Excel** buttons (company page, screener, portfolio) save the underlying numbers; every table also has a CSV button, and every chart can be saved as PNG.
* **The tool.** Send the pipx command above, or the `local` folder as a zip: they double-click the launcher for their system.

## How fresh is the data?

| Data | Refresh |
|---|---|
| Quotes (price, change, pre/after-hours) | every 30 s while a market is open (one batched request for everything on screen), every 5 min when closed; adjustable under Settings |
| Intraday chart | 1-minute bars, reloaded every 60 s on the 1-day view |
| Daily bars and every daily statistic | today's bar is patched with the live quote on every read |
| Option chains | 2 min |
| News | 5 min |
| Analyst estimates | 1 h; fundamentals and ownership 6-12 h (they change quarterly) |

Exchange delays come from Yahoo: US stocks are real-time on most venues, some foreign exchanges are delayed 15-20 minutes (shown on the company header). If Yahoo throttles your connection, the tool switches quotes to a second Yahoo endpoint and serves the last good copy of everything else, then recovers by itself.

## Where things are saved

Settings, watchlists, your portfolio, the data cache and exports live in `~/.semiquant` (`%USERPROFILE%\.semiquant` on Windows). Delete its `cache` folder to force a full refresh. Set `SEMIQUANT_HOME` to keep them elsewhere.

## Under the hood

```text
semiquant/
  data/yahoo.py      every Yahoo request: caching, batching, fallbacks
  analytics/         pure numpy/pandas/scipy/statsmodels/arch functions, unit-tested
  service/           combines data and analytics; shared by the API, the CLI and exports
  server/app.py      FastAPI: JSON API under /api, the dashboard at /
  web/               the dashboard (vanilla JS, lightweight-charts, Plotly)
  cli.py             terminal commands
```

Run the tests (offline, on real Yahoo snapshots in `tests/fixtures`):

```bash
pip install -e ".[dev]" && pytest
```

## Disclaimer

For education and research. Models describe the past and are not forecasts or investment advice. Data © its providers via Yahoo Finance; check important numbers against filings before acting on them.
