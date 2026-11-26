"""Ticker universes: the 71-name semiconductor universe (kept identical to the web
terminal's `COS` list), the market dashboard groups, benchmarks and factor ETFs."""
from __future__ import annotations

# (ticker, name, sector, tier). Tier A = large / core names, Tier B = smaller or niche.
SEMIS: list[tuple[str, str, str, str]] = [
    ('SPY', 'S&P 500 ETF', 'Market', 'A'),
    ('TSM', 'Taiwan Semi (TSMC)', 'Foundry', 'A'),
    ('GFS', 'GlobalFoundries', 'Foundry', 'B'),
    ('UMC', 'United Microelectronics', 'Foundry', 'B'),
    ('TSEM', 'Tower Semiconductor', 'Foundry', 'B'),
    ('AMKR', 'Amkor Technology', 'OSAT', 'B'),
    ('ASX', 'ASE Technology', 'OSAT', 'B'),
    ('SNPS', 'Synopsys', 'EDA', 'A'),
    ('CDNS', 'Cadence Design Sys.', 'EDA', 'A'),
    ('ARM', 'ARM Holdings', 'IP', 'A'),
    ('ASML', 'ASML Holding', 'Equipment', 'A'),
    ('AMAT', 'Applied Materials', 'Equipment', 'A'),
    ('LRCX', 'Lam Research', 'Equipment', 'A'),
    ('KLAC', 'KLA Corporation', 'Equipment', 'A'),
    ('8035.T', 'Tokyo Electron', 'Equipment', 'A'),
    ('ASM.AS', 'ASM International', 'Equipment', 'A'),
    ('ENTG', 'Entegris', 'Equipment', 'B'),
    ('ONTO', 'Onto Innovation', 'Equipment', 'B'),
    ('CAMT', 'Camtek', 'Equipment', 'B'),
    ('NVMI', 'Nova Ltd', 'Equipment', 'B'),
    ('TER', 'Teradyne', 'Test', 'A'),
    ('6857.T', 'Advantest', 'Test', 'A'),
    ('FORM', 'FormFactor', 'Test', 'B'),
    ('MU', 'Micron Technology', 'Memory', 'A'),
    ('005930.KS', 'Samsung Electronics', 'Memory', 'A'),
    ('000660.KS', 'SK Hynix', 'Memory', 'A'),
    ('WDC', 'Western Digital', 'Memory', 'B'),
    ('SNDK', 'SanDisk', 'Memory', 'A'),
    ('STX', 'Seagate Technology', 'Memory', 'A'),
    ('SIMO', 'Silicon Motion', 'Memory', 'B'),
    ('NVDA', 'NVIDIA', 'AI', 'A'),
    ('AMD', 'AMD', 'AI', 'A'),
    ('SMCI', 'Super Micro Computer', 'AI', 'A'),
    ('INTC', 'Intel', 'CPU', 'A'),
    ('2454.TW', 'MediaTek', 'Fabless', 'A'),
    ('LSCC', 'Lattice Semiconductor', 'Fabless', 'A'),
    ('AMBA', 'Ambarella', 'Fabless', 'B'),
    ('SITM', 'SiTime', 'Fabless', 'B'),
    ('AVGO', 'Broadcom', 'SerDes', 'A'),
    ('MRVL', 'Marvell Technology', 'SerDes', 'A'),
    ('CRDO', 'Credo Technology', 'SerDes', 'A'),
    ('ALAB', 'Astera Labs', 'SerDes', 'A'),
    ('RMBS', 'Rambus', 'SerDes', 'A'),
    ('MXL', 'MaxLinear', 'SerDes', 'B'),
    ('4966.TWO', 'Parade Technologies', 'SerDes', 'B'),
    ('COHR', 'Coherent Corp', 'Optical', 'A'),
    ('LITE', 'Lumentum Holdings', 'Optical', 'A'),
    ('MTSI', 'MACOM Technology', 'Optical', 'A'),
    ('CIEN', 'Ciena', 'Optical', 'A'),
    ('FN', 'Fabrinet', 'Optical', 'B'),
    ('ANET', 'Arista Networks', 'Networking', 'A'),
    ('TXN', 'Texas Instruments', 'Analog', 'A'),
    ('ADI', 'Analog Devices', 'Analog', 'A'),
    ('MPWR', 'Monolithic Power', 'Analog', 'A'),
    ('CRUS', 'Cirrus Logic', 'Analog', 'A'),
    ('MCHP', 'Microchip Technology', 'Analog', 'A'),
    ('SLAB', 'Silicon Laboratories', 'Analog', 'A'),
    ('ON', 'onsemi', 'Analog', 'A'),
    ('SYNA', 'Synaptics', 'Analog', 'B'),
    ('STM', 'STMicroelectronics', 'Analog', 'B'),
    ('QCOM', 'Qualcomm', 'RF', 'A'),
    ('SWKS', 'Skyworks Solutions', 'RF', 'B'),
    ('QRVO', 'Qorvo', 'RF', 'B'),
    ('NXPI', 'NXP Semiconductors', 'MCU', 'A'),
    ('RNECY', 'Renesas Electronics', 'MCU', 'A'),
    ('CEVA', 'CEVA Inc', 'DSP', 'B'),
    ('IFNNY', 'Infineon Technologies', 'Power', 'B'),
    ('SMTC', 'Semtech', 'Power', 'B'),
    ('ALGM', 'Allegro MicroSystems', 'Power', 'B'),
    ('POWI', 'Power Integrations', 'Power', 'B'),
    ('NVTS', 'Navitas Semiconductor', 'Power', 'B'),
]

