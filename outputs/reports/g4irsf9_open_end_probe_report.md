# G4IRSF9 Open-End Probe Report

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

Probe category: `java_closed_interval_conflict`.

| Case | Java Conflict | Open-End Conflict | Temp Java |
| --- | --- | --- | --- |
| touching_endpoint | True | False | True |
| strictly_separated | False | False | False |
| overlap | True | True | True |

The temp runner is outside legacy Java and mirrors the audited predicate. It does not modify original source files.
