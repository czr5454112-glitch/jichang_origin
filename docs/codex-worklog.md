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

## 2026-06-17 03:35 - Phase4C pure-Python MLP-EdgeScore BC smoke

- Request: Continue Phase4 by proving the teacher manifest can feed a first behavior-cloning baseline.
- Branch: `main`.
- Files changed: added `src/czr005/models/edge_score.py` and exports, added `tests/test_phase4_bc_edge_score.py`, added `scripts/train/train_phase4_bc_smoke.py`, generated `outputs/tables/phase4_bc_smoke_history.csv` and `outputs/reports/phase4_bc_smoke_report.md`. The local model artifact is written to ignored `artifacts/models/phase4_mlp_edge_score_smoke.json`.
- Commands run: target Python pytest, target Phase4 BC smoke, and target CTest.
- Key observations: A small pure-Python MLP-EdgeScore model trains on the 78-slice teacher manifest and reaches safe-masked top1 `0.974359` on the same smoke set. The implementation intentionally avoids numpy matrix operations after a Windows native `0xc06d007f` crash occurred during an initial numpy version of the smoke.
- Tests / validation: target Python pytest passed `23 passed`; Phase4 BC smoke passed with final loss `0.078525`; target CTest passed 2/2.
- Safety / parity notes: This is not a validated learning result. It has no train/validation split, no shadow replay, no closed-loop BC+shield run, and no comparison against Phase2 baselines yet.
- Follow-up: add Phase5 shadow replay for the BC scorer or expand teacher data and add split metadata first.

## 2026-06-17 04:05 - Phase5 BC shadow and closed-loop smoke

- Request: Continue from Phase4 BC into Phase5 shadow mode and a first shielded closed-loop smoke.
- Branch: `main`.
- Files changed: added `src/czr005/eval/shadow.py` and exports, added `tests/test_phase5_shadow.py`, added `scripts/eval/run_phase5_shadow_smoke.py`, generated `outputs/tables/phase5_shadow_smoke_metrics.csv` and `outputs/reports/phase5_shadow_and_closed_loop_smoke.md`, and updated the Phase4 BC history/report after changing BC training to penalize unsafe candidates in the raw softmax.
- Commands run: target Python pytest, target Phase4 BC smoke, target Phase5 shadow smoke, and target CTest.
- Key observations: Shadow replay over the 8-task smoke produced 78 decisions, 2 disagreements with the A*-guided baseline, unsafe proposal rate `0.000000`, and zero post-shield conflicts. The safe-masked BC+shield closed-loop replay stayed conflict-free but planned only `6/8` task legs, so it is not yet competitive with the baseline.
- Tests / validation: target Python pytest passed `24 passed`; Phase4 BC smoke passed with final loss `0.078525` and safe-masked top1 `0.974359`; Phase5 smoke passed with closed-loop conflicts `0`; target CTest passed 2/2.
- Safety / parity notes: This is a shadow/closed-loop plumbing smoke. It does not yet include heldout data, deadline-critical mistake analysis, larger task sets, faults, density sweeps, or Phase2 baseline comparisons.
- Follow-up: expand teacher data with splits and run larger Phase5 shadow/closed-loop comparisons before any RL fine-tuning.

## 2026-06-17 04:45 - Phase5 DAgger-style BC closed-loop recovery smoke

- Request: Strengthen the Phase5 gate before any RL work because the initial BC+shield closed-loop smoke was safe but only planned `6/8` task legs.
- Branch: `codex/czr005-rewrite`.
- Files changed: extended `src/czr005/datasets/teacher_slices.py` with behavior-policy state collection and expert relabeling, exported it, expanded `tests/test_phase5_shadow.py`, updated `scripts/eval/run_phase5_shadow_smoke.py`, regenerated `outputs/tables/phase5_shadow_smoke_metrics.csv` and `outputs/reports/phase5_shadow_and_closed_loop_smoke.md`, and added `artifacts/teacher/junction_slices_dagger_smoke.jsonl`.
- Commands run: target Python pytest, target Phase5 shadow smoke, and target CTest.
- Key observations: The script now records 461 DAgger-style slices from model-visited states, retrains the pure-Python MLP-EdgeScore smoke model, and improves the 8-task closed-loop result from base BC `6/8` to DAgger BC `8/8`, with zero post-shield conflicts.
- Tests / validation: target Python pytest passed `25 passed`; Phase5 smoke passed with shadow unsafe rate `0.000000`, DAgger closed-loop planned `8/8`, and DAgger closed-loop conflicts `0`; target CTest passed 2/2.
- Safety / parity notes: This is still a small same-map smoke, not a heldout or paper-grade evaluation. It is enough to unblock larger Phase5 comparisons and then cautious Phase6 RL fine-tuning.
- Follow-up: add heldout split metadata and larger shadow/closed-loop sweeps before claiming learning-policy advantage.

## 2026-06-17 05:25 - Phase5 task-window validation sweep

- Request: Continue hardening Phase5 before Phase6 by adding heldout task-window evidence for the DAgger BC+shield smoke policy.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `scripts/eval/run_phase5_validation_sweep.py`, added `tests/test_phase5_validation.py`, and generated `outputs/tables/phase5_validation_sweep_metrics.csv` plus `outputs/reports/phase5_validation_sweep_report.md`.
- Commands run: target Python pytest, target Phase5 validation sweep, and target CTest.
- Key observations: Training used the base teacher manifest plus the DAgger smoke manifest. On `train_first8`, `heldout_next8`, and `combined_first16`, DAgger BC+shield matched the A*-guided baseline planned counts (`8/8`, `7/8`, `15/16`) with zero post-shield conflicts.
- Tests / validation: target Python pytest passed `26 passed`; Phase5 validation sweep passed all task-window gates; target CTest passed 2/2.
- Safety / parity notes: This is a same-map task-window heldout smoke, not a heldout-map, density, or fault validation. It reduces but does not eliminate overfit risk before Phase6.
- Follow-up: add heldout-map/synthetic-map validation, fault/density sweeps, and Phase2 baseline comparisons on larger windows before strong learning claims.

