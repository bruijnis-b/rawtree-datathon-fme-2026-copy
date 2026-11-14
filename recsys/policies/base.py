"""The interface every recommendation algorithm implements."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..catalog import LiveCatalog


@dataclass(frozen=True)
class Request:
    """One shop.requests record, normalised."""
    request_id: str
    ts_ms: int  # request time, epoch milliseconds (UTC)
    user_id: str
    is_new_user: bool
    device: str
    region: str
    page: str
    recent_views: tuple[str, ...] = field(default=())  # product IDs, oldest first

    @property
    def last_view(self) -> str | None:
        return self.recent_views[-1] if self.recent_views else None

    @staticmethod
    def from_row(r: dict[str, Any]) -> "Request":
        return Request(
            request_id=str(r["request_id"]),
            ts_ms=int(r["ts_ms"]),
            user_id=str(r.get("user_id") or ""),
            is_new_user=bool(r.get("is_new_user")),
            device=str(r.get("device") or ""),
            region=str(r.get("region") or ""),
            page=str(r.get("page") or ""),
            recent_views=_views(r.get("recent_views")),
        )


def _views(raw: Any) -> tuple[str, ...]:
    """recent_views arrives as a list of {product_id, ts} objects, or an empty/None-typed array."""
    if not raw:
        return ()
    items = []
    for v in raw:
        if isinstance(v, dict) and v.get("product_id"):
            items.append((str(v.get("ts") or ""), str(v["product_id"])))
        elif isinstance(v, str) and v:
            items.append(("", v))
    items.sort(key=lambda t: t[0])  # stable: keeps array order when timestamps are missing
    return tuple(p for _, p in items)


class Policy:
    """A recommender. Subclasses set `name`/`version` and implement `fit` and `recommend`.

    - `fit` runs once at startup (and may be called again to refresh): load whatever the policy needs.
    - `recommend` must be fast (a few ms) and return a ranked list of product IDs. It may return fewer or more
      than 10, inactive or duplicate IDs: the guard cleans and pads every answer before it is sent.
    """
    name = "policy"
    version = "v1"

    def __init__(self, catalog: LiveCatalog) -> None:
        self.catalog = catalog

    @property
    def internal_version(self) -> str:
        """Our own name for this policy, e.g. 'coview-v1'. NEVER send it: submissions carry an opaque ID
        from recsys.model_registry instead."""
        return f"{self.name}-{self.version}"

    def fit(self) -> None:
        pass

    def recommend(self, req: Request) -> list[str]:
        raise NotImplementedError
