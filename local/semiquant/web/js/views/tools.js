/* Screener, Compare, Portfolio, Offer & RSU simulator, Calendar, Settings & help. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts } = SQ;
  const enc = encodeURIComponent;
  const sec = ui.sec;
  const pageHead = (title, sub, actions) => h('div', { class: 'page-h' }, h('div', null, h('h1', null, title), sub ? h('div', { class: 'sub' }, sub) : null),
    actions ? h('div', { class: 'actions' }, actions) : null);
  const dlIcon = '<svg viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14"/></svg>';

  // ─── Screener ─────────────────────────────────────────────────────────
  const GROUPS = {
    Overview: ['ticker', 'name', 'sector', 'price', 'change_pct', 'score', 'ret_1m', 'ret_ytd', 'ret_1y', 'market_cap_usd', 'fpe', 'target_upside', 'vol_3m', 'trend', 'earnings'],
    Performance: ['ticker', 'name', 'price', 'change_pct', 'ext_change_pct', 'ret_5d', 'ret_1m', 'ret_3m', 'ret_6m', 'ret_ytd', 'ret_1y', 'mom_12_1', 'rel_strength_3m', 'pct_from_52w_high'],
    Valuation: ['ticker', 'name', 'price', 'market_cap_usd', 'pe', 'fpe', 'ev_sales', 'ev_ebitda', 'fcf_yield', 'dividend_yield', 'score'],
    'Quality & growth': ['ticker', 'name', 'gross_margin', 'operating_margin', 'roe', 'rev_growth', 'eps_growth', 'eps_rev_30d', 'score'],
    'Risk & technical': ['ticker', 'name', 'vol_3m', 'beta_1y', 'max_dd_1y', 'sharpe_1y', 'short_pct', 'rsi14', 'pos_52w', 'trend', 'rel_volume'],
    Analysts: ['ticker', 'name', 'price', 'target_upside', 'rec_mean', 'eps_rev_30d', 'earnings', 'score'],
    Scores: ['ticker', 'name', 'score', 'momentum', 'trend_score', 'value', 'quality', 'growth', 'revisions', 'analyst', 'low_vol'],
  };
  const HEAT = { change_pct: 0.04, ext_change_pct: 0.03, ret_5d: 0.08, ret_1m: 0.15, ret_3m: 0.3, ret_6m: 0.4, ret_ytd: 0.6, ret_1y: 0.8, mom_12_1: 0.8, rel_strength_3m: 0.2, target_upside: 0.4, eps_rev_30d: 0.05 };

  SQ.views.screener = async function (view, parts, params) {
    const lists = SQ.watchlists.lists || {};
    let saved = 'semis';
    try { saved = localStorage.getItem('sq_u') || 'semis'; } catch (e) { /* ignore */ }
    let src = params.list ? 'l:' + params.list : 'u:' + (params.u || saved);
    let group = 'Overview', sector = 'All', text = '';
    const q = () => (src.startsWith('l:') ? 'list=' + enc(src.slice(2)) : 'u=' + enc(src.slice(2)));
    view.appendChild(pageHead('Screener', 'Live quotes + daily metrics + fundamentals, ranked into a 0-100 quant score. Pick a universe (semiconductors, US large caps across every sector, global leaders, ETFs) or one of your watchlists. Click a row to open it; click a header to sort.', SQ.static ? null : [
      h('button', { class: 'btn', onclick: () => ui.download('/api/export/screener.xlsx?' + q()) }, h('span', { html: dlIcon }), 'Excel'),
      h('button', { class: 'btn', onclick: () => ui.download('/api/export/screener.csv?' + q()) }, h('span', { html: dlIcon }), 'CSV')]));
    const tools = h('div', { class: 't-tools' });
    const out = h('div');
    view.appendChild(tools); view.appendChild(out);
    let data = null;
    const load = () => ui.async(out, () => api('/api/screener?' + q()), (b, d) => { data = d; sector = 'All'; draw(); }, 500);
    let unis = [];
    try { unis = await api('/api/universes'); } catch (e) { unis = [{ key: 'semis', label: 'Semiconductors', count: 70 }]; }
    tools.appendChild(ui.select(unis.map((u) => ['u:' + u.key, `${u.label} (${u.count})`]).concat(SQ.snapshot ? [] : Object.keys(lists).map((k) => ['l:' + k, 'Watchlist: ' + k])), src, (v) => {
      src = v;
      if (v.startsWith('u:')) { try { localStorage.setItem('sq_u', v.slice(2)); } catch (e) { /* ignore */ } }
      load();
    }));
    tools.appendChild(ui.seg(Object.keys(GROUPS), group, (v) => { group = v; draw(); }));
    const sectorSel = h('span');
    tools.appendChild(sectorSel);
    tools.appendChild(h('input', { class: 'inp', placeholder: 'Filter…', style: { width: '140px' }, oninput: (e) => { text = e.target.value.toLowerCase(); draw(); } }));
    function draw() {
      if (!data) return;
      const cols = Object.fromEntries(data.columns.map((c) => [c.key, c]));
      const sectors = ['All'].concat(Array.from(new Set(data.rows.map((r) => r.sector).filter(Boolean))).sort());
      sectorSel.innerHTML = '';
      sectorSel.appendChild(ui.select(sectors, sector, (v) => { sector = v; draw(); }));
      const rows = data.rows.filter((r) => (sector === 'All' || r.sector === sector) && (!text || (r.ticker + ' ' + (r.name || '')).toLowerCase().includes(text)));
      const keys = GROUPS[group];
      const spec = keys.map((k) => {
        const c = cols[k] || { key: k, label: k.replace(/_/g, ' '), format: 'score' };
        const f = { pct: 'pct', big: 'big', x: 'x', num: 'num', price: 'price', score: 'score', date: 'date', text: undefined }[c.format];
        const o = { key: k, label: c.label, fmt: f, l: c.format === 'text', txt: k === 'name' || k === 'sector' };
        if (k === 'ticker') { o.cls = 'sym'; }
        if (HEAT[k]) o.heat = HEAT[k];
        if (['score', 'momentum', 'trend_score', 'value', 'quality', 'growth', 'revisions', 'analyst', 'low_vol'].includes(k)) {
          o.render = (r) => { const v = r[k]; if (!fmt.ok(v)) return '–'; const c2 = v >= 67 ? 'up' : v >= 40 ? 'warn' : 'down'; return `<span class="${c2}">${Math.round(v)}</span> <span class="bar" style="width:${v * 0.5}px;background:var(--${c2})"></span>`; };
        }
        if (k === 'price') o.render = (r) => `${fmt.price(r.price)}${r.currency && r.currency !== 'USD' ? ' <span class="dim">' + r.currency + '</span>' : ''}`;
        if (k === 'trend_score') o.label = 'Trend';
        if (k === 'trend') o.render = (r) => `<span class="${r.trend === 'up' ? 'up' : r.trend === 'down' ? 'down' : 'dim'}">${r.trend || '–'}</span>`;
        if (k === 'ext_change_pct') o.sign = true;
        if (k === 'change_pct') o.render = (r) => `<span class="${fmt.cls(r.change_pct)}" data-live="${r.ticker}:change_pct:pct" data-sign="change_pct">${fmt.pct(r.change_pct, 2)}</span>`;
        return o;
      });
      out.innerHTML = '';
      out.appendChild(ui.panel(`${data.name} · ${rows.length} names`, ui.table(spec, rows, { sort: 'score', max: true, onRow: (r) => SQ.go('#/t/' + enc(r.ticker)),
        rowClass: (r) => (r.missing ? 'dim' : ''), csv: 'screener.csv' }),
      { cap: `Scores are percentile ranks within this list (100 = best). Composite weights: momentum 20%, trend 10%, value 15%, quality 15%, growth 10%, revisions 15%, analysts 5%, low volatility 10%. Relative strength vs ${data.rel_bench || 'SPY'}. Fundamentals refresh every 6 hours, prices live.` }));
      SQ.live.register('screener', rows.map((r) => r.ticker));
      // Scatter map
      out.appendChild(sec('Map'));
      const numKeys = data.columns.filter((c) => ['pct', 'num', 'x', 'big', 'score'].includes(c.format)).map((c) => [c.key, c.label]);
      let xk = 'vol_3m', yk = 'ret_1y';
      const sEl = charts.div('chart tall');
      const drawMap = () => {
        const pts = rows.filter((r) => fmt.ok(r[xk]) && fmt.ok(r[yk]));
        const fx = (cols[xk] || {}).format === 'pct' ? '.0%' : ',.2f', fy = (cols[yk] || {}).format === 'pct' ? '.0%' : ',.2f';
        charts.scatter(sEl, { x: pts.map((r) => r[xk]), y: pts.map((r) => r[yk]), text: pts.map((r) => r.ticker),
          size: pts.map((r) => (r.market_cap_usd ? Math.max(7, Math.min(34, Math.sqrt(r.market_cap_usd / 1e9) * 1.3)) : 8)),
          color: pts.map((r) => (fmt.ok(r.score) ? (r.score >= 67 ? 'up' : r.score >= 40 ? 'warn' : 'down') : 'ink4')) },
        { xfmt: fx, yfmt: fy, xtitle: (cols[xk] || {}).label, ytitle: (cols[yk] || {}).label });
        sEl.on && sEl.on('plotly_click', (ev) => { const p = ev.points && ev.points[0]; if (p && p.text) SQ.go('#/t/' + enc(p.text)); });
      };
      out.appendChild(ui.panel(null, sEl, { right: h('span', { style: { display: 'flex', gap: '6px', alignItems: 'center' } }, 'x', ui.select(numKeys, xk, (v) => { xk = v; drawMap(); }),
        'y', ui.select(numKeys, yk, (v) => { yk = v; drawMap(); })), cap: 'Bubble size = market cap; colour = quant score (green ≥ 67, red < 40). Click a bubble to open it.' }));
      drawMap();
      SQ.live.apply(out);
    }
    load();
  };

  // ─── Compare ──────────────────────────────────────────────────────────
  SQ.views.compare = async function (view, parts, params) {
    let syms = (params.s || 'NVDA,AMD,AVGO,TSM,SOXX').split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    let rng = params.r || '1Y';
    view.appendChild(pageHead('Compare', 'Performance, risk, valuation and correlation side by side (up to 12 symbols, any Yahoo ticker).'));
    const chips = h('div', { class: 'chips', style: { alignItems: 'center' } });
    const inp = h('input', { class: 'inp', placeholder: 'Add ticker…', style: { width: '130px' }, onkeydown: (e) => { if (e.key === 'Enter' && inp.value.trim()) { syms.push(inp.value.trim().toUpperCase()); inp.value = ''; go(); } } });
    view.appendChild(h('div', { class: 't-tools' }, chips, inp, ui.seg(['3M', '6M', 'YTD', '1Y', '2Y', '5Y', '10Y'], rng, (v) => { rng = v; go(); })));
    const out = h('div');
    view.appendChild(out);
    const go = () => { SQ.go(`#/compare?s=${enc(syms.join(','))}&r=${rng}`); };
    chips.innerHTML = '';
    syms.forEach((s) => chips.appendChild(h('span', { class: 'chip acc', style: { cursor: 'pointer' }, title: 'Remove', onclick: () => { syms = syms.filter((x) => x !== s); go(); } }, s + ' ✕')));
    ui.async(out, () => api(`/api/compare?symbols=${enc(syms.join(','))}&range=${rng}`), (b, d) => {
      const nEl = charts.div('chart tall'), dEl = charts.div('chart short');
      const names = Object.keys(d.normalized);
      b.appendChild(ui.panel(`Growth of 100 since ${fmt.date(d.start)}`, nEl));
      charts.lines(nEl, names.map((s) => ({ name: s, ...d.normalized[s], width: s === d.bench ? 1.2 : 1.8, dash: s === d.bench ? 'dot' : 'solid' })), { yfmt: ',.0f' });
      b.appendChild(h('div', { style: { height: '14px' } }));
      b.appendChild(ui.panel('Drawdown from peak', dEl));
      charts.lines(dEl, names.map((s) => ({ name: s, ...d.drawdowns[s], width: 1.2 })), { yfmt: '.0%' });
      b.appendChild(sec('Statistics'));
      b.appendChild(ui.panel(null, ui.table([{ key: 'symbol', label: 'Symbol', l: true, cls: 'sym' }, { key: 'total_return', label: 'Return', fmt: 'pct', sign: true },
        { key: 'cagr', label: 'CAGR', fmt: 'pct', sign: true }, { key: 'vol', label: 'Vol', fmt: 'pctu' }, { key: 'sharpe', label: 'Sharpe', fmt: 'num' },
        { key: 'sortino', label: 'Sortino', fmt: 'num' }, { key: 'max_drawdown', label: 'Max DD', fmt: 'pct', cls: 'down' }, { key: 'beta', label: 'Beta ' + d.bench, fmt: 'num' },
        { key: 'alpha', label: 'Alpha', fmt: 'pct', sign: true }, { key: 'up_capture', label: 'Up cap.', fmt: 'num' }, { key: 'down_capture', label: 'Down cap.', fmt: 'num' },
        { key: 'fpe', label: 'Fwd P/E', fmt: 'x' }, { key: 'ev_sales', label: 'EV/Sales', fmt: 'x' }, { key: 'gross_margin', label: 'Gross mgn', fmt: 'pctu' },
        { key: 'rev_growth', label: 'Rev growth', fmt: 'pct' }, { key: 'target_upside', label: 'Target upside', fmt: 'pct', sign: true }], d.stats,
      { sort: 'sharpe', onRow: (r) => SQ.go('#/t/' + enc(r.symbol)), csv: 'compare.csv' })));
      if (d.correlation && d.correlation.tickers) {
        const cEl = charts.div('chart');
        cEl.style.height = Math.max(260, 34 * d.correlation.tickers.length + 60) + 'px';
        b.appendChild(sec('Correlation of daily returns'));
        b.appendChild(ui.panel(null, cEl, { cap: `Average pairwise correlation ${fmt.num(d.correlation.avg_corr, 2)}. Names that move together diversify little.` }));
        charts.heatmap(cEl, { z: d.correlation.matrix, x: d.correlation.tickers, y: d.correlation.tickers }, { fmt: 'num', zmid: 0.5, zmin: 0, zmax: 1, colors: undefined, div: true });
      }
    }, 500);
  };

  // ─── Portfolio ────────────────────────────────────────────────────────
  SQ.views.portfolio = async function (view) {
    let p;
    try { p = await api('/api/portfolio'); } catch (e) { p = { holdings: [], benchmark: 'SPY' }; }
    view.appendChild(pageHead('Portfolio', 'Live value, risk decomposition, crisis replays, optimizers, efficient frontier, backtest and Monte Carlo. Holdings are saved on this device only.'));
    const tb = h('tbody');
    const ed = h('table', { class: 't holdings' }, h('thead', null, h('tr', null, ['Ticker', 'Shares', 'Cost / share (optional)', ''].map((x) => h('th', { class: 'l' }, x)))), tb);
    const row = (x = {}) => {
      const tr = h('tr', null,
        h('td', { class: 'l' }, h('input', { class: 'inp', value: x.ticker || '', placeholder: 'NVDA', 'data-k': 'ticker' })),
        h('td', { class: 'l' }, h('input', { class: 'inp', type: 'number', value: x.shares ?? '', step: 'any', 'data-k': 'shares' })),
        h('td', { class: 'l' }, h('input', { class: 'inp', type: 'number', value: x.cost ?? '', step: 'any', 'data-k': 'cost' })),
        h('td', { class: 'l' }, h('button', { class: 'btn sm', type: 'button', onclick: () => tr.remove() }, '✕')));
      tb.appendChild(tr);
    };
    (p.holdings || []).forEach(row);
    if (!(p.holdings || []).length) row();
    const bench = h('input', { class: 'inp', value: p.benchmark || 'SPY', style: { width: '90px' } });
    const maxw = h('input', { class: 'inp', type: 'number', value: p.max_weight ? Math.round((p.max_weight <= 1 ? p.max_weight * 100 : p.max_weight) * 10) / 10 : 35, /* stored as a fraction */ step: 5, style: { width: '80px' } });
    const read = () => ({ ...p, benchmark: bench.value.trim().toUpperCase() || 'SPY', max_weight: (parseFloat(maxw.value) || 35) / 100,
      holdings: Array.from(tb.querySelectorAll('tr')).map((tr) => {
        const g = (k) => tr.querySelector(`[data-k="${k}"]`).value;
        return { ticker: g('ticker').trim().toUpperCase(), shares: parseFloat(g('shares')), cost: g('cost') === '' ? null : parseFloat(g('cost')) };
      }).filter((x) => x.ticker && isFinite(x.shares)) });
    const out = h('div');
    const analyze = async () => {
      const body = read();
      try { await SQ.put('/api/portfolio', body); } catch (e) { /* snapshot or offline */ }
      if (SQ.static) { // web edition / Android app: the full analysis runs on this device
        ui.async(out, async () => SQ.quant.portfolio(await staticPortfolio(body), body), (b, d) => renderPortfolio(b, d, body), 300);
        return;
      }
      ui.async(out, () => SQ.post('/api/portfolio/analyze', body), (b, d) => renderPortfolio(b, d, body), 600);
    };
    const xlsx = async () => {
      try {
        const r = await fetch('/api/export/portfolio.xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(read()) });
        if (!r.ok) throw new Error('export failed');
        ui.saveBlob(await r.blob(), 'portfolio.xlsx');
      } catch (e) { ui.toast(e.message); }
    };
    view.appendChild(ui.panel('Holdings', h('div', null, ed, h('div', { class: 't-tools', style: { marginTop: '10px' } },
      h('button', { class: 'btn', type: 'button', onclick: () => row() }, '+ Add holding'),
      h('label', { class: 'field' }, h('span', null, 'Benchmark'), bench), h('label', { class: 'field' }, h('span', null, 'Max weight % (optimizers)'), maxw),
      h('button', { class: 'btn primary', type: 'button', onclick: analyze }, 'Save & analyze'),
      h('button', { class: 'btn', type: 'button', onclick: xlsx }, h('span', { html: dlIcon }), 'Excel'))),
    { cap: 'Foreign listings are converted to USD at live FX. Risk statistics use local-currency returns over the last 2-3 years.' }));
    view.appendChild(h('div', { style: { height: '16px' } }));
    view.appendChild(out);
    analyze();
  };

  function renderPortfolio(b, d, input) {
    const r = d.risk || {};
    (d.warnings || []).forEach((w) => b.appendChild(h('div', { class: 'note', style: { marginBottom: '10px' } }, w)));
    b.appendChild(ui.kpis([
      { label: 'Value (USD)', value: fmt.money(d.nav), sub: d.cash ? 'incl. cash ' + fmt.money(d.cash) : '' },
      { label: 'Today', value: fmt.money(d.day_change), cls: fmt.cls(d.day_change), sub: fmt.pct(d.day_change_pct, 2) },
      { label: 'Exp. return (hist.)', value: fmt.pct(r.exp_return) }, { label: 'Volatility', value: fmt.pctu(r.vol) },
      { label: 'Sharpe', value: fmt.num(r.sharpe, 2) }, { label: 'Beta vs ' + d.benchmark, value: fmt.num(r.beta, 2), sub: 'TE ' + fmt.pctu(r.tracking_error) },
      { label: '1-day VaR 95%', value: fmt.money(r.var95_value), sub: fmt.pctu(r.var95, 2) + ' · ES ' + fmt.money(r.es95_value) },
      { label: 'Max drawdown', value: fmt.pct(r.max_drawdown), cls: 'down' },
      { label: 'Diversification', value: fmt.num(r.diversification_ratio, 2), sub: 'effective N ' + fmt.num(r.effective_n, 1) },
    ]));
    b.appendChild(sec('Holdings & risk contribution'));
    const rc = Object.fromEntries((r.holdings || []).map((x) => [x.ticker, x]));
    const rows = d.rows.map((x) => ({ ...x, ...(rc[x.ticker] || {}), weight: x.weight }));
    const rcEl = charts.div('chart short');
    b.appendChild(h('div', { class: 'grid g-main' }, ui.panel(null, ui.table([{ key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'shares', label: 'Shares', fmt: 'num', d: 2 },
      { key: 'price', label: 'Price', fmt: 'price' }, { key: 'value', label: 'Value $', fmt: 'big' }, { key: 'weight', label: 'Weight', fmt: 'pctu' },
      { key: 'day_change_pct', label: 'Day', fmt: 'pct', d: 2, sign: true }, { key: 'pnl', label: 'P&L $', fmt: 'big', sign: true }, { key: 'pnl_pct', label: 'P&L %', fmt: 'pct', sign: true },
      { key: 'vol', label: 'Vol', fmt: 'pctu' }, { key: 'beta', label: 'Beta', fmt: 'num' }, { key: 'risk_contrib', label: 'Risk share', fmt: 'pctu' }],
    rows, { sort: 'value', onRow: (x) => SQ.go('#/t/' + enc(x.ticker)), csv: 'portfolio.csv' })),
    ui.panel('Weight vs share of risk', rcEl, { cap: 'A holding whose risk share far exceeds its weight dominates the portfolio\'s ups and downs.' })));
    charts.bars(rcEl, [{ name: 'Weight', x: rows.map((x) => x.ticker), y: rows.map((x) => x.weight), colors: 'ink4' }, { name: 'Risk share', x: rows.map((x) => x.ticker), y: rows.map((x) => x.risk_contrib), colors: 'accent' }], { yfmt: '.0%' });
    if (d.optimizers) {
      b.appendChild(sec('Optimizers & efficient frontier'));
      const fEl = charts.div('chart tall');
      const fr = d.frontier || {};
      const opt = Object.entries(d.optimizers).filter(([, v]) => v);
      const names = { equal: 'Equal weight', inverse_vol: 'Inverse vol', min_var: 'Min variance', max_sharpe: 'Max Sharpe', erc: 'Risk parity (ERC)', hrp: 'HRP', max_div: 'Max diversification' };
      b.appendChild(h('div', { class: 'grid g2' }, ui.panel('Efficient frontier (long-only)', fEl, { cap: 'Shrunk expected returns and Ledoit-Wolf covariance, 3 years of daily data. Dots: each optimizer; diamond: your current weights.' }),
        ui.panel('Suggested weights', ui.table([{ key: 't', label: 'Ticker', l: true, cls: 'sym' }, { key: 'current', label: 'Current', fmt: 'pctu', d: 0 }]
          .concat(opt.map(([k]) => ({ key: k, label: names[k] || k, fmt: 'pctu', d: 0 }))),
        Object.keys(d.weights).map((t) => Object.fromEntries([['t', t], ['current', d.weights[t]]].concat(opt.map(([k, v]) => [k, (v.weights || {})[t]])))))
          , { cap: opt.map(([k, v]) => `${names[k] || k}: return ${fmt.pct(v.exp_return)}, vol ${fmt.pctu(v.vol)}, Sharpe ${fmt.num(v.sharpe, 2)}`).join(' · ') })));
      const pts = fr.points || [];
      charts.plot(fEl, (t) => ({
        data: [{ type: 'scatter', mode: 'lines', name: 'Frontier', x: pts.map((x) => x.vol), y: pts.map((x) => x.ret), line: { color: t.accent, width: 2 }, hovertemplate: 'vol %{x:.1%} · ret %{y:.1%}<extra></extra>' },
          { type: 'scatter', mode: 'markers+text', name: 'Assets', x: (fr.assets || []).map((a) => a.vol), y: (fr.assets || []).map((a) => a.ret), text: (fr.assets || []).map((a) => a.ticker), textposition: 'top center', marker: { color: t.ink4, size: 8 }, textfont: { size: 10.5, color: t.ink3 } },
          { type: 'scatter', mode: 'markers+text', name: 'Optimizers', x: opt.map(([, v]) => v.vol), y: opt.map(([, v]) => v.exp_return), text: opt.map(([k]) => names[k] || k), textposition: 'bottom center', marker: { color: t.warn, size: 10 }, textfont: { size: 10.5, color: t.ink2 } },
          { type: 'scatter', mode: 'markers', name: 'Current', x: [r.vol], y: [r.exp_return], marker: { color: t.down, size: 14, symbol: 'diamond' } }],
        layout: { hovermode: 'closest', xaxis: { tickformat: '.0%', title: { text: 'volatility' } }, yaxis: { tickformat: '.0%', title: { text: 'expected return' } } },
      }));
    }
    const bt = d.backtest;
    if (bt && bt.equity) {
      b.appendChild(sec('Backtest of current weights (monthly rebalancing, 10 bp costs)'));
      const eEl = charts.div('chart');
      const s = bt.stats || {};
      b.appendChild(h('div', { class: 'grid g-main' }, ui.panel(null, eEl),
        ui.panel('Statistics', ui.kv([['CAGR', `${fmt.pct(s.cagr)} vs ${fmt.pct(s.bench_cagr)}`], ['Volatility', `${fmt.pctu(s.vol)} vs ${fmt.pctu(s.bench_vol)}`],
          ['Sharpe', `${fmt.num(s.sharpe, 2)} vs ${fmt.num(s.bench_sharpe, 2)}`], ['Max drawdown', `${fmt.pct(s.max_drawdown)} vs ${fmt.pct(s.bench_max_drawdown)}`],
          ['Turnover / year', fmt.pctu(s.turnover_ann)]]), { cap: 'In-sample: today\'s weights applied to the past. It shows how the mix behaved, not what it will earn.' })));
      charts.lines(eEl, [{ name: 'Portfolio', ...bt.equity, color: 'accent', width: 2 }, { name: d.benchmark, ...bt.benchmark, color: 'ink3', dash: 'dot' }], { yfmt: ',.2f' });
    }
    const st = d.stress && d.stress.rows ? d.stress.rows.filter((x) => x.covered) : [];
    if (st.length) {
      b.appendChild(sec('Crisis replay (current weights)'));
      b.appendChild(ui.panel(null, ui.table([{ key: 'name', label: 'Episode', l: true, txt: true }, { key: 'start', label: 'From', fmt: 'date' }, { key: 'end', label: 'To', fmt: 'date' },
        { key: 'return', label: 'Portfolio', fmt: 'pct', sign: true }, { key: 'value', label: 'On today\'s value', get: (x) => (fmt.ok(x.return) ? x.return * d.nav : null), fmt: 'big', sign: true },
        { key: 'max_drawdown', label: 'Worst point', fmt: 'pct', cls: 'down' }, { key: 'spy', label: 'S&P 500', get: (x) => (x.bench || {}).SPY, fmt: 'pct', sign: true }], st),
      { cap: `Holdings' actual returns during each window (history since ${fmt.date(d.history_start)}, only episodes every holding traded through).` }));
    }
    const mc = d.montecarlo;
    if (mc && mc.percentiles) {
      b.appendChild(sec('Next 12 months: Monte Carlo (block bootstrap, 10,000 paths)'));
      const mEl = charts.div('chart');
      const p = mc.percentiles, t = mc.terminal || {};
      b.appendChild(h('div', { class: 'grid g-main' }, ui.panel(null, mEl),
        ui.panel('Outcome distribution', ui.kv([['Median', fmt.money(t.median)], ['5th percentile', fmt.money(t.p5)], ['95th percentile', fmt.money(t.p95)],
          ['Chance of a loss', fmt.pctu(t.prob_loss, 0)], ['Chance of −20% or worse', fmt.pctu(t.prob_loss_20, 0)], ['Chance of +20% or better', fmt.pctu(t.prob_gain_20, 0)]]),
        { cap: 'Resamples 5-day blocks of the portfolio\'s own daily returns (keeps fat tails and volatility clustering). Drift = historical average.' })));
      charts.lines(mEl, [{ name: '95th', t: p.days, v: p.p95, color: 'up', width: 1, dash: 'dot' }, { name: '75th', t: p.days, v: p.p75, color: 'teal', width: 1 },
        { name: 'Median', t: p.days, v: p.p50, color: 'accent', width: 2 }, { name: '25th', t: p.days, v: p.p25, color: 'warn', width: 1 },
        { name: '5th', t: p.days, v: p.p5, color: 'down', width: 1, dash: 'dot' }], { yfmt: '$,.0f', xtitle: 'trading days ahead' });
    }
    if (d.correlation && d.correlation.tickers) {
      const cEl = charts.div('chart');
      cEl.style.height = Math.max(240, 32 * d.correlation.tickers.length + 60) + 'px';
      b.appendChild(sec('Correlation (1 year, clustered)'));
      b.appendChild(ui.panel(null, cEl));
      charts.heatmap(cEl, { z: d.correlation.matrix, x: d.correlation.tickers, y: d.correlation.tickers }, { fmt: 'num', zmid: 0.5, zmin: 0, zmax: 1 });
    }
    void input;
  }

  // ─── Offer & RSU simulator ────────────────────────────────────────────
  SQ.views.offer = async function (view, parts, params) {
    view.appendChild(pageHead('Offer & RSU value', 'What could an equity grant be worth at each vesting date? Monte Carlo on the company\'s own price history; compare up to three offers.'));
    const today = new Date().toISOString().slice(0, 10);
    const offers = [{ ticker: params.t || 'NVDA', kind: 'rsu', grant_value: 100000, start: today, years: 4, cliff_months: 12, frequency: 'quarterly', method: 'bootstrap', drift: 'zero' }];
    if (!params.t) offers.push({ ticker: 'AVGO', kind: 'rsu', grant_value: 100000, start: today, years: 4, cliff_months: 12, frequency: 'quarterly', method: 'bootstrap', drift: 'zero' });
    const forms = h('div', { class: 'grid g3' });
    const out = h('div');
    view.appendChild(forms);
    view.appendChild(h('div', { class: 't-tools', style: { margin: '12px 0' } },
      h('button', { class: 'btn', type: 'button', onclick: () => { if (offers.length < 3) { offers.push({ ...offers[offers.length - 1], ticker: '' }); drawForms(); } } }, '+ Add offer'),
      h('button', { class: 'btn primary', type: 'button', onclick: () => run() }, 'Simulate'),
      h('span', { class: 'dim', style: { fontSize: '12.5px' } }, 'Drift "zero" is the conservative default: no assumed growth, only the stock\'s own volatility.')));
    view.appendChild(out);
    function field(o, k, labelText, type = 'text', opts) {
      const el = opts ? ui.select(opts, o[k], (v) => { o[k] = v; }) : h('input', { class: 'inp', type, value: o[k] ?? '', step: 'any', oninput: (e) => { o[k] = type === 'number' ? (e.target.value === '' ? null : parseFloat(e.target.value)) : e.target.value.toUpperCase(); } });
      return h('label', { class: 'field' }, h('span', null, labelText), el);
    }
    function drawForms() {
      forms.innerHTML = '';
      offers.forEach((o, i) => forms.appendChild(ui.panel(`Offer ${i + 1}`, h('div', { class: 'form' },
        field(o, 'ticker', 'Company ticker'), field(o, 'kind', 'Grant type', 'text', [['rsu', 'RSUs'], ['option', 'Stock options']]),
        field(o, 'grant_value', 'Grant value $ (RSUs)', 'number'), field(o, 'units', 'or number of units', 'number'),
        field(o, 'grant_price', 'Grant price (blank = 30-day avg)', 'number'), field(o, 'strike', 'Option strike', 'number'),
        h('label', { class: 'field' }, h('span', null, 'Vesting start'), h('input', { class: 'inp', type: 'date', value: o.start, oninput: (e) => { o.start = e.target.value; } })),
        field(o, 'years', 'Vesting years', 'number'), field(o, 'cliff_months', 'Cliff (months)', 'number'),
        field(o, 'frequency', 'Then vests', 'text', [['monthly', 'monthly'], ['quarterly', 'quarterly'], ['semiannual', 'every 6 months'], ['annual', 'yearly']]),
        field(o, 'method', 'Model', 'text', [['bootstrap', 'Bootstrap (history)'], ['garch', 'GARCH-t'], ['gbm', 'Lognormal (GBM)']]),
        field(o, 'drift', 'Drift', 'text', [['zero', 'Zero (conservative)'], ['riskfree', 'Risk-free rate'], ['historical', 'Historical average']])),
      { right: offers.length > 1 ? h('button', { class: 'btn sm', type: 'button', onclick: () => { offers.splice(i, 1); drawForms(); } }, 'Remove') : null })));
    }
    drawForms();
    async function run() {
      out.innerHTML = '';
      const results = await Promise.all(offers.filter((o) => o.ticker).map((o) => (SQ.static ? staticOffer(o) : SQ.post('/api/offer', o)).then((r) => ({ ok: true, r })).catch((e) => ({ ok: false, e, o }))));
      const good = results.filter((x) => x.ok).map((x) => x.r);
      results.filter((x) => !x.ok).forEach((x) => out.appendChild(ui.error(`${x.o.ticker}: ${x.e.message}`)));
      if (!good.length) return;
      if (good.length > 1) {
        out.appendChild(sec('Side by side'));
        const cEl = charts.div('chart short');
        out.appendChild(ui.panel('Total value at the end of vesting', cEl, { cap: 'Bars: median; whiskers: 5th to 95th percentile.' }));
        charts.plot(cEl, (t) => ({
          data: [{ type: 'bar', x: good.map((g) => g.context.ticker), y: good.map((g) => (g.result.total || {}).p50), marker: { color: t.accent, opacity: 0.8 },
            error_y: { type: 'data', symmetric: false, array: good.map((g) => (g.result.total.p95 || 0) - (g.result.total.p50 || 0)), arrayminus: good.map((g) => (g.result.total.p50 || 0) - (g.result.total.p5 || 0)), color: t.ink3 },
            hovertemplate: '%{x}: median $%{y:,.0f}<extra></extra>' }],
          layout: { showlegend: false, yaxis: { tickformat: '$,.0f' } },
        }));
      }
      good.forEach((g) => out.appendChild(offerResult(g)));
    }
    run();
  };

  function offerResult(g) {
    const r = g.result || {}, c = g.context || {}, tot = r.total || {};
    const isOpt = (g.input.kind || 'rsu') === 'option';
    const box = h('div');
    box.appendChild(sec(`${c.ticker} · ${c.name || ''} · ${isOpt ? 'stock options' : 'RSUs'}`));
    box.appendChild(ui.kpis([
      isOpt ? { label: 'Black-Scholes value', value: fmt.money(r.bs_value_total), sub: fmt.price(r.bs_value_per_option) + ' per option' } : { label: 'Grant value', value: fmt.money(r.grant_value), sub: `${fmt.num(r.units, 1)} units at ${fmt.price(r.grant_price)}` },
      { label: 'Expected total', value: fmt.money(tot.mean), sub: isOpt ? '' : 'vs grant ' + fmt.pct(tot.expected_vs_grant) },
      { label: 'Median total', value: fmt.money(tot.p50) }, { label: '5% worst case', value: fmt.money(tot.p5), cls: 'down' }, { label: '5% best case', value: fmt.money(tot.p95), cls: 'up' },
      { label: isOpt ? 'Chance options end worthless' : 'Chance worth less than granted', value: fmt.pctu(isOpt ? (r.vests || []).slice(-1).map((v) => v.prob_underwater)[0] : tot.prob_below_grant_value, 0) },
      { label: 'Stock volatility (1Y)', value: fmt.pctu(c.vol_1y), sub: 'GARCH long-run ' + fmt.pctu(c.garch_long_run) },
      { label: 'Max drawdown (5Y)', value: fmt.pct(c.max_drawdown_5y), cls: 'down' },
    ]));
    const vests = r.vests || [];
    const el = charts.div('chart');
    box.appendChild(h('div', { style: { height: '12px' } }));
    box.appendChild(h('div', { class: 'grid g-main' }, ui.panel('Value of each vest', el, { cap: 'Bars: median; whiskers: 5th-95th percentile. Past vest dates use actual prices.' }),
      ui.panel('Schedule', ui.table([{ key: 'date', label: 'Vests', fmt: 'date' }, { key: 'fraction', label: 'Share', fmt: 'pctu', d: 1 },
        { key: isOpt ? 'p50' : 'p50', label: 'Median $', fmt: 'big' }, { key: 'p5', label: 'P5 $', fmt: 'big' }, { key: 'p95', label: 'P95 $', fmt: 'big' },
        { key: isOpt ? 'prob_underwater' : 'prob_below_grant', label: isOpt ? 'P(underwater)' : 'P(< grant)', fmt: 'pctu', d: 0 }], vests, { sort: 'date', desc: false, csv: `${c.ticker}-vesting.csv` }))));
    charts.plot(el, (t) => ({
      data: [{ type: 'bar', x: vests.map((v) => v.date), y: vests.map((v) => v.p50 ?? v.mean_intrinsic), marker: { color: vests.map((v) => (v.past ? t.ink4 : t.accent)), opacity: 0.8 },
        error_y: { type: 'data', symmetric: false, array: vests.map((v) => (v.p95 || 0) - (v.p50 || 0)), arrayminus: vests.map((v) => (v.p50 || 0) - (v.p5 || 0)), color: t.ink3 },
        hovertemplate: '%{x}: median $%{y:,.0f}<extra></extra>' }],
      layout: { showlegend: false, yaxis: { tickformat: '$,.0f' } },
    }));
    return box;
  }

  // ─── Published website: portfolio value and offer Monte Carlo in the browser ──
  const FX_SUB = { GBp: ['GBP', 100], GBX: ['GBP', 100], ILA: ['ILS', 100], ZAc: ['ZAR', 100] };
  async function staticPortfolio(p) {
    const hold = (p.holdings || []).filter((x) => x.ticker && fmt.ok(x.shares));
    if (!hold.length) throw new Error('Add at least one holding (ticker and number of shares).');
    const syms = hold.map((x) => x.ticker.toUpperCase());
    const q = await api('/api/quotes?symbols=' + encodeURIComponent(syms.join(',')));
    const curs = Array.from(new Set(syms.map((s) => (q[s] || {}).currency).filter((c) => c && c !== 'USD')));
    const fxSyms = curs.map((c) => (FX_SUB[c] ? FX_SUB[c][0] : c) + '=X');
    const fx = fxSyms.length ? await api('/api/quotes?symbols=' + encodeURIComponent(fxSyms.join(','))) : {};
    const toUsd = (c) => { if (!c || c === 'USD') return 1; const [b, d] = FX_SUB[c] || [c, 1]; const r = (fx[b + '=X'] || {}).price; return r ? 1 / (r * d) : null; };
    let total = 0, day = 0;
    const rows = hold.map((x) => {
      const s = x.ticker.toUpperCase(), qq = q[s] || {}, k = toUsd(qq.currency);
      const val = fmt.ok(qq.price) && k ? qq.price * x.shares * k : null;
      const dch = val != null && fmt.ok(qq.change) ? qq.change * x.shares * k : null;
      total += val || 0; day += dch || 0;
      return { ticker: s, shares: x.shares, price: qq.price, currency: qq.currency, value: val, day_change: dch, day_change_pct: qq.change_pct,
        pnl: val != null && fmt.ok(x.cost) ? val - x.cost * x.shares * k : null, pnl_pct: fmt.ok(x.cost) && fmt.ok(qq.price) ? qq.price / x.cost - 1 : null, missing: !q[s] };
    });
    rows.forEach((r) => { r.weight = r.value && total ? r.value / total : 0; });
    return { rows, total, day, day_pct: total - day ? day / (total - day) : null };
  }
  function renderStaticPortfolio(b, d) {
    const pnl = d.rows.reduce((a, r) => a + (r.pnl || 0), 0);
    b.appendChild(ui.kpis([{ label: 'Value (USD)', value: fmt.money(d.total) }, { label: 'Today', value: fmt.money(d.day), cls: fmt.cls(d.day), sub: fmt.pct(d.day_pct, 2) },
      { label: 'Unrealised P&L', value: d.rows.some((r) => fmt.ok(r.pnl)) ? fmt.money(pnl) : '–', cls: fmt.cls(pnl), sub: 'from your cost basis' }]));
    b.appendChild(h('div', { style: { height: '14px' } }));
    b.appendChild(ui.panel('Holdings', ui.table([{ key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'shares', label: 'Shares', fmt: 'num', d: 2 },
      { key: 'price', label: 'Price', fmt: 'price' }, { key: 'value', label: 'Value $', fmt: 'big' }, { key: 'weight', label: 'Weight', fmt: 'pctu' },
      { key: 'day_change_pct', label: 'Day', fmt: 'pct', d: 2, sign: true }, { key: 'pnl', label: 'P&L $', fmt: 'big', sign: true }, { key: 'pnl_pct', label: 'P&L %', fmt: 'pct', sign: true }],
    d.rows, { sort: 'value', onRow: (r) => SQ.go('#/t/' + enc(r.ticker)), csv: 'portfolio.csv' }),
    { cap: 'Holdings are saved on this device only. Risk decomposition, optimizers, crisis replays and Monte Carlo for the portfolio run in the local edition.' }));
  }

  function vestSchedule(start, years, cliffMonths, freq) {
    const step = { monthly: 1, quarterly: 3, semiannual: 6, annual: 12 }[freq] || 3, total = Math.round(years * 12);
    const d0 = new Date(start + 'T12:00:00'), add = (m) => { const d = new Date(d0); d.setMonth(d.getMonth() + m); return d.toISOString().slice(0, 10); };
    const out = [];
    const cliff = Math.min(Math.max(0, cliffMonths || 0), total);
    if (cliff > 0) out.push({ date: add(cliff), fraction: cliff / total });
    for (let m = (cliff > 0 ? cliff : 0) + step; m <= total; m += step) out.push({ date: add(m), fraction: step / total });
    const sum = out.reduce((a, v) => a + v.fraction, 0);
    if (out.length && Math.abs(sum - 1) > 1e-9) out[out.length - 1].fraction += 1 - sum;
    return out;
  }
  function pct(sorted, p) { if (!sorted.length) return null; const i = Math.min(sorted.length - 1, Math.max(0, Math.round(p * (sorted.length - 1)))); return sorted[i]; }
  function normCdf(x) { const t = 1 / (1 + 0.2316419 * Math.abs(x)), d = 0.3989423 * Math.exp(-x * x / 2); const pr = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - pr : pr; }
  async function staticOffer(o) {
    const sym = (o.ticker || '').toUpperCase();
    const ch = await api(`/api/ticker/${enc(sym)}/chart?range=10Y`);
    const t = ch.bars.t, c = ch.bars.c;
    const spot = c[c.length - 1];
    const lr = []; for (let i = Math.max(1, c.length - 1260); i < c.length; i++) if (c[i] > 0 && c[i - 1] > 0) lr.push(Math.log(c[i] / c[i - 1]));
    const mean = lr.reduce((a, v) => a + v, 0) / lr.length, sd = Math.sqrt(lr.reduce((a, v) => a + (v - mean) ** 2, 0) / (lr.length - 1));
    const drift = o.drift === 'historical' ? mean : o.drift === 'riskfree' ? 0.04 / 252 - sd * sd / 2 : -sd * sd / 2;
    const resid = lr.map((v) => v - mean);
    const today = new Date().toISOString().slice(0, 10);
    const sched = vestSchedule(o.start || today, +o.years || 4, +o.cliff_months || 12, o.frequency || 'quarterly');
    const avg30 = c.slice(-30).reduce((a, v) => a + v, 0) / Math.min(30, c.length);
    const grantPrice = fmt.ok(o.grant_price) ? +o.grant_price : avg30;
    const isOpt = (o.kind || 'rsu') === 'option';
    const units = fmt.ok(o.units) && o.units > 0 ? +o.units : isOpt ? 1000 : (+o.grant_value || 100000) / grantPrice;
    const strike = isOpt ? (fmt.ok(o.strike) ? +o.strike : spot) : null;
    const tdays = (d) => Math.max(0, Math.round((new Date(d + 'T12:00:00') - new Date(today + 'T12:00:00')) / 864e5 * 252 / 365));
    const steps = sched.map((v) => tdays(v.date)), P = 4000, block = 5;
    const model = SQ.quant.offerModel(o.method, lr, drift); // null = block bootstrap
    const vals = sched.map(() => new Float64Array(P)), tot = new Float64Array(P);
    const closeOn = (d) => { let k = -1; for (let i = 0; i < t.length; i++) { if (t[i] <= d) k = i; else break; } return k >= 0 ? c[k] : null; };
    for (let p = 0; p < P; p++) {
      let logS = Math.log(spot), day = 0, pos = 0, left = 0;  // block bootstrap: 5-day blocks of demeaned returns
      const st = model ? model.start() : null;
      const order = steps.map((s, i) => [s, i]).sort((a, b) => a[0] - b[0]);
      for (const [s, i] of order) {
        while (day < s) {
          if (model) { logS += model.step(st); day++; continue; }
          if (left === 0) { pos = Math.floor(Math.random() * (resid.length - block)); left = block; }
          logS += resid[pos] + drift; pos++; left--; day++;
        }
        const past = sched[i].date <= today, px = past ? closeOn(sched[i].date) || spot : Math.exp(logS);
        const v = isOpt ? Math.max(px - strike, 0) * units * sched[i].fraction : px * units * sched[i].fraction;
        vals[i][p] = v; tot[p] += v;
      }
    }
    const stat = (arr) => { const s = Array.from(arr).sort((a, b) => a - b); return { mean: s.reduce((a, v) => a + v, 0) / s.length, p5: pct(s, 0.05), p25: pct(s, 0.25), p50: pct(s, 0.5), p75: pct(s, 0.75), p95: pct(s, 0.95), s }; };
    const grantValue = units * grantPrice;
    const vests = sched.map((v, i) => {
      const st = stat(vals[i]);
      const out = { date: v.date, fraction: v.fraction, units: units * v.fraction, past: v.date <= today, mean: st.mean, p5: st.p5, p25: st.p25, p50: st.p50, p75: st.p75, p95: st.p95 };
      if (isOpt) { out.mean_intrinsic = st.mean; out.prob_underwater = st.s.filter((x) => x <= 0).length / P; }
      else out.prob_below_grant = st.s.filter((x) => x < grantValue * v.fraction).length / P;
      return out;
    });
    const T = stat(tot);
    const total = { mean: T.mean, p5: T.p5, p25: T.p25, p50: T.p50, p75: T.p75, p95: T.p95 };
    const result = { units, grant_price: grantPrice, grant_value: grantValue, spot, vests, total, method: model ? model.label : 'bootstrap (browser)', drift: o.drift || 'zero' };
    if (isOpt) {
      const vol = sd * Math.sqrt(252), Tm = +o.expiry_years || 10, r = 0.04;
      const d1 = (Math.log(spot / strike) + (r + vol * vol / 2) * Tm) / (vol * Math.sqrt(Tm)), d2 = d1 - vol * Math.sqrt(Tm);
      const bs = spot * normCdf(d1) - strike * Math.exp(-r * Tm) * normCdf(d2);
      Object.assign(result, { strike, vol, bs_value_per_option: bs, bs_value_total: bs * units });
    } else {
      total.prob_below_grant_value = T.s.filter((x) => x < grantValue).length / P;
      total.expected_vs_grant = T.mean / grantValue - 1;
    }
    const tail = c.slice(-1260);
    let pk = -Infinity, mdd = 0; tail.forEach((v) => { pk = Math.max(pk, v); mdd = Math.min(mdd, v / pk - 1); });
    const q = await api('/api/quotes?symbols=' + enc(sym)).catch(() => ({}));
    return { input: { ...o, ticker: sym }, schedule: sched, result,
      context: { ticker: sym, name: (q[sym] || {}).name, price: spot, currency: ch.currency, vol_1y: sd * Math.sqrt(252), garch_long_run: model && model.garch ? model.vol : null, max_drawdown_5y: mdd } };
  }

  // ─── Calendar ─────────────────────────────────────────────────────────
  SQ.views.calendar = async function (view) {
    view.appendChild(pageHead('Calendar', 'Earnings dates for the semiconductor universe and the wider market, and upcoming economic releases (Yahoo Finance).'));
    const out = h('div');
    view.appendChild(out);
    ui.async(out, () => api('/api/calendar'), (b, d) => {
      b.appendChild(ui.panel('Your universes: next 90 days (semiconductors, US large caps, global leaders)', ui.table([{ key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'name', label: 'Company', l: true, txt: true },
        { key: 'universe', label: 'Universe', l: true }, { key: 'sector', label: 'Sector', l: true }, { key: 'time', label: 'Date', render: (r) => fmt.dateTime(r.time) + (r.estimated ? ' <span class="dim">(est.)</span>' : '') },
        { key: 'days', label: 'In days', fmt: 'num', d: 0 }], d.universe || [], { sort: 'time', desc: false, onRow: (r) => SQ.go('#/t/' + enc(r.ticker) + '/analysts') })));
      b.appendChild(h('div', { style: { height: '14px' } }));
      b.appendChild(h('div', { class: 'grid g2' },
        ui.panel('All US earnings, next 3 weeks', ui.table([{ key: 'Symbol', label: 'Symbol', l: true, cls: 'sym' }, { key: 'Company', label: 'Company', l: true, txt: true },
          { key: 'Event Start Date', label: 'Date', render: (r) => fmt.dateTime(r['Event Start Date']) }, { key: 'Timing', label: 'When', l: true },
          { key: 'EPS Estimate', label: 'EPS est.', fmt: 'num' }, { key: 'Marketcap', label: 'Mkt cap', fmt: 'big' }], d.earnings || [],
        { sort: 'Marketcap', max: true, onRow: (r) => SQ.go('#/t/' + enc(r.Symbol)), rowClass: (r) => (r.in_universe ? 'self' : '') }), { cap: 'Highlighted: in one of your universes. BMO = before the open, AMC = after the close.' }),
        ui.panel('Economic calendar', ui.table([{ key: 'Event Time', label: 'Time', render: (r) => fmt.dateTime(r['Event Time']) }, { key: 'Region', label: 'Region', l: true },
          { key: 'Event', label: 'Event', l: true, txt: true }, { key: 'For', label: 'For', l: true }, { key: 'Expected', label: 'Expected', fmt: 'num' },
          { key: 'Last', label: 'Last', fmt: 'num' }, { key: 'Actual', label: 'Actual', fmt: 'num' }], d.economic || [], { sort: 'Event Time', desc: false, max: true }))));
    }, 500);
  };

  // ─── Settings & help ──────────────────────────────────────────────────
  SQ.views.settings = async function (view) {
    view.appendChild(pageHead('Settings & help'));
    const g = h('div', { class: 'grid g2' });
    view.appendChild(g);
    const s = SQ.settings;
    const num = (k) => h('input', { class: 'inp', type: 'number', min: 5, value: s[k], onchange: async (e) => {
      s[k] = parseInt(e.target.value, 10);
      try { Object.assign(SQ.settings, await SQ.put('/api/settings', { [k]: s[k] })); ui.toast('Saved'); SQ.live.tick(true); } catch (err) { ui.toast(err.message); }
    } });
    const sInfo = h('div', { class: 'dim mono', style: { fontSize: '12px', marginTop: '8px' } });
    const showStream = () => {
      const i = SQ.stream ? SQ.stream.info() : {};
      sInfo.textContent = !i.enabled ? 'Off: prices update with each refresh.'
        : i.connected ? `Connected · ${i.symbols} symbols · ${fmt.int(i.ticks)} trades received` + (i.last ? ' · last ' + new Date(i.last).toLocaleTimeString() : '')
          : 'Connecting…';
    };
    const streamTimer = setInterval(showStream, 2000);
    SQ.onCleanup(() => clearInterval(streamTimer));
    showStream();
    g.appendChild(ui.panel('Real-time prices', h('div', null,
      h('label', { style: { display: 'flex', gap: '10px', alignItems: 'center', cursor: 'pointer' } },
        h('input', { type: 'checkbox', checked: s.stream !== false, onchange: async (e) => {
          const v = e.target.checked;
          try { Object.assign(SQ.settings, await SQ.put('/api/settings', { stream: v })); } catch (err) { SQ.settings.stream = v; }
          if (SQ.stream) SQ.stream.restart();
          setTimeout(showStream, 300);
          ui.toast(v ? 'Streaming on' : 'Streaming off: prices update with each refresh');
        } }),
        h('span', null, 'Stream prices from Yahoo Finance (every trade, about once a second)')), sInfo),
    { cap: 'Prices, day changes, pre-market, after-hours and overnight prints and the intraday chart update as trades happen, for every symbol on screen. ' +
      'The connection goes straight from this device to Yahoo and pauses while the page is in the background. It uses mobile data while a market trades: turn it off to save data.' }));
    if (SQ.static) {
      const m = (SQ.st && SQ.st.meta) || {};
      g.appendChild(ui.panel('Data & updates', h('div', null, ui.kv([['Published', fmt.dateTime(m.built_at)], ['Companies with full analysis', String((m.full || []).length)],
        ['Quotes, heatmaps, screener, 1-day charts', 'every ~15 min in market hours'], ['Scores, longer charts, breadth', 'hourly'],
        ['Risk, volatility, options, factors, analysts', 'every 3 hours'], ['Fundamentals, ownership, filings', 'daily']]),
      h('div', { class: 't-tools', style: { marginTop: '10px' } }, h('button', { class: 'btn primary', type: 'button', onclick: SQ.install }, 'Install as an app'))),
      { cap: 'Prices stream in real time (see Real-time prices). The analytics come from the latest build; this page checks for a new one every minute. Exchange delays from Yahoo still apply.' }));
    }
    if (!SQ.static) g.appendChild(ui.panel('Refresh', h('div', { class: 'form' },
      h('label', { class: 'field' }, h('span', null, 'Quotes while a market is open (s)'), num('quote_refresh_seconds')),
      h('label', { class: 'field' }, h('span', null, 'Quotes while all are closed (s)'), num('closed_refresh_seconds')),
      h('label', { class: 'field' }, h('span', null, '1-minute chart refresh (s)'), num('intraday_refresh_seconds'))),
    { cap: 'One batched Yahoo request refreshes every visible quote. Daily bars are patched with the live quote on every read, so today\'s move is always included.' }));
    const wl = SQ.watchlists.lists || {};
    const ta = h('textarea', { class: 'inp', style: { width: '100%', height: '210px', padding: '8px', fontFamily: 'var(--mono)', fontSize: '12.5px' } },
      Object.entries(wl).map(([k, v]) => `${k}: ${v.join(', ')}`).join('\n'));
    g.appendChild(ui.panel('Watchlists', h('div', null, ta, h('div', { class: 't-tools', style: { marginTop: '8px' } },
      h('button', { class: 'btn primary', type: 'button', onclick: async () => {
        const out = {};
        ta.value.split('\n').forEach((line) => { const i = line.indexOf(':'); if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).split(/[,\s]+/).map((x) => x.trim().toUpperCase()).filter(Boolean); });
        try { SQ.watchlists.lists = await SQ.put('/api/watchlists', out); SQ.renderWatchlist(); ui.toast('Watchlists saved'); } catch (e) { ui.toast(e.message); }
      } }, 'Save watchlists'))), { cap: 'One list per line: <code>Name: TICK1, TICK2, …</code>. Right-click a sidebar row to remove it quickly.' }));
    const st = h('div');
    g.appendChild(ui.panel('Data & storage', st));
    ui.async(st, () => api('/api/status'), (b, d) => b.appendChild(ui.kv([['Version', d.version], ['Data source', 'Yahoo Finance via yfinance ' + ((d.data || {}).yfinance || '')],
      ['Saved in', d.home], ['Cache hits / misses', `${(d.data.cache || {}).hits} / ${(d.data.cache || {}).misses}`], ['Served stale (Yahoo throttled)', String((d.data.cache || {}).stale_served)],
      ['US market', (d.market || {}).message || '–']])), 120);
    g.appendChild(ui.panel('Share with a friend', h('div', { class: 'note' },
      h('p', null, h('b', null, 'Share a result: '), 'every company page has a ', h('b', null, 'Share'), ' button that saves one HTML file with all tabs (interactive charts, frozen numbers). It opens in any browser, no install needed. ', h('b', null, 'Excel'), ' saves the raw data.'),
      h('p', { style: { marginTop: '8px' } }, h('b', null, 'Share the tool: '), 'your friend needs Python 3.10+ and one command:'),
      h('pre', { class: 'mono', style: { background: 'var(--well)', padding: '10px', borderRadius: '7px', marginTop: '6px', whiteSpace: 'pre-wrap', fontSize: '12px' } },
        'pipx install "git+https://github.com/chennakeshavadasa/career-semi-quant.git#subdirectory=local"\nsemiquant'),
      h('p', { style: { marginTop: '8px' } }, 'Or send them the ', h('code', null, 'local'), ' folder: double-click ', h('code', null, 'start-windows.bat'), ' / ', h('code', null, 'start-mac.command'), ' / ', h('code', null, 'start-linux.sh'), '.'))));
    g.appendChild(ui.panel('Keyboard', ui.kv([['Search / jump to ticker', '/  or  Ctrl K'], ['Refresh now', 'R'], ['Toggle theme', 'T'], ['Market dashboard', 'G']])));
    g.appendChild(ui.panel('About the numbers', h('p', { class: 'note' },
      'Prices, fundamentals, estimates, options and ownership come from Yahoo Finance (exchange delays apply: US stocks are real-time on most venues, some foreign exchanges 15-20 min). ',
      'Every model is computed locally on your machine. Statistical models describe the past and are not forecasts or investment advice.')));
  };
})();
