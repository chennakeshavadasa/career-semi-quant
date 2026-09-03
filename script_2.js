
const COS = [
  // === BENCHMARK ===
  {n:"S&P 500 ETF",           t:"SPY",   tier:"a", pub:true,  sector:"Market"},
  // === FOUNDRIES ===
  {n:"Taiwan Semi (TSMC)",    t:"TSM",   tier:"a", pub:true,  sector:"Foundry"},
  {n:"GlobalFoundries",       t:"GFS",   tier:"b", pub:true,  sector:"Foundry"},
  // === EDA & IP ===
  {n:"Synopsys",              t:"SNPS",  tier:"a", pub:true,  sector:"EDA"},
  {n:"Cadence Design Sys.",   t:"CDNS",  tier:"a", pub:true,  sector:"EDA"},
  {n:"ARM Holdings",          t:"ARM",   tier:"a", pub:true,  sector:"IP"},
  // === EQUIPMENT & FAB ===
  {n:"ASML Holding",          t:"ASML",  tier:"a", pub:true,  sector:"Equipment"},
  {n:"Applied Materials",     t:"AMAT",  tier:"a", pub:true,  sector:"Equipment"},
  {n:"Lam Research",          t:"LRCX",  tier:"a", pub:true,  sector:"Equipment"},
  {n:"KLA Corporation",       t:"KLAC",  tier:"a", pub:true,  sector:"Equipment"},
  {n:"Tokyo Electron",        t:"TOELY", tier:"a", pub:true,  sector:"Equipment"},
  // === MEMORY ===
  {n:"Micron Technology",     t:"MU",    tier:"a", pub:true,  sector:"Memory"},
  {n:"Western Digital",       t:"WDC",   tier:"b", pub:true,  sector:"Memory"},
  // === AI / GPU ===
  {n:"NVIDIA",                t:"NVDA",  tier:"a", pub:true,  sector:"AI"},
  {n:"AMD",                   t:"AMD",   tier:"a", pub:true,  sector:"AI"},
  {n:"Super Micro Computer",  t:"SMCI",  tier:"a", pub:true,  sector:"AI"},
  // === HIGH-SPEED / SERDES ===
  {n:"Broadcom",              t:"AVGO",  tier:"a", pub:true,  sector:"SerDes"},
  {n:"Marvell Technology",    t:"MRVL",  tier:"a", pub:true,  sector:"SerDes"},
  {n:"Credo Technology",      t:"CRDO",  tier:"a", pub:true,  sector:"SerDes"},
  {n:"Astera Labs",           t:"ALAB",  tier:"a", pub:true,  sector:"SerDes"},
  {n:"Rambus",                t:"RMBS",  tier:"a", pub:true,  sector:"SerDes"},
  {n:"MaxLinear",             t:"MXL",   tier:"b", pub:true,  sector:"SerDes"},
  // === OPTICAL Rx/Tx ===
  {n:"Coherent Corp",         t:"COHR",  tier:"a", pub:true,  sector:"Optical"},
  {n:"Lumentum Holdings",     t:"LITE",  tier:"a", pub:true,  sector:"Optical"},
  {n:"MACOM Technology",      t:"MTSI",  tier:"a", pub:true,  sector:"Optical"},
  // === ANALOG & MIXED SIGNAL ===
  {n:"Texas Instruments",     t:"TXN",   tier:"a", pub:true,  sector:"Analog"},
  {n:"Analog Devices",        t:"ADI",   tier:"a", pub:true,  sector:"Analog"},
  {n:"Monolithic Power",      t:"MPWR",  tier:"a", pub:true,  sector:"Analog"},
  {n:"Cirrus Logic",          t:"CRUS",  tier:"a", pub:true,  sector:"Analog"},
  {n:"Microchip Technology",  t:"MCHP",  tier:"a", pub:true,  sector:"Analog"},
  {n:"Silicon Laboratories",  t:"SLAB",  tier:"a", pub:true,  sector:"Analog"},
  {n:"onsemi",                t:"ON",    tier:"a", pub:true,  sector:"Analog"},
  {n:"Synaptics",             t:"SYNA",  tier:"b", pub:true,  sector:"Analog"},
  // === RF & WIRELESS ===
  {n:"Qualcomm",              t:"QCOM",  tier:"a", pub:true,  sector:"RF"},
  {n:"Skyworks Solutions",    t:"SWKS",  tier:"b", pub:true,  sector:"RF"},
  {n:"Qorvo",                 t:"QRVO",  tier:"b", pub:true,  sector:"RF"},
  // === MCU / DSP / EMBEDDED ===
  {n:"NXP Semiconductors",    t:"NXPI",  tier:"a", pub:true,  sector:"MCU"},
  {n:"Renesas Electronics",   t:"RNECY", tier:"a", pub:true,  sector:"MCU"},
  {n:"CEVA Inc",              t:"CEVA",  tier:"b", pub:true,  sector:"DSP"},
  // === POWER & CONNECTIVITY ===
  {n:"Intel",                 t:"INTC",  tier:"a", pub:true,  sector:"CPU"},
  {n:"Semtech",               t:"SMTC",  tier:"b", pub:true,  sector:"Power"},
  // === INTERNATIONAL ===
  {n:"Samsung Electronics",   t:"SSNLF", tier:"a", pub:true,  sector:"Memory"},
  {n:"Infineon Technologies", t:"IFNNY", tier:"b", pub:true,  sector:"Power"},
  {n:"STMicroelectronics",    t:"STM",   tier:"b", pub:true,  sector:"Analog"},
  {n:"Parade Technologies",   t:"PRTEF", tier:"b", pub:true,  sector:"SerDes"}
];


// --- NEW FEATURES ---

function exportCSV() {
  if (Object.keys(D).length === 0) return alert("No data loaded yet.");
  let csv = "Ticker,Name,Sector,Price,6M_Return,1Y_Return,RSI,Volatility,Sharpe,Sortino,QuantScore\n";
  COS.forEach(co => {
    const d = D[co.t];
    if (d && d.ok) {
      csv += `${co.t},"${co.n}",${co.sector},${d.price.toFixed(2)},${d.chg6m.toFixed(2)},${d.chg1y.toFixed(2)},${d.rsi.toFixed(2)},${d.vol.toFixed(2)},${d.sharpe.toFixed(2)},${d.sortino.toFixed(2)},${d.score}\n`;
    }
  });
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `quant_export_${new Date().toISOString().split('T')[0]}.csv`;
  a.click();
}

function toggleBacktest() {
  const m = document.getElementById('backtest-modal');
  m.style.display = m.style.display === 'flex' ? 'none' : 'flex';
}

