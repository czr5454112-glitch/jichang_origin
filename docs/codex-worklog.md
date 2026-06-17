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

## 2026-06-16 21:05 - Phase1D pybind boundary

- Request: Continue from Phase1C into the Python/C++ boundary required by the master plan.
- Branch: `main`.
- Files changed: added `cpp/ics_core/bindings/czr005_cpp.cpp`, `cpp/tests/test_pybind_smoke.py`, `outputs/reports/phase1d_pybind_report.md`, and CMake pybind wiring.
- Commands run: CMake configure/build/CTest using `NMake Makefiles`, explicit `cl`, and pybind11 from the `czr005` Conda environment.
- Key observations: CMake finds Python 3.11.15 and pybind11 3.0.3 in the Conda env; the build emits `czr005_cpp.cp311-win_amd64.pyd` under `build_nmake/python`.
- Tests / validation: scaffold CTest passed 2/2; target CTest passed 2/2; target Python pytest passed `6 passed`.
- Safety / parity notes: The binding exposes parser summaries and A* path planning only; no learning/runtime policy code is bound yet.
- Follow-up: add Phase1E parity/speed smoke using the binding.

## 2026-06-16 21:25 - Phase1E Python/C++ parity and speed smoke

- Request: Continue into Phase1E by producing a reproducible Python/C++ parity and speed smoke.
- Branch: `main`.
- Files changed: extended `czr005_cpp` with batched path planning and an internal benchmark helper; added `scripts/eval/run_phase1e_py_cpp_parity_speed.py`; generated `outputs/tables/phase1e_astar_py_cpp_parity.csv` and `outputs/reports/phase1e_py_cpp_parity_speed_report.md`.
- Commands run: CMake build/CTest using `NMake Makefiles` and explicit `cl`; Phase1E parity/speed script.
- Key observations: target run matched 40/40 map2 start/end route cases. With 100 repeats, Python reference measured 4,445.23 plans/s and C++ pybind core measured 5,687.79 plans/s on this smoke.
- Tests / validation: scaffold CTest passed 2/2; target CTest passed 2/2; target Phase1E script passed; target Python pytest passed `6 passed`.
- Safety / parity notes: This is a small map2 A* smoke, not a large-scale event-simulation benchmark. It does not yet include task stream replay or reservation-heavy scaling.
- Follow-up: begin Phase1a A* scalability diagnosis or Phase2 baseline/shield work.

## 2026-06-16 21:50 - Phase1a planner-only A* scalability diagnosis

- Request: Continue after Phase1E with preliminary A* scalability evidence from the real task stream.
- Branch: `main`.
- Files changed: added `scripts/eval/run_phase1a_astar_scalability.py`, generated `outputs/tables/phase1a_astar_scalability.csv`, `outputs/reports/phase1a_astar_scalability_diagnosis.md`, and `outputs/figures/phase1a_runtime_vs_active_bags.png`.
- Commands run: Phase1a scalability script against the scaffold and target build-tree `czr005_cpp` modules.
- Key observations: 500/1000/2000/4000/8000 planner-only task-leg sweeps all matched Python/C++ checksums. In the target run at 8,000 plans, Python reference took 1.837983s and C++ pybind core took 1.516141s, a 1.212x speedup.
- Tests / validation: scaffold and target scripts passed and generated CSV/report/PNG. Matplotlib triggered a native `python.exe` application error in this Windows session, so the script now uses Pillow to draw the PNG without GUI/native plotting backends.
- Safety / parity notes: This is planner-only; it does not yet include reservation-heavy event replay, faults, rolling replans, or active queue pressure.
- Follow-up: move to Phase2 baseline/shield work.

## 2026-06-16 22:15 - Phase2A junction shield skeleton

- Request: Start Phase2 baseline/shield work after Phase1 parity and scalability smoke.
- Branch: `main`.
- Files changed: added `cpp/ics_core/shield/junction_shield.hpp`, expanded C++ smoke tests, and updated safety/C++ docs plus `outputs/reports/phase2a_reservation_shield_report.md`.
- Commands run: CMake build/CTest using `NMake Makefiles` and explicit `cl`.
- Key observations: The initial C++ shield rejects missing edges, faulted edges, node reservation conflicts, edge capacity conflicts, edge headway conflicts, and next-hop choices that make the goal unreachable.
- Tests / validation: scaffold CTest passed 2/2; target CTest passed 2/2; target Python pytest passed `6 passed`.
- Safety / parity notes: This is a deterministic shield skeleton only; buffer capacity, merge groups, SIPP, rolling horizon, and PIBT-style resolver remain pending.
- Follow-up: expand Phase2 baselines.

## 2026-06-16 22:35 - Phase2B minimal Python SIPP baseline

