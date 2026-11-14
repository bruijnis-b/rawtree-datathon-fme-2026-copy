| # | run | settings | objective ± se | lift all | lift cold | slate_auc | org. recall | cal. err | slot gap | eligible | checks failed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | embed-a1/26 | preset=desc | 3.217 ± 0.137 | 3.229 | 3.159 | 0.755 | 0.245 | 0.66 | 0.20 | yes | calibration within 20 % per decile |
| 2 | embed-a1/11 | preset=hist50 | 3.158 ± 0.139 | 3.163 | 3.135 | 0.760 | 0.257 | 0.67 | 0.21 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 3 | embed-a1/28 | preset=lr07 | 3.151 ± 0.128 | 3.155 | 3.135 | 0.752 | 0.237 | 0.37 | 0.17 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 4 | embed-a1/2 | preset=dim32 | 3.033 ± 0.125 | 3.060 | 2.899 | 0.754 | 0.239 | 0.36 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 5 | embed-a1/6 | preset=iddrop50 | 3.003 ± 0.130 | 3.001 | 3.011 | 0.749 | 0.238 | 0.60 | 0.21 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 6 | embed-a1/33 | preset=bs4096 | 2.992 ± 0.125 | 2.988 | 3.010 | 0.753 | 0.240 | 0.59 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 7 | embed-a1/9 | preset=histdrop50 | 2.919 ± 0.126 | 2.900 | 3.015 | 0.748 | 0.240 | 0.61 | 0.19 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 8 | embed-a1/31 | preset=wd4 | 2.862 ± 0.127 | 2.862 | 2.860 | 0.747 | 0.240 | 0.62 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 9 | embed-a1/22 | preset=click03 | 2.859 ± 0.128 | 2.857 | 2.867 | 0.753 | 0.240 | 0.53 | 0.23 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 10 | embed-a1/5 | preset=iddrop0 | 2.833 ± 0.125 | 2.796 | 3.018 | 0.740 | 0.243 | 0.93 | 0.19 | no | calibration within 20 % per decile |
| 11 | embed-a1/1 | preset=default | 2.808 ± 0.124 | 2.816 | 2.770 | 0.751 | 0.240 | 0.61 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 12 | embed-a1/30 | preset=wd0 | 2.790 ± 0.123 | 2.781 | 2.830 | 0.749 | 0.240 | 0.66 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 13 | embed-a1/14 | preset=recency50 | 2.788 ± 0.125 | 2.772 | 2.867 | 0.746 | 0.243 | 0.74 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 14 | embed-a1/12 | preset=pool_mean | 2.731 ± 0.123 | 2.714 | 2.815 | 0.750 | 0.236 | 0.56 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 15 | embed-a1/24 | preset=slot_fixed | 2.724 ± 0.117 | 2.723 | 2.728 | 0.747 | 0.239 | 0.67 | 0.00 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 16 | embed-a1/25 | preset=slot_off | 2.720 ± 0.117 | 2.724 | 2.702 | 0.750 | 0.240 | 0.69 | 1.51 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 17 | embed-a1/13 | preset=pool_att | 2.694 ± 0.120 | 2.674 | 2.795 | 0.747 | 0.238 | 0.76 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 18 | embed-a1/20 | preset=prop05 | 2.666 ± 0.124 | 2.664 | 2.678 | 0.750 | 0.240 | 0.66 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 19 | embed-a1/27 | preset=noprice | 2.639 ± 0.119 | 2.649 | 2.587 | 0.748 | 0.241 | 0.65 | 0.22 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 20 | embed-a1/32 | preset=bs1024 | 2.571 ± 0.122 | 2.568 | 2.587 | 0.743 | 0.240 | 0.74 | 0.20 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 21 | embed-a1/8 | preset=histdrop0 | 2.568 ± 0.118 | 2.596 | 2.427 | 0.744 | 0.240 | 0.82 | 0.21 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 22 | embed-a1/19 | preset=org_uniform_types | 2.531 ± 0.114 | 2.534 | 2.514 | 0.745 | 0.226 | 0.68 | 0.20 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 23 | embed-a1/18 | preset=org_nologq | 2.417 ± 0.115 | 2.418 | 2.416 | 0.748 | 0.104 | 0.76 | 0.21 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 24 | embed-a1/4 | preset=hidden256 | 2.414 ± 0.114 | 2.391 | 2.531 | 0.743 | 0.240 | 0.80 | 0.19 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 25 | embed-a1/29 | preset=lr5 | 2.358 ± 0.119 | 2.302 | 2.639 | 0.739 | 0.238 | 0.81 | 0.21 | no | calibration within 20 % per decile |
| 26 | embed-a1/3 | preset=dim128 | 2.268 ± 0.114 | 2.248 | 2.369 | 0.736 | 0.238 | 0.85 | 0.20 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile, p99 latency, batch 1 |
| 27 | embed-a1/21 | preset=prop01 | 2.265 ± 0.114 | 2.264 | 2.269 | 0.744 | 0.237 | 0.77 | 0.21 | yes | calibration within 20 % per decile |
| 28 | embed-a1/10 | preset=hist0 | 2.211 ± 0.100 | 2.197 | 2.278 | 0.715 | 0.182 | 0.79 | 0.19 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 29 | embed-a1/23 | preset=click3 | 2.096 ± 0.105 | 2.081 | 2.171 | 0.734 | 0.232 | 0.87 | 0.20 | no | calibration within 20 % per decile |
| 30 | embed-a1/7 | preset=iddrop100 | 2.040 ± 0.098 | 2.010 | 2.192 | 0.728 | 0.197 | 0.41 | 0.21 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 31 | embed-a1/17 | preset=org_staged | 2.019 ± 0.105 | 2.032 | 1.956 | 0.741 | 0.093 | 0.78 | 0.20 | no | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 32 | embed-a1/16 | preset=org_w03 | 1.989 ± 0.103 | 1.963 | 2.122 | 0.733 | 0.231 | 0.87 | 0.20 | no | calibration within 20 % per decile |
| 33 | embed-a1/15 | preset=org_off | 0.373 ± 0.055 | 0.386 | 0.310 | 0.715 | 0.030 | 0.98 | 0.21 | no | calibration within 20 % per decile |
