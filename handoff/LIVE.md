# Live arms (server writes this)

Updated: 2026-11-15 01:20 UTC. Code: branch `run/live-ab`, restarted 01:10:33 UTC (v2's scorer, shopper
history of 100 events).

## Live now

| Share | Public ID | Arm | Question | At this share since |
|---|---|---|---|---|
| 50% | m2b37f8 | `embed_score` on v1, default settings | Champion | 01:10 |
| 25% | med6134 | `embed_score` on v2, default settings | Does v2 beat v1 live? Offline it does, clearly | 01:10 |
| 25% | m649454 | `embed_score` on v1, refit weights (`alpha` 0.58, `w_cat` 1.95, `w_sub` 0.58, `ctx` 1.9, `recent` 2.7, `cart` 3.5, `new` 2.8) | Do refit weights help? Looks like no for new shoppers; decided at 02:10 | 01:10 |

`arms.txt` is the file the process reads. Next review: 02:10 UTC.

## Conversion, 00:18 – 01:08 UTC (all three ran side by side)

| Public ID | Answers | Purchases | Conversion (± 1 s.e.) | New shoppers: answers, purchases, conversion |
|---|---|---|---|---|
| m2b37f8 (v1 default) | 3,674 | 76 | 2.07% ± 0.23 | 1,120, 36, 3.21% |
| m649454 (v1 refit) | 3,594 | 65 | 1.81% ± 0.22 | 1,106, 19, 1.72% |
| mdfdc72 (`combined`) | 1,894 | 25 | 1.32% ± 0.26 | 597, 14, 2.35% |

## Pruned

| Public ID | Arm | Live (UTC) | Why pruned |
|---|---|---|---|
| mdfdc72 | `combined` (no model) | 23:12 – 01:10 | 1.32% against 2.07% for v1 over the same 50 minutes: 2.1 standard errors lower, and lower in every earlier comparison |
| m679016 | `cold_combined` | 23:51 – 00:18 | Conversion 1.25% against 1.73% for `combined` over the same period; cold conversion lower too. Far too strong a push for new products (x7.5) |
| m11bb0e | `embed_score` on v0, refit weights | 23:22 – 00:18 | No gain over v0 default in the one period both ran; v0 is behind v1 anyway |
| mf4c79f | `embed_score` on v0, default settings | 23:12 – 23:37 | 1.04% against 1.73% for `combined`; replaced by v1 |
| m4e07bd | `shopper_score` (no model, no discount or trend factor) | 23:12 – 23:37 | 1.21%; `combined` beat it in every period |