- Request: Expand Phase2 baselines after the initial C++ shield skeleton.
- Branch: `main`.
- Files changed: added `src/czr005/baselines/sipp.py`, `src/czr005/baselines/__init__.py`, `tests/test_phase2_baselines.py`, and `outputs/reports/phase2b_sipp_baseline_report.md`.
- Commands run: Python pytest in scaffold.
- Key observations: The SIPP baseline can wait for the next safe node interval; on a three-node test graph, legacy-compatible A* fails against a node reservation while SIPP waits and reaches the goal.
- Tests / validation: scaffold Python pytest passed `8 passed`; target Python pytest passed `8 passed`; target CTest passed 2/2.
- Safety / parity notes: This is Python-only and node-reservation focused. Edge capacity/headway, buffers, merge groups, C++ parity, and event replay remain pending.
- Follow-up: continue Phase2 baseline expansion.

## 2026-06-17 00:20 - Phase2C rolling-horizon SIPP baseline

- Request: Continue Phase2 baseline expansion toward rolling-horizon prioritized planning.
- Branch: `main`.
- Files changed: added `src/czr005/baselines/rolling_horizon.py`, exported it from `czr005.baselines`, expanded `tests/test_phase2_baselines.py`, and added `outputs/reports/phase2c_rolling_horizon_baseline_report.md`.
- Commands run: Python pytest in scaffold.
- Key observations: The baseline batches tasks by pass-time horizon, prioritizes tighter deadline slack, plans with SIPP against shared reservations, and reports unplanned tasks when fault edges block the only route.
- Tests / validation: scaffold Python pytest passed `10 passed`; target Python pytest passed `10 passed`; target CTest passed 2/2.
- Safety / parity notes: This is a Python skeleton, not full active-bag replanning or C++ runtime parity. Edge capacity/headway and merge-aware priority remain pending.
- Follow-up: add broader baseline replay diagnostics.

## 2026-06-17 00:40 - Phase2 baseline smoke replay

- Request: Add a reproducible Phase2 baseline/shield smoke after the rolling-horizon skeleton.
- Branch: `main`.
- Files changed: added `scripts/eval/run_phase2_baseline_smoke.py`, generated `outputs/tables/phase2_baseline_smoke_metrics.csv`, and generated `outputs/reports/phase2_baseline_and_shield_report.md`.
- Commands run: Phase2 baseline smoke in scaffold.
- Key observations: On the first 128 expanded task legs, reference A* planned 113 and left 15 unplanned; rolling-horizon SIPP planned 128/128. Both runs reported zero reservation conflicts.
- Tests / validation: scaffold script passed; target script passed; target Python pytest passed `10 passed`; target CTest passed 2/2.
- Safety / parity notes: This is still a smoke replay, not full multi-seed/fault/density evaluation. It covers node reservation safety but not edge capacity/headway or merge groups.
- Follow-up: continue Phase2 baseline expansion with edge/headway-aware SIPP or PIBT-style one-step resolver.

## 2026-06-17 01:05 - Phase2D PIBT-style one-step resolver

- Request: Continue Phase2 baseline expansion with the PIBT/CS-PIBT-style one-step resolver from the master plan.
- Branch: `main`.
- Files changed: added `src/czr005/baselines/pibt.py`, exported it from `czr005.baselines`, expanded `tests/test_phase2_baselines.py`, updated `docs/safety-spec.md`, and added `outputs/reports/phase2d_pibt_style_resolver_report.md`.
- Commands run: target Python pytest and target CTest.
- Key observations: The resolver orders agents by deadline slack/waiting priority, avoids same-slice merge conflicts, falls back to hold when no safe edge is available, and selects a safe alternative when the preferred edge is faulted.
- Tests / validation: target Python pytest passed `12 passed`; target CTest passed 2/2.
- Safety / parity notes: This is a deterministic one-step baseline, not full recursive PIBT. Edge headway/capacity, merge groups, full replay integration, and C++ parity remain pending.
- Follow-up: integrate one-step resolver into replay diagnostics or add edge/headway-aware SIPP.

## 2026-06-17 01:30 - Phase2B edge/headway-aware SIPP extension

- Request: Strengthen Phase2 safety constraints by adding edge capacity/headway awareness to the Python SIPP baseline.
- Branch: `main`.
- Files changed: added `EdgeReservation` and `EdgeReservationTable` to `src/czr005/sim_py/reservation.py`, exported them from `czr005.sim_py`, extended SIPP with edge reservation/capacity/headway parameters, expanded Phase2 baseline tests, updated safety docs, and added `outputs/reports/phase2b_edge_headway_sipp_report.md`.
- Commands run: target Python pytest and target CTest.
- Key observations: SIPP now waits for an occupied edge-capacity slot and for edge entry headway before traversing, then still aligns arrival with target-node safe intervals.
- Tests / validation: target Python pytest passed `14 passed`; target CTest passed 2/2.
- Safety / parity notes: Rolling-horizon replay does not yet emit edge reservations, merge groups and buffers are still pending, and C++ SIPP parity remains pending.
- Follow-up: integrate edge reservations into rolling-horizon replay or add C++ SIPP parity.

