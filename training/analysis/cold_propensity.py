"""Q1. Purchase propensity of cold vs known users: organic events (shop.events) and our carousels (feedback).

Exploration split only (see cold_common). Run: python -m training.analysis.cold_propensity
"""
from __future__ import annotations

import numpy as np

from training.analysis.cold_common import connect, rate, show


def carousels(c):
    """Table f: one row per answered request (10 shown) with the request context and outcome."""
    c.execute("""CREATE TABLE f AS SELECT r.*, f.shown, f.clicked, f.purchased, f.served_by,
        (f.clicked IS NOT NULL)::INT AS ck, (f.purchased IS NOT NULL)::INT AS pu, len(r.recent_views) AS nrv,
        row_number() OVER (PARTITION BY r.user_id ORDER BY r.ts) AS rq_no
        FROM rq r JOIN fb f USING (request_id) WHERE len(f.shown) = 10""")


def boot_ratio(c, col: str, n_boot: int = 2000) -> str:
    """new/known ratio of a per-carousel rate, 95 % interval from a bootstrap over users."""
    rows = c.execute(f"SELECT user_id, any_value(is_new_user)::INT, count(*), sum({col}) FROM f WHERE explore "
                     f"GROUP BY 1").fetchall()
    a = np.array([r[1:] for r in rows], dtype=float)
    rng = np.random.default_rng(0)
    new, old = a[a[:, 0] == 1], a[a[:, 0] == 0]

    def r(x, y):
        return (x[:, 2].sum() / x[:, 1].sum()) / (y[:, 2].sum() / y[:, 1].sum())

    bs = [r(new[rng.integers(0, len(new), len(new))], old[rng.integers(0, len(old), len(old))])
          for _ in range(n_boot)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return f"{r(new, old):.2f}x [{lo:.2f}, {hi:.2f}]"


def split(c, title: str, key: str, where: str = "TRUE"):
    rows = c.execute(f"SELECT {key} AS k, is_new_user, count(*), sum(ck), sum(pu) FROM f WHERE explore AND {where} "
                     f"GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    print(f"\n## carousels by {title}:  click rate | purchase rate | purchases per click")
    for k, nw, n, ck, pu in rows:
        print(f"{str(k):>10} {'new  ' if nw else 'known'} click {rate(ck, n)}  purchase {rate(pu, n)}  "
              f"cvr {pu / ck if ck else float('nan'):.2f}")


def main():
    c = connect()
    show(c, "user classes (all live users): in history x flagged is_new_user in a request",
         "SELECT in_hist, flagged, has_rq, count(*) AS users, sum(held::INT) AS held_out FROM users "
         "GROUP BY ALL ORDER BY ALL")
    show(c, "when users are first seen in the live stream (users per hour, UTC)",
         "SELECT hour(u_start) AS h, count(DISTINCT user_id) FILTER (cls = 'cold') AS cold, "
         "count(DISTINCT user_id) FILTER (cls = 'known') AS known FROM ev GROUP BY 1 ORDER BY 1")

    # ---- organic: sessions (a session's events share one timestamp to within ~50 ms, so the session is the unit)
    c.execute("""CREATE TABLE se AS SELECT session_id, any_value(user_id) AS user_id, any_value(cls) AS cls,
        any_value(sess_no) AS sess_no, min(ts) AS ts, any_value(u_start) AS u_start, count(*) AS n,
        sum((event_type = 'view')::INT) AS nv, sum((event_type = 'add_to_cart')::INT) AS nc,
        sum((event_type = 'purchase')::INT) AS np, any_value(device) AS device, any_value(region) AS region
        FROM ev WHERE explore GROUP BY 1""")
    show(c, "session length: events and seconds (all sessions)",
         "SELECT quantile_cont(n, [0.1, 0.5, 0.9]) AS events, quantile_cont(d, [0.5, 0.99]) AS seconds FROM "
         "(SELECT count(*) AS n, epoch(max(ts) - min(ts)) AS d FROM ev GROUP BY session_id)")
    print("\n## organic, per class")
    for cls, s, u, n, nv, nc, np_, s_c, s_p in c.execute(
            "SELECT cls, count(*), count(DISTINCT user_id), sum(n), sum(nv), sum(nc), sum(np), sum((nc > 0)::INT), "
            "sum((np > 0)::INT) FROM se GROUP BY 1 ORDER BY 1").fetchall():
        print(f"{cls:>5}: {u} users, {s / u:.2f} sessions/user, {n / s:.2f} events/session")
        print(f"       purchases per event    {rate(np_, n)}")
        print(f"       sessions with a cart   {rate(s_c, s)}")
        print(f"       sessions with purchase {rate(s_p, s)}")
        print(f"       purchases per add-to-cart {np_ / nc:.3f}")
    show(c, "organic: session purchase rate by the user's n-th live session (session phase)",
         "SELECT least(sess_no, 10) AS sess_no, round(100 * avg((np > 0)::INT) FILTER (cls = 'cold'), 2) AS cold_pct, "
         "count(*) FILTER (cls = 'cold') AS n_cold, round(100 * avg((np > 0)::INT) FILTER (cls = 'known'), 2) "
         "AS known_pct, count(*) FILTER (cls = 'known') AS n_known FROM se GROUP BY 1 ORDER BY 1")
    for key in ("device", "region"):
        show(c, f"organic: session purchase rate by {key}",
             f"SELECT {key}, round(100 * avg((np > 0)::INT) FILTER (cls = 'cold'), 2) AS cold_pct, "
             f"round(100 * avg((np > 0)::INT) FILTER (cls = 'known'), 2) AS known_pct, count(*) AS n FROM se "
             f"GROUP BY 1 ORDER BY n DESC LIMIT 8")
    show(c, "organic: known users by history size (events in 60 days)",
         "SELECT CASE WHEN h_events < 50 THEN 'a <50' WHEN h_events < 200 THEN 'b 50-199' ELSE 'c 200+' END AS hist, "
         "count(DISTINCT u.user_id) AS users, round(count(*) / count(DISTINCT u.user_id), 2) AS sess_per_user, "
         "round(100 * avg((np > 0)::INT), 2) AS purchase_pct FROM se JOIN users u USING (user_id) "
         "WHERE se.cls = 'known' GROUP BY 1 ORDER BY 1")
    c.execute("""CREATE TABLE carts AS SELECT a.cls, a.user_id, a.session_id, a.product_id, a.ts,
        count(p.ts) FILTER (p.session_id = a.session_id) > 0 AS same_sess, count(p.ts) > 0 AS ever
        FROM ev a LEFT JOIN ev p ON p.user_id = a.user_id AND p.product_id = a.product_id
             AND p.event_type = 'purchase' AND p.explore AND p.s_start >= a.s_start
        WHERE a.event_type = 'add_to_cart' AND a.explore GROUP BY ALL""")
    show(c, "organic: add-to-cart -> purchase of the same product (same session / same or a later session)",
         "SELECT cls, count(*) AS carts, round(100 * avg(same_sess::INT), 2) AS same_session_pct, "
         "round(100 * avg(ever::INT), 2) AS ever_pct FROM carts GROUP BY 1 ORDER BY 1")
    show(c, "organic: first purchase of a user (users first seen before 12:00 UTC; minutes and session number)",
         "SELECT cls, count(*) AS users, round(100 * avg((fp IS NOT NULL)::INT), 1) AS bought_pct, "
         "quantile_cont(epoch(fp - u_start) / 60, [0.25, 0.5, 0.75]) AS minutes_q, "
         "quantile_cont(fs, [0.25, 0.5, 0.75]) AS session_q FROM (SELECT user_id, any_value(cls) AS cls, "
         "any_value(u_start) AS u_start, min(ts) FILTER (np > 0) AS fp, min(sess_no) FILTER (np > 0) AS fs "
         "FROM se GROUP BY 1) WHERE hour(u_start) < 12 GROUP BY 1 ORDER BY 1")

    # ---- carousels
    carousels(c)
    print("\n## carousels (exploration split), is_new_user vs not")
    for nw, n, ck, pu in c.execute("SELECT is_new_user, count(*), sum(ck), sum(pu) FROM f WHERE explore "
                                   "GROUP BY 1 ORDER BY 1").fetchall():
        print(f"{'new  ' if nw else 'known'}: click {rate(ck, n)}  purchase {rate(pu, n)}  cvr {pu / ck:.3f}")
    print("ratio new/known (bootstrap over users): click", boot_ratio(c, "ck"), " purchase", boot_ratio(c, "pu"))
    split(c, "served_by", "served_by")
    split(c, "page", "page")
    split(c, "device", "device")
    split(c, "number of recent views", "least(nrv, 4)")
    split(c, "the user's n-th request", "least(rq_no, 4)")
    split(c, "hour (UTC)", "hour(ts)")


if __name__ == "__main__":
    main()
