# CIE fixed-fault specialty results

Campaign status: **COMPLETE**.

Campaign identity gate: **True**. Pair effects require the same commit, runner, binary (requested and actually loaded), workload, release schedule, and reference request.

Every executed cell uses the original 1× population (28,506 raw bags / 43,603 segments), canonical `pass_time` releases, the same fixed horizon, and fixed-denominator completion, deadline, tardiness and backlog metrics.

Strict counters describe pre-feasibility filtering and are not a paired final-action trace. DLP committed mutations are runtime ranking mutations, likewise not a paired final-action trace.

For potential cells with source-unreachable bags, both arms use the same unreachable recognition, native admission cohort, complete raw-bag denominator, and releases. The only request delta is the existing DLP artifact.

Timing is shown only after all 28,506 raw bags complete at 1×. No survivor/common-cohort timing is used; a future 2× extension remains formal THT N/A by protocol.

## Arm results

| Study | Map/fault | Arm | Status | Integrity | Complete | On time | Missed | Tardiness sum (s) | End backlog | Timing | Mean/P95/P99/max (s) | Cohort |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| potential | map2/pair_2_4 | EDGE_FILTER_ONLY | COMPLETE | True | 5453 | 5453 | 23053 | 1151541327.0 | 23053 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| potential | map2/pair_2_4 | SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL | COMPLETE | True | 22113 | 22113 | 6393 | 330114387.0 | 6393 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| potential | map2/single_4 | EDGE_FILTER_ONLY | COMPLETE | True | 10248 | 10248 | 18258 | 897020322.0 | 18258 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| potential | map2/single_4 | SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL | COMPLETE | True | 28506 | 28506 | 0 | 0.0 | 0 | FULL_POPULATION_RAW_BAG_TIMING_1X | 268.620/386.748/454.094/566.264 | same |
| potential | nanning/pair_3_5 | EDGE_FILTER_ONLY | COMPLETE | True | 12186 | 12186 | 16320 | 778884180.0 | 16320 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| potential | nanning/pair_3_5 | SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL | COMPLETE | True | 12186 | 12186 | 16320 | 778884180.0 | 16320 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| potential | nanning/single_3 | EDGE_FILTER_ONLY | COMPLETE | True | 17559 | 17538 | 10968 | 539016854.1 | 10947 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| potential | nanning/single_3 | SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL | COMPLETE | True | 28506 | 26018 | 2488 | 8855046.2 | 0 | FULL_POPULATION_RAW_BAG_TIMING_1X | 1500.531/8308.623/10516.194/17068.734 | same |
| strict | map2/pair_2_4 | FULL_WITHOUT_STRICT_DESCENT | COMPLETE | True | 22113 | 22113 | 6393 | 330114387.0 | 6393 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| strict | map2/pair_2_4 | FULL_WITH_STRICT_DESCENT | COMPLETE | True | 22113 | 22113 | 6393 | 330114387.0 | 6393 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| strict | map2/single_4 | FULL_WITHOUT_STRICT_DESCENT | COMPLETE | True | 28506 | 28506 | 0 | 0.0 | 0 | FULL_POPULATION_RAW_BAG_TIMING_1X | 268.620/386.748/454.094/566.264 | same |
| strict | map2/single_4 | FULL_WITH_STRICT_DESCENT | COMPLETE | True | 28506 | 28506 | 0 | 0.0 | 0 | FULL_POPULATION_RAW_BAG_TIMING_1X | 268.620/386.748/454.094/566.264 | same |
| strict | nanning/pair_3_5 | FULL_WITHOUT_STRICT_DESCENT | COMPLETE | True | 12186 | 12186 | 16320 | 778884180.0 | 16320 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| strict | nanning/pair_3_5 | FULL_WITH_STRICT_DESCENT | COMPLETE | True | 12186 | 12186 | 16320 | 778884180.0 | 16320 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| strict | nanning/single_3 | FULL_WITHOUT_STRICT_DESCENT | COMPLETE | True | 28491 | 25617 | 2889 | 12860465.2 | 15 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE | N/A/N/A/N/A/N/A | same |
| strict | nanning/single_3 | FULL_WITH_STRICT_DESCENT | COMPLETE | True | 28506 | 26018 | 2488 | 8855046.2 | 0 | FULL_POPULATION_RAW_BAG_TIMING_1X | 1500.531/8308.623/10516.194/17068.734 | same |

## Registered pair effects

| Study | Map/fault | Valid | Interpretation | Δ complete | Δ on time | Δ missed | Δ tardiness (s) | Δ end backlog | Δ mean/P95/P99/max (s) |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| strict | map2/single_4 | yes | PURE_REGISTERED_SINGLE_FACTOR | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.0000 | 0.000/0.000/0.000/0.000 |
| strict | map2/pair_2_4 | yes | PURE_REGISTERED_SINGLE_FACTOR | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.0000 | N/A/N/A/N/A/N/A |
| strict | nanning/single_3 | yes | PURE_REGISTERED_SINGLE_FACTOR | 15.0000 | 401.0000 | -401.0000 | -4005419.0 | -15.0000 | N/A/N/A/N/A/N/A |
| strict | nanning/pair_3_5 | yes | PURE_REGISTERED_SINGLE_FACTOR | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.0000 | N/A/N/A/N/A/N/A |
| potential | map2/single_4 | yes | PURE_REGISTERED_SINGLE_FACTOR | 18258.0000 | 18258.0000 | -18258.0000 | -897020322.0 | -18258.0000 | N/A/N/A/N/A/N/A |
| potential | map2/pair_2_4 | yes | PURE_REGISTERED_SINGLE_FACTOR | 16660.0000 | 16660.0000 | -16660.0000 | -821426940.0 | -16660.0000 | N/A/N/A/N/A/N/A |
| potential | nanning/single_3 | yes | PURE_REGISTERED_SINGLE_FACTOR | 10947.0000 | 8480.0000 | -8480.0000 | -530161807.9 | -10947.0000 | N/A/N/A/N/A/N/A |
| potential | nanning/pair_3_5 | yes | PURE_REGISTERED_SINGLE_FACTOR | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.0000 | N/A/N/A/N/A/N/A |

## Missing / invalid cells

Missing: none

Invalid: none

Backlog-area values in the CSV are fixed-horizon corrected views. Legacy last-event values and method identities are retained in adjacent columns; an unrecoverable incomplete tail is N/M and is never reused as if it covered the horizon.
