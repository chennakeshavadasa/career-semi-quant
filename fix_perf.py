import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove the blocking fetch from fetchOne
bad_fetch_pattern = re.compile(
    r"  let fund = \{ pe: null, mcap: null, earnDate: null \};\s+"
    r"try \{\s+"
    r"const rF = await fetch\(`https://api\.allorigins\.win/raw\?url=\$\{encodeURIComponent\('https://query1\.finance\.yahoo\.com/v7/finance/quote\?symbols='\+ticker\)\}`\)\.then\(x => x\.json\(\)\);\s+"
    r"const res = rF\?\.quoteResponse\?\.result\?\.\[0\];\s+"
    r"if \(res\) \{\s+"
    r"fund = \{\s+"
    r"pe: res\.trailingPE \|\| res\.forwardPE,\s+"
    r"mcap: res\.marketCap,\s+"
    r"earnDate: res\.earningsTimestamp \? new Date\(res\.earningsTimestamp \* 1000\) : null\s+"
    r"\};\s+"
    r"\}\s+"
    r"\} catch\(e\) \{\}\s+"
    r"const rsi   = calcRSI\(closes, 14\);"
)

if bad_fetch_pattern.search(content):
    content = bad_fetch_pattern.sub("  const rsi   = calcRSI(closes, 14);", content)
else:
    print("Could not find the fundamental fetch block in fetchOne.")

# 2. Add the batched fetch to loadAll() right after the loop finishes
batch_fetch_code = """
  // Batch fetch fundamentals for earnings tags (1 API call instead of 40)
  try {
    const allTickers = PUB.map(c => c.t).join(',');
    const yurl = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${allTickers}`;
    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(yurl)}`;
    const rF = await fetch(proxyUrl).then(x => x.json());
    if (rF && rF.quoteResponse && rF.quoteResponse.result) {
      rF.quoteResponse.result.forEach(res => {
        const t = res.symbol;
        if (D[t]) {
          D[t].fund = {
            pe: res.trailingPE || res.forwardPE,
            mcap: res.marketCap,
            earnDate: res.earningsTimestamp ? new Date(res.earningsTimestamp * 1000) : null
          };
          const co = COS.find(c => c.t === t);
          if (co) refreshCard(co);
        }
      });
    }
  } catch(e) { console.warn("Batched fundamental fetch failed", e); }

  COS.filter(c => !c.pub).forEach(co => refreshCard(co));"""

# find `COS.filter(c => !c.pub).forEach(co => refreshCard(co));` in loadAll
if 'COS.filter(c => !c.pub).forEach(co => refreshCard(co));' in content:
    content = content.replace('  COS.filter(c => !c.pub).forEach(co => refreshCard(co));', batch_fetch_code)
else:
    print("Could not find COS.filter in loadAll.")

# 3. Remove `fund,` from fetchOne returns to prevent undefined variable error since we deleted `let fund`
content = content.replace('return { fund,', 'return {')
content = content.replace('  return {\n    fund,', '  return {\n   ')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done patching.")
