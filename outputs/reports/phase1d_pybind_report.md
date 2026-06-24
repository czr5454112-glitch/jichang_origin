# Phase1D Pybind Boundary Report

Date: 2026-06-16

## Scope

Added a minimal `pybind11` boundary for the C++ core:

- `cpp/ics_core/bindings/czr005_cpp.cpp`
- `src/czr005/cpp_backend.py`
- `cpp/tests/test_pybind_smoke.py`
- `CMakeLists.txt` pybind target and CTest smoke

The binding module is named `czr005_cpp` and is emitted into the CMake build-tree Python directory. Python code can import it through `czr005.cpp_backend`, which searches `CZR005_CPP_PYTHON_PATH`, `build_vs/python/Debug`, `build_vs/python/Release`, and `build_nmake/python`.

## Bound Functions

- `read_legacy_map_summary(path)`: reads `map2.txt` through the C++ reader and returns node/edge/type counts.
- `read_legacy_task_summary(path)`: reads `inputdata.txt` through the C++ reader and returns raw/expanded task counts and start-node distribution.
- `plan_legacy_map_path(map_path, start, goal)`: runs the C++ A* planner and returns route locations.
- `plan_legacy_map_paths(map_path, cases)`: reads the map once and returns route locations for a batch of start/goal cases.
- `benchmark_legacy_map_paths(map_path, cases, repeats)`: reads the map once and times repeated C++ A* planning loops.
- `reference_simulator_from_records(node_records, edge_records, heuristic_time, task_records, ...)`: runs the C++ Phase1C reference event simulator on in-memory records and returns routes, events, unplanned tasks, and summary metrics.

`read_legacy_map_summary`, `plan_legacy_map_path`, `plan_legacy_map_paths`, and `benchmark_legacy_map_paths` also accept `allow_ragged_heuristic` for the explicit Java-compatible `example1/map.txt` fixture path.

## Python Backend Wrapper

`src/czr005/cpp_backend.py` provides:

- deterministic build-tree search paths for the optional extension
- a clear `CppBackendUnavailable` error when `czr005_cpp` has not been built or discoverable
- thin wrappers for legacy map/task summaries, A* route planning, batch route planning, route benchmarking, and in-memory reference simulator replay
- support for explicit `search_path` overrides and the `CZR005_CPP_PYTHON_PATH` environment variable

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
pytest tests/test_cpp_binding_smoke.py tests/test_cpp_backend.py tests/test_legacy_parsers.py tests/test_phase1b_sim_py.py tests/test_phase2_baselines.py
40 passed
```

The pybind smoke imports `czr005_cpp`, checks map/task parser summaries, validates C++ A* paths for `0 -> 47` and `52 -> 49`, and covers the explicit `example1` ragged-heuristic compatibility mode. The Python backend and exact master-plan `tests/test_cpp_binding_smoke.py` tests import through `czr005.cpp_backend`, validate the same wrapper boundary, and compare C++ `reference_simulator_from_records` with the Python `ReferenceSimulator` on the same in-memory event-sim fixture.

Standalone backend discovery also passed with only `src` on `PYTHONPATH`; `cpp_backend` found the local Debug build-tree extension without `CZR005_CPP_PYTHON_PATH`, and `tests/test_cpp_backend.py` passed `4 passed`.

## Remaining Phase1D/E Work

- Installed-wheel packaging of the pybind extension is still separate from the build-tree loader.
- Broader route parity and speed smoke evidence is now covered by the Phase1E report, while `example1` route parity is covered by the dedicated legacy example report.
