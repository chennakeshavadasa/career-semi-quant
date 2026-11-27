/* Charts: Plotly (analytics) themed from the CSS tokens and re-themed live, plus a
 * TradingView-style price chart (lightweight-charts 4.2) with indicator panes. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const { h, fmt } = SQ;
  const registry = new Set(); // Plotly elements
  const lwcs = new Set(); // price chart instances

  function theme() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    return {
      ink: v('--ink'), ink2: v('--ink-2'), ink3: v('--ink-3'), ink4: v('--ink-4'), rule: v('--rule'), ruleStrong: v('--rule-strong'),
      accent: v('--accent'), up: v('--up'), down: v('--down'), warn: v('--warn'), violet: v('--violet'), teal: v('--teal'),
      pink: v('--pink'), card: v('--card'), page: v('--page'), raise: v('--raise'), mono: v('--mono'), serif: v('--serif'),
      upRgb: v('--up-rgb'), downRgb: v('--down-rgb'), accentRgb: v('--accent-rgb'), dark: document.documentElement.getAttribute('data-theme') === 'dark',
    };
  }
  const NAMED = ['accent', 'up', 'down', 'warn', 'violet', 'teal', 'pink', 'ink', 'ink2', 'ink3', 'ink4'];
  const col = (t, c) => (NAMED.includes(c) ? t[c] : c);
  const palette = (t) => [t.accent, t.warn, t.violet, t.teal, t.pink, t.up, t.down, t.ink3, t.ink2];

  function merge(a, b) {
    const out = { ...a };
    for (const [k, v] of Object.entries(b || {})) {
      if (v === undefined) continue; // Plotly chokes on keys like yaxis2: undefined
      out[k] = v && typeof v === 'object' && !Array.isArray(v) && a[k] && typeof a[k] === 'object' && !Array.isArray(a[k]) ? merge(a[k], v) : v;
    }
    return out;
  }
  function axis(t) {
    return { gridcolor: t.rule, zerolinecolor: t.ruleStrong, linecolor: t.ruleStrong, tickfont: { size: 10.5, color: t.ink3 }, automargin: true, showspikes: false };
  }
  function baseLayout(t) {
    return {
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { family: t.mono, size: 11, color: t.ink3 },
      margin: { l: 50, r: 14, t: 8, b: 32 }, colorway: palette(t), xaxis: axis(t), yaxis: axis(t),
      legend: { orientation: 'h', y: 1.02, yanchor: 'bottom', x: 0, font: { size: 11, color: t.ink2 }, bgcolor: 'rgba(0,0,0,0)' },
      hoverlabel: { bgcolor: t.card, bordercolor: t.ruleStrong, font: { family: t.mono, size: 12, color: t.ink } },
      hovermode: 'x unified', showlegend: true, dragmode: TOUCH ? false : 'zoom',
    };
  }
  // Touch screens: no toolbar and no drag-zoom, so swipes scroll the page (tap still shows values).
  const TOUCH = window.matchMedia && matchMedia('(hover: none)').matches;
  const CONFIG = {
    displaylogo: false, responsive: true, displayModeBar: TOUCH ? false : 'hover',
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines', 'hoverCompareCartesian', 'hoverClosestCartesian'],
    toImageButtonOptions: { format: 'png', scale: 2, filename: 'semiquant-chart' },
  };

  // plot(el, build): build(theme) -> {data, layout}; re-run on theme change.
  function plot(el, build) {
    if (!window.Plotly) { el.appendChild(SQ.ui.empty('Chart library failed to load.')); return el; }
    el._sqBuild = build;
    const draw = () => {
      const t = theme();
      const spec = build(t);
      const layout = merge(baseLayout(t), spec.layout || {});
      Plotly.react(el, spec.data, layout, { ...CONFIG, ...(spec.config || {}) });
    };
    el._sqDraw = draw;
    draw();
    registry.add(el);
    return el;
  }
  window.addEventListener('sq-theme', () => {
    for (const el of Array.from(registry)) {
      if (!document.body.contains(el)) { registry.delete(el); continue; }
      try { el._sqDraw(); } catch (e) { /* ignore */ }
    }
    for (const c of Array.from(lwcs)) c.retheme && c.retheme();
  });

  function disposeAll(root) {
    for (const el of Array.from(registry)) {
      if (!root || root.contains(el)) { try { Plotly.purge(el); } catch (e) { /* ignore */ } registry.delete(el); }
    }
    for (const c of Array.from(lwcs)) {
      if (!root || root.contains(c.root)) { c.destroy(); }
    }
  }

  const div = (cls = 'chart') => h('div', { class: cls });

  // ─── Plotly builders ──────────────────────────────────────────────────
  // series: [{name, t, v, color, dash, width, fill, y2, mode, shape, opacity}]
  function lines(el, series, o = {}) {
    return plot(el, (t) => ({
      data: series.filter((s) => s && s.t && s.t.length).map((s, i) => ({
        type: 'scatter', mode: s.mode || 'lines', name: s.name, x: s.t, y: s.v, yaxis: s.y2 ? 'y2' : 'y',
        line: { color: col(t, s.color) || palette(t)[i % 9], width: s.width || 1.6, dash: s.dash || 'solid', shape: s.shape || 'linear' },
        fill: s.fill || undefined, fillcolor: s.fillcolor ? col(t, s.fillcolor) : undefined, opacity: s.opacity,
        hovertemplate: s.hover || ('%{y:' + (s.y2 ? (o.y2fmt || o.yfmt || ',.2f') : (o.yfmt || ',.2f')) + '}'),
        connectgaps: false, showlegend: s.legend !== false,
      })),
      layout: merge({
        yaxis: { tickformat: o.yfmt || undefined, title: o.ytitle ? { text: o.ytitle, font: { size: 11 } } : undefined, type: o.logy ? 'log' : undefined, rangemode: o.zero ? 'tozero' : undefined },
        yaxis2: o.y2 ? { overlaying: 'y', side: 'right', tickformat: o.y2fmt, showgrid: false, ...axis(t), title: o.y2title ? { text: o.y2title, font: { size: 11 } } : undefined } : undefined,
        xaxis: { type: o.xtype || undefined, title: o.xtitle ? { text: o.xtitle, font: { size: 11 } } : undefined, tickformat: o.xfmt },
        shapes: (o.shapes || []).map((sh) => ({ ...sh, line: { color: col(t, (sh.line || {}).color || 'ink4'), width: (sh.line || {}).width || 1, dash: (sh.line || {}).dash || 'dot' } })),
        annotations: o.annotations || [], showlegend: o.legend !== false, hovermode: o.hovermode || 'x unified',
        margin: o.margin,
      }, o.layout || {}),
    }));
  }

  // bars: {x, y, name, colors: array|'sign'|named, text, horizontal, hover}
  function bars(el, sets, o = {}) {
    const arr = Array.isArray(sets) ? sets : [sets];
    return plot(el, (t) => ({
      data: arr.map((s, i) => {
        let c = s.colors;
        if (c === 'sign') c = (s.horizontal ? s.x : s.y).map((v) => (v >= 0 ? t.up : t.down));
        else if (Array.isArray(c)) c = c.map((x) => col(t, x));
        else c = col(t, c) || palette(t)[i % 9];
        return {
          type: 'bar', name: s.name, x: s.horizontal ? s.x : s.x, y: s.y, orientation: s.horizontal ? 'h' : 'v',
          marker: { color: c, opacity: s.opacity ?? 0.85, line: { width: 0 } }, text: s.text, textposition: s.text ? 'outside' : undefined,
          textfont: { size: 10.5, color: t.ink2 }, cliponaxis: false,
          hovertemplate: s.hover || (s.horizontal ? '%{y}: %{x:' + (o.xfmt || o.yfmt || ',.2f') + '}<extra></extra>' : '%{x}: %{y:' + (o.yfmt || ',.2f') + '}<extra>' + (s.name || '') + '</extra>'),
        };
      }),
      layout: merge({
        barmode: o.barmode || 'group', bargap: 0.25, showlegend: arr.length > 1 && o.legend !== false, hovermode: 'closest',
        yaxis: { tickformat: o.horizontal ? undefined : o.yfmt, automargin: true, autorange: o.horizontal ? 'reversed' : undefined, title: o.ytitle ? { text: o.ytitle, font: { size: 11 } } : undefined,
          type: o.horizontal ? 'category' : undefined, dtick: o.horizontal ? 1 : undefined, tickfont: o.horizontal ? { size: 10.5 } : undefined },
        xaxis: { tickformat: o.horizontal ? (o.xfmt || o.yfmt) : undefined, type: o.xtype, title: o.xtitle ? { text: o.xtitle, font: { size: 11 } } : undefined },
        shapes: (o.shapes || []).map((sh) => ({ ...sh, line: { color: col(t, (sh.line || {}).color || 'ink4'), width: 1, dash: (sh.line || {}).dash || 'dot' } })),
        margin: o.margin,
      }, o.layout || {}),
    }));
  }

  // heatmap: {z, x, y, text}; o.div (diverging around zmid), o.fmt
  function heatmap(el, d, o = {}) {
    return plot(el, (t) => {
      const seq = [[0, t.dark ? '#16233a' : '#eef2fb'], [1, t.accent]];
      const dv = [[0, t.down], [0.5, t.dark ? '#1c2636' : '#f3f5f8'], [1, t.up]];
      const z = d.z;
      let zmin = o.zmin, zmax = o.zmax;
      if (o.div !== false && (zmin == null || zmax == null)) {
        const flat = z.flat().filter(fmt.ok);
        const m = Math.max(...flat.map((v) => Math.abs(v - (o.zmid || 0))), 1e-9);
        zmin = (o.zmid || 0) - m; zmax = (o.zmid || 0) + m;
      }
      return {
        data: [{
          type: 'heatmap', z, x: d.x, y: d.y, colorscale: o.colors || (o.div === false ? seq : dv), zmin, zmax, xgap: 1.5, ygap: 1.5,
          text: d.text || z.map((r) => r.map((v) => (fmt.ok(v) ? (o.fmt === 'num' ? v.toFixed(2) : fmt.pct(v, o.d ?? 1)) : ''))),
          texttemplate: o.showText === false ? undefined : '%{text}', textfont: { size: o.textSize || 10.5, family: t.mono },
          hovertemplate: '%{y} · %{x}: %{text}<extra></extra>', showscale: false,
        }],
        layout: { hovermode: 'closest', showlegend: false, xaxis: { side: o.xtop ? 'top' : 'bottom', type: 'category', showgrid: false },
          yaxis: { autorange: 'reversed', type: 'category', showgrid: false }, margin: o.margin || { l: 70, r: 10, t: o.xtop ? 30 : 8, b: 40 } },
      };
    });
  }

  // scatter: points [{x, y, text, size, color, symbol}]
  function scatter(el, sets, o = {}) {
    const arr = Array.isArray(sets) ? sets : [sets];
    return plot(el, (t) => ({
      data: arr.map((s, i) => ({
        type: 'scatter', mode: s.mode || 'markers+text', name: s.name, x: s.x, y: s.y, text: s.text,
        textposition: 'top center', textfont: { size: 10.5, color: t.ink2, family: t.mono },
        marker: { size: s.size || 9, color: Array.isArray(s.color) ? s.color.map((c) => col(t, c)) : col(t, s.color) || palette(t)[i], opacity: 0.85,
          symbol: s.symbol, line: { width: 1, color: t.card } },
        line: s.line ? { color: col(t, s.line.color) || palette(t)[i], width: s.line.width || 1.5, dash: s.line.dash } : undefined,
        hovertemplate: s.hover || '%{text}<br>x %{x:' + (o.xfmt || ',.2f') + '} · y %{y:' + (o.yfmt || ',.2f') + '}<extra></extra>',
      })),
      layout: merge({
        hovermode: 'closest', showlegend: arr.length > 1,
        xaxis: { tickformat: o.xfmt, title: o.xtitle ? { text: o.xtitle, font: { size: 11 } } : undefined, zeroline: true },
        yaxis: { tickformat: o.yfmt, title: o.ytitle ? { text: o.ytitle, font: { size: 11 } } : undefined, zeroline: true },
        shapes: o.shapes || [],
      }, o.layout || {}),
    }));
  }

  function surface(el, d, o = {}) {
    return plot(el, (t) => ({
      data: [{ type: 'surface', x: d.x, y: d.y, z: d.z, colorscale: [[0, t.teal], [0.5, t.accent], [1, t.violet]], showscale: false,
        contours: { z: { show: true, usecolormap: true, project: { z: false } } }, connectgaps: false,
        hovertemplate: (o.xlabel || 'x') + ' %{x:.2f}<br>' + (o.ylabel || 'y') + ' %{y}<br>IV %{z:.1%}<extra></extra>' }],
      layout: {
        margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false,
        scene: {
          xaxis: { title: { text: o.xlabel || 'x' }, gridcolor: t.rule, color: t.ink3, backgroundcolor: 'rgba(0,0,0,0)' },
          yaxis: { title: { text: o.ylabel || 'y' }, gridcolor: t.rule, color: t.ink3, backgroundcolor: 'rgba(0,0,0,0)' },
          zaxis: { title: { text: 'IV' }, tickformat: '.0%', gridcolor: t.rule, color: t.ink3, backgroundcolor: 'rgba(0,0,0,0)' },
          camera: { eye: { x: 1.6, y: -1.5, z: 0.75 } },
        },
      },
    }));
  }

  // Treemap tiles colored by % change.
  function treemap(el, d, o = {}) {
    return plot(el, (t) => {
      const m = o.scale || 0.04;
      return {
        data: [{
          type: 'treemap', ids: ['root'].concat(d.ids), labels: [''].concat(d.labels),
          parents: [''].concat(d.parents.map((p) => p || 'root')), values: [d.values.reduce((a, v, i) => a + (d.parents[i] ? 0 : v), 0)].concat(d.values),
          branchvalues: 'total', maxdepth: 3, level: 'root',
          text: [''].concat(d.text), customdata: [''].concat(d.custom), textinfo: 'label+text',
          textfont: { family: t.mono, size: 12, color: [t.ink].concat(d.colors.map((v) => (Math.abs(v || 0) > m * 0.55 ? '#ffffff' : t.ink))) },
          marker: { colors: [0].concat(d.colors), colorscale: [[0, t.down], [0.5, t.dark ? '#253045' : '#e9edf3'], [1, t.up]], cmin: -m, cmax: m, cmid: 0,
            line: { color: t.page, width: 1.5 }, pad: { t: 18, l: 2, r: 2, b: 2 } },
          pathbar: { visible: false }, tiling: { packing: 'squarify', pad: 2 },
          hovertemplate: '<b>%{label}</b><br>%{customdata}<extra></extra>',
        }],
        layout: { margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false, uirevision: 'treemap' }, // live redraws keep a zoomed sector
        config: { displayModeBar: false },
      };
    });
  }

  // ─── Price chart (lightweight-charts) ─────────────────────────────────
  const OVERLAYS = { sma20: 'teal', sma50: 'accent', sma100: 'violet', sma200: 'warn', ema9: 'pink', ema21: 'teal', ema50: 'accent', ema200: 'warn', vwap: 'violet' };
  const PANES = ['rsi', 'macd', 'stoch', 'adx', 'atr', 'obv', 'cci', 'mfi'];

  function lwcOptions(t, intraday) {
    return {
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: t.ink3, fontFamily: t.mono, fontSize: 11, attributionLogo: true },
      grid: { vertLines: { color: t.rule }, horzLines: { color: t.rule } },
      rightPriceScale: { borderColor: t.ruleStrong },
      timeScale: { borderColor: t.ruleStrong, timeVisible: intraday, secondsVisible: false, rightOffset: 3 },
      crosshair: { mode: 0, vertLine: { color: t.ink4, labelBackgroundColor: t.ink2 }, horzLine: { color: t.ink4, labelBackgroundColor: t.ink2 } },
      localization: { priceFormatter: (p) => fmt.price(p) },
      handleScroll: { vertTouchDrag: false }, // vertical swipes scroll the page, horizontal ones pan the chart
    };
  }

  function priceChart(root, data, o = {}) {
    const LW = window.LightweightCharts;
    if (!LW) { root.appendChild(SQ.ui.empty('Chart library failed to load.')); return null; }
    const t0 = theme();
    const bars = data.bars;
    let n = bars.t.length;
    const style = o.style || (data.intraday && data.range === '1D' ? 'area' : 'candles');
    const legend = h('div', { class: 'pc-legend' });
    const mainEl = h('div', { class: 'pc-main' });
    root.appendChild(legend);
    root.appendChild(mainEl);
    const charts = [];
    const main = LW.createChart(mainEl, lwcOptions(t0, data.intraday));
    charts.push(main);
    if (o.log) main.priceScale('right').applyOptions({ mode: 1 });
    const sess = data.session;
    const inSession = (ts) => {
      if (!sess || !data.intraday) return true;
      const d = new Date(ts * 1000), m = d.getUTCHours() * 60 + d.getUTCMinutes();
      return m >= 570 && m < 960;
    };
    let series;
    const candleData = [], lineData = [], candleIdx = []; // candleIdx: index in bars of each candle
    const paint = (c) => { // extended-hours candles are drawn faded
      if (inSession(c.time)) return;
      const a = c.close >= c.open ? `rgba(${t0.upRgb},.45)` : `rgba(${t0.downRgb},.45)`;
      c.color = a; c.wickColor = a; c.borderColor = a;
    };
    for (let i = 0; i < n; i++) {
      if (!fmt.ok(bars.c[i])) continue;
      const time = bars.t[i];
      const c = { time, open: bars.o[i] ?? bars.c[i], high: bars.h[i] ?? bars.c[i], low: bars.l[i] ?? bars.c[i], close: bars.c[i] };
      paint(c);
      candleData.push(c);
      lineData.push({ time, value: bars.c[i] });
      candleIdx.push(i);
    }
    function makeMain(t) {
      if (style === 'candles') {
        series = main.addCandlestickSeries({ upColor: t.up, downColor: t.down, borderUpColor: t.up, borderDownColor: t.down, wickUpColor: t.up, wickDownColor: t.down, priceLineColor: t.ink4 });
        series.setData(candleData);
      } else if (style === 'line') {
        series = main.addLineSeries({ color: t.accent, lineWidth: 2, priceLineColor: t.ink4 });
        series.setData(lineData);
      } else {
        const upish = lineData.length > 1 && lineData[lineData.length - 1].value >= (data.prev_close || lineData[0].value);
        const c = upish ? t.up : t.down, rgb = upish ? t.upRgb : t.downRgb;
        series = main.addAreaSeries({ lineColor: c, topColor: `rgba(${rgb},.22)`, bottomColor: `rgba(${rgb},0)`, lineWidth: 2, priceLineColor: t.ink4 });
        series.setData(lineData);
      }
    }
    makeMain(t0);
    if (data.intraday && data.range === '1D' && fmt.ok(data.prev_close)) {
      series.createPriceLine({ price: data.prev_close, color: t0.ink4, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'prev close' });
    }
    // Volume
    let vol = null;
    if (bars.v && bars.v.length && o.volume !== false) {
      vol = main.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
      main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(bars.t.map((time, i) => ({ time, value: bars.v[i] || 0,
        color: (bars.c[i] >= (bars.o[i] ?? bars.c[i])) ? `rgba(${t0.upRgb},.35)` : `rgba(${t0.downRgb},.35)` })).filter((x, i) => fmt.ok(bars.c[i])));
    }
    // Overlays
    const ind = data.indicators || {};
    const overlaySeries = [];
    const toLine = (arr) => {
      const out = [];
      for (let i = 0; i < n; i++) if (fmt.ok(arr[i])) out.push({ time: bars.t[i], value: arr[i] });
      return out;
    };
    function addLine(chart, arr, color, width = 1.3, style = 0, title) {
      const s = chart.addLineSeries({ color, lineWidth: width, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, title: title || '' });
      s.setData(toLine(arr));
      return s;
    }
    for (const [name, d] of Object.entries(ind)) {
      if (PANES.includes(name)) continue;
      if (d.v) overlaySeries.push([name, addLine(main, d.v, col(t0, OVERLAYS[name] || 'teal'), name === 'sma200' ? 1.6 : 1.3)]);
      else if (name === 'bb' || name === 'keltner' || name === 'donchian') {
        const c = name === 'bb' ? t0.violet : name === 'keltner' ? t0.teal : t0.pink;
        if (d.upper) overlaySeries.push([name + ' upper', addLine(main, d.upper, c, 1, 2)]);
        if (d.mid) overlaySeries.push([name + ' mid', addLine(main, d.mid, c, 1, 1)]);
        if (d.lower) overlaySeries.push([name + ' lower', addLine(main, d.lower, c, 1, 2)]);
      } else if (name === 'ichimoku') {
        if (d.tenkan) overlaySeries.push(['tenkan', addLine(main, d.tenkan, t0.teal, 1)]);
        if (d.kijun) overlaySeries.push(['kijun', addLine(main, d.kijun, t0.down, 1)]);
        if (d.senkou_a) overlaySeries.push(['senkou A', addLine(main, d.senkou_a, t0.up, 1, 2)]);
        if (d.senkou_b) overlaySeries.push(['senkou B', addLine(main, d.senkou_b, t0.warn, 1, 2)]);
      } else if (name === 'supertrend' && d.line) {
        overlaySeries.push(['supertrend', addLine(main, d.line, t0.warn, 1.6)]);
      }
    }
    // Sub-panes
    const panes = [];
    for (const name of PANES) {
      const d = ind[name];
      if (!d) continue;
      const el = h('div', { class: 'pc-sub' }, h('span', { class: 'tag' }, name.toUpperCase()));
      root.appendChild(el);
      const paneOpts = lwcOptions(t0, data.intraday);
      paneOpts.layout.attributionLogo = false; // one TradingView attribution (main chart) is enough
      paneOpts.localization = { priceFormatter: (p) => (Math.abs(p) >= 1e6 ? fmt.big(p) : p.toFixed(2)) };
      const c = LW.createChart(el, { ...paneOpts, timeScale: { visible: false, borderColor: t0.ruleStrong } });
      charts.push(c);
      const ss = [];
      if (name === 'macd') {
        const hs = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
        hs.setData(bars.t.map((time, i) => (fmt.ok(d.hist && d.hist[i]) ? { time, value: d.hist[i], color: d.hist[i] >= 0 ? `rgba(${t0.upRgb},.55)` : `rgba(${t0.downRgb},.55)` } : null)).filter(Boolean));
        ss.push(['hist', hs], ['macd', addLine(c, d.macd || [], t0.accent, 1.4)], ['signal', addLine(c, d.signal || [], t0.warn, 1.2)]);
      } else if (d.v) {
        const s = addLine(c, d.v, t0.accent, 1.4);
        ss.push([name, s]);
        const bands = { rsi: [30, 70], mfi: [20, 80], cci: [-100, 100] }[name];
        if (bands) bands.forEach((b) => s.createPriceLine({ price: b, color: t0.ink4, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
      } else {
        Object.entries(d).forEach(([k, arr], i) => ss.push([k, addLine(c, arr, [t0.accent, t0.warn, t0.violet][i % 3], 1.3)]));
      }
      panes.push({ name, chart: c, series: ss });
    }
    // Sync time scales.
    let syncing = false;
    charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (syncing || !r) return;
      syncing = true;
      charts.forEach((o2) => { if (o2 !== c) o2.timeScale().setVisibleLogicalRange(r); });
      syncing = false;
    }));
    // Legend
    const idxByTime = new Map(bars.t.map((x, i) => [typeof x === 'object' ? JSON.stringify(x) : x, i]));
    function showLegend(i) {
      if (i == null || i < 0) i = n - 1;
      const o1 = bars.o[i], c1 = bars.c[i], prev = i > 0 ? bars.c[i - 1] : null;
      const ch = fmt.ok(prev) && fmt.ok(c1) ? c1 / prev - 1 : null;
      const tlabel = data.intraday ? new Date(bars.t[i] * 1000).toLocaleString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : fmt.date(bars.t[i]);
      const parts = [`<span class="dim">${tlabel}</span>`, `O ${fmt.price(o1)}`, `H ${fmt.price(bars.h[i])}`, `L ${fmt.price(bars.l[i])}`,
        `C <b>${fmt.price(c1)}</b>`, `<span class="${fmt.cls(ch)}">${fmt.pct(ch, 2)}</span>`];
      if (bars.v && bars.v.length) parts.push(`Vol ${fmt.big(bars.v[i])}`);
      for (const [name, d] of Object.entries(ind)) {
        if (d.v && !PANES.includes(name) && d.v[i] !== undefined) parts.push(`<span style="color:${col(theme(), OVERLAYS[name] || 'teal')}">${name.toUpperCase()} ${fmt.price(d.v[i])}</span>`);
      }
      if (ind.rsi && ind.rsi.v) parts.push(`RSI ${fmt.num(ind.rsi.v[i], 1)}`);
      if (ind.macd && ind.macd.macd) parts.push(`MACD ${fmt.num(ind.macd.macd[i], 2)}`);
      legend.innerHTML = parts.map((p) => `<span>${p}</span>`).join('');
    }
    showLegend();
    let hover = false;
    charts.forEach((c) => c.subscribeCrosshairMove((p) => {
      if (!p || p.time === undefined) { hover = false; showLegend(); return; }
      hover = true;
      showLegend(idxByTime.get(typeof p.time === 'object' ? JSON.stringify(p.time) : p.time));
    }));

    // ── live updates (stream ticks and polled quotes) ──
    // Intraday bars are on the exchange's wall clock encoded as UTC epoch seconds (see
    // service/common.epoch_local), so a tick's time is converted the same way before it is
    // bucketed into the chart's interval. Daily bars are 'YYYY-MM-DD' strings.
    const IV = { '1m': 60, '2m': 120, '5m': 300, '15m': 900, '30m': 1800, '60m': 3600, '1h': 3600, '90m': 5400 }[data.interval] || 60;
    const prepost = data.intraday && (data.range === '1D' || data.range === '5D');
    let zone = null;
    try {
      if (data.tz) zone = new Intl.DateTimeFormat('en-US', { timeZone: data.tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (e) { zone = null; }
    const wall = (ms) => {
      const p = {};
      zone.formatToParts(new Date(ms)).forEach((x) => { p[x.type] = x.value; });
      return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second) / 1000;
    };
    function addBar(time, price) {
      const c = { time, open: price, high: price, low: price, close: price };
      paint(c);
      candleData.push(c); lineData.push({ time, value: price });
      bars.t.push(time); bars.o.push(price); bars.h.push(price); bars.l.push(price); bars.c.push(price);
      if (bars.v && bars.v.length) bars.v.push(null);
      n = bars.t.length;
      candleIdx.push(n - 1);
      idxByTime.set(time, n - 1);
      return c;
    }
    // kind: 'regular' | 'ext' (pre-market / after hours) | 'overnight'. ms: trade time (epoch ms).
    function tick(price, ms, kind, quiet) {
      if (!fmt.ok(price) || !candleData.length || kind === 'overnight') return; // overnight prints are not on Yahoo's charts
      let last = candleData[candleData.length - 1];
      if (ms && zone) {
        const w = wall(ms);
        if (data.intraday) {
          if (kind === 'ext' && !prepost) return;
          const bt = Math.floor(w / IV) * IV;
          if (bt < last.time) return; // already inside an earlier bar
          if (bt > last.time) {
            if (bt - last.time > 4 * 86400) return; // the chart is days old: wait for its reload
            last = addBar(bt, price);
          }
        } else {
          if (kind === 'ext') return; // daily bars hold the regular session only
          const day = new Date(w * 1000).toISOString().slice(0, 10);
          if (typeof last.time !== 'string' || day < last.time) return;
          if (day > last.time) {
            if (Date.parse(day) - Date.parse(last.time) >= 7 * 864e5) return; // old chart or a new week: wait for its reload
            if (data.interval !== '1wk') last = addBar(day, price); // a new trading day
          }
        }
      }
      last.close = price;
      if (price > last.high) last.high = price;
      if (price < last.low) last.low = price;
      paint(last);
      const i = candleIdx[candleIdx.length - 1];
      bars.c[i] = price; bars.h[i] = last.high; bars.l[i] = last.low;
      lineData[lineData.length - 1].value = price;
      // A copy: series.update() rewrites the object it gets (its time becomes {year, month, day}).
      if (style === 'candles') series.update({ ...last }); else series.update({ time: last.time, value: price });
      if (!hover && !quiet) showLegend();
    }
    main.timeScale().fitContent();
    const inst = {
      root, charts,
      destroy() { charts.forEach((c) => { try { c.remove(); } catch (e) { /* ignore */ } }); lwcs.delete(inst); },
      retheme() {
        const t = theme();
        charts.forEach((c, i) => {
          if (i === 0) { c.applyOptions(lwcOptions(t, data.intraday)); return; }
          const o2 = lwcOptions(t, data.intraday);
          o2.layout.attributionLogo = false;
          o2.localization = { priceFormatter: (p) => (Math.abs(p) >= 1e6 ? fmt.big(p) : p.toFixed(2)) };
          c.applyOptions({ ...o2, timeScale: { visible: false } });
        });
        if (style === 'candles') series.applyOptions({ upColor: t.up, downColor: t.down, borderUpColor: t.up, borderDownColor: t.down, wickUpColor: t.up, wickDownColor: t.down });
      },
      png(name) {
        const cv = main.takeScreenshot();
        cv.toBlob((b) => SQ.ui.saveBlob(b, (name || 'chart') + '.png'));
      },
      // Live update from a quote or a streamed trade: extends the chart, no refetch.
      tickLast(price, ms, kind) { tick(price, ms, kind || 'regular'); },
      // Replay streamed 1-minute bars [minute, open, high, low, close, kind 0/1/2] newer than the data.
      replay(tape) {
        if (!tape || !tape.length) return;
        for (const [m, o, hi, lo, c, k] of tape) {
          const ms = m * 60000, kind = k === 0 ? 'regular' : k === 2 ? 'overnight' : 'ext';
          tick(o, ms, kind, true); tick(hi, ms, kind, true); tick(lo, ms, kind, true); tick(c, ms + 59000, kind, true);
        }
        if (!hover) showLegend();
      },
    };
    lwcs.add(inst);
    return inst;
  }

  SQ.charts = { theme, plot, lines, bars, heatmap, scatter, surface, treemap, priceChart, disposeAll, div, col };
})();
