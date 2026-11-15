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

## 2026-11-15 07:50: own check confirms dropping `new=2`

200 products were released after 00:59 UTC, so v3 and v4 never saw them: the final round's case. Lift on top of
the v3+v4 average, list position held constant, viewed products left out, logged answers after 00:59 UTC:

| Products | Shown | Bought | Lift on top of the model |
|---|---|---|---|
| Unseen, 0–1 h old | 4,417 | 4 | x0.88 |
| Unseen, 1–3 h old | 7,679 | 16 | x1.28 |
| Unseen, 3 h+ old | 6,771 | 7 | x0.78 |
| New but known to the models (released before 00:59) | 27,015 | 91 | **x2.77 (1.77–3.35)** |

The premium is in new products the models already know, not in unseen ones: unseen products sit around x1 (27
purchases in all, so a small effect either way cannot be ruled out). `new` stays 1.

## 2026-11-15 07:40: reply to the trainer's final hand-off: `new` back to 1

Thank you; read in full.

- **`new=2` withdrawn, `new` stays 1.** The 07:20 verdict named this exception, and both of your checks meet it:
  products unseen by the models already got 1.3-1.6x their purchase share of slots (held out of v10/v11, and the
  100 released at 02:00 unseen by v2-v4), and fresh products sell below average (0-1 h 0.56x, 1-4 h 0.89x; the
  premium my fits found sits in products out for 4 h or more). Small counts in the fresh rows; the direction is
  what decides it.
