# G4IRSF32 V3R13 Candidate A Stage 2 campaign

Status: `NO_GO_V3R13_CANDIDATE_A_STAGE2`.

| case | start-49 source-wait proxy ratio | target P95 ratio | whole mean ratio | max resource ratio | pass |
|---|---:|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 0.975 | 1.000 | 1.000 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 0.975 | 1.000 | 1.000 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 0.972 | 1.000 | 1.000 | 1.006 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | n/a | n/a | 1.000 | 1.000 | FAIL |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | n/a | n/a | 1.000 | 1.086 | FAIL |
| g4irsf32_s2_nanning_2x_stable_2p5 | 0.987 | 1.000 | 1.002 | 1.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 0.987 | 1.000 | 0.999 | 1.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 0.987 | 1.000 | 1.002 | 1.000 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | n/a | n/a | 1.000 | 1.001 | FAIL |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | n/a | n/a | 1.000 | 1.018 | FAIL |

## Failed case gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: resources_within_1p10, nanning_mixed_origin_wait_or_idle_effect_proven, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: resources_within_1p10, nanning_mixed_origin_wait_or_idle_effect_proven, nanning_target_p95_improves_2pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: resources_within_1p10, nanning_mixed_origin_wait_or_idle_effect_proven, nanning_target_p95_improves_2pct
- `g4irsf32_s2_map2_1x_stable_2p5`: resources_within_1p10
- `g4irsf32_s2_map2_1x_fault_sentinel_single_1`: resources_within_1p10
- `g4irsf32_s2_nanning_2x_stable_2p5`: resources_within_1p10, nanning_mixed_origin_wait_or_idle_effect_proven, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: resources_within_1p10, nanning_mixed_origin_wait_or_idle_effect_proven, nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: resources_within_1p10, nanning_mixed_origin_wait_or_idle_effect_proven, nanning_target_p95_improves_2pct
- `g4irsf32_s2_map2_2x_stable_2p5`: resources_within_1p10
- `g4irsf32_s2_map2_2x_fault_sentinel_single_1`: resources_within_1p10

## Decision

Stage 3 is not authorized.

Failed campaign gates: all_nanning_gates, all_map2_gates
