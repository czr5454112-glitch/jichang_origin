# G4I No-Leakage Runtime Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `b3d2296`
Contains G4H: `True`
Pushed to upstream at runtime: `True`

## Result

| Check | Status | Details |
| --- | --- | --- |
| head_contains_g4h | PASS | b3d2296 |
| legacy_java_no_diff | PASS |  |
| g4i_cpp_replay_no_astar_planner | PASS | G4I replay loop computes local no-A* decisions; static A* benchmark is outside this function. |
| g4i_cpp_replay_no_forbidden_features | PASS | [] |
| runtime_full_cie_astar_default | PASS | disabled; G4I C++ summary reports runtime_full_cie_astar_calls=0 |
| edge_capacity_primary | PASS | False; edge overlap diagnostic only |
| remote_head_contains_g4h_at_runtime | PASS | upstream=origin/codex/czr005-rewrite; pushed=True |