- **Final setup (PR #20): the v10+v11 average with default settings**, your pick. It has run live since 06:40 as
  `m655200`. The decision record is in `recsys/README.md`, "Final setup".
- `new_view` off, no routing, no change for new shoppers without views: agreed.
- Cart x2.5: noted as the one wrapper setting with real offline support. Not separated live, so not in the final
  setup.

## 2026-11-15 07:20: verdict on `new` and `new_view` (Bas: no new test runs; act only on what the data supports)

- **`new` (all products added during the event): set to 2 in the final setup.** Supported offline on top of a
  model three times out of four (v1/v2 x2.7, v3+v4 x2.3 and x3.3, ranges above 1). 2 is below every fitted value
  that held up, so it errs on the safe side. No live arm for it; it goes in with the final switch, on whichever arm
  wins. Our own results agree in direction: models under-score new products even when they know them by ID; the
  final round's 300 products they do not know at all.
- **`new_view` (extra lift on requests that viewed a new product): stays off.** No fit separates it from `new`
  (x3.3 against x2.3, ranges overlap), and its one live test (`cold_combined`) lost.
- **New shoppers without recent views:** no change; 40 purchases support nothing.
- Exception: if the trainer's held-out check on v10/v11 shows unseen products already get their share of slots or
  more, `new` stays at 1.

## 2026-11-15 07:10: the two cold gaps, and the newness multipliers

Logged answers after 00:59 UTC (unseen by v3 and v4), score = mean of v3 and v4: 65,581 answers, 1,381 purchases.
Lifts are fitted on top of that score with list position held constant; ranges are 5–95% from a bootstrap over
answers. Offline fits on shown products only, so treat them as leads, not proof.

| Segment | Share of answers | Conversion | Purchases |
|---|---|---|---|
| Viewed a new product | 17.4% | 2.29% | 261 |
| New shopper, no recent views (all on the home page) | 6.1% | 1.00% | 40 |
| New shopper with views | 18.9% | 3.26% | 404 |
| Warm | 57.6% | 1.79% | 676 |

**Requests that viewed a new product:** new products sell **x3.3 (1.8–4.2)** more than the model expects; on
all other requests x2.3 (1.2–2.7). The viewed new product itself gets nothing extra (x1.1, 0.4–1.7), nor does its
subcategory (x0.85). So `new` (all new products) is supported offline; `new_view` (extra on these requests) is not
separately: x3.3 against x2.3 overlap.

**New shoppers without recent views:** 40 purchases, too few to support any change. Popularity adds nothing on top
of the model; cart x4 (1.6–8.6) is already covered by the default x6.

**Evidence behind `new` and `new_view` so far:**

| Setting | Where the value came from | Live |
|---|---|---|
| `new` = 2.5 in `combined` | Logistic fit on the practice day, policy without a model | `combined` lost to every model arm |
| `new` = 1 in `embed_score` | Assumption: "the model scores new products from their fields" | All default arms |
| `new` on top of a model | Offline: v1/v2 x2.7 (1.8–4.1); v3/v4 x1.4 (0.6–3.9, 01:00); v3+v4 x2.3 (1.2–2.7, now) | Only inside `m8277ec` (1.5), mixed with five other changes |
| `new_view` = 3 (`cold_combined`), 6 (`cold_embed`) | 17 purchases, practice day, policy without a model | `cold_combined` lost: −10% conversion, −17% cold |

**Caveat that matters for the final round:** v3, v4, v10 and v11 all know the practice new products by ID (they
were fine-tuned on them) and still under-score them. The 300 products of the final round are unseen by every model.
Nothing measured tonight is on unseen products. **Trainer:** please give, for v10 and v11, the share of top-10
slots that products held out completely (content only) get, against their share of purchases. That is the only
evidence that can set `new` for the final round.

## 2026-11-15 06:50: correction: the route arm's cold side was not chosen on evidence

At 06:27 I sent cold requests to the v2+v3 average because it had the highest cold conversion. Paired per quarter
hour (official cold conversion, both arms over the same minutes), none of the differences is near significant:

| Comparison | Period (UTC) | Cold requests | Difference in cold conversion | Quarter hours won |
|---|---|---|---|---|
| v2+v3 average vs v4 | 02:30–06:15 | 4,578 / 4,499 | +0.18 ± 0.20 | 9 of 15 |
| v2+v3 average vs v2 | 02:30–05:30 | 3,482 / 3,431 | +0.01 ± 0.18 | 6 of 12 |
| v2+v3 average vs v3+v4 average | 05:30–06:30 | 1,397 / 1,322 | +0.15 ± 0.19 | 3 of 4 |

The warm side (v3+v4 with multipliers from offline fits) rested on 797 requests, so on even less. The route arm is a
live test of an idea, not a setup backed by data; it is only a candidate for the final round if it wins clearly.

## 2026-11-15 06:42: v10+v11 live; reply to the trainer's 06:36 note

**v10 and v11:** sha256 match the cards; 7 data files each, flat; dry run of the v10+v11 average for 100 s: 0
policy errors, p95 0.8–1.1 s. **Live since 06:40 UTC as `m655200`, default settings, 25%**, in place of the
v2+v3 average (weakest arm since 05:31). It reads straight against `m9f6fa4` (v3+v4, default settings): same
setup, older models. Agreed on not mixing fresh and old models in one average.

Official since 05:31 UTC (score; cold / warm conversion):

| Arm | Score | Requests | Cold | Warm |
|---|---|---|---|---|
| v3+v4, multipliers from offline fits (`m8277ec`) | 63.7 | 1,471 | 2.33% | 2.03% |
| v3+v4, default settings (`m9f6fa4`) | 63.0 | 3,349 | 2.42% | 1.93% |
| route (`me5b04d`), from 06:26 | 62.7 | 464 | 2.50% | 1.82% |
| v2+v3, default settings (`m09c26e`), pruned | 60.5 | 3,354 | 2.50% | 1.73% |

No gap is near two standard errors.

**Your offer of v12/v13 (more seeds):** not now. Four arms already split the traffic and the final round starts at
09:00. If v10+v11 leads at 07:40, I may ask for v12 to build a fresh cold-side pair for the route arm; I will say
so here. **Your research sweep:** deliver a variant only if it clearly beats v10/v11 on your carousel hold-out;
anything after about 07:45 only gets checks, no live test.

## 2026-11-15 06:27: cold routing live

Every team above us beats us on cold requests by 0.2–1.3 points of conversion, not on warm ones. Two teams send
cold requests to a separate model. New policy `route` (`recsys/policies/route.py`): a cold request (new shopper,
or a recent view of a product added during the event, the official definition) goes to one policy, the rest to
another. Live since 06:25 UTC as `me5b04d`:

| Side | Policy | Why |
|---|---|---|
| Cold | v2+v3 average | Best cold conversion on the most data: 2.66% over 3,722 cold requests (v4 2.44%, v3+v4 2.47%) |
| Warm | v3+v4 average, tuned layer | Best warm conversion so far: 2.27% (797 requests), v3+v4 default 1.96% |

Per-arm cold and warm conversion since 03:22 UTC (official, expected; ± one Bernoulli standard error, which
overstates the noise of expected conversion):

| Arm | Cold requests | Cold conversion | Warm conversion |
|---|---|---|---|
| v2+v3 | 3,722 | 2.66% ± 0.26 | 1.78% ± 0.19 |
| v2 | 2,493 | 2.56% ± 0.32 | 1.47% ± 0.21 |
| v3+v4 | 1,138 | 2.47% ± 0.46 | 1.96% ± 0.35 |
| v4 | 3,603 | 2.44% ± 0.26 | 1.75% ± 0.19 |
| v2, recent views x2 | 2,461 | 2.42% ± 0.31 | 1.75% ± 0.23 |
| v3+v4 tuned | 346 | 2.28% ± 0.80 | 2.27% ± 0.70 |

Honest caveat: the cold differences between our arms are within noise. Routing can only gain where the two
halves really differ; the large gap to the other teams on cold is not explained by any of our arms.

## 2026-11-15 06:03: the tuned layer is live as one arm

Until now every live arm used the default wrapper settings, which were fitted for a policy without a model. Since
06:02 UTC `m8277ec` runs the v3+v4 average with every factor the offline fits support: cart x2.5 (x6 before),
discount lift capped at x1.3, shopper's category and subcategory shares of views on (1 and 1), new products x1.5,
live popularity 0.3; trend x8 and the bought filter as before. It differs from `m9f6fa4` only in those settings,
so the two read straight against each other. Caution: the evidence for each factor is offline, on our logged
answers, which ranked the recipes backwards; a similar package on v1 lost live last night.

For the trainer: when v10/v11 arrive, I test them with the setting that is leading by then (default or tuned).

## 2026-11-15 05:45: reply to the trainer's 05:30 "FINAL: v4"

Agreed as the fallback: if nothing else arrives, the final round runs v4 or the v4-containing average, whichever
leads round 3 at 08:30 UTC. But the final round starts at **09:00 UTC, not 05:30**: there are three hours of
practice traffic left, and our gap to the leader (about 5 points) is real. So my 05:32 asks still stand, if your
compute allows:

1. **v4's recipe on a snapshot from now** (05:30 or later), delivered by about 07:30 UTC for an hour of live test.
   Fresher live data is the one lever we know works: v1 to v2–v4 was the largest gain of the night.
2. If there is room, one model of v2/v3's recipe on the same snapshot, for a cross-recipe pair (`m9f6fa4`, v3+v4,
   is testing that idea live now).

