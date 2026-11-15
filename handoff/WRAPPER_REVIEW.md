# Offline review of the wrapper factors on top of the models (server, 02:00 UTC)

Written by a second server session that only read data; it changed no code, arms or branch. What the server did
with it is in `FINDINGS.md` (entry of 02:05 UTC).

Organic numbers come from `shop.events` since 09:00 UTC Sat (3.5M views, 183k purchases). Carousel numbers come
from our own feedback, only on answers each model never trained on: v0 all day, v1/v2 after 21:00, v3/v4 after
00:59. Each factor is fitted by logistic regression on top of the model score, with list position held constant.
"xN" is the odds multiplier in the model's own units, with its 95% range.

**The best combination on paper has never run live.** Every live arm was a model with the default wrapper
settings: trend x8, sale lift, cart x6, everything else off. Those settings were fitted on Saturday for `combined`,
which used popularity instead of a model, and were never refit for v2–v4.

## Trends: keep x8 and the detector as they are

- Organic: a trending subcategory's purchases go up about 10x (8–14x), flat for all 45 minutes, then drop to
  normal at once. Views only go up 3–5x. Every 2 h at :30 (none at 17:30); if the final round keeps this, a trend
  starts at 09:30 UTC.
- Carousel, on top of the model: x8.2 (v0), x8.5 (v1), x8.2–9.4 (v2). The current x8 fits.
- Detector replayed over the whole day: 8 of 8 trends found, 3.3 min late, 92% of trend time covered, 0 false
  alarms. Faster settings cover at most 3 points more and bring 3–34 false alarms.
- The fine-tuned models barely remember the practice trends by hour of day: at most +0.3 log-odds at a past
  trend's hour, within v0's noise.

## Discounts: no lift visible in the carousel; cap the lift

- Organic: purchases x1.32 (1.28–1.36), views x1.22, so per view only x1.08. By depth: 11–14% off x1.07, 14–16%
  x1.23, 16–20% x1.37.
- Carousel, on top of the model: x1.07 (0.58–1.96, v0 all day, 62 purchases) and x0.57 (0.23–1.43, v2). No
  measurable lift.
- The lift grows in a straight line with the discount. All practice discounts were 11–20% off, so 40% off in the
  final round would give about x2.6, with no evidence behind it. **Suggest capping it at x1.3.**

## Other factors on top of v2–v4

| Factor | Live | Fitted | Suggest |
|---|---|---|---|
| Cart, not bought | x6 | v2 x2.0 (1.6–2.5), v3 x2.5 (1.5–4.1), v4 x2.3 (1.4–4.0) | **2.5** |
| New product (practice) | x1 | v1/v2 x2.7 (1.8–4.1), v3/v4 x1.4 (0.6–3.9) | 2 on v2, 1.5 on v3/v4 |
| Category / subcategory share of views | 0 | +1.1 to +2.8 per unit share, positive on every model | `w_cat` 1, `w_sub` 1 |
| Recent views of a new shopper | x1 | v1 x2.2 (1.2–4.3), v2 x2.2 (1.3–3.8) | 2 |

Cart is the clearest one: cart products take 20% of all slots, and x6 is above the 95% range on v2 (407
purchases).

Offline AUC on v2: 0.9238 with the live settings, 0.9305 with all the suggested settings. Expect a few percent at
most; only a live arm can confirm it.

## Other directions

- **Averaging models' scores (ensemble) is the biggest gain on paper.** On answers after 00:59, v2+v3 beats the
  best single model by +149 ± 48 log-likelihood per 1,000 purchases, and AUC goes from 0.901 to 0.908. That rests
  on only 136 purchases: re-check with more data. v1+v2 is worse than v2 alone because v1 is too weak. Serving it
  needs a small code change in the embedding policy.
- **Mixing products from more subcategories hurts.** Answers with 8–10 subcategories sold 0.88x what their
  products predict; answers with 3 or fewer sold 1.06x. Do not add diversity.
- **Subcategory of a purchase in the last hour:** x1.28 (0.90–1.81). The model already covers it.

## Suggested next steps, in order

1. Test one tuned arm next to the champion, at 20–25%:
   `cold_embed:embed_model=models/v2,new_view=1,recent_new_user=2,new=2,cart=2.5,w_cat=1,w_sub=1`
   For v3 or v4, use `new=1.5`.
2. Re-check the v2+v3 average with an hour more answers; if it holds, add score averaging to the embedding policy
   and test it live.
3. Cap the discount lift at x1.3.

## For the trainer

- The 300 new products in the final round are the biggest unknown. v0, which scores new products from their
  catalogue fields alone, had to be corrected x12 for the practice new products. v2–v4 know those products by ID,
  so the numbers above say nothing about products none of them has seen. **Please put the IDs of the 60 practice
  products held out of v2 in `TRAINER.md`.** With them, the server can measure how v2 scores unseen products on
  our own carousel and set `new` for the final round.
- v2 and v3 add to each other offline (see the ensemble numbers). If the final model can be an average of two
  recipes, that is worth checking.
