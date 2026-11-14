"""Live, in-memory view of the product catalogue.

Load `shop.catalog` once, then every second fetch only the `shop.catalog_updates` rows near or after the
last timestamp seen and apply them. Every update row carries the full product state after the change, so
applying a row means replacing the product. Lookups are plain dict reads (well under a millisecond).

Ordering rules, from the data:
- Updates are timestamped on round minutes, and one product can get two updates with the same `ts`
  (e.g. `price_change` + `back_in_stock` at 12:30, where the price row still says inactive). Within one
  product and `ts`, stock changes win: new_product < price_change < out_of_stock/back_in_stock.
- Rows may land after we polled past their `ts`, so each poll re-reads an overlap window and every product
  remembers the (ts, priority) of its last applied row; older or equal rows are skipped.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from . import client

log = logging.getLogger(__name__)

PRIORITY = {"new_product": 0, "price_change": 1, "out_of_stock": 2, "back_in_stock": 2}
OVERLAP_S = 300  # re-read the last 5 minutes of updates on every poll
_TS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?$")

FIELDS = """product_id::String AS product_id, category::String AS category, subcategory::String AS subcategory,
       brand::String AS brand, price_eur::Float64 AS price_eur, is_active::Bool AS is_active,
       created_at::String AS created_at, description::String AS description"""


@dataclass(frozen=True)
class Product:
    product_id: str
    category: str
    subcategory: str
    brand: str
    price_eur: float
    is_active: bool
    created_at: str
    description: str
    is_new: bool = False  # added during the event (a `new_product` update): makes a request "cold"


class LiveCatalog:
    def __init__(self) -> None:
        self.products: dict[str, Product] = {}
        self._applied: dict[str, tuple[str, int]] = {}  # product_id -> (ts, priority) of last applied update
        self.cursor: str | None = None  # max update ts seen, as 'YYYY-MM-DD HH:MM:SS.fffffffff'
        self.last_sync = 0.0
        self.version = 0  # bumps whenever something changed; policies can use it to refresh caches
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ---- reads (called per request) -------------------------------------------------------------
    def get(self, product_id: str) -> Product | None:
        return self.products.get(product_id)

    def is_active(self, product_id: str) -> bool:
        p = self.products.get(product_id)
        return p is not None and p.is_active

    def snapshot(self) -> list[Product]:
        """All products, copied under the lock (the sync thread may be adding new ones)."""
        with self._lock:
            return list(self.products.values())

    def active_ids(self) -> list[str]:
        return [p.product_id for p in self.snapshot() if p.is_active]

    def new_ids(self) -> list[str]:
        return [p.product_id for p in self.snapshot() if p.is_new]

    # ---- loading and syncing ------------------------------------------------------------------
    def load(self) -> None:
        """Full load: base catalogue plus every update so far."""
        rows = client.query(f"SELECT {FIELDS} FROM shop.catalog")
        with self._lock:
            self.products = {r["product_id"]: _product(r) for r in rows}
            self._applied.clear()
            self.cursor = None
        self.sync()
        log.info("catalogue loaded: %d products, %d active, %d new",
                 len(self.products), len(self.active_ids()), len(self.new_ids()))

    def sync(self) -> int:
        """Fetch and apply updates since the cursor (with overlap). Returns how many rows changed state."""
        where = ""
        if self.cursor:
            assert _TS.match(self.cursor), self.cursor  # our own value from the DB, checked before it goes into SQL
            where = f"WHERE ts::DateTime64(3) >= toDateTime64('{self.cursor[:23]}', 3) - INTERVAL {OVERLAP_S} SECOND"
        rows = client.query(f"""
            SELECT {FIELDS}, ts::String AS ts, change::String AS change
            FROM shop.catalog_updates {where}
            ORDER BY ts""")
        rows.sort(key=lambda r: (r["ts"], PRIORITY.get(r["change"], 1)))
        first_load = self.cursor is None
        changed = 0
        new_batches: dict[str, Counter[str]] = defaultdict(Counter)  # update ts -> changes seen for the first time
        with self._lock:
            for r in rows:
                key = (r["ts"], PRIORITY.get(r["change"], 1))
                pid = r["product_id"]
                if pid in self._applied and key <= self._applied[pid]:
                    continue
                old = self.products.get(pid)
                is_new = r["change"] == "new_product" or (old is not None and old.is_new)
                self.products[pid] = _product(r, is_new=is_new)
                self._applied[pid] = key
                changed += 1
                new_batches[r["ts"]][r["change"]] += 1
                if self.cursor is None or r["ts"] > self.cursor:
                    self.cursor = r["ts"]
            if changed:
                self.version += 1
        self.last_sync = time.time()
        if not first_load:
            # How late do we see updates? Lag = now minus the update's ts (local clock, so include skew).
            for ts, changes in sorted(new_batches.items()):
                lag = self.last_sync - datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc).timestamp()
                log.info("catalogue: applied %s from %s UTC, %.1fs after their ts", dict(changes), ts[:19], lag)
        return changed

    def start(self, every_s: float = 1.0, fast_every_s: float = 0.2) -> None:
        """Keep syncing in a background thread, so the serving loop never waits on it.

        Every update so far is timestamped on a whole minute (stock changes every 5 minutes), so around
        minute boundaries (local second 58 to 12) we poll every `fast_every_s`, and every `every_s` otherwise.
        The margin covers a few seconds of clock skew between this machine and RawTree.
        """
        def run() -> None:
            while True:
                second = time.time() % 60
                time.sleep(fast_every_s if (second >= 58 or second < 12) else every_s)
                try:
                    self.sync()
                except Exception as e:  # keep the last known state; try again next tick
                    log.warning("catalogue sync failed: %s", e)

        self._thread = threading.Thread(target=run, name="catalog-sync", daemon=True)
        self._thread.start()

    def staleness_s(self) -> float:
        return time.time() - self.last_sync if self.last_sync else float("inf")


def _product(r: dict, is_new: bool = False) -> Product:
    return Product(
        product_id=r["product_id"], category=r["category"], subcategory=r["subcategory"], brand=r["brand"],
        price_eur=float(r["price_eur"]), is_active=bool(r["is_active"]), created_at=r["created_at"],
        description=r["description"], is_new=is_new,
    )
