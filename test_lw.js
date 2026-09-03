  const d = { prices: Array.from({length: 100}, (_, i) => 150 + Math.sin(i)) };
  const nowMs = Date.now();
  const oneWeek = 7 * 24 * 60 * 60 * 1000;
  
  const ohlc = [];
  for(let i=0; i<d.prices.length; i++) {
    const p = d.prices[i];
    const prev = i>0 ? d.prices[i-1] : p;
    const tDate = new Date(nowMs - (d.prices.length - 1 - i) * oneWeek);
    ohlc.push({ 
      time: tDate.toISOString().split('T')[0], 
      open: prev, 
      high: Math.max(prev,p)*1.02, 
      low: Math.min(prev,p)*0.98, 
      close: p 
    });
  }
  
  let duplicateFound = false;
  for (let i = 1; i < ohlc.length; i++) {
    if (ohlc[i].time <= ohlc[i-1].time) {
      console.error(`Duplicate or decreasing time at ${i}: ${ohlc[i-1].time} -> ${ohlc[i].time}`);
      duplicateFound = true;
    }
  }
  if (!duplicateFound) console.log("Data generated successfully. Time is strictly increasing.");
