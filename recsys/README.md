# recsys: our real-time recommender

Answers every `shop.requests` record with 10 ranked product IDs in `team_NN.submissions`, using one
pluggable **policy** (algorithm). Every answer goes through a **guard** so it is always valid.

## Run

From the repo root, with `TEAM_ID` and `RAWTREE_API_KEY` in `.env` (only needs `requests`):

```bash
python -m recsys.main --policy coview --dry-run
```

`--dry-run` computes answers against the live stream but sends nothing: use it to try a policy while
another process is serving. To answer live, **stop any other server first** (the starter baseline too):
the organisers count one answer per request.

```bash
python -m recsys.main --policy coview
```

Logs go to the console and `logs/recsys.log`. Every 30 s, one line: answers sent, push time after the
request (p95, local clock), deadline fallbacks, policy and push errors, what the guard had to fix, and catalogue freshness. It is
a WARNING when a policy proposed inactive or unknown products (it works from stale data). Also logged: the
first 3 policy crashes per 30 s with traceback (those requests still get the fallback), and every
catalogue update batch with how many seconds after its `ts` we applied it.

Right after startup the push-time p95 is high for one window: it answers the backlog of the last 10 s,
some already past the deadline.

## Reliability safeguards

Reliability (share of requests answered validly within 3000 ms) is scored, so `main.py` never lets a
request go unanswered or late because of the policy:

- **Fallback:** `category_pop` (best sellers in the category of the last viewed product), then all-time best
  sellers. Better than the organisers' fallback, which is all-time best sellers only.
- **Deadline:** `recommend()` runs in a pool of 4 worker threads. The loop waits for each answer only until
  the request is `DEADLINE_MS = 2000` old (request `ts` to now, local clock), and at most
  `BATCH_BUDGET_MS = 500` per batch, so a slow policy never stops it pulling new requests. Whatever is not
  ready by then gets the fallback; the slow call finishes in the background, unused (Python cannot kill a
  thread). Tested with a policy that blocks for 3 s on 2 of every 3 requests: answers still went out within
  ~2 s (p95). Watch `deadline fallbacks` in the log: near 0 normally (right after startup, the backlog of
  old requests falls back, as expected). If this machine's clock ran seconds ahead of RawTree's, many
  requests would fall back.
- **Background push:** answers are inserted by a push thread, so the next pull of `shop.requests` starts
  right away instead of waiting ~0.3-0.5 s for the insert; pulls run every 0.1 s (`POLL_S`). A failed or
  slow (>3 s, `PUSH_TIMEOUT_S`) insert is retried on the next pull while the request is still fresh.
- **Policy crash:** that request gets the fallback.
- **Guard:** every answer is padded from the fallback to exactly 10 distinct, active products.

## Layout

| File | What it does |
|---|---|
| `main.py` | Entry point: loads and syncs the catalogue, fits the policy, then loops: pull recent requests, `policy.recommend` (worker threads, with deadline), `guard.finalize`, batch insert (push thread) |
| `catalog.py` | `LiveCatalog`: the current catalogue in memory, kept in sync with `shop.catalog_updates` |
| `trends.py` | `TrendDetector`: which subcategories are trending right now, from `shop.events` |
| `guard.py` | Exactly 10 distinct, active IDs; pads from the fallback; reports what it fixed |
| `model_registry.py` | Opaque public `model_version` IDs and the private log of what they mean |
| `features.py` | Signals computed in RawTree SQL: purchase counts, rankings, co-views |
| `client.py` | RawTree HTTP client (query, insert) |
| `policies/` | One file per algorithm, registered in `policies/__init__.py` |

### Live catalogue

`shop.catalog` is loaded once; a background thread then fetches only the updates from the last 5 minutes
before the newest `ts` seen, and applies them. All updates are timestamped on whole minutes (stock changes
every 5 minutes), so it polls every 0.2 s from second 58 to 12 of each minute and every 1 s otherwise.
Each update row is the full product after the change, so applying it means replacing the product. Two details from the data:

- Updates sit on round minutes and one product can get two at the same `ts` (e.g. `price_change` and
  `back_in_stock`, where the price row still says inactive). Within one product and `ts`, stock changes
  win: `new_product` < `price_change` < `out_of_stock` / `back_in_stock`.
- Each product remembers the (`ts`, priority) of its last applied update, so re-reading the overlap
  window, or a row arriving late, never rolls a product back.

Checked against a SQL `argMax` over all updates: identical stock and price for every updated product.
Lookups take ~0.1 µs; a sync takes ~0.2 s and never blocks serving. Products added during the event are
flagged `is_new` (that makes a request "cold" for scoring).

### Trend detection