function runBacktest() {
  const strat = document.getElementById('bt-strategy').value;
  const resDiv = document.getElementById('bt-results');
  resDiv.innerHTML = '<div style="padding:20px; text-align:center;">Running Backtest Simulator...</div>';
  
  setTimeout(() => {
    let html = `<table style="width:100%; text-align:left; border-collapse:collapse; font-size:13px;">
      <tr style="border-bottom:1px solid var(--border); background:rgba(255,255,255,0.05);">
        <th style="padding:10px;">Ticker</th><th style="padding:10px;">Strategy Ret</th><th style="padding:10px;">Buy&Hold Ret</th><th style="padding:10px;">Win Rate</th><th style="padding:10px;">Trades</th>
      </tr>`;
      
    COS.forEach(co => {
      const d = D[co.t];
      if (!d || !d.ok || !d.prices || d.prices.length < 20) return;
      const prices = d.prices;
      let pos = 0, entryPrice = 0;
      let stratRet = 1;
      let trades = 0, wins = 0;
      
      for (let i = 26; i < prices.length; i++) {
        const slice = prices.slice(0, i+1);
        const curPrice = prices[i];
        let buySig = false, sellSig = false;
        
        if (strat === 'rsi') {
          const rsi = calcRSI(slice, 14);
          if (rsi < 30) buySig = true;
          if (rsi > 70) sellSig = true;
        } else if (strat === 'macd') {
          const macd = calcMACD(slice);
          const prevMacd = calcMACD(slice.slice(0, slice.length-1));
          if (macd.hist > 0 && prevMacd.hist <= 0) buySig = true;
          if (macd.hist < 0 && prevMacd.hist >= 0) sellSig = true;
        }
        
        if (buySig && pos === 0) { pos = 1; entryPrice = curPrice; }
        else if (sellSig && pos === 1) { 
          pos = 0; 
          const ret = (curPrice - entryPrice) / entryPrice;
          stratRet *= (1 + ret);
          trades++;
          if (ret > 0) wins++;
        }
      }
      if (pos === 1) {
        const ret = (prices[prices.length-1] - entryPrice) / entryPrice;
        stratRet *= (1 + ret);
        trades++;
        if (ret > 0) wins++;
      }
      
      const bhRet = prices[prices.length-1] / prices[0];
      const sRetPct = (stratRet - 1) * 100;
      const bhRetPct = (bhRet - 1) * 100;
      const winRate = trades > 0 ? (wins/trades*100).toFixed(1) : 0;
      
      html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.05); transition: background 0.1s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
        <td style="padding:10px; color:var(--blue); font-weight:500;">${co.n} (${co.t})</td>
        <td style="padding:10px; color:${sRetPct>=0?'var(--green)':'var(--red)'}; font-family:var(--mono);">${sRetPct>=0?'+':''}${sRetPct.toFixed(1)}%</td>
        <td style="padding:10px; color:${bhRetPct>=0?'var(--green)':'var(--red)'}; font-family:var(--mono);">${bhRetPct>=0?'+':''}${bhRetPct.toFixed(1)}%</td>
        <td style="padding:10px;">${winRate}%</td>
        <td style="padding:10px;">${trades}</td>
      </tr>`;
    });
    html += `</table>`;
    resDiv.innerHTML = html;
  }, 10);
}

let myPortfolio = JSON.parse(localStorage.getItem('my_portfolio') || '[]');

function toggleTracker() {
  const m = document.getElementById('tracker-modal');
  m.style.display = m.style.display === 'flex' ? 'none' : 'flex';
  if (m.style.display === 'flex') renderTracker();
}

function addToTracker() {
  const t = document.getElementById('trk-ticker').value.toUpperCase().trim();
  const s = parseFloat(document.getElementById('trk-shares').value);
  if (!t || !s) return;
  const ex = myPortfolio.find(x => x.t === t);
  if (ex) ex.s += s; else myPortfolio.push({t, s});
  localStorage.setItem('my_portfolio', JSON.stringify(myPortfolio));
  document.getElementById('trk-ticker').value = '';
  document.getElementById('trk-shares').value = '';
  renderTracker();
}

function clearTracker() {
  myPortfolio = [];
  localStorage.setItem('my_portfolio', '[]');
  renderTracker();
}

function renderTracker() {
  const holdDiv = document.getElementById('trk-holdings');
  const sumDiv = document.getElementById('trk-summary');
  if (!myPortfolio.length) { holdDiv.innerHTML = '<p style="padding:20px; color:var(--text-muted);">No holdings in your tracker. Add some above.</p>'; sumDiv.innerHTML = ''; return; }
  
  let html = `<table style="width:100%; text-align:left; border-collapse:collapse; font-size:13px;">
    <tr style="border-bottom:1px solid var(--border); background:rgba(255,255,255,0.05);">
      <th style="padding:10px;">Ticker</th><th style="padding:10px;">Shares</th><th style="padding:10px;">Current Price</th><th style="padding:10px;">Total Value</th>
    </tr>`;
  let totalVal = 0;
  myPortfolio.forEach(p => {
    const d = D[p.t];
    const price = d && d.ok ? d.price : 0;
    const val = price * p.s;
    totalVal += val;
    html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
      <td style="padding:10px; color:var(--blue); font-weight:500;">${p.t}</td>
      <td style="padding:10px;">${p.s}</td>
      <td style="padding:10px; font-family:var(--mono);">$${price.toFixed(2)}</td>
      <td style="padding:10px; font-family:var(--mono);">$${val.toFixed(2)}</td>
    </tr>`;
  });
  html += `</table>`;
  holdDiv.innerHTML = html;
  sumDiv.innerHTML = `Total Portfolio Value: <span style="color:var(--green); font-weight:600;">$${totalVal.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span>`;
}

// Fundamentals Cache
const F = {};
async function fetchFundamentals(ticker) {
  if (F[ticker]) return F[ticker];
  try {
    const yurl = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${ticker}`;
    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(yurl)}`;
    const r = await fetch(proxyUrl).then(x => x.json());
    const res = r?.quoteResponse?.result?.[0];
    if (res) {
      F[ticker] = {
        pe: res.trailingPE || res.forwardPE,
        mcap: res.marketCap,
        eps: res.epsTrailingTwelveMonths,
        earnDate: res.earningsTimestamp ? new Date(res.earningsTimestamp * 1000).toLocaleDateString() : null
      };
      return F[ticker];
    }
  } catch(e) {}
  F[ticker] = { pe: null, mcap: null, eps: null, earnDate: null };
  return F[ticker];
}
// --- END NEW FEATURES ---

// ============================
// THEME SYSTEM
// ============================
function setTheme(name) {
  document.documentElement.className = name === 'midnight' ? '' : `theme-${name}`;
  localStorage.setItem('sqt_theme', name);
  document.querySelectorAll('.theme-dot').forEach(d =>
    d.classList.toggle('active', d.dataset.theme === name)
  );
}
(function initTheme() {
  const saved = localStorage.getItem('sqt_theme') || 'midnight';
  setTheme(saved);
})();

let timeRangeYears = 1.5;
let D = {}, activeFilter = 'all', searchQ = '', sortKey = '';
let SPY_CLOSES = [];
let SOXX_CLOSES = [];   // sector benchmark (PHLX Semiconductor) for factor decomposition
const PUB = COS.filter(c => c.pub);

// ============================
// QUANT MATH ENGINE
// ============================
function calcRSI(prices, period = 14) {
  if (prices.length <= period) return 50;
  let gains = 0, losses = 0;
  for (let i = prices.length - period; i < prices.length; i++) {
    const d = prices[i] - prices[i - 1];
    if (d > 0) gains += d; else losses -= d;
  }
  const avgG = gains / period, avgL = losses / period;
  if (avgL === 0) return 100;
  return 100 - (100 / (1 + avgG / avgL));
}

function calcStoch(prices, period = 14) {
  if (prices.length < period) return 50;
  const slice = prices.slice(-period);
  const low = Math.min(...slice), high = Math.max(...slice);
  if (high === low) return 50;
  return ((slice[slice.length - 1] - low) / (high - low)) * 100;
}

function calcVolAndRisk(prices) {
  const rets = [];
  for (let i = 1; i < prices.length; i++) rets.push((prices[i] - prices[i-1]) / prices[i-1]);
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / rets.length;
  const vol = Math.sqrt(variance) * Math.sqrt(52);

  const downRets = rets.filter(r => r < 0);
  const downVar = downRets.reduce((a, b) => a + b * b, 0) / (rets.length || 1);
  const downStd = Math.sqrt(downVar) * Math.sqrt(52);
  const riskFree = 0.045;
  const sortino = downStd === 0 ? 0 : (mean * 52 - riskFree) / downStd;
  const sharpe  = vol === 0 ? 0 : (mean * 52 - riskFree) / vol;

  const var95 = (mean - 1.645 * Math.sqrt(variance)) * 100;
  
  const varThreshold = mean - 1.645 * Math.sqrt(variance);
  const tailRets = rets.filter(r => r <= varThreshold);
  const cvar95 = tailRets.length ? (tailRets.reduce((a,b)=>a+b,0) / tailRets.length) * 100 : var95;

  return { weeklyDrift: mean, vol, sharpe, sortino, var95, cvar95 };
}

function calcMaxDD(prices) {
  let peak = prices[0], maxDD = 0;
  for (const p of prices) {
    if (p > peak) peak = p;
    const dd = (p - peak) / peak;
    if (dd < maxDD) maxDD = dd;
  }
  return maxDD * 100;
}

function calcMACD(prices) {
  const ema = (data, p) => {
    const k = 2 / (p + 1);
    const e = [data[0]];
    for (let i = 1; i < data.length; i++) e.push(data[i] * k + e[i-1] * (1 - k));
    return e;
  };
  const e12 = ema(prices, 12), e26 = ema(prices, 26);
  const macd = prices.map((_, i) => e12[i] - e26[i]);
  const sig  = ema(macd, 9);
  return { val: macd[macd.length-1], hist: macd[macd.length-1] - sig[sig.length-1] };
}

function calcBollinger(prices, period = 20) {
  const slice = prices.slice(-period);
  const p = slice.length || 1;
  const sma   = slice.reduce((a, b) => a + b, 0) / p;
  const std   = Math.sqrt(slice.reduce((a, b) => a + Math.pow(b - sma, 2), 0) / p);
  return { sma, upper: sma + std * 2, lower: sma - std * 2 };
}

function calcTechAndFib(prices) {
  const low  = Math.min(...prices), high = Math.max(...prices), cur = prices[prices.length - 1];
  const fib618 = high - (high - low) * 0.618;
  const fib382 = high - (high - low) * 0.382;
  const distHigh = ((cur - high) / high) * 100;
  const sma10 = prices.slice(-10).reduce((a, b) => a + b, 0) / 10;
  const sma40 = (prices.length >= 40 ? prices.slice(-40) : prices).reduce((a, b) => a + b, 0) / Math.min(prices.length, 40);
  const cross = sma10 > sma40 ? 'BULL CROSS' : 'BEAR CROSS';
  const crossCls = sma10 > sma40 ? 'g' : 'r';
  return { fib618, fib382, distHigh, cross, crossCls, sma10, sma40 };
}

function calcBetaAlphaAndMore(prices, benchPrices) {
  if (!benchPrices || benchPrices.length < 30 || prices.length < 30) return { beta: 1, alpha: 0, r2: 0, treynor: 0, infoRatio: 0 };
  const len = Math.min(prices.length, benchPrices.length);
  const pS = prices.slice(-len);
  const bS = benchPrices.slice(-len);
  
  let pRets = [], bRets = [];
  for (let i = 1; i < len; i++) {
    pRets.push((pS[i] - pS[i-1]) / pS[i-1]);
    bRets.push((bS[i] - bS[i-1]) / bS[i-1]);
  }
  
  const pMean = pRets.reduce((a, b) => a + b, 0) / pRets.length;
  const bMean = bRets.reduce((a, b) => a + b, 0) / bRets.length;
  
  let cov = 0, varB = 0, varP = 0;
  for (let i = 0; i < pRets.length; i++) {
    const pDiff = pRets[i] - pMean;
    const bDiff = bRets[i] - bMean;
    cov += pDiff * bDiff;
    varB += bDiff * bDiff;
    varP += pDiff * pDiff;
  }
  
  const beta = varB === 0 ? 1 : cov / varB;
  const rf = 0.045 / 52;
  const weeklyAlpha = pMean - (rf + beta * (bMean - rf));
  
  const r2 = (varP === 0 || varB === 0) ? 0 : (cov * cov) / (varP * varB);
  const annRet = pMean * 52;
  const treynor = beta === 0 ? 0 : (annRet - 0.045) / beta;
  
  const excessRets = pRets.map((pr, i) => pr - bRets[i]);
  const excessMean = excessRets.reduce((a, b) => a + b, 0) / excessRets.length;
  const trackingErrorSq = excessRets.reduce((a, b) => a + Math.pow(b - excessMean, 2), 0) / excessRets.length;
  const annTrackingError = Math.sqrt(trackingErrorSq) * Math.sqrt(52);
  const infoRatio = annTrackingError === 0 ? 0 : (excessMean * 52) / annTrackingError;
  
  return { beta, alpha: weeklyAlpha * 52, r2, treynor, infoRatio, trackingError: annTrackingError };
}

function calcKelly(prices) {
  let wins = 0, loss = 0, sumW = 0, sumL = 0;
  for (let i = 1; i < prices.length; i++) {
    const r = (prices[i] - prices[i-1]) / prices[i-1];
    if (r > 0) { wins++; sumW += r; }
    else if (r < 0) { loss++; sumL += Math.abs(r); }
  }
  if (loss === 0) return { size: 100, winRate: 1, avgWin: sumW/wins, avgLoss: 0 };
  if (wins === 0) return { size: 0, winRate: 0, avgWin: 0, avgLoss: sumL/loss };
  const wProb = wins / (wins + loss);
  const avgW = sumW / wins;
  const avgL = sumL / loss;
  const R = avgW / avgL;
  const kelly = wProb - ((1 - wProb) / R);
  return {
    size: Math.max(0, Math.min(1, kelly / 2)) * 100,
    winRate: wProb,
    avgWin: avgW,
    avgLoss: avgL
  };
}

// Calmar Ratio = Annualized Return / |Max Drawdown|
function calcCalmar(prices) {
  const annRet = ((prices[prices.length-1] - prices[0]) / prices[0]) * (52 / Math.max(prices.length - 1, 1));
  const mdd = calcMaxDD(prices);
  if (mdd === 0) return 0;
  return annRet / Math.abs(mdd / 100);
}

// ATR (14-week, close-to-close approximation) expressed as % of current price
function calcATR(prices, period = 14) {
  if (prices.length < period + 1) return 0;
  const trs = [];
  for (let i = 1; i < prices.length; i++) trs.push(Math.abs(prices[i] - prices[i-1]));
  const atr = trs.slice(-period).reduce((a,b) => a+b, 0) / period;
  return (atr / prices[prices.length-1]) * 100;
}

// Price Z-Score = (current price - 52W mean) / 52W std
function calcPriceZScore(prices) {
  const mean = prices.reduce((a,b) => a+b, 0) / prices.length;
  const std = Math.sqrt(prices.reduce((a,b) => a + Math.pow(b-mean,2), 0) / prices.length);
  if (std === 0) return 0;
  return (prices[prices.length-1] - mean) / std;
}

// Upside/Downside Capture Ratios vs benchmark
function calcCaptureRatios(prices, benchPrices) {
  if (!benchPrices || benchPrices.length < 20 || prices.length < 20) return { upCapture: 100, downCapture: 100 };
  const len = Math.min(prices.length, benchPrices.length);
  const pS = prices.slice(-len), bS = benchPrices.slice(-len);
  let upP = 0, upB = 0, downP = 0, downB = 0;
  for (let i = 1; i < len; i++) {
    const bRet = (bS[i] - bS[i-1]) / bS[i-1];
    const pRet = (pS[i] - pS[i-1]) / pS[i-1];
    if (bRet > 0) { upP += pRet; upB += bRet; }
    else if (bRet < 0) { downP += pRet; downB += bRet; }
  }
  return {
    upCapture:   upB   === 0 ? 100 : (upP   / upB)   * 100,
    downCapture: downB === 0 ? 100 : (downP / downB) * 100
  };
}

// ==== ADVANCED QUANT ANALYTICS ====

function calcMomentsJB(returns) {
  const n = returns.length;
  if (n < 4) return { skew: 0, kurtosis: 3, jb: 0 };
  const mean = returns.reduce((a,b)=>a+b,0)/n;
  let m2=0, m3=0, m4=0;
  for(let i=0; i<n; i++) {
    const d = returns[i] - mean;
    m2 += d*d; m3 += d*d*d; m4 += d*d*d*d;
  }
  m2 /= n; m3 /= n; m4 /= n;
  const std = Math.sqrt(m2);
  const skew = std === 0 ? 0 : m3 / Math.pow(std, 3);
  const kurt = std === 0 ? 3 : m4 / Math.pow(std, 4); 
  const jb = (n / 6) * (skew*skew + 0.25 * Math.pow(kurt - 3, 2));
  return { skew, kurtosis: kurt, jb };
}

function calcCornishFisherVaR(returns, conf = 0.95) {
  if (returns.length < 4) return 0;
  const z = -1.645;
  const { skew, kurtosis } = calcMomentsJB(returns);
  const excessK = kurtosis - 3;
  const z_cf = z + (1/6)*(z*z - 1)*skew + (1/24)*(z*z*z - 3*z)*excessK - (1/36)*(2*z*z*z - 5*z)*skew*skew;
  const mean = returns.reduce((a,b)=>a+b,0)/returns.length;
  const std = Math.sqrt(returns.reduce((a,b)=>a+Math.pow(b-mean,2),0)/returns.length);
  return -(mean + z_cf * std);
}

function calcHurst(prices) {
  if (prices.length < 20) return 0.5;
  const returns = [];
  for(let i=1; i<prices.length; i++) returns.push(Math.log(prices[i]/prices[i-1]));
  const mean = returns.reduce((a,b)=>a+b,0)/returns.length;
  let dev = 0, sum = 0, maxZ = -Infinity, minZ = Infinity;
  for(let i=0; i<returns.length; i++) {
    dev += Math.pow(returns[i]-mean, 2);
    sum += (returns[i]-mean);
    if(sum > maxZ) maxZ = sum;
    if(sum < minZ) minZ = sum;
  }
  const R = maxZ - minZ;
  const S = Math.sqrt(dev/returns.length);
  if (S === 0) return 0.5;
  const RS = R/S;
  return Math.log(RS) / Math.log(returns.length);
}

function calcAutocorrelation(returns) {
  if (returns.length < 3) return 0;
  const mean = returns.reduce((a,b)=>a+b,0)/returns.length;
  let num = 0, den = 0;
  for(let i=1; i<returns.length; i++) {
    num += (returns[i]-mean) * (returns[i-1]-mean);
    den += Math.pow(returns[i-1]-mean, 2);
  }
  return den === 0 ? 0 : num / den;
}

function calcOmegaRatio(returns, threshold = 0) {
  let gains = 0, losses = 0;
  for(let r of returns) {
    if (r > threshold) gains += (r - threshold);
    else if (r < threshold) losses += (threshold - r);
  }
  return losses === 0 ? 99 : gains / losses;
}

function calcUlcerIndex(prices) {
  if (prices.length < 2) return 0;
  let maxP = prices[0];
  let sumSqDD = 0;
  for(let i=1; i<prices.length; i++) {
    if (prices[i] > maxP) maxP = prices[i];
    const dd = (prices[i] - maxP) / maxP;
    sumSqDD += dd * dd;
  }
  return Math.sqrt(sumSqDD / prices.length) * 100;
}

function calcTailRatio(returns) {
  if (returns.length < 20) return 1;
  const sorted = [...returns].sort((a,b)=>a-b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
  const p5 = sorted[Math.floor(sorted.length * 0.05)] || 0;
  if (p5 === 0) return 99;
  return Math.abs(p95 / p5);
}

// ==== END ADVANCED QUANT ANALYTICS ====

// ==== INSTITUTIONAL QUANT RATIOS ====

// Gain-to-Pain Ratio = sum(gains) / sum(|losses|)
function calcGainToPain(returns) {
  let gains = 0, losses = 0;
  for (const r of returns) {
    if (r > 0) gains += r;
    else losses += Math.abs(r);
  }
  return losses === 0 ? 99 : gains / losses;
}

// Pain Index = time-average of all underwater depths (%)
function calcPainIndex(prices) {
  if (prices.length < 2) return 0;
  let peak = prices[0], sumDD = 0;
  for (const p of prices) {
    if (p > peak) peak = p;
    sumDD += Math.abs((p - peak) / peak) * 100;
  }
  return sumDD / prices.length;
}

// Recovery Factor = |total return| / |max drawdown|
function calcRecoveryFactor(prices) {
  const totalRet = ((prices[prices.length-1] - prices[0]) / prices[0]) * 100;
  const mdd = Math.abs(calcMaxDD(prices));
  return mdd === 0 ? 99 : totalRet / mdd;
}

// 12-1 Month Momentum Factor (Fama-French, annualized in %)
function calcMomentumFactor(prices) {
  if (prices.length < 52) return 0;
  const p12 = prices[prices.length - 52];
  const p1  = prices[prices.length - 4]; // exclude last 1 month
  return ((p1 - p12) / p12) * 100;
}

// Volatility Regime = EWMA Vol / Historical Vol (>1 = vol expanding)
function calcVolRegime(returns) {
  if (returns.length < 13) return 1;
  const histVar = returns.reduce((a,b) => a + b*b, 0) / returns.length;
  const histVol = Math.sqrt(histVar * 52);
  const decay = 0.94;
  let ewmaVar = histVar;
  for (const r of returns.slice(-26)) ewmaVar = decay * ewmaVar + (1 - decay) * r * r;
  const ewmaVol = Math.sqrt(ewmaVar * 52);
  return histVol === 0 ? 1 : ewmaVol / histVol;
}

// Max Drawdown Duration (longest time underwater, in weeks)
function calcDrawdownDuration(prices) {
  let peak = prices[0], maxDur = 0, curDur = 0;
  for (const p of prices) {
    if (p >= peak) { peak = p; maxDur = Math.max(maxDur, curDur); curDur = 0; }
    else curDur++;
  }
  return Math.max(maxDur, curDur);
}

// Serenity Ratio = (Ann.Return - Rf) / Pain Index
function calcSerenityRatio(prices) {
  const painIdx = calcPainIndex(prices);
  if (painIdx === 0) return 0;
  const annRet = ((prices[prices.length-1] - prices[0]) / prices[0]) * (52 / Math.max(prices.length-1, 1));
  return (annRet - 0.045) / (painIdx / 100);
}

// Historical VaR at 90%, 95%, 99% confidence (weekly, %)
function calcVaRFull(returns) {
  if (returns.length < 10) return { p90: 0, p95: 0, p99: 0 };
  const sorted = [...returns].sort((a,b) => a-b);
  const n = sorted.length;
  return {
    p90: Math.abs(sorted[Math.max(0, Math.floor(n * 0.10))] * 100),
    p95: Math.abs(sorted[Math.max(0, Math.floor(n * 0.05))] * 100),
    p99: Math.abs(sorted[Math.max(0, Math.floor(n * 0.01))] * 100)
  };
}

// ==== END INSTITUTIONAL QUANT RATIOS ====

// Merton Jump Diffusion Monte Carlo 6-Month Simulation (2000 Iterations)
function runMonteCarlo(cur, drift, vol, iterations=2000, weeks=26) {
  if (!vol || vol === 0) return { median: cur, p10: cur, p90: cur };
  const finalPrices = new Float32Array(iterations);
  const weeklyVol = vol / Math.sqrt(52);
  
  // Jump parameters (Tech/Semi average tail event estimation)
  const jumpFreq = 1.2; // Expected jumps per year
  const jumpMean = -0.04; // Average jump is negative 4%
  const jumpVol = 0.08; // Volatility of jumps
  
  const weeklyJumpFreq = jumpFreq / 52;
  const driftAdj = drift - 0.5 * Math.pow(weeklyVol, 2) - weeklyJumpFreq * (Math.exp(jumpMean + 0.5 * Math.pow(jumpVol,2)) - 1);
  
  for(let i=0; i<iterations; i++) {
    let p = cur;
    for(let w=0; w<weeks; w++) {
      let u = 0, v = 0;
      while(u === 0) u = Math.random();
      while(v === 0) v = Math.random();
      const rand = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
      
      let jump = 0;
      if (Math.random() < weeklyJumpFreq) {
         let u2 = 0, v2 = 0;
         while(u2 === 0) u2 = Math.random();
         while(v2 === 0) v2 = Math.random();
         const randJump = Math.sqrt(-2.0 * Math.log(u2)) * Math.cos(2.0 * Math.PI * v2);
         jump = jumpMean + jumpVol * randJump;
      }
      
      p = p * Math.exp(driftAdj + weeklyVol * rand + jump);
    }
    finalPrices[i] = p;
  }
  
  finalPrices.sort();
  return {
    p10: finalPrices[Math.floor(iterations * 0.10)],
    median: finalPrices[Math.floor(iterations * 0.50)],
    p90: finalPrices[Math.floor(iterations * 0.90)]
  };
}

// ============================================================
//  ADVANCED FACTOR / VOL / TAIL ANALYTICS  (added module)
// ============================================================
function _rets(a){const r=[];for(let i=1;i<a.length;i++)r.push((a[i]-a[i-1])/a[i-1]);return r;}
function _erf(x){const t=1/(1+0.3275911*Math.abs(x));const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return x>=0?y:-y;}
function normCDF(x){return 0.5*(1+_erf(x/Math.SQRT2));}
function normInv(p){
  if(p<=0)return -6; if(p>=1)return 6;
  const a=[-3.969683028665376e+01,2.209460984245205e+02,-2.759285104469687e+02,1.383577518672690e+02,-3.066479806614716e+01,2.506628277459239e+00];
  const b=[-5.447609879822406e+01,1.615858368580409e+02,-1.556989798598866e+02,6.680131188771972e+01,-1.328068155288572e+01];
  const c=[-7.784894002430293e-03,-3.223964580411365e-01,-2.400758277161838e+00,-2.549732539343734e+00,4.374664141464968e+00,2.938163982698783e+00];
  const d=[7.784695709041462e-03,3.224671290700398e-01,2.445134137142996e+00,3.754408661907416e+00];
  const pl=0.02425,ph=1-pl;let q,r;
  if(p<pl){q=Math.sqrt(-2*Math.log(p));return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);}
  if(p<=ph){q=p-0.5;r=q*q;return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);}
  q=Math.sqrt(-2*Math.log(1-p));return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
}

