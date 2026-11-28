/* Bootstrap: sidebar watchlist, search / command palette, shortcuts, first render. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { $, h, fmt, ui, api } = SQ;

  // ─── Watchlist sidebar ────────────────────────────────────────────────
  const WL = { lists: {}, current: null };
  SQ.watchlists = WL;
  function renderWatchlist() {
    const sel = $('#wl-select'), rows = $('#wl-rows');
    sel.innerHTML = '';
    Object.keys(WL.lists).forEach((k) => sel.appendChild(h('option', { value: k, selected: k === WL.current }, k)));
    const syms = WL.lists[WL.current] || [];
    rows.innerHTML = '';
    const cur = (SQ.route().parts[0] === 't') ? (SQ.route().parts[1] || '').toUpperCase() : '';
    syms.forEach((s) => {
      const q = SQ.live.quotes[s] || {};
      const row = h('div', { class: 'wl-row' + (s === cur ? ' on' : ''), title: 'Open ' + s, onclick: () => SQ.go('#/t/' + encodeURIComponent(s)) },
        h('span', { class: 's' }, s),
        h('span', { class: 'p', dataset: { live: s + ':price:price' } }, fmt.price(q.price)),
        h('span', { class: 'n', dataset: { live: s + ':name:text' } }, q.name || ''),
        h('span', { class: 'c ' + fmt.cls(q.change_pct), dataset: { live: s + ':change_pct:pct', sign: 'change_pct' } }, fmt.pct(q.change_pct, 2)));
      row.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        if (SQ.snapshot) return;
        if (confirm(`Remove ${s} from "${WL.current}"?`)) { WL.lists[WL.current] = syms.filter((x) => x !== s); saveWatchlists(); }
      });
      rows.appendChild(row);
    });
    if (!syms.length) rows.appendChild(h('div', { class: 'dim', style: { padding: '6px 8px', fontSize: '13px' } }, 'Empty list. Add a ticker below.'));
    SQ.live.register('sidebar', syms);
    SQ.live.apply(rows);
  }
  SQ.renderWatchlist = renderWatchlist;
  async function saveWatchlists() {
    try { WL.lists = await SQ.put('/api/watchlists', WL.lists); } catch (e) { ui.toast('Could not save: ' + e.message); }
    renderWatchlist();
    SQ.live.tick(true);
  }
  SQ.addToWatchlist = (sym, list) => {
    const name = list || WL.current;
    const arr = WL.lists[name] || (WL.lists[name] = []);
    if (!arr.includes(sym)) { arr.push(sym); saveWatchlists(); ui.toast(`${sym} added to "${name}"`); }
    else ui.toast(`${sym} is already in "${name}"`);
  };
  async function loadWatchlists() {
    try { WL.lists = await api('/api/watchlists'); } catch (e) { WL.lists = { 'My watchlist': ['NVDA', 'AMD', 'AVGO', 'TSM'] }; }
    let saved = null;
    try { saved = localStorage.getItem('sq_wl'); } catch (e) { /* ignore */ }
    WL.current = saved && WL.lists[saved] ? saved : Object.keys(WL.lists).includes('My watchlist') ? 'My watchlist' : Object.keys(WL.lists)[0];
    renderWatchlist();
  }
  $('#wl-select').addEventListener('change', (e) => {
    WL.current = e.target.value;
    try { localStorage.setItem('sq_wl', WL.current); } catch (err) { /* ignore */ }
    renderWatchlist(); SQ.live.tick(true);
  });
  const addFromInput = () => {
    const v = $('#wl-input').value.trim().toUpperCase();
    if (!v) return;
    $('#wl-input').value = '';
    SQ.addToWatchlist(v);
  };
  $('#wl-add-btn').addEventListener('click', addFromInput);
  $('#wl-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') addFromInput(); });
  window.addEventListener('hashchange', renderWatchlist);

  // ─── Search / command palette ─────────────────────────────────────────
  const COMMANDS = [
    ['#/market', 'Market dashboard', 'Page'], ['#/world', 'World risk: conflicts, straits, shipping', 'Page'], ['#/screener', 'Screener: semis, US large caps, global, ETFs', 'Page'],
    ['#/compare', 'Compare tickers', 'Page'], ['#/portfolio', 'Portfolio risk & optimizer', 'Page'],
    ['#/offer', 'Offer & RSU value simulator', 'Page'], ['#/calendar', 'Earnings & economic calendar', 'Page'],
    ['#/settings', 'Settings, exports & help', 'Page'],
  ];
  const input = $('#q'), box = $('#suggest');
  let items = [], sel = -1, timer = null, seq = 0;
  function close() { box.classList.add('hidden'); sel = -1; }
  function choose(it) {
    close(); input.value = ''; input.blur();
    if (it.href) SQ.go(it.href);
  }
  function draw() {
    box.innerHTML = '';
    if (!items.length) { close(); return; }
    let grp = null;
    items.forEach((it, i) => {
      if (it.grp !== grp) { grp = it.grp; box.appendChild(h('div', { class: 'grp label' }, grp)); }
      box.appendChild(h('div', { class: 'it' + (i === sel ? ' on' : ''), role: 'option', onmousedown: (e) => { e.preventDefault(); choose(it); } },
        h('span', { class: 's' }, it.sym), h('span', { class: 'n' }, it.name || ''), h('span', { class: 't' }, it.type || '')));
    });
    box.classList.remove('hidden');
  }
  async function query(v) {
    const my = ++seq;
    const s = v.trim();
    if (!s) { items = []; draw(); return; }
    const up = s.toUpperCase();
    const cmds = COMMANDS.filter(([, label]) => label.toLowerCase().includes(s.toLowerCase())).slice(0, 4)
      .map(([href, label, type]) => ({ href, sym: '→', name: label, type, grp: 'Go to' }));
    const direct = /^[\^A-Z0-9.=\-]{1,15}$/.test(up) ? [{ href: '#/t/' + encodeURIComponent(up), sym: up, name: 'Open ' + up, type: 'Ticker', grp: 'Open' }] : [];
    items = direct.concat(cmds); sel = 0; draw();
    if (SQ.snapshot) return;
    try {
      const res = await api('/api/search?q=' + encodeURIComponent(s));
      if (my !== seq) return;
      const found = res.filter((r) => r.symbol !== up).map((r) => ({ href: '#/t/' + encodeURIComponent(r.symbol), sym: r.symbol, name: r.name,
        type: [r.type, r.exchange || r.sector].filter(Boolean).join(' · '), grp: r.universe ? 'Universe: ' + r.universe : 'Yahoo Finance' }));
      items = direct.concat(found, cmds);
      sel = 0; draw();
    } catch (e) { /* keep local items */ }
  }
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => query(input.value), 140); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(items.length - 1, sel + 1); draw(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    else if (e.key === 'Enter') { if (items[sel]) choose(items[sel]); else if (input.value.trim()) choose({ href: '#/t/' + encodeURIComponent(input.value.trim().toUpperCase()) }); }
    else if (e.key === 'Escape') { close(); input.blur(); }
  });
  input.addEventListener('blur', () => setTimeout(close, 120));
  input.addEventListener('focus', () => { if (input.value) query(input.value); });

  // ─── Shortcuts & buttons ──────────────────────────────────────────────
  document.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if (e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) { e.preventDefault(); input.focus(); input.select(); }
    else if (e.key === 'r' && !e.metaKey && !e.ctrlKey) { refresh(); }
    else if (e.key === 't' && !e.metaKey && !e.ctrlKey) { SQ.toggleTheme(); }
    else if (e.key === 'g') { SQ.go('#/market'); }
  });
  function refresh() { SQ.live.tick(true); SQ.updateStatus(); SQ.render(); ui.toast('Refreshing…', 1200); }
  $('#refresh-btn').addEventListener('click', refresh);
  $('#theme-btn').addEventListener('click', SQ.toggleTheme);

  // ─── Phone pages: watchlist and "more" ────────────────────────────────
  SQ.views.watchlist = async function (view) {
    const lists = WL.lists || {};
    view.appendChild(h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Watchlist'),
      h('div', { class: 'sub' }, SQ.static ? 'Saved on this device. Prices refresh with every published update.' : 'Live prices; tap a row to open it.'))));
    const sel = ui.select(Object.keys(lists), WL.current, (v) => { WL.current = v; try { localStorage.setItem('sq_wl', v); } catch (e) { /* ignore */ } draw(); });
    const inp = h('input', { class: 'inp', placeholder: 'Add ticker (e.g. NVDA)', style: { flex: '1', minWidth: '0' } });
    const add = () => { const v = inp.value.trim().toUpperCase(); if (v) { inp.value = ''; SQ.addToWatchlist(v); setTimeout(draw, 300); } };
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
    view.appendChild(h('div', { class: 't-tools' }, sel, inp, h('button', { class: 'btn primary', type: 'button', onclick: add }, 'Add')));
    const box = h('section', { class: 'panel wl-page' });
    view.appendChild(box);
    function draw() {
      const syms = (WL.lists || {})[WL.current] || [];
      box.innerHTML = '';
      syms.forEach((s) => {
        const q = SQ.live.quotes[s] || {};
        const remove = (e) => { e.stopPropagation(); WL.lists[WL.current] = syms.filter((x) => x !== s); saveWatchlists(); setTimeout(draw, 200); };
        const row = h('div', { class: 'wl-row', onclick: () => SQ.go('#/t/' + encodeURIComponent(s)) },
          h('span', { class: 's' }, s), h('span', { class: 'p', dataset: { live: s + ':price:price' } }, fmt.price(q.price)),
          h('button', { class: 'btn sm x', type: 'button', title: 'Remove', onclick: remove }, '✕'),
          h('span', { class: 'n', dataset: { live: s + ':name:text' } }, q.name || ''),
          h('span', { class: 'c ' + fmt.cls(q.change_pct), dataset: { live: s + ':change_pct:pct', sign: 'change_pct' } }, fmt.pct(q.change_pct, 2)));
        box.appendChild(row);
      });
      if (!syms.length) box.appendChild(ui.empty('Empty list: add a ticker above.'));
      SQ.live.register('wlpage', syms);
      SQ.live.tick(true);
    }
    draw();
  };

  // Phones: a short command-line prompt instead of the long desktop hint.
  if (window.matchMedia && matchMedia('(max-width: 980px)').matches) $('#q').placeholder = 'Ticker or company…';

  // Phones clamp page intros to two lines: a tap shows the whole text.
  document.addEventListener('click', (e) => { const s = e.target.closest('.page-h .sub'); if (s) s.classList.toggle('open'); });
  // Swipeable tab rows: bring the active tab into view whenever a row is (re)drawn.
  const centerActive = (row) => {
    const on = row.querySelector('.on');
    if (!on || row.scrollWidth <= row.clientWidth) return;
    const r = on.getBoundingClientRect(), rr = row.getBoundingClientRect();
    row.scrollLeft += (r.left - rr.left) - (row.clientWidth - r.width) / 2;
  };
  new MutationObserver((muts) => {
    const rows = new Set();
    for (const m of muts) {
      if (m.target.nodeType === 1 && m.target.matches('.tabs, .seg')) rows.add(m.target); // tabs filled in after the row
      for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.matches('.tabs, .seg')) rows.add(n);
        n.querySelectorAll('.tabs, .seg').forEach((r) => rows.add(r));
      }
    }
    if (rows.size) requestAnimationFrame(() => rows.forEach(centerActive));
  }).observe($('#view'), { childList: true, subtree: true });

  let installEvt = null;
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installEvt = e; $('#install-btn').classList.remove('hidden'); });
  SQ.install = async () => {
    if (installEvt) { installEvt.prompt(); await installEvt.userChoice; installEvt = null; $('#install-btn').classList.add('hidden'); return; }
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    ui.toast(ios ? 'iPhone / iPad: tap Share (the square with the arrow) in Safari, then "Add to Home Screen".'
      : 'Open the browser menu and choose "Install app" or "Add to Home screen".', 7000);
  };
  $('#install-btn').addEventListener('click', SQ.install);
  // Inside the Android app (a WebView that tags its user agent) there is nothing to install.
  const inAndroidApp = /SemiQuantAndroid/.test(navigator.userAgent);
  const standalone = () => inAndroidApp || window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const APK = 'https://github.com/chennakeshavadasa/career-semi-quant/releases/download/android/SemiQuant.apk';

  SQ.views.more = async function (view) {
    const icon = (d) => h('span', { html: '<svg viewBox="0 0 24 24">' + d + '</svg>' });
    view.appendChild(h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'More'))));
    const items = [
      ['#/world', 'World risk', 'Wars, straits and shipping, and what they can hit', '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/>'],
      ['#/factorlab', 'Factor lab', 'Which signals predict returns: IC, quintile spreads, decay', '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/>'],
      ['#/congress', 'Congress trades', 'What members of Congress bought and sold; committee seats flagged', '<path d="M4 20h16M5 17h14M6 17V10M10 17V10M14 17V10M18 17V10M3 10h18L12 4z"/>'],
      ['#/compare', 'Compare', 'Performance, risk and correlation side by side', '<path d="M4 18l5-6 4 3 7-9"/>'],
      ['#/portfolio', 'Portfolio', 'Risk, optimizers, backtest, Monte Carlo', '<circle cx="12" cy="12" r="8"/><path d="M12 4v8l6 4"/>'],
      ['#/offer', 'Offer & RSU value', 'What an equity grant could be worth at each vest', '<rect x="4" y="7" width="16" height="12" rx="2"/><path d="M9 7V5h6v2"/>'],
      ['#/settings', 'Settings & help', 'Watchlists, data freshness, sharing', '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>'],
    ];
    const list = h('div', { class: 'menu-list' }, items.map(([href, t, sub, d]) => h('a', { href }, icon(d), h('span', null, t, h('small', null, sub)))),
      h('button', { type: 'button', onclick: SQ.toggleTheme }, icon('<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16z"/>'),
        h('span', null, 'Terminal / light theme', h('small', null, 'Black Bloomberg-style terminal or paper light; follows your choice everywhere'))),
      standalone() ? null : h('button', { type: 'button', onclick: SQ.install }, icon('<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>'),
        h('span', null, 'Install as an app', h('small', null, 'Home-screen icon, opens full screen, keeps the last data offline'))),
      inAndroidApp && window.SQAndroid && SQAndroid.checkUpdate
        // Two parts update separately: the layout (web edition, redeployed on every push) and the
        // Android shell (APK, rebuilt only when android/ changes). The button refreshes both.
        ? h('button', { type: 'button', onclick: () => {
            // App builds with checkAppUpdate leave the layout to this page; older ones only have checkUpdate.
            if (SQAndroid.checkAppUpdate) SQAndroid.checkAppUpdate(); else SQAndroid.checkUpdate();
            if (SQ.checkForUpdate) SQ.checkForUpdate();
          } },
          icon('<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>'),
          h('span', null, 'Update app', h('small', null, 'App ' + (SQAndroid.appVersion ? SQAndroid.appVersion() : '?')
            + (SQ.static && window.SQ_STATIC.build ? ' · layout ' + window.SQ_STATIC.build : '') + ' · loads the newest layout and app build')))
        : SQ.static && SQ.checkForUpdate
          ? h('button', { type: 'button', onclick: () => SQ.checkForUpdate() }, icon('<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>'),
            h('span', null, 'Check for updates', h('small', null, 'Build ' + window.SQ_STATIC.build + ' · reloads into the newest published version')))
          : null,
      SQ.static && !inAndroidApp && /android/i.test(navigator.userAgent)
        ? h('a', { href: APK, rel: 'noopener' }, icon('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>'),
          h('span', null, 'Android app (APK)', h('small', null, 'Download and install the native app')))
        : null);
    view.appendChild(list);
  };

  if (SQ.static && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => null));
  }

  // ─── Start ────────────────────────────────────────────────────────────
  (async function start() {
    if (SQ.snapshot) {
      const b = $('#snap-banner');
      b.classList.remove('hidden');
      b.innerHTML = `<b>Shared snapshot</b> · data as of ${fmt.dateTime(SQ.snapshot.created)} · interactive charts, frozen numbers. ` +
        `Install the free local tool for live data: <a href="https://github.com/chennakeshavadasa/career-semi-quant/tree/master/local" target="_blank" rel="noopener">how to run it</a>.`;
      $('#refresh-btn').classList.add('hidden');
      $('#wl-input').closest('.wl-add').classList.add('hidden');
    }
    if (SQ.static) {
      const sub = $('.brand small');
      if (sub) sub.textContent = 'Web edition · live prices · analytics every ~15 min';
    }
    if (SQ.snapshot) {
      Object.assign(SQ.live.quotes, SQ.snapshot.quotes || {});
      if (!location.hash && SQ.snapshot.home) history.replaceState(null, '', '#/' + SQ.snapshot.home);
    }
    await SQ.loadSettings();
    if (SQ.stream) SQ.stream.sync(); // honour a saved "streaming off"
    await loadWatchlists();
    SQ.updateStatus();
    if (!SQ.snapshot) setInterval(SQ.updateStatus, 60000);
    SQ.render();
    // Content blockers match scripts by file name (EasyPrivacy blocked our old "quant.js"): say so
    // instead of failing later with "SQ.quant is undefined".
    const missing = [['quant', 'portfolio and offer models'], ['charts', 'charts'], ['ta', 'indicators'], ['qp', 'quant panels']]
      .filter(([k]) => !SQ[k]).map(([, label]) => label);
    if (missing.length) ui.toast(`Part of the app did not load (${missing.join(', ')}). A content blocker may have blocked it: allow this site, then reload.`, 15000);
  })();
})();
