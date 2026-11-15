# Trainer notes (trainer writes this; newest on top)

Notes, questions and plans for the server. Model details go in `handoff/models/<name>.md`.

## 2026-11-15 07:30 UTC: FINAL HAND-OFF (trainer side is finished; nothing else comes)

**Server: this is the last entry from the trainer side.** Written by the research session on Jules's request. The
final models are **v10 and v11** (`handoff/models/`, training data ends 06:24 UTC). No v12/v13, no scorer change,
no further delivery. Open questions go to Jules in person.

### 1. Research sweep: the embeddings are as good as this recipe gets

22 check runs on snapshot 3 (live hold-out, 2,869 held-out carousel clicks, 2 seeds; seed spread 0.02–0.05).
Carousel hold-out, all / new shoppers:

| Variant | v10's recipe | v11's recipe |
|---|---|---|
| baseline (= v10, v11) | 1.41 / 0.92 | 1.43 / 0.92 |
| recency weighting, 6 h half-life | 1.41 / 0.92 | 1.43 / 0.90 |
| 25 % history batches | 1.36 / 0.87 | 1.40 / 0.89 |
| 4 epochs | 1.37 / 0.87 | 1.32 / 0.78 |
| lr 1x | 1.38 / 0.88 | 1.29 / 0.72 |
| learning from our own carousels | 1.15 / 0.68 | 1.03 / 0.56 |

Nothing beats the baseline. The two recipes are level on this snapshot (v10's lead on snapshot 2 is gone).

### 2. Your 07:10 ask: unseen products already get their share, so `new` should stay at 1

- **Held-out products (content only), check runs of v10 and v11:** 0.92 % and 1.19 % of top-10 slots against 0.73 %
  of purchases (1.3x and 1.6x). By your own exception in the 07:20 verdict, `new` stays at 1.
- **Live, the same thing:** the 100 products released at 02:00 UTC were unseen by v2, v3 and v4. 02:30–05:25 they
  got 2.4 % (v4) to 3.9 % (v2) of our slots against 2.0 % of organic purchases, and sold 1.8 per 1,000 showings
  against 2.0 for old products (20 purchases in 10,930 showings).
- **Why your fits ask for x2.3:** the premium is in products that have been out for hours, not in fresh ones.
  All team answers of the practice day, per showing against the slot average, viewed products left out:

  | Product age when shown | Showings | Purchases | vs slot average |
  |---|---|---|---|
  | 0–1 h | 4,330 | 3 | 0.56x |
  | 1–4 h | 17,548 | 23 | 0.89x |
  | 4–12 h | 26,737 | 47 | 1.39x |
  | 12 h+ | 26,629 | 88 | 2.44x |

  Organically a new product is viewed 1.03–1.11x as often as an old one at every age, with the same purchases per
  view. In the final round every new product is 0–2 h old, so `new=2` would push products that sell at or below
  average. Small counts in the first two rows (26 purchases): the direction is clear, the size is not.
- **`new_view` off: agreed.** On requests that viewed a new product, new products of the same category sold 3.7–7x
  the slot average (32 purchases), other new products 1.5x; organically there is no new-to-new pull (next view is
  new in 6.9 % of sessions against 6.0 %). A hypothesis, not a setting.

### 3. Pros and cons of what you can run at 09:00

| Setup | For | Against |
|---|---|---|
| **v10+v11 average, default settings** (my pick) | 5.5 h more live data than v3+v4, both recipes, same score level, averaging beat single models all night | about two hours of live evidence by 09:00 |
| v3+v4 average | most live evidence of any pair (since 05:31) | training data ends 00:59 |
| One model alone | simplest | single models lost to averages in every period |
| Cold/warm route | none measured | no cold difference above one standard error between any of our arms |
| Offline-fitted multipliers | cart 2.5 matches the fits on top of the model (x2.6–3.4; the default is x6) | `w_cat`, `w_sub`, `alpha` repeat what the model has (AUC +0.008 on v2); `new=1.5` see section 2; live 63.7 vs 63.0, within noise |

If you change one wrapper setting on the winner, the cart factor is the one with the most support.

### 4. What the models do and do not cover (so nothing is corrected twice)

- **In the model:** product content and identity, shopper history (100 events, history plus live), the request's
  recent views, device, region, page, hour, `is_new_user`.
- **Not in the model, yours:** discount (the model gets the original price; its own discount weight is −0.07), stock,
  already bought, open cart, trend. Checked: outside trend windows the subcategories that trended earlier are not
  over-shown (3.6 % of slots against 4.8 % of organic purchases).
- **The viewed product itself** is ranked like any similar product, by design (in the list for 10 % of views, old
  and new alike). Your x2 test for new shoppers showed no gain; I have nothing that says otherwise.

### 5. What to expect in the final round

- **300 new products at 09:00:** embedded from their fields by your sync; expect them near their organic share of
  slots (about 5 % of the catalogue). No model knows them by ID; the checks above are on exactly that case.
- **Trend:** practice trends started every 2 hours at :30 and lasted 45 minutes, one subcategory each (03:30
  Sneakers, 05:30 Watches). By that schedule the next are 07:30 and 09:30. In the Sneakers window trending products
  got 7.3 % of our slots against 6.2 % of organic purchases and sold 0.17 % per showing against 0.21 % for the
  rest: x8 is about right, slightly strong. Conversion inside trend windows equals outside (2.05–2.08 % vs 2.14 %).
- **Known weak spot:** a new shopper without recent views (6 % of answers, 1.1 % conversion). The model has only
  device, region, page and hour there. Agreed that 40 purchases support no change.
- **Calibration:** v10 0.12, v11 0.25 (max decile error). Rankings are unaffected; treat v11's level with care in
  any refit.

## 2026-11-15 06:36 UTC: v10 and v11 delivered (training data ends 06:24 UTC)

Both of your asks are on the branch (`0ff21b9`, `01649a8`), 25 minutes early. No scorer change; all checks pass.
- **v10 = v4's recipe**, **v11 = v2/v3's recipe**, same bases as v4 and v3, fine-tuned on the live stream up to
  **06:24 UTC**. Evaluate both on answers after 06:24.
- **Offline, same hold-out for both** (last 2 h + 20 % of live users): the recipes are level on our carousels (v10
  1.42, v11 1.41) and on organic purchases (2.49, 2.52); v10 is better calibrated (0.12 vs 0.25), v11 has the higher
  purchase AUC (0.757 vs 0.742, 1.6 s.e.). Nothing separates them offline, which fits your live table. So the
  **v10+v11 average** is what I would test first, against v3+v4.
- **Score level:** both fresh models score higher than their parents (about +0.2 log-odds for v10 against v4, +0.4
  for v11 against v3; the recalibration is refit per snapshot). Averaging a fresh model with an old one mixes the two
  levels; averaging v10 with v11 does not.
- **For your cold/warm route:** v10+v11 fits the warm side. If you want a fresh same-recipe pair for the cold side
  (as v2+v3 is now), the other seeds are trained: I can deliver a second seed of v11's recipe as v12 (and of v10's
  as v13) within minutes. **Say so in `FINDINGS.md`**; I check the branch every few minutes.
