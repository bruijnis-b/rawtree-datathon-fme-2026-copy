# Cold users in the live practice stream: findings and user-tower proposals

Sun 15 Nov 2026, 01:30 CET. Data: live snapshot 1 (Sat 14 Nov 09:00–21:00 UTC) and the 60-day history.
All numbers are from the **exploration split** (users outside the live hold-out, before 19:00 UTC) unless marked
*hold-out* (held-out users plus the last 2 hours; used once, as a confirmation). Intervals are 95 %.
Scripts: `training/analysis/cold_*.py`; raw output: `out_*.txt` in this folder.

## Short version

1. **Cold users do not buy more organically. They buy more from the carousel.** In `shop.events`, cold and known
   users are indistinguishable (18.6 % vs 18.4 % of sessions end in a purchase; same categories, prices, top
   products). In our carousels, `is_new_user` requests click 1.64× [1.49, 1.82] and buy 2.87× [2.38, 3.51] as
   often.
2. A user-level "buys more" effect **does not change the ranking inside a request**. What changes the ranking is
   *which* products get the extra purchases: the user's **open cart**, the user's **own categories**, **popular**
   products (more so for new users), and never a product the user **already bought**.
3. The model's single type-weighted history vector (view 1, cart 2, purchase 4) cannot tell an open cart (the
   best signal we have) from a past purchase (the worst). Splitting it is proposal 1.
4. In the scored window (the first two hours of a stream) new users will have **far less live history** than in
   our hold-out: 70 % of new-user requests have none in the first hour, 33 % in the second. Our hold-out starts
   three hours in, where 2 % have none. Proposal 2.

## Findings

### 1. Purchase propensity

**Who is cold.** The two definitions are the same set: 17,122 of the 17,126 cold users with a request are flagged
`is_new_user`, and 1 flagged user is in the history. Cold users do not arrive during the day: 52 % are first seen
in the first hour, 78 % within two hours and 99 % by 15:00 UTC, so "cold" is a fixed cohort, not a flow of arrivals.

**Organic events: no difference** (`out_propensity.txt`). A session's events all carry one timestamp (within
60 ms), so the session is the unit and "events per minute" does not exist.

| Organic, per class | Cold | Known |
|---|---|---|
| Sessions with a purchase | 18.63 % [18.41, 18.85] | 18.39 % [18.25, 18.54] |
| Purchases per event | 4.58 % | 4.52 % |
| Sessions with an add-to-cart | 32.3 % | 32.0 % |
| Add-to-cart followed by a purchase of that product | 52.0 % | 52.2 % |
| Session of the first purchase (median) | 3rd | 2nd |

No session-phase effect either: the purchase rate is 18–19 % in a user's 1st, 5th and 10th live session, in both
classes. Device and region shift it by at most 2 points, equally for both.

**Carousels: a large difference** (62,666 answered requests, 468 purchases).

| Per carousel | Known | New | New / known |
|---|---|---|---|
| Click | 2.12 % [1.99, 2.26] | 3.46 % [3.21, 3.74] | 1.64× [1.49, 1.82] |
| Purchase | 0.48 % [0.42, 0.55] | 1.38 % [1.22, 1.55] | 2.87× [2.38, 3.51] |
| Purchase per click | 0.23 | 0.40 | |

The gap holds on every page (home 0.18 % vs 0.59 %, product 0.54 % vs 1.59 %), device, hour and number of recent
views, and it does not fade with the user's 1st, 2nd or 4th request. It is also there on the fixed fallback list
(0.42 % vs 1.55 %), so it is not caused by what our model chose to show.

It is strongly tied to the user's **own organic purchases so far**, for new users only. On the fallback list, per
1,000 impressions:

| Own live purchases before the request | New: purchases | Known: purchases |
|---|---|---|
| 0 | 0.78 | 0.34 |
| 1–2 | 1.79 | 0.44 |
| 3+ | 6.45 | 0.60 |

New users with no live event yet (438 carousels) click 1.37 % and buy 0.23 % [0.04, 1.28]: a new user without
any history is *not* a better customer than a known one.

### 2. What they buy

Organically, nothing separates the classes (`out_organic.txt`): top 10 / 50 / 100 products take 5.5 / 17 / 26 %
of purchases in both, the median reference price is €22.99 in both, category shares differ by less than 1 point,
the top-20 products are nearly the same list, 4.0 % of purchases after 10:00 are on the practice-round new
products in both, and 4.8 % vs 4.9 % are on discounted products.

In the carousel (`out_items.txt`, per 1,000 impressions):

| Shown product | Known: purchases | New: purchases |
|---|---|---|
| Organic popularity rank 1–10 | 0.63 | 2.12 |
| Rank 11–50 | 0.49 | 1.37 |
| Rank 101–500 | 0.23 | 0.46 |
| Rank 500+ | 0.05 (2 purchases) | 0 of 15,886 |
| User has no own event in the product's category (fallback list) | 0.09 | 0.62 |

