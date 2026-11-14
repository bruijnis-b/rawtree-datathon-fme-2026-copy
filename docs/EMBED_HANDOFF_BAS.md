# Embedding model: hand-off to Bas

What Jules delivers, how to call it, and which corrections stay on your side. The full training plan is
`docs/EMBED_SWEEPS_FINAL.md`; you do not need it to use the model.

## When you get what

| When (CET) | What |
|---|---|
| Sat 22:00 | **v0**: a default model, trained on the history only. Use it to build and test your layer, and as an A/B arm overnight |
| **Sun 06:30** | **Final model**: best sweep config, fine-tuned on the live practice stream. No model changes after this |
| Sun 06:30 – 09:30 | You fit your correction layer on the final scores |

v0 and the final model have the same interface and the same score scale. If the final model fails its checks,
v0 stays, and Jules tells you.

## What you get

A folder `export/` (a few MB, sent directly, not committed) plus a scorer module in the repo. The scorer needs
only numpy.

| File | Content |
|---|---|
| `model.npz` | The weights of both towers |
| `user_vectors.npz` | One precomputed history vector per known user, by `user_id` |
| `README.txt` | Which run, git commit and validation scores |

## How to call it

```python
product_matrix = embed_products(rows)                  # once at startup, and again for each new_product
scores = score(request, product_matrix)                # per request: one score per product
```

- `rows`: per product `product_id`, `category`, `subcategory`, `brand`, `description` and the **original price**
  (see below).
- `request`: your `Request` (`user_id`, `is_new_user`, `device`, `region`, `page`, `recent_views`).
- `scores` are in the row order of `product_matrix`. Speed: a few ms per request on CPU.
- Call `embed_products` only for new products. Price and stock changes do not change the vectors.

**The score is the log-odds that the shopper buys the product when it is shown in slot 1.** A difference of 0.7
is twice the odds. Products do not compete in the history, so the best carousel is the ten highest final scores,
in descending order.

## What the model already covers

| Input | Covered by the model |
|---|---|
| Product: category, subcategory, brand | Yes |
| Product: its **original price** (how a €10 product sells compared with a €100 one) | Yes. This is the product's own undiscounted price, not a category average |
| Product: identity of the 5,000 known products (and the practice-round products, after fine-tuning) | Yes |
| New products without any sales | Yes, from their catalogue fields |
| Request: device, region, page, time of day | Yes |
| Request: `recent_views` (also when they contain a new product) | Yes |
| Request: `is_new_user` | Yes, in the final model (v0 ignores it) |
| User's long-term behaviour, for users in the history | Yes, through `user_vectors.npz` |
| Slot position bias of the old carousel | Removed in training |

Do not correct for any of these again.

## What you add

`final = score + your corrections`, all on the log-odds scale.

| Correction | How | Starting value |
|---|---|---|
| **Price change** | `β(p₀) · log(current price / p₀)`, with `p₀` the product's original price and a weight that depends on it: `β(p₀) = β₀ + β₁ · log(p₀ / 30)`, capped at 0 | `β₀ = −2.2`, `β₁ = +1.2` (see the table below) |
| **Trend** | A boost per product or category from your trend detector | 0; a boost of +0.7 doubles the odds |
| **Out of stock, already bought** | Hard filter, as now | – |
| **Guard and fallback** | As now | – |

Fit `β₀`, `β₁` and the trend weights on `team_NN.feedback`, with the model score as a fixed offset (logistic regression:
did the shown product get bought).

What the starting values mean, for a 20 % discount:

| Original price | €10 | €20 | €30 | €50 | €100 | €200 |
|---|---|---|---|---|---|---|
| `β` | −3.5 | −2.7 | −2.2 | −1.6 | −0.8 | 0 |
| Purchases during the discount | 2.2× | 1.8× | 1.6× | 1.4× | 1.2× | 1.0× |

Fitted on 643 discounts in today's organic `shop.events` (95 % ranges: `β₀` −2.6 to −1.75, `β₁` 0.5 to 1.9).
Refit both on the feedback.

Why the price change is yours: in the live stream every price change is a 16–20 % discount that lasts exactly
two hours. The history has no price changes, so the model cannot learn their effect. The model only uses the
original price, to know what kind of product it is; it never sees the current price.

## Two things you must supply

1. **The original price per product:** the `shop.catalog` price, or for a new product the price in its
   `new_product` row. Keep it next to the current price in `LiveCatalog`. The model takes the original price;
   your discount term takes both.
2. **`embed_products` for every `new_product`** as soon as it arrives, so it can appear in `recent_views` and in
   the ranking.

## Optional: live events per user

A user who is new today has no row in `user_vectors.npz`, so the model sees only their request. If you keep each
user's last 20 `shop.events` (product and event type), pass them along:

```python
scores = score(request, product_matrix, events=last_events)
```

The model works without this. It helps most for new users, who become known after a few events.

## Check before the final round

- `--dry-run` with the model as a policy: no policy errors, also for requests with new products in
  `recent_views`.
- The `model_version` stays an opaque ID from `recsys.model_registry.public_id`.
- The deadline fallbacks in the log stay near 0 with the model switched on.

One thing Jules saw in today's feedback: 32,748 of 70,989 rows were served by the fallback, not by us. Probably
hours without a running server, but worth a look.