- **Still running:** a research sweep on the same snapshot (learning from our own carousels, recency weighting, more
  epochs, learning rate), verdict by 07:25 UTC. If a variant clearly beats these on the carousel hold-out I deliver
  it by about 07:45; otherwise v10 and v11 are my final models and nothing else comes.

## 2026-11-15 06:25 UTC: trainer back; v10 and v11 training now, ETA 07:00

Read your 05:32, 05:45 and 06:03 entries. Answers:
- **Why 05:30 was missed:** the trainer's laptop session went down from 02:31 to 05:29 UTC (Windows logoff, exit
  0xC000026B, which killed every background job: the 03:30 and 04:50 snapshots and v5–v9 never ran). After that the
  GPU cluster needed a fresh SSH login. The CPU fallback (v10b) promised at 05:50 died with the previous session;
  it is not coming. **Final model so far: v4.**
- **Now (06:25):** the cluster is reachable again. Exporting a fresh live snapshot (to ~06:25 UTC) and publishing it,
  then training both of your asks in parallel on it:
  - **v10 = v4's recipe** (v1's configuration, 100-event history, all-history base fine-tuned on all live data).
  - **v11 = v2/v3's recipe** on the same snapshot (one seed), for the cross-recipe pair v10+v11.
- **ETA: both by ~07:00 UTC**, each delivered the moment it passes parity, latency, loader and a 70 s dry run.
  Cards will give the training-data end time and the check run's offline numbers. **No scorer change.**
- If either slips past 07:30 I will say so here; v4 (or your v4-containing average) stands as the fallback.

## 2026-11-15 05:50 UTC: fresh v4 on its way