SEMI_TICKERS = [t for t, _, s, _ in SEMIS if s != "Market"]
META = {t: {"ticker": t, "name": n, "sector": s, "tier": tier} for t, n, s, tier in SEMIS}

# Benchmarks used across analytics.
BENCHMARKS = {"SPY": "S&P 500", "SOXX": "Semiconductors (SOXX)", "QQQ": "Nasdaq 100"}

# Style factors as long-short ETF spreads (daily returns): name -> (long, short or None).
STYLE_FACTORS = {
    "Market": ("SPY", None),
    "Semis": ("SOXX", "SPY"),
    "Size": ("IWM", "SPY"),
    "Value": ("IWD", "IWF"),
    "Momentum": ("MTUM", "SPY"),
    "Quality": ("QUAL", "SPY"),
    "Low vol": ("USMV", "SPY"),
}
# Macro sensitivities: name -> (ticker, kind). kind "ret" = % return, "chg" = level change.
MACRO_FACTORS = {
    "S&P 500": ("SPY", "ret"),
    "10Y yield": ("^TNX", "chg"),
    "US dollar": ("DX-Y.NYB", "ret"),
    "Oil": ("CL=F", "ret"),
    "VIX": ("^VIX", "chg"),
}
FACTOR_ETFS = sorted({t for pair in STYLE_FACTORS.values() for t in pair if t}
                     | {t for t, _ in MACRO_FACTORS.values()})

# Market dashboard groups: (symbol, label).
MARKET_GROUPS: dict[str, list[tuple[str, str]]] = {
    "US indices": [("^GSPC", "S&P 500"), ("^NDX", "Nasdaq 100"), ("^DJI", "Dow 30"),
                   ("^RUT", "Russell 2000"), ("^SOX", "PHLX Semis"), ("^VIX", "VIX")],
    "Futures": [("ES=F", "S&P fut"), ("NQ=F", "Nasdaq fut"), ("YM=F", "Dow fut"), ("RTY=F", "Russell fut")],
    "Rates": [("^IRX", "13-week"), ("^FVX", "5-year"), ("^TNX", "10-year"), ("^TYX", "30-year")],
    "FX & crypto": [("DX-Y.NYB", "Dollar index"), ("EURUSD=X", "EUR/USD"), ("USDJPY=X", "USD/JPY"),
                    ("USDKRW=X", "USD/KRW"), ("USDTWD=X", "USD/TWD"), ("BTC-USD", "Bitcoin")],
    "Commodities": [("GC=F", "Gold"), ("SI=F", "Silver"), ("HG=F", "Copper"), ("CL=F", "WTI crude"), ("NG=F", "Nat gas")],
    "Global": [("^STOXX50E", "Euro Stoxx 50"), ("^GDAXI", "DAX"), ("^FTSE", "FTSE 100"), ("^N225", "Nikkei 225"),
               ("^HSI", "Hang Seng"), ("^KS11", "KOSPI"), ("^TWII", "Taiwan"), ("000001.SS", "Shanghai")],
}
VIX_TERM = [("^VIX9D", "9D"), ("^VIX", "30D"), ("^VIX3M", "3M"), ("^VIX6M", "6M"), ("^VIX1Y", "1Y")]
YIELD_CURVE = [("^IRX", "3M", 0.25), ("^FVX", "5Y", 5.0), ("^TNX", "10Y", 10.0), ("^TYX", "30Y", 30.0)]
SECTOR_ETFS = [("XLK", "Technology"), ("SMH", "Semis (SMH)"), ("SOXX", "Semis (SOXX)"), ("XLC", "Communication"),
               ("XLY", "Discretionary"), ("XLF", "Financials"), ("XLV", "Health care"), ("XLI", "Industrials"),
               ("XLE", "Energy"), ("XLB", "Materials"), ("XLP", "Staples"), ("XLRE", "Real estate"), ("XLU", "Utilities")]

