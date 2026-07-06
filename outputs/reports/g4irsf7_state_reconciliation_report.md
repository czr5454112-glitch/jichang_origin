# G4IRSF7 State Reconciliation Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
committed_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
remote_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Audit | Status | Details |
| --- | --- | --- |
| remote_head_is_g4irsf6 | PASS | G4IRSF7 starts from the pushed G4IRSF6 baseline f7772c1. |
| legacy_java_clean | PASS | Original Java project is read-only; only evidence is extracted. |
| real_main_map_clean | PASS | All speed maps are derived artifacts, never edits to data/processed/maps/map2.json. |
