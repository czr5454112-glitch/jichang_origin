# G4IRSF24 Native Closed Loop

Status: `DLP_LADDER_NO_GO_KEEP_S4`.

- Active policy after the 1x/2x ladder and corridor pivots: `S4`.
- Corridor pivot status: `CLOSED_LOOP_MEASURED_NO_GO`; strongest no-go margin: `0.500` s.

| Campaign | Margin | Scale | Candidate | Status | Mean (s) | P95 (s) | P99 (s) | Max (s) | Proposals | Mutations | Fallback | Mean Δ (s) | P95 Δ (s) | P99 Δ (s) | Max Δ (s) | Eligible | Strongest no-go |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DLP_LADDER | NOT_MEASURED | 1.000 | S4 | PASS | 210.770 | 247.204 | 254.004 | 407.404 | 0 | 0 | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | FAIL |
| DLP_LADDER | NOT_MEASURED | 2.000 | S4 | PASS | 283.176 | 512.004 | 1284.029 | 5511.454 | 0 | 0 | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | FAIL |
| RECONVERGENT_CORRIDOR | 0.500 | 1.000 | CORRIDOR_MARGIN_0.500 | CORRIDOR_NO_GO_KEEP_S4 | 210.997 | 247.204 | 254.804 | 404.004 | 1835 | 1834 | 370878 | 0.227026 | 0.000000 | 0.800000 | -3.400000 | FAIL | PASS |
| RECONVERGENT_CORRIDOR | 0.500 | 2.000 | CORRIDOR_MARGIN_0.500 | CORRIDOR_NO_GO_KEEP_S4 | 278.321 | 495.676 | 1124.668 | 5935.304 | 46074 | 8897 | 1395779 | -4.855069 | -16.327500 | -159.360500 | 423.850000 | FAIL | PASS |
| RECONVERGENT_CORRIDOR | 2.000 | 1.000 | CORRIDOR_MARGIN_2.000 | CORRIDOR_NO_GO_KEEP_S4 | 210.997 | 247.204 | 254.804 | 404.004 | 1835 | 1834 | 370878 | 0.227026 | 0.000000 | 0.800000 | -3.400000 | FAIL | FAIL |
| RECONVERGENT_CORRIDOR | 2.000 | 2.000 | CORRIDOR_MARGIN_2.000 | CORRIDOR_NO_GO_KEEP_S4 | 282.947 | 511.071 | 1213.724 | 6487.004 | 45602 | 8961 | 1430105 | -0.228872 | -0.933400 | -70.305000 | 975.550000 | FAIL | FAIL |
