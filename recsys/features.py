"""Precomputed signals shared by policies, computed in RawTree SQL and cached in memory."""
from __future__ import annotations

from collections import defaultdict

from . import client


def purchase_counts(days: int | None = None) -> dict[str, int]:
    """Purchases per product in shop.history_events (all 60 days, or the last `days` of history)."""
    where = "event_type = 'purchase'"
    if days:
        where += (f" AND ts::DateTime64(3) >= (SELECT max(ts::DateTime64(3)) FROM shop.history_events)"
                  f" - INTERVAL {int(days)} DAY")
    rows = client.query(f"""
        SELECT product_id::String AS product_id, count() AS n
        FROM shop.history_events WHERE {where}
        GROUP BY product_id""")
    return {r["product_id"]: int(r["n"]) for r in rows}


def rank(counts: dict[str, int]) -> list[str]:
    """Products by count, highest first; ties broken by higher product_id (same as the starter baseline)."""
    return [p for _, p in sorted(((n, p) for p, n in counts.items()), reverse=True)]


def rank_by_group(counts: dict[str, int], group_of) -> dict[str, list[str]]:
    """`rank` within each group, e.g. group_of = lambda pid: catalog.get(pid).category."""
    groups: dict[str, dict[str, int]] = defaultdict(dict)
    for p, n in counts.items():
        g = group_of(p)
        if g is not None:
            groups[g][p] = n
    return {g: rank(c) for g, c in groups.items()}


def coviews(top_k: int = 20) -> dict[str, list[str]]:
    """For every product, the `top_k` products most often viewed in the same session (history). ~3 s."""
    rows = client.query(f"""
        SELECT a.product_id AS p, b.product_id AS q, count() AS n
        FROM (SELECT session_id::String AS s, product_id::String AS product_id
              FROM shop.history_events WHERE event_type = 'view') AS a
        INNER JOIN (SELECT session_id::String AS s, product_id::String AS product_id
                    FROM shop.history_events WHERE event_type = 'view') AS b ON a.s = b.s
        WHERE a.product_id != b.product_id
        GROUP BY p, q
        ORDER BY p, n DESC, q
        LIMIT {int(top_k)} BY p""", timeout=120)
    out: dict[str, list[str]] = defaultdict(list)
    for r in rows:  # already ordered by p, then n DESC
        out[r["p"]].append(r["q"])
    return dict(out)
