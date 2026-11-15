# Live arms (server writes this)

Updated: 2026-11-15 01:22 UTC. Code: branch `run/live-ab`, restarted 01:10:33 UTC (v2's scorer, shopper
history of 100 events).

## Live now

| Share | Public ID | Arm | Question | At this share since |
|---|---|---|---|---|
| 34% | m2b37f8 | `embed_score` on v1, default settings | Champion | 01:20 |
| 33% | med6134 | `embed_score` on v2, default settings | Does v2 beat v1 live? Offline it does, clearly | 01:20 (25% from 01:10) |
| 33% | m0cba68 | `embed_score` on v3, default settings | Does the final pipeline (v3) beat v1 and v2 live? | 01:20 |

Equal shares: offline v2 looks better than the champion, and v3 is v2's recipe on more data. `arms.txt` is the
file the process reads. Next review: 02:20 UTC (one hour side by side).

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
