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

Each model is a folder under `models/`, committed to the repo, and listed in `recsys/embed_models.json` (name,
checksums, and which model is the `default`). The scorer is
`training/export/scorer.py` (numpy only); `recsys/embeddings.py` serves it to every policy.

```bash
python -m recsys.embeddings list          # files present and matching, * = default
```

| File | Content |
|---|---|
| `model.npz` | The weights of both towers |
| `user_vectors.npz` | One precomputed history vector per known user, by `user_id` |
| `README.txt` | Which run, git commit and validation scores |

## How to call it

In a policy (see `recsys/README.md`, "Embedding models"):

```python
def fit(self):
    self.model = self.embedding_model(self.embed_model)   # '' = the default model; shared, loaded once
def recommend(self, req):
    s = self.model.scores(req)          # one score per product: s.ids, s.values, s.get(pid), s.aligned(ids), s.top(10)
```

- Pick a model with `--set embed_model=NAME` (or per A/B arm); each model gets its own public ID.
- `embed` is the model alone; `embed_score` is `combined` (your corrections) on top of the model score.
- Speed: ~0.3 ms per request for `scores()`.

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

Both are handled by `recsys/embeddings.py` now:

1. **The original price per product** is `Product.list_price` from `LiveCatalog`.
2. **New products** are embedded in a background thread within ~0.2 s of their `new_product` update.

## Optional: live events per user

Handled: `Profiles` keeps each shopper's last 50 events in time order (history tail, then live `shop.events`),
and `scores(req)` passes them to the model exactly as in training. Shoppers without live events use their
precomputed history vector (the same result). Pass `events=None` to switch this off, or `use_events=False` on
the policy.

## Check before the final round

- `--dry-run` with the model as a policy: no policy errors, also for requests with new products in
  `recent_views`.
- The `model_version` stays an opaque ID from `recsys.model_registry.public_id`.
- The deadline fallbacks in the log stay near 0 with the model switched on.

One thing Jules saw in today's feedback: 32,748 of 70,989 rows were served by the fallback, not by us. Probably
hours without a running server, but worth a look.
