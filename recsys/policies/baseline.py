"""The organisers' baseline: the 10 all-time best sellers that are active. Same for every shopper."""
from __future__ import annotations

from .. import features
from .base import Policy, Request


class Baseline(Policy):
    name = "baseline"
    version = "v1"

    def fit(self) -> None:
        self.best = features.rank(features.purchase_counts())

    def recommend(self, req: Request) -> list[str]:
        return [p for p in self.best if self.catalog.is_active(p)][:10]
