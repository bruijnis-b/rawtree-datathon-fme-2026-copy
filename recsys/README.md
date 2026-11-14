# recsys: our real-time recommender

Answers every `shop.requests` record with 10 ranked product IDs in `team_NN.submissions`, using one
pluggable **policy** (algorithm). Every answer goes through a **guard** so it is always valid.

## Run

From the repo root, with `TEAM_ID` and `RAWTREE_API_KEY` in `.env` (only needs `requests`):

```bash
python -m recsys.main --policy category_pop --dry-run
```

`--dry-run` computes answers against the live stream but sends nothing: use it to try a policy while
another process is serving. To answer live, **stop any other server first** (the starter baseline too):
the organisers count one answer per request.

```bash
python -m recsys.main --policy category_pop
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
| `popularity.py` | `Popularity`: best-seller rankings from history plus the last hour of live purchases, with new products included |
| `profiles.py` | `Profiles`: per shopper, the categories viewed, the cart and the purchases, from `shop.events` and `shop.history_events` |
| `embeddings.py` | `Embeddings`: embedding models as a shared service, per request a purchase log-odds per product; model selection, download and publish (below) |
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

### Popularity (history + live, new products included)

Every best-seller ranking (`category_pop`, the trend and discount candidates, our fallback) comes from one
shared `Popularity`:

    score = (1 - live_weight) x history share + live_weight x share of purchases in the last 60 min

- History share: the product's share of all purchases in `shop.history_events` (60 days).
- Live share: its share of purchases in `shop.events` over the last 60 minutes, re-counted every minute in a
  background thread. Trends and sales show up here, and new products earn their place within minutes.
- New products have no history. With `new_prior` they start at the average history share of the existing
  products in their subcategory: they sell like average products from their first minute (practice day),
  and always use an existing subcategory, category and brand.
- Stock-outs: minutes a product was out of stock in the live window count at its history rate. Stock-outs
  last exactly 60 min and demand comes back at the same level (0.98x views, 0.99x purchases over 222
  stock-outs, no catch-up spike), so without this a product that just returned ranked too low for up to an
  hour (`category_pop` v3).

Default `live_weight` 0.5 (a setting of `category_pop`, `trend_boost` and `discount_boost`). With history only,
none of the 200 new products of the practice day was ever recommended; with the defaults all 200 are ranked
and ~6 reach a category's top 30. Rankings are rebuilt once per refresh (~4 ms) and cached.

### Shopper profiles (shop.events)

`shop.events` holds the shoppers' other sessions, not the one a request comes from (a request's
`recent_views` are not in it). 95% of requests come from a shopper with earlier events that day (median ~20
views), `is_new_user` shoppers included. `Profiles` keeps, per shopper: views per category and subcategory,
cart and purchases. A background thread reads the last 12 hours at startup (~25 s; policies work without
profiles until then), then new events every 2 s, up to 3 s ago. The stats line shows how many profiles
there are and how old the newest event read is.

Measured on 79,000 of our answers (practice day; 598 purchases, so indicative), purchase rate per shown
product, average 0.076%:

| Shown product is | Purchase rate |
|---|---|
| In the shopper's cart, not bought | 1.07% |
| One of the request's `recent_views` | 0.74% |
| In a category with 60%+ of the shopper's event views | 0.46% |
| In a category the shopper never viewed | 0.03% |
| Already bought by the shopper that day | 0.03% |

The last viewed product is in the shopper's most viewed category only 25% of the time.

A second thread loads the same from the 60 days of `shop.history_events`, once (~35 s, 60,000 shoppers);
`get()` returns history and live together. This part does not depend on the live stream, so it is there
from the first minute of the final round. Checked on the practice day's live feedback:

- Products the shopper bought in the history: bought again 3 times in 39,000 showings (0.008%). The old
  carousel log (`history_sessions`) says the opposite (1.47%): for repeat purchases the live shop behaves
  differently from the history, so check such findings on live feedback. `category_pop` spends ~9% of
  its slots on these products.
- History cart-not-bought products: 0.44%. History view shares predict as well as the live ones.

`events(user_id)` gives the shopper's last 50 events (view, add_to_cart, purchase) in time order: the last
50 of `shop.history_events`, then the live ones. This is the sequence the embedding models were trained on.

### Embedding models (embeddings.py)

Jules's models score every product for a request: **the log-odds that the shopper buys it when shown in slot 1**.
Any policy gets one with `self.embedding_model(name)` in `fit()`. That is one shared copy per process, loaded on
first use (~1 s), with new products embedded within ~0.2 s of their `new_product` update.

```python
s = self.embedding_model(self.embed_model).scores(req)   # Scores: s.ids, s.values, s.index
s.get(pid); s.aligned(my_ids); s.top(10)                  # one product, your own order, best in stock
model.similar(pid, 20)                                    # nearest products by embedding
```

What the model covers: product content and identity, original price, the request context, its recent views,
and the shopper's events. Users in the history get their history; once they have live events, the model gets
their history tail plus the live events, exactly as in training. Do not correct for those again. What it does
not cover: current discounts, trends, cart and bought-before. Corrections go on top, on the log-odds scale (or as
odds multipliers: `exp(score) x factor`).

**Choosing a model.** Models are folders under `models/` (gitignored). `recsys/embed_models.json` (tracked) lists
each one with its checksums and its GitHub release, and names the `default`. Policies built on a model have an
`embed_model` setting (`''` = default). It is resolved to the real name at startup, so each model gets its own
public ID.

```bash
python -m recsys.embeddings list              # models, downloaded or not, * = default
python -m recsys.embeddings fetch v0          # download from its GitHub release (needs gh, logged in)
python -m recsys.main --policy embed_score --set embed_model=v1 --dry-run
python -m recsys.main --policy embed_score --ab embed_score:embed_model=v1    # A/B: default vs v1
python -m recsys.embeddings publish models/v1 --name v1 [--default]   # Jules: upload a new model
```

A model is 2 MB of weights plus ~18 MB of user vectors: too big to commit one per version, so each one is a
release asset of this (private) repo. A name never changes content: the checksums in the manifest refuse a
different file under the same name. A model with a new architecture adds its format in `load_backend`;
policies do not change. A folder path also works as `embed_model` for trying a model that is not published.

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
| `category_pop` | Best sellers in the category of the last viewed product; overall best sellers without views. "Best sellers" = shared popularity (below); `live_weight` 0 + `new_prior` false = history only, as in v1 |
| `coview` | Products viewed in the same sessions as the recent views (recent views weigh more), then `category_pop`. Live on the practice day it sold ~40% less than `category_pop` and less than the baseline: co-viewed products are mostly alternatives people look at, not what they buy |
| `shopper_profile` | Cart-not-bought and recently viewed products first, then best sellers from the categories the shopper views most (below); `category_pop` for shoppers we know nothing about |
| `shopper_score` | Every product scored as popularity x fit with the shopper (categories viewed, cart, recent views, new product); bought-before products left out (below) |
| `shopper_discount` | `shopper_score` x `price_discount`'s lift for products on sale (settings `boost`, `floor`, `rel_price`) |
| `trend_boost` | Wraps another policy (`base`, default `category_pop`); while a subcategory is trending, mixes in its best sellers (below) |
| `discount_boost` | Wraps another policy; pushes products that are on sale up, and pulls in discounted best sellers from the shopper's category (below) |
| `embed` | The embedding model on its own: the ten highest scores in stock, no corrections (the reference arm) |
| `embed_score` | `shopper_discount` with the embedding model's score as its base: `exp(score_weight x score)` x discount lift x cart, bought-before left out. Factors the model covers (`alpha`, `w_cat`, `w_sub`, `ctx`, `recent`, `new`) are off by default. `--set embed_model=NAME` picks the model |
| `price_discount` | `discount_boost` with the lift fitted to the sales: no lift up to 12% off, and cheap products (within their subcategory) gain more than pricey ones (below) |

### Shopper profile: tunable settings

| Setting (default) | Effect |
|---|---|
| `n_cart` (3), `n_recent` (3) | How many cart-not-bought products, then recently viewed products, go first |
| `context` (0.3) | Weight of the last view's category. A category's weight is its share of the shopper's views, plus `context` if it is the last view's; products score weight / (rank + 1) |
| `prior` (5) | Views added to the denominator of every share, so 1-2 views do not count as certain |
| `sub_boost` (1.0) | Within a category, a product scores x (1 + `sub_boost` x its subcategory's share of the views) |
| `base` (`category_pop`) | Filler after those, and the whole answer without profile and views |

Products the shopper bought before are left out. Live on the practice day (2 hours, 4 arms, v1 without
history): official conversion 1.15 against 0.89 for `category_pop`. All of the gain came from shoppers with
products in the cart. Its weak spots, from its rows:

- Recently viewed products in positions 2-5 sold 0.13%, less than best sellers of the top category there
  (0.2%): a viewed product only sells when it is also popular.
- Products from categories with under 30% of the views: 0 purchases in 12,900 showings.

`shopper_score` addresses both. Composes with the wrappers: `discount_boost:base=shopper_profile`.

### Shopper score: tunable settings

One score per in-stock product, the 30 highest returned. The defaults are the coefficients of a logistic
regression on the practice day's live feedback (684,000 shown products, 648 purchases), not yet tested live.

| Setting (default) | Factor |
|---|---|
| `alpha` (1.2) | popularity ^ `alpha` (the shared live popularity) |
| `w_cat` (3.0), `w_sub` (1.0) | x exp(`w_cat` x category share + `w_sub` x subcategory share) of the shopper's views, history + live |
| `ctx` (1.5) | x this, in the category of the last viewed product |
| `recent` (4.5) | x this, for the request's recent views |
| `cart` (6.0) | x this, in the cart and not bought (history or live) |
| `new` (2.5) | x this, for products added during the event (they sold 0.26% against 0.09% when shown) |
| `prior` (5) | views added to the denominator of every share |

Bought-before products score 0. Subclasses can add a factor per product (`multiplier`).

### Trend boost: tunable settings

`trend_boost` returns the base list unchanged when nothing is trending. During a trend it adds the trending
subcategory's best sellers (in stock, at most `per_brand` per brand), in one of three ways (`mode`):

| `mode` | What it does | Settings (default) |
|---|---|---|
| `slots` | Same number of trend products for everyone | `n_slots` (2), `slot` (1 = first position) |
| `context` (default) | Depends on the shopper: last viewed the trending subcategory / no views / other | `n_related` (4), `n_home` (3), `n_other` (1), `slot` (1) |
| `score` | Base rank r scores 1/(r+1), trend rank t adds `boost`/(t+1); sorted by total | `boost` (1.0: top trend product ties the base's first; 0 = off) |

Shared settings: `base` (policy to wrap, default `category_pop`) and `per_brand` (2). Settings of other modes are
ignored. Notes:

- Trend products already in the base list are moved to the trend positions, never duplicated.
- With several trends at once, the strongest (highest lift) comes first.
- The defaults are guesses, not yet tested: the A/B tests are there to find better values.
- `--set` changes `trend_boost`'s own settings, not those of the wrapped policy (e.g. `category_pop`'s `top_n`).

Tune without editing code; every combination gets its own public model ID:

```bash
python -m recsys.main --policy trend_boost --set mode=score boost=0.5
```

### Discount boost: tunable settings

On the practice day ~500-650 products went 11-20% below their original price for 2 hours, every 3 hours
(10:30, 13:30, 16:30 UTC; a new set each time); while discounted they got ~20% more views and ~30-55% more
purchases. The live catalogue keeps each product's original price (`Product.list_price`, `Product.discount`).

| Setting (default) | Effect |
|---|---|
| `boost` (3.0) | Every product's score is multiplied by 1 + `boost` x discount: 20% off and `boost` 3 = x1.6. 0 = off |
| `inject` (0.5) | Pulls in discounted best sellers from the category of the last viewed product (all categories without views): candidate rank t adds `inject`/(t+1) next to base rank r's 1/(r+1). 0 = only re-rank the base list |
| `n_candidates` (10), `min_discount` (0.05) | How many discounted best sellers to consider; how much off counts as discounted |

Both at 0 returns the base list unchanged. Tested on 400 recent requests during a sale: `coview` shows ~1.1
discounted products per answer; `boost` alone barely changes that (base lists hold few discounted
products), `inject` 0.5 raises it to ~2.0. Wrappers compose: `discount_boost:base=trend_boost`.

`price_discount` replaces the multiplier with 1 + `boost` x max(0, discount - `floor`) x (1 - `rel_price` x q),
q = list-price percentile in the subcategory (0 cheapest, 1 priciest); defaults `boost` 6, `floor` 0.12,
`rel_price` 0.6, `min_discount` 0.12. Fitted on the 3 sales of 14 Nov (organic purchases on sale vs the same
product at full price): 11-14% off 1.02x, 17-20% off 1.36x; cheapest third of a subcategory 1.33x, priciest
1.19x. The old `boost` 3 gave x1.33-1.60 for every discount, too much for small ones. Result: 18% off is x1.36
for the cheapest product, x1.14 for the priciest.

### A/B tests

`--ab` adds extra policies (arms), each optionally with its own settings after a colon. Every request is
answered by exactly one arm, picked from its request ID (stable), and each arm sends its own public model
ID, so the dashboard compares them per `model_version`. By default all arms get an equal share;
`--ab-share N` gives each `--ab` arm N% and `--policy` the rest. `--set` applies to every arm.

```bash
python -m recsys.main --policy category_pop --ab trend_boost trend_boost:mode=score,boost=2
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
`recent_views` (product IDs, oldest first). `self.catalog` gives the live product state, `self.profiles` the
shopper profiles, `self.popularity()` the best sellers, `self.embedding_model()` an embedding model. A wrapper
builds its base policy with `self.sibling(name)`, which shares all of these.