## 2026-06-17 05:55 - Phase5 robustness sweep for Phase6 fault curriculum

- Request: Continue preparing for Phase6 by adding density/fault diagnostics instead of starting RL before the failure modes are visible.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `scripts/eval/run_phase5_robustness_sweep.py`, generated `outputs/tables/phase5_robustness_sweep_metrics.csv`, and generated `outputs/reports/phase5_robustness_sweep_report.md`.
- Commands run: target Python pytest, target Phase5 robustness sweep, and target CTest.
- Key observations: A*-guided and DAgger BC+shield match on no-fault density windows with zero conflicts, but selected fault windows expose a BC robustness gap. With fault `16->17`, DAgger BC plans only `4/8` while rolling-horizon SIPP plans `8/8`; with fault `28->47`, both junction policies plan `0/8` while rolling-horizon SIPP plans `8/8`. All methods still report zero post-shield conflicts.
- Tests / validation: target Python pytest passed `26 passed`; Phase5 robustness sweep produced the density/fault diagnostics; target CTest passed 2/2.
- Safety / parity notes: This is a diagnostic sweep, not a learning improvement. It defines concrete Phase6 fault-curriculum targets and shows rolling-horizon SIPP remains the stronger recovery baseline under these faults.
- Follow-up: add fault-aware teacher slices and DAgger relabeling before RL fine-tuning, then compare against rolling-horizon SIPP and PIBT-style baselines on larger windows.

## 2026-06-17 06:35 - Phase5 fault-aware teacher curriculum smoke

- Request: Address the fault robustness gap found by the Phase5 robustness diagnostics before attempting Phase6 RL fine-tuning.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `fault_aware_astar_policy_factory` to `src/czr005/envs/ics_junction_env.py` and exports, added `tests/test_phase5_fault_curriculum.py`, added `scripts/eval/run_phase5_fault_curriculum_smoke.py`, generated `artifacts/teacher/junction_slices_fault_curriculum_smoke.jsonl`, `outputs/tables/phase5_fault_curriculum_metrics.csv`, and `outputs/reports/phase5_fault_curriculum_report.md`.
- Commands run: target Python pytest, target Phase5 fault curriculum smoke, and target CTest.
- Key observations: The fault-aware teacher produced 208 recovery slices for selected faults. Retraining MLP-EdgeScore with base + DAgger + fault-curriculum slices recovers both selected fault windows with zero conflicts: fault `16->17` improves from base DAgger BC `4/8` to `8/8`, and fault `28->47` improves from `0/8` to `8/8`. Rolling-horizon SIPP still has better fault-case travel time and remains the stronger recovery baseline.
- Tests / validation: target Python pytest passed `28 passed`; Phase5 fault curriculum smoke passed with zero post-shield conflicts; target CTest passed 2/2.
- Safety / parity notes: This is still same-map BC curriculum evidence, not RL and not heldout-map validation. It is a stronger starting checkpoint candidate for Phase6 but does not satisfy Phase6 gates by itself.
- Follow-up: add model-visited fault DAgger relabeling, larger fault/repair sweeps, and then a conservative Phase6 fine-tuning smoke.

## 2026-06-17 07:10 - Phase8 C++ MLP-EdgeScore runtime parity smoke

- Request: Move some learned-policy runtime work back toward C++ instead of only improving Python-side learning prerequisites.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `cpp/ics_core/models/edge_score.hpp`, exposed `edge_score_scores` and `edge_score_predict` through `cpp/ics_core/bindings/czr005_cpp.cpp`, expanded C++ and pybind smoke tests, updated `cpp/ics_core/README.md`, added `scripts/eval/run_phase8_edge_score_cpp_parity.py`, and generated `outputs/tables/phase8_edge_score_cpp_parity.csv` plus `outputs/reports/phase8_edge_score_cpp_parity_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, and Phase8 edge-score Python/C++ parity smoke.
- Key observations: The C++ header-only MLP scorer matches Python scorer outputs on 32 real teacher-slice feature rows using deterministic weights. The maximum score difference is within `1e-12`, and masked argmax predictions match.
- Tests / validation: target Python pytest passed `28 passed`; target CTest passed 2/2; Phase8 parity smoke passed.
- Safety / parity notes: This is scorer parity only. Production model loading, C++ closed-loop replay, runtime latency, and C++ shielded policy execution remain pending.
- Follow-up: export trained model artifacts into a stable C++ format, then add C++ closed-loop replay and latency measurement.

## 2026-06-17 07:45 - Phase8 EdgeScore runtime model text loader

- Request: Turn the C++ scorer parity smoke into a loadable runtime artifact path for the trained pure-Python MLP-EdgeScore model.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `cpp/ics_core/models/edge_score_io.hpp`, exposed `EdgeScoreRuntimeModel.from_text` and `edge_score_load_summary` through pybind, added `save_edge_score_runtime_text`, expanded pybind/Python tests, added `scripts/eval/run_phase8_edge_score_runtime_loader.py`, and generated `artifacts/runtime/phase8_edge_score_runtime_model.txt`, `outputs/tables/phase8_edge_score_runtime_loader_parity.csv`, and `outputs/reports/phase8_edge_score_runtime_loader_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, and Phase8 runtime-loader parity script.
- Key observations: The fault-curriculum MLP-EdgeScore checkpoint exports to a simple text format with magic/version, feature dimension, hidden dimension, and dense weights. C++ loads the artifact as a runtime model and matches Python scores/predictions on 64 real fault-curriculum teacher slices with max absolute score difference `0.000000000000` and zero masked-prediction mismatches.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `29 passed`; Phase8 runtime-loader parity script passed.
- Safety / parity notes: This closes the model-export/load prerequisite for C++ policy runtime, but it is still not C++ closed-loop replay, runtime latency measurement, or heldout-map validation.
- Follow-up: bind the loaded scorer into a C++ shielded replay loop, measure latency on larger replay batches, and validate exported checkpoints across heldout maps and fault schedules.

