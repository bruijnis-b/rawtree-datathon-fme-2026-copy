# Model v1

IVAN experiment `exp-0200`, git `e06b136`, fine-tuned from `embed-b/13`.

**v1** (Sat 23:31): history configuration `b_a2_43`, chosen for its live score and its ranking of new products (not for its history score, which does not predict live results), fine-tuned on live snapshot 1 (practice stream up to Sat 21:00 UTC). Focus: cold start, i.e. new users and new products.

**Measured after delivery (live hold-out):** the user's long-term history is worth +0.6 to +0.8 lift. New users score 2.13 without history and 2.81 when their last 50 live events are passed with `events=`; for a user with a saved history, using 50 events instead of the exported 20 adds about +0.1.

## In one paragraph

A two-tower recommender. One tower turns a product into a vector of 32 numbers, the other turns a shopper's request into a vector of the same size; the score of a product is how well the two line up (dot product) plus a per-product bias. The score is calibrated as the **log-odds that the shopper buys the product when it is shown in slot 1**, so corrections (discount, trend) can be added to it. It was trained on the 60-day history and then fine-tuned on the live practice stream, so it has seen today's new users and new products.

## What it embeds

**Product tower** (no request input, so product vectors are computed once):

- category, subcategory and brand: learned vectors;
- reference price (the product's original price, never the current one): its log, and its log minus the subcategory's mean log price;
- description: a bag of words (hashed into 4,096 buckets, averaged);
- a learned vector per known product (its identity), hidden in training 50% of the time so the content path also learns to score a product alone; during fine-tuning the practice-round products hid theirs 50% of the time;
- a bias from the content (expected popularity), plus a learned offset for products without an identity vector (every new product at serving time).

**User tower** (from the request, plus the user's history if known):

- device, region, page, hour of day: learned vectors;
- `recent_views` (up to 6 products from the request): their product vectors, pooled by a recency-weighted mean (the newest view counts most, each step back × 0.7);
- long-term history: the product vectors of the user's last 20 events (views 1×, add-to-carts 2×, purchases 4×), averaged; dropped entirely in 50% of training examples so the model also works without it. Known users' history vectors are precomputed in `user_vectors.npz` (74,174 users); live events can be passed with `score(..., events=...)`.
- `is_new_user`: an input whose weights start at zero; learned during the live fine-tuning.
- no per-user identity vector: a user is described only by what they do.

## How it was trained, and why

- **Two tasks on shared towers.** (1) Carousel: did the shopper click each of the 10 shown products, and buy after clicking. (2) Organic: which product did the shopper view, add to cart or buy next on the site (weight 1.0; purchases sampled 6× as often as views), against the other products in the batch, corrected for popularity (logQ). The organic task covers the whole catalogue, where the old carousel only shows a few products; without it the model is much worse.
- **Old-carousel bias removed.** A slot term (attention by slot and device) is learned in the click head and dropped at serving; products shown only by the old policy's choice are not treated as negatives elsewhere.
- Settings: dimension 32, hidden layer 128, click weight 0.3, learning rate 0.0007, weight decay 1e-05, batch 4096, 20 epochs, trained on fold 0 (10 % of users and 300 products held out to test cold start).
- **Live fine-tuning:** 2 epochs over the live organic events (live dataset v1), 50% of each batch from the history to avoid forgetting, learning rate 1.0× the history rate, weights trained: all, carousel feedback task off (with a live hold-out: 20 % of live users, the last 2 hours, 60 practice products).
- **Recalibration:** the final score is `0.985 · score -0.246`, fitted on half of the history validation week and checked on the other half (applied inside the scorer).

## Strong points (measured)

Lifts are relative to best sellers on the same requests (+2.0 = 3× best sellers), with 95 % intervals.

| Measure | All | Cold | New users | New products |
|---|---|---|---|---|
| History: ips_hit@10 (carousel, propensity-weighted) | +3.65 [+3.39, +3.93] | +3.84 [+3.30, +4.54] | +3.02 [+2.38, +3.82] | +4.46 [+3.66, +5.56] |
| History: organic recall@10 | +2.36 [+2.20, +2.52] | +3.04 [+2.53, +3.60] | +1.59 [+1.25, +2.04] | +6.16 [+4.69, +8.10] |
| Live hold-out: organic recall@10 | +2.33 [+2.19, +2.48] | +2.26 [+2.06, +2.47] | +2.44 [+2.20, +2.71] | +1.86 [+1.59, +2.18] |

- within a shown carousel, the clicked product scores above another shown product 75% of the time (slate_auc; 50 % = random).
- held-out practice products get 1.11% of top-10 slots against 1.15% of purchases.
- calibration: predicted and observed purchase rates differ by at most 17% per score decile.

## Weak points and what it does not do

- Discounts are not in the model (it only sees the original price): the discount effect (+60 % purchases for a 20 % discount) belongs in the correction layer.
- Trends of the final round are not in the model: the history has none, and live trends are left out on purpose.
- Stock, already-bought and diversity are not handled: hard filters in recsys.
- A user's history is frozen at export time unless live events are passed with `events=`.

## Use

```python
from training.export.scorer import load
model = load("models/v1")
pm = model.embed_products(rows)      # rows: product_id, category, subcategory, brand, description, price (ORIGINAL)
scores = model.score(request, pm)  # one per product, in pm.ids order; optional events=[(product_id, event_type), ...]
```
