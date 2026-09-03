const yurl = 'https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1wk&period1=1690000000&period2=1720000000';
const proxies = [
  u => u,
  u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
  u => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
  u => `https://corsproxy.io/?${encodeURIComponent(u)}`
];

async function run() {
  for (let i = 0; i < proxies.length; i++) {
    const url = proxies[i](yurl);
    try {
      const res = await fetch(url);
      console.log(`Proxy ${i}: ${res.status} ${res.statusText}`);
      if (res.ok) {
         // const text = await res.text();
         // console.log(text.substring(0, 100));
      }
    } catch (e) {
      console.log(`Proxy ${i} failed:`, e.message);
    }
  }
}
run();
