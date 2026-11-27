/* Technical indicators in the browser (same definitions as semiquant.analytics.technicals:
 * Wilder RSI/ATR/ADX, 12-26-9 MACD, 20-2 Bollinger, session VWAP intraday / 20-day VWAP daily).
 * Used when chart data arrives as raw bars (published website). Output shape matches the API:
 * {name: {v: [...]}} for one line, {name: {field: [...]}} for several. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const N = (n) => new Array(n).fill(null);

  function sma(x, n) {
    const out = N(x.length);
    let s = 0;
    for (let i = 0; i < x.length; i++) {
      s += x[i];
      if (i >= n) s -= x[i - n];
      if (i >= n - 1) out[i] = s / n;
    }
    return out;
  }
  function ema(x, n) {
    const out = N(x.length), a = 2 / (n + 1);
    if (x.length < n) return out;
    let e = x.slice(0, n).reduce((p, q) => p + q, 0) / n;
    out[n - 1] = e;
    for (let i = n; i < x.length; i++) { e = a * x[i] + (1 - a) * e; out[i] = e; }
    return out;
  }
  function emaNullable(x, n) { // EMA over a series with leading nulls (MACD signal)
    const i0 = x.findIndex((v) => v != null);
    if (i0 < 0) return N(x.length);
    return N(i0).concat(ema(x.slice(i0), n));
  }
  function wilder(x, n) {
    const out = N(x.length);
    if (x.length <= n) return out;
    let r = 0;
    for (let i = 1; i <= n; i++) r += x[i];
    r /= n;
    out[n] = r;
    for (let i = n + 1; i < x.length; i++) { r = (r * (n - 1) + x[i]) / n; out[i] = r; }
    return out;
  }
  function rollMax(x, n) { return x.map((_, i) => (i < n - 1 ? null : Math.max(...x.slice(i - n + 1, i + 1)))); }
  function rollMin(x, n) { return x.map((_, i) => (i < n - 1 ? null : Math.min(...x.slice(i - n + 1, i + 1)))); }
  function rollStd(x, n) {
    return x.map((_, i) => {
      if (i < n - 1) return null;
      const w = x.slice(i - n + 1, i + 1), m = w.reduce((a, b) => a + b, 0) / n;
      return Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / n);
    });
  }
  function trueRange(h, l, c) { return h.map((v, i) => (i === 0 ? v - l[i] : Math.max(v - l[i], Math.abs(v - c[i - 1]), Math.abs(l[i] - c[i - 1])))); }

  function rsi(c, n = 14) {
    const g = c.map((v, i) => (i ? Math.max(v - c[i - 1], 0) : 0)), d = c.map((v, i) => (i ? Math.max(c[i - 1] - v, 0) : 0));
    const ag = wilder(g, n), ad = wilder(d, n);
    return ag.map((v, i) => (v == null ? null : ad[i] === 0 ? 100 : 100 - 100 / (1 + v / ad[i])));
  }
  function macd(c) {
    const f = ema(c, 12), s = ema(c, 26);
    const m = f.map((v, i) => (v == null || s[i] == null ? null : v - s[i]));
    const sig = emaNullable(m, 9);
    return { macd: m, signal: sig, hist: m.map((v, i) => (v == null || sig[i] == null ? null : v - sig[i])) };
  }
  function bollinger(c, n = 20, k = 2) {
    const mid = sma(c, n), sd = rollStd(c, n);
    return { upper: mid.map((m, i) => (m == null ? null : m + k * sd[i])), mid, lower: mid.map((m, i) => (m == null ? null : m - k * sd[i])) };
  }
  function vwap(b, intraday) {
    const tp = b.c.map((c, i) => ((b.h[i] ?? c) + (b.l[i] ?? c) + c) / 3), v = b.v.map((x) => x || 0);
    if (!intraday) {
      const pv = tp.map((p, i) => p * v[i]), spv = sma(pv, 20), sv = sma(v, 20);
      return spv.map((x, i) => (x == null || !sv[i] ? null : x / sv[i]));
    }
    const out = N(tp.length);
    let day = null, cpv = 0, cv = 0;
    b.t.forEach((t, i) => {
      const d = Math.floor(t / 86400);
      if (d !== day) { day = d; cpv = 0; cv = 0; }
      cpv += tp[i] * v[i]; cv += v[i];
      out[i] = cv ? cpv / cv : tp[i];
    });
    return out;
  }
  function atr(b, n = 14) { return wilder(trueRange(b.h, b.l, b.c), n); }
  function stoch(b, n = 14, s = 3) {
    const hh = rollMax(b.h, n), ll = rollMin(b.l, n);
    const k = b.c.map((c, i) => (hh[i] == null || hh[i] === ll[i] ? null : 100 * (c - ll[i]) / (hh[i] - ll[i])));
    const i0 = k.findIndex((x) => x != null);
    const d = i0 < 0 ? N(k.length) : N(i0).concat(sma(k.slice(i0), s));
    return { k, d };
  }
  function adx(b, n = 14) {
    const up = b.h.map((h, i) => (i ? h - b.h[i - 1] : 0)), dn = b.l.map((l, i) => (i ? b.l[i - 1] - l : 0));
    const pdm = up.map((u, i) => (u > dn[i] && u > 0 ? u : 0)), mdm = dn.map((d, i) => (d > up[i] && d > 0 ? d : 0));
    const tr = wilder(trueRange(b.h, b.l, b.c), n), p = wilder(pdm, n), m = wilder(mdm, n);
    const pdi = p.map((x, i) => (x == null || !tr[i] ? null : 100 * x / tr[i])), mdi = m.map((x, i) => (x == null || !tr[i] ? null : 100 * x / tr[i]));
    const dx = pdi.map((x, i) => (x == null || mdi[i] == null || x + mdi[i] === 0 ? 0 : 100 * Math.abs(x - mdi[i]) / (x + mdi[i])));
    const i0 = pdi.findIndex((x) => x != null);
    const a = i0 < 0 ? N(dx.length) : N(i0).concat(wilder(dx.slice(i0), n));
    return { adx: a, plus_di: pdi, minus_di: mdi };
  }
  function obv(b) { let s = 0; return b.c.map((c, i) => { if (i) s += c > b.c[i - 1] ? b.v[i] || 0 : c < b.c[i - 1] ? -(b.v[i] || 0) : 0; return s; }); }
  function cci(b, n = 20) {
    const tp = b.c.map((c, i) => (b.h[i] + b.l[i] + c) / 3), m = sma(tp, n);
    return tp.map((x, i) => {
      if (m[i] == null) return null;
      const w = tp.slice(i - n + 1, i + 1), md = w.reduce((a, y) => a + Math.abs(y - m[i]), 0) / n;
      return md ? (x - m[i]) / (0.015 * md) : 0;
    });
  }
  function mfi(b, n = 14) {
    const tp = b.c.map((c, i) => (b.h[i] + b.l[i] + c) / 3), mf = tp.map((x, i) => x * (b.v[i] || 0));
    return tp.map((x, i) => {
      if (i < n) return null;
      let pos = 0, neg = 0;
      for (let j = i - n + 1; j <= i; j++) { if (tp[j] > tp[j - 1]) pos += mf[j]; else if (tp[j] < tp[j - 1]) neg += mf[j]; }
      return neg === 0 ? 100 : 100 - 100 / (1 + pos / neg);
    });
  }
  function donchian(b, n = 20) { const u = rollMax(b.h, n), l = rollMin(b.l, n); return { upper: u, mid: u.map((x, i) => (x == null ? null : (x + l[i]) / 2)), lower: l }; }
  function keltner(b, n = 20, k = 2) { const mid = ema(b.c, n), a = atr(b, n); return { upper: mid.map((m, i) => (m == null || a[i] == null ? null : m + k * a[i])), mid, lower: mid.map((m, i) => (m == null || a[i] == null ? null : m - k * a[i])) }; }
  function ichimoku(b) {
    const mid = (n) => { const hh = rollMax(b.h, n), ll = rollMin(b.l, n); return hh.map((x, i) => (x == null ? null : (x + ll[i]) / 2)); };
    const ten = mid(9), kij = mid(26), sb = mid(52), shift = (x, s) => N(s).concat(x.slice(0, x.length - s));
    const sa = ten.map((x, i) => (x == null || kij[i] == null ? null : (x + kij[i]) / 2));
    return { tenkan: ten, kijun: kij, senkou_a: shift(sa, 26), senkou_b: shift(sb, 26), chikou: b.c.slice(26).concat(N(26)) };
  }
  function supertrend(b, n = 10, k = 3) {
    const a = atr(b, n), len = b.c.length, line = N(len), dir = N(len);
    let fu = null, fl = null, d = 1;
    for (let i = 0; i < len; i++) {
      if (a[i] == null) continue;
      const m = (b.h[i] + b.l[i]) / 2, bu = m + k * a[i], bl = m - k * a[i];
      fu = fu == null || bu < fu || b.c[i - 1] > fu ? bu : fu;
      fl = fl == null || bl > fl || b.c[i - 1] < fl ? bl : fl;
      if (d === 1 && b.c[i] < fl) d = -1; else if (d === -1 && b.c[i] > fu) d = 1;
      line[i] = d === 1 ? fl : fu; dir[i] = d;
    }
    return { line, direction: dir };
  }

  // compute(chartPayload, names) -> indicators dict
  function compute(d, names) {
    const b = d.bars || {};
    if (!b.c || !b.c.length) return {};
    const fill = (arr) => { let p = null; return (arr || []).map((v, i) => (v == null ? (p ?? b.c[i]) : (p = v))); };
    const bars = { t: b.t, c: fill(b.c), o: fill(b.o), h: fill(b.h), l: fill(b.l), v: (b.v || []).map((x) => x || 0) };
    if (!bars.v.length) bars.v = N(bars.c.length).map(() => 0);
    const out = {};
    for (const raw of names || []) {
      const n = String(raw).toLowerCase();
      try {
        let m;
        if ((m = n.match(/^sma(\d+)$/))) out[n] = { v: sma(bars.c, +m[1]) };
        else if ((m = n.match(/^ema(\d+)$/))) out[n] = { v: ema(bars.c, +m[1]) };
        else if (n === 'bb') out[n] = bollinger(bars.c);
        else if (n === 'vwap') out[n] = { v: vwap(bars, d.intraday) };
        else if (n === 'rsi') out[n] = { v: rsi(bars.c) };
        else if (n === 'macd') out[n] = macd(bars.c);
        else if (n === 'atr') out[n] = { v: atr(bars) };
        else if (n === 'adx') out[n] = adx(bars);
        else if (n === 'stoch') out[n] = stoch(bars);
        else if (n === 'obv') out[n] = { v: obv(bars) };
        else if (n === 'cci') out[n] = { v: cci(bars) };
        else if (n === 'mfi') out[n] = { v: mfi(bars) };
        else if (n === 'donchian') out[n] = donchian(bars);
        else if (n === 'keltner') out[n] = keltner(bars);
        else if (n === 'ichimoku') out[n] = ichimoku(bars);
        else if (n === 'supertrend') out[n] = supertrend(bars);
      } catch (e) { /* one bad indicator never breaks the chart */ }
    }
    return out;
  }

  SQ.ta = { sma, ema, rsi, macd, bollinger, vwap, atr, adx, stoch, obv, cci, mfi, donchian, keltner, ichimoku, supertrend, compute };
})();
