# G4IRSF32 V3R14 Candidate B real-map core screen

Status: `NO_GO_V3R14_CANDIDATE_B`.

Primary comparison: `candidate_a_b / off`. Candidate A attribution is diagnostic only.

| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |
|---|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 0.986 | 0.994 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 0.988 | 0.990 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 0.987 | 0.994 | 1.000 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | 1.015 | 1.003 | 1.001 | FAIL |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | 1.010 | 1.002 | 1.001 | FAIL |
| g4irsf32_s2_nanning_2x_stable_2p5 | 0.990 | 0.998 | 1.014 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 0.994 | 0.994 | 1.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 0.990 | 0.997 | 1.009 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | 1.081 | 1.038 | 1.205 | FAIL |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | 1.083 | 1.036 | 1.197 | FAIL |

## Failed core gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct
- `g4irsf32_s2_map2_1x_stable_2p5`: map2_p95_regression_at_most_0p5pct
- `g4irsf32_s2_map2_1x_fault_sentinel_single_1`: map2_p95_regression_at_most_0p5pct
- `g4irsf32_s2_nanning_2x_stable_2p5`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_map2_2x_stable_2p5`: no_new_starvation_threshold_crossings, core_resources_within_1p10, map2_mean_regression_at_most_0p5pct, map2_p95_regression_at_most_0p5pct, map2_p99_regression_at_most_0p5pct
- `g4irsf32_s2_map2_2x_fault_sentinel_single_1`: no_new_starvation_threshold_crossings, core_resources_within_1p10, map2_mean_regression_at_most_0p5pct, map2_p95_regression_at_most_0p5pct, map2_p99_regression_at_most_0p5pct

## Decision

Candidate B is NO-GO; Stage 3 remains blocked.

Stage 3 authorized: `false`.

Failed campaign gates: all_nanning_core_gates, all_map2_core_gates