If neither can be done by 07:30, say so in `TRAINER.md` and v4 stands. No apology needed for the crash.

## 2026-11-15 05:32: TRAINER, START HERE (what happened while you were away)

**Live verdict after three hours** (official expected score, 02:30 – 05:25 UTC, about 7,900 requests per arm):

| Arm | Score | Conversion | Cold conversion |
|---|---|---|---|
| v2+v3 average | 60.8 | 2.10% | 2.62% |
| v4 | 60.3 | 2.10% | 2.40% |
| v2, recent views x2 for new shoppers | 58.2 | 2.04% | 2.37% |
| v2 | 57.1 | 2.00% | 2.63% |

- **v4's recipe is back in.** v4 and the v2+v3 average are level; v2 on its own is the weakest in every reading.
  My 02:20/02:40 advice ("v2's recipe wins, skip v7") came from an offline AUC that ranked the recipes the wrong
  way round. Your carousel measure was closer.
- Averaging two models helps: the average beats both of its members' recipes as single models (v2 here, v3
  earlier at 59–62).
- Team since 02:30: 59.1, 6th. Leader team_06 65.7. Our gap is mostly cold conversion (theirs 2.73%).

**Live now, since 05:31 UTC, a third each:** v4 (`mab651f`), v2+v3 average (`m09c26e`), **v3+v4 average**
(`m9f6fa4`, new: one model of each recipe). Question: is mixing recipes better than one recipe alone?

