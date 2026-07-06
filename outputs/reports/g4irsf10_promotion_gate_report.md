# G4IRSF10 Promotion Gate Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `b2e3d799a8107f06dfb97ef9e102b03f29503719`
committed_head_at_generation: `b2e3d799a8107f06dfb97ef9e102b03f29503719`
remote_head_at_generation: `b2e3d799a8107f06dfb97ef9e102b03f29503719`
policy_id: `model_plus_pibt_lite_java_source_queue_v2_safe`
release_semantics: `java_source_queue_one_per_epoch`
reservation_semantics: `baseline`
tth_denominator: `java_release_time_tth`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
v2_open_used_for_paper_claim: false
g4j_opened: false

| Gate | Status | Notes |
| --- | --- | --- |
| state_clean | PASS | Git/protected file state recorded. |
| v2_safe_freeze_revalidated | PASS | v2-safe bundle remains the conservative candidate. |
| paper_protocol_repeats_stable | PASS | paper main 2.5 repeat x5 stable, 0 conflict, 0 full A*. |
| paper_protocol_matrix_complete | PASS | repeat x5 + speed 4 + dynamic/static 12 + fault 16. |
| high_flow_core_matrix_complete | PASS | 1x/2x/4x/8x no-fault scale ladder complete. |
| high_flow_optional_boundaries_recorded | PASS | 16x, 32x smoke, and rolling rows either executed or explicitly recorded as blocker/not-run. |
| hard_case_dataset_generated | PASS | hard cases seen=5731536, written=50000 |
| v3_training_protocol_generated | PASS | Lightweight supervised/ranking protocol only. |
| no_leakage_pass | PASS | Forbidden teacher/future/post-hoc inputs excluded. |
| fault_branch_plan_defined | PASS | Fault branch separate from v2-safe paper claim. |
| legacy_map_inputdata_clean | PASS | Protected files unchanged. |
| g4j_closed | PASS | G4J remains closed. |
