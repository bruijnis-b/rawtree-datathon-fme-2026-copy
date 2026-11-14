"""Best sellers in the category of the product the shopper viewed last.

No views (home page, new shopper): the all-time best sellers. The category comes from the live catalogue, so
it also works when the last view is a product added during the event.
"""
from __future__ import annotations

from .. import features
from .base import Policy, Request


class CategoryPop(Policy):
    name = "category_pop"
    version = "v1"
    top_n = 30  # how many per-category candidates to keep; the guard filters inactive ones

    def fit(self) -> None:
        counts = features.purchase_counts()
        self.best = features.rank(counts)

        def category(pid: str) -> str | None:
            p = self.catalog.get(pid)
            return p.category if p else None

        self.best_by_category = features.rank_by_group(counts, category)

    def recommend(self, req: Request) -> list[str]:
        last = self.catalog.get(req.last_view) if req.last_view else None
        ranked = self.best if last is None else self.best_by_category.get(last.category, [])
        return [p for p in ranked if self.catalog.is_active(p)][:self.top_n]
