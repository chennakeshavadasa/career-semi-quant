/* World risk: wars and flashpoints, the straits and canals ships pass through, the markets that react, and what
 * it means for chip supply.
 * Data: /api/world (ship counts per strait from IMF PortWatch, its event log, markets, chip-supply exposure),
 * /api/world/chokepoint/<id> (daily series for one strait) and /api/world/news?theatre=<id> (GDELT headlines and
 * coverage trend for one flashpoint). */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts, esc } = SQ;
  const sec = ui.sec;
  const enc = encodeURIComponent;

  const STATUS = { severe: ['Severe', 'down'], disrupted: ['Disrupted', 'down'], watch: ['Below normal', 'warn'], surge: ['Above normal', 'acc'], normal: ['Normal', ''], low: ['Little traffic', ''] };
  const RANK = { severe: 4, disrupted: 3, watch: 2, surge: 1, normal: 0, low: -1 };
  const TYPE_NAME = { tanker: 'Tankers', container: 'Containers', dry_bulk: 'Dry bulk', other: 'Other cargo' };
  const LEVEL = { alert: ['Disrupted now', 'down'], watch: ['Watch', 'warn'], calm: ['Calm', ''] };
  const ALERT = { RED: 'down', ORANGE: 'warn', GREEN: 'up' };

  const statusChip = (s) => ui.chip((STATUS[s] || [s])[0], (STATUS[s] || [])[1] || '');
  const ships = (v) => (v == null ? '–' : v >= 10 ? fmt.int(v) : fmt.num(v, 1));
  const since = (r) => (r.since ? (r.since_source === 'estimate' ? 'about ' : '') + fmt.date(r.since) : '');
  const canLink = (sym) => !SQ.static || SQ.isPublished(sym);
  const symLink = (sym, text) => (canLink(sym) ? `<a href="#/t/${enc(sym)}">${esc(text)}</a>` : esc(text));
  // News requests are slow on the local edition (GDELT allows one call per 5 seconds, so they queue on the server):
  // run only a couple at a time so they do not use up the browser's connections.
  const queue = [];
  let running = 0;
  function limited(fn) {
    return new Promise((resolve, reject) => {
      queue.push(() => fn().then(resolve, reject));
      pump();
    });
  }
  function pump() {
    const max = SQ.static ? 6 : 2;
    while (running < max && queue.length) {
      const job = queue.shift();
      running++;
      job().finally(() => { running--; pump(); });
    }
  }
  const scrollTo = (el) => { if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); };

  // A strait or canal named inside a sentence: a chip that selects it in the detail panel.
  const pickChip = (r, pick) => h('button', { class: 'chip pick ' + ((STATUS[r.status] || [])[1] || ''), type: 'button', title: 'Show ' + r.name + ' in detail', onclick: () => pick(r.id) },
    r.name, h('span', { class: 'dim' }, ' · ' + (STATUS[r.status] || [r.status])[0].toLowerCase()));

  function move(m) {
    const v = m.chg5d;
    return h('span', { class: 'chip', title: m.label + ': ' + fmt.pct(v, 1) + ' over 5 trading days' },
      m.label.replace(/ \(.*\)$/, ''), ' ', h('b', { class: fmt.ok(v) && Math.abs(v) >= 0.01 ? fmt.cls(v) : 'dim' }, fmt.pct(v, 1)));
  }

  // ─── Top: what is broken right now ────────────────────────────────────
  function banner(d, pick) {
    const bad = d.chokepoints.filter((r) => r.status === 'severe' || r.status === 'disrupted');
    if (!bad.length) {
      return h('div', { class: 'flags' }, h('div', { class: 'flag green' }, h('div', { class: 'ft' }, 'No strait or canal is severely disrupted right now.'),
        h('div', { class: 'fd' }, `${d.summary.tracked} chokepoints are tracked from daily ship counts. ${d.summary.counts.watch || 0} are below their normal traffic.`)));
    }
    return h('div', { class: 'flags' }, bad.map((r) => {
      const tt = Object.entries(r.types || {}).filter(([, v]) => v.chg != null && v.base >= 2).sort((a, b) => a[1].chg - b[1].chg).slice(0, 3)
        .map(([k, v]) => `${(TYPE_NAME[k] || k).toLowerCase()} ${fmt.pct(v.chg, 0)}`).join(', ');
      return h('div', { class: 'flag red click', role: 'button', tabindex: '0', onclick: () => pick(r.id), onkeydown: (e) => { if (e.key === 'Enter') pick(r.id); } },
        h('div', { class: 'ft' }, h('span', { class: 'new-badge wbadge' }, r.status === 'severe' ? 'SEVERE' : 'DISRUPTED'),
          `${r.name}: ${ships(r.avg7)} ships a day against about ${ships(r.base)} normally (${fmt.pct(r.chg, 0)})`),
        h('div', { class: 'fd' }, [tt ? 'By type: ' + tt + '. ' : '', r.carries].filter(Boolean).join('')),
        h('div', { class: 'fm' }, r.since ? `${r.days != null ? r.days + ' days, ' : ''}since ${since(r)} · ` : '', 'tap for the chart and what it affects'));
    }));
  }

  function kpis(d) {
    const s = d.summary, c = s.counts || {}, bad = (c.severe || 0) + (c.disrupted || 0);
    return ui.kpis([
      { label: 'Straits disrupted', value: `${bad} of ${s.tracked}`, cls: bad ? 'down' : '', sub: `${c.watch || 0} more below normal · ${c.surge || 0} above`, title: 'Of the 28 straits and canals tracked by IMF PortWatch from ship signals' },
      { label: 'Cargo capacity missing', value: fmt.ok(s.missing_capacity) ? fmt.pctu(s.missing_capacity, 1) : '–', cls: s.missing_capacity > 0.03 ? 'down' : '', sub: 'of all tracked strait traffic, by estimated tonnage', title: 'Estimated cargo carried through the tracked straits compared with normal, summed over those below normal. Oil and gas are worth more per ton than the share suggests.' },
      s.longest ? { label: 'Longest disruption', value: `${s.longest.days} days`, cls: 'down', sub: `${s.longest.name} since ${fmt.date(s.longest.since)}` } : { label: 'Longest disruption', value: 'None', sub: 'no severe closure' },
      { label: 'Markets stressed', value: fmt.int(s.markets_stressed), cls: s.markets_stressed ? 'warn' : '', sub: 'oil, gas, freight, havens: 5-day move above 2 standard deviations' },
      { label: 'Ship data through', value: fmt.date((d.sources.portwatch || {}).last_date), sub: 'PortWatch updates weekly' },
    ]);
  }

  // ─── Straits and canals ───────────────────────────────────────────────
  function straitsSection(d, state, pick) {
    const box = h('div');
    const need = (r) => ['severe', 'disrupted', 'watch', 'surge'].includes(r.status);
    const hasNeed = d.chokepoints.some(need);
    let mode = hasNeed ? 'issues' : 'all';
    const rows = () => (mode === 'issues' ? d.chokepoints.filter(need) : d.chokepoints);
    const tbl = ui.table([
      { key: 'status', label: 'Strait or canal', l: true, get: (r) => RANK[r.status], title: 'Sorted by severity', render: (r) => h('div', { class: 'wname' }, h('b', null, r.name), statusChip(r.status)) },
      { key: 'chg', label: 'vs normal', fmt: 'pct', d: 0, heat: 0.5, sign: true, title: 'Blend of the last 7 and 28 days, against the more cautious of the 3-year level and the same weeks of earlier years' },
      { key: 'avg7', label: 'Ships/day', render: (r) => ships(r.avg7), title: 'Average of the last 7 days' },
      { key: 'base', label: 'Normal', render: (r) => ships(r.base), title: 'Median weekly traffic over the last three years' },
      { key: 'yoy', label: 'Year on year', fmt: 'pct', d: 0, sign: true },
      { key: 'since', label: 'Since', l: true, render: (r) => (r.since ? since(r) : '') },
      { key: 'weekly', label: 'Last 52 weeks', nosort: true, render: (r) => ui.spark(r.weekly, 90, 24) },
    ], rows(), { sort: 'status', onRow: (r) => pick(r.id), rowClass: (r) => (r.id === state.sel ? 'self' : '') });
    state.table = { box: tbl, rows };
    const seg = ui.seg([['issues', 'Needs attention'], ['all', `All ${d.chokepoints.length}`]], mode, (v) => { mode = v; tbl.redraw(rows()); });
    box.appendChild(h('div', { class: 't-tools', style: { marginBottom: '8px' } }, seg));
    box.appendChild(ui.panel(null, tbl, { cap: `Ships per day through each strait or canal, counted from satellite ship signals by <a href="https://portwatch.imf.org" target="_blank" rel="noopener">IMF PortWatch</a>. "Normal" is the 3-year median; a strait is only flagged when it is low against that <i>and</i> against the same weeks of earlier years, so seasonal swings do not trigger it. Tap a row for the chart.` }));
    return box;
  }

  function detailPanel(d, state) {
    const box = h('div', { id: 'w-detail', style: { scrollMarginTop: '72px' } });
    state.detail = box;
    return box;
  }

  async function showDetail(d, state, id, pick) {
    const r = d.chokepoints.find((x) => x.id === id);
    const box = state.detail;
    if (!r || !box) return;
    state.sel = id;
    if (state.table) state.table.box.redraw(state.table.rows());
    box.innerHTML = '';
    const head = h('div', { class: 'page-h', style: { marginTop: '18px', marginBottom: '10px' } }, h('div', null, h('h2', { class: 'sec', style: { margin: 0 } }, r.name),
      h('div', { class: 'sub' }, r.role)), h('div', { class: 'actions' }, statusChip(r.status)));
    box.appendChild(head);
    box.appendChild(ui.kpis([
      { label: 'Ships per day (7-day avg)', value: ships(r.avg7), cls: STATUS[r.status][1], sub: `normal about ${ships(r.base)}` },
      { label: 'Against normal', value: fmt.pct(r.chg, 0), cls: fmt.cls(r.chg) },
      { label: 'Year on year', value: fmt.pct(r.yoy, 0), cls: fmt.cls(r.yoy) },
      { label: r.since && r.days != null ? 'Duration' : 'Share of tracked cargo', value: r.since && r.days != null ? `${r.days} days` : fmt.pctu(r.share, 1), sub: r.since ? 'since ' + since(r) : 'normal traffic, by tonnage' },
    ]));
    const chartEl = charts.div('chart tall');
    const types = Object.entries(r.types || {}).filter(([, v]) => v.base >= 0.5);
    const linkedT = (r.theatres || []).map((tid) => (d.theatres.find((t) => t.id === tid))).filter(Boolean);
    const linkedA = (r.assets || []).map((s) => d.markets.find((m) => m.symbol === s)).filter(Boolean);
    box.appendChild(h('div', { class: 'wsplit' },
      ui.panel('Ships per day', chartEl, { cap: 'Daily count, its 7-day average and the normal level. The dashed vertical line marks when the current disruption started.' }),
      h('div', { class: 'grid' },
        ui.panel('What it carries', h('div', null, h('p', { class: 'note', style: { margin: '0 0 8px' } }, r.carries || '–'),
          h('p', { class: 'note', style: { margin: 0 } }, h('b', null, 'If it closes: '), r.if_closed || '–'))),
        types.length ? ui.panel('By ship type', ui.table([
          { key: 'k', label: 'Type', l: true, render: (x) => esc(TYPE_NAME[x.k] || x.k) }, { key: 'avg7', label: 'Now', render: (x) => ships(x.avg7) },
          { key: 'base', label: 'Normal', render: (x) => ships(x.base) }, { key: 'chg', label: 'Change', fmt: 'pct', d: 0, sign: true, heat: 0.5 },
        ], types.map(([k, v]) => ({ k, ...v })), { sort: null })) : null,
        linkedT.length || linkedA.length ? ui.panel('What to watch with it', h('div', null,
          linkedT.length ? h('div', { class: 'chips', style: { marginBottom: '8px' } }, linkedT.map((t) => h('button', { class: 'chip pick', type: 'button', onclick: () => scrollTo(document.getElementById('th-' + t.id)) }, t.name))) : null,
          linkedA.length ? h('div', { class: 'chips' }, linkedA.map(move)) : null)) : null)));
    ui.async(chartEl, () => api(`/api/world/chokepoint/${enc(id)}`), (c, s) => {
      if (s.unavailable) { c.appendChild(ui.empty(s.message)); return; }
      const ma = s.total.map((_, i) => (i < 6 ? null : s.total.slice(i - 6, i + 1).reduce((a, b) => a + b, 0) / 7));
      const shapes = r.since ? [{ type: 'line', xref: 'x', x0: r.since, x1: r.since, yref: 'paper', y0: 0, y1: 1, line: { color: 'down', dash: 'dot', width: 1.4 } }] : [];
      charts.lines(c, [
        { name: 'Daily', t: s.dates, v: s.total, color: 'ink4', width: 1, opacity: 0.55 },
        { name: '7-day average', t: s.dates, v: ma, color: 'accent', width: 2.4 },
        { name: 'Normal', t: s.dates, v: s.dates.map(() => s.base), color: 'ink3', width: 1.2, dash: 'dash' },
      ], { yfmt: ',.0f', zero: true, shapes });
    }, 300);
    if (state.scroll) scrollTo(box);
    state.scroll = false;
  }

  // ─── Flashpoints ──────────────────────────────────────────────────────
  function newsInto(box, badge, n) {
    box.innerHTML = '';
    if (n.unavailable || !n.headlines || !n.headlines.length) {
      const failed = n.unavailable || (n.errors || []).some((e) => /^headlines/.test(e));
      box.appendChild(h('div', { class: 'note dim', style: { margin: 0 } }, failed ? 'Headlines are being prepared; the news source did not answer at the last refresh.' : 'No recent headlines matched.'));
    } else {
      box.appendChild(h('ul', { class: 'wnews' }, n.headlines.slice(0, 4).map((a) => h('li', null,
        h('a', { href: a.url, target: '_blank', rel: 'noopener' }, a.title), h('span', { class: 'wmeta' }, a.domain + (a.seen ? ' · ' + fmt.ago(a.seen) : ''))))));
    }
    const at = n.attention;
    badge.innerHTML = '';
    if (at && fmt.ok(at.ratio) && at.z >= 2 && at.ratio >= 1.3) badge.appendChild(ui.chip(`Coverage ${at.ratio.toFixed(1)}× its recent norm`, 'warn'));
    else if (at && fmt.ok(at.ratio) && at.z <= -1.5) badge.appendChild(ui.chip('Quieter than usual', ''));
  }

  function theatreCard(t, d, pick) {
    const by = Object.fromEntries(d.chokepoints.map((r) => [r.id, r]));
    const badge = h('span');
    const newsBox = h('div', { class: 'wnewsbox' }, ui.skeleton(96));
    const straits = t.chokepoints.map((c) => by[c.id]).filter(Boolean);
    const mk = t.assets.map((s) => d.markets.find((m) => m.symbol === s)).filter(Boolean);
    limited(() => api(`/api/world/news?theatre=${enc(t.id)}`)).then((n) => newsInto(newsBox, badge, n || {}), () => newsInto(newsBox, badge, { unavailable: true }));
    return h('section', { class: 'panel wcard', id: 'th-' + t.id },
      h('div', { class: 'ph' }, h('h3', null, t.name), ui.chip(t.region), h('div', { class: 'wb' }, badge)),
      h('div', { class: 'pb' }, newsBox,
        h('div', { class: 'wsub' }, 'Can affect'), h('ul', { class: 'wlist' }, t.affects.map((a) => h('li', null, a))),
        straits.length ? h('div', { class: 'wsub' }, 'Straits it touches') : null,
        straits.length ? h('div', { class: 'chips' }, straits.map((r) => pickChip(r, pick))) : null,
        mk.length ? h('div', { class: 'wsub' }, 'Markets to watch (5 days)') : null,
        mk.length ? h('div', { class: 'chips' }, mk.map(move)) : null));
  }

  function theatresSection(d, pick) {
    const by = Object.fromEntries(d.chokepoints.map((r) => [r.id, r]));
    const worst = (t) => Math.max(-1, ...t.chokepoints.map((c) => (by[c.id] ? RANK[by[c.id].status] : -1)));
    const order = d.theatres.map((t, i) => [t, i]).sort((a, b) => worst(b[0]) - worst(a[0]) || a[1] - b[1]).map((x) => x[0]);
    return h('div', { class: 'wgrid' }, order.map((t) => theatreCard(t, d, pick)));
  }

  // ─── Event log ────────────────────────────────────────────────────────
  function eventsSection(d, pick) {
    const rows = d.events || [];
    if (!rows.length) return ui.panel(null, ui.empty('No events logged.'));
    return ui.panel(null, ui.table([
      { key: 'start', label: 'Started', fmt: 'date' },
      { key: 'type_label', label: 'Type', l: true, render: (r) => ui.chip(r.type_label, ALERT[r.alert] || '').outerHTML },
      { key: 'name', label: 'Event', l: true, txt: true },
      { key: 'end', label: 'Ended', l: true, render: (r) => (r.ongoing ? '<span class="down">ongoing</span>' : esc(fmt.date(r.end))) },
      { key: 'where', label: 'Where', l: true, txt: true, get: (r) => (r.chokepoints.length ? r.chokepoints.map((c) => c.name).join(', ') : r.countries.join(', ')) },
      { key: 'n_ports', label: 'Ports hit', fmt: 'int' },
    ], rows, { sort: 'start', onRow: (r) => { if (r.chokepoints.length) pick(r.chokepoints[0].id); }, rowClass: (r) => (r.ongoing ? 'flagged' : ''), max: true }),
    { cap: 'The event log kept by <a href="https://portwatch.imf.org" target="_blank" rel="noopener">IMF PortWatch</a>: storms, quakes, fires and trade disruptions that affect ports and straits. Closures such as Hormuz are logged with their start date and stay "ongoing" until PortWatch closes them.' });
  }

  // ─── Markets ──────────────────────────────────────────────────────────
  function marketsSection(d) {
    const groups = (d.asset_groups || []).map((g) => [g, d.markets.filter((m) => m.group === g)]).filter(([, r]) => r.length);
    if (!groups.length) return ui.panel(null, ui.empty('Prices are unavailable right now.'));
    return h('div', { class: 'grid g2' }, groups.map(([g, rows]) => ui.panel(g, ui.table([
      { key: 'label', label: 'Asset', l: true, render: (r) => symLink(r.symbol, r.label) },
      { key: 'chg1d', label: '1D', fmt: 'pct', d: 1, heat: 0.05, sign: true }, { key: 'chg5d', label: '5D', fmt: 'pct', d: 1, heat: 0.1, sign: true },
      { key: 'chg1m', label: '1M', fmt: 'pct', d: 1, heat: 0.2, sign: true },
      { key: 'z5', label: 'Stress', title: 'The last 5-day move in units of its usual 5-day swing over a year. Above 2 is unusual.', render: (r) => (r.z5 != null && Math.abs(r.z5) >= 2 ? `<span class="${r.z5 > 0 ? 'up' : 'down'}">${r.z5 > 0 ? '+' : '−'}${Math.abs(r.z5).toFixed(1)}σ</span>` : '<span class="dim">–</span>') },
      { key: 'spark', label: '', nosort: true, render: (r) => ui.spark(r.spark, 64, 22) },
    ], rows, { sort: null }))));
  }

  // ─── Chip supply ──────────────────────────────────────────────────────
  function semisSection(d, pick) {
    const by = Object.fromEntries(d.chokepoints.map((r) => [r.id, r]));
    return h('div', { class: 'wgrid' }, (d.semis || []).map((x) => h('section', { class: 'panel wcard' },
      h('div', { class: 'ph' }, h('h3', null, x.label), h('div', { class: 'wb' }, ui.chip(LEVEL[x.level][0], LEVEL[x.level][1]))),
      h('div', { class: 'pb' }, h('p', { class: 'note', style: { margin: '0 0 8px' } }, x.why),
        x.signals.length ? h('div', { class: 'chips', style: { marginBottom: '8px' } }, x.signals.map((s) => (s.kind === 'chokepoint' && by[s.id]
          ? pickChip(by[s.id], pick)
          : h('button', { class: 'chip pick', type: 'button', onclick: () => scrollTo(document.getElementById('th-' + s.id)) }, s.name)))) : null,
        x.tickers.length ? h('div', { class: 'wtick' }, x.tickers.map((t) => h(canLink(t.symbol) ? 'a' : 'span', { class: 'chip tk', href: canLink(t.symbol) ? '#/t/' + enc(t.symbol) : null, title: t.name },
          t.symbol, ' ', h('span', { class: fmt.cls(t.change_pct) }, fmt.pct(t.change_pct, 1))))) : null))));
  }

  // ─── The page ─────────────────────────────────────────────────────────
  SQ.views.world = async function (view, parts, params) {
    view.appendChild(h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'World risk'),
      h('div', { class: 'sub' }, 'Wars and flashpoints, the straits ships pass through, and what they can hit: oil and gas, shipping, chip supply. Live ship counts, news and prices.'))));
    const box = h('div', { class: 'world' });
    view.appendChild(box);
    ui.async(box, () => api('/api/world'), (b, d) => {
      if (d && d.unavailable) { b.appendChild(ui.empty(d.message)); return; }
      const state = { sel: null, scroll: false };
      const pick = (id) => { state.scroll = true; showDetail(d, state, id, pick); };
      if (d.chokepoints.length) {
        b.appendChild(banner(d, pick));
        b.appendChild(h('div', { style: { height: '12px' } }));
        b.appendChild(kpis(d));
        b.appendChild(sec('Straits and canals'));
        b.appendChild(straitsSection(d, state, pick));
        b.appendChild(detailPanel(d, state));
        const first = params.s && d.chokepoints.find((r) => r.id === params.s) ? params.s : (d.chokepoints[0] || {}).id;
        if (first) showDetail(d, state, first, pick);
      } else {
        b.appendChild(ui.empty('Ship counts are unavailable right now (the IMF PortWatch service did not answer).'));
      }
      b.appendChild(sec('Flashpoints'));
      b.appendChild(h('p', { class: 'note' }, 'Conflicts and tensions, newest English-language headlines from ', h('a', { href: 'https://www.gdeltproject.org', target: '_blank', rel: 'noopener' }, 'GDELT'),
        ', and what each can affect. The "can affect" lists are curated judgement, not data; the headlines and the markets are live. Straits that are disrupted come first.'));
      b.appendChild(theatresSection(d, pick));
      b.appendChild(sec('Events logged by PortWatch'));
      b.appendChild(eventsSection(d, pick));
      b.appendChild(sec('Markets reacting'));
      b.appendChild(marketsSection(d));
      b.appendChild(sec('What it means for chip supply'));
      b.appendChild(h('p', { class: 'note' }, 'Where semiconductor supply depends on a strait or a region, with the live signals above. Shares are approximate public figures and the links are curated; they show exposure, not a forecast.'));
      b.appendChild(semisSection(d, pick));
      b.appendChild(h('p', { class: 'note', style: { marginTop: '18px' } }, h('b', null, 'How to read this. '),
        'Ship counts come from satellite ship signals (AIS) and lag by about a week; ships that switch the signal off are not counted. A status needs the traffic to be low against both its 3-year level and the same weeks of earlier years. News volume measures attention, not severity. ',
        `Sources: IMF PortWatch (CC BY 4.0), GDELT Project, Yahoo Finance. Built ${fmt.dateTime(d.as_of)}.`));
      if ((d.errors || []).length) b.appendChild(h('p', { class: 'note dim' }, 'Some sources did not answer at the last refresh: ' + d.errors.map((e) => e.split(':')[0]).join(', ') + '.'));
    }, 520);
  };
})();
