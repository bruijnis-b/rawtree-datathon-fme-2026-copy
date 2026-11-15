"""Q2-Q4 on our carousels: which shown products do cold (is_new_user) and known users click and buy?

One row per shown product (10 per answered request) with: slot, popularity, match with the request's recent_views,
match with the user's own organic events before the request (live events, plus the 60-day history for known
users), cart state and activity counts. Prints per-impression click / purchase rates per bucket, new vs known,
and two logistic regressions (click per impression, purchase per click) with is_new interactions.

Exploration split only. Popularity is the organic purchase count over the whole exploration split (not strictly
before each request): fine for a description, not a feature definition.

Run: python -m training.analysis.cold_items
"""
from __future__ import annotations

import os

import numpy as np

from training.analysis.cold_common import HIST, LIVE, connect, show, wilson

# COLD_SPLIT=holdout re-runs everything on the live hold-out (held-out users + last 2 h) as a confirmation
SPLIT = "NOT r.explore" if os.environ.get("COLD_SPLIT") == "holdout" else "r.explore"


def build(c):
    c.execute(f"""CREATE TABLE f AS SELECT r.request_id, r.user_id, r.ts, r.is_new_user AS nw, r.page, r.device,
        f.shown, f.clicked, f.purchased, f.served_by, len(r.recent_views) AS nrv,
        list_transform(r.recent_views, lambda x: x.product_id) AS rvp
        FROM rq r JOIN fb f USING (request_id) WHERE len(f.shown) = 10 AND {SPLIT}""")
    c.execute("""CREATE TABLE pop AS SELECT product_id, sum((event_type = 'purchase')::INT) AS np,
        rank() OVER (ORDER BY sum((event_type = 'purchase')::INT) DESC, product_id) AS prank
        FROM ev WHERE explore GROUP BY 1""")
    # every organic event of the request's user before the request: live (all users) + history (known users)
    c.execute(f"""CREATE TABLE prior AS
        SELECT f.request_id, e.product_id, e.event_type, e.ts, TRUE AS live FROM f JOIN ev0 e
          ON e.user_id = f.user_id AND e.ts < f.ts
        UNION ALL
        SELECT f.request_id, h.product_id, h.event_type, h.ts, FALSE FROM f
          JOIN read_parquet('{HIST}/history_events/*.parquet') h ON h.user_id = f.user_id""")
    c.execute("""CREATE TABLE prior_p AS SELECT request_id, product_id, count(*) AS n,
        sum((event_type = 'view')::INT) AS nv, sum((event_type = 'add_to_cart')::INT) AS nc,
        sum((event_type = 'purchase')::INT) AS np, max(ts) FILTER (event_type = 'add_to_cart') AS last_cart,
        max(ts) FILTER (event_type = 'purchase') AS last_pur FROM prior GROUP BY 1, 2""")
    c.execute("""CREATE TABLE prior_u AS SELECT request_id, count(*) AS n_all, sum(live::INT) AS n_live,
        sum((live AND event_type = 'purchase')::INT) AS n_live_pur,
        sum((live AND event_type = 'add_to_cart')::INT) AS n_live_cart,
        epoch(max(f.ts) - max(prior.ts)) / 60 AS min_since_last, epoch(max(f.ts) - min(prior.ts) FILTER (live)) / 60
        AS min_since_first FROM prior JOIN f USING (request_id) GROUP BY 1""")
    for key in ("category", "subcategory", "brand"):
        c.execute(f"""CREATE TABLE prior_{key} AS SELECT request_id, {key}, count(*) AS n,
            sum((event_type = 'purchase')::INT) AS np FROM prior JOIN cat USING (product_id) GROUP BY 1, 2""")
    c.execute("""CREATE TABLE rvc AS SELECT request_id, list(DISTINCT p.category) AS cats,
        list(DISTINCT p.subcategory) AS subs, list(DISTINCT p.brand) AS brands,
        count(*) - count(DISTINCT t.pid) AS rv_repeats, count(DISTINCT p.subcategory) AS rv_nsub
        FROM f, unnest(f.rvp) AS t(pid) JOIN cat p ON p.product_id = t.pid GROUP BY 1""")
    c.execute(f"""CREATE TABLE price_now AS SELECT f.request_id, u.product_id, arg_max(u.price_eur, u.ts) AS price
        FROM f JOIN read_parquet('{LIVE}/catalog_updates.parquet') u ON u.ts <= f.ts AND u.change = 'price_change'
        WHERE list_contains(f.shown, u.product_id) GROUP BY 1, 2""")
    c.execute("""CREATE TABLE it AS
        SELECT f.request_id, f.user_id, f.nw::INT AS nw, f.page, f.device, f.nrv, f.served_by, s.slot, s.pid,
          coalesce((s.pid = f.clicked)::INT, 0) AS ck, coalesce((s.pid = f.purchased)::INT, 0) AS pu,
          p.category, p.subcategory, p.brand, p.ref_price, coalesce(p.is_new_product, FALSE)::INT AS newp,
          coalesce(pop.prank, 9999) AS prank, coalesce(pop.np, 0) AS pop_np,
          list_contains(f.rvp, s.pid)::INT AS in_rv,
          coalesce(list_contains(rvc.subs, p.subcategory), FALSE)::INT AS rv_sub,
          coalesce(list_contains(rvc.cats, p.category), FALSE)::INT AS rv_cat,
          coalesce(list_contains(rvc.brands, p.brand), FALSE)::INT AS rv_brand,
          coalesce(rvc.rv_repeats, 0) AS rv_repeats, coalesce(rvc.rv_nsub, 0) AS rv_nsub,
          coalesce(pp.nv, 0) AS o_view, coalesce(pp.nc, 0) AS o_cart, coalesce(pp.np, 0) AS o_pur,
          (pp.last_cart IS NOT NULL AND (pp.last_pur IS NULL OR pp.last_pur < pp.last_cart - INTERVAL 1 SECOND))::INT
            AS in_cart,
          coalesce(pu.n_all, 0) AS n_all, coalesce(pu.n_live, 0) AS n_live, coalesce(pu.n_live_pur, 0) AS n_live_pur,
          coalesce(pu.n_live_cart, 0) AS n_live_cart, pu.min_since_last, pu.min_since_first,
          coalesce(pc.n, 0) / greatest(coalesce(pu.n_all, 0), 1) AS share_cat,
          coalesce(ps.n, 0) AS o_sub, coalesce(ps.np, 0) AS o_sub_pur,
          coalesce(pb.n, 0) AS o_brand, coalesce(pb.np, 0) AS o_brand_pur,
          coalesce(pn.price / p.ref_price, 1.0) AS price_ratio
        FROM f, unnest(f.shown) WITH ORDINALITY AS s(pid, slot)
        LEFT JOIN cat p ON p.product_id = s.pid LEFT JOIN pop ON pop.product_id = s.pid
        LEFT JOIN rvc ON rvc.request_id = f.request_id
        LEFT JOIN prior_p pp ON pp.request_id = f.request_id AND pp.product_id = s.pid
        LEFT JOIN prior_u pu ON pu.request_id = f.request_id
        LEFT JOIN prior_category pc ON pc.request_id = f.request_id AND pc.category = p.category
        LEFT JOIN prior_subcategory ps ON ps.request_id = f.request_id AND ps.subcategory = p.subcategory
        LEFT JOIN prior_brand pb ON pb.request_id = f.request_id AND pb.brand = p.brand
        LEFT JOIN price_now pn ON pn.request_id = f.request_id AND pn.product_id = s.pid""")


