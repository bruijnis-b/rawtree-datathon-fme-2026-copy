"""An embedding model on its own: the ten products with the highest model scores, no corrections.

The model is the one named by `embed_model` ('' = the default in recsys/embed_models.json); see
recsys/embeddings.py. This is the reference arm: corrections (discounts, trends, cart) go on top in embed_score,
or wrap it (`--set base=embed` for trend_boost and discount_boost re-rank by position only).
"""
from __future__ import annotations

from .base import Policy, Request


class EmbedModelMixin:
    """`embed_model` setting and the shared model, for every policy built on an embedding model."""
    embed_model = ""  # manifest name or folder ('' = default); set to the resolved name in fit, for the public ID
    use_events = True  # pass the shopper's history + live events (False: precomputed history vectors only)

    def load_embedding_model(self) -> None:
        self.model = self.embedding_model(self.embed_model)
        self.embed_model = self.model.model_id  # the default changes over time: log which model this really is

    def model_scores(self, req: Request):
        return self.model.scores(req, events="auto" if self.use_events else None)


class Embed(EmbedModelMixin, Policy):
    name = "embed"
    version = "v1"

    def fit(self) -> None:
        self.load_embedding_model()

    def recommend(self, req: Request) -> list[str]:
        return self.model_scores(req).top(10)
