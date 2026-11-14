"""Live trend detector: which subcategories are getting far more views than usual right now.

On the practice day, one subcategory at a time got ~4x the views (and ~10x the purchases) for exactly
45 minutes, every 2 hours. Every minute, for each subcategory:

    views in the last 3 complete minutes  vs  expected = (all views in those minutes) x normal share

normal share = max(history share, median per-minute share over the 2 hours before the window). The median
keeps a running trend from raising its own baseline; the history floor keeps a stock-out from dragging it
to zero. A trend starts after 2 checks in a row with lift >= 2.5, z >= 8 and >= 30 views, and ends when the
lift (against the share frozen at its start) drops below 1.6. Replayed on the practice day up to 16:30 UTC:
4 of 4 trends found 1-3 min after they started, ended 1-2 min after their real end, 0 false alarms.

    python -m recsys.trends     # replay today's stream and print the trends it finds
"""
from __future__ import annotations

import logging
import math
import statistics
import threading
import time
from collections import Counter
from dataclasses import dataclass

from . import client

log = logging.getLogger(__name__)

WINDOW_MIN = 3     # minutes of views compared
BASE_MIN = 120     # minutes of history for the median share
RATIO_ON = 2.5     # lift needed to start a trend ...
Z_ON = 8.0         # ... clearly above noise (Poisson z-score) ...
MIN_VIEWS = 30     # ... with enough views to mean something ...
PERSIST = 2        # ... for this many checks in a row
RATIO_OFF = 1.6    # lift below which a trend ends

# Product -> subcategory, including products added during the event.
_SUBCATS = """(SELECT product_id::String AS pid, any(subcategory::String) AS sub FROM (
    SELECT product_id, subcategory FROM shop.catalog
    UNION ALL SELECT product_id, subcategory FROM shop.catalog_updates WHERE change::String = 'new_product')
  GROUP BY pid)"""


@dataclass
class Trend:
    subcategory: str
    started: str    # first minute of the window that confirmed it (UTC, 'YYYY-MM-DD HH:MM:SS')
    lift: float     # latest views / expected
    views: int      # views in the latest window
    base_share: float  # normal share when it started; frozen, so the trend cannot raise its own baseline