## 2026-06-17 08:25 - Phase8 C++ runtime policy and latency smoke

- Request: Continue Phase8 by measuring runtime inference latency and using the C++ loaded scorer inside a closed-loop shielded policy smoke.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `EdgeScoreRuntimeModel.predict_many`, added Python runtime-text loading and `runtime_edge_score_policy_factory`, expanded Python/pybind tests, added `scripts/eval/run_phase8_cpp_runtime_policy_smoke.py`, and generated `outputs/tables/phase8_cpp_runtime_latency.csv`, `outputs/tables/phase8_cpp_runtime_closed_loop.csv`, and `outputs/reports/phase8_cpp_runtime_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, and Phase8 C++ runtime policy smoke.
- Key observations: The C++ runtime model matches Python masked predictions on 208 fault-curriculum slices with zero mismatches. On this pybind batch smoke, `cpp_predict_many` measured about `18106.09` decisions/s. The C++ runtime policy matched the Python-loaded artifact planned counts on four density/fault closed-loop cases, with zero post-shield conflicts and no truncation.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `31 passed`; Phase8 runtime policy smoke passed.
- Safety / parity notes: This measures and uses C++ inference inside the existing Python event environment. Native C++ event replay, larger latency sweeps, and heldout-map/fault-schedule validation remain pending.
- Follow-up: move the event replay loop itself into C++, compare runtime against rolling-horizon/SIPP on identical larger windows, then validate exported checkpoints on heldout maps and randomized schedules.

## 2026-06-17 09:00 - Phase8 compact native C++ EdgeScore replay

- Request: Push Phase8 beyond pybind inference by adding a first native C++ replay path that constructs candidates, applies the shield, and executes the loaded EdgeScore policy inside C++.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `cpp/ics_core/runtime/edge_score_replay.hpp`, exposed `edge_score_native_replay_summary` through pybind, expanded C++/pybind smoke tests, updated `cpp/ics_core/README.md`, added `scripts/eval/run_phase8_native_cpp_replay_smoke.py`, and generated `outputs/tables/phase8_native_cpp_replay.csv` plus `outputs/reports/phase8_native_cpp_replay_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, and Phase8 native C++ replay smoke.
- Key observations: The compact C++ replay uses the runtime text model, C++ candidate feature construction, C++ `JunctionShield`, node/edge reservations, and hold fallback. On four small real map/task windows, it planned all `40/40` configured tasks with zero post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `31 passed`; Phase8 native C++ replay smoke passed.
- Safety / parity notes: This is the first native C++ replay loop, but it is still compact/sequential and not the final high-throughput event simulator. Feature/metric parity with the Python environment needs larger one-for-one checks.
- Follow-up: replace the compact replay with a full C++ event simulator, align replay features/metrics against Python on larger windows, and add repair-event plus heldout-map validation.

## 2026-06-17 09:25 - Phase8 native C++ replay fallback gate

- Request: Cover the Phase8 runtime requirement that execution must fall back safely when the learned model is unavailable.
- Branch: `codex/czr005-rewrite`.
- Files changed: extended `cpp/ics_core/runtime/edge_score_replay.hpp` with an optional-model replay path and `run_edge_score_fallback_replay`, exposed `edge_score_native_fallback_replay_summary` through pybind, expanded C++/pybind smoke tests, updated `cpp/ics_core/README.md`, and regenerated the Phase8 native replay CSV/report with both `edge_score_runtime` and `shortest_safe_fallback` rows.
- Commands run: CMake build, target CTest, target Python pytest, and Phase8 native C++ replay smoke.
- Key observations: The native fallback replay uses the same C++ candidate construction, shield, and reservations without loading a model. Across the four small real map/task windows, EdgeScore runtime plus fallback rows accounted for `80/80` configured tasks and reported zero post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `31 passed`; Phase8 native C++ replay smoke passed.
- Safety / parity notes: This covers model-unavailable fallback for the compact native replay only. The full high-throughput event simulator, larger parity checks, and heldout-map validation remain pending.
- Follow-up: compare compact C++ replay against Python environment metrics one-for-one on larger windows, then move the event scheduler itself into C++.

## 2026-06-17 09:45 - Phase8 native C++ / Python replay parity diagnostic

- Request: Verify that the compact native C++ EdgeScore replay is not only internally safe, but also aligned with the existing Python junction environment on identical windows.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `scripts/eval/run_phase8_native_cpp_python_parity.py` and generated `outputs/tables/phase8_native_cpp_python_parity.csv` plus `outputs/reports/phase8_native_cpp_python_parity_report.md`.
- Commands run: Phase8 native C++ / Python parity diagnostic.
- Key observations: The loaded EdgeScore runtime policy matches Python environment metrics exactly on four real map/task windows: planned/unplanned counts, decision counts, mean travel time, and post-shield conflicts all match within tolerance. The shortest-safe fallback remains conflict-free on both sides but does not have strict metric parity because compact C++ fallback and Python fallback differ in tie-breaking and goal-node reservation handling.
- Tests / validation: Phase8 native C++ / Python parity script passed with `4/4` EdgeScore strict parity rows and fallback safety diagnostic PASS.
- Safety / parity notes: This strengthens Phase8 compact replay evidence, but it is not full high-throughput C++ event-simulator parity and does not cover repair schedules or heldout maps.
- Follow-up: align fallback semantics if fallback metric parity becomes a claim, expand to larger/randomized windows, then replace the compact replay with the full C++ event scheduler.

