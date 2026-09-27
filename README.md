# Career Semi Quant Terminal

**Live: [nithinpuru.github.io/quant-terminal](https://nithinpuru.github.io/quant-terminal/)**

Institutional-style quant analytics for 70+ semiconductor stocks, including momentum, risk, factor models, regime detection, portfolio optimization, stress testing, pairs trading and walk-forward backtests. It runs entirely in the browser. Full documentation: [`quant-terminal/README.md`](quant-terminal/README.md) · maths and plots: [`quant-terminal/DOCUMENTATION.md`](quant-terminal/DOCUMENTATION.md).

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
| `public/quant-terminal/js/tools.js` | Tool UIs: factor model, regimes, risk & stress, pairs, rotation, backtester, screener |
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
