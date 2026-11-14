"""Best sellers in the category of the product the shopper viewed last.

No views (home page, new shopper): the overall best sellers. "Best sellers" comes from the shared
popularity: history blended with the last hour of live purchases (`live_weight`), with new products
starting at their subcategory's average (`new_prior`). live_weight 0 and new_prior False = history only (v1).
The category comes from the live catalogue, so it also works when the last view is a new product.
"""
from __future__ import annotations

from .base import Policy, Request


class CategoryPop(Policy):
    name = "category_pop"
    version = "v2"
    top_n = 30          # how many per-category candidates to keep; the guard filters inactive ones
    live_weight = 0.5   # weight of the last hour's purchases vs 60 days of history
    new_prior = True    # new products start at their subcategory's average history share

    def fit(self) -> None:
        self.popularity()  # load now, not on the first request

    def ranked(self, group: str) -> dict[str, list[str]]:
        return self.popularity().ranked(group, self.live_weight, self.new_prior)

    @property
    def best(self) -> list[str]:
        """Overall best sellers (also the guard's last padding)."""
        return self.ranked("all").get("", [])

    def recommend(self, req: Request) -> list[str]:
        last = self.catalog.get(req.last_view) if req.last_view else None
        ranked = self.best if last is None else self.ranked("category").get(last.category, [])
        return [p for p in ranked if self.catalog.is_active(p)][:self.top_n]
