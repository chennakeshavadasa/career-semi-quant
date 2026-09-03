import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Inject earnings/fundamentals call inside fetchOne
fetch_one_old = "const rsi   = calcRSI(closes, 14);"
fetch_one_new = """
  let fund = { pe: null, mcap: null, earnDate: null };
  try {
    const rF = await fetch(`https://api.allorigins.win/raw?url=${encodeURIComponent('https://query1.finance.yahoo.com/v7/finance/quote?symbols='+ticker)}`).then(x => x.json());
    const res = rF?.quoteResponse?.result?.[0];
    if (res) {
      fund = {
        pe: res.trailingPE || res.forwardPE,
        mcap: res.marketCap,
        earnDate: res.earningsTimestamp ? new Date(res.earningsTimestamp * 1000) : null
      };
    }
  } catch(e) {}
  
  const rsi   = calcRSI(closes, 14);
"""
if 'let fund = {' not in content:
    content = content.replace(fetch_one_old, fetch_one_new)

# Add earnings badge in cardHTML
card_html_old = """    <div class="c-top">
      <div><div class="c-name">${co.n}</div><div class="c-tkr">${co.t}</div></div>
      <div class="badges">${sectorB}${tierB}</div>
    </div>"""

card_html_new = """    <div class="c-top">
      <div><div class="c-name">${co.n}</div><div class="c-tkr">${co.t}</div></div>
      <div class="badges">${sectorB}${tierB}</div>
    </div>
    ${d && d.fund && d.fund.earnDate && (d.fund.earnDate.getTime() - Date.now() > 0 && d.fund.earnDate.getTime() - Date.now() < 14*86400000) ? `<div style="font-size:9px; background:rgba(255,165,0,0.2); color:orange; border-radius:4px; padding:2px 6px; display:inline-block; margin-top:4px;">⚠️ Earnings in ${Math.ceil((d.fund.earnDate.getTime() - Date.now())/86400000)} days</div>` : ''}"""
if '⚠️ Earnings' not in content:
    content = content.replace(card_html_old, card_html_new)

# Ensure fetchOne returns the 'fund' object
return_old = "return {"
return_new = "return { fund,"
if 'return { fund,' not in content:
    content = content.replace(return_old, return_new)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
