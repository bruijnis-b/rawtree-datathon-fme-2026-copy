"""shopper_discount with an embedding model's score as its base: the model ranks, Bas's corrections adjust.

shopper_score multiplies factors per product. The model's score is a purchase log-odds, so it enters as one more
factor, `exp(score_weight x score)` (adding log-odds = multiplying odds). Factors the model already covers are
switched off by default: popularity (`alpha`), the shopper's category and subcategory shares (`w_cat`, `w_sub`),
the last viewed category (`ctx`), recent views (`recent`) and new products (`new`). What stays:

    exp(score_weight x model score)
      x discount lift    (price_discount's: only real discounts, cheap products gain most)
      x cart             in the cart, not bought
      x 0                bought before (history or today)
      x popularity ^ alpha   (0 = off; > 0 lets live best sellers, e.g. a new trend, pull up)

Every setting is a class attribute, so `--set` tunes them, and `--set embed_model=NAME` switches the model;
each combination gets its own public model ID. Refit them on team_NN.feedback with the model score as a fixed
offset. trend_boost can wrap it (`--policy trend_boost --set base=embed_score`).
"""
from __future__ import annotations

import numpy as np

from .base import Request
from .embed import EmbedModelMixin
from .shopper_discount import ShopperDiscount


class EmbedScore(EmbedModelMixin, ShopperDiscount):
    name = "embed_score"
    version = "v1"
    score_weight = 1.0  # weight of the model's log-odds (1 = as calibrated)
    alpha = 0.0         # popularity exponent (the model has popularity in its product bias)
    w_cat = 0.0         # covered by the model (shopper history)
    w_sub = 0.0
    ctx = 1.0           # covered by the model (recent views)
    recent = 1.0
    new = 1.0           # covered by the model (new products are scored from their catalogue fields)

    def fit(self) -> None:
        self.load_embedding_model()
        super().fit()

    def request_factor(self, req: Request, ids: list[str]) -> np.ndarray:
        s = self.model_scores(req).aligned(ids)
        return np.exp(self.score_weight * (s - s.max()))  # shifted: same ranking, no overflow