# Historical stress windows (start, end inclusive): replayed on daily closes.
STRESS_WINDOWS: list[tuple[str, str, str]] = [
    ("Global financial crisis", "2008-09-01", "2009-03-09"),
    ("Flash crash / euro crisis", "2010-04-23", "2010-07-02"),
    ("US downgrade", "2011-07-22", "2011-10-03"),
    ("China devaluation", "2015-08-10", "2015-08-25"),
    ("Volmageddon", "2018-01-26", "2018-02-08"),
    ("Q4 2018 selloff", "2018-10-03", "2018-12-24"),
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("2022 bear market", "2022-01-03", "2022-10-12"),
    ("SVB banking stress", "2023-03-08", "2023-03-13"),
    ("Yen carry unwind", "2024-07-10", "2024-08-07"),
    ("DeepSeek shock", "2025-01-24", "2025-01-27"),
    ("2025 tariff shock", "2025-04-02", "2025-04-08"),
]


def sectors() -> list[str]:
    return sorted({s for _, _, s, _ in SEMIS if s != "Market"})


def meta(ticker: str) -> dict:
    return META.get(ticker.upper(), {"ticker": ticker.upper(), "name": None, "sector": None, "tier": None})


# ─── Broader universes (beyond semiconductors) ───────────────────────────────
# (ticker, name, group). Group = GICS sector, region or ETF category; it drives the
# heatmap grouping and the screener's sector filter. Delisted / renamed tickers are
# flagged in the UI ("no recent trades") instead of breaking anything.

