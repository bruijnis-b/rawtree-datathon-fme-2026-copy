"""Export the RawTree history to Parquet: python -m training.data.export_history [--out DIR] [--workers N].

Writes, under --out (default data/raw/rawtree_history):

- catalog.parquet
- history_sessions/date=YYYY-MM-DD.parquet   one file per UTC day
- history_events/date=YYYY-MM-DD.parquet     one file per UTC day
- manifest.json                              rows per table and day, checked against count() in RawTree

Only types are made concrete and `context.*` is flattened to device/region/page; nothing is filtered or joined.
Days already on disk with the expected row count are skipped, so an interrupted export resumes. Runs on a
machine with the RawTree key in .env (it reuses recsys.client); the key is never written anywhere.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from recsys.client import query

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "raw" / "rawtree_history"

TS = pa.timestamp("ms", tz="UTC")

CATALOG_SCHEMA = pa.schema([
    ("product_id", pa.string()), ("category", pa.string()), ("subcategory", pa.string()),
    ("brand", pa.string()), ("price_eur", pa.float64()), ("description", pa.string()),
    ("created_at", TS), ("is_active", pa.bool_()),
])

SESSIONS_SCHEMA = pa.schema([
    ("request_id", pa.string()), ("ts", TS), ("user_id", pa.string()),
    ("device", pa.string()), ("region", pa.string()), ("page", pa.string()),
    ("recent_views", pa.list_(pa.struct([("product_id", pa.string()), ("ts", TS)]))),
    ("shown", pa.list_(pa.string())), ("propensity", pa.list_(pa.float64())),
    ("clicked", pa.string()), ("purchased", pa.string()), ("revenue_eur", pa.float64()),
])

EVENTS_SCHEMA = pa.schema([
    ("ts", TS), ("event_type", pa.string()), ("user_id", pa.string()), ("session_id", pa.string()),
    ("product_id", pa.string()), ("price_eur", pa.float64()), ("device", pa.string()), ("region", pa.string()),
])

DAY_FILTER = "ts::DateTime64(3) >= '{d} 00:00:00' AND ts::DateTime64(3) < '{d} 00:00:00' + INTERVAL 1 DAY"

SESSIONS_SQL = """
SELECT request_id::String AS request_id, toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms,
       user_id::String AS user_id, context.device::String AS device, context.region::String AS region,
       context.page::String AS page, recent_views, shown, propensity,
       clicked::Nullable(String) AS clicked, purchased::Nullable(String) AS purchased,
       revenue_eur::Float64 AS revenue_eur
FROM shop.history_sessions WHERE {where} ORDER BY ts_ms, request_id
"""

EVENTS_SQL = """
SELECT toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms, event_type::String AS event_type,
       user_id::String AS user_id, session_id::String AS session_id, product_id::String AS product_id,
       price_eur::Float64 AS price_eur, device::String AS device, region::String AS region
