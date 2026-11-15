"""One row per product shown in our live answers: the embedding model's score plus every shopper_score factor, as
the policy saw them at request time. python -m recsys.refit.build v1 (or a folder) -> data/refit/ds_v1.parquet

Factors: popularity (history share blended 50/50 with the last hour's live share; no stock-out correction),
the shopper's category and subcategory shares of views (history + live, prior 5), last-viewed category, recent view,
cart (not bought), bought before, new product, discount and list-price percentile in the subcategory.
The model gets the shopper's history tail plus live events once they have live events, as in serving.
"""
from __future__ import annotations

import bisect
import collections
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from recsys import client
from recsys.embeddings import MODELS_DIR, default_name
from training.export.scorer import load

from .download import OUT

COLS = ["r", "t", "m", "pos", "click", "purch", "s", "pop", "cat", "sub", "ctx", "recent", "cart", "bought", "new",
        "disc", "relq", "new_user", "has_live", "has_hist"]


def products() -> tuple[list[dict], set[str]]:
    """Every product with its ORIGINAL price (catalogue, or first price of a new product) and description."""
    base = client.query("""SELECT product_id::String product_id, category::String category, subcategory::String subcategory,
        brand::String brand, description::String description, price_eur::Float64 price FROM shop.catalog""")
    known = {r["product_id"] for r in base}
    new = [r for r in client.query("""SELECT product_id::String product_id, argMin(category::String, ts::DateTime64(3)) category,
        argMin(subcategory::String, ts::DateTime64(3)) subcategory, argMin(brand::String, ts::DateTime64(3)) brand,
        argMin(description::String, ts::DateTime64(3)) description, argMin(price_eur::Float64, ts::DateTime64(3)) price
        FROM shop.catalog_updates WHERE change::String = 'new_product' GROUP BY product_id""") if r["product_id"] not in known]
    return base + new, {r["product_id"] for r in new}


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else default_name()
    if not Path(folder).is_dir():  # a published model's name: its folder under models/
        folder = str(MODELS_DIR / folder)
    model = load(folder)
    hl = int(model.meta.get("history_len", 0))
    prods, NEW = products()
    pm = model.embed_products(prods)
    P = {r["product_id"]: r for r in prods}
    listp = {p: r["price"] for p, r in P.items()}
    ph: dict[str, tuple[list, list]] = collections.defaultdict(lambda: ([], []))
    for r in client.query("""SELECT product_id::String p, toUnixTimestamp64Milli(ts::DateTime64(3)) t, price_eur::Float64 x
            FROM shop.catalog_updates WHERE change::String = 'price_change' ORDER BY t"""):
        ph[r["p"]][0].append(r["t"]); ph[r["p"]][1].append(r["x"])

    def disc(p, t):
        ts, xs = ph.get(p, ((), ()))
        i = bisect.bisect_right(ts, t) - 1
        return max(0.0, 1 - xs[i] / listp[p]) if i >= 0 and listp.get(p) else 0.0

    bysub = collections.defaultdict(list)
    for r in P.values():
        bysub[r["subcategory"]].append(r["price"])
    for v in bysub.values():
        v.sort()
    relq = {p: bisect.bisect_left(bysub[r["subcategory"]], r["price"]) / max(len(bysub[r["subcategory"]]) - 1, 1)
            for p, r in P.items()}

    fb = pd.read_parquet(OUT / "feedback.parquet")
    m = fb[fb.sb == "team"].merge(pd.read_parquet(OUT / "requests.parquet"), on="r")
    users = set(m.u)
    ev = pd.read_parquet(OUT / "events.parquet").sort_values("t")
    he = pd.read_parquet(OUT / "hevents.parquet", columns=["t", "u", "p", "e"])
    hist_pop = he[he.e == "purchase"].p.value_counts()
    hist_total = hist_pop.sum()
    he = he[he.u.isin(users)].sort_values("t")
    hseq = {u: list(zip(d.p.values[-hl:], d.e.values[-hl:])) for u, d in he.groupby("u")} if hl else {}
    hbought = he[he.e == "purchase"].groupby("u").p.agg(set).to_dict()
    hcart = he[he.e == "add_to_cart"].groupby("u").p.agg(set).to_dict()
    del he
    h = pd.read_parquet(OUT / "hist_user_subcat.parquet")
    hs = collections.defaultdict(collections.Counter)
    hc = collections.defaultdict(collections.Counter)
    for u, c, s, n in zip(h.u, h.c, h.s, h.n):
        if u in users:
            hs[u][s] += n; hc[u][c] += n
    del h
    byu = {u: (d.t.values, d.p.values, d.e.values) for u, d in ev[ev.u.isin(users)].groupby("u")}
    pur = ev[ev.e == "purchase"]
    pt = {p: d.t.values for p, d in pur.groupby("p")}
    pur_t = pur.t.values

    def pop(p, t):
        a = pt.get(p)
        live = np.searchsorted(a, t) - np.searchsorted(a, t - 3_600_000) if a is not None else 0
        tot = max(np.searchsorted(pur_t, t) - np.searchsorted(pur_t, t - 3_600_000), 1)
        return 0.5 * hist_pop.get(p, 0) / hist_total + 0.5 * live / tot

    rows, t0 = [], time.time()
    for k, r in enumerate(m.itertuples()):
        rv, t = list(r.rv), r.t
        tt, pp, ee = byu.get(r.u, ((), (), ()))
        i = bisect.bisect_right(tt, t) if len(tt) else 0
        live = list(zip(pp[:i], ee[:i]))
        events = [e for e in (hseq.get(r.u, []) + live)[-100:] if e[0] in pm.index] if live and hl else None
        req = dict(user_id=r.u, is_new_user=r.new, device=r.dv, region=r.rg, page=r.page, recent_views=rv, ts_ms=t)
        sc = model.score(req, pm, events=events)
        vc, vs = collections.Counter(hc.get(r.u, {})), collections.Counter(hs.get(r.u, {}))
        bought, cart = set(hbought.get(r.u, ())), set(hcart.get(r.u, ()))
        for p, e in live:
            if e == "view" and p in P:
                vc[P[p]["category"]] += 1; vs[P[p]["subcategory"]] += 1
            elif e == "add_to_cart":
                cart.add(p)
            elif e == "purchase":
                bought.add(p)
        nv = sum(vc.values()) + 5
        lv = P.get(rv[-1]) if rv else None
        for pos, p in enumerate(r.shown):
            if p not in P:
                continue
            j = pm.index.get(p)
            rows.append((r.r, t, r.m, pos, p == r.c, p == r.p, float(sc[j]) if j is not None else np.nan, pop(p, t),
                         vc[P[p]["category"]] / nv, vs[P[p]["subcategory"]] / nv,
                         bool(lv) and lv["category"] == P[p]["category"], p in rv, p in cart and p not in bought,
                         p in bought, p in NEW, disc(p, t), relq[p], r.new, events is not None, r.u in hs))
        if k % 20000 == 0:
            print(f"{k}/{len(m)} answers, {time.time() - t0:.0f} s", flush=True)
    name = folder.rstrip("/\\").replace("\\", "/").split("/")[-1]
    pd.DataFrame(rows, columns=COLS).to_parquet(OUT / f"ds_{name}.parquet")
    print(f"{len(rows)} shown products, {int(m.p.ne('').sum())} purchases -> {OUT / f'ds_{name}.parquet'}")


if __name__ == "__main__":
    main()
