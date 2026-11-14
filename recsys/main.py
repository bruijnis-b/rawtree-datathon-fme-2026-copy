"""Entry point: keep the live catalogue in sync and answer every shop.requests record with one policy.

    python -m recsys.main --policy category_pop             # live: answers every request
    python -m recsys.main --policy category_pop --dry-run   # computes answers but sends nothing
    python -m recsys.main --policy category_pop --ab trend_boost trend_boost:mode=score,boost=2   # 3 arms, 1/3 each

Only one process may answer live at a time (the organisers count one answer per request): stop the starter
baseline or any other server first.
"""
from __future__ import annotations

import argparse
import logging
import statistics
import time
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from queue import SimpleQueue

from . import client, guard, model_registry
from .catalog import LiveCatalog
from .trends import TrendDetector
from .policies import REGISTRY, Policy, Request
from .policies.category_pop import CategoryPop

log = logging.getLogger("recsys")

PULL = """
SELECT request_id::String AS request_id, toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms,
       user_id::String AS user_id, is_new_user::Bool AS is_new_user, context.device::String AS device,
       context.region::String AS region, context.page::String AS page, recent_views
FROM shop.requests
WHERE ts::DateTime64(3) > now64(3) - INTERVAL 10 SECOND
ORDER BY ts DESC
LIMIT 500"""
"""Requests from the last 10 s; anything older is past the 3 s deadline anyway."""

STATS_EVERY_S = 30
POLL_S = 0.1          # pause between pulls of shop.requests (pushes run in the background)
PUSH_TIMEOUT_S = 3    # an insert slower than this is late anyway
DEADLINE_MS = 2000
"""By this age (request ts to now, local clock) a request has its answer, leaving ~1 s to push before the
organisers' 3000 ms deadline. recommend() runs in a worker thread; if it is not done by then, the request
gets the fallback and the slow call finishes in the background, unused (Python cannot kill a thread)."""
BATCH_BUDGET_MS = 500
"""Also wait at most this long per batch, so slow policies never stop the loop from pulling new requests."""


def pick_arm(request_id: str, bounds: list[int]) -> int:
    """Stable split: the request ID's bucket (0-99) picks the arm whose share covers it; same ID, same arm."""
    bucket = zlib.crc32(request_id.encode()) % 100
    return next(i for i, upper in enumerate(bounds) if bucket < upper)


def arm_bounds(n_arms: int, ab_share: int | None) -> list[int]:
    """Cumulative bucket bounds: each --ab arm gets ab_share percent (default: all arms equal), --policy the rest."""
    shares = [100 // n_arms] * n_arms if ab_share is None else [100 - ab_share * (n_arms - 1)] + [ab_share] * (n_arms - 1)
    shares[0] += 100 - sum(shares)
    if min(shares) <= 0:
        raise SystemExit(f"--ab-share {ab_share} leaves no requests for --policy")
    return [sum(shares[:i + 1]) for i in range(n_arms)]


def apply_settings(policy: Policy, settings: list[str]) -> None:
    """--set NAME=VALUE overrides, converted to the type of the policy's default."""
    for item in settings:
        key, _, value = item.partition("=")
        if hasattr(policy, key) and not key.startswith("_"):
            default = getattr(policy, key)
            setattr(policy, key, value.lower() in ("1", "true", "yes") if isinstance(default, bool)
                    else type(default)(value))


def fallback_items(fallback: CategoryPop, req: Request) -> list[str]:
    """Category best sellers for this request, then all-time best sellers (the guard keeps the first 10)."""
    try:
        return fallback.recommend(req) + fallback.best
    except Exception:
        return fallback.best


def push(answers: list[dict], ts_ms: list[int], pushed: SimpleQueue) -> None:
    """Insert one batch (runs in a push thread) and report the outcome to the main loop."""
    try:
        client.insert("submissions", answers, timeout=PUSH_TIMEOUT_S)
        now_ms = time.time() * 1000
        pushed.put((True, answers, [now_ms - t for t in ts_ms]))
    except Exception as e:
        log.warning("push of %d answers failed: %s", len(answers), e)
        pushed.put((False, answers, []))


def setup_logging() -> None:
    (client.ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(client.ROOT / "logs" / "recsys.log", encoding="utf-8")])


