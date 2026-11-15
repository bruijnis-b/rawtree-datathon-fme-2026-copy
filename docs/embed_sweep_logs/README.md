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
| Phase L1 | 22:30 | 22:30 | `embed-l1` (40, v0); `embed-l1b` failed (bug); `embed-l1c` 23:27 (b_a2_43); `embed-l1d` 23:30 (grid) |
| Phase B | 00:00 | 22:53 | `embed-b` (48), `embed-lt` live transfer (16) |
| v1 to Bas (added) | ~01:00 | 23:31 | `embed-l1c/4` → `models/v1`; see `v1_handoff.md` |
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

### Live A/B hand-off with Bas's server (Sun 01:58 CET = 00:58 UTC onwards; times below UTC)

Bas set up an overnight loop on branch `run/live-ab` (`handoff/README.md`): the trainer delivers models as flat zips
plus a card in `handoff/models/`, writes notes in `handoff/TRAINER.md`; the server puts each model live as an A/B
arm and reports in `handoff/LIVE.md` / `FINDINGS.md`. Deadlines: last live-tested model 04:30 UTC, final 05:30 UTC.
Work on that branch happens in a separate worktree (`../rawtree-liveab`), so this checkout stays on `embed-sweeps`
for the phase C runs.

- **00:58 v2 delivered** (`077ac9a`): zip sha256 `30b8661b…`, card, and the scorer update (min-history rule, cart
  support). Backward compatibility checked: v0 and v1 score exactly as with the old scorer; v2 differs only for
  histories of fewer than 5 events (intended).
- **v1 on the carousel hold-out** (`embed-v1-eval`): 0.59 vs v2 0.54 (±0.12 each). v2 leads on organic (2.43 vs
  2.32) and history (4.23 vs 3.68); v1 leads on the carousel measure and on new users with 5 events (2.39 vs 2.29).
  Reported to the server; the live A/B decides.
- **01:00 live snapshot 2 published early** (up to 00:59 UTC: 3.83 M events, 172.6 k requests, 142.9 k carousels), so
  a model on fresher data gets a live test. `phase_c.sh` started on it: v3 = the final recipe on all history + live
  up to 00:59, delivery ≈ 02:00. `phase_c_live.sh` (LIVE=3, TAG=v4) waits for the 03:30 UTC snapshot: v4 ≈ 04:15.
- Live conversion 00:20–01:02 (our feedback): v1 default 2.02 % ± 0.50 (3,074 answers), v1 refit 1.84 % ± 0.49,
  `combined` 1.51 % ± 0.60.

### Phase C preparation (Sun 01:28–01:40)

- `embed-c-hist` (c_a4_25 + history 100, all history, seeds 0/1/2): succeeded in 5–6 min each. In-sample objective
  4.88–4.95 and calibration 0.84–0.97 are not informative (the validation week is in training); the recalibration is
  the out-of-sample value from phase B2.
- **Rehearsal of the final step** on snapshot 1 (`embed-c-rehearsal`): the export succeeded but the run failed in
  `description.md` (NaN/None numbers without a live hold-out). Fixed (`describe._num`). `embed-c-rehearsal2`: passes;
  parity 9.5e-6, p99 0.24 ms, 79,338 known users, ID vectors for all 5,300 products, dry run 0 policy errors.
- `training/phase_c.sh` is running in the background: it waits for `rawtree_live` v2 (published by the 04:30 export
  job), runs `embed-c-check` (fold-0 base with the live hold-out on snapshot 2, untuned vs tuned; gives the
  recalibration), then `embed-c-final` (the 3 all-history seeds on all of snapshot 2), and copies the exports to
  `models/final-1..3`.

### Cart decision, final recipe, v2 (Sun 01:25–01:30)

`embed-cart2` + control `embed-cart2c` (phase C base, 2 seeds each; carousel hold-out = our logged carousels):

