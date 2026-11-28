"""The map behind the World risk page: which flashpoints and straits matter, what flows through them, which
markets react, and how chip supply depends on them.

This is curated judgement, not data: approximate public figures (EIA, USGS, industry bodies), kept general on
purpose because the world changes faster than a file. The live numbers (ships per day, news volume, prices)
come from the data layers and are never hard-coded here.
"""
from __future__ import annotations

# ─── Markets that transmit shocks (Yahoo symbols) ─────────────────────────────────────────────
ASSETS: dict[str, dict] = {
    "BZ=F": {"label": "Brent crude", "group": "Energy"},
    "CL=F": {"label": "WTI crude", "group": "Energy"},
    "NG=F": {"label": "US natural gas", "group": "Energy"},
    "TTF=F": {"label": "Dutch TTF gas (Europe)", "group": "Energy"},
    "BDRY": {"label": "Dry-bulk freight ETF", "group": "Shipping"},
    "ZIM": {"label": "ZIM (container line)", "group": "Shipping"},
    "MATX": {"label": "Matson (Pacific container)", "group": "Shipping"},
    "FRO": {"label": "Frontline (crude tankers)", "group": "Shipping"},
    "STNG": {"label": "Scorpio Tankers", "group": "Shipping"},
    "ITA": {"label": "US defense ETF", "group": "Havens & defense"},
    "GC=F": {"label": "Gold", "group": "Havens & defense"},
    "^VIX": {"label": "VIX", "group": "Havens & defense"},
    "DX-Y.NYB": {"label": "Dollar index", "group": "Havens & defense"},
    "ZW=F": {"label": "Wheat", "group": "Food & metals"},
    "HG=F": {"label": "Copper", "group": "Food & metals"},
    "REMX": {"label": "Rare-earth miners ETF", "group": "Food & metals"},
    "SOXX": {"label": "Semiconductors (SOXX)", "group": "Asia & chips"},
    "TSM": {"label": "TSMC", "group": "Asia & chips"},
    "EWT": {"label": "Taiwan ETF", "group": "Asia & chips"},
    "EWY": {"label": "Korea ETF", "group": "Asia & chips"},
    "EWJ": {"label": "Japan ETF", "group": "Asia & chips"},
    "FXI": {"label": "China large caps ETF", "group": "Asia & chips"},
    "INDA": {"label": "India ETF", "group": "Asia & chips"},
}
ASSET_GROUPS = ["Energy", "Shipping", "Havens & defense", "Food & metals", "Asia & chips"]

