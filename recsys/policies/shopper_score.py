"""Every product scored for this shopper: popularity x how well it fits what we know about the shopper.

`shopper_profile` puts cart and recently viewed products first, whatever they are. Its live rows showed
that this wastes the best positions: a recently viewed product sells 1.0% when it is a best seller and
0.03% when it is not (cart products: 1.0% against 0.3%), and the first position sells ~6x the last.
So here every in-stock product gets one score, and the 30 highest are returned, best first:

    popularity ^ alpha
      x exp(w_cat x category share + w_sub x subcategory share)   share of the shopper's views, history + live
      x ctx      if it is in the category of the last viewed product
      x recent   if it is one of the request's recent views
      x cart     if it is in the shopper's cart and not bought
      x new      if it was added during the event
      x 0        if the shopper bought it before (history or today)

The defaults are the coefficients of a logistic regression on the practice day's live feedback (684,000
shown products, 648 purchases; list position controlled for). Popularity is the shared live popularity
(popularity.py); shares are views / (all views + prior). Without profile and views this is the best sellers.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from ..catalog import Product
from .base import Policy, Request

REFRESH_S = 5  # the per-product arrays (popularity, multiplier) are rebuilt at most this often


class ShopperScore(Policy):
    name = "shopper_score"
    version = "v1"
    alpha = 1.2        # popularity exponent
    w_cat = 3.0        # exp(w_cat x category share): 60% of the views in the category = x6
    w_sub = 1.0        # exp(w_sub x subcategory share)
    ctx = 1.5          # category of the last viewed product
    recent = 4.5       # one of the request's recent views
    cart = 6.0         # in the cart, not bought
    new = 2.5          # product added during the event
    prior = 5.0        # views added to the denominator of every share
    top_n = 30         # products returned
    live_weight = 0.5  # popularity: weight of live purchases vs history (see popularity.py)

    def fit(self) -> None:
        self.popularity()
        self._built = 0.0
        self._lock = threading.Lock()
        self._build()

    def multiplier(self, p: Product) -> float:
        """Extra factor per product, for subclasses (e.g. discounts)."""
        return 1.0

    def request_factor(self, req: Request, ids: list[str]) -> np.ndarray | None:
        """Extra factor per product for this request, in the order of `ids` (the same list object until the
        next rebuild), for subclasses (e.g. an embedding model's scores, see embed_score). None = none."""
        return None

    def _build(self) -> None:
        """Per-product arrays: base score (popularity, new, multiplier) and category / subcategory index."""
        pop = self.popularity().scores(self.live_weight)
        products = self.catalog.snapshot()
        cats = {c: i for i, c in enumerate(sorted({p.category for p in products}))}
        subs = {s: i for i, s in enumerate(sorted({p.subcategory for p in products}))}
        base = np.array([pop.get(p.product_id, 0.0) ** self.alpha * (self.new if p.is_new else 1.0)
                         * self.multiplier(p) for p in products])
        self._arrays = ([p.product_id for p in products], {p.product_id: i for i, p in enumerate(products)}, base,
                        np.array([cats[p.category] for p in products]),
                        np.array([subs[p.subcategory] for p in products]), cats, subs)
        self._built = time.time()

    def recommend(self, req: Request) -> list[str]:
        if time.time() - self._built > REFRESH_S and self._lock.acquire(blocking=False):
            try:
                self._build()
            finally:
                self._lock.release()
        ids, index, base, cat_of, sub_of, cats, subs = self._arrays
        score = base.copy()
        factor = self.request_factor(req, ids)
        if factor is not None:
            score *= factor
        prof = self.profiles.get(req.user_id) if self.profiles is not None else None
        if prof is not None and prof.views:
            total = prof.views + self.prior
            w = np.zeros(len(cats))
            for c, n in prof.categories.items():
                if c in cats:
                    w[cats[c]] = self.w_cat * n / total
            ws = np.zeros(len(subs))
            for s, n in prof.subcategories.items():
                if s in subs:
                    ws[subs[s]] = self.w_sub * n / total
            score *= np.exp(w[cat_of] + ws[sub_of])
        last = self.catalog.get(req.last_view) if req.last_view else None
        if last is not None and last.category in cats:
            score[cat_of == cats[last.category]] *= self.ctx
        for pid in set(req.recent_views):
            if pid in index:
                score[index[pid]] *= self.recent
        if prof is not None:
            for pid in prof.cart:
                if pid in index:
                    score[index[pid]] *= self.cart
            for pid in prof.bought:
                if pid in index:
                    score[index[pid]] = 0.0
        n = min(self.top_n + 20, len(ids))  # spare ones for products that are out of stock
        top = np.argpartition(-score, n - 1)[:n]
        top = top[np.argsort(-score[top])]
        return [ids[i] for i in top if score[i] > 0 and self.catalog.is_active(ids[i])][:self.top_n]
