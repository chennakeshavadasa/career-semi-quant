# Career Semi Quant Terminal - Documentation

Welcome to the documentation for the Career Semi Quant Terminal. This guide explains two of the most powerful features in the terminal: the **Strategy Backtesting Engine** and the **Portfolio Optimizer**.

## Strategy Backtesting Engine

The **Strategy Backtesting Engine** allows you to test systematic trading strategies over historical semiconductor stock data. Instead of relying on gut feelings, you can see exactly how a quantitative strategy would have performed if you had traded it in the past.

### How it Works
1. **Select a Strategy:** You can choose from pre-built models such as **RSI Mean Reversion** (buy when oversold, sell when overbought) or **MACD Trend Following** (buy on upward momentum crosses).
2. **Execute on Universe:** The engine runs the strategy across the historical daily prices of all loaded stocks.
3. **Analyze Results:** It outputs the total Profit & Loss (P&L), Win Rate, Average Win vs. Average Loss, and Total Trades executed.

![Backtesting Engine](/home/nithin/.gemini/antigravity-cli/brain/77bb6738-c554-4972-9233-67bff379d826/backtest_plot_1781554061597.jpg)

*Example: A backtest visualization showing precise algorithmic buy (green) and sell (red) signals plotted directly on the price curve.*

---

## Portfolio Optimizer

The **Portfolio Optimizer** uses Modern Portfolio Theory (Mean-Variance Optimization) to help you construct the mathematically optimal allocation of your capital across different semiconductor stocks to maximize your Sharpe Ratio (risk-adjusted return).

### How it Works
1. **Covariance & Expected Returns:** The optimizer calculates the historical drift (returns) and the covariance matrix (how the stocks move in relation to each other).
2. **Monte Carlo Simulation:** It simulates thousands of random portfolio weight combinations.
3. **Efficient Frontier:** It plots these portfolios on a scatter chart (Risk vs. Return) and identifies the **Tangency Portfolio**—the single portfolio that offers the highest return for the lowest possible risk.
4. **Capital Allocation:** The tool outputs the exact percentage weights you should allocate to each stock (e.g., 32% NVDA, 22% TSM, etc.) to achieve this optimal balance.

![Portfolio Optimizer](/home/nithin/.gemini/antigravity-cli/brain/77bb6738-c554-4972-9233-67bff379d826/optimizer_plot_1781554081744.jpg)

*Example: The Efficient Frontier scatter plot showing the optimal tangency portfolio, alongside a breakdown of recommended asset allocation weights.*

---

*Note: This terminal is for informational and research purposes only and does not constitute financial advice.*
