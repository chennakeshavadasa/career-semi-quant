# Handoff: Semi Quant Terminal

State at 2026-11-28 11:46 UTC. Read this first, then `git log --oneline -20 origin/master`.

## What this is

One codebase, four ways to use it:

| Surface | Where | Built from |
|---|---|---|
| **Local edition** (full app, live data on your PC) | `semiquant serve` → http://127.0.0.1:8050 | `local/` (Python package `semiquant`: `data/`, `analytics/`, `service/`, `server/`, `web/`) |
| **Web edition, Android's copy** | https://chennakeshavadasa.github.io/career-semi-quant/app/ | `.github/workflows/webapp.yml`: `semiquant publish` (static UI + `data/*.json`), every 15 min weekdays, every 3 h weekends |
| **Android app** (WebView on the URL above) | release `android` (`SemiQuant.apk`, `version.json`) | `.github/workflows/android.yml`, only when `android/**` changes on master |
| **Website** | https://nithinpuru.github.io/quant-terminal/ → forwards to `/quant-terminal/app/` | repo **NithinPuru/nithinpuru.github.io**, `deploy.yml` pip-installs `semiquant` from this repo's `master` and publishes it. The old single-page terminal (`public/quant-terminal/`, mirrored by its `quant-terminal-sync.yml`) is served at `/quant-terminal/classic.html` |

`master` is production. Working branch for Claude sessions: `claude/pensive-einstein-jrrduh` (fast-forward master to it).

## Shipped today (newest first)

