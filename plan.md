# Implementation Plan
1.  **Dependencies**: Inject Lightweight Charts CDN.
2.  **UI Additions**: Add buttons for CSV Export, Portfolio, Backtest in the header. Add modals for Portfolio and Backtest.
3.  **CSV Export logic**: Simple loop over `D` object and download Blob.
4.  **Lightweight Charts logic**: Modify `showDetail(ticker)` to instantiate `LightweightCharts.createChart` instead of `Chart.js` for the main price chart. Add Candlestick series and SMA/Bollinger overlay series.
5.  **Fundamentals / Earnings logic**: Add `fetchFundamentals(ticker)` using Alpha Vantage / Finnhub / Yahoo. Add display elements to `cardHTML` and `detail modal`.
6.  **Portfolio Tracker logic**: UI to add stocks + weights, save to `localStorage`, compute portfolio equity curve, render with Chart.js.
7.  **Backtesting Engine logic**: Simple moving average crossover or RSI strategy logic loop over `closes` array, compute equity curve and metrics, render in modal.
