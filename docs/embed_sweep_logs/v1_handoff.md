# v1 for Bas (Sat 23:31 CET)

**Where:** `models/v1/` on Jules's laptop (IVAN `embed-l1c/4`, share path
`/mnt/epoch/projects/rawtree/experiments/names/embed-l1c/4/export`), ≈ 15 MB. Same interface and policy as v0:
`EMBED_MODEL=models/v1 python -m recsys.main --policy embed --dry-run` (dry run 23:31: 0 policy errors).

**What:** history config `b_a2_43` (description bag-of-words, dim 32, ID dropout 0.5, history dropout 0.5, recency
pooling, click weight 0.3, batch 4096, lr 7e-4; IVAN `embed-b/13`, fold 0), fine-tuned on live snapshot 1 (up to
Sat 21:00 UTC): 2 epochs, all weights, 50 % history batches, lr 1×, practice-round products drop their ID vector half
the time, no carousel-feedback task. Then the score is recalibrated on the history validation week.

**Compared with v0** (live hold-out: 20 % of live users, the last 2 h of the snapshot, 60 held-out practice products):

| | v0 | v1 |
|---|---|---|
| Live objective (lift over live best sellers, organic recall@10) | 2.05 | **2.32** |
| Live new users | | 2.44 |
| Live new products | | 1.86 |
| Held-out practice products: share of top-10 vs share of purchases | 0.4 % vs 1.15 % | **1.11 % vs 1.15 %** |
| History objective (ips_hit@10) | 2.79 | 3.68 |
| Calibration, max decile error (history) | 0.64 | **0.17** |
| `is_new_user` | ignored | learned |
| Users known (`user_vectors.npz`) | 59,841 | 74,174 (history + live) |

**Score scale:** v1 is recalibrated (`score_a` 0.985, `score_c` −0.246, applied inside the scorer), so its scores
are closer to true purchase log-odds than v0's. Refit your β on v1 scores, not v0's.

**Discount:** the live fine-tuning learned a discount weight of −0.06 (your measurement: −2.3). The discount effect is
not in the model; it stays in your layer, as agreed.

The final model (06:30) will have the same interface; it is fine-tuned on snapshot 2 (later live data) without a
hold-out, after a check run with the hold-out.
