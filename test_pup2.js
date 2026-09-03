const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ headless: "new", args: ['--no-sandbox'] });
  const page = await browser.newPage();
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));
  await page.goto('file:///home/nithin/quant-terminal/index.html');
  
  await page.evaluate(() => {
    // Inject mock data
    window.D = {
      'AAPL': {
        ok: true,
        price: 150,
        prices: Array(100).fill(150),
        vol: 0.2,
        macd: {hist: 1},
        tech: {crossCls: 'g'},
        rsi: 50,
        stoch: 50
      }
    };
    window.SPY_CLOSES = Array(100).fill(400);
    window.SOXX_CLOSES = Array(100).fill(500);
    console.log('Opening detail for AAPL');
    window.openDetail('AAPL', 'Apple');
  });
  
  await new Promise(r => setTimeout(r, 1000));
  await browser.close();
})();