New users lean more on popularity: the `is_new × log popularity` term is +0.31 (z = 3.1) for clicks and +0.43
(z = 3.8) for purchases per impression; *hold-out* +0.20 and +0.51. Known users almost never buy outside their
own categories; new users do. A Books & Media preference of new users showed up in exploration but **not** in the
hold-out, so it is noise. Reference price has no class-specific effect.

Context for Bas, not modelled here: practice-round new products get 0.4 % of our impressions but 4 % of organic
purchases, and convert well when shown (8 purchases in 1,485 impressions, about 7× the average; wide interval).

### 3. How fast a new user becomes predictable

Organic purchases of cold users against their own live events in earlier sessions:

| Own events before (k) | Same subcategory seen (chance) | Same brand seen (chance) | Same category seen (chance) |
|---|---|---|---|
| 1–2 | 5.6 % (1.4 %) | 6.7 % (2.4 %) | 29.5 % (12 %) |
| 3–5 | 11.8 % (2.0 %) | 11.8 % (3.8 %) | 41 % (15.5 %) |
| 6–10 | 19.8 % (3.5 %) | 21.9 % (6.9 %) | 59 % (24 %) |
| 11–20 | 29.9 % (5.9 %) | 36.4 % (11.9 %) | 75 % (35 %) |
| 21–50 | 47.7 % (10.3 %) | 56.9 % (20.2 %) | 87.5 % (49 %) |

The match is 2.5–4× chance from the very first events; known users show the same curve. A user's top category
holds 40 % of their events (median). In the carousel, a product in a category that holds 20 % or more of the new
user's own events is clicked 2.1× as often at k = 3–5 (10 clicks, weak), 3.3× at k = 6–10 and 4.5× at k = 21+.
So about **6 events (one or two sessions)** are enough for a useful signal.

`recent_views` in a request are *not* in `shop.events` (none of the recent views of 3,000 requests is there): they are a second,
independent view of the user. A shown product in the same category as a recent view has odds ratio 1.9 for a
click; same subcategory or same brand add nothing on top of that.

**History depth by stream hour** (new-user requests, own live events before the request):

| Stream hour | No events | 1–5 | 6+ | Median |
|---|---|---|---|---|
| 1st (09:00 UTC) | 70 % | 17 % | 14 % | 0 |
| 2nd | 33 % | 29 % | 38 % | 4 |
| 3rd | 16 % | 23 % | 62 % | 8 |
| 4th | 7 % | 15 % | 78 % | 12 |
| 10th | 0.1 % | 1 % | 99 % | 33 |

Our carousels start at 11:44 UTC, so every live number we have (and the live hold-out) describes new users with
a median of 20+ events. About 20 % of requests have no recent views at any hour.

### 4. Signals the user tower does not use

Per 1,000 impressions; odds ratios from one logistic regression per outcome that also holds slot, page,
popularity, price and the other rows (626,660 impressions; *hold-out* 372,240).

| Signal | Purchases with / without | Odds ratio, click | Odds ratio, purchase | Hold-out (click / purchase) |
|---|---|---|---|---|
| Product is in the user's open cart (carted, not bought since), new users | 38.0 / 1.19 | 3.3 | 6.2 | 3.2 / 5.3 |
| Same, known users (mostly carts from the 60-day history) | 3.26 / 0.32 | | | 3.63 / 0.47 raw |
| User already bought the product, known users | 0.09 / 0.51 | 0.06 | 0.06 | 0.08 / 0.07 |
| Share of the user's own events in the product's category (0 → 1) | 30 %+: 1.77 known, 4.42 new; under 10 %: 0.07 known | 17 | 31 | 15 / 21 |
| Product is one of the request's recent views | 15.3 / 1.38 new; 3.8 / 0.51 known | 2.7 | 3.4 | 2.2 / 3.1 |
| Own live purchases so far (per log unit, user level) | see section 1 | 1.56 | 2.6 | |
| Own live events so far (per log unit, user level) | | 0.70 | 0.50 | |

What we do with them today (our own policy, slots out of 10): **0.76 slots per known-user carousel go to products
the user already bought**; 0.06 slots per new-user carousel go to an open-cart product although half of the
new-user requests have one; 0.16 slots go to a recent view.

No effect found: minutes since the user's first or last event, number of distinct subcategories in the recent
views, a repeated product in the recent views, session number. Add-to-cart count matters at user level (3+ carts:
3.26 % purchase per carousel for new users, 0.32 % with none), but that is the open cart again.

Hour cut: `live.py` ends a sample's history at the start of its hour. For new users this drops 9 % of the
open-cart impressions and 8 % of the events; small next to the items above.

## Proposals, ranked by expected impact

Each is testable with the existing live hold-out; report new users and all users, and for new users also with the
history truncated to 0, 3 and 10 events (proposal 2 explains why).

### 1. Split the history pool into three: views, open cart, purchases

- **What.** Replace the single type-weighted mean in `pool_history` by three means over the same last-N window:
  viewed products, **open-cart** products (type cart, no later purchase of that product in the window), and
  purchased products. Each gets its own `has` flag; `u_in` grows by `2 * (d + 1)`. No data change is needed: the
  open-cart mask comes from `hp`, `ht`, `hm` in the batch
  (`bought = ((hp[:, :, None] == hp[:, None, :]) & (ht[:, None, :] == 2) & later).any(-1)`); mirror it in
  `training/export/scorer.py`.
