Two-tower embedding model, fine-tuned on the live stream.
experiment: exp-0226
run dir: /root/ivan-projects/rawtree/experiments/exp-0226/exp-0226-1
base: embed-c-hist-b/1
live dataset version: 2
git commit: 18915c4
trained: 2026-11-15 01:23:43

score_a: 1.0616
score_c: 0.2951
parity_max_abs: 1.1444091796875e-05
product_parity_max_abs: 4.76837158203125e-07
latency_p50_ms: 0.11900899698957801
latency_p99_ms: 0.18948032637126744
cart_beta: 0.0
live_share_purchases_heldout_new: None
calibration_max_err: None
live_objective: nan
live_objective_se: nan
live_lift_all: nan
live_lift_cold: nan
live_share_top10_heldout_new: nan
disc_beta: -0.0157945454120636
new_gain: 0.0
minutes: 1.0419896324475606
live_objective_before: nan

Use: from training.export.scorer import load; model = load(<this folder>)
