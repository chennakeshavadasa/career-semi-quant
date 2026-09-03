const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ headless: "new", args: ['--no-sandbox'] });
  const page = await browser.newPage();
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));
  await page.goto('file:///home/nithin/quant-terminal/index.html');
  
  await page.evaluate(() => {
    window.D = {
      'AAPL': {
        ok: true,
        price: 150,
        prices: [150, 151, 152, 153], // 4 items
        vol: 0.2, macd: {hist: 1}, tech: {crossCls: 'g'}, rsi: 50, stoch: 50
      }
    };
    window.SPY_CLOSES = [400, 401, 402, 403];
    window.openDetail('AAPL', 'Apple');
  });
  
  await new Promise(r => setTimeout(r, 1000));
  
  const errText = await page.evaluate(() => {
    return document.getElementById('det-lw-chart').innerHTML;
  });
  console.log("Chart innerHTML:", errText.includes("Chart rendering failed") ? "FAILED" : "SUCCESS");
  
  await browser.close();
})();
