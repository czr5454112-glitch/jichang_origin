# G4IRSF26 paper experiment report

Evidence labels are strict: `EXACT_FRESH` is a current canonical-cohort result admitted by its table-appropriate safety gate, `RECONSTRUCTED` combines named exact runs or the registered line mapping, and `TOPOLOGY_PROVEN_RECONSTRUCTION` is limited to a topology-saturated Table 5.5 primary rate. `ARCHIVED` is a paper value. Missing evidence is `NOT_MEASURED`.

The interruption primary success rate is `completed raw bags / 28,506`. `finish <= STD` and `finish <= STD - 2700` are secondary views.

Repeat policy: Table 5.2 fresh HCA uses two independent Java-process repeats per speed, while S4 uses one run per Table 5.2 cell. Table 5.4 uses one S4 run per cell. Table 5.5 uses one fresh HCA and one S4 run per executable scenario. Early censored or truncated probes were superseded by their formal reruns and are not counted as repeats.

## Outcome summary

- Table 5.2 mean vs fresh HCA: S4 wins 4/4 measured; ties 0; losses 0; NOT_MEASURED 0.
- Table 5.4 vs archived dynamic: S4 wins 4/12 measured; ties 0; losses 8; NOT_MEASURED 0.
- Table 5.4 vs archived static: S4 wins 6/12 measured; ties 0; losses 6; NOT_MEASURED 0.
- Table 5.5 vs fresh HCA: S4 wins 2/15 measured; ties 2; losses 11; NOT_MEASURED 1.

S4 does not win every paper experiment.

## Table 5.2 — speed

| Speed | Metric | Paper | Fresh HCA | Fresh S4 | S4 vs paper | S4 vs HCA |
|---:|---|---:|---:|---:|---|---|
| 1.5 | tth_min_minutes | 5.1000 | 5.1000 | 5.0889 | S4_WIN | S4_WIN |
| 1.5 | tth_mean_minutes | 6.4400 | 6.4199 | 5.7187 | S4_WIN | S4_WIN |
| 1.5 | tth_max_minutes | 9.6800 | 9.6333 | 9.2056 | S4_WIN | S4_WIN |
| 2.0 | tth_min_minutes | 3.8700 | 3.8667 | 3.8667 | S4_WIN | ORIGINAL_WIN |
| 2.0 | tth_mean_minutes | 4.9300 | 4.9274 | 4.3252 | S4_WIN | S4_WIN |
| 2.0 | tth_max_minutes | 7.3700 | 7.3667 | 5.8084 | S4_WIN | S4_WIN |
| 2.5 | tth_min_minutes | 3.1300 | 3.1333 | 3.1334 | ORIGINAL_WIN | ORIGINAL_WIN |
| 2.5 | tth_mean_minutes | 3.9600 | 3.9452 | 3.5128 | S4_WIN | S4_WIN |
| 2.5 | tth_max_minutes | 5.9800 | 5.9500 | 6.7901 | ORIGINAL_WIN | ORIGINAL_WIN |
| 3.0 | tth_min_minutes | 2.6300 | 2.6333 | 2.6389 | ORIGINAL_WIN | ORIGINAL_WIN |
| 3.0 | tth_mean_minutes | 3.3700 | 3.3546 | 2.9528 | S4_WIN | S4_WIN |
| 3.0 | tth_max_minutes | 5.0500 | 5.0500 | 5.0167 | S4_WIN | S4_WIN |

## Table 5.3 — archived algorithms

| Method | Metric | Paper | Fresh HCA | Fresh S4 | S4 vs paper |
|---|---|---:|---:|---:|---|
| dispersed_heuristic | min (minutes) | 3.5600 | NOT_MEASURED | 3.1334 | S4_WIN |
| dispersed_heuristic | mean (minutes) | 4.4300 | NOT_MEASURED | 3.5128 | S4_WIN |
| dispersed_heuristic | max (minutes) | 8.6200 | NOT_MEASURED | 6.7901 | S4_WIN |
| iot_drpa_hca_star | min (minutes) | 3.1300 | 3.1333 | 3.1334 | ORIGINAL_WIN |
| iot_drpa_hca_star | mean (minutes) | 3.9600 | 3.9452 | 3.5128 | S4_WIN |
| iot_drpa_hca_star | max (minutes) | 5.9800 | 5.9500 | 6.7901 | ORIGINAL_WIN |
| paper_improvement | min (percent) | 12.1000 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| paper_improvement | mean (percent) | 10.6000 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| paper_improvement | max (percent) | 30.6000 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |

## Table 5.4 — two-speed reconstruction

Each cell requires both the exact nominal Table 5.2 run and the exact degraded-speed run.