- **Bargo cross-check** (`data/bargo.py`, `congress.cross_check`). Bargo's free Congress API (no key: 30 requests / 100 rows a day per address, last 3 months) is called once per 6 hours (disk cache) and compared with our trades by date, ticker, side and last name; trades only Bargo has are added as `source: "bargo"`, linked "via Bargo", and the Congress page and Insiders tab carry the visible credit its licence requires (no raw-dataset redistribution allowed). At build time its latest trades all matched ours (12 of 12; every NVDA trade since September too). It lacks most paper filers (95 of Khanna's ~900 recent trades, none of Rogers, Fleischmann...), so it is a check, not a source. Other providers looked at (owner asked for free ones only): Disclosed Capitol has a free API key (90 days, 750 credits; says it covers the executive branch: President, cabinet, senior staff) and needs the owner to sign up and add the key as `DISCLOSED_CAPITOL_KEY`; Quiver is paid and personal-use only; Capitol Trades has no public API; House/Senate Stock Watcher are dead.
- **Scanned (paper) House reports are now read** (`data/paper_ptr.py`). About 1 House report in 8 is a scanned image with no text layer, so the text reader found nothing and counted it "unreadable": every report of Ro Khanna (CA-17, 22 reports in 2025-26, about 8,800 trades of his family trusts, 21 of them NVDA) and others (McCaul, Harshbarger, Wied...). The reader finds the form's grid from its ruled lines (long ink runs, so dashed or faint lines work), reads purchase/sale/partial and the amount band from the x marks (an empty printed checkbox and a dashed line are not marks), OCRs only owner, asset and date columns (Tesseract), anchors rows on the trade dates, turns sideways (portrait) scans upright, fixes a misread year from the notification date and maps asset names to tickers (`CALL/NVDA ...` = an NVDA option; notes "linked to" an index get no ticker). Verified 25/25 rows on two real pages incl. the worst one (`tests/data/ptr_scan/`, `tests/test_paper_ptr.py`). Reports stored as unreadable before OCR existed are read again (`congress._stale_scan`), newest first; rows read this way carry `ocr: true` and their link says "Filing (scan)". Needs `tesseract-ocr`: installed in `webapp.yml`, `local-tests.yml` and the website's `deploy.yml`; without it nothing changes. Still not read: handwritten House forms (e.g. Fleischmann, Rogers) and Senate paper filings (images on eFD).
- **World risk** page `#/world` (local and web, desktop nav + phone More list): ships per day through 28 straits and canals (IMF PortWatch, AIS-based, lags about a week) with a status against each strait's own normal (3-year median *and* the same weeks of earlier years, the more cautious wins; start dates from PortWatch's event log when it has one), PortWatch's disruption log, 16 flashpoints with headlines (Yahoo Finance news search first, GDELT tops up) and GDELT's coverage trend, the markets that carry a shock (Yahoo: oil, gas, freight, defense, havens, Asian chip markets) and chip-supply exposure. Code: `data/portwatch.py`, `data/gdelt.py`, `analytics/worldrisk.py`, `world.py` (the curated map: what each strait carries, what each flashpoint can affect, chip links), `service/world.py`, `web/js/views/world.js`. Static files: `world.json`, `world/chokepoint/<id>.json`, `world/news__theatre-<id>.json`. Tests `test_worldrisk.py`, `test_portwatch_gdelt.py`, `test_world.py` on real recorded answers in `tests/fixtures/world/` (regenerate: `python tests/make_world_fixtures.py`). At build time the data showed Hormuz at about 3 ships a day against 78 normally since 1 Mar 2026 (PortWatch event HORMUZ-26, ongoing), Kerch and Bosporus disrupted, Bab el-Mandeb below normal.
- Verified live at 11:02 UTC: the Insiders & Congress tab works on both sites. All 227 published symbols serve `smartmoney.json` on both; the website needed the 10:52 `quick` deploy that was already running.
- `bcb3c23` publish: each stock's Insiders & Congress data moved to the always-run pass (the first run's 2-min heavy budget was used up reading Congress filings, so the tab 404'd).
- `0a2cefa` **Insiders & Congress**: ticker tab `smart` + page `#/congress`. Data: `local/semiquant/data/congress.py` (House Clerk index + PTR PDFs via pypdf, Senate eFD search + report pages, @unitedstates legislators/committees), `data/sec.py` (EDGAR full-text search: Form 4, Form 144, 13D/13G), `service/smartmoney.py` (highlights, committee oversight heuristic, feed). UI `web/js/views/smartmoney.js`. Tests `local/tests/test_congress.py` (+ real filings in `tests/data/`).
- `85bd2b6` `js/quant.js` → `js/models.js`: EasyPrivacy's `/quant.js` rule (uBlock, AdGuard, Brave) blocked it and broke Offer/Portfolio. `tests/test_blocklists.py` now fails on any blocked file name.
- `8ca279e` webapp.yml: restores (page_build) only read the cache and take the newest build; push runs save under their own key. Before this a restore could bring back an older build (old logo).
- `e96051e` restored the `quantpack.js` script tag + Factor lab link that a merge dropped.
- `94e06d3` merged the other session's update fixes; **logo = "bell of candles"** (owner's pick, option B) everywhere: `brand/`, PWA icons, Android mipmaps, favicons, header marks (web + classic page).
- Earlier today: quant pack (crash risk/PSR, liquidity & impact, HAR-RV, random-walk tests, implied distribution, model-free IV, systemic risk, factor lab) and its tests.
- Website repo (NithinPuru/nithinpuru.github.io, `main`): `3a04c4c` `/quant-terminal/` forwards to the app (classic page at `classic.html`; smoke test updated), `d849176` `deploy.yml` input `quick` and 2-min budget on pushes.

## In flight at handoff (verify first)

- World risk deploys: the webapp push run and a website `deploy.yml` run with `quick: true`. Check:
  ```bash
  curl -sI https://chennakeshavadasa.github.io/career-semi-quant/app/data/world.json | head -1
  curl -sI https://nithinpuru.github.io/quant-terminal/app/data/world.json | head -1
  ```
  then open `#/world` on both. Flashpoint headlines fill over the first runs (GDELT has a time cap per run, see below); cards say "Headlines are being prepared" until then.
- First Congress runs leave a few filings "pending"; each run reads more (4-min cap). `stats` in `data/congress__days-90.json` shows it.

## Open items

1. **Owner setting (recommended):** career-semi-quant → Settings → Pages → Source: **GitHub Actions**. Stops the branch-based Pages builds that blank the app for a minute after every push to master (the restore dance in `webapp.yml`).
2. **Every fund ≥0.5% (13F) and exact 5%+ stake percentages** need SEC archive access, which requires a contact email in the User-Agent. Only with the owner's explicit OK and an address they choose; today `data/sec.py` uses the search API, which needs none.
3. Executive-branch officials' trades (OGE 278-T) are not covered: no clean feed.
4. Polish: chart annotation text 9-10.5 px on a few heatmaps (risk, factor lab) is flagged "tiny" by the phone audit.
5. World risk: GDELT rate-limits GitHub's build servers too (the first website build got 429s), so flashpoint headlines come from Yahoo's news search first and GDELT only tops them up and gives the coverage trend (the "Coverage 2x its recent norm" badge). If that badge never appears, the trend is not getting through; look at GDELT's other feeds. The notes in `world.py` are judgement; review them now and then.
6. Congress: handwritten House paper reports and Senate paper filings are still unread (`stats.unreadable` in `data/congress__days-90.json`). The OCR reader handles the typed form and its broker attachments.

