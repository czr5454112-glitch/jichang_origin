# G4IRSF7 Java Runtime Minimal Runner Report

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

| Attempt | Status | Notes |
| --- | --- | --- |
| dependency_inventory_original_project | PASS | Read-only inventory from original project path. |
| compile_original_project_java | PASS | Class output stays in a temp directory; original project is not modified. |
| run_original_project_RUN_Main_headless | BLOCKED | Swing GUI entrypoint is expected to block paper-grade Java runtime in headless mode. |
| run_temp_headless_astar_probe | PASS | This proves static Java A* can run headlessly; it is not the full Java/CIE scheduler baseline. |
| compile_original_project_with_external_stub_gui | PASS | Original sources are not modified; original ICS_GUI.java is excluded and replaced by a temp stub class. |
| run_external_stub_gui_RUN_Main | BLOCKED_TIMEOUT | Stub removes the JFrame blocker but does not complete a trustworthy full Java/CIE paper runtime within timeout. |
| g4irsf7_first_n_epoch_release_evidence | EVIDENCE_ONLY | Tasks.generate_tasks proves per-source one-head-per-epoch release; full RUN.Main still blocked by GUI/time horizon. |

Java/CIE progress is recorded, but Java blockage does not block engineering THT gap closure.
