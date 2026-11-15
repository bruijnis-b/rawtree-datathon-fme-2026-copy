Two-tower embedding model, fine-tuned on the live stream.
experiment: exp-0240
run dir: /root/ivan-projects/rawtree/experiments/exp-0240/exp-0240-2
base: embed-c-hist/2
live dataset version: 3
git commit: df15ea5
trained: 2026-11-15 06:30:59

score_a: 1.0328
score_c: 0.43
parity_max_abs: 9.5367431640625e-06
product_parity_max_abs: 9.5367431640625e-07
latency_p50_ms: 0.12500048615038395
latency_p99_ms: 0.22396561398636539
cart_beta: 0.0
live_share_purchases_heldout_new: None
calibration_max_err: None
live_objective: nan
live_objective_se: nan
live_lift_all: nan
live_lift_cold: nan
live_share_top10_heldout_new: nan
disc_beta: -0.07665140181779861
new_gain: 0.0
minutes: 2.2210948705673217
live_objective_before: nan

Use: from training.export.scorer import load; model = load(<this folder>)