# ─── Chokepoints (PortWatch ids) ──────────────────────────────────────────────────────────────
# role: what it is; carries: what flows; if_closed: the workaround and its cost; theatres / assets: links.
CHOKEPOINTS: dict[str, dict] = {
    "chokepoint6": {
        "role": "The only sea exit of the Persian Gulf (Iran, Iraq, Kuwait, Saudi Arabia's east coast, Bahrain, Qatar, UAE).",
        "carries": "About a fifth of the world's oil consumption and of its LNG trade (EIA); Qatar's LNG and helium; Gulf petrochemicals, fertilizer and aluminium.",
        "if_closed": "Only partial bypasses for oil (Saudi pipeline to the Red Sea, UAE pipeline to Fujairah), a few million barrels a day against normal flows of about 20 million. LNG has no bypass.",
        "theatres": ["iran_gulf"], "assets": ["BZ=F", "CL=F", "NG=F", "TTF=F", "FRO", "STNG", "ITA"]},
    "chokepoint1": {
        "role": "Canal linking the Mediterranean with the Red Sea: the short route between Asia and Europe.",
        "carries": "About 12% of world trade and roughly 30% of container traffic (Suez Canal Authority); oil, LNG, electronics, machinery.",
        "if_closed": "Ships go round the Cape of Good Hope: roughly 10 extra days Asia to northern Europe, more fuel, higher freight and insurance.",
        "theatres": ["red_sea", "israel_gaza"], "assets": ["ZIM", "BDRY", "BZ=F"]},
    "chokepoint4": {
        "role": "Gate between the Red Sea and the Gulf of Aden, the southern end of the Suez route.",
        "carries": "Container ships, tankers and bulk carriers heading to or from Suez. Attacks on ships near the strait since late 2023 pushed many carriers onto the Cape route.",
        "if_closed": "Same as Suez: the Cape of Good Hope detour, roughly +10 days Asia to Europe.",
        "theatres": ["red_sea", "sudan_horn"], "assets": ["ZIM", "BDRY", "BZ=F"]},
    "chokepoint7": {
        "role": "The southern tip of Africa: the alternative to Suez.",
        "carries": "Traffic rises here when the Red Sea is unsafe; also bulk ore and grain between the Atlantic and Indian oceans.",
        "if_closed": "Very rarely closed; weather rather than conflict is its main risk.",
        "theatres": ["red_sea"], "assets": ["ZIM", "BDRY"]},
    "chokepoint5": {
        "role": "Between Malaysia/Singapore and Indonesia: the main sea link between the Indian Ocean and the South China Sea.",
        "carries": "Roughly a quarter of world trade and much of the Gulf oil bound for East Asia; Singapore's port traffic.",
        "if_closed": "Ships can use the Sunda or Lombok straits in Indonesia: about 1 to 3 extra days, but with limited capacity for the largest tankers.",
        "theatres": ["south_china_sea"], "assets": ["BZ=F", "BDRY", "SOXX"]},
    "chokepoint11": {
        "role": "Between Taiwan and mainland China, one of the busiest shipping lanes on earth.",
        "carries": "Trade of China, Japan, Korea and Taiwan; Taiwan's own imports (it brings in nearly all its energy by sea, much of it LNG) and exports of chips and electronics.",
        "if_closed": "Ships can pass east of Taiwan for roughly a day, but a blockade or inspection regime would hit Taiwan's imports and exports directly, and insurers would reprice the whole region.",
        "theatres": ["taiwan"], "assets": ["TSM", "SOXX", "EWT"]},
    "chokepoint14": {
        "role": "Between Taiwan and the Philippines: the gateway from the South China Sea to the Pacific.",
        "carries": "Traffic to and from the Americas; a main route for undersea data cables. Takes the overflow when the Taiwan Strait is avoided.",
        "if_closed": "Alternatives exist through other Philippine straits, at modest extra distance.",
        "theatres": ["taiwan", "south_china_sea"], "assets": ["TSM", "EWT"]},
    "chokepoint12": {
        "role": "Between Korea and Japan: Busan, Korea's largest port, sits on it.",
        "carries": "Korean exports (including chips and memory), Japan-Korea trade, Russia-Far East links.",
        "if_closed": "Ships can go round Japan's east coast, adding about a day or more.",
        "theatres": ["korea", "east_china_sea"], "assets": ["EWY", "EWJ"]},
    "chokepoint3": {
        "role": "The Bosporus (with the Dardanelles): the only sea exit from the Black Sea.",
        "carries": "Grain, sunflower oil, fertilizer and oil from Russia, Ukraine, Romania, Bulgaria and Georgia.",
        "if_closed": "No sea alternative; some cargo can go by rail, road or the Danube.",
        "theatres": ["ukraine_russia", "black_sea"], "assets": ["ZW=F", "TTF=F"]},
    "chokepoint28": {
        "role": "Between the Black Sea and the Sea of Azov, beside Crimea.",
        "carries": "Traffic of Russian Azov ports (grain, coal, metals). Traffic is thin and often invisible to ship tracking.",
        "if_closed": "Azov ports lose their sea access.",
        "theatres": ["ukraine_russia", "black_sea"], "assets": ["ZW=F"]},
    "chokepoint2": {
        "role": "Canal between the Atlantic and the Pacific.",
        "carries": "About 5% of world trade: US East Coast to Asia containers, US LNG, LPG and grain. Limited by water levels in a drought.",
        "if_closed": "Via Suez or the Cape, or the US rail 'landbridge': roughly a week or more extra.",
        "theatres": [], "assets": ["ZIM", "MATX", "NG=F"]},
    "chokepoint8": {
        "role": "Between Spain and Morocco: the Atlantic door of the Mediterranean.",
        "carries": "Asia-Europe and Mediterranean trade, Algerian and Libyan energy exports.",
        "if_closed": "No alternative into the Mediterranean from the Atlantic.",
        "theatres": ["israel_gaza"], "assets": ["ZIM", "BDRY"]},
    "chokepoint9": {
        "role": "Between England and France: one of the busiest straits in the world.",
        "carries": "Northern Europe's trade (Rotterdam, Antwerp, Hamburg) with the Atlantic; North Sea oil and gas.",
        "if_closed": "A route north of Scotland adds about two days.",
        "theatres": ["baltic_arctic"], "assets": ["BZ=F", "TTF=F"]},
    "chokepoint10": {
        "role": "The Danish straits: the only way into and out of the Baltic Sea.",
        "carries": "Russia's Baltic oil and grain exports, Nordic and Baltic trade; undersea power and data cables run through the area.",
        "if_closed": "No sea alternative.",
        "theatres": ["baltic_arctic", "ukraine_russia"], "assets": ["BZ=F", "TTF=F", "ITA"]},
    "chokepoint17": {
        "role": "The entrance to the Bohai Sea, serving Tianjin, Dalian, Qingdao and other northern Chinese ports.",
        "carries": "North China's coal, iron ore, crude and containers.",
        "if_closed": "Ports would lose their sea access.",
        "theatres": ["east_china_sea", "taiwan"], "assets": ["FXI", "BDRY"]},
    "chokepoint13": {
        "role": "Between Honshu and Hokkaido, in northern Japan.",
        "carries": "Coastal and Pacific-bound Japanese traffic, some Russian Far East trade.",
        "if_closed": "Ships go around Hokkaido.",
        "theatres": ["east_china_sea"], "assets": ["EWJ"]},
    "chokepoint15": {
        "role": "Deep strait between Bali and Lombok: the main alternative to Malacca for the largest ships.",
        "carries": "Iron ore, coal and oil between Australia, the Middle East and East Asia.",
        "if_closed": "Ships use Sunda or Malacca.",
        "theatres": ["south_china_sea"], "assets": ["BDRY"]},
    "chokepoint19": {
        "role": "Between Java and Sumatra: a shortcut and Malacca alternative.",
        "carries": "Bulk and oil traffic, mostly smaller ships than Lombok.",
        "if_closed": "Ships use Lombok or Malacca.",
        "theatres": ["south_china_sea"], "assets": ["BDRY"]},
    "chokepoint20": {
        "role": "Between Borneo and Sulawesi, on the deep-water route from Lombok to the Pacific.",
        "carries": "Bulk carriers and tankers avoiding Malacca.",
        "if_closed": "Ships go east of Sulawesi.",
        "theatres": ["south_china_sea"], "assets": ["BDRY"]},
    "chokepoint16": {
        "role": "Between Timor and Alor in eastern Indonesia.",
        "carries": "Deep-draft ships between the Indian Ocean and the Pacific, including LNG from Australia.",
        "if_closed": "Ships use Lombok-Makassar or go around Australia.",
        "theatres": [], "assets": ["BDRY"]},
    "chokepoint27": {
        "role": "Between Mindoro and Palawan in the Philippines.",
        "carries": "Traffic between the South China Sea and the Sulu and Celebes seas.",
        "if_closed": "Other Philippine straits.",
        "theatres": ["south_china_sea"], "assets": ["BDRY"]},
    "chokepoint25": {
        "role": "Between Palawan and Borneo, at the southern edge of the South China Sea.",
        "carries": "Regional traffic between the South China Sea and the Sulu Sea.",
        "if_closed": "Other Philippine or Indonesian straits.",
        "theatres": ["south_china_sea"], "assets": ["BDRY"]},
    "chokepoint18": {
        "role": "Between Australia and Papua New Guinea.",
        "carries": "Australian coal, iron ore and gas heading north; coastal and regional traffic.",
        "if_closed": "Ships go around northern Australia.",
        "theatres": [], "assets": ["BDRY"]},
    "chokepoint22": {
        "role": "Between Cuba and Mexico: the exit of the Gulf of Mexico.",
        "carries": "US Gulf Coast exports (crude, refined fuels, LNG, grain), Mexican oil and Mississippi River cargo.",
        "if_closed": "Through the Florida Straits.",
        "theatres": ["venezuela_caribbean"], "assets": ["CL=F", "NG=F"]},
    "chokepoint23": {
        "role": "Between Cuba and Haiti.",
        "carries": "Caribbean traffic between the Atlantic and the Panama Canal.",
        "if_closed": "Other Caribbean passages (Mona, Anegada).",
        "theatres": ["venezuela_caribbean"], "assets": []},
    "chokepoint24": {
        "role": "Between the Dominican Republic and Puerto Rico.",
        "carries": "Atlantic to Panama Canal and Gulf of Mexico traffic.",
        "if_closed": "Other Caribbean passages.",
        "theatres": ["venezuela_caribbean"], "assets": []},
    "chokepoint21": {
        "role": "Passage at the southern tip of South America, alongside Cape Horn.",
        "carries": "Little traffic today; a fallback if the Panama Canal is restricted.",
        "if_closed": "Cape Horn or Panama.",
        "theatres": [], "assets": []},
    "chokepoint26": {
        "role": "Between Russia and Alaska: the entrance to the Arctic sea route.",
        "carries": "A few ships a day, mostly in the ice-free summer.",
        "if_closed": "Suez or Cape routes.",
        "theatres": ["baltic_arctic"], "assets": []},
}

