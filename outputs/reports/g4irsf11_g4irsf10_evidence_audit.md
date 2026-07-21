# G4IRSF11 G4IRSF10 evidence re-audit

This is a direct artifact/code audit, not a restatement of the previous promotion report.

## Scale evidence

| Scale | Mean THT | p95 | p99 | Backlog count | Max queue delay s | Loops | Fallback/decision | Decision/s | Safe execution | Capacity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1x | 3.556594 | 4.180000 | 4.386667 | 310 | 309.000 | 0 | 1.910878 | 4689.888 | PASS | UNVERIFIED |
| 2x | 4.123078 | 6.326681 | 7.503348 | 956 | 955.000 | 4504 | 1.928434 | 2942.341 | PASS | UNVERIFIED |
| 4x | 74.041240 | 138.724559 | 189.490821 | 6968 | 6967.000 | 2473 | 1.899227 | 1454.593 | PASS | UNVERIFIED |
| 8x | 590.217082 | 1270.115808 | 1496.812798 | 60556 | 60555.000 | 2534 | 1.772619 | 753.082 | PASS | UNVERIFIED |
| 16x | 1551.371367 | 3502.997042 | 3773.314105 | 179744 | 179743.000 | 2354 | 1.760778 | 392.488 | PASS | UNVERIFIED |

All five rows pass the narrow safe-execution predicate only when completion is exact and conflicts/full A* are zero. Queue stability remains `UNVERIFIED_NO_TIME_SERIES`; service level remains `UNVERIFIED_NO_SLO`. Therefore none is relabelled as capacity PASS. In particular, 16x is retained as operational-capacity negative evidence.

## Smoke and rolling scope

| Scenario | Status | Executed | Generated | Coverage | Time span s | Copy indices | Full scope |
| --- | --- | --- | --- | --- | --- | --- | --- |
| high_flow_no_fault_32x_smoke | PREFIX_MEASURED | 32768 | 1395296 | 0.023485 | 11088.000 | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31] | False |
| rolling_7_day_1x_smoke | PREFIX_MEASURED | 32768 | 305221 | 0.107358 | 53262.000 | [0] | False |
| rolling_2_day_1x | PREFIX_MEASURED | 87206 | 87206 | 1.000000 | 160070.000 | [0, 1] | True |

The measured scope uses the prefix actually passed to the runtime. The unconsumed tail of a generated JSONL is not continuity evidence.

## Generator classification

The audited generator copies every processed base row for each replica/day and adds deterministic replica micro-offsets. It preserves selected empirical distributions, but it is not independent-day generation and is not an original Java rule replay.

## Legacy hard-case index

| Rows | Unique content | Duplicates | Duplicate rate | Scenarios | High-flow | Fault | Tail | Required coverage gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 50000 | 43603 | 6397 | 0.127940 | 2 | False | False | True | False |

The index is task/path-derived and sequentially capped. This audit measures the rows actually written; the manifest's pre-cap `seen` counter is not used as coverage proof. The index remains diagnostic-only and is not eligible for v3 training.

## Claim boundary

G4IRSF10 demonstrated a complete zero-conflict, zero-full-A* execution closure. It did not demonstrate 16x operational capacity, queue stability, a seven-day executed continuity window, temporal repair, real peak RSS, or a decision-level training dataset.
