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

## 2026-11-15 02:20: three arms until 05:30, nothing else

Bas asked for few arms that collect requests instead of many that never separate. Live since 02:18 UTC, a third
each, **not to be changed before 05:30 UTC**: v2 (`med6134`), the v2+v3 average (`m09c26e`), v4 (`mab651f`).

Why these three: they answer the two questions the final choice hangs on. Which recipe (v2's against v4's, the
trainer's candidate), and one model or an average.

What this means:
- **A new model no longer goes live automatically.** I check it, dry-run it and score it offline against v2, v3
  and v4 on the same logged answers, and write the result here. It only takes an arm if it is clearly ahead
  offline (two standard errors), and then it replaces the weakest of the three.
- **For the trainer:** so do not count on a live test for v5. What decides at 05:30 is (1) three hours of live
  purchases on these three arms, which tell you which recipe to use, and (2) the offline score of each new model.
  If you are choosing what to train now, the live arms say: train v2's recipe and v4's recipe both on the last
  snapshot, and expect to deliver the pair for an average.
- The wrapper questions (cart 2.5, trend 3, popularity, discount cap) are settled offline, not live; their arms
  ran 5–20 minutes and say nothing. I write the final settings with their evidence before 05:30.

## 2026-11-15 02:15: the average of two models holds up; experiment round live

**Offline, logged answers after 00:59 UTC, now 11,626 answers and 251 purchases** (same rows for every column;
gain is against v2, ± one standard error from a bootstrap over answers; rank = place of the bought product among
the 10 shown):

| | v2 | v3 | v4 | v2+v3 | v2+v4 | v3+v4 | v2+v3+v4 |
|---|---|---|---|---|---|---|---|
| AUC, all | 0.894 | 0.898 | 0.886 | **0.905** | 0.900 | 0.902 | 0.906 |
| Gain over v2 | | +0.004 ± 0.007 | −0.008 ± 0.006 | **+0.011 ± 0.003** | +0.006 ± 0.003 | +0.008 ± 0.006 | +0.011 ± 0.004 |
| Rank, all | 3.04 | 3.02 | 3.35 | **2.87** | 3.13 | 3.00 | 2.97 |
| AUC, new shoppers (106 purchases) | 0.883 | 0.873 | 0.884 | 0.889 | 0.893 | 0.890 | 0.894 |
| AUC, known shoppers (145 purchases) | 0.898 | 0.909 | 0.885 | 0.912 | 0.901 | 0.907 | 0.910 |

- **v2+v3 beats v2 by 3 standard errors**, and beats v3 too. Adding v4 as a third changes nothing.
- v2 and v3 are the same recipe on different data, and still add to each other. v3 is better for known
  shoppers, v2 for new ones; the average is at least as good as the better one in both groups.
- v4 is last on rank in both runs (3.38 and 3.35) and 1.3 standard errors below v2 on AUC.

**New policy `embed_blend`** (`recsys/policies/embed_blend.py`): `embed_model2` averages a second model's scores
with the first; `max_lift` caps the discount lift (0 = off). It is a separate policy so the IDs of the
`embed_score` arms stay the same. Dry run: 0 errors, p95 0.7–0.9 s with two models per request.

**Live since 02:13 UTC (restart, about 15 s without answers):** seven arms, see `LIVE.md`. New: the v2+v3 average
(`m09c26e`) and v2 with live popularity, `alpha=0.3` (`m76d67a`). The popularity arm is there for generalising:
the trend detector only sees one subcategory surging by 2.5x or more; a popularity term also follows a surge of
another shape, and new products once they start to sell.

**For the trainer:**
- An average needs two models with different errors. For the final delivery, **two models are worth more than
  one**: v2's recipe on the last snapshot plus a second that differs (other seed, other fold, or v2's own data
  cut). I can serve any pair, no scorer change needed.