# ─── Flashpoints ──────────────────────────────────────────────────────────────────────────────
# search: Yahoo Finance news search (the main headline source; it works from the build servers).
# query: GDELT DOC search (English-language news) for extra headlines and the coverage trend. Phrases in quotes,
#        groups with OR in parentheses; its first group also decides which headlines count as relevant.
THEATRES: list[dict] = [
    {"id": "iran_gulf", "name": "Iran and the Gulf", "region": "Middle East", "search": "Strait of Hormuz Iran",
     "query": '("Strait of Hormuz" OR Hormuz OR "Persian Gulf" OR Iran) (blockade OR strike OR tanker OR navy OR sanctions OR missile)',
     "chokepoints": ["chokepoint6"], "assets": ["BZ=F", "CL=F", "NG=F", "TTF=F", "FRO", "STNG", "ITA", "GC=F"],
     "affects": ["Oil and LNG prices and tanker rates", "Qatar's helium, used in chip fabs", "Gulf petrochemicals, fertilizer, aluminium",
                 "Power costs for LNG-importing Asia (Taiwan, Korea, Japan)", "Shipping insurance"]},
    {"id": "red_sea", "name": "Red Sea and Yemen", "region": "Middle East", "search": "Red Sea shipping Houthi",
     "query": '(Houthi OR Houthis OR "Red Sea" OR "Bab el-Mandeb" OR "Gulf of Aden") (attack OR ship OR shipping OR vessel OR missile)',
     "chokepoints": ["chokepoint4", "chokepoint1", "chokepoint7"], "assets": ["ZIM", "BDRY", "BZ=F", "ITA"],
     "affects": ["Asia-Europe container routes and transit times", "Freight rates and shipping insurance", "Europe's imports of electronics and machinery",
                 "Suez Canal traffic and Cape of Good Hope diversions"]},
    {"id": "israel_gaza", "name": "Israel, Gaza and Lebanon", "region": "Middle East", "search": "Israel Gaza Lebanon",
     "query": '(Gaza OR Hezbollah OR Lebanon OR Israel) (strike OR ceasefire OR war OR hostages)',
     "chokepoints": ["chokepoint1", "chokepoint8"], "assets": ["ITA", "GC=F", "BZ=F", "^VIX"],
     "affects": ["Regional escalation risk (Iran, Red Sea)", "Oil risk premium", "Israeli chip design and fab operations (Intel, Nvidia, Tower, Mobileye sites)",
                 "Defense spending"]},
    {"id": "ukraine_russia", "name": "Russia and Ukraine", "region": "Europe", "search": "Russia Ukraine war",
     "query": '(Ukraine OR Russia) (war OR offensive OR drone OR missile OR frontline OR ceasefire)',
     "chokepoints": ["chokepoint3", "chokepoint28", "chokepoint10"], "assets": ["ZW=F", "TTF=F", "ITA", "HG=F"],
     "affects": ["Grain, sunflower oil and fertilizer", "European gas and power prices", "Neon, palladium and other inputs used by chip makers",
                 "Defense budgets and sanctions on Russia"]},
    {"id": "black_sea", "name": "Black Sea shipping", "region": "Europe", "search": "Black Sea shipping",
     "query": '("Black Sea" OR Odesa OR Novorossiysk OR "Kerch Strait") (ship OR vessel OR port OR grain OR attack)',
     "chokepoints": ["chokepoint3", "chokepoint28"], "assets": ["ZW=F", "FRO"],
     "affects": ["Grain export corridors", "Russian and Kazakh oil shipments from Novorossiysk", "War-risk insurance for Black Sea ports"]},
    {"id": "taiwan", "name": "Taiwan and China", "region": "East Asia", "search": "Taiwan China military",
     "query": '(Taiwan OR "Taiwan Strait") (PLA OR blockade OR drills OR "coast guard" OR invasion OR military)',
     "chokepoints": ["chokepoint11", "chokepoint14", "chokepoint17"], "assets": ["TSM", "SOXX", "EWT", "FXI", "GC=F"],
     "affects": ["Leading-edge chips (TSMC makes about 90% of the most advanced logic)", "Taiwan's LNG and energy imports", "Container flows between China, Japan, Korea and the world",
                 "Every company that designs chips for TSMC: Nvidia, AMD, Apple, Qualcomm, Broadcom, Marvell"]},
    {"id": "south_china_sea", "name": "South China Sea", "region": "East Asia", "search": "South China Sea Philippines",
     "query": '("South China Sea" OR "Scarborough Shoal" OR "Second Thomas Shoal") (Philippines OR "coast guard" OR collision OR clash)',
     "chokepoints": ["chokepoint5", "chokepoint14", "chokepoint27", "chokepoint25"], "assets": ["BDRY", "SOXX", "FXI"],
     "affects": ["The main trade artery of East Asia", "Philippine and Vietnamese electronics assembly and test sites", "Malacca-bound oil flows"]},
    {"id": "korea", "name": "Korean Peninsula", "region": "East Asia", "search": "North Korea missile",
     "query": '("North Korea" OR Pyongyang) (missile OR launch OR troops OR nuclear OR artillery)',
     "chokepoints": ["chokepoint12"], "assets": ["EWY", "EWJ", "GC=F"],
     "affects": ["Samsung and SK hynix: most of the world's DRAM and much of its HBM", "Korea-Japan sea lanes", "Regional risk appetite"]},
    {"id": "east_china_sea", "name": "East China Sea and Japan", "region": "East Asia", "search": "Japan China East China Sea",
     "query": '("East China Sea" OR Senkaku OR Diaoyu) (China OR Japan) ("coast guard" OR military OR drills OR vessels)',
     "chokepoints": ["chokepoint13", "chokepoint12", "chokepoint17"], "assets": ["EWJ", "FXI"],
     "affects": ["Japanese photoresist, wafer and chemical suppliers", "China-Japan trade and rare-earth tensions", "Tokyo Electron and Advantest customers"]},
    {"id": "us_china_tech", "name": "US-China tech and trade controls", "region": "Global", "search": "chip export controls China",
     "query": '("export controls" OR "chip ban" OR tariffs OR "entity list") (China OR semiconductor OR chips OR "rare earth")',
     "chokepoints": [], "assets": ["SOXX", "FXI", "REMX", "HG=F"],
     "affects": ["Who can buy advanced chips and equipment", "Gallium, germanium, antimony and rare-earth supply from China", "Tariff costs and customer demand",
                 "Revenue of equipment makers selling to China"]},
    {"id": "india_pakistan", "name": "India and Pakistan", "region": "South Asia", "search": "India Pakistan",
     "query": 'India Pakistan (border OR strike OR clash OR military OR Kashmir)',
     "chokepoints": [], "assets": ["INDA", "GC=F"],
     "affects": ["Indian markets and its growing electronics assembly base", "Arabian Sea and airspace disruption", "Nuclear-armed escalation risk"]},
    {"id": "sudan_horn", "name": "Sudan and the Horn of Africa", "region": "Africa", "search": "Sudan war",
     "query": '(Sudan OR Somalia OR Ethiopia OR "Horn of Africa") (war OR fighting OR militia OR piracy)',
     "chokepoints": ["chokepoint4"], "assets": ["GC=F"],
     "affects": ["Red Sea coast stability and piracy risk", "Gold production and smuggling", "Humanitarian crises and migration"]},
    {"id": "africa_sahel", "name": "Congo, Sahel and West Africa", "region": "Africa", "search": "Congo rebels Sahel",
     "query": '("DR Congo" OR Congo OR Sahel OR Mali OR Niger OR "Burkina Faso") (rebels OR fighting OR militia OR attack OR junta)',
     "chokepoints": [], "assets": ["HG=F", "REMX"],
     "affects": ["Cobalt and copper (Congo supplies about 70% of cobalt)", "Tantalum and tin used in electronics", "Uranium and gold supply from the Sahel"]},
    {"id": "myanmar", "name": "Myanmar", "region": "Southeast Asia", "search": "Myanmar junta",
     "query": '(Myanmar OR Burma) (junta OR fighting OR rebels OR airstrike OR "rare earth")',
     "chokepoints": [], "assets": ["REMX"],
     "affects": ["Heavy rare-earth ore shipped to China", "Tin and tungsten supply", "Regional border trade"]},
    {"id": "venezuela_caribbean", "name": "Venezuela and the Caribbean", "region": "Americas", "search": "Venezuela military",
     "query": '(Venezuela OR Caribbean OR Cuba) (military OR navy OR strike OR blockade OR sanctions)',
     "chokepoints": ["chokepoint22", "chokepoint23", "chokepoint24"], "assets": ["CL=F"],
     "affects": ["Heavy crude exports to US Gulf refiners", "Caribbean shipping lanes to the Panama Canal", "Migration and sanctions policy"]},
    {"id": "baltic_arctic", "name": "Baltic and Arctic", "region": "Europe", "search": "Baltic Sea Russia NATO",
     "query": '(Baltic OR Arctic OR Kaliningrad OR "undersea cable" OR "shadow fleet") (NATO OR sabotage OR drone OR Russia OR tanker)',
     "chokepoints": ["chokepoint10", "chokepoint9", "chokepoint26"], "assets": ["TTF=F", "BZ=F", "ITA"],
     "affects": ["Undersea power, gas and data cables", "Russian oil exports through the Baltic", "NATO readiness and defense spending"]},
]

