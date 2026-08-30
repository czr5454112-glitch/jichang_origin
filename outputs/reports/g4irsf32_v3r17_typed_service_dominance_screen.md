# G4IRSF32 V3R17 typed service-dominance core screen

Status: `NO_GO_V3R17_TYPED_SERVICE_DOMINANCE`.

Primary comparison: `candidate_a_dominance / off`. Historical Candidate A attribution is diagnostic only.

| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |
|---|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 0.991 | 0.998 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 0.990 | 0.997 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 0.993 | 0.998 | 1.007 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | 1.000 | 1.000 | 1.000 | PASS |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | 1.000 | 1.000 | 1.000 | PASS |
| g4irsf32_s2_nanning_2x_stable_2p5 | 0.995 | 1.000 | 1.014 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 0.994 | 0.997 | 1.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 0.995 | 0.999 | 1.009 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | 1.000 | 1.000 | 1.010 | PASS |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | 1.000 | 1.000 | 1.000 | PASS |

## Failed core gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: no_new_starvation_threshold_crossings, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_stable_2p5`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: nanning_target_p95_improves_2pct

## Decision

Typed service dominance is NO-GO; Stage 3 remains blocked.

Stage 3 authorized: `false`.

Failed campaign gates: all_nanning_core_gates
