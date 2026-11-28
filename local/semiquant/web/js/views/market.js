/* Market dashboard. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt, ui, api, charts } = SQ;

  function tile(r) {
    const el = h('div', { class: 'tile', title: `${r.name || r.label} (${r.symbol})`, onclick: () => SQ.go('#/t/' + encodeURIComponent(r.symbol)) },
      h('div', { class: 'lb' }, h('span', null, r.label), h('span', null, r.symbol)),
      h('div', { class: 'px', dataset: { live: r.symbol + ':price:price' } }, fmt.price(r.price)),
      h('div', { class: 'ch ' + fmt.cls(r.change_pct), dataset: { live: r.symbol + ':change_pct:pct', sign: 'change_pct' } }, fmt.pct(r.change_pct, 2)));
    if (r.spark && r.spark.length > 1) el.appendChild(ui.spark(r.spark));
    return el;
  }

  // Compact quote board: one row per symbol (label, price, change, 3-month spark).
  function quoteBoard(title, rows) {
    const bp = title === 'Rates';  // yields: show the change in basis points
    const body = h('div', { class: 'qb' }, rows.map((r) => h('div', { class: 'qb-row', title: `${r.name || r.label} (${r.symbol})`, onclick: () => SQ.go('#/t/' + encodeURIComponent(r.symbol)) },
      h('span', { class: 'qb-l' }, r.label, h('small', null, r.symbol)),
      h('span', { class: 'qb-p', dataset: { live: r.symbol + ':price:' + (bp ? 'num' : 'price') } }, bp ? fmt.num(r.price, 3) + '%' : fmt.price(r.price)),
      bp ? h('span', { class: 'qb-c ' + fmt.cls(r.change) }, fmt.ok(r.change) ? (r.change > 0 ? '+' : '') + (r.change * 100).toFixed(1) + ' bp' : '–')
        : h('span', { class: 'qb-c ' + fmt.cls(r.change_pct), dataset: { live: r.symbol + ':change_pct:pct', sign: 'change_pct' } }, fmt.pct(r.change_pct, 2)),
      ui.spark(r.spark, 56, 18))));
    return ui.panel(title, body);
  }

  SQ.views.market = async function (view) {
    view.appendChild(h('div', { class: 'page-h' },
      h('div', null, h('h1', null, 'Markets'),
        h('div', { class: 'sub' }, SQ.static
          ? 'Yahoo Finance data published every ~15 minutes in market hours; this page checks for a new build every minute. Semiconductors, US large caps across all sectors, global leaders and ETFs. Tap anything to open it.'
          : ['Live Yahoo Finance quotes, refreshed automatically (every ', String(SQ.settings.quote_refresh_seconds), ' s while markets are open). Semiconductors, US large caps across all sectors, global leaders and ETFs. Click anything to open it.'])),
      h('div', { class: 'actions' },
        h('button', { class: 'btn', onclick: () => (SQ.static ? SQ.shareLink('Semi Quant Terminal: markets') : ui.download('/api/export/snapshot.html?market=true')), title: 'One HTML file with this dashboard and the screener: send it to a friend, it opens in any browser' },
          h('span', { html: '<svg viewBox="0 0 24 24"><path d="M4 12v7h16v-7M12 3v12m0-12l-4 4m4-4l4 4"/></svg>' }), SQ.static ? 'Share' : 'Share snapshot'),
        h('a', { class: 'btn', href: '#/screener' }, 'Open screener'))));

    // Global strip
    const stripBox = h('div');
    view.appendChild(stripBox);
    ui.async(stripBox, () => api('/api/market/strip'), (box, s) => {
      SQ.live.register('market-strip', Object.values(s.groups).flat().map((r) => r.symbol));
      const board = h('div', { class: 'grid g3' });
      for (const [g, rows] of Object.entries(s.groups)) board.appendChild(quoteBoard(g, rows));
      box.appendChild(board);
      // Rates & volatility structure + sector rotation
      box.appendChild(ui.sec('Volatility, rates & sector rotation'));
      const vixEl = charts.div('chart short'), ycEl = charts.div('chart short'), secEl = charts.div('chart short');
      const ratio = s.vix_ratio;
      const vixCap = fmt.ok(ratio) ? (ratio > 1 ? `<b class="down">Backwardation</b> (VIX / VIX3M = ${ratio.toFixed(2)}): near-term fear exceeds longer-term, typical of stress.`
        : `<b class="up">Contango</b> (VIX / VIX3M = ${ratio.toFixed(2)}): the normal, calm shape.`) : '';
      const sp = s.spread_10y_3m;
      const ycCap = fmt.ok(sp) ? `10Y minus 3M spread: <b class="${sp < 0 ? 'down' : 'up'}">${sp.toFixed(2)} pp</b>${sp < 0 ? ' (inverted: historically a recession warning)' : ''}.` : '';
      let secPeriod = 'change_pct';
      const secBox = h('div');
      const drawSec = () => {
        const rows = s.sectors.filter((r) => fmt.ok(r[secPeriod])).sort((a, b) => b[secPeriod] - a[secPeriod]);
        charts.bars(secEl, { x: rows.map((r) => r[secPeriod]), y: rows.map((r) => r.label), horizontal: true, colors: 'sign' },
          { horizontal: true, xfmt: '.1%', margin: { l: 96, r: 10, t: 4, b: 26 } });
      };
      box.appendChild(h('div', { class: 'grid g3' },
        ui.panel('VIX term structure', vixEl, { cap: vixCap }),
        ui.panel('US Treasury yield curve', ycEl, { cap: ycCap }),
        ui.panel('Sector ETFs', h('div', null, secEl), { right: ui.seg([['change_pct', '1D'], ['ret_5d', '1W'], ['ret_1m', '1M'], ['ret_3m', '3M']], secPeriod, (v) => { secPeriod = v; drawSec(); }) })));
      const vt = s.vix_term.filter((r) => fmt.ok(r.value));
      charts.lines(vixEl, [{ name: 'VIX curve', t: vt.map((r) => r.label), v: vt.map((r) => r.value), mode: 'lines+markers', color: 'accent', width: 2 }],
        { yfmt: '.1f', legend: false, xtype: 'category', hovermode: 'closest', margin: { l: 40, r: 10, t: 8, b: 28 } });
      const yc = s.yield_curve.filter((r) => fmt.ok(r.value));
      charts.lines(ycEl, [{ name: 'Yield', t: yc.map((r) => r.label), v: yc.map((r) => r.value / 100), mode: 'lines+markers', color: 'warn', width: 2 }],
        { yfmt: '.2%', legend: false, xtype: 'category', hovermode: 'closest', margin: { l: 50, r: 10, t: 8, b: 28 } });
      drawSec();
      void secBox;
    }, 260);

    // Universe section: heatmap, movers, group moves, breadth & regime for the chosen universe
    const UNIS = [['semis', 'Semiconductors'], ['us_large', 'US large caps'], ['global', 'Global leaders'], ['etfs', 'ETFs']];
    let uni = 'semis';
    try { uni = localStorage.getItem('sq_u') || 'semis'; } catch (e) { /* ignore */ }
    if (SQ.snapshot && !['semis', 'us_large'].includes(uni)) uni = 'semis';
    const uniHead = h('div', { class: 't-tools', style: { margin: '26px 0 10px' } }, h('span', { class: 'label' }, 'Today in'));
    const uniBox = h('div');
    view.appendChild(uniHead);
    view.appendChild(uniBox);
    uniHead.appendChild(ui.seg(SQ.snapshot ? UNIS.slice(0, 2) : UNIS, uni, (v) => {
      uni = v;
      try { localStorage.setItem('sq_u', v); } catch (e) { /* ignore */ }
      drawUniverse();
    }));
    uniHead.appendChild(h('a', { class: 'btn sm', href: '#', onclick: (e) => { e.preventDefault(); SQ.go('#/screener?u=' + uni); } }, 'Screen this universe'));
    let uniCleanup = [];
    function drawUniverse() {
      uniCleanup.splice(0).forEach((fn) => { try { fn(); } catch (e) { /* ignore */ } });
      charts.disposeAll(uniBox);
      uniBox.innerHTML = '';
      const hmGrid = h('div', { class: 'grid g-main' });
      const hmBox = h('div'), sideBox = h('div'), brHead = h('div'), brBox = h('div');
      hmGrid.appendChild(hmBox); hmGrid.appendChild(sideBox);
      uniBox.appendChild(hmGrid); uniBox.appendChild(brHead); uniBox.appendChild(brBox);
      const syBox = h('div');
      uniBox.appendChild(syBox);
      if (SQ.qp) SQ.qp.systemic(syBox, uni);
      ui.async(hmBox, () => api('/api/market/heatmap?u=' + uni), (box, d) => {
        const el = charts.div('chart tall');
        const capped = d.tiles.filter((t) => t.market_cap_usd && !t.missing).length;
        const equal = capped < d.tiles.length / 2;  // caps unknown (ETFs, or first run while Yahoo throttles)
        const size = (t) => (equal ? 1 : t.market_cap_usd);
        const draw = (tiles) => {
          const sectors = Array.from(new Set(tiles.map((t) => t.sector)));
          const ids = [], labels = [], parents = [], values = [], colors = [], text = [], custom = [];
          sectors.forEach((s) => {
            const kids = tiles.filter((t) => t.sector === s && !t.missing && size(t));
            const tot = kids.reduce((a, t) => a + size(t), 0);
            if (!tot) return;
            ids.push('s:' + s); labels.push(s); parents.push(''); values.push(tot);
            const w = kids.reduce((a, t) => a + size(t) * (t.change_pct || 0), 0) / tot;
            colors.push(w); text.push(fmt.pct(w, 2)); custom.push(`${s} · ${equal ? kids.length + ' names' : fmt.money(tot)} · ${fmt.pct(w, 2)}`);
            kids.forEach((t) => {
              ids.push(t.ticker); labels.push(t.ticker); parents.push('s:' + s); values.push(size(t));
              colors.push(t.change_pct || 0); text.push(fmt.pct(t.change_pct, 2));
              custom.push(`${t.name} · ${fmt.price(t.price)} ${t.currency || ''} · ${fmt.pct(t.change_pct, 2)}${t.market_cap_usd ? ' · cap ' + fmt.money(t.market_cap_usd) : ''}`);
            });
          });
          charts.treemap(el, { ids, labels, parents, values, colors, text, custom }, { scale: uni === 'etfs' ? 0.025 : 0.04 });
        };
        box.appendChild(ui.panel(`${d.label}: ${equal ? 'heatmap' : 'heatmap by market cap (USD)'}, coloured by today's move`, el,
          { cap: `Click a tile to open it. ${d.group_label} tiles show the ${equal ? 'average' : 'cap-weighted'} move. ` +
            (equal && uni !== 'etfs' ? 'Tiles are equal-sized until market caps load. ' : '') +
            (d.missing && d.missing.length ? `No recent trades: ${d.missing.join(', ')} (delisted or suspended).` : '') }));
        draw(d.tiles);
        el.on && el.on('plotly_click', (ev) => {
          const p = ev.points && ev.points[0];
          if (p && p.id && !String(p.id).startsWith('s:') && p.id !== 'root') SQ.go('#/t/' + encodeURIComponent(p.id));
        });
        SQ.live.register('market-heat', d.tiles.map((t) => t.ticker));
        let redraw = null, drawn = 0;
        const off = SQ.live.onQuotes((qs) => {
          let changed = false;
          d.tiles.forEach((t) => { const q = qs[t.ticker]; if (q && q.change_pct !== t.change_pct) { t.change_pct = q.change_pct; t.price = q.price; changed = true; } });
          if (!changed || redraw) return; // streamed ticks: redraw at most every 4 s
          redraw = setTimeout(() => { redraw = null; drawn = Date.now(); if (el.isConnected) draw(d.tiles); }, Math.max(0, 4000 - (Date.now() - drawn)));
        });
        uniCleanup.push(() => clearTimeout(redraw));
        uniCleanup.push(off, () => SQ.live.unregister('market-heat'));
        const tot = d.advancers + d.decliners;
        sideBox.appendChild(ui.kpis([
          { label: 'Advancers', value: String(d.advancers), cls: 'up', sub: tot ? fmt.pctu(d.advancers / tot, 0) + ' of names' : '' },
          { label: 'Decliners', value: String(d.decliners), cls: 'down', sub: tot ? fmt.pctu(d.decliners / tot, 0) + ' of names' : '' },
        ]));
        const secEl = charts.div('chart short');
        secEl.style.height = Math.max(220, 22 * d.sectors.length + 40) + 'px';
        sideBox.appendChild(h('div', { style: { height: '12px' } }));
        sideBox.appendChild(ui.panel(`${d.group_label} moves (${equal ? 'average' : 'cap-weighted'})`, secEl));
        charts.bars(secEl, { x: d.sectors.map((s) => s.change_pct), y: d.sectors.map((s) => s.sector), horizontal: true, colors: 'sign' },
          { horizontal: true, xfmt: '.1%', margin: { l: 120, r: 10, t: 4, b: 26 } });
        const mv = (rows, best) => ui.table([
          { key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'name', label: 'Name', l: true, txt: true },
          { key: 'change_pct', label: 'Day', fmt: 'pct', d: 2, sign: true }], rows, { onRow: (r) => SQ.go('#/t/' + encodeURIComponent(r.ticker)), sort: 'change_pct', desc: best });
        sideBox.appendChild(h('div', { style: { height: '12px' } }));
        sideBox.appendChild(h('div', { class: 'grid g2' }, ui.panel('Top gainers', mv(d.gainers, true)), ui.panel('Top losers', mv(d.losers, false))));
      }, 520);

      brHead.appendChild(ui.sec('Breadth & regime (daily)'));
      ui.async(brBox, () => api('/api/market/breadth?u=' + uni), (box, d) => {
        const b = d.breadth || {}, r = d.regime || {};
        const cur = r.current_label;
        const probs = r.current_probs || [];
        box.appendChild(ui.kpis([
          { label: 'Above 20-day avg', value: fmt.pctu(b.pct_above_sma20, 0) },
          { label: 'Above 50-day avg', value: fmt.pctu(b.pct_above_sma50, 0) },
          { label: 'Above 200-day avg', value: fmt.pctu(b.pct_above_sma200, 0) },
          { label: 'New 52W highs / lows', value: `${b.new_highs_52w ?? '–'} / ${b.new_lows_52w ?? '–'}` },
          { label: 'Avg correlation 63d', value: fmt.num(b.avg_corr_63d, 2), title: 'High correlation = names move together (macro-driven); low = stock-picker\'s market' },
          { label: '1M dispersion', value: fmt.pctu(b.dispersion_1m, 1), title: 'Cross-sectional standard deviation of 1-month returns' },
          { label: `${d.regime_ref} regime (HMM)`, value: cur || '–', cls: cur === 'Turbulent' ? 'down' : cur === 'Calm' ? 'up' : '',
            sub: probs.length ? 'P(calm) ' + fmt.pctu(probs[0], 0) : '' },
        ]));
        const el = charts.div('chart short');
        box.appendChild(h('div', { style: { height: '12px' } }));
        const states = (r.states || []).map((s) => `${s.label}: ${fmt.pctu(s.vol_ann, 0)} vol, lasts ~${fmt.num(s.expected_duration_days, 0)} days`).join(' · ');
        box.appendChild(ui.panel(`${d.label}: share above the 50-day average (1 year)`, el,
          { cap: `Breadth above 70% = broad strength; below 30% = washed-out. Regime: two-state Gaussian hidden Markov model on ${d.regime_ref} daily returns (5 years). ` + states }));
        if (b.pct_above_sma50_series) charts.lines(el, [{ name: '% above 50d', ...b.pct_above_sma50_series, color: 'accent', fill: 'tozeroy', fillcolor: 'rgba(' + charts.theme().accentRgb + ',.08)' }],
          { yfmt: '.0%', legend: false, shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0.5, y1: 0.5 }] });
      }, 200);
    }
    SQ.onCleanup(() => uniCleanup.splice(0).forEach((fn) => { try { fn(); } catch (e) { /* ignore */ } }));
    drawUniverse();

    // Movers + earnings + news
    view.appendChild(ui.sec('US movers, upcoming earnings & news'));
    const g = h('div', { class: 'grid g3' });
    view.appendChild(g);
    const mvBox = h('div'), erBox = h('div'), nwBox = h('div');
    g.appendChild(mvBox); g.appendChild(erBox); g.appendChild(nwBox);
    ui.async(mvBox, () => api('/api/market/movers'), (box, d) => {
      let which = 'gainers';
      const tb = h('div');
      const draw = () => {
        tb.innerHTML = '';
        tb.appendChild(ui.table([{ key: 'symbol', label: 'Symbol', l: true, cls: 'sym' }, { key: 'name', label: 'Name', l: true, txt: true },
          { key: 'price', label: 'Price', fmt: 'price' }, { key: 'change_pct', label: 'Day', fmt: 'pct', d: 2, sign: true },
          { key: 'volume', label: 'Volume', fmt: 'big' }], d[which] || [], { onRow: (r) => SQ.go('#/t/' + r.symbol) }));
      };
      box.appendChild(ui.panel('US stocks (Yahoo screens)', tb, { right: ui.seg([['gainers', 'Gainers'], ['losers', 'Losers'], ['active', 'Most active']], which, (v) => { which = v; draw(); }) }));
      draw();
    }, 300);
    ui.async(erBox, () => api('/api/market/earnings'), (box, rows) => {
      box.appendChild(ui.panel('Universe earnings, next 30 days', rows.length ? ui.table([
        { key: 'ticker', label: 'Ticker', l: true, cls: 'sym' }, { key: 'name', label: 'Company', l: true, txt: true },
        { key: 'time', label: 'When', render: (r) => fmt.dateTime(r.time) + (r.estimated ? ' (est.)' : '') }], rows,
      { onRow: (r) => SQ.go('#/t/' + r.ticker + '/analysts'), sort: 'time', desc: false }) : ui.empty('No universe company reports in the next 30 days.'),
      { right: h('a', { class: 'btn sm', href: '#/calendar' }, 'Full calendar') }));
    }, 300);
    ui.async(nwBox, () => api('/api/market/news'), (box, items) => {
      box.appendChild(ui.panel('Latest headlines', newsList(items.slice(0, 10))));
    }, 300);
  };

  function newsList(items) {
    if (!items || !items.length) return ui.empty('No news right now.');
    return h('div', { class: 'news' }, items.map((n) => h('a', { href: n.url || '#', target: '_blank', rel: 'noopener' },
      h('span', { class: 'tt' }, n.title), n.thumbnail ? h('img', { src: n.thumbnail, alt: '', loading: 'lazy' }) : null,
      h('span', { class: 'src' }, [n.publisher, fmt.ago(n.time)].filter(Boolean).join(' · ')))));
  }
  SQ.newsList = newsList;
})();
