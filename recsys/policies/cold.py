"""Extra lifts for cold requests, on top of shopper_score-based policies (combined, embed_score).

Measured on 94k of our practice-day answers (purchase rate per shown product):

- A request whose recent views include a product added during the event: new products sold 0.54-0.81%
  (the viewed one 0.63%, new products of other subcategories 0.54%), old products 0.08%, also those of the
  viewed new product's subcategory. About 7x, against ~3x for new products on warm requests. It is about
  newness, not the subcategory. So new products get x `new_view` on these requests (on top of `new`).
- A new shopper (`is_new_user`): their recent views sold 0.70% against 0.13% for other products (5x; 3x for
  warm shoppers). So recent views get x `recent_new_user` (on top of `recent`).

About 17 purchases behind the first number and 57 behind the second: rough, test live on the cold conversion.
The embedding model was trained on history without new products, so it cannot know the first one either.
"""
from __future__ import annotations

import numpy as np

from .base import Request
from .combined import Combined
from .embed_score import EmbedScore


class ColdBoostMixin:
    new_view = 3.0         # new products, when the request's recent views include a new product
    recent_new_user = 2.0  # the request's recent views, for a new shopper

    def request_factor(self, req: Request, ids: list[str]) -> np.ndarray | None:
        factor = super().request_factor(req, ids)
        viewed_new = any((p := self.catalog.get(pid)) is not None and p.is_new for pid in req.recent_views)
        new_user = req.is_new_user and bool(req.recent_views)
        if not (viewed_new and self.new_view != 1) and not (new_user and self.recent_new_user != 1):
            return factor
        factor = np.ones(len(ids)) if factor is None else factor.copy()
        if viewed_new and self.new_view != 1:
            if getattr(self, "_new_mask_ids", None) is not ids:  # same list object until the next rebuild
                self._new_mask = np.array([(p := self.catalog.get(pid)) is not None and p.is_new for pid in ids])
                self._new_mask_ids = ids
            factor[self._new_mask] *= self.new_view
        if new_user and self.recent_new_user != 1:
            ids0, index = self._arrays[:2]
            if ids0 is not ids:  # rebuilt meanwhile
                index = {pid: i for i, pid in enumerate(ids)}
            for pid in set(req.recent_views):
                if pid in index:
                    factor[index[pid]] *= self.recent_new_user
        return factor


class ColdCombined(ColdBoostMixin, Combined):
    name = "cold_combined"
    version = "v1"


class ColdEmbed(ColdBoostMixin, EmbedScore):
    """embed_score has `new` = 1 (the model scores new products from their catalogue fields), so the newness
    lift for cold requests is all in `new_view`."""
    name = "cold_embed"
    version = "v1"
    new_view = 6.0
