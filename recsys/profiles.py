"""Live shopper profiles from shop.events: what each shopper looks at, has in the cart and has bought.

shop.events holds the shoppers' other sessions (not the one a request comes from), each written in one
burst. 95% of requests come from a shopper with earlier events that day (median ~20 views), `is_new_user`
shoppers included: for them it is the only profile there is. Measured on 79,000 of our answers (practice
day), purchase rate per shown product, average 0.076%:

- in the shopper's cart, not bought: 1.07%; already bought that day: 0.03%
- in a category with 60%+ of the shopper's event views: 0.46%; in a category never viewed: 0.03%

A background thread reads the events in time order: first the last BACKFILL_H hours in 30-minute steps,
then every POLL_S seconds up to LAG_S seconds ago (rows may land slightly late).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from . import client
from .catalog import LiveCatalog

log = logging.getLogger(__name__)

BACKFILL_H = 12   # hours of events read at startup
STEP_MIN = 30     # at most this many minutes of events per query (~120,000 rows)
POLL_S = 2.0      # pause between reads once caught up
LAG_S = 3         # read up to this many seconds ago


@dataclass
class Profile:
    views: int = 0
    categories: Counter[str] = field(default_factory=Counter)     # views per category
    subcategories: Counter[str] = field(default_factory=Counter)  # views per subcategory
    cart: dict[str, int] = field(default_factory=dict)            # product -> time added (ms)
    bought: set[str] = field(default_factory=set)

    def open_cart(self) -> list[str]:
        """Products in the cart and not bought, most recently added first."""
        return [p for p in sorted(self.cart, key=lambda p: -self.cart[p]) if p not in self.bought]


class Profiles:
    def __init__(self, catalog: LiveCatalog) -> None:
        self.catalog = catalog
        self.users: dict[str, Profile] = {}
        self.cursor_ms = 0   # events up to here are in the profiles (RawTree clock)
        self.offset_ms = 0   # RawTree clock minus local clock
        self._lock = threading.Lock()

    def get(self, user_id: str) -> Profile | None:
        """A copy of the shopper's profile (safe to read while the sync thread writes), or None."""
        with self._lock:
            p = self.users.get(user_id)
            return None if p is None else Profile(p.views, Counter(p.categories), Counter(p.subcategories),
                                                  dict(p.cart), set(p.bought))

    def staleness_s(self) -> float:
        return (time.time() * 1000 + self.offset_ms - self.cursor_ms) / 1000

    def _now_ms(self) -> int:
        return int(time.time() * 1000 + self.offset_ms)

    def sync(self) -> bool:
        """Read the next step of events; True when caught up."""
        upper = min(self.cursor_ms + STEP_MIN * 60_000, self._now_ms() - LAG_S * 1000)
        if upper <= self.cursor_ms:
            return True
        rows = client.query(f"""
            SELECT toUnixTimestamp64Milli(ts::DateTime64(3)) AS t, user_id::String AS u,
                   product_id::String AS p, event_type::String AS e
            FROM shop.events
            WHERE ts::DateTime64(3) > fromUnixTimestamp64Milli({self.cursor_ms})
              AND ts::DateTime64(3) <= fromUnixTimestamp64Milli({upper})""", timeout=30)
        with self._lock:
            for r in rows:
                prof = self.users.get(r["u"])
                if prof is None:
                    prof = self.users[r["u"]] = Profile()
                if r["e"] == "view":
                    product = self.catalog.get(r["p"])
                    if product is not None:
                        prof.views += 1
                        prof.categories[product.category] += 1
                        prof.subcategories[product.subcategory] += 1
                elif r["e"] == "add_to_cart":
                    prof.cart[r["p"]] = int(r["t"])
                elif r["e"] == "purchase":
                    prof.bought.add(r["p"])
            self.cursor_ms = upper
        return upper >= self._now_ms() - LAG_S * 1000 - 1000

    def start(self) -> None:
        """Background thread: backfill, then keep up. Policies work without profiles until it has caught up."""
        def run() -> None:
            caught_up = False
            while True:
                try:
                    if not self.cursor_ms:
                        db_now = int(client.query("SELECT toUnixTimestamp64Milli(now64(3)) AS t")[0]["t"])
                        self.offset_ms = db_now - int(time.time() * 1000)
                        self.cursor_ms = db_now - BACKFILL_H * 3_600_000
                    done = self.sync()
                    if done and not caught_up:
                        log.info("shopper profiles caught up: %d shoppers", len(self.users))
                    caught_up = caught_up or done
                    if done:
                        time.sleep(POLL_S)
                except Exception as e:  # keep the profiles we have
                    log.warning("shopper profile sync failed: %s", e)
                    time.sleep(POLL_S)

        threading.Thread(target=run, name="profiles", daemon=True).start()
