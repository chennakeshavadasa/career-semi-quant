# career-semi-quant — Full Upgrade Instructions for Gemini Pro

You are an expert JavaScript and frontend developer. Your task is to upgrade
the `career-semi-quant` repository. The entire application lives in a single
`index.html` file. Follow every instruction below exactly.
Do not skip any item. Do not break existing functionality.

The repo has one file that matters: `index.html` (100 % HTML/CSS/JS, no build
step, no backend). Everything runs in the user's browser.

The app fetches 1.5 years of weekly price data for 40+ semiconductor company
tickers, computes RSI/MACD/Bollinger/Monte Carlo/Beta/Alpha/Sharpe etc. in JS,
and renders company cards. A detail modal shows 7 interactive Chart.js charts.

---

## PART 1 — CRITICAL PERFORMANCE FIXES

### Fix 1 · Deduplicate SPY fetches

**Problem**: Every company card independently calls the CORS proxy to fetch
SPY price history to compute Beta and Alpha. With 40+ companies this means
40+ identical SPY requests — most fail due to rate limiting, causing wrong
Beta/Alpha values silently falling back to 0.

**Fix**: Fetch SPY exactly once at page load, store it in a module-scoped
variable, and reuse it for all calculations.

Find where SPY is fetched inside the per-ticker logic (it will be inside a
`fetchStockData` or equivalent function that calls a CORS proxy for each
ticker). Extract the SPY fetch into a dedicated startup function.

Add this near the top of your main `<script>`:

```javascript
// ── Shared SPY data, fetched exactly once ─────────────────────────────────
let _spyPrices  = null;   // array of weekly close prices
let _spyFetched = false;
let _spyPromise = null;

async function getSpyPrices() {
  if (_spyPrices !== null) return _spyPrices;
  if (_spyPromise)         return _spyPromise;

  _spyPromise = (async () => {
    try {
      const data = await fetchYahooWeekly('SPY', 80);   // reuse your existing fetch helper
      _spyPrices  = data.closes;
      _spyFetched = true;
      return _spyPrices;
    } catch {
      _spyPrices = [];
      return [];
    }
  })();
  return _spyPromise;
}
```

Then in your `computeBeta(stockCloses, spyCloses)` call, replace the inline
SPY fetch with `await getSpyPrices()`.

Call `getSpyPrices()` once during page init before any card loads:
```javascript
// In your DOMContentLoaded or init function, BEFORE starting ticker loads:
getSpyPrices();   // fire-and-forget; cards will await the shared promise
```

---

### Fix 2 · Stagger API calls in batches

**Problem**: All 40+ tickers fire simultaneously on page load, instantly
hitting rate limits on every CORS proxy, causing mass DATA UNAVAILABLE
failures.

**Fix**: Replace the current "fire all at once" approach with a batched
loader. Process tickers in groups of 8, with a 400 ms delay between batches.

Find the function that iterates over all company tickers and starts their
fetch. Replace it with:

```javascript
const BATCH_SIZE  = 8;
const BATCH_DELAY = 400;   // ms between batches

async function loadAllTickers(companies) {
  for (let i = 0; i < companies.length; i += BATCH_SIZE) {
    const batch = companies.slice(i, i + BATCH_SIZE);
    // Fire batch in parallel
    await Promise.allSettled(batch.map(company => loadOneTicker(company)));
    // Wait before next batch (skip delay after last batch)
    if (i + BATCH_SIZE < companies.length) {
      await new Promise(r => setTimeout(r, BATCH_DELAY));
    }
  }
}
```

`loadOneTicker(company)` is a wrapper around your existing per-ticker fetch
and render logic that catches all errors and shows DATA UNAVAILABLE on
failure, without throwing.

---

### Fix 3 · localStorage cache with 4-hour TTL

**Problem**: Reloading the page re-fetches all 40+ tickers. In a 4-hour
trading window, weekly prices barely change — each reload wastes API quota
and time.

**Fix**: Cache successful fetch results in localStorage. On cache hit, skip
the API call entirely. Cache expires after 4 hours.

Add these two utility functions:

```javascript
const CACHE_TTL_MS = 4 * 60 * 60 * 1000;   // 4 hours
const CACHE_PREFIX = 'csq_v2_';             // version prefix — bump on data schema change

function cacheSet(ticker, data) {
  try {
    localStorage.setItem(CACHE_PREFIX + ticker, JSON.stringify({
      ts:   Date.now(),
      data: data,
    }));
  } catch { /* localStorage quota exceeded — ignore */ }
}

function cacheGet(ticker) {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + ticker);
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw);
    if (Date.now() - ts > CACHE_TTL_MS) {
      localStorage.removeItem(CACHE_PREFIX + ticker);
      return null;
    }
    return data;
  } catch { return null; }
}
```

