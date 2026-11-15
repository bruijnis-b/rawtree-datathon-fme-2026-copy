# Live arms (server writes this)

Updated: 2026-11-15 06:03 UTC. Code: branch `run/live-ab`, restarted 02:13 UTC.

## Live now: round 3, four arms, a quarter each

| Share | Public ID | Arm | Question | Live since |
|---|---|---|---|---|
| 25% | mab651f | `embed_score` on v4, default settings | One model, v4's recipe | 01:33 |
| 25% | m09c26e | `embed_blend`: average of v2 and v3 | Average within one recipe | 02:13 |
| 25% | m9f6fa4 | `embed_blend`: average of v3 and v4 | Average across the two recipes | 05:31 |
| 25% | m8277ec | v3+v4 average **with every tuned factor**: `cart=2.5`, `max_lift=1.3`, `w_cat=1`, `w_sub=1`, `new=1.5`, `alpha=0.3` | Best on paper (Bas, 06:00): does the tuned layer beat the defaults on the same models? Read against m9f6fa4 | 06:02 |

`arms.txt` is the file the process reads. Read with `handoff/tools/board.py` from 05:31 UTC (m8277ec from 06:02).
A fresh model from the trainer (v10/v11) replaces the weakest arm when it has passed its checks.

Round 3 at 05:59 UTC (28 minutes, about 1,450 requests per arm): v3+v4 65.7, v2+v3 60.1, v4 60.0. Too early.

Pruned at 05:31: `med6134` (v2 alone, weakest in every reading since 02:30) and `mac2638` (recent views x2 for
new shoppers: no cold gain, −0.21 ± 0.22 against v2).

## Official scores since 02:30 UTC (`board.py`; four frozen arms)

| Read at (UTC) | v2 (med6134) | v2+v3 average (m09c26e) | v4 (mab651f) | v2, recent views x2 (mac2638) | Requests per arm | Leader |
|---|---|---|---|---|---|---|
| 03:07 | 57.2 (cold 2.80%) | 53.4 (cold 2.46%) | 58.7 (cold 2.53%) | 51.4 (cold 2.07%) | 1,530–1,620 | team_06 60.9; us 55.1, 4th |
| 03:37 | 58.9 (cold 2.72%) | 51.5 (cold 2.39%) | 61.5 (cold 2.41%) | 55.9 (cold 2.35%) | 2,870–2,990 | team_06 62.8; us 57.0, 5th |
| 04:07 | 59.5 (cold 2.78%) | 53.8 (cold 2.42%) | 62.8 (cold 2.46%) | 56.4 (cold 2.33%) | 4,240–4,320 | team_06 64.6; us 58.1, 5th |
| 04:37 | 56.1 | 56.5 | **61.2** | 57.5 | 5,550–5,700 | team_06 64.3; us 57.8, 5th |
| 05:07 | 55.4 (cold 2.56%) | 59.9 (cold 2.59%) | 61.1 (cold 2.41%) | 58.0 (cold 2.38%) | 6,880–7,030 | team_06 65.3; us 58.6, 5th |

05:07: v4 and the v2+v3 average are level (+0.8 ± 5.9); both are above v2 alone (v4 +5.1 ± 2.8, average
+4.3 ± 6.2 per quarter hour). Recent views x2 shows no cold gain. Nothing is separated by two standard errors.

## Official scores, 01:11 – 02:31 UTC (`board.py`; score out of 100, expected conversion)

| Arm | Score | Conversion | Cold conversion | Requests |
|---|---|---|---|---|
| v2 (med6134) | 59.4 | 2.15% | 2.51% | 3,383 |
| v3 (m0cba68) | 62.1 | 2.22% | 2.83% | 2,921 |
| v4 (mab651f) | 57.7 | 2.09% | 2.76% | 2,284 |
| v1 (m2b37f8) | 50.2 | 1.91% | 2.13% | 2,609 |
| v2+v3 average (m09c26e), 02:13 on | 69.6 | 2.41% | 3.25% | 558 |

The average looks strong but has 558 requests; one arm swings 10 points over 15 minutes. Leader (team_06) over
the same period: 64.1.

## Conversion, 01:33 – 02:13 UTC (last period before the cut to three arms)

