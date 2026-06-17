# Phase8 Native C++ Scaling Diagnostic

Date: 2026-06-17

## Scope

This diagnostic extends the compact native C++ / Python comparison to larger same-map task windows. It is a compact-replay parity gate for these configured windows, not a substitute for the final high-throughput C++ event scheduler, repair-event validation, or heldout-map evaluation.

## Metrics

| Window | Py planned | C++ planned | Py unplanned | C++ unplanned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Planned match | Decision match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 24 | 20 | 20 | 4 | 4 | 302 | 302 | 0.000000 | 0 | 0 | True | True |
| 32 | 26 | 26 | 6 | 6 | 432 | 432 | 0.000000 | 0 | 0 | True | True |
| 48 | 35 | 35 | 13 | 13 | 794 | 794 | 0.000000 | 0 | 0 | True | True |
| 64 | 45 | 45 | 19 | 19 | 1053 | 1053 | 0.000000 | 0 | 0 | True | True |

CSV: `outputs/tables/phase8_native_cpp_scaling_diagnostic.csv`

## Diagnostic Status

- larger-window safety: PASS
- larger-window divergence observed: NO
- configured-window aggregate parity: PASS
- full high-throughput event-scheduler parity: not covered

## Notes

After aligning unreachable-goal safety and unplanned-task reservation cleanup, the compact C++ replay matches the Python junction environment on the configured 24/32/48/64 task windows for planned/unplanned counts, decision counts, mean travel time, and post-shield conflicts.

## Remaining Work

- expand trace parity beyond the current 24-task trace window and into repair/randomized schedules
- validate heldout maps, randomized density, and repair-event cases
- replace compact replay with the full C++ event scheduler and rerun this diagnostic