// EWMA volatility — JP Morgan RiskMetrics (lambda = 0.94), annualized %
function calcEWMAVol(prices,lambda=0.94){const r=_rets(prices);if(!r.length)return 0;let v=r.slice(0,Math.min(10,r.length)).reduce((a,b)=>a+b*b,0)/Math.min(10,r.length);for(const x of r)v=lambda*v+(1-lambda)*x*x;return Math.sqrt(v)*Math.sqrt(52)*100;}

// GARCH(1,1) conditional volatility — grid-MLE fit, returns series + multi-step forecast
function calcGARCH(prices,fw=12){
  const r=_rets(prices),n=r.length;
  if(n<20)return{condVol:[],forecast:[],current:0,longRun:0,alpha:0,beta:0,persistence:0};
  const mean=r.reduce((a,b)=>a+b,0)/n;
  const uv=r.reduce((a,b)=>a+(b-mean)*(b-mean),0)/n;
  let best=-Infinity,bA=0.1,bB=0.85;
  for(const a of [0.05,0.08,0.1,0.12,0.15,0.18])for(const b of [0.75,0.8,0.85,0.88,0.9]){
    if(a+b>=0.999)continue;const om=uv*(1-a-b);let vt=uv,ll=0,ok=true;
    for(let i=0;i<n;i++){if(vt<=0){ok=false;break;}const e2=(r[i]-mean)**2;ll+=-0.5*(Math.log(2*Math.PI)+Math.log(vt)+e2/vt);vt=om+a*e2+b*vt;}
    if(ok&&ll>best){best=ll;bA=a;bB=b;}
  }
  const alpha=bA,beta=bB,om=uv*(1-alpha-beta);
  const condVol=[];let vt=uv;
  for(let i=0;i<n;i++){condVol.push(Math.sqrt(vt)*Math.sqrt(52)*100);vt=om+alpha*(r[i]-mean)**2+beta*vt;}
  const forecast=[];let f=vt;for(let h=0;h<fw;h++){forecast.push(Math.sqrt(f)*Math.sqrt(52)*100);f=om+(alpha+beta)*f;}
  return{condVol,forecast,current:Math.sqrt(vt)*Math.sqrt(52)*100,longRun:Math.sqrt(uv)*Math.sqrt(52)*100,alpha,beta,persistence:alpha+beta};
}

// Probabilistic Sharpe Ratio (Lopez de Prado) — P(true SR > benchmark) adjusting for skew/kurtosis & sample length
function calcPSR(returns,benchSR=0){
  const n=returns.length;if(n<10)return 0.5;
  const mean=returns.reduce((a,b)=>a+b,0)/n;
  const sd=Math.sqrt(returns.reduce((a,b)=>a+(b-mean)**2,0)/n);if(sd===0)return 0.5;
  const sk=returns.reduce((a,b)=>a+((b-mean)/sd)**3,0)/n;
  const ku=returns.reduce((a,b)=>a+((b-mean)/sd)**4,0)/n;
  const sr=mean/sd;
  const denom=Math.sqrt(Math.max(1e-9,1-sk*sr+((ku-1)/4)*sr*sr));
  return normCDF((sr-benchSR)*Math.sqrt(n-1)/denom);
}

// Parametric (variance-covariance / Gaussian) VaR, weekly loss %
function calcParametricVaR(returns,conf=0.95){
  const n=returns.length;const mean=returns.reduce((a,b)=>a+b,0)/n;
  const sd=Math.sqrt(returns.reduce((a,b)=>a+(b-mean)**2,0)/n);
  const z=conf===0.99?2.326:conf===0.95?1.645:1.282;
  return Math.abs(mean-z*sd)*100;
}

// Two-factor model: market (SPY) + sector (SOXX) OLS — pure betas, idiosyncratic vol, factor R²
function calcTwoFactor(prices,spy,sox){
  if(!spy||!sox||spy.length<30||sox.length<30)return{betaMkt:1,betaSec:0,alpha:0,idioVol:0,r2:0,betaSoxxRaw:1};
  const len=Math.min(prices.length,spy.length,sox.length);
  if(len<30)return{betaMkt:1,betaSec:0,alpha:0,idioVol:0,r2:0,betaSoxxRaw:1};
  const p=_rets(prices.slice(-len)),m=_rets(spy.slice(-len)),s=_rets(sox.slice(-len));
  const N=p.length;
  const pm=p.reduce((a,b)=>a+b,0)/N,mm=m.reduce((a,b)=>a+b,0)/N,sm=s.reduce((a,b)=>a+b,0)/N;
  let Sxx1=0,Sxx2=0,Sx1x2=0,Sx1y=0,Sx2y=0,Syy=0;
  for(let i=0;i<N;i++){const x1=m[i]-mm,x2=s[i]-sm,y=p[i]-pm;Sxx1+=x1*x1;Sxx2+=x2*x2;Sx1x2+=x1*x2;Sx1y+=x1*y;Sx2y+=x2*y;Syy+=y*y;}
  const det=Sxx1*Sxx2-Sx1x2*Sx1x2;
  let b1,b2;if(Math.abs(det)<1e-14){b1=Sx1y/(Sxx1||1);b2=0;}else{b1=(Sxx2*Sx1y-Sx1x2*Sx2y)/det;b2=(Sxx1*Sx2y-Sx1x2*Sx1y)/det;}
  let ssr=0;for(let i=0;i<N;i++){const pred=b1*(m[i]-mm)+b2*(s[i]-sm);ssr+=(p[i]-pm-pred)**2;}
  const r2=Syy===0?0:Math.max(0,1-ssr/Syy);
  const idioVol=Math.sqrt(ssr/N)*Math.sqrt(52)*100;
  const rf=0.045/52;const alpha=(pm-(rf+b1*(mm-rf)+b2*(sm-mm)))*52;
  let cov=0,vs=0;for(let i=0;i<N;i++){cov+=(p[i]-pm)*(s[i]-sm);vs+=(s[i]-sm)**2;}
  const betaSoxxRaw=vs===0?1:cov/vs;
  return{betaMkt:b1,betaSec:b2,alpha,idioVol,r2,betaSoxxRaw};
}

// Asymmetric (bull / bear) beta — sensitivity in up vs down market weeks
function calcAsymBeta(prices,bench){
  if(!bench||bench.length<30)return{bull:1,bear:1};
  const len=Math.min(prices.length,bench.length);if(len<30)return{bull:1,bear:1};
  const p=_rets(prices.slice(-len)),b=_rets(bench.slice(-len));
  const sub=idx=>{if(idx.length<5)return 1;const bm=idx.reduce((a,i)=>a+b[i],0)/idx.length,pm=idx.reduce((a,i)=>a+p[i],0)/idx.length;let cov=0,vb=0;idx.forEach(i=>{cov+=(p[i]-pm)*(b[i]-bm);vb+=(b[i]-bm)**2;});return vb===0?1:cov/vb;};
  const up=[],dn=[];for(let i=0;i<b.length;i++)(b[i]>=0?up:dn).push(i);
  return{bull:sub(up),bear:sub(dn)};
}

// Compound annual growth rate over the window, %
function calcCAGR(prices){const yrs=(prices.length-1)/52;if(yrs<=0)return 0;return (Math.pow(prices[prices.length-1]/prices[0],1/yrs)-1)*100;}

function calcFearGreed(rsi, stoch, vol) {
  const volScore = Math.max(0, Math.min(100, 100 - (vol * 100 - 15) * 1.5));
  const fg = (rsi + stoch + volScore) / 3;
  const label = fg < 25 ? 'EXTREME FEAR' : fg < 45 ? 'FEAR' : fg < 55 ? 'NEUTRAL' : fg < 75 ? 'GREED' : 'EXTREME GREED';
  const cls   = fg < 25 ? 'fg-ef' : fg < 45 ? 'fg-f' : fg < 55 ? 'fg-n' : fg < 75 ? 'fg-g' : 'fg-eg';
  return { val: fg, label, cls };
}

// ============================
// API KEY MANAGEMENT
// ============================
let apiKeys = {
  poly:    localStorage.getItem('poly_key')    || '',
  alpha:   localStorage.getItem('alpha_key')   || '',
  finnhub: localStorage.getItem('finnhub_key') || ''
};

function toggleSettings() {
  const m = document.getElementById('settings-modal');
  if (m.style.display === 'none' || !m.style.display) {
    document.getElementById('key-poly').value    = apiKeys.poly;
    document.getElementById('key-alpha').value   = apiKeys.alpha;
    document.getElementById('key-finnhub').value = apiKeys.finnhub;
    m.style.display = 'flex';
  } else {
    m.style.display = 'none';
  }
}

