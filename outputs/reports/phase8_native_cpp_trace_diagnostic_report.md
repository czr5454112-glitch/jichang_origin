# Phase8 Native C++ Trace Diagnostic

Date: 2026-06-17

## Scope

This diagnostic compares Python and compact native C++ EdgeScore decision traces on the first `24` same-map tasks. It verifies trace parity on this window and localizes the first divergence when parity does not hold.

## Summary

| Runtime | Planned | Unplanned | Decisions | Mean travel | Conflicts | Truncated |
|---|---:|---:|---:|---:|---:|---|
| Python | 20 | 4 | 302 | 57.760000 | 0 | False |
| C++ compact replay | 20 | 4 | 302 | 57.760000 | 0 | False |

## First Divergence

| Status | Decision | Field | Python | C++ | Python task | C++ task |
|---|---:|---|---|---|---|---|
| match |  | none |  |  |  /  |  /  |

First mismatch CSV: `outputs/tables/phase8_native_cpp_trace_first_mismatch.csv`
Trace context CSV: `outputs/tables/phase8_native_cpp_trace_context.csv`

## Gate Status

- trace diagnostic safety: PASS
- 24-task decision trace parity: PASS
- full high-throughput event-scheduler parity: not covered

## Notes

The configured 24-task decision trace now matches exactly between Python and compact native C++ replay. This validates the previously mismatching unreachable-goal safety and unplanned-task cleanup semantics on this window.
