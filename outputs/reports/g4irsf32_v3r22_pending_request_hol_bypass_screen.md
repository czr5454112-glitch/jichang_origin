# G4IRSF32 V3R22 pending-request HOL-bypass core screen

Status: `NO_GO_V3R22_PENDING_REQUEST_HOL_BYPASS`.

Primary comparison: `candidate_a_hol_bypass / off`. Candidate A is attribution-only.

| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |
|---|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 1.031 | 1.001 | 12.667 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 0.997 | 0.998 | 18.667 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 1.029 | 1.001 | 12.333 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | 0.931 | 0.979 | 35.500 | FAIL |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | 0.929 | 0.979 | 35.500 | FAIL |
| g4irsf32_s2_nanning_2x_stable_2p5 | 1.021 | 0.991 | 45.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 0.996 | 0.990 | 50.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 1.021 | 0.990 | 45.000 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | 0.998 | 0.988 | 64.000 | FAIL |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | 0.997 | 0.988 | 61.000 | FAIL |

## Failed core gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: no_new_starvation_threshold_crossings, core_resources_within_1p10, nanning_target_p95_improves_2pct, nanning_whole_p99_regression_at_most_1pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: no_new_starvation_threshold_crossings, core_resources_within_1p10, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, core_resources_within_1p10, nanning_target_p95_improves_2pct, nanning_whole_p99_regression_at_most_1pct
- `g4irsf32_s2_map2_1x_stable_2p5`: no_new_starvation_threshold_crossings, core_resources_within_1p10
- `g4irsf32_s2_map2_1x_fault_sentinel_single_1`: no_new_starvation_threshold_crossings, core_resources_within_1p10
- `g4irsf32_s2_nanning_2x_stable_2p5`: no_new_starvation_threshold_crossings, core_resources_within_1p10, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: no_new_starvation_threshold_crossings, core_resources_within_1p10, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, core_resources_within_1p10, nanning_target_p95_improves_2pct
- `g4irsf32_s2_map2_2x_stable_2p5`: no_new_starvation_threshold_crossings, core_resources_within_1p10
- `g4irsf32_s2_map2_2x_fault_sentinel_single_1`: no_new_starvation_threshold_crossings, core_resources_within_1p10

## Decision

Pending-request HOL bypass is NO-GO; Stage 3 remains blocked.

Stage 3 authorized: `false`.

Failed campaign gates: all_nanning_core_gates, all_map2_core_gates
