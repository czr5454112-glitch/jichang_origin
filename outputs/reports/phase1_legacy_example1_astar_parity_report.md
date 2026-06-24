# Phase1 Legacy Example1 A* Parity Diagnostic

## Scope

This non-learning diagnostic checks the Python reference A* planner and the C++ pybind A* planner on the legacy `example1` topology. The map has a ragged final heuristic row that Java accepts by leaving the missing double-array cell at `0.0`; the Python and C++ parsers keep strict mode by default and require an explicit Java-compatible flag for this fixture.

- map: `legacy/jichang_origin_readonly/example1/map.txt`
- task snapshots: 31
- nodes: 11
- edges: 13
- starts: [0, 10]
- goals: [9]
- strict parser check: `heuristic row 23 has 10 values, expected 11`
- compatibility padding check: final heuristic row tail `[24.0, 24.0, 0.0]`
- table: `outputs/tables/phase1_legacy_example1_astar_parity.csv`

## Results

- route cases from task snapshots and start/end anchors: 10
- Python/C++ exact path matches: 10 / 10
- legacy output anchor matches: 2 / 2

| Start | Goal | Python path | C++ path | Parity | Legacy anchor |
|---:|---:|---|---|---|---|
| 0 | 9 | `[0, 1, 3, 5, 8, 9]` | `[0, 1, 3, 5, 8, 9]` | True | True |
| 1 | 9 | `[1, 3, 5, 8, 9]` | `[1, 3, 5, 8, 9]` | True |  |
| 2 | 9 | `[2, 4, 6, 7, 9]` | `[2, 4, 6, 7, 9]` | True |  |
| 3 | 9 | `[3, 5, 8, 9]` | `[3, 5, 8, 9]` | True |  |
| 4 | 9 | `[4, 6, 7, 9]` | `[4, 6, 7, 9]` | True |  |
| 5 | 9 | `[5, 8, 9]` | `[5, 8, 9]` | True |  |
| 6 | 9 | `[6, 7, 9]` | `[6, 7, 9]` | True |  |
| 7 | 9 | `[7, 9]` | `[7, 9]` | True |  |
| 8 | 9 | `[8, 9]` | `[8, 9]` | True |  |
| 10 | 9 | `[10, 2, 4, 6, 7, 9]` | `[10, 2, 4, 6, 7, 9]` | True | True |

## Gate Status

Phase1 legacy `example1` A* parity gate is PASS.
