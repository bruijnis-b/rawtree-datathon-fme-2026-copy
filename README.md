# Team 33 · RawTree Challenge, Datathon FME 2026

Our real-time recommender for the RawTree challenge: every few seconds a shopper arrived, and within 3 s we
chose the 10 products they saw. The challenge was scored only in the final round, **Sun 15 Nov 2026,
10:00–12:00 CET**. The event is over; this repo is kept as a record of what we built and why.

The organisers' full rules and data description: [CHALLENGE_README.md](CHALLENGE_README.md).

## Result

Our row in the last official snapshot our monitor recorded after the final round (11:08 UTC, `model_version`
`md363d5`):

| Measure | Value |
|---|---|
| Requests answered | 21,600 |
| Answered validly within 3 s | 99.98 % |
| Conversion score | 52.5 |
| Cold-start score | 45.4 |
| Overall score | 58.3 |

Our rank among the teams is not recorded here.

## What ran in the final

`recsys/arms.final.txt`: the average of two embedding models (v10 and v11, product and user towers, fine-tuned
on live data up to 06:24 UTC), with live adjustments on top of the model scores: discount lift, a boost for
subcategories the trend detector flags, a lift for products left in the cart, and a filter for products the
shopper already bought. Each decision and its evidence: [recsys/README.md](recsys/README.md), "Final setup".

## What is in this repo

| Folder | What it is |
|---|---|
| [`recsys/`](recsys/README.md) | **Our recommender.** Live catalogue state, pluggable policies (algorithms), a guard that keeps every answer valid, and the serving loop |
| [`monitor/`](monitor/README.md) | Streamlit dashboard: are we answering, are we selling, how does our leaderboard row look |
| `training/` | Model code: history export, data inspection, embedding training and fine-tuning (run on IVAN, Team Epoch's GPU scheduler) |
| `models/` | The embedding models the recommender loaded (v0–v4, v10, v11): weights and user vectors |
| `docs/` | [Plan of approach](docs/POA.md), the embedding hand-off and the sweep logs |
| `tools/` | `board.py`: official expected score per quarter hour, for comparing arms over the same minutes |
| `analysis/` | First exploration notebook |
| `conf/`, `ivan.yaml` | Hydra config and IVAN project file for `training/` |
| [`starter/`](starter/) | The organisers' starter kit, untouched: baseline recommender, SQL examples, offline evaluation notebook |

## How it works

```
 shop.requests ──► main.py ──► policy.recommend() ──► guard.finalize() ──► team_33.submissions
                       ▲               ▲                      ▲
 shop.catalog ─┐       │               │                      │
 catalog_updates ──► LiveCatalog (in memory, synced every 0.2–1 s): prices, stock, new products
 shop.history_events ─► features (SQL in RawTree): best sellers, co-views
```

- **Live catalogue:** the whole catalogue in memory, kept current with the update stream, so checking a
  product's stock or price takes ~0.1 µs per request.
- **Embedding models:** a product tower (content only, so a new product is scored as soon as it appears) and a
  user tower; the score is their dot product. Trained on the 60-day history and fine-tuned on live data.
- **Popularity:** best sellers = 60 days of history blended with the last hour of live purchases; new
  products start at their subcategory's average, so they get recommended too.
- **Trend detection:** spots a subcategory that suddenly gets far more views than usual (on the practice
  day: ~4x views, ~10x purchases, 45 min, every 2 h) within 1-3 minutes.
- **Policies:** one file per algorithm in `recsys/policies/`, all with the same interface, swappable with
  `--policy` or mixed as A/B arms with `--arms`.
- **Guard:** whatever a policy returns, the answer sent is exactly 10 distinct, active products, padded from
  our fallback (best sellers in the category of the last viewed product). If a policy crashes, or a request
  is already 2000 ms old, the request gets that fallback right away: still a valid answer, and on time.
- **Opaque model IDs:** submissions carried a random `model_version` (like `m3f9a2c`) that said nothing about
  our approach; what each ID means is in `recsys/model_versions.json`.

## Run

This needs the challenge's RawTree database, which may no longer be reachable now that the event is over.
Put `TEAM_ID` and `RAWTREE_API_KEY` in `.env` (see `.env.example`). Then, from the repo root:

```bash
python -m recsys.main --policy category_pop --dry-run
```

```bash
python -m recsys.main --arms recsys/arms.final.txt
```

The first computes answers without sending them; the second answers live with the final setup. **Only one
process may answer live at a time.** Logs go to the console and `logs/recsys.log`. To see what each public
model ID means:

```bash
python -m recsys.model_registry
```

The dashboard: see [monitor/README.md](monitor/README.md).
