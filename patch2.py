import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the Chart.js creation for det-chart with LightweightCharts
lw_js = """
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
"""

# We need to remove the old Chart.js instantiation for `det-chart`.
# The old one looks like `chartInst = new Chart(document.getElementById('det-chart').getContext('2d'), { ... });`
# It's likely right after the loop that prepares dates, sma40, etc.

content = re.sub(
    r"chartInst = new Chart\(document\.getElementById\('det-chart'\)\.getContext\('2d'\), \{.*?\}\);",
    lw_js,
    content,
    flags=re.DOTALL
)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