In your per-ticker fetch function, wrap the API call:

```javascript
async function fetchStockDataCached(ticker) {
  const cached = cacheGet(ticker);
  if (cached) {
    console.debug(`[cache hit] ${ticker}`);
    return cached;
  }
  const fresh = await fetchStockData(ticker);   // your existing function
  if (fresh && fresh.closes && fresh.closes.length >= 25) {
    cacheSet(ticker, fresh);
  }
  return fresh;
}
```

Replace all calls to `fetchStockData(ticker)` with `fetchStockDataCached(ticker)`.

Add a small "Clear Cache" button to the dashboard UI (top-right corner):
```javascript
document.getElementById('clear-cache-btn').addEventListener('click', () => {
  Object.keys(localStorage)
    .filter(k => k.startsWith(CACHE_PREFIX))
    .forEach(k => localStorage.removeItem(k));
  location.reload();
});
```

Add the button HTML in the header/filter bar:
```html
<button id="clear-cache-btn" class="ctrl-sm-btn" title="Clear cached data and reload">
  ⟳ Refresh Data
</button>
```

---

## PART 2 — NEW FEATURES

### Feature 1 · URL State Persistence

**Problem**: Filter state (TIER-A, STRONG BUYS), sort order, active company
modal, and search query are all lost on page refresh. Users cannot bookmark
or share a specific view.

**Fix**: Sync all UI state to the URL query string. Use
`history.replaceState` (not `pushState`) so Back button behaviour is
unchanged.

State to persist:
| URL param     | Values                              | Default         |
|---------------|-------------------------------------|-----------------|
| `filter`      | `all`, `tier_a`, `tier_b`, `strong_buys`, `fear` | `all`   |
| `sort`        | `score`, `rsi`, `return_6m`, `return_1y`, `volatility` | `score` |
| `sort_dir`    | `asc`, `desc`                       | `desc`          |
| `q`           | search query string                 | `""`            |
| `company`     | ticker symbol (e.g. `TXN`)          | `""`            |

```javascript
function getUrlState() {
  const p = new URLSearchParams(location.search);
  return {
    filter:   p.get('filter')   || 'all',
    sort:     p.get('sort')     || 'score',
    sort_dir: p.get('sort_dir') || 'desc',
    q:        p.get('q')        || '',
    company:  p.get('company')  || '',
  };
}

function pushUrlState(state) {
  const p = new URLSearchParams();
  if (state.filter   && state.filter   !== 'all')   p.set('filter',   state.filter);
  if (state.sort     && state.sort     !== 'score')  p.set('sort',     state.sort);
  if (state.sort_dir && state.sort_dir !== 'desc')   p.set('sort_dir', state.sort_dir);
  if (state.q)                                       p.set('q',        state.q);
  if (state.company)                                 p.set('company',  state.company);
  const qs = p.toString();
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}
```

Call `pushUrlState(currentState)` every time any filter, sort, search, or
modal state changes.

On page load, call `getUrlState()` and apply it before rendering any cards:
```javascript
document.addEventListener('DOMContentLoaded', async () => {
  const initialState = getUrlState();
  applyFilter(initialState.filter);
  applySort(initialState.sort, initialState.sort_dir);
  if (initialState.q) {
    document.getElementById('search-input').value = initialState.q;
    applySearch(initialState.q);
  }
  await loadAllTickers(COMPANIES);
  if (initialState.company) {
    openModal(initialState.company);   // auto-open modal if URL has company
  }
});
```

---

### Feature 2 · 4-Week Forward Return Validation Stat

**Problem**: The Composite Quant Score is a black-box heuristic. There is no
signal on whether it actually predicts anything. Professional users will
dismiss it without evidence.

**Fix**: For each company, compute the **historical hit rate**: over the past
year of weekly data, how often did a score threshold above X precede a
positive 4-week forward return? Display this as an additional metric in the
detail modal.

Add a new function that takes the company's weekly close price history:

