/* Semi Quant Terminal - core runtime: DOM helpers, formatting, API client (with
 * snapshot mode for shared HTML files), live quotes, router, theme and UI components.
 * Classic script (no modules) so the exporter can inline everything into one file. */
(function () {
  'use strict';
  const SQ = (window.SQ = window.SQ || {});
  SQ.views = SQ.views || {};
  const SNAP = window.SQ_SNAPSHOT || null;
  SQ.snapshot = SNAP;
  const STATIC = window.SQ_STATIC || null; // published website (see static.js)
  SQ.static = STATIC;

  // ─── DOM ──────────────────────────────────────────────────────────────
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'html') el.innerHTML = v;
        else if (k === 'text') el.textContent = v;
        else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else if (k === 'dataset') Object.assign(el.dataset, v);
        else el.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const c of kids.flat(Infinity)) {
      if (c == null || c === false) continue;
      el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }
  SQ.$ = $; SQ.$$ = $$; SQ.h = h; SQ.esc = esc;

  // ─── Formatting ───────────────────────────────────────────────────────
  const ok = (x) => x !== null && x !== undefined && typeof x === 'number' && isFinite(x);
  const DASH = '–';
  const fmt = {
    ok,
    num(x, d = 2) { return ok(x) ? x.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) : DASH; },
    int(x) { return ok(x) ? Math.round(x).toLocaleString('en-US') : DASH; },
    pct(x, d = 1, sign = true) { return ok(x) ? (sign && x > 0 ? '+' : '') + (x * 100).toFixed(d) + '%' : DASH; },
    pctu(x, d = 1) { return fmt.pct(x, d, false); },
    pp(x, d = 1) { return ok(x) ? (x > 0 ? '+' : '') + (x * 100).toFixed(d) + ' pp' : DASH; },
    price(x, ccy) {
      if (!ok(x)) return DASH;
      const a = Math.abs(x), d = a >= 1000 ? 2 : a >= 1 ? 2 : a >= 0.01 ? 4 : 6;
      const s = x.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
      return ccy && ccy !== 'USD' ? s : (ccy === 'USD' ? '$' + s : s);
    },
    money(x, ccy = 'USD') {
      if (!ok(x)) return DASH;
      const sym = { USD: '$', EUR: '€', GBP: '£', JPY: '¥', KRW: '₩', TWD: 'NT$', CNY: '¥', HKD: 'HK$' }[ccy] || '';
      return (x < 0 ? '-' : '') + sym + fmt.big(Math.abs(x)).replace(/^\$/, '') + (sym ? '' : ' ' + (ccy || ''));
    },
    big(x, d = 2) {
      if (!ok(x)) return DASH;
      const a = Math.abs(x), s = x < 0 ? '-' : '';
      if (a >= 1e12) return s + (a / 1e12).toFixed(d) + 'T';
      if (a >= 1e9) return s + (a / 1e9).toFixed(d) + 'B';
      if (a >= 1e6) return s + (a / 1e6).toFixed(d) + 'M';
      if (a >= 1e3) return s + (a / 1e3).toFixed(1) + 'K';
      return s + a.toFixed(a < 10 ? 2 : 0);
    },
    x(x, d = 1) { return ok(x) ? x.toFixed(d) + '×' : DASH; },
    date(s) {
      if (!s) return DASH;
      const d = new Date(String(s).length === 10 ? s + 'T12:00:00' : s);
      return isNaN(d) ? String(s) : d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    },
    dateShort(s) {
      if (!s) return DASH;
      const d = new Date(String(s).length === 10 ? s + 'T12:00:00' : s);
      return isNaN(d) ? String(s) : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },
    time(s) {
      if (!s) return DASH;
      const d = new Date(s);
      return isNaN(d) ? DASH : d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    },
    dateTime(s) {
      if (!s) return DASH;
      const d = new Date(s);
      return isNaN(d) ? String(s) : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    },
    ago(s) {
      if (!s) return '';
      const sec = (Date.now() - new Date(s).getTime()) / 1000;
      if (!isFinite(sec)) return '';
      if (sec < 60) return 'just now';
      if (sec < 3600) return Math.round(sec / 60) + ' min ago';
      if (sec < 86400) return Math.round(sec / 3600) + ' h ago';
      return Math.round(sec / 86400) + ' d ago';
    },
    cls(x) { return ok(x) ? (x > 0 ? 'up' : x < 0 ? 'down' : '') : ''; },
    arrow(x) { return ok(x) ? (x > 0 ? '▲' : x < 0 ? '▼' : '') : ''; },
    any(x, kind, d) {
      switch (kind) {
        case 'pct': return fmt.pct(x, d ?? 1);
        case 'pctu': return fmt.pctu(x, d ?? 1);
        case 'num': return fmt.num(x, d ?? 2);
        case 'int': return fmt.int(x);
        case 'price': return fmt.price(x);
        case 'big': return fmt.big(x);
        case 'x': return fmt.x(x, d ?? 1);
        case 'date': return fmt.date(x);
        case 'score': return ok(x) ? Math.round(x).toString() : DASH;
        default: return x == null || x === '' ? DASH : String(x);
      }
    },
  };
  SQ.fmt = fmt;

  // ─── API ──────────────────────────────────────────────────────────────
  const inflight = new Map();
  let busy = 0;
  function setBusy(d) {
    busy = Math.max(0, busy + d);
    const l = $('#loading');
    if (l) l.classList.toggle('hidden', busy === 0);
  }
  // Must match semiquant.service.export.snap_key (sorted query, 'ind' ignored).
  function snapKey(path) {
    const u = new URL(path, 'http://x');
    const p = Array.from(u.searchParams.entries()).filter(([k]) => k !== 'ind').sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    return u.pathname.replace(/\^/g, '%5E') + (p.length ? '?' + p.map(([k, v]) => k + '=' + v).join('&') : '');
  }
  SQ.snapKey = snapKey;
  const DAILY_DAYS = { '3M': 92, '6M': 183, '1Y': 366, '2Y': 731, '5Y': 1827 };
  function snapLookup(path) {
    const k = snapKey(path);
    if (k in SNAP.data) {
      const v = SNAP.data[k];
      if (v && v.error && Object.keys(v).length === 1) throw new Error(v.error);
      return JSON.parse(JSON.stringify(v));
    }
    // Daily chart ranges are slices of the stored 10-year series.
    const m = k.match(/^(\/api\/ticker\/[^/]+\/chart)\?range=(3M|6M|YTD|1Y|2Y|5Y)$/);
    const base = m && SNAP.data[m[1] + '?range=10Y'];
    if (base && base.bars) {
      const d = JSON.parse(JSON.stringify(base));
      const t = d.bars.t, last = new Date(t[t.length - 1] + 'T12:00:00');
      const start = m[2] === 'YTD' ? new Date(last.getFullYear(), 0, 1) : new Date(last.getTime() - DAILY_DAYS[m[2]] * 864e5);
      const iso = start.toISOString().slice(0, 10);
      const i0 = Math.max(0, t.findIndex((x) => x >= iso));
      for (const f of ['t', 'o', 'h', 'l', 'c', 'v']) if (d.bars[f]) d.bars[f] = d.bars[f].slice(i0);
      for (const ind of Object.values(d.indicators || {})) for (const f of Object.keys(ind)) ind[f] = ind[f].slice(i0);
      d.range = m[2];
      return d;
    }
    throw new Error('This view is not included in the shared snapshot. Run the tool locally for live data.');
  }
  async function api(path, opts = {}) {
    if (STATIC) return SQ.staticApi(path, opts);
    if (SNAP) return snapLookup(path);
    const key = (opts.method || 'GET') + ' ' + path + (opts.body ? JSON.stringify(opts.body) : '');
    if (!opts.body && inflight.has(key)) return inflight.get(key);
    const p = (async () => {
      setBusy(1);
      try {
        const r = await fetch(path, {
          method: opts.method || 'GET',
          headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
          body: opts.body ? JSON.stringify(opts.body) : undefined,
        });
        let data = null;
        try { data = await r.json(); } catch (e) { /* non-JSON */ }
        if (!r.ok) throw new Error((data && data.error) || `Request failed (${r.status})`);
        return data;
      } finally {
        setBusy(-1);
        inflight.delete(key);
      }
    })();
    inflight.set(key, p);
    return p;
  }
  SQ.api = api;
  SQ.post = (path, body) => api(path, { method: 'POST', body });
  SQ.put = (path, body) => api(path, { method: 'PUT', body });

  // ─── Settings ─────────────────────────────────────────────────────────
  SQ.settings = { quote_refresh_seconds: 30, closed_refresh_seconds: 300, intraday_refresh_seconds: 60 };
  SQ.loadSettings = async () => {
    try { Object.assign(SQ.settings, await api('/api/settings')); } catch (e) { /* defaults */ }
  };

  // ─── Live quotes ──────────────────────────────────────────────────────
  // Elements with data-live="SYM:field[:format]" are updated in place on every refresh.
  const live = {
    regs: new Map(), quotes: {}, listeners: new Set(), timer: null, last: null, anyOpen: false,
    register(id, syms) { this.regs.set(id, new Set((syms || []).filter(Boolean).map((s) => s.toUpperCase()))); },
    unregister(id) { this.regs.delete(id); },
    onQuotes(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); },
    symbols() { const s = new Set(); for (const v of this.regs.values()) v.forEach((x) => s.add(x)); return Array.from(s); },
    apply(root = document) {
      for (const el of $$('[data-live]', root)) {
        const [sym, field, kind] = el.dataset.live.split(':');
        const q = this.quotes[sym];
        if (!q) continue;
        let v = q[field];
        if (field === 'best') v = q.price;
        const text = kind ? fmt.any(v, kind) : (field.includes('pct') ? fmt.pct(v, 2) : fmt.price(v));
        if (el.textContent !== text) {
          const prev = parseFloat(el.dataset.v);
          el.textContent = text;
          if (fmt.ok(v)) {
            if (fmt.ok(prev) && prev !== v && field === 'price') {
              el.classList.remove('flash-up', 'flash-down'); void el.offsetWidth;
              el.classList.add(v > prev ? 'flash-up' : 'flash-down');
            }
            el.dataset.v = v;
          }
        }
        if (el.dataset.sign !== undefined) {
          const sv = q[el.dataset.sign || field];
          el.classList.toggle('up', fmt.ok(sv) && sv > 0);
          el.classList.toggle('down', fmt.ok(sv) && sv < 0);
        }
      }
    },
    async tick(force) {
      if (SNAP) return;
      clearTimeout(this.timer);
      const syms = this.symbols();
      const dot = $('#live-dot');
      if (syms.length && (force || !document.hidden)) {
        dot && dot.classList.add('busy');
        try {
          const qs = await api('/api/quotes?symbols=' + encodeURIComponent(syms.join(',')));
          Object.assign(this.quotes, qs);
          this.last = new Date();
          this.anyOpen = Object.values(qs).some((q) => ['REGULAR', 'PRE', 'POST'].includes(q.market_state));
          this.apply();
          this.listeners.forEach((fn) => { try { fn(qs); } catch (e) { console.error(e); } });
          const t = $('#live-time');
          if (t) t.textContent = '· ' + this.last.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
        } catch (e) {
          console.warn('quote refresh failed', e);
        } finally {
          dot && dot.classList.remove('busy');
        }
      }
      const sec = this.anyOpen ? SQ.settings.quote_refresh_seconds : SQ.settings.closed_refresh_seconds;
      this.timer = setTimeout(() => this.tick(), Math.max(5, sec || 30) * 1000);
    },
  };
  SQ.live = live;
  document.addEventListener('visibilitychange', () => { if (!document.hidden) live.tick(true); });

  // ─── Market status (top bar) ──────────────────────────────────────────
  SQ.updateStatus = async () => {
    if (SNAP) {
      $('#mkt-text').textContent = 'Snapshot · ' + fmt.dateTime(SNAP.created);
      return;
    }
    try {
      const s = await api('/api/market/strip');
      const st = s.status || {};
      const dot = $('#live-dot');
      const open = (st.status || '').toLowerCase() === 'open';
      dot.className = 'dot ' + (open ? 'open' : '');
      $('#mkt-text').textContent = (st.message || 'US market') + (open && st.close ? ' · closes ' + fmt.time(st.close) : (!open && st.open ? ' · opens ' + fmt.dateTime(st.open) : ''));
      SQ.marketStrip = s;
    } catch (e) {
      $('#mkt-text').textContent = 'Offline: ' + e.message;
    }
  };

  // ─── Theme ────────────────────────────────────────────────────────────
  SQ.setTheme = (t) => {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('theme', t); } catch (e) { /* private mode */ }
    window.dispatchEvent(new CustomEvent('sq-theme', { detail: t }));
  };
  SQ.toggleTheme = () => SQ.setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');

  // ─── Router ───────────────────────────────────────────────────────────
  let current = null;
  SQ.cleanups = [];
  SQ.onCleanup = (fn) => SQ.cleanups.push(fn);
  function parseHash() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, qs] = raw.split('?');
    const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
    const params = Object.fromEntries(new URLSearchParams(qs || ''));
    return { parts, params, raw };
  }
  SQ.route = parseHash;
  SQ.go = (hash) => { if (location.hash !== hash) location.hash = hash; else render(); };
  async function render() {
    const { parts, params } = parseHash();
    const name = parts[0] || (SNAP && SNAP.home ? SNAP.home : 'market');
    const view = $('#view');
    const same = current && current.name === name && name === 't' && current.sym === (parts[1] || '').toUpperCase();
    if (!same) {
      SQ.cleanups.splice(0).forEach((fn) => { try { fn(); } catch (e) { /* ignore */ } });
      if (window.SQ.charts) SQ.charts.disposeAll(view);
      for (const id of Array.from(live.regs.keys())) if (id !== 'sidebar') live.unregister(id);
      view.innerHTML = '';
      $('#main').scrollTop = 0;
    }
    $$('#nav a, #bnav a').forEach((a) => a.classList.toggle('on', a.dataset.r === name));
    const fn = SQ.views[name === 't' ? 'ticker' : name];
    current = { name, sym: (parts[1] || '').toUpperCase() };
    if (!fn) { view.innerHTML = '<div class="empty">Page not found.</div>'; return; }
    try {
      await fn(view, parts.slice(1), params, same);
    } catch (e) {
      console.error(e);
      view.appendChild(SQ.ui.error(e));
    }
    live.tick(true);
  }
  SQ.render = render;
  window.addEventListener('hashchange', render);

  // ─── UI components ────────────────────────────────────────────────────
  const ui = {};
  SQ.ui = ui;
  ui.skeleton = (height = 160) => h('div', { class: 'skel', style: { height: height + 'px' } });
  ui.error = (err, retry) => h('div', { class: 'err' }, h('b', null, 'Could not load. '), String(err && err.message ? err.message : err),
    retry ? h('span', null, ' ', h('a', { href: '#', onclick: (e) => { e.preventDefault(); retry(); } }, 'Try again')) : null);
  ui.empty = (msg) => h('div', { class: 'empty' }, msg);
  ui.toast = (msg, ms = 3200) => {
    const t = h('div', { class: 'toast', role: 'status' }, msg);
    document.body.appendChild(t);
    setTimeout(() => t.remove(), ms);
  };
  ui.panel = (title, body, opts = {}) => h('section', { class: 'panel ' + (opts.cls || '') },
    title || opts.right ? h('div', { class: 'ph' }, title ? h('h3', null, title) : null, opts.sub ? h('span', { class: 'dim', style: { fontSize: '12.5px' } }, opts.sub) : null,
      opts.right ? h('div', { class: 'r' }, opts.right) : null) : null,
    h('div', { class: 'pb' }, body),
    opts.cap ? h('div', { class: 'cap', html: opts.cap }) : null);
  ui.sec = (title) => h('h2', { class: 'sec' }, title);
  ui.kpis = (items) => h('div', { class: 'kpis' }, items.filter(Boolean).map((k) => h('div', { class: 'kpi', title: k.title || '' },
    h('div', { class: 'label' }, k.label), h('div', { class: 'v ' + (k.cls || '') , html: k.html || null }, k.html ? null : k.value),
    k.sub ? h('div', { class: 'd', html: k.subHtml ? k.sub : null }, k.subHtml ? null : k.sub) : null)));
  ui.kv = (pairs) => h('div', { class: 'kv' }, pairs.filter(Boolean).map(([k, v, cls, title]) =>
    h('div', { title: title || '' }, h('span', null, k), h('span', { class: cls || '' }, v))));
  ui.seg = (options, value, onChange) => {
    const el = h('div', { class: 'seg', role: 'tablist' });
    options.forEach((o) => {
      const [val, label] = Array.isArray(o) ? o : [o, o];
      el.appendChild(h('button', { class: val === value ? 'on' : '', type: 'button', onclick: () => {
        $$('button', el).forEach((b) => b.classList.remove('on'));
        el.children[options.indexOf(o)].classList.add('on');
        onChange(val);
      } }, label));
    });
    return el;
  };
  ui.select = (options, value, onChange, attrs = {}) => {
    const s = h('select', { class: 'inp', ...attrs, onchange: (e) => onChange(e.target.value) });
    options.forEach((o) => {
      const [val, label] = Array.isArray(o) ? o : [o, o];
      s.appendChild(h('option', { value: val, selected: String(val) === String(value) }, label));
    });
    return s;
  };
  ui.chip = (text, cls = '') => h('span', { class: 'chip ' + cls }, text);
  ui.ring = (score) => {
    const c = !fmt.ok(score) ? 'var(--ink-4)' : score >= 67 ? 'var(--up)' : score >= 40 ? 'var(--warn)' : 'var(--down)';
    return h('div', { class: 'ring', style: { '--p': fmt.ok(score) ? score : 0, '--c': c } }, h('b', null, fmt.ok(score) ? Math.round(score) : DASH));
  };
  ui.spark = (vals, w = 64, hgt = 24) => {
    const v = (vals || []).filter(fmt.ok);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${w} ${hgt}`);
    svg.setAttribute('class', 'spark');
    svg.setAttribute('aria-hidden', 'true');
    if (v.length < 2) return svg;
    const mn = Math.min(...v), mx = Math.max(...v), r = mx - mn || 1;
    const d = v.map((y, i) => `${i ? 'L' : 'M'}${(i / (v.length - 1) * w).toFixed(1)},${(hgt - 2 - (y - mn) / r * (hgt - 4)).toFixed(1)}`).join('');
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', d);
    p.setAttribute('fill', 'none');
    p.setAttribute('stroke', v[v.length - 1] >= v[0] ? 'var(--up)' : 'var(--down)');
    p.setAttribute('stroke-width', '1.4');
    svg.appendChild(p);
    return svg;
  };
  ui.heat = (x, scale = 0.05) => {
    if (!fmt.ok(x)) return '';
    const a = Math.min(1, Math.abs(x) / scale) * 0.32;
    return x >= 0 ? `rgba(var(--up-rgb),${a.toFixed(3)})` : `rgba(var(--down-rgb),${a.toFixed(3)})`;
  };

  // Async section: skeleton -> render(data) or error with retry.
  ui.async = (container, loader, renderFn, skelH = 180) => {
    const run = async () => {
      container.innerHTML = '';
      container.appendChild(ui.skeleton(skelH));
      try {
        const data = await loader();
        container.innerHTML = '';
        await renderFn(container, data);
      } catch (e) {
        console.error(e);
        container.innerHTML = '';
        container.appendChild(ui.error(e, run));
      }
    };
    run();
    return run;
  };

  // CSV download of rows/columns.
  ui.csv = (rows, cols, name = 'export.csv') => {
    const q = (v) => {
      const s = v == null ? '' : String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const lines = [cols.map((c) => q(c.label || c.key)).join(',')]
      .concat(rows.map((r) => cols.map((c) => q(typeof c.get === 'function' ? c.get(r) : r[c.key])).join(',')));
    ui.saveBlob(new Blob([lines.join('\n')], { type: 'text/csv' }), name);
  };
  ui.saveBlob = (blob, name) => {
    const a = h('a', { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  };
  ui.download = (url) => {
    if (SNAP || STATIC) { ui.toast(STATIC ? SQ.LOCAL_ONLY : 'Downloads need the local tool (this is a snapshot).', 5000); return; }
    const a = h('a', { href: url, download: '' }); document.body.appendChild(a); a.click(); a.remove();
  };

  // Sortable table. cols: {key, label, fmt, d, cls(row), heat(scale), l (left), get(row), render(row), title, nosort}
  ui.table = (cols, rows, opts = {}) => {
    let sortKey = opts.sort || null, desc = opts.desc !== false;
    const wrap = h('div', { class: 'tw' + (opts.max ? ' max' : '') });
    const csvBtn = opts.csv ? h('button', { class: 'btn sm', type: 'button', title: 'Download as CSV', onclick: () => ui.csv(sorted(), cols, opts.csv) },
      h('span', { html: '<svg viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14"/></svg>' }), 'CSV') : null;
    const val = (r, c) => (typeof c.get === 'function' ? c.get(r) : r[c.key]);
    function sorted() {
      if (!sortKey) return rows.slice();
      const c = cols.find((x) => x.key === sortKey) || {};
      return rows.slice().sort((a, b) => {
        const va = val(a, c), vb = val(b, c);
        const na = va == null || (typeof va === 'number' && !isFinite(va)), nb = vb == null || (typeof vb === 'number' && !isFinite(vb));
        if (na && nb) return 0; if (na) return 1; if (nb) return -1;
        const r = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb));
        return desc ? -r : r;
      });
    }
    function draw() {
      const t = h('table', { class: 't' });
      const tr = h('tr');
      cols.forEach((c) => {
        const th = h('th', { class: (c.l ? 'l ' : '') + (c.nosort ? '' : 'sortable ') + (sortKey === c.key ? 'sorted' : ''), title: c.title || '' },
          c.label + (sortKey === c.key ? (desc ? ' ↓' : ' ↑') : ''));
        if (!c.nosort) th.addEventListener('click', () => { if (sortKey === c.key) desc = !desc; else { sortKey = c.key; desc = !c.l; } draw(); });
        tr.appendChild(th);
      });
      t.appendChild(h('thead', null, tr));
      const tb = h('tbody');
      const list = sorted();
      (opts.limit ? list.slice(0, opts.limit) : list).forEach((r) => {
        const row = h('tr', { class: (opts.onRow ? 'click ' : '') + (opts.rowClass ? opts.rowClass(r) || '' : '') });
        if (opts.onRow) row.addEventListener('click', () => opts.onRow(r));
        cols.forEach((c) => {
          const v = val(r, c);
          const td = h('td', { class: (c.l ? 'l ' : '') + (c.txt ? 'txt ' : '') + (typeof c.cls === 'function' ? c.cls(v, r) || '' : c.cls || '') });
          if (c.render) { const out = c.render(r, v); if (out instanceof Node) td.appendChild(out); else td.innerHTML = out == null ? DASH : out; }
          else td.textContent = fmt.any(v, c.fmt, c.d);
          if (c.heat && fmt.ok(v)) td.style.background = ui.heat(v, c.heat);
          if (c.sign && fmt.ok(v) && fmt.cls(v)) td.classList.add(fmt.cls(v));
          row.appendChild(td);
        });
        tb.appendChild(row);
      });
      t.appendChild(tb);
      wrap.innerHTML = '';
      wrap.appendChild(t);
      if (!list.length) wrap.appendChild(ui.empty(opts.emptyText || 'No rows.'));
    }
    draw();
    const box = h('div', null, csvBtn || opts.tools ? h('div', { class: 't-tools' }, opts.tools || null, csvBtn) : null, wrap);
    box.redraw = (newRows) => { rows = newRows; draw(); };
    return box;
  };

  // Tiny helper for a labelled live price + change (used in headers & lists).
  ui.livePrice = (sym, q, big) => h('span', { class: 'nowrap' },
    h('span', { class: big ? 'px' : 'mono', dataset: { live: sym + ':price:price', v: q && q.price } }, fmt.price(q && q.price)), ' ',
    h('span', { class: 'mono ' + fmt.cls(q && q.change_pct), dataset: { live: sym + ':change_pct:pct', sign: 'change_pct' } }, fmt.pct(q && q.change_pct, 2)));
})();
