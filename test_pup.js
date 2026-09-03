const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ headless: "new", args: ['--no-sandbox'] });
  const page = await browser.newPage();
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));
  await page.goto('file:///home/nithin/quant-terminal/index.html');
  await new Promise(r => setTimeout(r, 3000));
  
  await page.evaluate(() => {
    const card = document.querySelector('.card');
    if (card) {
      console.log('Clicking card:', card.id);
      card.click();
    } else {
      console.log('No card found');
    }
  });
  
  await new Promise(r => setTimeout(r, 1000));
  await browser.close();
})();
