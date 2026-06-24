# Java / Python / C++ A* Performance Baseline

Date: 2026-06-24

## Scope

This benchmark compares the legacy Java `Astar.research` implementation against the Python reference A* and C++ pybind A* on the same `map2` task-stream `(start, goal)` cases. It is a headless planner benchmark: GUI, socket, and legacy file-output loops are not included.

- map: `legacy/jichang_origin_readonly/map2.txt`
- task stream: `data/processed/tasks/inputdata.jsonl`
- case count: `8000`
- measured repeats: `10`
- Java warmup repeats: `3`
- C++ pybind path: `C:\PROGRAMING\czr005\build_vs\python\Release`
- performance table: `outputs/tables/java_python_cpp_astar_performance.csv`
- path parity table: `outputs/tables/java_python_cpp_astar_path_parity.csv`

## Performance

| Runtime | Repeats | Total plans | Elapsed seconds | Plans/second | Checksum |
|---|---:|---:|---:|---:|---:|
| legacy_java_astar | 10 | 80000 | 1.564633700 | 51130.178265 | 661760 |
| python_reference_astar | 10 | 80000 | 20.074064500 | 3985.241753 | 661760 |
| cpp_pybind_astar | 10 | 80000 | 0.901461300 | 88744.796920 | 661760 |

C++/Java planner throughput ratio: `1.736x`.
Python/Java planner throughput ratio: `0.078x`.

## Function Parity

- checksum match across Java/Python/C++: PASS
- Java/Python exact path parity: PASS
- Java/C++ exact path parity: PASS

## Gate Status

- functionality matches legacy Java on this benchmark: PASS
- C++ pybind A* is not slower than legacy Java A*: PASS

## Notes

This is the first apples-to-apples Java baseline for the port. It covers the core A* planner path used by the legacy project, not the full Java GUI/event/file-output loop. Full-system Java simulation timing would require a separate headless Java event harness.
