/* Who else is trading a stock: the "Insiders & Congress" ticker tab and the Congress trades page.
 * Data: /api/ticker/<sym>/smartmoney (highlights, Congress, Form 4 insiders, SEC Form 4/144/13D/13G filings,
 * funds holding 0.5%+) and /api/congress?days=30|90|365. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts, esc } = SQ;
  const T = SQ.tabs;
  const enc = encodeURIComponent;
  const sec = ui.sec;

  const money = (v) => (fmt.ok(v) ? fmt.money(v) : '–');
  const short = (v) => (v >= 1e6 ? `$${+(v / 1e6).toFixed(v % 1e6 > 1e5 && v < 1e7 ? 1 : 0)}M` : `$${Math.round(v / 1e3)}K`);
  const range = (lo, hi) => (lo == null ? '–' : hi ? `${short(lo)}–${short(hi)}` : `over ${short(lo - 1)}`);
  const SIDE = { buy: ['Buy', 'up'], sell: ['Sell', 'down'], sell_partial: ['Sell (part)', 'down'], exchange: ['Exchange', 'dim'] };
  const side = (t) => { const s = SIDE[t] || [t || '–', 'dim']; return `<span class="${s[1]}">${esc(s[0])}</span>`; };
  const who = (r) => `${esc(r.member || '')} <span class="dim">${esc([r.party, r.state].filter(Boolean).join('-'))}${r.chamber ? ' · ' + esc(String(r.chamber)[0] === 'S' ? 'Senate' : 'House') : ''}</span>`;
  const link = (url, text) => (url ? `<a href="${esc(url)}" target="_blank" rel="noopener"${/scan/.test(text || '') ? ' title="A paper report, scanned: read with OCR. Check the filing if a number matters."' : ''}>${esc(text || 'Filing')}</a>` : '–');
  const lag = (d) => (d == null ? '–' : `<span class="${d > 45 ? 'down' : 'dim'}" title="${d > 45 ? 'Later than the 45 days the law allows' : 'Days from trade to disclosure'}">${d}d${d > 45 ? ' late' : ''}</span>`);
  const BARGO = 'https://www.bargo.ai/free-apis/congress';
  // A trade read from the official filing, or one only Bargo's copy had (its licence asks for a visible credit link).
  const filing = (r) => (r.source === 'bargo'
    ? `<a href="${BARGO}" target="_blank" rel="noopener" title="Not found in our reading of the official filings; this trade comes from Bargo's free Congress API">via Bargo</a>`
    : link(r.url, r.ocr ? 'Filing (scan)' : 'Filing'));
  const bargoCredit = (st) => (st && st.checked ? h('p', { class: 'note', style: { margin: '0 0 10px' } },
    'Cross-checked with ', h('a', { href: BARGO, target: '_blank', rel: 'noopener' }, 'Bargo'),
    `'s free Congress API: ${st.matched} of its ${st.checked} latest trades were already here` +
    (st.added ? `; ${st.added} more ${st.added === 1 ? 'is' : 'are'} added from it, marked "via Bargo".` : '.')) : null);
  const ROLE = { top: ['Top executive', 'down'], owner: ['10%+ owner', 'warn'], director: ['Director', ''], officer: ['Officer', ''] };

  function flags(list) {
    if (!list.length) return ui.empty('Nothing notable: no planned sales, insider buying or selling streaks, activist stakes, committee-linked Congress trades or big fund moves.');
    return h('div', { class: 'flags' }, list.map((f) => h('div', { class: 'flag ' + f.level },
      h('div', { class: 'ft' }, f.new ? h('span', { class: 'new-badge', title: 'Public in the last 2 days' }, 'NEW') : null, f.title),
      h('div', { class: 'fd' }, f.detail),
      h('div', { class: 'fm' }, f.public ? 'Public since ' + fmt.date(f.public) : '', f.url ? [' · ', h('a', { href: f.url, target: '_blank', rel: 'noopener' }, 'source filing')] : null))));
  }

  // Price with every disclosed trade marked: Congress (triangles) and company insiders (circles), on the trade date.
  function tradeChart(el, closes, congress, insiders) {
    const t0 = new Date(Date.now() - 2 * 365 * 864e5).toISOString().slice(0, 10);
    const idx = closes.t.map((d, i) => [d, closes.c[i]]).filter(([d]) => d >= t0);
    const px = (d) => { let lo = 0, hi = idx.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (idx[m][0] <= d) { k = m; lo = m + 1; } else hi = m - 1; } return k >= 0 ? idx[k][1] : null; };
    const set = (rows, pick, name, symbol, color) => {
      const pts = rows.filter((r) => pick(r) && r.date >= t0 && px(r.date) != null);
      return { type: 'scatter', mode: 'markers', name, x: pts.map((r) => r.date), y: pts.map((r) => px(r.date)), text: pts.map((r) => r.label),
        hovertemplate: '%{text}<extra></extra>', marker: { symbol, size: pts.map((r) => r.size), color, line: { width: 1, color: '#000' }, opacity: 0.9 } };
    };
    const sz = (usd) => Math.max(8, Math.min(22, 4 + 2.2 * Math.log10(Math.max(usd || 1000, 1000))));
    const cg = congress.map((r) => ({ date: r.traded, s: r.side, size: sz(((r.amount_lo || 0) + (r.amount_hi || r.amount_lo || 0)) / 2),
      label: `${r.member} (${[r.party, r.state].filter(Boolean).join('-')}) ${r.side === 'buy' ? 'bought' : 'sold'} ${range(r.amount_lo, r.amount_hi)}<br>traded ${r.traded}, disclosed ${r.disclosed}` }));
    const ins = insiders.filter((r) => r.kind === 'buy' || r.kind === 'sell').map((r) => ({ date: r.date, s: r.kind, size: sz(r.value),
      label: `${r.insider} (${r.position || 'insider'}) ${r.kind === 'buy' ? 'bought' : 'sold'} ${money(r.value)}<br>${r.date}` }));
    charts.plot(el, (t) => ({
      data: [{ type: 'scatter', mode: 'lines', name: 'Price', x: idx.map((p) => p[0]), y: idx.map((p) => p[1]), line: { color: t.ink3, width: 1.4 }, hovertemplate: '%{x}<br>%{y:,.2f}<extra></extra>' },
        set(cg, (r) => r.s === 'buy', 'Congress buy', 'triangle-up', t.up), set(cg, (r) => r.s === 'sell', 'Congress sell', 'triangle-down', t.down),
        set(ins, (r) => r.s === 'buy', 'Insider buy', 'circle', t.up), set(ins, (r) => r.s === 'sell', 'Insider sell', 'circle-open', t.down)],
      layout: { hovermode: 'closest', showlegend: true, legend: { orientation: 'h', x: 0, y: 1.02, yanchor: 'bottom' }, xaxis: { type: 'date' }, yaxis: { tickformat: ',.0f' }, margin: { t: 40 } },
    }));
  }

  // ─── Ticker tab ───────────────────────────────────────────────────────
  T.smart = (body, sym) => {
    const box = h('div');
    body.appendChild(box);
    ui.async(box, () => api(`/api/ticker/${enc(sym)}/smartmoney`), (b, d) => {
      if (d && d.unavailable) { b.appendChild(ui.empty(d.message)); return; }
      const cg = d.congress || [], ins = d.insiders || [], s = d.sec || {}, funds = d.funds || [];
      const yr = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
      const c12 = cg.filter((r) => (r.disclosed || '') >= yr);
      const is6 = (d.insider_summary || {})['6M'] || {};
      const adds = funds.filter((f) => (f.change || 0) > 0.005).length, cuts = funds.filter((f) => (f.change || 0) < -0.005).length;
      if (cg.some((r) => r.source === 'bargo')) {
        b.appendChild(h('p', { class: 'note', style: { margin: '0 0 6px' } }, 'Some Congress trades below come from ',
          h('a', { href: BARGO, target: '_blank', rel: 'noopener' }, 'Bargo'), '\'s free Congress API (marked "via Bargo").'));
      }
      b.appendChild(h('p', { class: 'note' }, h('b', null, 'Who else is trading ' + sym + '. '),
        'Members of Congress, big funds and 5%+ holders, and the company\'s own executives, with the trades that matter flagged. ',
        'Each item shows when it happened and when it became public: the law decides how fast each kind is disclosed (table at the bottom).'));
      b.appendChild(ui.kpis([
        { label: 'Congress (12 months)', value: `${c12.filter((r) => r.side === 'buy').length} buys · ${c12.filter((r) => r.side === 'sell').length} sells`, sub: `${new Set(c12.map((r) => r.member)).size} members` },
        { label: 'Committee-linked trades', value: fmt.int(c12.filter((r) => (r.relevant || []).length).length), cls: c12.some((r) => (r.relevant || []).length) ? 'warn' : '', sub: 'member sits on an oversight committee' },
        { label: 'Insider net (6 months)', value: fmt.money(is6.net_value), cls: fmt.cls(is6.net_value), sub: `${is6.buys ?? 0} buys · ${is6.sells ?? 0} sells (Form 4)` },
        { label: 'Planned sales (30 days)', value: fmt.int((s.form144 || []).filter((f) => (f.filed || '') >= new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10)).length), sub: 'Form 144 notices' },
        { label: 'Funds holding 0.5%+', value: fmt.int(funds.length), sub: `${adds} added · ${cuts} cut last quarter` },
        { label: '5%+ stake filings (2 years)', value: fmt.int((s.stakes || []).length), sub: (s.stakes || []).some((f) => /13D/.test(f.form)) ? 'incl. an activist 13D' : '13G = passive holder' },
      ]));
      b.appendChild(sec('Highlights'));
      b.appendChild(flags(d.highlights || []));
      (d.notes || []).forEach((n) => b.appendChild(h('p', { class: 'note' }, n)));

      b.appendChild(sec('Trades on the price chart'));
      const cEl = charts.div('chart');
      b.appendChild(ui.panel(null, cEl, { cap: 'Two years of daily closes. Triangles: members of Congress (on the trade date, not the later disclosure date); circles: company insiders (Form 4). Bigger marker = bigger trade.' }));
      api(`/api/ticker/${enc(sym)}/chart?range=10Y`).then((ch) => tradeChart(cEl, ch.bars, cg, ins)).catch(() => cEl.appendChild(ui.empty('Price history unavailable.')));

      b.appendChild(sec('Members of Congress'));
      b.appendChild(ui.panel(null, ui.table([
        { key: 'disclosed', label: 'Public', fmt: 'date' }, { key: 'traded', label: 'Traded', fmt: 'date' },
        { key: 'lag_days', label: 'Delay', render: (r) => lag(r.lag_days) },
        { key: 'member', label: 'Member', l: true, render: (r) => who(r) },
        { key: 'side', label: 'Type', l: true, render: (r) => side(r.type) },
        { key: 'amount_lo', label: 'Amount', render: (r) => range(r.amount_lo, r.amount_hi) },
        { key: 'rel', label: 'Oversight committee', l: true, get: (r) => ((r.relevant || [])[0] || {}).name || '', render: (r) => ((r.relevant || []).length ? `<span class="warn">${esc(r.relevant[0].name.replace(/^(House|Senate|United States Senate) (Select |Permanent Select |Special )?Committee on (the )?/, ''))}${r.relevant[0].title ? ' (' + esc(r.relevant[0].title) + ')' : ''}</span>` : '<span class="dim">–</span>') },
        { key: 'owner', label: 'Owner', l: true, txt: true }, { key: 'url', label: 'Filing', l: true, nosort: true, render: (r) => filing(r) },
      ], cg, { sort: 'disclosed', max: true, csv: `${sym}-congress.csv`, rowClass: (r) => ((r.relevant || []).length ? 'flagged' : ''),
        emptyText: 'No member of Congress disclosed a trade in this stock in the last two years.' }),
      { cap: `Committees that oversee this industry: ${(d.oversight || []).map((c) => c.replace(/^(House|Senate) (Select |Permanent Select )?Committee on (the )?/, (m, ch) => ch + ' ')).join('; ') || '–'}. Amounts are the reported ranges. Paper reports are scanned images, read with OCR: their link says "scan".` }));

      b.appendChild(sec('Company insiders (Form 4)'));
      b.appendChild(ui.panel(null, ui.table([
        { key: 'date', label: 'Traded', fmt: 'date' }, { key: 'insider', label: 'Insider', l: true, txt: true },
        { key: 'role', label: 'Who', l: true, render: (r) => { const x = ROLE[r.role] || ROLE.officer; return `<span class="${x[1]}">${esc(x[0])}</span> <span class="dim">${esc(r.position || '')}</span>`; } },
        { key: 'kind', label: 'Type', l: true, render: (r) => `<span class="${r.kind === 'buy' ? 'up' : r.kind === 'sell' ? 'down' : 'dim'}">${esc(r.kind || '')}</span>` },
        { key: 'shares', label: 'Shares', fmt: 'big' }, { key: 'value', label: 'Value', fmt: 'big' }, { key: 'text', label: 'Detail', l: true, txt: true },
      ], ins, { sort: 'date', max: true, csv: `${sym}-insiders.csv`, rowClass: (r) => ((r.role === 'top' || r.role === 'owner') && (r.kind === 'sell' || r.kind === 'buy') ? 'flagged' : '') }),
      { cap: 'Executives, directors and 10%+ owners report within 2 business days. Open-market purchases are the stronger signal; many sales are pre-scheduled (10b5-1 plans) or for taxes.' }));

      b.appendChild(sec('Newest SEC filings (last 90 days)'));
      const fresh = [...(s.form144 || []).map((f) => ({ ...f, what: 'Planned sale (144)' })), ...(s.form4 || []).map((f) => ({ ...f, what: 'Insider trade (Form 4)' }))];
      b.appendChild(ui.panel(null, ui.table([
        { key: 'filed', label: 'Filed', fmt: 'date' }, { key: 'what', label: 'Form', l: true, render: (r) => `<span class="${/144/.test(r.form) ? 'warn' : ''}">${esc(r.what)}${/A$/.test(r.form) ? ' (amended)' : ''}</span>` },
        { key: 'party', label: 'Who', l: true, txt: true }, { key: 'period', label: 'Trade date', fmt: 'date' },
        { key: 'url', label: 'Filing', l: true, nosort: true, render: (r) => link(r.url, r.ocr ? 'Filing (scan)' : 'Filing') },
      ], fresh, { sort: 'filed', max: true, emptyText: 'No Form 4 or 144 filed in the last 90 days.' }),
      { cap: 'Straight from SEC EDGAR, minutes after filing. A Form 144 is filed on or before the sale day: the earliest public warning of insider selling.' }));

      b.appendChild(sec(`Big funds holding ${fmt.pctu(d.min_stake || 0.005, 1)}+ of the shares (13F)`));
      b.appendChild(ui.panel(null, ui.table([
        { key: 'holder', label: 'Holder', l: true, txt: true }, { key: 'kind', label: 'Type', l: true, txt: true },
        { key: 'pct_held', label: '% of shares', fmt: 'pctu', d: 2 }, { key: 'change', label: 'Position change', fmt: 'pct', d: 1, sign: true },
        { key: 'value', label: 'Value', fmt: 'big' }, { key: 'reported', label: 'As of', fmt: 'date' },
      ], funds, { sort: 'pct_held', max: true, rowClass: (r) => (Math.abs(r.change || 0) >= 0.05 ? 'flagged' : '') }),
      { cap: 'From the largest institutional and mutual-fund holders. Funds managing over $100M file their holdings quarterly, up to 45 days after the quarter ends: a trend, not a timing signal.' }));

      b.appendChild(sec('5%+ stakes (Schedule 13D / 13G, last 2 years)'));
      b.appendChild(ui.panel(null, ui.table([
        { key: 'filed', label: 'Filed', fmt: 'date' }, { key: 'party', label: 'Holder', l: true, txt: true },
        { key: 'form', label: 'Form', l: true, render: (r) => `<span class="${/13D/.test(r.form) ? 'warn' : ''}">${esc(r.form)}${/13D/.test(r.form) ? ' · activist' : ' · passive'}${/A$/.test(r.form) ? ' · stake changed' : ''}</span>` },
        { key: 'url', label: 'Filing', l: true, nosort: true, render: (r) => link(r.url, r.ocr ? 'Filing (scan)' : 'Filing') },
      ], s.stakes || [], { sort: 'filed', emptyText: 'No 5%+ stake filings in the last two years.' }),
      { cap: '13D: a 5%+ holder that intends to influence the company (an activist), filed within 5 business days. 13G: a passive holder (index funds, asset managers).' }));

      b.appendChild(sec('How fast each kind becomes public'));
      b.appendChild(h('div', { class: 'grid g2' },
        ui.panel(null, ui.table([{ key: 0, label: 'Who', l: true, txt: true, nosort: true }, { key: 1, label: 'Disclosed', l: true, txt: true, nosort: true }], d.speed || [])),
        ui.panel('Cross-check on other trackers', h('div', { class: 'links' }, (d.links || []).map((l) => h('a', { class: 'btn', href: l.url, target: '_blank', rel: 'noopener' }, l.label))),
          { cap: 'They read the same public filings; this page adds the committee links and the flags.' })));
    }, 420);
  };

  // ─── Congress trades page ─────────────────────────────────────────────
  SQ.views.congress = async function (view, parts, params) {
    let days = [30, 90, 365].includes(+params.days) ? +params.days : 90;
    const f = { chamber: 'all', party: 'all', side: 'all', flagged: false, q: '' };
    view.appendChild(h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Congress trades'),
      h('div', { class: 'sub' }, 'Stocks bought and sold by members of the House and Senate (STOCK Act reports), with trades by members of a committee that oversees the company\'s industry flagged. Members report within 45 days, so every trade is weeks old when it appears: the signal is what they buy, not when.'))));
    view.appendChild(ui.seg([[30, '30 days'], [90, '90 days'], [365, '1 year']], days, (v) => { days = +v; history.replaceState(null, '', '#/congress?days=' + v); load(); }));
    const box = h('div', { style: { marginTop: '12px' } });
    view.appendChild(box);
    function load() {
      box.innerHTML = '';
      ui.async(box, () => api('/api/congress?days=' + days), (b, d) => {
        const tt = d.totals || {}, st = d.stats || {};
        const credit = bargoCredit(st.bargo);
        if (credit) b.appendChild(credit);
        b.appendChild(ui.kpis([
          { label: 'Trades disclosed', value: fmt.int(tt.trades), sub: `in the last ${days} days` },
          { label: 'Buys / sells', value: `${fmt.int(tt.buys)} / ${fmt.int(tt.sells)}`, cls: (tt.buys || 0) >= (tt.sells || 0) ? 'up' : 'down' },
          { label: 'Members trading', value: fmt.int(tt.members) },
          { label: 'Committee-linked', value: fmt.int(tt.committee_flagged), cls: tt.committee_flagged ? 'warn' : '', sub: 'member oversees the industry' },
          { label: 'Filings read', value: fmt.int((st.filings || 0) - (st.unreadable || 0) - (st.pending || 0)), sub: `${fmt.int(st.unreadable)} paper scans not readable${st.handwritten ? ` (${fmt.int(st.handwritten)} handwritten)` : ''}${st.pending ? ` · ${st.pending} pending` : ''}` },
        ]));
        const tcols = (k) => [{ key: 'ticker', label: 'Ticker', l: true, render: (r) => `<a href="#/t/${enc(r.ticker)}">${esc(r.ticker)}</a>` },
          { key: 'name', label: 'Name', l: true, txt: true }, { key: k, label: k === 'buys' ? 'Buys' : 'Sells', fmt: 'int' },
          { key: k === 'buys' ? 'buy_usd' : 'sell_usd', label: '≈ $', fmt: 'big' }, { key: 'members', label: 'Members', fmt: 'int' }];
        b.appendChild(h('div', { class: 'grid g3' },
          ui.panel('Most bought', ui.table(tcols('buys'), d.most_bought || [], { sort: 'buys' })),
          ui.panel('Most sold', ui.table(tcols('sells'), d.most_sold || [], { sort: 'sells' })),
          ui.panel('Most active members', ui.table([{ key: 'member', label: 'Member', l: true, render: (r) => who(r) }, { key: 'trades', label: 'Trades', fmt: 'int' },
            { key: 'buy_usd', label: 'Bought ≈', fmt: 'big' }, { key: 'sell_usd', label: 'Sold ≈', fmt: 'big' }], d.most_active || [], { sort: 'trades' }))));
        b.appendChild(sec('Every trade'));
        const search = h('input', { type: 'search', placeholder: 'Member or ticker…', 'aria-label': 'Filter by member or ticker', value: f.q,
          oninput: (e) => { f.q = e.target.value.trim().toLowerCase(); redraw(); } });
        const sel = (key, opts) => h('select', { 'aria-label': key, onchange: (e) => { f[key] = e.target.value; redraw(); } },
          opts.map(([v, l]) => h('option', { value: v, selected: f[key] === v }, l)));
        const flagBox = h('label', { class: 'nowrap' }, h('input', { type: 'checkbox', checked: f.flagged, onchange: (e) => { f.flagged = e.target.checked; redraw(); } }), ' Committee-linked only');
        const tools = h('div', { class: 'filters' }, search, sel('chamber', [['all', 'House + Senate'], ['H', 'House'], ['S', 'Senate']]),
          sel('party', [['all', 'All parties'], ['D', 'Democrats'], ['R', 'Republicans'], ['I', 'Independents']]),
          sel('side', [['all', 'Buys + sells'], ['buy', 'Buys'], ['sell', 'Sells']]), flagBox);
        const pass = (r) => (f.chamber === 'all' || r.chamber === f.chamber) && (f.party === 'all' || r.party === f.party)
          && (f.side === 'all' || (f.side === 'buy' ? r.type === 'buy' : /sell/.test(r.type || ''))) && (!f.flagged || r.committee)
          && (!f.q || (r.member || '').toLowerCase().includes(f.q) || (r.ticker || '').toLowerCase() === f.q || (r.ticker || '').toLowerCase().startsWith(f.q));
        const rows = d.rows || [];
        const tbl = ui.table([
          { key: 'disclosed', label: 'Public', fmt: 'date' }, { key: 'traded', label: 'Traded', fmt: 'date' }, { key: 'lag', label: 'Delay', render: (r) => lag(r.lag) },
          { key: 'member', label: 'Member', l: true, render: (r) => who(r) },
          { key: 'ticker', label: 'Ticker', l: true, render: (r) => `<a href="#/t/${enc(r.ticker)}">${esc(r.ticker)}</a>` },
          { key: 'type', label: 'Type', l: true, render: (r) => side(r.type) }, { key: 'lo', label: 'Amount', render: (r) => range(r.lo, r.hi) },
          { key: 'committee', label: 'Oversight committee', l: true, render: (r) => (r.committee ? `<span class="warn">${esc(r.committee.replace(/^(House|Senate) (Select |Permanent Select )?Committee on (the )?/, ''))}</span>` : '<span class="dim">–</span>') },
          { key: 'asset', label: 'Asset', l: true, txt: true }, { key: 'url', label: 'Filing', l: true, nosort: true, render: (r) => filing(r) },
        ], rows.filter(pass), { sort: 'disclosed', max: true, limit: 400, csv: `congress-trades-${days}d.csv`, tools, rowClass: (r) => (r.committee ? 'flagged' : ''),
          emptyText: 'No trade matches these filters.' });
        function redraw() { tbl.redraw(rows.filter(pass)); }
        b.appendChild(ui.panel(null, tbl, { cap: (d.rows_note ? d.rows_note + '. ' : '') + 'Sorted by disclosure date; the first 400 rows are shown (CSV has all). Sources: the House Clerk and the Senate eFD; paper reports (scans) are read with OCR and their link says "scan"; a handwritten row whose date OCR cannot read is left out, not guessed. Oversight committee: the member sits on a committee with jurisdiction over the company\'s industry (a heuristic).' }));
      }, 420);
    }
    load();
  };
})();