FROM shop.history_events WHERE {where} ORDER BY ts_ms
"""

TABLES = {
    "history_sessions": (SESSIONS_SQL, SESSIONS_SCHEMA),
    "history_events": (EVENTS_SQL, EVENTS_SCHEMA),
}


def _ts_ms(s: str | None) -> int | None:
    """'2026-10-01 00:00:21.951000000' (UTC) -> epoch ms."""
    if not s:
        return None
    s = str(s)[:23]  # keep millisecond precision
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _str_or_none(v) -> str | None:
    return None if v in (None, "") else str(v)


def _sessions_table(rows: list[dict]) -> pa.Table:
    cols: dict[str, list] = {f.name: [] for f in SESSIONS_SCHEMA}
    for r in rows:
        cols["request_id"].append(r["request_id"])
        cols["ts"].append(int(r["ts_ms"]))
        cols["user_id"].append(r["user_id"])
        cols["device"].append(r["device"])
        cols["region"].append(r["region"])
        cols["page"].append(r["page"])
        views = [v for v in (r.get("recent_views") or []) if isinstance(v, dict) and v.get("product_id")]
        cols["recent_views"].append([{"product_id": str(v["product_id"]), "ts": _ts_ms(v.get("ts"))} for v in views])
        cols["shown"].append([str(p) for p in (r.get("shown") or [])])
        cols["propensity"].append([float(p) for p in (r.get("propensity") or [])])
        cols["clicked"].append(_str_or_none(r.get("clicked")))
        cols["purchased"].append(_str_or_none(r.get("purchased")))
        cols["revenue_eur"].append(float(r.get("revenue_eur") or 0.0))
    return pa.table(cols, schema=SESSIONS_SCHEMA)


def _events_table(rows: list[dict]) -> pa.Table:
    cols: dict[str, list] = {f.name: [r[f.name if f.name != "ts" else "ts_ms"] for r in rows] for f in EVENTS_SCHEMA}
    cols["ts"] = [int(x) for x in cols["ts"]]
    return pa.table(cols, schema=EVENTS_SCHEMA)


def _query(sql: str, attempts: int = 4) -> list[dict]:
    for i in range(attempts):
        try:
            return query(sql, timeout=180)
        except Exception:  # noqa: BLE001  network hiccups and RawTree 5xx: back off and retry
            if i == attempts - 1:
                raise
            time.sleep(2 ** i * 2)
    raise AssertionError("unreachable")


def day_counts(table: str) -> dict[str, int]:
    rows = _query(f"SELECT toString(toDate(ts::DateTime64(3))) AS d, count() AS n FROM shop.{table} GROUP BY d ORDER BY d")
    return {r["d"]: int(r["n"]) for r in rows}


def export_day(table: str, day: str, out: Path) -> tuple[str, int, int]:
    sql_tpl, _ = TABLES[table]
    rows = _query(sql_tpl.format(where=DAY_FILTER.format(d=day)))
    t = _sessions_table(rows) if table == "history_sessions" else _events_table(rows)
    path = out / table / f"date={day}.parquet"
    tmp = path.with_suffix(".tmp")
    pq.write_table(t, tmp, compression="zstd")
    tmp.replace(path)
    return day, t.num_rows, path.stat().st_size


def export_catalog(out: Path) -> int:
    rows = _query("""
        SELECT product_id::String AS product_id, category::String AS category, subcategory::String AS subcategory,
               brand::String AS brand, price_eur::Float64 AS price_eur, description::String AS description,
               toUnixTimestamp64Milli(created_at::DateTime64(3)) AS created_ms, is_active::Bool AS is_active
        FROM shop.catalog ORDER BY product_id""")
    cols = {f.name: [r.get(f.name) for r in rows] for f in CATALOG_SCHEMA}
    cols["created_at"] = [int(r["created_ms"]) for r in rows]
    pq.write_table(pa.table(cols, schema=CATALOG_SCHEMA), out / "catalog.parquet", compression="zstd")
    return len(rows)


def _on_disk(path: Path) -> int | None:
    return pq.ParquetFile(path).metadata.num_rows if path.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    out: Path = args.out
    for table in TABLES:
        (out / table).mkdir(parents=True, exist_ok=True)

    manifest: dict = {"source": "RawTree shop.* (history)", "tables": {}}

    n_cat = export_catalog(out)
    rawtree_cat = int(_query("SELECT count() AS n FROM shop.catalog")[0]["n"])
    manifest["tables"]["catalog"] = {"rows": n_cat, "rawtree_rows": rawtree_cat, "single_file": True}
    print(f"catalog: {n_cat:,} products")

    failed = []
    for pos, table in enumerate(TABLES):
        expected = day_counts(table)
        todo = [d for d, n in expected.items() if _on_disk(out / table / f"date={d}.parquet") != n]
        bar = tqdm(total=len(expected), initial=len(expected) - len(todo), desc=table, unit="day")
        rows_done, mb = 0, 0.0
        with ThreadPoolExecutor(args.workers) as pool:
            futures = {pool.submit(export_day, table, d, out): d for d in todo}
            for f in as_completed(futures):
                try:
                    _, n, size = f.result()
                except Exception as e:  # noqa: BLE001
                    failed.append((table, futures[f], repr(e)[:200]))
                    bar.write(f"FAILED {table} {futures[f]}: {repr(e)[:200]}")
                    continue
                rows_done += n
                mb += size / 1e6
                bar.update(1)
                bar.set_postfix(rows=f"{rows_done:,}", parquet_mb=f"{mb:.0f}")
        bar.close()

        days = {d: _on_disk(out / table / f"date={d}.parquet") or 0 for d in expected}
        bad = {d: (days[d], n) for d, n in expected.items() if days[d] != n}
        for d, (got, want) in bad.items():
            print(f"MISMATCH {table} {d}: parquet {got:,} vs rawtree {want:,}")
        manifest["tables"][table] = {
            "rows": sum(days.values()), "rawtree_rows": sum(expected.values()), "days": days,
        }

    manifest["exported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["first_day"] = min(manifest["tables"]["history_events"]["days"])
    manifest["last_day"] = max(manifest["tables"]["history_events"]["days"])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    for table, info in manifest["tables"].items():
        print(f"{table:18s} {info['rows']:>12,} rows (rawtree {info['rawtree_rows']:,})")
    if failed or any(i["rows"] != i["rawtree_rows"] for i in manifest["tables"].values()):
        raise SystemExit(f"export incomplete ({len(failed)} failed days): run again to resume")
    print(f"done: {out}")


if __name__ == "__main__":
    main()