| Variant | Carousel all | New | Known | In-cart | Organic live | Calibration |
|---|---|---|---|---|---|---|
| **no cart, no feedback task** | **0.524** | **0.477** | **0.572** | **1.32** | 2.44 | **0.18** |
| cart 50 events, no feedback | 0.446 | 0.440 | 0.452 | 1.26 | **2.72** | 0.20 |
| cart 10 events, no feedback | 0.472 | 0.459 | 0.485 | 0.74 | 2.55 | 0.19 |
| cart 50 + feedback task | 0.340 | 0.346 | 0.334 | 1.14 | 2.63 | 0.30 |
| no cart + feedback task | 0.409 | 0.366 | 0.454 | 1.02 | 2.39 | 0.30 |

- The **carousel-feedback task hurts** in every arm (carousel −0.11, calibration fails): off.
- The **cart in the embedding** raises the organic proxy (+0.1 to +0.3) but **lowers our real carousels in every
  variant** (−0.05 to −0.08). The carousel hold-out is the faithful measure, so the cart stays **out** of the model.
  The signal itself is real (cold analysis: odds ratio 5–6): it belongs in Bas's layer as one weight on "candidate is
  in the open cart", fitted on live feedback with our score as offset, next to his already-bought filter.
- **Final recipe:** base `c_a4_25` + history 100 (compact contexts); fine-tune 2 epochs, 50 % history, lr 0.3×,
  new-product ID dropout 0.5, all weights, `new_user_trunc`, no feedback, no cart; serving rule min 5 history events.
- **v2** = `embed-cart2c/1` (that recipe on snapshot 1): live 2.43 (v1 2.32), cold 2.31, carousel hold-out 0.54,
  new users 2.09 (none) / 2.29 (5 events) / 2.86 (50), calibration 0.18, history 4.23, parity 1.1e-5, p99 0.28 ms,
  dry run 0 policy errors. `models/v2/`, `models/v2_for_bas.zip` (20 MB, with `description.md`).
- **Phase C history runs started early** (`embed-c-hist`, 01:27): c_a4_25 + history 100 on all history, 3 seeds,
  recalibration fixed at [1.0185, 0.2188] (mean of the 8 phase B2 runs of this configuration). After snapshot 2
  (04:30) only the fine-tuning remains.

### Open cart in the embedding, short histories (Sun 01:00–01:30)

**Short-history training (`embed-cold`, phase C base, 2 seeds):**

| New users, history at scoring | none | 1 | 3 | 5 | 10 | 50 |
|---|---|---|---|---|---|---|
| recipe | 2.09 | **1.50** | 1.92 | 2.16 | 2.46 | 2.83 |
| + `ft.new_user_trunc` | 2.10 | 1.68 | 2.06 | 2.29 | 2.53 | 2.85 |

A very short history scores *worse* than none. Truncation training helps exactly there (+0.13 to +0.18 at 1–5
events), costs nothing at full length, calibration 0.17. **Adopted.** Even so, < 5 events loses to none, so the
export now carries a serving rule: a history shorter than `ft.min_history_events` (5) is ignored by the scorer
(both `events=` and the snapshot; `counts` stored in `user_vectors.npz`). `is_new` gain on the bias: learned −0.02,
no gain: dropped.

**Open cart** (`ft.cart`): products carted and not bought since within the user's last 50 events, pooled into the
user vector through a zero-start adapter, plus a learned in-cart term on the score, learned from our carousel
feedback (organic labels would teach it the opposite: there the purchased product is removed from the context). The
scorer takes the cart from `events=` or from the cart saved at export (`cart_ids` in `user_vectors.npz`). Parity
first failed (0.27): `scatter_` let a closed duplicate entry overwrite an open one in the in-cart indicator (affected
training and evaluation too). Fixed (additive scatter, capped): 2.5e-5.

New metric, **carousel hold-out** (`evaluate_feedback`): our own logged carousels of held-out users / last 2 h with a
click; does our full-catalogue top 10 contain the clicked product (purchase 3×), vs live best sellers. The only
offline measure that sees the cart effect. 1,199 clicks, 12 % of them on an open-cart product.

`embed-cart` (phase C base, feedback task on in both arms, 2 seeds):

| | no cart | cart |
|---|---|---|
| carousel hold-out, all (lift) | 0.435 / 0.383 | 0.321 / 0.354 |
| carousel, clicks on in-cart products | 1.05 / 1.00 | **1.21 / 1.18** |
| carousel, known users | 0.50 / 0.41 | 0.31 / 0.34 |
| organic live objective | 2.42 / 2.36 | **2.64 / 2.62** |
| calibration | 0.28 / 0.31 | 0.34 / 0.28 |

