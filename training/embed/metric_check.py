"""Metric check: score baseline, category_pop and coview offline with the same ips_hit@10 / slate_auc code.

python -m training.embed.metric_check [--fold 0]. Their offline order must match their live order.
Offline equivalents, built from training days only: baseline = all-time best sellers (organic purchases);
category_pop = best sellers in the category of the last recent view, then baseline; coview = products viewed by the
same user within 30 min of the recent views (decay 0.7 per step back, 1/rank), then category_pop.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict

import numpy as np

from training.embed import data as D
from training.embed.metrics import boot_lift


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold", type=int, default=0)
    a = ap.parse_args()
    d = D.load(a.fold)
    s, e = d.s, d.e
    P = len(d.product_ids)
    lt = D.theta_table(d.vocab["device"])
    pop = d.popularity
    best = list(np.argsort(-pop)[:10])
    cat = d.prod["cat"]
    by_cat = {c: list(np.argsort(-(pop * (cat == c)))[:10]) for c in np.unique(cat)}
    # co-views: consecutive views of a user within 30 min, training days
    tr = (e["day"] <= D.TRAIN_LAST_DAY) & (e["type"] == 0)
    prev = e["rv"][tr][:, -1]
    cur = e["prod"][tr]
    ok = prev >= 0
    pairs = Counter()
    for p, q in zip(prev[ok].tolist(), cur[ok].tolist()):
        if p != q:
            pairs[(p, q)] += 1
            pairs[(q, p)] += 1
    nb = defaultdict(list)
    for (p, q), n in pairs.most_common():
        if len(nb[p]) < 20:
            nb[p].append(q)

    def rec_catpop(rv):
        last = [p for p in rv if p >= 0]
        lst = by_cat.get(cat[last[-1]], []) if last else []
        return (lst + [b for b in best if b not in lst])[:10]

    def rec_coview(rv):
        sc = Counter()
        views = [p for p in rv if p >= 0][-5:]
        for k, v in enumerate(reversed(views)):
            for r, q in enumerate(nb.get(v, [])):
                sc[q] += 0.7 ** k / (r + 1)
        items = [q for q, _ in sc.most_common(10)]
        return (items + [b for b in rec_catpop(rv) if b not in items])[:10]

    vi = np.flatnonzero((s["day"] > D.TRAIN_LAST_DAY) & (s["click_slot"] >= 0))
    held_u, held_p = d.heldout_users, d.heldout_products
    pols = {"baseline": lambda rv: best, "category_pop": rec_catpop, "coview": rec_coview}
    num = {k: np.zeros(len(vi), np.float32) for k in pols}
    for j, i in enumerate(vi):
        cs = s["click_slot"][i]
        cp = s["shown"][i, cs]
        w = (3.0 if s["purchased"][i] else 1.0) / max(s["prop"][i, cs], 0.01)
        dv = s["device"][i]
        for k, f in pols.items():
            top = f(s["rv"][i])
            if cp in top:
                num[k][j] = w * np.exp(lt[top.index(cp), dv])
    rv = s["rv"][vi]
    cold = held_u[s["user"][vi]] | (held_p[rv.clip(0)] & (rv >= 0)).any(1)
    masks = {"all": np.ones(len(vi), np.float32), "cold": cold.astype(np.float32)}
    print("ips_hit@10 lift over baseline (same code as training.embed.metrics):")
    for k in pols:
        r, _ = boot_lift(num[k], num["baseline"], masks, 500)
        print(f"  {k:13s} all {r['all']['lift']:+.3f} [{r['all']['lift_lo']:+.3f}, {r['all']['lift_hi']:+.3f}]"
              f"   cold {r['cold']['lift']:+.3f}   value {r['all']['value']:.3f}")


if __name__ == "__main__":
    main()
