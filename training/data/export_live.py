"""Export the live practice stream to Parquet: python -m training.data.export_live [--out DIR] [--until TS].

Writes, under --out (default data/raw/rawtree_live):

- catalog.parquet                     shop.catalog
- catalog_updates.parquet             shop.catalog_updates (new_product, price_change, out_of_stock, ...)
- requests/hour=YYYY-MM-DDTHH.parquet shop.requests, one file per UTC hour
- events/hour=...parquet              shop.events
- feedback/hour=...parquet            <team>.feedback (placeholder row removed)
- manifest.json                       rows per table and hour, checked against count() in RawTree

Same approach as export_history.py: hours on disk with the expected row count are skipped. Everything up to --until
(default: now, rounded down to the minute) is exported; the last hour is partial. Runs on the laptop (key in .env).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from recsys.client import query
from training.data.export_history import CATALOG_SCHEMA, EVENTS_SCHEMA, TS, _ts_ms

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "raw" / "rawtree_live"
TEAM = os.environ.get("TEAM_ID", "team_33")

REQUESTS_SCHEMA = pa.schema([
    ("request_id", pa.string()), ("ts", TS), ("user_id", pa.string()), ("is_new_user", pa.bool_()),
    ("device", pa.string()), ("region", pa.string()), ("page", pa.string()),
    ("recent_views", pa.list_(pa.struct([("product_id", pa.string()), ("ts", TS)]))),
])
FEEDBACK_SCHEMA = pa.schema([
    ("request_id", pa.string()), ("ts", TS), ("shown", pa.list_(pa.string())), ("clicked", pa.string()),
    ("purchased", pa.string()), ("revenue_eur", pa.float64()), ("served_by", pa.string()),
    ("fallback_reason", pa.string()), ("latency_ms", pa.float64()),
])
UPDATES_SCHEMA = pa.schema([
    ("ts", TS), ("change", pa.string()), ("product_id", pa.string()), ("category", pa.string()),
    ("subcategory", pa.string()), ("brand", pa.string()), ("price_eur", pa.float64()), ("description", pa.string()),
    ("is_active", pa.bool_()),
])

WHERE = "ts::DateTime64(3) >= '{a}' AND ts::DateTime64(3) < '{b}'"
SQL = {
    "requests": """SELECT request_id::String AS request_id, toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms,
        user_id::String AS user_id, is_new_user::Bool AS is_new_user, context.device::String AS device,
        context.region::String AS region, context.page::String AS page, recent_views
        FROM shop.requests WHERE {w}""",
    "events": """SELECT toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms, event_type::String AS event_type,
        user_id::String AS user_id, session_id::String AS session_id, product_id::String AS product_id,
        price_eur::Float64 AS price_eur, device::String AS device, region::String AS region
        FROM shop.events WHERE {w}""",
    "feedback": """SELECT request_id::String AS request_id, toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms, shown,
        clicked::Nullable(String) AS clicked, purchased::Nullable(String) AS purchased,
        revenue_eur::Float64 AS revenue_eur, served_by::Nullable(String) AS served_by,
        fallback_reason::Nullable(String) AS fallback_reason, latency_ms::Float64 AS latency_ms
        FROM {team}.feedback WHERE request_id::String != '__init__' AND {w}""",
}
SOURCE = {"requests": "shop.requests", "events": "shop.events", "feedback": f"{TEAM}.feedback"}


def _q(sql: str, attempts: int = 4) -> list[dict]:
    for i in range(attempts):
        try:
            return query(sql, timeout=180)
        except Exception:  # noqa: BLE001
            if i == attempts - 1:
                raise
            time.sleep(2 ** i * 2)
    raise AssertionError


def _s(v):
    return None if v in (None, "") else str(v)


def _table(name: str, rows: list[dict]) -> pa.Table:
    if name == "events":
        cols = {f.name: [r[f.name if f.name != "ts" else "ts_ms"] for r in rows] for f in EVENTS_SCHEMA}
        cols["ts"] = [int(x) for x in cols["ts"]]
        return pa.table(cols, schema=EVENTS_SCHEMA)
    if name == "requests":
        cols = {f.name: [] for f in REQUESTS_SCHEMA}
        for r in rows:
            cols["request_id"].append(r["request_id"])
            cols["ts"].append(int(r["ts_ms"]))
            cols["user_id"].append(r["user_id"])
            cols["is_new_user"].append(bool(r.get("is_new_user")))
            for k in ("device", "region", "page"):
                cols[k].append(r.get(k))
            views = [v for v in (r.get("recent_views") or []) if isinstance(v, dict) and v.get("product_id")]
            cols["recent_views"].append([{"product_id": str(v["product_id"]), "ts": _ts_ms(v.get("ts"))}
                                         for v in views])
        return pa.table(cols, schema=REQUESTS_SCHEMA)
    cols = {f.name: [] for f in FEEDBACK_SCHEMA}
    for r in rows:
        cols["request_id"].append(r["request_id"])
        cols["ts"].append(int(r["ts_ms"]))
        cols["shown"].append([str(p) for p in (r.get("shown") or [])])
        cols["clicked"].append(_s(r.get("clicked")))
        cols["purchased"].append(_s(r.get("purchased")))
        cols["revenue_eur"].append(float(r.get("revenue_eur") or 0))
        cols["served_by"].append(_s(r.get("served_by")))
        cols["fallback_reason"].append(_s(r.get("fallback_reason")))
        cols["latency_ms"].append(float(r.get("latency_ms") or 0))
    return pa.table(cols, schema=FEEDBACK_SCHEMA)


def hour_counts(name: str, until: str) -> dict[str, int]:
    extra = "request_id::String != '__init__' AND " if name == "feedback" else ""
    rows = _q(f"SELECT formatDateTime(toStartOfHour(ts::DateTime64(3)), '%Y-%m-%dT%H') AS h, count() AS n "
              f"FROM {SOURCE[name]} WHERE {extra}ts::DateTime64(3) >= '2026-11-01' AND ts::DateTime64(3) < '{until}' "
              f"GROUP BY h ORDER BY h")
    return {r["h"]: int(r["n"]) for r in rows}


def export_hour(name: str, hour: str, until: str, out: Path) -> int:
    a = hour.replace("T", " ") + ":00:00"
    b_dt = datetime.fromisoformat(a) .replace(tzinfo=timezone.utc).timestamp() + 3600
    b = min(datetime.fromtimestamp(b_dt, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), until)
    rows = _q(SQL[name].format(w=WHERE.format(a=a, b=b), team=TEAM))
    t = _table(name, rows)
    path = out / name / f"hour={hour}.parquet"
    tmp = path.with_suffix(".tmp")
    pq.write_table(t, tmp, compression="zstd")
    tmp.replace(path)
    return t.num_rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--until", default=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:00"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    out, until = args.out, args.until
    manifest = {"source": "RawTree live practice stream", "until_utc": until, "tables": {}}
    out.mkdir(parents=True, exist_ok=True)

    cat = _q("""SELECT product_id::String AS product_id, category::String AS category,
        subcategory::String AS subcategory, brand::String AS brand, price_eur::Float64 AS price_eur,
        description::String AS description, toUnixTimestamp64Milli(created_at::DateTime64(3)) AS created_ms,
        is_active::Bool AS is_active FROM shop.catalog ORDER BY product_id""")
    cols = {f.name: [r.get(f.name) for r in cat] for f in CATALOG_SCHEMA}
    cols["created_at"] = [int(r["created_ms"]) for r in cat]
    pq.write_table(pa.table(cols, schema=CATALOG_SCHEMA), out / "catalog.parquet", compression="zstd")
    manifest["tables"]["catalog"] = {"rows": len(cat)}

    upd = _q(f"""SELECT toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms, change::String AS change,
        product_id::String AS product_id, category::Nullable(String) AS category,
        subcategory::Nullable(String) AS subcategory, brand::Nullable(String) AS brand,
        price_eur::Nullable(Float64) AS price_eur, description::Nullable(String) AS description,
        is_active::Nullable(Bool) AS is_active FROM shop.catalog_updates WHERE ts::DateTime64(3) < '{until}'
        ORDER BY ts_ms""")
    cols = {f.name: [r.get(f.name if f.name != "ts" else "ts_ms") for r in upd] for f in UPDATES_SCHEMA}
    pq.write_table(pa.table(cols, schema=UPDATES_SCHEMA), out / "catalog_updates.parquet", compression="zstd")
    manifest["tables"]["catalog_updates"] = {"rows": len(upd)}
    print(f"catalog {len(cat)}, catalog_updates {len(upd)}", flush=True)

    bad = []
    for name in SQL:
        (out / name).mkdir(exist_ok=True)
        expected = hour_counts(name, until)
        def on_disk(h):
            p = out / name / f"hour={h}.parquet"
            return pq.ParquetFile(p).metadata.num_rows if p.exists() else None
        todo = [h for h, n in expected.items() if on_disk(h) != n]
        with ThreadPoolExecutor(args.workers) as pool:
            futs = {pool.submit(export_hour, name, h, until, out): h for h in todo}
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as e:  # noqa: BLE001
                    bad.append((name, futs[f], repr(e)[:200]))
        got = {h: on_disk(h) or 0 for h in expected}
        mism = {h: (got[h], n) for h, n in expected.items() if got[h] != n}
        manifest["tables"][name] = {"rows": sum(got.values()), "rawtree_rows": sum(expected.values()), "hours": got}
        print(f"{name:10s} {sum(got.values()):>10,} rows (rawtree {sum(expected.values()):,}); mismatched hours: "
              f"{mism or 'none'}", flush=True)
        if mism:
            bad.append((name, "mismatch", str(mism)))
    manifest["exported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if bad:
        raise SystemExit(f"export incomplete: {bad[:5]}; run again to resume")
    print(f"done: {out}")


if __name__ == "__main__":
    main()