The cart does what it should on in-cart products and on the organic proxy, but loses on known users' carousels
(their open carts are mostly old history carts), so it does not win on the carousel hold-out overall (difference
within noise, wrong direction). The feedback task also costs calibration (0.17 → ~0.3). Follow-up `embed-cart2`:
window 10 vs 50 × in-cart term from feedback vs adapter only, with a no-cart / no-feedback control.

### Cold-request analysis (side session, Sun 00:40–01:30) and what we do with it

Full report: `docs/cold_analysis/README.md` on branch `claude/cold-analysis-50bdea` (not merged). Key points:
- Organically, new users buy exactly like known users (18.6 % vs 18.4 % of sessions end in a purchase; same
  categories, prices, top products). **In our carousels they buy 2.87× [2.38, 3.51] as often** (click 1.64×), on every
  page and device, also on the fixed fallback list. The effect grows with their own live purchases so far.
- A user-level "buys more" does not change the ranking within a request. What does: the user's **open cart**
  (odds ratio for a purchase 5–6, both splits), the user's own categories, popularity (more for new users), and an
  **already-bought product** (odds ratio 0.06). Our policy spends 0.76 of 10 slots per known-user carousel on
  already-bought products, and 0.06 slots per new-user carousel on open-cart products although half of them have one.
- Early in a stream new users have almost no history (70 % none in the first hour, median 4 events in the second),
  while our live hold-out's new users have a median of 20+.

Decisions:
1. **Split history into views / open cart / purchases (proposal 1): not tonight.** It needs a retrain of the user
   tower, and our organic-purchase proxy cannot measure it fairly (it removes the purchased product's own events from
   the history, which is exactly the open cart). **Serving rule for Bas instead** (the report's cheap fallback, in his
   layer): drop products the user already bought, and put the user's open-cart products (carted, not bought since)
   first. The bought filter alone frees 7.6 % of known-user impressions.
2. **Short-history training for new users (proposal 2)** and **`is_new` gain on the product bias (proposal 3)**:
   implemented as fine-tuning options (`ft.new_user_trunc`, `ft.new_gain`, default off); being tested on the phase C
   base (`embed-cold`, 2 × 2 × 2 seeds), judged on new users with 0/1/3/5/10 live events (new evaluation lengths).
3. Proposals 4 (purchase-head offset) and 5 (activity scalars): skipped (calibration is already within target;
   expected effect within noise).
4. The 2.87× purchase propensity of new users is a level effect: relevant for Bas's calibration of corrections per
   user type, not for our ranking.

**Compaction check** (`embed-cmp` + `embed-cmpf`, c_a4_25 + history 100, fold 0, 2 seeds): compacted contexts
history 4.18 / live 2.444 vs gaps 4.15 / 2.433; parity 7.6e-6. Kept.

### Phase B2 and the phase C configuration (Sun 00:30–01:05)

`embed-b2` / `embed-b2h`: the 4 best A4 configurations by live score, at their own history length and at 100,
3 folds × 2 seeds; `embed-b2f`: each run fine-tuned with the phase C recipe and scored on the live hold-out.
Tables: `phase_b2_history.md` (history side).

| Config | Live (mean ± SE, 6 runs) | New users: no history / last 50 live events | Calibration | History | Checks passed |
|---|---|---|---|---|---|
| c_a4_39 + history 100 | **2.440 ± 0.004** | 2.11 / 2.85 | 0.23 | 4.13 | 19/24 |
| **c_a4_25 + history 100** | 2.428 ± 0.006 | 2.07 / 2.83 | **0.13** | 4.16 | **23/24** |
| c_a4_36 + history 100 | 2.424 ± 0.005 | 2.10 / 2.81 | 0.23 | 4.30 | 20/24 |
| c_a4_100 + history 100 | 2.421 ± 0.010 | 2.09 / 2.83 | 0.21 | 4.12 | 20/24 |
| (own history length 35/50) | 2.37–2.41 | | | 3.85–3.98 | |
| b_a2_43 + history 150 / 200 | 2.41 / 2.40 | | | 4.10 / 4.12 | |

