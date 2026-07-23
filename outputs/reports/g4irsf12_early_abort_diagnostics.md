# G4IRSF12-D Early-Abort Diagnostics

Status: `PROTOCOL_READY_NO_ATTEMPTS`.

This report is size-ladder diagnostic evidence, not a final performance gate.
It never authorizes 1.1x or larger workloads. Empty tables mean no runtime
attempt was executed; they are not PASS evidence.

## Frozen protocol

- Segment ladder: `144 -> 512 -> 2048 -> 8192 -> 43603`.
- Full original workload: `43603` segments / `28506` bags.
- Input order: `canonical_inputdata_jsonl_row_order`.
- Prefix selection: `first_n_segments_without_reordering`.
- Early-abort status: `EARLY_ABORT_DIAGNOSTIC_COLLAPSE`.
- One soft symptom holds promotion for review; two simultaneous soft symptoms abort.
- Any repeated cycle, nonlinear event growth, gross p99 projection, or rapid starvation aborts.

## Attempts (negative and partial attempts retained)

| Candidate | Attempt | Size | Descriptor | Diagnostic | Promotion | Blockers |
| --- | --- | ---: | --- | --- | --- | --- |
| — | — | — | NO_ATTEMPTS | NOT_EVALUATED | NOT_AUTHORIZED | No descriptor supplied |

## Diagnostic thresholds

```json
{
  "composite_soft_trigger_count": 2,
  "cross_tier_normalized_growth_factor": 4.0,
  "departure_to_arrival_ratio_max": 0.8,
  "large_backlog_fraction": 0.1,
  "low_critical_utilization_max": 0.2,
  "minimum_last_interval_events": 100,
  "minimum_observed_arrival_fraction": 0.25,
  "minimum_source_hold_delta": 16,
  "minimum_starvation_total": 8,
  "minimum_starvation_window": 4,
  "nonlinear_interval_rate_factor": 3.0,
  "p99_control_ratio_abort": 4.0,
  "recent_window_snapshots": 4,
  "repeated_cycle_snapshots": 3,
  "source_hold_delta_fraction": 0.05,
  "starvation_total_fraction": 0.02,
  "starvation_window_fraction": 0.005
}
```

## Claim boundary

`ELIGIBLE_FOR_NEXT_SIZE` authorizes only the immediately following original-1x tier. `ORIGINAL_1X_DIAGNOSTIC_COMPLETE_NOT_FINAL_GATE` is not an algorithm PASS, does not establish superiority over historical HCA*, and does not authorize scaling.
