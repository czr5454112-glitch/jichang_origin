# G4IR2 C++ Optimization Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Before/After

| Round | Mode | Mean Seconds | Speedup | Notes |
| --- | --- | --- | --- | --- |
| round0_debug_trace_payload | cpp_trace500_tasks_profile_off | 0.44381448 | 1.0 | G4I-style task payload and trace sample. |
| round1_summary_payload | cpp_trace0_summary_profile_off | 0.41133962 | 1.078949020276724 | Remove task/trace payload from timed path. |
| round2_edge_diag_off | cpp_no_edge_diag_trace0_summary | 0.39282838 | 1.1297923026844445 | Disable diagnostic-only edge overlap scan. |
| round3_final_scan_off | cpp_no_final_scan_trace0_summary | 0.39568538 | 1.1216347695232005 | Disable final full conflict scan for latency isolation. |
| round4_combined_latency_floor | cpp_no_edge_diag_no_final_scan_trace0_summary | 0.38162104 | 1.16297172713538 | Combined latency floor; not the standalone safety-reporting mode. |

## Guardrails

| Round | Status | Planned | Conflicts | Full A* | Details |
| --- | --- | --- | --- | --- | --- |
| round0_debug_trace_payload | PASS | 4449 | 0 | 0 | same planned count and zero runtime full A* |
| round1_summary_payload | PASS | 4449 | 0 | 0 | same planned count and zero runtime full A* |
| round2_edge_diag_off | PASS | 4449 | 0 | 0 | same planned count and zero runtime full A* |
| round3_final_scan_off | PASS | 4449 | 0 | 0 | same planned count and zero runtime full A* |
| round4_combined_latency_floor | PASS | 4449 | 0 | 0 | same planned count and zero runtime full A* |

Modes with the final scan disabled are latency diagnostics only. Safety reporting still uses modes where the final conflict audit is enabled.
