import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add Lightweight Charts CDN
if 'lightweight-charts' not in content:
    content = content.replace(
        '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>',
        '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>'
    )

# 2. Add header buttons
if 'toggleTracker' not in content:
    btns = """      <button class="btn" onclick="exportCSV()" style="border-color:#e3b341;color:#e3b341;">💾 EXPORT CSV</button>
      <button class="btn" onclick="toggleTracker()" style="border-color:#ff7b72;color:#ff7b72;">💼 TRACKER</button>
      <button class="btn" onclick="toggleBacktest()" style="border-color:#79c0ff;color:#79c0ff;">🔬 BACKTEST</button>"""
    content = content.replace(
        '<button class="btn" onclick="togglePortfolio()" style="border-color:var(--green-bright,var(--green));color:var(--green-bright,var(--green));">⚖ OPTIMIZER</button>',
        f'<button class="btn" onclick="togglePortfolio()" style="border-color:var(--green-bright,var(--green));color:var(--green-bright,var(--green));">⚖ OPTIMIZER</button>\n{btns}'
    )

# 3. Add Modals for Backtest and Tracker
modals_html = """
<!-- Backtest Modal -->
<div class="modal-bg" id="backtest-modal">
  <div class="modal-box" style="width: 900px; max-width: 95vw; height: 80vh; display: flex; flex-direction: column;">
    <h3>Strategy Backtesting Engine</h3>
    <p>Test a systematic strategy over the currently loaded historical data.</p>
    <div style="display:flex; gap:10px; margin-bottom:15px; flex-shrink: 0;">
      <select id="bt-strategy" class="search" style="padding:8px;">
        <option value="rsi">RSI Mean Reversion (Buy < 30, Sell > 70)</option>
        <option value="macd">MACD Trend Following (Buy Cross Up, Sell Cross Down)</option>
      </select>
      <button class="btn" onclick="runBacktest()">Run Backtest on Universe</button>
      <button class="btn" onclick="toggleBacktest()">Close</button>
    </div>
    <div id="bt-results" style="flex: 1; overflow-y: auto;"></div>
  </div>
</div>

<!-- Tracker Modal -->
<div class="modal-bg" id="tracker-modal">
  <div class="modal-box" style="width: 800px; max-width: 95vw; height: 80vh; display: flex; flex-direction: column;">
    <h3>Custom Portfolio Tracker</h3>
    <div style="display:flex; gap:10px; margin-bottom:15px; flex-shrink: 0;">
      <input type="text" id="trk-ticker" class="search" placeholder="Ticker (e.g. NVDA)" style="width:120px;">
      <input type="number" id="trk-shares" class="search" placeholder="Shares" style="width:100px;">
      <button class="btn" onclick="addToTracker()">Add</button>
      <button class="btn" onclick="clearTracker()">Clear All</button>
      <button class="btn" onclick="toggleTracker()">Close</button>
    </div>
    <div id="trk-holdings" style="flex: 1; overflow-y: auto; margin-bottom:20px;"></div>
    <div id="trk-summary" style="font-family:var(--mono); font-size:16px; padding:15px; background:rgba(0,0,0,0.3); border-radius:8px; flex-shrink: 0;"></div>
  </div>
</div>
"""
if 'backtest-modal' not in content:
    content = content.replace('<!-- Settings Modal -->', modals_html + '\n<!-- Settings Modal -->')

# 4. Modify Detail Modal for Lightweight Charts & Fundamentals
det_old = """      <h3 style="margin-top:0px; margin-bottom:8px; font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; font-weight:600;">Price Action, 40-Wk SMA & Volatility Bands</h3>
      <div style="height:350px; min-height:350px; position:relative; background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:10px; padding:10px;">
        <canvas id="det-chart"></canvas>
      </div>"""

det_new = """      <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:8px;">
        <h3 style="margin:0px; font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; font-weight:600;">Interactive Candlesticks, 40-Wk SMA & Volatility Bands</h3>
        <div id="det-fundamentals" style="font-family:var(--mono); font-size:12px; color:var(--blue); background:rgba(88,166,255,0.1); padding:4px 8px; border-radius:4px; border:1px solid rgba(88,166,255,0.2);">Loading Fundamentals...</div>
      </div>
      <div style="height:400px; min-height:400px; position:relative; background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:10px; padding:10px;" id="det-lw-chart">
      </div>"""
if 'det-lw-chart' not in content:
    content = content.replace(det_old, det_new)

# 5. Add JS functions
js_code = """
// --- NEW FEATURES ---

function exportCSV() {
  if (Object.keys(D).length === 0) return alert("No data loaded yet.");
  let csv = "Ticker,Name,Sector,Price,6M_Return,1Y_Return,RSI,Volatility,Sharpe,Sortino,QuantScore\\n";
  COS.forEach(co => {
    const d = D[co.t];
    if (d && d.ok) {
      csv += `${co.t},"${co.n}",${co.sector},${d.price.toFixed(2)},${d.chg6m.toFixed(2)},${d.chg1y.toFixed(2)},${d.rsi.toFixed(2)},${d.vol.toFixed(2)},${d.sharpe.toFixed(2)},${d.sortino.toFixed(2)},${d.score}\\n`;
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
"""
if 'function exportCSV' not in content:
    content = content.replace('// ============================', js_code + '\n// ============================', 1)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
