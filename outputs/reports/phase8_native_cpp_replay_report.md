# Phase8 Native C++ EdgeScore Replay Smoke

Date: 2026-06-17

## Scope

This smoke runs the loaded MLP-EdgeScore runtime artifact inside the native C++ replay loop. Unlike the previous Phase8 policy smoke, both candidate construction and action execution happen in C++ through the pybind summary boundary.

The replay is intentionally compact and sequential. It is a native-runtime gate, not the final high-throughput event simulator.

## Metrics

| Case | Fault edges | Tasks | Planned | Unplanned | Decisions | Conflicts | Mean travel | Decisions/s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| native_first8 | none | 8 | 8 | 0 | 78 | 0 | 49.750000 | 4658.25 |
| native_first16 | none | 16 | 16 | 0 | 173 | 0 | 57.012500 | 4729.71 |
| native_fault_alt_route_first8 | 16->17 | 8 | 8 | 0 | 74 | 0 | 51.850000 | 3000.20 |
| native_fault_goal_exit_first8 | 28->47 | 8 | 8 | 0 | 186 | 0 | 146.750000 | 2974.05 |

CSV: `outputs/tables/phase8_native_cpp_replay.csv`

## Gate Status

- native C++ replay callable through pybind: PASS
- all configured task windows accounted for: PASS
- zero post-shield conflicts: PASS
- at least one task planned by native replay: PASS
- full high-throughput event simulator: not covered

## Remaining Work

- replace the compact sequential native replay with the full C++ event simulator
- align C++ replay features and metrics one-for-one with the Python environment over larger windows
- add repair events, randomized density schedules, and heldout-map replay
