# G4IRSF11 Claim Boundary

Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`.

G4IRSF10 16x remains a safe-execution result and an operational-capacity failure (mean 1551.371367 min, p99 3773.31410471 min, maximum source-queue delay 179743 s).

The new event runtime selects at most one edge at ARRIVE_JUNCTION, stores no future route, uses local one-step calendars, and reports zero runtime full A* only when measured. Completion alone is never a capacity PASS.

Formal negative capacity rows retained: `63`.
Unexecuted/failed formal rows retained: `0`.

| Gate | Status | Evidence |
| --- | --- | --- |
| paper_full_event_runtime | PARTIAL_WITH_EXPLICIT_BLOCKER | real_map_paper_full |
| fractional_frontier_execution_complete | PASS | executed=63/63 |
| local_safety_ablation | PARTIAL_WITH_EXPLICIT_BLOCKER | executed=9/9; runtime_invariant_pass=9/9; zero_unresolved_deadlock=0/9; zero_starvation=0/9; unresolved_deadlock_total=167; starvation_total=640069 |
| source_admission_ablation_operational | PASS | aging_enabled=True; aging_attempts=1212488; aging_pressure_holds=1103628; aging_beacon_reads=1561764; aging_max_pressure=655; off_enabled=False; off_attempts=114958; off_pressure_holds=0; off_beacon_reads=0; off_max_pressure=0; counter_partition_pass=2/2; substantive_outcome_differences=completed_segment_count,failed_segment_count,end_backlog,peak_backlog,backlog_area_seconds,source_peak_backlog,source_backlog_area_seconds,network_peak_backlog,network_end_backlog,original_entry_p95_seconds,original_entry_p99_seconds,source_delay_p95_seconds,source_delay_p99_seconds,network_time_p95_seconds,deadline_miss_rate,starvation_count,max_wait_seconds,wait_fairness_jain,unresolved_deadlock_count |
| temporal_fault_recovery | PARTIAL_WITH_EXPLICIT_BLOCKER | executed=5/5; recovery_pass=0/5; unrecovered_windows=6 |
| real_resource_instrumentation | PASS | isolated worker OS working-set measurements |

G4J remains closed unless a separately accepted Java/CIE boundary report says otherwise. Remote GitHub Actions are not claimed from local pytest output.
