# Overnight model loop: how the two agents work together

Two agents iterate on the embedding models until **Sun 15 Nov 05:30 UTC (06:30 CET)**. They talk only through
this branch, `run/live-ab`. All times in this folder are **UTC**.

| Agent | Works for | Job |
|---|---|---|
| **Trainer** | Jules | Trains models on IVAN, delivers them here, watches the live results |
| **Server** | Bas | Puts each model live as an A/B arm, keeps the number of arms small, reports what it learns |

The live recommender runs from Bas's checkout of this branch. Only the server starts, stops or changes it.

## Who writes what

Each agent only changes its own files, so pushes never conflict.

| Path | Owner | Content |
|---|---|---|
| `handoff/models/<name>.zip` | Trainer | One model per file |
| `handoff/models/<name>.md` | Trainer | The model's card (template below) |
| `handoff/TRAINER.md` | Trainer | Notes, questions and plans for the server; newest on top |
| `training/` | Trainer | Only when a model needs a scorer change (say so in the card) |
| `handoff/LIVE.md` | Server | What is live right now, and what was pruned and why |
| `handoff/FINDINGS.md` | Server | Results per model and other findings; requests to the trainer |
| `arms.txt`, `recsys/` | Server | The live arms and the serving code |

Before every push: `git pull --rebase origin run/live-ab`. Never force-push. Commit messages start with
`trainer:` or `server:`.

## No waiting for the sake of waiting

From Bas and Jules, for both agents. The only thing worth waiting for is **live requests**: an arm needs traffic
before its conversion means anything. Nothing else is a reason to sit idle.

- Do not wait for the other agent. Deliver, decide and write down why; the other reads it when it gets there.
- Do not wait for a planned time ("v5 around 04:15", "review at 02:20") when the work can start now.
- While traffic builds up, do the work that needs no traffic. Trainer: score candidates on the carousels we
  already logged, train the next candidate, check the model on products and shoppers it has never seen (300 new
  products and at least one new trend arrive at 09:00 UTC). Server: compare models offline on the logged answers,
  refit the leading model, check the trend and discount factors on top of it, prepare the final round.
- If you are waiting, write in your file what for and until when.

## Trainer: delivering a model

1. Name it `v2`, `v3`, ... A name never changes content: a fixed model gets a new name.
2. Zip the model folder **flat** (files at the top level of the zip), as `handoff/models/<name>.zip`:
   `model.npz`, `user_vectors.npz`, and `README.txt`, `metrics.json`, `config.yaml` as before. Only `.npz`, `.txt`,
   `.json`, `.yaml` and `.md` files; nothing executable. Same interface and score scale as v0 and v1.
3. Write `handoff/models/<name>.md` from the template below.
4. Commit both in one commit (`trainer: deliver v2`) and push.

Deliver a model as soon as it is ready; do not hold it for a time slot or for the server's next review. The
last model that can still get a live test must be pushed by **04:30 UTC**. The final model is due at
**05:30 UTC**; no model changes after that.

### Model card template

```markdown
# <name>
- Delivered: <UTC time>
- Zip sha256: <sha256 of the zip>
- Based on: <parent model or config>, IVAN run <name>
- Training data ends: <UTC time>     <- the server only evaluates on answers after this
- What changed against the previous model, in one or two lines
- Offline scores: objective on the history hold-out and on the live hold-out, next to the previous model's
- New products: their share of top-10 slots against their share of purchases
- Scorer change: none | what changed in training/export/scorer.py
- Known weaknesses
- Suggested test: default settings, or the settings you want tried
```

## Server: what happens to a delivered model

The server checks this branch every 15 minutes. For a new model it:

1. Checks the zip (sha256, file names), unpacks it to `models/<name>/` and loads it.
2. Runs it for 100 seconds next to the live process without sending anything. It must answer every request
   with 0 policy errors and a p95 under 1.5 s.
3. Builds the refit dataset and reports the purchase AUC on our own answers after the model's training data
   ends, next to the current best model's (`python -m recsys.refit.build`, `.fit --after`).
4. Adds it to `arms.txt` as `embed_score:embed_model=models/<name>` (the model plus our discount, trend and cart
   factors, default settings). The running process picks the file up; no restart.
5. Writes the new arms and their public IDs to `handoff/LIVE.md`, and commits `recsys/model_versions.json`.

A model that fails step 1 or 2 does not go live; the reason goes to `handoff/FINDINGS.md`.

## Rules for the live arms

There is no fixed number of arms. Traffic follows what we know about each arm.

**From 02:18 UTC on 15 Nov: three arms, fixed until 05:30 UTC** (Bas: few promising arms that collect requests
tell more than many that never separate). See `LIVE.md`. A new model is checked and scored offline; it only takes
an arm if it is clearly ahead there. The rules below applied before that and apply again after.

- **Every arm answers a question**, written in `handoff/LIVE.md`. No question, no arm.
- **Share follows quality.** The best arm so far (champion) gets the largest share. An arm that looks as good as
  the champion gets the same share. A new or uncertain arm starts at 15–25%.
- **No arm below 15%.** Under that it collects fewer than 30 purchases per hour and answers nothing in time.
- **Pruned when clearly worse:** live conversion more than two standard errors below the champion over the
  period both ran, or lower on the offline AUC and not better live after an hour. Its share goes to the arms
  that are left.
- **Pruned when answered:** an arm that is within noise of another after two hours, with no offline difference,
  is the same thing twice. The simpler one stays.
- **Promoted when better:** a model becomes champion when its offline AUC on unseen answers is higher and its
  live conversion is not more than one standard error lower.
- Every answer goes through the guard, whatever the arm: 10 distinct, active products, none that the shopper
  already bought.

## What live traffic can tell

About 180 requests and 3.2 purchases per minute in total. An arm at 40% collects about 75 purchases per hour,
so two such arms differ by 16% (one standard error) from noise alone. One hour of live data only shows large
differences (30% or more). Smaller ones need the offline scores, or several hours.

## Trainer: watching the live results

You read the same tables with the same key. Nothing here needs a write.

- What each `model_version` means: `recsys/model_versions.json` on this branch (private; the IDs themselves say
  nothing). What is live now: `handoff/LIVE.md`.
- Our answers and their outcome: `team_NN.feedback` (`shown`, `clicked`, `purchased`, `served_by`,
  `model_version`). Leave out `request_id = '__init__'` and rows with `served_by != 'team'`.
- Conversion per arm since a given time:

```sql
SELECT model_version::String AS m, count() AS answers, countIf(purchased::String != '') AS purchases
FROM team_NN.feedback
WHERE request_id::String != '__init__' AND served_by::String = 'team'
  AND ts::DateTime64(3) >= '2026-11-15 00:20:00'
GROUP BY m ORDER BY answers DESC
```

- Compare arms only over a period in which both ran: conversion moves with the time of day and with trends.
- Cold requests (`is_new_user`, or a new product in `recent_views`): join `shop.requests` on `request_id`.

## Not leaking

`model_version` in `team_NN.submissions` stays an opaque ID from `recsys.model_registry`. Never write model
names, settings or findings to a RawTree table. This repository is private; these files are fine here.
