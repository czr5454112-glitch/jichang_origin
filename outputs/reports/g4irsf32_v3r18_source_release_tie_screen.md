# G4IRSF32 V3R18 source release-tie longest-static core screen

Status: `NO_GO_V3R18_SOURCE_RELEASE_TIE`.

Primary comparison: `candidate_a_source_tie / off`. Historical Candidate A attribution is diagnostic only.

| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |
|---|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 0.932 | 1.022 | 1.018 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 0.918 | 1.016 | 1.031 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 0.933 | 1.023 | 1.055 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | 1.010 | 1.024 | 1.089 | FAIL |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | 1.006 | 1.024 | 1.089 | FAIL |
| g4irsf32_s2_nanning_2x_stable_2p5 | 0.986 | 1.015 | 1.046 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 0.941 | 1.009 | 1.007 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 0.986 | 1.015 | 1.011 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | 0.990 | 1.017 | 1.018 | FAIL |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | 0.990 | 1.017 | 1.031 | FAIL |

## Failed core gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: no_new_starvation_threshold_crossings, nanning_whole_mean_regression_at_most_0p5pct, nanning_whole_p99_regression_at_most_1pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: no_new_starvation_threshold_crossings, nanning_whole_mean_regression_at_most_0p5pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, nanning_whole_mean_regression_at_most_0p5pct, nanning_whole_p99_regression_at_most_1pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_map2_1x_stable_2p5`: no_new_starvation_threshold_crossings, map2_mean_regression_at_most_0p5pct, map2_p95_regression_at_most_0p5pct
- `g4irsf32_s2_map2_1x_fault_sentinel_single_1`: no_new_starvation_threshold_crossings, map2_mean_regression_at_most_0p5pct, map2_p95_regression_at_most_0p5pct
- `g4irsf32_s2_nanning_2x_stable_2p5`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct, nanning_whole_mean_regression_at_most_0p5pct, nanning_whole_p99_regression_at_most_1pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: no_new_starvation_threshold_crossings, nanning_whole_mean_regression_at_most_0p5pct, nanning_whole_p99_regression_at_most_1pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct, nanning_whole_mean_regression_at_most_0p5pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_map2_2x_stable_2p5`: no_new_starvation_threshold_crossings, map2_mean_regression_at_most_0p5pct, map2_p99_regression_at_most_0p5pct
- `g4irsf32_s2_map2_2x_fault_sentinel_single_1`: no_new_starvation_threshold_crossings, map2_mean_regression_at_most_0p5pct, map2_p99_regression_at_most_0p5pct

## Decision

Source release-tie longest-static is NO-GO; Stage 3 remains blocked.

Stage 3 authorized: `false`.

Failed campaign gates: all_nanning_core_gates, all_map2_core_gates
