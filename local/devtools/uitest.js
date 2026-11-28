// Dev tool (not shipped): needs Node and Playwright (npm i playwright). See HANDOFF.md.
// Phone UI test harness for the web edition.
// node uitest.js <baseUrl> <outDir> [configs=all] [routes=all]
// Conditions: several phone sizes, both themes, landscape, tablet and Android text zoom 130 %.
// Per page it reports: nested scroll areas, content past the screen edge, overlapping text,
// clipped / spilling text, small tap targets, tiny text, content hidden under the tab bar,
// page errors; and saves a screenshot of the first screen.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2];
const OUT = process.argv[3];
const CONFIGS = {
  a360: { viewport: { width: 360, height: 780 }, theme: 'dark' },
  p412: { viewport: { width: 412, height: 915 }, theme: 'dark' },
  se375light: { viewport: { width: 375, height: 667 }, theme: 'light' },
  zoom130: { viewport: { width: 393, height: 852 }, theme: 'dark', zoom: 1.3 },
  land800: { viewport: { width: 800, height: 360 }, theme: 'dark' },
  tab768: { viewport: { width: 768, height: 1024 }, theme: 'dark' },
  desk1400: { viewport: { width: 1400, height: 900 }, theme: 'dark' },
  desk1400light: { viewport: { width: 1400, height: 900 }, theme: 'light' },
};
const T = ['overview', 'risk', 'volatility', 'tail', 'options', 'fundamentals', 'analysts', 'ownership', 'factors', 'events'];
const ROUTES = [
  ['market', '#/market'], ['screener', '#/screener'], ['watchlist', '#/watchlist'], ['calendar', '#/calendar'], ['more', '#/more'],
  ['compare', '#/compare?s=NVDA,AMD,SOXX'], ['portfolio', '#/portfolio'], ['offer', '#/offer?t=NVDA'], ['settings', '#/settings'],
  ...T.map((t) => ['nvda_' + t, '#/t/NVDA/' + t]),
  ['nvda_smart', '#/t/NVDA/smart'], ['congress', '#/congress'], ['congress365', '#/congress?days=365'],
  ['world', '#/world'], ['world_taiwan', '#/world?s=chokepoint11'],
  ['factorlab', '#/factorlab?u=semis'], ['factorlab_us', '#/factorlab?u=us_large'],
  ['aapl', '#/t/AAPL'], ['spy', '#/t/SPY'], ['tokyo', '#/t/8035.T'], ['btc', '#/t/BTC-USD'],
];
const cfgNames = process.argv[4] && process.argv[4] !== 'all' ? process.argv[4].split(',') : Object.keys(CONFIGS);
const routeNames = process.argv[5] && process.argv[5] !== 'all' ? process.argv[5].split(',') : ROUTES.map((r) => r[0]);
fs.mkdirSync(OUT, { recursive: true });

