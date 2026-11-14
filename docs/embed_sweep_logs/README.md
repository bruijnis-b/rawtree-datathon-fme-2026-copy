# Embedding sweeps: log and findings

Running log of the sweeps in `docs/EMBED_SWEEPS_FINAL.md` (Sat 14 → Sun 15 Nov 2026, times CET). Newest
findings at the top of each section. Raw results: IVAN (project `rawtree`), backups in `ivan_backup/`.

## Status

| Milestone | Planned | Actual | Notes |
|---|---|---|---|
| Pipeline end to end on IVAN | Sat 21:00 | Sat 20:39 | `embed-smoke` (1 epoch), `embed-smoke2` (20 epochs, 4.5 min) |
| Phase A launch | 21:15 | 21:15 | `embed-a1` (33 one-axis presets), `embed-a2` (45 random), all done by 21:45; `embed-a3` (5 reruns with calibration fixes) |
| v0 to Bas | 22:00 | 21:39 | `embed-v0` → `models/v0`; see `v0_handoff.md` |
| Live snapshot 1 | 22:00 | 22:00:38 | `rawtree_live` v1 (up to 21:00 UTC; 2.88 M events, 99.9 k carousels) |
| Phase L1 | 22:30 | | |
| Phase B | 00:00 | | |
| Live snapshot 2 | 03:00 | | |
| Phase C | 03:00 | | |
| Final model to Bas | 06:30 | | |

## Pipeline (what was built)

- `python -m training.train` (Hydra config `conf/train.yaml`): history training. Data prep from the Parquet
  history (DuckDB → numpy, cached per fold in `~/.cache/rawtree_embed`, 34 s on epochserver), then two towers trained
  jointly on the carousel (click head with slot term s[slot, device], purchase-given-click head) and the organic
  next-event task (in-batch sampled softmax with logQ). ~10 s per epoch on one GPU; 20 epochs + eval + export ≈ 4.5 min.
- `python -m training.finetune base=<experiment>` (`conf/finetune.yaml`): live fine-tuning on `rawtree_live`, live
  hold-out (20 % users, last 2 h, 60 practice products), forgetting check on the history validation week.
- `training/export/scorer.py`: numpy-only scorer (`load(folder)`, `embed_products`, `score`, `user_vector`).
- `recsys/policies/embed.py`: policy `embed` (plain model scores), `EMBED_MODEL=<export folder>`.
- `training/data/export_live.py`: live snapshot export (laptop), resumable per hour, checked against RawTree counts.
- `training/embed/metric_check.py`: baseline / category_pop / coview scored with the same `ips_hit@10` code.
- Phase A one-axis variants are named presets (`training/embed/presets.py`, `preset=<name>`).

### Deviations from the plan, and why

- **Runs take ~5 min, not 10–20.** One epoch over 1.6 M carousels + 1.6 M organic samples takes 10 s; validation
  objective plateaus after ~6–10 epochs (smoke2). Default 20 epochs. Shorter runs = more of the sweep finishes.
- **Organic context excludes the target product.** In the history, 99.98 % of organic purchases have the same product
  among the user's previous 6 events (view → cart → purchase). With it in the context, the organic task is trivial
  copying (organic recall@10 = 0.94 in the first smoke run). A carousel click is in `recent_views` only 9 % of the time.
- **Calibration error** is computed only over deciles with ≥ 30 observed purchases (low deciles have 0 purchases, so a
  relative error is undefined).
- **Live carousel task has no discount input** (the price at the time a carousel was shown is not joined); the
  discount weight is learned on the organic task only.
