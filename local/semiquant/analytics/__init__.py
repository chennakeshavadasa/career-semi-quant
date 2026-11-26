"""Quant analytics: pure functions on pandas/numpy data (no network, no I/O).

Modules
-------
performance   returns tables, ratio suite, drawdowns, rolling metrics, monthly returns
technicals    indicators (SMA/EMA/RSI/MACD/BB/ATR/ADX/Stoch/OBV/VWAP/Ichimoku) and a signal summary
volatility    realized-vol estimators (Yang-Zhang etc.), vol cone, GARCH/GJR forecasts
risk          VaR/ES (historical, normal, Cornish-Fisher, Student-t, EVT, filtered HS), backtests, stress tests
factors       ETF style-factor and macro regressions (Newey-West), rolling betas, peer correlation
regimes       Gaussian hidden Markov model (Baum-Welch + Viterbi)
montecarlo    price cones and RSU / stock-option grant valuation
options       Black-Scholes greeks, implied vol, smile/skew, term structure, GEX, max pain, implied moves
earnings      earnings event study (market-model abnormal returns), implied vs historical move
fundamentals  statement-derived quality, growth, Piotroski F, Altman Z, multiples, DCF / reverse DCF
portfolio     covariance shrinkage, min-var / max-Sharpe / ERC / HRP, frontier, risk decomposition, backtest
pairs         Engle-Granger cointegration, half-life, spread z-scores, pair scans with FDR control
scoring       cross-sectional universe metrics and the composite quant score

Every public function returns JSON-ready values (see ``_util.jsonable``).
"""