// Runs in the page.
function inspect(opts) {
  const vw = window.innerWidth, vh = window.innerHeight;
  const vis = (el) => el && el.checkVisibility ? el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) : !!(el && el.offsetParent);
  const label = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const c = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.') : '';
    if (c) s += '.' + c;
    const t = (el.textContent || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 28);
    return t ? `${s} "${t}"` : s;
  };
  const out = { vw };
  // 1. scroll areas other than the page itself
  out.scrollers = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    const sx = /(auto|scroll)/.test(s.overflowX) && el.scrollWidth > el.clientWidth + 1;
    const sy = /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 1;
    if (sx || sy) out.scrollers.push(label(el).slice(0, 60) + (sx ? ' [X]' : '') + (sy ? ' [Y]' : ''));
  }
  const docScrollX = document.documentElement.scrollWidth - vw;
  out.pageScrollX = docScrollX > 1 ? docScrollX : 0;
  // 2. content past the screen edge (not inside a table scroller)
  out.past = [];
  const inTable = (el) => !!el.closest('.tw');
  const reported = [];
  for (const el of document.querySelectorAll('#view *, .topbar *, #bnav *')) {
    if (!vis(el) || inTable(el)) continue;
    if (reported.some((r) => r.contains(el))) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right > vw + 1.5 || r.left < -1.5) { reported.push(el); out.past.push(`${label(el)} [${Math.round(r.left)}..${Math.round(r.right)}]`); }
  }
  // 3. text boxes -> overlaps
  const clipCache = new Map();
  const clipOf = (el) => { // visible region allowed by overflow-clipping ancestors
    if (clipCache.has(el)) return clipCache.get(el);
    let c = { l: -1e9, t: -1e9, r: 1e9, b: 1e9 };
    const p = el.parentElement;
    if (p && p !== document.body) {
      c = { ...clipOf(p) };
      const s = getComputedStyle(p);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const r = p.getBoundingClientRect();
        if (s.overflowX !== 'visible') { c.l = Math.max(c.l, r.left); c.r = Math.min(c.r, r.right); }
        if (s.overflowY !== 'visible') { c.t = Math.max(c.t, r.top); c.b = Math.min(c.b, r.bottom); }
      }
    }
    clipCache.set(el, c);
    return c;
  };
  const boxes = [];
  const range = document.createRange();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (tw.nextNode()) {
    const n = tw.currentNode, el = n.parentElement;
    if (!el || !n.textContent.trim() || el.closest('script,style,.suggest,.ind-pop,.toast,svg,.hidden,[hidden]') || !vis(el)) continue;
    let c = clipOf(el);
    { // the text's own element clips too (line clamps, ellipsis)
      const s = getComputedStyle(el);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const r = el.getBoundingClientRect();
        c = { ...c };
        if (s.overflowX !== 'visible') { c.l = Math.max(c.l, r.left); c.r = Math.min(c.r, r.right); }
        if (s.overflowY !== 'visible') { c.t = Math.max(c.t, r.top); c.b = Math.min(c.b, r.bottom); }
      }
    }
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      const b = { l: Math.max(r.left, c.l), t: Math.max(r.top, c.t), r: Math.min(r.right, c.r), b: Math.min(r.bottom, c.b) };
      if (b.r - b.l > 1 && b.b - b.t > 1) boxes.push({ ...b, el, txt: n.textContent.trim().slice(0, 22), fixed: !!el.closest('#bnav,.topbar') });
    }
  }
  for (const el of document.querySelectorAll('svg text')) {
    if (!el.textContent.trim() || !vis(el)) continue;
    const r = el.getBoundingClientRect(), c = clipOf(el);
    const b = { l: Math.max(r.left, c.l), t: Math.max(r.top, c.t), r: Math.min(r.right, c.r), b: Math.min(r.bottom, c.b) };
    if (b.r - b.l > 1 && b.b - b.t > 1) boxes.push({ ...b, el, txt: el.textContent.trim().slice(0, 22), svg: true });
  }
  // text running past the screen edge (elements can fit while their text spills out)
  for (const b of boxes) {
    if (b.fixed || b.svg) continue;
    if (b.r > vw + 1.5 && !b.el.closest('.tw')) { out.past.push(`text "${b.txt}" [${Math.round(b.l)}..${Math.round(b.r)}]`); if (out.past.length > 30) break; }
  }
  boxes.sort((a, b) => a.t - b.t);
  out.overlaps = [];
  for (let i = 0; i < boxes.length; i++) {
    const a = boxes[i];
    for (let j = i + 1; j < boxes.length && boxes[j].t < a.b; j++) {
      const b = boxes[j];
      if (a.el === b.el || a.fixed !== b.fixed) continue;
      const ox = Math.min(a.r, b.r) - Math.max(a.l, b.l), oy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
      if (ox > 2 && oy > Math.max(3, 0.35 * Math.min(a.b - a.t, b.b - b.t))) {
        out.overlaps.push(`"${a.txt}" x "${b.txt}" @${Math.round(a.l)},${Math.round(a.t)}${a.svg || b.svg ? ' (svg)' : ''}`);
        if (out.overlaps.length > 40) break;
      }
    }
    if (out.overlaps.length > 40) break;
  }
  // 4. clipped or spilling text
  out.clipped = [];
  for (const el of document.querySelectorAll('#view *, .topbar *, #bnav *')) {
    if (!vis(el) || !el.childNodes.length) continue;
    const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) continue;
    const s = getComputedStyle(el);
    const clipX = s.overflowX !== 'visible' && s.textOverflow !== 'ellipsis' && el.scrollWidth > el.clientWidth + 2;
    const clipY = s.overflowY !== 'visible' && !/-webkit-box/.test(s.display) && !parseInt(s.webkitLineClamp || 0, 10) && el.scrollHeight > el.clientHeight + 2;
    const spillY = s.overflowY === 'visible' && /px$/.test(s.height) && s.height !== 'auto' && el.scrollHeight > el.clientHeight + 4 && el.clientHeight > 0;
    if (clipX || clipY || spillY) out.clipped.push(label(el) + (clipX ? ' clipX' : '') + (clipY ? ' clipY' : '') + (spillY ? ' spillY' : ''));
  }
  // 5. tap targets
  out.small = [];
  const sel = 'a[href], button, select, input:not([type=hidden]), [role=button], .tile, .qb-row, tr.click';
  for (const el of document.querySelectorAll(sel)) {
    if (!vis(el) || el.closest('.note, .cap, p, .news, td.txt, .suggest')) continue;
    if (el.matches('a') && el.closest('table') && !el.closest('th')) continue;
    let t = el;
    if (el.matches('input[type=checkbox], input[type=radio]') && el.closest('label')) t = el.closest('label');
    const r = t.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.height < 32 || r.width < 32) out.small.push(`${label(t)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  // 6. tiny text
  out.tiny = [];
  for (const b of boxes) {
    const fs = b.svg ? parseFloat(b.el.getAttribute('font-size') || getComputedStyle(b.el).fontSize) : parseFloat(getComputedStyle(b.el).fontSize);
    if (fs < 11 && !out.tiny.some((x) => x.startsWith(b.txt))) out.tiny.push(`${b.txt} ${fs}px${b.svg ? ' svg' : ''}`);
  }
  // 7. bottom bar covering the end of the page
  const nav = document.querySelector('#bnav');
  out.navCover = null;
  if (nav && vis(nav)) {
    const sc = [document.querySelector('#main'), document.scrollingElement].find((e) => e && e.scrollHeight > e.clientHeight + 1) || document.scrollingElement;
    sc.scrollTop = sc.scrollHeight;
    const navTop = nav.getBoundingClientRect().top;
    let last = null;
    for (const el of document.querySelectorAll('#view *')) {
      if (!vis(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.height > 0 && (!last || r.bottom > last.b)) last = { b: r.bottom, el };
    }
    if (last && last.b > navTop + 1) out.navCover = `${label(last.el)} bottom ${Math.round(last.b)} > bar ${Math.round(navTop)}`;
    sc.scrollTop = 0;
  }
  out.empty = (() => { const e = document.querySelector('#view .err, #view .empty'); return e ? e.textContent.trim().slice(0, 90) : null; })();
  return out;
}

function zoomText(f) {
  const els = Array.from(document.querySelectorAll('body *')).filter((e) => !(e instanceof SVGElement) && !['CANVAS', 'SCRIPT', 'STYLE', 'BR'].includes(e.tagName));
  const sizes = els.map((e) => parseFloat(getComputedStyle(e).fontSize));
  els.forEach((e, i) => e.style.setProperty('font-size', sizes[i] * f + 'px', 'important'));
}

async function runConfig(browser, name) {
  const c = CONFIGS[name];
  const ctx = await browser.newContext({ viewport: c.viewport, deviceScaleFactor: 1, isMobile: c.viewport.width < 980, hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36 SemiQuantTest' });
  await ctx.addInitScript((t) => { try { localStorage.setItem('sq-theme', t); localStorage.setItem('sq_settings', JSON.stringify({ stream: false })); } catch (e) { /* */ } }, c.theme);
  const res = {};
  for (const [rn, hash] of ROUTES) {
    if (!routeNames.includes(rn)) continue;
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message.slice(0, 140)));
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text().slice(0, 140)); });
    try {
      await page.goto(BASE + hash, { waitUntil: 'load', timeout: 45000 });
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2500);
      if (c.zoom) { await page.evaluate(zoomText, c.zoom); await page.waitForTimeout(600); }
      const r = await page.evaluate(inspect, {});
      r.errors = errors;
      res[rn] = r;
      await page.screenshot({ path: path.join(OUT, `${name}__${rn}.png`), fullPage: name === 'a360' || name === 'se375light' || name.startsWith('desk') });
    } catch (e) {
      res[rn] = { fatal: String(e).slice(0, 160), errors };
    }
    await page.close();
  }
  await ctx.close();
  return res;
}

(async () => {
  const browser = await chromium.launch();
  const all = {};
  await Promise.all(cfgNames.map(async (n) => { all[n] = await runConfig(browser, n); process.stdout.write(n + ' done; '); }));
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(all, null, 1));
  // Summary
  const keys = ['scrollers', 'past', 'overlaps', 'clipped', 'small', 'tiny'];
  console.log('\n' + 'config/page'.padEnd(26) + 'scrl past ovlp clip small tiny pgX nav err');
  for (const [cn, pages] of Object.entries(all)) {
    for (const [pn, r] of Object.entries(pages)) {
      if (r.fatal) { console.log(`${cn}/${pn}`.padEnd(26) + 'FATAL ' + r.fatal); continue; }
      console.log(`${cn}/${pn}`.padEnd(26) + keys.map((k) => String(r[k].length).padStart(k === 'small' ? 5 : 4)).join(' ') + String(r.pageScrollX).padStart(4) + (r.navCover ? '  NAV' : '    -') + String(r.errors.length).padStart(3) + (r.empty ? '  | ' + r.empty.slice(0, 50) : ''));
    }
  }
  await browser.close();
})();
