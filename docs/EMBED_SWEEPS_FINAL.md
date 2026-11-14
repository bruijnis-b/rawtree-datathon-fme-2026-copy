# Embedding sweeps: final plan

Brief for the session that builds the training pipeline and manages the IVAN sweeps (Jules's part of the RawTree
challenge). Written Sat 14 Nov 2026, 19:30 CET. The final round is Sun 15 Nov 10:00–12:00 CET.

Read first: `CLAUDE.md`, `docs/POA.md` (do not edit it), `recsys/README.md`. Branch: `embed-sweeps`.
This file replaces the older handoff `EMBED_SWEEP.md` where the two differ; the differences are listed in
[Changes from the earlier handoff](#changes-from-the-earlier-handoff).

## Deadlines (hard)

| When (CET) | What |
|---|---|
| Sat 21:00 | Pipeline works end to end: one default-config run on IVAN, with metrics, export and numpy scorer |
| **Sat 22:00** | **v0 to Bas**: the default model (history only) behind the final interface. He runs it as an A/B arm overnight and builds his correction layer against it |
| Sat 21:30 – Sun 00:00 | Phase A (broad sweep, history) |
| Sat 22:00 | Live snapshot 1 exported to IVAN (`rawtree_live` v1) |
| Sat 22:30 – Sun 02:30 | Phase L1 (live fine-tuning recipe, on v0, in parallel with A and B) |
| Sun 00:00 – 02:30 | Phase B (top configs, 3 folds × 2 seeds, history) |
| Sun 03:00 | Live snapshot 2 exported (`rawtree_live` v2), as late as the schedule allows |
| Sun 03:00 – 05:45 | Phase C (final: winner of B on all history, then the L1 recipe on all live data, 3 seeds) |
| **Sun 06:30** | **Final model to Bas.** After this, no model changes |
| Sun 06:30 – 09:30 | Bas fits his correction layer on the final scores |
| Sun 09:30 | Everything frozen |

Rules:
- If a phase is late, cut its size, not the deadline.
- The final model replaces v0 only if it passes every [acceptance check](#acceptance-checks). Otherwise v0 is final.
- v0 and the final model have the same interface and the same score scale, so Bas's layer needs no rework.

## What the model is

Two towers; the score is a dot product. **The score is the calibrated log-odds that the shopper buys the product
when it is shown in slot 1.** Bas adds his terms to it:

```
final = score + β_discount · log(price / reference_price) + β_trend · trend + …
```

Trained in two stages: the towers learn on the **history** (IVAN dataset `rawtree_history` v1), and are then
**fine-tuned on the live practice stream** (`rawtree_live`), the only data with real new users and new products.
See [Live fine-tuning](#live-fine-tuning).

**Product tower** (no request-dependent input, so vectors are cached):
- category, subcategory, brand: learned vectors;
- **reference price** (the product's first catalogue price), as log price and as log price relative to its
  subcategory mean. Never the current price: see [Price](#price);
- product-ID vector, added to the content vector, with ID dropout (default 0.25). A new product has no ID vector;
- a bias term predicted from the content features (its "expected popularity");
- description: off by default; one sweep axis (hashed bag-of-words learned in the tower). No sentence-transformer:
  serving must not need one at 10:00.

**User tower:**
- device, region, page, hour of day;
- `recent_views`: product-tower vectors, pooled (default: recency-weighted mean; sweep: attention). No GRU;
- long-term history: pooled product vectors of the user's last N events (default 20, weighted by type), with
  **history dropout** (default 0.3: the whole history is removed);
- `is_new_user`: an input whose weights start at zero. The history does not have the flag, so it has no effect
  after history training; the live fine-tuning learns it;
- no user-ID vector.

**Serving package** (in `training/export/`, consumed by a `recsys` policy):
- `model.npz` with the weights, and a **numpy-only** scorer: `embed_products(rows) → matrix`,
  `score(request, user_history, product_matrix) → score per product`;
- `user_vectors.npz`: the precomputed history vector for each of the 59,698 known users, so serving needs no live
  event feed. Unknown users get the "no history" vector;
- a parity test (numpy vs. PyTorch, max abs difference < 1e-4) and a latency report.

## Removing the bias of the historical carousels

The old carousel showed best sellers far more often than shoppers buy them (top 50: 33 % of slots, 20 % of organic
purchases), and attention falls steeply with the slot (click rate 4.4 % in slot 1, 1.2 % in slot 10). Two separate
biases follow:

1. **Position bias:** the label depends on the slot, not only on the product.
2. **Selection bias:** we only see outcomes for the products the old policy chose to show.

Options considered:

| Option | Fixes | Problem |
|---|---|---|
| A. Softmax over the whole catalogue with sampled negatives, on carousel clicks | – | Treats "not shown" as "not wanted": the model learns the old policy. Rejected |
| B. Pointwise loss on the 10 shown products, with a slot term | position | Selection: no labels where the old policy never looked. The model must extrapolate |
| C. B, weighted by 1/propensity | position, selection (in expectation) | High variance: a few rarely shown products dominate. Needs clipping |
| D. Train on organic `events` only | both (no carousel involved) | Organic browsing is not the carousel: different purchase rates and no slot |
| E. Remove popularity from the model (popularity-corrected negatives everywhere) | exposure | Popularity is real demand; the baseline we must beat is best sellers |

**Pick: B and D trained jointly, with C as a sweep axis.**

- The outcome of a shown product, given the user, the product and the slot, is an honest sample of the simulator
  whichever policy chose it. The old policy decides *where* we have labels, not *what* they are. So a pointwise
  model with a slot term (B) is unbiased wherever it has data; the slot term is set to slot 1 at inference.
- Where the carousel has no data, the organic task (D) covers the whole catalogue: next viewed/carted/purchased
  product, sampled softmax with in-batch negatives and a popularity (logQ) correction. Both tasks share the towers.
- Propensity weighting (C) only helps if the model is too simple to fit both the head and the tail. It is cheap to
  test: weights `1 / max(propensity, clip)`, self-normalised per batch, clip ∈ {0.01, 0.05}.
- The carousel loss has two heads on the same dot product: click, and purchase given click. The delivered score is
  the purchase log-odds in slot 1.

### Slot bias

Measured on all 2,000,000 historical carousels (20 M impressions, 74,915 clicks, 28,053 purchases):

| Slot | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Click rate, % | 1.07 | 0.60 | 0.44 | 0.34 | 0.28 | 0.25 | 0.22 | 0.20 | 0.17 | 0.16 |
| Raw, relative to slot 1 | 1 | 0.56 | 0.41 | 0.32 | 0.26 | 0.23 | 0.21 | 0.18 | 0.16 | 0.15 |
| **Attention `θ_k`** (product-adjusted) | 1 | 0.62 | 0.50 | 0.42 | 0.37 | 0.36 | 0.33 | 0.31 | 0.29 | 0.28 |

- **The raw curve overstates the slot effect.** The old policy put stronger products higher (the mean product
  click strength falls by 46 % from slot 1 to 10). After adjusting for the product (`click rate = θ_slot × r_product`,
  fitted by alternating updates), slot 10 gets 0.28 of slot 1's attention, not 0.15.
- **The slot effect is a pure multiplier.** `θ_k` is the same for the 18 strongest products (a third of all
  clicks), the next 91 and the remaining 4,582: within ±0.02 at every slot.
- **It differs by device:** slot 10 is 0.22 on Android, 0.32 on iOS and web. It does not differ by page.
- **Products do not compete.** The click rate of the slot-1 product does not depend on how attractive the other
  nine are (index 0.997–1.007 across quintiles), and a slot-5 product barely depends on what is above it
  (0.97–1.07). So this is a position-based model, not a choice among the ten and not a cascade.
- **The slot acts on the click only.** Purchase after a click falls from 42 % in slot 1 to 30 % in slot 10, but
  that is all product mix: product-adjusted it is flat (0.97–1.03).
- **The slot effect is identifiable** because the old policy was random (`propensity`): the same product appears
  in different slots.

Options considered:

| Option | Problem |
|---|---|
| Ignore the slot | The model learns "products the old policy ranked high are good": the old ordering leaks into the scores |
| Train on slot-1 impressions only | Throws away 71 % of the clicks |
| Weight each click by `1/θ_k` | Unbiased, but slot-10 clicks get 3.5× the weight: more variance for the same result |
| Slot term in the click head, removed at inference | Needs the multiplier assumption, which the data supports |

**Pick: a slot term in the click head.** `logit(click) = u·v + b + s[slot, device]`. At click rates around 1 %
an additive term on the logit is the multiplier `θ`. Details:

- `s` is initialised at `log θ_k` from the table (per device) and then learned; `s[1, ·]` is fixed at 0. At
  inference `s` is dropped, so the score is the slot-1 log-odds.
- The purchase-given-click head gets **no** slot term.
- Sweep axis: `s` learned (default), `s` fixed at `log θ_k`, no slot term (expected to be worse).
- The metric weights (`θ_k` in `ips_hit@10`, `1/θ_slot` in `slate_auc`) use the product-adjusted, per-device curve.
- Checks after every run: the learned `s` stays within 0.1 of `log θ_k`; predicted and observed click rates
  agree per slot on the validation week; `slate_auc` computed per logged slot is similar across slots.

Consequences for serving (Bas): with no competition between products, expected purchases are
`Σ_k θ_k · p_k`, so the best carousel is simply the ten highest scores in descending order. The history gives no
reason to diversify the list.

Other facts from the same analysis:
- 309 of the 5,000 products were never shown in a historical carousel. For those, the carousel task has no
  labels at all; they depend on the organic task and on content, like new products.
- Clicks are very concentrated: 18 products take a third of them. Best sellers is a strong baseline.
- Never 2 clicks in one carousel, where independent clicks would give about 1,400 such carousels. Too rare to
  model.

`propensity` is documented as the probability of showing that product *in that slot, given the slots above*.
Check this once before using it as a weight: the propensities of one slot should sum to about 1 over the
candidate products.

## Validation

Goal: the model must stay good on what the final round adds (new users, 300 new products), and the number we
select on must not reward copying the old carousel.

**Split** (deterministic from hashes, no split file needed; fold `f` ∈ {0, 1, 2}):
- **Time:** train on days 0–52, validate on days 53–59.
- **Held-out users:** 10 % (`hash(user_id, f)`). All their carousels and events leave training.
- **Held-out products:** 300, stratified on subcategory and price tercile, seeded by `f`. Removed from
  everything in training: carousels (the impression is dropped), events, `recent_views`, user histories.

**Slices** of the validation week:
- `warm`: known user, known products in `recent_views`;
- `new_user`: held-out users with their history removed;
- `new_product`: `recent_views` contain a held-out product;
- `cold` = `new_user` ∪ `new_product` (the challenge's definition); `all` = everything, with held-out users
  evaluated without history.

**Metrics**, each as lift over in-stock best sellers on the same slice, `(model − baseline) / baseline`, with a
bootstrap interval over requests (1,000 resamples):

| Metric | What | Why |
|---|---|---|
| `ips_hit@10` (primary) | Rank the whole catalogue. A click or purchase counts if the product is in our top 10, weighted by our slot's `θ_k` and by `1 / max(propensity, 0.01)` of the logged impression; self-normalised. A purchase counts 3× a click | Closest to the challenge metric; the propensity weight removes the reward for copying the old policy |
| `slate_auc` | Within the 10 shown products, does the score rank the clicked one first? Clicks weighted by `1/θ_slot` | Low variance (every click counts); checks the purchase model itself |
| `organic_recall@10` | Next organic purchase in the validation week, ranked against the whole catalogue | No carousel bias at all |
| `calibration` | Predicted vs. observed purchase rate per score decile and per slice | Bas adds his terms on the log-odds scale |

**Sweep objective:** `(50 · lift_all + 10 · lift_cold) / 60` on `ips_hit@10`. A config is only eligible if
`slate_auc` and `organic_recall@10` are not below the default config's interval.

**Metric check (once, with v0):** score `baseline`, `category_pop` and `coview` with the same code. Their offline
order must match their live order on Bas's dashboard. If it does not, select on `slate_auc` instead and say so in
the report.

**Live check:** v0, and later the final model, run as an A/B arm on the practice stream. Realised purchases per
100 requests against `coview` is the only measurement of the real scoring; it overrules the offline numbers.

## Sweep phases

Compute: IVAN showed nothing running or queued at 19:17 and `rawtree` shares the free GPUs (`LightMyCells` is at
ratio 0). Jules counts about 20 idle GPUs; `runs_per_gpu` is 2. A run should take 10–20 minutes: fix epochs so it does.

| Phase | Runs | Design | Selects on |
|---|---|---|---|
| 0 · smoke | 1 | Default config, `train.epochs=1`, `--force` | It finishes; metrics, export and parity exist |
| A · broad | ~80 | Fold 0, 1 seed. About 35 one-axis changes from the default, then ~45 random combinations | Objective, with the eligibility rule |
| B · deep | ~48 | Top 8 of A (at least 2 that differ in more than one axis), 3 folds × 2 seeds | Mean objective minus one standard error; p99 latency < 20 ms |
| L1 · live recipe | ~40 | Fine-tune v0 on live snapshot 1, with the live hold-out. See [Live fine-tuning](#live-fine-tuning) | Live objective; no forgetting on the history |
| C · final | 4 | One check run of the B winner + L1 recipe with the live hold-out on snapshot 2; then the same on **all** history and all live data, 3 seeds | Acceptance checks; of the 3 seeds, the one with the median score in the check metrics |

Axes for phase A (default first):
- embedding dimension: 64, 32, 128;
- ID dropout: 0.25, 0, 0.5, 1.0 (content only);
- history dropout: 0.3, 0, 0.5; history length: 20, 0 (off), 50;
- `recent_views` pooling: recency-weighted mean, plain mean, attention;
- organic task: joint (weight 1.0), off, weight 0.3, staged (pre-train, then carousel only);
- organic negatives: in-batch with logQ, without logQ;
- propensity weighting: off, clip 0.05, clip 0.01;
- click-head weight relative to purchase: 1.0, 0.3, 3.0;
- slot term (see [Slot bias](#slot-bias)): learned per slot × device, fixed at `log θ_k`, off;
- description: off, hashed bag-of-words;
- price input: reference price (default), none (to measure what price adds);
- learning rate, weight decay, batch size: 3 values each.

IVAN mechanics:
- From the laptop: `IVAN_URL=http://localhost:8000` through the SSH tunnel (`ssh epoch`). The branch must be
  pushed; runs use HEAD.
- `ivan run training.train train.epochs=1 --force --name smoke --hypothesis "…"`, then
  `ivan sweep training.train --name embed-a --hypothesis "…"`; follow with `ivan status`,
  `ivan experiment show embed-a`, `ivan logs embed-a/3`. Group the phases with `ivan group`.
- A run that itself writes a dataset (`ivan.data.output`) uses `--machine epochserver`. The live snapshots are
  not such runs: they are exported on the laptop and published with `ivan data add`.
- **Use all machines: no `--machine epochserver` for embedding runs.** The first run on a PC copies the dataset
  to that worker, which is near-instant. (`--machine epochserver` in `CLAUDE.md` is only for runs that *install*
  data on the share.)
- PC2 and PC8 GPU 1 have only 11 GB. Keep a run under that (it should be, with `runs_per_gpu` 2 in mind), and
  check the memory of the smoke run.
- Preprocess inside the run (DuckDB → tensors, cached on local disk, keyed by fold). This avoids a new
  `ivan data add`, which needs epochviipc5 and the `rsync` workaround (TeamEpochGithub/ivan#127).
- **IVAN is where results live.** `ivan.log_step` per epoch (losses, validation metrics) and `ivan.log_summary`
  at the end: the objective, every metric per slice with its interval, calibration, the learned slot term,
  p50/p99 CPU latency at batch size 1 (numpy scorer), and the config. The sweep's `metric` is read from this
  summary. The run also writes the same numbers to `export/metrics.json`.
- **Backup on the laptop: `ivan_backup/`** in the repo root (gitignored). After every phase, and before any
  experiment is deleted, copy each experiment's results there, without the PyTorch checkpoints:

  ```bash
  ssh epoch "tar -C /mnt/epoch/projects/rawtree/experiments/names -czh --exclude='*.pt' embed-a" | tar -xz -C ivan_backup
  ```

  (`-h` follows the name links.) Also save the text of `ivan experiment show <name>` as
  `ivan_backup/<name>/show.txt`. The exports of v0 and of the phase C runs are copied in full to `models/`.
- **No W&B.** It is not known whether the workers hold a W&B key for `rawtree`, so the pipeline does not call
  `wandb` at all.
- Local DuckDB has no `Relation.fetchone()`: use `con.execute(sql).fetchall()`; cast booleans to INT before
  averaging.

## Views and the logging contract

Four views exist in `training/views/` and are registered in `ivan.yaml`; run and sweep pages open on `overview`.
They are also meant for the final presentation. They read only what a run logs, so **the pipeline must log
exactly these names**. A view shows a calm note, not an error, when its data is missing.

| Page | View | Shows |
|---|---|---|
| Run | `overview` | Headline numbers; lift over best sellers per slice with intervals (history and live); acceptance checks; training and validation curves |
| Run | `diagnostics` | Slot term learned vs. measured, click rate per slot; calibration; ranking of new products; serving checks; settings |
| Sweep | `overview` | Leaderboard; all vs. cold requests per run; objective with standard errors; configurations averaged over folds and seeds |
| Sweep | `axes` | Objective per value of every setting that varies; effect table; which choices matter most |

IVAN's own sweep view `default` (parallel coordinates, parameter importance) cannot be removed, but it is not
included in ours (`default_graphs=False`) and pages do not open on it.

**`ivan.log_summary`** (one call at the end; all lifts as fractions, 0.25 = +25 %):
`objective`, `objective_se`, `lift_all`, `lift_cold`, `slate_auc`, `organic_recall`, `latency_p50_ms`,
`latency_p99_ms`, `parity_max_abs`, `calibration_max_err`, `slot_max_gap`; after live fine-tuning also
`live_objective`, `live_lift_cold`. The sweep config sets `metric: {name: objective, goal: maximize}`.

**`ivan.log_step`** (once per epoch): `epoch`, `loss`, `loss_click`, `loss_purchase`, `loss_organic`,
`val_objective`, `val_lift_all`, `val_lift_cold`.

**`ivan.log_records`:**

| Name | One row per | Columns |
|---|---|---|
| `metrics` | dataset × slice × metric | `dataset` (`history`, `live`), `slice` (`all`, `cold`, `warm`, `new_user`, `new_product`), `metric` (`ips_hit@10`, `slate_auc`, `organic_recall@10`), `value`, `baseline`, `lift`, `lift_lo`, `lift_hi`, `n` |
| `checks` | acceptance check | `check`, `value` (text), `needed` (text), `passed` (bool) |
| `slot` | device × slot | `device`, `slot` (1–10), `theta_learned`, `theta_measured`, `ctr_pred`, `ctr_obs` |
| `calibration` | dataset × slice × score decile | `dataset`, `slice`, `decile`, `predicted`, `observed`, `n` |
| `products` | product group | `group` (`known`, `held-out`), `share_top10`, `share_clicks` |

Settings the sweep views treat as repeats, not as design choices: `fold`, `seed`, `data.fold`, `train.seed`.
Name the fold and seed settings one of these.

Status: all four views render without error on synthetic data with these names (17 figures and tables). They
have **not** been seen in the dashboard yet. After the smoke run, open its page, check both run views, and fix
what looks wrong; `ivan results <name>` re-renders old runs after a view changes (it runs on an office PC).

## Getting a model from IVAN to Bas

Runs execute on office PCs, so the model never lands on the laptop by itself. Every run writes its serving package
to its run folder, which IVAN keeps on the share of epochserver:

- In the code: `ivan.runs.dir() / "export"` holds `model.npz`, `user_vectors.npz`, `config.yaml`, `metrics.json`
  and the PyTorch checkpoint. Phase A may skip `user_vectors.npz` to save space; v0, phase B and phase C write it.
- On the share: `projects/rawtree/experiments/names/<experiment>/<k>/export/` (a single run has no `<k>`). The
  share is mounted at `/mnt/epoch` on epochviipc5 (checked: `/mnt/epoch/projects/rawtree/experiments` exists).
- To the laptop, through the existing `ssh epoch` access:

  ```bash
  scp -r epoch:/mnt/epoch/projects/rawtree/experiments/names/embed-c/1/export models/embed-c-1
  ```

  `models/` is gitignored. The package is a few MB (59,698 users × 64 floats is about 15 MB uncompressed).
- **Prove the route with the smoke run**, before v0: copy its export to the laptop, load it with the numpy scorer
  and score one request. Do not discover a broken route at 06:00.
- To Bas: the `export/` folder plus the scorer module in the repo. The weights are not committed; send the folder
  directly. A file `export/README.txt` states the experiment, run, git commit
  and metrics, so he can tell v0 from the final model.

## Acceptance checks

The final model goes to Bas at 06:30 only if all hold; otherwise v0 stays.

1. Objective in phase B above v0's, by more than one standard error.
2. `lift_cold > 0` on every history fold **and** on the live hold-out: better than best sellers for new users
   and new products. On the live hold-out the fine-tuned model also beats the history-only model.
3. Held-out products are not over-ranked: their share of top-10 slots is at most 2× their share of clicks.
4. Calibration: predicted and observed purchase rates within 20 % in every score decile, on `all` and on `cold`.
5. Numpy scorer equals PyTorch (< 1e-4); p99 < 20 ms at batch size 1; no torch import in the serving package.
6. A dry run in `recsys` (`--dry-run`) answers 1,000 live requests without a policy error, including requests
   with the practice round's new products in `recent_views`.

## Price

**Decision: the tower uses the reference price only. The whole effect of a price change is a term in Bas's
layer, on `log(price / reference_price)`.**

Analysis of the live practice stream (Sat 09:00–18:15 UTC, 2.2 M organic events):

- **Every price change is a temporary discount.** 3,061 changes on 1,787 products: a drop of 16–20 %, and exactly
  120 minutes later the price returns to the catalogue price. No price ever rises above its reference.
- **A discount raises purchases by about 60 %.** For 643 discounts with a full 2 h before and after, without a
  stock-out, organic purchases during the discount are 1.60× those in the surrounding 4 h (95 % interval
  1.47–1.73, corrected for site traffic). Views rise 1.22×, add-to-carts 1.54×. That is an elasticity of about
  **−2.3**.
- **By price** (reference price quartiles):

  | Reference price | Views | Purchases | Purchases, n (before+after / during) |
  |---|---|---|---|
  | < €24 | 1.23× | 1.65× | 558 / 457 |
  | €24–36 | 1.23× | 1.88× | 228 / 213 |
  | €36–53 | 1.22× | 1.50× | 255 / 189 |
  | ≥ €54 | 1.21× | 1.02× | 126 / 64 |

  Views rise equally everywhere; purchases do not rise for the most expensive quarter (few purchases there, so
  this is uncertain).
- **The history gives the right sign but a much weaker effect.** Across products in the history, within a
  subcategory, 1 % higher price goes with 0.9 % fewer purchases (−0.3 % views); across the whole catalogue only
  0.26 %. The weaker effect for expensive products is there too (−1.3 below €24, −0.4 above €54).
- **Our own carousel feedback points the same way** but is too thin to measure it: for products that had a
  discount, the slot-adjusted click rate is 1.6× higher during the discount (60 vs. 90 clicks).

Conclusions:
- An earlier concern, that a history-trained price effect could have the wrong sign, is **not** supported: the
  sign is right. The problem is size. A model fed the current price would predict a 20 % discount to add about
  +22 % purchases (from −0.9), against +60 % measured; with ID vectors it would predict even less, because the ID
  absorbs a product's price level.
- A discount in the simulator is more than a lower price: views rise by the same 22 % in every price band. That
  is an effect of *being discounted*, which the history cannot contain.
- The model still needs a price input. Price level is a real property of a product (the −0.9), and for a new
  product it is one of the few signals. The reference price gives exactly that, and it never changes, so product
  vectors are only recomputed for new products.
- So Bas does not replace the model's price input; he adds the discount term. His `LiveCatalog` must keep each
  product's reference price: the `shop.catalog` price, or the price in its `new_product` row.
- Bas's weight scales with the log of the original price: `β(p₀) = β₀ + β₁ · log(p₀ / 30)`, capped at 0.
  Fitted on the 643 discounts (binomial likelihood, purchases during vs. around the discount):
  `β₀ = −2.2` (95 % range −2.6 to −1.75), `β₁ = +1.2` (0.5 to 1.9); better than a constant weight
  (likelihood-ratio statistic 10.3). A 20 % discount then multiplies purchases by 2.2 at €10, 1.6 at €30, 1.2 at
  €100 and 1.0 at €200. Bas refits both on live feedback with the model score as a fixed offset.
- "Reference price" in this file always means the product's own original, undiscounted price. The tower gets it
  as two features: its log, and its log minus the subcategory's mean log price (so the tower can tell a cheap
  laptop from an expensive phone case). No category price replaces the product's own price anywhere.

Limits of this analysis: it uses organic events, not carousel outcomes; the final round may use other discount
sizes or durations; the scripts were one-off and are not in the repo.

## What describes a user, and who supplies it

A request and the event log are two different things:

| Source | What it holds | Size | Who has it at serving time |
|---|---|---|---|
| The request (`shop.requests`; in the history: `history_sessions`) | `device`, `region`, `page`, `is_new_user`, and `recent_views`: at most 6 products the shopper just looked at (mean 2.0; empty in 20 % of requests; the last one a median 31 s before the request) | One row per request | In the request itself |
| The event log (`history_events`; live: `shop.events`) | Every organic view, add-to-cart and purchase of the user, outside the carousel | Median 122 events per history user (10 %: 30, 90 %: 441) | Nobody, unless it is looked up by `user_id` |

So the request is the shopper's context of the last minute, not their shopping behaviour so far. It has no
purchases, no add-to-carts and nothing older than the last few views. `recent_views` are also not a copy of the
event log: in the history, none of them match a logged view event.

What the model embeds:
- **Everything in the request**, on every request, with nothing needed from Bas beyond the request.
- **The user's long-term behaviour** from `history_events`, precomputed per user into `user_vectors.npz` and
  looked up by `user_id`. This covers the 59,698 history users.
- Whether the long-term history adds anything on top of `recent_views` is a sweep axis (history length 0 vs.
  20 vs. 50). If it adds little, drop it and the model needs the request only.

What is left to Bas:
- **Live events of a user** (`shop.events`). A user who is new today has no row in `user_vectors.npz`, but new
  users are very active: the 15,786 live users flagged `is_new_user` already have 555 k events (25 k purchases).
  If Bas keeps each user's last 20 live events, the scorer turns them into the same vector
  (`user_vector(events)`, one pooling step). Optional: without it a new user is embedded from the request alone.
- **Everything that changes during the round:** trends, live popularity, discounts, stock, already bought.

## Live fine-tuning

The history has no new users and no new products, so it cannot show how the simulator treats them. The practice
stream can. Measured Sat 18:45 UTC, after under 10 hours:

- 105 k requests from 48 k users; 30 % of requests are flagged `is_new_user` (the flag stays set on all of a
  user's requests). New users have `recent_views` as often as known users (mean 2.06).
- `shop.events`: 2.34 M events from 73 k users, 106 k purchases. Of those, 555 k events and 25 k purchases are
  from new users, and 74 k events and 3.8 k purchases are on the 300 practice-round new products.
- `team_NN.feedback`: 71 k carousels with 1,763 clicks and 524 purchases. Small, and 46 % were served by the
  fallback (best sellers).

**Dataset `rawtree_live`:** `shop.requests`, `shop.events`, `shop.catalog_updates`, `shop.catalog` and our
`feedback`, exported with the code of `training/data/export_history.py`. Snapshot 1 at Sat 22:00, snapshot 2 at
Sun 03:00. **The export runs on the laptop** (decided by Jules): the RawTree key is only in the laptop's `.env`
and does not go to epochserver.

1. Laptop: `uv run python -m training.data.export_live --out data/raw/rawtree_live` (new module, same structure
   and manifest check as `export_history.py`; Parquet).
2. Copy to the office PC: `scp -r data/raw/rawtree_live epoch:~/rawtree_live`.
3. Publish there, from an interactive shell because the IVAN token is in `.bashrc`:
   `ssh epoch 'bash -ic "ivan data --project rawtree add rawtree_live ~/rawtree_live -m \"live stream up to <time>\""'`,
   with the `rsync` wrapper early in `PATH` that appends `--no-group --no-owner` (TeamEpochGithub/ivan#127).
4. Training runs read it as `${ivan:rawtree_live,<version>}` in the Hydra config, on any machine. Pin the version
   per phase: v1 for L1, v2 for phase C.

The laptop must stay on and awake for snapshot 2 at Sun 03:00. Never pass the key as a run override or print
it: IVAN stores overrides and logs.

**Tasks on live data:**
- Organic next-event prediction on `shop.events`, the same task as on the history. This is the main signal.
- Carousel click/purchase on `feedback`, pointwise with the slot term. There is no propensity; none is needed
  for the pointwise loss.
- Both with `log(price / reference_price)` as an extra input with its own weight, because discounts change the
  live labels. The weight is reported to Bas and **not** exported: the delivered score stays discount-free.

**What it should learn:** the `is_new_user` weights; ID vectors for the practice-round products; a better content
path, now that 300 real new products have labels; any shift between the history and the live simulator.

**What it must not learn:** the practice round's trends (Bas's layer; the final round has other trends) or a
popularity ranking of today. Guards: a low learning rate, history batches mixed in, and the time hold-out below.

**Hold-out (no selecting on training data):**
- 20 % of live users (`hash(user_id)`), all their requests and events;
- the last 2 hours of the snapshot, for everyone;
- 60 of the 300 practice-round products, removed from live training like held-out products in the history.

Slices: `new_user` (flagged, or not in the history), `new_product` (a practice-round product in `recent_views`
or as the target), `cold` (their union), `all`. Metric: `organic_recall@10` and its lift over best sellers, with
the objective `(50 · lift_all + 10 · lift_cold) / 60`; plus `ips_hit@10` on the history validation week, which
must not drop by more than its interval (forgetting check).

**Phase L1: the recipe** (on v0, snapshot 1, ~40 runs). Axes:
- what is trained: everything; only the new parts (`is_new_user` weights, new ID vectors, content bias);
  everything with the ID vectors of history products frozen;
- learning rate: 0.1×, 0.3×, 1× the history rate; epochs over the live data: 1, 2, 4;
- share of history batches mixed in: 0, 50 %, 80 %;
- `feedback` task: on, off; live-event weight by recency: none, half-life 6 h.

The first run of L1 is the reference: v0 **without** fine-tuning on the live hold-out. That number is the honest
cold-start score of a history-only model, and the recipe must beat it.

**Phase C: the final model.** The winner of phase B, trained on all history, then the L1 recipe on all of
snapshot 2 (no hold-out), 3 seeds. Before that, one run of the same pipeline *with* the hold-out on snapshot 2
confirms the recipe still helps on the newer data; if it does not, the final model is the history-only one.

**Serving after fine-tuning:** `user_vectors.npz` also gets a row for every live user, built from their live
events up to the snapshot, so most "new" users of the final round who were active in the practice round are
known.

Limit: the final round's 300 products and its new users are again unseen. The live hold-out measures exactly
that case (held-out users and held-out practice products), which is the best estimate available.

## Contract with Bas (agree before 22:00)

Bas's own summary of this is `docs/EMBED_HANDOFF_BAS.md`. Build the scorer to match it: `embed_products(rows)`
and `score(request, product_matrix, events=None)`. If the interface must change, update that file too.

1. Scores are log-odds; his terms are additive; he fits them on `team_NN.feedback` with our score as offset.
2. He supplies per request: the `Request` fields and, per product, the catalogue fields plus the reference price.
3. He calls `embed_products` at startup and for each `new_product`; never on a price or stock change.
4. He needs no live event feed for the model: user history comes from `user_vectors.npz`. Optionally he passes a
   user's recent `shop.events` to `user_vector(events)` (see above).
5. Trends, discounts, stock and already-bought are his. The model takes `is_new_user` from the request.
6. Price deviates from `docs/POA.md` ("the model takes the current price"): he should confirm this.

## Changes from the earlier handoff

| Earlier | Now | Why |
|---|---|---|
| Current price as model input | Reference price; discount term at Bas | Live analysis above |
| Metric: hit on the purchased carousel item | Propensity-weighted, plus two guards | The plain hit rewards copying the old carousel |
| `is_new_user` as input | Input with zero start, learned in the live fine-tuning | Not in the history |
| Negatives: shown / random / popularity-sampled | Shown only for the carousel task | "Not shown" is not "not wanted" |
| Product ID optional | ID with dropout by default | 5,000 of 5,300 products are known |
| Frozen sentence embedding | Off; bag-of-words as one axis | No heavy dependency at 10:00 |
| Live check on top candidates | A fine-tuning recipe chosen on a live hold-out, applied to the winner | The only data with real new users and products |
| Stratified folds from a notebook | Hash-based folds in the pipeline | Time |
| Live event history in the user tower | Precomputed user vectors | `Request` carries no events |