## 2026-06-17 10:20 - Phase8 native C++ scaling diagnostic

- Request: Continue hardening Phase8 after a Python/C++ runtime exception surfaced during larger-window replay probes.
- Branch: `codex/czr005-rewrite`.
- Files changed: added runtime-predict exception fallback in `src/czr005/eval/shadow.py`, added a regression test in `tests/test_phase5_shadow.py`, exposed Python-compatible goal-node overlap configuration for compact C++ replay, added `scripts/eval/run_phase8_native_cpp_scaling_diagnostic.py`, regenerated the Phase8 native replay smoke outputs, and generated `outputs/tables/phase8_native_cpp_scaling_diagnostic.csv` plus `outputs/reports/phase8_native_cpp_scaling_diagnostic_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 native C++ replay smoke, Phase8 native C++ / Python parity diagnostic, and Phase8 native C++ scaling diagnostic.
- Key observations: The runtime EdgeScore Python policy now falls back to the shortest-safe policy if the C++ runtime model raises during prediction, preventing the observed interpreter crash path. EdgeScore small-window parity remains strict PASS. Larger 24/32/48/64 task windows remain no-crash and zero-conflict, but compact C++ replay diverges from Python in planned counts and decision counts once fallback-heavy states appear.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `32 passed`; Phase8 native replay smoke passed with `80/80` accounted tasks and zero conflicts; Phase8 parity diagnostic passed with `edge_strict_pass=True`; Phase8 scaling diagnostic passed safety gates and recorded `4/4` expected divergence rows.
- Safety / parity notes: The larger-window report is explicitly diagnostic, not a strict parity claim. The divergence should be closed by aligning fallback execution/task cleanup semantics or by replacing the compact replay with the full C++ event scheduler.
- Follow-up: add trace-level localization for the first larger-window mismatch, then implement the full C++ event scheduler and rerun this diagnostic on repair and heldout schedules.

## 2026-06-17 10:55 - Phase8 native C++ trace localization

- Request: Continue the Python/C++ rewrite work by turning the larger-window compact replay divergence into a concrete implementation target.
- Branch: `codex/czr005-rewrite`.
- Files changed: added decision-level trace rows to `cpp/ics_core/runtime/edge_score_replay.hpp`, exposed `edge_score_native_replay_trace` through pybind, expanded the pybind smoke test, added `scripts/eval/run_phase8_native_cpp_trace_diagnostic.py`, generated `outputs/tables/phase8_native_cpp_trace_first_mismatch.csv`, `outputs/tables/phase8_native_cpp_trace_context.csv`, and `outputs/reports/phase8_native_cpp_trace_diagnostic_report.md`, and refreshed native replay/scaling outputs.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 native trace diagnostic, Phase8 native scaling diagnostic, Phase8 native C++ / Python parity diagnostic, and Phase8 native replay smoke.
- Key observations: The compact C++ replay now counts and traces unplanned no-safe-action attempts as decision attempts, matching the Python environment's step accounting more closely. The first larger-window divergence is localized at decision `216` on task `17:storage_in`: Python executes a safe `46 -> 35` move, while compact C++ reports `unplanned/no_safe_action` from the same node and ready time. This points the next fix at C++ candidate safety / reservation semantics, not EdgeScore inference.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `32 passed`; Phase8 trace diagnostic passed safety gates; Phase8 parity diagnostic kept `edge_strict_pass=True`; Phase8 scaling diagnostic still reports zero conflicts with expected larger-window divergence.
- Safety / parity notes: This is localization evidence, not a final parity claim. Small-window EdgeScore parity remains strict; larger-window compact replay parity remains open until the C++ candidate safety semantics are aligned or replaced by the full event scheduler.
- Follow-up: inspect the C++ vs Python node/edge reservation state at task `17:storage_in`, decision `216`, then either align compact replay safety checks or move the full event scheduler implementation forward.

## 2026-06-17 11:30 - Phase8 compact replay safety parity alignment

- Request: Continue closing the Python/C++ compact native replay divergence exposed by the Phase8 trace diagnostic.
- Branch: `codex/czr005-rewrite`.
- Files changed: added Python `unreachable_goal` action-mask safety with a regression test, propagated `require_reachable_goal` through the observation/env layer, added C++ `EdgeReservationTable::remove_task`, cleaned node/edge reservations on C++ unplanned-task exits, fixed Python trace task-decision indexing, and refreshed Phase8 parity/scaling/trace/native replay reports and CSVs.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 native trace diagnostic, Phase8 native scaling diagnostic, Phase8 native C++ / Python parity diagnostic, and Phase8 native replay smoke.
- Key observations: The old first mismatch at task `17:storage_in`, decision `216` was caused by Python missing the shield's no-route-to-goal check. After aligning that rule, the next mismatch exposed stale C++ reservations from unplanned tasks; clearing node/edge reservations on C++ unplanned exits removed it. The 24-task decision trace now matches exactly, and 24/32/48/64 larger-window aggregate parity is PASS with zero mean-travel difference and zero post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `33 passed`; Phase8 trace diagnostic reports 24-task decision trace parity PASS; Phase8 scaling diagnostic reports `divergences=0`; Phase8 parity diagnostic reports EdgeScore and fallback strict replay parity PASS; Phase8 native replay smoke passed with zero conflicts.
- Safety / parity notes: This closes the compact-replay same-map parity gap for the configured windows, but it is still not the final high-throughput C++ event scheduler and does not cover repair-event schedules, randomized density, or heldout maps.
- Follow-up: expand trace/scaling parity to repair and randomized schedules, then implement the full C++ event scheduler required for final runtime claims.

## 2026-06-17 12:05 - Phase8 offset/fault compact replay parity

- Request: Broaden compact native replay parity beyond first-window same-map cases before moving to full event-scheduler claims.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `task_offset` support to `EdgeScoreReplayConfig` and pybind replay/trace/fallback entry points, expanded the pybind smoke test, added `scripts/eval/run_phase8_native_cpp_offset_fault_parity.py`, and generated `outputs/tables/phase8_native_cpp_offset_fault_parity.csv` plus `outputs/reports/phase8_native_cpp_offset_fault_parity_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 offset/fault parity diagnostic, Phase8 native scaling diagnostic, Phase8 native trace diagnostic, Phase8 native C++ / Python parity diagnostic, and Phase8 native replay smoke.
- Key observations: Compact C++ replay now runs arbitrary windows from the legacy task stream. Eight 24-task windows, mixing deterministic offsets and fixed-seed randomized offsets with static fault edges, matched the Python junction environment exactly on planned/unplanned counts, decision counts, mean travel time, and post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `33 passed`; Phase8 offset/fault parity reports `8/8` strict PASS rows; existing Phase8 scaling remains `divergences=0`; trace parity remains PASS.
- Safety / parity notes: This strengthens same-map static-fault compact replay evidence. It still does not cover repair-event schedules, heldout maps, randomized synthetic maps, or the final high-throughput C++ event scheduler.
- Follow-up: add repair-event semantics and heldout/randomized-map parity gates, then replace compact replay with the full C++ event scheduler.

