"""Everything we have in one policy: shopper_score x the sale lift x a lift for trending subcategories.

- shopper_score: popularity x the shopper's categories, cart, recent views, new products; products bought
  before are left out (shopper_score.py). Profiles come from the 60-day history and the live events.
- Sale lift: price_discount's, through shopper_discount.
- Trend: products of a subcategory that the live detector (trends.py) flags get x `trend`. On the practice
  day, Bike Helmets products shown during their trend sold 0.56% against 0.07% outside it (7 and 4
  purchases; clicks 4.5x), hence the default 8. The live popularity picks a trend up too, but only as
  the hour fills; this factor works from the minute the trend is detected. Tried on 600 live requests with a
  made-up trend: x8 puts 0.04 (Kettles) to 1.6 (Bike Helmets) trending products in an answer on average,
  mostly for shoppers whose last view is in that category; x4 almost none.
"""
from __future__ import annotations

from ..catalog import Product
from .shopper_discount import ShopperDiscount


class Combined(ShopperDiscount):
    name = "combined"
    version = "v1"
    trend = 8.0  # factor for products in a trending subcategory (1 = off)

    def _build(self) -> None:
        self._trending = set(self.trends.active()) if self.trends is not None else set()
        super()._build()

    def multiplier(self, p: Product) -> float:
        return super().multiplier(p) * (self.trend if p.subcategory in self._trending else 1.0)
