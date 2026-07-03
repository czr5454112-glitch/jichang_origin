# G4IRSF6 Promotion Gate Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Gate | Status | Notes |
| --- | --- | --- |
| state_reconciled | PASS | G4IRSF5 generation/commit mismatch recorded. |
| paper_tables_reproduced | PASS | Includes THT, TH, speed, dispersed, dynamic/static, fault rows. |
| tth_gap_autopsy_complete | PASS | Bag-level original/no-A* deltas generated. |
| quality_sweep_complete | PASS | Unsafe or incomplete variants rejected. |
| speed_sweep_complete | PASS | Temporary speed map artifacts used. |
| dynamic_static_protocol_complete | PASS | Protocol not mixed with static lower bound. |
| fault_bag_level_complete | PASS | Baggage success rate reported for mapped fault diagnostics. |
| java_baseline_attempts_recorded | PASS | Full Java/CIE remains blocked/proxy-only if not completed. |
| apples_to_apples_v2_complete | PASS | No unsupported winner claim allowed. |
| no_leakage_and_no_full_astar | PASS | Teacher/future schedule not used; full CIE/A* calls remain zero. |
| legacy_and_main_map_clean | PASS | Legacy Java and real main map have no diff. |
| g4j_closed | PASS | No comparable non-inferior paper-main executable baseline; G4J remains closed. |

Promotion result: G4IRSF6 closes the evidence gap, but does not promote G4J. The paper-main winner boundary remains closed.
