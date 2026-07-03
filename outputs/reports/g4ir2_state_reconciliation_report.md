# G4IR2 State Reconciliation Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Audit

| Check | Status | Local | Remote/Recorded |
| --- | --- | --- | --- |
| current_branch | INFO | codex/czr005-rewrite | origin/codex/czr005-rewrite |
| local_head | INFO | 5d4be59617284ae240e43a2a6de2663c494bb979 | 5d4be59617284ae240e43a2a6de2663c494bb979 |
| head_matches_upstream_tracking_ref | PASS | 5d4be59 | 5d4be59 |
| head_is_ancestor_of_upstream | PASS | True | origin/codex/czr005-rewrite |
| working_tree_status | WARN | M cpp/ics_core/bindings/czr005_cpp.cpp |  M scripts/eval/g4i_runtime.py |  M src/czr005/cpp_backend.py | ?? outputs/tables/g4ir2_git_state_audit.csv | ?? scripts/eval/g4ir2_baseline_fairness.py | ?? scripts/eval/g4ir2_edge_diagnostic_audit.py | ?? scripts/eval/g4ir2_no_leakage_runtime.py | ?? scripts/eval/g4ir2_optimization_sweep.py | ?? scripts/eval/g4ir2_policy_ablation_quality.py | ?? scripts/eval/g4ir2_runtime.py | ?? scripts/eval/g4ir2_runtime_profile.py | ?? scripts/eval/g4ir2_scale_stress.py | ?? scripts/eval/g4ir2_state_reconciliation.py |  |
| legacy_java_no_diff | PASS |  |  |
| g4i_report_recorded_heads | WARN | 5d4be59 | ['b3d2296'] |
| recent_log | INFO | 5d4be59 eval: add g4i full cpp runtime audit | b3d2296 eval: add g4h no-astar cpp runtime audit | dc3891b eval: add g4g no-astar fallback stress audit | 7fdf7c0 eval: add g4f no-astar fallback audit | 4599f9b eval: add g4e fallback reduction audit | 597b9b9 eval: add g4d large-window runtime audit | 678c169 eval: add g4c failure-driven aggregation | 5d7ebad eval: add g4 cie retry policy pilot |  |

## Interpretation

This step reconciles the local HEAD, the configured upstream tracking ref, G4I report metadata, and legacy Java cleanliness before running new runtime benchmarks.
A WARN is retained when metadata was produced before the current G4IR2 files were generated or when the tracking ref is not enough to prove a remote GitHub Actions run.