| Standard | Actual | Deviation | Paper dynamic | Paper static | S4 nominal | S4 degraded | Evidence | S4 vs archived dynamic | S4 vs archived static |
|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 1.5 | 1.350 | 10% | 6.4500 | 6.5900 | 5.7187 | 6.3343 | RECONSTRUCTED | S4_WIN | S4_WIN |
| 1.5 | 1.200 | 20% | 6.6700 | 6.8600 | 5.7187 | 7.1009 | RECONSTRUCTED | ORIGINAL_WIN | ORIGINAL_WIN |
| 1.5 | 1.050 | 30% | 6.9100 | 7.1100 | 5.7187 | 8.0965 | RECONSTRUCTED | ORIGINAL_WIN | ORIGINAL_WIN |
| 2.0 | 1.800 | 10% | 4.9200 | 5.0700 | 4.3252 | 4.7954 | RECONSTRUCTED | S4_WIN | S4_WIN |
| 2.0 | 1.600 | 20% | 5.1600 | 5.3600 | 4.3252 | 5.3714 | RECONSTRUCTED | ORIGINAL_WIN | ORIGINAL_WIN |
| 2.0 | 1.400 | 30% | 5.4200 | 5.6200 | 4.3252 | 6.1145 | RECONSTRUCTED | ORIGINAL_WIN | ORIGINAL_WIN |
| 2.5 | 2.250 | 10% | 3.9900 | 4.1900 | 3.5128 | 3.8807 | RECONSTRUCTED | S4_WIN | S4_WIN |
| 2.5 | 2.000 | 20% | 4.2500 | 4.4600 | 3.5128 | 4.3323 | RECONSTRUCTED | ORIGINAL_WIN | S4_WIN |
| 2.5 | 1.750 | 30% | 4.4900 | 4.7200 | 3.5128 | 4.9372 | RECONSTRUCTED | ORIGINAL_WIN | ORIGINAL_WIN |
| 3.0 | 2.700 | 10% | 3.3900 | 3.5600 | 2.9528 | 3.2647 | RECONSTRUCTED | S4_WIN | S4_WIN |
| 3.0 | 2.400 | 20% | 3.5100 | 3.7200 | 2.9528 | 3.6487 | RECONSTRUCTED | ORIGINAL_WIN | S4_WIN |
| 3.0 | 2.100 | 30% | 3.6400 | 3.8700 | 2.9528 | 4.1433 | RECONSTRUCTED | ORIGINAL_WIN | ORIGINAL_WIN |

## Table 5.5 — interruptions

Line IDs 1, 6, and 7 use explicit 69-edge reconstruction mappings. `pair_5_7` alone follows the archived workbook sheet `33-44,46-36`; an exact-label fresh HCA run produced 8,013/28,506 rather than the cached 13,939/28,506, so this source-inconsistent row is archived-only and cannot produce a fresh verdict. It is not a global line remap. For topology-proven rows, both secondary deadline views are censored and remain `NOT_MEASURED`.
Fresh HCA verdicts in this table are `PROTOCOL_CONTROLLED_RECONSTRUCTION`: both arms use the same canonical input and fixed 28,506-bag denominator, but S4 uses the registered 2.5 m/s no-fault release trace while faulted HCA realizes its own (possibly partial) release stream. They are not exact per-segment release-paired comparisons.

| Scenario | Reconstructed edge(s) | Paper | Fresh HCA primary | Fresh S4 primary | S4 evidence | S4 <= STD | S4 literal | Secondary status | S4 vs paper | S4 vs fresh HCA | HCA comparison evidence |
|---|---|---:|---:|---:|---|---:|---:|---|---|---|---|
| single_1 | 6->12 | 1.0000 | 1.0000 | 1.0000 | EXACT_FRESH | 1.0000 | 0.4293 | MEASURED | TIE | TIE | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_2 | 8->11 | 0.8800 | 0.8880 | 0.8870 | EXACT_FRESH | 0.8870 | 0.3761 | MEASURED | S4_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_3 | 13->23 | 1.0000 | 1.0000 | 0.7974 | EXACT_FRESH | 0.7974 | 0.3311 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_4 | 24->27 | 0.9500 | 0.9988 | 0.1608 | EXACT_FRESH | 0.1608 | 0.0621 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_5 | 14->46 | 0.9700 | 0.9992 | 0.7912 | EXACT_FRESH | 0.7912 | 0.3221 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_6 | 43->15 | 0.9600 | 1.0000 | 0.9987 | EXACT_FRESH | 0.9987 | 0.4281 | MEASURED | S4_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_7 | 33->44 | 1.0000 | 1.0000 | 0.9844 | EXACT_FRESH | 0.7809 | 0.4262 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| single_8 | 31->32 | 0.9900 | 0.9997 | 1.0000 | EXACT_FRESH | 1.0000 | 0.4266 | MEASURED | S4_WIN | S4_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| pair_1_7 | 6->12,33->44 | 1.0000 | 1.0000 | 0.9844 | EXACT_FRESH | 0.7835 | 0.4264 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| pair_2_4 | 8->11,24->27 | 0.7600 | 0.7747 | 0.1390 | EXACT_FRESH | 0.1390 | 0.0548 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| pair_3_5 | 13->23,14->46 | 0.6600 | 0.6635 | 0.6613 | EXACT_FRESH | 0.6613 | 0.2677 | MEASURED | S4_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| pair_4_5 | 14->46,24->27 | 0.0000 | 0.0000 | 0.0000 | TOPOLOGY_PROVEN_RECONSTRUCTION | NOT_MEASURED | NOT_MEASURED | CENSORED_NOT_MEASURED | TIE | TIE | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| pair_5_7 | 33->44,46->36 | 0.4800 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| triple_2_4_6 | 8->11,24->27,43->15 | 0.2600 | 0.2615 | 0.1339 | EXACT_FRESH | 0.1339 | 0.0547 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| triple_3_5_8 | 13->23,14->46,31->32 | 0.0500 | 0.0000 | 0.0028 | EXACT_FRESH | 0.0028 | 0.0017 | MEASURED | ORIGINAL_WIN | S4_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |
| triple_4_6_7 | 24->27,33->44,43->15 | 0.2600 | 0.1977 | 0.0706 | EXACT_FRESH | 0.0706 | 0.0620 | MEASURED | ORIGINAL_WIN | ORIGINAL_WIN | PROTOCOL_CONTROLLED_RECONSTRUCTION |

## Claim boundary

Every S4 verdict above is calculated from the value in that cell. The report does not assume that S4 wins all cells. Archived, exact, topology-proven, and reconstructed values remain separate.