def tab(c, title: str, key: str, where: str = "TRUE"):
    """Per-impression click and purchase rates (per 1,000 impressions) by bucket, new vs known."""
    rows = c.execute(f"SELECT {key} AS k, nw, count(*), sum(ck), sum(pu) FROM it WHERE {where} GROUP BY 1, 2 "
                     f"ORDER BY 1, 2").fetchall()
    print(f"\n## {title}   (per 1,000 impressions, 95 % interval)")
    for k, nw, n, ck, pu in rows:
        cl, ch = wilson(ck, n)
        pl, ph = wilson(pu, n)
        print(f"{str(k):>22} {'new  ' if nw else 'known'} n={n:7d}  click {1e3 * ck / n:6.2f} [{1e3 * cl:5.2f},"
              f"{1e3 * ch:6.2f}]  purchase {1e3 * pu / n:5.2f} [{1e3 * pl:5.2f},{1e3 * ph:5.2f}]  ({ck}/{pu})")


def logit(X: np.ndarray, y: np.ndarray, names: list[str], title: str, l2: float = 1e-3):
    """Logistic regression by Newton's method; prints coefficient, standard error, odds ratio."""
    X = np.column_stack([np.ones(len(y)), X])
    w = np.zeros(X.shape[1])
    for _ in range(40):
        p = 1 / (1 + np.exp(-X @ w))
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w))
        step = np.linalg.solve(H, X.T @ (y - p) - l2 * w)
        w += step
        if np.abs(step).max() < 1e-8:
            break
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    print(f"\n## logistic regression: {title}  (n={len(y)}, positives={int(y.sum())})")
    print(f"{'feature':>24}   coef    se     z   odds-ratio")
    for n, b, s in zip(["const"] + names, w, se):
        print(f"{n:>24} {b:6.2f} {s:5.2f} {b / s:6.1f}  {np.exp(b):6.2f}")


