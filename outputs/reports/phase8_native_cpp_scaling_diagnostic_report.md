# Phase8 Native C++ Scaling Diagnostic

Date: 2026-06-17

## Scope

This diagnostic extends the compact native C++ / Python comparison to larger same-map task windows. It is intentionally a diagnostic rather than a parity gate: the compact C++ replay and Python environment still diverge after fallback-heavy states appear.

## Metrics

| Window | Py planned | C++ planned | Py unplanned | C++ unplanned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Planned match | Decision match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 24 | 20 | 22 | 4 | 2 | 740 | 321 | 1.085455 | 0 | 0 | False | False |
| 32 | 26 | 28 | 6 | 4 | 1109 | 449 | 0.689011 | 0 | 0 | False | False |
| 48 | 33 | 37 | 15 | 11 | 2127 | 815 | 1.428501 | 0 | 0 | False | False |
| 64 | 43 | 48 | 21 | 16 | 3101 | 1230 | 2.418411 | 0 | 0 | False | False |

CSV: `outputs/tables/phase8_native_cpp_scaling_diagnostic.csv`

## Diagnostic Status

- larger-window safety: PASS
- larger-window divergence observed: YES
- strict larger-window parity: not claimed

## Notes

The first 8/16 task windows have strict EdgeScore parity in the separate Phase8 parity report. Larger windows remain conflict-free but diverge in planned counts and decision counts once fallback-heavy local states occur. This gives the next C++ event-scheduler work a concrete target instead of hiding the mismatch.

## Remaining Work

- align fallback execution semantics and task cleanup between compact C++ replay and Python env
- add trace-level divergence localization for the first mismatching task/decision
- replace compact replay with the full C++ event scheduler and rerun this diagnostic
