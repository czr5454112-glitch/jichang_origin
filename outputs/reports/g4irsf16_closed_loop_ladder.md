# G4IRSF16 closed-loop diagnostic ladder

All rows are real native, matched E4 H5-vs-supervisor-off executions. H5 is `8192_DIAGNOSTIC_ONLY_NOT_PROMOTED`; a PASS means runtime/safety gates passed, not that performance improved or that H5 was promoted.

| Segments | Action changes | Candidate mean (min) | Off mean (min) | Mean delta (s/raw bag) | P95 delta (s) | P99 delta (s) | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 144 | 19 | 170.207038989120 | 170.207038989120 | +0.000000000000 | +0.000000 | +0.000000 | MEAN_TIE |
| 512 | 102 | 146.945365573763 | 146.945365573763 | +0.000000000000 | +0.000000 | +0.000000 | MEAN_TIE |
| 2048 | 515 | 105.229054941149 | 105.229040045893 | +0.000893715377 | +0.000000 | +0.000000 | CANDIDATE_WORSE_MEAN |
| 8192 | 1865 | 57.390967335351 | 57.389450114717 | +0.091033238056 | +0.000000 | +0.000000 | CANDIDATE_WORSE_MEAN |

## Decision boundary

At 8,192 segments H5 is **+0.091033238056 seconds per raw bag worse** than its matched E4/off control. Its p95 and p99 gates pass, but this is not a benefit and cannot authorize promotion.

The formal learned candidate remains no-go. No 43,603-segment learned closed-loop candidate was run; the offline no-go is the allowed terminal path.