On the practice day one subcategory at a time got ~4x the views and ~10x the purchases for exactly 45
minutes, every 2 hours (Aquariums 09:30, Kettles 11:30, Cutting Boards 13:30, Bike Helmets 15:30 UTC).
`TrendDetector` finds these live: every minute it compares each subcategory's views in the last 3 minutes
with its normal share (the higher of its 60-day history share and its median over the previous 2 hours).
A trend starts after 2 checks in a row with lift >= 2.5, z >= 8 and >= 30 views, and ends when the lift
falls below 1.6. Thresholds are the constants at the top of `trends.py`.

`main.py` runs it in a background thread, logs every trend start and end, and adds the active trends to
the 30 s stats line. Policies read it as `self.trends.active()` (used by `trend_boost`). Replay today's
stream through it, the same code, to check changes:

```bash
python -m recsys.trends
```

Replayed on the practice day: 4 of 4 trends found 1-3 min after they started, ended 1-2 min after their
real end, 0 false alarms. Tuned on these 4 events only: the final round's trends may differ.

## Policies

| Name | Idea |
|---|---|
| `baseline` | All-time best sellers, same for everyone (the organisers' baseline; the score's 0 point) |
| `category_pop` | Best sellers in the category of the last viewed product; all-time best sellers without views |
| `coview` | Products viewed in the same sessions as the recent views (recent views weigh more), then `category_pop` |
| `trend_boost` | Wraps another policy (`base`, default `coview`); while a subcategory is trending, mixes in its best sellers (below) |

### Trend boost: tunable settings

`trend_boost` returns the base list unchanged when nothing is trending. During a trend it adds the trending
subcategory's best sellers (in stock, at most `per_brand` per brand), in one of three ways (`mode`):

| `mode` | What it does | Settings (default) |
|---|---|---|
| `slots` | Same number of trend products for everyone | `n_slots` (2), `slot` (1 = first position) |
| `context` (default) | Depends on the shopper: last viewed the trending subcategory / no views / other | `n_related` (4), `n_home` (3), `n_other` (1), `slot` (1) |
| `score` | Base rank r scores 1/(r+1), trend rank t adds `boost`/(t+1); sorted by total | `boost` (1.0: top trend product ties the base's first; 0 = off) |

Shared settings: `base` (policy to wrap, default `coview`) and `per_brand` (2). Settings of other modes are
ignored. Notes:

- Trend products already in the base list are moved to the trend positions, never duplicated.
- With several trends at once, the strongest (highest lift) comes first.
- The defaults are guesses, not yet tested: the A/B tests are there to find better values.
- `--set` changes `trend_boost`'s own settings, not those of the wrapped policy (e.g. `coview`'s `decay`).

Tune without editing code; every combination gets its own public model ID:

```bash
python -m recsys.main --policy trend_boost --set mode=score boost=0.5
```

### A/B tests

`--ab` adds extra policies (arms), each optionally with its own settings after a colon. Every request is
answered by exactly one arm, picked from its request ID (stable), and each arm sends its own public model
ID, so the dashboard compares them per `model_version`. By default all arms get an equal share;
`--ab-share N` gives each `--ab` arm N% and `--policy` the rest. `--set` applies to every arm.

```bash
python -m recsys.main --policy coview --ab trend_boost trend_boost:mode=score,boost=2
```

Each request shows one arm's list, so we only see that arm's result: the comparison is between groups of
similar requests, not within a request. More arms means fewer requests each. At ~0.75% purchases, telling
two arms apart takes roughly 8,500 requests each for a +50% difference and 53,000 for +20% (a night is
~170,000 requests in total); clicks (~2.5%) need about a third of that. For `trend_boost` vs its base,
compare only requests during trend windows: outside them both answer the same.

### Public model IDs (never leak our approach)

The `model_version` we send must reveal nothing, so it is a random ID like `m3f9a2c`. `model_registry.py`
creates one the first time a policy runs live with a new combination of name, version and parameters, and
logs what it means (internal name, parameters, description, git commit, first live time) in
`model_versions.json`. Dry runs register nothing. The dashboard's per-`model_version` split shows these IDs;
look them up with `python -m recsys.model_registry`. Never send `Policy.internal_version` or any descriptive
string to a table others might read.

### Adding a policy

1. Create `policies/my_policy.py` with a `Policy` subclass: set `name` and `version` (internal only), put
   tunable settings in class attributes (they are logged with the public ID), load what it needs
   in `fit()` (runs once at startup), and return a ranked list in `recommend(req)` (must take a few ms).
   It may return any number of IDs, duplicates or inactive ones: the guard cleans and pads.
2. Add the class to `REGISTRY` in `policies/__init__.py`.
3. Try it with `--dry-run`, then serve it.

`req` is a `Request`: `request_id`, `ts_ms`, `user_id`, `is_new_user`, `device`, `region`, `page`, and
`recent_views` (product IDs, oldest first). `self.catalog` gives the live product state.
