# G4IRSF13 Original-Scale Joint Decision

Status: `HISTORICAL_ONLY_PASS`.

H0 and H1 both completed the protected original 1x population. H1 was selected before the full run by the interpretable Q1 thesis-local tie-break; no empirical superiority was inferred from candidate IDs. Q0, Q3, P1, and P3 remain explicitly recorded as equal 8192 controls.

## Primary raw-entry result

| Candidate/control | Mean (min) | Median (s) | p95 (s) | p99 (s) | Max (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| H0 F2 frozen | 41.514218717973 | 2566.793125 | 7349.348647 | 10789.015763 | 11861.554940 |
| H1 Q1 no-learning | 41.514218717973 | 2566.793125 | 7349.348647 | 10789.015763 | 11861.554940 |
| frozen v2-safe raw-entry | 41.495306987809 | N/A | N/A | N/A | N/A |
| corrected historical HCA raw-entry | 43.135938280418 | N/A | N/A | N/A | N/A |

H1 delta versus v2-safe: `+1.134703810 s/bag`; delta versus fresh H0/F2: `+0.000000000 s/bag`.

The primary gate uses the Stage-B reconciled raw-entry v2 value `41.49530698780892 min`. The old `4.124305453` number is pass-time anchored and is not used as a raw-entry comparator.

## Timing decomposition

| Candidate | Scheduled dwell (min) | Source wait (min) | Network (min) | Decision-sensitive (min) | Mean path edges | Loop detour (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H0 | 37.371001534322 | 0.362718228911 | 3.780498954741 | 4.143217183651 | 11.955729 | 0.000000 |
| H1 | 37.371001534322 | 0.362718228911 | 3.780498954741 | 4.143217183651 | 11.955729 | 0.000000 |

## Five deterministic repeats

| Candidate | Repeats | Result hash | Binary hash | Hard gates |
| --- | ---: | --- | --- | --- |
| H0_F2_FROZEN | 5 | `ccb017518d2d00b6d3290882380cf90e62402a2892bb2b485823f5a8deefe937` | `814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7` | PASS |
| H1_Q1_THESIS_NO_LEARNING | 5 | `7241a9605441b0c067ee673956361c272cab340272cebde4d92f2f0bd92a435d` | `814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7` | PASS |

The five identical repeats are deterministic reproductions, not five independent statistical samples. The independent statistical sample count is therefore recorded as one per candidate.

An earlier five-run H1 attempt is retained as `FAILED_PROJECTION_AUDIT`: its legacy hash admitted a host-throughput measurement and did not retain complete bags/junction/full-summary component hashes. Those runs all passed runtime hard gates but are not reused as final equivalence evidence. The replacement protocol hashes complete bags, junction state, and the full algorithm summary while excluding only an explicit timing/RSS whitelist.

A subsequent ten-run replacement passed every runtime hard gate but is retained as `PROJECTION_VALIDATOR_FAILURE`: its committed CSV looked for the completed-segment count in the counter projection instead of the independently validated timing projection. Those runs are not reused; this final identity binds requested/completed segment counts directly from the timing projection.

A later ten-run replacement is retained as `REPORT_ENCODING_VALIDATOR_FAILURE`: non-ASCII dash characters in the formal report were not portable across legacy decoders. Those runs are not reused; final report text is strict ASCII.

## Hard gates

Both candidates recorded 28,506/28,506 complete raw bags and 43,603/43,603 completed segments; zero failed segments, conflicts, unsafe entries, runtime A*/CIE calls, global reservation scans, stored future routes, and unresolved deadlocks; no event/time limit; and reservation depth 1. Map, input, binary, source, segment-result, slice, and deterministic runtime hashes are repeat-bound.

## Real-input robustness slices

The CSV includes every protected source, goal, clock hour, contiguous six-hour input block, direct/EBS storage lifecycle, the actual frozen F2 PIBT-involved task set, and the empirically busiest input hour. Highlighted H1 rows:

| Slice | ID | Bags | Raw-entry mean (min) | Delta vs H0 (s/bag) |
| --- | --- | ---: | ---: | ---: |
| busy_hour | 06 | 3107 | 31.167658712209 | +0.000000000 |
| contention | F2_ACTUAL_PIBT_INVOLVED | 31 | 54.358333123656 | +0.000000000 |
| ebs_release | HAS_STORAGE_OUT | 15097 | 75.406506784850 | +0.000000000 |
| storage_lifecycle | DIRECT | 13409 | 3.355379658712 | +0.000000000 |
| storage_lifecycle | EBS_SPLIT | 15097 | 75.406506784850 | +0.000000000 |

## PIBT and learning conclusion

The history-closed matched contention gate passed, but P1-P4 were outcome-identical and P0 was 0.069048448 s/bag faster on that 8192 diagnostic. Dodge changed four unique-exit penalties without changing outcomes; regret had zero prior hits and is NOT_APPLICABLE. These are negative mechanism findings, not hidden promotion evidence.

H2 and H3 are `NOT_RUN`: `V3_OFFLINE_GATE_FAIL:RUNTIME_ELIGIBLE_FALSE:CLOSED_LOOP_NOT_RUN`. The v3 offline gate failed, runtime eligibility is false, and closed-loop execution is not authorized. Consequently independent learning contribution is not proven.

## Decision

- selected evaluated candidate: `H1_Q1_THESIS_NO_LEARNING`
- strict win vs v2-safe: `False`
- strict win vs F2: `False`
- all original-1x hard gates pass: `True`
- final label: `HISTORICAL_ONLY_PASS`

H1 beats the corrected historical HCA control but does not beat frozen v2-safe and does not independently beat F2. The scientifically valid outcome is therefore historical-only pass, with F2 retained and no new candidate promoted.

Selection evidence status: `PASS_INTERPRETABLE_TIE_BREAK`. No full candidate beyond H0/H1 was launched.
