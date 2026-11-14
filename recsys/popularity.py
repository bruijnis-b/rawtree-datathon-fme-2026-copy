"""Product popularity: 60 days of history blended with the last hour of live purchases.

    score = (1 - live_weight) x history share + live_weight x live share

- history share: the product's share of all purchases in shop.history_events. A product added during the
  event has none; with `new_prior` it gets the average history share of the existing products in its
  subcategory, so it ranks like a typical product there instead of last.
- live share: its share of purchases in shop.events over the last LIVE_MIN minutes, refreshed every minute.
  This is where new products earn their place, and where trends and sales show up.

Rankings (overall, per category, per subcategory) are cached per refresh, so policies just look them up.
Without load()/start(), e.g. offline, it is history only.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter, defaultdict

from . import client, features
from .catalog import LiveCatalog

log = logging.getLogger(__name__)

LIVE_MIN = 60  # minutes of live purchases counted


class Popularity:
    def __init__(self, catalog: LiveCatalog) -> None:
        self.catalog = catalog
        self.hist: dict[str, int] = {}
        self.live: Counter[str] = Counter()
        self.version = 0
        self._cache: dict[tuple, dict[str, list[str]]] = {}
        self._lock = threading.Lock()

    def load(self) -> None:
        """History counts (once); call refresh()/start() for the live part."""
        self.hist = features.purchase_counts()
        self.version += 1
        self._cache = {}

    def refresh(self) -> None:
        rows = client.query(f"""
            SELECT product_id::String AS p, count() AS n FROM shop.events
            WHERE event_type = 'purchase' AND ts::DateTime64(3) > now64(3) - INTERVAL {LIVE_MIN} MINUTE
            GROUP BY p""", timeout=30)
        live = Counter({r["p"]: int(r["n"]) for r in rows})
        with self._lock:
            self.live, self._cache = live, {}
            self.version += 1

    def start(self, every_s: float = 60.0) -> None:
        def run() -> None:
            while True:
                time.sleep(every_s)
                try:
                    self.refresh()
                except Exception as e:  # keep the last known counts
                    log.warning("popularity refresh failed: %s", e)

        threading.Thread(target=run, name="popularity", daemon=True).start()

    def ranked(self, group: str = "all", live_weight: float = 0.5, new_prior: bool = True) -> dict[str, list[str]]:
        """Products by score, best first, per `group` ('all' -> key '', 'category', 'subcategory')."""
        key = (group, live_weight, new_prior)
        with self._lock:
            cached = self._cache.get(key)
            live = self.live
        if cached is not None:
            return cached
        products = self.catalog.snapshot()
        hist_total = sum(self.hist.values()) or 1
        live_total = sum(live.values()) or 1
        share = {p.product_id: self.hist.get(p.product_id, 0) / hist_total for p in products}
        if new_prior:  # new products: the average history share of the existing products in their subcategory
            by_sub: dict[str, list[float]] = defaultdict(list)
            for p in products:
                if not p.is_new:
                    by_sub[p.subcategory].append(share[p.product_id])
            for p in products:
                if p.is_new and p.product_id not in self.hist and by_sub.get(p.subcategory):
                    share[p.product_id] = sum(by_sub[p.subcategory]) / len(by_sub[p.subcategory])
        w = live_weight if live else 0.0
        score = {pid: (1 - w) * s + w * live.get(pid, 0) / live_total for pid, s in share.items()}
        groups: dict[str, list[str]] = defaultdict(list)
        for p in sorted(products, key=lambda p: (-score[p.product_id], p.product_id)):
            if score[p.product_id] <= 0:
                continue  # never bought and no prior: leave out, like the history-only rankings
            k = "" if group == "all" else p.category if group == "category" else p.subcategory
            groups[k].append(p.product_id)
        result = dict(groups)
        with self._lock:
            self._cache[key] = result
        return result
