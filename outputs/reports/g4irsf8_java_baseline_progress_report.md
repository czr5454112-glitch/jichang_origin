# G4IRSF8 Java Baseline Progress Report

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

Java baseline remains a separate integration track. G4IRSF8 adds source queue trace extraction but does not modify legacy Java.

| Attempt | Status | Notes |
| --- | --- | --- |
| dependency_inventory_original_project | PASS | Read-only inventory from original project path. |
| compile_original_project_java | PASS | Class output stays in a temp directory; original project is not modified. |
| run_original_project_RUN_Main_headless | BLOCKED | Swing GUI entrypoint is expected to block paper-grade Java runtime in headless mode. |
| run_temp_headless_astar_probe | PASS | This proves static Java A* can run headlessly; it is not the full Java/CIE scheduler baseline. |
| compile_original_project_with_external_stub_gui | PASS | Original sources are not modified; original ICS_GUI.java is excluded and replaced by a temp stub class. |
| run_external_stub_gui_RUN_Main | BLOCKED_TIMEOUT | Stub removes the JFrame blocker but does not complete a trustworthy full Java/CIE paper runtime within timeout. |
| g4irsf8_source_queue_trace_extraction | EVIDENCE_ONLY | Trace extraction supports denominator audit without modifying legacy Java. |
