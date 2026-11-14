"""Any policy, with products that are on sale pushed up.

On the practice day ~500-650 products went 11-20% below their original price for 2 hours, every 3 hours
(10:30, 13:30, 16:30 UTC); while discounted they got ~20% more views and ~30-55% more purchases. Two knobs:

- `boost`:  how much a discount lifts a product. Every product's score is multiplied by
            (1 + boost x discount): with boost 3, a 20%-off product scores x1.6. 0 = no lift.
- `inject`: how strongly to pull in discounted best sellers the base did not pick, from the category of the
            shopper's last viewed product (all categories if no views). Candidate rank t scores
            inject/(t+1), next to base rank r scoring 1/(r+1). 0 = only re-rank the base list.

Products need at least `min_discount` off to count. Composes with other wrappers, e.g.
`--set base=trend_boost` (settings are class attributes, so `--set` tunes them and each combination gets
its own public model ID).
"""
from __future__ import annotations

from .. import features
from .base import Policy, Request


class DiscountBoost(Policy):
    name = "discount_boost"
    version = "v1"
    base = "category_pop"  # policy to wrap (a REGISTRY name)
    boost = 3.0            # score x (1 + boost x discount)
    inject = 0.5           # weight of discounted best sellers from the shopper's category (0 = re-rank only)
    n_candidates = 10      # how many discounted best sellers to consider per request
    min_discount = 0.05    # at least 5% off to count as discounted

    def fit(self) -> None:
        from . import REGISTRY  # late import: the registry imports this module
        self.inner = REGISTRY[self.base](self.catalog, self.trends)
        self.inner.fit()
        counts = features.purchase_counts()

        def category(pid: str) -> str | None:
            p = self.catalog.get(pid)
            return p.category if p else None

        self.best = features.rank(counts)
        self.best_by_category = features.rank_by_group(counts, category)

    def discounted(self, ranked: list[str]) -> list[str]:
        """The first n_candidates products of `ranked` that are in stock and discounted enough."""
        out = []
        for pid in ranked:
            p = self.catalog.get(pid)
            if p and p.is_active and p.discount >= self.min_discount:
                out.append(pid)
                if len(out) == self.n_candidates:
                    break
        return out

    def recommend(self, req: Request) -> list[str]:
        items = self.inner.recommend(req)
        score: dict[str, float] = {}
        for r, pid in enumerate(items):
            score.setdefault(pid, 1 / (r + 1))  # first position counts (base lists may repeat a product)
        if self.inject > 0:
            last = self.catalog.get(req.last_view) if req.last_view else None
            pool = self.best_by_category.get(last.category, []) if last else self.best
            for t, pid in enumerate(self.discounted(pool)):
                score[pid] = score.get(pid, 0.0) + self.inject / (t + 1)
        for pid in score:
            p = self.catalog.get(pid)
            if p is not None and p.discount >= self.min_discount:
                score[pid] *= 1 + self.boost * p.discount
        return sorted(score, key=lambda pid: -score[pid])