## How to work here (learned the hard way)

- **Sync before anything**: other Claude sessions push to master too. `git fetch origin`, merge, never force-push or rebase pushed history.
- **Merge conflicts in text files**: resolve the hunks. `git checkout --theirs <file>` takes the whole file and silently drops your side (it dropped the quant pack's script tag).
- **What a push to master triggers**: branch Pages build (app 404 for ~1 min; installed apps show their cached copy) → `webapp.yml` restore; `webapp.yml` publish (push = 2-min heavy budget, scheduled = 12); `android.yml` if `android/**` changed (new APK, in-app update); `test.yml` if `public/**`; `local-tests.yml` if `local/**`. **The website only updates through its own deploy**: dispatch `deploy.yml` in NithinPuru/nithinpuru.github.io with `quick: true` after a code change, or wait for its schedule.
- **Anything every stock page needs goes in `Publisher.ticker()`** (always runs). `ticker_slow()` stops at the time budget.
- **File names**: no shipped file may match a content-blocker rule (`local/tests/data/blocked_script_names.txt`). The test enforces it.
- **SEC**: `www.sec.gov` (archives, company_tickers.json) refuses requests without a contact email; `efts.sec.gov` and `data.sec.gov` work with a generic client name. In the search API's `forms` filter list **base forms only** (`4,144`, `SCHEDULE 13G`, ...): listing `/A` forms drops results; amendments come back anyway.
- **Congress sources**: House PDFs put NULs where the heading font lacks glyphs (`parse_house_text` handles it); Senate eFD needs the terms-of-use POST first (`_senate_session`). Disclosure lag: median 27 days, 10% over 116 days (the law allows 45).
- **World risk sources**: PortWatch is an ArcGIS service (`services9.arcgis.com/weJ1QsnbMYJlCHdG/.../Daily_Chokepoints_Data`, `PortWatch_chokepoints_database`, `portwatch_disruptions_database`); `date` is a DateOnly field, filter with `date >= 'YYYY-MM-DD'`, 10,000 rows per answer. GDELT DOC API: `data/gdelt.py` throttles to one call per 5.5 s, retries once, pauses 10 min after 4 failures (`gdelt.paused()`); headlines come from `yahoo.search_news` first (each flashpoint has a `search` phrase), GDELT tops up below 3; the publisher caps the news at 200 s per run (less on budgeted push runs) and a partial answer carries `"available": false` so it is retried next run. The cloud environment "Semi Quant Terminal" allows both github.io hosts, `api.gdeltproject.org`, `services9.arcgis.com`, `disclosures-clerk.house.gov` and `www.bargo.ai`; Yahoo is not reachable from it, so build a static copy with synthetic prices to test UI (see the World risk commit).
- **Checks before shipping**:
  ```bash
  cd local && pytest -q                        # 279 tests
  for f in semiquant/web/js/*.js semiquant/web/js/views/*.js; do node --check "$f"; done
  semiquant serve --no-browser &               # then the phone audit:
  node devtools/uitest.js http://127.0.0.1:8050/ /tmp/ui a360,p412,zoom130,se375light,land800,tab768 market,nvda_smart,congress,world
  ```
  `uitest.js` (Playwright) reports overflow, overlapping text, clipping, small tap targets and tiny text per page and screen size; `scrl` (table scrollers) is expected.
- **Static check without a deploy**: `Publisher(out, full=[...])` + `copy_app()`, `quotes()`, `put(...)` for the pages you changed, `meta()`; serve `out` and open it (see `0a2cefa` for the routes).

## Owner's preferences (from this conversation)

- Wants changes **live** (app and website), quickly; checks often ("is it live now?"). Report status plainly with what was verified.
- Logo is settled: bell of candles. Rejected: chip, Q (looks like a search icon), fan of paths, "worm" curves, black swan (a metaphor, not quant).
- Phone UI quality matters: test every screen size before shipping.
- Wants the newest information fastest: show both "traded" and "public since" dates, flag NEW items.
