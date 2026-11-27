/* Static (published website) mode: the same dashboard served from GitHub Pages.
 * Every API path maps to a precomputed data/<file>.json written by `semiquant publish`.
 * Quotes come from data/quotes.json; data/meta.json is polled every minute and a new
 * build (every ~15 min during market hours) refreshes quotes in place.
 * Watchlists, settings and the portfolio live in this browser (localStorage). */
(function () {
  'use strict';
  const SQ = window.SQ;
  const ST = window.SQ_STATIC;
  if (!ST) return;
  const { fmt } = SQ;
  const S = (SQ.st = { meta: null, quotes: null, quotesBuild: null, search: null, names: {} });
  SQ.LOCAL_ONLY = 'This tool needs live calculations, so it runs in the free local edition (on your computer). The website shows everything else.';

  // Must match semiquant.publish.file_key
  SQ.fileKey = (path) => {
    let k = SQ.snapKey(path);
    k = k.startsWith('/api/') ? k.slice(5) : k.replace(/^\//, '');
    return k.replace(/\?/g, '__').replace(/&/g, '__').replace(/=/g, '-').replace(/%/g, '_') + '.json';
  };
  async function get(file, bust) {
    const r = await fetch(ST.base + file + (bust ? (file.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(bust) : ''), { cache: 'no-cache' });
    if (!r.ok) {
      const e = new Error(r.status === 404 ? 'not published' : `HTTP ${r.status}`);
      e.status = r.status;
      throw e;
    }
    return r.json();
  }
  const built = () => (S.meta && S.meta.built_at) || ST.build;

  SQ.loadMeta = async () => {
    const m = await get('meta.json', String(Math.floor(Date.now() / 20000)));
    const changed = !S.meta || S.meta.built_at !== m.built_at;
    S.meta = m;
    return changed;
  };
  async function quotes(force) {
    if (!S.quotes || force || S.quotesBuild !== built()) {
      S.quotes = await get('quotes.json', built());
      S.quotesBuild = built();
    }
    return S.quotes;
  }
  async function searchIndex() {
    if (!S.search) {
      S.search = await get('search.json', ST.build).catch(() => []);
      S.search.forEach(([t, n]) => { S.names[t] = n; });
    }
    return S.search;
  }
  SQ.isPublished = (sym) => !!(S.meta && (S.meta.full || []).includes(String(sym).toUpperCase()));

  // ─── device-local state ────────────────────────────────────────────────
  const LS = (k, d) => { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; } catch (e) { return d; } };
  const SV = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } return v; };
  const DEFAULT_LISTS = {
    'My watchlist': ['NVDA', 'AMD', 'AVGO', 'TSM', 'ASML', 'MU', 'SPY', 'QQQ'],
    'US mega caps': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'AVGO', 'TSLA', 'BRK-B', 'JPM', 'LLY', 'V', 'WMT', 'XOM'],
  };
  const DEFAULT_PORTFOLIO = { name: 'My portfolio', benchmark: 'SPY', holdings: [{ ticker: 'NVDA', shares: 10 }, { ticker: 'AVGO', shares: 5 }, { ticker: 'TSM', shares: 8 }] };
  const SETTINGS = { quote_refresh_seconds: 60, closed_refresh_seconds: 120, intraday_refresh_seconds: 300, stream: true };

  // ─── search (published names + every universe member) ─────────────────
  async function search(q) {
    const s = q.trim();
    if (!s) return [];
    const up = s.toUpperCase(), low = s.toLowerCase();
    const idx = await searchIndex();
    const hits = idx.filter(([t, n]) => t.startsWith(up) || (n || '').toLowerCase().includes(low));
    hits.sort((a, b) => (a[0] !== up) - (b[0] !== up) || (!a[0].startsWith(up)) - (!b[0].startsWith(up)) || a[0].length - b[0].length);
    return hits.slice(0, 12).map(([t, n, u, sec]) => ({ symbol: t, name: n, type: SQ.isPublished(t) ? 'Full analysis' : 'Quote', exchange: null, sector: sec, universe: u }));
  }

  // ─── charts: raw bars from the files, indicators computed here ────────
  const DAILY = { '3M': 92, '6M': 183, '1Y': 366, '2Y': 731, '5Y': 1827 };
  async function chart(sym, rng, ind) {
    const daily = rng in DAILY || rng === 'YTD';
    const file = SQ.fileKey('/api/ticker/' + encodeURIComponent(sym) + '/chart?range=' + (daily ? '10Y' : rng));
    const d = await get(file, built());
    d.indicators = SQ.ta ? SQ.ta.compute(d, ind) : {};
    if (daily) {
      const t = d.bars.t, last = new Date(t[t.length - 1] + 'T12:00:00');
      const start = rng === 'YTD' ? new Date(last.getFullYear(), 0, 1) : new Date(last.getTime() - DAILY[rng] * 864e5);
      const iso = start.toISOString().slice(0, 10);
      const i0 = Math.max(0, t.findIndex((x) => x >= iso));
      for (const f of ['t', 'o', 'h', 'l', 'c', 'v']) if (d.bars[f]) d.bars[f] = d.bars[f].slice(i0);
      for (const v of Object.values(d.indicators)) for (const f of Object.keys(v)) v[f] = v[f].slice(i0);
      d.range = rng;
    }
    return d;
  }

  // ─── compare, computed in the browser from published 10-year bars ─────
  async function compare(symbols, rng, bench) {
    const syms = symbols.filter((s) => SQ.isPublished(s)).slice(0, 12);
    if (!syms.length) throw new Error('Compare works with tickers that have full analysis on the website (semiconductors and US mega caps). Use the local edition for any other ticker.');
    const all = syms.concat(syms.includes(bench) ? [] : [bench]);
    const data = await Promise.all(all.map((s) => chart(s, '10Y', []).catch(() => null)));
    const series = {};
    all.forEach((s, i) => { if (data[i]) series[s] = new Map(data[i].bars.t.map((t, j) => [t, data[i].bars.c[j]])); });
    const cal = (data[all.indexOf(bench)] || data.find(Boolean)).bars.t;
    const last = new Date(cal[cal.length - 1] + 'T12:00:00');
    const days = { '3M': 92, '6M': 183, '1Y': 366, '2Y': 731, '5Y': 1827, '10Y': 3653 }[rng];
    const startD = rng === 'YTD' ? new Date(last.getFullYear(), 0, 1) : new Date(last.getTime() - (days || 366) * 864e5);
    const dates = cal.filter((t) => t >= startD.toISOString().slice(0, 10));
    const ret = (arr) => arr.slice(1).map((v, i) => (fmt.ok(v) && fmt.ok(arr[i]) && arr[i] ? v / arr[i] - 1 : null));
    const closes = {};
    Object.keys(series).forEach((s) => {
      let prev = null;
      closes[s] = dates.map((t) => { const v = series[s].get(t); if (fmt.ok(v)) prev = v; return prev; });
    });
    const normalized = {}, drawdowns = {}, rets = {};
    Object.entries(closes).forEach(([s, c]) => {
      const i0 = c.findIndex(fmt.ok);
      if (i0 < 0) return;
      normalized[s] = { t: dates.slice(i0), v: c.slice(i0).map((v) => 100 * v / c[i0]) };
      let pk = -Infinity;
      drawdowns[s] = { t: dates.slice(i0), v: c.slice(i0).map((v) => { pk = Math.max(pk, v); return v / pk - 1; }) };
      rets[s] = ret(c);
    });
    const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
    const sd = (a) => { const m = mean(a); return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / (a.length - 1)); };
    const pair = (a, b) => { const x = [], y = []; a.forEach((v, i) => { if (fmt.ok(v) && fmt.ok(b[i])) { x.push(v); y.push(b[i]); } }); return [x, y]; };
    const cov = (x, y) => { const mx = mean(x), my = mean(y); return x.reduce((s, v, i) => s + (v - mx) * (y[i] - my), 0) / (x.length - 1); };
    const q = await quotes();
    const stats = syms.filter((s) => rets[s]).map((s) => {
      const r = rets[s].filter(fmt.ok), c = closes[s].filter(fmt.ok);
      const yrs = r.length / 252, tot = c[c.length - 1] / c[0] - 1, vol = sd(r) * Math.sqrt(252);
      const neg = r.filter((v) => v < 0);
      const [x, y] = pair(rets[s], rets[bench] || []);
      const beta = x.length > 20 ? cov(x, y) / cov(y, y) : null;
      const corr = x.length > 20 ? cov(x, y) / (sd(x) * sd(y)) : null;
      const cagr = Math.pow(1 + tot, 1 / Math.max(yrs, 1 / 252)) - 1;
      const ann = mean(r) * 252;
      const benchAnn = y.length ? mean(y) * 252 : null;
      const up = x.filter((v, i) => y[i] > 0), upb = y.filter((v) => v > 0), dn = x.filter((v, i) => y[i] < 0), dnb = y.filter((v) => v < 0);
      return { symbol: s, name: S.names[s], price: (q[s] || {}).price, change_pct: (q[s] || {}).change_pct, total_return: tot, cagr, vol,
        sharpe: vol ? (ann - 0.04) / vol : null, sortino: neg.length > 2 ? (ann - 0.04) / (sd(neg) * Math.sqrt(252)) : null,
        max_drawdown: Math.min(...drawdowns[s].v), beta, correlation: corr, alpha: beta != null && benchAnn != null ? ann - (0.04 + beta * (benchAnn - 0.04)) : null,
        up_capture: upb.length ? mean(up) / mean(upb) : null, down_capture: dnb.length ? mean(dn) / mean(dnb) : null, fpe: (q[s] || {}).fpe };
    });
    const tick = syms.filter((s) => rets[s]);
    const matrix = tick.map((a) => tick.map((b) => { const [x, y] = pair(rets[a], rets[b]); return x.length > 20 ? cov(x, y) / (sd(x) * sd(y)) : null; }));
    const offd = []; matrix.forEach((r, i) => r.forEach((v, j) => { if (i < j && fmt.ok(v)) offd.push(v); }));
    return { symbols: syms, bench, range: rng, start: dates[0], normalized, drawdowns, stats,
      correlation: tick.length > 1 ? { tickers: tick, matrix, avg_corr: offd.length ? mean(offd) : null } : null };
  }

  // ─── the API ───────────────────────────────────────────────────────────
  SQ.staticApi = async (path, opts = {}) => {
    const u = new URL(path, 'http://x');
    const p = u.pathname, q = u.searchParams, method = (opts.method || 'GET').toUpperCase();
    if (!S.meta) await SQ.loadMeta().catch(() => null);
    if (p === '/api/watchlists') return method === 'PUT' ? SV('sq_lists', opts.body) : LS('sq_lists', DEFAULT_LISTS);
    if (p === '/api/settings') return method === 'PUT' ? SV('sq_settings', { ...LS('sq_settings', {}), ...opts.body }) : { ...SETTINGS, ...LS('sq_settings', {}) };
    if (p === '/api/portfolio') return method === 'PUT' ? SV('sq_portfolio', opts.body) : LS('sq_portfolio', DEFAULT_PORTFOLIO);
    if (p === '/api/quotes') {
      const all = await quotes();
      await searchIndex();
      const out = {};
      (q.get('symbols') || '').split(',').filter(Boolean).forEach((s) => { if (all[s]) out[s] = { symbol: s, name: S.names[s] || s, ...all[s] }; });
      return out;
    }
    if (p === '/api/search') return search(q.get('q') || '');
    if (p === '/api/status') return { version: ST.version, data: { yfinance: 'published build', cache: {} }, market: (S.meta || {}).market, home: 'this browser (watchlists and portfolio stay on this device)', meta: S.meta };
    if (p === '/api/compare') return compare((q.get('symbols') || '').split(',').filter(Boolean), q.get('range') || '1Y', q.get('bench') || 'SPY');
    if (method !== 'GET' || p.startsWith('/api/export') || p === '/api/offer') throw new Error(SQ.LOCAL_ONLY);
    const m = p.match(/^\/api\/ticker\/([^/]+)\/chart$/);
    if (m) {
      const sym = decodeURIComponent(m[1]);
      if (!SQ.isPublished(sym)) throw new Error(`${sym}: full charts are published for semiconductors and US mega caps. The local edition charts any ticker.`);
      return chart(sym, q.get('range') || '6M', (q.get('ind') || '').split(',').filter(Boolean));
    }
    try {
      return await get(SQ.fileKey(path), built());
    } catch (e) {
      if (e.status === 404) throw new Error(SQ.isPublished(decodeURIComponent((p.match(/^\/api\/ticker\/([^/]+)/) || [])[1] || ''))
        ? 'This section is still being prepared: new analytics are added at every refresh (about every 15 minutes). The local edition computes it instantly.'
        : 'Not published on the website. The local edition (free, runs on your computer) has this for any ticker.');
      throw e;
    }
  };

  // ─── freshness: poll meta.json, refresh quotes when a new build lands ─
  const ago = (iso) => { const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000); return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : Math.round(m / 60) + ' h ago'; };
  SQ.updateStatus = async () => {
    try { await SQ.loadMeta(); } catch (e) { /* offline: keep the last state */ }
    const m = S.meta;
    const txt = SQ.$('#mkt-text'), dot = SQ.$('#live-dot');
    if (!m) { if (txt) txt.textContent = 'Offline: showing saved data'; return; }
    const st = m.market || {};
    const open = (st.status || '').toLowerCase() === 'open';
    if (dot) dot.className = 'dot ' + (open ? 'open' : '');
    const streaming = SQ.stream && SQ.stream.fresh(); // prices are live; the analytics are from the build
    if (txt) txt.textContent = `${streaming ? 'Analytics' : 'Data'} ${fmt.time(m.built_at)} · ${ago(m.built_at)} · ${open ? 'US market open' : st.message || 'US market closed'}`;
  };
  async function poll() {
    let changed = false;
    try { changed = await SQ.loadMeta(); } catch (e) { /* offline */ }
    if (changed && S.quotes) {
      try { await quotes(true); SQ.live.tick(true); } catch (e) { /* ignore */ }
      SQ.ui.toast(`New data published (${fmt.time(S.meta.built_at)}). Prices updated; tap refresh for every number.`, 5000);
    }
    SQ.updateStatus();
  }
  setInterval(poll, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

  // ─── sharing a page (instead of downloading an HTML snapshot) ─────────
  SQ.shareLink = async (title) => {
    const url = location.href;
    try {
      if (navigator.share) { await navigator.share({ title: title || document.title, url }); return; }
      await navigator.clipboard.writeText(url);
      SQ.ui.toast('Link copied: send it to anyone.');
    } catch (e) { /* cancelled */ }
  };
})();
