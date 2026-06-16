# Codex Worklog

## 2026-06-16 18:00 - Phase0 and Phase1A startup

- Request: Complete the Python/C++ port prerequisites described in `czr005_project_master_plan.md`, starting with Phase0 and Phase1A.
- Branch: local startup work.
- Files changed: project metadata, docs skeletons, legacy parser modules, conversion scripts, parser tests.
- Commands run: legacy file inspection; parser count checks against `map2.txt` and `inputdata.txt`; conversion scripts; pytest; conda/cmake environment checks.
- Key observations: `map2.txt` has 54 nodes, 54 heuristic rows, and 69 directed edges. `inputdata.txt` has 28,506 raw tasks and expands to 43,603 Java-equivalent task legs under the early-bag split rule.
- Tests / validation: `python -m pytest` passed in scaffold and target; `C:\Users\38908\.conda\envs\czr005\python.exe -m pytest` passed in target.
- Safety / parity notes: this round does not change Java and does not introduce RL logic.
- Follow-up: full `environment.yml` creation timed out once during dependency solving/download, but the `czr005` env is registered and satisfies the Phase0 gates checked so far. Finish Python reference simulator, then C++ core parity and pybind boundary.

## 2026-06-16 19:15 - Phase1B Python reference simulator

- Request: Continue the Python/C++ port stages in the master plan after Phase1A.
- Branch: `main`.
- Files changed: added `src/czr005/sim_py/*`, Phase1B smoke tests, and `outputs/reports/phase1b_python_reference_simulator_report.md`.
- Commands run: Java A* source inspection; legacy output smoke lookup; `python -m pytest`; `C:\Users\38908\.conda\envs\czr005\python.exe -m pytest`.
- Key observations: Java A* is a directed-graph planner with `t1/t2` node windows and strict interval non-overlap for non-goal nodes. Three legacy smoke routes match historical output exactly; `3 -> 49` is retained only as a structural smoke because the historical output file appears inconsistent with current Java/map semantics.
- Tests / validation: target repo under `czr005` Conda env passed `6 passed`.
- Safety / parity notes: simulator is headless, deterministic, and returns structured logs; no GUI, RL, or hidden step-time file writes were added.
- Follow-up: implement Phase1C C++ graph/task/A*/reservation/metrics core, then Python/C++ parity tests and pybind boundary.

## 2026-06-16 19:45 - Phase1C C++ core smoke

- Request: Continue the Python/C++ port by starting the C++ high-performance core.
- Branch: `main`.
- Files changed: added header-only C++ graph, task stream, reservation, A*, and metrics modules; added `cpp/tests/test_cpp_core_smoke.cpp`; updated CMake.
- Commands run: CMake configure/build/CTest attempts with Ninja, Visual Studio, and NMake; final successful command used `NMake Makefiles` with `cl` inside the `czr005` activated environment.
- Key observations: `cl.exe` is available after `conda activate czr005`; Ninja is not on PATH; Visual Studio generator probing failed to resolve the compiler, but NMake + explicit `CMAKE_CXX_COMPILER=cl` works.
- Tests / validation: `cpp_core_smoke` passed 1/1 under CTest in both scaffold and target repo; Python pytest still passed `6 passed`.
- Safety / parity notes: C++ smoke covers deterministic graph routing, node reservation conflicts, fault-edge blocking, and metrics. It does not yet load `map2.json` or compare against Python on map2.
- Follow-up: add C++ JSON/JSONL loading or a generated fixture bridge, then Python/C++ parser and A* parity tests.

## 2026-06-16 20:05 - Phase1C legacy map reader

- Request: Strengthen the C++ port with a parser/parity step closer to the Phase1C gate.
- Branch: `main`.
- Files changed: added `cpp/ics_core/io/legacy_map_reader.hpp`, extended graph type counts and C++ smoke test, and fixed A* current-record lifetime during open-list expansion.
- Commands run: CMake configure/build/CTest using `NMake Makefiles` and explicit `cl`; `C:\Users\38908\.conda\envs\czr005\python.exe -m pytest`.
- Key observations: C++ can now read legacy `map2.txt` directly, parse 54 nodes, 54 heuristic rows, and 69 edges, and reproduce the `0 -> 47` map2 A* path. The smoke test now reports failures through stderr/exit code instead of MSVC debug `assert` dialogs.
- Tests / validation: target CTest passed 1/1; target Python pytest passed `6 passed`.
- Safety / parity notes: This improves parser parity evidence but still does not cover `inputdata.txt`/JSONL task loading or broad Python/C++ A* parity.
- Follow-up: add task stream reader and multi-case Python/C++ parity table.

## 2026-06-16 20:30 - Phase1C legacy task stream reader

- Request: Continue Phase1C by bringing C++ task parsing closer to Python parser parity.
- Branch: `main`.
- Files changed: added `cpp/ics_core/io/legacy_task_reader.hpp`, extended `TaskLeg` with `source_line`, aligned C++ task stream ordering with Python, and expanded the C++ smoke test.
- Commands run: CMake build/CTest using `NMake Makefiles` and explicit `cl`.
- Key observations: C++ now reads legacy `inputdata.txt`, applies the same early-bag split constants as Python, and validates 28,506 raw tasks -> 43,603 expanded task legs with the same start-node distribution.
- Tests / validation: scaffold CTest passed 1/1; target CTest passed 1/1; target Python pytest passed `6 passed`.
- Safety / parity notes: This adds parser parity coverage only; it does not yet run full task-stream simulation parity or pybind bindings.
- Follow-up: add broader Python/C++ A* parity and Phase1D pybind.

## 2026-06-16 20:45 - Phase1C map2 A* parity smoke expansion

- Request: Continue Phase1C by broadening C++ A* smoke parity against the Python reference.
- Branch: `main`.
- Files changed: extended `cpp/tests/test_cpp_core_smoke.cpp` with three Python-reference map2 paths and one structural route check for the historically inconsistent `3 -> 49` case.
- Commands run: CMake build/CTest using `NMake Makefiles` and explicit `cl`.
- Key observations: C++ matches Python exact routes for `0 -> 47`, `52 -> 49`, and `53 -> 50`; `3 -> 49` remains structural only for the same reason documented in the Python tests.
- Tests / validation: scaffold CTest passed 1/1; target CTest passed 1/1; target Python pytest passed `6 passed`.
- Safety / parity notes: This is still smoke parity, not a full generated parity table or timing report.
- Follow-up: move to Phase1D pybind or a generated Phase1E parity/speed table.
