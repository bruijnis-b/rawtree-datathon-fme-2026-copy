Two-tower embedding model, fine-tuned on the live stream.
experiment: exp-0220
run dir: /root/ivan-projects/rawtree/experiments/exp-0220/exp-0220-2
base: embed-c-hist/2
live dataset version: 2
git commit: b379f41
trained: 2026-11-15 01:06:44

score_a: 1.0168
score_c: -0.0031
parity_max_abs: 1.1444091796875e-05
product_parity_max_abs: 9.5367431640625e-07
latency_p50_ms: 0.2692205016501248
latency_p99_ms: 0.41768112452700734
cart_beta: 0.0
live_share_purchases_heldout_new: None
calibration_max_err: None
live_objective: nan
live_objective_se: nan
live_lift_all: nan
live_lift_cold: nan
live_share_top10_heldout_new: nan
disc_beta: -0.014982686378061771
new_gain: 0.0
minutes: 2.0013564904530843
live_objective_before: nan

Use: from training.export.scorer import load; model = load(<this folder>)
