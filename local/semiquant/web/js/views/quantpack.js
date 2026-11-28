/* Institutional quant pack: crash risk and track-record confidence, liquidity and execution cost
 * (Risk tab); HAR-RV forecasts and random-walk tests (Volatility tab); risk-neutral distribution and
 * model-free implied volatility (Options tab); systemic risk (Market page); the Factor lab page.
 * Every block renders from fields the services add to existing payloads, so the web edition gets
 * them through the same published files. Missing fields simply leave a block out. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts } = SQ;
  const sec = ui.sec;
  const bp = (x, d = 0) => (fmt.ok(x) ? (x * 1e4).toFixed(d) + ' bp' : '–');
  const yrs = (x) => (fmt.ok(x) ? (x < 1 ? Math.round(x * 12) + ' months' : fmt.num(x, 1) + ' years') : '–');
  const QP = (SQ.qp = {});

  // ─── Risk tab: crash risk, Sharpe confidence, drawdown risk, liquidity ──────────────
  QP.riskExtras = (box, d) => {
    const c = d.crash, sc = d.sharpe_confidence || {}, dr = d.drawdown_risk, lq = d.liquidity;
    if (c || Object.keys(sc).length || dr) {
      box.appendChild(sec('Crash risk & how much to trust the track record'));
      const s5 = sc['5Y'] || sc['3Y'] || sc['1Y'] || {};
      const w5 = sc['5Y'] ? '5Y' : sc['3Y'] ? '3Y' : '1Y';
      const td = ((c && c.tail_dependence) || [])[0] || {};
      const per = c && c.freq === 'weekly' ? 'weeks' : 'days';
      box.appendChild(ui.kpis([
        c ? { label: 'Downside beta', value: fmt.num(c.downside_beta, 2), cls: (c.beta_asymmetry || 0) > 0.2 ? 'down' : '',
          sub: `upside ${fmt.num(c.upside_beta, 2)} · overall ${fmt.num(c.beta, 2)}`,
          title: 'Beta measured only when the S&P 500 is below its average (Ang, Chen & Xing). Above the upside beta = falls harder than it rises with the market.' } : null,
        c ? { label: 'Crash beta', value: fmt.num(c.crash_beta, 2), sub: `${fmt.pct(c.crash_avg_stock, 1)} on the S&P's worst 5% of ${per}`,
          title: 'Average move on the market\'s worst 5% of periods, relative to the market\'s average move on those periods.' } : null,
        c ? { label: 'Co-skewness', value: fmt.num(c.coskewness, 2), cls: fmt.cls(c.coskewness),
          sub: 'negative = hit harder when the market swings', title: 'Harvey & Siddique co-skewness, standardised. Investors demand a premium for negative co-skewness.' } : null,
        c ? { label: 'Tail dependence (5%)', value: fmt.pctu(td.lower, 0), sub: `independent ${fmt.pctu(td.independent, 0)} · upside ${fmt.pctu(td.upper, 0)}`,
          title: 'Share of the S&P 500\'s worst 5% of periods on which this stock was also in its own worst 5%.' } : null,
        { label: `Sharpe (${w5}) · 95% range`, value: fmt.num(s5.sharpe, 2), sub: `${fmt.num(s5.ci_low, 2)} to ${fmt.num(s5.ci_high, 2)}`,
          title: 'Sharpe ratio with its 95% confidence interval from the non-normal standard error (Mertens 2002): fat tails and negative skew widen it.' },
        { label: 'Probabilistic Sharpe', value: fmt.pctu(s5.psr, 0), cls: (s5.psr || 0) >= 0.95 ? 'up' : (s5.psr || 0) < 0.5 ? 'down' : '',
          sub: 'chance the true Sharpe is above 0', title: 'Bailey & Lopez de Prado (2012). Above 95% = the positive Sharpe is unlikely to be luck.' },
        { label: 'Track record needed', value: yrs(s5.min_track_record_years), sub: `for 95% confidence · history ${yrs(s5.years)}`,
          title: 'Minimum track record length: history needed before a Sharpe this size is significant at 95%.' },
        dr ? { label: 'Conditional drawdown-at-risk', value: fmt.pct(-dr.cdar, 1), cls: 'down', sub: `DaR 95% ${fmt.pct(-dr.dar, 1)} · pain ${fmt.pct(-dr.pain_index, 1)}`,
          title: 'Average depth of the worst 5% of drawdown days over 10 years (Chekhlov, Uryasev & Zabarankin).' } : null,
        dr ? { label: 'Time under water', value: fmt.pctu(dr.underwater_share, 0), sub: `longest ${fmt.int(dr.longest_underwater_days)} days · now ${fmt.int(dr.current_underwater_days)}`,
          title: 'Share of trading days below a previous high.' } : null,
      ]));
      const rows = Object.entries(sc).filter(([, v]) => v && fmt.ok(v.sharpe)).map(([w, v]) => ({ w, ...v }));
      if (rows.length) {
        box.appendChild(h('div', { style: { height: '10px' } }));
        box.appendChild(ui.panel('Is the Sharpe ratio skill or luck?', ui.table([
          { key: 'w', label: 'Window', l: true, nosort: true }, { key: 'sharpe', label: 'Sharpe', fmt: 'num', d: 2 },
          { key: 'ci_low', label: '95% low', fmt: 'num', d: 2 }, { key: 'ci_high', label: '95% high', fmt: 'num', d: 2 },
          { key: 'psr', label: 'P(Sharpe > 0)', fmt: 'pctu', d: 0 }, { key: 'skew', label: 'Skew', fmt: 'num', d: 2 },
          { key: 'kurtosis', label: 'Kurtosis', fmt: 'num', d: 1 },
          { key: 'min_track_record_years', label: 'History needed', render: (r) => yrs(r.min_track_record_years) }], rows),
        { cap: 'Daily excess returns over the T-bill rate. A short or fat-tailed history leaves a wide range around the Sharpe ratio; the probabilistic Sharpe ratio and the minimum track record account for skew and kurtosis (Bailey & Lopez de Prado).' }));
      }
    }
    if (lq) {
      box.appendChild(sec('Liquidity & execution cost'));
      if (!lq.available) { box.appendChild(ui.empty(lq.message || 'No volume data.')); return; }
      const src = { quoted: 'live bid/ask', typical: 'typical for its dollar volume' }[lq.spread_source] || '';
      const illiquid = (lq.adv_usd_20d || 0) < 5e7;
      box.appendChild(ui.kpis([
        { label: 'Dollar volume (20d avg)', value: fmt.money(lq.adv_usd_20d), sub: `60d ${fmt.money(lq.adv_usd_60d)} · trend ${fmt.pct(lq.volume_trend, 0)}` },
        { label: 'Shares traded (20d avg)', value: fmt.big(lq.adv_shares_20d), sub: fmt.ok(lq.turnover_daily) ? `${fmt.pctu(lq.turnover_daily, 2)} of shares a day` : '' },
        { label: 'Bid-ask spread', value: bp(lq.spread_used, 1), sub: src + (illiquid && lq.spread_cs ? ` · high-low est. ${bp(lq.spread_cs)}` : ''),
          title: 'Live quoted spread while the market is open; otherwise the typical spread for this much daily volume (daily-bar estimators mistake volatility for spread on liquid stocks).' },
        { label: 'Amihud illiquidity', value: fmt.ok(lq.amihud) ? bp(lq.amihud * 10, 2) : '–', sub: 'average move per $10M traded',
          title: 'Amihud (2002): mean |daily return| per dollar traded over 60 days.' },
        { label: 'Daily volatility (60d)', value: fmt.pctu(lq.daily_vol, 2), sub: 'drives the impact estimate' },
      ]));
      const rows = (lq.orders || []).map((o) => ({ ...o, size: fmt.money(o.usd) }));
      box.appendChild(h('div', { style: { height: '10px' } }));
      box.appendChild(ui.panel('What a trade would cost (square-root impact law)', ui.table([
        { key: 'size', label: 'Order', l: true, nosort: true }, { key: 'pct_adv', label: '% of daily vol.', fmt: 'pctu', d: 2 },
        { key: 'cost', label: 'Expected cost', render: (r) => bp(r.cost, 1) }, { key: 'cost_usd', label: 'Cost $', fmt: 'big' },
        { key: 'days_10', label: 'Days at 10%', fmt: 'num', d: 1 }, { key: 'risk_10', label: 'Price risk', fmt: 'pctu', d: 1, title: '1 sd of the price drift while working the order at 10% of volume' },
        { key: 'days_20', label: 'Days at 20%', fmt: 'num', d: 1 }], rows),
      { cap: `Expected cost = half the spread + ${fmt.num(lq.impact_y, 1)} × daily volatility × √(order / daily volume) (Almgren et al. 2005; Tóth et al. 2011). It depends on the order's size relative to volume, not on how slowly it is worked; working it over more days to stay under 10-20% of volume (the usual desk limit) adds price risk instead (1 sd of the drift, Almgren & Chriss). Estimates, not quotes.` }));
    }
  };

  // ─── Volatility tab: HAR-RV and random-walk diagnostics ─────────────────────────────
  QP.volExtras = (box, d) => {
    const har = d.har;
    if (har && har.forecasts && har.forecasts.length) {
      box.appendChild(sec('HAR-RV forecast (day, week, month cascade)'));
      const name = { 1: 'Next day', 5: 'Next week', 21: 'Next month', 63: 'Next quarter' };
      const cur = har.current || {};
      box.appendChild(ui.kpis(har.forecasts.map((f) => ({ label: name[f.h] || `${f.h} days`, value: fmt.pctu(f.vol), sub: `R² ${fmt.pctu(f.r2, 0)} · annualised` }))
        .concat([{ label: 'Realised now', value: fmt.pctu(cur.month), sub: `day ${fmt.pctu(cur.day, 0)} · week ${fmt.pctu(cur.week, 0)}` }])));
      if (har.fit && har.fit.t) {
        const el = charts.div('chart');
        box.appendChild(h('div', { style: { height: '10px' } }));
        box.appendChild(ui.panel('Model vs what happened (next 21 days)', el, { cap: 'Annualised. The HAR-RV model (Corsi 2009, log form) forecasts volatility from the last day, week and month of range-based realised variance; the line is what the next 21 days then realised. Institutional desks run it next to GARCH: it adapts faster after shocks.' }));
        charts.lines(el, [{ name: 'Realised (next 21d)', t: har.fit.t, v: har.fit.actual, color: 'ink3', width: 1 },
          { name: 'HAR forecast', t: har.fit.t, v: har.fit.fitted, color: 'accent', width: 1.8 }], { yfmt: '.0%' });
      }
    }
    const rw = d.random_walk;
    if (rw && rw.verdict) {
      box.appendChild(sec('Trending, mean-reverting or a random walk?'));
      const lb = (rw.ljung_box || []).find((x) => x.lag === 10) || {}, lb2 = (rw.ljung_box_sq || []).find((x) => x.lag === 10) || {};
      const cls = rw.verdict === 'trending' ? 'up' : rw.verdict === 'mean-reverting' ? 'warn' : '';
      box.appendChild(ui.kpis([
        { label: 'Verdict (5 years)', value: rw.verdict.replace(/^./, (x) => x.toUpperCase()), cls, sub: rw.verdict_detail },
        { label: 'Hurst exponent', value: fmt.num(rw.hurst, 2), sub: '0.5 random walk · >0.5 trends · <0.5 reverts' },
        rw.adf ? { label: 'ADF unit-root p', value: fmt.num(rw.adf.p, 2), sub: rw.adf.p > 0.05 ? 'prices wander: no level to revert to' : 'prices revert to a level' } : null,
        { label: 'Return predictability', value: fmt.num(lb.p, 3), sub: 'Ljung-Box p, 10 lags (low = predictable)' },
        { label: 'Volatility clustering', value: fmt.num(lb2.p, 3), cls: lb2.p < 0.05 ? 'warn' : '', sub: lb2.p < 0.05 ? 'yes: calm and storms come in runs' : 'not significant' },
      ]));
      const g = h('div', { class: 'grid g2', style: { marginTop: '10px' } });
      box.appendChild(g);
      g.appendChild(ui.panel('Variance ratios (Lo-MacKinlay)', ui.table([
        { key: 'q', label: 'Horizon (days)', l: true, nosort: true }, { key: 'vr', label: 'Variance ratio', fmt: 'num', d: 2 },
        { key: 'z', label: 'Robust z', fmt: 'num', d: 2 }, { key: 'p', label: 'p-value', fmt: 'num', d: 3 }], rw.variance_ratios || []),
      { cap: 'Variance of q-day returns over q × the variance of daily returns: 1 for a random walk, above 1 when moves persist, below 1 when they reverse. z is robust to volatility clustering; p < 0.05 is significant.' }));
      if (rw.acf && rw.acf.v) {
        const el = charts.div('chart short');
        g.appendChild(ui.panel('Autocorrelation of daily returns', el, { cap: 'Bars outside the dashed band (95%) are significant.' }));
        const b = rw.acf.band;
        charts.bars(el, { x: rw.acf.lags.map(String), y: rw.acf.v, colors: 'sign' }, { yfmt: '.2f', legend: false,
          shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: b, y1: b, line: { color: 'ink4', dash: 'dash' } },
            { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: -b, y1: -b, line: { color: 'ink4', dash: 'dash' } }] });
      }
    }
  };

  // ─── Options tab: risk-neutral distribution and model-free implied vol ───────────────
  QP.optionsExtras = (box, d) => {
    const r = d.rnd;
    if (r) {
      box.appendChild(sec(`Market-implied distribution${r.expiry ? ' · ' + fmt.date(r.expiry) : ''}`));
      if (!r.available) box.appendChild(ui.empty(r.message || 'Not enough clean quotes.'));
      else {
        const q = r.quantiles || {}, p = r.prob || {};
        box.appendChild(ui.kpis([
          { label: 'Chance of finishing up', value: fmt.pctu(p.up, 0), sub: `median ${fmt.price(q.p50)} · spot ${fmt.price(r.spot)}` },
          { label: 'Down more than 10%', value: fmt.pctu(p.down_10, 1), cls: 'down', sub: `more than 20%: ${fmt.pctu(p.down_20, 1)}` },
          { label: 'Up more than 10%', value: fmt.pctu(p.up_10, 1), cls: 'up', sub: `more than 20%: ${fmt.pctu(p.up_20, 1)}` },
          { label: '90% range', value: `${fmt.price(q.p5)} – ${fmt.price(q.p95)}`, sub: `50%: ${fmt.price(q.p25)} – ${fmt.price(q.p75)}` },
          { label: 'Implied skew / kurtosis', value: `${fmt.num(r.skew, 2)} / ${fmt.num(r.kurtosis, 1)}`, sub: 'lognormal: slightly positive / about 3' },
        ]));
        const el = charts.div('chart');
        box.appendChild(h('div', { style: { height: '10px' } }));
        box.appendChild(ui.panel('Probability density of the price at expiry', el, { cap: `Risk-neutral density from the option prices (Breeden-Litzenberger); the dotted line is today's price. The smile is smoothed with ${r.method === 'svi' ? 'SVI' : 'a quadratic'} in log-moneyness and differentiated twice. The dashed curve is a lognormal with the same forward and the ATM vol: where the solid curve sits above it, the options price in more of that outcome (usually crashes). Risk-neutral probabilities include risk premia: they are what the market charges for, not a forecast. Quality: ${fmt.pctu(r.mass_in_grid, 0)} of the probability inside the strikes, ${fmt.pctu(r.negative_mass, 1)} arbitrage noise removed.` }));
        const t = charts.theme();
        charts.plot(el, (th) => ({
          data: [{ type: 'scatter', mode: 'lines', name: 'Implied', x: r.curve.k, y: r.curve.pdf, line: { color: th.accent, width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(' + th.accentRgb + ',.12)', hovertemplate: 'price %{x:,.2f}<extra></extra>' },
            { type: 'scatter', mode: 'lines', name: 'Lognormal (ATM vol)', x: r.curve.k, y: r.curve.lognormal, line: { color: th.ink4, width: 1.2, dash: 'dash' }, hoverinfo: 'skip' }],
          layout: { hovermode: 'x unified', yaxis: { showticklabels: false, title: { text: 'density' } }, xaxis: { tickformat: ',.0f' },
            shapes: [{ type: 'line', x0: r.spot, x1: r.spot, yref: 'paper', y0: 0, y1: 1, line: { color: t.ink2, width: 1, dash: 'dot' } }] },
        }));
      }
    }
    const mf = d.mfiv || [];
    if (mf.length) {
      box.appendChild(sec('Model-free implied volatility (VIX method)'));
      box.appendChild(ui.kpis([
        { label: '30-day model-free IV', value: fmt.pctu(d.mfiv_30d), sub: `ATM 30d ${fmt.pctu(d.atm_iv_30d)}` },
        { label: 'Tail premium', value: fmt.pp(fmt.ok(d.mfiv_30d) && fmt.ok(d.atm_iv_30d) ? d.mfiv_30d - d.atm_iv_30d : null), sub: 'model-free minus ATM: what the wings add' },
        { label: 'Variance risk premium', value: fmt.pp(d.vrp_mf), cls: fmt.cls(d.vrp_mf), sub: 'model-free IV minus realised 21d' },
      ]));
      const el = charts.div('chart short');
      box.appendChild(h('div', { style: { height: '10px' } }));
      box.appendChild(ui.panel('Term structure: whole-strip vs at-the-money', el, { cap: 'The CBOE VIX formula applied to this stock, expiry by expiry: the fair strike of a variance swap from every out-of-the-money option, not just the ATM. It sits above the ATM vol when the skew and wings are expensive (crash protection in demand).' }));
      charts.lines(el, [{ name: 'Model-free', t: mf.map((m) => Math.round(m.dte)), v: mf.map((m) => m.mfiv), color: 'accent', mode: 'lines+markers', width: 2 },
        { name: 'ATM', t: mf.map((m) => Math.round(m.dte)), v: mf.map((m) => m.atm_iv), color: 'teal', mode: 'lines+markers', width: 1.4 }],
      { yfmt: '.0%', xtitle: 'days to expiry', layout: { xaxis: { type: 'linear' } } });
    }
  };

  // ─── Market page: systemic risk of a universe ───────────────────────────────────────
  QP.systemic = (container, uni) => {
    const head = h('div'), body = h('div');
    container.appendChild(head); container.appendChild(body);
    head.appendChild(sec('Systemic risk (daily)'));
    ui.async(body, () => api('/api/market/systemic?u=' + uni), (b, d) => {
      const a = d.absorption || {}, t = d.turbulence || {};
      if (!a.available && !t.available) { b.appendChild(ui.empty('Not enough history for this universe.')); return; }
      b.appendChild(ui.kpis([
        a.available ? { label: 'Absorption ratio', value: fmt.pctu(a.current, 0), sub: `percentile ${fmt.num(a.percentile, 0)} (5Y) · top ${a.n_top} of ${a.n_assets} factors`,
          title: 'Share of the universe\'s variance absorbed by its top fifth of eigenvectors (Kritzman et al. 2011). High = stocks move as one and shocks spread.' } : null,
        a.available ? { label: 'Absorption shift', value: fmt.num(a.shift, 2), cls: (a.shift || 0) > 1 ? 'down' : (a.shift || 0) < -1 ? 'up' : '',
          sub: (a.shift || 0) > 1 ? 'fragile: above +1' : 'normal (warning above +1)', title: '3-week average minus 1-year average, in 1-year standard deviations.' } : null,
        a.available ? { label: 'Market factor', value: fmt.pctu(a.pc1, 0), sub: 'variance in the first principal component' } : null,
        t.available ? { label: 'Turbulence (today)', value: fmt.num(t.current, 2), cls: t.current > t.threshold_95 ? 'down' : '',
          sub: `percentile ${fmt.num(t.percentile, 0)} · typical day ≈ 1`, title: 'Mahalanobis distance of today\'s returns from normal, per stock (Kritzman & Li 2010). Catches unusual combinations of moves, not just big ones.' } : null,
        t.available ? { label: 'Turbulence (10-day)', value: fmt.num(t.current_smooth, 2), cls: t.current_smooth > t.threshold_95 ? 'down' : '',
          sub: `95% threshold ${fmt.num(t.threshold_95, 2)} · ${t.turbulent_days_21} turbulent days in 21` } : null,
      ]));
      const el = charts.div('chart');
      b.appendChild(h('div', { style: { height: '10px' } }));
      const drivers = (t.contributors || []).filter((x) => fmt.ok(x.share)).slice(0, 5).map((x) => `${x.ticker} ${fmt.pctu(x.share, 0)}`).join(' · ');
      b.appendChild(ui.panel(`${d.label}: absorption ratio and turbulence`, el,
        { cap: 'Absorption ratio (left) from the 1-year correlation matrix, every week for 5 years; turbulence (right), 10-day average, refitted monthly with a shrunk covariance. Both rising together = a crowded, correlated market under stress.' + (drivers ? ` Today\'s turbulence is driven by: ${drivers}.` : '') }));
      const series = [];
      if (a.series) series.push({ name: 'Absorption ratio', t: a.series.t, v: a.series.ar, color: 'accent', width: 1.8 });
      if (t.series) series.push({ name: 'Turbulence (10d)', t: t.series.t, v: t.series.smooth, color: 'teal', width: 1.2, y2: true });
      charts.lines(el, series, { yfmt: '.0%', y2: !!t.series, y2fmt: '.1f' });
    }, 300);
  };

  // ─── Factor lab page ─────────────────────────────────────────────────────────────────
  SQ.views.factorlab = async function (view, parts, params) {
    let uni = params.u || 'semis';
    view.appendChild(h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Factor lab'),
      h('div', { class: 'sub' }, 'Do classic price signals predict next month\'s returns? Monthly rank information coefficients, quintile spreads, decay and turnover: the research loop of a systematic equity desk.'))));
    const UNIS = [['semis', 'Semiconductors'], ['us_large', 'US large caps'], ['global', 'Global leaders'], ['etfs', 'ETFs']];
    view.appendChild(ui.seg(UNIS, uni, (v) => { uni = v; history.replaceState(null, '', '#/factorlab?u=' + v); load(); }));
    const box = h('div', { style: { marginTop: '12px' } });
    view.appendChild(box);
    function load() {
      charts.disposeAll(box);
      box.innerHTML = '';
      ui.async(box, () => api('/api/factorlab?u=' + uni), (b, d) => {
        if (!d.available) { b.appendChild(ui.empty(d.message || 'Not available for this universe.')); return; }
        const sigs = d.signals || [];
        let pick = sigs.slice().sort((x, y) => Math.abs(y.ic_t || 0) - Math.abs(x.ic_t || 0))[0];
        b.appendChild(h('p', { class: 'note' }, `${d.label}: ${d.n_assets} stocks, ${d.months} months (${fmt.date(d.start)} → ${fmt.date(d.end)}). `,
          h('b', null, 'Read the t-statistic: '), '|t| above 2 means the signal has reliably ranked next month\'s winners (positive) or losers (negative); below 1 is noise.'));
        b.appendChild(sec('Signal scorecard'));
        const detail = h('div');
        b.appendChild(ui.panel(null, ui.table([
          { key: 'label', label: 'Signal', l: true, txt: true, title: 'Higher signal value = the side the signal favours' },
          { key: 'ic_mean', label: 'Mean IC', fmt: 'num', d: 3, sign: true }, { key: 'ic_t', label: 'IC t-stat', fmt: 'num', d: 2, sign: true },
          { key: 'hit_rate', label: 'IC > 0', fmt: 'pctu', d: 0 },
          { key: 'ls_ann', label: 'Top-bottom /yr', fmt: 'pct', d: 1, sign: true, get: (r) => r.spread.ann },
          { key: 'ls_sh', label: 'Sharpe', fmt: 'num', d: 2, get: (r) => r.spread.sharpe },
          { key: 'ls_dd', label: 'Max DD', fmt: 'pct', d: 0, get: (r) => r.spread.max_dd },
          { key: 'turnover', label: 'Turnover /mo', fmt: 'pctu', d: 0 },
          { key: 'd3', label: 'IC 3M', fmt: 'num', d: 3, get: (r) => r.decay['3'] }, { key: 'd6', label: 'IC 6M', fmt: 'num', d: 3, get: (r) => r.decay['6'] }],
        sigs, { onRow: (r) => { pick = r; drawDetail(); }, sort: 'ic_t' }),
        { cap: 'IC = rank correlation between the signal at a month-end and the next month\'s returns across the universe. Top-bottom = equal-weight top quintile minus bottom quintile, rebalanced monthly. Tap a row for its details.' }));
        const cumEl = charts.div('chart');
        b.appendChild(h('div', { style: { height: '10px' } }));
        b.appendChild(ui.panel('Top-minus-bottom quintile, cumulative', cumEl, { cap: 'Long the top fifth, short the bottom fifth of the universe by each signal, before costs.' }));
        charts.lines(cumEl, sigs.map((s) => ({ name: s.label, t: s.spread_cum.t, v: s.spread_cum.v })), { yfmt: '.0%' });
        b.appendChild(detail);
        function drawDetail() {
          charts.disposeAll(detail);
          detail.innerHTML = '';
          if (!pick) return;
          detail.appendChild(sec(pick.label));
          detail.appendChild(h('p', { class: 'note' }, pick.desc));
          const g = h('div', { class: 'grid g2', style: { marginTop: '8px' } });
          detail.appendChild(g);
          const qEl = charts.div('chart short'), iEl = charts.div('chart short');
          g.appendChild(ui.panel('Return by quintile (annualised)', qEl, { cap: 'Q1 = weakest signal, Q5 = strongest. A clean staircase is what a real factor looks like.' }));
          g.appendChild(ui.panel('Monthly IC', iEl, { cap: `Mean ${fmt.num(pick.ic_mean, 3)} · decay: 1M ${fmt.num(pick.decay['1'], 3)}, 3M ${fmt.num(pick.decay['3'], 3)}, 6M ${fmt.num(pick.decay['6'], 3)}.` }));
          charts.bars(qEl, { x: ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], y: pick.quintiles, colors: 'sign' }, { yfmt: '.0%' });
          charts.bars(iEl, { x: pick.ic_series.t, y: pick.ic_series.v, colors: 'sign' }, { yfmt: '.2f', xtype: 'date' });
        }
        drawDetail();
        const sc = d.signal_corr;
        if (sc && sc.z) {
          const hEl = charts.div('chart');
          b.appendChild(sec('How alike are the signals?'));
          b.appendChild(ui.panel(null, hEl, { cap: 'Average cross-sectional rank correlation between signals. Highly correlated signals are the same bet twice.' + (window.innerWidth < 560 ? ' Mom = momentum 12-1, Rev = reversal, LowV = low volatility, 52W = 52-week-high proximity, LowB = low beta.' : '') }));
          hEl.style.height = Math.max(260, 34 * sc.labels.length + 80) + 'px';
          const tiny = { 'Momentum 12-1': 'Mom', 'Short-term reversal': 'Rev', 'Low volatility': 'LowV', '52-week-high proximity': '52W', Trend: 'Trend', 'Low beta': 'LowB' };
          const short = (x) => (hEl.clientWidth && hEl.clientWidth < 560 ? tiny[x] || x
            : x.replace('52-week-high proximity', '52W high').replace('Short-term reversal', 'Reversal').replace('Momentum 12-1', 'Mom 12-1').replace('Low volatility', 'Low vol'));
          charts.heatmap(hEl, { z: sc.z, x: sc.labels.map(short), y: sc.labels.map(short) }, { fmt: 'num', d: 2, zmin: -1, zmax: 1, margin: { l: 80, r: 8, t: 8, b: 70 } });
        }
        const cur = d.current;
        if (cur) {
          b.appendChild(sec(`Today's ranking (all signals combined, ${fmt.date(cur.asof)})`));
          const cols = [{ key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'name', label: 'Name', l: true, txt: true },
            { key: 'composite', label: 'Composite z', fmt: 'num', d: 2, sign: true }].concat(sigs.map((s) => ({ key: s.key, label: s.label.replace('52-week-high proximity', '52W high').replace('Short-term reversal', 'Reversal'), fmt: 'num', d: 1, sign: true })));
          const gg = h('div', { class: 'grid g2' });
          b.appendChild(gg);
          gg.appendChild(ui.panel('Strongest', ui.table(cols, cur.top || [], { onRow: (r) => SQ.go('#/t/' + encodeURIComponent(r.ticker)) })));
          gg.appendChild(ui.panel('Weakest', ui.table(cols, cur.bottom || [], { onRow: (r) => SQ.go('#/t/' + encodeURIComponent(r.ticker)), desc: false })));
        }
        if (d.caveats) b.appendChild(h('div', { class: 'note', style: { marginTop: '12px' } }, h('b', null, 'Caveats: '), d.caveats.join(' ')));
      }, 500);
    }
    load();
  };
})();
