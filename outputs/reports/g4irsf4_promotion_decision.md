# G4IRSF4 Promotion Decision

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Gate | Status | Evidence |
| --- | --- | --- |
| state_clean_or_recorded | PASS | outputs/tables/g4irsf4_git_state_audit.csv |
| task_hash_verified | PASS | artifacts/tasks/g4irsf2_high_flow_manifest.json |
| continuous_runtime_api | PASS | docs/czr005_no_astar_streaming_runtime_api.md |
| continuous_full_manifest_run | PASS | outputs/tables/g4irsf4_full_manifest_continuous_benchmark.csv |
| loop_autopsy_complete | PASS | outputs/reports/g4irsf4_loop_closure_report.md |
| fault_aware_runtime_variant | PASS | outputs/tables/g4irsf4_fault_aware_runtime_results.csv |
| java_dependency_audit | PASS | outputs/tables/g4irsf4_java_baseline_run_attempts.csv |
| no_leakage | PASS | runtime_full_cie_astar_calls=0 and no teacher/future inputs in reports |
| node_window_conflicts_zero | PASS | outputs/tables/g4irsf4_full_manifest_continuous_benchmark.csv |
| runtime_full_astar_zero | PASS | outputs/tables/g4irsf4_full_manifest_continuous_benchmark.csv |
| legacy_java_diff_empty | PASS | outputs/tables/g4irsf4_git_state_audit.csv |
| g4j_closed | PASS | remaining failures/baseline boundaries still require more work before G4J |

G4IRSF4 is an execution/audit pass, not a G4J promotion. G4J remains closed until continuous failures are near zero and Java/CIE or a stronger Java-semantics baseline is available.