```javascript
function computeScoreHitRate(weeklyCloses, weeklyScores, threshold = 55) {
  /**
   * For each week where the score was above `threshold`,
   * check if the price was higher 4 weeks later.
   * Returns { hitRate: float 0–1, sampleSize: int, avgGain: float }
   */
  if (!weeklyCloses || weeklyCloses.length < 8) {
    return { hitRate: null, sampleSize: 0, avgGain: null };
  }

  let hits = 0, total = 0, totalGain = 0;
  // weeklyScores must be pre-computed for each historical week
  // Approximate: reuse the same indicator functions on rolling slices
  const n = weeklyCloses.length;
  for (let i = 0; i < n - 4; i++) {
    // Re-compute score on window closes[0..i]
    const slice = weeklyCloses.slice(0, i + 1);
    if (slice.length < 15) continue;
    const score = computeCompositeScore(slice);   // your existing function
    if (score >= threshold) {
      const fwdReturn = (weeklyCloses[i + 4] - weeklyCloses[i]) / weeklyCloses[i];
      if (fwdReturn > 0) hits++;
      totalGain += fwdReturn;
      total++;
    }
  }
  if (total === 0) return { hitRate: null, sampleSize: 0, avgGain: null };
  return {
    hitRate:    hits / total,
    sampleSize: total,
    avgGain:    totalGain / total,
  };
}
```

**Important performance note**: This function runs on historical data slices
and will be slow for large arrays. Run it asynchronously after the card
renders using `setTimeout(fn, 0)` so it does not block the UI.

Display in the detail modal under a new "Score Validation" section:
```
Historical Signal Accuracy (score ≥ 55, 4-week forward)
  Hit Rate:    63.2%   (42 of 66 signals, trailing 52 weeks)
  Avg Gain:   +1.8%    when signal fired
```

If `sampleSize < 10`, display "Insufficient data" instead.

Color the hit rate:
- ≥ 60 %: `var(--positive)`  
- 45–60 %: `var(--neutral)`  
- < 45 %: `var(--negative)`  

---

### Feature 3 · Progressive Loading with Skeleton Cards

**Problem**: The dashboard shows a blank grid while tickers load. Users
see nothing for several seconds and have no feedback on progress.

**Fix**: Render skeleton placeholder cards immediately on page load, then
replace them with real content as each ticker resolves.

Skeleton card HTML (inject 40 of these on DOMContentLoaded before any
fetch starts):

```html
<div class="company-card skeleton" data-ticker-placeholder>
  <div class="skel-line skel-w60"></div>
  <div class="skel-line skel-w40" style="margin-top:6px"></div>
  <div class="skel-sparkline"></div>
  <div class="skel-line skel-w80" style="margin-top:10px"></div>
  <div class="skel-line skel-w50"></div>
</div>
```

```css
.skeleton { pointer-events: none; }
.skel-line {
  height: 12px; border-radius: 4px;
  background: linear-gradient(90deg,
    rgba(255,255,255,0.04) 25%,
    rgba(255,255,255,0.09) 50%,
    rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skel-sparkline {
  height: 60px; margin-top: 10px; border-radius: 6px;
  background: rgba(255,255,255,0.04);
  animation: shimmer 1.4s infinite 0.2s;
}
.skel-w40 { width: 40%; }
.skel-w60 { width: 60%; }
.skel-w80 { width: 80%; }
.skel-w50 { width: 50%; }
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

When `loadOneTicker(company)` resolves, find the placeholder at the same
grid position and replace `innerHTML` + remove the `.skeleton` class.

---

### Feature 4 · Retain Existing Sort/Filter Logic — Just Add URL Sync

Do not rewrite the filter or sort logic. Only wrap every existing
filter-change and sort-change event handler with a `pushUrlState()` call.
For example:

```javascript
// Existing filter button click handler — ADD the pushUrlState call:
filterBtn.addEventListener('click', () => {
  // ... existing logic ...
  pushUrlState({ ...currentState, filter: selectedFilter });
});
```

---

## PART 3 — UX POLISH

### Polish 1 · Loading Progress Bar

Add a thin progress bar across the top of the page that fills from 0 → 100 %
as tickers load:

```javascript
let loadedCount = 0;
const totalCount = COMPANIES.length;

function onTickerLoaded() {
  loadedCount++;
  const pct = (loadedCount / totalCount) * 100;
  document.getElementById('progress-bar').style.width = pct + '%';
  if (loadedCount >= totalCount) {
    setTimeout(() => {
      document.getElementById('progress-bar-wrap').style.opacity = '0';
    }, 600);
  }
}
```

```html
<div id="progress-bar-wrap" style="position:fixed;top:0;left:0;right:0;z-index:999;height:3px;background:rgba(255,255,255,0.05)">
  <div id="progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#4A9EFF,#A78BFA);transition:width 0.3s ease"></div>
