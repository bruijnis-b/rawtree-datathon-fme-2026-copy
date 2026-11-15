"""Two policies in one arm: one answers cold requests, the other the rest.

A request is cold when the shopper is new (`is_new_user`) or a recent view is a product added during the event:
the organisers' definition of the cold-start score. Each side is a full policy spec with `;` instead of `,`
(commas separate this policy's own settings), for example

    route:cold=embed_blend;embed_model=models/v2;embed_model2=models/v3,warm=embed_score;embed_model=models/v4

Why: overnight the arms that were best on cold requests were not the ones best on warm requests, and other teams
answer cold requests with a model of their own.
"""
from __future__ import annotations

from .base import Policy, Request


def _build(owner: Policy, spec: str) -> Policy:
    name, *settings = spec.split(";")
    policy = owner.sibling(name)
    for item in settings:  # the same conversion as main.apply_settings
        key, _, value = item.partition("=")
        if hasattr(policy, key) and not key.startswith("_"):
            default = getattr(policy, key)
            setattr(policy, key, value.lower() in ("1", "true", "yes") if isinstance(default, bool)
                    else type(default)(value))
    policy.fit()
    return policy


class Route(Policy):
    name = "route"
    version = "v1"
    cold = ""  # policy spec for cold requests (`;` between its settings)
    warm = ""  # policy spec for every other request

    def fit(self) -> None:
        if not self.cold or not self.warm:
            raise ValueError("route needs both cold= and warm=")
        self._cold = _build(self, self.cold)
        self._warm = _build(self, self.warm)

    def is_cold(self, req: Request) -> bool:
        if req.is_new_user:
            return True
        return any((p := self.catalog.get(pid)) is not None and p.is_new for pid in req.recent_views)

    def recommend(self, req: Request) -> list[str]:
        return (self._cold if self.is_cold(req) else self._warm).recommend(req)