- History 100 helps every configuration on history (+0.15 to +0.25) and on live (+0.02 to +0.05); 150 and 200
  add nothing over 100.
- **Phase C configuration: `c_a4_25` + history 100** (dim 64, hidden 128, ID dropout 0.4, history dropout 0.3,
  recency pooling, slot learned, click weight 0.3, organic weight 1.0, batch 2048, 15 epochs, lr 1e-3, wd 0): within
  2 SE of the top live score, the only top configuration that passes calibration reliably, most checks passed, new
  products at their purchase share (1.20 % vs 1.15 %). Live +0.14 over v1's recipe, +0.38 over v0.

**Parity for fine-tuned models** (acceptance check 5): fine-tune exports now check numpy vs torch on product vectors
(from the raw catalogue, incl. new products) and 300 live requests, plus latency. On v1: 1.1e-5, p99 1.1 ms. The test
first showed 0.71: organic contexts had gaps where the purchased (or a held-out) product was removed, and recency
pooling counts positions; a real request never has gaps, so the scorer compacts. **Fix:** contexts are compacted in
training and evaluation too (`features.compact`, `RAWTREE_COMPACT=1` default). Being checked on the phase C
configuration (`embed-cmp`, fold 0, 2 seeds) against the B2 runs before phase C uses it.

**Incident:** commit `ca7f915` included `docs/NIGHT_LOOP.md`, a file written by someone else in the shared
checkout (a plan for live A/B arms overnight on a `night` branch). Removed from `embed-sweeps` in the next commit;
the file is left on disk, untouched. Commits now stage files by path.

### History length at training time, base screen, recipe grid (Sun 00:07–00:25)

**Recipe grid `embed-l1d`** (48 runs, b_a2_43): every recipe scores 2.27–2.30 live; the recipe has plateaued (seed
SE 0.001–0.018). v1's 2.32 was the lucky end of its recipe (mean 2.29). **Phase C recipe:** 2 epochs, 50 % history
batches, lr 0.3×, new-product ID dropout 0.5, all weights, no feedback (2.295, both seeds pass all checks,
calibration 0.16, history 3.72).

**History length at training time `embed-hl` + `embed-hlf`** (b_a2_43, 2 seeds, each fine-tuned with that recipe):

| N | 0 | 10 | 20 (v1) | 35 | 50 | 100 |
|---|---|---|---|---|---|---|
| Live objective (held-out users without history) | 2.02 | 2.25 | 2.31 | 2.36 | 2.36 | **2.41** |
| Live, snapshot history 100 events at serving | 2.04 | 2.70 | 2.80 | 2.86 | 2.88 | **2.91** |
| Live, new users with their last 50 live events | 2.12 | 2.75 | 2.81 | 2.81 | 2.82 | 2.83 |
| History objective | 2.87 | 3.54 | 3.70 | 3.85 | 3.92 | **4.11** |
| Calibration max error | 0.31 | 0.30 | 0.20 | 0.12 | 0.17 | **0.12** |

Longer is better on history *and* live, up to 100 so far; N = 100 passes calibration and ranks new products at their
purchase share (1.20 % vs 1.15 %). `embed-hl2` tests 150 and 200.

