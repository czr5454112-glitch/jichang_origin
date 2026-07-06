# G4IRSF9 Promotion Gate Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `3432ef51f97d15045ac02d8632aae97450e9ce1a`
committed_head_at_generation: `3432ef51f97d15045ac02d8632aae97450e9ce1a`
remote_head_at_generation: `3432ef51f97d15045ac02d8632aae97450e9ce1a`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false
real_inputdata_modified: false

| Gate | Status | Notes |
| --- | --- | --- |
| state_clean | PASS | remote/protected file state recorded |
| governance_updated | PASS | No-A* candidate tiering rule added |
| open_end_proof_audit_complete | PASS | java_closed_interval_conflict |
| denominator_evidence_expanded | PASS | source/segment/integrality grouped evidence |
| source_queue_fairness_audit_complete | PASS | one release per source per epoch retained |
| v2_safe_main_pass | PASS | v2-safe beats original project under java_release_time_tth without open-end |
| v2_safe_speed_dynamic_no_material_regression | PASS | speed sweep and dynamic/static diagnostics safe |
| fault_boundary_documented | PASS | fault diagnostics are not mixed into paper-main candidate |
| v2_safe_bundle_frozen | PASS | model_plus_pibt_lite_java_source_queue_v2_safe |
| v2_open_kept_separate | PASS | open candidate is not merged into v2-safe claim |
| legacy_map_inputdata_clean | PASS | protected files unchanged |
| g4j_closed | PASS | G4J still closed |