def log_stats(counts: Counter[str], ages_ms: list[float], issues: Counter[str], catalog: LiveCatalog,
              trends: TrendDetector) -> None:
    """One line per STATS_EVERY_S; WARNING if the policy proposed products it should not have."""
    p95 = lambda xs: round(statistics.quantiles(xs, n=20)[18]) if len(xs) >= 2 else None
    level = logging.WARNING if issues.keys() & {"inactive", "unknown", "emergency"} else logging.INFO
    active = {s: f"{t.lift:.1f}x" for s, t in trends.active().items()}
    log.log(level, "answered %d | push %s ms after request (p95, local clock) | deadline fallbacks %d | "
            "policy errors %d | push errors %d | guard fixes %s | catalogue %.1fs old | trends %s",
            counts["answered"], p95(ages_ms), counts["deadline_fallbacks"], counts["policy_errors"],
            counts["push_errors"], dict(issues) or "none", catalog.staleness_s(), active or "none")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", default="category_pop", choices=sorted(REGISTRY))
    ap.add_argument("--ab", nargs="*", default=[], metavar="POLICY[:NAME=VALUE,...]",
                    help="A/B test: extra policies, each with optional own settings, "
                         "e.g. --ab trend_boost trend_boost:mode=score,boost=2")
    ap.add_argument("--ab-share", type=int, help="percent of requests per --ab policy (default: all arms equal)")
    ap.add_argument("--set", nargs="*", default=[], metavar="NAME=VALUE",
                    help="override policy settings, e.g. --set mode=score boost=2 (applies where the setting exists)")
    ap.add_argument("--dry-run", action="store_true", help="compute answers but do not insert them")
    args = ap.parse_args()
    setup_logging()

    catalog = LiveCatalog()
    catalog.load()
    catalog.start()  # background thread: applies shop.catalog_updates every 0.2-1 s
    trends = TrendDetector()
    try:
        trends.load()
    except Exception as e:  # optional signal: serve without it rather than not at all
        log.warning("trend detector not loaded, it will build up from live data: %s", e)
    trends.start()  # background thread: re-checks subcategory views every minute, logs trend start/end
    # Our fallback, better than the organisers' (all-time best sellers): best sellers in the category of the
    # last viewed product, then all-time best sellers. Used to pad answers and when the policy is skipped.
    fallback = CategoryPop(catalog)
    fallback.fit()
    arms = []  # (policy, public model ID); with --ab, the request ID decides which arm answers
    for spec in [args.policy] + args.ab:
        name, _, own = spec.partition(":")
        if name not in REGISTRY:
            raise SystemExit(f"unknown policy {name!r}: choose from {sorted(REGISTRY)}")
        policy = REGISTRY[name](catalog, trends)
        apply_settings(policy, args.set + [s for s in own.split(",") if s])
        policy.fit()
        arms.append((policy, model_registry.public_id(policy, register=not args.dry_run)))
    bounds = arm_bounds(len(arms), args.ab_share)
    for i, (policy, public_id) in enumerate(arms):
        log.info("running %s %s as model_version %s, %d%% of requests%s", policy.internal_version,
                 model_registry.params(policy), public_id, bounds[i] - (bounds[i - 1] if i else 0),
                 " (DRY RUN, nothing is sent)" if args.dry_run else "")

    workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="recommend")
    pushers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="push")
    pushed: SimpleQueue = SimpleQueue()  # (ok, answers, ages_ms) from finished pushes
    seen: dict[str, float] = {}
    counts: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    ages_ms: list[float] = []
    last_stats = time.time()
    while True:
        loop_start = time.time()
        try:
            fresh = [Request.from_row(r) for r in client.query(PULL, timeout=5) if r["request_id"] not in seen]
            # Start every recommend() in a worker thread, then wait for each only until its request's deadline.
            jobs, arm_of = {}, {}
            for req in fresh:
                seen[req.request_id] = loop_start
                arm_of[req.request_id] = arms[pick_arm(req.request_id, bounds)]
                if time.time() * 1000 - req.ts_ms < DEADLINE_MS:
                    jobs[req.request_id] = workers.submit(arm_of[req.request_id][0].recommend, req)
            answers = []
            batch_end = time.time() + BATCH_BUDGET_MS / 1000
            for req in fresh:
                items: list[str] = []  # empty: the guard fills it from the fallback
                job = jobs.get(req.request_id)
                try:
                    if job is None:
                        counts["deadline_fallbacks"] += 1  # already too old when pulled
                    else:
                        wait_until = min((req.ts_ms + DEADLINE_MS) / 1000, batch_end)
                        items = job.result(timeout=max(0.0, wait_until - time.time()))
                except FuturesTimeout:  # too slow: answer with the fallback; the call finishes unused
                    job.cancel()
                    counts["deadline_fallbacks"] += 1
                except Exception:
                    counts["policy_errors"] += 1
                    if counts["policy_errors"] <= 3:  # traceback for the first few per stats window
                        log.exception("policy failed on %s", req.request_id)
                final, fixed = guard.finalize(items, catalog, fallback_items(fallback, req))
                issues.update(fixed)
                answers.append({"request_id": req.request_id, "items": final,
                                "model_version": arm_of[req.request_id][1]})

            if answers and not args.dry_run:  # push in the background: the next pull starts right away
                pushers.submit(push, answers, [r.ts_ms for r in fresh], pushed)
            elif answers:
                pushed.put((True, answers, [time.time() * 1000 - r.ts_ms for r in fresh]))

            while not pushed.empty():  # results of finished pushes
                ok, done, ages = pushed.get()
                if ok:
                    counts["answered"] += len(done)
                    ages_ms += ages
                else:  # forget them, so the next pull retries them while they are still fresh
                    counts["push_errors"] += 1
                    for a in done:
                        seen.pop(a["request_id"], None)

            if time.time() - last_stats >= STATS_EVERY_S:
                log_stats(counts, ages_ms, issues, catalog, trends)
                counts, issues, ages_ms, last_stats = Counter(), Counter(), [], time.time()
                seen = {k: v for k, v in seen.items() if v > loop_start - 60}
        except Exception as e:  # keep running: shoppers keep arriving while you sleep
            log.warning("loop error: %s", e)
            time.sleep(1)
        time.sleep(max(0.0, POLL_S - (time.time() - loop_start)))


if __name__ == "__main__":
    main()
