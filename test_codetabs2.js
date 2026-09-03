(async () => {
  try {
    const url = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1wk";
    const p = `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(url)}`;
    console.log("Fetching", p);
    const r = await fetch(p);
    console.log("Status:", r.status);
    const j = await r.json();
    console.log("Keys:", Object.keys(j));
  } catch(e) {
    console.error("Error:", e);
  }
})();
