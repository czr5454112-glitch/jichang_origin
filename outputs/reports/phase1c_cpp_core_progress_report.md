# Phase1C C++ Core Progress Report

Date: 2026-06-16

## Scope

Started the Phase1C C++ high-performance core with a dependency-light, header-only smoke implementation:

- `cpp/ics_core/graph/graph.hpp`
- `cpp/ics_core/io/legacy_map_reader.hpp`
- `cpp/ics_core/task_stream/task_stream.hpp`
- `cpp/ics_core/reservation/reservation.hpp`
- `cpp/ics_core/routing/astar_types.hpp`
- `cpp/ics_core/routing/astar.hpp`
- `cpp/ics_core/metrics/metrics.hpp`
- `cpp/tests/test_cpp_core_smoke.cpp`

`CMakeLists.txt` now builds `test_cpp_core_smoke` and registers it as `cpp_core_smoke` in CTest.

## Semantics Implemented

- Directed graph with service times, edge travel time, and heuristic table.
- Legacy `map2.txt` reader with Java-equivalent heuristic scaling.
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

The smoke test now also reads `legacy/jichang_origin_readonly/map2.txt`, checks 54 nodes, 54 heuristic rows, 69 edges, start/end node type counts, and verifies the `0 -> 47` path:

```text
0 6 12 13 23 24 27 28 47
```

During the map2 smoke expansion, a C++ A* lifetime bug was fixed by copying the current record before appending children to the `records` vector. This avoids invalid references after vector reallocation and prevents the MSVC debug-runtime dialog that was previously triggered by `assert`/abort behavior.

## Current Gate Status

- C++17 boundary: implemented in CMake.
- No GUI: yes.
- No global mutable singleton: yes.
- Deterministic smoke planner: yes.
- CTest smoke: passed in scaffold and target repo.

## Remaining Phase1C Work

- Decide whether C++ should load normalized JSON directly or keep the legacy txt reader plus generated parity fixtures.
- Load/represent expanded task stream from JSONL.
- Compare C++ task parser counts against Python parser output.
- Compare C++ A* against Python A* on a broader map2 smoke set.
- Add larger deterministic simulation parity cases.
