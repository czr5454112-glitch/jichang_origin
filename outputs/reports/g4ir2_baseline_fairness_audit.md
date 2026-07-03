# G4IR2 Baseline Fairness Audit

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Responsibility Matrix

| System | Role | Full A* | Trace | Notes |
| --- | --- | --- | --- | --- |
| verified_cie_java_original | semantic_teacher_and_original_reference_not_directly_timed_here | True | unknown | Legacy Java remains read-only in G4IR2. |
| static_astar_proxy_lower_bound | lower_bound_proxy_only | True | False | A hard baseline for path-planning kernel cost, not scheduler parity. |
| python_reference_no_astar | fair_no_astar_algorithmic_reference | False | True | Same G4I no-A* loop, Python implementation. |
| cpp_trace500_tasks_profile_off | debug_runtime_mode | False | True | Includes task payload and sample trace overhead. |
| cpp_no_edge_diag_no_final_scan_trace0_summary | latency_floor_diagnostic_not_safety_report_mode | False | False | Edge diagnostic and final audit disabled only for bottleneck isolation. |

## Speed Scorecard

| Comparison | Status | Candidate Mean | Baseline Mean | Speedup |
| --- | --- | --- | --- | --- |
| optimized_cpp_vs_python_reference | PASS | 0.38162104 | 8.63101872 | 22.61672658299972 |
| optimized_cpp_vs_static_astar_lower_bound_proxy | FAIL | 0.38162104 | 0.12578112 | 0.32959692159530823 |
| debug_cpp_trace500_vs_optimized_cpp | INFO | 0.44381448 | 0.38162104 | 1.16297172713538 |