Understood: scoring starts 09:00 UTC. Doing now:
- **Live snapshot at ~05:50 UTC**, exported on the laptop (RawTree only).
- **v10 = v4's recipe on that snapshot** (all-history base, fine-tuned on all live data up to ~05:50), and
  **v11 = v2/v3's recipe on the same snapshot** (one seed), for a cross-recipe pair. Target: both by **07:00 UTC**.
- **Blocker:** the GPU cluster is unreachable from the laptop (its SSH needs a re-login by Jules). If it is back by
  ~06:30, v10 and v11 come from the cluster as above. If not, **fallback v10b**: v4 itself fine-tuned further on the
  new live data on the laptop CPU (same scorer, same interface), by ~07:15. I will write here which one it is.
No scorer change in any of these.

## 2026-11-15 05:30 UTC: FINAL: v4

**Final model: v4** (`handoff/models/v4.zip`, sha256 `ee731938…`), `embed_score:embed_model=models/v4`, default
settings. No new model: this trainer session crashed at about 02:31 UTC and was down until 05:29, so the 03:30 and
04:50 snapshots and v5–v9 were never made. Nothing changes on your side.

Why v4: it leads live on the official score since 02:30 (61.1, +5.1 ± 2.8 over v2, 7 of 10 quarter hours, the
steadiest arm) and the average with v2/v3 is level with it, not ahead (+0.8 ± 5.9). It is v1's configuration with a
100-event history and live fine-tuning up to 00:59 UTC; our held-out carousel measure preferred it too. Known
weakness: cold conversion 2.41 % against 2.59 % for the average; if you want one change for cold requests, the v2+v3
average is the alternative, but the evidence does not separate them.

Sorry for the silence since 02:35, and thank you for the 04:40 correction: it was right.

## 2026-11-15 02:35 UTC

Read your 02:20 and 02:25 entries. **Agreed: v2's recipe wins.** v4 (v1's configuration) is behind on purchases
twice (AUC 0.886 vs 0.894/0.898; official score 56.9 vs 61.0/60.9). My carousel measure (is the *clicked* product in
the full-catalogue top 10) favoured v4's configuration; your purchase AUC on our logged answers and the official
expected scores are closer to the real score, so they decide. **v4 is no longer my candidate.**

Deliveries from here (all without scorer change):
- **~04:10 UTC, from a 03:30 UTC snapshot** (training data ends 03:30): **v5 and v6 = v2/v3's configuration
  (`c_a4_25`, 100-event history), two seeds** of the all-data pipeline (same recipe as v3), delivered as a pair for
  `embed_blend`. Plus **v7 = v4's recipe** on the same snapshot, because you asked for it; I do not expect it to win.
- **~05:15 UTC, from a 04:50 UTC snapshot:** **v8 and v9 = the same pair on 80 more minutes of live data.** My
  proposal for the final setup: the average of v8 and v9 (or v5 and v6 if v8/v9 fail a check or arrive late),
  unless your three live arms show v4's recipe ahead by 05:30.

On cold requests, where the other teams are ahead: v3/v4 (all-data, practice products with ID vectors) did better
on cold than v2 in your table. Two seeds of the all-data recipe averaged should keep that. Routing cold and warm
requests to different models is your call; I have no offline evidence for it.

## 2026-11-15 01:32 UTC

**v4 delivered: my candidate for the final model.** It is v1's configuration (your live champion) with a 100-event
history, trained on all history and fine-tuned on the live stream up to 00:59 UTC (same data as v3).

Why: on snapshot 2 I re-ranked the configurations on **our own logged carousels** (1,844 held-out clicks), not only
on organic purchases. Over 3 folds × 2 seeds, v1's configuration with the longer history beats v2/v3's by +0.10
(lift 0.80 vs 0.70, ~6 standard errors; new shoppers 0.63 vs 0.55), with better calibration and new products closer
to their purchase share. v2/v3's configuration is only ahead on organic purchases (2.46 vs 2.41). This matches what
you see live: v1 stays champion.

**Suggested priority for live traffic: v4 > v3 > v2.** If you can only test one new arm, test v4 against v1.
Please tell me in `FINDINGS.md` what `med6134` (live since 01:10) is.

v5 = v4's pipeline on a 03:30 UTC snapshot, around 04:15 UTC (the last model with a live test).

## 2026-11-15 01:12 UTC

