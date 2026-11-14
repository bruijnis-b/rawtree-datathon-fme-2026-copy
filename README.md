# Team 33 · RawTree Challenge, Datathon FME 2026

Our real-time recommender for the RawTree challenge: every few seconds a shopper arrives, and within 3 s we
choose the 10 products they see. Scored only in the final round, **Sun 15 Nov 10:00–12:00 CET**.

The organisers' full rules and data description: [CHALLENGE_README.md](CHALLENGE_README.md).

## What is in this repo

| Folder | What it is |
|---|---|
| [`recsys/`](recsys/README.md) | **Our recommender.** Live catalogue state, pluggable policies (algorithms), a guard that keeps every answer valid, and the serving loop |
| [`monitor/`](monitor/README.md) | Streamlit dashboard: are we answering, are we selling, how does our leaderboard row look (also during the final, when the leaderboard goes dark) |
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
- **Trend detection:** spots a subcategory that suddenly gets far more views than usual (on the practice
  day: ~4x views, ~10x purchases, 45 min, every 2 h) within 1-3 minutes. See `recsys/README.md`.
- **Policies:** one file per algorithm in `recsys/policies/`, all with the same interface, swappable with
  `--policy`. Current: `baseline`, `category_pop` (best so far), `coview`, plus the `trend_boost` and `discount_boost` wrappers.
- **Guard:** whatever a policy returns, the answer sent is exactly 10 distinct, active products, padded from
  our fallback (best sellers in the category of the last viewed product, better than the organisers'
  all-time best sellers). If a policy crashes, or a request is already 2000 ms old, the request gets that
  fallback right away: still a valid answer, and on time.
- **Opaque model IDs:** submissions carry a random `model_version` (like `m3f9a2c`) that says nothing about
  our approach; what each ID means is logged privately in `recsys/model_versions.json`.

## Run

Put `TEAM_ID` and `RAWTREE_API_KEY` in `.env` (see `.env.example`). Then, from the repo root:

```bash
python -m recsys.main --policy category_pop --dry-run
```

```bash
python -m recsys.main --policy category_pop
```

The first computes answers without sending them; the second answers live. **Only one process may answer
live at a time**, so stop any other server (including the starter baseline) first. Logs go to the console
and `logs/recsys.log`. To see what each public model ID means:

```bash
python -m recsys.model_registry
```

The dashboard: see [monitor/README.md](monitor/README.md).

## Before the final (Sun 10:00 CET)

- Best version running live by 10:00, on a machine that will not sleep.
- Monitor dashboard and `monitor.record_official` running; status light green.
- Check `logs/recsys.log` for guard warnings (proposed inactive products) and policy errors.
