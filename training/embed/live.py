"""Live practice stream (IVAN dataset rawtree_live) -> arrays aligned with a history Data, plus the live hold-out.

Products: the 5,000 history products keep their index; products added during the stream (`new_product`) are
appended. Users: history users keep their index; live-only users are appended. The history source for pooling is
history events + live events, sorted by (user, ts); a sample's history window ends at the start of its hour.

Hold-out (live_holdout=True): 20 % of live users (crc32(user_id:live) % 5 == 0), the last 2 hours of the snapshot for
everyone, and 60 of the practice-round products (removed from training like held-out history products).
"""
from __future__ import annotations

import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np

from training.embed import data as D
from training.export import features as F

HOUR_MS = 3_600_000
N_HELDOUT_NEW = 60


def _log(msg):
    print(f"[live {time.strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class Live:
    product_ids: np.ndarray  # all products: history order, then new ones
    prod: dict  # features for all products
    new_product: np.ndarray  # bool [P]
    heldout_products: np.ndarray  # bool [P] (60 of the new ones when hold-out is on)
    user_ids: np.ndarray
    new_user: np.ndarray  # bool [U]: flagged is_new_user in a request, or not in the history
    heldout_users: np.ndarray  # bool [U]
    h: dict  # combined history source (sorted by user, ts), held-out products/users removed
    e: dict  # live events
    f: dict  # live carousels (feedback joined with requests)
    t_end: int
    t_holdout: int  # events at or after this are held out (last 2 h)
    popularity: np.ndarray
    n_hist_products: int
    a: dict | None = None  # every event (history + all live, any user/product/time), sorted: inputs only (open cart)


def build(hist: D.Data, folder: Path, holdout: bool = True) -> Live:
    t0 = time.time()
    c = duckdb.connect()
    c.execute("SET TimeZone = 'UTC'")
    f = folder.as_posix()
    P0 = len(hist.product_ids)
    new = c.execute(f"SELECT product_id, any_value(category), any_value(subcategory), any_value(brand), "
                    f"any_value(price_eur), any_value(description) FROM read_parquet('{f}/catalog_updates.parquet') "
                    f"WHERE change = 'new_product' GROUP BY product_id ORDER BY product_id").fetchall()
    known = set(hist.product_ids.tolist())
    new = [r for r in new if r[0] not in known]
    pids = np.concatenate([hist.product_ids, np.array([r[0] for r in new], dtype=hist.product_ids.dtype)]
                          ).astype(str)
    v = hist.vocab
    prod = {k: np.concatenate([hist.prod[k], nv]) for k, nv in {
        "cat": F.lookup(v["cat"], [r[1] for r in new]), "sub": F.lookup(v["sub"], [r[2] for r in new]),
        "brand": F.lookup(v["brand"], [r[3] for r in new]),
        "price": F.price_features([r[4] for r in new], [r[2] for r in new], hist.sub_mean, hist.global_mean),
        "tokens": F.token_matrix([r[5] for r in new])}.items()}
    P = len(pids)
    is_new_p = np.zeros(P, bool)
    is_new_p[P0:] = True
    held_p = np.zeros(P, bool)
    if holdout and P > P0:
        rng = np.random.default_rng(77)
        order = np.lexsort((rng.random(P - P0), prod["sub"][P0:]))
        step = (P - P0) / N_HELDOUT_NEW
        held_p[P0 + order[(np.arange(N_HELDOUT_NEW) * step).astype(int)]] = True
    sorter = np.argsort(pids)
    spids = pids[sorter]

    def pidx(values):
        m = D._map_ids(spids, np.asarray(values, dtype=object))
        return np.where(m >= 0, sorter[m.clip(0)], -1)

    # reference price per product (catalogue price, or the new_product price), for the discount input
    ref_logp = np.full(P, np.nan)
    cat = c.execute(f"SELECT product_id, price_eur FROM read_parquet('{f}/catalog.parquet')").fetchall()
    ref_logp[pidx([r[0] for r in cat])] = np.log(np.maximum([r[1] for r in cat], 0.01))
    for r, i in zip(new, range(P0, P)):
        ref_logp[i] = np.log(max(r[4] or 0.01, 0.01))

    ev = c.execute(f"SELECT epoch_ms(ts) AS ts_ms, event_type, user_id, product_id, device, region, price_eur "
                   f"FROM read_parquet('{f}/events/*.parquet')").fetchnumpy()
    rq = c.execute(f"SELECT request_id, epoch_ms(ts) AS ts_ms, user_id, is_new_user, device, region, page, "
                   f"len(recent_views) AS nrv, "
                   + ", ".join(f"recent_views[len(recent_views) - {5 - i}].product_id AS rv{i}" for i in range(6))
                   + f" FROM read_parquet('{f}/requests/*.parquet')").fetchnumpy()
    fb = c.execute(f"SELECT r.request_id, epoch_ms(r.ts) AS ts_ms, "
                   + ", ".join(f"shown[{i + 1}] AS s{i}" for i in range(10))
                   + f", clicked, purchased FROM read_parquet('{f}/feedback/*.parquet') r "
                   f"WHERE len(shown) = 10").fetchnumpy()
    _log(f"read {len(ev['ts_ms'])} events, {len(rq['ts_ms'])} requests, {len(fb['ts_ms'])} carousels")

    # users
    live_users = np.unique(np.concatenate([ev["user_id"].astype(str), rq["user_id"].astype(str)]))
    extra = np.setdiff1d(live_users, hist.user_ids.astype(str))
    users = np.concatenate([hist.user_ids.astype(str), extra])
    U0 = len(hist.user_ids)
    usort = np.argsort(users)
    susers = users[usort]

    def uidx(values):
        m = D._map_ids(susers, np.asarray(values, dtype=str))
        return np.where(m >= 0, usort[m.clip(0)], -1)

    new_u = np.zeros(len(users), bool)
    new_u[U0:] = True
    flagged = rq["is_new_user"].astype(bool)
    new_u[uidx(rq["user_id"].astype(str)[flagged])] = True
    held_u = np.zeros(len(users), bool)
    if holdout:
        lu = uidx(live_users)
        held_u[lu] = np.array([zlib.crc32(f"{u}:live".encode()) % 5 == 0 for u in live_users])

    e_ts = ev["ts_ms"].astype(np.int64)
    t_end = int(e_ts.max())
    t_hold = t_end - 2 * HOUR_MS if holdout else t_end + 1
    e_user = uidx(ev["user_id"].astype(str))
    e_prod = pidx(ev["product_id"])
    e_type = np.array([F.EVENT_TYPES.get(t, 0) for t in ev["event_type"].astype(str)], dtype=np.int64)
    e_dev = F.lookup(v["device"], ev["device"].astype(str))
    e_reg = F.lookup(v["region"], ev["region"].astype(str))
    price = np.asarray(ev["price_eur"], dtype=np.float64)
    ok = (e_prod >= 0) & (e_user >= 0)
    o = np.lexsort((e_ts, e_user))
    o = o[ok[o]]
    e_user, e_ts, e_prod, e_type, e_dev, e_reg, price = (a[o] for a in (e_user, e_ts, e_prod, e_type, e_dev, e_reg,
                                                                        price))
    disc = np.nan_to_num(np.log(np.maximum(price, 0.01)) - ref_logp[e_prod], nan=0.0).clip(-1, 0.5)

    # combined history source: history events (held-out history products removed already) + live training events
    hk_live = ~held_p[e_prod] & ~held_u[e_user] & (e_ts < t_hold)
    hh = hist.h
    h_user = np.concatenate([hh["user"], e_user[hk_live]])
    h_ts = np.concatenate([hh["ts"], e_ts[hk_live]])
    h_prod = np.concatenate([hh["prod"], e_prod[hk_live]])
    h_type = np.concatenate([hh["type"], e_type[hk_live]])
    o2 = np.lexsort((h_ts, h_user))
    h = {"user": h_user[o2], "ts": h_ts[o2], "prod": h_prod[o2], "type": h_type[o2]}
    key = h["user"] * D.KEY + h["ts"]
    lo_user = np.searchsorted(key, np.arange(len(users) + 1) * D.KEY)
    # every event, for the open cart at a sample's time (a user's own past events are inputs, not labels)
    a_user = np.concatenate([hh["user"], e_user])
    a_ts = np.concatenate([hh["ts"], e_ts])
    o3 = np.lexsort((a_ts, a_user))
    a = {"user": a_user[o3], "ts": a_ts[o3], "prod": np.concatenate([hh["prod"], e_prod])[o3],
         "type": np.concatenate([hh["type"], e_type])[o3]}
    akey = a["user"] * D.KEY + a["ts"]
    a_lo = np.searchsorted(akey, np.arange(len(users) + 1) * D.KEY)

    n = len(e_ts)
    rec = np.full((n, F.MAX_RECENT), -1, dtype=np.int64)
    for k in range(1, F.MAX_RECENT + 1):
        prev = np.arange(n) - k
        pv = np.clip(prev, 0, None)
        valid = (prev >= 0) & (e_user[pv] == e_user) & (e_ts - e_ts[pv] <= 1_800_000)
        rec[:, F.MAX_RECENT - k] = np.where(valid, e_prod[pv], -1)
    rec[rec == e_prod[:, None]] = -1
    if D.COMPACT:
        rec = F.compact(rec)
    hour0 = e_ts // HOUR_MS * HOUR_MS
    e = {"user": e_user, "ts": e_ts, "prod": e_prod, "type": e_type, "device": e_dev, "region": e_reg,
         "hour": ((e_ts // HOUR_MS) % 24).astype(np.int64), "rv": rec, "disc": disc.astype(np.float32),
         "hist_end": np.searchsorted(key, e_user * D.KEY + hour0), "hist_lo": lo_user[e_user],
         "cart_end": np.searchsorted(akey, e_user * D.KEY + e_ts), "cart_lo": a_lo[e_user],
         "is_new": new_u[e_user].astype(np.float32)}

    # carousels: feedback x requests, with the request context
    rq_ids = rq["request_id"].astype(str)
    rs = np.argsort(rq_ids)
    fpos = np.searchsorted(rq_ids[rs], fb["request_id"].astype(str))
    fpos = np.clip(fpos, 0, len(rs) - 1)
    match = rq_ids[rs][fpos] == fb["request_id"].astype(str)
    ri = rs[fpos][match]
    nrv = rq["nrv"].astype(np.int64)[ri]
    rv = np.full((len(ri), 6), -1, dtype=np.int64)
    for i in range(6):
        m = pidx(np.asarray(rq[f"rv{i}"], dtype=object)[ri])
        rv[:, i] = np.where((5 - i) < nrv, m, -1)
    shown = np.stack([pidx(np.asarray(fb[f"s{i}"], dtype=object)[match]) for i in range(10)], 1)
    clicked = pidx(np.asarray(fb["clicked"], dtype=object)[match])
    purchased = pidx(np.asarray(fb["purchased"], dtype=object)[match])
    cs = np.where((shown == clicked[:, None]) & (clicked[:, None] >= 0), np.arange(10), 99).min(1)
    f_ts = rq["ts_ms"].astype(np.int64)[ri]
    f_user = uidx(rq["user_id"].astype(str)[ri])
    fr = {"ts": f_ts, "user": f_user, "device": F.lookup(v["device"], rq["device"].astype(str)[ri]),
          "region": F.lookup(v["region"], rq["region"].astype(str)[ri]),
          "page": F.lookup(v["page"], rq["page"].astype(str)[ri]), "hour": ((f_ts // HOUR_MS) % 24),
          "rv": rv, "shown": shown, "click_slot": np.where(cs == 99, -1, cs),
          "purchased": (purchased >= 0) & (purchased == clicked), "is_new": flagged[ri].astype(np.float32),
          "hist_end": np.searchsorted(key, f_user * D.KEY + f_ts // HOUR_MS * HOUR_MS), "hist_lo": lo_user[f_user],
          "cart_end": np.searchsorted(akey, f_user * D.KEY + f_ts), "cart_lo": a_lo[f_user],
          "prop": np.ones((len(ri), 10), np.float32)}
    tr = (e_ts < t_hold) & ~held_u[e_user]
    pop = np.bincount(e_prod[(e_type == 2) & tr], minlength=P).astype(np.float64)
    _log(f"live: {P - P0} new products ({held_p.sum()} held out), {len(extra)} new users, "
         f"{held_u.sum()} held-out users, {len(ri)} carousels ({time.time() - t0:.0f}s)")
    return Live(product_ids=pids, prod=prod, new_product=is_new_p, heldout_products=held_p, user_ids=users,
                new_user=new_u, heldout_users=held_u, h=h, e=e, f=fr, t_end=t_end, t_holdout=t_hold, popularity=pop,
                n_hist_products=P0, a=a)
