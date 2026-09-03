import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace fetchFundamentals
old_fetch_fundamentals = """async function fetchFundamentals(ticker) {
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
}"""

new_fetch_fundamentals = """async function fetchFundamentals(ticker) {
  if (F[ticker]) return F[ticker];
  const yurl = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${ticker}`;
  const proxies = [
    u => u,
    u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
    u => `https://corsproxy.io/?${encodeURIComponent(u)}`
  ];
  try {
    const r = await Promise.any(proxies.map(mkP => fetch(mkP(yurl)).then(x => { if(!x.ok) throw new Error(); return x.json(); })));
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
}"""

content = content.replace(old_fetch_fundamentals, new_fetch_fundamentals)

# Replace batch fetch in loadAll
old_batch = """  // Batch fetch fundamentals for earnings tags (1 API call instead of 40)
  try {
    const allTickers = PUB.map(c => c.t).join(',');
    const yurl = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${allTickers}`;
    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(yurl)}`;
    const rF = await fetch(proxyUrl).then(x => x.json());
    if (rF?.quoteResponse?.result) {
      rF.quoteResponse.result.forEach(res => {
        if (D[res.symbol]) {
          D[res.symbol].fund = {
            pe: res.trailingPE || res.forwardPE,
            mcap: res.marketCap,
            eps: res.epsTrailingTwelveMonths,
            earnDate: res.earningsTimestamp ? new Date(res.earningsTimestamp * 1000) : null
          };
        }
      });
      renderAll(); // Re-render tags with earnings warnings
    }
  } catch(e) { console.warn("Batched fundamental fetch failed", e); }"""

new_batch = """  // Batch fetch fundamentals for earnings tags (1 API call instead of 40)
  try {
    const allTickers = PUB.map(c => c.t).join(',');
    const yurl = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${allTickers}`;
    const proxies = [
      u => u,
      u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
      u => `https://corsproxy.io/?${encodeURIComponent(u)}`
    ];
    const rF = await Promise.any(proxies.map(mkP => fetch(mkP(yurl)).then(x => { if(!x.ok) throw new Error(); return x.json(); })));
    if (rF?.quoteResponse?.result) {
      rF.quoteResponse.result.forEach(res => {
        if (D[res.symbol]) {
          D[res.symbol].fund = {
            pe: res.trailingPE || res.forwardPE,
            mcap: res.marketCap,
            eps: res.epsTrailingTwelveMonths,
            earnDate: res.earningsTimestamp ? new Date(res.earningsTimestamp * 1000) : null
          };
        }
      });
      renderAll(); // Re-render tags with earnings warnings
    }
  } catch(e) { console.warn("Batched fundamental fetch failed", e); }"""

content = content.replace(old_batch, new_batch)

# Also update openDetail to prefer d.fund
old_opendetail_fund = """  // Trigger Fundamental Fetch
  document.getElementById('det-fundamentals').innerHTML = 'Loading Fundamentals...';
  fetchFundamentals(ticker).then(f => {"""

new_opendetail_fund = """  // Trigger Fundamental Fetch
  document.getElementById('det-fundamentals').innerHTML = 'Loading Fundamentals...';
  if (d && d.fund && d.fund.mcap) { F[ticker] = { ...d.fund, earnDate: d.fund.earnDate ? d.fund.earnDate.toLocaleDateString() : null }; }
  fetchFundamentals(ticker).then(f => {"""

content = content.replace(old_opendetail_fund, new_opendetail_fund)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fundamentals proxy fixed.")
