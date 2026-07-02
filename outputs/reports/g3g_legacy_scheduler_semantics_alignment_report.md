# G3g Legacy Scheduler Semantics Alignment

Date: 2026-07-02

## 1. Scope

G3g is a non-learning semantics audit. It compares the Legacy Java/Python route-window model, the current local executable G3f replay, and the full-route SIPP scheduler that already has Python/C++ parity evidence. It does not modify legacy Java, does not relax edge capacity, and does not start G4A or training.

## 2. Scheduler comparison

| Scheduler | Planned | Real conflicts | Route scope | Wait model |
| --- | --- | --- | --- | --- |
| g3f_local_executable_capacity_wait_budget_5s | 96/144 | 0 | single_executable_step | local_hold_consumes_current_node_capacity |
| legacy_node_window_full_route | 127/144 | 458 | full_route | timed_node_windows_only_no_explicit_edge_wait_occupancy |
| sipp_full_route_edge_capacity | 144/144 | 0 | full_route | full_route_release_time_search |

The key split is now explicit: the Legacy node-window scheduler can plan more route-intent tasks but is not runtime-safe under edge capacity, while SIPP full-route timing is runtime-safe but is not the paper-faithful Legacy-A* route source. G3f remains the strict local executable teacher and still plans only `96/144`.

## 3. Source-level semantics evidence

| Layer | Route scope | Edge model | Wait model |
| --- | --- | --- | --- |
| legacy_java_astar | reservations | node_window_only | timed_node_windows_only_no_explicit_edge_wait_occupancy |
| legacy_java_scheduler | full_route_saved_constraints | node_window_only | timed_node_windows_only_no_explicit_edge_wait_occupancy |
| python_legacy_astar | reservations | node_window_only | timed_node_windows_only_no_explicit_edge_wait_occupancy |
| python_runtime_mask | local_step_candidate | hard_edge_capacity | immediate_local_transition_check |
| python_runtime_hold | local_step_candidate | hold_occupies_current_node | explicit_hold_consumes_current_node_capacity |
| cpp_sipp_scheduler | full_route_search | hard_edge_capacity | full_route_release_time_search_without_local_hold_label |
| cpp_rolling_horizon | full_route_reservation | hard_edge_capacity | full_route_release_time_search_without_local_hold_label |

## 4. G3f unresolved cases

G3f best-variant unresolved capacity cases: `29`. Cases classified as current-node hold-capacity failures: `29`.

| Scenario | Edge | Cases | Mean nonoccupying wait |
| --- | --- | --- | --- |
| legacy_offset32_static16 | 27->28 | 6 | 4.737 |
| legacy_offset64_repair32 | 18->22 | 6 | 6.431 |
| legacy_offset64_merge32 | 18->22 | 5 | 6.465 |
| legacy_first32 | 18->22 | 3 | 4.201 |
| legacy_offset64_repair32 | 27->28 | 3 | 8.899 |
| legacy_first32 | 27->28 | 2 | 5.188 |
| legacy_first32 | 18->22 | 1 | 4.784 |
| legacy_offset32_static16 | 27->28 | 1 | 4.227 |
| legacy_offset64_merge32 | 27->28 | 1 | 1.960 |
| legacy_offset64_repair32 | 27->28 | 1 | 9.218 |

Top backpressure hotspots:

| Scenario | Edge | Cases | SIPP planned | Same edge in SIPP |
| --- | --- | --- | --- | --- |
| legacy_offset32_static16 | 27->28 | 7 | 7 | 6 |
| legacy_offset64_repair32 | 18->22 | 6 | 6 | 4 |
| legacy_offset64_merge32 | 18->22 | 5 | 5 | 4 |
| legacy_first32 | 18->22 | 4 | 4 | 3 |
| legacy_offset64_repair32 | 27->28 | 4 | 4 | 3 |
| legacy_first32 | 27->28 | 2 | 2 | 2 |
| legacy_offset64_merge32 | 27->28 | 1 | 1 | 0 |

## 5. Decision

Diagnostic pass: G3g explains the remaining G3f capacity blocker as a scheduler-semantics mismatch. The next step should be a backpressure-aware executable teacher or route pre-reservation semantics audit, not G4A/training.

## Artifacts

- Semantics matrix: `outputs/tables/g3g_scheduler_semantics_matrix.csv`
- Hold conflict taxonomy: `outputs/tables/g3g_hold_conflict_taxonomy.csv`
- Current vs upstream wait cases: `outputs/tables/g3g_current_vs_upstream_wait_cases.csv`
- Scheduler replay comparison: `outputs/tables/g3g_scheduler_replay_comparison.csv`
- Full route alignment: `outputs/tables/g3g_full_route_alignment.csv`
- Backpressure hotspots: `outputs/tables/g3g_backpressure_edge_hotspots.csv`
- Next-step gate: `outputs/tables/g3g_next_step_gate.csv`
- Trace JSONL sample: `artifacts/teacher/legacy_astar/g3g_scheduler_semantics_trace_sample.jsonl`
- Gap figure: `outputs/figures/g3g_scheduler_semantics_gap.png`
