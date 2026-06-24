# Java / C++ Legacy No-Fault Window Performance

Date: 2026-06-24

## Scope

This benchmark compares the read-only legacy Java `ICS_PathFinding` no-fault headless scheduling window against the native C++ port on the same `map2.txt` and `inputdata.txt` task stream. GUI, sockets, random faults, and repair events are disabled; task generation, active-route advancement, node constraints, unfinished-task retries, and A* route planning are included.

- map: `legacy/jichang_origin_readonly/map2.txt`
- tasks: `legacy/jichang_origin_readonly/inputdata.txt`
- start epoch: `8260`
- max epochs: `5000`
- max generated tasks: `64`
- C++ pybind path: `C:\PROGRAMING\czr005\build_vs\python\Release`

## Metrics

| Runtime | Repeats | Elapsed seconds | Windows/s | Plans/s | Generated | Planned | Completed | Active | Unfinished | Route checksum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy_java_ics_no_fault_window | 3 | 24.871284 | 0.1206 | 7.5991 | 64 | 63 | 57 | 6 | 1 | 85226 |
| cpp_pybind_legacy_no_fault_window | 3 | 0.511108 | 5.8696 | 369.7846 | 64 | 63 | 57 | 6 | 1 | 85226 |

C++/Java no-fault window planner throughput ratio: `48.661x`.

Performance CSV: `outputs/tables/java_cpp_legacy_window_performance.csv`
Route parity CSV: `outputs/tables/java_cpp_legacy_window_route_parity.csv`

## Gate Status

- Java/C++ summary parity: PASS
- Java/C++ planned route multiset parity: PASS
- C++ no-fault window is not slower than legacy Java: PASS

## Boundary

This is a deterministic no-fault window of the legacy scheduler. It is stronger than the isolated A* benchmark because it includes task arrival, active route progression, constraint rebuilds, retry handling, and Java `ICS_PathFinding` calls. It still does not cover stochastic fault/repair branches or the Swing GUI loop.
