const yurl = 'https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1wk&period1=1690000000&period2=1720000000';
const proxies = [
  u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
  u => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
  u => `https://corsproxy.io/?${encodeURIComponent(u)}`
];

async function run() {
  for (let i = 0; i < proxies.length; i++) {
    const url = proxies[i](yurl);
    try {
      const c = new AbortController();
      const id = setTimeout(() => c.abort(), 15000);
      const res = await fetch(url, { signal: c.signal });
      clearTimeout(id);
      console.log(`Proxy ${i}: ${res.status} ${res.statusText}`);
      if (res.ok) {
         console.log(await res.text().then(t => t.substring(0, 50)));
      }
    } catch (e) {
      console.log(`Proxy ${i} failed:`, e.message);
    }
  }
}
run();
