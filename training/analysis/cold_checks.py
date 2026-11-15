"""Follow-up checks for the proposals (carousels, exploration split unless COLD_SPLIT=holdout).

1. Is the new-user effect a property of the user or of what we showed? -> fixed fallback list only.
2. How much of the own-history signal survives when the history is cut at the start of the hour (as in
   training/embed/live.py) instead of at the request time?
3. How many slots do we spend on products the user already bought, and what could cart / recent-view items earn?

Run: python -m training.analysis.cold_checks
"""
from __future__ import annotations

from training.analysis import cold_items
from training.analysis.cold_common import connect, show


def main():
    c = connect()
    cold_items.build(c)
    # 1 ---------------------------------------------------------------
    show(c, "fallback carousels only (same popular list for everyone): rate per carousel by own live purchases",
         "SELECT nw, CASE WHEN n_live_pur = 0 THEN 'a 0' WHEN n_live_pur < 3 THEN 'b 1-2' ELSE 'c 3+' END AS "
         "live_purchases, count(DISTINCT request_id) AS carousels, sum(ck) AS clicks, sum(pu) AS purchases, "
         "round(1000.0 * sum(ck) / count(*), 2) AS click_per_1000_impr, round(1000.0 * sum(pu) / count(*), 2) AS "
         "purchase_per_1000_impr FROM it WHERE served_by = 'fallback' GROUP BY 1, 2 ORDER BY 1, 2")
    show(c, "fallback carousels only: purchases per click by class",
         "SELECT nw, sum(ck) AS clicks, sum(pu) AS purchases, round(sum(pu) / sum(ck), 3) AS cvr FROM it "
         "WHERE served_by = 'fallback' GROUP BY 1 ORDER BY 1")
    show(c, "fallback carousels only, impressions where the user has NO own event in the product's category "
            "(no personal match): new vs known",
         "SELECT nw, count(*) AS impressions, sum(ck) AS clicks, sum(pu) AS purchases, round(1000.0 * sum(ck) / "
         "count(*), 2) AS click_per_1000, round(1000.0 * sum(pu) / count(*), 2) AS purchase_per_1000 FROM it "
         "WHERE served_by = 'fallback' AND share_cat = 0 GROUP BY 1 ORDER BY 1")
    show(c, "all carousels, by own-category share bucket: new/known ratio left after matching on affinity",
         "SELECT CASE WHEN share_cat = 0 THEN 'a 0' WHEN share_cat < 0.1 THEN 'b <10%' WHEN share_cat < 0.3 THEN "
         "'c 10-30%' ELSE 'd 30%+' END AS own_cat_share, round(1000.0 * sum(pu) FILTER (nw = 1) / count(*) FILTER "
         "(nw = 1), 2) AS new_purch_per_1000, round(1000.0 * sum(pu) FILTER (nw = 0) / count(*) FILTER (nw = 0), 2) "
         "AS known_purch_per_1000 FROM it WHERE prank <= 50 GROUP BY 1 ORDER BY 1")
    # 2 ---------------------------------------------------------------
    c.execute("""CREATE TABLE cut AS SELECT f.request_id, f.nw,
        count(e.ts) AS n_now, count(e.ts) FILTER (e.ts < date_trunc('hour', f.ts)) AS n_hour
        FROM f LEFT JOIN ev0 e ON e.user_id = f.user_id AND e.ts < f.ts GROUP BY 1, 2""")
    show(c, "live events available per request: up to the request vs up to the start of the hour",
         "SELECT nw, round(avg(n_now), 1) AS mean_now, round(avg(n_hour), 1) AS mean_hour_cut, "
         "round(100 * avg((n_now > 0)::INT), 1) AS any_now_pct, round(100 * avg((n_hour > 0)::INT), 1) AS "
         "any_hour_cut_pct, round(100 * avg((n_now >= 6)::INT), 1) AS six_plus_now_pct, "
         "round(100 * avg((n_hour >= 6)::INT), 1) AS six_plus_hour_cut_pct FROM cut GROUP BY 1 ORDER BY 1")
    c.execute("""CREATE TABLE cart_h AS SELECT f.request_id, e.product_id,
        max(e.ts) FILTER (e.event_type = 'add_to_cart') AS lc, max(e.ts) FILTER (e.event_type = 'purchase') AS lp
        FROM f JOIN ev0 e ON e.user_id = f.user_id AND e.ts < date_trunc('hour', f.ts) GROUP BY 1, 2""")
    show(c, "in-cart impressions: at request time (for known users this includes carts from the 60-day history) vs "
            "live carts seen with the hour cut; compare the new-user row only",
         "SELECT it.nw, sum(it.in_cart) AS in_cart_now, sum((h.lc IS NOT NULL AND (h.lp IS NULL OR h.lp < h.lc - "
         "INTERVAL 1 SECOND))::INT) AS in_cart_hour_cut FROM it LEFT JOIN cart_h h ON h.request_id = it.request_id "
         "AND h.product_id = it.pid GROUP BY 1 ORDER BY 1")
    # 3 ---------------------------------------------------------------
    show(c, "slots spent per carousel (mean number of the 10 shown) by our own policy",
         "SELECT nw, round(10 * avg((o_pur > 0)::INT), 2) AS already_bought, round(10 * avg(in_cart), 2) AS in_cart, "
         "round(10 * avg(in_rv), 2) AS in_recent_views FROM it WHERE served_by = 'team' GROUP BY 1 ORDER BY 1")
    c.execute("""CREATE TABLE avail AS SELECT f.request_id, f.nw,
        count(DISTINCT e.product_id) FILTER (e.event_type = 'add_to_cart') AS carted,
        count(DISTINCT e.product_id) FILTER (e.event_type = 'purchase') AS bought
        FROM f LEFT JOIN ev0 e ON e.user_id = f.user_id AND e.ts < f.ts GROUP BY 1, 2""")
    show(c, "available per request from live events: distinct carted and bought products",
         "SELECT nw, round(avg(carted), 2) AS carted_products, round(avg(bought), 2) AS bought_products, "
         "round(100 * avg((carted > bought)::INT), 1) AS has_open_cart_pct FROM avail GROUP BY 1 ORDER BY 1")
    show(c, "in-cart impressions by slot group: click and purchase per 1,000",
         "SELECT nw, CASE WHEN slot <= 3 THEN 'slot 1-3' ELSE 'slot 4-10' END AS slots, count(*) AS n, "
         "round(1000.0 * sum(ck) / count(*), 1) AS click, round(1000.0 * sum(pu) / count(*), 1) AS purchase FROM it "
         "WHERE in_cart = 1 GROUP BY 1, 2 ORDER BY 1, 2")

    # 4 ---------------------------------------------------------------
    show(c, "new-user requests (all requests of the exploration split, also unanswered ones) by hour: own live "
            "events before the request",
         "SELECT hour(r.ts) AS hour_utc, count(*) AS requests, round(100 * avg((n = 0)::INT), 1) AS k0_pct, "
         "round(100 * avg((n BETWEEN 1 AND 5)::INT), 1) AS k1_5_pct, round(100 * avg((n >= 6)::INT), 1) AS "
         "k6plus_pct, median(n) AS median_k, round(100 * avg((len(r.recent_views) = 0)::INT), 1) AS no_recent_views_pct "
         "FROM (SELECT r.request_id, any_value(r.ts) AS ts, any_value(r.recent_views) AS recent_views, count(e.ts) "
         "AS n FROM rq r LEFT JOIN ev0 e ON e.user_id = r.user_id AND e.ts < r.ts WHERE r.explore AND r.is_new_user "
         "GROUP BY 1) r GROUP BY 1 ORDER BY 1")
    # 5 ---------------------------------------------------------------
    show(c, "are a request's recent_views in shop.events? (3,000 requests; same user and product within 5 s)",
         "SELECT count(*) AS recent_views, sum(hit) AS found_in_events FROM (SELECT EXISTS (SELECT 1 FROM ev0 e "
         "WHERE e.user_id = r.user_id AND e.product_id = v.product_id AND abs(epoch(e.ts - v.ts)) < 5)::INT AS hit "
         "FROM (SELECT * FROM rq0 ORDER BY request_id LIMIT 3000) r, unnest(r.recent_views) AS t(v))")


if __name__ == "__main__":
    main()
