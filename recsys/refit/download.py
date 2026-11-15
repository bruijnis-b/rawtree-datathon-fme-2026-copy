"""Download what the refit needs into data/refit/ (gitignored): python -m recsys.refit.download [--from 'YYYY-MM-DD HH:MM']

Live (re-downloaded every run, from --from, default today 09:00 UTC): shop.events, shop.requests, our feedback.
History (once, skipped when the file exists; ~10 min): purchases and the shopper's events from shop.history_events,
and views per shopper and subcategory.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from recsys.client import ROOT, TEAM, query

OUT = ROOT / "data" / "refit"


def _chunks(start: datetime, end: datetime, step: timedelta):
    t = start
    while t < end:
        yield t.strftime("%Y-%m-%d %H:%M:%S"), int(step.total_seconds())
        t += step


def live(start: datetime) -> None:
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    ev = []
    for a, s in _chunks(start, end, timedelta(minutes=20)):
        ev += query(f"""SELECT toUnixTimestamp64Milli(ts::DateTime64(3)) t, user_id::String u, product_id::String p,
            event_type::String e FROM shop.events
            WHERE ts::DateTime64(3) >= '{a}' AND ts::DateTime64(3) < toDateTime64('{a}', 3) + INTERVAL {s} SECOND""")
    pd.DataFrame(ev).to_parquet(OUT / "events.parquet")
    rq = []
    for a, s in _chunks(start, end, timedelta(hours=1)):
        rows = query(f"""SELECT request_id::String r, toUnixTimestamp64Milli(ts::DateTime64(3)) t, user_id::String u,
            is_new_user new, `context.page`::String page, `context.device`::String dv, `context.region`::String rg,
            recent_views rv FROM shop.requests
            WHERE ts::DateTime64(3) >= '{a}' AND ts::DateTime64(3) < toDateTime64('{a}', 3) + INTERVAL {s} SECOND""")
        for x in rows:
            x["rv"] = [v["product_id"] for v in sorted(x["rv"] or [], key=lambda v: v["ts"])]
            x["new"] = bool(x["new"])
        rq += rows
    pd.DataFrame(rq).to_parquet(OUT / "requests.parquet")
    fb = query(f"""SELECT request_id::String r, model_version::String m, shown, clicked::String c, purchased::String p,
        served_by::String sb FROM {TEAM}.feedback WHERE request_id::String != '__init__'""", timeout=60)
    pd.DataFrame(fb).to_parquet(OUT / "feedback.parquet")
    print(f"live: {len(ev)} events, {len(rq)} requests, {len(fb)} feedback rows")


def history() -> None:
    if not (OUT / "hevents.parquet").exists():
        ev = []
        for a, s in _chunks(datetime(2026, 9, 15), datetime(2026, 11, 14, 9), timedelta(hours=12)):
            ev += query(f"""SELECT toUnixTimestamp64Milli(ts::DateTime64(3)) t, user_id::String u, product_id::String p,
                event_type::String e FROM shop.history_events
                WHERE ts::DateTime64(3) >= '{a}' AND ts::DateTime64(3) < toDateTime64('{a}', 3) + INTERVAL {s} SECOND""")
        pd.DataFrame(ev).to_parquet(OUT / "hevents.parquet")
        print(f"history: {len(ev)} events")
    if not (OUT / "hist_user_subcat.parquet").exists():
        out = []
        for k in range(8):
            out += query(f"""SELECT e.user_id::String u, c.category::String c, c.subcategory::String s, count() n
                FROM shop.history_events e INNER JOIN shop.catalog c ON e.product_id::String = c.product_id::String
                WHERE e.event_type::String = 'view' AND cityHash64(e.user_id::String) % 8 = {k} GROUP BY u, c, s""")
        pd.DataFrame(out).to_parquet(OUT / "hist_user_subcat.parquet")
        print(f"history: {len(out)} shopper x subcategory rows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="start", default=None, help="UTC start of the live data (default today 09:00)")
    args = ap.parse_args()
    start = (datetime.strptime(args.start, "%Y-%m-%d %H:%M") if args.start
             else datetime.now(timezone.utc).replace(tzinfo=None, hour=9, minute=0, second=0, microsecond=0))
    OUT.mkdir(parents=True, exist_ok=True)
    t = time.time()
    history()
    live(start)
    print(f"done in {time.time() - t:.0f} s -> {OUT}")


if __name__ == "__main__":
    main()
