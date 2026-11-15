Two-tower embedding model, fine-tuned on the live stream.
experiment: exp-0236
run dir: /root/ivan-projects/rawtree/experiments/exp-0236/exp-0236-1
base: embed-c-hist-b/1
live dataset version: 3
git commit: df15ea5
trained: 2026-11-15 06:29:50

score_a: 1.0839
score_c: 0.502
parity_max_abs: 1.52587890625e-05
product_parity_max_abs: 4.76837158203125e-07
latency_p50_ms: 0.12151250848546624
latency_p99_ms: 0.2455497585469855
cart_beta: 0.0
live_share_purchases_heldout_new: None
calibration_max_err: None
live_objective: nan
live_objective_se: nan
live_lift_all: nan
live_lift_cold: nan
live_share_top10_heldout_new: nan
disc_beta: -0.0797765925526619
new_gain: 0.0
minutes: 1.3715536991755168
live_objective_before: nan

Use: from training.export.scorer import load; model = load(<this folder>)
