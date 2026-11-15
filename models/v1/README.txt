Two-tower embedding model, fine-tuned on the live stream.
experiment: exp-0200
run dir: /root/ivan-projects/rawtree/experiments/exp-0200/exp-0200-4
base: embed-b/13
live dataset version: 1
git commit: e06b136
trained: 2026-11-14 22:27:15

calibration_max_err_raw: 0.3794796348989218
score_a_half: 0.9878586323308698
score_c_half: -0.24757860624110595
score_a: 0.9848272716935186
score_c: -0.24648420092723472
live_share_purchases_heldout_new: 0.0115
calibration_max_err: 0.1707069444454531
live_objective: 2.3176042636235556
live_objective_se: 0.07244408875703812
live_lift_all: 2.329690456390381
live_lift_cold: 2.2571732997894287
live_share_top10_heldout_new: 0.0111375
disc_beta: -0.060848675668239594
minutes: 0.823621412118276
live_objective_before: 2.1620888312657676
objective: 3.684231996536255
objective_se: 0.14286024868488312
lift_all: 3.653510570526123
lift_cold: 3.837839126586914
organic_recall: 0.24275000393390656
slate_auc: 0.7534703016281128

Use: from training.export.scorer import load; model = load(<this folder>)