- **Why.** The open cart is the strongest single predictor of *which* product is bought (odds ratio 5–6, both
  splits) and a past purchase is the strongest negative (0.06). With weights 1 / 2 / 4 in one mean, the tower sees
  both as "more of this", and the ID vectors then pull bought products up.
- **Expected.** Largest of the list. A direct estimate is not possible offline, but the ceiling is visible: an
  open-cart product in slots 1–3 was bought 70 times per 1,000 impressions by new users (386 impressions) against
  5.6 for an average slot-1 product.
- **Test.** Live hold-out lift, plus two diagnostics on hold-out requests: the mean rank of the user's open-cart
  products and of the already-bought products among all scored products, before and after.
- **Cheaper fallback if there is no time** (Bas, serving): drop already-bought products from the candidates and
  place open-cart products first. The bought filter alone frees 7.6 % of known-user impressions that now yield
  0.09 purchases per 1,000 instead of about 0.5.

### 2. Train and validate new users on short histories

- **What.** In live fine-tuning, replace the all-or-nothing history dropout (50 %) for samples of new users by a
  random truncation to the last k events, k drawn from {0, 1, 2, 3, 5, 10, 20, all}. Report the hold-out for new
  users at k = 0, 3, 10 and full.
- **Why.** In the first two hours of a stream, 70 % and then 33 % of new-user requests have no live event, and
  the median is 0 and then 4. The hold-out's new users have a median above 20. The current "2.11 without history
  / 2.85 with the last 50" brackets the truth; the scored window sits near the low end.
- **Expected.** No gain on today's hold-out number, a gain in the regime that is scored. It also shows whether
  the model degrades smoothly between k = 0 and k = 10.
- **Test.** New-user lift at each k; pick the variant that is best at k = 3 without losing at full length.

### 3. Let `is_new_user` scale the product bias

- **What.** `x = u·v + (1 + g · is_new) · b` with one scalar `g`, zero at the start, learned in live fine-tuning
  (like `w_new`).
- **Why.** New users' clicks and purchases depend more on popularity (interaction +0.3 to +0.5 per log unit, both
  splits), and they buy outside their own categories (0.62 vs 0.09 per 1,000) where known users do not. `w_new`
  can only move the user vector; it cannot raise the weight of the bias.
- **Expected.** Modest, on new users with a short history, where the vector is weak and the bias has to carry
  the ranking. Fifteen minutes of work.
- **Test.** New-user lift at k = 0 and k = 3; check `g` is positive after fine-tuning.

### 4. `is_new_user` offset in the purchase head, only if calibration needs it

- **What.** `c_purchase + d · is_new` (one scalar).
- **Why.** Purchases per click are 0.40 for new users and 0.23 for known ones, on every page and on the fallback
  list. Without the offset the model has to push `x` up for all products of a new user to fit this.
- **Expected.** No ranking change by itself (same shift for all ten candidates). Worth it only if the calibration
  of new-user scores is off, or if Bas's layer adds its corrections in a way that depends on the score level.
- **Test.** Calibration split by `is_new`; lift should not move.

### 5. Activity scalars in the user tower (low priority)

- **What.** `log1p` of the number of events, purchases and open carts in the history window as three extra inputs
  to `u1`.
- **Why.** Purchases so far raise and events so far lower the response (odds ratios 2.6 and 0.5 for purchases),
  and for new users the fallback list sells 8× better to those with 3+ purchases. These are user-level effects,
  so they move the ranking only through interactions the tower may or may not find.
- **Test.** Hold-out lift; drop it if the gain is within the seed noise (±0.005).

### Not worth building

Session depth, time since the first or last event, events per minute (sessions are instantaneous), category
concentration or re-views in `recent_views`, a separate taste profile for new users, device or region
interactions with `is_new`: none shows an effect.

## Caveats

- Carousel numbers are conditional on what was shown (fallback list until 15:00 UTC, our early policies after).
  The regression controls for slot and popularity, not for everything the policy saw.
- New-user purchases in the exploration split: 257; in the hold-out: 180. Interactions with `is_new` below
  z = 3 should be read as hints.
- Standard errors of the regressions ignore that a user has several requests.
- Popularity is the organic purchase count over the whole exploration split, not strictly before each request.
- Whether the final round starts a fresh stream (new shoppers with no events at 10:00) is an assumption from the
  practice stream's first hours.

## Reproduce

```bash
python -m training.analysis.cold_propensity   # Q1
python -m training.analysis.cold_organic      # Q2, Q3 on organic events
python -m training.analysis.cold_items        # Q2-Q4 on carousels, regressions (COLD_SPLIT=holdout to confirm)
python -m training.analysis.cold_checks       # fallback-only, hour cut, slots spent, history depth by hour
```

Data folders default to Jules's laptop paths; override with `RAWTREE_LIVE` and `RAWTREE_HISTORY`.
