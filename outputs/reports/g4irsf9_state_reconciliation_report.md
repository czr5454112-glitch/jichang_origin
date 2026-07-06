# G4IRSF9 State Reconciliation Report

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

| Audit | Status | Details |
| --- | --- | --- |
| remote_head_matches_g4irsf8_start | PASS | G4IRSF9 starts from the pushed G4IRSF8 baseline. |
| protected_inputs_clean | PASS | legacy Java, real map2.json, and real inputdata.jsonl are read-only. |
| source_queue_manifest_available | PASS | C:\PROGRAMING\czr005\artifacts\tasks\g4irsf7\java_source_queue_one_per_epoch_manifest.json |
