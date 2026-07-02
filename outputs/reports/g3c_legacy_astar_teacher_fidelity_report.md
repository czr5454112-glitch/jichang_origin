# G3c Legacy-A* Teacher Fidelity Audit

Date: 2026-07-02

## Scope

This diagnostic audits whether the paper-faithful Legacy A* route source can be converted into per-junction imitation labels and replayed under the current Python event environment and hard shield. It is not model training, not PPO/MAPPO, and not a learning-success claim.

- teacher_source: `python_faithful_legacy_astar_event_trace`
- parity_verifier: `existing_java_cpp_phase1_legacy_acceptance`
- map: `data/processed/maps/map2.json`
- tasks: `data/processed/tasks/inputdata.jsonl`
- sampled teacher trace: `artifacts/teacher/legacy_astar/g3c_legacy_astar_teacher_sample.jsonl`

## Java/C++ Teacher Source Check

G3c did not modify the read-only legacy Java tree and did not add a new Java GUI/headless harness. It uses the existing Phase1/legacy acceptance artifacts as verifier evidence, then generates the event decision trace with the Python legacy-compatible A* implementation.

| Verifier | Rows | Pass | Role |
| --- | --- | --- | --- |
| legacy_java_astar | 8000 | True | source_of_truth_path_spotcheck |
| legacy_java_ics_legacy_no_fault_window | 63 | True | legacy_scheduler_window_spotcheck |
| legacy_java_ics_legacy_scheduled_fault_window | 63 | True | legacy_scheduler_window_spotcheck |
| legacy_java_ics_legacy_probability_extreme_window | 62 | True | legacy_scheduler_window_spotcheck |

## Replay Safety

| Scenario | Planned | Decisions | Candidate Recall | Safe Recall | Conflicts | Blocked |
| --- | --- | --- | --- | --- | --- | --- |
| legacy_first16 | 14/16 | 168 | 1.000 | 0.696 | 0 | edge_capacity:51 |
| legacy_first16_buffer2 | 14/16 | 168 | 1.000 | 0.696 | 0 | edge_capacity:51 |
| legacy_first32 | 21/32 | 335 | 1.000 | 0.637 | 0 | edge_capacity:120;legacy_astar_no_path:4 |
| legacy_offset32_static16 | 9/16 | 190 | 1.000 | 0.598 | 0 | edge_capacity:74;legacy_astar_no_path:6 |
| legacy_offset64_repair32 | 10/32 | 326 | 1.000 | 0.562 | 0 | edge_capacity:137;legacy_astar_no_path:13 |
| legacy_offset64_merge32 | 10/32 | 322 | 1.000 | 0.541 | 0 | edge_capacity:73;edge_capacity+merge_group:35;legacy_astar_no_path:19;merge_group:31 |

- aggregate planned: `78/144`
- aggregate decisions: `1509`
- aggregate teacher_action_candidate_recall: `1.000`
- aggregate teacher_action_safe_recall: `0.610`
- aggregate unavailable/blocked slices: `614`
- aggregate post-shield conflicts: `0`
- G3 SIPP teacher safe recall reference: `0.319`

## Legacy vs SIPP Teacher Agreement

| Scenario | Shared Decisions | Agreement | Rate | Legacy Planned | SIPP Planned |
| --- | --- | --- | --- | --- | --- |
| legacy_first16 | 149 | 147 | 0.987 | 14 | 16 |
| legacy_first16_buffer2 | 149 | 147 | 0.987 | 14 | 16 |
| legacy_first32 | 268 | 261 | 0.974 | 21 | 32 |
| legacy_offset32_static16 | 141 | 136 | 0.965 | 9 | 16 |
| legacy_offset64_repair32 | 248 | 233 | 0.940 | 10 | 32 |
| legacy_offset64_merge32 | 223 | 205 | 0.919 | 10 | 32 |

## Teacher Coverage

| Scenario | Node Kind | Decisions | Moves | No Path | Blocked | Safe Recall |
| --- | --- | --- | --- | --- | --- | --- |
| legacy_first16 | all | 168 | 168 | 0 | 51 | 0.696 |
| legacy_first16_buffer2 | all | 168 | 168 | 0 | 51 | 0.696 |
| legacy_first32 | all | 335 | 331 | 4 | 124 | 0.637 |
| legacy_offset32_static16 | all | 190 | 184 | 6 | 80 | 0.598 |
| legacy_offset64_repair32 | all | 326 | 313 | 13 | 150 | 0.562 |
| legacy_offset64_merge32 | all | 322 | 303 | 19 | 158 | 0.541 |

## Interpretation

Legacy A* safe recall (`0.610`) is above the G3 SIPP reference but still leaves enough blocked teacher slices that G3b-style mask/shield/event-horizon diagnosis should run before broad teacher scaling.

## Artifacts

- Java teacher verifier summary: `outputs/tables/g3c_java_teacher_trace_summary.csv`
- C++ teacher verifier summary: `outputs/tables/g3c_cpp_teacher_trace_summary.csv`
- Java/C++ parity summary: `outputs/tables/g3c_java_cpp_teacher_parity.csv`
- Junction slice sample: `outputs/tables/g3c_teacher_junction_slices_sample.csv`
- Replay safety: `outputs/tables/g3c_teacher_replay_safety.csv`
- Legacy vs SIPP agreement: `outputs/tables/g3c_legacy_vs_sipp_teacher_agreement.csv`
- Label coverage: `outputs/tables/g3c_teacher_label_coverage.csv`
- Unavailable cases: `outputs/tables/g3c_teacher_unavailable_cases.csv`
- JSONL sample: `artifacts/teacher/legacy_astar/g3c_legacy_astar_teacher_sample.jsonl`

## Gate Status

- Java/C++ verifier artifact availability: `PASS`
- route-to-decision conversion: `PASS`
- teacher replay conflict accounting: `PASS`
- safe-mask recall compared with G3 SIPP teacher: `PASS`
- overall G3c decision: `DEVELOPMENT_PASS_NEEDS_TARGETED_G3B`

## Next Blocking Question

Are the remaining blocked Legacy-A* labels caused by local mask timing, event-horizon semantics, or missing wait/repair labels?

## Follow-up

- Run G3b mask/shield/event-horizon audit on blocked Legacy-A* slices.
- Add explicit hold/repair labels only if the audit proves route-next labels are temporarily unsafe rather than globally invalid.
- Keep training work paused until replay semantics are clean.
