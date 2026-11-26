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
    ['#/market', 'Market dashboard', 'Page'], ['#/screener', 'Screener: semiconductor universe', 'Page'],
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
        type: [r.type, r.exchange].filter(Boolean).join(' · '), grp: r.universe ? 'Semiconductor universe' : 'Yahoo Finance' }));
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
    if (SQ.snapshot) {
      Object.assign(SQ.live.quotes, SQ.snapshot.quotes || {});
      if (!location.hash && SQ.snapshot.home) history.replaceState(null, '', '#/' + SQ.snapshot.home);
    }
    await SQ.loadSettings();
    await loadWatchlists();
    SQ.updateStatus();
    if (!SQ.snapshot) setInterval(SQ.updateStatus, 60000);
    SQ.render();
  })();
})();
