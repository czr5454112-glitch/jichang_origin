# CIE paired random-robustness audit

- manifest SHA-256: `0bc8471ed4f34e046aae0b912737290716556317cdc0aec9e57ff2ada460dc17`
- executed artifacts: 100/100
- frozen paired seeds: `[104729, 130363, 155921, 181081, 205759, 232003, 257053, 283303, 308081, 333667]`
- bootstrap: 10000 paired resamples, 95% percentile CI
- contrast: `P1D1 - P0D0`; negative is better only for lower-is-better metrics
- relative delta is `100 * mean(P1D1-P0D0) / mean(P0D0)` and is N/M when the P0D0 mean is zero
- paired Cohen dz is the paired-difference mean divided by its sample standard deviation; zero difference SD is explicitly N/M
- win/tie/loss counts orient each seed by the metric's preferred direction; failure rate uses all frozen seeds as its denominator
- incomplete and failed seeds are never removed or replaced
- 1x cells start from the audited same-HCA release schedule, then apply the frozen paired arrival jitter; the resulting trace is not eligible for a direct HCA timing comparison
- intermediate and 2x cells start from their canonical complete-flight population before the same paired jitter contract is applied
- 2x THT is N/A even when every bag completes; fixed-denominator capacity, deadline, tardiness, completion-target and backlog metrics remain eligible
- legacy incomplete backlog areas enter estimates only after frozen-seed jitter regeneration, identity verification, and exact fixed-horizon tail correction; ambiguous tails remain N/M

## Scenario gates

| Map | Load | Status | Valid pairs | Missing seeds | Failed seeds | Failure rate | Reconstructed tails |
|---|---:|---|---:|---|---|---:|---:|
| map2 | 1.00x | COMPLETE_FROZEN_PAIRED_SEEDS | 10 | none | none | 0.000 | 0 |
| map2 | 1.75x | COMPLETE_FROZEN_PAIRED_SEEDS | 10 | none | none | 0.000 | 0 |
| map2 | 2.00x | COMPLETE_FROZEN_PAIRED_SEEDS | 10 | none | none | 0.000 | 0 |
| nanning | 1.00x | COMPLETE_FROZEN_PAIRED_SEEDS | 10 | none | none | 0.000 | 0 |
| nanning | 2.00x | COMPLETE_FROZEN_PAIRED_SEEDS | 10 | none | none | 0.000 | 10 |

## Paired estimates

