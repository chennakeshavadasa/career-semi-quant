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
