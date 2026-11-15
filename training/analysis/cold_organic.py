"""Q2 + Q3 on organic events (shop.events): what cold users buy, and how fast their purchases become predictable.

A session's events share one timestamp, so "before" always means "in an earlier session of the same user".
Exploration split only. Run: python -m training.analysis.cold_organic
"""
from __future__ import annotations

from training.analysis.cold_common import LIVE, connect, show


def main():
    c = connect()
    c.execute("CREATE TABLE pu AS SELECT * FROM ev WHERE explore AND event_type = 'purchase'")
    c.execute("""CREATE TABLE pop AS SELECT product_id, count(*) AS n,
        row_number() OVER (ORDER BY count(*) DESC, product_id) AS prank FROM pu GROUP BY 1""")
    show(c, "organic purchases: concentration (share on the overall top-N products) and price",
         "SELECT cls, count(*) AS purchases, round(100 * avg((prank <= 10)::INT), 1) AS top10_pct, "
         "round(100 * avg((prank <= 50)::INT), 1) AS top50_pct, round(100 * avg((prank <= 100)::INT), 1) AS "
         "top100_pct, round(100 * avg((prank <= 500)::INT), 1) AS top500_pct, "
         "quantile_cont(ref_price, [0.25, 0.5, 0.75]) AS ref_price_q, "
         "round(100 * avg(is_new_product::INT), 2) AS new_product_pct, "
         "round(100 * avg((price_eur < 0.95 * ref_price)::INT), 1) AS discounted_pct "
         "FROM pu JOIN pop USING (product_id) GROUP BY 1 ORDER BY 1")
    show(c, "organic purchases: category shares (%)",
         "SELECT category, round(100 * count(*) FILTER (cls = 'cold') / sum(count(*) FILTER (cls = 'cold')) OVER (), "
         "2) AS cold_pct, round(100 * count(*) FILTER (cls = 'known') / sum(count(*) FILTER (cls = 'known')) "
         "OVER (), 2) AS known_pct FROM pu GROUP BY 1 ORDER BY 2 DESC")
    show(c, "organic views: category shares (%)",
         "SELECT category, round(100 * count(*) FILTER (cls = 'cold') / sum(count(*) FILTER (cls = 'cold')) OVER (), "
         "2) AS cold_pct, round(100 * count(*) FILTER (cls = 'known') / sum(count(*) FILTER (cls = 'known')) "
         "OVER (), 2) AS known_pct FROM ev WHERE explore AND event_type = 'view' GROUP BY 1 ORDER BY 2 DESC")
    show(c, "new products: share of organic events after 10:00 UTC, by class",
         "SELECT cls, event_type, count(*) AS n, round(100 * avg(is_new_product::INT), 2) AS on_new_products_pct "
         "FROM ev WHERE explore AND hour(ts) >= 10 GROUP BY 1, 2 ORDER BY 2, 1")
    show(c, "rank correlation check: top-20 products by cold purchases, with their rank among known users",
         "SELECT product_id, any_value(category) AS category, count(*) FILTER (cls = 'cold') AS cold_n, "
         "rank() OVER (ORDER BY count(*) FILTER (cls = 'cold') DESC) AS cold_rank, "
         "rank() OVER (ORDER BY count(*) FILTER (cls = 'known') DESC) AS known_rank FROM pu GROUP BY 1 "
         "ORDER BY cold_n DESC LIMIT 20")

    # ---- Q3: the purchase in session s vs the user's live events in sessions before s
    c.execute("""CREATE TABLE pk AS
        SELECT p.user_id, p.cls, p.session_id, p.product_id, p.category, p.subcategory, p.brand,
          count(e.ts) AS k,
          count(e.ts) FILTER (e.product_id = p.product_id) > 0 AS seen_product,
          count(e.ts) FILTER (e.product_id = p.product_id AND e.event_type = 'add_to_cart') > 0 AS carted_product,
          count(e.ts) FILTER (e.product_id = p.product_id AND e.event_type = 'purchase') > 0 AS bought_product,
          count(e.ts) FILTER (e.subcategory = p.subcategory) > 0 AS seen_sub,
          count(e.ts) FILTER (e.brand = p.brand) > 0 AS seen_brand,
          count(e.ts) FILTER (e.category = p.category) > 0 AS seen_cat,
          coalesce(count(e.ts) FILTER (e.category = p.category) / nullif(count(e.ts), 0), 0) AS cat_share,
          count(DISTINCT e.subcategory) AS n_sub, count(DISTINCT e.brand) AS n_brand,
          count(DISTINCT e.category) AS n_cat
        FROM pu p LEFT JOIN ev e ON e.user_id = p.user_id AND e.s_start < p.s_start AND e.explore
        GROUP BY ALL""")
    n_sub, n_brand, n_cat = c.execute("SELECT count(DISTINCT subcategory), count(DISTINCT brand), "
                                      "count(DISTINCT category) FROM cat").fetchall()[0]
    print(f"\ncatalogue: {n_cat} categories, {n_sub} subcategories, {n_brand} brands")
    kb = ("CASE WHEN k = 0 THEN 'k=0' WHEN k < 3 THEN 'k=1-2' WHEN k < 6 THEN 'k=3-5' WHEN k < 11 THEN 'k=6-10' "
          "WHEN k < 21 THEN 'k=11-20' WHEN k < 51 THEN 'k=21-50' ELSE 'k=51+' END")
    for cls in ("cold", "known"):
        show(c, f"{cls} users: organic purchase vs own live events in earlier sessions (k = number of such events); "
                f"'x_chance' = share expected if subcategories/brands were picked at random among those seen",
             f"SELECT {kb} AS k, count(*) AS purchases, round(100 * avg(seen_product::INT), 1) AS seen_product_pct, "
             f"round(100 * avg(carted_product::INT), 1) AS carted_pct, round(100 * avg(bought_product::INT), 1) AS "
             f"rebuy_pct, round(100 * avg(seen_sub::INT), 1) AS same_sub_pct, round(100 * avg(n_sub) / {n_sub}, 1) "
             f"AS sub_chance, round(100 * avg(seen_brand::INT), 1) AS same_brand_pct, "
             f"round(100 * avg(n_brand) / {n_brand}, 1) AS brand_chance, round(100 * avg(seen_cat::INT), 1) AS "
             f"same_cat_pct, round(100 * avg(n_cat) / {n_cat}, 1) AS cat_chance, round(100 * avg(cat_share), 1) AS "
             f"mean_cat_share_pct FROM pk WHERE cls = '{cls}' GROUP BY 1 ORDER BY min(k)")
    show(c, "category focus of a user's live events (users with 20+ events): share of events in the top category",
         "SELECT cls, count(*) AS users, quantile_cont(top_share, [0.25, 0.5, 0.75]) AS top_category_share_q FROM "
         "(SELECT user_id, cls, max(n) / sum(n) AS top_share FROM (SELECT user_id, cls, category, count(*) AS n "
         "FROM ev WHERE explore GROUP BY ALL) GROUP BY 1, 2 HAVING sum(n) >= 20) GROUP BY 1 ORDER BY 1")
    # ---- signals for the next organic session: cart contents and re-views
    c.execute("""CREATE TABLE open_cart AS
        SELECT a.user_id, a.cls, a.product_id, a.s_start,
          count(p.ts) FILTER (p.event_type = 'purchase' AND p.s_start > a.s_start) > 0 AS bought_later,
          count(p.ts) FILTER (p.event_type = 'view' AND p.s_start > a.s_start) > 0 AS viewed_later
        FROM ev a LEFT JOIN ev p ON p.user_id = a.user_id AND p.product_id = a.product_id AND p.explore
        WHERE a.explore AND a.event_type = 'add_to_cart' AND hour(a.ts) < 15
          AND NOT EXISTS (SELECT 1 FROM ev q WHERE q.session_id = a.session_id AND q.product_id = a.product_id
                          AND q.event_type = 'purchase')
        GROUP BY ALL""")
    show(c, "carts left open (carted, not bought in that session, before 15:00): bought in a later session?",
         "SELECT cls, count(*) AS open_carts, round(100 * avg(bought_later::INT), 2) AS bought_later_pct, "
         "round(100 * avg(viewed_later::INT), 2) AS viewed_later_pct FROM open_cart GROUP BY 1 ORDER BY 1")
    c.execute("""CREATE TABLE viewed_only AS
        SELECT a.user_id, a.cls, a.product_id, min(a.s_start) AS s_start FROM ev a
        WHERE a.explore AND a.event_type = 'view' AND hour(a.ts) < 15
          AND NOT EXISTS (SELECT 1 FROM ev q WHERE q.session_id = a.session_id AND q.product_id = a.product_id
                          AND q.event_type <> 'view') GROUP BY ALL""")
    show(c, "for comparison, products only viewed in a session (before 15:00): bought in a later session?",
         "SELECT v.cls, count(*) AS viewed_products, round(100 * avg((p.n > 0)::INT), 2) AS bought_later_pct FROM "
         "viewed_only v LEFT JOIN LATERAL (SELECT count(*) AS n FROM ev p WHERE p.user_id = v.user_id AND "
         "p.product_id = v.product_id AND p.event_type = 'purchase' AND p.s_start > v.s_start AND p.explore) p "
         "ON TRUE GROUP BY 1 ORDER BY 1")
    _ = LIVE


if __name__ == "__main__":
    main()