- v4 (v1's configuration, long history) is behind v2 and v3 on purchases in our logged answers, twice now. Live
  it is undecided. If you still prefer it on clicks, please check it on purchases first.

## 2026-11-15 02:05: wrapper review, and what I did with it

A second server session reviewed every wrapper factor on top of the models, offline, with the whole day of
organic events: `handoff/WRAPPER_REVIEW.md`. Read it; the short version and my decisions:

| Review says | Decision |
|---|---|
| Cart x6 is too high on v2–v4 (fitted x2.0–2.5; cart products fill 20% of slots) | **Live now:** v2 with `cart=2.5` as `mff9f12`, 20%, since 02:03 UTC |
| Trend x8 fits (x8.2–9.4 on v2, 8 trends, organic purchases x10) | It disagrees with my estimate of 01:52 (x2.2, range 1.0–10.5, 3 trends, 34 purchases). The review has more data and its range sits inside mine: **x8 stays the default.** The `trend=3` arm keeps running through the next trend (03:30 if the pattern holds) as the live check; outside trends it answers exactly like the champion, so it costs nothing |
| No discount lift visible in the carousel; cap it at x1.3 | Agrees with my 01:55 entry. Needs a small code change and a restart: goes in with the next restart, not on its own |
| Average of v2 and v3 scores beats either (136 purchases) | Re-check is running on about 300 purchases. If it holds I add score averaging to the policy and test it live |
| Tuned package (`new` 2, `recent_new_user` 2, `w_cat` 1, `w_sub` 1, `cart` 2.5) | One factor at a time: a similar package on v1 lost for new shoppers (01:20 entry). Cart first; the next factor follows when cart is read |
| Do not add diversity: answers with many subcategories sell less | Nothing to change |

**For the trainer, from the review:**
- **Please put the IDs of the 60 practice products held out of v2 in `TRAINER.md`.** With them I can measure, on
  our own carousels, how v2 scores products it has never seen, and set `new` for the 300 products of the final
  round. This is the largest open question.
- v2 and v3 add to each other offline. If the final model can be an average of two recipes, or you can deliver
  both recipes on the last snapshot, I can serve the average.

## 2026-11-15 02:00: v1 pruned, trend test live

The Leashes trend runs until about 02:15, so the trend test started now instead of at 02:10: v1 is off (see
`LIVE.md`) and its 15% runs v2 with `trend=3` as `m3cb3ff`, since 01:57:56 UTC. To read it: compare `m3cb3ff` with
`med6134` (v2, `trend=8`) over the minutes a trend is active; outside trends the two give the same answers.

## 2026-11-15 02:00: live numbers, and how each arm treats new products

**Live, 01:10:40 – 01:53 UTC** (v3 from 01:20, v4 from 01:33; v1 over the whole period):

| Arm | Answers | Purchases | Conversion | New shoppers |
|---|---|---|---|---|
| v1 | 2,428 | 49 | 2.02% ± 0.29 | 2.82% |
| v2 | 1,879 | 50 | 2.66% ± 0.37 | 4.16% |
| v3 | 1,845 | 43 | 2.33% ± 0.35 | 3.05% |
| v4 | 954 | 24 | 2.52% ± 0.51 | 4.78% |

All three new models are above v1; none is separated from another. No change to the arms.

**New products (added during the practice round) in our answers since 23:37 UTC:**

| Arm | Answers | Share of slots | Share of purchases | Rate, new products | Rate, old products |
|---|---|---|---|---|---|
| v1 | 7,465 | 4.0% | 4.6% (7 of 153) | 0.236% | 0.204% |
| v2 | 1,470 | 3.9% | 0 of 42 | 0 | 0.297% |
| v3 | 1,425 | 5.1% | 13.9% (5 of 36) | 0.686% | 0.229% |
| v4 | 628 | 4.4% | 0 of 13 | 0 | 0.216% |
| `combined` | 3,497 | 16.8% | 12.7% (7 of 55) | 0.119% | 0.165% |
| `cold_combined` | 959 | 25.2% | 16.7% (2 of 12) | 0.083% | 0.139% |

- The models give new products 4–5% of slots, about their share of purchases. The policies without a model gave
  them 17–25% and they sold worse there than old products: more evidence against a strong `new` factor.
- v3 is the only arm so far where new products sell clearly better than old ones (5 purchases: thin).
- **For the trainer:** these are products v3 and v4 have seen in fine-tuning. The 300 products of the final
  round are unseen by every model. Which of your candidates is best on products held out completely (content
  only), on purchases? That, more than anything here, decides the cold-start points.

## 2026-11-15 01:55: the discount lift also looks too strong on top of the model

Same logged answers (after 21:00 UTC, v2's scores, 799 purchases). "Against the model" is purchases divided by
what v2's score alone predicts for those products, with list position taken out.

| Discount of the shown product | Shown | Bought | Rate | Against the model |
|---|---|---|---|---|
| None | 461,429 | 768 | 0.166% | 1.03 |
| 12–16% | 4,549 | 9 | 0.198% | 1.46 |
| Over 16% | 27,422 | 21 | 0.077% | 0.63 |

- Products more than 16% off get a lift of up to x1.5 from us, and sold a third **less** than the model alone
  predicts (21 purchases where 33 were expected; about 2 standard errors).
- Limits: night hours only, 30 purchases on discounted products, and these are products the lift itself put
  in the list. The daytime A/B favoured the discount lift, but on a policy without a model.
- No change live yet. One factor at a time: the trend arm comes first (02:10), a `boost=0` arm after it.

## 2026-11-15 01:52: the trend lift (x8) is too strong on top of the model

All arms multiply the score of products in a trending subcategory by 8. That value was fitted on top of
popularity, never on top of a model. On our logged answers after 21:00 UTC (v2's scores; 799 purchases):

| During the trend in | Trending products: shown, bought, rate | Other products shown: rate | Same subcategory outside trends |
|---|---|---|---|
| Vitamins (23:30–00:17) | 20,540, 28, 0.136% | 0.190% | 0.071% |
| Leashes (01:30–, running) | 3,016, 6, 0.199% | 0.243% | 0.000% (0 of 4,259) |
| Face Cream (22:00–22:45) | 84, 0 | 0.133% | 0 of 111 |

- A trend is real: Vitamins products sold twice as often during their trend as outside it.
- But x8 gives them **a quarter of all slots** (2.5 of 10 per answer during Vitamins), and there they sell less
  than the products they push out (0.136% against 0.190%). Rough cost: 7% of the conversion during a trend.
- Fitted next to v2's score, the right lift is about **x2.2** (5%–95%: x1.0–x10.5). Wide, 34 purchases on
  trending products, but x8 is at the far end of it.

**Next:** when v1 is pruned at 02:10, its 15% goes to the champion with `trend=3`, to collect live evidence over
the coming trends. The final round has at least one new trend, so this setting matters there.

## 2026-11-15 01:46: offline, v2, v3 and v4 all beat v1 clearly; v2 is champion

**Offline, on our logged answers after 00:59 UTC** (the end of v3's and v4's training data; 6,137 answers, 60,610
shown products, 136 purchases; the same rows for every model; ± is one standard error from a bootstrap over
answers). AUC is for purchase; "rank" is the place the model gives the bought product among the 10 shown (1 = top).

| | v1 | v2 | v3 | v4 |
|---|---|---|---|---|
| AUC, all | 0.838 | 0.897 | 0.901 | 0.893 |
| Gain over v1 | | +0.058 ± 0.012 | +0.063 ± 0.012 | +0.055 ± 0.009 |
| Rank of the bought product, all | 3.88 | 3.07 | 3.06 | 3.38 |
| AUC, new shoppers (49 purchases) | 0.844 | 0.897 | 0.881 | 0.894 |
| Rank, new shoppers | 3.59 | 2.78 | 3.04 | 3.06 |
| AUC, known shoppers (87 purchases) | 0.834 | 0.895 | 0.910 | 0.891 |
| Rank, known shoppers | 4.03 | 3.23 | 3.07 | 3.56 |

- v2, v3 and v4 are each 4–6 standard errors above v1. The 100-event history is the common factor.
- Among the three there is no decision yet (differences under one standard error). v4 ranks the bought product
  a little lower than v2 and v3 (3.38 against 3.07), mostly for known shoppers.
- Caution: from 01:10 some of these answers were chosen by v2 or v3 themselves.

**Live, 01:10:40 – 01:42 UTC:** v2 3.05% ± 0.48 against v1 1.94% ± 0.30 (1.95 standard errors; table in `LIVE.md`).

**Decision:** v2 is champion (higher offline, higher live). v1 drops to 15% as a reference and is pruned at 02:10
unless it catches up. Shares: v2 30%, v3 30%, v4 25%, v1 15%.

**For the trainer:** on purchases, v1's configuration with a long history (v4) is not ahead of v2's recipe so
far: offline equal or slightly behind, live too early. Do not fix the final choice on the carousel-click measure
alone. If v5 can be either recipe, the purchase evidence does not yet say which; training **both** on the 03:30
snapshot would let the live test decide.

## 2026-11-15 01:42: v2 is back; it led v1 in its first 22 minutes

I took v2 off at 01:33 to make room for v4 without first looking at its numbers. That was a mistake:

| 01:10 – 01:33 UTC | Answers | Purchases | Conversion | New shoppers |
|---|---|---|---|---|
| v1 (champion) | 1,566 | 28 | 1.79% ± 0.33 | 2.01% (9 of 447) |
| v2 | 1,127 | 35 | 3.11% ± 0.52 | 4.73% (16 of 338) |

2.1 standard errors, on 63 purchases: early, but in the same direction as the offline AUC (0.923 against 0.883).
v3 over its first 13 minutes: 2.70% against 1.78% for v1. v2 is live again since 01:39:03 UTC under the same ID
(`med6134`). Four arms at 25% each: v1, v2, v3, v4.

**For the trainer:** live, v2's recipe does not look worse than v1's, although your held-out carousel clicks
prefer v1's configuration (0.80 against 0.70). Your measure counts clicks on carousels that our earlier
policies chose; the score that counts is purchases. Please also rank the configurations on **purchases** in
our logged carousels, not only clicks, if there are enough (we have about 1,350 purchases in 116,000 answers).

## 2026-11-15 01:40: v4 is live; no waiting for the sake of waiting

**From Bas and Jules, for both of us:** waiting for live requests is fine, waiting for anything else is not. The
rule is in `README.md` ("No waiting for the sake of waiting"). For you that means: deliver v5 and anything else
as soon as it exists, do not time it to my reviews, and use the gaps for work that needs no traffic. I now check
the branch every 5 minutes and a model is live about 4 minutes after I see it.

**v4:** zip sha256 matches the card; 7 data files; no scorer change. Dry run of 100 s: 0 policy errors, p95
0.8–0.9 s. Live since 01:32:53 UTC as `mab651f`. Shares: v1 34%, v3 33%, v4 33%.

**Your question: `med6134` is v2** (`embed_score:embed_model=models/v2`, default settings), live 01:10:33 –
01:32:53 UTC, at 25% and then 33%. Every public ID is in `handoff/LIVE.md` (live and pruned) and in
`recsys/model_versions.json` (`embed_model` in `params`). v2 left for v4, not because it did badly.

**Running now, no traffic needed:** v1–v4 scored on the same logged answers after 00:59 UTC (AUC, and the rank each
model gives the product that was bought), split by new and known shoppers. Results in the next entry.

**What only traffic can tell, and when:** v1 against v3 against v4 on live conversion. First numbers at 02:35 UTC
(one hour for v4), sooner if a gap of two standard errors shows.

## 2026-11-15 01:22: v3 is live next to v1 and v2

Zip sha256 matches the card; 7 data files; no scorer change, so no restart. Dry run of 100 s: 0 policy errors,
p95 1.0 s once warm. Live since 01:19:58 UTC as `m0cba68`. Shares: v1 34%, v2 33%, v3 33%.

- The v1 refit arm made room (see `LIVE.md`): refit weights belong to one model, and the question now is which
  model. If v2 or v3 wins, I refit for the winner and test that once, at 20%.
- v3's offline score needs answers after 00:59 UTC. There are 20 minutes of those now; I run it at the 02:20
  review with about 80 minutes (about 250 purchases).
- With three arms at a third each, every arm collects about 65 purchases per hour.

## 2026-11-15 01:20: v2 is live; offline it is well ahead of v1

**Checks:** zip sha256 matches the card; 7 data files, flat. Dry run of 100 s next to the live process: 0 policy
errors, p95 1.0–1.5 s. Live since 01:10:33 UTC as `med6134`, 25% of requests.

**Offline, on our own answers after 21:00 UTC** (44,731 answers, 436,080 shown products, 666 purchases; the same
rows for both models; purchase AUC, fitted on half of the answers and scored on the other half):

| Inputs | v1 | v2 |
|---|---|---|
| Model only | 0.883 | **0.923** |
| Model + shopper factors | 0.903 | **0.930** |

- v2 alone beats v1 with all our shopper factors on top.
- The shopper factors add less to v2 (+0.008) than to v1 (+0.020): v2's longer history covers part of them.
  Weights next to v2's score: category share +0.96 (v1: +1.96), popularity +0.28 (+0.46), cart +0.77 (+1.06).
- These are products our policies chose to show, so this measures re-ranking, not the whole catalogue.

**Promotion:** v2 becomes champion at the 02:10 review if its live conversion is not more than one standard error
below v1's. One hour at 25% gives about 50 purchases, so only a large gap would stop it.

**Answers to the trainer's questions (01:05):**
- `Profiles` keeps **100 events** per shopper since the 01:10 restart (was 50). v1 still takes its last 20.
- Yes: `Profiles` passes views, add-to-cart and purchases with their types, oldest first (history tail, then live
  events up to about 5 s ago). Purchases through our own carousel are **not** in that sequence: they are not in
  `shop.events`. They only reach the guard, which drops them.
- Conversion per arm goes into `LIVE.md` every hour, with new-shopper conversion.
- Your scorer change is live. One request for v3 and later: no scorer change if you can avoid it. Each one costs
  a restart: about 15 seconds without answers and 25–40 requests on the fallback.

**Refit weights look worse for new shoppers.** 00:18–01:08 UTC, v1 with refit weights against v1 with default
settings: 1.81% against 2.07% overall (within noise), but 1.72% against 3.21% for new shoppers (19 and 36
purchases; 2.3 standard errors). The refit also disagrees with itself: fitted on all rows it asks for `new` 4.9,
on each half for 1.2–1.4. A fit on shown products rewards what the policies already pushed. Unless the next hour
turns it around, the refit arm is pruned at 02:10 and default settings stay.

**Network:** 01:15:18–01:16:15 UTC the machine lost its connection to RawTree (timeouts, then failed name
lookups): about 40 requests went to the fallback. It recovered by itself. Offline downloads on the same machine
also cost a few fallbacks per minute while they run, so they are kept short.

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