## 2026-06-17 01:55 - Phase2C rolling-horizon edge reservation integration

- Request: Continue Phase2 by making the rolling-horizon SIPP replay use the edge capacity/headway machinery.
- Branch: `main`.
- Files changed: extended `src/czr005/baselines/rolling_horizon.py` with shared edge reservations and edge capacity/headway parameters, expanded `tests/test_phase2_baselines.py`, regenerated `outputs/tables/phase2_baseline_smoke_metrics.csv` and `outputs/reports/phase2_baseline_and_shield_report.md`, and added `outputs/reports/phase2c_edge_reservation_replay_report.md`.
- Commands run: target Python pytest, target Phase2 baseline smoke, and target CTest.
- Key observations: Rolling-horizon SIPP now reserves every traversed edge after a route is accepted, so later task legs wait for edge capacity or entry-headway availability before crossing.
- Tests / validation: target Python pytest passed `16 passed`; target Phase2 baseline smoke passed with rolling-horizon SIPP planning `128/128` task legs and zero reservation conflicts; target CTest passed 2/2.
- Safety / parity notes: This is still a deterministic Python replay baseline. Merge groups, buffer-capacity constraints, full active-bag replanning, recursive PIBT replay integration, C++ SIPP parity, and multi-seed density/fault sweeps remain pending.
- Follow-up: move to merge/buffer constraints, C++ SIPP parity, or Phase3 learning-environment scaffolding.

## 2026-06-17 02:35 - Phase3 Python junction learning environment smoke

- Request: Continue from Phase2 into the Phase3 learning-environment definition in the master plan.
- Branch: `main`.
- Files changed: added `src/czr005/envs/` with action masks, observations, reward shaping, a Gym-style `IcsJunctionEnv`, a lightweight vectorized wrapper, and scripted safe policies; expanded `EdgeReservationTable` cleanup helpers; added `tests/test_phase3_env.py`; added `scripts/eval/run_phase3_learning_env_smoke.py`; generated `outputs/tables/phase3_learning_env_smoke_metrics.csv` and `outputs/reports/phase3_learning_env_report.md`.
- Commands run: target Python pytest, target Phase3 learning-env smoke, and target CTest.
- Key observations: The environment exposes `reset`/`step`, candidate-edge observations, hard shield fallback, node/edge reservation checks, and structured episode summaries. On real `map2`/`inputdata`, the A*-guided safe policy planned `8/8` smoke task legs with zero post-shield conflicts; random-safe actions ran on `16` task legs with zero post-shield conflicts but many unplanned tasks, as expected for an unguided random policy.
- Tests / validation: target Python pytest passed `21 passed`; Phase3 smoke passed; target CTest passed 2/2.
- Safety / parity notes: This is an environment contract and smoke gate, not a strong learned-policy result. Multi-agent PettingZoo compatibility, richer occupancy/merge/buffer observations, queue-aware scripted policy, and teacher-slice export remain pending.
- Follow-up: start Phase4 teacher junction-slice generation or strengthen Phase3 with richer local features and a queue-aware policy baseline.

## 2026-06-17 03:05 - Phase4A teacher junction-slice manifest smoke

- Request: Continue from Phase3 into the master-plan teacher data stage, without starting BC training yet.
- Branch: `main`.
- Files changed: added `src/czr005/datasets/teacher_slices.py` and exports, added `tests/test_phase4_teacher_slices.py`, added `scripts/eval/run_phase4_teacher_dataset_smoke.py`, generated `artifacts/teacher/junction_slices_manifest.jsonl`, `outputs/tables/phase4_teacher_dataset_summary.csv`, and `outputs/reports/phase4_teacher_dataset_report.md`.
- Commands run: target Python pytest, target Phase4 teacher dataset smoke, and target CTest.
- Key observations: The first teacher manifest records 78 shielded junction decision slices from 8 real task legs using the A*-guided safe scripted policy. Each slice includes task observation features, candidate edges, action mask, proposed action, executed expert action, expert rank, cost-to-goal proxy, future-delay proxy, shield result, unsafe-proposal flag, reward, and goal flag.
- Tests / validation: target Python pytest passed `22 passed`; Phase4 smoke wrote the manifest with `8/8` planned task legs and zero reservation conflicts; target CTest passed 2/2.
- Safety / parity notes: This is a small manifest schema smoke, not a training set or learned policy. Larger teacher sweeps, split metadata, SIPP/rolling-horizon/PIBT teacher sources, and the first BC baseline remain pending.
- Follow-up: add the first MLP-EdgeScore behavior cloning baseline or expand teacher dataset generation across density/fault settings.
