# G4IRSF6 Java Baseline Progress Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
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

The full Java/CIE paper runtime remains unavailable as a claim-grade baseline. Static A* and temp-stub probes are explicitly recorded as proxies only.
