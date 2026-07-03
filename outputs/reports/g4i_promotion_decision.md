# G4I Promotion Decision

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `b3d2296`
Contains G4H: `True`
Pushed to upstream at runtime: `True`

## Gate

| Criterion | Status | Evidence |
| --- | --- | --- |
| cpp_full_batch_replay_runs | PASS | stress_rows=21 |
| cpp_python_episode_parity | PASS | windows=8 |
| node_window_conflicts_zero | PASS | parity and stress |
| runtime_full_cie_astar_zero | PASS | C++ replay |
| model_plus_pibt_lite_beats_rule_only | PASS | 4449>582 |
| model_plus_pibt_lite_not_worse_than_model_only | PASS | 4449>=4449 |
| cpp_runtime_faster_than_python | PASS | cpp=0.50506883; python=10.6607754 |
| cpp_runtime_faster_than_cie_astar_proxy | FAIL | cpp=0.50506883; cie_proxy=0.18993917 |
| stress_2048_4096_8192_stable | PASS | 2048/4096/8192 |
| hidden_leakage_pass | PASS | ["PASS", "PASS", "PASS", "PASS", "PASS", "PASS", "PASS"] |
| negative_boundary_preserved | PASS | 47 |
| overall_g4i_gate | FAIL | block G4J; keep negative/runtime caveats |

## Decision

G4I does not pass the promotion gate. The blocker is retained in the table above; do not promote to G4J or make a runtime speed replacement claim until the blocker is resolved.