**What I need from you, in this order:**
1. **v4's recipe on the freshest snapshot you can finish** (the planned v7, or newer). Deliver it the moment it
   exists.
2. **v2/v3's recipe on the same snapshot** (one seed is enough), so the best pair can be averaged on fresh data.
3. A note in `TRAINER.md`: what is training, and when each will land.

Scoring starts at **09:00 UTC**. Anything delivered before about **07:30 UTC** gets a live test of at least an
hour; later than that it only gets checks. No scorer change, please. I check the branch every 15 minutes.

## 2026-11-15 05:10: half an hour later the average has caught up; v2 alone is the weak one

Official score, 02:30 – 05:07 UTC, 7,000 requests per arm, ten quarter hours:

| Arm | Score | Conversion | Cold conversion | Against v2 per quarter hour | Quarter hours won against v2 |
|---|---|---|---|---|---|
| v4 (`mab651f`) | 61.1 | 2.13% | 2.41% | +5.1 ± 2.8 | 7 of 10 |
| v2+v3 average (`m09c26e`) | 59.9 | 2.09% | 2.59% | +4.3 ± 6.2 | 7 of 10 |
| v2, recent views x2 (`mac2638`) | 58.0 | 2.04% | 2.38% | +2.9 ± 4.1 | 4 of 10 |
| v2 (`med6134`) | 55.4 | 1.96% | 2.56% | reference | |

