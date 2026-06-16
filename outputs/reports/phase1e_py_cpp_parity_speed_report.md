# Phase1E Python/C++ Parity and Speed Smoke

Date: 2026-06-16

## Scope

This smoke compares the Python reference A* planner and the C++ A* planner exposed through `czr005_cpp` on every `map2.txt` start/end pair:

- starts: [0, 1, 2, 3, 4, 5, 52, 53]
- goals: [47, 48, 49, 50, 51]
- cases: 40

## Parity

- matched cases: 40 / 40
- mismatched cases: 0
- table: `outputs/tables/phase1e_astar_py_cpp_parity.csv`

## Speed Smoke

Both timings parse/load the graph before the timed loop.

| Runtime | Repeats | Total plans | Elapsed seconds | Plans/second |
|---|---:|---:|---:|---:|
| Python reference | 100 | 4000 | 0.899840 | 4445.23 |
| C++ pybind core | 100 | 4000 | 0.703261 | 5687.79 |

Python checksum: 38900

C++ checksum: 38900

## Gate Status

Phase1E smoke gate is PASS for exact path parity on this case set.
