/* Ticker workspace: live header, tabs, Overview tab (price chart + panels). Other tabs
 * live in ticker_tabs.js / ticker_tabs2.js and register themselves in SQ.tabs. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts } = SQ;
  SQ.tabs = SQ.tabs || {};

  const TABS = [
    ['overview', 'Overview'], ['risk', 'Risk & returns'], ['volatility', 'Volatility'], ['tail', 'Tail risk & stress'],
    ['options', 'Options'], ['fundamentals', 'Fundamentals'], ['analysts', 'Analysts & earnings'], ['ownership', 'Ownership'],
    ['factors', 'Factors & regimes'], ['events', 'Filings & news'],
  ];
  SQ.TICKER_TABS = TABS;
  const state = { sym: null, quote: null, overview: null };
  SQ.tickerState = state;

  function header(sym, q) {
    const m = (q && q.meta) || {};
    const ext = q && q.ext_price ? h('span', { class: 'ext' }, `${q.ext_label}: `,
      h('span', { dataset: { live: sym + ':ext_price:price' } }, fmt.price(q.ext_price)), ' ',
      h('span', { class: fmt.cls(q.ext_change_pct), dataset: { live: sym + ':ext_change_pct:pct', sign: 'ext_change_pct' } }, fmt.pct(q.ext_change_pct, 2))) : null;
    const state_ = (q && q.market_state) || '';
    const stateLabel = { REGULAR: 'Market open', PRE: 'Pre-market', POST: 'After hours', POSTPOST: 'Closed', PREPRE: 'Closed', CLOSED: 'Closed' }[state_] || state_;
    return h('div', { class: 'th-wrap' },
      h('div', { class: 'th-name' },
        h('h1', null, (q && (q.long_name || q.name)) || sym),
        h('div', { class: 'meta' }, h('span', { class: 'acc' }, sym), q && q.exchange ? h('span', null, '· ' + q.exchange) : null,
          q && q.currency ? h('span', null, '· ' + q.currency) : null, m.sector ? ui.chip(m.sector, 'acc') : null,
          m.tier ? ui.chip('Tier ' + m.tier) : null, q && q.type_disp ? ui.chip(q.type_disp) : null)),
      h('div', null,
        h('div', { class: 'th-price' },
          h('span', { class: 'px', dataset: { live: sym + ':price:price', v: q && q.price } }, fmt.price(q && q.price)),
          h('span', { class: 'chg ' + fmt.cls(q && q.change_pct), dataset: { live: sym + ':change:num', sign: 'change_pct' } }, fmt.num(q && q.change, 2)),
          h('span', { class: 'chg ' + fmt.cls(q && q.change_pct), dataset: { live: sym + ':change_pct:pct', sign: 'change_pct' } }, fmt.pct(q && q.change_pct, 2)), ext),
        h('div', { class: 'dim mono', style: { fontSize: '11.5px', marginTop: '4px' } },
          stateLabel, q && q.time ? ' · last trade ' + fmt.dateTime(q.time) : '', q && q.delay_min ? ` · delayed ${q.delay_min} min` : '')),
      h('div', { class: 'th-actions' },
        h('button', { class: 'btn', title: 'Add to the current watchlist', onclick: () => SQ.addToWatchlist(sym) }, '☆ Watch'),
        h('a', { class: 'btn', href: '#/compare?s=' + encodeURIComponent(sym + ',SOXX,SPY') }, 'Compare'),
        h('a', { class: 'btn', href: '#/offer?t=' + encodeURIComponent(sym) }, 'Value a grant'),
        h('button', { class: 'btn', title: 'Excel workbook with prices, risk, options, statements, estimates and ownership', onclick: () => ui.download('/api/export/ticker/' + encodeURIComponent(sym) + '.xlsx') },
          h('span', { html: '<svg viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14"/></svg>' }), 'Excel'),
        h('button', { class: 'btn primary', title: 'One self-contained HTML file with every tab: send it to a friend, it opens in any browser', onclick: () => {
          ui.toast('Building the shareable file (takes a few seconds)…', 4000);
          ui.download('/api/export/snapshot.html?market=false&symbols=' + encodeURIComponent(sym));
        } }, h('span', { html: '<svg viewBox="0 0 24 24"><path d="M4 12v7h16v-7M12 3v12m0-12l-4 4m4-4l4 4"/></svg>' }), 'Share')));
  }

  SQ.views.ticker = async function (view, parts, params, same) {
    const sym = decodeURIComponent(parts[0] || '').toUpperCase();
    const tab = TABS.some(([k]) => k === parts[1]) ? parts[1] : 'overview';
    if (!sym) { SQ.go('#/market'); return; }
    if (!same || state.sym !== sym) {
      state.sym = sym; state.quote = null; state.overview = null;
      view.innerHTML = '';
      const head = h('div', { id: 'th' }, ui.skeleton(70));
      const tabs = h('nav', { class: 'tabs', id: 'tt' });
      const body = h('div', { id: 'tb' });
      view.appendChild(head); view.appendChild(tabs); view.appendChild(body);
      SQ.live.register('ticker', [sym]);
      try {
        const qs = await api('/api/quotes?symbols=' + encodeURIComponent(sym));
        state.quote = qs[sym];
        if (!state.quote) throw new Error(`Yahoo has no quote for "${sym}". Check the symbol: international listings need a suffix (005930.KS, 8035.T, ASML.AS), crypto uses BTC-USD, indices ^GSPC.`);
        head.innerHTML = '';
        head.appendChild(header(sym, state.quote));
        document.title = `${sym} ${fmt.price(state.quote.price)} · Semi Quant Terminal`;
      } catch (e) {
        head.innerHTML = '';
        head.appendChild(ui.error(e));
        return;
      }
    }
    const tabs = SQ.$('#tt'), body = SQ.$('#tb');
    tabs.innerHTML = '';
    TABS.forEach(([k, label]) => tabs.appendChild(h('a', { href: `#/t/${encodeURIComponent(sym)}/${k}`, class: k === tab ? 'on' : '' }, label)));
    SQ.cleanups.splice(0).forEach((fn) => { try { fn(); } catch (e) { /* ignore */ } });
    charts.disposeAll(body);
    body.innerHTML = '';
    const fn = tab === 'overview' ? overviewTab : SQ.tabs[tab];
    if (!fn) { body.appendChild(ui.empty('Coming soon.')); return; }
    await fn(body, sym, params);
  };

  // ─── Price chart panel ────────────────────────────────────────────────
  const OVERLAY_OPTS = [['sma20', 'SMA 20'], ['sma50', 'SMA 50'], ['sma200', 'SMA 200'], ['ema21', 'EMA 21'], ['bb', 'Bollinger'], ['vwap', 'VWAP'],
    ['ichimoku', 'Ichimoku'], ['supertrend', 'Supertrend'], ['keltner', 'Keltner'], ['donchian', 'Donchian']];
  const PANE_OPTS = [['rsi', 'RSI 14'], ['macd', 'MACD'], ['stoch', 'Stochastic'], ['adx', 'ADX / DI'], ['atr', 'ATR'], ['obv', 'OBV'], ['mfi', 'MFI'], ['cci', 'CCI']];
  function loadPrefs() {
    try { return JSON.parse(localStorage.getItem('sq_chart') || 'null') || {}; } catch (e) { return {}; }
  }
  function savePrefs(p) { try { localStorage.setItem('sq_chart', JSON.stringify(p)); } catch (e) { /* ignore */ } }

  function chartPanel(sym) {
    const prefs = Object.assign({ range: '6M', style: 'auto', log: false, ind: ['sma20', 'sma50', 'sma200', 'rsi', 'macd'] }, loadPrefs());
    const host = h('div');
    let inst = null, timer = null;
    const ranges = ['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', '2Y', '5Y', '10Y', 'MAX'];
    const pop = h('div', { class: 'ind-pop hidden' });
    const indBtn = h('button', { class: 'btn sm', type: 'button', onclick: (e) => { e.stopPropagation(); pop.classList.toggle('hidden'); } }, 'Indicators');
    const drawPop = () => {
      pop.innerHTML = '';
      pop.appendChild(h('div', { class: 'label', style: { gridColumn: '1 / -1' } }, 'On the price chart'));
      OVERLAY_OPTS.forEach(([k, l]) => pop.appendChild(h('label', null, h('input', { type: 'checkbox', checked: prefs.ind.includes(k), onchange: (e) => toggle(k, e.target.checked) }), l)));
      pop.appendChild(h('div', { class: 'label', style: { gridColumn: '1 / -1', marginTop: '6px' } }, 'Panes below'));
      PANE_OPTS.forEach(([k, l]) => pop.appendChild(h('label', null, h('input', { type: 'checkbox', checked: prefs.ind.includes(k), onchange: (e) => toggle(k, e.target.checked) }), l)));
    };
    const toggle = (k, on) => { prefs.ind = on ? Array.from(new Set(prefs.ind.concat(k))) : prefs.ind.filter((x) => x !== k); savePrefs(prefs); load(); };
    document.addEventListener('click', (e) => { if (!pop.contains(e.target)) pop.classList.add('hidden'); });
    drawPop();
    const tools = h('div', { class: 'pc-tools' },
      ui.seg(ranges, prefs.range, (v) => { prefs.range = v; savePrefs(prefs); load(); }),
      ui.seg([['auto', 'Auto'], ['candles', 'Candles'], ['line', 'Line'], ['area', 'Area']], prefs.style, (v) => { prefs.style = v; savePrefs(prefs); load(); }),
      h('span', { class: 'ind-menu' }, indBtn, pop),
      h('label', { class: 'mono', style: { fontSize: '12px', display: 'flex', gap: '5px', alignItems: 'center' } },
        h('input', { type: 'checkbox', checked: prefs.log, onchange: (e) => { prefs.log = e.target.checked; savePrefs(prefs); load(); } }), 'Log'),
      h('span', { style: { marginLeft: 'auto', display: 'flex', gap: '6px' } },
        h('button', { class: 'btn sm', type: 'button', title: 'Save the chart as PNG', onclick: () => inst && inst.png(sym + '-' + prefs.range) }, 'PNG')));
    const chartBox = h('div');
    const panel = h('section', { class: 'panel' }, tools, chartBox);
    host.appendChild(panel);
    async function load() {
      clearTimeout(timer);
      if (inst) { inst.destroy(); inst = null; }
      chartBox.innerHTML = '';
      chartBox.appendChild(h('div', { style: { padding: '14px' } }, ui.skeleton(430)));
      const intra = ['1D', '5D', '1M'].includes(prefs.range);
      const ind = prefs.ind.filter((k) => (intra ? k !== 'sma200' : k !== 'vwap') || prefs.ind.length < 2);
      try {
        const d = await api(`/api/ticker/${encodeURIComponent(sym)}/chart?range=${prefs.range}&ind=${encodeURIComponent((intra && !ind.includes('vwap') ? ind.concat('vwap') : ind).join(','))}`);
        chartBox.innerHTML = '';
        inst = charts.priceChart(chartBox, d, { style: prefs.style === 'auto' ? undefined : prefs.style, log: prefs.log });
        if (d.intraday && !SQ.snapshot) timer = setTimeout(load, Math.max(30, SQ.settings.intraday_refresh_seconds || 60) * 1000);
      } catch (e) {
        chartBox.innerHTML = '';
        chartBox.appendChild(h('div', { style: { padding: '14px' } }, ui.error(e, load)));
      }
    }
    const off = SQ.live.onQuotes((qs) => { const q = qs[sym]; if (q && inst) inst.tickLast(q.price); });
    SQ.onCleanup(() => { off(); clearTimeout(timer); if (inst) inst.destroy(); });
    load();
    return host;
  }
  SQ.chartPanel = chartPanel;

  // ─── Overview tab ─────────────────────────────────────────────────────
  async function overviewTab(body, sym) {
    const grid = h('div', { class: 'grid g-main' });
    const left = h('div', { class: 'grid' }), right = h('div', { class: 'grid' });
    grid.appendChild(left); grid.appendChild(right);
    body.appendChild(grid);
    left.appendChild(chartPanel(sym));
    const lower = h('div', { class: 'grid' }), side = h('div', { class: 'grid' });
    left.appendChild(lower); right.appendChild(side);
    lower.appendChild(ui.skeleton(300)); side.appendChild(ui.skeleton(500));
    let d;
    try { d = await api(`/api/ticker/${encodeURIComponent(sym)}/overview`); }
    catch (e) { lower.innerHTML = ''; side.innerHTML = ''; lower.appendChild(ui.error(e)); return; }
    state.overview = d;
    lower.innerHTML = ''; side.innerHTML = '';
    const q = d.quote || {}, ks = d.key_stats || {}, pr = d.profile || {};

    // Returns table
    if (d.returns && d.returns.rows) {
      const hz = d.returns.horizons;
      const rows = d.returns.rows.map((r) => ({ name: r.name === 'Asset' ? sym : r.name, ...r.values }));
      lower.appendChild(ui.panel('Performance', ui.table([{ key: 'name', label: '', l: true, txt: true, nosort: true }]
        .concat(hz.map((k) => ({ key: k, label: k + (d.returns.annualized.includes(k) ? ' ann.' : ''), fmt: 'pct', d: 1, sign: true, nosort: true }))), rows,
      { rowClass: (r) => (r.name === sym ? 'self' : '') }), { cap: '3Y and longer are annualised (CAGR). Benchmarks aligned to the same dates. Includes today\'s live move.' }));
    }
    // Key statistics
    const cur = q.currency;
    lower.appendChild(ui.panel('Key statistics', ui.kv([
      ['Market cap', fmt.money(ks.market_cap, cur)], ['Enterprise value', fmt.money(ks.enterprise_value, cur)],
      ['P/E (trailing)', fmt.x(ks.pe)], ['P/E (forward)', fmt.x(ks.fpe)], ['PEG', fmt.num(ks.peg, 2)], ['Price / sales', fmt.x(ks.ps)],
      ['Price / book', fmt.x(ks.pb)], ['EV / revenue', fmt.x(ks.ev_revenue)], ['EV / EBITDA', fmt.x(ks.ev_ebitda)],
      ['EPS (TTM)', fmt.num(ks.eps_ttm, 2)], ['EPS (forward)', fmt.num(ks.eps_fwd, 2)], ['Revenue (TTM)', fmt.money(ks.revenue, pr.financial_currency || cur)],
      ['Revenue growth (yoy)', fmt.pct(ks.revenue_growth), fmt.cls(ks.revenue_growth)], ['Earnings growth (yoy)', fmt.pct(ks.earnings_growth), fmt.cls(ks.earnings_growth)],
      ['Gross margin', fmt.pctu(ks.gross_margin)], ['Operating margin', fmt.pctu(ks.operating_margin)], ['Net margin', fmt.pctu(ks.net_margin)],
      ['ROE', fmt.pctu(ks.roe)], ['ROA', fmt.pctu(ks.roa)], ['Free cash flow', fmt.money(ks.fcf, pr.financial_currency || cur)],
      ['Cash', fmt.money(ks.cash, pr.financial_currency || cur)], ['Debt', fmt.money(ks.debt, pr.financial_currency || cur)],
      ['Debt / equity', fmt.num(ks.debt_to_equity, 2)], ['Current ratio', fmt.num(ks.current_ratio, 2)],
      ['Beta (5Y monthly)', fmt.num(ks.beta, 2)], ['Dividend yield', fmt.pctu(ks.dividend_yield, 2)], ['Ex-dividend', fmt.date(ks.ex_dividend)],
      ['Shares outstanding', fmt.big(ks.shares_out)], ['Float', fmt.big(ks.float)], ['Short % of float', fmt.pctu(ks.short_pct_float)],
      ['Days to cover', fmt.num(ks.short_ratio, 1)], ['Insiders hold', fmt.pctu(ks.insiders)], ['Institutions hold', fmt.pctu(ks.institutions)],
      ['Avg volume (3M)', fmt.big(ks.avg_volume)], ['52-week change', fmt.pct(ks.change_52w), fmt.cls(ks.change_52w)],
    ]), { cap: 'Source: Yahoo Finance (quote + company profile). Statement figures in ' + (pr.financial_currency || cur || 'USD') + '.' }));
    if (pr.summary) {
      lower.appendChild(ui.panel('About ' + (pr.name || sym), h('div', null,
        h('p', { class: 'note', style: { maxWidth: 'none' } }, pr.summary),
        h('div', { class: 'chips', style: { marginTop: '10px' } }, [pr.sector, pr.industry, pr.country, pr.employees ? fmt.int(pr.employees) + ' employees' : null]
          .filter(Boolean).map((x) => ui.chip(x))),
        pr.website ? h('p', { style: { marginTop: '8px', fontSize: '13px' } }, h('a', { href: pr.website, target: '_blank', rel: 'noopener' }, pr.website)) : null)));
    }

    // Side: score
    const sc = d.score;
    if (sc && fmt.ok(sc.score)) {
      side.appendChild(ui.panel('Quant score', h('div', null,
        h('div', { style: { display: 'flex', gap: '14px', alignItems: 'center' } }, ui.ring(sc.score),
          h('div', { class: 'note' }, `Rank ${sc.rank} of ${sc.of} in the ${sc.universe}. Percentile blend of momentum, trend, value, quality, growth, estimate revisions, analyst view and low volatility.`)),
        h('div', { style: { marginTop: '10px' } }, (sc.components || []).map((c) => h('div', { class: 'comp', title: JSON.stringify(c.inputs || {}) },
          h('span', null, c.name), h('span', { class: 'b' }, h('i', { style: { width: (c.score || 0) + '%', background: c.score >= 67 ? 'var(--up)' : c.score >= 40 ? 'var(--warn)' : 'var(--down)' } })),
          h('span', null, fmt.ok(c.score) ? Math.round(c.score) : '–')))),
        (sc.strengths || []).length || (sc.weaknesses || []).length ? h('div', { class: 'note', style: { marginTop: '8px' } },
          (sc.strengths || []).slice(0, 3).map((s) => h('div', { class: 'up' }, '+ ' + s)),
          (sc.weaknesses || []).slice(0, 3).map((s) => h('div', { class: 'down' }, '− ' + s))) : null)));
    }
    // Technical rating
    const sg = d.signals;
    if (sg && sg.counts) {
      const pos = ((sg.score || 0) + 1) / 2 * 100;
      const key = (sg.signals || []).filter((s) => /SMA 50|SMA 200|RSI|MACD|ADX|cross/i.test(s.name)).slice(0, 7);
      side.appendChild(ui.panel('Technical rating', h('div', null,
        h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' } },
          h('b', { class: /buy/i.test(sg.rating) ? 'up' : /sell/i.test(sg.rating) ? 'down' : '', style: { fontSize: '19px' } }, sg.rating),
          h('span', { class: 'mono dim', style: { fontSize: '12px' } }, `${sg.counts.buy} buy · ${sg.counts.neutral} neutral · ${sg.counts.sell} sell`)),
        h('div', { class: 'meter' }, h('i', { style: { left: pos + '%' } })),
        h('div', { class: 'meter-l' }, h('span', null, 'Strong sell'), h('span', null, 'Neutral'), h('span', null, 'Strong buy')),
        ui.table([{ key: 'name', label: 'Signal', l: true, txt: true, nosort: true }, { key: 'value', label: 'Value', fmt: 'num', d: 2, nosort: true },
          { key: 'signal', label: '', nosort: true, render: (r) => `<span class="${r.signal === 'buy' ? 'up' : r.signal === 'sell' ? 'down' : 'dim'}">${r.signal}</span>` }], key)),
      { cap: 'TradingView-style summary of moving-average and oscillator signals on daily bars. Full list in the Risk & returns tab is not needed: hover rows for notes.' }));
    }
    // 52w range & levels
    const lv = d.levels || {}, tr = d.trend || {};
    if (fmt.ok(q.low_52w) && fmt.ok(q.high_52w)) {
      const pos = Math.max(0, Math.min(1, (q.price - q.low_52w) / (q.high_52w - q.low_52w))) * 100;
      const pv = lv.pivots || {};
      side.appendChild(ui.panel('Range & levels', h('div', null,
        h('div', { class: 'meter-l' }, h('span', null, '52W low ' + fmt.price(q.low_52w)), h('span', null, '52W high ' + fmt.price(q.high_52w))),
        h('div', { class: 'range52' }, h('i', { style: { left: pos + '%' } })),
        ui.kv([['From 52W high', fmt.pct(tr.pct_from_52w_high), fmt.cls(tr.pct_from_52w_high)], ['Trend', tr.regime || '–', tr.regime === 'uptrend' ? 'up' : tr.regime === 'downtrend' ? 'down' : ''],
          ['vs 50-day avg', tr.above_sma50 == null ? '–' : tr.above_sma50 ? 'above' : 'below', tr.above_sma50 ? 'up' : 'down'],
          ['vs 200-day avg', tr.above_sma200 == null ? '–' : tr.above_sma200 ? 'above' : 'below', tr.above_sma200 ? 'up' : 'down'],
          ['Momentum 12-1', fmt.pct(tr.momentum_12_1), fmt.cls(tr.momentum_12_1)], ['Pivot', fmt.price(pv.P)],
          ['Resistance R1 / R2', `${fmt.price(pv.R1)} / ${fmt.price(pv.R2)}`], ['Support S1 / S2', `${fmt.price(pv.S1)} / ${fmt.price(pv.S2)}`]]))));
    }
    // Risk snapshot
    const st = d.stats_1y || {}, tl = d.tail || {};
    side.appendChild(ui.panel('Risk snapshot (1 year, daily)', ui.kv([
      ['Volatility (ann.)', fmt.pctu(st.vol)], ['Sharpe', fmt.num(st.sharpe, 2)], ['Sortino', fmt.num(st.sortino, 2)],
      ['Max drawdown', fmt.pct(st.max_drawdown), 'down'], ['Beta vs S&P 500', fmt.num(st.beta, 2)], ['Correlation vs S&P', fmt.num(st.correlation, 2)],
      ['1-day VaR 95% / 99%', `${fmt.pctu(tl.var95_1d)} / ${fmt.pctu(tl.var99_1d)}`], ['Worst day (5Y)', fmt.pct(tl.worst_day), 'down']]),
    { right: h('a', { class: 'btn sm', href: `#/t/${encodeURIComponent(sym)}/risk` }, 'Details') }));
    // Analysts
    if (fmt.ok(ks.target_mean)) {
      side.appendChild(ui.panel('Analyst consensus', ui.kv([
        ['Recommendation', (ks.rec_key || '–').replace('_', ' ') + (fmt.ok(ks.rec_mean) ? ` (${ks.rec_mean.toFixed(2)})` : '')],
        ['Analysts', fmt.int(ks.n_analysts)], ['Mean target', fmt.price(ks.target_mean)], ['Upside to mean', fmt.pct(ks.upside), fmt.cls(ks.upside)],
        ['Target range', `${fmt.price(ks.target_low)} – ${fmt.price(ks.target_high)}`]]),
      { right: h('a', { class: 'btn sm', href: `#/t/${encodeURIComponent(sym)}/analysts` }, 'Estimates') }));
    }
    const ne = d.next_earnings;
    if (ne && (ne.time || ne.date)) {
      side.appendChild(ui.panel('Next earnings', ui.kv([['Date', ne.time ? fmt.dateTime(ne.time) : fmt.date(ne.date)], ['Confirmed', ne.estimated ? 'no (estimated)' : 'yes'],
        ['EPS estimate', fmt.num(ne.eps_avg, 2)], ['EPS range', `${fmt.num(ne.eps_low, 2)} – ${fmt.num(ne.eps_high, 2)}`], ['Revenue estimate', fmt.money(ne.rev_avg)]])));
    }
    side.appendChild(ui.panel('News', SQ.newsList((d.news || []).slice(0, 8)), { right: h('a', { class: 'btn sm', href: `#/t/${encodeURIComponent(sym)}/events` }, 'More') }));
  }
})();
