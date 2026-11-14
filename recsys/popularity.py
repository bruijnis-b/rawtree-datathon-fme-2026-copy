"""Product popularity: 60 days of history blended with the last hour of live purchases.

    score = (1 - live_weight) x history share + live_weight x live share

- history share: the product's share of all purchases in shop.history_events. A product added during the
  event has none; with `new_prior` it gets the average history share of the existing products in its
  subcategory, so it ranks like a typical product there instead of last.
- live share: its share of purchases in shop.events over the last LIVE_MIN minutes, refreshed every minute.
  This is where new products earn their place, and where trends and sales show up. Minutes a product was
  out of stock in the window count at its history rate: stock-outs last 60 min and demand comes back at the
  same level (0.98x views, 0.99x purchases over 222 stock-outs), so otherwise a product that just returned
  would rank too low for up to an hour.

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
        self.out_minutes: dict[str, float] = {}  # minutes out of stock within the live window
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
        out = self._out_of_stock_minutes()
        with self._lock:
            self.live, self.out_minutes, self._cache = live, out, {}
            self.version += 1

    def _out_of_stock_minutes(self) -> dict[str, float]:
        """Minutes each product was out of stock within the live window (stock-outs last 60 min, so looking
        back LIVE_MIN + 120 min also finds ones that started before the window)."""
        rows = client.query(f"""
            SELECT product_id::String AS p, change::String AS ch, toUnixTimestamp(ts::DateTime64(3)) AS t,
                   toUnixTimestamp(now64(3)) AS now
            FROM shop.catalog_updates
            WHERE change::String IN ('out_of_stock', 'back_in_stock')
              AND ts::DateTime64(3) > now64(3) - INTERVAL {LIVE_MIN + 120} MINUTE
            ORDER BY p, t""", timeout=30)
        out: dict[str, float] = {}
        since: dict[str, float] = {}
        for r in rows:
            now, start = float(r["now"]), float(r["now"]) - LIVE_MIN * 60
            if r["ch"] == "out_of_stock":
                since[r["p"]] = float(r["t"])
            elif r["p"] in since:
                a, b = max(since.pop(r["p"]), start), min(float(r["t"]), now)
                if b > a:
                    out[r["p"]] = out.get(r["p"], 0.0) + (b - a) / 60
        if rows:
            now = float(rows[0]["now"])
            for p, t in since.items():  # still out of stock
                out[p] = out.get(p, 0.0) + (now - max(t, now - LIVE_MIN * 60)) / 60
        return out

    def start(self, every_s: float = 60.0) -> None:
        def run() -> None:
            while True:
                time.sleep(every_s)
                try:
                    self.refresh()
                except Exception as e:  # keep the last known counts
                    log.warning("popularity refresh failed: %s", e)

        threading.Thread(target=run, name="popularity", daemon=True).start()

    def scores(self, live_weight: float = 0.5, new_prior: bool = True) -> dict[str, float]:
        """Score per product (shares, so they sum to ~1): see the module docstring."""
        key = ("scores", live_weight, new_prior)
        with self._lock:
            cached = self._cache.get(key)
            live, out_minutes = self.live, self.out_minutes
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
        # A product that was out of stock in the window sold nothing then, through no lack of demand (and
        # demand returns at the same level afterwards): count those minutes at its history rate instead.
        live = Counter(live)
        for pid, minutes in out_minutes.items():
            if pid in share:
                live[pid] += min(minutes, LIVE_MIN) / LIVE_MIN * share[pid] * live_total
        w = live_weight if live else 0.0
        score = {pid: (1 - w) * s + w * live.get(pid, 0) / live_total for pid, s in share.items()}
        with self._lock:
            self._cache[key] = score
        return score

    def ranked(self, group: str = "all", live_weight: float = 0.5, new_prior: bool = True) -> dict[str, list[str]]:
        """Products by score, best first, per `group` ('all' -> key '', 'category', 'subcategory')."""
        key = (group, live_weight, new_prior)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        score = self.scores(live_weight, new_prior)
        groups: dict[str, list[str]] = defaultdict(list)
        for p in sorted(self.catalog.snapshot(), key=lambda p: (-score.get(p.product_id, 0.0), p.product_id)):
            if score.get(p.product_id, 0.0) <= 0:
                continue  # never bought and no prior: leave out, like the history-only rankings
            k = "" if group == "all" else p.category if group == "category" else p.subcategory
            groups[k].append(p.product_id)
        result = dict(groups)
        with self._lock:
            self._cache[key] = result
        return result