| Arm | Answers | Purchases | Conversion (± 1 s.e.) | New shoppers |
|---|---|---|---|---|
| v2 (med6134) | 1,717 | 34 | 1.98% ± 0.34 | 2.53% |
| v3 (m0cba68) | 2,004 | 38 | 1.90% ± 0.30 | 3.52% |
| v4 (mab651f) | 1,768 | 41 | 2.32% ± 0.36 | 4.00% |
| v1 (m2b37f8), to 01:58 | 959 | 22 | 2.29% ± 0.48 | 4.10% |

Nothing separates here. Over this period v2's early lead over v1 is gone: the first 22 minutes flattered it.

## Conversion, 01:10:40 – 01:53 UTC

| Arm | Answers | Purchases | Conversion (± 1 s.e.) | New shoppers |
|---|---|---|---|---|
| v1 (m2b37f8) | 2,428 | 49 | 2.02% ± 0.29 | 2.82% |
| v2 (med6134) | 1,879 | 50 | 2.66% ± 0.37 | 4.16% |
| v3 (m0cba68), from 01:20 | 1,845 | 43 | 2.33% ± 0.35 | 3.05% |
| v4 (mab651f), from 01:33 | 954 | 24 | 2.52% ± 0.51 | 4.78% |

## Conversion, 00:18 – 01:08 UTC (all three ran side by side)

| Public ID | Answers | Purchases | Conversion (± 1 s.e.) | New shoppers: answers, purchases, conversion |
|---|---|---|---|---|
| m2b37f8 (v1 default) | 3,674 | 76 | 2.07% ± 0.23 | 1,120, 36, 3.21% |
| m649454 (v1 refit) | 3,594 | 65 | 1.81% ± 0.22 | 1,106, 19, 1.72% |
| mdfdc72 (`combined`) | 1,894 | 25 | 1.32% ± 0.26 | 597, 14, 2.35% |

## Pruned

| Public ID | Arm | Live (UTC) | Why pruned |
|---|---|---|---|
| m0cba68 | `embed_score` on v3, default settings | 01:20 – 02:18 | Not worse than v2 (offline equal, live equal). It runs on inside the v2+v3 average; a third of the traffic is worth more there |
| mff9f12 | v2, `cart=2.5` | 02:03 – 02:18 | Stopped to concentrate traffic; 6 purchases, no reading. Decided offline: fitted x2.0–2.5 on v2–v4 |
| m3cb3ff | v2, `trend=3` | 01:58 – 02:18 | Stopped to concentrate traffic; 15 trend minutes, 7 purchases, no reading. x8 stays (whole-day review) |
| m76d67a | v2, `alpha=0.3` | 02:13 – 02:18 | Stopped to concentrate traffic after 5 minutes; no reading |
| m2b37f8 | `embed_score` on v1, default settings | 23:37 – 01:58 | Offline 4–6 standard errors below v2, v3 and v4 on the same answers; live below all three (2.02% against 2.33–2.66%). Its share went to the trend test while a trend was running |
| m649454 | `embed_score` on v1, refit weights | 23:37 – 01:20 | Its weights were fitted for v1, and v2 and v3 are about to replace v1. Overall within noise of v1 default (1.81% against 2.07%), but clearly worse for new shoppers (1.72% against 3.21%) |
| mdfdc72 | `combined` (no model) | 23:12 – 01:10 | 1.32% against 2.07% for v1 over the same 50 minutes: 2.1 standard errors lower, and lower in every earlier comparison |
| m679016 | `cold_combined` | 23:51 – 00:18 | Conversion 1.25% against 1.73% for `combined` over the same period; cold conversion lower too. Far too strong a push for new products (x7.5) |
| m11bb0e | `embed_score` on v0, refit weights | 23:22 – 00:18 | No gain over v0 default in the one period both ran; v0 is behind v1 anyway |
| mf4c79f | `embed_score` on v0, default settings | 23:12 – 23:37 | 1.04% against 1.73% for `combined`; replaced by v1 |
| m4e07bd | `shopper_score` (no model, no discount or trend factor) | 23:12 – 23:37 | 1.21%; `combined` beat it in every period |