- v4 against the average: +0.8 ± 5.9. **No difference between them.** My 04:40 entry said the average shows no
  gain; its last three quarter hours were 69, 72 and 75, and it is now level with v4. The 04:40 requests stand
  (deliver v4's recipe on fresh data), but the average is not written off.
- What holds across every reading: **v2 on its own is the weakest**, and nothing is separated by two standard
  errors. Three hours of live traffic cannot rank these recipes more finely than that.
- v4 is the steadiest (± 2.6 between quarter hours; the average ± 4.1) and has the best conversion; the
  average has the best cold conversion.
- Recent views x2 for new shoppers: cold conversion −0.21 ± 0.22 against v2. No gain; it stays off.
- Team since 02:30: 58.6, 5th; team_06 65.3, team_03 61.8, team_37 61.7.

Nothing from the trainer since 02:35 and no model since v4. If nothing arrives by 05:30 the final choice is
between what is here: v4, or an average that includes v4.

## 2026-11-15 04:40: URGENT for the trainer. Live, v4's recipe leads. Deliver v7; do not drop that recipe

I was wrong at 02:20 and 02:40. Two hours of the official expected score, four arms side by side at 25% each,
5,600 requests per arm (02:30 – 04:37 UTC):

| Arm | Score since 02:30 | Per quarter hour (8), mean ± s.e. | Against v2, same quarter hours |
|---|---|---|---|
| **v4** (`mab651f`) | **61.2** | 61.9 ± 2.1 | **+6.5 ± 2.7** |
| v2, recent views x2 (`mac2638`) | 57.5 | 57.8 ± 2.2 | +2.3 ± 4.9 |
| v2+v3 average (`m09c26e`) | 56.5 | 56.0 ± 4.3 | +0.5 ± 7.2 |
| v2 (`med6134`) | 56.1 | 55.5 ± 3.5 | reference |

- **v4 is ahead of v2 by 2.4 standard errors**, and it is the steadiest arm (51–70 per quarter hour; v2 37–67).
- **The average of v2 and v3 shows no gain live** (+0.5 ± 7.2), against +0.011 AUC offline.
- So my purchase AUC on our logged answers ranked the recipes the wrong way round. Those answers are lists that
  earlier policies chose; a model is scored only on products that were shown. Your held-out carousel measure
  preferred v4's configuration and the live score agrees with it. **Trust your measure over my offline AUC.**

**What I ask for the final delivery (deadline 05:30 UTC, 50 minutes from now):**
1. **Deliver v7** (v4's recipe on the 03:30 snapshot) if it exists. Ignore my "skip v7".
2. **The final model should be v4's recipe on the latest snapshot you can finish**, not the v8+v9 pair of the
   other recipe. If you can only finish one thing, finish that.
3. If both recipes are ready, deliver both; I serve what the evidence supports and can average a pair, but an
   average has not earned its place live.
4. If nothing new arrives in time, **the final model is v4 as it is**: it has the most live evidence of anything
   we have.

## 2026-11-15 02:40: reply to the trainer's 02:35 plan

Agreed on all of it. Three points:

- **Skip v7** (v4's recipe on the 03:30 snapshot). I asked for both recipes at 02:20, before the official scores
  were in; they have settled it. Use the compute for something that can help the average instead: a third seed,
  or one member trained with a different data cut (v2 and v3 differ in data, not only in seed, and their average
  beat both: +0.011 AUC, and 69.6 on the official score over its first 558 requests against 59–62 for single
  models).
- **v5 and v6 (about 04:10):** I check and dry-run them and score v5, v6, v5+v6 and v2+v3 offline on answers after
  03:30. They do not go live while the four arms are frozen, unless the pair is two standard errors ahead.
- **v8 and v9 (about 05:15) as the final pair:** fine as the plan. They arrive too late for anything but the
  checks (sha256, dry run, a short offline score), so the fallback order is v8+v9, then v5+v6, then v2+v3, which
  is the only pair with live evidence. Please deliver v8 and v9 by 05:15 at the latest.
- New since your entry: a fourth arm, v2 with a new shopper's recent views x2 (`mac2638`), see the 02:32 entry.
  It asks you one thing: can the model take "this product is in the recent views" as an input?

## 2026-11-15 02:32: cold requests, where we lose to the other teams

Logged answers of the model arms (v1–v4) since 23:37 UTC, 14,304 answers. Purchases counted, so read the sizes,
not the decimals.

**Who is cold:**

| Request | Share of answers | Conversion | Recent views |
|---|---|---|---|
| New shopper, 1–2 recent views | 13.5% | 4.11% | 1.5 |
| New shopper, 3+ recent views | 9.9% | 3.39% | 3.9 |
| New shopper, no recent views (home page) | 6.2% | 1.12% | 0 |
| Known shopper who viewed a new product | 10.3% | 1.69% | 3.2 |
| Warm | 60.1% | 1.74% | 1.8 |

Cold is mostly new shoppers with a few views, and they buy twice as often as anyone else.

**What a new shopper with recent views buys from us** (purchase rate per shown product):

| Shown product | Share of slots | Rate |
|---|---|---|
| In their cart | 8.5% | 1.5–1.9% |
| One of their recent views | 2.3–2.9% | 0.9–1.0% |
| Same category as a view, other subcategory | 26–30% | 0.28–0.41% |
| Same subcategory as a view | 19–21% | 0.16–0.20% |
| Anything else | 37–43% | 0.15–0.19% |

- **We show only 14% of a new shopper's recent views; 75% of their answers contain none.** When one is shown it
  sells five times as often as an unrelated product. `embed_score` has `recent` = 1 because "the model covers
  recent views". It does not cover the viewed product itself: in training that product is removed from the
  context (trainer, 01:05).
- Fitted on top of v2's score, with list position held constant (answers after 21:00 UTC, 869 purchases):

| Factor | New shopper | Known shopper |
|---|---|---|
| A recent view itself | **x1.6** (1.3–3.4) | x1.05 (0.8–2.6) |
| In the cart, not bought | **x3.4** (2.9–4.5) | **x2.6** (1.8–3.5) |
| Same subcategory as a view | x1.0 | x0.7 |
| Same category, other subcategory | x1.2 (1.0–1.7) | x1.0 |

- So two wrapper settings are off for cold requests: recent views (x1 live, x1.6 fitted) and cart (x6 live, x3.4
  fitted for new shoppers, x2.6 for known ones, where cart products fill 37% of the slots).
- A product from the **same subcategory** as a view sells no better than the model expects, and worse than one
  from a neighbouring subcategory. More of the same is not what these shoppers buy.

**Live since 02:29 UTC:** `mac2638` = v2 with a new shopper's recent views x2 and nothing else changed. Known
shoppers get exactly v2's answers, so its cold conversion is read straight against `med6134`'s.

**For the trainer:**
- The viewed product itself is a blind spot by construction. Can the model get an explicit "this product is in
  the recent views" input, so it learns the size of the effect per shopper type instead of our flat x2?
- New shoppers buy from the neighbouring subcategory more than from the viewed one. Does the model see that?

## 2026-11-15 02:25: our models against the other teams, on the official numbers

The public leaderboard has a per-model view with **expected** conversion (the simulator's probabilities, not the
purchases that happened to fall). It is the real score and far less noisy than counting purchases, which is what
every table above this entry does. `handoff/tools/board.py "<from>" "<to>"` (UTC, 15 min to 3 h; run from the repo
root with the `.env` loaded) prints it for our arms and for every team. **Use this from now on, both of us.**
Score = our estimate of the leaderboard score out of 100 from the two conversions (`monitor/data.py`).

**Last 3 hours (23:23 – 02:23 UTC), single models with 2,500+ requests:**

| Whose | Model | Score | Conversion | Cold conversion | Requests |
|---|---|---|---|---|---|
| team_06 | their best | 74.3 | 2.58% | 3.30% | 3,140 |
| team_17 | their main | 67.7 | 2.40% | 3.10% | 10,671 |
| team_06 | 2nd–4th | 66.4–67.4 | 2.36–2.40% | 2.99–3.13% | 3,159–8,825 |
| team_14 | their best | 66.9 | 2.38% | 2.94% | 9,117 |
| team_42 | their best | 65.2 | 2.33% | 2.97% | 5,922 |
| team_03 | their main | 62.7 | 2.26% | 2.90% | 19,451 |
| team_37 | their main | 62.5 | 2.27% | 2.74% | 17,440 |
| **us** | **v2** | **61.0** | 2.23% | 2.59% | 3,090 |
| **us** | **v3** | **60.9** | 2.22% | 2.83% | 2,921 |
| us | v4 (last 70 min) | 56.9 | 2.07% | 2.85% | 1,990 |
| us | v1 | 55.7 | 2.07% | 2.70% | 7,806 |
| us | v1 refit | 49.9 | 1.91% | 2.42% | 5,551 |
| us | `combined` | 38.2 | 1.59% | 2.06% | 4,266 |
| organisers | reference | 51.4 | 1.98% | 1.80% | |

Team scores over the same 3 hours: team_06 65.2, team_03 61.6, team_17 61.0, team_14 59.1, team_42 58.4,
team_22 57.4, team_26 53.1, **us 51.7 (8th)**.

- **Our rank understates us.** The team score is the average over every arm we tried, the weak ones included.
  Had v2 or v3 answered everything, we would have scored about 61: 2nd to 4th, 4 points behind team_06.
- **The gap to the best is real: about 7% in conversion** (2.22% against 2.37–2.40%) and more on cold requests
  (2.6–2.8% against 3.0–3.3%). Cold is where the others are ahead of us.
- **v2 and v3 are equal** (61.0, 60.9) and both clearly above v1 (55.7). v3 is better on cold requests.
- **v4 is behind v2 and v3** over its 2,000 requests (56.9). That is the trainer's candidate recipe.
- Two teams (26, 01) have models whose conversion equals their cold conversion exactly: those models answer only
  cold requests. They send cold and warm requests to different models. Worth a thought for us: v3 and v4 are
  our best on cold, v2 on warm.
- Noise: over 20–40 minutes one arm's score still swings by 10 points or more (v1: 38.7, then 63.4). Trust
  3,000+ requests.

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
