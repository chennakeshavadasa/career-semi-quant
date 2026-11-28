"""Who else is trading a stock: members of Congress, big funds and 5%+ holders, and the company's own insiders
with the people who matter flagged, plus the fastest public signals (planned sales, fresh Form 4s, stakes).

How fast each kind becomes public is set by law, not by this app: Form 144 on or before the sale, Form 4
within 2 business days, 13D within 5 business days, Congress within 45 days of the trade, fund holdings (13F)
quarterly with a 45-day delay. Each item carries both dates: when it happened and when it became public.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from ..analytics._util import clean, jsonable, safe
from ..data import congress, sec, yahoo
from ..universe import ALL_META
from . import ticker as tk
from .common import memo

# Committees with oversight of an industry (a heuristic). The industry decides when it matches one of these;
# otherwise the sector does.
INDUSTRY_OVERSIGHT = [
    (("semiconductor",), ["HSIF", "HSSY", "HSZS", "HSFA", "SSCM", "SSBK"]),  # chips: commerce, science, China, export controls
    (("aerospace", "defense"), ["HSAS", "SSAS", "HSAP", "SSAP"]),
    (("internet", "software", "interactive media", "entertainment", "social"), ["HSIF", "HSJU", "SSCM", "SSJU"]),  # incl. antitrust
    (("bank", "insurance", "capital market", "credit", "asset management", "reit", "real estate"), ["HSBA", "SSBK"]),
    (("pharma", "biotech", "drug", "medical", "health"), ["HSIF", "HSWM", "SSHR", "SSFI"]),
    (("oil", "gas", "coal", "solar", "uranium", "utilit"), ["HSIF", "HSII", "SSEG", "SSEV"]),
    (("airline", "railroad", "trucking", "logistics", "auto"), ["HSPW", "SSCM"]),
    (("agri", "farm", "food"), ["HSAG", "SSAF"]),
]
SECTOR_OVERSIGHT = [
    (("technology", "communication", "telecom", "media", "information"), ["HSIF", "HSSY", "SSCM"]),
    (("financ", "real estate"), ["HSBA", "SSBK"]),
    (("health",), ["HSIF", "HSWM", "SSHR", "SSFI"]),
    (("energy", "utilit"), ["HSIF", "HSII", "SSEG", "SSEV"]),
    (("consumer", "retail", "staples", "discretionary"), ["HSIF", "SSCM"]),
    (("industrial", "transport"), ["HSPW", "HSAS", "SSCM", "SSAS"]),
    (("material", "chemical", "mining", "metal"), ["HSII", "SSEG", "SSEV"]),
]
OVERSIGHT = INDUSTRY_OVERSIGHT + SECTOR_OVERSIGHT
TOP_ROLES = ("chief executive", "ceo", "chief financial", "cfo", "chief operating", "coo", "president", "chair", "founder")
MIN_STAKE = 0.005  # funds holding at least 0.5 % of the shares

__all__ = ["ticker", "congress_feed", "oversight_committees", "role_of", "OVERSIGHT"]


def oversight_committees(sector: str | None, industry: str | None) -> set[str]:
    ind, sec_ = (industry or "").lower(), (sector or "").lower()
    hit = {c for keys, codes in INDUSTRY_OVERSIGHT if any(k in ind for k in keys) for c in codes}
    return hit or {c for keys, codes in SECTOR_OVERSIGHT if any(k in sec_ for k in keys) for c in codes}


def _sector(sym: str) -> tuple[str | None, str | None]:
    m = ALL_META.get(sym) or {}
    if m.get("universe") == "semis":
        return "Technology", "Semiconductors"
    return m.get("sector"), None


def role_of(position: str | None) -> str:
    """'top' (CEO, CFO, COO, president, chair, founder), 'owner' (10%+ holder), 'director' or 'officer'."""
    p = (position or "").lower()
    if "beneficial owner" in p or "10%" in p:
        return "owner"
    if any(k in p for k in TOP_ROLES):
        return "top"
    if "director" in p:
        return "director"
    return "officer"


def _mid(r: dict) -> float:
    lo, hi = r.get("amount_lo") or 0, r.get("amount_hi")
    return (lo + hi) / 2 if hi else lo


def _side(kind: str | None) -> str | None:
    return "buy" if kind == "buy" else "sell" if kind in ("sell", "sell_partial") else None


def _money(v: float | None) -> str:
    if v is None:
        return "?"
    v = abs(v)
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}K" if v >= 1e3 else f"${v:.0f}"


def _issuer(asset: str | None) -> str | None:
    """'Snowflake Inc. - Class A Common Stock' -> 'Snowflake Inc.'"""
    if not asset:
        return None
    a = re.split(r"\s+-\s+|\s+(?:Class [A-C]\s+)?(?:Common|Ordinary|Capital) (?:Stock|Shares)|\s+ADR\b|\s+American Depositary", asset)[0]
    return a.strip(" ,-")[:40] or None


def _range(r: dict) -> str:
    lo, hi = r.get("amount_lo"), r.get("amount_hi")
    if lo is None:
        return "?"
    return f"{_money(lo)}-{_money(hi)}" if hi else f"over {_money(lo - 1)}"


def _congress_rows(rows: list[dict], committees: dict, oversight: set[str]) -> list[dict]:
    out = []
    for r in rows:
        seats = committees.get(r.get("bioguide") or "", [])
        rel = [c for c in seats if c["code"] in oversight]
        out.append({k: r.get(k) for k in ("chamber", "member", "party", "state", "asset", "asset_type", "type",
                                          "amount_lo", "amount_hi", "traded", "disclosed", "owner", "url", "ocr")}
                   | {"side": _side(r.get("type")),
                      "relevant": [{"name": c["name"], "title": c.get("title")} for c in rel],
                      "lag_days": (date.fromisoformat(r["disclosed"]) - date.fromisoformat(r["traded"])).days
                      if r.get("disclosed") and r.get("traded") else None})
    return out


def ticker(sym: str) -> dict:
    sym = yahoo.norm_symbol(sym)

    def build():
        today = date.today()
        info = safe(yahoo.info, sym, default={}) or {}
        sector, industry = info.get("sector") or _sector(sym)[0], info.get("industry") or _sector(sym)[1]
        oversight = oversight_committees(sector, industry)
        notes, highlights = [], []

        # Congress
        try:
            data = congress.trades(730)
            crows = _congress_rows([r for r in data["rows"] if r.get("ticker") == sym], data["committees"], oversight)
        except Exception as exc:  # noqa: BLE001 - the rest of the page still works
            crows = []
            notes.append(f"Congress filings could not be read just now ({type(exc).__name__}); retried on the next refresh.")
        # Company insiders (Form 4, via Yahoo) and fresh filings straight from the SEC
        own = safe(tk.ownership, sym, default={}) or {}
        insiders = []
        for t in own.get("insider_transactions") or []:
            insiders.append({**t, "role": role_of(t.get("position"))})
        fresh = safe(sec.recent, sym, default=None) or {"form4": [], "form144": [], "stakes": []}
        # Big funds (top institutional and mutual fund holders, quarterly 13F)
        funds = []
        for kind, rows in (("Institution", own.get("institutional") or []), ("Mutual fund", own.get("mutualfund") or [])):
            for r in rows:
                held = clean(r.get("pctHeld"))
                if held is None or held < MIN_STAKE:
                    continue
                funds.append({"holder": r.get("Holder"), "kind": kind, "pct_held": held, "shares": clean(r.get("Shares")),
                              "value": clean(r.get("Value")), "change": clean(r.get("pctChange")),
                              "reported": str(r.get("Date Reported") or "")[:10] or None})
        funds.sort(key=lambda f: f["pct_held"] or 0, reverse=True)

        # ── highlights, fastest signals first ──
        d30, d90, d180, d365 = (str(today - timedelta(days=n)) for n in (30, 90, 180, 365))
        planned = [f for f in fresh["form144"] if (f["filed"] or "") >= d30]
        if planned:
            who = sorted({f["party"] for f in planned if f["party"]})
            highlights.append({"level": "amber", "kind": "planned_sale", "public": planned[0]["filed"],
                               "title": f"Planned insider sale{'s' if len(planned) > 1 else ''} filed (Form 144)",
                               "detail": f"{', '.join(who[:4])}{' and others' if len(who) > 4 else ''} gave notice of a sale in the last 30 days "
                                         "(filed on or before the sale day: the earliest public warning).",
                               "url": planned[0]["url"]})
        buys = [t for t in insiders if t["kind"] == "buy" and (t["date"] or "") >= d90]
        if len({t["insider"] for t in buys}) >= 3:
            highlights.append({"level": "green", "kind": "cluster_buy", "public": max(t["date"] for t in buys),
                               "title": f"Cluster buying: {len({t['insider'] for t in buys})} insiders bought in 90 days",
                               "detail": f"Open-market purchases worth {_money(sum(t['value'] or 0 for t in buys))}: insiders buying with "
                                         "their own money is the stronger insider signal."})
        elif buys:
            b = max(buys, key=lambda t: t["value"] or 0)
            highlights.append({"level": "green", "kind": "insider_buy", "public": b["date"],
                               "title": f"Insider purchase: {str(b['insider']).title()} ({b['position']})",
                               "detail": f"Bought {_money(b['value'])} on {b['date']} (open market)."})
        top_sells = [t for t in insiders if t["kind"] == "sell" and t["role"] in ("top", "owner") and (t["date"] or "") >= d180]
        top_buys = [t for t in insiders if t["kind"] == "buy" and t["role"] in ("top", "owner") and (t["date"] or "") >= d180]
        if top_sells and not top_buys:
            by = defaultdict(float)
            for t in top_sells:
                by[(str(t["insider"]).title(), t["position"])] += t["value"] or 0
            lead = sorted(by.items(), key=lambda kv: -kv[1])[:3]
            highlights.append({"level": "red", "kind": "exec_selling", "public": max(t["date"] for t in top_sells),
                               "title": f"Top executives / 10% owners net sellers: {_money(sum(by.values()))} sold in 6 months, nothing bought",
                               "detail": "; ".join(f"{n} ({p}) {_money(v)}" for (n, p), v in lead) +
                                         ". Many executive sales are pre-scheduled (10b5-1 plans) or for taxes; read it as a lean, not a verdict."})
        activist = [f for f in fresh["stakes"] if "13D" in f["form"] and (f["filed"] or "") >= d365]
        if activist:
            highlights.append({"level": "amber", "kind": "activist", "public": activist[0]["filed"],
                               "title": f"Activist stake (13D): {activist[0]['party']}",
                               "detail": f"{activist[0]['form']} filed {activist[0]['filed']}: a 5%+ holder that intends to influence the company.",
                               "url": activist[0]["url"]})
        new_holders = [f for f in fresh["stakes"] if f["form"].endswith(("13G", "13D")) and (f["filed"] or "") >= d365]
        for f in new_holders[:2]:
            highlights.append({"level": "info", "kind": "new_5pct", "public": f["filed"], "url": f["url"],
                               "title": f"New 5%+ holder: {f['party']}", "detail": f"{f['form']} filed {f['filed']}."})
        recent_c = [r for r in crows if (r["disclosed"] or "") >= d365]
        flagged, seen = [], set()
        for r in sorted([r for r in recent_c if r["relevant"] and r["side"]], key=lambda r: -_mid(r)):
            if (r["member"], r["side"]) not in seen:  # one line per member and direction
                seen.add((r["member"], r["side"]))
                flagged.append(r)
        for r in flagged[:3]:
            c, big = r["relevant"][0], _mid(r) >= 50000
            late = f" Late: the law allows 45 days." if (r["lag_days"] or 0) > 45 else ""
            highlights.append({"level": ("red" if r["side"] == "sell" else "green") if big else "amber", "kind": "congress_committee",
                               "public": r["disclosed"], "url": r["url"],
                               "title": f"{r['member']} ({r['party'] or '?'}-{r['state'] or '?'}) "
                                        f"{'sold' if r['side'] == 'sell' else 'bought'} {_range(r)}: sits on {c['name']}"
                                        + (f" ({c['title']})" if c.get("title") else ""),
                               "detail": f"Traded {r['traded']}, disclosed {r['disclosed']} ({r['lag_days']} days later).{late} "
                                         "The committee oversees the company's industry."})
        if recent_c:
            b = sum(_mid(r) for r in recent_c if r["side"] == "buy")
            s = sum(_mid(r) for r in recent_c if r["side"] == "sell")
            members = sorted({r["member"] for r in recent_c})
            highlights.append({"level": "red" if s > b * 1.5 and s > 50000 else "green" if b > s * 1.5 and b > 50000 else "info",
                               "kind": "congress", "public": recent_c[0]["disclosed"],
                               "title": f"Congress: {len(members)} member{'s' if len(members) != 1 else ''}, "
                                        f"{sum(1 for r in recent_c if r['side'] == 'buy')} buys / {sum(1 for r in recent_c if r['side'] == 'sell')} sells in 12 months",
                               "detail": f"Roughly {_money(b)} bought vs {_money(s)} sold (midpoints of the reported ranges). "
                                         f"{', '.join(members[:5])}{' and others' if len(members) > 5 else ''}."})
        moved = [f for f in funds if f["change"] is not None and abs(f["change"]) >= 0.02]
        if moved:
            adds = sorted([f for f in moved if f["change"] > 0], key=lambda f: -f["change"])[:3]
            cuts = sorted([f for f in moved if f["change"] < 0], key=lambda f: f["change"])[:3]
            parts = ([("added: " + ", ".join(f"{f['holder']} +{f['change'] * 100:.0f}%" for f in adds))] if adds else []) + \
                    ([("cut: " + ", ".join(f"{f['holder']} {f['change'] * 100:.0f}%" for f in cuts))] if cuts else [])
            highlights.append({"level": "red" if len(cuts) > len(adds) else "green" if len(adds) > len(cuts) else "info",
                               "kind": "funds", "public": max(f["reported"] or "" for f in moved),
                               "title": "Big funds (0.5%+ holders) changed their positions last quarter",
                               "detail": "; ".join(parts) + ". Quarterly filings (13F), up to 45 days after the quarter ends."})
        short = own.get("short") or {}
        if short.get("change_mom") is not None and abs(short["change_mom"]) >= 0.15:
            highlights.append({"level": "red" if short["change_mom"] > 0 else "green", "kind": "short", "public": short.get("date"),
                               "title": f"Short interest {'up' if short['change_mom'] > 0 else 'down'} {abs(short['change_mom']) * 100:.0f}% in a month",
                               "detail": f"{(short.get('pct_float') or 0) * 100:.1f}% of the float is sold short ({short.get('days_to_cover') or '?'} days to cover)."})
        order = {"red": 0, "amber": 1, "green": 2, "info": 3}
        highlights.sort(key=lambda h: (h["public"] or "") >= str(today - timedelta(days=2)) and 0 or 1)
        highlights.sort(key=lambda h: order[h["level"]])
        for h in highlights:
            h["new"] = bool(h.get("public") and h["public"] >= str(today - timedelta(days=2)))

        lsym = sym.lower()
        links = [{"label": "Quiver: Congress trades", "url": f"https://www.quiverquant.com/congresstrading/stock/{sym}"},
                 {"label": "OpenInsider: Form 4s", "url": f"http://openinsider.com/search?q={sym}"},
                 {"label": "WhaleWisdom: fund holders (13F)", "url": f"https://whalewisdom.com/stock/{lsym}"},
                 {"label": "Unusual Whales: insiders", "url": f"https://unusualwhales.com/stock/{sym}/insiders"},
                 {"label": "SEC EDGAR filings", "url": f"https://www.sec.gov/edgar/browse/?CIK={sym}"}]
        return jsonable({
            "symbol": sym, "name": info.get("shortName") or info.get("longName"), "sector": sector, "industry": industry,
            "oversight": sorted(congress.COMMITTEE_NAMES.get(c, c) for c in oversight),
            "highlights": highlights, "congress": crows, "insiders": insiders[:80], "insider_summary": own.get("insider_summary"),
            "sec": fresh, "funds": funds, "min_stake": MIN_STAKE, "short": short, "links": links, "notes": notes,
            "speed": [["Planned sale (Form 144)", "on or before the sale day"], ["Executives, directors, 10%+ owners (Form 4)", "within 2 business days"],
                      ["Activist 5%+ stake (13D)", "within 5 business days"], ["Members of Congress", "within 45 days (median about 4 weeks)"],
                      ["Fund holdings (13F)", "quarterly, 45 days after the quarter"]],
        })

    return memo(f"smart:{sym}", 1800, build)


def congress_feed(days: int = 90) -> dict:
    """Every trade disclosed in the last ``days`` days, with the most bought / sold tickers and the most active
    members; trades by a member of a committee overseeing the company's industry are flagged."""

    def build():
        data = congress.trades(730)
        cut = str(date.today() - timedelta(days=days))
        rows = []
        for r in data["rows"]:
            if (r.get("disclosed") or "") < cut or not r.get("ticker"):
                continue
            sector, industry = _sector(r["ticker"]) if r.get("ticker") else (None, None)
            rel = oversight_committees(sector, industry) if sector else set()
            seats = data["committees"].get(r.get("bioguide") or "", [])
            hit = [c["name"] for c in seats if c["code"] in rel]
            lag = (date.fromisoformat(r["disclosed"]) - date.fromisoformat(r["traded"])).days if r.get("traded") and r.get("disclosed") else None
            rows.append({"chamber": r["chamber"][0], "member": r["member"], "party": r.get("party"), "state": r.get("state"),
                         "ticker": r.get("ticker"), "asset": (r.get("asset") or "")[:80], "atype": r.get("asset_type"),
                         "type": r.get("type"), "lo": r.get("amount_lo"), "hi": r.get("amount_hi"), "traded": r.get("traded"),
                         "disclosed": r.get("disclosed"), "owner": r.get("owner"), "lag": lag, "committee": hit[0] if hit else None,
                         "url": r.get("url"), "ocr": bool(r.get("ocr"))})
        by_t = defaultdict(lambda: {"buys": 0, "sells": 0, "buy_usd": 0.0, "sell_usd": 0.0, "members": set(), "asset": None})
        by_m = defaultdict(lambda: {"trades": 0, "buy_usd": 0.0, "sell_usd": 0.0, "party": None, "state": None, "chamber": None})
        for r in rows:
            side = _side(r["type"])
            mid = _mid({"amount_lo": r["lo"], "amount_hi": r["hi"]})
            if r["ticker"] and side:
                t = by_t[r["ticker"]]
                t["buys" if side == "buy" else "sells"] += 1
                t["buy_usd" if side == "buy" else "sell_usd"] += mid
                t["members"].add(r["member"])
                t["asset"] = t["asset"] or r["asset"]
            m = by_m[r["member"]]
            m["trades"] += 1
            m.update(party=r["party"], state=r["state"], chamber=r["chamber"])
            if side:
                m["buy_usd" if side == "buy" else "sell_usd"] += mid
        totals = {"trades": len(rows), "members": len(by_m), "buys": sum(1 for r in rows if _side(r["type"]) == "buy"),
                  "sells": sum(1 for r in rows if _side(r["type"]) == "sell"),
                  "committee_flagged": sum(1 for r in rows if r["committee"])}
        if days > 90:  # a year of rows is too heavy for a phone: keep the flagged and the big ones
            rows = [r for r in rows if r["committee"] or (r["lo"] or 0) >= 100001]
        tickers = [{"ticker": k, "name": (ALL_META.get(k) or {}).get("name") or _issuer(t["asset"]),
                    **{x: v for x, v in t.items() if x not in ("members", "asset")},
                    "members": len(t["members"]), "net_usd": t["buy_usd"] - t["sell_usd"]} for k, t in by_t.items()]
        members_ = [{"member": k, **m} for k, m in by_m.items()]
        return jsonable({
            "days": days, "as_of": data["as_of"], "stats": data["stats"], "rows": rows,
            "totals": totals, "rows_note": "Flagged and $100K+ trades only" if days > 90 else None,
            "most_bought": sorted(tickers, key=lambda t: (-t["buys"], -t["buy_usd"]))[:15],
            "most_sold": sorted(tickers, key=lambda t: (-t["sells"], -t["sell_usd"]))[:15],
            "most_active": sorted(members_, key=lambda m: -m["trades"])[:15],
        })

    return memo(f"congress-feed:{days}", 1800, build)
