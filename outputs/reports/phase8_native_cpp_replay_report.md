# Phase8 Native C++ EdgeScore Replay Smoke

Date: 2026-06-17

## Scope

This smoke runs the loaded MLP-EdgeScore runtime artifact inside the native C++ replay loop. Unlike the previous Phase8 policy smoke, both candidate construction and action execution happen in C++ through the pybind summary boundary.

The replay is intentionally compact and sequential. It is a native-runtime gate, not the final high-throughput event simulator.

## Metrics

| Case | Policy | Fault edges | Tasks | Planned | Unplanned | Decisions | Conflicts | Mean travel | Decisions/s |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| native_first8 | edge_score_runtime | none | 8 | 8 | 0 | 78 | 0 | 49.750000 | 3733.72 |
| native_first8 | shortest_safe_fallback | none | 8 | 8 | 0 | 73 | 0 | 55.225000 | 5148.75 |
| native_first16 | edge_score_runtime | none | 16 | 16 | 0 | 173 | 0 | 57.012500 | 4780.21 |
| native_first16 | shortest_safe_fallback | none | 16 | 16 | 0 | 198 | 0 | 58.800000 | 4205.09 |
| native_fault_alt_route_first8 | edge_score_runtime | 16->17 | 8 | 8 | 0 | 74 | 0 | 51.850000 | 4896.84 |
| native_fault_alt_route_first8 | shortest_safe_fallback | 16->17 | 8 | 8 | 0 | 73 | 0 | 55.225000 | 5318.92 |
| native_fault_goal_exit_first8 | edge_score_runtime | 28->47 | 8 | 8 | 0 | 186 | 0 | 146.750000 | 4079.03 |
| native_fault_goal_exit_first8 | shortest_safe_fallback | 28->47 | 8 | 8 | 0 | 155 | 0 | 132.575000 | 4614.59 |

CSV: `outputs/tables/phase8_native_cpp_replay.csv`

## Gate Status

- native C++ replay callable through pybind: PASS
- all configured task windows accounted for: PASS
- zero post-shield conflicts: PASS
- at least one task planned by native replay: PASS
- model-unavailable fallback replay: PASS
- full high-throughput event simulator: not covered

## Remaining Work

- replace the compact sequential native replay with the full C++ event simulator
- align C++ replay features and metrics one-for-one with the Python environment over larger windows
- add repair events, randomized density schedules, and heldout-map replay
