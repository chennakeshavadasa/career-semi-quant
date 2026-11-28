"""Regenerate tests/fixtures/world from the live PortWatch service (GDELT samples are saved by hand from real answers).

    python tests/make_world_fixtures.py

Four chokepoints (Hormuz, Suez, Bab el-Mandeb, Taiwan Strait) from 2023-11-01, kept in the service's own row shape
and gzipped, so the tests run the same parsing code as production.
"""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from semiquant.data import portwatch as pw  # noqa: E402

OUT = os.path.join(HERE, "fixtures", "world")
IDS = ["chokepoint6", "chokepoint1", "chokepoint4", "chokepoint11"]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    d = pw._query("PortWatch_chokepoints_database", where="1=1", orderByFields="vessel_count_total DESC",
                  outFields="portid,portname,lat,lon,vessel_count_total,industry_top1,industry_top2,industry_top3")
    json.dump(d, open(os.path.join(OUT, "portwatch_chokepoints.json"), "w"), separators=(",", ":"))
    rows = []
    for cid in IDS:
        off = 0
        while True:
            r = pw._query("Daily_Chokepoints_Data", where=f"date >= '2023-11-01' AND portid = '{cid}'", orderByFields="date",
                          outFields="date,portid,portname,n_total,n_tanker,n_container,n_dry_bulk,n_cargo,capacity",
                          resultOffset=off, resultRecordCount=pw.PAGE)
            got = r.get("features", [])
            rows += got
            if len(got) < pw.PAGE:
                break
            off += len(got)
    with gzip.open(os.path.join(OUT, "portwatch_daily.json.gz"), "wt") as f:
        json.dump({"features": rows}, f, separators=(",", ":"))
    d = pw._query("portwatch_disruptions_database", where="1=1", orderByFields="fromdate DESC", resultRecordCount=30,
                  outFields="eventid,eventtype,eventname,htmlname,alertlevel,country,fromdate,todate,severitytext,affectedports,n_affectedports,editdate")
    json.dump(d, open(os.path.join(OUT, "portwatch_disruptions.json"), "w"), separators=(",", ":"))
    print("wrote", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