- `recsys/policies/__init__.py` registers the new `embed` policy (Bas's area: one line).

## Findings

### Revised plan (Sat 22:50, agreed with Jules): more volume, three issues addressed

Runs take 5–7 min (history) and 1–2 min (fine-tune), so the overnight budget is ~10× the plan. Deadlines unchanged.
Launched 22:53: `embed-b` (8 configs × 3 folds × 2 seeds = 48), `embed-a4` (150 random runs in a refined space:
description on, ID dropout ≥ 0.25, lr 5e-4…1.5e-3, 15–40 epochs, …), `embed-l1b` (80 live recipes on v0, with the
new-product ID dropout axis).

How each issue is handled:
1. **Calibration.** History runs: the score is recalibrated (`a · score + c`) on half the validation week and
   checked on the other half. Fine-tuned runs: refit after tuning on the history validation week (local test:
   0.86 → 0.11). Calibration ≤ 0.2 is a selection requirement.
2. **New products.** Check 3 is two-sided (0.5×–2× of the click share) on the history, and fine-tuning adds a live
   check: the 60 held-out practice products' share of top-10 slots against their share of held-out purchases.
   **Finding:** v0-based fine-tuning gives them 0.38 % of top-10 slots against 1.15 % of purchases: 3× under-ranked
   on live data. Fix under test in `embed-l1b`: `ft.new_id_dropout` (0.25–1.0) drops the practice products' ID
   vectors more often, so the content path and the no-ID bias learn the live level of products without history.
3. **Offline metric vs live.** The model-ID mapping is in `recsys/model_versions.json` on `origin/main`. Live
   arms ran one after another, not side by side:

   | Live (UTC) | Requests | Purchases / 100 |
   |---|---|---|
   | Organisers' fallback = best sellers, 11:45–14:45 | ~32 k | 0.76 |
   | category_pop v1, 15:30–15:45 and 17:15–17:45 | 1,933 | 0.98 ± 0.44 |
   | coview v1, 15:45–17:15 | 13,097 | 0.56 ± 0.13 |

   Offline order: category_pop > coview > baseline. Live: category_pop ≥ baseline > coview, but sequential windows
   (the fallback's own rate varies 2× between quarter-hours), so this does not establish a mismatch. Instead of
   switching metrics: (a) a config must be strong on both `ips_hit@10` and `slate_auc`; (b) **live transfer check**:
   every phase B fold-0 model is scored without fine-tuning on the live hold-out (real simulator purchases, no
   deployment needed). If the history ranking of configs predicts their live ranking, the offline metric is validated.

### Phase L1 (Sat 22:30–22:40): 40 recipes on v0, live snapshot 1

Reference (v0, no tuning): live objective 2.05 ± 0.07 (all +2.09, cold +1.85). Best recipes 2.23–2.29 (+0.2,
≈ 3 SE); cold gains most (→ 2.15–2.18). Trade-off with forgetting: live only, 1 epoch, lr 0.3×: 2.29 live but history
2.79 → 2.59; 80 % history batches: 2.22–2.23 live, history 2.61–2.67; live only at lr 1× for 2–4 epochs wipes out the
history (0.3–1.3). Feedback task and recency weighting: no clear effect. Freezing history ID vectors ≈ training all.
Learned discount weight −0.02…−0.1 (Bas measured −2.3): the discount effect stays in Bas's layer.

### Phase A (Sat 21:15–21:45): 78 runs, fold 0, 1 seed

Full tables: `phase_a.md` (A1 + A2), `phase_a1.md`, `phase_a3_calibration.md`. Default: objective 2.81 ± 0.12.

What matters (one-axis, `embed-a1`; differences of ~0.3 are about 2 standard errors):
- **The organic task is essential.** Off: 0.37 (organic recall 0.03). Staged (pre-train, then carousel only): 2.02.
  Weight 0.3: 1.99. Without logQ: 2.42 (organic recall halves, 0.10). Purchases upweighted in the organic targets
  (1/3/6) beats uniform (2.53).
- **Description bag-of-words helps most:** 3.22 (+0.41), and it is in all of the top 6 random combinations.
- History length 50: 3.16; no long-term history: 2.21 (organic recall 0.18 vs 0.24). History dropout 0: 2.57.
- Lower learning rate (7e-4): 3.15; higher (5e-3): 2.36. dim 32: 3.03; dim 128: 2.27; hidden 256: 2.41.
- Content only (ID dropout 1.0): 2.04. ID dropout 0.5: 3.00; 0: 2.83 but see below.
- Propensity weighting does not help (clip 0.05: 2.67; 0.01: 2.27). Click weight 3: 2.10; 0.3: 2.86.
- Slot term learned / fixed / off: 2.81 / 2.72 / 2.72: small effect on the ranking (the slot is dropped at
  inference), but "off" leaves the slot gap at 1.51.
- Reference price adds a little: without price 2.64.
- Pooling: recency-weighted mean (default) ≥ plain mean (2.73) ≥ attention (2.69).
- dim128 failed the p99 < 20 ms check once: CPU noise on a shared worker (its p50 is normal); recheck in B.

Random combinations (`embed-a2`): best `a2/45` 3.89 ± 0.16 (description, dim 32, history 50, ID dropout 0,
mean pooling, slot fixed, wd 1e-4), then `a2/25` 3.71, `a2/43` 3.69, `a2/8` 3.49, `a2/10` 3.19.

**New-product ranking (added check).** `a2/45` (ID dropout 0) gives held-out products 0.6 % of top-10 slots against
2.6 % of clicks: 4× under-ranked. Its content-only path is never trained alone, so new products would hardly be
shown in the final round. The plan's check 3 only bounds over-ranking (≤ 2×); it is now two-sided (0.5×–2×).
Shares for the B candidates: a2/25 5.4 %, a2/43 3.0 %, a2/8 3.4 %, a2/10 3.7 %, desc 2.5 %, hist50 6.4 %,
lr07 8.7 % (default 6.7 %).

**Calibration fails in every phase A run** (max decile error 0.36–0.98). Per-slot click rates are calibrated almost
exactly (e.g. iOS slot 1 predicted 0.0096 vs observed 0.0097); the purchase score is too spread out on held-out data:
deciles 5–9 are predicted at 0.1–0.45 × the observed rate, the top decile at 1.11 ×. Tried (`embed-a3`):
1. a learned bias offset for products without an ID vector: learned +0.12…+0.24, no effect on the share of new
   products in the top 10 (kept, harmless);
2. a refit of the heads with frozen towers on training carousels: x_scale 1.07, calibration *worse* (0.81),
   because on training data the towers are sharp. Switched off (`train.calibrate_epochs=0`).
3. **Adopted for phase B:** an affine map of the delivered score, `a · score + c`, fitted by logistic regression on
   half of the validation requests and checked on the other half (local test: 0.72 → 0.23). Exported as two scalars
   (`score_a`, `score_c`) that the scorer applies; it does not change the ranking. For the all-data runs of phase C
   the values come from the phase B runs of the same configuration (`train.score_affine=[a,c]`).

### Smoke runs (Sat 20:20–20:40)

`embed-smoke2`, default config, fold 0, 20 epochs:

| | all | cold | new_user | new_product |
|---|---|---|---|---|
| ips_hit@10 lift over best sellers | +2.83 [2.60, 3.05] | +2.82 [2.36, 3.40] | +2.02 | +3.43 |
| organic_recall@10 (best sellers) | 0.240 (0.074) | 0.181 (0.054) | 0.182 | 0.178 |

slate_auc 0.748 (+9 % over popularity). Parity numpy vs torch 7.6e-6; p99 latency 0.22 ms at batch 1.

Failing acceptance checks on the default: held-out products take 6.7 % of top-10 slots vs 2.6 % of clicks (> 2×);
calibration max error 0.66; learned slot term up to 0.21 from log θ (check wants 0.1).

### Metric check (once, with v0)

Offline `ips_hit@10` lift over best sellers, fold 0 validation week, same code:

| Policy | all | cold |
|---|---|---|
| category_pop | +2.98 [2.83, 3.13] | +3.21 |
| coview | +0.72 [0.60, 0.87] | +0.90 |
| baseline | 0 | 0 |
| smoke2 model | +2.83 | +2.82 |

Live order: our `recsys/model_versions.json` only knows `m1e06ef` = category_pop (0.98 purchases / 100 requests,
1,933 requests). The other live model_version IDs in `team_33.feedback` are registered on Bas's machine, so the
live order could not be checked here: **Bas, please compare with your dashboard.** If coview beats category_pop live,
the offline metric is wrong and selection should move to `slate_auc`.
