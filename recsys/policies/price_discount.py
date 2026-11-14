"""discount_boost with the lift shaped like today's sales: only real discounts count, and cheap products gain most.

Measured on the 3 sales of 14 Nov (1,733 discounted products, organic purchases on sale vs the same product at
full price): 11-14% off gave no lift (1.02x), 17-20% off 1.36x; the cheapest third of a subcategory gained
1.33x, the priciest third 1.19x. So the multiplier is

    1 + boost x max(0, discount - floor) x (1 - rel_price x q)

with q the product's list-price percentile in its subcategory (0 = cheapest, 1 = priciest). Defaults fit those
numbers: 18% off gives ~x1.33 for a cheap product, ~x1.17 for a pricey one, 12% off nothing.
Everything else (inject, candidates) is discount_boost's.
"""
from __future__ import annotations

import bisect
from collections import defaultdict

from ..catalog import Product
from .discount_boost import DiscountBoost


class PriceDiscount(DiscountBoost):
    name = "price_discount"
    version = "v1"
    boost = 6.0          # lift per unit of discount above `floor`
    floor = 0.12         # discounts up to this give no lift
    rel_price = 0.6      # how much less a product at the top of its subcategory's price range gains
    min_discount = 0.12  # candidates for `inject` need at least this much off

    def fit(self) -> None:
        super().fit()
        self._q: dict[str, float] = {}
        self._n = -1

    def rel(self, p: Product) -> float:
        """List-price percentile in its subcategory; rebuilt when the catalogue grows (new products)."""
        if len(self.catalog.products) != self._n:  # cheap check; rebuild ~5 ms
            products = self.catalog.snapshot()
            by_sub: dict[str, list[float]] = defaultdict(list)
            for x in products:
                by_sub[x.subcategory].append(x.list_price)
            for v in by_sub.values():
                v.sort()
            self._q = {x.product_id: bisect.bisect_left(by_sub[x.subcategory], x.list_price)
                       / max(len(by_sub[x.subcategory]) - 1, 1) for x in products}
            self._n = len(products)
        return self._q.get(p.product_id, 0.5)

    def lift(self, p: Product) -> float:
        return 1 + self.boost * max(0.0, p.discount - self.floor) * (1 - self.rel_price * self.rel(p))
