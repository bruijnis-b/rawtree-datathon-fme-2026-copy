"""shopper_score with products on sale lifted the way price_discount lifts them.

shopper_score multiplies factors per product, so the discount is one more factor: price_discount's
`lift` (only real discounts count, and cheap products gain most; see price_discount.py). The settings
`boost`, `floor` and `rel_price` are price_discount's; nothing is injected, because every product is
already scored.
"""
from __future__ import annotations

from ..catalog import Product
from .price_discount import PriceDiscount
from .shopper_score import ShopperScore


class ShopperDiscount(ShopperScore):
    name = "shopper_discount"
    version = "v1"
    boost = PriceDiscount.boost          # lift per unit of discount above `floor`
    floor = PriceDiscount.floor          # discounts up to this give no lift
    rel_price = PriceDiscount.rel_price  # how much less a product at the top of its subcategory's price range gains

    def fit(self) -> None:
        self._pricing = PriceDiscount(self.catalog, self.trends, self._popularity)
        self._pricing._q, self._pricing._n = {}, -1  # what PriceDiscount.fit sets up, without its base policy
        self._pricing.boost, self._pricing.floor, self._pricing.rel_price = self.boost, self.floor, self.rel_price
        super().fit()

    def multiplier(self, p: Product) -> float:
        return self._pricing.lift(p) if p.discount > self.floor else 1.0
