# Java / C++ Legacy Probability-Extreme Window Performance

Date: 2026-06-24

## Scope

This benchmark compares the read-only legacy Java `Tasks.generate_tasks` probability branches against the native C++ port using deterministic extreme probabilities. Only `0.0` and `1.0` are accepted because intermediate Java `Math.random()` outcomes are not reproducible without modifying the legacy project.

- map: `legacy/jichang_origin_readonly/map2.txt`
- tasks: `legacy/jichang_origin_readonly/inputdata.txt`
- fault probability: `1.0`
- repair probability: `0.0`
- start epoch: `8260`
- max epochs: `5000`
- max generated tasks: `64`
- C++ pybind path: `C:\PROGRAMING\czr005\build_vs\python\Release`

## Metrics

| Runtime | Repeats | Elapsed seconds | Windows/s | Plans/s | Generated | Planned | Generated fault edges | Generated repair edges | Active faults | Route checksum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy_java_ics_probability_extreme_window | 3 | 28.742092 | 0.1044 | 6.4713 | 64 | 62 | 145314 | 145245 | 69 | 80333 |
| cpp_pybind_legacy_probability_extreme_window | 3 | 0.745111 | 4.0262 | 249.6273 | 64 | 62 | 145314 | 145245 | 69 | 80333 |

C++/Java probability-extreme window planner throughput ratio: `38.574x`.

Performance CSV: `outputs/tables/java_cpp_legacy_probability_extreme_window_performance.csv`
Route parity CSV: `outputs/tables/java_cpp_legacy_probability_extreme_window_route_parity.csv`

## Gate Status

- Java/C++ probability-extreme summary parity: PASS
- Java/C++ probability-extreme planned route multiset parity: PASS
- C++ probability-extreme window is not slower than legacy Java: PASS

## Boundary

This covers deterministic probability extremes in the legacy task generator. Random intermediate probabilities remain intentionally outside the gate because the read-only Java project does not expose an injectable random seed.
