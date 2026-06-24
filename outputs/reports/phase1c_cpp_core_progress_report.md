# Phase1C C++ Core Progress Report

Date: 2026-06-16

## Scope

Started the Phase1C C++ high-performance core with a dependency-light, header-only smoke implementation:

- `cpp/ics_core/graph/graph.hpp`
- `cpp/ics_core/io/legacy_map_reader.hpp`
- `cpp/ics_core/io/legacy_task_reader.hpp`
- `cpp/ics_core/task_stream/task_stream.hpp`
- `cpp/ics_core/event_sim/event_sim.hpp`
- `cpp/ics_core/reservation/reservation.hpp`
- `cpp/ics_core/routing/astar_types.hpp`
- `cpp/ics_core/routing/astar.hpp`
- `cpp/ics_core/metrics/metrics.hpp`
- `cpp/tests/test_cpp_core_smoke.cpp`

`CMakeLists.txt` now builds `test_cpp_core_smoke` and registers it as `cpp_core_smoke` in CTest.

## Semantics Implemented

- Directed graph with service times, edge travel time, and heuristic table.
- Legacy `map2.txt` reader with Java-equivalent heuristic scaling.
- Legacy `inputdata.txt` reader with Java-equivalent early-bag storage splitting.
- Sequential headless reference simulator using A* + node reservations.
- Java-compatible node reservation intervals using strict non-overlap.
- A* route planning over directed outgoing edges.
- Fault-edge blocking.
- Simple episode metric aggregation.
- Non-GUI C++ smoke checks that print stderr failures and return non-zero on mismatch.

## Validation

Successful scaffold command shape:

```text
conda activate czr005
cmake -S . -B build_nmake -G "NMake Makefiles" -DCMAKE_CXX_COMPILER=cl
cmake --build build_nmake --config Release
ctest --test-dir build_nmake --output-on-failure
```

Scaffold result:

```text
1/1 Test #1: cpp_core_smoke ... Passed
100% tests passed
```

Target result under `C:\PROGRAMING\czr005`:

```text
1/1 Test #1: cpp_core_smoke ... Passed
100% tests passed
```

Ninja was not available on PATH, and Visual Studio generator probing did not find `CMAKE_CXX_COMPILER` in this shell. NMake with explicit `cl` is the current verified Windows build path.

The smoke test now also reads `legacy/jichang_origin_readonly/map2.txt`, checks 54 nodes, 54 heuristic rows, 69 edges, start/end node type counts, and verifies these Python-reference A* paths:

```text
0 -> 47:  0 6 12 13 23 24 27 28 47
52 -> 49: 52 29 30 31 32 37 49
53 -> 50: 53 20 10 15 14 46 36 44 50
```

The historical Java output for `3 -> 49` is inconsistent with current Java/map behavior, so C++ keeps it as a structural smoke only: non-empty route, correct start, correct goal.

During the map2 smoke expansion, a C++ A* lifetime bug was fixed by copying the current record before appending children to the `records` vector. This avoids invalid references after vector reallocation and prevents the MSVC debug-runtime dialog that was previously triggered by `assert`/abort behavior.

The smoke test also reads `legacy/jichang_origin_readonly/inputdata.txt` and checks Python parser parity for:

- raw task count: 28,506
- direct raw tasks: 13,409
- early-split raw tasks: 15,097
- expanded task legs: 43,603
- expanded start-node distribution: `{0: 3200, 1: 3193, 2: 3199, 3: 4887, 4: 4887, 5: 4886, 52: 15097, 53: 4254}`
- first Python-sorted task leg: `0:storage_in`, pass time `8267.845453`, start `3`, goal `47`

The C++ core smoke now also exercises the Phase1C event simulator:

- two non-overlapping tasks are planned sequentially by `ReferenceSimulator`
- node reservations stay conflict-free
- per-task events preserve segment ids and A* path locations
- a faulted only-edge case produces one unplanned event under `max_tasks=1`

The pybind boundary additionally exposes `reference_simulator_from_records(...)`; `tests/test_cpp_backend.py` compares C++ event-simulator metrics/events/path locations against the Python `ReferenceSimulator` on the same in-memory records.

## Current Gate Status

- C++17 boundary: implemented in CMake.
- No GUI: yes.
- No global mutable singleton: yes.
- Deterministic smoke planner: yes.
- CTest smoke: passed in scaffold and target repo.
- C++ event_sim vs Python reference simulator parity: covered by `tests/test_cpp_backend.py`.

## Remaining Phase1C Work

- Decide whether C++ should load normalized JSON directly or keep the legacy txt reader plus generated parity fixtures.
- Larger deterministic simulation parity beyond the small in-memory event-sim fixture remains useful but is now an expansion task, not a missing Phase1C event_sim boundary.
