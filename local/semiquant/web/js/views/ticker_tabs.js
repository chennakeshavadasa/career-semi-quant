/* Ticker tabs: Risk & returns, Volatility, Tail risk & stress, Options. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts } = SQ;
  const T = SQ.tabs;
  const enc = encodeURIComponent;
  const sec = ui.sec;

  function loadInto(body, path, render, skel = 420) {
    const box = h('div');
    body.appendChild(box);
    ui.async(box, () => api(path), render, skel);
  }

  // ─── Risk & returns ───────────────────────────────────────────────────
  T.risk = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/risk`, (box, d) => {
    let win = d.stats['3Y'] ? '3Y' : Object.keys(d.stats)[0], vs = 'vs_spy';
    const kp = h('div'), cmp = h('div');
    const drawStats = () => {
      const s = (d.stats[win] || {})[vs] || {};
      const bn = vs === 'vs_spy' ? 'S&P 500' : 'SOXX';
      kp.innerHTML = '';
      kp.appendChild(ui.kpis([
        { label: 'Total return', value: fmt.pct(s.total_return), cls: fmt.cls(s.total_return), sub: `${fmt.date(s.start)} → ${fmt.date(s.end)}` },
        { label: 'CAGR', value: fmt.pct(s.cagr), cls: fmt.cls(s.cagr), sub: `${bn} ${fmt.pct(s.bench_cagr)}` },
        { label: 'Volatility', value: fmt.pctu(s.vol), sub: `${bn} ${fmt.pctu(s.bench_vol)}` },
        { label: 'Sharpe', value: fmt.num(s.sharpe, 2), sub: `${bn} ${fmt.num(s.bench_sharpe, 2)}` },
        { label: 'Sortino', value: fmt.num(s.sortino, 2) }, { label: 'Calmar', value: fmt.num(s.calmar, 2) },
        { label: 'Max drawdown', value: fmt.pct(s.max_drawdown), cls: 'down', sub: `${bn} ${fmt.pct(s.bench_max_drawdown)}` },
        { label: 'Current drawdown', value: fmt.pct(s.current_drawdown), cls: fmt.cls(s.current_drawdown) },
        { label: 'Beta', value: fmt.num(s.beta, 2), sub: 'vs ' + bn }, { label: 'Alpha (ann.)', value: fmt.pct(s.alpha), cls: fmt.cls(s.alpha), sub: 'Jensen' },
        { label: 'Correlation', value: fmt.num(s.correlation, 2), sub: 'R² ' + fmt.num(s.r2, 2) },
        { label: 'Tracking error', value: fmt.pctu(s.tracking_error) }, { label: 'Information ratio', value: fmt.num(s.information_ratio, 2) },
        { label: 'Up / down capture', value: `${fmt.num(s.up_capture, 2)} / ${fmt.num(s.down_capture, 2)}` },
        { label: 'VaR 95% (1-day)', value: fmt.pctu(s.var95), sub: 'CVaR ' + fmt.pctu(s.cvar95) },
        { label: 'Skew / ex. kurtosis', value: `${fmt.num(s.skew, 2)} / ${fmt.num(s.kurtosis, 1)}` },
        { label: 'Best / worst day', value: `${fmt.pct(s.best_day)} / ${fmt.pct(s.worst_day)}` },
        { label: 'Up days', value: fmt.pctu(s.pct_up_days, 0) }, { label: 'Ulcer index', value: fmt.num(s.ulcer_index, 2) },
        { label: 'Omega (0%)', value: fmt.num(s.omega, 2) }, { label: 'Tail ratio', value: fmt.num(s.tail_ratio, 2) },
        { label: 'Gain-to-pain', value: fmt.num(s.gain_to_pain, 2) }, { label: 'Lag-1 autocorr.', value: fmt.num(s.autocorr1, 3) },
      ]));
    };
    box.appendChild(h('div', { class: 't-tools' }, ui.seg(Object.keys(d.stats), win, (v) => { win = v; drawStats(); }),
      ui.seg([['vs_spy', 'vs S&P 500'], ['vs_soxx', 'vs SOXX']], vs, (v) => { vs = v; drawStats(); }),
      h('span', { class: 'dim', style: { fontSize: '12.5px' } }, `Daily data, risk-free ${fmt.pctu(d.rf, 2)} (13-week T-bill).`)));
    box.appendChild(kp); drawStats();
    box.appendChild(cmp);

    if (d.returns && d.returns.rows) {
      box.appendChild(sec('Trailing returns'));
      const hz = d.returns.horizons;
      box.appendChild(ui.panel(null, ui.table([{ key: 'name', label: '', l: true, txt: true, nosort: true }].concat(hz.map((k) => ({ key: k, label: k + (d.returns.annualized.includes(k) ? ' ann.' : ''), fmt: 'pct', sign: true, nosort: true }))),
        d.returns.rows.map((r) => ({ name: r.name === 'Asset' ? sym : r.name, ...r.values })), { rowClass: (r) => (r.name === sym ? 'self' : '') })));
    }

    box.appendChild(sec('Drawdowns'));
    const ddEl = charts.div('chart short');
    const dg = h('div', { class: 'grid g-main' });
    dg.appendChild(ui.panel('Underwater curve (10 years)', ddEl, { cap: 'Percent below the running peak. Deep, long troughs are what a holder actually lives through.' }));
    const dd = d.drawdowns || {};
    dg.appendChild(ui.panel('Worst drawdowns', ui.table([{ key: 'depth', label: 'Depth', fmt: 'pct', cls: 'down' }, { key: 'peak', label: 'Peak', fmt: 'date' },
      { key: 'trough', label: 'Trough', fmt: 'date' }, { key: 'recovery', label: 'Recovered', render: (r) => (r.recovery ? fmt.date(r.recovery) : '<span class="warn">not yet</span>') },
      { key: 'length', label: 'Days', fmt: 'int' }], dd.table || [], { sort: 'depth', desc: false })));
    box.appendChild(dg);
    if (dd.underwater) charts.lines(ddEl, [{ name: 'Drawdown', ...dd.underwater, color: 'down', fill: 'tozeroy', fillcolor: 'rgba(' + charts.theme().downRgb + ',.12)', width: 1.2 }], { yfmt: '.0%', legend: false });

    box.appendChild(sec('Rolling risk (63-day window)'));
    let metric = 'vol', rb = 'rolling_spy';
    const rEl = charts.div('chart');
    const drawRoll = () => {
      const r = d[rb] || {};
      const s = r[metric];
      const fmts = { vol: '.0%', sharpe: '.1f', beta: '.2f', correlation: '.2f', return: '.0%' };
      if (s && s.t) charts.lines(rEl, [{ name: metric, ...s, color: 'accent' }], { yfmt: fmts[metric], legend: false,
        shapes: metric === 'beta' ? [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 1, y1: 1 }] : [] });
    };
    box.appendChild(ui.panel(null, rEl, { right: h('span', { style: { display: 'flex', gap: '6px' } },
      ui.seg([['vol', 'Volatility'], ['sharpe', 'Sharpe'], ['beta', 'Beta'], ['correlation', 'Correlation'], ['return', 'Return']], metric, (v) => { metric = v; drawRoll(); }),
      ui.seg([['rolling_spy', 'vs S&P'], ['rolling_soxx', 'vs SOXX']], rb, (v) => { rb = v; drawRoll(); })) }));
    drawRoll();

    box.appendChild(sec('Return distribution & seasonality'));
    const g2 = h('div', { class: 'grid g2' });
    box.appendChild(g2);
    let dist = 'distribution';
    const distEl = charts.div('chart'), distInfo = h('div');
    const drawDist = () => {
      const x = d[dist];
      if (!x) return;
      const mids = x.edges.slice(0, -1).map((e, i) => (e + x.edges[i + 1]) / 2);
      charts.plot(distEl, (t) => ({
        data: [{ type: 'bar', x: mids, y: x.density, name: 'Observed', marker: { color: t.accent, opacity: 0.55 }, hovertemplate: '%{x:.2%}: %{y:.2f}<extra></extra>' },
          { type: 'scatter', mode: 'lines', x: x.normal_pdf.x, y: x.normal_pdf.y, name: 'Normal', line: { color: t.warn, width: 1.6 } },
          { type: 'scatter', mode: 'lines', x: x.t_pdf.x, y: x.t_pdf.y, name: `Student-t (ν=${fmt.num(x.t_df, 1)})`, line: { color: t.violet, width: 1.6, dash: 'dot' } }],
        layout: { bargap: 0.02, xaxis: { tickformat: '.0%' }, hovermode: 'closest' },
      }));
      distInfo.innerHTML = '';
      distInfo.appendChild(ui.kv([['Mean', fmt.pct(x.mean, 2)], ['Std dev', fmt.pctu(x.std, 2)], ['Skew', fmt.num(x.skew, 2)], ['Excess kurtosis', fmt.num(x.kurtosis, 2)],
        ['1% / 99% quantile', `${fmt.pct((x.quantiles || {})['1%'], 1)} / ${fmt.pct((x.quantiles || {})['99%'], 1)}`],
        ['Jarque-Bera p', fmt.num((x.jarque_bera || {}).p, 4), (x.jarque_bera || {}).p < 0.05 ? 'warn' : '']]));
    };
    g2.appendChild(ui.panel('Return distribution (5 years)', h('div', null, distEl, distInfo),
      { right: ui.seg([['distribution', 'Daily'], ['distribution_week', 'Weekly']], dist, (v) => { dist = v; drawDist(); }),
        cap: 'Fat tails show up as bars outside the normal curve. Jarque-Bera p < 0.05 rejects normality, so Gaussian VaR understates risk.' }));
    drawDist();
    const mo = d.monthly;
    if (mo && mo.matrix) {
      const mEl = charts.div('chart'), sEl = charts.div('chart xs');
      g2.appendChild(ui.panel('Monthly returns', h('div', null, mEl, sEl), { cap: 'Rows are years, last column the calendar-year total. Bottom: average return by month and the share of positive years.' }));
      const z = mo.matrix.map((r, i) => r.concat([mo.year_total[i]]));
      mEl.style.height = Math.max(220, 26 * mo.years.length + 40) + 'px';
      charts.heatmap(mEl, { z, x: mo.months.concat(['Year']), y: mo.years.map(String) }, { xtop: true, d: 1, textSize: 9.5, margin: { l: 44, r: 6, t: 26, b: 6 } });
      const se = mo.seasonality || [];
      charts.bars(sEl, { x: se.map((s) => s.month), y: se.map((s) => s.mean), colors: 'sign', text: se.map((s) => fmt.pctu(s.hit_rate, 0)) }, { yfmt: '.1%', margin: { l: 46, r: 8, t: 14, b: 24 } });
    }
  });

  // ─── Volatility ───────────────────────────────────────────────────────
  T.volatility = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/volatility`, (box, d) => {
    const s = d.summary || {}, g = d.garch || {}, p = g.params || {};
    box.appendChild(ui.kpis([
      { label: 'Realized 21d (Yang-Zhang)', value: fmt.pctu(s.rv_21d_yz), sub: 'percentile 1Y ' + fmt.pctu(s.rv_percentile_1y, 0) },
      { label: 'Realized 63d', value: fmt.pctu(s.rv_63d_cc), sub: 'percentile 5Y ' + fmt.pctu(s.rv_percentile_5y, 0) },
      { label: 'EWMA (RiskMetrics)', value: fmt.pctu(s.ewma) },
      { label: 'GARCH next 21d', value: fmt.pctu(s.garch_avg_21d), sub: (g.model || '').toUpperCase() + ' · t errors' },
      { label: 'Long-run vol', value: fmt.pctu(g.long_run_vol) },
      { label: 'Persistence', value: fmt.num(g.persistence, 3), sub: 'half-life ' + fmt.num(g.half_life_days, 0) + ' days' },
      { label: 'Implied vol 30d', value: fmt.pctu(d.atm_iv_30d), sub: 'from the option chain' },
      { label: 'Vol risk premium', value: fmt.pp(s.vrp), cls: fmt.cls(s.vrp), sub: 'IV − realized; IV/RV ' + fmt.num(s.iv_rv_ratio, 2) },
    ]));
    box.appendChild(h('p', { class: 'note', style: { margin: '10px 0 0' } }, h('b', null, 'Reading it: '),
      'volatility clusters (calm follows calm) and mean-reverts to its long-run level at the GARCH half-life. When implied vol trades above the realized/GARCH forecast, options are rich (premium sellers are paid); below it, options are cheap.'));
    box.appendChild(sec('Conditional volatility and forecast'));
    const el = charts.div('chart tall');
    box.appendChild(ui.panel(null, el, { cap: 'Annualised. GARCH conditional volatility (fitted on 10 years of daily returns), 21-day Yang-Zhang realized volatility, EWMA, and the forward GARCH path. The flat line is the 30-day implied volatility.' }));
    const series = [];
    if (g.cond_vol && g.cond_vol.t) { const n = g.cond_vol.t.length, k = Math.max(0, n - 756); series.push({ name: 'GARCH conditional', t: g.cond_vol.t.slice(k), v: g.cond_vol.v.slice(k), color: 'accent', width: 1.6 }); }
    const rv = d.realized && d.realized.series && (d.realized.series.yang_zhang || Object.values(d.realized.series)[0]);
    if (rv && rv.t) { const n = rv.t.length, k = Math.max(0, n - 756); series.push({ name: 'Realized 21d (YZ)', t: rv.t.slice(k), v: rv.v.slice(k), color: 'ink3', width: 1, dash: 'dot' }); }
    if (d.ewma && d.ewma.t) series.push({ name: 'EWMA', ...d.ewma, color: 'teal', width: 1 });
    if (g.forecast && g.forecast.vol && series.length) {
      const last = new Date(series[0].t[series[0].t.length - 1] + 'T12:00:00');
      const ft = g.forecast.days.map((k) => { const x = new Date(last); x.setDate(x.getDate() + Math.round(k * 7 / 5)); return x.toISOString().slice(0, 10); });
      series.push({ name: 'GARCH forecast', t: ft, v: g.forecast.vol, color: 'warn', width: 2, dash: 'dash' });
    }
    const shapes = fmt.ok(d.atm_iv_30d) ? [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: d.atm_iv_30d, y1: d.atm_iv_30d, line: { color: 'violet', dash: 'dash' } }] : [];
    if (fmt.ok(g.long_run_vol)) shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: g.long_run_vol, y1: g.long_run_vol, line: { color: 'ink4', dash: 'dot' } });
    charts.lines(el, series, { yfmt: '.0%', shapes });

    const g2 = h('div', { class: 'grid g2' });
    box.appendChild(sec('Volatility cone & estimators'));
    box.appendChild(g2);
    const c = d.cone;
    if (c && c.windows) {
      const cEl = charts.div('chart');
      g2.appendChild(ui.panel('Volatility cone (5 years)', cEl, { cap: 'Distribution of realized volatility for each window length. The marker is today: near the top = unusually volatile, near the bottom = unusually calm.' }));
      const x = c.windows.map((w) => w + 'd');
      charts.lines(cEl, [
        { name: 'max', t: x, v: c.max, color: 'ink4', width: 1, dash: 'dot' }, { name: '90th', t: x, v: c.p90, color: 'down', width: 1 },
        { name: '75th', t: x, v: c.p75, color: 'warn', width: 1 }, { name: 'median', t: x, v: c.median, color: 'ink3', width: 1.6 },
        { name: '25th', t: x, v: c.p25, color: 'teal', width: 1 }, { name: '10th', t: x, v: c.p10, color: 'up', width: 1 },
        { name: 'min', t: x, v: c.min, color: 'ink4', width: 1, dash: 'dot' },
        { name: 'today', t: x, v: c.current, color: 'accent', mode: 'lines+markers', width: 2.4 }], { yfmt: '.0%', xtype: 'category' });
    }
    const r = d.realized;
    if (r && r.table) {
      const rows = Object.entries(r.table).map(([m, vals]) => ({ method: m.replace(/_/g, ' '), ...vals }));
      g2.appendChild(ui.panel('Realized volatility estimators', h('div', null,
        ui.table([{ key: 'method', label: 'Estimator', l: true, txt: true }].concat(r.windows.map((w) => ({ key: String(w), label: w + 'd', fmt: 'pctu', d: 1 }))), rows),
        h('p', { class: 'note', style: { marginTop: '10px' } }, 'Range-based estimators (Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang) use the daily high, low and open and are up to 5-8× more efficient than close-to-close. Yang-Zhang also handles overnight gaps, which matter around earnings.'),
        g.params ? h('div', { style: { marginTop: '10px' } }, ui.kv(Object.entries(p).map(([k, v]) => [k, fmt.num(v, 4)]).concat([
          ['AIC / BIC', `${fmt.num(g.aic, 0)} / ${fmt.num(g.bic, 0)}`], ['Ljung-Box p (squared resid.)', fmt.num(g.ljung_box_sq_p, 3), g.ljung_box_sq_p < 0.05 ? 'warn' : 'up']]))) : null)));
    }
  });

  // ─── Tail risk & stress ───────────────────────────────────────────────
  T.tail = (body, sym) => loadInto(body, `/api/ticker/${enc(sym)}/tail`, (box, d) => {
    let pos = 10000;
    const ve = d.var_es || {};
    const tbl = h('div');
    const drawVar = () => {
      const rows = {};
      (ve.table || []).forEach((r) => {
        const k = r.method;
        rows[k] = rows[k] || { method: k.replace(/_/g, ' ') };
        rows[k][`var_${r.level}_${r.horizon}`] = r.var;
        rows[k][`es_${r.level}_${r.horizon}`] = r.es;
      });
      const cols = [{ key: 'method', label: 'Model', l: true, txt: true }];
      (ve.levels || [0.95, 0.99]).forEach((lv) => (ve.horizons || [1, 10]).forEach((hz) => {
        cols.push({ key: `var_${lv}_${hz}`, label: `VaR ${lv * 100}% ${hz}d`, render: (r) => `${fmt.pctu(r[`var_${lv}_${hz}`], 2)}<br><span class="dim">${fmt.money(fmt.ok(r[`var_${lv}_${hz}`]) ? r[`var_${lv}_${hz}`] * pos : null)}</span>` });
        cols.push({ key: `es_${lv}_${hz}`, label: `ES ${lv * 100}% ${hz}d`, render: (r) => `${fmt.pctu(r[`es_${lv}_${hz}`], 2)}<br><span class="dim">${fmt.money(fmt.ok(r[`es_${lv}_${hz}`]) ? r[`es_${lv}_${hz}`] * pos : null)}</span>` });
      }));
      tbl.innerHTML = '';
      tbl.appendChild(ui.table(cols, Object.values(rows), { csv: `${sym}-var.csv` }));
    };
    const posIn = h('input', { class: 'inp', type: 'number', value: pos, step: 1000, style: { width: '120px' }, oninput: (e) => { pos = parseFloat(e.target.value) || 0; drawVar(); } });
    const ev = ve.evt || {};
    box.appendChild(ui.panel('Value at Risk and Expected Shortfall', h('div', null, tbl,
      h('div', { class: 'note', style: { marginTop: '10px' } }, `Losses as positive numbers on ${fmt.int(ve.observations)} daily returns (5 years). Extreme-value fit (GPD over the 90th-percentile loss): tail index ξ = ${fmt.num(ev.xi, 3)} `,
        fmt.ok(ev.xi) ? (ev.xi > 0 ? '(fat-tailed: losses beyond VaR can be much larger than a normal model suggests)' : '(thin tail)') : '', `, ${fmt.int(ev.n_exceed)} exceedances. Expected Shortfall is the average loss on the days worse than VaR.`)),
    { right: h('label', { class: 'mono', style: { fontSize: '12px', display: 'flex', gap: '6px', alignItems: 'center' } }, 'Position $', posIn) }));
    drawVar();

    const bts = d.backtests || [];
    if (bts.length) {
      box.appendChild(sec('Is the model calibrated? Rolling 99% VaR backtests'));
      let pick = 0;
      const bEl = charts.div('chart');
      const drawBt = () => {
        const b = bts[pick], s = b.series || {};
        if (!s.t) return;
        const ex = s.t.map((t, i) => (fmt.ok(s.ret[i]) && fmt.ok(s.var[i]) && s.ret[i] < -s.var[i] ? s.ret[i] : null));
        charts.lines(bEl, [{ name: 'Daily return', t: s.t, v: s.ret, color: 'ink4', width: 0.8 }, { name: '−VaR 99%', t: s.t, v: s.var.map((v) => (fmt.ok(v) ? -v : null)), color: 'warn', width: 1.5 },
          { name: 'Exceptions', t: s.t, v: ex, mode: 'markers', color: 'down' }], { yfmt: '.0%' });
      };
      box.appendChild(h('div', { class: 'grid g-main' },
        ui.panel(null, bEl, { right: ui.seg(bts.map((b, i) => [i, b.method]), 0, (v) => { pick = v; drawBt(); }) }),
        ui.panel('Backtest statistics', ui.table([{ key: 'method', label: 'Model', l: true, txt: true }, { key: 'exceptions', label: 'Breaches', fmt: 'int' },
          { key: 'expected', label: 'Expected', fmt: 'num', d: 1 }, { key: 'kupiec', label: 'Kupiec p', render: (r) => fmt.num((r.kupiec || {}).p, 3) },
          { key: 'christoffersen', label: 'Indep. p', render: (r) => fmt.num((r.christoffersen || {}).p, 3) },
          { key: 'traffic_light', label: 'Basel', render: (r) => `<span class="${{ green: 'up', yellow: 'warn', red: 'down' }[r.traffic_light] || ''}">${r.traffic_light || '–'}</span>` }], bts),
        { cap: 'Kupiec tests the breach count, Christoffersen whether breaches cluster. p < 0.05 means the model is mis-calibrated for this stock; prefer the model that passes both.' })));
      drawBt();
    }

    const st = d.stress && d.stress.rows ? d.stress.rows.filter((r) => r.covered) : [];
    box.appendChild(sec('Historical crisis replay'));
    if (st.length) {
      const sEl = charts.div('chart');
      const benches = Object.keys(st[0].bench || {});
      charts.bars(sEl, [{ name: sym, x: st.map((r) => r.name), y: st.map((r) => r.return), colors: 'accent' }]
        .concat(benches.map((b, i) => ({ name: b, x: st.map((r) => r.name), y: st.map((r) => (r.bench || {})[b]), colors: i ? 'violet' : 'ink3' }))), { yfmt: '.0%' });
      box.appendChild(h('div', { class: 'grid g-main' }, ui.panel(null, sEl, { cap: `Actual price moves during past market crises (data since ${fmt.date(d.first_date)}).` }),
        ui.panel(null, ui.table([{ key: 'name', label: 'Episode', l: true, txt: true }, { key: 'return', label: sym, fmt: 'pct', sign: true },
          { key: 'max_drawdown', label: 'Worst point', fmt: 'pct', cls: 'down' }].concat(benches.map((b) => ({ key: b, label: b, get: (r) => (r.bench || {})[b], fmt: 'pct', sign: true }))), st))));
    } else box.appendChild(ui.empty('Not enough history for the crisis windows.'));

    const sh = d.shocks && d.shocks.rows;
    if (sh && sh.length) {
      box.appendChild(sec('Hypothetical shocks (beta-implied)'));
      const hEl = charts.div('chart short');
      box.appendChild(h('div', { class: 'grid g2' }, ui.panel(null, hEl),
        ui.panel(null, ui.table([{ key: 'name', label: 'Scenario', l: true, txt: true }, { key: 'beta', label: 'Beta', fmt: 'num', d: 3 },
          { key: 'r2', label: 'R²', fmt: 'num', d: 2 }, { key: 'impact', label: 'Est. move', fmt: 'pct', sign: true }], sh),
        { cap: 'First-order estimates from 2 years of daily sensitivities (yield in bp, VIX in points). Low R² means the factor explains little of this stock.' })));
      charts.bars(hEl, { x: sh.map((r) => r.impact), y: sh.map((r) => r.name), horizontal: true, colors: 'sign' }, { horizontal: true, xfmt: '.0%', margin: { l: 120, r: 10, t: 4, b: 26 } });
    }
  });

  // ─── Options ──────────────────────────────────────────────────────────
  T.options = (body, sym, params) => {
    const box = h('div');
    body.appendChild(box);
    const load = (expiry) => ui.async(box, () => api(`/api/ticker/${enc(sym)}/options` + (expiry ? '?expiry=' + enc(expiry) : '')), (b, d) => renderOptions(b, sym, d, load), 520);
    load(params && params.expiry);
  };

  function renderOptions(box, sym, d, reload) {
    if (!d.available) { box.appendChild(ui.empty(d.message || 'No options for this symbol.')); return; }
    const c = d.chain || {}, sk = c.skew || {}, pc = c.put_call || {}, gx = c.gex || {};
    const ts = d.term || {};
    const sel = ui.select(d.expiries.map((e) => [e.expiry, `${fmt.date(e.expiry)} (${e.dte}d)`]), d.expiry, (v) => reload(v));
    box.appendChild(h('div', { class: 't-tools' }, h('span', { class: 'label' }, 'Expiry'), sel,
      h('span', { class: 'dim', style: { fontSize: '12.5px' } }, `Spot ${fmt.price(d.spot)} · r ${fmt.pctu(d.rate, 2)} · q ${fmt.pctu(d.dividend_yield, 2)} · ${d.market_state === 'REGULAR' ? 'live quotes' : 'last session quotes (market closed: bids/asks may be stale)'}`)));
    box.appendChild(ui.kpis([
      { label: 'ATM implied vol', value: fmt.pctu(c.atm_iv), sub: `${c.dte}d · ATM strike ${fmt.price(c.atm_strike)}` },
      { label: '30-day IV', value: fmt.pctu(d.atm_iv_30d), sub: 'realized 21d ' + fmt.pctu(d.rv_21d) },
      { label: 'IV − RV', value: fmt.pp(d.vrp), cls: fmt.cls(d.vrp), sub: d.vrp > 0 ? 'options rich' : 'options cheap' },
      { label: 'Implied move', value: '±' + fmt.pctu(c.implied_move), sub: `to ${fmt.dateShort(c.expiry)}: ${fmt.price((c.expected_range || [])[0])} – ${fmt.price((c.expected_range || [])[1])}` },
      { label: 'Put/call OI', value: fmt.num(pc.oi_ratio, 2), sub: 'volume ' + fmt.num(pc.volume_ratio, 2) },
      { label: 'Max pain', value: fmt.price(c.max_pain), sub: fmt.ok(c.max_pain) && d.spot ? fmt.pct(c.max_pain / d.spot - 1) + ' vs spot' : '' },
      { label: 'Net gamma (GEX)', value: fmt.money(gx.total), cls: fmt.cls(gx.total), sub: 'flip ≈ ' + fmt.price(gx.flip) },
      { label: '25Δ risk reversal', value: fmt.pp(sk.rr25), cls: fmt.cls(sk.rr25), sub: 'butterfly ' + fmt.pp(sk.bf25) },
      ts.earnings && fmt.ok(ts.earnings.implied_event_move) ? { label: 'Earnings implied move', value: '±' + fmt.pctu(ts.earnings.implied_event_move), sub: fmt.date(ts.earnings.date) + ' (term-structure kink)' } : null,
    ]));
    if ((c.warnings || []).length) box.appendChild(h('p', { class: 'note warn', style: { marginTop: '8px' } }, c.warnings.join(' ')));

    const g = h('div', { class: 'grid g2' });
    box.appendChild(sec('Smile, term structure, positioning'));
    box.appendChild(g);
    const smEl = charts.div('chart'), tsEl = charts.div('chart'), oiEl = charts.div('chart'), gxEl = charts.div('chart');
    g.appendChild(ui.panel('Volatility smile', smEl, { cap: 'Out-of-the-money puts (left of the forward) and calls (right), IV recomputed from bid/ask mids. A steep left side = expensive downside protection.' }));
    g.appendChild(ui.panel('Term structure', tsEl, { cap: 'ATM implied vol by expiry and the straddle-implied move. A hump at an expiry just after earnings prices the event.' }));
    g.appendChild(ui.panel('Open interest by strike', oiEl, { cap: 'Where positions sit. Large walls often act as magnets/pins into expiry; dashed lines mark spot and max pain.' }));
    g.appendChild(ui.panel('Dealer gamma exposure by strike', gxEl, { cap: 'Naive GEX: dealers long calls / short puts. Positive net gamma dampens moves (dealers sell rallies, buy dips); negative amplifies them.' }));
    const sm = c.smile || [];
    const puts = sm.filter((x) => x.side === 'put'), calls = sm.filter((x) => x.side === 'call');
    const vline = (x, color) => ({ type: 'line', x0: x, x1: x, yref: 'paper', y0: 0, y1: 1, line: { color, dash: 'dash' } });
    charts.lines(smEl, [{ name: 'OTM puts', t: puts.map((x) => x.strike), v: puts.map((x) => x.iv), mode: 'lines+markers', color: 'down' },
      { name: 'OTM calls', t: calls.map((x) => x.strike), v: calls.map((x) => x.iv), mode: 'lines+markers', color: 'up' }],
    { yfmt: '.0%', xfmt: ',.0f', hovermode: 'closest', shapes: [vline(d.spot, 'ink3')] });
    const tr = ts.rows || [];
    charts.lines(tsEl, [{ name: 'ATM IV', t: tr.map((r) => r.dte), v: tr.map((r) => r.atm_iv), mode: 'lines+markers', color: 'accent', width: 2 },
      { name: 'Implied move', t: tr.map((r) => r.dte), v: tr.map((r) => r.implied_move), mode: 'lines+markers', color: 'warn', y2: true }],
    { yfmt: '.0%', y2: true, y2fmt: '.0%', xtitle: 'days to expiry', hovermode: 'x unified' });
    const near = (k) => !fmt.ok(d.spot) || Math.abs(k / d.spot - 1) < 0.35;
    const oi = (c.oi_by_strike || []).filter((r) => near(r.strike));
    charts.bars(oiEl, [{ name: 'Calls', x: oi.map((r) => r.strike), y: oi.map((r) => r.call_oi), colors: 'up' }, { name: 'Puts', x: oi.map((r) => r.strike), y: oi.map((r) => -(r.put_oi || 0)), colors: 'down' }],
      { barmode: 'relative', yfmt: ',.0f', shapes: [vline(d.spot, 'ink3'), fmt.ok(c.max_pain) ? vline(c.max_pain, 'violet') : null].filter(Boolean) });
    const gb = (gx.by_strike || []).filter((r) => near(r.strike));
    charts.bars(gxEl, { x: gb.map((r) => r.strike), y: gb.map((r) => r.net), colors: 'sign', name: 'Net GEX' },
      { yfmt: '$.2s', shapes: [vline(d.spot, 'ink3'), fmt.ok(gx.flip) ? vline(gx.flip, 'warn') : null].filter(Boolean) });

    if (d.surface && d.surface.iv && d.surface.iv.length > 1) {
      box.appendChild(sec('Implied volatility surface'));
      const sEl = charts.div('chart tall');
      box.appendChild(ui.panel(null, sEl, { cap: 'IV by moneyness (strike / forward) and days to expiry, interpolated within each expiry\'s quoted range. Drag to rotate.' }));
      charts.surface(sEl, { x: d.surface.moneyness, y: d.surface.dte, z: d.surface.iv }, { xlabel: 'K / F', ylabel: 'DTE' });
    }

    box.appendChild(sec(`Chain · ${fmt.date(c.expiry)}`));
    let all = false;
    const chainBox = h('div');
    const drawChain = () => {
      const rows = (c.rows || []).filter((r) => all || near(r.strike) && Math.abs(r.strike / d.spot - 1) < 0.2);
      chainBox.innerHTML = '';
      chainBox.appendChild(ui.table([
        { key: 'call_oi', label: 'C OI', fmt: 'int' }, { key: 'call_volume', label: 'C vol', fmt: 'int' }, { key: 'call_iv', label: 'C IV', fmt: 'pctu' },
        { key: 'call_delta', label: 'C Δ', fmt: 'num', d: 2 }, { key: 'call_bid', label: 'C bid', fmt: 'num' }, { key: 'call_ask', label: 'C ask', fmt: 'num' },
        { key: 'strike', label: 'Strike', render: (r) => `<b>${fmt.price(r.strike)}</b>` },
        { key: 'put_bid', label: 'P bid', fmt: 'num' }, { key: 'put_ask', label: 'P ask', fmt: 'num' }, { key: 'put_delta', label: 'P Δ', fmt: 'num', d: 2 },
        { key: 'put_iv', label: 'P IV', fmt: 'pctu' }, { key: 'put_volume', label: 'P vol', fmt: 'int' }, { key: 'put_oi', label: 'P OI', fmt: 'int' },
        { key: 'call_gamma', label: 'Γ', fmt: 'num', d: 4 }, { key: 'call_theta', label: 'C θ/day', fmt: 'num', d: 3 }, { key: 'call_vega', label: 'Vega', fmt: 'num', d: 3 },
      ], rows, { sort: 'strike', desc: false, max: true, csv: `${sym}-${c.expiry}-chain.csv`,
        rowClass: (r) => (Math.abs(r.strike - c.atm_strike) < 1e-9 ? 'self' : ''),
        tools: h('label', { class: 'mono', style: { fontSize: '12px', display: 'flex', gap: '6px', alignItems: 'center' } },
          h('input', { type: 'checkbox', checked: all, onchange: (e) => { all = e.target.checked; drawChain(); } }), 'all strikes (default ±20% of spot)') }));
    };
    box.appendChild(ui.panel(null, chainBox, { cap: 'Greeks from Black-Scholes-Merton with the implied forward; theta per calendar day, vega per 1 vol point. Highlighted row = ATM.' }));
    drawChain();
    if ((c.unusual || []).length) {
      box.appendChild(sec('Unusual activity (volume ≥ 2× open interest)'));
      box.appendChild(ui.panel(null, ui.table([{ key: 'contract', label: 'Contract', l: true }, { key: 'side', label: 'Side', l: true },
        { key: 'strike', label: 'Strike', fmt: 'price' }, { key: 'volume', label: 'Volume', fmt: 'int' }, { key: 'oi', label: 'Open int.', fmt: 'int' },
        { key: 'vol_oi', label: 'Vol/OI', fmt: 'num', d: 1 }, { key: 'iv', label: 'IV', fmt: 'pctu' }, { key: 'mid', label: 'Mid', fmt: 'num' }], c.unusual, { sort: 'volume' })));
    }
  }
})();
