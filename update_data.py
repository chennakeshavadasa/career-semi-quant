import yfinance as yf
import json
import time

TICKERS = ["SPY", "SOXX", "TSM", "GFS", "SNPS", "CDNS", "ARM", "ASML", "AMAT", "LRCX", "KLAC", "TOELY", "MU", "WDC", "NVDA", "AMD", "SMCI", "AVGO", "MRVL", "CRDO", "ALAB", "RMBS", "MXL", "COHR", "LITE", "MTSI", "TXN", "ADI", "MPWR", "CRUS", "MCHP", "SLAB", "ON", "SYNA", "QCOM", "SWKS", "QRVO", "NXPI", "RNECY", "CEVA", "INTC", "SMTC", "SSNLF", "IFNNY", "STM", "PRTEF"]

data = {}
print("Fetching data using yfinance...")

for t in TICKERS:
    try:
        ticker = yf.Ticker(t)
        hist = ticker.history(period="5y", interval="1wk")
        if hist.empty:
            continue
        
        # We need closes
        closes = []
        for v in hist['Close'].values:
            if v > 0:
                closes.append(float(v))
                
        if len(closes) > 0:
            # Get fundamentals
            info = ticker.info
            data[t] = {
                "closes": closes,
                "fund": {
                    "pe": info.get('trailingPE') or info.get('forwardPE'),
                    "mcap": info.get('marketCap'),
                    "earnDate": None # yfinance earnDate is complex, skip for now
                }
            }
            print(f"Loaded {t}")
    except Exception as e:
        print(f"Failed {t}: {e}")
    time.sleep(0.1)

with open('market_data.json', 'w') as f:
    json.dump(data, f)
print("Saved to market_data.json")
