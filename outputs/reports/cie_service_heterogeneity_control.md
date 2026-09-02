# CIE potential factorial and adaptation decomposition

## Evidence status

- Executed input runs discovered: **8**; status COMPLETE: **8**.
- Verified full-population timing runs: **7**.
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
| map2 | 1 | population latency mean (s) | COMPLETE | 714.963 | 609.302 | 697.982 | 629.272 | -87.1861 | 1.49483 | 36.9508 |
| map2 | 1 | population latency P95 (s) | COMPLETE | 4718.85 | 3770.8 | 4573.66 | 3916.6 | -802.556 | 0.30675 | 290.986 |
| map2 | 1 | population latency P99 (s) | COMPLETE | 5923.53 | 5772.2 | 5754.59 | 5546.99 | -179.466 | -197.076 | -56.2725 |
| map2 | 1 | population latency max (s) | COMPLETE | 6355.6 | 6110.35 | 6130 | 5865.25 | -255 | -235.35 | -19.5 |
| map2 | 1 | fixed-denominator on-time raw bags | COMPLETE | 28117 | 28370 | 28153 | 28317 | 208.5 | -8.5 | -89 |
| map2 | 1 | fixed-denominator on-time rate | COMPLETE | 0.986354 | 0.995229 | 0.987617 | 0.99337 | 0.00731425 | -0.000298183 | -0.00312215 |
| map2 | 1 | fixed-denominator missed raw bags | COMPLETE | 389 | 136 | 353 | 189 | -208.5 | 8.5 | 89 |
| map2 | 1 | fixed-denominator missed rate | COMPLETE | 0.0136462 | 0.00477093 | 0.0123834 | 0.00663018 | -0.00731425 | 0.000298183 | 0.00312215 |
| map2 | 1 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 279094 | 71691 | 283805 | 165001 | -163104 | 49009.9 | 88599.4 |
| map2 | 1 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 9.79072 | 2.51495 | 9.95596 | 5.78828 | -5.72173 | 1.71928 | 3.1081 |
| map2 | 1 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 208.993 | 0 | 146.946 | 0 | -177.97 | -31.0237 | 62.0475 |
| map2 | 1 | fixed-horizon all-population tardiness max (s) | COMPLETE | 3046.65 | 2968.65 | 2930 | 2771.2 | -118.4 | -157.05 | -80.8 |
| map2 | 1 | time to 90% completion from first arrival (s) | COMPLETE | 63258.7 | 63143.8 | 63229.4 | 63161.8 | -91.25 | -5.65 | 47.3 |
| map2 | 1 | time to 95% completion from first arrival (s) | COMPLETE | 67299.2 | 67299.2 | 67299.2 | 67299.2 | 0 | 0 | 0 |
| map2 | 1 | time to 99% completion from first arrival (s) | COMPLETE | 71140.4 | 71129.6 | 71140.4 | 71129.6 | -10.8 | 0 | 0 |
| map2 | 1 | raw-bag total backlog area (bag-s) | COMPLETE | 7.72086e+07 | 7.51769e+07 | 7.68574e+07 | 7.55927e+07 | -1.64814e+06 | 32324.4 | 766951 |
| map2 | 1 | raw-bag total backlog peak | COMPLETE | 2536 | 2471 | 2518 | 2489 | -47 | 0 | 36 |
| map2 | 1 | raw-bag total backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog area (bag-s) | COMPLETE | 6.68735e+07 | 6.68735e+07 | 6.68735e+07 | 6.68735e+07 | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog peak | COMPLETE | 2193 | 2193 | 2193 | 2193 | 0 | 0 | 0 |
| map2 | 1 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | raw-bag network backlog area (bag-s) | COMPLETE | 1.0335e+07 | 8.30341e+06 | 9.98388e+06 | 8.71921e+06 | -1.64814e+06 | 32324.5 | 766951 |
| map2 | 1 | raw-bag network backlog peak | COMPLETE | 829 | 642 | 803 | 675 | -157.5 | 3.5 | 59 |
| map2 | 1 | raw-bag network backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| map2 | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | COMPLETE | 6441 | 5527 | 2948 | 3326 | -268 | -2847 | 1292 |
| map2 | 1 | wall time (s) | COMPLETE | 33.6451 | 36.9048 | 33.08 | 38.7149 | 4.44733 | 0.622518 | 2.37527 |
| map2 | 1 | CPU time (s) | COMPLETE | 32.8594 | 35.75 | 32.3906 | 37.6094 | 4.05469 | 0.695312 | 2.32812 |
| map2 | 2 | completed segments | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | completed raw bags | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag completion rate | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | population latency mean (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | population latency P95 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | population latency P99 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | population latency max (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-denominator on-time raw bags | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-denominator on-time rate | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-denominator missed raw bags | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-denominator missed rate | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness sum (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness mean (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness P95 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness P99 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness max (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | time to 90% completion from first arrival (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | time to 95% completion from first arrival (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | time to 99% completion from first arrival (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag total backlog area (bag-s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag total backlog peak | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag total backlog at horizon end | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag source backlog area (bag-s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag source backlog peak | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag source backlog at horizon end | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag network backlog area (bag-s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag network backlog peak | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | raw-bag network backlog at horizon end | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | wall time (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| map2 | 2 | CPU time (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 1 | completed segments | COMPLETE | 39047 | 43603 | 43603 | 43603 | 2278 | 2278 | -4556 |
| nanning | 1 | completed raw bags | COMPLETE | 24107 | 28506 | 28506 | 28506 | 2199.5 | 2199.5 | -4399 |
| nanning | 1 | raw-bag completion rate | COMPLETE | 0.845682 | 1 | 1 | 1 | 0.0771592 | 0.0771592 | -0.154318 |
| nanning | 1 | population latency mean (s) | METRIC_NOT_AVAILABLE_FULL_POPULATION_REQUIRED | — | 9296.63 | 9315 | 8850.44 | — | — | — |
| nanning | 1 | population latency P95 (s) | METRIC_NOT_AVAILABLE_FULL_POPULATION_REQUIRED | — | 34536.7 | 36276.3 | 34110.6 | — | — | — |
| nanning | 1 | population latency P99 (s) | METRIC_NOT_AVAILABLE_FULL_POPULATION_REQUIRED | — | 38595.5 | 40548.6 | 38334.6 | — | — | — |
| nanning | 1 | population latency max (s) | METRIC_NOT_AVAILABLE_FULL_POPULATION_REQUIRED | — | 42520.4 | 44677 | 41779 | — | — | — |
| nanning | 1 | fixed-denominator on-time raw bags | COMPLETE | 10212 | 10326 | 10532 | 10575 | 78.5 | 284.5 | -71 |
| nanning | 1 | fixed-denominator on-time rate | COMPLETE | 0.35824 | 0.36224 | 0.369466 | 0.370975 | 0.00275381 | 0.00998036 | -0.0024907 |
| nanning | 1 | fixed-denominator missed raw bags | COMPLETE | 18294 | 18180 | 17974 | 17931 | -78.5 | -284.5 | 71 |
| nanning | 1 | fixed-denominator missed rate | COMPLETE | 0.64176 | 0.63776 | 0.630534 | 0.629025 | -0.00275381 | -0.00998036 | 0.0024907 |
| nanning | 1 | fixed-horizon all-population tardiness sum (s) | COMPLETE | 4.15838e+08 | 2.64982e+08 | 2.68236e+08 | 2.56738e+08 | -8.11775e+07 | -7.79231e+07 | 1.39358e+08 |
| nanning | 1 | fixed-horizon all-population tardiness mean (s) | COMPLETE | 14587.7 | 9295.65 | 9409.82 | 9006.44 | -2847.73 | -2733.57 | 4888.71 |
| nanning | 1 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | 44559 | 39402.7 | 39478.1 | 38434.5 | -3099.97 | -3024.58 | 4112.71 |
| nanning | 1 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | 67059 | 55784.4 | 54719.7 | 54425.1 | -5784.56 | -6849.34 | 10980 |
| nanning | 1 | fixed-horizon all-population tardiness max (s) | COMPLETE | 71559 | 60006.3 | 58950.6 | 58702.9 | -5900.17 | -6955.92 | 11305 |
| nanning | 1 | time to 90% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/off) | — | 79556.5 | 78780.8 | 78230.2 | — | — | — |
| nanning | 1 | time to 95% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/off) | — | 84559.8 | 83581.2 | 83570.3 | — | — | — |
| nanning | 1 | time to 99% completion from first arrival (s) | METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED (ff/off) | — | 88432.7 | 88184.3 | 88141.2 | — | — | — |
| nanning | 1 | raw-bag total backlog area (bag-s) | COMPLETE | 5.38124e+08 | 3.87389e+08 | 3.89796e+08 | 3.7775e+08 | -8.13902e+07 | -7.89831e+07 | 1.38688e+08 |
| nanning | 1 | raw-bag total backlog peak | COMPLETE | 9606 | 7514 | 7620 | 7388 | -1162 | -1056 | 1860 |
| nanning | 1 | raw-bag total backlog at horizon end | COMPLETE | 4399 | 0 | 0 | 0 | -2199.5 | -2199.5 | 4399 |
| nanning | 1 | raw-bag source backlog area (bag-s) | COMPLETE | 1.87679e+08 | 1.87673e+08 | 1.87672e+08 | 1.87672e+08 | -2615.45 | -3722.73 | 6774.54 |
| nanning | 1 | raw-bag source backlog peak | COMPLETE | 3477 | 3477 | 3477 | 3477 | 0 | 0 | 0 |
| nanning | 1 | raw-bag source backlog at horizon end | COMPLETE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nanning | 1 | raw-bag network backlog area (bag-s) | COMPLETE | 3.50445e+08 | 1.99717e+08 | 2.02125e+08 | 1.90078e+08 | -8.13876e+07 | -7.89794e+07 | 1.38682e+08 |
| nanning | 1 | raw-bag network backlog peak | COMPLETE | 7631 | 4927 | 5205 | 4905 | -1502 | -1224 | 2404 |
| nanning | 1 | raw-bag network backlog at horizon end | COMPLETE | 4399 | 0 | 0 | 0 | -2199.5 | -2199.5 | 4399 |
| nanning | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | COMPLETE | 169100 | 188404 | 223379 | 156815 | -23630 | 11345 | -85868 |
| nanning | 1 | wall time (s) | COMPLETE | 425.839 | 254.46 | 254.749 | 244.403 | -90.8619 | -90.5732 | 161.033 |
| nanning | 1 | CPU time (s) | COMPLETE | 415.469 | 248.734 | 247.438 | 237.469 | -88.3516 | -89.6484 | 156.766 |
| nanning | 2 | completed segments | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | completed raw bags | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag completion rate | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | population latency mean (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | population latency P95 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | population latency P99 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | population latency max (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-denominator on-time raw bags | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-denominator on-time rate | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-denominator missed raw bags | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-denominator missed rate | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness sum (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness mean (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness P95 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness P99 (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness max (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | time to 90% completion from first arrival (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | time to 95% completion from first arrival (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | time to 99% completion from first arrival (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag total backlog area (bag-s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag total backlog peak | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag total backlog at horizon end | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag source backlog area (bag-s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag source backlog peak | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag source backlog at horizon end | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag network backlog area (bag-s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag network backlog peak | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | raw-bag network backlog at horizon end | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | wall time (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |
| nanning | 2 | CPU time (s) | MISSING_CELLS (ff/off;sa/off;ff/full;sa/full) | — | — | — | — | — | — | — |

## CIE-DH common-executor adaptation decomposition

This is an H_FF versus H_SA adaptation contrast in the common C++ executor. It is **not native Feng DH**, is not merged into the S4 factorial, and is not used for a cross-protocol ranking.

| map | scale | metric | status | H_FF/full | H_SA/full | H_SA − H_FF |
|---|---:|---|---|---:|---:|---:|
| map2 | 1 | completed segments | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | completed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag completion rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | population latency mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | population latency P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | population latency P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | population latency max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-denominator on-time raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-denominator on-time rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-denominator missed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-denominator missed rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-horizon all-population tardiness sum (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-horizon all-population tardiness mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-horizon all-population tardiness P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-horizon all-population tardiness P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | fixed-horizon all-population tardiness max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | time to 90% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | time to 95% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | time to 99% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag total backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag total backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag total backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag source backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag source backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag source backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag network backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag network backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | raw-bag network backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | wall time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 1 | CPU time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | completed segments | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | completed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag completion rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | population latency mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | population latency P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | population latency P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | population latency max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-denominator on-time raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-denominator on-time rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-denominator missed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-denominator missed rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness sum (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | fixed-horizon all-population tardiness max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | time to 90% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | time to 95% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | time to 99% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag total backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag total backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag total backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag source backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag source backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag source backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag network backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag network backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | raw-bag network backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | wall time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| map2 | 2 | CPU time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | completed segments | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | completed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag completion rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | population latency mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | population latency P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | population latency P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | population latency max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-denominator on-time raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-denominator on-time rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-denominator missed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-denominator missed rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-horizon all-population tardiness sum (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-horizon all-population tardiness mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-horizon all-population tardiness P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-horizon all-population tardiness P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | fixed-horizon all-population tardiness max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | time to 90% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | time to 95% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | time to 99% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag total backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag total backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag total backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag source backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag source backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag source backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag network backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag network backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | raw-bag network backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | pre-feasibility component raw-argmin counterfactual changes (total) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | wall time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 1 | CPU time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | completed segments | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | completed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag completion rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | population latency mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | population latency P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | population latency P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | population latency max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-denominator on-time raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-denominator on-time rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-denominator missed raw bags | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-denominator missed rate | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness sum (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness mean (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness P95 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness P99 (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | fixed-horizon all-population tardiness max (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | time to 90% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | time to 95% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | time to 99% completion from first arrival (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag total backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag total backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag total backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag source backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag source backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag source backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag network backlog area (bag-s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag network backlog peak | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | raw-bag network backlog at horizon end | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | pre-feasibility component raw-argmin counterfactual changes (total) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | wall time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |
| nanning | 2 | CPU time (s) | MISSING_CELLS (ff/full;sa/full) | — | — | — |

## Interpretation boundary

Missing, duplicate, contract-mismatched, incomplete-population, and unreported cells remain explicit in the tables. Legacy incomplete backlog areas are used only after an exact fixed-horizon tail correction; an unrecoverable tail is N/M. The long table preserves the legacy area and correction method. No value is imputed, no survivor/common-cohort latency is substituted, and runtime cost is not treated as an algorithm-quality victory metric.