# ─── How chip supply depends on all this ──────────────────────────────────────────────────────
SEMIS: list[dict] = [
    {"id": "taiwan_fabs", "label": "Leading-edge chips are made in Taiwan",
     "why": "TSMC makes about 90% of the world's most advanced logic chips: almost every AI accelerator and phone processor. A blockade, an inspection regime or a long cut in Taiwan's sea and energy links would hit all of its customers.",
     "chokepoints": ["chokepoint11", "chokepoint14"], "theatres": ["taiwan"], "tickers": ["TSM", "NVDA", "AMD", "AVGO", "QCOM", "MRVL", "UMC", "2454.TW"]},
    {"id": "korea_memory", "label": "Memory is concentrated in Korea",
     "why": "Samsung and SK hynix make roughly two thirds or more of the world's DRAM and most high-bandwidth memory (HBM) used with AI accelerators.",
     "chokepoints": ["chokepoint12"], "theatres": ["korea", "east_china_sea"], "tickers": ["005930.KS", "000660.KS", "MU", "NVDA"]},
    {"id": "gulf_helium_lng", "label": "Gulf helium and LNG",
     "why": "Qatar supplies about a third of the world's helium (a by-product of its LNG), which fabs use for cooling and leak testing. Taiwan, Korea and Japan also burn Gulf LNG for power. A shut Strait of Hormuz cuts both.",
     "chokepoints": ["chokepoint6"], "theatres": ["iran_gulf"], "tickers": ["TSM", "005930.KS", "000660.KS", "MU", "INTC"]},
    {"id": "neon_gases", "label": "Neon and rare gases from the Black Sea region",
     "why": "Before 2022 Ukraine supplied roughly half of the neon used in chip-making lasers. Producers have since diversified, but supply and prices still follow the war.",
     "chokepoints": ["chokepoint3", "chokepoint28"], "theatres": ["ukraine_russia", "black_sea"], "tickers": ["ASML", "TSM", "INTC"]},
    {"id": "china_minerals", "label": "Gallium, germanium and rare earths from China",
     "why": "China produces the large majority of primary gallium, most germanium and most rare-earth processing, and has used export licences as a lever. RF, power and optical chips depend on them.",
     "chokepoints": [], "theatres": ["us_china_tech", "myanmar"], "tickers": ["QRVO", "SWKS", "ON", "NVTS", "MTSI"]},
    {"id": "japan_materials", "label": "Photoresists, wafers and chemicals from Japan",
     "why": "Japanese firms supply the large majority of advanced photoresist and a big share of silicon wafers and high-purity chemicals. Earthquakes, typhoons and regional tensions are the risks.",
     "chokepoints": ["chokepoint13", "chokepoint12"], "theatres": ["east_china_sea", "korea"], "tickers": ["8035.T", "6857.T", "AMAT", "LRCX", "KLAC", "TSM"]},
    {"id": "asia_europe_freight", "label": "Asia to Europe sea freight",
     "why": "Chips, modules and equipment moving between Asia and Europe go through Suez and the Red Sea or round the Cape (about 10 days longer). Disruption raises lead times, freight cost and inventory needs.",
     "chokepoints": ["chokepoint1", "chokepoint4", "chokepoint7"], "theatres": ["red_sea", "israel_gaza"], "tickers": ["STM", "NXPI", "ASML", "IFNNY", "ASM.AS"]},
    {"id": "battery_metals", "label": "Cobalt, tantalum and tin",
     "why": "Congo supplies about 70% of cobalt and a large part of tantalum (capacitors); Myanmar and Indonesia supply tin for solder. Conflict there lifts prices and compliance costs.",
     "chokepoints": [], "theatres": ["africa_sahel", "myanmar"], "tickers": []},
]

