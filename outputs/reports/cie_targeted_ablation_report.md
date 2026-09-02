# CIE targeted 2× ablation audit

Mandatory cells: **12/12** executed, **9** integrity-admissible; conditional `FULL_MINUS_WC`: **0/2**; figure: `WRITTEN`.

All registered arms were enumerated mechanically on both maps. No arm was selected, promoted, or removed from observed outcomes. Missing cells remain `NA`; no value is interpolated.

`FULL_MINUS_WC` was pre-specified and frozen before result inspection as conditional on at least 100 wc counterfactual raw-argmin changes. The separate activation census recorded zero wc opportunities, so its missing cells are an intentional dormant-mechanism stop, not failed runs.

The 2× THT columns are always `NA` under the frozen protocol. Business outcomes use the complete fixed raw-bag denominator, including incomplete bags through fixed-horizon tardiness lower bounds.

Activation counters that compare pre-feasibility raw scorer argmins are diagnostics only. They are **not final-action changes** and are not used by this aggregator to rank or select arms.

Executed cells that fail an integrity gate remain visible with their fixed-denominator diagnostic outcomes, but their paired effects are `NA` and they are excluded from paper-admissible comparisons.

## Cell audit

| map | arm | status | completed | on-time | missed | tardiness mean (s) | backlog area (bag-s) |
|---|---|---|---:|---:|---:|---:|---:|
| map2 | FULL_S4 | COMPLETE | 57012 | 56875 | 137 | 1.40865 | 1.44729e+08 |
| map2 | H_ONLY_SERVICE_AWARE | COMPLETE | 57012 | 56186 | 826 | 8.41772 | 1.49954e+08 |
| map2 | FULL_MINUS_Q | COMPLETE | 57012 | 56929 | 83 | 0.795739 | 1.44281e+08 |
| map2 | FULL_MINUS_I | COMPLETE | 57012 | 56221 | 791 | 11.0912 | 1.50282e+08 |
| map2 | FULL_MINUS_WS | COMPLETE | 57012 | 56884 | 128 | 1.29012 | 1.44773e+08 |
| map2 | H_PLUS_Q_PLUS_I | COMPLETE | 57012 | 56884 | 128 | 1.29012 | 1.44773e+08 |
| map2 | FULL_MINUS_WC | MISSING_CELL | NA | NA | NA | NA | NA |
| nanning | FULL_S4 | COMPLETE | 57012 | 20963 | 36049 | 9419.51 | 7.77998e+08 |
| nanning | H_ONLY_SERVICE_AWARE | COMPLETE | 57012 | 20334 | 36678 | 9402.39 | 7.82179e+08 |
| nanning | FULL_MINUS_Q | FAILED_EXECUTION_INTEGRITY | 55925 | 21044 | 35968 | 10265.4 | 8.25377e+08 |
| nanning | FULL_MINUS_I | COMPLETE | 57012 | 20466 | 36546 | 9297.75 | 7.7453e+08 |
| nanning | FULL_MINUS_WS | FAILED_EXECUTION_INTEGRITY | 56059 | 20990 | 36022 | 10182.3 | 8.2148e+08 |
| nanning | H_PLUS_Q_PLUS_I | FAILED_EXECUTION_INTEGRITY | 56059 | 20990 | 36022 | 10182.3 | 8.2148e+08 |
| nanning | FULL_MINUS_WC | MISSING_CELL | NA | NA | NA | NA | NA |

## Status counts

Cell status: `COMPLETE`=9, `FAILED_EXECUTION_INTEGRITY`=3, `MISSING_CELL`=2.

Paired metric status: `COMPLETE`=91, `MISSING_OR_INVALID_ARM`=65, `SELF_REFERENCE`=26.

Every reported difference is `arm − FULL_S4` within the same map, binary, workload and fixed-population protocol. A raw sign is not a significance claim.

Backlog area is the fixed-horizon corrected view. The run table preserves the legacy value and method; an incomplete legacy tail that cannot be reconstructed exactly is reported as N/M for that metric only.

## Failed integrity gates

| map | arm | failed gates | interpretation |
|---|---|---|---|
| nanning | FULL_MINUS_Q | merge_grant_active_bijection | diagnostic outcomes retained; paired effect excluded |
| nanning | FULL_MINUS_WS | merge_grant_active_bijection | diagnostic outcomes retained; paired effect excluded |
| nanning | H_PLUS_Q_PLUS_I | merge_grant_active_bijection | diagnostic outcomes retained; paired effect excluded |
