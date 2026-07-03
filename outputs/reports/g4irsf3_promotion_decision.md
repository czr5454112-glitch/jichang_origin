# G4IRSF3 Promotion Decision

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Gate

| Criterion | Status | Evidence |
| --- | --- | --- |
| high_flow_task_hash_verified | PASS | outputs/tables/g4irsf3_high_flow_file_hash_audit.csv |
| full_manifest_task_coverage_by_chunks | PASS | 348824/348824 tasks measured |
| chunked_noastar_zero_conflict_zero_astar | FAIL | planned=348098/348824; conflicts=0; full_astar=0 |
| continuous_full_manifest_state | FAIL | chunk carry-over API missing; single-call full streaming blocked |
| fault_aware_upstream_avoidance_promoted | FAIL | best improvement is shadow-only |
| original_java_cie_baseline_runnable | FAIL | see g4irsf3_java_baseline_run_attempts.csv |
| astar_hardness_v2 | FAIL | static A* lower-bound remains faster; Java runner unavailable |
| g4irsf3_execution_complete | PASS | Audit artifacts generated and negative results preserved. |
| g4irsf3_primary_success_gate | FAIL | Full manifest has remaining no-A* failures and promotion blockers; do not claim success. |
| g4j_paper_grade_gate | FAIL | Do not enter final replacement claim until continuous state, promoted fault-aware runtime, Java/CIE baseline, and A* hardness are resolved. |

G4IRSF3 execution is complete as an honest engineering audit, but the primary success gate and paper-grade G4J gate remain failed. This is intentional: the blockers are now explicit instead of hidden.
