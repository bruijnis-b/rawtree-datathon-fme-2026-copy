"""Look around in the historical data: python -m training.data.inspect <command> [args].

Commands (all read the local Parquet through DuckDB; no RawTree access needed):

  summary                       rows, columns and types, null %, time range, distinct users/products per table
  sample <table> [-n N]         random rows of catalog | sessions | events
  product <product_id>          catalogue row, organic events, carousel shows/clicks/purchases, CTR per slot
  user <user_id> [-n N]         the user's organic events and carousels, merged on one timeline
  carousel <request_id>         context, recent views and the 10 shown products with their details and outcome
  sql "<query>"                 any DuckDB query over the views catalog, sessions, events

Views: catalog(product_id, category, subcategory, brand, price_eur, description, created_at, is_active),
sessions(request_id, ts, user_id, device, region, page, recent_views, shown, propensity, clicked, purchased,
revenue_eur), events(ts, event_type, user_id, session_id, product_id, price_eur, device, region).
"""
from __future__ import annotations

import argparse
import sys

import duckdb

from training.data.paths import con, history_dir

TABLES = ("catalog", "sessions", "events")


def _show(rel: duckdb.DuckDBPyRelation, rows: int = 50) -> None:
    rel.show(max_rows=rows, max_width=200)


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def summary(c: duckdb.DuckDBPyConnection) -> None:
    print(f"dataset: {history_dir()}\n")
    for t in TABLES:
        n = c.execute(f"SELECT count(*) FROM {t}").fetchall()[0][0]
        print(f"== {t}: {n:,} rows")
        cols = c.execute(f"DESCRIBE {t}").fetchall()
        nulls = ", ".join(f"round(100 * count_if({name} IS NULL) / count(*), 2) AS \"{name}\"" for name, *_ in cols)
        null_pct = dict(zip([name for name, *_ in cols], c.execute(f"SELECT {nulls} FROM {t}").fetchall()[0]))
        for name, typ, *_ in cols:
            print(f"   {name:14s} {typ:45s} null {null_pct[name]:6.2f} %")
        if t != "catalog":
            lo, hi, users, prods = c.execute(f"""
                SELECT min(ts), max(ts), count(DISTINCT user_id),
                       {'count(DISTINCT product_id)' if t == 'events' else 'NULL'} FROM {t}""").fetchall()[0]
            print(f"   time {lo} .. {hi} · {users:,} users" + (f" · {prods:,} products" if prods else ""))
        print()
    _show(c.sql("SELECT event_type, count(*) AS n FROM events GROUP BY ALL ORDER BY n DESC"))
    _show(c.sql("""SELECT count(*) AS carousels, avg((clicked IS NOT NULL)::INT) AS click_rate,
                          avg((purchased IS NOT NULL)::INT) AS purchase_rate, avg(revenue_eur) AS revenue_per_carousel,
                          avg(len(recent_views)) AS avg_recent_views FROM sessions"""))


def sample(c, table: str, n: int) -> None:
    _show(c.sql(f"SELECT * FROM {table} USING SAMPLE {n} ROWS"), n)


def product(c, pid: str) -> None:
    p = _lit(pid)
    _show(c.sql(f"SELECT * FROM catalog WHERE product_id = {p}"))
    _show(c.sql(f"""SELECT event_type, count(*) AS n, count(DISTINCT user_id) AS users, min(ts) AS first, max(ts) AS last
                    FROM events WHERE product_id = {p} GROUP BY ALL ORDER BY n DESC"""))
    _show(c.sql(f"""
        WITH s AS (SELECT unnest(range(1, 11)) AS slot, unnest(shown) AS pid, unnest(propensity) AS prop, clicked, purchased
                   FROM sessions)
        SELECT slot, count(*) AS shown, avg(prop) AS avg_propensity,
               count_if(clicked = pid) AS clicks, count_if(purchased = pid) AS purchases,
               round(count_if(clicked = pid) / count(*), 4) AS ctr
        FROM s WHERE pid = {p} GROUP BY slot ORDER BY slot"""))


def user(c, uid: str, n: int) -> None:
    u = _lit(uid)
    _show(c.sql(f"""
        SELECT ts, 'event' AS source, event_type AS what, product_id AS item, session_id AS detail, device, region
        FROM events WHERE user_id = {u}
        UNION ALL
        SELECT ts, 'carousel', page, coalesce(purchased, clicked, '-'),
               request_id || ' · ' || CASE WHEN purchased IS NOT NULL THEN 'purchased'
                                           WHEN clicked IS NOT NULL THEN 'clicked' ELSE 'no click' END, device, region
        FROM sessions WHERE user_id = {u}
        ORDER BY ts LIMIT {n}"""), n)


def carousel(c, rid: str) -> None:
    r = _lit(rid)
    _show(c.sql(f"SELECT request_id, ts, user_id, device, region, page, clicked, purchased, revenue_eur FROM sessions WHERE request_id = {r}"))
    print("recent views:")
    _show(c.sql(f"""
        WITH v AS (SELECT unnest(recent_views) AS v FROM sessions WHERE request_id = {r})
        SELECT v.ts, v.product_id, c.category, c.subcategory, c.brand, c.price_eur
        FROM v LEFT JOIN catalog c ON c.product_id = v.product_id ORDER BY v.ts"""))
    print("shown:")
    _show(c.sql(f"""
        WITH s AS (SELECT unnest(range(1, 11)) AS slot, unnest(shown) AS pid, unnest(propensity) AS propensity,
                          clicked, purchased FROM sessions WHERE request_id = {r})
        SELECT slot, pid AS product_id, c.category, c.subcategory, c.brand, c.price_eur, propensity,
               CASE WHEN purchased = pid THEN 'PURCHASED' WHEN clicked = pid THEN 'clicked' ELSE '' END AS outcome
        FROM s LEFT JOIN catalog c ON c.product_id = s.pid ORDER BY slot"""))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Inspect the historical RawTree data.", epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary")
    s = sub.add_parser("sample"); s.add_argument("table", choices=TABLES); s.add_argument("-n", type=int, default=10)
    s = sub.add_parser("product"); s.add_argument("product_id")
    s = sub.add_parser("user"); s.add_argument("user_id"); s.add_argument("-n", type=int, default=100)
    s = sub.add_parser("carousel"); s.add_argument("request_id")
    s = sub.add_parser("sql"); s.add_argument("query")
    a = ap.parse_args(argv)

    c = con()
    if a.cmd == "summary":
        summary(c)
    elif a.cmd == "sample":
        sample(c, a.table, a.n)
    elif a.cmd == "product":
        product(c, a.product_id)
    elif a.cmd == "user":
        user(c, a.user_id, a.n)
    elif a.cmd == "carousel":
        carousel(c, a.request_id)
    elif a.cmd == "sql":
        _show(c.sql(a.query), 200)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