## 2026-06-17 12:35 - Phase8 repair-window compact replay parity

- Request: Add repair-event schedule semantics to the Python/C++ compact replay parity path before moving to broader heldout and event-scheduler work.
- Branch: `codex/czr005-rewrite`.
- Files changed: added time-bounded `fault_windows` support to Python action-mask/observation/env layers, added C++ `EdgeFaultWindow` support and active-fault evaluation in native replay, exposed repair windows through pybind replay/trace/fallback entry points, expanded Python/C++/pybind tests, added `scripts/eval/run_phase8_native_cpp_repair_parity.py`, and generated `outputs/tables/phase8_native_cpp_repair_parity.csv` plus `outputs/reports/phase8_native_cpp_repair_parity_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 repair-window parity diagnostic, Phase8 offset/fault parity diagnostic, Phase8 native C++ / Python parity diagnostic, Phase8 native trace diagnostic, and Phase8 native scaling diagnostic.
- Key observations: Both Python and C++ now treat a repair window as active when `fault_start <= ready_time < repair_time`, unioned with any static fault edges for that decision. Four 24-task same-map repair-window rows matched exactly on planned/unplanned counts, decision counts, mean travel time, and post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `34 passed`; Phase8 repair parity reports `4/4` strict PASS rows; existing offset/fault parity still reports `8/8` strict PASS rows; existing trace/scaling diagnostics still pass.
- Safety / parity notes: This validates compact replay repair-window semantics, not the full Java route-update behavior or final high-throughput C++ event scheduler. Heldout-map and randomized-map repair validation remain open.
- Follow-up: add heldout/randomized repair schedule gates, then implement the full C++ event scheduler required for final runtime claims.

## 2026-06-17 13:05 - Phase8 randomized synthetic compact replay parity

- Request: Continue broadening Python/C++ runtime parity toward the master-plan gates for randomized controls, density variation, and fault/repair schedules.
- Branch: `codex/czr005-rewrite`.
- Files changed: added pybind in-memory graph/task record replay entry points, added record-trace support for diagnostics, expanded pybind smoke coverage, exposed C++ reservation intervals, aligned C++ start-node waiting with Python interval skipping, changed C++ mean travel time to use `finish_time - task.pass_time`, added `scripts/eval/run_phase8_native_cpp_randomized_parity.py`, and generated `outputs/tables/phase8_native_cpp_randomized_parity.csv` plus `outputs/reports/phase8_native_cpp_randomized_parity_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 randomized synthetic parity diagnostic, Phase8 repair-window parity diagnostic, Phase8 offset/fault parity diagnostic, Phase8 native C++ / Python parity diagnostic, Phase8 trace diagnostic, and Phase8 scaling diagnostic.
- Key observations: The randomized synthetic gate initially exposed two real compact-replay parity gaps: C++ start-node waiting advanced by fixed hold steps instead of jumping to the conflicting interval end, and C++ mean travel time excluded pre-start waiting. After alignment, four fixed-seed synthetic directed ICS-like maps with varied density, static faults, and repair windows matched Python exactly on planned/unplanned counts, decision counts, mean travel time, and post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `34 passed`; randomized synthetic parity reports `4/4` strict PASS rows; repair-window parity reports `4/4` strict PASS rows; offset/fault parity reports `8/8` strict PASS rows; trace and scaling diagnostics still pass.
- Safety / parity notes: This is randomized synthetic-map compact replay evidence, not a real heldout airport map and not the final high-throughput C++ event scheduler. It adds a stronger regression gate for future scheduler work because synthetic graphs are passed directly through the in-memory pybind API.
- Follow-up: add persisted heldout-map fixtures or generated-map manifests, then carry these randomized schedules into the full C++ event scheduler.

## 2026-06-17 13:20 - Phase8 persisted synthetic replay manifest

