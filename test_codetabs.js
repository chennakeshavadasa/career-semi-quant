(async () => {
  try {
    const url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL";
    const p = `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(url)}`;
    console.log("Fetching", p);
    const r = await fetch(p);
    console.log("Status:", r.status);
    const j = await r.json();
    console.log("Keys:", Object.keys(j));
    if (j.quoteResponse) {
       console.log("Success! Price:", j.quoteResponse.result[0].regularMarketPrice);
    }
  } catch(e) {
    console.error("Error:", e);
  }
})();
