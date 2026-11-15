Two-tower embedding model, fine-tuned on the live stream.
experiment: exp-0214
run dir: /root/ivan-projects/rawtree/experiments/exp-0214/exp-0214-1
base: embed-cmp/1
live dataset version: 1
git commit: a8fb90c
trained: 2026-11-15 00:23:48

calibration_max_err_raw: 0.3773573399698762
score_a_half: 0.9736660562988485
score_c_half: 0.10478168149817013
score_a: 0.9732216457645807
score_c: 0.11773132125385595
parity_max_abs: 1.1444091796875e-05
product_parity_max_abs: 8.344650268554688e-07
latency_p50_ms: 0.18897501286119223
latency_p99_ms: 0.2801789954537525
hm_none_0_all: 2.0163934230804443
hm_none_0_new_user: 2.0921449661254883
hm_none_0_cold: 1.9245483875274658
hm_snapshot_10_all: 2.4644808769226074
hm_snapshot_10_new_user: 2.537764310836792
hm_snapshot_10_cold: 2.3156216144561768
hm_snapshot_20_all: 2.7358834743499756
hm_snapshot_20_new_user: 2.7598187923431396
hm_snapshot_20_cold: 2.4962806701660156
hm_snapshot_50_all: 2.9653916358947754
hm_snapshot_50_new_user: 2.861027240753174
hm_snapshot_50_cold: 2.601487874984741
hm_snapshot_100_all: 3.023679256439209
hm_snapshot_100_new_user: 2.8700907230377197
hm_snapshot_100_cold: 2.6450583934783936
hm_dynamic_1_all: 1.5974500179290771
hm_dynamic_1_new_user: 1.7039275169372559
hm_dynamic_1_cold: 1.5419766902923584
hm_dynamic_3_all: 1.9544627666473389
hm_dynamic_3_new_user: 2.072507619857788
hm_dynamic_3_cold: 1.8799149990081787
hm_dynamic_5_all: 2.153460741043091
hm_dynamic_5_new_user: 2.2900302410125732
hm_dynamic_5_cold: 2.082890510559082
hm_dynamic_10_all: 2.4631147384643555
hm_dynamic_10_new_user: 2.506042242050171
hm_dynamic_10_cold: 2.277364492416382
hm_dynamic_20_all: 2.7404372692108154
hm_dynamic_20_new_user: 2.755286931991577
hm_dynamic_20_cold: 2.480340003967285
hm_dynamic_50_all: 2.9608378410339355
hm_dynamic_50_new_user: 2.854984998703003
hm_dynamic_50_cold: 2.6036131381988525
hm_dynamic_100_all: 3.028233051300049
hm_dynamic_100_new_user: 2.8670694828033447
hm_dynamic_100_cold: 2.643995761871338
fb_lift_all: 0.5365853309631348
fb_lift_new_user: 0.4760638475418091
fb_hit_all: 0.5866528749465942
fb_clicks: 1199
fb_share_clicks_in_cart: 0.11843202668890743
fb_hit_in_cart: 0.6619718074798584
cart_beta: 0.0
live_share_purchases_heldout_new: 0.0115
calibration_max_err: 0.17627974187053042
live_objective: 2.428792436917623
live_objective_se: 0.0749664232134819
live_lift_all: 2.453552007675171
live_lift_cold: 2.304994583129883
live_share_top10_heldout_new: 0.0103875
disc_beta: -0.057244013994932175
new_gain: 0.0
minutes: 1.3912544250488281
live_objective_before: 2.295109510421753
objective: 4.230793635050456
objective_se: 0.1652401238679886
lift_all: 4.235015392303467
lift_cold: 4.2096848487854
organic_recall: 0.2699500024318695
slate_auc: 0.7761151790618896

Use: from training.export.scorer import load; model = load(<this folder>)
