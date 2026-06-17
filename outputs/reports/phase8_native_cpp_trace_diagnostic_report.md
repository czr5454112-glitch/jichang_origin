# Phase8 Native C++ Trace Diagnostic

Date: 2026-06-17

## Scope

This diagnostic compares Python and compact native C++ EdgeScore decision traces on the first `24` same-map tasks. It localizes the first larger-window replay divergence for the future full C++ event scheduler work.

## Summary

| Runtime | Planned | Unplanned | Decisions | Mean travel | Conflicts | Truncated |
|---|---:|---:|---:|---:|---:|---|
| Python | 20 | 4 | 740 | 57.760000 | 0 | False |
| C++ compact replay | 22 | 2 | 323 | 58.845455 | 0 | False |

## First Divergence

| Status | Decision | Field | Python | C++ | Python task | C++ task |
|---|---:|---|---|---|---|---|
| mismatch | 216 | event | step | unplanned | 17 / 17:storage_in | 17 / 17:storage_in |

First mismatch CSV: `outputs/tables/phase8_native_cpp_trace_first_mismatch.csv`
Trace context CSV: `outputs/tables/phase8_native_cpp_trace_context.csv`

## Gate Status

- trace diagnostic safety: PASS
- strict larger-window parity: not claimed

## Notes

This report narrows the larger-window mismatch from aggregate counts to a concrete decision-level comparison. It is intended to guide the next implementation step: aligning compact replay semantics or replacing them with the full C++ event scheduler.
