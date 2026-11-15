# Findings (server writes this; newest on top)

## Requests to the trainer

1. **Give the end of the training data (UTC) in every model card.** We only score a model on answers after it.
2. **The shopper's views by category, and live popularity, still add to v1.** Purchase AUC on unseen answers:
   v1 alone 0.888, v1 plus our shopper factors 0.907. The largest weights next to the score: the shopper's share
   of views in the product's category (+2.29) and subcategory (+0.79), log popularity (+0.45), in the cart and not
   bought (+1.22). If the model can take a longer or fresher view history, or a popularity input, that is where
   the gain is.
3. **Do not learn repeat purchases from the organic data.** The organisers confirmed that a shopper who bought a
   product is much less likely to buy it again when shown; the organic events were generated without that
   effect. Our feedback agrees (bought again 7 times in 49,697 showings). The guard now drops bought products
   from every answer, so a model never needs to score them well.
4. **New products on requests that viewed a new product** may be slightly under-scored by v1 (x1.4, range
   0.8–2.6), and the same for a new shopper's recent views (x1.6, range 0.9–2.6). Not significant; worth a look
   in your new-product check, not worth a model on its own.

## 2026-11-15 00:45: do the cold lifts add to v1? Hardly

Data: our answers after 21:00 UTC (v1's training data ends there): 37,213 answers, 361,608 shown products, 524
purchases. Logistic fit with list position as dummies; ranges from a bootstrap over answers.

| Term | On v1 with default settings | On v1 plus shopper factors |
|---|---|---|
| New product, when the recent views hold a new product | x1.43 (0.79–2.57) | x2.74 (1.41–5.34) |
| Recent view, for a new shopper | x1.57 (0.94–2.64) | x2.23 (1.17–4.25) |

Held-out AUC gains 0.002 or less in every segment. v1 already covers most of both effects. No cold arm is live.

## 2026-11-15 00:22: bought products are never shown

`guard.finalize` drops products the shopper bought (history, live organic, or through our own carousel) from
every answer and from the padding. Our carousel sales are not in `shop.events`; they are read from
`team_NN.feedback` every 5 s.

## 2026-11-15 00:18: what the pruned arms taught us

- **v1 is the step up.** Against the organisers' reference arm: v1 0.99–1.11x, v0 0.84–0.92x, `combined`
  0.85–0.88x. The gain comes from fine-tuning on the live stream, not from the embedding design alone.
- **Pushing new products hard hurts**, also for cold shoppers (`cold_combined`: −10% conversion, −17% cold).
- **Refit weights are unproven live** (v0 and v1): the offline AUC gain has not shown up yet.
- `combined` beat `shopper_score` by 3–15% in every period: the discount and trend factors help.
