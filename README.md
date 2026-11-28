# Career Semi Quant Terminal

**Live: [nithinpuru.github.io/quant-terminal](https://nithinpuru.github.io/quant-terminal/)**

Institutional-style quant analytics for 70+ semiconductor stocks, including momentum, risk, factor models, regime detection, portfolio optimization, stress testing, pairs trading and walk-forward backtests, plus GARCH volatility forecasting, extreme-value VaR with Kupiec/Christoffersen backtests, random-matrix covariance denoising, Kalman-filter betas and deflated-Sharpe strategy validation. It runs entirely in the browser. The web edition and the local edition also have a **World risk** page (wars and flashpoints, ship traffic through 28 straits and canals from IMF PortWatch, live conflict headlines, and what they can hit, down to chip supply) and an **Insiders & Congress** tab for every stock (Congress trades, executives' Form 4s, planned sales, 5%+ stakes). Full documentation: [`quant-terminal/README.md`](quant-terminal/README.md) · maths and plots: [`quant-terminal/DOCUMENTATION.md`](quant-terminal/DOCUMENTATION.md).

## Local edition: live data on your own computer

[`local/`](local/README.md) is a separate, deeper version that runs on your machine: live Yahoo Finance quotes (refreshed every 30 s), 1-minute charts, option chains, statements, analyst estimates and ownership, for semiconductors, 165 US large caps across every sector, 64 global leaders, 65 ETFs or any ticker. Institutional analytics run locally: VaR/ES with backtests, GARCH, implied vs realized volatility, gamma exposure, factor regressions, regimes, DCF, portfolio optimizers and an RSU/option offer simulator, plus World risk (straits, conflicts, supply chain) and Insiders & Congress. It opens as a browser dashboard, works from the terminal, and exports to Excel or a single shareable HTML file.

```bash
pipx install "git+https://github.com/chennakeshavadasa/career-semi-quant.git#subdirectory=local"
```

```bash
semiquant
```

Or download the repo and double-click `local/start-windows.bat`, `local/start-mac.command` or `local/start-linux.sh`. Details: [`local/README.md`](local/README.md).

## This repo is the source of truth

Edit the terminal **here**. The portfolio site ([NithinPuru/nithinpuru.github.io](https://github.com/NithinPuru/nithinpuru.github.io)) mirrors the same folders automatically:

```
you push to master
   │
   ▼
Test workflow ── unit tests (quant library) + headless-browser e2e test
   │  pass
   ▼
site: "Sync quant terminal code" (every 30 min) copies the newest *passing* commit
   │  public/quant-terminal/ (except market_data.json) + quant-terminal/
   ▼
site redeploys → nithinpuru.github.io/quant-terminal

site: "Update quant terminal data" (twice daily) fetches prices → market_data.json
   │
   ▼
here: "Pull market data from site" (every 3 h) copies market_data.json back
```

Each side writes only the files it owns, so the two repos can't conflict or loop. A commit that fails its tests is never published. To publish immediately, run **Sync quant terminal code** manually on the site repo's Actions tab. Don't edit `public/quant-terminal/` or `quant-terminal/` directly in the site repo: the next sync overwrites them.

## Layout

| Path | What |
|---|---|
| `public/quant-terminal/index.html` | The app (dashboard, cards, detail view, optimizer, tracker) |
| `public/quant-terminal/js/quant-lib.js` | Quant library: HMM, cointegration, factor models, ERC/HRP/Black-Litterman, walk-forward engine |
| `public/quant-terminal/js/quant-ext.js` | Risk & validation models: GARCH/GJR, EVT & VaR backtests, deflated Sharpe, bootstrap, PCA / Marchenko-Pastur, Kalman filter |
| `public/quant-terminal/js/tools.js` | Tool UIs: factor model, regimes, risk & stress, pairs, rotation, backtester, screener |
| `public/quant-terminal/js/tools2.js` | Tool UIs: volatility & tail risk, market structure, strategy validation |
| `public/quant-terminal/market_data.json` | Weekly prices + fundamentals + FX (written by the site's data bot) |
| `quant-terminal/update_data.py` | yfinance data pipeline (runs on the site repo) |
| `quant-terminal/tests/` | `quant-lib.test.mjs` unit tests, `e2e.mjs` browser test |
| `index.html`, `404.html` | Redirect the old URL (chennakeshavadasa.github.io/career-semi-quant) to the live page |

## Develop locally

```bash
npm install                 # puppeteer, for the browser test
npm run serve               # http://localhost:8000/quant-terminal/
npm test                    # unit + end-to-end tests (what CI runs)
python quant-terminal/update_data.py   # refresh market_data.json locally (pip install -r quant-terminal/requirements.txt)
```

MIT License · For educational purposes only, not financial advice.
