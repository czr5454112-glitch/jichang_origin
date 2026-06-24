# Java / C++ Legacy Scheduled Fault Window Performance

Date: 2026-06-24

## Scope

This benchmark compares the read-only legacy Java `ICS_PathFinding` scheduler against the native C++ port on a deterministic fault/repair window. The schedule is injected through an external Java harness by toggling in-memory edge fault states before the legacy `Tasks.generate_tasks` call; no legacy source file is modified. The default schedule faults the first active route after it has been planned, then repairs the edge.

- map: `legacy/jichang_origin_readonly/map2.txt`
- tasks: `legacy/jichang_origin_readonly/inputdata.txt`
- schedule: `8268:3:16:fault;8300:3:16:repair`
- start epoch: `8260`
- max epochs: `5000`
- max generated tasks: `64`
- C++ pybind path: `C:\PROGRAMING\czr005\build_vs\python\Release`

## Metrics

| Runtime | Repeats | Elapsed seconds | Windows/s | Plans/s | Generated | Planned | Completed | Fault events | Repair events | Active faults | Route checksum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy_java_ics_scheduled_fault_window | 3 | 26.444111 | 0.1134 | 7.1471 | 64 | 63 | 56 | 1 | 1 | 0 | 85226 |
| cpp_pybind_legacy_scheduled_fault_window | 3 | 0.535391 | 5.6034 | 353.0133 | 64 | 63 | 56 | 1 | 1 | 0 | 85226 |

C++/Java scheduled fault-window planner throughput ratio: `49.392x`.

Performance CSV: `outputs/tables/java_cpp_legacy_scheduled_fault_window_performance.csv`
Route parity CSV: `outputs/tables/java_cpp_legacy_scheduled_fault_window_route_parity.csv`

## Gate Status

- Java/C++ scheduled fault summary parity: PASS
- Java/C++ scheduled fault planned route multiset parity: PASS
- C++ scheduled fault window is not slower than legacy Java: PASS

## Boundary

This covers deterministic fault activation and repair propagation through the legacy task-generation/path-finding loop, including the active-route first-edge `Handling_faults` branch. It does not yet cover random fault sampling or the Swing GUI repaint/sleep loop.