| Map | Load | Metric | Status | P0D0 mean | P1D1 mean | Delta | Delta % | dz | W/T/L | 95% CI |
|---|---:|---|---|---:|---:|---:|---|---|---|---|
| map2 | 1.00x | completed raw bags | COMPLETE_FROZEN_PAIRED_SEEDS | 28506 | 28506 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | raw-bag completion rate | COMPLETE_FROZEN_PAIRED_SEEDS | 1 | 1 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | fixed-denominator on-time bags | COMPLETE_FROZEN_PAIRED_SEEDS | 28506 | 28506 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | fixed-denominator on-time rate | COMPLETE_FROZEN_PAIRED_SEEDS | 1 | 1 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | fixed-denominator missed bags | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | fixed-denominator missed rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | all-population tardiness sum (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | all-population tardiness mean (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | all-population tardiness P95 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | all-population tardiness P99 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | all-population tardiness max (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | time to 90% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 62932.4 | 62932.4 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | time to 95% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 67286.7 | 67286.7 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | time to 99% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 71125.8 | 71121.6 | -4.18023 | -0.00587724% | -6.5814 | 10/0/0 | [-4.5464, -3.80381] |
| map2 | 1.00x | total raw-bag backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 7.21553e+07 | 7.21462e+07 | -9080.04 | -0.012584% | -4.95815 | 10/0/0 | [-10185.4, -8058.17] |
| map2 | 1.00x | total raw-bag backlog peak | COMPLETE_FROZEN_PAIRED_SEEDS | 2367.9 | 2367.7 | -0.2 | -0.0084463% | -0.316228 | 1/9/0 | [-0.6, 0] |
| map2 | 1.00x | source backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 6.68735e+07 | 6.68735e+07 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.00x | network backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 5.28175e+06 | 5.27267e+06 | -9080.04 | -0.171914% | -4.95815 | 10/0/0 | [-10202.1, -8071.97] |
| map2 | 1.00x | 1x full-population mean THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 213.06 | 211.957 | -1.1026 | -0.51751% | -4.25311 | 10/0/0 | [-1.25083, -0.94918] |
| map2 | 1.00x | 1x full-population P95 THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 252.337 | 249.293 | -3.04362 | -1.20617% | -2.24108 | 10/0/0 | [-3.86669, -2.28217] |
| map2 | 1.00x | 1x full-population P99 THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 275.182 | 263.752 | -11.4297 | -4.15352% | -4.01691 | 10/0/0 | [-13.1169, -9.72456] |
| map2 | 1.00x | 1x full-population max THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 321.171 | 304.189 | -16.9828 | -5.28776% | -1.6979 | 9/1/0 | [-22.656, -11.0911] |
| map2 | 1.75x | completed raw bags | COMPLETE_FROZEN_PAIRED_SEEDS | 49765 | 49765 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.75x | raw-bag completion rate | COMPLETE_FROZEN_PAIRED_SEEDS | 1 | 1 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.75x | fixed-denominator on-time bags | COMPLETE_FROZEN_PAIRED_SEEDS | 49635.2 | 49754.7 | 119.5 | 0.240757% | 1.59805 | 10/0/0 | [76.4, 163.802] |
| map2 | 1.75x | fixed-denominator on-time rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.997392 | 0.999793 | 0.00240129 | 0.240757% | 1.59805 | 10/0/0 | [0.00154325, 0.00329353] |
| map2 | 1.75x | fixed-denominator missed bags | COMPLETE_FROZEN_PAIRED_SEEDS | 129.8 | 10.3 | -119.5 | -92.0647% | -1.59805 | 10/0/0 | [-164.9, -76.1] |
| map2 | 1.75x | fixed-denominator missed rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.00260826 | 0.000206973 | -0.00240129 | -92.0647% | -1.59805 | 10/0/0 | [-0.00329549, -0.00153517] |
| map2 | 1.75x | all-population tardiness sum (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 69706.3 | 4308.78 | -65397.5 | -93.8187% | -1.07308 | 10/0/0 | [-103530, -32528] |
| map2 | 1.75x | all-population tardiness mean (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.40071 | 0.0865825 | -1.31413 | -93.8187% | -1.07308 | 10/0/0 | [-2.10797, -0.664942] |
| map2 | 1.75x | all-population tardiness P95 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.75x | all-population tardiness P99 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 0 | 0 | 0 | N/M (N_M_ZERO_P0D0_MEAN) | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.75x | all-population tardiness max (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1204.59 | 291.265 | -913.328 | -75.8205% | -1.96715 | 10/0/0 | [-1184.39, -636.587] |
| map2 | 1.75x | time to 90% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 64335.4 | 64335.9 | 0.4987 | 0.000775157% | 0.726875 | 0/6/4 | [0.10712, 0.926664] |
| map2 | 1.75x | time to 95% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 67876.7 | 67876.7 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.75x | time to 99% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 71703.4 | 71702.8 | -0.57776 | -0.000805764% | -0.950992 | 8/2/0 | [-0.945314, -0.232792] |
| map2 | 1.75x | total raw-bag backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.28282e+08 | 1.24885e+08 | -3.39649e+06 | -2.64767% | -3.34155 | 10/0/0 | [-4.03098e+06, -2.85078e+06] |
| map2 | 1.75x | total raw-bag backlog peak | COMPLETE_FROZEN_PAIRED_SEEDS | 4050 | 4010.4 | -39.6 | -0.977778% | -2.86586 | 10/0/0 | [-47.9, -31.6] |
| map2 | 1.75x | source backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.11654e+08 | 1.11654e+08 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 1.75x | network backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.66284e+07 | 1.32319e+07 | -3.39649e+06 | -20.4259% | -3.34155 | 10/0/0 | [-4.02166e+06, -2.8337e+06] |
| map2 | 1.75x | 1x full-population mean THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 549.658 | 395.127 | -154.531 | -28.114% | -4.48543 | 10/0/0 | [-175.721, -135.061] |
| map2 | 1.75x | 1x full-population P95 THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 2817.13 | 1411.63 | -1405.5 | -49.8913% | -4.41059 | 10/0/0 | [-1593.94, -1227.39] |
| map2 | 1.75x | 1x full-population P99 THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 5015.97 | 3002.89 | -2013.08 | -40.1335% | -3.3035 | 10/0/0 | [-2397.72, -1679.01] |
| map2 | 1.75x | 1x full-population max THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 5557.61 | 3526.63 | -2030.98 | -36.5441% | -3.57281 | 10/0/0 | [-2387.91, -1722.69] |
| map2 | 2.00x | completed raw bags | COMPLETE_FROZEN_PAIRED_SEEDS | 57012 | 57012 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 2.00x | raw-bag completion rate | COMPLETE_FROZEN_PAIRED_SEEDS | 1 | 1 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 2.00x | fixed-denominator on-time bags | COMPLETE_FROZEN_PAIRED_SEEDS | 55532.5 | 56797.4 | 1264.9 | 2.27777% | 2.27234 | 10/0/0 | [937.397, 1592.5] |
| map2 | 2.00x | fixed-denominator on-time rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.974049 | 0.996236 | 0.0221866 | 2.27777% | 2.27234 | 10/0/0 | [0.0165369, 0.0278734] |
| map2 | 2.00x | fixed-denominator missed bags | COMPLETE_FROZEN_PAIRED_SEEDS | 1479.5 | 214.6 | -1264.9 | -85.4951% | -2.27234 | 10/0/0 | [-1592.6, -936.485] |
| map2 | 2.00x | fixed-denominator missed rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.0259507 | 0.00376412 | -0.0221866 | -85.4951% | -2.27234 | 10/0/0 | [-0.0280608, -0.0165103] |
| map2 | 2.00x | all-population tardiness sum (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.34525e+06 | 162952 | -1.1823e+06 | -87.8868% | -1.47878 | 10/0/0 | [-1.69219e+06, -759768] |
| map2 | 2.00x | all-population tardiness mean (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 23.5959 | 2.85821 | -20.7377 | -87.8868% | -1.47878 | 10/0/0 | [-29.651, -13.3073] |
| map2 | 2.00x | all-population tardiness P95 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 24.2467 | 0 | -24.2467 | -100% | -0.316228 | 1/9/0 | [-72.7401, 0] |
| map2 | 2.00x | all-population tardiness P99 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 746.753 | 48.4304 | -698.322 | -93.5145% | -1.47111 | 9/1/0 | [-972.149, -418.592] |
| map2 | 2.00x | all-population tardiness max (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 3536.31 | 1682.95 | -1853.36 | -52.4095% | -2.44887 | 10/0/0 | [-2307.71, -1441.89] |
| map2 | 2.00x | time to 90% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 64385.7 | 64384.9 | -0.830539 | -0.00128994% | -1.02418 | 7/3/0 | [-1.33502, -0.388608] |
| map2 | 2.00x | time to 95% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 67649.4 | 67650.1 | 0.712316 | 0.00105295% | 0.509889 | 1/5/4 | [0.00446324, 1.6182] |
| map2 | 2.00x | time to 99% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 71582.4 | 71580.4 | -2.03841 | -0.00284765% | -1.10294 | 7/2/1 | [-3.12082, -0.963015] |
| map2 | 2.00x | total raw-bag backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.55729e+08 | 1.4618e+08 | -9.54828e+06 | -6.13136% | -4.16102 | 10/0/0 | [-1.08937e+07, -8.22083e+06] |
| map2 | 2.00x | total raw-bag backlog peak | COMPLETE_FROZEN_PAIRED_SEEDS | 4920.8 | 4594.9 | -325.9 | -6.62291% | -3.10091 | 10/0/0 | [-388.002, -266.3] |
| map2 | 2.00x | source backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.27838e+08 | 1.27838e+08 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| map2 | 2.00x | network backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 2.7891e+07 | 1.83428e+07 | -9.54828e+06 | -34.2342% | -4.16102 | 10/0/0 | [-1.09225e+07, -8.23855e+06] |
| map2 | 2.00x | 1x full-population mean THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| map2 | 2.00x | 1x full-population P95 THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| map2 | 2.00x | 1x full-population P99 THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| map2 | 2.00x | 1x full-population max THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 1.00x | completed raw bags | COMPLETE_FROZEN_PAIRED_SEEDS | 28506 | 28506 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| nanning | 1.00x | raw-bag completion rate | COMPLETE_FROZEN_PAIRED_SEEDS | 1 | 1 | 0 | 0% | N/M (N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD) | 0/10/0 | [0, 0] |
| nanning | 1.00x | fixed-denominator on-time bags | COMPLETE_FROZEN_PAIRED_SEEDS | 18455.9 | 18471.6 | 15.7 | 0.0850676% | 3.36343 | 10/0/0 | [12.9, 18.3] |
| nanning | 1.00x | fixed-denominator on-time rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.647439 | 0.64799 | 0.000550761 | 0.0850676% | 3.36343 | 10/0/0 | [0.000452536, 0.00064197] |
| nanning | 1.00x | fixed-denominator missed bags | COMPLETE_FROZEN_PAIRED_SEEDS | 10050.1 | 10034.4 | -15.7 | -0.156217% | -3.36343 | 10/0/0 | [-18.4, -12.8] |
| nanning | 1.00x | fixed-denominator missed rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.352561 | 0.35201 | -0.000550761 | -0.156217% | -3.36343 | 10/0/0 | [-0.00064197, -0.000452449] |
| nanning | 1.00x | all-population tardiness sum (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 9.11545e+07 | 9.10626e+07 | -91872 | -0.100787% | -4.80654 | 10/0/0 | [-103594, -81301] |
| nanning | 1.00x | all-population tardiness mean (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 3197.73 | 3194.51 | -3.2229 | -0.100787% | -4.80654 | 10/0/0 | [-3.6295, -2.85393] |
| nanning | 1.00x | all-population tardiness P95 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 27477.6 | 27469.5 | -8.02695 | -0.0292127% | -8.36739 | 10/0/0 | [-8.56147, -7.4313] |
| nanning | 1.00x | all-population tardiness P99 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 44640.1 | 44637.4 | -2.67067 | -0.00598267% | -1.20345 | 10/0/0 | [-4.0366, -1.4401] |
| nanning | 1.00x | all-population tardiness max (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 48907.1 | 48772.1 | -134.981 | -0.275995% | -2.80007 | 10/0/0 | [-164.25, -107.971] |
| nanning | 1.00x | time to 90% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 68139.6 | 68126.5 | -13.1591 | -0.0193119% | -0.979498 | 10/0/0 | [-22.2236, -6.23374] |
| nanning | 1.00x | time to 95% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 71972.1 | 71973.7 | 1.54431 | 0.0021457% | 1.02115 | 1/2/7 | [0.689261, 2.42598] |
| nanning | 1.00x | time to 99% completion (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 75442.8 | 75442.5 | -0.383517 | -0.000508354% | -0.906319 | 8/1/1 | [-0.630149, -0.138766] |
| nanning | 1.00x | total raw-bag backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.93465e+08 | 1.93178e+08 | -286423 | -0.148049% | -4.91673 | 10/0/0 | [-322726, -254789] |
| nanning | 1.00x | total raw-bag backlog peak | COMPLETE_FROZEN_PAIRED_SEEDS | 3607.2 | 3601.6 | -5.6 | -0.155245% | -3.91652 | 10/0/0 | [-6.4, -4.8] |
| nanning | 1.00x | source backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.87668e+08 | 1.87668e+08 | 2.95715 | 1.57573e-06% | 0.246039 | 4/0/6 | [-3.59163, 10.6541] |
| nanning | 1.00x | network backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 5.79683e+06 | 5.5104e+06 | -286426 | -4.94108% | -4.91658 | 10/0/0 | [-322124, -254840] |
| nanning | 1.00x | 1x full-population mean THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 298.193 | 285.7 | -12.4931 | -4.1896% | -5.44472 | 10/0/0 | [-13.9283, -11.2532] |
| nanning | 1.00x | 1x full-population P95 THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 524.657 | 483.812 | -40.8454 | -7.78516% | -3.98468 | 10/0/0 | [-46.8005, -34.7529] |
| nanning | 1.00x | 1x full-population P99 THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 624.524 | 574.649 | -49.8752 | -7.98611% | -3.45561 | 10/0/0 | [-58.4464, -41.6781] |
| nanning | 1.00x | 1x full-population max THT (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 983.351 | 849.286 | -134.065 | -13.6335% | -3.25728 | 10/0/0 | [-157.22, -109.187] |
| nanning | 2.00x | completed raw bags | COMPLETE_FROZEN_PAIRED_SEEDS | 46876.2 | 56186.4 | 9310.2 | 19.8613% | 9.91454 | 10/0/0 | [8717.76, 9811.31] |
| nanning | 2.00x | raw-bag completion rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.822216 | 0.985519 | 0.163302 | 19.8613% | 9.91454 | 10/0/0 | [0.152622, 0.172257] |
| nanning | 2.00x | fixed-denominator on-time bags | COMPLETE_FROZEN_PAIRED_SEEDS | 20353.5 | 20712.2 | 358.7 | 1.76235% | 1.3167 | 8/0/2 | [192.59, 513.302] |
| nanning | 2.00x | fixed-denominator on-time rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.357004 | 0.363295 | 0.00629166 | 1.76235% | 1.3167 | 8/0/2 | [0.00336061, 0.00900525] |
| nanning | 2.00x | fixed-denominator missed bags | COMPLETE_FROZEN_PAIRED_SEEDS | 36658.5 | 36299.8 | -358.7 | -0.978491% | -1.3167 | 8/0/2 | [-512.205, -194] |
| nanning | 2.00x | fixed-denominator missed rate | COMPLETE_FROZEN_PAIRED_SEEDS | 0.642996 | 0.636705 | -0.00629166 | -0.978491% | -1.3167 | 8/0/2 | [-0.00896303, -0.00341156] |
| nanning | 2.00x | all-population tardiness sum (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 8.84523e+08 | 5.78124e+08 | -3.06399e+08 | -34.64% | -5.5816 | 10/0/0 | [-3.39302e+08, -2.7472e+08] |
| nanning | 2.00x | all-population tardiness mean (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 15514.7 | 10140.4 | -5374.28 | -34.64% | -5.5816 | 10/0/0 | [-5942.67, -4816.93] |
| nanning | 2.00x | all-population tardiness P95 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 34206.5 | 33130.7 | -1075.77 | -3.14494% | -0.115926 | 6/0/4 | [-6520.71, 4218.61] |
| nanning | 2.00x | all-population tardiness P99 (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 48183.9 | 48093.1 | -90.7888 | -0.188421% | -0.0151997 | 6/0/4 | [-3500.62, 3439.09] |
| nanning | 2.00x | all-population tardiness max (s) | COMPLETE_FROZEN_PAIRED_SEEDS | 56066 | 58621.1 | 2555.1 | 4.55731% | 0.968407 | 1/0/9 | [1027.27, 4083.66] |
| nanning | 2.00x | time to 90% completion (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 2.00x | time to 95% completion (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 2.00x | time to 99% completion (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 2.00x | total raw-bag backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.12752e+09 | 8.20363e+08 | -3.07161e+08 | -27.2421% | -5.52863 | 10/0/0 | [-3.39858e+08, -2.74747e+08] |
| nanning | 2.00x | total raw-bag backlog peak | COMPLETE_FROZEN_PAIRED_SEEDS | 20108.5 | 15828.1 | -4280.4 | -21.2865% | -4.05382 | 10/0/0 | [-4896.1, -3656.58] |
| nanning | 2.00x | source backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 1.32029e+08 | 1.31918e+08 | -111394 | -0.0843707% | -1.19293 | 10/0/0 | [-166720, -59383.4] |
| nanning | 2.00x | network backlog area (bag-s) | COMPLETE_FROZEN_PAIRED_SEEDS | 9.95495e+08 | 6.88445e+08 | -3.0705e+08 | -30.8439% | -5.53083 | 10/0/0 | [-3.39367e+08, -2.74749e+08] |
| nanning | 2.00x | 1x full-population mean THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 2.00x | 1x full-population P95 THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 2.00x | 1x full-population P99 THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |
| nanning | 2.00x | 1x full-population max THT (s) | N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED | N/M | N/M | N/M | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M (N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE) | N/M | N/M |

## Fixed-fault scope

Status: `BLOCKED_N_M_COMMON_EXECUTOR_FACTORIAL_FAULT_PREPARATION_NOT_AVAILABLE`.

The existing map-specific fault paths change reachability, admission and structural-value artifacts. They cannot be reused here while preserving the two-arm stochastic-input-only contrast, so no fault number or dynamic-recovery claim is fabricated.

## Interpretation boundary

These intervals quantify robustness of the frozen P0D0/P1D1 contrast. They do not convert a common-executor adaptation into a Feng-native result and do not authorize cross-protocol ranking.
