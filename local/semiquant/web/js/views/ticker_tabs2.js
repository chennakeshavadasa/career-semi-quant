/* Ticker tabs: Fundamentals, Analysts & earnings, Ownership, Factors & regimes, Filings & news. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts } = SQ;
  const T = SQ.tabs;
  const enc = encodeURIComponent;
  const sec = ui.sec;
  const pick = (o, ...keys) => { for (const k of keys) if (o && o[k] != null) return o[k]; return null; };

  function loadInto(body, path, render, skel = 420) {
    const box = h('div');
    body.appendChild(box);
    ui.async(box, () => api(path), render, skel);
  }
  const label = (k) => String(k).replace(/_/g, ' ').replace(/\b(pct|yoy|ttm|roe|roa|roic|eps|ebitda|fcf|sbc|rnd|dso)\b/gi, (m) => m.toUpperCase()).replace(/^\w/, (c) => c.toUpperCase());

  // ─── Fundamentals ─────────────────────────────────────────────────────
  T.fundamentals = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/fundamentals`, (box, d) => {
    if (!d.available) { box.appendChild(ui.empty(d.message || 'No fundamentals for this symbol (ETFs and indices have none).')); return; }
    const v = d.valuation || {}, pz = d.piotroski || {}, az = d.altman_z || {}, rd = d.reverse_dcf || {}, dc = d.dcf || {}, as = d.assumptions || {};
    const price = (SQ.live.quotes[sym] || {}).price || (SQ.tickerState.quote || {}).price;
    box.appendChild(ui.kpis([
      { label: 'P/E ttm / fwd', value: `${fmt.x(v.pe_ttm)} / ${fmt.x(v.pe_fwd)}` }, { label: 'PEG', value: fmt.num(v.peg, 2) },
      { label: 'EV / sales', value: fmt.x(v.ev_sales) }, { label: 'EV / EBITDA', value: fmt.x(v.ev_ebitda) },
      { label: 'P / FCF', value: fmt.x(v.p_fcf), sub: 'FCF yield ' + fmt.pctu(v.fcf_yield) }, { label: 'Earnings yield', value: fmt.pctu(v.earnings_yield) },
      { label: 'Price / book', value: fmt.x(v.pb) }, { label: 'Shareholder yield', value: fmt.pctu(v.shareholder_yield), sub: `div ${fmt.pctu(v.dividend_yield, 2)} + buyback ${fmt.pctu(v.buyback_yield)}` },
      { label: 'Piotroski F-score', value: fmt.ok(pz.score) ? `${pz.score} / ${pz.max || 9}` : '–', cls: pz.score >= 7 ? 'up' : pz.score <= 3 ? 'down' : '', sub: 'financial strength' },
      { label: 'Altman Z', value: fmt.num(az.z, 2), cls: az.zone === 'safe' ? 'up' : az.zone === 'distress' ? 'down' : 'warn', sub: az.zone ? az.zone + ' zone' : '' },
      { label: 'Market-implied FCF growth', value: fmt.pct(rd.implied_growth), sub: 'reverse DCF, 10 years' },
      { label: 'DCF value / share', value: fmt.price(dc.per_share), sub: fmt.ok(dc.per_share) && price ? fmt.pct(dc.per_share / price - 1) + ' vs price' : '' },
    ]));
    if ((d.warnings || []).length) box.appendChild(h('p', { class: 'note warn', style: { marginTop: '8px' } }, d.warnings.join(' ')));

    // Derived metric charts
    let freq = 'q';
    const mg = h('div');
    box.appendChild(sec('Profitability, growth & efficiency'));
    box.appendChild(h('div', { class: 't-tools' }, ui.seg([['q', 'Quarterly'], ['a', 'Annual']], freq, (x) => { freq = x; drawDerived(); }),
      h('span', { class: 'dim', style: { fontSize: '12.5px' } }, 'Yahoo provides about 5 quarters and 4-5 fiscal years.')));
    box.appendChild(mg);
    function drawDerived() {
      const dm = freq === 'q' ? d.derived_q : d.derived_a;
      mg.innerHTML = '';
      if (!dm || !dm.periods) { mg.appendChild(ui.empty('No statement history.')); return; }
      const m = dm.metrics || {}, t = dm.periods;
      const g3 = h('div', { class: 'grid g3' });
      mg.appendChild(g3);
      const blocks = [
        ['Margins', [['gross_margin', 'Gross', 'accent'], ['operating_margin', 'Operating', 'teal'], ['net_margin', 'Net', 'violet'], ['fcf_margin', 'FCF', 'warn']], '.0%'],
        ['Returns on capital', [['roe', 'ROE', 'accent'], ['roic', 'ROIC', 'warn'], ['roa', 'ROA', 'teal']], '.0%'],
        ['Reinvestment & dilution', [['rnd_pct_revenue', 'R&D % revenue', 'accent'], ['sbc_pct_revenue', 'SBC % revenue', 'down'], ['capex_pct_revenue', 'Capex % revenue', 'teal'], ['share_change_yoy', 'Share count yoy', 'violet']], '.0%'],
      ];
      blocks.forEach(([title, keys, f]) => {
        const el = charts.div('chart short');
        g3.appendChild(ui.panel(title, el));
        charts.lines(el, keys.filter(([k]) => m[k] && m[k].some(fmt.ok)).map(([k, n, c]) => ({ name: n, t, v: m[k], color: c, mode: 'lines+markers' })), { yfmt: f, xtype: 'category' });
      });
      const rows = Object.entries(dm.latest || {}).map(([k, val]) => ({ metric: label(k), value: val, k }));
      const pctKeys = /margin|growth|pct|roe|roa|roic|change/;
      mg.appendChild(h('div', { style: { height: '14px' } }));
      mg.appendChild(ui.panel('Latest values', ui.kv(rows.map((r) => [r.metric, pctKeys.test(r.k) ? fmt.pct(r.value) : fmt.num(r.value, 2)]))));
    }
    drawDerived();

    // DCF: interactive two-stage model (same maths as the server's dcf()).
    box.appendChild(sec('Valuation: discounted cash flow'));
    const fcf0 = pick(as, 'fcf0', 'fcf'), nd = pick(as, 'net_debt') || 0, shares = pick(as, 'shares');
    const inputs = { growth: pick(as, 'growth') ?? 0.1, wacc: pick(as, 'wacc') ?? 0.1, tg: pick(as, 'terminal_growth') ?? 0.03, years: 10 };
    const out = h('div'), sens = charts.div('chart short');
    const dcfJS = (g, w, tg, n) => {
      if (!fmt.ok(fcf0) || !fmt.ok(shares) || fcf0 <= 0 || w <= tg) return null;
      let f = fcf0, pv = 0;
      for (let i = 1; i <= n; i++) {
        const gi = g + (tg - g) * (i - 1) / Math.max(1, n - 1);
        f *= 1 + gi; pv += f / Math.pow(1 + w, i);
      }
      const tv = f * (1 + tg) / (w - tg) / Math.pow(1 + w, n);
      return { ps: (pv + tv - nd) / shares, tvShare: tv / (pv + tv) };
    };
    const drawDcf = () => {
      const r = dcfJS(inputs.growth, inputs.wacc, inputs.tg, inputs.years);
      out.innerHTML = '';
      out.appendChild(ui.kv([['Fair value / share', r ? fmt.price(r.ps) : '–'], ['vs current price', r && price ? fmt.pct(r.ps / price - 1) : '–', r && price ? fmt.cls(r.ps / price - 1) : ''],
        ['Terminal value share', r ? fmt.pctu(r.tvShare, 0) : '–'], ['FCF (TTM, start)', fmt.money(fcf0)], ['Net debt', fmt.money(nd)], ['Shares', fmt.big(shares)]]));
      const ws = [inputs.wacc - 0.02, inputs.wacc - 0.01, inputs.wacc, inputs.wacc + 0.01, inputs.wacc + 0.02];
      const tgs = [inputs.tg - 0.01, inputs.tg - 0.005, inputs.tg, inputs.tg + 0.005, inputs.tg + 0.01];
      const z = ws.map((w) => tgs.map((tg) => { const x = dcfJS(inputs.growth, w, tg, inputs.years); return x && price ? x.ps / price - 1 : null; }));
      charts.heatmap(sens, { z, x: tgs.map((x) => 'g ' + fmt.pctu(x, 1)), y: ws.map((x) => 'WACC ' + fmt.pctu(x, 1)) }, { d: 0, margin: { l: 80, r: 6, t: 6, b: 30 } });
    };
    const num = (k, step) => h('input', { class: 'inp', type: 'number', step, value: (inputs[k] * (k === 'years' ? 1 : 100)).toFixed(k === 'years' ? 0 : 1),
      oninput: (e) => { const x = parseFloat(e.target.value); if (isFinite(x)) { inputs[k] = k === 'years' ? Math.round(x) : x / 100; drawDcf(); } } });
    box.appendChild(h('div', { class: 'grid g2' },
      ui.panel('Your assumptions', h('div', null, h('div', { class: 'form' },
        h('label', { class: 'field' }, h('span', null, 'FCF growth, year 1 (%)'), num('growth', 1)),
        h('label', { class: 'field' }, h('span', null, 'Discount rate / WACC (%)'), num('wacc', 0.5)),
        h('label', { class: 'field' }, h('span', null, 'Terminal growth (%)'), num('tg', 0.5)),
        h('label', { class: 'field' }, h('span', null, 'Years'), num('years', 1))), h('div', { style: { marginTop: '12px' } }, out)),
      { cap: `Two-stage DCF: growth fades linearly to the terminal rate. Defaults: WACC from CAPM (beta ${fmt.num(as.beta, 2)}), growth from ${as.growth_source || 'analyst / revenue growth'}. Reverse DCF: the market price implies <b>${fmt.pct(rd.implied_growth)}</b> initial FCF growth. ${rd.note || ''}` }),
      ui.panel('Sensitivity: upside vs price', sens, { cap: 'Rows = discount rate, columns = terminal growth, at your growth input.' })));
    drawDcf();

    // Scores
    box.appendChild(sec('Quality scores'));
    box.appendChild(h('div', { class: 'grid g2' },
      ui.panel(`Piotroski F-score: ${pz.score ?? '–'} / 9`, ui.table([{ key: 'name', label: 'Criterion', l: true, txt: true }, { key: 'pass', label: 'Pass', render: (r) => (r.pass == null ? '–' : r.pass ? '<span class="up">✓</span>' : '<span class="down">✗</span>') },
        { key: 'value', label: 'Latest', fmt: 'num', d: 3 }, { key: 'prior', label: 'Prior', fmt: 'num', d: 3 }], pz.criteria || []), { cap: '8-9 = strong, 0-2 = weak (Piotroski 2000). Uses the two latest fiscal years.' }),
      ui.panel(`Altman Z-score: ${fmt.num(az.z, 2)} (${az.zone || '–'})`, ui.kv(Object.entries(az.components || {}).map(([k, x]) => [label(k), fmt.num(x, 3)])),
        { cap: 'Z > 2.99 safe, 1.81-2.99 grey, < 1.81 distress (original manufacturing model).' })));

    // Statements
    box.appendChild(sec('Financial statements'));
    const tables = d.tables || {};
    const keys = Object.keys(tables);
    let cur = keys.find((k) => /income/i.test(k) && /q/i.test(k)) || keys[0];
    const stBox = h('div');
    const drawSt = () => {
      const t = tables[cur];
      stBox.innerHTML = '';
      if (!t || !t.rows) { stBox.appendChild(ui.empty('No data.')); return; }
      const cols = [{ key: 'item', label: 'Item', l: true, txt: true, nosort: true }].concat(t.periods.map((p, i) => ({ key: 'p' + i, label: p, fmt: 'big', nosort: true })));
      stBox.appendChild(ui.table(cols, t.rows.map((r) => Object.fromEntries([['item', r.item]].concat(r.values.map((x, i) => ['p' + i, x])))), { csv: `${sym}-${cur}.csv` }));
    };
    box.appendChild(ui.panel(null, stBox, { right: ui.seg(keys.map((k) => [k, label(k).replace(/ a$/i, ' (annual)').replace(/ q$/i, ' (quarterly)')]), cur, (k) => { cur = k; drawSt(); }),
      cap: `Values in ${d.financial_currency || d.currency || 'reporting currency'}.` }));
    drawSt();

    const vh = d.valuation_history;
    if (vh && vh.rows && vh.rows.length) {
      box.appendChild(sec('Valuation history (Yahoo)'));
      box.appendChild(ui.panel(null, ui.table([{ key: 'metric', label: 'Measure', l: true, txt: true, nosort: true }].concat(vh.columns.map((c, i) => ({ key: 'c' + i, label: c, nosort: true,
        render: (r) => { const x = r['c' + i]; return /cap|value/i.test(r.metric) ? fmt.big(x) : fmt.num(x, 2); } }))),
      vh.rows.map((r) => Object.fromEntries([['metric', r.metric]].concat(r.values.map((x, i) => ['c' + i, x])))))));
    }
    if ((d.peers || []).length > 1) {
      box.appendChild(sec(`Sector peers: ${d.sector}`));
      box.appendChild(ui.panel(null, ui.table([{ key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'name', label: 'Name', l: true, txt: true },
        { key: 'market_cap', label: 'Mkt cap', fmt: 'big' }, { key: 'pe', label: 'P/E', fmt: 'x' }, { key: 'fpe', label: 'Fwd P/E', fmt: 'x' }, { key: 'pb', label: 'P/B', fmt: 'x' },
        { key: 'change_52w', label: '52W chg', fmt: 'pct', sign: true }, { key: 'dividend_yield', label: 'Div yld', fmt: 'pctu', d: 2 }], d.peers,
      { onRow: (r) => SQ.go('#/t/' + enc(r.ticker) + '/fundamentals'), rowClass: (r) => (r.self ? 'self' : ''), sort: 'market_cap' }), { cap: 'Live quote multiples; market caps in each listing\'s currency.' }));
    }
  });

  // ─── Analysts & earnings ──────────────────────────────────────────────
  T.analysts = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/analysts`, (box, d) => {
    const t = d.targets || {};
    box.appendChild(ui.kpis([
      { label: 'Mean target', value: fmt.price(t.mean), sub: 'upside ' + fmt.pct(t.upside_mean), cls: '' },
      { label: 'Median target', value: fmt.price(t.median), sub: 'upside ' + fmt.pct(t.upside_median) },
      { label: 'High / low', value: `${fmt.price(t.high)} / ${fmt.price(t.low)}`, sub: `${fmt.pct(t.upside_high)} / ${fmt.pct(t.upside_low)}` },
      { label: 'Current price', value: fmt.price(d.price) },
      d.event_study ? { label: 'Avg earnings move', value: '±' + fmt.pctu(d.event_study.mean_abs_move), sub: `${d.event_study.n_events} reports, beat rate ${fmt.pctu(d.event_study.beat_rate, 0)}` } : null,
      fmt.ok(d.implied_event_move) ? { label: 'Options-implied next move', value: '±' + fmt.pctu(d.implied_event_move), sub: d.implied_vs_history ? 'vs history ×' + fmt.num(d.implied_vs_history.ratio, 2) : '' } : null,
    ]));
    const g = h('div', { class: 'grid g2' });
    box.appendChild(sec('Ratings & price targets'));
    box.appendChild(g);
    const recEl = charts.div('chart short');
    g.appendChild(ui.panel('Recommendation trend', recEl, { cap: 'Number of analysts per rating, this month and the three before.' }));
    const recs = (d.recommendations || []).slice().reverse();
    const per = recs.map((r) => ({ '0m': 'Now', '-1m': '1M ago', '-2m': '2M ago', '-3m': '3M ago' }[r.period] || r.period));
    charts.bars(recEl, [['strongBuy', 'Strong buy', 'up'], ['buy', 'Buy', 'teal'], ['hold', 'Hold', 'ink4'], ['sell', 'Sell', 'warn'], ['strongSell', 'Strong sell', 'down']]
      .map(([k, n, c]) => ({ name: n, x: per, y: recs.map((r) => r[k] || 0), colors: c })), { barmode: 'stack', yfmt: ',.0f' });
    const tgEl = charts.div('chart short');
    g.appendChild(ui.panel('Price target range', tgEl));
    if (fmt.ok(t.low) && fmt.ok(t.high)) {
      charts.plot(tgEl, (th) => ({
        data: [{ type: 'scatter', mode: 'lines', x: [t.low, t.high], y: ['Targets', 'Targets'], line: { color: th.ruleStrong, width: 10 }, hoverinfo: 'skip', showlegend: false },
          { type: 'scatter', mode: 'markers+text', x: [t.low, t.mean, t.high], y: ['Targets', 'Targets', 'Targets'], text: ['low', 'mean', 'high'], textposition: 'top center',
            marker: { size: 12, color: [th.down, th.accent, th.up] }, showlegend: false, hovertemplate: '%{text}: %{x:,.2f}<extra></extra>' },
          { type: 'scatter', mode: 'markers+text', x: [d.price], y: ['Targets'], text: ['price'], textposition: 'bottom center', marker: { size: 14, symbol: 'diamond', color: th.ink }, showlegend: false, hovertemplate: 'price %{x:,.2f}<extra></extra>' }],
        layout: { hovermode: 'closest', yaxis: { visible: false }, xaxis: { tickformat: ',.0f' }, margin: { l: 10, r: 10, t: 30, b: 30 } },
      }));
    }
    const up = d.upgrades || [];
    if (up.length) {
      box.appendChild(ui.panel('Latest rating changes', ui.table([
        { key: 'GradeDate', label: 'Date', render: (r) => fmt.date(r.GradeDate) }, { key: 'Firm', label: 'Firm', l: true, txt: true },
        { key: 'Action', label: 'Action', l: true, render: (r) => `<span class="${r.Action === 'up' ? 'up' : r.Action === 'down' ? 'down' : ''}">${{ up: 'Upgrade', down: 'Downgrade', main: 'Maintain', init: 'Initiate', reit: 'Reiterate' }[r.Action] || r.Action || ''}</span>` },
        { key: 'FromGrade', label: 'From', l: true }, { key: 'ToGrade', label: 'To', l: true },
        { key: 'priorPriceTarget', label: 'Old PT', fmt: 'price' }, { key: 'currentPriceTarget', label: 'New PT', fmt: 'price' },
        { key: 'pt_chg', label: 'PT change', get: (r) => (r.priorPriceTarget ? r.currentPriceTarget / r.priorPriceTarget - 1 : null), fmt: 'pct', sign: true }], up,
      { max: true, csv: `${sym}-rating-changes.csv` })));
    }
    box.appendChild(sec('Consensus estimates & revisions'));
    const estCols = [{ key: 'label', label: 'Period', l: true, txt: true, nosort: true }, { key: 'avg', label: 'Average', fmt: 'num', nosort: true }, { key: 'low', label: 'Low', fmt: 'num', nosort: true },
      { key: 'high', label: 'High', fmt: 'num', nosort: true }, { key: 'yearAgoEps', label: 'Year ago', fmt: 'num', nosort: true }, { key: 'numberOfAnalysts', label: 'Analysts', fmt: 'int', nosort: true },
      { key: 'growth', label: 'Growth', fmt: 'pct', sign: true, nosort: true }];
    const revCols = estCols.map((c) => (c.key === 'yearAgoEps' ? { ...c, key: 'yearAgoRevenue', label: 'Year ago', fmt: 'big' } : ['avg', 'low', 'high'].includes(c.key) ? { ...c, fmt: 'big' } : c));
    box.appendChild(h('div', { class: 'grid g2' }, ui.panel('EPS estimates', ui.table(estCols, d.earnings_estimate || [])), ui.panel('Revenue estimates', ui.table(revCols, d.revenue_estimate || []))));
    const tr = d.eps_trend || [];
    if (tr.length) {
      box.appendChild(h('div', { style: { height: '14px' } }));
      box.appendChild(ui.panel('EPS estimate trend (revisions)', ui.table([{ key: 'label', label: 'Period', l: true, txt: true, nosort: true },
        { key: '90daysAgo', label: '90 days ago', fmt: 'num', nosort: true }, { key: '60daysAgo', label: '60 days ago', fmt: 'num', nosort: true },
        { key: '30daysAgo', label: '30 days ago', fmt: 'num', nosort: true }, { key: '7daysAgo', label: '7 days ago', fmt: 'num', nosort: true },
        { key: 'current', label: 'Now', fmt: 'num', nosort: true }, { key: 'rev_30d', label: '30d revision', fmt: 'pct', d: 2, sign: true, nosort: true },
        { key: 'rev_90d', label: '90d revision', fmt: 'pct', d: 2, sign: true, nosort: true }], tr),
      { cap: 'Rising estimates (positive revisions) are one of the most persistent return signals in equities (earnings-revision momentum).' }));
    }
    const es = d.event_study;
    box.appendChild(sec('Earnings history & event study'));
    const hist = (d.history || []).filter((r) => r['Reported EPS'] != null).slice(0, 16).reverse();
    const ehEl = charts.div('chart short');
    const caarEl = charts.div('chart short');
    box.appendChild(h('div', { class: 'grid g2' }, ui.panel('EPS: estimate vs reported', ehEl, { cap: 'Labels show the surprise.' }),
      ui.panel('Average path around reports', caarEl, { cap: 'Cumulative abnormal return (market model vs S&P 500) from 5 days before to 20 after, split by beats and misses. A drift after day 1 is post-earnings-announcement drift.' })));
    const xd = hist.map((r) => fmt.dateShort(r['Earnings Date']) + " '" + String(r['Earnings Date']).slice(2, 4));
    charts.bars(ehEl, [{ name: 'Estimate', x: xd, y: hist.map((r) => r['EPS Estimate']), colors: 'ink4' },
      { name: 'Reported', x: xd, y: hist.map((r) => r['Reported EPS']), colors: hist.map((r) => (r['Surprise(%)'] >= 0 ? 'up' : 'down')), text: hist.map((r) => (fmt.ok(r['Surprise(%)']) ? (r['Surprise(%)'] > 0 ? '+' : '') + r['Surprise(%)'].toFixed(1) + '%' : '')) }], { yfmt: ',.2f' });
    if (es && es.caar) {
      charts.lines(caarEl, [{ name: 'Beats', t: es.caar.days, v: es.caar.beat, color: 'up' }, { name: 'Misses', t: es.caar.days, v: es.caar.miss, color: 'down' },
        { name: 'All', t: es.caar.days, v: es.caar.all, color: 'ink3', dash: 'dot' }], { yfmt: '.1%', xtitle: 'trading days from report',
        shapes: [{ type: 'line', x0: 0, x1: 0, yref: 'paper', y0: 0, y1: 1 }] });
      box.appendChild(h('div', { style: { height: '14px' } }));
      box.appendChild(ui.kpis([
        { label: 'Mean |move| on report', value: fmt.pctu(es.mean_abs_move), sub: 'median ' + fmt.pctu(es.median_abs_move) },
        { label: 'Beat rate', value: fmt.pctu(es.beat_rate, 0), sub: es.n_events + ' reports' },
        { label: 'Avg move on beats', value: fmt.pct(es.avg_move_beat), cls: fmt.cls(es.avg_move_beat) },
        { label: 'Avg move on misses', value: fmt.pct(es.avg_move_miss), cls: fmt.cls(es.avg_move_miss) },
        { label: 'Drift after beats (2-20d)', value: fmt.pct((es.drift_beat || {}).mean), sub: 't = ' + fmt.num((es.drift_beat || {}).t, 2) },
        { label: 'Drift after misses (2-20d)', value: fmt.pct((es.drift_miss || {}).mean), sub: 't = ' + fmt.num((es.drift_miss || {}).t, 2) },
      ]));
      box.appendChild(h('div', { style: { height: '14px' } }));
      box.appendChild(ui.panel('Every report', ui.table([{ key: 'date', label: 'Report', fmt: 'date' }, { key: 'timing', label: 'When', l: true },
        { key: 'eps_est', label: 'EPS est.', fmt: 'num' }, { key: 'eps_act', label: 'EPS act.', fmt: 'num' }, { key: 'surprise_pct', label: 'Surprise', render: (r) => (fmt.ok(r.surprise_pct) ? `<span class="${fmt.cls(r.surprise_pct)}">${r.surprise_pct > 0 ? '+' : ''}${r.surprise_pct.toFixed(1)}%</span>` : '–') },
        { key: 'reaction', label: 'Day move', fmt: 'pct', sign: true }, { key: 'abnormal', label: 'Abnormal', fmt: 'pct', sign: true },
        { key: 'car_2_20', label: 'Drift 2-20d', fmt: 'pct', sign: true }], es.events || [], { max: true, csv: `${sym}-earnings.csv` })));
    } else caarEl.appendChild(ui.empty('Not enough earnings history.'));
  });

  // ─── Ownership ────────────────────────────────────────────────────────
  T.ownership = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/ownership`, (box, d) => {
    const m = d.major || {}, s = d.short || {}, is = d.insider_summary || {};
    box.appendChild(ui.kpis([
      { label: 'Insiders hold', value: fmt.pctu(m.insidersPercentHeld, 2) }, { label: 'Institutions hold', value: fmt.pctu(m.institutionsPercentHeld, 1), sub: fmt.int(m.institutionsCount) + ' institutions' },
      { label: 'Short % of float', value: fmt.pctu(s.pct_float, 2), sub: 'as of ' + fmt.date(s.date) }, { label: 'Days to cover', value: fmt.num(s.days_to_cover, 1) },
      { label: 'Short interest change', value: fmt.pct(s.change_mom), cls: fmt.cls(-(s.change_mom || 0)), sub: 'vs prior month' },
      { label: 'Insider net (6M)', value: fmt.money((is['6M'] || {}).net_value), cls: fmt.cls((is['6M'] || {}).net_value), sub: `${(is['6M'] || {}).buys ?? 0} buys · ${(is['6M'] || {}).sells ?? 0} sells` },
    ]));
    box.appendChild(sec('Insider activity'));
    const sumRows = Object.entries(is).map(([k, v]) => ({ period: k, ...v }));
    box.appendChild(h('div', { class: 'grid g-main' },
      ui.panel('Transactions (Form 4)', ui.table([{ key: 'date', label: 'Date', fmt: 'date' }, { key: 'insider', label: 'Insider', l: true, txt: true },
        { key: 'position', label: 'Role', l: true, txt: true }, { key: 'kind', label: 'Type', l: true, render: (r) => `<span class="${r.kind === 'buy' ? 'up' : r.kind === 'sell' ? 'down' : 'dim'}">${r.kind}</span>` },
        { key: 'shares', label: 'Shares', fmt: 'big' }, { key: 'value', label: 'Value', fmt: 'big' }, { key: 'text', label: 'Detail', l: true, txt: true }], d.insider_transactions || [],
      { max: true, csv: `${sym}-insiders.csv` })),
      ui.panel('Net insider flow', ui.table([{ key: 'period', label: 'Window', l: true }, { key: 'buys', label: 'Buys', fmt: 'int' }, { key: 'sells', label: 'Sells', fmt: 'int' },
        { key: 'net_value', label: 'Net $', fmt: 'big', sign: true }], sumRows), { cap: 'Open-market purchases are a stronger signal than sales (insiders sell for many reasons: taxes, diversification, 10b5-1 plans).' })));
    box.appendChild(sec('Largest holders'));
    const hcols = [{ key: 'Holder', label: 'Holder', l: true, txt: true }, { key: 'pctHeld', label: '% held', fmt: 'pctu', d: 2 }, { key: 'Shares', label: 'Shares', fmt: 'big' },
      { key: 'Value', label: 'Value', fmt: 'big' }, { key: 'pctChange', label: 'Change', fmt: 'pct', sign: true }, { key: 'Date Reported', label: 'Reported', fmt: 'date' }];
    box.appendChild(h('div', { class: 'grid g2' }, ui.panel('Institutions (13F)', ui.table(hcols, d.institutional || [], { sort: 'pctHeld' })),
      ui.panel('Mutual funds', ui.table(hcols, d.mutualfund || [], { sort: 'pctHeld' }))));
    if ((d.insider_purchases || []).length) {
      box.appendChild(h('div', { style: { height: '14px' } }));
      const cols = Object.keys(d.insider_purchases[0]).map((k, i) => ({ key: k, label: k, l: i === 0, txt: i === 0, fmt: i ? 'num' : undefined, d: 0 }));
      box.appendChild(ui.panel('Insider purchases summary (last 6 months, Yahoo)', ui.table(cols, d.insider_purchases)));
    }
  });

  // ─── Factors & regimes ────────────────────────────────────────────────
  T.factors = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/factors`, (box, d) => {
    const st = d.style || {}, mc = d.macro || {}, rg = d.regime || {};
    box.appendChild(ui.kpis([
      { label: 'Explained by factors (R²)', value: fmt.pctu(st.r2, 0), sub: 'style model, 2 years daily' },
      { label: 'Stock-specific risk', value: fmt.pctu(st.idio_share, 0), sub: 'idio vol ' + fmt.pctu(st.idio_vol_ann) },
      { label: 'Alpha (ann.)', value: fmt.pct(st.alpha_ann), cls: fmt.cls(st.alpha_ann), sub: 't = ' + fmt.num(st.alpha_t, 2) },
      { label: 'Current regime', value: rg.current_label || '–', cls: rg.current_label === 'Turbulent' ? 'down' : 'up', sub: (rg.current_probs || []).map((p, i) => ((rg.states || [])[i] || {}).label + ' ' + fmt.pctu(p, 0)).join(' · ') },
    ]));
    box.appendChild(sec('What drives this stock'));
    const fEl = charts.div('chart short'), mEl = charts.div('chart short');
    const fr = st.factors || [], mr = mc.factors || [];
    box.appendChild(h('div', { class: 'grid g2' },
      ui.panel('Style factor betas (ETF long-short spreads)', h('div', null, fEl, ui.table([{ key: 'name', label: 'Factor', l: true, txt: true }, { key: 'beta', label: 'Beta', fmt: 'num', d: 2 },
        { key: 't', label: 't (Newey-West)', fmt: 'num', d: 1 }, { key: 'contribution', label: 'Share of variance', fmt: 'pctu', d: 0 }], fr)),
      { cap: 'Market = SPY; Semis = SOXX − SPY; Size = IWM − SPY; Value = IWD − IWF; Momentum = MTUM − SPY; Quality = QUAL − SPY; Low vol = USMV − SPY. |t| > 2 is significant.' }),
      ui.panel('Macro sensitivities', h('div', null, mEl, ui.table([{ key: 'name', label: 'Factor', l: true, txt: true }, { key: 'beta', label: 'Beta', fmt: 'num', d: 4 },
        { key: 't', label: 't', fmt: 'num', d: 1 }], mr)), { cap: 'Daily return per unit move: S&P 500, US dollar and oil per 1% return; 10-year yield per 1 bp; VIX per 1 point.' })));
    charts.bars(fEl, { x: fr.map((f) => f.name), y: fr.map((f) => f.beta), colors: fr.map((f) => (Math.abs(f.t || 0) >= 2 ? (f.beta >= 0 ? 'accent' : 'down') : 'ink4')) }, { yfmt: '.2f' });
    charts.bars(mEl, { x: mr.map((f) => f.name), y: mr.map((f) => f.t), colors: mr.map((f) => (Math.abs(f.t || 0) >= 2 ? (f.t >= 0 ? 'up' : 'down') : 'ink4')), name: 't-stat' }, { yfmt: '.1f', ytitle: 't-stat',
      shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 2, y1: 2 }, { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: -2, y1: -2 }] });
    const rb = d.rolling;
    if (rb && rb.t) {
      box.appendChild(sec('Rolling factor betas (126-day window)'));
      const rEl = charts.div('chart');
      box.appendChild(ui.panel(null, rEl, { cap: 'Style drift: a stable profile means the historical betas are a fair guide; big swings mean they are not.' }));
      charts.lines(rEl, Object.keys(rb).filter((k) => !['t', 'window'].includes(k)).map((k) => ({ name: k, t: rb.t, v: rb[k] })), { yfmt: '.2f' });
    }
    box.appendChild(sec('Volatility regimes (hidden Markov model)'));
    const pEl = charts.div('chart short');
    const states = rg.states || [];
    box.appendChild(h('div', { class: 'grid g-main' },
      ui.panel('Probability of the turbulent state', pEl, { cap: 'Two-state Gaussian HMM on 5 years of daily returns (Baum-Welch fit, smoothed probabilities).' }),
      ui.panel('States', h('div', null, ui.table([{ key: 'label', label: 'State', l: true, txt: true }, { key: 'mean_ann', label: 'Return (ann.)', fmt: 'pct' },
        { key: 'vol_ann', label: 'Vol (ann.)', fmt: 'pctu' }, { key: 'share', label: 'Time spent', fmt: 'pctu', d: 0 }, { key: 'expected_duration_days', label: 'Avg length (days)', fmt: 'num', d: 0 }], states),
      rg.transition ? h('p', { class: 'note', style: { marginTop: '8px' } }, 'Daily transition probabilities: ' + rg.transition.map((r, i) => `${(states[i] || {}).label} stays ${fmt.pctu(r[i], 1)}`).join(', ') + '.') : null))));
    if (rg.probs && rg.probs.t) charts.lines(pEl, [{ name: 'P(turbulent)', t: rg.probs.t, v: rg.probs.p.map((x) => x[x.length - 1]), color: 'down', fill: 'tozeroy', fillcolor: 'rgba(' + charts.theme().downRgb + ',.1)', width: 1 }], { yfmt: '.0%', legend: false });
    const pr = d.peers;
    if (pr && pr.peers) {
      box.appendChild(sec('Closest peers by daily correlation (1 year)'));
      box.appendChild(ui.panel(null, ui.table([{ key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'corr', label: 'Correlation', fmt: 'num', d: 2, render: (r) => `${fmt.num(r.corr, 2)} <span class="bar" style="width:${Math.max(0, r.corr) * 80}px"></span>` },
        { key: 'beta', label: `Beta to ${sym}`, fmt: 'num', d: 2 }], pr.peers, { onRow: (r) => SQ.go('#/t/' + enc(r.ticker)) })));
    }
  });

  // ─── Filings & news ───────────────────────────────────────────────────
  T.events = (body, sym) => {
    const g = h('div', { class: 'grid g2' });
    body.appendChild(g);
    const nb = h('div'), fb = h('div');
    g.appendChild(nb); g.appendChild(fb);
    ui.async(nb, () => api(`/api/ticker/${enc(sym)}/news?count=40`), (b, items) => b.appendChild(ui.panel('News', SQ.newsList(items))), 400);
    ui.async(fb, () => api(`/api/ticker/${enc(sym)}/events`), (b, d) => {
      b.appendChild(ui.panel('SEC filings', ui.table([{ key: 'date', label: 'Date', fmt: 'date' }, { key: 'type', label: 'Form', l: true },
        { key: 'title', label: 'Title', l: true, txt: true, render: (r) => `<a href="${SQ.esc(r.url)}" target="_blank" rel="noopener">${SQ.esc(r.title || r.type)}</a>` }], d.filings || [], { max: true })));
      const cal = d.calendar || {};
      if (Object.keys(cal).length) { b.appendChild(h('div', { style: { height: '14px' } })); b.appendChild(ui.panel('Calendar', ui.kv(Object.entries(cal).map(([k, v]) => [k, String(v)])))); }
      if (d.dividends && d.dividends.t && d.dividends.t.length) {
        const el = charts.div('chart short');
        b.appendChild(h('div', { style: { height: '14px' } }));
        b.appendChild(ui.panel('Dividends per share', el));
        charts.bars(el, { x: d.dividends.t, y: d.dividends.v, colors: 'accent' }, { yfmt: ',.3f' });
      }
      if (d.splits && d.splits.t && d.splits.t.length) {
        b.appendChild(h('div', { style: { height: '14px' } }));
        b.appendChild(ui.panel('Stock splits', ui.kv(d.splits.t.map((t, i) => [fmt.date(t), d.splits.v[i] + ' : 1']))));
      }
    }, 400);
  };
})();