US_LARGE: list[tuple[str, str, str]] = [
    # Information Technology
    ("AAPL", "Apple", "Technology"), ("MSFT", "Microsoft", "Technology"), ("NVDA", "NVIDIA", "Technology"),
    ("AVGO", "Broadcom", "Technology"), ("ORCL", "Oracle", "Technology"), ("CRM", "Salesforce", "Technology"),
    ("AMD", "AMD", "Technology"), ("ADBE", "Adobe", "Technology"), ("CSCO", "Cisco", "Technology"),
    ("ACN", "Accenture", "Technology"), ("IBM", "IBM", "Technology"), ("NOW", "ServiceNow", "Technology"),
    ("INTU", "Intuit", "Technology"), ("QCOM", "Qualcomm", "Technology"), ("TXN", "Texas Instruments", "Technology"),
    ("MU", "Micron", "Technology"), ("AMAT", "Applied Materials", "Technology"), ("LRCX", "Lam Research", "Technology"),
    ("KLAC", "KLA", "Technology"), ("ADI", "Analog Devices", "Technology"), ("INTC", "Intel", "Technology"),
    ("PANW", "Palo Alto Networks", "Technology"), ("CRWD", "CrowdStrike", "Technology"), ("PLTR", "Palantir", "Technology"),
    ("FTNT", "Fortinet", "Technology"), ("WDAY", "Workday", "Technology"), ("ADSK", "Autodesk", "Technology"),
    ("DELL", "Dell Technologies", "Technology"), ("APH", "Amphenol", "Technology"), ("MSI", "Motorola Solutions", "Technology"),
    # Communication Services
    ("GOOGL", "Alphabet", "Communication"), ("META", "Meta Platforms", "Communication"), ("NFLX", "Netflix", "Communication"),
    ("DIS", "Walt Disney", "Communication"), ("TMUS", "T-Mobile US", "Communication"), ("VZ", "Verizon", "Communication"),
    ("T", "AT&T", "Communication"), ("CMCSA", "Comcast", "Communication"), ("CHTR", "Charter Communications", "Communication"),
    ("TTWO", "Take-Two Interactive", "Communication"),
    # Consumer Discretionary
    ("AMZN", "Amazon", "Consumer discretionary"), ("TSLA", "Tesla", "Consumer discretionary"), ("HD", "Home Depot", "Consumer discretionary"),
    ("MCD", "McDonald's", "Consumer discretionary"), ("LOW", "Lowe's", "Consumer discretionary"), ("BKNG", "Booking Holdings", "Consumer discretionary"),
    ("TJX", "TJX Companies", "Consumer discretionary"), ("SBUX", "Starbucks", "Consumer discretionary"), ("NKE", "Nike", "Consumer discretionary"),
    ("CMG", "Chipotle", "Consumer discretionary"), ("ABNB", "Airbnb", "Consumer discretionary"), ("ORLY", "O'Reilly Automotive", "Consumer discretionary"),
    ("MAR", "Marriott", "Consumer discretionary"), ("GM", "General Motors", "Consumer discretionary"), ("F", "Ford", "Consumer discretionary"),
    ("RCL", "Royal Caribbean", "Consumer discretionary"), ("DASH", "DoorDash", "Consumer discretionary"),
    # Consumer Staples
    ("WMT", "Walmart", "Consumer staples"), ("COST", "Costco", "Consumer staples"), ("PG", "Procter & Gamble", "Consumer staples"),
    ("KO", "Coca-Cola", "Consumer staples"), ("PEP", "PepsiCo", "Consumer staples"), ("PM", "Philip Morris", "Consumer staples"),
    ("MO", "Altria", "Consumer staples"), ("MDLZ", "Mondelez", "Consumer staples"), ("CL", "Colgate-Palmolive", "Consumer staples"),
    ("TGT", "Target", "Consumer staples"), ("KDP", "Keurig Dr Pepper", "Consumer staples"), ("MNST", "Monster Beverage", "Consumer staples"),
    # Health Care
    ("LLY", "Eli Lilly", "Health care"), ("UNH", "UnitedHealth", "Health care"), ("JNJ", "Johnson & Johnson", "Health care"),
    ("ABBV", "AbbVie", "Health care"), ("MRK", "Merck", "Health care"), ("PFE", "Pfizer", "Health care"),
    ("TMO", "Thermo Fisher", "Health care"), ("ABT", "Abbott", "Health care"), ("DHR", "Danaher", "Health care"),
    ("ISRG", "Intuitive Surgical", "Health care"), ("AMGN", "Amgen", "Health care"), ("GILD", "Gilead", "Health care"),
    ("VRTX", "Vertex", "Health care"), ("BSX", "Boston Scientific", "Health care"), ("SYK", "Stryker", "Health care"),
    ("MDT", "Medtronic", "Health care"), ("CVS", "CVS Health", "Health care"), ("REGN", "Regeneron", "Health care"),
    # Financials
    ("BRK-B", "Berkshire Hathaway", "Financials"), ("JPM", "JPMorgan Chase", "Financials"), ("V", "Visa", "Financials"),
    ("MA", "Mastercard", "Financials"), ("BAC", "Bank of America", "Financials"), ("WFC", "Wells Fargo", "Financials"),
    ("GS", "Goldman Sachs", "Financials"), ("MS", "Morgan Stanley", "Financials"), ("C", "Citigroup", "Financials"),
    ("AXP", "American Express", "Financials"), ("SCHW", "Charles Schwab", "Financials"), ("BLK", "BlackRock", "Financials"),
    ("SPGI", "S&P Global", "Financials"), ("PGR", "Progressive", "Financials"), ("CB", "Chubb", "Financials"),
    ("MRSH", "Marsh McLennan", "Financials"), ("COF", "Capital One", "Financials"), ("BX", "Blackstone", "Financials"),
    ("KKR", "KKR", "Financials"), ("CME", "CME Group", "Financials"), ("ICE", "Intercontinental Exchange", "Financials"),
    ("PYPL", "PayPal", "Financials"),
    # Industrials
    ("GE", "GE Aerospace", "Industrials"), ("CAT", "Caterpillar", "Industrials"), ("RTX", "RTX", "Industrials"),
    ("HON", "Honeywell", "Industrials"), ("UNP", "Union Pacific", "Industrials"), ("BA", "Boeing", "Industrials"),
    ("DE", "Deere", "Industrials"), ("LMT", "Lockheed Martin", "Industrials"), ("UPS", "UPS", "Industrials"),
    ("ETN", "Eaton", "Industrials"), ("ADP", "ADP", "Industrials"), ("WM", "Waste Management", "Industrials"),
    ("GD", "General Dynamics", "Industrials"), ("NOC", "Northrop Grumman", "Industrials"), ("MMM", "3M", "Industrials"),
    ("FDX", "FedEx", "Industrials"), ("UBER", "Uber", "Industrials"), ("CSX", "CSX", "Industrials"),
    ("PH", "Parker-Hannifin", "Industrials"), ("VRT", "Vertiv", "Industrials"), ("GEV", "GE Vernova", "Industrials"),
    ("PWR", "Quanta Services", "Industrials"),
    # Energy
    ("XOM", "Exxon Mobil", "Energy"), ("CVX", "Chevron", "Energy"), ("COP", "ConocoPhillips", "Energy"), ("SLB", "SLB", "Energy"),
    ("EOG", "EOG Resources", "Energy"), ("PSX", "Phillips 66", "Energy"), ("MPC", "Marathon Petroleum", "Energy"),
    ("OXY", "Occidental", "Energy"), ("WMB", "Williams", "Energy"), ("KMI", "Kinder Morgan", "Energy"),
    # Utilities
    ("NEE", "NextEra Energy", "Utilities"), ("SO", "Southern Co", "Utilities"), ("DUK", "Duke Energy", "Utilities"),
    ("CEG", "Constellation Energy", "Utilities"), ("VST", "Vistra", "Utilities"), ("AEP", "American Electric Power", "Utilities"),
    ("SRE", "Sempra", "Utilities"), ("D", "Dominion Energy", "Utilities"),
    # Real Estate
    ("PLD", "Prologis", "Real estate"), ("AMT", "American Tower", "Real estate"), ("EQIX", "Equinix", "Real estate"),
    ("WELL", "Welltower", "Real estate"), ("SPG", "Simon Property", "Real estate"), ("O", "Realty Income", "Real estate"),
    ("DLR", "Digital Realty", "Real estate"), ("PSA", "Public Storage", "Real estate"),
    # Materials
    ("LIN", "Linde", "Materials"), ("SHW", "Sherwin-Williams", "Materials"), ("APD", "Air Products", "Materials"),
    ("ECL", "Ecolab", "Materials"), ("FCX", "Freeport-McMoRan", "Materials"), ("NEM", "Newmont", "Materials"),
    ("DOW", "Dow", "Materials"), ("NUE", "Nucor", "Materials"),
]