**Base screen `embed-s4`**: the 102 A4 configurations in the new-product band, each fine-tuned with the phase C
recipe. Live 2.16–2.40 (v1's base: 2.29). Within this refined space history and live agree (rank correlation +0.52).
What drives live: recency pooling 2.35 vs mean 2.24; history 35/50 2.32 vs 20 2.25; dim 32/48 ≥ 64; ID dropout
0.25–0.75 barely matters. Best passing all checks: `a4/39` 2.41, `a4/100` 2.40, `a4/36` 2.39, `a4/25` 2.38.

**Phase B2 (00:30)**: those 4 configurations × {own history length, 100} × 3 folds × 2 seeds (`embed-b2`,
`embed-b2h`, 96 runs), then each fine-tuned and scored live. (A first launch with an invalid override was cancelled
and deleted within a minute.)

### Long-term history at serving time (Sat 23:53, v1, live hold-out) (IMPORTANT for Bas)

New evaluation in every fine-tune run (`history_modes` records): held-out live purchases scored with no long-term
history, a snapshot (history + live events up to the start of the 2-hour hold-out window, like a `user_vectors.npz`
exported then), or dynamic (every event of the user before the purchase, like Bas passing `events=`), at 10/20/50/100
events. Events on the purchased product itself are left out (same rule as the recent context).

| History at scoring time | All | New users | Cold |
|---|---|---|---|
| none (brand-new user) | 2.05 | 2.13 | 1.97 |
| snapshot 10 | 2.53 | 2.60 | 2.38 |
| snapshot 20 (v1 export today) | 2.69 | 2.73 | 2.50 |
| snapshot 50 | 2.79 | 2.78 | 2.54 |
| snapshot 100 | 2.82 | 2.79 | 2.54 |
| dynamic 50 (`events=`) | 2.81 | 2.81 | 2.57 |
| dynamic 100 | 2.83 | 2.81 | 2.56 |

- Long-term history is worth **+0.6 to +0.8** on live data.
- Serving with 50 events instead of the trained 20 adds ≈ +0.1 without retraining; little gain beyond 50.
- Snapshot ≈ dynamic here only because this snapshot is at most 2 h old. In the final round, new shoppers have no
  snapshot, so for them the choice is **none (2.13) vs dynamic (2.81)**: Bas passing each user's live events is worth
  ≈ +0.7 lift for new users.
- Note: the standard `live_objective` (2.32 for v1) scores the 20 % held-out users without any history, the
  pessimistic case.
- Follow-up running: `embed-hl` (training history length 0/10/20/35/50/100 × 2 seeds on b_a2_43, then fine-tuned).
  `embed-a4` cancelled at 91/150 runs at 23:55: history-only scores do not predict live, so the remaining runs had
  less value than the live experiments queued behind them.

### L1c and v1 (Sat 23:27–23:31)

`embed-l1c`: recipes on base `b_a2_43` (live objective before tuning 2.16). IVAN stopped the sweep after 17 of 80
runs (runs 5–9 are missing from its list; not investigated, the 17 were enough). Best:

| Recipe | Live | New user | New product | New products top-10 / purchases | History | Calibration |
|---|---|---|---|---|---|---|
| `l1c/4`: 2 ep, history 50 %, lr 1×, new-ID dropout 0.5, all, no feedback | **2.32** | 2.44 | 1.86 | 1.11 % / 1.15 % | 3.68 | 0.17 |
| `l1c/3`: 2 ep, history 80 %, lr 0.3×, half-life 6 h, new-ID dropout 0.5 | 2.31 | 2.44 | 1.83 | 1.07 % | 3.76 | 0.16 |
| `l1c/15`: 2 ep, no history, lr 0.1×, feedback, new-ID dropout 0.25 | 2.30 | 2.41 | 1.81 | 1.15 % | 3.69 | 0.20 |
| new-ID dropout 1.0 (4 runs) | 2.17–2.19 | 2.33–2.36 | 1.45–1.49 | | | |

- Fine-tuning adds +0.16 live on this base, mostly for new products (1.45 → 1.86) and new users (2.32 → 2.44), with
  no forgetting (history 3.66 → 3.68). New-ID dropout 0.5 is best; 1.0 (content only for practice products) is worst.
- The carousel-feedback task is not needed (best recipes have it off), so fine-tuning does not depend on what is
  deployed.
- **v1 = `l1c/4`, delivered to `models/v1` at 23:31** (see `v1_handoff.md`): passes every check.
- `embed-l1d` (23:30): 48-run grid around the best recipes (new-ID dropout 0.25/0.5/0.75 × epochs 2/3 × history
  50/80 % × lr 0.3/1 × 2 seeds) to pick the phase C recipe reliably.

### Live transfer check (Sat 23:15–23:21): history gains do not carry over to live (IMPORTANT)

`embed-lt`: the 16 fold-0 phase B models, no fine-tuning, scored on the live hold-out (snapshot 1).

| Config | History objective | Live objective | Live new user | Live new product | New products: top-10 share / purchase share |
|---|---|---|---|---|---|
| b_desc | 3.35 | **2.18** | 2.33 | 1.35 | 0.96 % / 1.15 % |
| b_a2_43 | 3.66 | **2.17** | 2.32 | **1.45** | 1.14 % / 1.15 % |
| b_hist50 | 3.25 | 2.17 | 2.33 | 1.04 | 0.53 % / 1.15 % |
| b_lr07 | 3.27 | 2.10 | 2.25 | 0.99 | 0.46 % / 1.15 % |
| b_a2_8 | 3.49 | 2.09 | 2.22 | 1.29 | 1.03 % / 1.15 % |
| b_a2_10 | 3.36 | 2.08 | 2.26 | 1.30 | 0.92 % / 1.15 % |
| b_a2_45 | 3.86 | 2.07 | 2.26 | 0.86 | 0.15 % / 1.15 % |
| b_a2_25 | 3.66 | 2.00 | 2.16 | 1.13 | 1.03 % / 1.15 % |
| v0 (default) | 2.79 | 2.05 | | | 0.4 % / 1.15 % |

- Rank correlation between history and live over the 8 configurations: **−0.45** (history ips objective), −0.19
  (history organic recall, the *same* metric as live), −0.57 (slate_auc). So it is a **data shift** (the live
  simulator differs from the history), not a metric problem.
- The +0.8 history gain over v0 becomes at most +0.13 live. The live spread between configurations (2.00–2.18) is
  small, about 2–3 × the noise (≈ 0.05 for 2 runs).
- New products are the weak spot live: lift 0.9–1.45 against ~4 on held-out history products.
- **Decision:** select the final model on the **live hold-out (after fine-tuning)**, with the history metrics as a
  guard (forgetting, calibration, new-product band). Base for v1 and the recipe search: **b_a2_43** (2nd on history,
  2nd on live, best live new-product lift, new products at exactly their purchase share, best calibration).
- `embed-l1b` (80 recipes on v0) failed on every run: a variable shadowing bug in the new-product ID dropout, and the
  fine-tune sweep inherited the A4 parameters (Hydra merged the two `sweep` sections). Both fixed (`conf/sweep/`);
  relaunched as `embed-l1c` on base `embed-b/13` (b_a2_43, fold 0, seed 0) at 23:27.

### Phase B (Sat 22:53–23:12): 8 configurations × 3 folds × 2 seeds, all 48 succeeded

Table: `phase_b.md` (`python -m training.embed.aggregate embed-b`). Fold/seed noise is small (SE ≈ 0.03 over 6
runs), much smaller than the bootstrap SE of one run (≈ 0.14), so differences of 0.1 between configurations are real.

| Config | Objective (mean ± SE) | New user | New product | slate_auc | Calibration (mean/max) | Held-out ÷ clicks | Pass all |
|---|---|---|---|---|---|---|---|
| b_a2_45 | 3.79 ± 0.04 | 2.79 | 4.18 | 0.766 | 0.24 / 0.29 | **0.12** | 0/6 |
| b_a2_25 | 3.64 ± 0.03 | 2.86 | 4.00 | 0.758 | 0.21 / 0.35 | 0.97 | 4/6 |
| b_a2_43 | 3.58 ± 0.03 | **2.98** | 3.85 | 0.749 | **0.13** / 0.21 | 0.97 | 4/6 |
| b_a2_8 | 3.48 ± 0.01 | 2.47 | 4.00 | 0.765 | 0.30 / 0.45 | 0.99 | 0/6 |
| default (v0, phase A) | 2.81 | 2.0 | 3.36 | 0.751 | 0.61 (raw) | 2.6 | – |

- **The phase A leader is out**: ID dropout 0 makes new products 8× under-ranked (0.06–0.29 of their click share).
- `b_a2_25` (dim 64, ID dropout 0.5, history dropout 0.5, mean pooling, lr 7e-4) and `b_a2_43` (dim 32, ID dropout
  0.5, history dropout 0.5, recency pooling, click weight 0.3, batch 4096, lr 7e-4) both rank held-out products at
  their click share, gain about +0.8 over v0, and gain most on new users (+0.9). Their failing runs miss calibration
  narrowly (0.21–0.35) or the held-out band once (0.48×).
- Recalibration roughly halves the calibration error (0.61 → 0.13–0.33) but does not always reach 0.2.
- The common factors of the good configurations: description on, ID dropout 0.5, history dropout 0.5, lr 7e-4.

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
