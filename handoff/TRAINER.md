# Trainer notes (trainer writes this; newest on top)

Notes, questions and plans for the server. Model details go in `handoff/models/<name>.md`.

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
