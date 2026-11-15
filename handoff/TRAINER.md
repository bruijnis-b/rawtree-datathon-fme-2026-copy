# Trainer notes (trainer writes this; newest on top)

Notes, questions and plans for the server. Model details go in `handoff/models/<name>.md`.

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
