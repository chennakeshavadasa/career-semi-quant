# Career Semi Quant Terminal 📈

> A zero-server, fully client-side quantitative stock analytics dashboard for the global semiconductor industry.  
> **Live → [chennakeshavadasa.github.io/career-semi-quant](https://chennakeshavadasa.github.io/career-semi-quant/)**

![Status](https://img.shields.io/badge/Status-Live-brightgreen)
![Architecture](https://img.shields.io/badge/Architecture-100%25_Client--Side-blue)
![Stocks](https://img.shields.io/badge/Companies-45+-purple)
![Cost](https://img.shields.io/badge/Cost-Free-green)

---

## Why This Exists

When you're a semiconductor engineer evaluating job offers, one of the hardest questions to answer is:

> *"This company is offering me RSUs / stock options. Are they actually worth anything?"*

Glassdoor won't tell you. LinkedIn won't tell you. And Bloomberg Terminal costs $24,000/year.

**Career Semi Quant Terminal** was built to solve exactly this problem. It gives semiconductor professionals — analog designers, ASIC engineers, layout engineers, verification teams — a single dashboard where they can:

1. **Discover** which companies exist in their specific sub-field (Optical Rx/Tx, SerDes IP, Mixed-Signal, AI accelerators)
2. **Analyze** each company's stock trajectory using the same mathematical models institutional funds use
3. **Evaluate** whether a prospective employer's RSUs/ESPPs are trending up, collapsing, or stagnating — *before* accepting an offer

No login. No account. No API key required. Open the page and the data loads.

---

## What It Calculates

Every single metric on the dashboard is computed **live in your browser** from real weekly close prices. Nothing is pre-baked, cached, or scraped from a third-party analysis site.

### Momentum & Trend Indicators

| Indicator | What It Tells You |
|---|---|
| **RSI (14-period)** | Whether the stock is overbought (>70) or oversold (<30). Mean-reversion signal. |
| **Stochastic Oscillator** | Where the current price sits relative to its 14-week range. Complements RSI. |
| **MACD Histogram** | Whether short-term momentum is accelerating (Bullish) or decelerating (Bearish). |
| **10/40 SMA Cross** | Whether the 10-week moving average is above or below the 40-week. A Bull Cross means the trend has turned upward; a Death Cross means the opposite. |
| **Bollinger Band Position** | Whether the price has broken above the upper band (OVERBOUGHT) or below the lower band (OVERSOLD). |

### Risk Metrics

| Metric | What It Tells You |
|---|---|
| **Annualized Volatility** | How wildly the stock swings. A 60%+ volatility means your RSU grant could halve in value in a single quarter. |
| **Sharpe Ratio** | Risk-adjusted return vs. the 10-Year Treasury (~4.5%). Above 1.0 = the stock is compensating you for the risk. Below 0 = you'd be better off in government bonds. |
| **Sortino Ratio** | Like Sharpe, but only penalizes *downside* volatility. A high Sortino means the stock goes up a lot but doesn't crash often. |
| **Value at Risk (95%)** | The worst weekly loss you can expect 95% of the time. If VaR is -5.2%, there's a 5% chance any given week could be *worse* than -5.2%. |
| **Maximum Drawdown** | The largest peak-to-trough drop in the past year. If Max DD is -40%, the stock fell 40% from its high before recovering. |

### Structural Analysis

| Metric | What It Tells You |
|---|---|
| **Fibonacci 61.8% Support** | The "golden ratio" retracement level. If the stock is near this price, it's at a historically significant support zone. |
| **Distance to 52-Week High** | How far the stock has fallen from its peak. A stock at -45% from its high is either a deep value opportunity or in serious trouble — the other indicators help you decide which. |
| **Monte Carlo 6M Target** | A 2,000-iteration Monte Carlo simulation of Geometric Brownian Motion based on historical drift and volatility. Returns a 3-point confidence interval: Median (Base Case), 90th percentile (Bull Case), and 10th percentile (Bear Case). |

### Composite Quant Score (0–100)

A weighted composite of all the above indicators. The score is designed to surface stocks that are:
- Trending upward (positive 6M and 1Y returns, bullish MACD)
- In a fear zone (low RSI, low Fear & Greed index)
- Well-compensating for risk (high Sortino/Sharpe)
- At a trend inflection point (Bull Cross)

**Score ≥ 70** = Strong momentum, highlighted in green  
**Score < 40** = Weak or deteriorating, highlighted in red  
**Between** = Neutral

### Fear & Greed Index

A custom composite of RSI, Stochastic, and Volatility that classifies each stock into one of five emotional states:

`EXTREME FEAR` → `FEAR` → `NEUTRAL` → `GREED` → `EXTREME GREED`

Extreme Fear often signals a buying opportunity. Extreme Greed often signals overextension.

---

## Covered Sectors (45+ Companies)

The dashboard covers every major publicly traded company across the semiconductor value chain:

| Sector | Companies |
|---|---|
| **Foundries** | TSMC, GlobalFoundries |
| **EDA & Design IP** | Synopsys, Cadence, ARM |
| **Fab Equipment** | ASML, Applied Materials, Lam Research, KLA, Tokyo Electron |
| **Memory** | Micron, Western Digital, Samsung Electronics |
| **AI / GPU** | NVIDIA, AMD, Super Micro Computer |
| **High-Speed SerDes** | Broadcom, Marvell, Credo, Astera Labs, Rambus, MaxLinear, Alphawave, Parade |
| **Optical Rx/Tx** | Coherent Corp, Lumentum, MACOM |
| **Analog & Mixed-Signal** | Texas Instruments, Analog Devices, Monolithic Power, Cirrus Logic, Microchip, Silicon Labs, onsemi, Synaptics, STMicro |
| **RF & Wireless** | Qualcomm, Skyworks, Qorvo |
| **MCU / DSP** | NXP, Renesas, CEVA |
| **Power & CPU** | Intel, Semtech, Infineon |
| **Private (Pre-IPO)** | FermionIC, Aura Semi, Steradian, Saankhya Labs, AGNIT |

Private companies are displayed with a `NOT PUBLICLY LISTED` state — they're included so engineers in the Indian semiconductor ecosystem can see the landscape even if the company hasn't IPO'd yet.

---

## How the Data Pipeline Works

```
┌─────────────────────────────────────────────────────┐
│                  YOUR BROWSER                        │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ LEVEL 1: Yahoo Finance (via 4 parallel proxies)│   │
│  │   • Direct fetch                              │   │
│  │   • AllOrigins proxy                          │   │
│  │   • CodeTabs proxy                            │   │
│  │   • CORSProxy.io                              │   │
│  │   → Promise.any() — fastest wins (9s timeout) │   │
│  └───────────────────┬──────────────────────────┘   │
│                      │ if < 25 data points           │
│  ┌───────────────────▼──────────────────────────┐   │
│  │ LEVEL 2: Polygon.io  (user API key)           │   │
│  └───────────────────┬──────────────────────────┘   │
│                      │ if still < 25 data points     │
│  ┌───────────────────▼──────────────────────────┐   │
│  │ LEVEL 3: Alpha Vantage  (user API key)        │   │
│  └───────────────────┬──────────────────────────┘   │
│                      │ if still < 25 data points     │
│  ┌───────────────────▼──────────────────────────┐   │
│  │ LEVEL 4: Finnhub  (user API key)              │   │
│  └───────────────────┬──────────────────────────┘   │
│                      │ if still < 25 data points     │
│  ┌───────────────────▼──────────────────────────┐   │
│  │ LEVEL 5: STRICT FAIL                          │   │
│  │   → "DATA UNAVAILABLE" (no fake/simulated     │   │
│  │      data is ever generated)                  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  Once data is obtained:                              │
│  → Run RSI, Stoch, Vol, Sharpe, Sortino, VaR,       │
│    MaxDD, MACD, Bollinger, Fibonacci, Monte Carlo,   │
│    Fear & Greed, Composite Score                     │
│  → Render card with sparkline + all metrics          │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Why No Simulated Data?

Earlier versions of this tool included a Geometric Brownian Motion fallback that generated synthetic price data when all APIs failed. **We removed it entirely.** Every number on this dashboard comes from a verified market data source. If data can't be fetched, the card explicitly shows `DATA UNAVAILABLE` — because showing fake numbers to professionals making career decisions is unacceptable.

### Why Client-Side Only?

- **Privacy**: Your API keys never leave your browser. They're stored in `localStorage`, not sent to any server.
- **Cost**: GitHub Pages hosting is free. No backend to maintain, no database to pay for.
- **Speed**: No server round-trip. The math runs natively in your browser's JavaScript engine.
- **Portability**: Works on any device with a browser. Bookmark it on your phone.

---

## Features

- **Sort** by Quant Score, RSI, 6M/1Y Return, or Volatility (ascending or descending)
- **Filter** by Tier-A, Tier-B, Strong Buys (≥70), or Extreme Fear
- **Search** by company name or ticker symbol
- **Sector tags** on every card for at-a-glance classification
- **Gradient area sparklines** showing 52-week price trajectory
- **Data freshness timestamp** so you always know when the data was last pulled
- **Live progress bar** showing which stocks are loading in real-time
- **Responsive grid** that adapts from mobile to ultrawide monitors

---

## Setup & Deployment

### Option 1: Just Use It
Visit **[chennakeshavadasa.github.io/career-semi-quant](https://chennakeshavadasa.github.io/career-semi-quant/)** — no setup needed.

### Option 2: Fork & Deploy Your Own
1. Fork this repository
2. Go to **Settings → Pages → Deploy from branch** → select `master` → Save
3. Your copy will be live at `https://<your-username>.github.io/career-semi-quant/`

### Option 3: Run Locally
```bash
git clone https://github.com/chennakeshavadasa/career-semi-quant.git
cd career-semi-quant
python3 -m http.server 8000
# Open http://localhost:8000
```

### Adding API Keys (Optional)
Click the **⚙ API KEYS** button on the dashboard and paste your free keys from:
- [Polygon.io](https://polygon.io/) — best for US equities
- [Alpha Vantage](https://www.alphavantage.co/) — good international coverage
- [Finnhub](https://finnhub.io/) — solid free tier

Keys are stored locally in your browser. They help fetch data for international stocks (Samsung, Infineon, etc.) that free proxies sometimes block.

---

## Limitations & Disclaimers

> **This tool is for educational and informational purposes only. It is NOT financial advice.**

- The **Monte Carlo Simulation** generates mathematical probabilities based on historical volatility. It cannot predict market crashes, earnings misses, or macroeconomic shocks.
- The **Quant Score** is a composite heuristic, not a trading signal. It surfaces interesting stocks — it doesn't tell you to buy or sell.
- **Momentum states** (Overbought/Oversold) are technical indicators based on price action. They are not fundamental valuations (P/E, DCF, etc.).
- Data depends on free proxy availability. Some international tickers may show `DATA UNAVAILABLE` if all proxies are blocked.
- Weekly resolution means intraday moves are not captured.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Structure** | Single `index.html` file — zero build step |
| **Styling** | Vanilla CSS with CSS custom properties (dark theme) |
| **Typography** | [Outfit](https://fonts.google.com/specimen/Outfit) (headings) + [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) (data) |
| **Math Engine** | Pure JavaScript — no external libraries |
| **Charts** | Inline SVG sparklines with gradient fills |
| **Hosting** | GitHub Pages (free) |
| **Data** | Yahoo Finance (via CORS proxies) + optional Polygon / Alpha Vantage / Finnhub |

---

## Contributing

Want to add more companies, improve the math, or fix a bug? PRs are welcome.

```bash
# Clone
git clone https://github.com/chennakeshavadasa/career-semi-quant.git

# Edit index.html — that's the entire app

# Test locally
python3 -m http.server 8000

# Push
git add . && git commit -m "your change" && git push
```

---

## License

MIT — use it however you want.
