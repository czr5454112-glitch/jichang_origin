# G4IRSF11 Java/CIE Boundary Audit

Boundary status: `PARTIAL_WITH_EXPLICIT_BLOCKER`.
G4J: `CLOSED` (opened=false).

## Result

The repository contains a genuine non-GUI external Java wrapper that directly runs the read-only `Tasks.generate_tasks` and `ICS_PathFinding` lifecycle. Its accepted evidence is a bounded 64-task first-N window. It is not a full Java/CIE paper baseline, and Python/C++ parity/proxy rows are not counted as Java.

## Gates

| Criterion | Status | Observed | Required |
| --- | --- | --- | --- |
| protected_legacy_map_input_clean | PASS | clean | no worktree or baseline diff under legacy/map/inputdata |
| legacy_java_lifecycle_identified | PASS | {"harness_imports_legacy_scheduler": true, "harness_is_non_gui": true, "harness_records_route_state": true, "harness_runs_epoch_loop": true, "main_calls_generate_tasks": true, "main_calls_ics_path_finding": true, "main_gui_coupled": true, "scheduler_has_saved_routes": true, "scheduler_has_unfinished_retry": true, "scheduler_rebuilds_constrains": true, "tasks_one_head_per_source_epoch": true} | GUI boundary plus Tasks.generate_tasks and ICS_PathFinding lifecycle present |
| external_non_gui_java_cie_wrapper | PASS | true | external Java class directly invokes read-only Tasks and ICS_PathFinding without showmap |
| java_source_queue_trace_complete | PASS | 43603 | 43603 |
| first_n_epoch_real_java_cie_evidence | PASS | 3 real Java windows; max generated=64 | at least one non-GUI external Java ICS_PathFinding first-N run |
| first_n_java_source_saved_routes_constrains_trace | FAIL | source release trace exists; Java windows persist route/summary snapshots but not per-epoch constrains deltas | first-N per-epoch source queue, saved_routes before/after, constrains before/after |
| full_java_cie_scope | FAIL | full candidates=0; bounded Java windows=3 | >=43603 generated, >=28506 completed, active=0, unfinished=0 |
| full_java_source_saved_routes_constrains_trace | FAIL | no accepted per-epoch full-run saved_routes/constrains delta artifact | source queue plus saved_routes/constrains before/after for first N and full run |
| full_java_exact_command_returncode_manifest | FAIL | missing | exact javac/java or Java-orchestrating command, return code 0, hashes, full-scope counts |
| python_cpp_proxy_excluded_from_java_identity | PASS | all cpp_pybind/static_astar/noastar rows are classified non-Java or lower-bound | no Python/C++ proxy accepted as Java |
| accepted_headless_java_cie_full_baseline | FAIL | false | all full-scope, identity, command, trace, and protected-file checks PASS |
| g4j_closed | PASS | CLOSED | CLOSED |

## Explicit blockers

- external GUI-stub RUN.Main attempt timed out without an accepted result
- no accepted first-N/full-run source queue + saved_routes + constrains delta trace
- no full-run manifest records exact command, return code 0, input/output hashes, and full-scope counts
- no headless Java/CIE run covers 28506 raw bags / 43603 Java segments and drains active/unfinished state
- original RUN.Main headless full attempt remains blocked by Swing/HeadlessException
- real external Java/CIE evidence is bounded to 64 generated tasks (first-N), not the full 28,506-bag stream

## Exact reproduction commands

First-N Java/CIE evidence (Python only orchestrates javac/java plus the separate C++ parity row):

```text
C:\Users\38908\.conda\envs\czr005\python.exe C:\PROGRAMING\czr005\scripts\eval\run_java_cpp_legacy_window_performance.py --start-epoch 8260 --max-epochs 5000 --max-new-tasks 64 --repeats 3 --java-warmup-repeats 1 --cpp-warmup-repeats 1 --cpp-python-path C:\PROGRAMING\czr005\build_vs\python\Release
```

Required full attempt; this command is recorded but was not executed or accepted by this audit:

```text
C:\Users\38908\.conda\envs\czr005\python.exe C:\PROGRAMING\czr005\scripts\eval\run_java_cpp_legacy_window_performance.py --start-epoch 8260 --max-epochs 90000 --max-new-tasks 0 --repeats 1 --java-warmup-repeats 0 --cpp-warmup-repeats 0 --cpp-python-path C:\PROGRAMING\czr005\build_vs\python\Release
```

A future full result must additionally persist the Java subprocess command and return code, input/output hashes, all 43,603 Java release segments, drained active/unfinished state, and per-epoch source queue / saved_routes / constrains deltas. Merely running the command does not pass.

## Evidence identity

| Classification | Rows | Accepted full |
| --- | --- | --- |
| G4J_BOUNDARY_RECORD | 1 | 0 |
| JAVA_BUILD_OR_DEPENDENCY_EVIDENCE | 3 | 0 |
| JAVA_CIE_BOUNDED_WINDOW | 3 | 0 |
| JAVA_GUI_FULL_ATTEMPT | 2 | 0 |
| JAVA_SOURCE_SEMANTICS_EVIDENCE | 1 | 0 |
| JAVA_STATIC_ASTAR_PROBE | 2 | 0 |
| JAVA_STUB_GUI_ATTEMPT | 1 | 0 |
| NON_JAVA_PROXY | 4 | 0 |
| ORIGINAL_PROJECT_RESULT_ARTIFACT | 1 | 0 |
| PAPER_REPORTED_RESULT | 1 | 0 |

## Artifacts

- attempts: `outputs/tables/g4irsf11_java_cie_attempt_audit.csv`
- gates: `outputs/tables/g4irsf11_java_cie_boundary_gate.csv`
- evidence inventory with SHA-256: `outputs/tables/g4irsf11_java_cie_evidence_inventory.csv`
- machine status: `outputs/reports/g4irsf11_java_cie_boundary_status.json`

No legacy Java, real map, or real inputdata file is modified by this audit.
