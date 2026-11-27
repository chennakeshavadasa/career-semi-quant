"""The browser port (web/js/quant.js, used by the web edition and the Android app) must give the
same optimizer weights and portfolio risk as semiquant.analytics.portfolio. Needs Node; skipped
without it."""
import json
import os
import shutil
import subprocess

import pytest

from semiquant.analytics import portfolio as pf

QUANT_JS = os.path.join(os.path.dirname(__file__), "..", "semiquant", "web", "js", "quant.js")

RUNNER = r"""
global.window = { SQ: { fmt: { ok: (v) => v != null && isFinite(v) } } };
require(process.argv[2]);
const Q = window.SQ.quant, d = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const C = Q.ledoitWolf(d.R).map((r) => r.map((v) => v * 252)), mu = Q.bayesStein(d.R), [lo, hi] = Q.bounds(d.n, 0.35);
const out = { opt: {} };
for (const m of d.methods) out.opt[m] = Q.solveMethod(m, mu, C, lo, hi, 0.04);
const r = Q.portfolioRisk(d.w, d.R, null, 0.04, 1);
out.risk = [r.vol, r.var95, r.es95, r.max_drawdown, r.sharpe, r.diversification_ratio];
out.rc = r.holdings.map((h) => h.risk_contrib);
console.log(JSON.stringify(out));
"""

METHODS = ("equal", "inverse_vol", "min_var", "max_sharpe", "erc", "hrp", "max_div")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_port_matches_python(closes, tmp_path):
    cols = ["NVDA", "AMD", "TSM", "AVGO", "MU", "INTC"]
    R = closes[cols].pct_change().dropna().tail(756)
    w = [1 / len(cols)] * len(cols)
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER)
    payload = json.dumps({"R": R.values.tolist(), "n": len(cols), "w": w, "methods": METHODS})
    res = subprocess.run(["node", str(runner), os.path.abspath(QUANT_JS)], input=payload, capture_output=True,
                         text=True, timeout=120, check=True)
    js = json.loads(res.stdout)
    for m in METHODS:
        py = pf.optimize(R, m, 0.35, 0.0, 0.04)["weights"]
        assert js["opt"][m] == pytest.approx([py[c] for c in cols], abs=2e-3), m
    r = pf.portfolio_risk(dict(zip(cols, w)), R, None, 0.04, 1.0)
    assert js["risk"] == pytest.approx([r["vol"], r["var95"], r["es95"], r["max_drawdown"], r["sharpe"],
                                        r["diversification_ratio"]], rel=1e-6)
    assert js["rc"] == pytest.approx([h["risk_contrib"] for h in r["holdings"]], rel=1e-6)
