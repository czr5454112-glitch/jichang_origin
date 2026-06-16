# Phase1D Pybind Boundary Report

Date: 2026-06-16

## Scope

Added a minimal `pybind11` boundary for the C++ core:

- `cpp/ics_core/bindings/czr005_cpp.cpp`
- `cpp/tests/test_pybind_smoke.py`
- `CMakeLists.txt` pybind target and CTest smoke

The binding module is named `czr005_cpp` and is emitted into `build_nmake/python` during the verified NMake build.

## Bound Functions

- `read_legacy_map_summary(path)`: reads `map2.txt` through the C++ reader and returns node/edge/type counts.
- `read_legacy_task_summary(path)`: reads `inputdata.txt` through the C++ reader and returns raw/expanded task counts and start-node distribution.
- `plan_legacy_map_path(map_path, start, goal)`: runs the C++ A* planner and returns route locations.

## Validation

Verified scaffold command:

```text
conda activate czr005
cmake -S . -B build_nmake -G "NMake Makefiles" -DCMAKE_CXX_COMPILER=cl
cmake --build build_nmake --config Release
ctest --test-dir build_nmake --output-on-failure
```

Scaffold result:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

Target result under `C:\PROGRAMING\czr005`:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

Target Python pytest:

```text
6 passed
```

The pybind smoke imports `czr005_cpp`, checks map/task parser summaries, and validates C++ A* paths for `0 -> 47` and `52 -> 49`.

## Remaining Phase1D/E Work

- Decide packaging strategy for installed Python imports versus CMake build-tree imports.
- Add generated Python/C++ parity tables for broader route cases and timings.
- Add a speed smoke that compares Python planner and C++ planner via the binding under identical map/task inputs.
