const fs = require('fs');
const jsdom = require("jsdom");
const { JSDOM } = jsdom;
const html = fs.readFileSync('index.html', 'utf-8');
const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://localhost" });
const window = dom.window;

// Mock external things like Chart, fetch
window.Chart = class { constructor() {} destroy() {} };
window.Chart.defaults = { color: '', font: { family: '' } };
window.LightweightCharts = { 
  createChart: () => ({ 
    addCandlestickSeries: () => ({ setData: () => {} }),
    addLineSeries: () => ({ setData: () => {} }),
    timeScale: () => ({ fitContent: () => {} })
  }) 
};

// Expose the global functions to node
setTimeout(() => {
  try {
    console.log("Setting mock D");
    window.D = { 'AAPL': { ok: true, price: 150, prices: Array(100).fill(150), vol: 0.2, macd: {hist:1}, tech: {crossCls:'g'}, rsi:50, stoch:50 } };
    window.openDetail('AAPL', 'Apple');
    console.log("openDetail executed without throwing.");
  } catch(e) {
    console.error("ERROR in openDetail:", e);
  }
}, 500);
