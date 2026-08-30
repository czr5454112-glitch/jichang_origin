# G4IRSF32 V3R20 service-aware static-dominance core screen

Status: `NO_GO_V3R20_SERVICE_AWARE_STATIC_DOMINANCE`.

Primary comparison: `candidate_a_static_dominance / off`. Historical Candidate A attribution is diagnostic only.

| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |
|---|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 0.991 | 0.997 | 1.027 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 0.987 | 0.995 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 0.993 | 0.997 | 1.000 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | 1.000 | 1.000 | 1.082 | PASS |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | 1.000 | 1.000 | 1.016 | PASS |
| g4irsf32_s2_nanning_2x_stable_2p5 | 0.998 | 1.003 | 1.014 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 1.000 | 1.000 | 1.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 0.998 | 1.002 | 1.014 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | 1.000 | 1.000 | 1.000 | PASS |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | 1.000 | 1.000 | 1.000 | PASS |

## Failed core gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_stable_2p5`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct

## Decision

Service-aware static dominance is NO-GO; Stage 3 remains blocked.

Stage 3 authorized: `false`.

Failed campaign gates: all_nanning_core_gates
