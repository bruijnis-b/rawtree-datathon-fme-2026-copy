"""Any policy, plus the best sellers of the subcategories trending right now.

Wraps a base policy (`base`). With no active trend it returns the base list unchanged. While the trend
detector reports a trending subcategory, it mixes in that subcategory's best sellers (in stock, at most
`per_brand` per brand; strongest trend first) in one of three ways, set by `mode`:

- "slots":   always put `n_slots` trend products at position `slot` (1 = first), for everyone.
- "context": how many depends on the shopper: `n_related` if they last viewed the trending subcategory,
             `n_home` if they have no recent views, `n_other` otherwise; placed at position `slot`.
- "score":   blend scores: base rank r scores 1/(r+1), trend rank t adds boost/(t+1); sort by total.
             boost 0 = base only, 1 = the top trend product ties the base's first product, higher = more.

All settings are class attributes, so `--set` in main.py can tune them and each setting gets its own
public model ID.
"""
from __future__ import annotations

from collections import Counter

from .base import Policy, Request


class TrendBoost(Policy):
    name = "trend_boost"
    version = "v1"
    base = "category_pop"  # policy to wrap (a REGISTRY name)
    mode = "context"    # "slots" | "context" | "score"
    slot = 1            # first position the trend products take (slots/context)
    n_slots = 2         # slots mode: how many
    n_related = 4       # context mode: shopper last viewed the trending subcategory
    n_home = 3          # context mode: no recent views (home page, new shopper)
    n_other = 1         # context mode: anything else
    boost = 1.0         # score mode: weight of the trend ranking
    per_brand = 2       # at most this many trend products per brand
    live_weight = 0.5   # trend product ranking: weight of live purchases vs history (see popularity.py)

    def fit(self) -> None:
        if self.mode not in ("slots", "context", "score"):
            raise ValueError(f"unknown mode {self.mode!r}: use slots, context or score")
        from . import REGISTRY  # late import: the registry imports this module
        self.inner = REGISTRY[self.base](self.catalog, self.trends, self._popularity)
        self.inner.fit()
        self.popularity()

    def trend_products(self) -> list[str]:
        """Best sellers of the active trends, strongest trend first, in stock, capped per brand."""
        active = self.trends.active() if self.trends else {}
        out: list[str] = []
        for sub in sorted(active, key=lambda s: -active[s].lift):
            brands: Counter[str] = Counter()
            for pid in self.popularity().ranked("subcategory", self.live_weight).get(sub, []):
                p = self.catalog.get(pid)
                if p and p.is_active and brands[p.brand] < self.per_brand:
                    brands[p.brand] += 1
                    out.append(pid)
                if len(out) >= 10 * len(active):
                    break
        return out

    def how_many(self, req: Request) -> int:
        if self.mode == "slots":
            return self.n_slots
        last = self.catalog.get(req.last_view) if req.last_view else None
        active = self.trends.active() if self.trends else {}
        if last is not None and last.subcategory in active:
            return self.n_related
        return self.n_home if not req.recent_views else self.n_other

    def recommend(self, req: Request) -> list[str]:
        items = self.inner.recommend(req)
        picks = self.trend_products()
        if not picks:
            return items
        if self.mode == "score":
            score: dict[str, float] = {}
            for r, p in enumerate(items):
                score.setdefault(p, 1 / (r + 1))  # first position counts (base lists may repeat a product)
            for t, p in enumerate(picks):
                score[p] = score.get(p, 0.0) + self.boost / (t + 1)
            return sorted(score, key=lambda p: -score[p])
        chosen = picks[:self.how_many(req)]
        rest = [p for p in items if p not in chosen]
        at = max(0, self.slot - 1)
        return rest[:at] + chosen + rest[at:]