- Request: Turn the randomized synthetic parity cases into reusable heldout-like fixtures so future Python/C++ and scheduler gates can share exactly the same maps, tasks, and fault schedules.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `scripts/eval/phase8_synthetic_replay_cases.py`, added `scripts/eval/generate_phase8_synthetic_replay_manifest.py`, generated `data/processed/phase8/phase8_synthetic_replay_cases.json`, rewrote `scripts/eval/run_phase8_native_cpp_randomized_parity.py` to read the persisted manifest, updated `outputs/reports/phase8_native_cpp_randomized_parity_report.md`, and added `tests/test_phase8_synthetic_manifest.py`.
- Commands run: generated the Phase8 synthetic replay manifest, ran the manifest-backed randomized parity diagnostic, target Python pytest, and target CTest.
- Key observations: The persisted manifest contains four fixed-seed directed ICS-like synthetic maps and `84` total tasks with static and repair-window fault schedules. The randomized parity gate still reports `4/4` strict PASS rows after loading from the manifest rather than regenerating in the diagnostic script.
- Tests / validation: target Python pytest passed `35 passed`; target CTest passed 2/2; manifest-backed randomized parity passed with `strict_pass=True`.
- Safety / parity notes: This is a persisted synthetic heldout-like fixture set, not a real airport heldout map. It improves reproducibility and gives the future full C++ event scheduler a concrete shared input manifest.
- Follow-up: reuse this manifest in the full scheduler gate, then add real heldout-map fixtures if/when available.

## 2026-06-17 13:45 - Phase8 native C++ event-queue replay smoke

- Request: Start replacing compact sequential replay with an event-queue C++ scheduler path required by the runtime phase.
- Branch: `codex/czr005-rewrite`.
- Files changed: added event-arrival and decision-event scheduling to `cpp/ics_core/runtime/edge_score_replay.hpp`, exposed EdgeScore and fallback event replay summaries through pybind record APIs, expanded C++ and pybind smoke coverage, updated `cpp/ics_core/README.md`, added `scripts/eval/run_phase8_native_cpp_event_scheduler_smoke.py`, and generated `outputs/tables/phase8_native_cpp_event_scheduler.csv` plus `outputs/reports/phase8_native_cpp_event_scheduler_report.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase8 event scheduler smoke, manifest-backed randomized parity, repair-window parity, offset/fault parity, scaling diagnostic, and trace diagnostic.
- Key observations: The first native C++ event scheduler processes task arrivals by `pass_time`, interleaves active bag decisions by ready time, applies the C++ `JunctionShield`, updates node/edge reservations, and honors repair-window fault schedules. On the four persisted synthetic schedules, both EdgeScore-event and fallback-event rows accounted for all configured tasks with zero post-shield conflicts.
- Tests / validation: CMake build succeeded; target CTest passed 2/2; target Python pytest passed `35 passed`; event scheduler smoke reported `8` safety-pass rows; existing randomized, repair, offset/fault, scaling, and trace gates still pass.
- Safety / parity notes: This is the first event-queue runtime path, but it is not yet a final paper-grade high-throughput scheduler claim. Compact-vs-event aggregate parity is not expected on dense cases because the event scheduler interleaves active bags chronologically.
- Follow-up: add event-level trace diagnostics and a Python event-scheduler reference or equivalent audit, then scale this scheduler over larger persisted manifests and Phase9 baselines.

## 2026-06-17 14:15 - Phase8 native C++ event trace audit

- Request: Continue hardening the native C++ event scheduler beyond summary-only smoke output.
- Branch: `codex/czr005-rewrite`.
- Files changed: exposed EdgeScore and fallback event-scheduler decision traces through pybind record APIs, expanded the pybind smoke test, added `scripts/eval/run_phase8_native_cpp_event_trace_diagnostic.py`, generated `outputs/tables/phase8_native_cpp_event_trace_diagnostic.csv` plus `outputs/reports/phase8_native_cpp_event_trace_diagnostic_report.md`, refreshed the event scheduler smoke outputs, and updated `cpp/ics_core/README.md`.
- Commands run: CMake build through the VS developer environment, target CTest, target Python pytest, Phase8 event trace diagnostic, Phase8 event scheduler smoke, randomized synthetic compact parity, repair-window compact parity, offset/fault compact parity, native trace diagnostic, and native scaling diagnostic.
- Key observations: The event scheduler now exposes auditable decision-level traces for both EdgeScore and fallback policies on persisted synthetic schedules. The diagnostic checks direct scheduler invariants: summary/trace length agreement, chronological global ready times, per-task ready-time monotonicity, contiguous global and per-task decision ordinals, candidate-count sanity, post-shield step safety, hold/move semantics, terminal unplanned rows, complete planned/unplanned accounting, and zero post-shield conflicts.
- Tests / validation: CTest passed 2/2; Python pytest passed `35 passed`; event trace diagnostic reported `8` invariant-pass rows; event scheduler smoke reported `8` safety-pass rows; randomized synthetic parity reported `4/4` strict PASS rows; repair parity reported `4/4` strict PASS rows; offset/fault parity reported `8/8` strict PASS rows; existing trace diagnostic still matched and scaling reported `divergences=0`.
- Safety / parity notes: This is an event-level audit of the C++ scheduler itself, not Python event-scheduler trace parity and not final paper-grade throughput validation.
- Follow-up: add a Python event-scheduler reference or equivalent route-update oracle, scale the event trace diagnostic over larger manifests, and carry the audited event path into Phase9 baseline comparisons.

## 2026-06-17 14:45 - Phase8 event scheduler Python/C++ parity

- Request: Close the previous event-trace audit gap by adding a Python event-scheduler reference and comparing it directly with native C++ event replay.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `src/czr005/eval/event_replay.py` as a Python event-queue replay reference, exported `run_event_replay`, added `tests/test_phase8_event_replay.py`, added `scripts/eval/run_phase8_native_cpp_event_parity.py`, generated `outputs/tables/phase8_native_cpp_event_parity.csv` plus `outputs/reports/phase8_native_cpp_event_parity_report.md`, refreshed event scheduler smoke outputs, and updated `cpp/ics_core/README.md`.
- Commands run: target Python pytest, target CTest, Phase8 event scheduler Python/C++ parity diagnostic, Phase8 event trace diagnostic, Phase8 event scheduler smoke, randomized synthetic compact parity, repair-window compact parity, offset/fault compact parity, native trace diagnostic, and native scaling diagnostic.
- Key observations: The Python event reference now uses the same chronological event semantics as native C++: task-arrival events by `pass_time`, active-bag decision events by ready time, start-node waiting, node/edge reservations, repair-window faults, shortest-safe fallback, and C++ runtime-model prediction through the pybind `predict(features, mask)` surface. On the persisted synthetic manifest, EdgeScore-event and fallback-event rows matched C++ exactly on summaries and decision-level traces.
- Tests / validation: Python pytest passed `36 passed`; CTest passed 2/2; event scheduler parity reported `8` strict PASS rows; event trace audit reported `8` invariant PASS rows; event scheduler smoke reported `8` safety PASS rows; randomized synthetic parity reported `4/4` strict PASS rows; repair parity reported `4/4` strict PASS rows; offset/fault parity reported `8/8` strict PASS rows; existing trace diagnostic still matched and scaling reported `divergences=0`.
- Safety / parity notes: This establishes event-level Python/C++ parity on persisted synthetic heldout-like schedules, but it is still not real-airport heldout parity and not final paper-grade high-throughput validation.
- Follow-up: add real heldout-map event parity if fixtures become available, scale event replay over larger manifests, and carry the event scheduler into Phase9 baseline comparisons.

## 2026-06-17 15:20 - Phase2 C++ SIPP parity

- Request: Continue closing Python/C++ port and prerequisite baseline gaps by bringing the Python SIPP baseline into the C++ core.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `cpp/ics_core/routing/sipp.hpp`, extended C++ `EdgeReservationTable` with interval and earliest-start helpers, exposed `sipp_plan_from_records` through pybind, expanded C++ and pybind smoke tests, added `scripts/eval/run_phase2_cpp_sipp_parity.py`, generated `outputs/tables/phase2_cpp_sipp_parity.csv` plus `outputs/reports/phase2_cpp_sipp_parity_report.md`, and updated `cpp/ics_core/README.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase2 C++ SIPP parity diagnostic, Phase8 event scheduler parity, Phase8 event trace diagnostic, randomized synthetic compact parity, repair-window compact parity, and native scaling diagnostic.
- Key observations: The C++ SIPP planner now matches the Python SIPP baseline on timed route rows for clear routing, node-reservation waiting, edge-capacity waiting, edge-headway waiting, fault-edge blocking, and first-task routes from all four persisted synthetic schedules.
- Tests / validation: CTest passed 2/2; Python pytest passed `36 passed`; Phase2 C++ SIPP parity reported `9` strict PASS rows; Phase8 event scheduler parity still reported `8` strict PASS rows; event trace audit still reported `8` invariant PASS rows; randomized synthetic parity reported `4/4` strict PASS rows; repair parity reported `4/4` strict PASS rows; scaling reported `divergences=0`.
- Safety / parity notes: This closes the first C++ SIPP planner parity gate, but it is not yet a full C++ rolling-horizon replay or merge/buffer-aware baseline.
- Follow-up: wrap C++ SIPP into rolling-horizon/batch replay, then compare Phase5/Phase8 policies against the C++ baseline under larger density and fault schedules.

