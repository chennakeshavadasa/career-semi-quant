import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_fetch = """async function fetchFundamentals(ticker) {
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

new_fetch = """async function fetchFundamentals(ticker) {
  if (F[ticker]) return F[ticker];
  
  // 1. Primary: Yahoo Finance via Proxies
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
  } catch(e) { console.warn("Yahoo fundamentals failed, trying fallbacks..."); }

  // 2. Fallback: Finnhub
  if (apiKeys.finnhub) {
    try {
      const fh = await fetch(`https://finnhub.io/api/v1/stock/metric?symbol=${ticker}&metric=all&token=${apiKeys.finnhub}`).then(x => x.json());
      if (fh && fh.metric && fh.metric.marketCapitalization) {
        F[ticker] = {
          pe: fh.metric.peBasicExclExtraTTM || fh.metric.peExclExtraAnnual || null,
          mcap: fh.metric.marketCapitalization * 1e6, // Finnhub reports in millions
          eps: fh.metric.epsTTM || null,
          earnDate: null
        };
        return F[ticker];
      }
    } catch(e) { console.warn("Finnhub fundamentals failed", e); }
  }

  // 3. Fallback: Alpha Vantage
  if (apiKeys.alpha) {
    try {
      const av = await fetch(`https://www.alphavantage.co/query?function=OVERVIEW&symbol=${ticker}&apikey=${apiKeys.alpha}`).then(x => x.json());
      if (av && av.PERatio) {
        F[ticker] = {
          pe: parseFloat(av.PERatio) || null,
          mcap: parseFloat(av.MarketCapitalization) || null,
          eps: parseFloat(av.EPS) || null,
          earnDate: null
        };
        return F[ticker];
      }
    } catch(e) { console.warn("Alpha Vantage fundamentals failed", e); }
  }

  // All failed
  F[ticker] = { pe: null, mcap: null, eps: null, earnDate: null };
  return F[ticker];
}"""

if old_fetch in content:
    content = content.replace(old_fetch, new_fetch)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fallback fundamentals added successfully.")
else:
    print("Could not find the function to replace. Check string matching.")
