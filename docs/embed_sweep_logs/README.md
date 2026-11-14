# Embedding sweeps: log and findings

Running log of the sweeps in `docs/EMBED_SWEEPS_FINAL.md` (Sat 14 → Sun 15 Nov 2026, times CET). Newest
findings at the top of each section. Raw results: IVAN (project `rawtree`), backups in `ivan_backup/`.

## Status

| Milestone | Planned | Actual | Notes |
|---|---|---|---|
| Pipeline end to end on IVAN | Sat 21:00 | Sat 20:39 | `embed-smoke` (1 epoch), `embed-smoke2` (20 epochs, 4.5 min) |
| Phase A launch | 21:15 | | |
| v0 to Bas | 22:00 | | |
| Live snapshot 1 | 22:00 | | |
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
