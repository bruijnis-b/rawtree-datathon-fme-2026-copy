# Live arms (server writes this)

Updated: 2026-11-15 02:00 UTC. Code: branch `run/live-ab`, restarted 01:10:33 UTC (v2's scorer, shopper
history of 100 events).

## Live now

| Share | Public ID | Arm | Question | Live since |
|---|---|---|---|---|
| 30% | med6134 | `embed_score` on v2, default settings | Champion since 01:42 | 01:10 (off 01:33 – 01:39) |
| 30% | m0cba68 | `embed_score` on v3, default settings | v2's recipe on all data: better than v2? | 01:20 |
| 25% | mab651f | `embed_score` on v4, default settings | The trainer's final candidate: better than v2 and v3? | 01:33 |
| 15% | m3cb3ff | `embed_score` on v2, `trend=3` | Is a trend lift of 3 better than 8 on top of the model? Compare with med6134 during trends | 01:58 |

`arms.txt` is the file the process reads. Waiting for: live requests (about 55–60 purchases per hour on v2 and
v3, 50 on v4). Next comparison at 02:40 UTC, sooner if a gap of two standard errors shows.

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
| m2b37f8 | `embed_score` on v1, default settings | 23:37 – 01:58 | Offline 4–6 standard errors below v2, v3 and v4 on the same answers; live below all three (2.02% against 2.33–2.66%). Its share went to the trend test while a trend was running |
| m649454 | `embed_score` on v1, refit weights | 23:37 – 01:20 | Its weights were fitted for v1, and v2 and v3 are about to replace v1. Overall within noise of v1 default (1.81% against 2.07%), but clearly worse for new shoppers (1.72% against 3.21%) |
| mdfdc72 | `combined` (no model) | 23:12 – 01:10 | 1.32% against 2.07% for v1 over the same 50 minutes: 2.1 standard errors lower, and lower in every earlier comparison |
| m679016 | `cold_combined` | 23:51 – 00:18 | Conversion 1.25% against 1.73% for `combined` over the same period; cold conversion lower too. Far too strong a push for new products (x7.5) |
| m11bb0e | `embed_score` on v0, refit weights | 23:22 – 00:18 | No gain over v0 default in the one period both ran; v0 is behind v1 anyway |
| mf4c79f | `embed_score` on v0, default settings | 23:12 – 23:37 | 1.04% against 1.73% for `combined`; replaced by v1 |
| m4e07bd | `shopper_score` (no model, no discount or trend factor) | 23:12 – 23:37 | 1.21%; `combined` beat it in every period |
