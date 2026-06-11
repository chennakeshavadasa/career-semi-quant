# Career Semi Quant Terminal — Complete Documentation

> **Who is this for?** Everyone — from someone who has never bought a stock, to a software engineer evaluating RSU packages, to an experienced quant researcher. Every metric is explained from first principles with simple analogies, precise mathematics, and real semiconductor-stock examples.

---

## Table of Contents

1. [Introduction — Why Quant Analytics?](#1-introduction)
2. [The Main Price Chart — SMA & Bollinger Bands](#2-main-price-chart)
3. [Fear & Greed Gauge](#3-fear--greed-gauge)
4. [Risk Metrics Grid (Card)](#4-risk-metrics-grid)
5. [Advanced Quant Analytics (Card)](#5-advanced-quant-analytics)
6. [S&P 500 Benchmarking Grid](#6-sp-500-benchmarking-grid)
7. [Quant & Trading Grid](#7-quant--trading-grid)
8. [Detail Modal — 9 Charts Explained](#8-detail-modal--9-charts)
9. [Detail Modal — Extended Metrics Grid (25 metrics)](#9-extended-metrics-grid)
10. [Universe Risk Map](#10-universe-risk-map)
11. [Universe Correlation Heatmap](#11-universe-correlation-heatmap)
12. [The Monte Carlo Engine (Merton Jump-Diffusion)](#12-the-monte-carlo-engine)
13. [Statistical Foundations Appendix](#13-appendix--statistical-foundations)
14. [Quick-Reference Cheat Sheet](#14-quick-reference-cheat-sheet)

---

## 1. Introduction

### Why does quantitative analysis matter?

Imagine you are choosing between two job offers. Both offer you RSUs (Restricted Stock Units). Company A's stock went up 200% last year. Company B's stock went up 80%. Which is better?

If you said Company A — you might be wrong. What if Company A crashed 70% the year before? What if it swings 15% every single week, making your future comp wildly unpredictable? What if Company B quietly outperforms the stock market every single year with very low risk?

**Quantitative finance** is the practice of measuring returns, risk, and value using mathematics — so you can make decisions based on evidence rather than gut feeling. This terminal applies the same institutional-grade quant methods used by hedge funds and asset managers to semiconductor stocks, so you can objectively evaluate any company's stock before joining.

### How the terminal works

1. Fetches **weekly closing prices** for 18+ months from live market data (Yahoo Finance, Polygon, Alpha Vantage, Finnhub)
2. Runs **35+ mathematical models** on those prices in real-time
3. Displays results as color-coded, comparable stock cards
4. Clicking any card opens a **deep-dive modal** with 9 professional charts + 25 metrics
5. Universe tools (Risk Map, Correlation Heatmap) give a portfolio-level view

### A note on data frequency

All calculations use **weekly prices**. This is deliberate:
- Daily prices contain too much noise (market microstructure, short-term speculation)
- Monthly prices have too few data points for meaningful statistics
- Weekly prices give a clean signal with ~52–78 data points per 1–1.5 years — enough for robust statistics

---

## 2. Main Price Chart

### What you see
The large chart at the top of every stock's detail modal shows three things together:
- **Blue line** — actual weekly closing price
- **Gold dashed line** — 40-Week Simple Moving Average (SMA)
- **Faint white band** — Bollinger Bands (20-week, ±2 standard deviations)

---

### 2.1 Simple Moving Average (SMA)

**Simple explanation (the step counter):**
Imagine you track your daily steps. Monday: 5,000. Tuesday: 7,000. Wednesday: 4,000. A 3-day moving average for Wednesday = (5,000+7,000+4,000)/3 = **5,333**. It smooths out the noise and reveals the underlying trend.

**Mathematical definition:**

```
SMA(n) at time t = (P[t] + P[t-1] + ... + P[t-n+1]) / n
```

Where P[t] is the closing price at week t, and n is the window size (10 weeks or 40 weeks).

**The two SMAs in this tool:**

| SMA | Speed | Purpose |
|-----|-------|---------|
| 10-Week SMA | Fast — reacts to recent moves | Short-term trend direction |
| 40-Week SMA | Slow — smooths out noise | Long-term trend / major support/resistance |

**Bull/Bear Cross Signal:**

When the fast SMA (10-week) crosses the slow SMA (40-week), it generates one of the most reliable trend signals in technical analysis:

- **BULL CROSS** 🟢 = SMA10 rises above SMA40 → trend turning upward
- **BEAR CROSS** 🔴 = SMA10 falls below SMA40 → trend turning downward

**Simple numerical example:**

Week 1–40: Stock averaging $100. Week 41–52: Stock rises to $150.
- SMA40 is slow: still pulls toward $100 range
- SMA10 is fast: already reflects the $150 range
- SMA10 > SMA40 → **BULL CROSS** triggered

**Real semiconductor example:**
In late 2022, NVIDIA's stock bottomed at ~$108. The SMA10 crossed above SMA40 in February 2023 — right at the beginning of the AI-driven bull run. A trader watching only this signal would have entered near the beginning of a 10x move. The signal is imprecise but powerful as a confirmation tool.

---

### 2.2 Bollinger Bands

**Simple explanation (the mood ring):**
If someone's daily mood score averages 7/10 and almost never goes above 9 or below 5, then a score of 9.5 today is *statistically unusual* — it'll probably drift back toward 7. Bollinger Bands apply exactly this statistical reasoning to stock prices.

**Mathematical definition:**

```
Middle Band  = SMA(20)
Upper Band   = SMA(20) + 2 × σ(20)
Lower Band   = SMA(20) - 2 × σ(20)
```

Where σ(20) is the standard deviation of the last 20 weekly closing prices.

By the properties of the normal distribution, approximately:
- **68%** of all prices should fall within ±1σ (inside half-width of band)
- **95%** of all prices should fall within ±2σ (inside the full bands)

**What the bands tell you:**

| Price Location | Interpretation |
|---------------|----------------|
| Touches upper band | Statistically expensive. Watch for reversal. |
| Touches lower band | Statistically cheap. Watch for bounce. |
| Bands expanding (widening) | Volatility increasing. Uncertainty rising. |
| Bands contracting (squeezing) | Volatility compressing. Large move imminent. |
| Price rides the upper band | Very strong uptrend (don't sell just because it's "expensive") |

**Real example — the Bollinger Squeeze:**
Marvell Technology (MRVL) in Q1 2024 showed a classic Bollinger Squeeze. The weekly bands compressed to their narrowest in 18 months over a 6-week period. This "coiling" behavior preceded a 45% breakout move. The squeeze was the early warning signal — the direction wasn't certain, but *a big move was coming*.

---

### 2.3 MACD (Moving Average Convergence Divergence)

Shown as a signal in the tech bar at the bottom of each card: **MACD: Bullish / Bearish**

**Simple explanation (the speedometer):**
MACD measures whether a stock's momentum is accelerating or decelerating. If the stock is going up faster than before → Bullish. Slowing down → Bearish.

**Mathematical definition:**

```
EMA(n) = Exponential Moving Average with period n
MACD Line    = EMA(12) − EMA(26)
Signal Line  = EMA(9) of MACD Line
Histogram    = MACD Line − Signal Line
```

An Exponential Moving Average weights recent prices more heavily:
```
EMA[t] = Price[t] × k + EMA[t-1] × (1-k)
where k = 2 / (n+1)
```

**Interpretation:**
- **Histogram > 0** → Short-term momentum is above long-term momentum → **Bullish**
- **Histogram < 0** → Short-term momentum lagging → **Bearish**

---

## 3. Fear & Greed Gauge

### Simple explanation (the crowd at an auction)

Think of the stock market as a crowd at an auction. When everyone is terrified (fear), they dump assets for whatever they can get — historically great buying opportunities. When everyone is euphoric (greed), they overbid for everything — dangerous territory for buyers.

The Fear & Greed gauge is a 0–100 score combining three market signals to measure crowd psychology for each specific stock.

| Range | Label | Meaning |
|-------|-------|---------|
| 0–25 | EXTREME FEAR 🔴 | Stock is being abandoned. Historically great buying zone |
| 25–45 | FEAR 🟠 | Cautious pessimism. Worth monitoring |
| 45–55 | NEUTRAL ⚪ | Balanced sentiment |
| 55–75 | GREED 🟡 | Elevated optimism. Be cautious |
| 75–100 | EXTREME GREED 🔴 | Euphoria. High crash risk |

### The Formula

```
FearGreed = (RSI + Stochastic + VolScore) / 3

VolScore = clamp(100 − (AnnualVol% − 15) × 1.5, 0, 100)
```

**Component 1 — RSI (0–100):**
High RSI = recent strong gains = momentum greed. See Section 7.4 for full RSI explanation.

**Component 2 — Stochastic Oscillator (0–100):**
Measures where the current price sits within its recent high/low range:
```
Stochastic = ((Current Price − Lowest Low) / (Highest High − Lowest Low)) × 100
```
Near 100 = price at top of recent range = greed. Near 0 = price at bottom = fear.

**Component 3 — VolScore (inverted volatility):**
High volatility means market participants are afraid and uncertain. So we invert it: high vol → low score → more fear. The formula starts penalizing once volatility exceeds 15% (above the typical SPY level of ~16%).

**Simple numerical example:**
- Stock RSI = 28 (oversold)
- Stochastic = 15 (at bottom of range)
- Annual volatility = 80% → VolScore = 100 − (80−15)×1.5 = 100−97.5 = 2.5
- Fear & Greed = (28 + 15 + 2.5) / 3 = **15.2 → EXTREME FEAR**

**Real semiconductor example:**
In October 2022, the semiconductor sector was in a brutal bear market. Stocks like NVDA and AMD had Fear & Greed scores of 12–18 (EXTREME FEAR). The tool was accurately signaling the generational buying opportunity. Three months later, those same stocks were up 80–120%.

---

## 4. Risk Metrics Grid

These appear at the top of the risk section on every stock card. They answer the fundamental questions about what can go wrong.

---

### 4.1 Max Drawdown (MaxDD)

**Simple explanation (the worst-case investor):**
"If I had the worst possible timing — buying at the exact peak and selling at the exact bottom — how much would I have lost?" That's Max Drawdown.

**Mathematical definition:**

```
MaxDD = min over all time t of: (P[t] − max(P[0..t])) / max(P[0..t]) × 100
```

**Step by step:**
1. Track the running maximum price seen so far (the "peak")
2. At every week, calculate: (current price − peak) / peak
3. The most negative this number ever becomes = Max Drawdown

**Simple numerical example:**

Prices over time: $100 → $130 → $150 → $90 → $80 → $120

| Week | Price | Running Peak | Drawdown |
|------|-------|-------------|---------|
| 1 | $100 | $100 | 0% |
| 2 | $130 | $130 | 0% |
| 3 | $150 | $150 | 0% |
| 4 | $90 | $150 | −40.0% |
| 5 | $80 | $150 | −46.7% ← MaxDD |
| 6 | $120 | $150 | −20.0% |

**MaxDD = −46.7%** — the worst peak-to-trough loss in history.

**Real semiconductor example:**
During the 2022 semiconductor bear market:
- AMD: MaxDD ≈ −65% from November 2021 peak
- NVDA: MaxDD ≈ −66%
- TSMC: MaxDD ≈ −50%

This means RSU grants made at the peak in late 2021 were underwater by up to two-thirds a year later.

**Why it matters for RSU planning:**
If a company's historical MaxDD is −70%, a 4-year RSU grant made at the peak might spend years deeply underwater. Understanding this distribution of outcomes helps you decide:
- Should I sell RSUs immediately on vest or hold?
- How much of my net worth can be in this single stock?

**Color coding:** Always shown in red. It's always a loss.

---

### 4.2 Value at Risk — VaR 95% (Weekly Parametric)

**Simple explanation (the weather forecast for losses):**
"There is a 95% chance my weekly loss will be smaller than X%. In the worst 5% of weeks, I will lose at least X%."

VaR is the most widely used risk metric in professional finance. Every bank, hedge fund, and asset manager calculates VaR. We compute it weekly.

**Mathematical definition (Parametric / Gaussian VaR):**

```
VaR 95% = −(μ_weekly − 1.645 × σ_weekly) × 100
```

Where:
- μ_weekly = mean of all weekly returns
- σ_weekly = standard deviation of all weekly returns
- 1.645 = the 5th percentile of the standard normal distribution (z-score)

**Simple numerical example:**

Stock has:
- Mean weekly return: +0.3%
- Weekly std deviation: 5.0%

```
VaR 95% = −(0.3% − 1.645 × 5.0%) = −(0.3% − 8.23%) = +7.93%
```

Interpretation: In the worst 5% of weeks, you lose **at least 7.93%** of your portfolio.

**Real example:**
ASML (ASML), the Dutch monopoly on EUV chip-making equipment, had weekly VaR95 of ~−6% in 2023. This is notably lower than the typical −10 to −15% seen in more volatile semiconductor stocks like MXL or COHR, reflecting ASML's near-monopoly pricing power and predictable revenue.

> **Important caveat:** Parametric VaR assumes returns follow a normal (bell curve) distribution. They don't. Real returns have fat tails — crashes happen more often than the normal distribution predicts. This is why we also compute CF mVaR and CVaR. See Section 5.1.

---

### 4.3 Sortino Ratio

**Simple explanation (the unfair penalty):**
Standard Sharpe Ratio penalizes you equally for going up 30% in a week (great!) and going down 30% (terrible!). That's unfair — you don't mind upside volatility. The Sortino Ratio fixes this by only penalizing **downside volatility**.

**Mathematical definition:**

```
Sortino Ratio = (Annualized Return − Risk-Free Rate) / Downside Deviation

Downside Deviation = sqrt( sum(r²) for all negative weeks / total weeks ) × sqrt(52)
```

Note the denominator: we include only negative weekly returns in the squared sum, but divide by the **total** number of weeks. This correctly penalizes the frequency AND magnitude of losses.

The risk-free rate used is **4.5%** (approximate US 10-year Treasury yield).

**Interpretation table:**

| Sortino | Quality |
|---------|---------|
| < 0 | Worse than risk-free rate given downside risk |
| 0.0–0.5 | Poor |
| 0.5–1.0 | Below average |
| 1.0–2.0 | Good. Institutional quality |
| 2.0–3.0 | Excellent |
| > 3.0 | Exceptional. Rare. |

**Simple numerical example:**

Stock A: Annual return 20%, Downside deviation 8%
```
Sortino A = (20% − 4.5%) / 8% = 15.5/8 = 1.94 ← GOOD
```

Stock B: Annual return 35%, Downside deviation 25%
```
Sortino B = (35% − 4.5%) / 25% = 30.5/25 = 1.22 ← WORSE
```

Despite Stock B having higher raw returns, Stock A is a better risk-adjusted investment. This is the entire point of the Sortino Ratio.

**Real semiconductor example:**
MACOM Technology (MTSI) during its recovery phase showed Sortino of ~2.73 — exceptional for a semiconductor stock. This meant the gains dramatically outweighed the downside risk. In contrast, MaxLinear (MXL) with its high volatility often shows Sortino below 1.0, indicating the downside risk isn't being well-compensated by returns.

---

### 4.4 RSI (Relative Strength Index) — shown in tech bar

**Simple explanation (the tired runner):**
A runner sprinting at full speed for 10 minutes can't sustain that pace. They'll slow down. RSI applies this "fatigue" concept to stock prices. A stock that has surged every week for months is "tired" and likely to slow down or reverse.

**Mathematical definition:**

```
RSI = 100 − 100 / (1 + RS)

RS = Average Gain (up weeks) / Average Loss (down weeks) over last 14 weeks
```

More precisely, it uses Wilder's smoothing method where the initial average is the simple average, and subsequent values use:
```
Avg Gain[t] = (Avg Gain[t-1] × 13 + Gain[t]) / 14
```

**RSI Scale:**

| RSI | Signal | Meaning |
|-----|--------|---------|
| < 30 | 🟢 Oversold | Stock has fallen rapidly. Reversal likely. Contrarian buy. |
| 30–45 | Mild oversold | Possible opportunity |
| 45–55 | Neutral | No strong signal |
| 55–75 | Bullish | Uptrend in progress |
| > 75 | 🔴 Overbought | Stock has risen rapidly. Reversal likely. Caution. |

**Real semiconductor example:**
NVDA's RSI timeline during the AI boom:
- Oct 2022: RSI 28 (EXTREME OVERSOLD) → Perfect buy signal
- Mar 2023: RSI 58 (neutral) → Safe to hold
- Jun 2023: RSI 82 (OVERBOUGHT) → Caution signal. Stock did correct 20% over next 6 weeks.
- Nov 2023: RSI 72 → Again getting extended

---

### 4.5 Stochastic Oscillator — shown in tech bar

**Simple explanation (where are you in the room):**
If someone walks between a 5-foot and 6-foot-tall person, and their height is 5.8 feet, they're at the 80th percentile of that range. Stochastic tells you: where is the current price relative to the recent high-low range?

**Mathematical definition:**

```
Stochastic = (Close − Lowest Low[14wk]) / (Highest High[14wk] − Lowest Low[14wk]) × 100
```

**Interpretation:**
- Near 100: Price at top of recent range → Overbought/Greed
- Near 0: Price at bottom of recent range → Oversold/Fear

---

## 5. Advanced Quant Analytics

These appear in the lower section of the risk grid on each card. Color-coded purple and cyan to distinguish them from basic metrics.

---

### 5.1 Cornish-Fisher Modified VaR (CF mVaR 95%)

**The problem with standard VaR:**
The z-score of 1.645 in standard VaR assumes stock returns follow a perfect bell curve. They don't. Real returns have:
- **Negative skewness**: Crashes are more common and severe than rallies
- **Excess kurtosis (fat tails)**: Extreme events happen far more often than the bell curve predicts

**The Cornish-Fisher expansion:**
William Cornish and Ronald Fisher (1938) developed a way to adjust the z-score based on the actual higher moments of the distribution.

**Mathematical definition:**

```
z_CF = z + (1/6)(z²-1)S + (1/24)(z³-3z)K − (1/36)(2z³-5z)S²

CF mVaR = −(μ + z_CF × σ)
```

Where:
- z = −1.645 (standard 5% z-score)
- S = skewness of the return distribution
- K = excess kurtosis (kurtosis − 3)
- μ = mean weekly return
- σ = standard deviation of weekly returns

**Intuition with an example:**

Stock has:
- Normal VaR95 = −8% (assuming bell curve)
- Skewness = −1.2 (negatively skewed — crashes harder than it rallies)
- Excess kurtosis = +2.0 (fatter tails than normal)

With the CF adjustment, the z-score shifts from −1.645 toward a more negative number, producing:
- CF mVaR95 = −13% (vs −8% standard)

The Cornish-Fisher adjustment revealed an additional 5% of hidden tail risk that the standard VaR completely missed.

**Real semiconductor example:**
MaxLinear (MXL) shows:
- Standard VaR 95% (weekly) = −25.8%
- CF mVaR 95% (weekly) = −19.3%

Wait — CF mVaR is actually *smaller* in magnitude here? That's because skewness and kurtosis can go either direction. In MXL's case, the distribution has *positive* tail adjustment (the extreme upside weeks are big too), partially offsetting the downside fat tail. This is why the VaR Stress Test chart (Chart 9) showing all 5 measures together is more informative than any single number.

> **Key principle:** When JB test (Section 5.2) is high, standard VaR is unreliable. CF mVaR is the more honest single-number risk estimate.

---

### 5.2 Jarque-Bera Test (JB Statistic)

**Simple explanation (the normality detector):**
The Jarque-Bera test is a formal statistical hypothesis test. The null hypothesis is: "This distribution is normal (bell-curved)." A high JB score means we reject that hypothesis — the distribution has significant skewness and/or kurtosis that make standard risk models unreliable.

**Mathematical definition:**

```
JB = (n/6) × (S² + (K−3)²/4)
```

Where:
- n = number of weekly observations
- S = skewness
- K = kurtosis (K−3 is excess kurtosis)

**Interpretation:**

| JB Value | Assessment |
|----------|-----------|
| < 5 | Nearly normal. Standard risk models are reliable. |
| 5–20 | Mild non-normality. Use CF mVaR alongside standard VaR. |
| 20–100 | Significant non-normality. CF mVaR and CVaR are essential. |
| > 100 | Extreme non-normality. Heavy tail crash risk. Standard VaR is dangerously misleading. |

**Understanding Skewness:**

```
Skewness S = (1/n) × Σ((r-μ)/σ)³
```

- S = 0: Symmetric distribution (normal)
- S < 0: **Negative skew** — the left tail is longer. The stock crashes harder than it rallies. Most semiconductor stocks have negative skew during bear markets.
- S > 0: **Positive skew** — the right tail is longer. Occasional big wins with smaller, more frequent losses. (Think lottery tickets, but also options and small-cap biotech.)

**Understanding Kurtosis:**

```
Kurtosis K = (1/n) × Σ((r-μ)/σ)⁴
```

- K = 3: Normal distribution (baseline)
- K > 3 (Excess K > 0): **Leptokurtic / Fat tails** — extreme events happen more often than normal. The distribution has a taller center and fatter tails. Most financial returns have K of 4–8.
- K < 3: Thin tails (rare in practice for stocks)

**Simple visual analogy:**

Normal distribution = gentle rolling hills with predictable heights.
Leptokurtic = very flat central plain with sudden, tall, jagged mountain peaks at the edges.

**Real semiconductor example:**
- COHR (Coherent Corp): JB ≈ 2.5 → Nearly normal. Sharpe ratio is meaningful.
- MACOM (MTSI): JB ≈ 56.4 → Highly non-normal. MACOM makes occasional huge moves (big contract wins, tech breakthroughs) that make its distribution look nothing like a bell curve. A standard Sharpe ratio would completely understate its true risk/reward.

---

### 5.3 Omega Ratio

**Simple explanation (the totals ledger):**
At the end of the year, add up every dollar you made in up-weeks. Add up every dollar you lost in down-weeks. Divide the gains by the losses. That's the Omega Ratio.

Unlike every other ratio, Omega makes zero assumptions about the shape of the return distribution. It just counts the actual money.

**Mathematical definition:**

```
Ω(τ) = Σ(r_i − τ) for r_i > τ
        ÷
        Σ(τ − r_i) for r_i < τ
```

Where τ is the threshold (we use τ = 0, meaning: beating doing nothing).

**Properties of Omega:**

1. **Ω > 1**: You make more money in winning weeks than you lose in losing weeks (before compounding). Good.
2. **Ω = 1**: Exactly break-even. Every winning week perfectly cancelled by a losing week.
3. **Ω < 1**: You lose more than you gain. Bad.
4. **Ω = ∞**: If there are literally no losing weeks (impossible in practice but theoretically...)
5. **No distributional assumptions** — this is Omega's superpower. Sharpe assumes normality. Omega doesn't.

**Simple numerical example:**

10 weekly returns: +5%, −2%, +8%, −1%, +3%, −4%, +6%, −3%, +2%, −1%

Sum of gains (τ=0): 5+8+3+6+2 = **24%**
Sum of losses (τ=0): 2+1+4+3+1 = **11%**

```
Omega = 24% / 11% = 2.18
```

For every 1% lost, the stock historically gained 2.18%. Strong positive asymmetry.

**Interpretation table:**

| Omega | Quality |
|-------|---------|
| < 0.8 | Losing strategy |
| 0.8–1.2 | Roughly break-even |
| 1.2–1.5 | Marginal positive edge |
| 1.5–2.0 | Good |
| > 2.0 | Excellent asymmetric return |

**Real semiconductor example:**
Lumentum Holdings (LITE) during its optical networking recovery: Omega ≈ 2.52. This means for every 1% of weekly losses, LITE produced 2.52% of weekly gains historically. Strong positive skew in the return stream.

---

### 5.4 Hurst Exponent

**Simple explanation (the trending vs bouncing detector):**

Flip a fair coin repeatedly. Heads = stock goes up. Tails = stock goes down. Each flip is independent of the last — pure random walk. No predictability.

Now imagine a stock that "trends": if it went up this week, it's *slightly more likely* to go up next week. Or a stock that "mean-reverts": if it went up a lot, it's *slightly more likely* to come down.

The Hurst Exponent H (developed by Harold Hurst studying the Nile River in 1951) detects exactly which regime a time series is in.

**Mathematical definition (Rescaled Range Analysis):**

```
1. Compute log returns: r[t] = ln(P[t]/P[t-1])
2. Compute mean return: μ
3. Build cumulative deviation series: Y[t] = Σ(r[i] − μ) from i=1 to t
4. Range: R = max(Y) − min(Y)
5. Standard deviation: S = std(r)
6. H = log(R/S) / log(n)
```

**Hurst Exponent Interpretation:**

| H | Regime | Meaning | Strategy |
|---|--------|---------|----------|
| H < 0.4 | Strong mean-reversion | Extreme moves reverse. Anti-persistent. | Buy dips, sell rips. |
| 0.4–0.5 | Mild mean-reversion | Slight tendency to reverse | Slight contrarian lean |
| H = 0.5 | Pure random walk | No predictability | Standard passive investing |
| 0.5–0.6 | Mild trending | Slight tendency to continue | Slight momentum lean |
| H > 0.6 | Strong trending | Moves persist. Buy winners. | Momentum / trend-following |
| H > 0.7 | Very strong trend | Very predictable trends | Aggressive trend-following |

**Simple numerical intuition:**

If H = 0.7:
- After a big up week, there's a ~60% chance next week is also positive
- After a sustained 3-week run, momentum is even more likely to continue

If H = 0.3:
- After a big up week, there's a ~65% chance next week reverses
- Mean-reversion strategy: short after 3 consecutive up weeks

**Real semiconductor examples:**

- NVIDIA (NVDA) during the AI boom 2023-2024: H ≈ 0.68 → Strong trending. The AI narrative created persistent momentum. "Buy the trend" strategies worked exceptionally well.
- A small-cap semiconductor trading in a range (H ≈ 0.38) → Mean-reverting. The optimal strategy is completely different: buy at the lower Bollinger Band, sell at the upper band.

---

### 5.5 Autocorrelation (Lag-1)

**Simple explanation (does history repeat?):**
Autocorrelation at lag-1 measures the linear correlation between this week's return and last week's return. If last week was +8% and this week tends to be positive too, autocorrelation is positive (momentum). If last week being +8% tends to predict a negative this week, autocorrelation is negative (mean-reversion).

**Mathematical definition:**

```
ρ₁ = Σ[(r[t] − μ)(r[t-1] − μ)] / Σ[(r[t-1] − μ)²]
    for t = 2 to n
```

This is literally the Pearson correlation coefficient between the returns series and the same series shifted by one period.

**Interpretation:**

| Autocorrelation | Meaning | Trading implication |
|-----------------|---------|---------------------|
| 0.3 to 0.5 | Strong positive momentum | Last week up → This week likely up |
| 0.1 to 0.3 | Mild positive momentum | Slight trend continuation |
| −0.1 to 0.1 | Near-zero / random | No predictability from lag-1 |
| −0.1 to −0.3 | Mild mean-reversion | Slight reversal tendency |
| −0.3 to −0.5 | Strong mean-reversion | Big moves tend to reverse next week |

**Real semiconductor examples:**

During earnings season in the semiconductor sector, you often see positive lag-1 autocorrelation (~0.15-0.20) as strong results from one company generate multiple weeks of positive momentum. After the sector rotates out of favor, autocorrelation often turns slightly negative as the initial down moves create oversold conditions that bounce.

Autocorrelation > 0.3 in weekly data for an individual stock is actually unusual and suggests either a structural trend or data quality issues.

---

### 5.6 Ulcer Index

**Simple explanation (the stress meter):**
Max Drawdown tells you the worst single moment of pain. Ulcer Index tells you how *continuously painful* the investment has been over time. A stock that falls 20% and immediately recovers is fine — brief pain. A stock that falls 20% and stays there for 8 months has a very high Ulcer Index — chronic suffering.

Peter Martin invented it in 1987 (published in "The Investor's Guide to Fidelity Funds"). The name captures the key insight: prolonged drawdowns are what give investors actual stomach ulcers.

**Mathematical definition:**

```
Ulcer Index = sqrt( Σ(D[t]²) / n ) × 100

where D[t] = (P[t] − Peak[t]) / Peak[t]  (the drawdown fraction at time t)
```

**Key properties:**
1. Uses the square of drawdowns → deeper drawdowns are penalized disproportionately
2. Averages over all weeks → captures duration, not just depth
3. A drawdown that is twice as deep contributes 4x to the Ulcer Index (because of squaring)

**Simple numerical example:**

Stock A: Falls 20% for 2 weeks, then recovers
- Week 1: D = −0.10 → D² = 0.01
- Week 2: D = −0.20 → D² = 0.04
- Average D² = 0.025 over 50 weeks total = 0.025×2/50 = 0.001
- Ulcer = sqrt(0.001) × 100 = **3.16** (low pain — brief dip)

Stock B: Falls 20% and stays there for 20 weeks
- 20 weeks at D² = 0.04
- Over 50 weeks: average D² = 20×0.04/50 = 0.016
- Ulcer = sqrt(0.016) × 100 = **12.65** (much higher pain — chronic suffering)

**Interpretation:**

| Ulcer Index | Experience |
|-------------|-----------|
| < 5 | Low pain. Brief, shallow drawdowns |
| 5–10 | Moderate. Typical for high-quality growth stock |
| 10–20 | High pain. Extended or deep drawdowns |
| > 20 | Very high pain. Multiple bear phases |
| > 40 | Extreme. Speculative stock in sustained bear market |

**Real example:**
GlobalFoundries (GFS) during the 2022-2023 bear market had an Ulcer Index exceeding 28 — investors spent nearly the entire period in sustained drawdown. TSMC in the same period had Ulcer ≈ 18 despite a similar decline, because it began recovering faster.

---

### 5.7 Tail Ratio

**Simple explanation (is the upside bigger than the downside):**
In the best 5% of weeks, how much does this stock gain? In the worst 5% of weeks, how much does it lose? The ratio of those two numbers is the Tail Ratio. Above 1.0 means the upside surprises are bigger than the downside surprises — great asymmetry.

**Mathematical definition:**

```
Tail Ratio = |P₉₅| / |P₅|
```

Where P₉₅ is the 95th percentile of returns and P₅ is the 5th percentile (the worst 5% of weeks).

**Interpretation:**

| Tail Ratio | Meaning |
|-----------|---------|
| < 0.7 | Crashes much worse than rallies. High skew risk. |
| 0.7–1.0 | Slight negative asymmetry |
| 1.0 | Perfectly symmetric tails |
| 1.0–1.5 | Good. Upside tail slightly bigger |
| 1.5–2.0 | Good positive asymmetry |
| > 2.0 | Excellent. Best weeks far exceed worst weeks |

**Simple example:**
- Best 5% of weeks average: +12%
- Worst 5% of weeks average: −8%
- Tail Ratio = 12/8 = **1.5** — positive asymmetry. When this stock moves big, it more often moves big up than big down.

---

## 6. S&P 500 Benchmarking Grid

This entire section compares each stock to the S&P 500 (using SPY ETF as proxy). The fundamental question: **Is this stock worth holding vs. just buying an index fund?**

---

### 6.1 Beta (vs SPY)

**Simple explanation (the amplifier):**
Beta measures how much the stock amplifies or dampens market moves. If the S&P 500 moves 1%, how much does this stock move?

- Beta = 1.0 → Moves exactly with the market
- Beta = 2.0 → Moves twice as much (up OR down)
- Beta = 0.5 → Moves half as much
- Beta = 0 → No correlation to market (independent)
- Beta < 0 → Moves opposite to market (very rare)

**Mathematical definition:**

```
β = Cov(r_stock, r_market) / Var(r_market)
  = ρ × (σ_stock / σ_market)
```

Where ρ is the correlation between stock and market returns.

**Simple numerical example:**

| Week | SPY | Stock |
|------|-----|-------|
| 1 | +2% | +4% |
| 2 | −3% | −6% |
| 3 | +1% | +2% |
| 4 | −1% | −2% |

The stock consistently moves exactly 2× the market → **Beta ≈ 2.0**

**Typical semiconductor betas:**

| Company Type | Typical Beta |
|-------------|-------------|
| TSMC (monopoly, defensive revenue) | 1.2–1.6 |
| NVDA (high growth, AI-driven) | 1.5–2.0 |
| Fabless mid-cap (MRVL, MXCHIP) | 1.8–2.5 |
| Small-cap speculative (MXL, COHU) | 2.0–3.5 |

**Color coding:**
- Beta > 1.2 → 🔴 Red (high systematic risk)
- Beta 0.8–1.2 → 🟢 Green (market-proportional)
- Beta < 0.8 → 🟡 Yellow (defensive; but may underperform in bull runs)

**RSU implication:** A company with Beta = 3.0 means a 10% market crash leads to a ~30% stock crash. If your RSUs have a 4-year cliff, a bad market environment could wipe out years of comp. Understanding Beta helps size the risk.

---

### 6.2 Annual Alpha (Jensen's Alpha)

**Simple explanation (the skill bonus):**
If you hire a portfolio manager who invests only in very risky stocks (Beta = 2), and markets went up 20%, you'd expect their portfolio to go up ~40%. If it went up 45%, that extra +5% is their skill premium — their Alpha.

Alpha answers: *"How much did this stock earn BEYOND what its risk level (Beta) deserved?"*

**Mathematical definition (Jensen's Alpha, 1968):**

```
α = R_stock − [R_f + β × (R_market − R_f)]
```

Where:
- R_stock = annualized stock return
- R_f = risk-free rate (4.5%, US Treasury)
- β = Beta vs SPY
- R_market = SPY annualized return
- The bracket term = "CAPM expected return" — the return Beta alone should deliver

**Step-by-step example:**

Given: Stock returned 32% annually. Beta = 2.0. SPY returned 15%. Rf = 4.5%

```
CAPM expected return = 4.5% + 2.0 × (15% − 4.5%)
                     = 4.5% + 2.0 × 10.5%
                     = 4.5% + 21%
                     = 25.5%

Alpha = 32% − 25.5% = +6.5% ← Outperformed by 6.5%!
```

**Interpretation:**

| Alpha | Meaning |
|-------|---------|
| > +5% | 🟢 Strong alpha generation. Company has structural competitive advantages. |
| 0% to +5% | Slight outperformance. |
| −2% to 0% | Slight underperformance. May be noise. |
| < −5% | 🔴 Persistent underperformance. Destroys value vs risk-free investment. |

**Real examples:**
- TSMC: Historical alpha +8–15% → Semiconductor manufacturing monopoly moat
- ARM Holdings: Alpha varies widely with licensing cycle
- Speculative small-caps: Often negative alpha despite high volatility

**Color coding:** 🟢 positive, 🔴 negative.

---

### 6.3 R-Squared (R²)

**Simple explanation (the market puppet string):**
What percentage of this stock's movements can be explained by the S&P 500? How much is it a "market puppet" vs. having its own independent story?

- R² = 0.9 (90%): 90% of the stock's weekly moves are explained by market moves. It's essentially a leveraged index fund.
- R² = 0.1 (10%): Only 10% explained by market. The stock has its own independent narrative.

**Mathematical definition:**

```
R² = Cov²(r_stock, r_market) / (Var(r_stock) × Var(r_market))
   = ρ²
```

R² is literally the square of the Pearson correlation coefficient between stock and market returns.

**Practical implications:**

| R² | Meaning |
|-----|---------|
| > 0.8 | Highly market-driven. Alpha less reliable (stock just amplifies market). |
| 0.4–0.8 | Mixed. Both market and company-specific factors drive returns. |
| < 0.4 | Company-specific. Earnings, products, management drive price more than macro. |
| < 0.1 | Nearly independent of market. Alpha calculation is statistically uncertain. |

**For RSU decision:** If R² is high (>0.7), your RSU is essentially a leveraged bet on the stock market with extra volatility. If R² is low (<0.3), you're taking company-specific risk — the company's own success (or failure) dominates.

---

### 6.4 Treynor Ratio

**Simple explanation (return per market risk unit):**
Sharpe divides return by *total* volatility. But if you hold this stock as part of a diversified portfolio, company-specific volatility gets diversified away. Only *market risk (Beta)* remains undiversifiable. Treynor divides return only by Beta — the irreducible market risk you can't escape.

**Mathematical definition:**

```
Treynor Ratio = (Annualized Return − Risk-Free Rate) / Beta
```

**Simple comparison example:**

| Stock | Return | Beta | Treynor |
|-------|--------|------|---------|
| Stock A | 25% | 2.0 | (25-4.5)/2.0 = 10.25 |
| Stock B | 15% | 0.8 | (15-4.5)/0.8 = 13.1 |
| SPY | 14% | 1.0 | (14-4.5)/1.0 = 9.5 |

Stock B has lower raw returns but higher Treynor — it's a better investment if held in a diversified portfolio. Stock B offers more return per unit of market risk.

**Color coding:** Green if Treynor > 0.05 (above threshold of meaningful positive return per beta unit), red otherwise.

---

### 6.5 Upside / Downside Capture Ratios

**Simple explanation (the asymmetric participation test):**

**Upside Capture = 150%** means: "When the S&P 500 goes up, this stock captures 150% of that gain."
**Downside Capture = 60%** means: "When the S&P 500 falls, this stock only falls 60% as much."

Together, these two numbers tell you the most important thing: **Does this stock participate disproportionately in market gains while cushioning against market losses?**

**Mathematical definition:**

```
Upside Capture = Avg(stock return | SPY return > 0)
               ÷ Avg(SPY return | SPY return > 0) × 100

Downside Capture = Avg(stock return | SPY return < 0)
                 ÷ Avg(SPY return | SPY return < 0) × 100
```

**The 4 quadrants:**

| Upside | Downside | Quadrant | Description |
|--------|----------|----------|-------------|
| > 100% | < 100% | ⭐ IDEAL | Wins more in rallies, loses less in crashes |
| > 100% | > 100% | ⚡ VOLATILE | More of everything — high Beta play |
| < 100% | < 100% | 🛡️ DEFENSIVE | Conservative — underperforms in rallies, cushions crashes |
| < 100% | > 100% | 🔴 WORST | Misses the gains, amplifies the losses. Avoid. |

**Real semiconductor examples:**

- **Coherent Corp (COHR)**: Upside 250%, Downside 73% → Almost perfectly ideal. Captured the optical networking boom while being resilient in downturns.
- **TSMC (TSM)**: Upside ~120%, Downside ~65% → Consistently asymmetric over multiple cycles. Reflects TSMC's pricing power and essential position in the supply chain.
- **GlobalFoundries (GFS)**: Upside ~80%, Downside ~130% → Worst quadrant in certain periods. Missed gains, amplified losses.

**Color coding:** Up Capture: green if >100%, yellow otherwise. Down Capture: green if <100%, red otherwise.

---

### 6.6 Information Ratio (IR)

**Simple explanation (the consistency champion):**
Alpha measures if a stock beats the market. Information Ratio measures *how consistently* it beats the market. You can be lucky once. IR penalizes inconsistency.

**Mathematical definition:**

```
IR = (Mean weekly excess return) / (Std dev of weekly excess return) × sqrt(52)

Where excess return = stock return − SPY return each week
```

This is literally the Sharpe Ratio of the excess return stream (active return relative to the benchmark).

**Interpretation:**

| IR | Quality |
|----|---------|
| < 0 | Consistently underperforms SPY |
| 0–0.3 | Slight positive alpha, but inconsistent |
| 0.3–0.5 | Good active management quality |
| 0.5–0.75 | Excellent |
| > 0.75 | Outstanding. Top-quartile hedge fund quality. |

**Simple example:**

Stock beats SPY by 1% per week on average, but the week-to-week difference ranges from −5% to +8%:

```
Mean excess = 1%
Std excess = 3%
IR = (1% / 3%) × sqrt(52) = 0.333 × 7.21 = 2.4 (annualized)
```

Wait — that seems high. In reality, even a consistent +1% weekly excess return is extraordinary and unsustainable. Most stocks show much smaller average excess returns.

---

### 6.7 Tracking Error

**Simple explanation (the wandering distance):**
How far does this stock wander from the S&P 500 path? Low tracking error = stays close to the index. High tracking error = takes its own journey.

**Mathematical definition:**

```
Tracking Error = Std Dev(stock return − SPY return each week) × sqrt(52)
```

This is the annualized standard deviation of the active return.

| Tracking Error | Context |
|---------------|---------|
| 0% | Is the index (impossible for individual stocks) |
| 1–5% | Almost passive. Very correlated to market. |
| 10–20% | Moderate active share |
| 30–50% | High idiosyncratic behavior. Company-specific drivers dominant. |
| > 50% | Very independent. Semiconductor mid/small-caps often here. |

---

### 6.8 Correlation to SPY

The Pearson correlation coefficient between weekly stock returns and SPY:

```
ρ = Cov(r_stock, r_SPY) / (σ_stock × σ_SPY)
  = sign(β) × sqrt(R²)
```

Ranges from −1 to +1. A simple reading guide:

| Correlation | Meaning |
|-------------|---------|
| 0.8–1.0 | Moves almost identically with market |
| 0.5–0.8 | Broadly follows market with meaningful independence |
| 0.2–0.5 | Partially independent. Company-specific factors important. |
| < 0.2 | Mostly independent of market direction |
| Negative | Moves opposite to market (very unusual for equities) |

---

## 7. Quant & Trading Grid

---

### 7.1 Quant Score (0–100)

The Quant Score is the terminal's proprietary composite signal — a single number summarizing all quantitative inputs for quick screening.

**Construction (additive model):**

```
Base Score = 50 (neutral starting point)

Positive factors:
+ 8  if 6-month return > 0
+ 8  if 1-year return > 0
+12  if MACD histogram > 0 (bullish momentum)
+18  if momentum = OVERSOLD (contrarian opportunity)
+ 8  if Fear & Greed < 30 (extreme fear = buy zone)
+ 8  if Sortino > 1.5 (good risk-adjusted performance)
+ 6  if Sharpe > 1.0
+ 5  if SMA10 > SMA40 (Bull Cross)
+ 8  if Alpha > 0.05 (outperforming market after beta adjustment)

Negative factors:
−18  if momentum = OVERBOUGHT (caution)
−12  if Fear & Greed > 80 (extreme greed = sell zone)
− 8  if Alpha < 0 (underperforming market)

Final Score = clamp(result, 5, 99)
```

**Card color coding:**

| Score | Border Color | Interpretation |
|-------|-------------|----------------|
| 70–99 | 🟢 Green "BUY" | Multiple bullish factors aligned simultaneously |
| 40–69 | ⚪ No border | Mixed signals |
| 0–35 | 🔴 Red "SELL" | Multiple bearish factors aligned |

**Important caveat:** This is a quantitative signal based on price action and risk metrics — NOT a fundamental analysis (P/E ratios, revenue growth, management quality). Use it to filter and rank stocks, not as a sole investment decision.

---

### 7.2 Sharpe Ratio

**Simple explanation (the risk-adjusted return):**
"I made 25% last year." But what if you took enormous risks to get there? What if you had months of 30% swings? The Sharpe Ratio normalizes returns by the total volatility experienced.

**Mathematical definition (William Sharpe, Nobel Prize 1990):**

```
Sharpe = (Annualized Return − Risk-Free Rate) / Annualized Volatility
       = (R_p − R_f) / σ_p
```

**The key difference from Sortino:** Sharpe penalizes ALL volatility — including upside surprises. Sortino only penalizes downside volatility. For semiconductor stocks with asymmetric return distributions, Sortino is generally more informative.

**Example:**

Stock A: 20% return, 15% vol → Sharpe = (20−4.5)/15 = **1.03**
Stock B: 30% return, 30% vol → Sharpe = (30−4.5)/30 = **0.85**

Despite B's higher return, A has better risk-adjusted performance.

**Benchmark:** The S&P 500 long-run Sharpe is approximately 0.5–0.6. Any stock above 1.0 is outperforming the market on a risk-adjusted basis.

---

### 7.3 Annual Volatility

The core risk measure. Measures the typical annual range of returns.

```
Ann. Volatility = Std Dev(weekly returns) × sqrt(52)
```

The sqrt(52) converts weekly standard deviation to annual (using the square-root-of-time rule, which assumes independent weekly returns).

**Reference benchmarks:**

| Asset | Typical Annual Volatility |
|-------|--------------------------|
| US Treasury bonds | 5–8% |
| S&P 500 (SPY) | 14–20% |
| TSMC (large-cap semi) | 30–45% |
| NVDA (AI-driven growth) | 45–70% |
| MXL (small-cap semi) | 80–150% |
| Individual startup stock | 100–200%+ |

The card label shows the S&P 500 baseline for immediate comparison: `Ann. Vol (SPY: 16%)`.

---

### 7.4 Fibonacci Support Level (61.8%)

Fibonacci retracement levels come from the golden ratio. In Fibonacci sequence (1,1,2,3,5,8,13...), dividing consecutive terms approaches 0.618 (and its complement 0.382). Traders believe price levels corresponding to these ratios act as support/resistance.

```
Fib 61.8% Level = High − (High − Low) × 0.618
```

Where High and Low are the 52-week high and low prices.

This level represents where a stock "should" find buyers if it's correcting from a trend — a meaningful support zone to watch for reversal signals.

---

### 7.5 Monte Carlo Scenarios (6-Month Projections)

**MC 6M Median:** Most likely 6-month price outcome (50th percentile of 2000 simulated paths)
**MC Bull 90%:** Optimistic scenario (90th percentile)
**MC Bear 10%:** Pessimistic scenario (10th percentile)

See Section 12 for the full mathematical explanation of the Merton Jump-Diffusion model used to generate these simulations.

**Quick interpretation:**
- MC Median > Current Price → Historical drift suggests mild upside in 6 months
- MC Bull / MC Bear spread → Wide spread = high uncertainty (high volatility stock)

---

## 8. Detail Modal — 9 Charts

Clicking any stock card opens the full-screen detail modal with 9 professional charts.

---

### Chart 1: Price Action + SMA40 + Bollinger Bands

**Full explanation:** See Section 2. This is the master reference chart showing 52 weeks of price history, the long-term trend (SMA40), and the statistical volatility envelope (Bollinger Bands).

**Pro tips:**
- If price is pressing against the UPPER band while SMA40 is rising → Very strong bull trend. Don't automatically sell just because price seems "high."
- If price breaks BELOW the lower band on HIGH volume → Possible panic selling. Contrarian opportunity.
- Watch for the "Bollinger Squeeze" → bands narrowing to their tightest point. This always precedes a big move.

---

### Chart 2: Underwater Drawdown

**What it shows:** A red-filled area chart sitting at 0% when the stock is at or above its prior peak, dropping negative when underwater.

**Mathematical construction:**
```
For each week t:
  Peak[t] = max(Price[0..t])
  Drawdown[t] = (Price[t] − Peak[t]) / Peak[t] × 100
```

**How to read the shape:**

| Pattern | Interpretation |
|---------|----------------|
| Brief, V-shaped dip (−10 to −20%, recovers in <6 weeks) | Healthy. Temporary fear response. |
| Long, flat trench at −30 to −40% for >6 months | Sustained bear market. Structural risk. |
| Multiple distinct trenches, each recovering | Cyclical stock. Works well for semiconductor capex cycles. |
| Deepening trench never recovering in data window | Caution. Stock still in downtrend. |

**RSU planning use:** If you're considering joining a company, look at this chart. A stock with one deep trench that fully recovered shows resilience. A stock with multiple sustained trenches shows it regularly spends long periods underwater — your RSU vesting windows may overlap with those periods.

---

### Chart 3: Weekly Returns Distribution (Histogram + Normal Overlay)

**What it shows:** A histogram of all weekly returns grouped into 2% bins from −20% to +20%, with a theoretical normal distribution overlaid in white.

**How to read it:**

The histogram shows what actually happened. The white curve shows what SHOULD happen if returns were normally distributed.

**Pattern recognition:**

| Pattern | Statistical Name | Meaning |
|---------|-----------------|---------|
| Bars match curve closely | Normal | Standard risk models accurate |
| Bars extend far LEFT beyond curve | Negative skew / fat left tail | Crash risk worse than models predict. Use CF mVaR. |
| Bars extend far RIGHT beyond curve | Positive skew | Occasional large gains. |
| Very tall center bar, thin everywhere else | Leptokurtic | Stock mostly flat with rare extreme moves. High JB score. |
| Short center bar, wide spread | Platykurtic | More uniformly distributed. Less extreme. |

**The white normal curve is calibrated to the stock's actual mean and std dev** — so any deviation from the white curve is genuine non-normality in the data.

---

### Chart 4: 26-Week Rolling Volatility (Annualized)

**Construction:**
For each week t, compute the standard deviation of the 26 weekly returns ending at week t, then annualize:
```
Rolling Vol[t] = StdDev(r[t-25..t]) × sqrt(52)
```

**Volatility regimes and what they signal:**

| Vol Level | Condition | Implication |
|-----------|-----------|-------------|
| Rising sharply | Vol expansion | Uncertainty growing. Options expensive. Risk rising. |
| Elevated but falling | Vol normalization | Fear subsiding. Possible buying opportunity ahead. |
| Very low and stable | Vol compression / Squeeze | Big move is coming — direction unknown. |
| Spike then rapid fall | Earnings or event volatility | VIX crush. Options were expensive before, now cheap. |

**Why 26-week rolling?** A 26-week (6-month) window balances responsiveness to recent conditions against statistical stability (needs enough data points to compute a meaningful standard deviation).

---

### Chart 5: 26-Week Rolling Beta (vs SPY)

**Construction:**
For each week t, compute covariance of stock returns vs SPY returns over the previous 26 weeks:
```
Rolling Beta[t] = Cov(r_stock[t-25..t], r_SPY[t-25..t]) / Var(r_SPY[t-25..t])
```

**Critical insight — Beta is not constant:**
During the 2022 bear market, the rolling beta of many semiconductor stocks temporarily surged from their normal 1.5–2.0 range up to 3.0–4.0 as panic selling disproportionately hit high-risk assets. The rolling beta chart captures this regime shift in real time.

**Reading the chart:**
- **Beta rising above 2.5** → Stock becoming highly correlated with market risk. A market correction will hit this stock hard.
- **Beta dropping toward 1.0** → Stock decoupling from market. Company-specific narrative dominating.
- **Beta near or below 0** → Very unusual. Stock moving on completely independent catalysts.

---

### Chart 6: 26-Week Rolling Sharpe Ratio

**Construction:**
```
Rolling Sharpe[t] = (Mean(r[t-25..t]) × 52 − 0.045) / (StdDev(r[t-25..t]) × sqrt(52))
```

**Reading the chart:**
- Consistent periods above +1.0 → The stock consistently delivered good risk-adjusted returns
- Oscillating around 0 → Average performance, inconsistent
- Dips below −1.0 → A distinct rough patch — sustained losses with high volatility

**Practical use:** This chart reveals *when* a stock was a good risk-adjusted investment vs. when it wasn't. Comparing the Rolling Sharpe to the Rolling Volatility chart together reveals whether the stock was compensating you for the risk it was taking at each point in time.

---

### Chart 7: Merton Jump-Diffusion Monte Carlo (15 sample paths shown)

For the full mathematical explanation, see Section 12. Here's how to visually interpret the chart:

**What you see:** 15 out of 2000 simulated 6-month price paths. Each path is a thin blue line representing one possible future scenario for the stock price.

**How to read it:**

| Observation | Interpretation |
|-------------|----------------|
| Paths are tightly clustered | Low volatility. Outcomes are predictable. |
| Paths diverge wildly | High volatility. Very uncertain 6-month outlook. |
| Most paths trend upward | Historical drift is positive. Base case is bullish. |
| Some paths show sudden jumps | The jump component of Merton model activating (earnings miss simulation, etc.) |
| A path briefly goes very low then recovers | A simulated jump event followed by recovery |

**Relationship to card metrics:**
The 3 numbers on the card (MC 6M Median, MC Bull 90%, MC Bear 10%) come from sorting all 2000 simulations and extracting percentiles — not from these 15 displayed paths.

---

### Chart 8: 26-Week Rolling Correlation vs S&P 500 (NEW)

**Construction:**
```
Rolling Corr[t] = Cov(r_stock[t-25..t], r_SPY[t-25..t])
                ÷ (StdDev(r_stock) × StdDev(r_SPY))
                [all computed over t-25..t window]
```

**Why rolling correlation matters (beyond static R²):**

Static R² is a single number across all history. Rolling correlation shows HOW that relationship has CHANGED over time. This is crucial because of a famous phenomenon:

**"Correlations go to 1 in a crisis"** — during market crashes, diversification disappears. Assets that were 0.3 correlated in normal times suddenly become 0.9 correlated as panic selling forces liquidation everywhere. The rolling correlation chart lets you SEE this happening.

**How to read it:**
- **Correlation rising toward +1.0** → Stock becoming a "market puppet." Beta is dominant. Less diversification benefit.
- **Correlation near 0.3–0.5** → Normal, company-specific drivers are active. Earnings, products, guidance matter.
- **Sudden spike toward +1.0** → Systemic risk event. The whole market is moving together. Macro/macro macro.
- **Correlation dropping below 0.2** → Stock is in its own world. Perhaps earnings catalyst or company-specific news dominating.
- **Dashed zero line** = Reference for "no correlation"

**Real example:** During COVID crash (March 2020), virtually every semiconductor stock showed rolling correlation spike to 0.90–0.95 simultaneously. In calm 2021, correlations dropped back to 0.35–0.55 as individual company earnings drove price action.

---

### Chart 9: VaR Stress Test Bar Chart (NEW)

**What it shows:** Five different risk measurement methodologies shown side-by-side for the same stock.

**The 5 bars explained:**

| Bar | Formula | Key Assumption |
|-----|---------|----------------|
| **VaR 90% (Historical)** | 10th percentile of actual returns × −1 | No distribution assumption; uses actual data |
| **VaR 95% (Historical)** | 5th percentile of actual returns × −1 | No distribution assumption; uses actual data |
| **VaR 99% (Historical)** | 1st percentile of actual returns × −1 | No distribution assumption; uses actual data |
| **CF mVaR 95%** | Cornish-Fisher adjusted 5% z-score | Accounts for skewness and kurtosis |
| **CVaR 95% (Expected Shortfall)** | Average of all returns below VaR 95% | What you EXPECT to lose in the worst 5% |

**Color coding:** Blue (mild 90%) → Orange (moderate 95/99%) → Red (severe CF/CVaR)

**Key relationships to examine:**

**If VaR99 >> VaR95 (e.g., VaR95 = 8%, VaR99 = 25%):**
The jump from 95th to 99th percentile is huge → very fat tails → crashes can be catastrophically worse than "bad." High JB test will confirm this.

**If CVaR ≈ VaR95 (e.g., both ~8%):**
The conditional tail is well-behaved. Losses in the worst 5% are consistently ~8%, not occasionally 20%. Less tail risk than it might appear.

**If CF mVaR > Historical VaR 95%:**
Non-normality is amplifying risk beyond what historical simulation alone shows. The distribution shape (skewness/kurtosis) is creating extra hidden risk.

---

## 9. Extended Metrics Grid

25 metrics in a 5×5 grid at the bottom of the detail modal. The top 10 are covered in earlier sections. Here are the remaining institutional metrics:

---

### 9.1 Calmar Ratio

```
Calmar = Annualized Return / |Max Drawdown|
```

Named after the California Managed Accounts Report (1991). Measures how efficiently the stock uses its "worst-case risk budget."

| Calmar | Quality |
|--------|---------|
| < 0 | Losing money |
| 0–0.5 | Poor. The pain isn't worth it. |
| 0.5–1.0 | Acceptable for a growth stock |
| 1.0–2.0 | Good. Well-compensated for worst-case risk |
| > 2.0 | Excellent. Hedge fund quality |

**Example:** A stock with 40% annualized return but MaxDD of −60% → Calmar = 40/60 = 0.67 (mediocre). A stock with 20% return but MaxDD of −15% → Calmar = 20/15 = 1.33 (better!).

---

### 9.2 ATR % (Average True Range, 14-Week)

```
ATR = Mean(|P[t] − P[t-1]|) over last 14 weeks
ATR% = ATR / Current Price × 100
```

ATR% tells you the typical weekly price swing as a percentage of current price.

**Uses:**
1. **Stop-loss placement:** Conservative stops at 2-3 ATR% below entry
2. **Position sizing:** A stock with ATR% = 10% is inherently riskier per dollar than ATR% = 3%
3. **Relative comparison:** Compare ATR% across stocks to understand which is genuinely more volatile

---

### 9.3 Price Z-Score

```
Z-Score = (Current Price − Mean Price 52W) / StdDev Price 52W
```

Where does the current price sit in its recent statistical distribution?

| Z-Score | Meaning |
|---------|---------|
| > +2.0 | 🔴 Very high relative to recent history. Statistically expensive. |
| +1.0 to +2.0 | Elevated |
| −1.0 to +1.0 | Normal range |
| −1.0 to −2.0 | Depressed. Possible value. |
| < −2.0 | 🟢 Very low relative to recent range. Contrarian buy signal. |

---

### 9.4 Win Rate (Weekly)

```
Win Rate = (Number of weeks with positive return) / (Total weeks) × 100
```

At face value, higher is better. But Win Rate must be interpreted with Average Win / Average Loss:

- 70% Win Rate with tiny wins and huge losses → Kelly says bet very small
- 45% Win Rate with big wins and small losses → Kelly says bet large

This is why Win Rate alone is insufficient — you need the full Kelly calculation.

---

### 9.5 Half-Kelly Position Size

```
Kelly Fraction K = p − (1−p)/R

where:
  p = Win Rate (probability of positive weekly return)
  R = Average Win / Average Loss

Half-Kelly = K / 2
```

John Kelly Jr. at Bell Labs derived this formula in 1956 to maximize long-term geometric growth (the log utility function). It's mathematically proven to be the optimal betting fraction given the win/loss statistics.

**Why Half-Kelly?** Full Kelly maximizes expected geometric return but creates enormous volatility — you might see −60% drawdowns before recovering. Virtually all professional quant firms use Half-Kelly or even Quarter-Kelly for practical position sizing.

**Simple worked example:**

Stock data:
- Win Rate p = 58% (56% of weeks are positive)
- Average Win = 3.2%
- Average Loss = 2.5%
- R = 3.2/2.5 = 1.28

```
K = 0.58 − (0.42/1.28) = 0.58 − 0.328 = 0.252
Half-Kelly = 0.252/2 = 0.126 = 12.6%
```

**Interpretation:** Put no more than 12.6% of your portfolio in this stock. This is a mathematically optimal allocation given the historical win/loss statistics.

---

### 9.6 Gain-to-Pain Ratio (NEW)

```
G2P = Σ(positive r_i) / Σ(|negative r_i|)
```

Jack Schwager (of "Market Wizards" fame) popularized this metric. Like Omega at threshold 0, but expressed as a simple cumulative ratio.

**Difference from Omega:** Omega uses the *threshold-adjusted* sums, Gain-to-Pain uses raw sums. For threshold = 0, they differ slightly in construction but tell a similar story.

**Real example:**

Stock has 78 weeks of data:
- Sum of all positive weekly returns: 164%
- Sum of all negative weekly returns (absolute): 87%
- G2P = 164/87 = **1.88** → For every 1% of total losses, the stock generated 1.88% in gains. Healthy positive asymmetry.

---

### 9.7 Pain Index (NEW)

```
Pain Index = (1/n) × Σ|DD[t]| × 100

where DD[t] = (P[t] − Peak[t]) / Peak[t]
```

**vs Ulcer Index:**
- Ulcer squares drawdowns → sensitive to depth
- Pain Index averages absolute drawdowns → sensitive to both depth AND duration equally

**Example:**

Scenario A: −20% drawdown for 1 week
- Pain Index contribution: 20/52 = 0.38%

Scenario B: −5% drawdown sustained for 26 weeks
- Pain Index contribution: 5×26/52 = 2.5%

Scenario B creates 6x more Pain Index despite being a shallower drawdown — because the duration is much longer. This is the key insight Pain Index captures that point-in-time metrics miss.

**RSU planning relevance:** If you're vesting quarterly over 4 years, what you care about is not just "did the stock crash once?" but "how many of my vesting quarters was the stock underwater?" Pain Index captures this chronic underwater experience better than MaxDD.

---

### 9.8 Recovery Factor (NEW)

```
Recovery Factor = |Total Return (%)| / |Max Drawdown (%)|
```

Measures whether the stock's cumulative gains justify its worst episode of pain.

**Example matrix:**

| Total Return | Max Drawdown | Recovery Factor | Verdict |
|-------------|-------------|-----------------|---------|
| 200% | 40% | 5.0 | Excellent |
| 50% | 50% | 1.0 | Marginal |
| 20% | 50% | 0.4 | Poor — drawdown > gain |
| −10% | 60% | Negative | Catastrophic |

---

### 9.9 Serenity Ratio (NEW)

```
Serenity Ratio = (Annualized Return − Risk-Free Rate) / Pain Index
```

Like the Sharpe Ratio but uses Pain Index as the risk denominator instead of standard deviation. Developed by Nathan Faber and popularized in quant research.

**The philosophical insight:**
A stock can have a very good Sharpe Ratio (high return, low standard deviation) but cause chronic stress if it regularly spends long periods underwater — even shallowly. Pain Index captures this chronic suffering. Serenity Ratio divides the net return by that chronic suffering.

**RSU context:** High Serenity means your stock's gains came without prolonged painful periods. Low Serenity means even if the stock ultimately performed, the journey involved sustained underwater periods that would make RSU holders feel trapped.

---

### 9.10 Fama-French 12-1 Momentum Factor (NEW)

```
Momentum = (P[t-4] − P[t-52]) / P[t-52] × 100
```

Return from 12 months ago (t-52 weeks) to 1 month ago (t-4 weeks), SKIPPING the most recent month.

**Why skip the most recent month?**
Jegadeesh & Titman (1993) discovered that the most recent month tends to *reverse* (short-term reversal effect), while 2-12 months ago shows *momentum* (continuation). By skipping the last 4 weeks, we capture the genuine intermediate-term momentum signal.

**Academic backing:** The momentum factor is one of the most replicated findings in empirical finance. Fama and French incorporated it into their 5-factor model. A stock with strong positive momentum (high 12-1 return) historically continues to outperform in subsequent months.

**Interpretation:**
- Positive momentum → The stock has been appreciating for 11 months (excluding last 4 weeks). Momentum is real and likely to continue in the short term.
- Negative momentum → The stock has been declining. Momentum is negative — trend continuation until a catalyst reverses it.

---

### 9.11 Volatility Regime: EWMA/Historical (NEW)

```
EWMA Vol = sqrt(EWMAVar × 52)
EWMAVar[t] = λ × EWMAVar[t-1] + (1-λ) × r[t]²

where λ = 0.94 (RiskMetrics standard decay factor)

Historical Vol = sqrt(Var(all returns) × 52)

Vol Regime = EWMA Vol / Historical Vol
```

**The RiskMetrics EWMA model:**
J.P. Morgan's RiskMetrics group (1994) developed the λ=0.94 EWMA model for practical risk management. With λ=0.94, the "half-life" of a return's influence is ~11.5 weeks — recent weeks matter much more than older weeks.

**Interpretation:**

| Ratio | Market Environment | Action |
|-------|-------------------|--------|
| < 0.7 | Volatility far below long-run average | Low-risk period. Options cheap. |
| 0.7–0.85 | Vol contracting toward normal | Calm settling in. |
| 0.85–1.15 | Normal volatility regime | Standard risk management |
| 1.15–1.4 | Elevated near-term volatility | Heightened risk. Possible upcoming event. |
| > 1.4 | Vol spike regime | Crisis or event risk elevated. |

**Practical use:** Before earnings season, EWMA vol typically rises to 1.2–1.5× historical vol as uncertainty increases. After earnings (if no surprise), vol rapidly collapses back. This ratio lets you see WHERE you are in that cycle.

---

### 9.12 Max Drawdown Duration (NEW)

```
DD Duration = Maximum number of consecutive weeks the stock spent below its prior peak
```

**Construction algorithm:**
1. Track running peak price
2. Start counting when price falls below peak
3. Stop counting when price recovers above peak (set counter to 0)
4. Record maximum counter value seen

**Why duration matters more than depth for RSU planning:**

Consider two scenarios for a 4-year RSU grant:

Scenario A: Stock crashes −50% but recovers in 3 months. You vest at grant price +200%.
Scenario B: Stock drops −20% and stays there for 3 years. You vest those years underwater.

Scenario A has worse MaxDD but much better DD Duration. From an RSU holder's perspective, Scenario B is far more painful — you're waiting 3 years for stocks to recover just to break even.

| Duration | Experience for RSU holder |
|----------|--------------------------|
| < 8 weeks | Brief correction. Normal and expected. |
| 8–26 weeks | A rough quarter. Manageable. |
| 26–52 weeks | One bad year. Unpleasant if vesting in this period. |
| 52–104 weeks | Two years underwater. Very painful for early employees. |
| > 104 weeks | Multi-year bear market. RSUs from this era largely unrealized. |

---

### 9.13 Historical VaR at 90%, 95%, 99% (NEW)

Unlike parametric VaR (Section 4.2 which uses the normal distribution), historical VaR uses the ACTUAL observed return distribution:

```
Historical VaR p% = −Percentile(sorted returns, 1-p)
```

- VaR 90% = Loss exceeded in 10% of weeks
- VaR 95% = Loss exceeded in 5% of weeks
- VaR 99% = Loss exceeded in 1% of weeks

**The jump from 95% to 99% VaR tells you about tail fatness:**

If a stock has:
- VaR 95% = −8% (loss in worst 5% of weeks)
- VaR 99% = −10% (loss in worst 1% of weeks)

The 99th percentile is only 2% worse than 95th → thin tails. Tail behavior is predictable.

If instead:
- VaR 95% = −8%
- VaR 99% = −30%

The jump is enormous → very fat tail → the worst 1% of weeks are catastrophically worse than the worst 5%. This is the hallmark of semiconductor stocks during earnings crises, regulatory shocks, or sudden demand collapses.

---

## 10. Universe Risk Map

The Universe Risk Map is a bubble scatter plot allowing portfolio-level comparison of all stocks simultaneously.

### Axes

- **X-axis:** Annual Volatility (Risk %) — computed from weekly return standard deviation
- **Y-axis:** 1-Year Return (%) — computed from 52-week price change
- **Each point:** One stock, labeled with ticker

### Reading the quadrants

```
         HIGH RETURN
              |
    DEFENSIVE |  IDEAL
    (good but | (best)
    low growth)|
              |
 LOW RISK ----|---- HIGH RISK
              |
    AVOID     |  AGGRESSIVE
 (worst)      | (high risk,
              |  high reward)
         LOW RETURN
```

**Ideal zone (top-left):** High return, low volatility. These are the stocks with structural competitive advantages — pricing power, monopolies, recurring revenue.

**Aggressive zone (top-right):** High return but high volatility. These worked out — but you took significant risk. The same fundamentals could have produced the bottom-right quadrant instead.

**Defensive zone (bottom-left):** Low volatility, low return. Safe but unexciting. May underperform the market on a risk-adjusted basis.

**Avoid zone (bottom-right):** High volatility, low return. The worst combination — you took all the risk and got none of the reward. Common in stocks with falling demand, competitive disruption, or guidance misses.

### RSU evaluation using the Risk Map

Before joining a company, locate its bubble:

1. Is it in the top-left or top-right? → Return-positive. Equity comp has delivered.
2. Is it bottom-right? → Caution. You'd be taking on volatility without commensurate return.
3. How does its X-axis position compare to SPY (~16% vol)? → How much extra volatility are you taking on versus just holding the market?
4. Is the bubble isolated (company-specific) or clustered with peers? → Sector risk vs. idiosyncratic risk.

---

## 11. Universe Correlation Heatmap

### What it is

A symmetric matrix where every cell (i,j) shows the Pearson correlation of weekly returns between stock i and stock j. Color-coded:
- **Deep blue / near +1.0** → Nearly perfect co-movement
- **White / near 0** → Independent
- **Deep red / near −1.0** → Move opposite (rare for equities; would be a near-perfect hedge)

### Mathematical definition of each cell

```
ρ(A,B) = Cov(r_A, r_B) / (σ_A × σ_B)
        = [Σ(r_A - μ_A)(r_B - μ_B)] / sqrt[Σ(r_A - μ_A)² × Σ(r_B - μ_B)²]
```

All computed over the overlapping weekly return history.

### How to read it

**Diagonal:** Always 1.0 (a stock perfectly correlates with itself). Deep blue.

**Off-diagonal patterns:**

| Pattern | Interpretation |
|---------|----------------|
| 0.7–1.0 between two stocks | Almost same stock. Holding both = no diversification. |
| 0.4–0.7 between two stocks | Similar sector/risk factors, but each has independent company-specific drivers. Some diversification. |
| 0.2–0.4 | Meaningful diversification benefit. Different sectors or geographies. |
| < 0.2 | Strong diversification. Independent risk factors. |

### The semiconductor sub-sector clustering you'll see

Stocks in the same sub-sector typically cluster with high correlations:
- **Optical networking (IIVI, COHR, LITE, VNET):** Correlation 0.65–0.85 (all driven by same optical demand cycle)
- **EDA tools (SNPS, CDNS):** Correlation 0.70–0.80 (duopoly, same customers)
- **Foundries (TSM, GFS):** Correlation 0.45–0.65 (similar but different competitive positions)
- **Across sub-sectors (TSM vs SNPS):** Correlation 0.25–0.40 (different business models)

### Portfolio construction insight

If your RSU company is COHR, and you also hold LITE and IIVI in your personal portfolio — you have almost zero diversification across those 3 positions. A single bad quarter for optical components hits all three simultaneously.

The optimal diversification would add something with LOW correlation to your RSU stock: perhaps SPY, real estate, bonds, or stocks from completely different sectors.

---

## 12. The Monte Carlo Engine

### The full Merton Jump-Diffusion model

Robert C. Merton (Nobel Prize 1997) extended Black-Scholes by adding random jumps to the continuous diffusion process, creating a more realistic model for stock prices that exhibit sudden discontinuous moves (earnings surprises, M&A news, regulatory changes).

### The price evolution equation

```
S[t+dt] = S[t] × exp([μ - σ²/2 - λ(exp(μ_J + σ_J²/2) - 1)] × dt
                    + σ × sqrt(dt) × Z
                    + J × N(λ×dt))
```

Where:
- **S[t]** = stock price at week t
- **μ** = historical mean weekly log return (drift)
- **σ** = historical weekly volatility
- **λ** = jump arrival rate = 1.2 jumps/year (calibrated for semiconductor stocks)
- **μ_J** = mean jump size = −4% (jumps are predominantly negative — earnings misses, guidance cuts)
- **σ_J** = jump volatility = 8% (variability in jump magnitude)
- **Z ~ N(0,1)** = standard normal random shock (the diffusion component)
- **J ~ N(μ_J, σ_J²)** = random jump magnitude, when a jump occurs

### The drift adjustment

The term in brackets adjusts the drift to account for the *expected* impact of jumps. Without this adjustment, the model would drift upward artificially because we separately simulate when jumps happen.

```
Adjusted drift = μ - σ²/2 - λ × (exp(μ_J + σ_J²/2) - 1)
```

The `exp(μ_J + σ_J²/2) - 1` term is the expected proportional jump size under the log-normal jump distribution.

### The random number generation

Box-Muller Transform converts two uniform random numbers into one standard normal:
```
U₁, U₂ ~ Uniform(0,1)
Z = sqrt(-2 × ln(U₁)) × cos(2π × U₂)
```

This generates the continuous diffusion shock Z for each simulated week.

### The simulation process

```
For each of 2000 simulations:
  Start: p = current stock price
  For each of 26 weeks:
    1. Generate diffusion: Z = Box-Muller random normal
    2. Check for jump: if Random() < λ/52 (probability ~2.3% per week):
         Generate jump: J = μ_J + σ_J × another Box-Muller Z
       else:
         J = 0
    3. Update price: p = p × exp(adjusted_drift + σ × Z + J)
  Record final price p
Sort all 2000 final prices
P10 = 10th percentile → Bear scenario
P50 = 50th percentile → Median scenario
P90 = 90th percentile → Bull scenario
```

### Why Merton vs. simple GBM?

**Simple GBM (Geometric Brownian Motion)** generates smooth continuous paths. It might predict a worst-case 6-month outcome of −30%.

**Merton Jump-Diffusion** adds sudden −15% to −40% jumps at random intervals. This correctly predicts much worse tail scenarios — because real semiconductor stocks regularly experience exactly these sudden crashes on earnings misses or macro shocks.

For NVDA, MXL, COHR — stocks that regularly gap down 10-30% on a single day of news — the Merton model is far more realistic than GBM.

### Interpreting the Monte Carlo results

**If Median > Current Price:**
The model's historical drift (average weekly return) is positive. The base case points to moderate appreciation over 6 months.

**If Bull/Bear spread is very wide:**
High volatility stock. The future is genuinely very uncertain. The difference between a great and terrible 6 months is enormous.

**Example — high-vol semiconductor (80% annual vol, slightly positive drift):**

```
Current Price: $100
MC Bull 90%: $195 (could nearly double)
MC Median:   $88  (might drift down slightly)
MC Bear 10%: $38  (could lose 62%)
```

The enormous spread between Bull and Bear is *correct behavior* for an 80%-vol stock. It's not a bug — it's accurately reflecting the genuine uncertainty.

---

## 13. Appendix — Statistical Foundations

### A. Standard Deviation and Variance

Given weekly returns r₁, r₂, ..., rₙ:

```
Mean: μ = (1/n) × Σrᵢ

Variance: σ² = (1/n) × Σ(rᵢ - μ)²

Standard Deviation: σ = sqrt(σ²)
```

Standard deviation is the fundamental unit of risk in finance. It measures the typical deviation of individual returns from the average. A stock with σ = 5% weekly typically moves ±5% per week.

### B. The Normal Distribution

The normal distribution (Gauss, 1809) is a symmetric bell-curve shaped distribution characterized entirely by its mean and standard deviation. Under it:
- 68.2% of observations fall within ±1σ
- 95.4% fall within ±2σ
- 99.7% fall within ±3σ

**Why finance breaks normality:**
1. Returns are bounded below (price can't go below zero) → log-normal is more appropriate
2. Crashes happen more often than predicted (fat tails / kurtosis > 3)
3. Crashes are larger than expected (negative skewness)
4. Volatility clusters (quiet periods followed by turbulent periods — GARCH effects)

This is why we use metrics like CF mVaR, CVaR, Omega, and the Jarque-Bera test — all are designed to capture the reality that returns are NOT normally distributed.

### C. Covariance and Correlation

Covariance measures linear co-movement between two return series:
```
Cov(A,B) = (1/n) × Σ(rA,t - μA)(rB,t - μB)
```

Positive = move together. Negative = move opposite. Magnitude depends on units.

Pearson Correlation standardizes to [−1, +1]:
```
ρ(A,B) = Cov(A,B) / (σA × σB)
```

Beta is a regression coefficient:
```
β = Cov(stock, market) / Var(market) = ρ × (σ_stock / σ_market)
```

### D. The Square Root of Time Rule

For independent (i.i.d.) returns, variance scales linearly with time. Therefore standard deviation scales with the square root of time:

```
σ_annual = σ_weekly × sqrt(52)
σ_annual = σ_monthly × sqrt(12)
σ_annual = σ_daily × sqrt(252)
```

This rule assumes independence between weekly returns. It's a reasonable approximation for most liquid stocks over intermediate horizons, though it breaks down during volatility clustering.

### E. Percentiles and Historical VaR

Sort n returns from smallest to largest. The p-th percentile is the value at position floor(n × p/100).

For 100 weekly returns:
- 5th percentile = 5th smallest return = worst 5% threshold = historical VaR 95%
- 1st percentile = worst 1 week out of 100 = historical VaR 99%

Historical VaR makes NO distributional assumption — it uses the actual observed data directly.

### F. Exponential Smoothing (EWMA)

Exponentially Weighted Moving Average gives geometrically declining weights to older observations:

```
EWMA_var[t] = λ × EWMA_var[t-1] + (1-λ) × r[t]²
```

With λ=0.94 (RiskMetrics standard), the weight of a return k weeks ago is: (0.94)^k × (1-0.94)

- This week: weight 0.06
- 10 weeks ago: 0.94^10 × 0.06 = 0.034
- 25 weeks ago: 0.94^25 × 0.06 = 0.013

The "half-life" (time for weight to halve) = log(0.5)/log(0.94) ≈ 11.2 weeks. So EWMA has a memory of roughly 11 weeks, making it highly responsive to recent volatility changes.

### G. Geometric vs. Arithmetic Returns

Arithmetic mean: (1% + 3% + (−5%)) / 3 = −1/3 = −0.33%

But the actual cumulative return is: (1.01 × 1.03 × 0.95) = 1.0093 − 1 = +0.93%

The difference is called the "variance drag" = σ²/2 per period. This is why Monte Carlo drift is:
```
Adjusted drift = μ - σ²/2
```

The σ²/2 term corrects for the geometric (compounding) nature of stock returns vs. the arithmetic mean.

---

## 14. Quick-Reference Cheat Sheet

| Metric | Green (Good) | Yellow (Caution) | Red (Bad) | Key Question |
|--------|-------------|------------------|-----------|--------------|
| **Max Drawdown** | > −20% | −20% to −40% | < −50% | Worst-case loss from peak |
| **VaR 95% (Wk)** | > −5% | −5% to −10% | < −15% | Worst 5% of weeks |
| **Sortino** | > 1.5 | 0.5–1.5 | < 0.5 | Return per downside risk |
| **Sharpe** | > 1.0 | 0.5–1.0 | < 0.5 | Return per total risk |
| **Beta** | 0.8–1.5 | 1.5–2.5 | > 3.0 | Market sensitivity |
| **Alpha** | > +5% | −2% to +5% | < −5% | Market outperformance |
| **Omega** | > 1.5 | 1.0–1.5 | < 1.0 | Cumulative gains vs losses |
| **Hurst** | > 0.55 (trend) | 0.45–0.55 (random) | < 0.45 (mean-rev) | Trending or bouncing? |
| **Calmar** | > 1.0 | 0.5–1.0 | < 0.5 | Return per worst-case pain |
| **Ulcer Index** | < 8 | 8–20 | > 20 | Chronic drawdown pain |
| **Serenity** | > 1.0 | 0–1.0 | < 0 | Return per sustained pain |
| **Recovery Factor** | > 2.0 | 1.0–2.0 | < 1.0 | Gains justify max loss? |
| **Gain-to-Pain** | > 1.5 | 0.8–1.5 | < 0.8 | Cumulative wins vs losses |
| **Vol Regime** | 0.8–1.2 | > 1.2 | > 1.5 | Current vol elevated? |
| **DD Duration** | < 13 wk | 13–26 wk | > 52 wk | Longest underwater stretch |
| **Up Capture** | > 100% | 80–100% | < 80% | Captures market rallies? |
| **Down Capture** | < 100% | 100–120% | > 120% | Cushions market crashes? |
| **Info Ratio** | > 0.5 | 0–0.5 | < 0 | Consistent outperformance? |
| **Tail Ratio** | > 1.5 | 1.0–1.5 | < 1.0 | Upside > downside extremes? |
| **Fear & Greed** | < 25 (extreme fear = BUY) | 45–55 (neutral) | > 80 (extreme greed = SELL) | Crowd sentiment |

---

*Documentation for Career Semi Quant Terminal — Semiconductor Analytics Platform*

*All calculations use 18+ months of weekly closing prices. Risk-free rate: 4.5% (US 10-year Treasury proxy). Benchmark: S&P 500 ETF (SPY). All figures are backward-looking; they represent historical statistics, not forward projections or investment advice.*

*Semiconductor sector focus: TSMC, GlobalFoundries, Synopsys, Cadence, ARM, Analog Devices, Texas Instruments, Marvell, Broadcom, ASML, ASIC, Coherent, Lumentum, MACOM, MaxLinear, ON Semi, Wolfspeed, Kulicke & Soffa, Axcelis, Photronics, Ultra Clean Holdings, Amkor, Entegris, PDF Solutions, Cohu, and more.*
