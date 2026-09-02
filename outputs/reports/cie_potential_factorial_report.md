# CIE potential factorial and adaptation decomposition

## Evidence status

- Executed input runs discovered: **24**; status COMPLETE: **24**.
- Verified full-population timing runs: **12**.
- Figure: `WRITTEN`.
- Population latency is reported only for integrity-passing, fully completed raw-bag populations with an explicit non-survivor timing contract; the 2× THT gate remains N/A.
- Fixed-denominator business outcomes retain incomplete bags and are comparable at 1× and 2×. Unreached 90/95/99% completion targets stay blank with an explicit status.
- Component raw-argmin changes are pre-feasibility counterfactual scorer diagnostics, not final-action changes.
- Effect signs are raw differences, not claims of statistical significance. For completion, higher is preferred; for latency, lower is preferred; wall/CPU are compute cost only.

## S4 neutral-FIFO 2×2 potential × dynamic factorial

`potential main = mean(H_SA) - mean(H_FF)`; `dynamic main = mean(full) - mean(off)`; interaction is the difference-in-differences.

| map | scale | metric | status | H_FF/off | H_SA/off | H_FF/full | H_SA/full | potential main | dynamic main | interaction |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| map2 | 1 | completed segments | COMPLETE | 43603 | 43603 | 43603 | 43603 | 0 | 0 | 0 |
| map2 | 1 | completed raw bags | COMPLETE | 28506 | 28506 | 28506 | 28506 | 0 | 0 | 0 |
| map2 | 1 | raw-bag completion rate | COMPLETE | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| map2 | 1 | population latency mean (s) | COMPLETE | 211.249 | 210.767 | 211.026 | 210.546 | -0.480827 | -0.222465 | 0.00192591 |
| map2 | 1 | population latency P95 (s) | COMPLETE | 247.802 | 247.202 | 247.602 | 247.202 | -0.5 | -0.1 | 0.2 |
| map2 | 1 | population latency P99 (s) | COMPLETE | 262.002 | 259.202 | 260.802 | 254.002 | -4.8 | -3.2 | -4 |
| map2 | 1 | population latency max (s) | COMPLETE | 298.202 | 292.602 | 292.602 | 278.202 | -10 | -10 | -8.8 |
| map2 | 1 | fixed-denominator on-time raw bags | COMPLETE | 28506 | 28506 | 28506 | 28506 | 0 | 0 | 0 |
| map2 | 1 | fixed-denominator on-time rate | COMPLETE | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| map2 | 1 | fixed-denominator missed raw bags | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-denominator missed rate | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness max (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | time to 90% completion from first arrival (s) | COMPLETE | 62931.6 | 62931.6 | 62931.6 | 62931.6 | 0 | 0 | 0 |
| map2 | 1 | time to 95% completion from first arrival (s) | COMPLETE | 67287.2 | 67287.2 | 67287.2 | 67287.2 | 0 | 0 | 0 |
| map2 | 1 | time to 99% completion from first arrival (s) | COMPLETE | 71125.8 | 71121.6 | 71125.8 | 71121.6 | -4.2 | 0 | 0 |
| map2 | 1 | raw-bag total backlog area (bag-s) | COMPLETE | 7.21311e+07 | 7.21231e+07 | 7.21277e+07 | 7.21261e+07 | -4813.38 | -253.525 | 6393.95 |
| map2 | 1 | raw-bag total backlog peak | COMPLETE | 2368 | 2368 | 2368 | 2368 | 0 | 0 | 0 |
| map2 | 1 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog area (bag-s) | COMPLETE | 6.68735e+07 | 6.68735e+07 | 6.68735e+07 | 6.68735e+07 | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog peak | COMPLETE | 2193 | 2193 | 2193 | 2193 | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | raw-bag network backlog area (bag-s) | COMPLETE | 5.25759e+06 | 5.24958e+06 | 5.25414e+06 | 5.25253e+06 | -4813.37 | -253.525 | 6393.95 |
| map2 | 1 | raw-bag network backlog peak | COMPLETE | 236 | 236 | 236 | 236 | 0 | 0 | 0 |
| map2 | 1 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | COMPLETE | 1297 | 1224 | 1203 | 810 | -233 | -254 | -320 |
| map2 | 1 | wall time (s) | COMPLETE | 20.1515 | 19.8786 | 19.8148 | 19.7234 | -0.182191 | -0.246007 | 0.181427 |
| map2 | 1 | CPU time (s) | COMPLETE | 19.4688 | 19.4531 | 19.3125 | 19.1562 | -0.0859375 | -0.226562 | -0.140625 |
| map2 | 2 | completed segments | COMPLETE | 87206 | 87206 | 87206 | 87206 | 0 | 0 | 0 |
| map2 | 2 | completed raw bags | COMPLETE | 57012 | 57012 | 57012 | 57012 | 0 | 0 | 0 |
| map2 | 2 | raw-bag completion rate | COMPLETE | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| map2 | 2 | population latency mean (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| map2 | 2 | population latency P95 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| map2 | 2 | population latency P99 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| map2 | 2 | population latency max (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| map2 | 2 | fixed-denominator on-time raw bags | COMPLETE | 55641 | 56186 | 55849 | 56872 | 784 | 447 | 478 |
| map2 | 2 | fixed-denominator on-time rate | COMPLETE | 0.975952 | 0.985512 | 0.979601 | 0.997544 | 0.0137515 | 0.00784045 | 0.0083842 |
| map2 | 2 | fixed-denominator missed raw bags | COMPLETE | 1371 | 826 | 1163 | 140 | -784 | -447 | -478 |
| map2 | 2 | fixed-denominator missed rate | COMPLETE | 0.0240476 | 0.0144882 | 0.0203992 | 0.00245562 | -0.0137515 | -0.00784045 | -0.0083842 |
| map2 | 2 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 1.05431e+06 | 479828 | 940632 | 80813.4 | -717151 | -256347 | -285336 |
| map2 | 2 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 18.4928 | 8.41626 | 16.4988 | 1.41748 | -12.5789 | -4.49636 | -5.00484 |
| map2 | 2 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 2 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 709.882 | 213.408 | 596.21 | 0 | -546.342 | -163.54 | -99.7362 |
| map2 | 2 | fixed-horizon all-population tardiness max (s) | COMPLETE | 3513.57 | 3422.85 | 3346.02 | 1813.75 | -811.493 | -888.322 | -1441.55 |
| map2 | 2 | time to 90% completion from first arrival (s) | COMPLETE | 64388.8 | 64388.8 | 64388.8 | 64388.4 | -0.20052 | -0.20052 | -0.40104 |
| map2 | 2 | time to 95% completion from first arrival (s) | COMPLETE | 67648.3 | 67647.3 | 67648.3 | 67648.3 | -0.5 | 0.5 | 1 |
| map2 | 2 | time to 99% completion from first arrival (s) | COMPLETE | 71585.4 | 71582.4 | 71584.2 | 71581.4 | -2.93343 | -1.13334 | 0.26667 |
| map2 | 2 | raw-bag total backlog area (bag-s) | COMPLETE | 1.53429e+08 | 1.49936e+08 | 1.52412e+08 | 1.44732e+08 | -5.58702e+06 | -3.1106e+06 | -4.18714e+06 |
| map2 | 2 | raw-bag total backlog peak | COMPLETE | 4788 | 4685 | 4760 | 4544 | -159.5 | -84.5 | -113 |
| map2 | 2 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 2 | raw-bag source backlog area (bag-s) | COMPLETE | 1.28401e+08 | 1.28401e+08 | 1.28401e+08 | 1.28401e+08 | 0 | 0 | 0 |
| map2 | 2 | raw-bag source backlog peak | COMPLETE | 4128 | 4128 | 4128 | 4128 | 0 | 0 | 0 |
| map2 | 2 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 2 | raw-bag network backlog area (bag-s) | COMPLETE | 2.50278e+07 | 2.15343e+07 | 2.40107e+07 | 1.63302e+07 | -5.58702e+06 | -3.1106e+06 | -4.18714e+06 |
| map2 | 2 | raw-bag network backlog peak | COMPLETE | 2644 | 2390 | 2607 | 1540 | -660.5 | -443.5 | -813 |
| map2 | 2 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | COMPLETE | 11572 | 12099 | 8366 | 5897 | -971 | -4704 | -2996 |
| map2 | 2 | wall time (s) | COMPLETE | 59.3342 | 57.5973 | 61.0998 | 51.7264 | -5.55518 | -2.05267 | -7.63655 |
| map2 | 2 | CPU time (s) | COMPLETE | 58.375 | 55.8906 | 59.625 | 50.5156 | -5.79688 | -2.0625 | -6.625 |
| nanning | 1 | completed segments | COMPLETE | 43603 | 43603 | 43603 | 43603 | 0 | 0 | 0 |
| nanning | 1 | completed raw bags | COMPLETE | 28506 | 28506 | 28506 | 28506 | 0 | 0 | 0 |
| nanning | 1 | raw-bag completion rate | COMPLETE | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| nanning | 1 | population latency mean (s) | COMPLETE | 293.479 | 281.724 | 287.536 | 282.933 | -8.17925 | -2.36701 | 7.15266 |
| nanning | 1 | population latency P95 (s) | COMPLETE | 508.267 | 473.152 | 486.77 | 475.339 | -23.273 | -9.6555 | 23.684 |
| nanning | 1 | population latency P99 (s) | COMPLETE | 592.093 | 552.369 | 562.851 | 553.466 | -24.5542 | -14.0726 | 30.3385 |
| nanning | 1 | population latency max (s) | COMPLETE | 929.995 | 808.585 | 822.145 | 812.698 | -65.4285 | -51.8685 | 111.963 |
| nanning | 1 | fixed-denominator on-time raw bags | COMPLETE | 18464 | 18476 | 18469 | 18476 | 9.5 | 2.5 | -5 |
| nanning | 1 | fixed-denominator on-time rate | COMPLETE | 0.647723 | 0.648144 | 0.647899 | 0.648144 | 0.000333263 | 8.77008e-05 | -0.000175402 |
| nanning | 1 | fixed-denominator missed raw bags | COMPLETE | 10042 | 10030 | 10037 | 10030 | -9.5 | -2.5 | 5 |
| nanning | 1 | fixed-denominator missed rate | COMPLETE | 0.352277 | 0.351856 | 0.352101 | 0.351856 | -0.000333263 | -8.77008e-05 | 0.000175402 |
| nanning | 1 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 9.112e+07 | 9.10249e+07 | 9.1073e+07 | 9.10435e+07 | -62291.8 | -14206.8 | 65506.6 |
| nanning | 1 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 3196.52 | 3193.18 | 3194.87 | 3193.84 | -2.18522 | -0.49838 | 2.298 |
| nanning | 1 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 27473.8 | 27465.2 | 27474.5 | 27468.4 | -7.3625 | 2.0045 | 2.499 |
| nanning | 1 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 44639.2 | 44636 | 44639.3 | 44637.3 | -2.6126 | 0.7142 | 1.1084 |
| nanning | 1 | fixed-horizon all-population tardiness max (s) | COMPLETE | 48875.1 | 48770.1 | 48778.5 | 48771.2 | -56.142 | -47.715 | 97.728 |
| nanning | 1 | time to 90% completion from first arrival (s) | COMPLETE | 68136.2 | 68124 | 68131.5 | 68122.2 | -10.702 | -3.246 | 2.908 |
| nanning | 1 | time to 95% completion from first arrival (s) | COMPLETE | 71970.5 | 71968.7 | 71970.5 | 71970.5 | -0.904 | 0.904 | 1.808 |
| nanning | 1 | time to 99% completion from first arrival (s) | COMPLETE | 75442.5 | 75440.7 | 75442.5 | 75442 | -1.164 | 0.644 | 1.288 |
| nanning | 1 | raw-bag total backlog area (bag-s) | COMPLETE | 1.93373e+08 | 1.93096e+08 | 1.93226e+08 | 1.93132e+08 | -185390 | -55782.2 | 181642 |
| nanning | 1 | raw-bag total backlog peak | COMPLETE | 3606 | 3600 | 3605 | 3601 | -5 | 0 | 2 |
| nanning | 1 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nanning | 1 | raw-bag source backlog area (bag-s) | COMPLETE | 1.87667e+08 | 1.87667e+08 | 1.87667e+08 | 1.87667e+08 | 7.7725 | 5.5895 | 0.621 |
| nanning | 1 | raw-bag source backlog peak | COMPLETE | 3477 | 3477 | 3477 | 3477 | 0 | 0 | 0 |
| nanning | 1 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nanning | 1 | raw-bag network backlog area (bag-s) | COMPLETE | 5.70522e+06 | 5.429e+06 | 5.55861e+06 | 5.46404e+06 | -185398 | -55787.8 | 181642 |
| nanning | 1 | raw-bag network backlog peak | COMPLETE | 166 | 159 | 161 | 161 | -3.5 | -1.5 | 7 |
| nanning | 1 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nanning | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | COMPLETE | 68993 | 57077 | 41576 | 46264 | -3614 | -19115 | 16604 |
| nanning | 1 | wall time (s) | COMPLETE | 42.3933 | 37.3898 | 39.9428 | 37.7492 | -3.59851 | -1.04555 | 2.80982 |
| nanning | 1 | CPU time (s) | COMPLETE | 40.8906 | 36.4062 | 39.1094 | 36.8438 | -3.375 | -0.671875 | 2.21875 |
| nanning | 2 | completed segments | COMPLETE | 77602 | 87206 | 87206 | 87206 | 4802 | 4802 | -9604 |
| nanning | 2 | completed raw bags | COMPLETE | 47864 | 57012 | 57012 | 57012 | 4574 | 4574 | -9148 |
| nanning | 2 | raw-bag completion rate | COMPLETE | 0.839543 | 1 | 1 | 1 | 0.0802287 | 0.0802287 | -0.160457 |
| nanning | 2 | population latency mean (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| nanning | 2 | population latency P95 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| nanning | 2 | population latency P99 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| nanning | 2 | population latency max (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — | — | — | — | — |
| nanning | 2 | fixed-denominator on-time raw bags | COMPLETE | 20482 | 20334 | 20910 | 20963 | -47.5 | 528.5 | 201 |
| nanning | 2 | fixed-denominator on-time rate | COMPLETE | 0.359258 | 0.356662 | 0.366765 | 0.367695 | -0.000833158 | 0.00926998 | 0.00352557 |
| nanning | 2 | fixed-denominator missed raw bags | COMPLETE | 36530 | 36678 | 36102 | 36049 | 47.5 | -528.5 | -201 |
| nanning | 2 | fixed-denominator missed rate | COMPLETE | 0.640742 | 0.643338 | 0.633235 | 0.632305 | 0.000833158 | -0.00926998 | -0.00352557 |
| nanning | 2 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 8.40569e+08 | 5.36049e+08 | 5.54349e+08 | 5.37025e+08 | -1.60922e+08 | -1.42622e+08 | 2.87196e+08 |
| nanning | 2 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 14743.7 | 9402.39 | 9723.37 | 9419.51 | -2822.6 | -2501.62 | 5037.47 |
| nanning | 2 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 31957.6 | 30137.4 | 32739 | 32344.4 | -1107.41 | 1494.21 | 1425.6 |
| nanning | 2 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 46209 | 42428.1 | 45665 | 44561.1 | -2442.4 | 794.513 | 2677.11 |
| nanning | 2 | fixed-horizon all-population tardiness max (s) | COMPLETE | 54325.3 | 52956.4 | 57100.5 | 56178.5 | -1145.44 | 2998.6 | 446.935 |
| nanning | 2 | time to 90% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/off) | — | 79952.7 | 80297.3 | 79869.5 | — | — | — |
| nanning | 2 | time to 95% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/off) | — | 84232.6 | 84532.3 | 83579.2 | — | — | — |
| nanning | 2 | time to 99% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/off) | — | 88384 | 88715.8 | 87670.9 | — | — | — |
| nanning | 2 | raw-bag total backlog area (bag-s) | COMPLETE | 1.08293e+09 | 7.82179e+08 | 7.95978e+08 | 7.77998e+08 | -1.59363e+08 | -1.45564e+08 | 2.82767e+08 |
| nanning | 2 | raw-bag total backlog peak | COMPLETE | 19189 | 15324 | 15577 | 15268 | -2087 | -1834 | 3556 |
| nanning | 2 | raw-bag total backlog at horizon end | COMPLETE | 9148 | 0 | 0 | 0 | -4574 | -4574 | 9148 |
| nanning | 2 | raw-bag source backlog area (bag-s) | COMPLETE | 1.31928e+08 | 1.31879e+08 | 1.31851e+08 | 1.31851e+08 | -24534.2 | -53028.2 | 48928.6 |
| nanning | 2 | raw-bag source backlog peak | COMPLETE | 4224 | 4224 | 4224 | 4224 | 0 | 0 | 0 |
| nanning | 2 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nanning | 2 | raw-bag network backlog area (bag-s) | COMPLETE | 9.50998e+08 | 6.503e+08 | 6.64127e+08 | 6.46148e+08 | -1.59338e+08 | -1.45511e+08 | 2.82718e+08 |
| nanning | 2 | raw-bag network backlog peak | COMPLETE | 18117 | 14040 | 14242 | 13848 | -2235.5 | -2033.5 | 3683 |
| nanning | 2 | raw-bag network backlog at horizon end | COMPLETE | 9148 | 0 | 0 | 0 | -4574 | -4574 | 9148 |
| nanning | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | COMPLETE | 264738 | 372820 | 351524 | 344109 | 50333.5 | 29037.5 | -115497 |
| nanning | 2 | wall time (s) | COMPLETE | 991.771 | 640.578 | 645.056 | 636.081 | -180.084 | -175.607 | 342.218 |
| nanning | 2 | CPU time (s) | COMPLETE | 963.188 | 623.203 | 626.781 | 619.906 | -173.43 | -169.852 | 333.109 |

## CIE-DH common-executor adaptation decomposition

This is an H_FF versus H_SA adaptation contrast in the common C++ executor. It is **not native Feng DH**, is not merged into the S4 factorial, and is not used for a cross-protocol ranking.

| map | scale | metric | status | H_FF/full | H_SA/full | H_SA − H_FF |
|---|---:|---|---|---:|---:|---:|
| map2 | 1 | completed segments | COMPLETE | 43603 | 43603 | 0 |
| map2 | 1 | completed raw bags | COMPLETE | 28506 | 28506 | 0 |
| map2 | 1 | raw-bag completion rate | COMPLETE | 1 | 1 | 0 |
| map2 | 1 | population latency mean (s) | COMPLETE | 210.884 | 210.888 | 0.00373606 |
| map2 | 1 | population latency P95 (s) | COMPLETE | 247.202 | 247.202 | 0 |
| map2 | 1 | population latency P99 (s) | COMPLETE | 256.402 | 256.402 | 0 |
| map2 | 1 | population latency max (s) | COMPLETE | 275.802 | 275.802 | 0 |
| map2 | 1 | fixed-denominator on-time raw bags | COMPLETE | 28506 | 28506 | 0 |
| map2 | 1 | fixed-denominator on-time rate | COMPLETE | 1 | 1 | 0 |
| map2 | 1 | fixed-denominator missed raw bags | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | fixed-denominator missed rate | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness max (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | time to 90% completion from first arrival (s) | COMPLETE | 62931.6 | 62931.6 | 0 |
| map2 | 1 | time to 95% completion from first arrival (s) | COMPLETE | 67287.2 | 67287.2 | 0 |
| map2 | 1 | time to 99% completion from first arrival (s) | COMPLETE | 71125.8 | 71121.6 | -4.2 |
| map2 | 1 | raw-bag total backlog area (bag-s) | COMPLETE | 7.21383e+07 | 7.21375e+07 | -703.3 |
| map2 | 1 | raw-bag total backlog peak | COMPLETE | 2368 | 2368 | 0 |
| map2 | 1 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog area (bag-s) | COMPLETE | 6.68735e+07 | 6.68735e+07 | 0 |
| map2 | 1 | raw-bag source backlog peak | COMPLETE | 2193 | 2193 | 0 |
| map2 | 1 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | raw-bag network backlog area (bag-s) | COMPLETE | 5.26471e+06 | 5.26401e+06 | -703.3 |
| map2 | 1 | raw-bag network backlog peak | COMPLETE | 237 | 237 | 0 |
| map2 | 1 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| map2 | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | METRIC_NOT_REPORTED | — | — | — |
| map2 | 1 | wall time (s) | COMPLETE | 20.3233 | 20.2523 | -0.0709656 |
| map2 | 1 | CPU time (s) | COMPLETE | 19.75 | 19.75 | 0 |
| map2 | 2 | completed segments | COMPLETE | 87206 | 87206 | 0 |
| map2 | 2 | completed raw bags | COMPLETE | 57012 | 57012 | 0 |
| map2 | 2 | raw-bag completion rate | COMPLETE | 1 | 1 | 0 |
| map2 | 2 | population latency mean (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| map2 | 2 | population latency P95 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| map2 | 2 | population latency P99 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| map2 | 2 | population latency max (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| map2 | 2 | fixed-denominator on-time raw bags | COMPLETE | 57012 | 57012 | 0 |
| map2 | 2 | fixed-denominator on-time rate | COMPLETE | 1 | 1 | 0 |
| map2 | 2 | fixed-denominator missed raw bags | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | fixed-denominator missed rate | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | fixed-horizon all-population tardiness max (s) | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | time to 90% completion from first arrival (s) | COMPLETE | 64387.4 | 64387.4 | 0 |
| map2 | 2 | time to 95% completion from first arrival (s) | COMPLETE | 67649.2 | 67651.3 | 2.06658 |
| map2 | 2 | time to 99% completion from first arrival (s) | COMPLETE | 71581.6 | 71581.6 | 0 |
| map2 | 2 | raw-bag total backlog area (bag-s) | COMPLETE | 1.45495e+08 | 1.44856e+08 | -638914 |
| map2 | 2 | raw-bag total backlog peak | COMPLETE | 4534 | 4503 | -31 |
| map2 | 2 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | raw-bag source backlog area (bag-s) | COMPLETE | 1.28401e+08 | 1.28401e+08 | 0 |
| map2 | 2 | raw-bag source backlog peak | COMPLETE | 4128 | 4128 | 0 |
| map2 | 2 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | raw-bag network backlog area (bag-s) | COMPLETE | 1.70934e+07 | 1.64544e+07 | -638914 |
| map2 | 2 | raw-bag network backlog peak | COMPLETE | 1722 | 1619 | -103 |
| map2 | 2 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| map2 | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | METRIC_NOT_REPORTED | — | — | — |
| map2 | 2 | wall time (s) | COMPLETE | 51.0019 | 49.9762 | -1.02567 |
| map2 | 2 | CPU time (s) | COMPLETE | 49.625 | 48.7188 | -0.90625 |
| nanning | 1 | completed segments | COMPLETE | 43603 | 43603 | 0 |
| nanning | 1 | completed raw bags | COMPLETE | 28506 | 28506 | 0 |
| nanning | 1 | raw-bag completion rate | COMPLETE | 1 | 1 | 0 |
| nanning | 1 | population latency mean (s) | COMPLETE | 287.263 | 280.707 | -6.55625 |
| nanning | 1 | population latency P95 (s) | COMPLETE | 484.692 | 469.978 | -14.7145 |
| nanning | 1 | population latency P99 (s) | COMPLETE | 541.424 | 525.496 | -15.9279 |
| nanning | 1 | population latency max (s) | COMPLETE | 709.115 | 794.531 | 85.416 |
| nanning | 1 | fixed-denominator on-time raw bags | COMPLETE | 18470 | 18470 | 0 |
| nanning | 1 | fixed-denominator on-time rate | COMPLETE | 0.647934 | 0.647934 | 0 |
| nanning | 1 | fixed-denominator missed raw bags | COMPLETE | 10036 | 10036 | 0 |
| nanning | 1 | fixed-denominator missed rate | COMPLETE | 0.352066 | 0.352066 | 0 |
| nanning | 1 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 9.10667e+07 | 9.10265e+07 | -40228.6 |
| nanning | 1 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 3194.65 | 3193.24 | -1.41123 |
| nanning | 1 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 27473.8 | 27466.6 | -7.214 |
| nanning | 1 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 44637.1 | 44635.9 | -1.2483 |
| nanning | 1 | fixed-horizon all-population tardiness max (s) | COMPLETE | 48770.3 | 48767 | -3.24 |
| nanning | 1 | time to 90% completion from first arrival (s) | COMPLETE | 68134.9 | 68124 | -10.857 |
| nanning | 1 | time to 95% completion from first arrival (s) | COMPLETE | 71972.4 | 71969.5 | -2.888 |
| nanning | 1 | time to 99% completion from first arrival (s) | COMPLETE | 75441.4 | 75440.7 | -0.688 |
| nanning | 1 | raw-bag total backlog area (bag-s) | COMPLETE | 1.93228e+08 | 1.93089e+08 | -138825 |
| nanning | 1 | raw-bag total backlog peak | COMPLETE | 3604 | 3602 | -2 |
| nanning | 1 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| nanning | 1 | raw-bag source backlog area (bag-s) | COMPLETE | 1.87667e+08 | 1.87667e+08 | 5.309 |
| nanning | 1 | raw-bag source backlog peak | COMPLETE | 3477 | 3477 | 0 |
| nanning | 1 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| nanning | 1 | raw-bag network backlog area (bag-s) | COMPLETE | 5.5605e+06 | 5.42167e+06 | -138831 |
| nanning | 1 | raw-bag network backlog peak | COMPLETE | 162 | 159 | -3 |
| nanning | 1 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| nanning | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | METRIC_NOT_REPORTED | — | — | — |
| nanning | 1 | wall time (s) | COMPLETE | 43.0982 | 39.6805 | -3.41768 |
| nanning | 1 | CPU time (s) | COMPLETE | 41.9688 | 38.2969 | -3.67188 |
| nanning | 2 | completed segments | COMPLETE | 79352 | 79232 | -120 |
| nanning | 2 | completed raw bags | COMPLETE | 49158 | 49038 | -120 |
| nanning | 2 | raw-bag completion rate | COMPLETE | 0.86224 | 0.860135 | -0.00210482 |
| nanning | 2 | population latency mean (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| nanning | 2 | population latency P95 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| nanning | 2 | population latency P99 (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| nanning | 2 | population latency max (s) | FORMAL_2X_TIMING_NA_BY_PROTOCOL | — | — | — |
| nanning | 2 | fixed-denominator on-time raw bags | COMPLETE | 16548 | 16525 | -23 |
| nanning | 2 | fixed-denominator on-time rate | COMPLETE | 0.290255 | 0.289851 | -0.000403424 |
| nanning | 2 | fixed-denominator missed raw bags | COMPLETE | 40464 | 40487 | 23 |
| nanning | 2 | fixed-denominator missed rate | COMPLETE | 0.709745 | 0.710149 | 0.000403424 |
| nanning | 2 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 7.8354e+08 | 7.74572e+08 | -8.96859e+06 |
| nanning | 2 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 13743.4 | 13586.1 | -157.311 |
| nanning | 2 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 48459 | 48459 | 0 |
| nanning | 2 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 62859 | 63142.5 | 283.5 |
| nanning | 2 | fixed-horizon all-population tardiness max (s) | COMPLETE | 72507.6 | 73640.6 | 1132.96 |
| nanning | 2 | time to 90% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/full;sa/full) | — | — | — |
| nanning | 2 | time to 95% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/full;sa/full) | — | — | — |
| nanning | 2 | time to 99% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag total backlog area (bag-s) | COMPLETE | 1.03513e+09 | 1.02638e+09 | -8.75199e+06 |
| nanning | 2 | raw-bag total backlog peak | COMPLETE | 19359 | 19118 | -241 |
| nanning | 2 | raw-bag total backlog at horizon end | COMPLETE | 7854 | 7974 | 120 |
| nanning | 2 | raw-bag source backlog area (bag-s) | COMPLETE | 1.31823e+08 | 1.31828e+08 | 4289.85 |
| nanning | 2 | raw-bag source backlog peak | COMPLETE | 4224 | 4224 | 0 |
| nanning | 2 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 |
| nanning | 2 | raw-bag network backlog area (bag-s) | COMPLETE | 9.03306e+08 | 8.94549e+08 | -8.75628e+06 |
| nanning | 2 | raw-bag network backlog peak | COMPLETE | 18369 | 18116 | -253 |
| nanning | 2 | raw-bag network backlog at horizon end | COMPLETE | 7854 | 7974 | 120 |
| nanning | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | METRIC_NOT_REPORTED | — | — | — |
| nanning | 2 | wall time (s) | COMPLETE | 1834.76 | 1665.07 | -169.697 |
| nanning | 2 | CPU time (s) | COMPLETE | 1777.83 | 1615.81 | -162.016 |

## Interpretation boundary

Missing, duplicate, contract-mismatched, incomplete-population, and unreported cells remain explicit in the tables. Legacy incomplete backlog areas are used only after an exact fixed-horizon tail correction; an unrecoverable tail is N/M. The long table preserves the legacy area and correction method. No value is imputed, no survivor/common-cohort latency is substituted, and runtime cost is not treated as an algorithm-quality victory metric.
