/* Real-time prices from Yahoo Finance's streaming feed, straight from the browser (no server).
 * One WebSocket (wss://streamer.finance.yahoo.com) carries every symbol on screen; each message
 * is a base64 protobuf (PricingData, the schema yfinance ships as pricing.proto). Ticks patch
 * SQ.live.quotes and the page updates in place about once a second. Quote polling stays on as
 * the backstop and supplies every field the stream does not carry.
 * Used by the local edition and the web edition / phone app alike; off in shared snapshots and
 * under Settings. The connection closes while the page is hidden (phone locked, app in the
 * background) and reopens when it is shown again. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { fmt } = SQ;
  const URL_ = 'wss://streamer.finance.yahoo.com/?version=2';
  const FLUSH_MS = 1000;           // repaint at most once a second
  const FRESH_MS = 90000;          // "live" while a tick arrived within this window
  const TAPE_MINUTES = 180;        // 1-minute bars kept per symbol (bridges charts published earlier)
  const MOBILE = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  const MAX_SYMBOLS = MOBILE ? 120 : 400;
  // Subscription priority when there are more symbols than MAX_SYMBOLS.
  const PRIORITY = ['ticker', 'wlpage', 'sidebar', 'market-strip', 'market-heat', 'screener'];
  // PricingData.market_hours: 0 pre-market, 1 regular, 2 after hours, 3 extended, 4 overnight.
  const EXT_LABEL = { 0: 'Pre-market', 2: 'After hours', 3: 'Extended hours', 4: 'Overnight' };
  const US_EXCHANGES = new Set(['NMS', 'NGM', 'NCM', 'NAS', 'NYQ', 'NYS', 'ASE', 'PCX', 'BTS', 'BATS', 'PNK', 'OQB', 'OQX', 'OEM', 'CXI']);

  // ─── protobuf: PricingData (proto3, so zero values are simply absent) ──
  const FIELDS = {
    1: ['id', 's'], 2: ['price', 'f'], 3: ['time', 'z'], 4: ['currency', 's'], 5: ['exchange', 's'], 6: ['quote_type', 'v'],
    7: ['market_hours', 'v'], 8: ['change_percent', 'f'], 9: ['day_volume', 'z'], 10: ['day_high', 'f'], 11: ['day_low', 'f'],
    12: ['change', 'f'], 13: ['short_name', 's'], 15: ['open_price', 'f'], 16: ['previous_close', 'f'],
  };
  const utf8 = new TextDecoder();
  function decode(b64) {
    const bin = atob(b64), n = bin.length, u = new Uint8Array(n);
    for (let i = 0; i < n; i++) u[i] = bin.charCodeAt(i);
    const dv = new DataView(u.buffer), out = {};
    let p = 0;
    const varint = () => { // exact up to 2^53: epoch milliseconds and volumes fit
      let x = 0, m = 1, b;
      do {
        if (p >= n) throw new Error('truncated');
        b = u[p++]; x += (b & 0x7f) * m; m *= 128;
      } while (b & 0x80);
      return x;
    };
    while (p < n) {
      const key = varint(), wt = key % 8, spec = FIELDS[(key - wt) / 8];
      let v = null;
      if (wt === 0) {
        v = varint();
        if (spec && spec[1] === 'z') v = v % 2 ? -(v + 1) / 2 : v / 2; // zigzag (sint64)
      } else if (wt === 5) {
        if (p + 4 > n) throw new Error('truncated');
        v = Number(dv.getFloat32(p, true).toPrecision(7)); // float32 carries ~7 digits
        p += 4;
      } else if (wt === 1) {
        if (p + 8 > n) throw new Error('truncated');
        v = dv.getFloat64(p, true);
        p += 8;
      } else if (wt === 2) {
        const len = varint();
        if (p + len > n) throw new Error('truncated');
        if (spec && spec[1] === 's') v = utf8.decode(u.subarray(p, p + len));
        p += len;
      } else {
        throw new Error('unsupported wire type ' + wt);
      }
      if (spec) out[spec[0]] = v;
    }
    return out;
  }

  // ─── connection ────────────────────────────────────────────────────────
  const S = {
    ws: null, subs: new Set(), retry: 0, opened: 0, timer: null, idle: null, hide: null, syncT: null,
    pending: new Map(), flushT: null, last: 0, count: 0, ticks: {}, tape: {},
  };
  const enabled = () => !SQ.snapshot && SQ.settings.stream !== false && typeof WebSocket === 'function';
  const isOpen = () => !!(S.ws && S.ws.readyState === 1);

  function wanted() {
    const live = SQ.live, ids = Array.from(live.regs.keys());
    ids.sort((a, b) => (PRIORITY.indexOf(a) + 1 || 99) - (PRIORITY.indexOf(b) + 1 || 99));
    const out = new Set();
    for (const id of ids) {
      for (const s of live.regs.get(id)) {
        if (out.size >= MAX_SYMBOLS) return out;
        out.add(s);
      }
    }
    return out;
  }
  const send = (msg) => { try { S.ws.send(JSON.stringify(msg)); } catch (e) { /* the close handler reconnects */ } };

  function sync() {
    clearTimeout(S.syncT); S.syncT = null;
    if (!enabled() || document.hidden) { close(); return; }
    const want = wanted();
    if (!want.size) { // nothing on screen: let the connection go after a minute
      if (S.ws && !S.idle) S.idle = setTimeout(close, 60000);
      return;
    }
    clearTimeout(S.idle); S.idle = null;
    if (!S.ws) { connect(); return; }
    if (!isOpen()) return; // onopen syncs
    const add = Array.from(want).filter((s) => !S.subs.has(s));
    const del = Array.from(S.subs).filter((s) => !want.has(s));
    if (add.length) send({ subscribe: add });
    if (del.length) send({ unsubscribe: del });
    S.subs = want;
    status();
  }
  function schedule() { if (!S.syncT) S.syncT = setTimeout(sync, 250); }

  function connect() {
    clearTimeout(S.timer);
    let ws;
    try { ws = new WebSocket(URL_); } catch (e) { retry(); return; }
    S.ws = ws; S.subs = new Set();
    ws.onopen = () => { if (S.ws === ws) { S.opened = Date.now(); sync(); } };
    ws.onmessage = (ev) => { if (S.ws === ws) onMessage(ev.data); };
    ws.onclose = () => { if (S.ws === ws) { S.ws = null; S.subs = new Set(); status(); retry(); } };
  }
  function retry() {
    clearTimeout(S.timer);
    if (!enabled() || document.hidden) return;
    if (S.opened && Date.now() - S.opened > 60000) S.retry = 0; // it had been working: retry soon
    S.opened = 0;
    const wait = Math.min(60000, 1000 * 2 ** Math.min(S.retry++, 6)) * (0.7 + 0.6 * Math.random());
    S.timer = setTimeout(sync, wait);
  }
  function close() {
    clearTimeout(S.timer); clearTimeout(S.idle); S.idle = null;
    const ws = S.ws;
    S.ws = null; S.subs = new Set();
    if (ws) { ws.onclose = null; try { ws.close(); } catch (e) { /* already closed */ } }
    status();
  }

  // ─── ticks ─────────────────────────────────────────────────────────────
  function onMessage(data) {
    if (typeof data !== 'string') return;
    let b64 = data;
    if (data.charCodeAt(0) === 123) { // version 2: {"type":"pricing","message":"<base64>"}
      let j;
      try { j = JSON.parse(data); } catch (e) { return; }
      if (!j || typeof j.message !== 'string' || (j.type && j.type !== 'pricing')) return;
      b64 = j.message;
    }
    let d;
    try { d = decode(b64); } catch (e) { return; }
    if (!d.id || !fmt.ok(d.price) || d.price <= 0) return;
    d.time = d.time || Date.now();
    d.market_hours = d.market_hours || 0;
    if (d.change == null) d.change = null; // absent = exactly zero, or not sent: derived below
    if (d.change_percent == null) d.change_percent = null;
    const sym = d.id.toUpperCase();
    d.kind = kindOf(SQ.live.quotes[sym] || {}, d);
    S.last = Date.now(); S.count++;
    record(sym, d);
    const prev = S.pending.get(sym);
    if (!prev || prev.time <= d.time) S.pending.set(sym, prev ? { ...prev, ...d } : d);
    if (!S.flushT) S.flushT = setTimeout(flush, FLUSH_MS);
  }

  // Extended-hours prints exist for US listings; elsewhere market_hours 0 is just "not sent".
  const usLike = (q, d) => (q.tz ? q.tz.startsWith('America/') && q.tz !== 'America/Toronto' : US_EXCHANGES.has(d.exchange));
  const kindOf = (q, d) => (d.market_hours === 1 ? 'regular' : d.market_hours === 4 ? 'overnight'
    : d.market_hours >= 2 || usLike(q, d) ? 'ext' : 'regular');

  function applyTick(q, d) {
    const p = d.price, t = d.time;
    if (kindOf(q, d) === 'regular') {
      const ref = fmt.ok(q.prev_close) ? q.prev_close : fmt.ok(d.previous_close) ? d.previous_close : null;
      q.price = p;
      q.change = d.change != null ? d.change : ref ? p - ref : 0;
      q.change_pct = d.change_percent != null ? d.change_percent / 100 : ref ? p / ref - 1 : 0;
      if (d.day_high) q.high = d.day_high; else if (fmt.ok(q.high) && p > q.high) q.high = p;
      if (d.day_low) q.low = d.day_low; else if (fmt.ok(q.low) && p < q.low) q.low = p;
      if (d.open_price && !fmt.ok(q.open)) q.open = d.open_price;
      if (d.day_volume) q.volume = d.day_volume;
      q.time = new Date(t).toISOString(); q.time_epoch = t / 1000;
      if (fmt.ok(q.high_52w) && fmt.ok(q.low_52w) && q.high_52w > q.low_52w) {
        q.pos_52w = (p - q.low_52w) / (q.high_52w - q.low_52w); q.pct_from_high = p / q.high_52w - 1;
      }
      q.market_state = 'REGULAR';
      if (q.ext_time && Date.parse(q.ext_time) < t) q.ext_price = q.ext_change = q.ext_change_pct = q.ext_label = q.ext_time = null;
    } else { // pre-market, after hours, overnight: measured from the last regular close (q.price)
      const ref = fmt.ok(q.price) ? q.price : null;
      q.ext_label = EXT_LABEL[d.market_hours] || 'Extended hours';
      q.ext_price = p;
      q.ext_change = d.change != null ? d.change : ref ? p - ref : null;
      q.ext_change_pct = d.change_percent != null ? d.change_percent / 100 : ref ? p / ref - 1 : null;
      q.ext_time = new Date(t).toISOString();
      if (d.market_hours === 0) q.market_state = 'PRE';
      else if (d.market_hours === 2) q.market_state = 'POST';
    }
    q.stream_time = t;
  }

  function record(sym, d) {
    const k = d.kind === 'regular' ? 0 : d.kind === 'overnight' ? 2 : 1;
    const m = Math.floor(d.time / 60000), p = d.price;
    const a = S.tape[sym] || (S.tape[sym] = []);
    const b = a[a.length - 1];
    if (b && b[0] === m && b[5] === k) {
      if (p > b[2]) b[2] = p;
      if (p < b[3]) b[3] = p;
      b[4] = p;
    } else if (!b || m >= b[0]) {
      a.push([m, p, p, p, p, k]);
      if (a.length > TAPE_MINUTES + 30) a.splice(0, a.length - TAPE_MINUTES);
    }
  }

  function flush() {
    S.flushT = null;
    if (!S.pending.size) return;
    const live = SQ.live, changed = {};
    for (const [sym, d] of S.pending) {
      const q = live.quotes[sym] || (live.quotes[sym] = { symbol: sym, name: d.short_name || sym, currency: d.currency });
      const kept = S.ticks[sym] || (S.ticks[sym] = {});
      if (kindOf(q, d) === 'regular') kept.reg = d; else kept.ext = d;
      applyTick(q, d);
      changed[sym] = q;
    }
    S.pending.clear();
    live.apply(document, new Set(Object.keys(changed)));
    live.emit(changed);
    status();
  }

  // Polled quotes replace the quote objects: re-apply ticks that are newer than what the poll returned.
  function reapply(qs) {
    for (const [sym, q] of Object.entries(qs || {})) {
      const k = S.ticks[sym];
      if (!k || !q) continue;
      const regT = (q.time_epoch || 0) * 1000;
      if (k.reg && k.reg.time > regT) applyTick(q, k.reg);
      const extT = q.ext_time ? Date.parse(q.ext_time) : 0;
      if (k.ext && k.ext.time > extT && k.ext.time > ((q.time_epoch || 0) * 1000)) applyTick(q, k.ext);
    }
  }

  // ─── status (top bar) ─────────────────────────────────────────────────
  const fresh = () => isOpen() && Date.now() - S.last < FRESH_MS;
  function status() {
    const b = SQ.$('#stream-badge');
    if (!b) return;
    const f = fresh();
    b.hidden = !isOpen();
    b.classList.toggle('on', f);
    b.title = f ? `Real-time prices from Yahoo Finance: ${S.subs.size} symbols streaming, last trade ${new Date(S.last).toLocaleTimeString()}`
      : 'Streaming connected. No trades in the last minute and a half (markets closed or quiet).';
    if (f) {
      const t = SQ.$('#live-time');
      if (t) t.textContent = '· ' + new Date(S.last).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
    }
  }
  setInterval(status, 15000);

  // ─── wiring ────────────────────────────────────────────────────────────
  const live = SQ.live;
  ['register', 'unregister'].forEach((k) => {
    const f = live[k].bind(live);
    live[k] = (...a) => { const r = f(...a); schedule(); return r; };
  });
  document.addEventListener('visibilitychange', () => {
    clearTimeout(S.hide);
    if (document.hidden) S.hide = setTimeout(close, 20000); // brief tab switches keep the connection
    else { S.retry = 0; sync(); }
  });
  window.addEventListener('online', () => { S.retry = 0; sync(); });
  window.addEventListener('pagehide', close);

  SQ.stream = {
    decode, reapply, sync, fresh,
    restart() { close(); S.retry = 0; sync(); },
    tape: (sym) => S.tape[String(sym || '').toUpperCase()] || [],
    info: () => ({ connected: isOpen(), enabled: enabled(), symbols: S.subs.size, ticks: S.count, last: S.last }),
  };
})();
