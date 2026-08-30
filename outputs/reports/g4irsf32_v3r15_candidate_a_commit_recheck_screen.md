# G4IRSF32 V3R15 Candidate A commit-recheck core screen

Status: `NO_GO_V3R15_CANDIDATE_A_COMMIT_RECHECK`.

Primary comparison: `candidate_a_recheck / off`. Historical Candidate A attribution is diagnostic only.

| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |
|---|---:|---:|---:|---:|
| g4irsf32_s2_nanning_1x_stable_2p5 | 1.000 | 1.000 | 1.000 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1 | 1.000 | 1.000 | 1.014 | FAIL |
| g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8 | 1.000 | 1.000 | 1.015 | FAIL |
| g4irsf32_s2_map2_1x_stable_2p5 | 1.000 | 1.000 | 1.000 | PASS |
| g4irsf32_s2_map2_1x_fault_sentinel_single_1 | 1.000 | 1.000 | 1.012 | PASS |
| g4irsf32_s2_nanning_2x_stable_2p5 | 1.000 | 1.002 | 1.022 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1 | 1.000 | 0.999 | 1.000 | FAIL |
| g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8 | 1.000 | 1.002 | 1.000 | FAIL |
| g4irsf32_s2_map2_2x_stable_2p5 | 1.000 | 1.000 | 1.000 | PASS |
| g4irsf32_s2_map2_2x_fault_sentinel_single_1 | 1.000 | 1.000 | 1.000 | PASS |

## Failed core gates

- `g4irsf32_s2_nanning_1x_stable_2p5`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_1x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct, nanning_no_source_to_network_unchanged_total_transfer
- `g4irsf32_s2_nanning_1x_fault_source_chain_inactive_single_8`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_stable_2p5`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_active_single_1`: nanning_target_p95_improves_2pct
- `g4irsf32_s2_nanning_2x_fault_source_chain_inactive_single_8`: nanning_target_p95_improves_2pct

## Decision

Candidate A commit recheck is NO-GO; Stage 3 remains blocked.

Stage 3 authorized: `false`.

Failed campaign gates: all_nanning_core_gates
