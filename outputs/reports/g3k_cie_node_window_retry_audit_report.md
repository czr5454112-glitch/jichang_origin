# G3k CIE Node-Window Retry Audit

Date: 2026-07-02

## 1. Scope

G3k audits the original CIE/Java scheduler behavior before any learning step. The route source is still the verified CIE/Legacy A* code path: node time windows plus active fault edges. `edge_capacity=1` and merge-capacity assumptions are not used as primary constraints; edge overlap is kept only as a diagnostic column.

The Java scheduler keeps `unfinishTasks`: when A* returns an empty path, the task is not discarded. It stays pending and is tried again at a later scheduler time. G3k mirrors that source-wait retry behavior without modifying the legacy Java project.

## 2. Primary reproduction and retry result

| Variant | Planned | Node conflicts | Recovered G3j no-path | Remaining G3j no-path | Diagnostic edge overlaps | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| g3j_primary_single_attempt | 127/144 | 0 | 0 | 17 | 433 | blocker_continue_java_semantics_audit |
| java_retry_tick_1s_max_delay_60s | 144/144 | 0 | 17 | 0 | 556 | g4a_pilot_dataset_candidate |

G3j primary is reproduced at `127/144` planned with `0` node-window conflicts. Under Java-style unfinished-task retry, the recommended variant `java_retry_tick_1s_max_delay_60s` reaches `144/144`, recovers `17/17` G3j no-path cases, and keeps node-window conflicts at `0`.

## 3. Are the 17 no-path cases truly no-path?

No. In this audit they are temporary no-path-at-current-time cases. They recover when source admission waits and CIE/A* is retried at a later scheduler tick. Failed attempts are retained in the timeline table rather than removed from the record.

| Context | Recovered | Remaining | Root cause |
| --- | --- | --- | --- |
| merge_window | 8 | 0 | temporary_node_time_window_blockage_in_merge_named_window_no_merge_constraint_applied |
| no_fault | 1 | 0 | temporary_node_time_window_blockage_recovered_by_source_retry |
| repair_window | 8 | 0 | temporary_node_time_window_blockage_after_repair_window_recovered_by_source_retry |

Repair-window note: the G3j repair-window no-path cases enter after the configured `28->47` repair window has ended, so the recovery is not from bypassing an active fault. It is from waiting until node time windows clear. Merge-window note: the merge-named scenario does not apply merge capacity in primary; its no-path cases are also node-window/source-retry cases.

## 4. Teacher-label decision

The clean teacher direction is source-wait retry plus CIE next-hop labels: `WAIT_AT_SOURCE_RETRY` for the recovered admission attempts, then `MOVE_TO_NEXT_CIE` along the CIE/A* route. No PPO, MAPPO, GNN, Transformer, or broad G4A training is performed in this step.

## 5. G4A pilot gate

Gate: planned `>=132/144` and node-window conflicts `0`, without using edge capacity as a primary constraint. Result: `144/144` planned and `0` node-window conflicts. Recommendation: enter G4A pilot dataset generation under this verified CIE/Java retry scope; do not start broad training from diagnostic edge-capacity assumptions.

## Artifacts

- Retry summary: `outputs/tables/g3k_retry_summary.csv`
- No-path retry timeline: `outputs/tables/g3k_no_path_retry_timeline.csv`
- Recovered cases: `outputs/tables/g3k_recovered_no_path_cases.csv`
- Remaining cases: `outputs/tables/g3k_remaining_no_path_cases.csv`
- Java semantics alignment: `outputs/tables/g3k_java_semantics_alignment.csv`
- Teacher label taxonomy: `outputs/tables/g3k_teacher_label_taxonomy.csv`
- Edge-overlap diagnostic only table: `outputs/tables/g3k_edge_overlap_diagnostic_only.csv`
- JSONL teacher sample: `artifacts/teacher/legacy_astar/g3k_cie_retry_teacher_sample.jsonl`
- Figure: `outputs/figures/g3k_retry_recovery_timeline.png`