function saveKeys() {
  apiKeys.poly    = document.getElementById('key-poly').value.trim();
  apiKeys.alpha   = document.getElementById('key-alpha').value.trim();
  apiKeys.finnhub = document.getElementById('key-finnhub').value.trim();
  localStorage.setItem('poly_key',    apiKeys.poly);
  localStorage.setItem('alpha_key',   apiKeys.alpha);
  localStorage.setItem('finnhub_key', apiKeys.finnhub);
  toggleSettings();
  reloadAll();
}

// ============================
// DATA FETCHING ENGINE
// ============================
async function fetchOne(ticker, isBench = false) {
  const now   = Math.floor(Date.now() / 1000);
  const from1Y = now - Math.floor(timeRangeYears * 31536000);
  let closes = [], source = 'Unknown';

  const yurl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1wk&period1=${from1Y}&period2=${now}`;
  const proxies = [
    u => u,
    u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
    u => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
    u => `https://corsproxy.io/?${encodeURIComponent(u)}`
  ];

  // LEVEL 1: Parallel Proxy Race — Yahoo Finance
  try {
    closes = await Promise.any(proxies.map(mkP => new Promise(async (res, rej) => {
      try {
        const c = new AbortController();
        const t = setTimeout(() => c.abort(), 9000);
        const r = await fetch(mkP(yurl), { signal: c.signal });
        clearTimeout(t);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const j  = await r.json();
        const p  = j?.chart?.result?.[0]?.indicators?.quote?.[0]?.close;
        const clean = (p || []).filter(v => v != null && v > 0);
        if (clean.length > 2) res(clean); else rej(new Error('sparse'));
      } catch(e) { rej(e); }
    })));
    source = 'Yahoo Finance';
  } catch (_) {}

  // LEVEL 2: Polygon.io
  if (closes.length < 3 && apiKeys.poly) {
    try {
      const fmt  = d => d.toISOString().split('T')[0];
      const dNow = new Date(), dFrom = new Date(Date.now() - timeRangeYears * 31536000000);
      const c = new AbortController(); const t = setTimeout(() => c.abort(), 9000);
      const r = await fetch(`https://api.polygon.io/v2/aggs/ticker/${ticker}/range/1/week/${fmt(dFrom)}/${fmt(dNow)}?adjusted=true&apiKey=${apiKeys.poly}`, { signal: c.signal }).then(x => x.json());
      clearTimeout(t);
      if (r.results?.length > 2) { closes = r.results.map(x => x.c); source = 'Polygon.io'; }
    } catch(_) {}
  }

  // LEVEL 3: Alpha Vantage
  if (closes.length < 3 && apiKeys.alpha) {
    try {
      const c = new AbortController(); const t = setTimeout(() => c.abort(), 9000);
      const r = await fetch(`https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=${ticker}&apikey=${apiKeys.alpha}`, { signal: c.signal }).then(x => x.json());
      clearTimeout(t);
      if (r['Weekly Time Series']) {
        const weeks = Math.max(4, Math.ceil(timeRangeYears * 52));
        const vals = Object.values(r['Weekly Time Series']).slice(0, weeks).reverse().map(x => parseFloat(x['4. close']));
        if (vals.length > 2) { closes = vals; source = 'Alpha Vantage'; }
      }
    } catch(_) {}
  }

  // LEVEL 4: Finnhub
  if (closes.length < 3 && apiKeys.finnhub) {
    try {
      const c = new AbortController(); const t = setTimeout(() => c.abort(), 9000);
      const r = await fetch(`https://finnhub.io/api/v1/stock/candle?symbol=${ticker}&resolution=W&from=${from1Y}&to=${now}&token=${apiKeys.finnhub}`, { signal: c.signal }).then(x => x.json());
      clearTimeout(t);
      if (r.s === 'ok' && r.c?.length > 2) { closes = r.c; source = 'Finnhub'; }
    } catch(_) {}
  }

  // LEVEL 5: No data — strict error, no simulation
  if (closes.length < 3) return { ok: false, source: 'No data — proxy blocked or ticker unavailable' };

  const cur   = closes[closes.length - 1];
  const idx6M = Math.max(0, closes.length - 26);
  const idx1Y = Math.max(0, closes.length - 52);
  const chg6m = ((cur - closes[idx6M]) / closes[idx6M]) * 100;
  const chg1y = ((cur - closes[idx1Y]) / closes[idx1Y]) * 100;

  
  const rsi   = calcRSI(closes, 14);

  const stoch = calcStoch(closes, 14);
  const { weeklyDrift, vol, sharpe, sortino, var95, cvar95 } = calcVolAndRisk(closes);
  const maxDD  = calcMaxDD(closes);
  const bb     = calcBollinger(closes, 20);
  const macd   = calcMACD(closes);
  const mc     = runMonteCarlo(cur, weeklyDrift, vol, 2000, 26);
  const fg     = calcFearGreed(rsi, stoch, vol);
  const tech   = calcTechAndFib(closes);
  const { beta, alpha, r2, treynor, infoRatio, trackingError } = isBench ? { beta: 1, alpha: 0, r2: 1, treynor: 0, infoRatio: 0, trackingError: 0 } : calcBetaAlphaAndMore(closes, SPY_CLOSES);
  const kellyObj   = calcKelly(closes);
  const calmar     = calcCalmar(closes);
  const atrPct     = calcATR(closes, 14);
  const priceZ     = calcPriceZScore(closes);
  const { upCapture, downCapture } = isBench ? { upCapture: 100, downCapture: 100 } : calcCaptureRatios(closes, SPY_CLOSES);

  // Advanced Quant Analytics
  const returns = [];
  for(let i=1; i<closes.length; i++) returns.push((closes[i] - closes[i-1])/closes[i-1]);
  
  const momentsJB = calcMomentsJB(returns);
  const cfVaR = calcCornishFisherVaR(returns) * 100;
  const hurst = calcHurst(closes);
  const autoCorr = calcAutocorrelation(returns);
  const omega = calcOmegaRatio(returns);
  const ulcer = calcUlcerIndex(closes);
  const tailRatio   = calcTailRatio(returns);
  const gainToPain  = calcGainToPain(returns);
  const painIndex   = calcPainIndex(closes);
  const recoveryF   = calcRecoveryFactor(closes);
  const momFactor   = calcMomentumFactor(closes);
  const volRegime   = calcVolRegime(returns);
  const ddDuration  = calcDrawdownDuration(closes);
  const serenity    = calcSerenityRatio(closes);
  const varFull     = calcVaRFull(returns);

  // --- Advanced factor / vol / tail analytics (added) ---
  const ewmaVol     = calcEWMAVol(closes);
  const garch       = calcGARCH(closes, 12);
  const psr         = calcPSR(returns);
  const paramVaR95  = calcParametricVaR(returns, 0.95);
  const paramVaR99  = calcParametricVaR(returns, 0.99);
  const twoFactor   = isBench ? {betaMkt:1,betaSec:0,alpha:0,idioVol:0,r2:1,betaSoxxRaw:1} : calcTwoFactor(closes, SPY_CLOSES, SOXX_CLOSES);
  const asymBeta    = isBench ? {bull:1,bear:1} : calcAsymBeta(closes, SPY_CLOSES);
  const cagr        = calcCAGR(closes);
  const sharpeAnn   = sharpe;

  // Momentum State (based strictly on price action — NOT fundamental valuation)
  let momentum = 'NEUTRAL', momCls = 'b';
  if      (cur < bb.lower || (cur < bb.sma && rsi < 30)) { momentum = 'OVERSOLD';   momCls = 'g'; }
  else if (cur > bb.upper || rsi > 75)                    { momentum = 'OVERBOUGHT'; momCls = 'r'; }

  // Composite Quant Score (0–100)
  let score = 50;
  if (chg6m > 0)           score += 8;
  if (chg1y > 0)           score += 8;
  if (macd.hist > 0)       score += 12;
  if (momentum === 'OVERSOLD')   score += 18;
  if (momentum === 'OVERBOUGHT') score -= 18;
  if (fg.val < 30)         score += 8;   // buy into extreme fear
  if (fg.val > 80)         score -= 12;  // avoid extreme greed
  if (sortino > 1.5)       score += 8;
  if (sharpe  > 1.0)       score += 6;
  if (tech.cross === 'BULL CROSS') score += 5;
  if (alpha > 0.05)        score += 8;
  if (alpha < 0)           score -= 8;
  score = Math.max(5, Math.min(99, Math.round(score)));

  return {
    ok: true, source, price: cur, prices: closes,
    chg6m, chg1y, rsi, stoch, vol, sharpe, sortino, var95, cvar95, maxDD,
    macd, mc, momentum, momCls, score, fg, tech, beta, alpha, r2, treynor, infoRatio, trackingError, kellyObj,
    calmar, atrPct, priceZ, upCapture, downCapture,
    momentsJB, cfVaR, hurst, autoCorr, omega, ulcer, tailRatio,
    gainToPain, painIndex, recoveryF, momFactor, volRegime, ddDuration, serenity, varFull,
    ewmaVol, garch, psr, paramVaR95, paramVaR99, twoFactor, asymBeta, cagr, sharpeAnn
  };
}

