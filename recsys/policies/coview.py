"""Products viewed in the same sessions as this shopper's recent views, then category best sellers.

Each recent view votes for its top co-viewed products; more recent views count more (decay per step back)
and higher-ranked co-views count more (1 / rank). Same idea as the policy in starter/offline_eval.ipynb.
"""
from __future__ import annotations

from collections import Counter

from .. import features
from .base import Policy, Request
from .category_pop import CategoryPop


class Coview(Policy):
    name = "coview"
    version = "v1"
    decay = 0.7       # weight of the view k steps before the last one: decay ** k
    max_views = 5     # only the most recent views
    top_k = 20        # co-viewed products kept per product

    def fit(self) -> None:
        self.covisit = features.coviews(self.top_k)
        self.fallback = CategoryPop(self.catalog, self.trends, self._popularity)
        self.fallback.fit()

    def recommend(self, req: Request) -> list[str]:
        score: Counter[str] = Counter()
        for k, viewed in enumerate(reversed(req.recent_views[-self.max_views:])):
            for rank, q in enumerate(self.covisit.get(viewed, [])):
                if self.catalog.is_active(q):
                    score[q] += self.decay ** k / (rank + 1)
        items = [q for q, _ in score.most_common(10)]
        return list(dict.fromkeys(items + self.fallback.recommend(req)))  # no duplicates: wrappers rank this list