def regressions(c):
    cols = ["nw", "ck", "pu", "slot", "page", "nrv", "pop_np", "in_rv", "rv_sub", "rv_cat", "rv_brand", "o_view",
            "o_cart", "o_pur", "in_cart", "o_sub", "o_brand", "share_cat", "n_live", "n_live_pur", "price_ratio",
            "ref_price", "newp", "category"]
    d = c.execute(f"SELECT {', '.join(cols)} FROM it").fetchnumpy()
    nw = d["nw"].astype(float)
    base = {
        "log_slot": np.log(d["slot"].astype(float)),
        "page_home": (d["page"] == "home").astype(float),
        "page_category": (d["page"] == "category").astype(float),
        "log_pop": np.log1p(d["pop_np"].astype(float)),
        "log_ref_price": np.log(np.maximum(d["ref_price"].astype(float), 1)),
        "discount(1-ratio)": 1 - np.asarray(d["price_ratio"], float),
        "new_product": d["newp"].astype(float),
        "books_media": (d["category"] == "Books & Media").astype(float),
        "rv: same product": d["in_rv"].astype(float),
        "rv: same subcategory": d["rv_sub"].astype(float),
        "rv: same category": d["rv_cat"].astype(float),
        "rv: same brand": d["rv_brand"].astype(float),
        "own: viewed product": (d["o_view"] > 0).astype(float),
        "own: product in cart": d["in_cart"].astype(float),
        "own: bought product": (d["o_pur"] > 0).astype(float),
        "own: log1p sub events": np.log1p(d["o_sub"].astype(float)),
        "own: log1p brand events": np.log1p(d["o_brand"].astype(float)),
        "own: category share": np.asarray(d["share_cat"], float),
        "user: log1p live events": np.log1p(d["n_live"].astype(float)),
        "user: log1p live purch": np.log1p(d["n_live_pur"].astype(float)),
    }
    inter = ["log_slot", "page_home", "log_pop", "log_ref_price", "discount(1-ratio)", "books_media",
             "rv: same product", "rv: same subcategory", "rv: same brand", "own: viewed product",
             "own: log1p sub events", "own: log1p brand events", "own: category share", "user: log1p live events",
             "user: log1p live purch"]
    names = list(base) + ["is_new"] + [f"is_new x {k}" for k in inter]
    X = np.column_stack(list(base.values()) + [nw] + [nw * base[k] for k in inter])
    ck = d["ck"].astype(float)
    logit(X, ck, names, "click per impression")
    m = ck == 1
    logit(X[m], d["pu"].astype(float)[m], names, "purchase per click", l2=1.0)
    logit(X, d["pu"].astype(float), names, "purchase per impression", l2=1.0)