GLOBAL: list[tuple[str, str, str]] = [
    # Europe
    ("ASML", "ASML", "Europe"), ("SAP", "SAP", "Europe"), ("NVO", "Novo Nordisk", "Europe"), ("AZN", "AstraZeneca", "Europe"),
    ("SHEL", "Shell", "Europe"), ("TTE", "TotalEnergies", "Europe"), ("BP", "BP", "Europe"), ("HSBC", "HSBC", "Europe"),
    ("UL", "Unilever", "Europe"), ("NVS", "Novartis", "Europe"), ("SNY", "Sanofi", "Europe"), ("DEO", "Diageo", "Europe"),
    ("BTI", "British American Tobacco", "Europe"), ("UBS", "UBS", "Europe"), ("SAN", "Banco Santander", "Europe"),
    ("SPOT", "Spotify", "Europe"), ("MC.PA", "LVMH", "Europe"), ("SIE.DE", "Siemens", "Europe"),
    ("NESN.SW", "Nestle", "Europe"), ("RHHBY", "Roche", "Europe"),
    # Japan
    ("TM", "Toyota", "Japan"), ("SONY", "Sony", "Japan"), ("MUFG", "Mitsubishi UFJ", "Japan"), ("SMFG", "Sumitomo Mitsui", "Japan"),
    ("HMC", "Honda", "Japan"), ("7974.T", "Nintendo", "Japan"), ("9984.T", "SoftBank Group", "Japan"), ("6861.T", "Keyence", "Japan"),
    ("8035.T", "Tokyo Electron", "Japan"),
    # China & Hong Kong
    ("BABA", "Alibaba", "China"), ("0700.HK", "Tencent", "China"), ("PDD", "PDD Holdings", "China"), ("JD", "JD.com", "China"),
    ("BIDU", "Baidu", "China"), ("NTES", "NetEase", "China"), ("1211.HK", "BYD", "China"), ("3690.HK", "Meituan", "China"),
    ("TCOM", "Trip.com", "China"),
    # Korea & Taiwan
    ("TSM", "TSMC", "Korea & Taiwan"), ("005930.KS", "Samsung Electronics", "Korea & Taiwan"),
    ("000660.KS", "SK hynix", "Korea & Taiwan"), ("2317.TW", "Hon Hai (Foxconn)", "Korea & Taiwan"),
    ("2454.TW", "MediaTek", "Korea & Taiwan"),
    # India
    ("INFY", "Infosys", "India"), ("HDB", "HDFC Bank", "India"), ("IBN", "ICICI Bank", "India"), ("WIT", "Wipro", "India"),
    ("RELIANCE.NS", "Reliance Industries", "India"), ("TCS.NS", "Tata Consultancy", "India"),
    # Americas ex-US
    ("RY", "Royal Bank of Canada", "Canada"), ("TD", "Toronto-Dominion", "Canada"), ("SHOP", "Shopify", "Canada"),
    ("ENB", "Enbridge", "Canada"), ("CNQ", "Canadian Natural", "Canada"), ("MELI", "MercadoLibre", "Latin America"),
    ("NU", "Nu Holdings", "Latin America"), ("VALE", "Vale", "Latin America"), ("PBR", "Petrobras", "Latin America"),
    ("ITUB", "Itau Unibanco", "Latin America"),
    # Asia-Pacific other
    ("BHP", "BHP", "Australia"), ("RIO", "Rio Tinto", "Australia"), ("CBA.AX", "Commonwealth Bank", "Australia"),
    ("SE", "Sea Ltd", "Southeast Asia"), ("GRAB", "Grab", "Southeast Asia"),
]

