"""Best sellers from the categories this shopper looks at, with cart and recently viewed products first.

`category_pop` follows the last viewed product, but that is in the shopper's most viewed category only 25%
of the time, while products from that category sell ~5x better (see profiles.py). The list is built as:

1. Products in the cart and not bought (at most `n_cart`), then the request's recent views (at most
   `n_recent`), most recent first. Purchase rates when shown: 1.07% and 0.74%, against 0.076% on average.
2. Best sellers per category, scored  weight(category) x (1 + sub_boost x subcategory share) / (rank + 1):

       weight(category) = views in the category / (all views + prior)  +  context if it is the last view's

   `prior` keeps a shopper with 1-2 views from counting as certain; `context` 0.3 puts the last view's
   category on a par with a category holding 30% of the views (what the practice data showed).
3. The base policy's list, as filler. Products bought that day are left out everywhere (0.03% when shown).

Without a profile and without views it returns the base list unchanged.
"""
from __future__ import annotations

from .base import Policy, Request


class ShopperProfile(Policy):
    name = "shopper_profile"
    version = "v1"
    base = "category_pop"  # filler, and the answer for shoppers we know nothing about
    context = 0.3          # weight of the last view's category, next to the view shares (which sum to <= 1)
    prior = 5.0            # views added to the denominator of every share
    sub_boost = 1.0        # extra weight for the shopper's subcategories within a category
    n_cart = 3             # cart-not-bought products put first
    n_recent = 3           # recently viewed products put next
    top_n = 30             # products kept
    live_weight = 0.5      # best-seller ranking: weight of live purchases vs history (see popularity.py)

    def fit(self) -> None:
        from . import REGISTRY  # late import: the registry imports this module
        self.inner = REGISTRY[self.base](self.catalog, self.trends, self._popularity, self.profiles)
        self.inner.fit()
        self.popularity()

    def recommend(self, req: Request) -> list[str]:
        prof = self.profiles.get(req.user_id) if self.profiles is not None else None
        base = self.inner.recommend(req)
        if prof is None and not req.recent_views:
            return base
        bought = prof.bought if prof else set()
        first = (prof.open_cart()[:self.n_cart] if prof else []) + list(reversed(req.recent_views))[:self.n_recent]

        weight: dict[str, float] = {}
        subs: dict[str, float] = {}
        if prof and prof.views:
            total = prof.views + self.prior
            weight = {c: n / total for c, n in prof.categories.items()}
            subs = {s: n / total for s, n in prof.subcategories.items()}
        last = self.catalog.get(req.last_view) if req.last_view else None
        if last is not None:
            weight[last.category] = weight.get(last.category, 0.0) + self.context

        score: dict[str, float] = {}
        by_category = self.popularity().ranked("category", self.live_weight)
        for category, w in weight.items():
            rank = 0
            for pid in by_category.get(category, []):
                p = self.catalog.get(pid)
                if p is None or not p.is_active:
                    continue
                score[pid] = w * (1 + self.sub_boost * subs.get(p.subcategory, 0.0)) / (rank + 1)
                rank += 1
                if rank == self.top_n:
                    break
        ranked = sorted(score, key=lambda pid: -score[pid])[:self.top_n]
        items = [p for p in dict.fromkeys(first + ranked + base) if p not in bought and self.catalog.is_active(p)]
        return items[:self.top_n]
