# G4IRSF17 fixed-map scale benchmark

Status: **`COMPLETE`**. Complete 1×–16× matrix: **True**. At least two high-load non-regression gates: **False**.

Business time and compute resource columns are kept separate. A timeout/OOM row is censored, never a win.

Per-node source/junction queue telemetry is available for **1/5** required scale rows; because coverage is incomplete across the matrix, a cross-scale queue-peak bound must not be inferred from aggregate TTH, source-wait, event, or resource columns.

| Candidate | Load | Status | Mean TTH/Δs | P95/Δs | Wall s | RSS/ΔMB |
|---|---|---|---|---|---|---|
| E4_OFF | 1× | COMPLETE | 217.5833616080811 | 270.05399999999645 | 32.011491199955344 | 1403.7734375 |
| E4_OFF | 2× | COMPLETE | 1388.0056777169436 | 7967.048999999799 | 166.5057678000303 | 1836.83203125 |
| E4_OFF | 4× | HARD_GATE_FAILED | — | — | 3983.464073400013 | 2328.84375 |
| E4_OFF | 8× | HARD_GATE_FAILED | — | — | 6669.971150400001 | 2990.546875 |
| E4_OFF | 16× | HARD_GATE_FAILED | — | — | 10229.041027100058 | 5174.640625 |

Evidence: `outputs/tables/g4irsf17_scale_results.csv`.