</div>
```

Call `onTickerLoaded()` at the end of `loadOneTicker()` regardless of success or failure.

---

### Polish 2 · Cache Status Indicator in Header

Show a small badge next to the "Refresh Data" button that indicates how many
tickers were served from cache vs. freshly fetched:

```javascript
// After all tickers load:
const cacheHits = COMPANIES.filter(c => cacheGet(c.ticker)).length;
document.getElementById('cache-status').textContent =
  cacheHits > 0 ? `${cacheHits} from cache` : 'Live data';
```

```html
<span id="cache-status" style="font-size:11px;color:var(--text-muted);font-family:monospace"></span>
```

---

### Polish 3 · Error State Card

When a ticker fails all 4 fetch levels (Yahoo → Polygon → Alpha Vantage → Finnhub),
show a clear error card instead of a blank placeholder:

```html
<div class="company-card error-card" data-tier="..." style="opacity:0.5">
  <div class="card-header">
    <span class="ticker">TICKER</span>
    <span class="data-badge" style="background:rgba(255,71,87,0.15);color:#FF4757">
      DATA UNAVAILABLE
    </span>
  </div>
  <p style="font-size:12px;color:var(--text-muted);margin-top:8px">
    All data sources failed for this ticker.<br>
    <a href="https://finance.yahoo.com/quote/TICKER" target="_blank"
       style="color:#4A9EFF">Check on Yahoo Finance ↗</a>
  </p>
</div>
```

---

## DO NOT CHANGE

- The quantitative computation functions: `computeRSI`, `computeMACD`,
  `computeBollinger`, `computeStochastic`, `computeWilliamsR`, `computeATR`,
  `computeCCI`, `computeZScore`, `computeVaR`, `computeMaxDrawdown`,
  `computeBeta`, `computeAlpha`, `computeSharpe`, `computeSortino`,
  `computeTreynor`, `computeInformationRatio`, `computeRSquared`,
  `computeKelly`, `computeFearGreed`, `computeCompositeScore`, `runMonteCarlo`
  — do not touch the math inside any of these functions
- The 4-level data cascade (Yahoo → Polygon → Alpha Vantage → Finnhub)
- The list of companies in the `COS` or `COMPANIES` array
- The detail modal's 7 Chart.js charts (do not change the chart types,
  metrics displayed, or chart layout)
- API key storage in localStorage (keys go in `localStorage`, never
  transmitted to any external server)
- The `multi_data.json`-independent architecture — this app has no backend
  and must remain fully client-side
- The MIT license attribution

---

## IMPLEMENTATION ORDER

Implement in this exact order to avoid regressions:

1. SPY deduplication (Fix 1) — test that Beta values are non-zero before proceeding
2. localStorage cache (Fix 3) — test that cache hit/miss works
3. Batched loader (Fix 2) — replace current parallel loader
4. Skeleton cards (Feature 3) — add before touching any filter/sort code
5. Progress bar (Polish 1)
6. URL state (Feature 1) — wrap existing handlers last, do not rewrite them
7. Score validation (Feature 2) — add to modal only, setTimeout deferred
8. Error card (Polish 3)
9. Cache badge (Polish 2)

---

## SUCCESS CRITERIA

- [ ] SPY is fetched exactly once per page load (verify via browser Network
      tab — exactly 1 request to any CORS proxy for SPY)
- [ ] A page reload within 4 hours serves at least some tickers from
      localStorage (verify via console.debug messages)
- [ ] With cache populated, page renders visible cards in < 1 s
- [ ] The URL updates when filter/sort/search/company state changes
- [ ] Opening a bookmarked URL with `?company=TXN` auto-opens the TXN modal
- [ ] Skeleton cards are visible briefly on first load before real cards appear
- [ ] The thin progress bar fills from left to right as tickers load
- [ ] Score Validation section appears in the detail modal with a percentage
      and sample size (or "Insufficient data" for small datasets)
- [ ] Error cards show for tickers where all 4 fetch levels fail — they do
      not cause uncaught JavaScript exceptions
- [ ] "Refresh Data" button clears localStorage and reloads
- [ ] No more than 8 simultaneous CORS proxy requests at any time
  (verify via Network tab)
- [ ] All existing features (modal, 7 charts, filter, sort, search, API key
      entry) continue to work exactly as before
- [ ] No JavaScript console errors
- [ ] Mobile layout unchanged at 375 px viewport width
