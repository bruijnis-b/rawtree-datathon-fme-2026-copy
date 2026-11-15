# Live arms (server writes this)

Updated: 2026-11-15 01:42 UTC. Code: branch `run/live-ab`, restarted 01:10:33 UTC (v2's scorer, shopper
history of 100 events).

## Live now

| Share | Public ID | Arm | Question | Live since |
|---|---|---|---|---|
| 25% | m2b37f8 | `embed_score` on v1, default settings | Champion | 23:37 |
| 25% | med6134 | `embed_score` on v2, default settings | Ahead of v1 in its first 22 minutes (below): does it hold? | 01:10 (off 01:33 – 01:39) |
| 25% | m0cba68 | `embed_score` on v3, default settings | v2's recipe on all data: better than v2 and v1? | 01:20 |
| 25% | mab651f | `embed_score` on v4, default settings | The trainer's final candidate: better than v1, v2, v3? | 01:33 |

`arms.txt` is the file the process reads. Waiting for: live requests on these four (each collects about 50
purchases per hour). Next comparison at 02:40 UTC, sooner if a gap of two standard errors shows.

## Conversion since v2 went live

| Period (UTC) | Arm | Answers | Purchases | Conversion (± 1 s.e.) | New shoppers |
|---|---|---|---|---|---|
| 01:10 – 01:33 | v1 (m2b37f8) | 1,566 | 28 | 1.79% ± 0.33 | 9 of 447, 2.01% |
| 01:10 – 01:33 | v2 (med6134) | 1,127 | 35 | 3.11% ± 0.52 | 16 of 338, 4.73% |
| 01:20 – 01:33 | v3 (m0cba68) | 741 | 20 | 2.70% ± 0.60 | 7 of 210, 3.33% |
| 01:20 – 01:33 | v1, same 13 minutes | 786 | 14 | 1.78% ± 0.47 | 5 of 219, 2.28% |

v2 is 2.1 standard errors above v1 over its 22 minutes. Short, but it agrees with the offline AUC.

## Conversion, 00:18 – 01:08 UTC (all three ran side by side)

| Public ID | Answers | Purchases | Conversion (± 1 s.e.) | New shoppers: answers, purchases, conversion |
|---|---|---|---|---|
| m2b37f8 (v1 default) | 3,674 | 76 | 2.07% ± 0.23 | 1,120, 36, 3.21% |
| m649454 (v1 refit) | 3,594 | 65 | 1.81% ± 0.22 | 1,106, 19, 1.72% |
| mdfdc72 (`combined`) | 1,894 | 25 | 1.32% ± 0.26 | 597, 14, 2.35% |

## Pruned

| Public ID | Arm | Live (UTC) | Why pruned |
|---|---|---|---|
| m649454 | `embed_score` on v1, refit weights | 23:37 – 01:20 | Its weights were fitted for v1, and v2 and v3 are about to replace v1. Overall within noise of v1 default (1.81% against 2.07%), but clearly worse for new shoppers (1.72% against 3.21%) |
| mdfdc72 | `combined` (no model) | 23:12 – 01:10 | 1.32% against 2.07% for v1 over the same 50 minutes: 2.1 standard errors lower, and lower in every earlier comparison |
| m679016 | `cold_combined` | 23:51 – 00:18 | Conversion 1.25% against 1.73% for `combined` over the same period; cold conversion lower too. Far too strong a push for new products (x7.5) |
| m11bb0e | `embed_score` on v0, refit weights | 23:22 – 00:18 | No gain over v0 default in the one period both ran; v0 is behind v1 anyway |
| mf4c79f | `embed_score` on v0, default settings | 23:12 – 23:37 | 1.04% against 1.73% for `combined`; replaced by v1 |
| m4e07bd | `shopper_score` (no model, no discount or trend factor) | 23:12 – 23:37 | 1.21%; `combined` beat it in every period |