// ============================
// SPARKLINE — area + line
// ============================
function spark(prices, up) {
  const W = 340, H = 52;
  const mn = Math.min(...prices), mx = Math.max(...prices), rng = mx - mn || 1;
  const pts = prices.map((p, i) => [
    (i / (prices.length - 1)) * W,
    H - ((p - mn) / rng) * (H - 6) - 3
  ]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
  const area = line + `L${W},${H} L0,${H} Z`;
  const col  = up ? 'var(--green)' : 'var(--red)';
  const gradId = `g${Math.random().toString(36).slice(2,7)}`;
  const lx = pts[pts.length-1][0].toFixed(1), ly = pts[pts.length-1][1].toFixed(1);
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs>
      <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${col}" stop-opacity="0.3"/>
        <stop offset="100%" stop-color="${col}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${area}" fill="url(#${gradId})"/>
    <path class="spark-path" d="${line}" stroke="${col}"/>
    <circle cx="${lx}" cy="${ly}" r="3.5" fill="${col}" opacity="0.9"/>
  </svg>`;
}

// ============================
// CARD RENDERING
// ============================
function cardHTML(co) {
  const id = `c${(co.t || co.n).replace(/[^a-z0-9]/gi,'_')}`;
  const d  = co.pub ? D[co.t] : null;
  const tierB = `<span class="badge ${co.tier === 'a' ? 'b-a' : 'b-b'}">TIER-${co.tier.toUpperCase()}</span>`;
  const sectorB = `<span class="badge" style="background:rgba(88,166,255,0.08);color:var(--blue);border:1px solid rgba(88,166,255,0.2);font-size:8px;">${co.sector}</span>`;

  // Loading skeleton
  if (co.pub && !d) return `<div class="card" id="${id}" data-tier="${co.tier}" data-pub="true" data-score="0" data-fg="50" data-rsi="50" data-chg6m="0" data-chg1y="0" data-vol="0">
    <div class="c-top">
      <div><div class="c-name">${co.n}</div><div class="c-tkr">${co.t}</div></div>
      <div class="badges">${sectorB}${tierB}</div>
    </div>
    ${d && d.fund && d.fund.earnDate && (d.fund.earnDate.getTime() - Date.now() > 0 && d.fund.earnDate.getTime() - Date.now() < 14*86400000) ? `<div style="font-size:9px; background:rgba(255,165,0,0.2); color:orange; border-radius:4px; padding:2px 6px; display:inline-block; margin-top:4px;">⚠️ Earnings in ${Math.ceil((d.fund.earnDate.getTime() - Date.now())/86400000)} days</div>` : ''}
    <div class="skel" style="margin:8px 0 6px;height:18px;"></div>
    <div class="skel" style="height:52px;margin-bottom:10px;"></div>
    <div class="skel" style="height:60px;"></div>
    <div class="pvt-state" style="margin-top:10px;">FETCHING LIVE DATA...</div>
  </div>`;

  // Private company
  if (!co.pub) return `<div class="card" id="${id}" data-tier="${co.tier}" data-pub="false" data-score="0" data-fg="50" data-rsi="50" data-chg6m="0" data-chg1y="0" data-vol="0">
    <div class="c-top">
      <div><div class="c-name">${co.n}</div><div class="c-tkr" style="color:var(--purple)">PRIVATE · PRE-IPO</div></div>
      <div class="badges">${sectorB}${tierB}</div>
    </div>
    <div class="pvt-state">◆ NOT PUBLICLY LISTED</div>
  </div>`;

  // Data unavailable
  if (d && !d.ok) return `<div class="card" id="${id}" data-tier="${co.tier}" data-pub="true" data-score="0" data-fg="50" data-rsi="50" data-chg6m="0" data-chg1y="0" data-vol="0">
    <div class="c-top">
      <div><div class="c-name">${co.n}</div><div class="c-tkr">${co.t}</div></div>
      <div class="badges">${sectorB}${tierB}</div>
    </div>
    ${d && d.fund && d.fund.earnDate && (d.fund.earnDate.getTime() - Date.now() > 0 && d.fund.earnDate.getTime() - Date.now() < 14*86400000) ? `<div style="font-size:9px; background:rgba(255,165,0,0.2); color:orange; border-radius:4px; padding:2px 6px; display:inline-block; margin-top:4px;">⚠️ Earnings in ${Math.ceil((d.fund.earnDate.getTime() - Date.now())/86400000)} days</div>` : ''}
    <div class="pvt-state" style="color:var(--red);border-color:rgba(248,81,73,0.2);">
      <span>⚠ DATA UNAVAILABLE</span>
      <span style="font-size:9px;color:var(--text-muted);text-align:center;padding:0 12px;">${d.source}</span>
    </div>
  </div>`;

  const u6  = d.chg6m >= 0, u1 = d.chg1y >= 0;
  const scoreColor = d.score >= 70 ? 'g' : d.score < 40 ? 'r' : 'y';
  const cardCls = d.score >= 70 ? 'buy' : d.score < 35 ? 'sell' : '';
  
  const spy = D['SPY'] || {};
  const sMaxDD = spy.ok ? spy.maxDD.toFixed(1) + '%' : '--';
  const sVar = spy.ok ? spy.var95.toFixed(2) + '%' : '--';
  const sSort = spy.ok ? spy.sortino.toFixed(2) : '--';
  const sVol = spy.ok ? (spy.vol * 100).toFixed(1) + '%' : '--';
  const sShp = spy.ok ? spy.sharpe.toFixed(2) : '--';

  return `<div class="card ${cardCls}" id="${id}" onclick="openDetail('${co.t}', '${co.n}')" style="cursor:pointer;"
    data-tier="${co.tier}" data-pub="true"
    data-score="${d.score}" data-fg="${d.fg.val.toFixed(0)}"
    data-rsi="${d.rsi.toFixed(1)}" data-chg6m="${d.chg6m.toFixed(2)}"
    data-chg1y="${d.chg1y.toFixed(2)}" data-vol="${(d.vol*100).toFixed(1)}">
    <div class="c-top">
      <div>
        <div class="c-name">${co.n}</div>
        <div class="c-tkr">
          <span style="font-weight:700;color:#fff;">${co.t}</span>
          <span style="opacity:0.45;font-size:9px;">SRC:${d.source.toUpperCase().replace(' ','')}</span>
        </div>
      </div>
      <div class="badges">${sectorB}${tierB}</div>
    </div>

    <div class="price-box">
      <span class="price">$${d.price.toFixed(2)}</span>
      <div class="chg-row">
        <span class="chg ${u6 ? 'up' : 'dn'}">${u6?'▲':'▼'} ${Math.abs(d.chg6m).toFixed(1)}%<span class="chg-label">6M</span></span>
        <span class="chg ${u1 ? 'up' : 'dn'}">${u1?'▲':'▼'} ${Math.abs(d.chg1y).toFixed(1)}%<span class="chg-label">1Y</span></span>
      </div>
    </div>

    <div class="fg-bar">
      <span class="fg-lbl">Fear &amp; Greed</span>
      <span class="fg-val ${d.fg.cls}">${d.fg.val.toFixed(0)} · ${d.fg.label}</span>
    </div>

    <div class="risk-grid">
      <div class="r-box"><span class="r-lbl">Max Drawdown (SPY: ${sMaxDD})</span><span class="r-val r">${d.maxDD.toFixed(1)}%</span></div>
      <div class="r-box"><span class="r-lbl">VaR 95% (SPY: ${sVar})</span><span class="r-val r">${d.var95.toFixed(2)}%</span></div>
      <div class="r-box"><span class="r-lbl">Sortino (SPY: ${sSort})</span><span class="r-val ${d.sortino>1?'g':'r'}">${d.sortino.toFixed(2)}</span></div>
      <div class="r-box" style="border-top: 1px solid var(--border); padding-top: 6px; margin-top: 6px; grid-column: span 3;"></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--purple);">CF mVaR 95%</span><span class="r-val" style="color:var(--purple);">${d.cfVaR.toFixed(2)}%</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--purple);">Jarque-Bera</span><span class="r-val" style="color:var(--purple);">${d.momentsJB.jb.toFixed(1)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--purple);">Omega Ratio</span><span class="r-val" style="color:var(--purple);">${d.omega.toFixed(2)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--cyan);">Hurst Exp</span><span class="r-val" style="color:var(--cyan);">${d.hurst.toFixed(2)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--cyan);">Ulcer Index</span><span class="r-val" style="color:var(--cyan);">${d.ulcer.toFixed(1)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--cyan);">AutoCorr (1W)</span><span class="r-val" style="color:var(--cyan);">${d.autoCorr.toFixed(2)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--orange);">Tail Ratio</span><span class="r-val" style="color:var(--orange);">${d.tailRatio.toFixed(2)}</span></div>
    </div>

    ${d.t === 'SPY' ? '' : `
    <div class="risk-grid" style="margin-top:-6px; background: rgba(57, 197, 207, 0.03); border-color: rgba(57, 197, 207, 0.15);">
      <div class="r-box" style="grid-column: span 3; background: transparent; padding: 2px 8px; text-align: center; border-bottom: 1px solid rgba(57, 197, 207, 0.2);">
        <span style="color:var(--cyan); font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase;">S&P 500 Benchmarking</span>
      </div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Beta vs SPY</span><span class="r-val ${d.beta>1.2?'r':d.beta<0.8?'y':'g'}">${d.beta.toFixed(2)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Ann. Alpha</span><span class="r-val ${d.alpha>0?'g':'r'}">${(d.alpha*100).toFixed(2)}%</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">R-Squared</span><span class="r-val" style="color:var(--cyan);">${d.r2.toFixed(2)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Treynor Ratio</span><span class="r-val ${d.treynor>0.05?'g':'r'}">${d.treynor.toFixed(3)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Up Capture</span><span class="r-val ${d.upCapture>100?'g':'y'}">${d.upCapture.toFixed(0)}%</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Down Capture</span><span class="r-val ${d.downCapture<100?'g':'r'}">${d.downCapture.toFixed(0)}%</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Info Ratio</span><span class="r-val ${d.infoRatio>0.5?'g':'y'}">${d.infoRatio.toFixed(2)}</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Track Error</span><span class="r-val" style="color:var(--cyan);">${(d.trackingError*100).toFixed(1)}%</span></div>
      <div class="r-box"><span class="r-lbl" style="color:var(--text-main);">Correlation</span><span class="r-val" style="color:var(--cyan);">${(Math.sqrt(d.r2)*(d.beta<0?-1:1)).toFixed(2)}</span></div>
    </div>
    `}

    <div class="quant-grid">
      <div class="q-box"><span class="q-lbl">Quant Score</span><span class="q-val ${scoreColor}">${d.score} / 100</span></div>
      <div class="q-box"><span class="q-lbl">Momentum</span><span class="q-val ${d.momCls}">${d.momentum}</span></div>
      <div class="q-box"><span class="q-lbl">Ann. Vol (SPY: ${sVol})</span><span class="q-val">${(d.vol*100).toFixed(1)}%</span></div>
      <div class="q-box"><span class="q-lbl">Sharpe (SPY: ${sShp})</span><span class="q-val ${d.sharpe>1?'g':d.sharpe>0?'y':'r'}">${d.sharpe.toFixed(2)}</span></div>
      <div class="q-box"><span class="q-lbl">Fib 61.8% Sup</span><span class="q-val b">$${d.tech.fib618.toFixed(2)}</span></div>
      <div class="q-box"><span class="q-lbl">Dist 52W High</span><span class="q-val ${d.tech.distHigh<-30?'r':'inherit'}">${d.tech.distHigh.toFixed(1)}%</span></div>
      <div class="q-box"><span class="q-lbl">MC 6M Median</span><span class="q-val ${d.mc.median>d.price?'g':'r'}">$${d.mc.median.toFixed(2)}</span></div>
      <div class="q-box"><span class="q-lbl">MC Bull (90%)</span><span class="q-val g">$${d.mc.p90.toFixed(2)}</span></div>
      <div class="q-box"><span class="q-lbl">MC Bear (10%)</span><span class="q-val r">$${d.mc.p10.toFixed(2)}</span></div>
    </div>

    <div class="spark-wrap">${spark(d.prices.slice(-52), d.mc.median > d.price)}</div>

    <div class="tech-bar">
      <div class="tech-item">RSI: <strong style="color:${d.rsi>75?'var(--red)':d.rsi<30?'var(--green)':'inherit'}">${d.rsi.toFixed(1)}</strong></div>
      <div class="tech-item">MACD: <strong style="color:${d.macd.hist>0?'var(--green)':'var(--red)'}">${d.macd.hist>0?'Bullish':'Bearish'}</strong></div>
      <div class="tech-item">Trend: <strong style="color:${d.tech.crossCls==='g'?'var(--green)':'var(--red)'}">${d.tech.cross}</strong></div>
      <div class="tech-item">Stoch: <strong style="color:${d.stoch>80?'var(--red)':d.stoch<20?'var(--green)':'inherit'}">${d.stoch.toFixed(0)}</strong></div>
    </div>
  </div>`;
}

// ============================
// DETAIL MODAL & CHART
// ============================
let chartInst = null, chartInst2 = null, chartInst3 = null, chartInst4 = null, chartInst5 = null, chartInst6 = null, chartInst7 = null, chartInst8 = null, chartInst9 = null, chartInst10 = null, chartInst11 = null, chartInst12 = null;
function closeDetail() { document.getElementById('detail-modal').style.display = 'none'; }
function openDetail(ticker, name) {
  const d = D[ticker];
  if (!d || !d.ok) return;
  
  document.getElementById('det-name').textContent = name;
  document.getElementById('det-sub').innerHTML = `<span style="color:#fff;font-weight:700;">$${d.price.toFixed(2)}</span> &nbsp;·&nbsp; ${ticker} &nbsp;·&nbsp; 1-Year Trajectory`;
  
  if (chartInst) chartInst.destroy();
  if (chartInst2) chartInst2.destroy();
  if (chartInst3) chartInst3.destroy();
  if (chartInst4) chartInst4.destroy();
  if (chartInst5) chartInst5.destroy();
  if (chartInst6) chartInst6.destroy();
  if (chartInst7) chartInst7.destroy();
  if (chartInst8) chartInst8.destroy();
  if (chartInst9) chartInst9.destroy();
  if (chartInst10) chartInst10.destroy();
  if (chartInst11) chartInst11.destroy();
  if (chartInst12) chartInst12.destroy();

  const dates = [], sma40 = [], bbUp = [], bbDn = [], ddData = [], wRets = [];
  let peak = d.prices[0];
  const oneWeek = 7 * 24 * 60 * 60 * 1000;
  const nowMs = Date.now();

  for (let i = 0; i < d.prices.length; i++) {
    const dt = new Date(nowMs - (d.prices.length - 1 - i) * oneWeek);
    dates.push(dt.toLocaleDateString(undefined, {year:'numeric', month:'short'}));
    
    if (d.prices[i] > peak) peak = d.prices[i];
    ddData.push(((d.prices[i] - peak) / peak) * 100);
    
    if (i > 0) wRets.push(((d.prices[i] - d.prices[i-1]) / d.prices[i-1]) * 100);
    
    if (i < 39) sma40.push(null);
    else sma40.push(d.prices.slice(i-39, i+1).reduce((a,b)=>a+b,0)/40);
    
    if (i < 19) { bbUp.push(null); bbDn.push(null); }
    else {
      const slice = d.prices.slice(i-19, i+1);
      const sma20 = slice.reduce((a,b)=>a+b,0)/20;
      const std = Math.sqrt(slice.reduce((a,b)=>a+Math.pow(b-sma20,2),0)/20);
      bbUp.push(sma20 + 2*std);
      bbDn.push(sma20 - 2*std);
    }
  }

  const bins = [], counts = [];
  for(let i=-20; i<=20; i+=2) { bins.push(i+'%'); counts.push(0); }
  for(let r of wRets) {
    let idx = Math.floor((r + 20) / 2);
    if(idx < 0) idx = 0;
    if(idx >= counts.length) idx = counts.length - 1;
    counts[idx]++;
  }

  // Normal Curve PDF Overlay
  const wStd = d.vol / Math.sqrt(52);
  const wMeanPct = wRets.reduce((a,b)=>a+b,0)/wRets.length;
  const wMeanDec = wMeanPct / 100;
  const normalCurve = [];
  for (let i = -20; i <= 20; i += 2) {
    const x = i / 100;
    const exponent = Math.exp(-Math.pow(x - wMeanDec, 2) / (2 * Math.pow(wStd, 2)));
    const pdf = (1 / (wStd * Math.sqrt(2 * Math.PI))) * exponent;
    normalCurve.push(pdf * wRets.length * 0.02);
  }

  const rollingVol = [], rollingBeta = [], rollingSharpe = [], rollingCorr = [];
  for (let i = 0; i < d.prices.length; i++) {
    if (i < 26) {
      rollingVol.push(null); rollingBeta.push(null); rollingSharpe.push(null); rollingCorr.push(null);
    } else {
      const windowPrices = d.prices.slice(i-26, i+1);
      const wR = [];
      for (let j = 1; j < windowPrices.length; j++) wR.push((windowPrices[j] - windowPrices[j-1]) / windowPrices[j-1]);
      const mean = wR.reduce((a,b)=>a+b,0)/26;
      const variance = wR.reduce((a,b)=>a+Math.pow(b-mean,2),0)/26;
      const rVol = Math.sqrt(variance) * Math.sqrt(52);
      rollingVol.push(rVol * 100);
      const rSharpe = rVol === 0 ? 0 : (mean * 52 - 0.045) / rVol;
      rollingSharpe.push(rSharpe);
      
      if (SPY_CLOSES && SPY_CLOSES.length > 0) {
        const bIndexEnd = SPY_CLOSES.length - (d.prices.length - i);
        if (bIndexEnd >= 26) {
          const bWindow = SPY_CLOSES.slice(bIndexEnd - 26, bIndexEnd + 1);
          const bR = [];
          for (let j = 1; j < bWindow.length; j++) bR.push((bWindow[j] - bWindow[j-1]) / bWindow[j-1]);
          const bMean = bR.reduce((a,b)=>a+b,0)/bR.length;
          let cov = 0, varB = 0, varP = 0;
          for (let k = 0; k < 26; k++) {
            cov  += (wR[k] - mean)  * (bR[k] - bMean);
            varB += Math.pow(bR[k] - bMean, 2);
            varP += Math.pow(wR[k] - mean,  2);
          }
          rollingBeta.push(varB === 0 ? 1 : cov / varB);
          rollingCorr.push((varP === 0 || varB === 0) ? 0 : cov / Math.sqrt(varP * varB));
        } else {
          rollingBeta.push(null); rollingCorr.push(null);
        }
      } else {
        rollingBeta.push(null); rollingCorr.push(null);
      }
    }
  }

  const mcPaths = [], mcLabels = [];
  for (let i = 0; i <= 26; i++) mcLabels.push('Wk ' + i);
  for (let p = 0; p < 15; p++) {
    const path = [d.price];
    let simP = d.price;
    for (let step = 0; step < 26; step++) {
      const u1 = Math.max(Math.random(), 1e-10), u2 = Math.random();
      const z = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
      simP = simP * Math.exp(wMeanDec - (wStd * wStd / 2) + wStd * z);
      path.push(simP);
    }
    mcPaths.push({ label: 'Path '+(p+1), data: path, borderColor: 'rgba(88,166,255,0.2)', borderWidth: 1, pointRadius: 0, fill: false, tension: 0.2 });
  }

  const d_dates = dates.slice(-52);
  const d_prices = d.prices.slice(-52);
  const d_sma40 = sma40.slice(-52);
  const d_bbUp = bbUp.slice(-52);
  const d_bbDn = bbDn.slice(-52);
  const d_ddData = ddData.slice(-52);
  const d_rollingVol = rollingVol.slice(-52);
  const d_rollingBeta = rollingBeta.slice(-52);
  const d_rollingSharpe = rollingSharpe.slice(-52);
  const d_rollingCorr = rollingCorr.slice(-52);

  Chart.defaults.color = 'rgba(255,255,255,0.7)';
  Chart.defaults.font.family = "'JetBrains Mono', monospace";

  
  // Trigger Fundamental Fetch
  document.getElementById('det-fundamentals').innerHTML = 'Loading Fundamentals...';
  fetchFundamentals(ticker).then(f => {
    let fHtml = '';
    if (f.mcap) fHtml += `Mkt Cap: <span style="color:#fff;">${(f.mcap/1e9).toFixed(1)}B</span> &nbsp;·&nbsp; `;
    if (f.pe) fHtml += `P/E: <span style="color:#fff;">${f.pe.toFixed(1)}x</span> &nbsp;·&nbsp; `;
    if (f.earnDate) fHtml += `Earnings: <span style="color:#fff;">${f.earnDate}</span>`;
    if (!fHtml) fHtml = 'No fundamental data found';
    document.getElementById('det-fundamentals').innerHTML = fHtml;
  });

  if (window.lwChartInst) { window.lwChartInst.remove(); window.lwChartInst = null; }
  const lwContainer = document.getElementById('det-lw-chart');
  if (lwContainer) {
    lwContainer.innerHTML = '';
    const chart = LightweightCharts.createChart(lwContainer, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b949e' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.1)' },
    });
    window.lwChartInst = chart;
    const candleSeries = chart.addCandlestickSeries({ upColor: '#3fb950', downColor: '#f85149', borderVisible: false, wickUpColor: '#3fb950', wickDownColor: '#f85149' });
    
    const ohlc = [];
    for(let i=0; i<d.prices.length; i++) {
      const p = d.prices[i];
      const prev = i>0 ? d.prices[i-1] : p;
      const tDate = new Date(nowMs - (d.prices.length - 1 - i) * oneWeek);
      ohlc.push({ time: tDate.toISOString().split('T')[0], open: prev, high: Math.max(prev,p)*1.02, low: Math.min(prev,p)*0.98, close: p });
    }
    candleSeries.setData(ohlc);

    const smaSeries = chart.addLineSeries({ color: '#58a6ff', lineWidth: 2, title: '40-Wk SMA' });
    const sData = [];
    for(let i=0; i<ohlc.length; i++) {
      if(i<39) continue;
      let sum=0; for(let j=0; j<40; j++) sum+=ohlc[i-j].close;
      sData.push({ time: ohlc[i].time, value: sum/40 });
    }
    smaSeries.setData(sData);
    chart.timeScale().fitContent();
  }


  chartInst2 = new Chart(document.getElementById('det-dd-chart').getContext('2d'), {
    type: 'line',
    data: {
      labels: d_dates,
      datasets: [{ label: 'Drawdown', data: d_ddData, borderColor: '#f85149', backgroundColor: 'rgba(248,81,73,0.15)', borderWidth: 1.5, pointRadius: 0, fill: true }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.parsed.y.toFixed(1)+'%'} } },
      scales: { x: { display: false }, y: { position: 'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  chartInst3 = new Chart(document.getElementById('det-dist-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: bins,
      datasets: [
        { label: 'Normal Distribution', data: normalCurve, type: 'line', borderColor: 'rgba(255,255,255,0.5)', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4, order: 1 },
        { label: 'Weeks', data: counts, backgroundColor: '#bc8cff', borderRadius: 2, order: 2 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1 } },
      scales: { x: { grid: { display: false } }, y: { display: false } }
    }
  });

  chartInst4 = new Chart(document.getElementById('det-vol-chart').getContext('2d'), {
    type: 'line',
    data: {
      labels: d_dates,
      datasets: [{ label: 'Rolling Volatility %', data: d_rollingVol, borderColor: '#e3b341', borderWidth: 1.5, pointRadius: 0, fill: false }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.parsed.y.toFixed(1)+'%'} } },
      scales: { x: { display: false }, y: { position: 'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  chartInst5 = new Chart(document.getElementById('det-beta-chart').getContext('2d'), {
    type: 'line',
    data: {
      labels: d_dates,
      datasets: [{ label: 'Rolling Beta', data: d_rollingBeta, borderColor: '#3fb950', borderWidth: 1.5, pointRadius: 0, fill: false }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.parsed.y.toFixed(2)} } },
      scales: { x: { display: false }, y: { position: 'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  chartInst6 = new Chart(document.getElementById('det-sharpe-chart').getContext('2d'), {
    type: 'line',
    data: {
      labels: d_dates,
      datasets: [{ label: 'Rolling Sharpe', data: d_rollingSharpe, borderColor: '#bc8cff', borderWidth: 1.5, pointRadius: 0, fill: false }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.parsed.y.toFixed(2)} } },
      scales: { x: { display: false }, y: { position: 'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  chartInst7 = new Chart(document.getElementById('det-mc-chart').getContext('2d'), {
    type: 'line',
    data: { labels: mcLabels, datasets: mcPaths },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>'$'+c.parsed.y.toFixed(2)} } },
      scales: { x: { display: false }, y: { position: 'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  // Chart 8: Rolling Correlation to SPY
  chartInst8 = new Chart(document.getElementById('det-corr-chart').getContext('2d'), {
    type: 'line',
    data: {
      labels: d_dates,
      datasets: [
        { label: 'Correlation', data: d_rollingCorr, borderColor: '#39c5cf', borderWidth: 1.5, pointRadius: 0, fill: false },
        { label: 'Zero', data: d_dates.map(()=>0), borderColor: 'rgba(255,255,255,0.2)', borderDash:[4,4], borderWidth:1, pointRadius:0, fill:false }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.dataset.label+': '+c.parsed.y.toFixed(2)} } },
      scales: { x: { display: false }, y: { position:'right', min:-1, max:1, grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  // Chart 9: VaR Stress Test Bar Chart
  const varFull = d.varFull || {p90:0, p95:0, p99:0};
  chartInst9 = new Chart(document.getElementById('det-var-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: ['VaR 90% (Hist.)', 'VaR 95% (Hist.)', 'VaR 99% (Hist.)', 'CF mVaR 95%', 'CVaR 95%'],
      datasets: [{
        label: 'Loss %',
        data: [varFull.p90, varFull.p95, varFull.p99, Math.abs(d.cfVaR), Math.abs(d.cvar95)],
        backgroundColor: ['rgba(88,166,255,0.6)', 'rgba(227,179,65,0.7)', 'rgba(248,81,73,0.7)', 'rgba(188,140,255,0.7)', 'rgba(248,81,73,0.5)'],
        borderColor:     ['#58a6ff', '#e3b341', '#f85149', '#bc8cff', '#f85149'],
        borderWidth: 1.5, borderRadius: 4
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>'-'+c.parsed.y.toFixed(2)+'%'} } },
      scales: { x: { grid:{ display:false }, ticks:{ font:{size:9} } }, y: { position:'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  // ---- Chart 10: GARCH(1,1) conditional volatility + forward forecast ----
  const garch = d.garch || {condVol:[], forecast:[], longRun:0};
  const gCond = garch.condVol.slice(-52);
  const gLabels = [];
  for (let i = 0; i < gCond.length; i++) gLabels.push('');
  const fLabels = garch.forecast.map((_,i)=>'+' + (i+1));
  const allGLabels = gLabels.concat(fLabels);
  // pad forecast so it begins where history ends
  const histPad = gCond.concat(garch.forecast.map(()=>null));
  const fcastPad = gCond.map(()=>null);
  if (gCond.length) fcastPad[gCond.length-1] = gCond[gCond.length-1];
  garch.forecast.forEach(v=>fcastPad.push(v));
  const lrLine = allGLabels.map(()=>garch.longRun);
  chartInst10 = new Chart(document.getElementById('det-garch-chart').getContext('2d'), {
    type: 'line',
    data: { labels: allGLabels, datasets: [
      { label: 'Conditional Vol', data: histPad, borderColor: '#e3b341', backgroundColor:'rgba(227,179,65,0.10)', borderWidth: 1.6, pointRadius: 0, fill: true, tension: 0.25 },
      { label: 'Forecast', data: fcastPad, borderColor: '#bc8cff', borderWidth: 1.8, borderDash:[5,3], pointRadius: 0, fill: false, tension: 0.25 },
      { label: 'Long-Run σ', data: lrLine, borderColor: 'rgba(255,255,255,0.25)', borderWidth: 1, borderDash:[2,3], pointRadius: 0, fill: false }
    ]},
    options: { responsive: true, maintainAspectRatio: false, interaction:{mode:'index',intersect:false},
      plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.dataset.label+': '+(c.parsed.y==null?'—':c.parsed.y.toFixed(1)+'%')} } },
      scales: { x: { grid:{display:false}, ticks:{maxTicksLimit:8, font:{size:8}} }, y: { position:'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
    }
  });

  // ---- Chart 11: Growth of $1 — Stock vs SPY vs SOXX (rebased relative performance) ----
  const rebase = (series, n) => { const s = series.slice(-n); if(!s.length) return []; const b = s[0]; return s.map(v => v / b); };
  const relN = 52;
  const stockGrowth = rebase(d.prices, relN);
  const spyGrowth = (SPY_CLOSES && SPY_CLOSES.length) ? rebase(SPY_CLOSES, relN) : [];
  const soxGrowth = (SOXX_CLOSES && SOXX_CLOSES.length) ? rebase(SOXX_CLOSES, relN) : [];
  const relLabels = d_dates;
  const relDatasets = [{ label: ticker, data: stockGrowth, borderColor: '#58a6ff', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.1 }];
  if (spyGrowth.length) relDatasets.push({ label: 'SPY', data: spyGrowth, borderColor: '#8b949e', borderWidth: 1.4, pointRadius: 0, fill: false, tension: 0.1 });
  if (soxGrowth.length) relDatasets.push({ label: 'SOXX', data: soxGrowth, borderColor: '#39c5cf', borderWidth: 1.4, borderDash:[4,3], pointRadius: 0, fill: false, tension: 0.1 });
  chartInst11 = new Chart(document.getElementById('det-rel-chart').getContext('2d'), {
    type: 'line', data: { labels: relLabels, datasets: relDatasets },
    options: { responsive: true, maintainAspectRatio: false, interaction:{mode:'index',intersect:false},
      plugins: { legend: { display: true, labels:{boxWidth:8, font:{size:9}, color:'#a0aab4'} }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>c.dataset.label+': '+(((c.parsed.y-1)*100).toFixed(1))+'%'} } },
      scales: { x: { display:false }, y: { position:'right', grid: { color: 'rgba(255,255,255,0.05)' }, ticks:{callback:(v)=>v.toFixed(2)+'x'} } }
    }
  });

  // ---- Chart 12: Normal Q–Q plot of weekly returns ----
  const qret = wRets.map(r=>r/100).slice().sort((a,b)=>a-b);
  const qn = qret.length;
  const qMean = qret.reduce((a,b)=>a+b,0)/qn;
  const qSd = Math.sqrt(qret.reduce((a,b)=>a+(b-qMean)**2,0)/qn) || 1;
  const qqPts = [];
  for (let i=0;i<qn;i++){ const p=(i+0.5)/qn; const theo=normInv(p); const emp=(qret[i]-qMean)/qSd; qqPts.push({x:theo,y:emp}); }
  const qLo = Math.min(qqPts[0].x, qqPts[0].y), qHi = Math.max(qqPts[qn-1].x, qqPts[qn-1].y);
  chartInst12 = new Chart(document.getElementById('det-qq-chart').getContext('2d'), {
    type: 'scatter',
    data: { datasets: [
      { label:'Sample Quantiles', data: qqPts, backgroundColor:'#bc8cff', pointRadius:2.5, pointHoverRadius:4 },
      { label:'Normal Reference', type:'line', data:[{x:qLo,y:qLo},{x:qHi,y:qHi}], borderColor:'rgba(255,255,255,0.4)', borderWidth:1.2, borderDash:[5,4], pointRadius:0, fill:false }
    ]},
    options: { responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{ backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>'theo '+c.parsed.x.toFixed(2)+' / emp '+c.parsed.y.toFixed(2)} } },
      scales:{ x:{ title:{display:true,text:'Theoretical (Normal)',color:'#6e7681',font:{size:9}}, grid:{color:'rgba(255,255,255,0.05)'} }, y:{ position:'right', title:{display:true,text:'Empirical',color:'#6e7681',font:{size:9}}, grid:{color:'rgba(255,255,255,0.05)'} } }
    }
  });

  // ---- Monthly return seasonality grid ----
  (function(){
    const monthSum = Array(12).fill(0), monthCnt = Array(12).fill(0);
    const mNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    for (let i=1;i<d.prices.length;i++){
      const dt = new Date(nowMs - (d.prices.length-1-i)*oneWeek);
      const m = dt.getMonth();
      monthSum[m] += ((d.prices[i]-d.prices[i-1])/d.prices[i-1])*100;
      monthCnt[m]++;
    }
    const avgs = monthSum.map((s,i)=> monthCnt[i] ? s/monthCnt[i] : null);
    const valid = avgs.filter(v=>v!=null);
    const maxAbs = Math.max(0.5, ...valid.map(v=>Math.abs(v)));
    let html='';
    for (let i=0;i<12;i++){
      const v = avgs[i];
      let bg='rgba(255,255,255,0.03)', col='var(--text-dim)', txt='—';
      if (v!=null){
        const inten = Math.min(1, Math.abs(v)/maxAbs);
        if (v>=0){ bg=`rgba(46,160,67,${0.12+inten*0.5})`; col='#7ee787'; }
        else { bg=`rgba(248,81,73,${0.12+inten*0.5})`; col='#ffa198'; }
        txt = (v>=0?'+':'')+v.toFixed(2)+'%';
      }
      html += `<div style="background:${bg};border:1px solid var(--border);border-radius:7px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2px;">
        <span style="font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;font-weight:700;">${mNames[i]}</span>
        <span style="font-family:var(--mono);font-size:12px;font-weight:800;color:${col};">${txt}</span></div>`;
    }
    document.getElementById('det-season-grid').innerHTML = html;
  })();

  document.getElementById('det-grid').innerHTML = `
    <div class="q-box"><span class="q-lbl">Treynor Ratio</span><span class="q-val ${d.treynor>0?'g':'r'}">${d.treynor.toFixed(3)}</span></div>
    <div class="q-box"><span class="q-lbl">Info Ratio</span><span class="q-val ${d.infoRatio>0.5?'g':d.infoRatio<0?'r':''}">${d.infoRatio.toFixed(3)}</span></div>
    <div class="q-box"><span class="q-lbl">R-Squared</span><span class="q-val">${(d.r2*100).toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">CVaR 95% (Wk)</span><span class="q-val r">${d.cvar95.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Quant Score</span><span class="q-val">${d.score}/100</span></div>

    <div class="q-box"><span class="q-lbl">Beta (vs SPY)</span><span class="q-val">${d.beta.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Annual Alpha</span><span class="q-val ${d.alpha>0?'g':'r'}">${(d.alpha*100).toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Half-Kelly Size</span><span class="q-val b">${d.kellyObj.size.toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">10-Wk SMA</span><span class="q-val">$${d.tech.sma10.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">40-Wk SMA</span><span class="q-val">$${d.tech.sma40.toFixed(2)}</span></div>

    <div class="q-box"><span class="q-lbl">Calmar Ratio</span><span class="q-val ${d.calmar>1?'g':d.calmar<0?'r':'y'}">${d.calmar.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">ATR (14-Wk %)</span><span class="q-val y">${d.atrPct.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Price Z-Score</span><span class="q-val ${d.priceZ>1.5?'r':d.priceZ<-1.5?'g':''}">${d.priceZ.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Win Rate (Wk)</span><span class="q-val ${d.kellyObj.winRate>0.55?'g':d.kellyObj.winRate<0.45?'r':''}">${(d.kellyObj.winRate*100).toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">Upside Capture</span><span class="q-val ${d.upCapture>100?'g':'r'}">${d.upCapture.toFixed(1)}%</span></div>

    <div class="q-box"><span class="q-lbl">Gain-to-Pain</span><span class="q-val ${d.gainToPain>1.5?'g':d.gainToPain<0.8?'r':'y'}">${d.gainToPain.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Pain Index</span><span class="q-val ${d.painIndex<5?'g':d.painIndex>15?'r':'y'}">${d.painIndex.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Recovery Factor</span><span class="q-val ${d.recoveryF>1?'g':d.recoveryF<0?'r':'y'}">${d.recoveryF.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Serenity Ratio</span><span class="q-val ${d.serenity>1?'g':d.serenity<0?'r':'y'}">${d.serenity.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">12-1 Momentum</span><span class="q-val ${d.momFactor>0?'g':'r'}">${d.momFactor.toFixed(1)}%</span></div>

    <div class="q-box"><span class="q-lbl">Vol Regime</span><span class="q-val ${d.volRegime>1.2?'r':d.volRegime<0.8?'g':'y'}">${d.volRegime.toFixed(2)}x</span></div>
    <div class="q-box"><span class="q-lbl">DD Duration (Wk)</span><span class="q-val ${d.ddDuration>26?'r':d.ddDuration<8?'g':'y'}">${d.ddDuration}</span></div>
    <div class="q-box"><span class="q-lbl">VaR 90% (Hist.)</span><span class="q-val r">-${varFull.p90.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">VaR 99% (Hist.)</span><span class="q-val r">-${varFull.p99.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Downside Capture</span><span class="q-val ${d.downCapture<100?'g':'r'}">${d.downCapture.toFixed(1)}%</span></div>

    <div class="q-box"><span class="q-lbl">CAGR (1Y)</span><span class="q-val ${d.cagr>0?'g':'r'}">${d.cagr.toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">EWMA Vol (λ=.94)</span><span class="q-val y">${d.ewmaVol.toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">GARCH Vol (now)</span><span class="q-val y">${d.garch.current.toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">GARCH Persist.</span><span class="q-val ${d.garch.persistence>0.95?'r':''}">${d.garch.persistence.toFixed(3)}</span></div>
    <div class="q-box"><span class="q-lbl">Prob. Sharpe</span><span class="q-val ${d.psr>0.95?'g':d.psr<0.5?'r':'y'}">${(d.psr*100).toFixed(1)}%</span></div>

    <div class="q-box"><span class="q-lbl">Param VaR 95%</span><span class="q-val r">-${d.paramVaR95.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Param VaR 99%</span><span class="q-val r">-${d.paramVaR99.toFixed(2)}%</span></div>
    <div class="q-box"><span class="q-lbl">Sector β (SOXX)</span><span class="q-val">${d.twoFactor.betaSoxxRaw.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Pure Market β</span><span class="q-val">${d.twoFactor.betaMkt.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Pure Sector β</span><span class="q-val">${d.twoFactor.betaSec.toFixed(2)}</span></div>

    <div class="q-box"><span class="q-lbl">Idiosyncratic Vol</span><span class="q-val ${d.twoFactor.idioVol>30?'r':'y'}">${d.twoFactor.idioVol.toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">2-Factor R²</span><span class="q-val">${(d.twoFactor.r2*100).toFixed(1)}%</span></div>
    <div class="q-box"><span class="q-lbl">Bull Beta (up)</span><span class="q-val g">${d.asymBeta.bull.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">Bear Beta (down)</span><span class="q-val ${d.asymBeta.bear>d.asymBeta.bull?'r':'g'}">${d.asymBeta.bear.toFixed(2)}</span></div>
    <div class="q-box"><span class="q-lbl">β Asymmetry</span><span class="q-val ${(d.asymBeta.bear-d.asymBeta.bull)>0.3?'r':''}">${(d.asymBeta.bear-d.asymBeta.bull).toFixed(2)}</span></div>
  `;
  
  document.getElementById('detail-modal').style.display = 'flex';
}

// ============================
// RENDER & FILTER & SORT
// ============================
function renderAll() {
  document.getElementById('grid').innerHTML = COS.map(cardHTML).join('');
  applyFS();
}

function refreshCard(co) {
  const id = `c${(co.t || co.n).replace(/[^a-z0-9]/gi,'_')}`;
  const el = document.getElementById(id);
  if (!el) return;
  const tmp = document.createElement('div');
  tmp.innerHTML = cardHTML(co);
  el.replaceWith(tmp.firstElementChild);
  applyFS();
}

function updateStats(loadedCount) {
  const vals = Object.values(D).filter(d => d.ok);
  document.getElementById('s-loaded').textContent  = loadedCount;
  document.getElementById('s-fear').textContent    = vals.filter(d => d.fg.val < 25).length;
  document.getElementById('s-greed').textContent   = vals.filter(d => d.fg.val > 75).length;
  document.getElementById('s-buy').textContent     = vals.filter(d => d.momentum === 'OVERSOLD').length;
  const avg = vals.reduce((a, b) => a + b.score, 0) / (vals.length || 1);
  document.getElementById('s-score').textContent   = vals.length ? avg.toFixed(0) : '—';
}

function setPill(cls, txt) {
  const p = document.getElementById('status-pill');
  p.className = `pill ${cls}`;
  p.textContent = txt;
}

async function loadAll() {
  const total = PUB.length;
  let loadedCount = 0;
  document.getElementById('s-total').textContent = total;
  document.getElementById('s-loaded').textContent = 0;
  document.getElementById('prog').style.width = '0%';
  D = {};
  
  setPill('loading', 'FETCHING SPY BENCHMARK...');
  try {
    const s = await fetchOne('SPY', true);
    if (s.ok) SPY_CLOSES = s.prices;
  } catch(e) {}

  setPill('loading', 'FETCHING SOXX SECTOR FACTOR...');
  try {
    const sx = await fetchOne('SOXX', true);
    if (sx.ok) SOXX_CLOSES = sx.prices;
  } catch(e) {}
  
  setPill('loading', 'EXECUTING QUANT MODELS...');
  renderAll();

  for (let i = 0; i < total; i += 4) {
    const batch = PUB.slice(i, i + 4);
    await Promise.all(batch.map(async co => {
      try {
        D[co.t] = await fetchOne(co.t);
      } catch(err) {
        console.warn(`[${co.t}] fetch threw:`, err);
        D[co.t] = { ok: false, source: 'Unexpected error' };
      }
      loadedCount++;
      document.getElementById('prog').style.width = `${Math.round(loadedCount / total * 100)}%`;
      refreshCard(co);
      updateStats(loadedCount);
    }));
  }


  // Batch fetch fundamentals for earnings tags (1 API call instead of 40)
  try {
    const allTickers = PUB.map(c => c.t).join(',');
    const yurl = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${allTickers}`;
    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(yurl)}`;
    const rF = await fetch(proxyUrl).then(x => x.json());
    if (rF && rF.quoteResponse && rF.quoteResponse.result) {
      rF.quoteResponse.result.forEach(res => {
        const t = res.symbol;
        if (D[t]) {
          D[t].fund = {
            pe: res.trailingPE || res.forwardPE,
            mcap: res.marketCap,
            earnDate: res.earningsTimestamp ? new Date(res.earningsTimestamp * 1000) : null
          };
          const co = COS.find(c => c.t === t);
          if (co) refreshCard(co);
        }
      });
    }
  } catch(e) { console.warn("Batched fundamental fetch failed", e); }

  COS.filter(c => !c.pub).forEach(co => refreshCard(co));

  const failCount = Object.values(D).filter(d => !d.ok).length;
  if (failCount === 0) {
    setPill('ok', `✓ ALL ${total} MODELS LIVE`);
  } else {
    const ok = total - failCount;
    setPill('ok', `✓ ${ok}/${total} LIVE · ${failCount} BLOCKED`);
  }

  const now = new Date();
  document.getElementById('ts-line').textContent =
    `Data refreshed: ${now.toLocaleDateString()} ${now.toLocaleTimeString()} (local) · Weekly close prices`;
}

function reloadAll() { D = {}; loadAll(); }

function changeTimeRange() {
  timeRangeYears = parseFloat(document.getElementById('time-range-sel').value);
  reloadAll();
}

function setFilter(f) {
  activeFilter = f;
  ['all','a','b','buy','fear'].forEach(x =>
    document.getElementById(`f-${x}`)?.classList.toggle('on', x === f));
  applyFS();
}

function doSearch(q) { searchQ = q.toLowerCase().trim(); applyFS(); }

function doSort(key) {
  sortKey = key;
  const grid = document.getElementById('grid');
  const cards = [...grid.querySelectorAll('.card')];
  const [field, dir] = key.split('-');
  if (!field) return;
  const dataKey = { score:'score', rsi:'rsi', chg6m:'chg6m', chg1y:'chg1y', vol:'vol' }[field];
  cards.sort((a, b) => {
    const av = parseFloat(a.dataset[dataKey] || 0);
    const bv = parseFloat(b.dataset[dataKey] || 0);
    return dir === 'd' ? bv - av : av - bv;
  });
  cards.forEach(c => grid.appendChild(c));
}

function applyFS() {
  document.querySelectorAll('.card').forEach(el => {
    const tier = el.dataset.tier, sc = parseFloat(el.dataset.score || 0), fg = parseFloat(el.dataset.fg || 50);
    let show = true;
    if (activeFilter === 'a')    show = tier === 'a';
    if (activeFilter === 'b')    show = tier === 'b';
    if (activeFilter === 'buy')  show = sc >= 70;
    if (activeFilter === 'fear') show = fg <= 25;
    if (searchQ && !el.innerText.toLowerCase().includes(searchQ)) show = false;
    el.style.display = show ? 'flex' : 'none';
  });
}

// ============================
// UNIVERSE MODALS
// ============================

let riskMapChart = null;
function toggleRiskMap() {
  const m = document.getElementById('risk-map-modal');
  if (m.style.display === 'flex') {
    m.style.display = 'none';
  } else {
    m.style.display = 'flex';
    renderRiskMap();
  }
}

function renderRiskMap() {
  const container = document.getElementById('risk-map-container');
  let canvas = document.getElementById('risk-map-canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.id = 'risk-map-canvas';
  }

  const data = [];
  for (const c of COS) {
    const d = D[c.t];
    if (d && d.ok) {
      data.push({ x: d.vol * 100, y: d.chg1y, ticker: c.t, r: 6 });
    }
  }

  if (data.length < 2) {
    container.innerHTML = "<p style='color:#f85149; text-align:center; margin-top:150px; font-weight:500;'>Not enough data loaded.<br><br>If this persists, your network may be blocking the free proxies. Please open Settings and add API keys.</p>";
    if (riskMapChart) { riskMapChart.destroy(); riskMapChart = null; }
    return;
  }
  
  if (!document.getElementById('risk-map-canvas')) {
    container.innerHTML = '';
    container.appendChild(canvas);
  }

  if (riskMapChart) riskMapChart.destroy();
  const ctx = canvas.getContext('2d');
  
  riskMapChart = new Chart(ctx, {
    type: 'bubble',
    data: {
      datasets: [{
        label: 'Universe Risk/Return',
        data: data,
        backgroundColor: 'rgba(57, 197, 207, 0.6)',
        borderColor: 'rgba(57, 197, 207, 1)'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return `${ctx.raw.ticker}: Vol ${ctx.raw.x.toFixed(1)}%, Ret ${ctx.raw.y.toFixed(1)}%`;
            }
          }
        }
      },
      scales: {
        x: { title: { display: true, text: 'Volatility (Risk) %', color: '#fff' }, ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.1)' } },
        y: { title: { display: true, text: '1Y Return %', color: '#fff' }, ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.1)' } }
      }
    }
  });
}

function toggleCorrelation() {
  const m = document.getElementById('correlation-modal');
  if (m.style.display === 'flex') {
    m.style.display = 'none';
  } else {
    m.style.display = 'flex';
    renderCorrelation();
  }
}

function renderCorrelation() {
  const container = document.getElementById('correlation-matrix-container');
  const validCos = COS.filter(c => D[c.t] && D[c.t].ok && D[c.t].prices);
  if (validCos.length < 2) {
    container.innerHTML = "<p style='color:#f85149; text-align:center; margin-top:250px; font-weight:500;'>Not enough data loaded.<br><br>If this persists, your network may be blocking the free proxies. Please open Settings and add API keys.</p>";
    return;
  }
  
  const cos = validCos.slice(0, 15);
  const n = cos.length;
  
  // Calculate matrix
  const matrix = Array(n).fill(0).map(()=>Array(n).fill(0));
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) {
        matrix[i][j] = 1;
      } else {
        const cP1 = D[cos[i].t].prices;
        const cP2 = D[cos[j].t].prices;
        const len = Math.min(cP1.length, cP2.length);
        const r1=[], r2=[];
        for(let k=1; k<len; k++) {
          r1.push((cP1[k]-cP1[k-1])/cP1[k-1]);
          r2.push((cP2[k]-cP2[k-1])/cP2[k-1]);
        }
        const mean1 = r1.reduce((a,b)=>a+b,0)/r1.length;
        const mean2 = r2.reduce((a,b)=>a+b,0)/r2.length;
        let num=0, den1=0, den2=0;
        for(let k=0; k<r1.length; k++) {
          num += (r1[k]-mean1)*(r2[k]-mean2);
          den1 += Math.pow(r1[k]-mean1, 2);
          den2 += Math.pow(r2[k]-mean2, 2);
        }
        matrix[i][j] = (den1===0||den2===0) ? 0 : num/Math.sqrt(den1*den2);
      }
    }
  }

  // Draw Heatmap on Canvas
  let canvas = document.getElementById('correlation-canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.id = 'correlation-canvas';
    canvas.style.borderRadius = '8px';
    canvas.style.boxShadow = '0 4px 15px rgba(0,0,0,0.5)';
  }
  container.innerHTML = ''; 
  container.appendChild(canvas); // Re-attach

  const W = 800; const H = 600;
  canvas.width = W * 2; canvas.height = H * 2; // Retina
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(2, 2);
  
  const paddingLeft = 100;
  const paddingTop = 100;
  const cellSize = Math.min((W - paddingLeft) / n, (H - paddingTop) / n);
  
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle = '#010409'; // bg
  ctx.fillRect(0,0,W,H);

  ctx.font = '12px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  for(let i=0; i<n; i++) {
    // Labels
    ctx.fillStyle = '#a0aab4';
    ctx.textAlign = 'right';
    ctx.fillText(cos[i].t, paddingLeft - 10, paddingTop + i*cellSize + cellSize/2);
    
    ctx.save();
    ctx.translate(paddingLeft + i*cellSize + cellSize/2, paddingTop - 10);
    ctx.rotate(-Math.PI/4);
    ctx.textAlign = 'left';
    ctx.fillText(cos[i].t, 0, 0);
    ctx.restore();

    for(let j=0; j<n; j++) {
      const v = matrix[i][j];
      // Color scale from Red (-1) to Black (0) to Green (1)
      let r, g, b;
      if (v > 0) {
        // Black to Green
        r = 0; g = Math.floor(v * 200); b = 0;
      } else {
        // Black to Red
        r = Math.floor(Math.abs(v) * 200); g = 0; b = 0;
      }
      
      const x = paddingLeft + j*cellSize;
      const y = paddingTop + i*cellSize;
      
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(x, y, cellSize-2, cellSize-2);
      
      // Text
      ctx.fillStyle = Math.abs(v) > 0.5 ? '#fff' : '#666';
      ctx.textAlign = 'center';
      ctx.fillText(v.toFixed(2), x + cellSize/2, y + cellSize/2);
    }
  }
}

// ============================
// PORTFOLIO OPTIMIZER (Markowitz Efficient Frontier)
// ============================
let pfChartInst = null;
let pfUniverse = 'all';

function togglePortfolio() {
  const m = document.getElementById('portfolio-modal');
  if (m.style.display === 'flex') { m.style.display = 'none'; }
  else { m.style.display = 'flex'; renderPortfolio(); }
}

function setPfUniverse(u) {
  pfUniverse = u;
  document.querySelectorAll('#pf-filterbar .btn').forEach(b => b.classList.remove('on'));
  const map = {all:'pf-f-all', a:'pf-f-a', Analog:'pf-f-analog', SerDes:'pf-f-serdes', AI:'pf-f-ai', Equipment:'pf-f-equip'};
  const btn = document.getElementById(map[u]); if (btn) btn.classList.add('on');
  renderPortfolio();
}

function selectPfAssets() {
  let pool = COS.filter(c => c.pub && c.t !== 'SPY' && D[c.t] && D[c.t].ok && D[c.t].prices && D[c.t].prices.length > 30);
  if (pfUniverse === 'a') pool = pool.filter(c => c.tier === 'a');
  else if (pfUniverse !== 'all') pool = pool.filter(c => c.sector === pfUniverse);
  return pool.slice(0, 28).map(c => ({ t: c.t, n: c.n, sector: c.sector, prices: D[c.t].prices }));
}

function optimizePortfolio(assets) {
  const RF = 0.045;
  const r = a => { const o = []; for (let i = 1; i < a.length; i++) o.push((a[i] - a[i-1]) / a[i-1]); return o; };
  const series = assets.map(a => r(a.prices));
  const minLen = Math.min(...series.map(s => s.length));
  const R = series.map(s => s.slice(-minLen));
  const n = R.length;
  const muW = R.map(s => s.reduce((a, b) => a + b, 0) / minLen);
  const mu = muW.map(m => m * 52);
  const cov = Array(n).fill(0).map(() => Array(n).fill(0));
  for (let i = 0; i < n; i++) for (let j = i; j < n; j++) {
    let c = 0; for (let k = 0; k < minLen; k++) c += (R[i][k] - muW[i]) * (R[j][k] - muW[j]);
    c = c / minLen * 52; cov[i][j] = c; cov[j][i] = c;
  }
  const vol = mu.map((_, i) => Math.sqrt(Math.max(0, cov[i][i])));
  const pStats = w => {
    let pr = 0; for (let i = 0; i < n; i++) pr += w[i] * mu[i];
    let pv = 0; for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) pv += w[i] * w[j] * cov[i][j];
    const sd = Math.sqrt(Math.max(0, pv));
    return { ret: pr, vol: sd, sharpe: sd === 0 ? 0 : (pr - RF) / sd };
  };
  const cloud = [];
  let maxSh = { sharpe: -Infinity }, minV = { vol: Infinity };
  for (let it = 0; it < 12000; it++) {
    let w = Array(n).fill(0).map(() => -Math.log(Math.max(Math.random(), 1e-12)));
    const s = w.reduce((a, b) => a + b, 0); w = w.map(x => x / s);
    const st = pStats(w);
    cloud.push({ x: st.vol * 100, y: st.ret * 100 });
    if (st.sharpe > maxSh.sharpe) maxSh = { ...st, w };
    if (st.vol < minV.vol) minV = { ...st, w };
  }
  let rp = vol.map(v => v > 0 ? 1 / v : 0); const rs = rp.reduce((a, b) => a + b, 0) || 1; rp = rp.map(x => x / rs);
  const rpStats = { ...pStats(rp), w: rp };
  const ew = Array(n).fill(1 / n); const ewStats = { ...pStats(ew), w: ew };
  const assetPts = assets.map((a, i) => ({ t: a.t, x: vol[i] * 100, y: mu[i] * 100 }));
  return { n, cloud, maxSh, minV, rp: rpStats, ew: ewStats, assets, assetPts };
}

function pfWeightTable(title, color, stats, assets) {
  const rows = stats.w.map((w, i) => ({ t: assets[i].t, w: w * 100 }))
    .filter(x => x.w > 0.8).sort((a, b) => b.w - a.w).slice(0, 8);
  let bars = rows.map(x => `
    <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
      <span style="font-family:var(--mono);font-size:10px;width:46px;color:var(--text-muted);">${x.t}</span>
      <div style="flex:1;height:9px;background:rgba(255,255,255,0.05);border-radius:5px;overflow:hidden;">
        <div style="height:100%;width:${Math.min(100,x.w)}%;background:${color};"></div></div>
      <span style="font-family:var(--mono);font-size:10px;width:42px;text-align:right;color:#fff;font-weight:700;">${x.w.toFixed(1)}%</span>
    </div>`).join('');
  return `
    <div style="background:var(--bg-card);border:1px solid var(--border);border-left:3px solid ${color};border-radius:10px;padding:12px 14px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">
        <span style="font-weight:800;color:${color};font-size:13px;letter-spacing:0.3px;">${title}</span>
        <span style="font-family:var(--mono);font-size:11px;color:var(--text-muted);">Sharpe ${stats.sharpe.toFixed(2)}</span>
      </div>
      <div style="display:flex;gap:14px;font-family:var(--mono);font-size:11px;margin-bottom:10px;">
        <span style="color:var(--text-muted);">Ret <b style="color:#7ee787;">${(stats.ret*100).toFixed(1)}%</b></span>
        <span style="color:var(--text-muted);">Vol <b style="color:#e3b341;">${(stats.vol*100).toFixed(1)}%</b></span>
      </div>
      ${bars}
    </div>`;
}

function renderPortfolio() {
  const results = document.getElementById('pf-results');
  const assets = selectPfAssets();
  if (assets.length < 3) {
    results.innerHTML = "<p style='color:#f85149;font-weight:500;'>Need at least 3 loaded tickers in this universe. Wait for data to finish loading, or pick a broader filter.</p>";
    if (pfChartInst) { pfChartInst.destroy(); pfChartInst = null; }
    return;
  }
  results.innerHTML = "<p style='color:var(--text-muted);'>Optimizing " + assets.length + " assets across 12,000 portfolios…</p>";

  setTimeout(() => {
    const o = optimizePortfolio(assets);
    results.innerHTML =
      pfWeightTable('★ MAX SHARPE (Tangency)', '#3fb950', o.maxSh, assets) +
      pfWeightTable('● MIN VARIANCE', '#58a6ff', o.minV, assets) +
      pfWeightTable('◆ RISK PARITY (Inv-Vol)', '#bc8cff', o.rp, assets) +
      pfWeightTable('○ EQUAL WEIGHT (1/N)', '#39c5cf', o.ew, assets) +
      `<p style="font-size:10px;color:var(--text-dim);line-height:1.5;margin-top:4px;">Long-only, fully invested. Frontier cloud = random simplex sampling. Past covariance is not predictive of future co-movement — for research only, not advice.</p>`;

    if (pfChartInst) pfChartInst.destroy();
    Chart.defaults.color = 'rgba(255,255,255,0.7)';
    Chart.defaults.font.family = "'JetBrains Mono', monospace";
    pfChartInst = new Chart(document.getElementById('pf-frontier-canvas').getContext('2d'), {
      type: 'scatter',
      data: { datasets: [
        { label: 'Portfolios', data: o.cloud, backgroundColor: 'rgba(88,166,255,0.13)', pointRadius: 1.6, pointHoverRadius: 2 },
        { label: 'Assets', data: o.assetPts, backgroundColor: 'rgba(227,179,65,0.9)', pointRadius: 4, pointHoverRadius: 6, pointStyle:'rectRot' },
        { label: 'Max Sharpe', data: [{ x: o.maxSh.vol*100, y: o.maxSh.ret*100 }], backgroundColor: '#3fb950', pointRadius: 9, pointHoverRadius: 11, pointStyle:'star' },
        { label: 'Min Variance', data: [{ x: o.minV.vol*100, y: o.minV.ret*100 }], backgroundColor: '#58a6ff', pointRadius: 7, pointHoverRadius: 9, pointStyle:'circle' },
        { label: 'Risk Parity', data: [{ x: o.rp.vol*100, y: o.rp.ret*100 }], backgroundColor: '#bc8cff', pointRadius: 7, pointHoverRadius: 9, pointStyle:'rect' },
        { label: 'Equal Weight', data: [{ x: o.ew.vol*100, y: o.ew.ret*100 }], backgroundColor: '#39c5cf', pointRadius: 7, pointHoverRadius: 9, pointStyle:'triangle' }
      ]},
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top', labels: { boxWidth: 8, font: { size: 9 }, color: '#a0aab4', filter: i => i.text !== 'Portfolios' } },
          tooltip: { backgroundColor: 'rgba(13,17,23,0.92)', titleColor: '#8b949e', bodyColor: '#fff', borderColor: 'rgba(99,102,241,0.8)', borderWidth: 1,
            callbacks: { label: c => { const t = c.dataset.data[c.dataIndex].t; return (t ? t + ': ' : c.dataset.label + ': ') + 'σ ' + c.parsed.x.toFixed(1) + '% / μ ' + c.parsed.y.toFixed(1) + '%'; } } }
        },
        scales: {
          x: { title: { display: true, text: 'Annualized Volatility (Risk) %', color: '#6e7681', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { title: { display: true, text: 'Annualized Return %', color: '#6e7681', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
        }
      }
    });
  }, 30);
}

// ============================
// BOOT
// ============================
document.getElementById('s-total').textContent = PUB.length;
loadAll();
