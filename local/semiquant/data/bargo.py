"""Bargo's free Congress stock-trades API: an independent copy of the House and Senate STOCK Act trades, used to
cross-check ours (www.bargo.ai/free-apis/congress, no key).

Free without a key: 30 requests and 100 rows a day per address, last 3 months only. One call every 6 hours
(cached on disk) stays far inside that. Licence: free to use with a visible credit linking to Bargo wherever its
data is shown; derived analyses are fine, redistributing its raw records is not. So it is used to *check* our
trades and to fill the rare trade we missed, each shown with the credit; it is never published as a dataset.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from . import cache

BASE = "https://www.bargo.ai/free-apis/congress/v1"
HOME = "https://www.bargo.ai/free-apis/congress"
UA = {"User-Agent": "SemiQuant research tool (personal use)"}
TTL = 6 * 3600

__all__ = ["recent", "parse", "BASE", "HOME"]


def parse(d: dict) -> list[dict]:
    """Bargo trades -> our row shape (``source: "bargo"``). Rows without a ticker or a trade date are dropped."""
    out = []
    for t in d.get("trades") or []:
        if not t.get("ticker") or not t.get("transaction_date"):
            continue
        kind = str(t.get("type") or "").lower()
        side = "buy" if kind.startswith("purchase") else "sell_partial" if "partial" in kind else "sell" if kind.startswith("sale") else (
            "exchange" if kind.startswith("exchange") else None)
        out.append({"member": t.get("member") or "", "chamber": "Senate" if str(t.get("chamber")).lower() == "senate" else "House",
                    "state_dst": t.get("state") or "", "ticker": str(t["ticker"]).upper().replace(".", "-"), "asset": t.get("asset") or "",
                    "asset_type": "Stock", "type": side, "traded": t["transaction_date"], "disclosed": t.get("disclosure_date"),
                    "notified": None, "amount_lo": t.get("amount_low"), "amount_hi": t.get("amount_high"), "owner": None,
                    "url": t.get("filing_portal") or HOME, "source": "bargo"})
    return out


def recent(days: int = 60, limit: int = 100) -> list[dict]:
    """Bargo's newest trades made in the last ``days`` days (one request, at most 100 rows), cached 6 hours."""
    since = (date.today() - timedelta(days=days)).isoformat()

    def load() -> list[dict]:
        r = requests.get(f"{BASE}/trades", params={"from": since, "limit": min(limit, 100)}, headers=UA, timeout=30)
        if r.status_code == 429:
            raise RuntimeError("Bargo free limit reached for today")
        r.raise_for_status()
        return parse(r.json())
    return cache.cached(f"bargo:recent:{since}:{limit}", TTL, load, disk=True)