ETFS: list[tuple[str, str, str]] = [
    ("SPY", "S&P 500", "Broad equity"), ("QQQ", "Nasdaq 100", "Broad equity"), ("DIA", "Dow 30", "Broad equity"),
    ("IWM", "Russell 2000", "Broad equity"), ("VTI", "Total US market", "Broad equity"), ("RSP", "S&P 500 equal weight", "Broad equity"),
    ("ACWI", "All-country world", "Broad equity"), ("VEA", "Developed ex-US", "Broad equity"), ("VWO", "Emerging markets", "Broad equity"),
    ("XLK", "Technology", "US sectors"), ("XLC", "Communication", "US sectors"), ("XLY", "Discretionary", "US sectors"),
    ("XLP", "Staples", "US sectors"), ("XLE", "Energy", "US sectors"), ("XLF", "Financials", "US sectors"),
    ("XLV", "Health care", "US sectors"), ("XLI", "Industrials", "US sectors"), ("XLB", "Materials", "US sectors"),
    ("XLRE", "Real estate", "US sectors"), ("XLU", "Utilities", "US sectors"), ("SMH", "Semiconductors (VanEck)", "US sectors"),
    ("SOXX", "Semiconductors (iShares)", "US sectors"), ("IGV", "Software", "US sectors"), ("XBI", "Biotech", "US sectors"),
    ("KRE", "Regional banks", "US sectors"), ("ITB", "Homebuilders", "US sectors"), ("ITA", "Aerospace & defense", "US sectors"),
    ("MTUM", "Momentum factor", "Factors"), ("QUAL", "Quality factor", "Factors"), ("USMV", "Minimum volatility", "Factors"),
    ("VLUE", "Value factor", "Factors"), ("IWF", "Russell 1000 growth", "Factors"), ("IWD", "Russell 1000 value", "Factors"),
    ("SCHD", "Dividend equity", "Factors"),
    ("SHY", "Treasuries 1-3y", "Bonds"), ("IEF", "Treasuries 7-10y", "Bonds"), ("TLT", "Treasuries 20y+", "Bonds"),
    ("TIP", "Inflation-protected", "Bonds"), ("LQD", "Investment-grade corporate", "Bonds"), ("HYG", "High yield", "Bonds"),
    ("AGG", "US aggregate bonds", "Bonds"), ("EMB", "EM sovereign bonds", "Bonds"),
    ("GLD", "Gold", "Commodities & crypto"), ("SLV", "Silver", "Commodities & crypto"), ("USO", "Crude oil", "Commodities & crypto"),
    ("DBC", "Commodity basket", "Commodities & crypto"), ("CPER", "Copper", "Commodities & crypto"),
    ("IBIT", "Bitcoin", "Commodities & crypto"), ("ETHA", "Ether", "Commodities & crypto"),
    ("EWJ", "Japan", "Countries"), ("FXI", "China large caps", "Countries"), ("MCHI", "China", "Countries"),
    ("INDA", "India", "Countries"), ("EWT", "Taiwan", "Countries"), ("EWY", "South Korea", "Countries"),
    ("EWG", "Germany", "Countries"), ("EWU", "United Kingdom", "Countries"), ("EWZ", "Brazil", "Countries"),
    ("EWC", "Canada", "Countries"),
    ("ARKK", "Innovation (ARK)", "Themes"), ("BOTZ", "Robotics & AI", "Themes"), ("URA", "Uranium", "Themes"),
    ("TAN", "Solar", "Themes"), ("LIT", "Lithium & batteries", "Themes"), ("ICLN", "Clean energy", "Themes"),
]

