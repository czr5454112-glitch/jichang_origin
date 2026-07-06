# G4IRSF9 Java Baseline Progress Report

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

| Attempt | Status | Notes |
| --- | --- | --- |
| dependency_inventory_original_project | PASS | Read-only inventory from original project path. |
| compile_original_project_java | PASS | Class output stays in a temp directory; original project is not modified. |
| run_original_project_RUN_Main_headless | BLOCKED | Swing GUI entrypoint is expected to block paper-grade Java runtime in headless mode. |
| run_temp_headless_astar_probe | PASS | This proves static Java A* can run headlessly; it is not the full Java/CIE scheduler baseline. |
| compile_original_project_with_external_stub_gui | PASS | Original sources are not modified; original ICS_GUI.java is excluded and replaced by a temp stub class. |
| run_external_stub_gui_RUN_Main | BLOCKED_TIMEOUT | Stub removes the JFrame blocker but does not complete a trustworthy full Java/CIE paper runtime within timeout. |
| g4irsf9_touching_interval_semantic_probe | EVIDENCE_ONLY | Probe mirrors audited Java strict >/< predicate and does not modify legacy Java. |
| g4irsf9_v2_safe_freeze_not_blocked_by_java_gui | RECORDED | Full Java/CIE remains needed for final G4J, but does not block v2-safe engineering candidate freeze. |