## 2026-06-17 16:00 - Phase2 C++ rolling-horizon SIPP parity

- Request: Continue the Python/C++ port and baseline prerequisites by wrapping the C++ SIPP planner into the Phase2 rolling-horizon replay baseline.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `cpp/ics_core/baselines/rolling_horizon.hpp`, exposed `rolling_horizon_sipp_from_records` through pybind, expanded C++ and pybind smoke tests, fixed Python/C++ rolling-horizon edge reservations to reserve actual traversal windows instead of pre-edge waiting time, added 1e-9 edge-overlap tolerance to Python and C++ edge reservation checks, added `scripts/eval/run_phase2_cpp_rolling_horizon_parity.py`, generated `outputs/tables/phase2_cpp_rolling_horizon_parity.csv` plus `outputs/reports/phase2_cpp_rolling_horizon_parity_report.md`, refreshed Phase2 baseline smoke outputs, and updated `cpp/ics_core/README.md`.
- Commands run: CMake build, target CTest, target Python pytest, Phase2 C++ rolling-horizon parity, Phase2 C++ SIPP parity, Phase2 baseline smoke, Phase8 event scheduler parity, Phase8 event trace diagnostic, randomized synthetic compact parity, repair-window compact parity, offset/fault compact parity, and native scaling diagnostic.
- Key observations: C++ rolling-horizon now matches Python on planned/unplanned summaries and event rows for deadline-priority ordering, static fault blocking, edge-capacity waiting, edge-headway waiting, and all four persisted synthetic schedules. The edge reservation fix removed false post-shield conflicts caused by treating node waiting as edge occupancy and by sub-nanosecond boundary roundoff.
- Tests / validation: CTest passed 2/2; Python pytest passed `36 passed`; Phase2 C++ rolling-horizon parity reported `8` strict PASS rows; Phase2 C++ SIPP parity reported `9` strict PASS rows; Phase2 baseline smoke reported zero post-shield conflicts; Phase8 event scheduler parity still reported `8` strict PASS rows; randomized synthetic parity reported `4/4` strict PASS rows; repair parity reported `4/4` strict PASS rows; offset/fault parity reported `8/8` strict PASS rows; scaling reported `divergences=0`.
- Safety / parity notes: This closes the deterministic C++ rolling-horizon replay parity gate, but it is still sequential task-leg replay rather than active-bag replanning and does not add merge/buffer constraints or recursive PIBT.
- Follow-up: add active-bag/periodic replanning semantics or C++ PIBT-style replay integration, then use the C++ baseline stack in larger Phase9 comparisons.

