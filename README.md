# Career Semi Quant Terminal 📈

A zero-server, fully client-side quantitative stock analysis dashboard built explicitly to track the global semiconductor supply chain (Foundries, Fabrication Equipment, and Memory). 

**🎯 Built for Semiconductor Engineers:** This terminal was designed specifically for hardware, ASIC, analog, and layout engineers who are job hunting or researching companies. It provides a massive, curated directory of the top players in every specialized sub-field (Optical Rx/Tx, SerDes IP, Mixed-Signal, AI Infrastructure) and runs live algorithmic stock analysis so you can instantly evaluate a prospective employer's financial health, market momentum, and stock option potential before deciding to join them.

This terminal executes institutional-grade mathematical models entirely within the browser to identify heavily discounted assets, predict future price action, and manage downside risk.

![Quant Terminal Dashboard](https://img.shields.io/badge/Status-Live-brightgreen) ![Architecture](https://img.shields.io/badge/Architecture-Serverless-blue) ![Math Engine](https://img.shields.io/badge/Math-Algorithmic-purple)

## 🧠 Institutional Quant Engine

The dashboard automatically calculates the following indicators from raw weekly close prices:
- **Trend Crosses:** 10-Week / 40-Week SMA Crossovers (Golden Cross & Death Cross).
- **Fibonacci Retracements:** Identifies the 61.8% Golden Ratio support level based on 52-week ranges.
- **Geometric Brownian Motion (GBM):** Predicts a 6-month target price using historical weekly drift and volatility.
- **Risk Metrics:** Annualized Volatility, Sharpe Ratio, Sortino Ratio, Value at Risk (VaR-95), and Maximum Drawdown.
- **Fear & Greed Index:** A custom composite algorithmic score identifying extreme psychological market states based on volume, RSI, and Stochastics.
- **Momentum Indicators:** MACD (Moving Average Convergence Divergence), RSI (Relative Strength Index), and Stochastic Oscillators.

## 🛡️ 5-Tier Foolproof API Architecture

To ensure the terminal **never crashes** and operates 100% serverless, it utilizes a deeply nested fetch hierarchy to bypass rate-limits and CORS blocks:
1. **Parallel Proxy Racing:** Instantly fires requests through 4 simultaneous proxy networks to fetch data directly from Yahoo Finance. The fastest successful proxy wins.
2. **Polygon.io Fallback:** Routes through user-provided Polygon API keys.
3. **Alpha Vantage Fallback:** Routes through Alpha Vantage API endpoints.
4. **Finnhub Fallback:** Routes through Finnhub API endpoints.
5. **Simulated Data Generator:** If all network requests fail entirely, a local stochastically-generated fallback engine spins up synthetic price movements so the UI never breaks.

## 🚀 Deployment (GitHub Pages)

Because this is a fully client-side architecture, it hosts directly on GitHub Pages for free.
No Node.js servers, no Python backends, and zero deployment costs.

1. Go to repository **Settings**.
2. Click **Pages**.
3. Under *Source*, select **Deploy from a branch**.
4. Select the **`master`** branch and click **Save**.

## ⚙️ Configuration

If you want to add your own API keys for the Level 2/3/4 fallbacks:
1. Open the live dashboard.
2. Click the **⚙️ API KEYS** button.
3. Paste your free keys from Polygon, Alpha Vantage, or Finnhub. Keys are saved securely in your browser's LocalStorage.

## 🏢 Tracked Coverage

**Foundries:** Taiwan Semi (TSM), GlobalFoundries (GFS)  
**Equipment & Fab:** ASML, Lam Research (LRCX), Applied Materials (AMAT), KLA Corp (KLAC), Tokyo Electron (TOELY)  
**Memory & Storage:** Micron (MU), Western Digital (WDC), Seagate (STX)  
**Optical Rx/Tx & Photonics:** Coherent Corp (COHR), Lumentum (LITE), MACOM (MTSI)  
**SerDes IP & High-Speed:** Rambus (RMBS), Alphawave Semi (AWE.L), Credo (CRDO), Astera Labs (ALAB)  
**Analog & Mixed-Signal:** Monolithic Power (MPWR), Cirrus Logic (CRUS), Synaptics (SYNA), Silicon Labs (SLAB)  
**AI & Design IP:** NVIDIA (NVDA), AMD, ARM Holdings (ARM), Super Micro Computer (SMCI), CEVA (CEVA)  
**Core Logic & RF:** Intel (INTC), Qualcomm (QCOM), Broadcom (AVGO), Texas Instruments (TXN), and 15+ more.
