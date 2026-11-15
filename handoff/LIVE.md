# Live arms (server writes this)

Updated: 2026-11-15 00:55 UTC. Code: branch `run/live-ab`, restarted 00:22:39 UTC with the bought filter.

## Live now

| Share | Public ID | Arm | Role | At this share since |
|---|---|---|---|---|
| 40% | m2b37f8 | `embed_score` on v1, default settings | Champion | 00:18 |
| 40% | m649454 | `embed_score` on v1, refit weights (`alpha` 0.58, `w_cat` 1.95, `w_sub` 0.58, `ctx` 1.9, `recent` 2.7, `cart` 3.5, `new` 2.8) | Side question: do refit weights help? | 00:18 |
| 20% | mdfdc72 | `combined` (no model) | Reference without a model | 00:18 |

Both v1 arms ran at 20% from 23:37. `arms.txt` is the file the process reads.

**When v2 arrives:** it starts at 25%. `combined` stays only while it still tells us something: it is below
v1 in every comparison so far, so it is the first to go. Shares then follow the rules in `handoff/README.md`.

## Pruned

| Public ID | Arm | Live (UTC) | Why pruned |
|---|---|---|---|
| m679016 | `cold_combined` | 23:51 – 00:18 | Conversion 1.25% against 1.73% for `combined` over the same period; cold conversion lower too. Far too strong a push for new products (x7.5) |
| m11bb0e | `embed_score` on v0, refit weights | 23:22 – 00:18 | No gain over v0 default in the one period both ran; v0 is behind v1 anyway |
| mf4c79f | `embed_score` on v0, default settings | 23:12 – 23:37 | 1.04% against 1.73% for `combined`; replaced by v1 |
| m4e07bd | `shopper_score` (no model, no discount or trend factor) | 23:12 – 23:37 | 1.21%; `combined` beat it in every period |

## Conversion so far (23:12 – 00:22 UTC, our own feedback)

| Public ID | Answers | Purchases | Conversion |
|---|---|---|---|
| m2b37f8 (v1 default) | 1,842 | 36 | 1.95% |
| m649454 (v1 refit) | 1,853 | 33 | 1.78% |
| mdfdc72 (`combined`) | 3,004 | 52 | 1.73% |
| m11bb0e (v0 refit) | 2,250 | 39 | 1.73% |
| m679016 (`cold_combined`) | 959 | 12 | 1.25% |

The arms did not all run over the same period, so only compare arms within a row pair that overlaps. The top
four are within noise of each other.