class TrendDetector:
    def __init__(self) -> None:
        self.hist_share: dict[str, float] = {}
        self.minutes: dict[str, Counter[str]] = {}  # complete minute -> views per subcategory
        self.checked: str | None = None             # last minute evaluated
        self.streak: Counter[str] = Counter()       # consecutive checks over the start threshold
        self._active: dict[str, Trend] = {}
        self._lock = threading.Lock()

    # ---- read by the recommender ----------------------------------------------------------------
    def active(self) -> dict[str, Trend]:
        """Subcategories trending right now (a copy, safe to use from any thread)."""
        with self._lock:
            return dict(self._active)

    # ---- data -------------------------------------------------------------------------------------
    def load(self) -> None:
        """History shares, plus the last BASE_MIN minutes of live views so the detector is ready at once."""
        rows = client.query(f"""
            SELECT k.sub AS sub, count() AS v FROM shop.history_events AS e
            INNER JOIN {_SUBCATS} AS k ON k.pid = e.product_id::String
            WHERE e.event_type = 'view' GROUP BY sub""", timeout=120)
        total = sum(int(r["v"]) for r in rows)
        self.hist_share = {r["sub"]: int(r["v"]) / total for r in rows}
        self._fetch(f"now64(3) - INTERVAL {BASE_MIN + WINDOW_MIN + 2} MINUTE", evaluate=False)
        log.info("trend detector ready: %d subcategories, %d minutes of live views",
                 len(self.hist_share), len(self.minutes))

    def _fetch(self, since_sql: str, evaluate: bool = True) -> list[tuple[str, str, Trend]]:
        """Load complete minutes since `since_sql` (re-reading recent ones: views arrive up to ~2 s late)."""
        rows = client.query(f"""
            SELECT k.sub AS sub, toString(toStartOfMinute(e.ts::DateTime64(3))) AS m, count() AS v
            FROM shop.events AS e INNER JOIN {_SUBCATS} AS k ON k.pid = e.product_id::String
            WHERE e.event_type = 'view' AND e.ts::DateTime64(3) >= {since_sql}
              AND toStartOfMinute(e.ts::DateTime64(3)) < toStartOfMinute(now64(3) - INTERVAL 10 SECOND)
            GROUP BY sub, m""", timeout=60)
        fresh: dict[str, Counter[str]] = {}
        for r in rows:
            fresh.setdefault(r["m"], Counter())[r["sub"]] = int(r["v"])
        self.minutes.update(fresh)
        events = []
        for m in sorted(self.minutes):
            if self.checked is None or m > self.checked:
                if evaluate:
                    events += self.step(m)
                self.checked = m
        return events

    def sync(self) -> list[tuple[str, str, Trend]]:
        """Fetch the latest minutes and evaluate each new one. Returns (event, minute, trend) changes."""
        events = self._fetch(f"now64(3) - INTERVAL {WINDOW_MIN + 2} MINUTE")
        for m in sorted(self.minutes)[:-(BASE_MIN + WINDOW_MIN + 5)]:  # keep only what the median needs
            del self.minutes[m]
        for kind, m, t in events:
            if kind == "start":
                log.info("trend started: %s (%.1fx views, %d in %d min, window from %s UTC)",
                         t.subcategory, t.lift, t.views, WINDOW_MIN, t.started)
            else:
                log.info("trend ended: %s (lift %.1fx at %s UTC)", t.subcategory, t.lift, m)
        return events

    # ---- detection --------------------------------------------------------------------------------
    def step(self, minute: str) -> list[tuple[str, str, Trend]]:
        """Evaluate the window ending at `minute` (inclusive). Pure in-memory: also used by the replay."""
        keys = sorted(m for m in self.minutes if m <= minute)
        window, before = keys[-WINDOW_MIN:], keys[-(WINDOW_MIN + BASE_MIN):-WINDOW_MIN]
        if len(window) < WINDOW_MIN:
            return []
        views = sum((self.minutes[m] for m in window), Counter())
        total = sum(views.values())
        totals_before = [(self.minutes[m], sum(self.minutes[m].values())) for m in before]
        events = []
        with self._lock:
            for sub in set(self.hist_share) | set(views):
                if sub in self._active:  # running trend: compare against its frozen baseline
                    trend = self._active[sub]
                    trend.lift, trend.views = views[sub] / (trend.base_share * total), views[sub]
                    if trend.lift < RATIO_OFF:
                        events.append(("end", minute, self._active.pop(sub)))
                    continue
                shares = [c[sub] / t for c, t in totals_before if t]
                median = statistics.median(shares) if len(shares) >= 10 else 0.0
                base_share = max(median, self.hist_share.get(sub, 0.0))
                expected = base_share * total
                if expected <= 0:
                    continue
                lift = views[sub] / expected
                z = (views[sub] - expected) / math.sqrt(max(expected, 1.0))
                hit = lift >= RATIO_ON and z >= Z_ON and views[sub] >= MIN_VIEWS
                self.streak[sub] = self.streak[sub] + 1 if hit else 0
                if self.streak[sub] >= PERSIST:
                    self._active[sub] = Trend(sub, window[0], lift, views[sub], base_share)
                    events.append(("start", minute, self._active[sub]))
        return events

    def start(self, every_s: float = 10.0) -> None:
        """Keep checking in a background thread (a new minute is evaluated ~10 s after it ends)."""
        def run() -> None:
            while True:
                time.sleep(every_s)
                try:
                    self.sync()
                except Exception as e:  # keep the last known trends; try again next tick
                    log.warning("trend check failed: %s", e)

        threading.Thread(target=run, name="trend-detector", daemon=True).start()


def replay() -> None:
    """Run the detector over today's whole stream, minute by minute, and print what it finds."""
    det = TrendDetector()
    det.load()
    det.minutes.clear()
    det._fetch("toStartOfDay(now64(3))", evaluate=False)
    det.checked = None
    for m in sorted(det.minutes):
        for kind, at, t in det.step(m):
            print(f"{at[11:16]} UTC  {kind:<5}  {t.subcategory:<20} lift {t.lift:.1f}x  ({t.views} views / {WINDOW_MIN} min)")
    print("active now:", {s: f"{t.lift:.1f}x since {t.started[11:16]}" for s, t in det.active().items()} or "none")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    replay()
