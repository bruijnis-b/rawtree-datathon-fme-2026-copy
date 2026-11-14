| # | run | settings | objective ± se | lift all | lift cold | slate_auc | org. recall | cal. err | slot gap | eligible | checks failed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | embed-a3/2 | preset=desc | 3.261 ± 0.138 | 3.243 | 3.354 | 0.753 | 0.243 | 0.83 | 0.20 | yes | calibration within 20 % per decile |
| 2 | embed-a3/4 | preset=lr07 | 3.257 ± 0.131 | 3.264 | 3.222 | 0.752 | 0.237 | 0.61 | 0.17 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 3 | embed-a3/3 | preset=hist50 | 3.196 ± 0.138 | 3.223 | 3.061 | 0.761 | 0.257 | 0.84 | 0.21 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 4 | embed-a3/5 | preset=dim32 | 3.043 ± 0.124 | 3.072 | 2.899 | 0.753 | 0.238 | 0.63 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
| 5 | embed-a3/1 | preset=default | 2.816 ± 0.121 | 2.820 | 2.795 | 0.749 | 0.240 | 0.81 | 0.20 | yes | held-out share of top-10 <= 2x share of clicks, calibration within 20 % per decile |
