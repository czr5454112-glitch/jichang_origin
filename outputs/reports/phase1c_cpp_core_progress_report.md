# Phase1C C++ Core Progress Report

Date: 2026-06-16

## Scope

Started the Phase1C C++ high-performance core with a dependency-light, header-only smoke implementation:

- `cpp/ics_core/graph/graph.hpp`
- `cpp/ics_core/task_stream/task_stream.hpp`
- `cpp/ics_core/reservation/reservation.hpp`
- `cpp/ics_core/routing/astar_types.hpp`
- `cpp/ics_core/routing/astar.hpp`
- `cpp/ics_core/metrics/metrics.hpp`
- `cpp/tests/test_cpp_core_smoke.cpp`

`CMakeLists.txt` now builds `test_cpp_core_smoke` and registers it as `cpp_core_smoke` in CTest.

## Semantics Implemented

- Directed graph with service times, edge travel time, and heuristic table.
- Java-compatible node reservation intervals using strict non-overlap.
- A* route planning over directed outgoing edges.
- Fault-edge blocking.
- Simple episode metric aggregation.

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

## Current Gate Status

- C++17 boundary: implemented in CMake.
- No GUI: yes.
- No global mutable singleton: yes.
- Deterministic smoke planner: yes.
- CTest smoke: passed in scaffold and target repo.

## Remaining Phase1C Work

- Load normalized `map2.json` into C++.
- Load/represent expanded task stream from JSONL.
- Compare C++ parser counts against Python parser output.
- Compare C++ A* against Python A* on map2 smoke cases.
- Add larger deterministic simulation parity cases.
