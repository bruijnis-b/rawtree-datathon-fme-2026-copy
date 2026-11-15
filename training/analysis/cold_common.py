"""Shared set-up for the cold-start analysis: loads the live snapshot and the history into DuckDB (in memory).

Tables
  ev       live events + user class + split + per-user / per-session ranks
  rq       live requests + user class + split
  users    one row per live user: in_hist, flagged (is_new_user in any request), has_rq, held (live hold-out user)
  cat      catalogue incl. the practice-round new products (ref_price = catalogue price, is_new_product)

Split: `explore` = user not in the live hold-out (crc32(user_id:live) % 5 != 0) AND ts before the last 2 hours of
the snapshot. All exploratory numbers use `explore` only, unless a script says otherwise.

Run any script as:  python -m training.analysis.<name>   (data folders: env RAWTREE_LIVE / RAWTREE_HISTORY).
"""
from __future__ import annotations

import math
import os
import zlib

import duckdb

LIVE = os.environ.get("RAWTREE_LIVE", "C:/Users/jules/Projects/rawtree/data/raw/rawtree_live")
HIST = os.environ.get("RAWTREE_HISTORY", "C:/Users/jules/Projects/rawtree/data/raw/rawtree_history")


def connect() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute("SET TimeZone = 'UTC'")
    c.create_function("held", lambda u: zlib.crc32(f"{u}:live".encode()) % 5 == 0, ["VARCHAR"], "BOOLEAN")
    c.execute(f"CREATE TABLE ev0 AS SELECT * FROM read_parquet('{LIVE}/events/*.parquet')")
    c.execute(f"CREATE TABLE rq0 AS SELECT * FROM read_parquet('{LIVE}/requests/*.parquet')")
    c.execute(f"""CREATE TABLE hist_users AS
        SELECT user_id, sum(n_ev) AS h_events, sum(n_pur) AS h_purchases, sum(n_rq) AS h_requests FROM (
          SELECT user_id, count(*) AS n_ev, sum((event_type = 'purchase')::INT) AS n_pur, 0 AS n_rq
          FROM read_parquet('{HIST}/history_events/*.parquet') GROUP BY 1
          UNION ALL
          SELECT user_id, 0, 0, count(*) FROM read_parquet('{HIST}/history_sessions/*.parquet') GROUP BY 1)
        GROUP BY 1""")
    c.execute("""CREATE TABLE users AS
        WITH lu AS (SELECT DISTINCT user_id FROM ev0 UNION SELECT DISTINCT user_id FROM rq0),
             fl AS (SELECT user_id, max(is_new_user::INT) AS flagged, min(is_new_user::INT) AS flagged_min,
                           count(*) AS n_rq FROM rq0 GROUP BY 1)
        SELECT lu.user_id, (h.user_id IS NOT NULL) AS in_hist, coalesce(h.h_events, 0) AS h_events,
               coalesce(h.h_purchases, 0) AS h_purchases, coalesce(fl.flagged, 0) = 1 AS flagged,
               fl.flagged_min, (fl.user_id IS NOT NULL) AS has_rq, held(lu.user_id) AS held,
               CASE WHEN h.user_id IS NULL THEN 'cold' ELSE 'known' END AS cls
        FROM lu LEFT JOIN hist_users h USING (user_id) LEFT JOIN fl USING (user_id)""")
    t_end = c.execute("SELECT max(ts) FROM ev0").fetchall()[0][0]
    c.execute(f"""CREATE TABLE cat AS
        SELECT product_id, category, subcategory, brand, price_eur AS ref_price, FALSE AS is_new_product,
               NULL::TIMESTAMPTZ AS added_ts FROM read_parquet('{LIVE}/catalog.parquet')
        UNION ALL
        SELECT product_id, any_value(category), any_value(subcategory), any_value(brand), any_value(price_eur),
               TRUE, min(ts) FROM read_parquet('{LIVE}/catalog_updates.parquet')
        WHERE change = 'new_product'
          AND product_id NOT IN (SELECT product_id FROM read_parquet('{LIVE}/catalog.parquet')) GROUP BY 1""")
    c.execute(f"""CREATE TABLE ev AS
        SELECT e.*, u.cls, u.in_hist, u.flagged, u.has_rq, u.held,
               (NOT u.held AND e.ts < TIMESTAMPTZ '{t_end}' - INTERVAL 2 HOUR) AS explore,
               row_number() OVER (PARTITION BY e.user_id ORDER BY e.ts) - 1 AS k_user,
               row_number() OVER (PARTITION BY e.session_id ORDER BY e.ts) - 1 AS k_sess,
               dense_rank() OVER (PARTITION BY e.user_id ORDER BY s.s_start, e.session_id) AS sess_no,
               s.s_start, min(e.ts) OVER (PARTITION BY e.user_id) AS u_start,
               p.category, p.subcategory, p.brand, p.ref_price, p.is_new_product
        FROM ev0 e JOIN users u USING (user_id)
        JOIN (SELECT session_id, min(ts) AS s_start FROM ev0 GROUP BY 1) s USING (session_id)
        LEFT JOIN cat p USING (product_id)""")
    c.execute(f"""CREATE TABLE rq AS
        SELECT r.*, u.cls, u.in_hist, u.flagged, u.held,
               (NOT u.held AND r.ts < TIMESTAMPTZ '{t_end}' - INTERVAL 2 HOUR) AS explore
        FROM rq0 r JOIN users u USING (user_id)""")
    c.execute(f"CREATE TABLE fb AS SELECT * FROM read_parquet('{LIVE}/feedback/*.parquet')")
    return c


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return mid - half, mid + half


def rate(k, n) -> str:
    """'12.3 % [11.9, 12.7] (n=...)' with a 95 % Wilson interval."""
    k, n = float(k or 0), float(n or 0)
    lo, hi = wilson(k, n)
    return f"{100 * k / n:6.2f} % [{100 * lo:5.2f}, {100 * hi:5.2f}] (n={int(n)})" if n else "n=0"


def show(c, title: str, sql: str, fmt=None) -> list:
    """Run sql and print a small table."""
    r = c.execute(sql)
    cols = [d[0] for d in r.description]
    rows = r.fetchall()
    print(f"\n## {title}")
    print(" | ".join(cols))
    for row in rows:
        print(" | ".join(f"{x:.4g}" if isinstance(x, float) else str(x) for x in row))
    return rows
