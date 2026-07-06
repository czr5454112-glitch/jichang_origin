# G4IRSF8 State Reconciliation Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `ab835c53e589fd8463675ea5901086f2f86a2648`
committed_head_at_generation: `ab835c53e589fd8463675ea5901086f2f86a2648`
remote_head_at_generation: `ab835c53e589fd8463675ea5901086f2f86a2648`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Audit | Status | Details |
| --- | --- | --- |
| remote_head_matches_g4irsf7_start | PASS | G4IRSF8 starts from the pushed G4IRSF7 baseline. |
| legacy_java_clean | PASS | Original Java remains read-only. |
| real_main_map_and_inputdata_clean | PASS | Derived maps/tasks are allowed; real processed map and inputdata are not edited. |
