# Phase1 Python/C++ Port Acceptance Report

Date: 2026-06-24

## Scope

This non-learning acceptance report consolidates the Phase1 Python reference and C++ pybind port evidence requested by the master plan. It covers legacy parser/A* parity for `map2`, the Java-compatible ragged `example1` map fixture, and a repeated A* speed smoke.

- parity table: `outputs/tables/phase1_parity_cases.csv`
- speed table: `outputs/tables/phase1_speed_benchmark.csv`

## Parity

- map2 start/end cases: 40
- legacy example1 cases: 10
- exact Python/C++ path matches: 50 / 50

## Speed Smoke

| Runtime | Repeats | Total plans | Elapsed seconds | Plans/second | Checksum |
|---|---:|---:|---:|---:|---:|
| python_reference_astar | 100 | 4000 | 0.851942100 | 4695.154753 | 38900 |
| cpp_pybind_astar | 100 | 4000 | 0.683350700 | 5853.509772 | 38900 |

C++/Python planner throughput ratio on this local smoke: 1.247x.

## Gate Status

Phase1 Python/C++ port acceptance gate is PASS.

This report intentionally excludes teacher data, BC, RL, and other learning stages.