UNIVERSES: dict[str, dict] = {
    "semis": {"label": "Semiconductors", "group_label": "Sub-sector", "bench": "SPY", "sector_bench": "SOXX",
              "regime": "SOXX", "rows": [(t, n, s) for t, n, s, _ in SEMIS if s != "Market"]},
    "us_large": {"label": "US large caps", "group_label": "Sector", "bench": "SPY", "sector_bench": "SPY",
                 "regime": "SPY", "rows": US_LARGE},
    "global": {"label": "Global leaders", "group_label": "Region", "bench": "ACWI", "sector_bench": "ACWI",
               "regime": "ACWI", "rows": GLOBAL},
    "etfs": {"label": "ETFs", "group_label": "Category", "bench": "SPY", "sector_bench": "SPY",
             "regime": "SPY", "rows": ETFS},
}
STOCK_UNIVERSES = ("semis", "us_large", "global")


def get_universe(key: str | None) -> dict:
    return UNIVERSES.get(key or "semis") or UNIVERSES["semis"]


def universe_key(key: str | None) -> str:
    return key if key in UNIVERSES else "semis"


def universe_tickers(key: str | None) -> list[str]:
    return [t for t, _, _ in get_universe(key)["rows"]]


def universe_meta(key: str | None) -> dict[str, dict]:
    k = universe_key(key)
    out = {}
    for t, n, s in UNIVERSES[k]["rows"]:
        tier = META.get(t, {}).get("tier") if k == "semis" else None
        out[t] = {"ticker": t, "name": n, "sector": s, "tier": tier, "universe": k}
    return out


# Every known ticker; semiconductors first so their sub-sector and tier win.
ALL_META: dict[str, dict] = {}
for _k in UNIVERSES:
    for _t, _m in universe_meta(_k).items():
        ALL_META.setdefault(_t, _m)


def home_universe(ticker: str) -> str | None:
    """First universe that lists the ticker (semis, then US large caps, global, ETFs)."""
    t = (ticker or "").upper()
    for k in UNIVERSES:
        if any(r[0] == t for r in UNIVERSES[k]["rows"]):
            return k
    return None
