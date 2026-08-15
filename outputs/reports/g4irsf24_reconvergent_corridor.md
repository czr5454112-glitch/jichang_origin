# G4IRSF24 Reconvergent Corridor

Status: `CLOSED_LOOP_MEASURED_NO_GO`.

- all supplied corridor pivots remain no-go
- Corridors=8, branches=4, reconvergence nodes=4, projected runtime edges=8.
- Closed-loop status: `MEASURED_NO_GO`; strongest no-go margin: `0.500` s. Mixed 1×/2× results do not activate the policy.
- Closed-loop arms reuse the same deterministic exogenous task stream as paired S4 counterfactuals; they do not establish generalization to a new day, seed, or order stream.
- Corridor support is the minimum marginal directed-edge support along a fitted path, and corridor duration is the sum of edge-level means—not a joint per-bag corridor trajectory count or duration.
- The 6s detour guard is the single rounded-up bound over the measured maximum static arm gap of 5.200s; the 2s margin run was one recorded sensitivity check, not a parameter sweep.
- Published summary: `outputs/reports/g4irsf24_reconvergent_corridor.md`; evidence-only artifact: `artifacts/policies/g4irsf24_dlp_corridor.json`.
- Campaign inputs: `outputs/tables/g4irsf24_reconvergent_corridor.json`, `outputs/tables/g4irsf24_reconvergent_corridor_margin2.json`.

## Closed-loop pivot

| Margin (s) | Scale | Proposals | Mutations | Fallback | Mean delta (s) | P95 delta (s) | P99 delta (s) | Max delta (s) | Safe | Overall | Strongest no-go |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.500 | 1 | 1835 | 1834 | 370878 | 0.227026 | 0.000000 | 0.800000 | -3.400000 | PASS | CORRIDOR_NO_GO_KEEP_S4 | PASS |
| 0.500 | 2 | 46074 | 8897 | 1395779 | -4.855069 | -16.327500 | -159.360500 | 423.850000 | PASS | CORRIDOR_NO_GO_KEEP_S4 | PASS |
| 2.000 | 1 | 1835 | 1834 | 370878 | 0.227026 | 0.000000 | 0.800000 | -3.400000 | PASS | CORRIDOR_NO_GO_KEEP_S4 | FAIL |
| 2.000 | 2 | 45602 | 8961 | 1430105 | -0.228872 | -0.933400 | -70.305000 | 975.550000 | PASS | CORRIDOR_NO_GO_KEEP_S4 | FAIL |

## Offline corridor structure

| Branch | First edge | Rejoin | Hops | Support | Residual (s) |
| --- | --- | --- | --- | --- | --- |
| 6 | 8 | 13 | 3 | 2962 | 35.100791 |
| 6 | 12 | 13 | 2 | 3996 | 48.899752 |
| 9 | 7 | 14 | 4 | 6202 | 22.433124 |
| 9 | 10 | 14 | 3 | 599 | 81.595682 |
| 16 | 17 | 24 | 4 | 9699 | 8.585467 |
| 16 | 21 | 24 | 3 | 576 | 38.532343 |
| 19 | 18 | 26 | 3 | 2443 | 3.766992 |
| 19 | 25 | 26 | 2 | 42 | 20.457143 |
