# G4IR2 Runtime Bottleneck Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Repeatability

| Mode | Repeats | Mean Seconds | Planned | Full A* | Notes |
| --- | --- | --- | --- | --- | --- |
| cpp_trace0_summary_profile_off | 5 | 0.4113396199885756 | 4449 | 0 | No trace rows, no task payload, final node-conflict audit on. |
| cpp_trace500_tasks_profile_off | 5 | 0.4438144799787551 | 4449 | 0 | G4I-like trace sample and full task payload. |
| cpp_full_trace_tasks_profile_off | 5 | 0.6532343800179661 | 4449 | 0 | Full decision trace for the G4D planned scope. |
| cpp_profile_on_trace0_summary | 5 | 0.43937247996218504 | 4449 | 0 | Profiler enabled with summary-only payload. |
| cpp_profile_on_trace500_tasks | 5 | 0.48300874000415206 | 4449 | 0 | Profiler enabled with trace sample and task payload. |
| cpp_no_edge_diag_trace0_summary | 5 | 0.39282837994396685 | 4449 | 0 | Diagnostic edge-overlap counter disabled; behavior should not change. |
| cpp_no_final_scan_trace0_summary | 5 | 0.39568538004532455 | 4449 | 0 | Final full conflict scan disabled for latency diagnosis; reservation safety remains active. |
| cpp_no_edge_diag_no_final_scan_trace0_summary | 5 | 0.3816210399847478 | 4449 | 0 | Best latency diagnostic mode; not a safety-reporting mode by itself. |
| cpp_no_file_io_trace0_summary | 5 | 0.3984474600292742 | 4449 | 0 | Timed before writing any G4IR2 files; pybind call only. |
| python_reference_no_astar | 5 | 8.631018719961867 | 4449 | 0 | Python reference loop from G4I parity path. |
| static_astar_proxy_lower_bound | 5 | 0.12578112 | 4449 | 15852 | Measured C++ static A* path proxy scaled to G4D retry attempts; lower-bound proxy, not Java GUI runtime. |

## Top Profiled C++ Stages

| Mode | Stage | Mean | Share |
| --- | --- | --- | --- |
| cpp_profile_on_trace500_tasks | feature_row_computation | 0.11871362000000539 | 0.263884265948652 |
| cpp_profile_on_trace0_summary | feature_row_computation | 0.11753254000000565 | 0.2762245876168739 |
| cpp_profile_on_trace500_tasks | earliest_safe_reservation_lookup | 0.09580518000000374 | 0.21296191286541774 |
| cpp_profile_on_trace0_summary | earliest_safe_reservation_lookup | 0.09572248000000433 | 0.224966656584333 |
| cpp_profile_on_trace500_tasks | model_inference | 0.04579684000000597 | 0.10180015996621863 |
| cpp_profile_on_trace0_summary | model_inference | 0.04520038000000542 | 0.1062297839017764 |
| cpp_profile_on_trace500_tasks | pibt_lite_fallback_scoring | 0.027576160000000117 | 0.061298061159977095 |
| cpp_profile_on_trace0_summary | pibt_lite_fallback_scoring | 0.027264820000000054 | 0.0640776899822632 |
| cpp_profile_on_trace500_tasks | trace_row_construction | 0.020196299999999973 | 0.044893633943422086 |
| cpp_profile_on_trace500_tasks | task_row_construction | 0.016656320000000002 | 0.03702473883456382 |

## Notes

The static A* row is retained as a lower-bound proxy only. It is useful for pressure-testing speed claims, but it is not the verified Java GUI scheduler runtime.
Trace construction, Python task payload construction, edge-overlap diagnostics, and final conflict scanning are measured separately so they cannot be hidden inside one aggregate number.