## 2026-06-17 16:35 - Phase2 C++ PIBT-style one-step parity

- Request: Continue closing Python/C++ baseline parity gaps and investigate the native/Python runtime error surfaced during smoke execution.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `cpp/ics_core/baselines/pibt.hpp`, exposed `pibt_resolve_from_records` through pybind, expanded C++ and pybind smoke coverage, added `scripts/eval/run_phase2_cpp_pibt_parity.py`, generated `outputs/tables/phase2_cpp_pibt_parity.csv` plus `outputs/reports/phase2_cpp_pibt_parity_report.md`, updated README status, and refreshed the Phase2D PIBT one-step report.
- Commands run: CMake build through the VS developer environment, target CTest, target Python pytest, Phase2 C++ PIBT parity, Phase2 C++ SIPP parity, Phase2 C++ rolling-horizon parity, Phase8 event scheduler parity, Phase8 event trace diagnostic, and Phase8 native scaling diagnostic.
- Key observations: The C++ one-step resolver now matches Python on deadline/waiting priority ordering, same-slice merge conflicts, fault-edge fallback, existing node reservations, custom hold duration, and a persisted synthetic manifest slice. The pybind smoke path passed after adding the new binding, so the reproduced command-line route did not trigger the Windows `python.exe` native exception dialog.
- Tests / validation: CTest passed 2/2; Python pytest passed `36 passed`; Phase2 C++ PIBT parity reported `6` strict PASS rows; Phase2 C++ SIPP parity reported `9` strict PASS rows; Phase2 C++ rolling-horizon parity reported `8` strict PASS rows; Phase8 event scheduler parity reported `8` strict PASS rows; event trace audit reported `8` invariant PASS rows; scaling reported `divergences=0`.
- Safety / parity notes: This closes the C++ parity gate for the deterministic one-step PIBT-style shield only. Recursive priority inheritance/backtracking, active-bag replanning integration, merge-group/buffer semantics, real heldout-map event parity, and final paper-grade runtime validation remain pending.
- Follow-up: integrate active-bag/periodic replanning semantics or recursive PIBT-style replay, then carry the C++ baseline stack into larger Phase9 comparisons.

## 2026-06-17 17:05 - Phase2 active-bag replan-cost audit

- Request: Continue closing Python/C++ port and prerequisite baseline gaps from the master plan, especially Phase2C active-bag/replan-cost evidence.
- Branch: `codex/czr005-rewrite`.
- Files changed: added `scripts/eval/run_phase2_active_bag_replanning_audit.py`, generated `outputs/tables/phase2_active_bag_replanning_audit.csv` plus `outputs/reports/phase2_active_bag_replanning_audit_report.md`, updated README status, and linked the new audit from the Phase2 baseline smoke report.
- Commands run: target Python pytest, target CTest through the VS developer environment, Phase8 event scheduler Python/C++ parity, Phase8 event trace diagnostic, and the new Phase2 active-bag replanning audit.
- Key observations: The new audit samples Python and C++ event-queue traces into fixed `5.0s` ticks and reports active-bag pressure, decision ticks, elapsed replay time, decisions per second, task accounting, and post-shield safety. All eight policy/case rows on the persisted synthetic manifest have matching Python/C++ binned active-bag metrics and zero post-shield conflicts.
- Tests / validation: Python pytest passed `36 passed`; CTest passed 2/2; Phase8 event scheduler parity reported `8` strict PASS rows; event trace diagnostic reported `8` invariant PASS rows; Phase2 active-bag audit reported `8` PASS rows.
- Safety / parity notes: This supplies a reproducible replan-cost/active-bag audit over the event scheduler. It is not a true route-discarding periodic SIPP replanner, not recursive PIBT, and not real heldout-map validation.
- Follow-up: implement a true route-discarding periodic replanning baseline if needed, add real heldout-map fixtures when available, and carry active-bag cost metrics into Phase9 comparisons.

## 2026-06-17 17:45 - Phase2 route-discarding periodic SIPP replanning parity

- Request: Continue closing Phase2C by implementing the true route-discarding periodic active-bag replanner that the previous audit explicitly left pending.
- Branch: `codex/czr005-rewrite`.
- Files changed: added Python `PeriodicReplanningBaseline`, added C++ `periodic_replanning.hpp`, exposed `periodic_replanning_sipp_from_records` through pybind, expanded C++/pybind/Python smoke tests, added `scripts/eval/run_phase2_periodic_replanning_parity.py`, generated `outputs/tables/phase2_periodic_replanning_parity.csv` plus `outputs/reports/phase2_periodic_replanning_parity_report.md`, and refreshed Phase2 status docs.
- Commands run: CMake build through the VS developer environment with CTest, target Phase2 pytest, and Phase2 periodic replanning parity.
- Key observations: The new baseline admits active bags on fixed ticks, replans SIPP from each bag's current node, commits only the next hop, discards the remaining planned route, and replans again at the next tick. Python and C++ matched exactly on summary metrics and event streams for active-bag, edge-capacity, static-fault alternate, and persisted synthetic slices.
- Tests / validation: CTest passed 2/2; target Phase2 pytest passed `12 passed`; Phase2 periodic replanning parity reported `5` strict PASS rows with zero post-shield conflicts.
- Safety / parity notes: This closes route-discarding one-step periodic SIPP replanning parity for static-fault schedules. Repair-window periodic replanning, recursive PIBT priority inheritance/backtracking, merge-group/buffer semantics, real heldout-map validation, and final Phase9 large-scale comparisons remain pending.
- Follow-up: extend periodic replanning to repair-window schedules if needed, then continue with recursive PIBT or heldout-map/runtime validation.
