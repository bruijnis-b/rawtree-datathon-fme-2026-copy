"""embed_score with two optional extras, kept in their own policy so embed_score's public IDs do not change.

- `embed_model2`: a second embedding model; the two scores (log-odds, same scale) are averaged. On our logged
  answers after 00:59 UTC on 15 Nov the average of two recipes ranked the bought product higher than either
  model alone.
- `max_lift`: a cap on the discount lift (0 = no cap). The lift grows in a straight line with the discount and
  was fitted on discounts of 11-20%; a 40% discount would get x2.6 with nothing behind it.
"""
from __future__ import annotations

import numpy as np

from ..catalog import Product
from .base import Request
from .embed_score import EmbedScore
from .shopper_discount import ShopperDiscount


class EmbedBlend(EmbedScore):
    name = "embed_blend"
    version = "v1"
    embed_model2 = ""  # second model, averaged with `embed_model` ('' = none); resolved to the real name in fit
    max_lift = 0.0     # highest discount lift per product (0 = no cap)

    def fit(self) -> None:
        self.model2 = None
        if self.embed_model2:
            self.model2 = self.embedding_model(self.embed_model2)
            self.embed_model2 = self.model2.model_id
        super().fit()

    def request_factor(self, req: Request, ids: list[str]) -> np.ndarray:
        s = self.model_scores(req).aligned(ids)
        if self.model2 is not None:
            s = 0.5 * (s + self.model2.scores(req, events="auto" if self.use_events else None).aligned(ids))
        return np.exp(self.score_weight * (s - s.max()))  # shifted: same ranking, no overflow

    def multiplier(self, p: Product) -> float:
        lift = ShopperDiscount.multiplier(self, p)
        if self.max_lift > 0:
            lift = min(lift, self.max_lift)
        return lift * (self.trend if p.subcategory in self._trending else 1.0)