**v3 delivered** (`572db17`), earlier than planned: v2's recipe on all history and all of the live stream up to
**00:59 UTC** (evaluate after 00:59). No scorer change. On the snapshot-2 hold-out the recipe lifts live organic
2.33 → 2.48, cold 2.17 → 2.39, new shoppers with 5 events 2.10 → 2.47; our held-out carousels 0.76 → 0.72 (noise);
calibration 0.26 (above target). Details in `models/v3.md`.

Suggested order, if traffic allows: v3 next to the v1 champion first (it is the final model's pipeline), v2 second.
Both started after your 00:55 update; I have not seen either go live yet.

v4 (same pipeline on a 03:30 UTC snapshot) follows around 04:15 UTC.

## 2026-11-15 01:05 UTC

**v2 delivered** (`077ac9a`): `handoff/models/v2.zip` + `v2.md`. Training data ends 2026-11-14 19:00 UTC; please
evaluate it on answers **after 21:00 UTC**. Suggested arm: `embed_score:embed_model=models/v2`, default settings,
against the v1 champion.

**Scorer change in the same commit** (`training/export/scorer.py`, identical to `embed-sweeps`). Checked: v0 and v1
give exactly the same scores as with the old scorer (max difference 0.0 over requests with and without `events`). v2
differs only for a shopper whose history has fewer than 5 events: v2 ignores such a history (`min_history_events`
in the model). Reason: on the live hold-out a 1- or 3-event history scored *below* no history (lift 1.60 and 1.95
vs 2.02); from 5 events on it helps (2.15 at 5, 2.96 at 50, 3.02 at 100).

**Please raise `Profiles` to 100 events if it is cheap.** v2 is trained on a 100-event history. On the live
hold-out, a saved history of 100 events scores 3.02 against 2.97 with 50 (v2 still works with 50).

**A caution on v2 vs v1.** Offline, v2 is better on two measures and slightly worse on one:

| Live hold-out (19:00–21:00 UTC + 20 % of live users) | v1 | v2 |
|---|---|---|
| Organic purchases in our top 10 (lift over best sellers) | 2.32 | **2.43** |
| Our own logged carousels: clicked product in our top 10 (lift) | **0.59** | 0.54 |
| New shoppers with 5 live events (organic) | **2.39** | 2.29 |
| History hold-out (ips_hit@10) | 3.68 | **4.23** |

The carousel measure is the closest to the real score, and there v1 is ahead (each number ±0.12, so within noise).
Only the live A/B can settle it: please keep v1 as champion until v2 beats it live.

**Answers to the requests in `FINDINGS.md`:**
1. End of training data: in every card from now on (v2: 19:00 UTC; evaluate after 21:00 UTC).
2. Category views and popularity: v2 has the longer view history you asked for (100 events). We also tried the
   open cart *inside* the model (pooled cart vector + a learned in-cart term): on our held-out carousels it lost in
   every variant (−0.05 to −0.08) although the signal is real, so **keep the cart factor in your layer**. Live
   popularity also belongs in your layer: it changes during the round; the model only has a static content bias.
3. Repeat purchases: agreed. The model is never trained to predict a product from the shopper's own events on it
   (that product is removed from the context in training), and with your guard it never needs to score bought
   products. Note that the history pool weights past purchases 4×, so it leans towards similar products.
4. New products: v2 gives the held-out practice products 1.04 % of top-10 slots against 1.15 % of purchases (v1:
   1.11 %): no clear under-scoring left to fix in the model. Your ×1.4 for a new product on a request that viewed a
   new product is a reasonable factor for your layer if the refit keeps it.

**Plan (UTC):**
- **v3 ≈ 02:00:** the final recipe on *all* history and the live stream up to **00:59 UTC** (no hold-out). Same
  configuration as v2; fresher data and no held-out users or products. Its live result tells us whether the final
  pipeline is sound before the final model depends on it.
- **v4 ≈ 04:15:** the same on a snapshot taken at 03:30 UTC. Last model with a live test (before your 04:30 limit).
- **05:30:** the final choice among v1–v4: the best live result, unless it fails an offline check. I will write it
  here with the reason.

**Questions:**
- Please write conversion per arm since v2 went live into `FINDINGS.md` about once an hour (and cold conversion if
  you have it). I also read `team_33.feedback` myself.
- Does `Profiles` pass add-to-cart and purchase events as well as views, with their types? v2 weights them
  (view 1, cart 2, purchase 4).

<!-- Example entry:
## 2026-11-15 01:10
- v2 delivered. Next: v3 around 02:10, fine-tuned on the stream up to 01:30.
- Question for the server: ...
-->
