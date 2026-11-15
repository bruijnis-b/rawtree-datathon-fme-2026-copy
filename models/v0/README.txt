Two-tower embedding model, serving package.
experiment: exp-0189
run dir: /root/ivan-projects/rawtree/experiments/exp-0189/exp-0189-1
git commit: 62bc1a7
trained: 2026-11-14 20:19:59
fold: 0 (all data: False); preset: default

objective: 2.7916
objective_se: 0.1257
lift_all: 2.8036
lift_cold: 2.7312
slate_auc: 0.7487
slate_auc_lift: 0.0921
organic_recall: 0.2393
organic_recall_lift: 2.2396
organic_recall_cold: 0.1786
calibration_max_err: 0.6387
slot_max_gap: 0.2021
parity_max_abs: 0.0000
product_parity_max_abs: 0.0000
latency_p50_ms: 0.1488
latency_p99_ms: 0.2153
minutes: 4.6316
alpha: 0.8126
c_click: -4.2788
c_purchase: -1.3509
slate_auc_lift_lo: 0.0821
slate_auc_lift_hi: 0.1013
organic_recall_lift_lo: 2.1292
organic_recall_lift_hi: 2.3637

Use: from training.export.scorer import load; model = load(<this folder>)
