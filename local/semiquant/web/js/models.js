/* Portfolio analytics computed in the browser (web edition and Android app, no server).
 * Never name this file quant.js: EasyPrivacy (uBlock Origin, AdGuard, Brave) blocks any "/quant.js"
 * script (Quantcast's tag), which left SQ.quant undefined for those users.
 * A port of semiquant.analytics.portfolio / risk.stress_test / montecarlo.simulate that returns the
 * same JSON as the local edition's /api/portfolio/analyze, so one renderer serves both:
 *   risk        ex-post risk of the current weights (2 years daily): vol, Sharpe, Sortino, beta,
 *               tracking error, historical VaR / ES, Euler risk contributions, diversification
 *   optimizers  equal, inverse vol, min variance, max Sharpe, risk parity (ERC), HRP, max
 *               diversification; long-only, capped; Ledoit-Wolf covariance, Bayes-Stein means
 *   frontier    long-only efficient frontier under the cap
 *   backtest    today's weights, monthly rebalancing, 10 bp costs, vs the benchmark
 *   stress      crisis replays on the published daily history
 *   montecarlo  12 months, 5-day block bootstrap of the portfolio's own returns, 10,000 paths
 * Input prices: the published 10-year daily bars of each holding. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const TD = 252, Z95 = 1.6448536269514722;
  const enc = encodeURIComponent;

  // ─── small linear algebra ────────────────────────────────────────────
  const dot = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; };
  const mv = (C, w) => C.map((row) => dot(row, w));
  const quad = (C, w) => dot(w, mv(C, w));
  const sum = (a) => a.reduce((s, v) => s + v, 0);
  const mean = (a) => sum(a) / a.length;
  const sd = (a) => { const m = mean(a); return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1)); };
  function solve(A, b) { // Gaussian elimination with partial pivoting
    const n = b.length, M = A.map((r, i) => r.concat([b[i]]));
    for (let c = 0; c < n; c++) {
      let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      if (Math.abs(M[p][c]) < 1e-18) throw new Error('singular');
      [M[c], M[p]] = [M[p], M[c]];
      for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c] / M[c][c]; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k]; }
    }
    return M.map((r, i) => r[n] / r[i]);
  }
  function quantile(sorted, q) { // numpy "linear"
    const h = (sorted.length - 1) * q, lo = Math.floor(h), hi = Math.ceil(h);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (h - lo);
  }
  function sampleCov(X) { // rows = observations
    const T = X.length, p = X[0].length, m = Array(p).fill(0);
    X.forEach((r) => r.forEach((v, j) => { m[j] += v / T; }));
    const C = Array.from({ length: p }, () => Array(p).fill(0));
    X.forEach((r) => { for (let i = 0; i < p; i++) { const di = r[i] - m[i]; for (let j = i; j < p; j++) C[i][j] += di * (r[j] - m[j]); } });
    for (let i = 0; i < p; i++) for (let j = i; j < p; j++) { C[i][j] /= (T - 1); C[j][i] = C[i][j]; }
    return C;
  }
  // Ledoit & Wolf (2004) towards mu*I, as portfolio._ledoit_wolf (biased 1/n sample covariance).
  function ledoitWolf(X) {
    const n = X.length, p = X[0].length, m = Array(p).fill(0);
    X.forEach((r) => r.forEach((v, j) => { m[j] += v / n; }));
    const Xc = X.map((r) => r.map((v, j) => v - m[j]));
    const S = Array.from({ length: p }, () => Array(p).fill(0));
    Xc.forEach((r) => { for (let i = 0; i < p; i++) for (let j = 0; j < p; j++) S[i][j] += r[i] * r[j] / n; });
    let tr = 0; for (let i = 0; i < p; i++) tr += S[i][i];
    const mu = tr / p;
    let d2 = 0, s2 = 0;
    for (let i = 0; i < p; i++) for (let j = 0; j < p; j++) { d2 += (S[i][j] - (i === j ? mu : 0)) ** 2; s2 += S[i][j] ** 2; }
    d2 /= p;
    let r4 = 0; Xc.forEach((r) => { const q = dot(r, r); r4 += q * q; });
    const bbar2 = (r4 / (n * n) - s2 / n) / p;
    const delta = d2 > 0 ? Math.min(bbar2, d2) / d2 : 1;
    return S.map((row, i) => row.map((v, j) => delta * (i === j ? mu : 0) + (1 - delta) * v));
  }
  // Bayes-Stein means (Jorion 1986), as expected_returns(..., "bayes_stein"); annualised.
  function bayesStein(X) {
    const T = X.length, p = X[0].length;
    const mu = Array(p).fill(0); X.forEach((r) => r.forEach((v, j) => { mu[j] += v / T; }));
    try {
      const S = ledoitWolf(X), one = Array(p).fill(1);
      const si1 = solve(S, one), mu0 = dot(si1, mu) / sum(si1);
      const d = mu.map((v) => v - mu0), q = T * dot(d, solve(S, d));
      const w = isFinite(q) && q >= 0 ? (p + 2) / ((p + 2) + q) : 1;
      return mu.map((v) => ((1 - w) * v + w * mu0) * TD);
    } catch (e) { return mu.map((v) => v * TD); }
  }

  // ─── long-only optimisation: projected gradient on {sum w = 1, lo <= w <= hi} ─
  function project(v, lo, hi) {
    let a = Math.min(...v) - hi - 1, b = Math.max(...v) - lo + 1;
    const at = (tau) => v.map((x) => Math.min(hi, Math.max(lo, x - tau)));
    for (let k = 0; k < 100; k++) { const tau = (a + b) / 2; if (sum(at(tau)) > 1) a = tau; else b = tau; }
    return at((a + b) / 2);
  }
  function pgd(f, grad, x0, lo, hi, iters = 4000) {
    let w = project(x0, lo, hi), fw = f(w), step = 1;
    for (let k = 0; k < iters; k++) {
      const g = grad(w);
      let moved = false;
      for (let t = 0; t < 40; t++) {
        const cand = project(w.map((x, i) => x - step * g[i]), lo, hi);
        const fc = f(cand);
        if (fc <= fw - 1e-4 * dot(g, w.map((x, i) => x - cand[i]))) {
          const change = Math.max(...cand.map((x, i) => Math.abs(x - w[i])));
          w = cand; fw = fc; step *= 1.6; moved = change > 1e-10; break;
        }
        step /= 2;
      }
      if (!moved) break;
    }
    return w;
  }
  function cap(w0, lo, hi) { // proportional capping (portfolio._cap)
    let w = w0.map((x) => Math.max(0, x)); const s = sum(w); w = s > 0 ? w.map((x) => x / s) : w.map(() => 1 / w.length);
    for (let it = 0; it < 200; it++) {
      const over = w.map((x) => x > hi + 1e-12), under = w.map((x) => x < lo - 1e-12);
      if (!over.some(Boolean) && !under.some(Boolean)) break;
      w = w.map((x, i) => (over[i] ? hi : under[i] ? lo : x));
      const free = w.map((x, i) => !over[i] && !under[i] && x > lo && x < hi);
      const fixedSum = sum(w.filter((_, i) => !free[i])), freeSum = sum(w.filter((_, i) => free[i]));
      if (!free.some(Boolean) || freeSum <= 0) break;
      w = w.map((x, i) => (free[i] ? x / freeSum * (1 - fixedSum) : x));
    }
    return w;
  }
  const ratio = (v, C) => ({ // -(w'v)/sqrt(w'Cw) and its gradient
    f: (w) => -dot(w, v) / Math.sqrt(Math.max(quad(C, w), 1e-300)),
    g: (w) => { const Cw = mv(C, w), s = Math.sqrt(Math.max(dot(w, Cw), 1e-300)), wv = dot(w, v); return v.map((x, i) => -(x / s - wv * Cw[i] / s ** 3)); },
  });
  const minVar = (C, lo, hi, x0) => pgd((w) => quad(C, w), (w) => mv(C, w).map((x) => 2 * x), x0 || C.map(() => 1 / C.length), lo, hi);
  function erc(C) {
    const n = C.length, b = 1 / n, d = C.map((r, i) => r[i]);
    let y = d.map((x) => 1 / Math.sqrt(x)); const s0 = sum(y); y = y.map((x) => x / s0);
    for (let it = 0; it < 5000; it++) {
      const prev = y.slice();
      for (let i = 0; i < n; i++) { const c = dot(C[i], y) - d[i] * y[i]; y[i] = (-c + Math.sqrt(c * c + 4 * d[i] * b)) / (2 * d[i]); }
      if (Math.max(...y.map((x, i) => Math.abs(x - prev[i]))) <= 1e-12 * Math.max(...y)) break;
    }
    const s = sum(y); return y.map((x) => x / s);
  }
  function linkageOrder(C) { // single-linkage on the Euclidean distance between correlation-distance columns
    const n = C.length, s = C.map((r, i) => Math.sqrt(r[i]));
    const D = C.map((r, i) => r.map((v, j) => Math.sqrt(Math.max(0, 0.5 * (1 - Math.max(-1, Math.min(1, v / (s[i] * s[j]))))))));
    const E = D.map((a) => D.map((b) => Math.sqrt(a.reduce((acc, v, k) => acc + (v - b[k]) ** 2, 0))));
    let clusters = D.map((_, i) => ({ leaves: [i] }));
    while (clusters.length > 1) {
      let best = [0, 1, Infinity];
      for (let a = 0; a < clusters.length; a++) for (let b = a + 1; b < clusters.length; b++) {
        let m = Infinity; for (const i of clusters[a].leaves) for (const j of clusters[b].leaves) m = Math.min(m, E[i][j]);
        if (m < best[2]) best = [a, b, m];
      }
      const [a, b] = best, merged = { leaves: clusters[a].leaves.concat(clusters[b].leaves) };
      clusters = clusters.filter((_, k) => k !== a && k !== b).concat([merged]);
    }
    return clusters[0].leaves;
  }
  function hrp(C) {
    const n = C.length; if (n === 1) return [1];
    const order = linkageOrder(C), w = Array(n).fill(1);
    const cvar = (idx) => { const iv = idx.map((i) => 1 / C[i][i]), s = sum(iv), u = iv.map((x) => x / s); let v = 0; idx.forEach((i, a) => idx.forEach((j, b) => { v += u[a] * C[i][j] * u[b]; })); return v; };
    let clusters = [order];
    while (clusters.length) {
      const next = [];
      for (const c of clusters) {
        if (c.length < 2) continue;
        const h = Math.floor(c.length / 2), c1 = c.slice(0, h), c2 = c.slice(h), v1 = cvar(c1), v2 = cvar(c2), a = 1 - v1 / (v1 + v2);
        c1.forEach((i) => { w[i] *= a; }); c2.forEach((i) => { w[i] *= 1 - a; });
        next.push(c1, c2);
      }
      clusters = next;
    }
    const s = sum(w); return w.map((x) => x / s);
  }
  function stats(w, mu, C, rf) {
    const Cw = mv(C, w), v = dot(w, Cw), vol = Math.sqrt(Math.max(v, 0)), ret = dot(w, mu), sdv = C.map((r, i) => Math.sqrt(r[i]));
    return { exp_return: ret, vol, sharpe: vol > 0 ? (ret - rf) / vol : null, rc: w.map((x, i) => (v > 0 ? x * Cw[i] / v : null)),
      diversification_ratio: vol > 0 ? dot(w, sdv) / vol : null, effective_n: 1 / dot(w, w) };
  }
  function solveMethod(m, mu, C, lo, hi, rf) {
    const n = C.length, eq = Array(n).fill(1 / n);
    if (m === 'equal') return eq;
    if (m === 'inverse_vol') return cap(C.map((r, i) => 1 / Math.sqrt(r[i])), lo, hi);
    if (m === 'min_var') return minVar(C, lo, hi);
    if (m === 'max_sharpe') {
      const ex = mu.map((x) => x - rf);
      if (!ex.some((x) => x > 0)) return minVar(C, lo, hi);
      const { f, g } = ratio(ex, C);
      let best = null;
      for (const x0 of [eq, minVar(C, lo, hi), cap(ex.map((x) => Math.max(x, 1e-9)), lo, hi)]) {
        const c = pgd(f, g, x0, lo, hi); if (!best || f(c) < f(best) - 1e-12) best = c;
      }
      return best;
    }
    if (m === 'max_div') { const { f, g } = ratio(C.map((r, i) => Math.sqrt(r[i])), C); return pgd(f, g, eq, lo, hi); }
    if (m === 'erc') {
      let w = erc(C);
      if (Math.max(...w) > hi + 1e-9 || Math.min(...w) < lo - 1e-9) { // least-squares risk parity under the bounds
        const f = (x) => { const Cx = mv(C, x), v = dot(x, Cx); return sum(x.map((xi, i) => (xi * Cx[i] / v - 1 / n) ** 2)) * 1e4; };
        const g = (x) => x.map((_, i) => { const e = 1e-7, xp = x.slice(); xp[i] += e; return (f(xp) - f(x)) / e; });
        w = pgd(f, g, cap(w, lo, hi), lo, hi, 1500);
      }
      return w;
    }
    if (m === 'hrp') { const w = hrp(C); return Math.max(...w) > hi + 1e-9 ? cap(w, lo, hi) : w; }
    return eq;
  }
  function bounds(n, maxW) { let hi = Math.min(Math.max(maxW || 0.35, 0), 1); if (hi * n < 1 - 1e-12) hi = 1 / n; return [0, hi]; }

  // ─── data ───────────────────────────────────────────────────────────
  async function closesOf(sym) {
    const ch = await SQ.api(`/api/ticker/${enc(sym)}/chart?range=10Y`);
    const m = new Map(); ch.bars.t.forEach((t, i) => { const c = ch.bars.c[i]; if (SQ.fmt.ok(c) && c > 0) m.set(t, c); });
    return m;
  }
  // Aligned closes on the dates where every series trades (short gaps forward-filled up to 5 days).
  function align(maps, calendar) {
    const dates = [], rows = [], last = maps.map(() => null), age = maps.map(() => 99);
    for (const d of calendar) {
      maps.forEach((m, k) => { if (m.has(d)) { last[k] = m.get(d); age[k] = 0; } else age[k]++; });
      if (last.every((v, k) => v != null && age[k] <= 5)) { dates.push(d); rows.push(last.slice()); }
    }
    return { dates, rows };
  }
  const toRets = (rows) => rows.slice(1).map((r, i) => r.map((v, j) => v / rows[i][j] - 1));

  // ─── the analysis ───────────────────────────────────────────────────
  function portfolioRisk(w, R, bench, rf, value) {
    const rp = R.map((r) => dot(r, w)), x = rp.slice().sort((a, b) => a - b);
    const mu_d = mean(rp), sd_d = sd(rp), expRet = mu_d * TD, vol = sd_d * Math.sqrt(TD);
    const down = Math.sqrt(mean(rp.map((v) => Math.min(v - rf / TD, 0) ** 2))) * Math.sqrt(TD);
    let wealth = 1, peak = 1, mdd = 0; rp.forEach((v) => { wealth *= 1 + v; peak = Math.max(peak, wealth); mdd = Math.min(mdd, wealth / peak - 1); });
    const q05 = quantile(x, 0.05), q01 = quantile(x, 0.01);
    const tail = (q) => { const t = x.filter((v) => v <= q); return -mean(t); };
    const out = { exp_return: expRet, vol, sharpe: vol > 0 ? (expRet - rf) / vol : null, sortino: down > 0 ? (expRet - rf) / down : null,
      max_drawdown: mdd, var95: -q05, var99: -q01, es95: tail(q05), es99: tail(q01), var95_param: Z95 * sd_d, n_obs: rp.length };
    for (const k of ['var95', 'var99', 'es95', 'es99']) out[k + '_value'] = out[k] * value;
    const Cd = sampleCov(R), Cw = mv(Cd, w), varP = dot(w, Cw), sda = Cd.map((r, i) => Math.sqrt(r[i] * TD));
    out.diversification_ratio = vol > 0 ? dot(w, sda) / vol : null;
    out.effective_n = 1 / dot(w, w);
    let assetBeta = Cw.map((c) => c / varP);
    if (bench) {
      const vb = sd(bench) ** 2, mb = mean(bench), mp = mean(rp);
      const cov = (a, ma) => a.reduce((s, v, i) => s + (v - ma) * (bench[i] - mb), 0) / (a.length - 1);
      out.beta = cov(rp, mp) / vb;
      const act = rp.map((v, i) => v - bench[i]), te = sd(act) * Math.sqrt(TD);
      out.tracking_error = te; out.information_ratio = te > 0 ? mean(act) * TD / te : null;
      assetBeta = w.map((_, j) => { const col = R.map((r) => r[j]); return cov(col, mean(col)) / vb; });
    }
    out.holdings = w.map((wi, i) => ({ weight: wi, vol: sda[i], beta: assetBeta[i], risk_contrib: varP > 0 ? wi * Cw[i] / varP : null,
      marginal_var: Z95 * Cw[i] / Math.sqrt(varP), component_var: wi * Z95 * Cw[i] / Math.sqrt(varP) }));
    return out;
  }

  function backtest(dates, P, w, benchMap, rf) {
    const cost = 10 / 1e4, n = P.length;
    const key = dates.map((d) => d.slice(0, 7));
    const reb = []; for (let i = 0; i < n - 1; i++) if (key[i] !== key[i + 1]) reb.push(i);
    const bnds = [0, ...reb, n - 1], eq = Array(n);
    let V = 1 - cost * sum(w.map(Math.abs)), h = w.slice(), turnover = 0; eq[0] = V;
    for (let k = 0; k < bnds.length - 1; k++) {
      const s = bnds[k], e = bnds[k + 1]; if (e <= s) continue;
      let lastRel = null;
      for (let i = s; i <= e; i++) { const rel = P[i].map((v, j) => v / P[s][j]); eq[i] = V * dot(rel, h); lastRel = rel; }
      V = eq[e];
      const g = dot(lastRel, h), drift = h.map((x, j) => x * lastRel[j] / g);
      if (reb.includes(e)) { const trade = sum(w.map((x, j) => Math.abs(x - drift[j]))); turnover += trade; V *= 1 - cost * trade; eq[e] = V; h = w.slice(); }
      else h = drift;
    }
    const perf = (vals) => {
      const r = vals.slice(1).map((v, i) => v / vals[i] - 1), yrs = (new Date(dates[dates.length - 1]) - new Date(dates[0])) / 864e5 / 365.25;
      let pk = -Infinity, dd = 0; vals.forEach((v) => { pk = Math.max(pk, v); dd = Math.min(dd, v / pk - 1); });
      const vol = sd(r) * Math.sqrt(TD);
      return { cagr: yrs > 0 ? (vals[vals.length - 1] / vals[0]) ** (1 / yrs) - 1 : null, vol, sharpe: vol ? (mean(r) * TD - rf) / vol : null, max_drawdown: dd, yrs };
    };
    const st = perf(eq);
    const out = { equity: { t: dates, v: eq }, stats: { cagr: st.cagr, vol: st.vol, sharpe: st.sharpe, max_drawdown: st.max_drawdown,
      turnover_ann: st.yrs > 0 ? 0.5 * turnover / st.yrs : null, n_rebalances: reb.length } };
    if (benchMap) {
      let last = null; const bv = dates.map((d) => { if (benchMap.has(d)) last = benchMap.get(d); return last; });
      const i0 = bv.findIndex((v) => v != null);
      if (i0 >= 0) {
        const b = bv.map((v) => (v == null ? null : v / bv[i0]));
        out.benchmark = { t: dates.slice(i0), v: b.slice(i0) };
        const bs = perf(b.slice(i0));
        Object.assign(out.stats, { bench_cagr: bs.cagr, bench_vol: bs.vol, bench_sharpe: bs.sharpe, bench_max_drawdown: bs.max_drawdown });
      }
    }
    return out;
  }

  const WINDOWS = [
    ['Global financial crisis', '2008-09-01', '2009-03-09'], ['Flash crash / euro crisis', '2010-04-23', '2010-07-02'],
    ['US downgrade', '2011-07-22', '2011-10-03'], ['China devaluation', '2015-08-10', '2015-08-25'],
    ['Volmageddon', '2018-01-26', '2018-02-08'], ['Q4 2018 selloff', '2018-10-03', '2018-12-24'],
    ['COVID crash', '2020-02-19', '2020-03-23'], ['2022 bear market', '2022-01-03', '2022-10-12'],
    ['SVB banking stress', '2023-03-08', '2023-03-13'], ['Yen carry unwind', '2024-07-10', '2024-08-07'],
    ['DeepSeek shock', '2025-01-24', '2025-01-27'], ['2025 tariff shock', '2025-04-02', '2025-04-08'],
  ];
  function windowStats(t, v, start, end) { // risk._window_stats on parallel date / value arrays
    if (t.length < 2 || t[0] >= start || t[t.length - 1] < end) return [false, null, null];
    const i0 = t.findIndex((d) => d >= start) - 1; let i1 = -1; for (let i = 0; i < t.length && t[i] <= end; i++) i1 = i;
    if (i0 < 0 || i1 < 0) return [false, null, null];
    const path = v.slice(i0, i1 + 1); let pk = -Infinity, dd = 0; path.forEach((x) => { pk = Math.max(pk, x); dd = Math.min(dd, x / pk - 1); });
    return [true, path[path.length - 1] / path[0] - 1, dd];
  }
  function stress(navT, navV, benches) {
    return { rows: WINDOWS.map(([name, s, e]) => {
      const [cov, ret, mdd] = windowStats(navT, navV, s, e), bench = {};
      for (const [bn, b] of Object.entries(benches)) { const r = windowStats(b.t, b.v, s, e); bench[bn] = r[0] && cov ? r[1] : null; }
      return { name, start: s, end: e, covered: cov, return: ret, max_drawdown: mdd, bench };
    }) };
  }

  function monteCarlo(navV, value, horizon = 252, paths = 10000, block = 5) {
    const r = []; const tail = navV.slice(-1261); for (let i = 1; i < tail.length; i++) r.push(Math.log(tail[i] / tail[i - 1]));
    const every = 5, rec = []; for (let d = 0; d <= horizon; d += every) rec.push(d); if (rec[rec.length - 1] !== horizon) rec.push(horizon);
    const grid = rec.map(() => new Float32Array(paths));
    for (let p = 0; p < paths; p++) {
      let x = 0, pos = 0, left = 0, k = 0;
      grid[0][p] = value; k = 1;
      for (let d = 1; d <= horizon; d++) {
        if (left === 0) { pos = Math.floor(Math.random() * (r.length - block)); left = block; }
        x += r[pos++]; left--;
        if (k < rec.length && rec[k] === d) { grid[k][p] = value * Math.exp(x); k++; }
      }
    }
    const pc = { days: rec, p5: [], p25: [], p50: [], p75: [], p95: [] };
    grid.forEach((col) => { const s = Array.from(col).sort((a, b) => a - b); pc.p5.push(quantile(s, 0.05)); pc.p25.push(quantile(s, 0.25)); pc.p50.push(quantile(s, 0.5)); pc.p75.push(quantile(s, 0.75)); pc.p95.push(quantile(s, 0.95)); });
    const end = Array.from(grid[grid.length - 1]).sort((a, b) => a - b), frac = (f) => end.filter(f).length / paths;
    return { percentiles: pc, terminal: { median: quantile(end, 0.5), p5: quantile(end, 0.05), p95: quantile(end, 0.95), mean: mean(end),
      prob_loss: frac((v) => v < value), prob_loss_20: frac((v) => v <= value * 0.8), prob_gain_20: frac((v) => v >= value * 1.2) }, method: 'bootstrap', paths };
  }

  /** base: the live valuation from the browser (rows, total, day); p: the saved portfolio input. */
  async function portfolio(base, p) {
    const bench = (p.benchmark || 'SPY').toUpperCase(), maxW = p.max_weight || 0.35;
    const warnings = [];
    const weights0 = {}; base.rows.forEach((r) => { if (r.weight > 0) weights0[r.ticker] = r.weight; });
    const tick = Object.keys(weights0);
    if (!tick.length) throw new Error('None of the holdings has a live price.');
    let rf = 0.04;
    try { const q = await SQ.api('/api/quotes?symbols=' + enc('^IRX')); const v = (q['^IRX'] || {}).price; if (v > 0 && v < 20) rf = v / 100; } catch (e) { /* default */ }
    const loaded = await Promise.all(tick.concat([bench, 'SPY', 'SOXX']).map((s) => closesOf(s).then((m) => [s, m]).catch(() => [s, null])));
    const M = Object.fromEntries(loaded);
    const have = tick.filter((t) => M[t]);
    const miss = tick.filter((t) => !M[t]);
    if (miss.length) warnings.push(`No published price history for ${miss.join(', ')} (full analysis covers semiconductors and US large caps): left out of the risk analysis.`);
    const out = { name: p.name || 'Portfolio', benchmark: bench, rows: base.rows, total: base.total, cash: 0, nav: base.total, day_change: base.day,
      day_change_pct: base.day_pct, weights: weights0, rf, warnings, asof: new Date().toISOString(), engine: 'browser' };
    if (!have.length) return out;
    const wsum = sum(have.map((t) => weights0[t])), w = have.map((t) => weights0[t] / wsum);
    const calMap = M[bench] || M.SPY || M[have[0]];
    const cal = Array.from(calMap.keys()).sort();
    const { dates, rows } = align(have.map((t) => M[t]), cal);
    if (rows.length < 30) { warnings.push('Too little overlapping history for risk statistics.'); return out; }
    const R = toRets(rows), rDates = dates.slice(1);
    const benchMap = M[bench] || M.SPY;
    const bRet = benchMap ? rDates.map((d, i) => { const a = benchMap.get(dates[i]), b = benchMap.get(d); return a && b ? b / a - 1 : null; }) : null;
    // risk over the last 2 years (rows where the benchmark traded too)
    const idx = []; for (let i = Math.max(0, R.length - 504); i < R.length; i++) if (!bRet || bRet[i] != null) idx.push(i);
    out.risk = portfolioRisk(w, idx.map((i) => R[i]), bRet ? idx.map((i) => bRet[i]) : null, rf, out.nav);
    out.risk.holdings.forEach((x, i) => { x.ticker = have[i]; });
    // optimizers and frontier on the last 3 years
    const R3 = R.slice(-756);
    if (have.length > 1) {
      const C = ledoitWolf(R3).map((r) => r.map((v) => v * TD)), mu = bayesStein(R3), [lo, hi] = bounds(have.length, maxW);
      out.optimizers = {};
      for (const m of ['equal', 'inverse_vol', 'min_var', 'max_sharpe', 'erc', 'hrp', 'max_div']) {
        const wm = solveMethod(m, mu, C, lo, hi, rf), st = stats(wm, mu, C, rf);
        out.optimizers[m] = { method: m, weights: Object.fromEntries(have.map((t, i) => [t, wm[i]])), exp_return: st.exp_return, vol: st.vol, sharpe: st.sharpe,
          risk_contrib: Object.fromEntries(have.map((t, i) => [t, st.rc[i]])), diversification_ratio: st.diversification_ratio, effective_n: st.effective_n, max_weight: hi };
      }
      // frontier: min variance subject to a target return, targets from the min-var return to the best attainable
      const wmv = minVar(C, lo, hi), rLo = dot(wmv, mu);
      const top = Array(have.length).fill(lo); let room = 1 - sum(top);
      mu.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).forEach(([, i]) => { const add = Math.min(hi - lo, room); top[i] += add; room -= add; });
      const rHi = dot(top, mu), K = rHi > rLo + 1e-9 ? 24 : 1, pts = [];
      let x0 = wmv;
      for (let k = 0; k < K; k++) {
        const tgt = K === 1 ? rLo : rLo + (rHi - rLo) * k / (K - 1);
        let wk = x0;
        for (const rho of [1e2, 1e4, 1e6]) {
          const f = (x) => quad(C, x) + rho * Math.max(0, tgt - dot(x, mu)) ** 2;
          const g = (x) => { const s = Math.max(0, tgt - dot(x, mu)); return mv(C, x).map((c, i) => 2 * c - 2 * rho * s * mu[i]); };
          wk = pgd(f, g, wk, lo, hi, 1500);
        }
        const st = stats(wk, mu, C, rf); pts.push({ vol: st.vol, ret: st.exp_return, sharpe: st.sharpe }); x0 = wk;
      }
      out.frontier = { points: pts, assets: have.map((t, i) => ({ ticker: t, vol: Math.sqrt(C[i][i]), ret: mu[i] })) };
      // correlation, 1 year, clustered order
      const R1 = R.slice(-252), Cc = sampleCov(R1), order = linkageOrder(Cc), s1 = Cc.map((r, i) => Math.sqrt(r[i]));
      out.correlation = { tickers: order.map((i) => have[i]), matrix: order.map((i) => order.map((j) => Cc[i][j] / (s1[i] * s1[j]))) };
    }
    out.backtest = backtest(dates, rows, w, benchMap, rf);
    // constant-weight NAV for crisis replays and Monte Carlo
    const navV = [1]; R.forEach((r) => navV.push(navV[navV.length - 1] * (1 + dot(r, w))));
    const benches = {};
    for (const b of ['SPY', 'SOXX']) if (M[b]) { const t = Array.from(M[b].keys()).sort(); benches[b] = { t, v: t.map((d) => M[b].get(d)) }; }
    out.stress = stress(dates, navV, benches);
    out.montecarlo = monteCarlo(navV, out.nav);
    out.history_start = dates[0];
    return out;
  }

  // ─── offer models beyond the bootstrap: GBM and GARCH(1,1)-t, fitted here ─
  function garchFit(r) { // variance-targeted GARCH(1,1), Student-t (nu = 6) likelihood, grid search
    const v = sd(r) ** 2, nu = 6, c = (nu - 2);
    let best = null;
    for (let a = 0.02; a <= 0.2001; a += 0.01) for (let b = 0.70; b <= 0.985; b += 0.005) {
      if (a + b >= 0.995) continue;
      const om = v * (1 - a - b); let h = v, ll = 0;
      for (let i = 0; i < r.length; i++) { ll += -0.5 * Math.log(h) - (nu + 1) / 2 * Math.log(1 + r[i] * r[i] / (h * c)); h = om + a * r[i] * r[i] + b * h; }
      if (!best || ll > best.ll) best = { ll, omega: om, alpha: a, beta: b, h, nu };
    }
    return best;
  }
  function studentT(nu) { // standardised (variance 1) t draw
    const g = () => { let u = 0, w = 0; while (u === 0) u = Math.random(); while (w === 0) w = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * w); };
    let chi = 0; for (let i = 0; i < nu; i++) chi += g() ** 2;
    return g() / Math.sqrt(chi / nu) * Math.sqrt((nu - 2) / nu);
  }
  function gauss() { let u = 0, w = 0; while (u === 0) u = Math.random(); while (w === 0) w = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * w); }
  /** Returns a step function (state) -> next log return, for the offer simulator. */
  function offerModel(method, lr, drift) {
    if (method === 'gbm') { const s = sd(lr); return { label: 'lognormal (GBM)', vol: s * Math.sqrt(TD), start: () => ({}), step: () => drift + s * gauss() }; }
    if (method === 'garch') {
      const g = garchFit(lr.map((x) => x - mean(lr)));
      return { label: 'GARCH(1,1)-t (browser fit)', vol: Math.sqrt(g.omega / (1 - g.alpha - g.beta) * TD), garch: g,
        start: () => ({ h: g.h }),
        step: (st) => { const e = Math.sqrt(st.h) * studentT(g.nu); st.h = g.omega + g.alpha * e * e + g.beta * st.h; return drift + e; } };
    }
    return null;
  }

  SQ.quant = { portfolio, offerModel, ledoitWolf, bayesStein, hrp, erc, project, quantile, solveMethod, stats, bounds, portfolioRisk };
})();