def main():
    c = connect()
    build(c)
    show(c, "impressions", "SELECT nw, count(*) AS impressions, count(DISTINCT request_id) AS carousels, sum(ck) "
                           "AS clicks, sum(pu) AS purchases FROM it GROUP BY 1 ORDER BY 1")
    show(c, "what we showed (share of impressions)",
         "SELECT served_by, nw, round(avg((prank <= 50)::INT), 3) AS top50, round(avg(in_rv), 3) AS in_rv, "
         "round(avg(rv_sub), 3) AS rv_sub, round(avg(rv_brand), 3) AS rv_brand, round(avg((o_view > 0)::INT), 3) AS "
         "own_viewed, round(avg(in_cart), 3) AS in_cart, round(avg(newp), 4) AS new_product FROM it "
         "GROUP BY ALL ORDER BY 1, 2")
    tab(c, "slot", "slot")
    tab(c, "organic popularity rank of the shown product",
        "CASE WHEN prank <= 10 THEN 'a top 10' WHEN prank <= 50 THEN 'b 11-50' WHEN prank <= 100 THEN 'c 51-100' "
        "WHEN prank <= 500 THEN 'd 101-500' ELSE 'e 500+' END")
    tab(c, "category", "category")
    tab(c, "reference price", "CASE WHEN ref_price < 15 THEN 'a <15' WHEN ref_price < 40 THEN 'b 15-40' "
                              "WHEN ref_price < 100 THEN 'c 40-100' ELSE 'd 100+' END")
    tab(c, "discount now (context only)", "CASE WHEN price_ratio < 0.95 THEN 'discounted' WHEN price_ratio > 1.05 "
                                          "THEN 'raised' ELSE 'at reference' END")
    tab(c, "practice-round new product", "newp")
    tab(c, "shown product is one of the recent_views", "in_rv", "nrv > 0")
    tab(c, "same subcategory as a recent view (not the product itself)", "rv_sub", "nrv > 0 AND in_rv = 0")
    tab(c, "same brand as a recent view (not the product itself)", "rv_brand", "nrv > 0 AND in_rv = 0")
    tab(c, "same category, other subcategory", "rv_cat", "nrv > 0 AND rv_sub = 0")
    tab(c, "user viewed the product organically before (not in recent_views)", "(o_view > 0)::INT", "in_rv = 0")
    tab(c, "product is in the user's cart (carted, not bought since)", "in_cart")
    tab(c, "user bought the product before", "(o_pur > 0)::INT")
    tab(c, "user's organic events in the product's subcategory",
        "CASE WHEN o_sub = 0 THEN 'a 0' WHEN o_sub < 3 THEN 'b 1-2' WHEN o_sub < 10 THEN 'c 3-9' ELSE 'd 10+' END",
        "n_all > 0")
    tab(c, "user's organic events on the product's brand",
        "CASE WHEN o_brand = 0 THEN 'a 0' WHEN o_brand < 3 THEN 'b 1-2' WHEN o_brand < 10 THEN 'c 3-9' ELSE 'd 10+' "
        "END", "n_all > 0")
    tab(c, "share of the user's organic events in the product's category",
        "CASE WHEN share_cat = 0 THEN 'a 0' WHEN share_cat < 0.1 THEN 'b <10%' WHEN share_cat < 0.3 THEN 'c 10-30%' "
        "ELSE 'd 30%+' END", "n_all >= 5")
    # Q3: how fast does a new user's own live history become useful?
    kb = ("CASE WHEN n_live = 0 THEN 'k=0' WHEN n_live < 3 THEN 'k=1-2' WHEN n_live < 6 THEN 'k=3-5' "
          "WHEN n_live < 11 THEN 'k=6-10' WHEN n_live < 21 THEN 'k=11-20' ELSE 'k=21+' END")
    show(c, "new users: carousels by number of own live events before the request (k)",
         f"SELECT {kb} AS k, count(DISTINCT request_id) AS carousels, round(100.0 * sum(ck) * 10 / count(*), 2) AS "
         f"click_pct, round(100.0 * sum(pu) * 10 / count(*), 2) AS purchase_pct FROM it WHERE nw = 1 GROUP BY 1 "
         f"ORDER BY min(n_live)")
    for name, cond in (("own subcategory", "o_sub > 0"), ("own brand", "o_brand > 0"),
                       ("own category share >= 20 %", "share_cat >= 0.2")):
        show(c, f"new users: click / purchase lift of '{name}' match by k (rate with match / rate without)",
             f"SELECT {kb} AS k, round(avg(({cond})::INT), 3) AS share_matching, sum(ck) FILTER ({cond}) AS "
             f"clicks_match, round((sum(ck) FILTER ({cond}) / count(*) FILTER ({cond})) / (sum(ck) FILTER (NOT "
             f"({cond})) / count(*) FILTER (NOT ({cond}))), 2) AS click_lift, sum(pu) FILTER ({cond}) AS "
             f"purch_match, round((sum(pu) FILTER ({cond}) / count(*) FILTER ({cond})) / (sum(pu) FILTER (NOT "
             f"({cond})) / count(*) FILTER (NOT ({cond}))), 2) AS purchase_lift FROM it WHERE nw = 1 AND n_live > 0 "
             f"GROUP BY 1 ORDER BY min(n_live)")
    # Q4: user-level signals (per carousel)
    c.execute("""CREATE TABLE car AS SELECT request_id, any_value(nw) AS nw, max(ck) AS ck, max(pu) AS pu,
        any_value(n_live) AS n_live, any_value(n_live_pur) AS n_live_pur, any_value(n_live_cart) AS n_live_cart,
        any_value(min_since_last) AS min_since_last, any_value(min_since_first) AS min_since_first,
        any_value(nrv) AS nrv, any_value(rv_repeats) AS rv_repeats, any_value(rv_nsub) AS rv_nsub,
        any_value(page) AS page FROM it GROUP BY 1""")

    def utab(title, key, where="TRUE"):
        rows = c.execute(f"SELECT {key} AS k, nw, count(*), sum(ck), sum(pu) FROM car WHERE {where} GROUP BY 1, 2 "
                         f"ORDER BY 1, 2").fetchall()
        print(f"\n## per carousel: {title}")
        for k, nw, n, ck, pu in rows:
            cl, ch = wilson(ck, n)
            pl, ph = wilson(pu, n)
            print(f"{str(k):>16} {'new  ' if nw else 'known'} n={n:6d}  click {100 * ck / n:5.2f} % [{100 * cl:4.2f},"
                  f"{100 * ch:5.2f}]  purchase {100 * pu / n:5.2f} % [{100 * pl:4.2f},{100 * ph:5.2f}]")

    utab("own live events before the request", "CASE WHEN n_live = 0 THEN 'a 0' WHEN n_live < 6 THEN 'b 1-5' "
                                               "WHEN n_live < 21 THEN 'c 6-20' ELSE 'd 21+' END")
    utab("own live purchases before the request", "CASE WHEN n_live_pur = 0 THEN 'a 0' WHEN n_live_pur < 3 THEN "
                                                  "'b 1-2' ELSE 'c 3+' END", "n_live > 0")
    utab("own live add-to-carts before the request", "CASE WHEN n_live_cart = 0 THEN 'a 0' WHEN n_live_cart < 3 "
                                                     "THEN 'b 1-2' ELSE 'c 3+' END", "n_live > 0")
    utab("minutes since the user's last organic event", "CASE WHEN min_since_last < 10 THEN 'a <10' WHEN "
                                                        "min_since_last < 60 THEN 'b 10-60' ELSE 'c 60+' END",
         "n_live > 0")
    utab("minutes since the user's first live event", "CASE WHEN min_since_first < 60 THEN 'a <60' WHEN "
                                                      "min_since_first < 240 THEN 'b 60-240' ELSE 'c 240+' END",
         "n_live > 0")
    utab("distinct subcategories among recent_views (2+ views)", "least(rv_nsub, 3)", "nrv >= 2")
    utab("a product repeated in recent_views (2+ views)", "(rv_repeats > 0)::INT", "nrv >= 2")
    regressions(c)


if __name__ == "__main__":
    main()
