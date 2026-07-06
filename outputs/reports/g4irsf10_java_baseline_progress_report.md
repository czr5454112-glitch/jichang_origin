# G4IRSF10 Java Baseline Progress Report

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

| Attempt | Status | Notes |
| --- | --- | --- |
| dependency_inventory_original_project | PASS | Read-only inventory from original project path. |
| compile_original_project_java | PASS | Class output stays in a temp directory; original project is not modified. |
| run_original_project_RUN_Main_headless | BLOCKED | Swing GUI entrypoint is expected to block paper-grade Java runtime in headless mode. |
| run_temp_headless_astar_probe | PASS | This proves static Java A* can run headlessly; it is not the full Java/CIE scheduler baseline. |
| compile_original_project_with_external_stub_gui | PASS | Original sources are not modified; original ICS_GUI.java is excluded and replaced by a temp stub class. |
| run_external_stub_gui_RUN_Main | BLOCKED_TIMEOUT | Stub removes the JFrame blocker but does not complete a trustworthy full Java/CIE paper runtime within timeout. |
| g4irsf10_source_queue_trace_extraction | EVIDENCE_ONLY | Source queue traces support scale validation; Java GUI blocker does not block v2-safe data flywheel. |
| g4irsf10_g4j_boundary | RECORDED | Final G4J still needs accepted Java/CIE or paper-protocol baseline boundary. |

Java/CIE baseline work continues, but it blocks only a final G4J paper-victory claim, not v2-safe scale validation or the v3 data flywheel.
