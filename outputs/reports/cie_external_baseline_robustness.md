# CIE external-baseline robustness report

Status: `INCOMPLETE` (164/180 normalized results).

All cells use the exact per-seed workload identity and a 98259-second fixed observation horizon. Population latency is reported only for a complete full population; formal 2x timing is always N/A. Null means the metric was not derivable from native evidence.

Identity boundary: the map2 CIE-DH values reported in Feng et al. are historical literature evidence only and are not represented by the native cells below. `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION` is a cross-map executable partial reconstruction in the archived Java environment, not the paper's original CIE-DH implementation. Its results may be optimistically biased and must not support a claim about the original algorithm or a leading-performance claim.

For Nanning rows the report uses `FENG_PAPER_ENV_CIE_DH_NANNING_PORTED` as a reporting-scope alias. The runtime method remains the unchanged map2 partial reconstruction; the alias prevents the port from being back-attributed to Feng's paper.

Execution accounting is based on validated normalized cells and the latest successful batch manifests. Superseded repair-attempt status files are retained as provenance and are not counted as current cell failures.

## Normalized native cells

| map | load | seed | method | completed | full | on-time | latency mean (s) |
|---|---:|---:|---|---:|:---:|---:|---:|
| map2 | 1 | 104729 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 237.127166 |
| map2 | 1 | 104729 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.518614 |
| map2 | 1 | 104729 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.236283 |
| map2 | 1 | 130363 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 236.764015 |
| map2 | 1 | 130363 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.429573 |
| map2 | 1 | 130363 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.045350 |
| map2 | 1 | 155921 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 236.978811 |
| map2 | 1 | 155921 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.380860 |
| map2 | 1 | 155921 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.228925 |
| map2 | 1 | 181081 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 237.033151 |
| map2 | 1 | 181081 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.547211 |
| map2 | 1 | 181081 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.250591 |
| map2 | 1 | 205759 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 237.113695 |
| map2 | 1 | 205759 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.354704 |
| map2 | 1 | 205759 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.225744 |
| map2 | 1 | 232003 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 237.276187 |
| map2 | 1 | 232003 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.490444 |
| map2 | 1 | 232003 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.164160 |
| map2 | 1 | 257053 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 236.914299 |
| map2 | 1 | 257053 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.429538 |
| map2 | 1 | 257053 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.090667 |
| map2 | 1 | 283303 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 236.867431 |
| map2 | 1 | 283303 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.490072 |
| map2 | 1 | 283303 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.113901 |
| map2 | 1 | 308081 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 237.052129 |
| map2 | 1 | 308081 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.467088 |
| map2 | 1 | 308081 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.011793 |
| map2 | 1 | 333667 | FENG_NATIVE_HCA | 28506 | yes | 28506 | 237.281204 |
| map2 | 1 | 333667 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 28506 | yes | 28506 | 241.605676 |
| map2 | 1 | 333667 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28506.0 | 237.146744 |
| map2 | 1.75 | 104729 | FENG_NATIVE_HCA | 49734 | no | 40617 | N/A |
| map2 | 1.75 | 104729 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49709 | 547.693471 |
| map2 | 1.75 | 104729 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 368.508748 |
| map2 | 1.75 | 130363 | FENG_NATIVE_HCA | 49734 | no | 40778 | N/A |
| map2 | 1.75 | 130363 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49705 | 552.609464 |
| map2 | 1.75 | 130363 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 368.937863 |
| map2 | 1.75 | 155921 | FENG_NATIVE_HCA | 49741 | no | 40425 | N/A |
| map2 | 1.75 | 155921 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49702 | 549.745415 |
| map2 | 1.75 | 155921 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 367.264754 |
| map2 | 1.75 | 181081 | FENG_NATIVE_HCA | 49729 | no | 40309 | N/A |
| map2 | 1.75 | 181081 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49704 | 550.632481 |
| map2 | 1.75 | 181081 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49764.0 | 369.067905 |
| map2 | 1.75 | 205759 | FENG_NATIVE_HCA | 49736 | no | 40502 | N/A |
| map2 | 1.75 | 205759 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49709 | 550.733134 |
| map2 | 1.75 | 205759 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 367.650553 |
| map2 | 1.75 | 232003 | FENG_NATIVE_HCA | 49723 | no | 40402 | N/A |
| map2 | 1.75 | 232003 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49714 | 548.564746 |
| map2 | 1.75 | 232003 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 365.027408 |
| map2 | 1.75 | 257053 | FENG_NATIVE_HCA | 49729 | no | 40351 | N/A |
| map2 | 1.75 | 257053 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49716 | 548.414267 |
| map2 | 1.75 | 257053 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 363.178194 |
| map2 | 1.75 | 283303 | FENG_NATIVE_HCA | 49731 | no | 40302 | N/A |
| map2 | 1.75 | 283303 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49712 | 548.033481 |
| map2 | 1.75 | 283303 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 367.098814 |
| map2 | 1.75 | 308081 | FENG_NATIVE_HCA | 49729 | no | 40246 | N/A |
| map2 | 1.75 | 308081 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49706 | 549.634229 |
| map2 | 1.75 | 308081 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 369.306315 |
| map2 | 1.75 | 333667 | FENG_NATIVE_HCA | 49736 | no | 40429 | N/A |
| map2 | 1.75 | 333667 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 49765 | yes | 49713 | 549.944431 |
| map2 | 1.75 | 333667 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 49765.0 | 361.390758 |
| map2 | 2 | 104729 | FENG_NATIVE_HCA | 56928 | no | 29244 | N/A |
| map2 | 2 | 104729 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56368 | N/A |
| map2 | 2 | 104729 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56888.0 | N/A |
| map2 | 2 | 130363 | FENG_NATIVE_HCA | 56910 | no | 30194 | N/A |
| map2 | 2 | 130363 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56371 | N/A |
| map2 | 2 | 130363 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56882.0 | N/A |
| map2 | 2 | 155921 | FENG_NATIVE_HCA | 56935 | no | 29704 | N/A |
| map2 | 2 | 155921 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56392 | N/A |
| map2 | 2 | 155921 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56896.0 | N/A |
| map2 | 2 | 181081 | FENG_NATIVE_HCA | 56903 | no | 29634 | N/A |
| map2 | 2 | 181081 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56375 | N/A |
| map2 | 2 | 181081 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56899.0 | N/A |
| map2 | 2 | 205759 | FENG_NATIVE_HCA | 56898 | no | 30115 | N/A |
| map2 | 2 | 205759 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56376 | N/A |
| map2 | 2 | 205759 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56893.0 | N/A |
| map2 | 2 | 232003 | FENG_NATIVE_HCA | 56912 | no | 29977 | N/A |
| map2 | 2 | 232003 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56377 | N/A |
| map2 | 2 | 232003 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56902.0 | N/A |
| map2 | 2 | 257053 | FENG_NATIVE_HCA | 56933 | no | 29354 | N/A |
| map2 | 2 | 257053 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56370 | N/A |
| map2 | 2 | 257053 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56887.0 | N/A |
| map2 | 2 | 283303 | FENG_NATIVE_HCA | 56895 | no | 29582 | N/A |
| map2 | 2 | 283303 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56370 | N/A |
| map2 | 2 | 283303 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56879.0 | N/A |
| map2 | 2 | 308081 | FENG_NATIVE_HCA | 56918 | no | 30166 | N/A |
| map2 | 2 | 308081 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56380 | N/A |
| map2 | 2 | 308081 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56900.0 | N/A |
| map2 | 2 | 333667 | FENG_NATIVE_HCA | 56887 | no | 30272 | N/A |
| map2 | 2 | 333667 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 57012 | yes | 56378 | N/A |
| map2 | 2 | 333667 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 56873.0 | N/A |
| nanning | 1 | 104729 | FENG_NATIVE_HCA | 28506 | yes | 18314 | 366.067495 |
| nanning | 1 | 104729 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12696 | no | 12330 | N/A |
| nanning | 1 | 104729 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28425.0 | 612.923968 |
| nanning | 1 | 130363 | FENG_NATIVE_HCA | 28506 | yes | 19092 | 364.777450 |
| nanning | 1 | 130363 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12701 | no | 12334 | N/A |
| nanning | 1 | 130363 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28432.0 | 612.030485 |
| nanning | 1 | 155921 | FENG_NATIVE_HCA | 28505 | no | 18484 | N/A |
| nanning | 1 | 155921 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12692 | no | 12324 | N/A |
| nanning | 1 | 155921 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28422.0 | 614.852317 |
| nanning | 1 | 181081 | FENG_NATIVE_HCA | 28505 | no | 18505 | N/A |
| nanning | 1 | 181081 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28424.0 | 613.830714 |
| nanning | 1 | 205759 | FENG_NATIVE_HCA | 28506 | yes | 18799 | 366.035466 |
| nanning | 1 | 205759 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12693 | no | 12326 | N/A |
| nanning | 1 | 205759 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28422.0 | 613.276177 |
| nanning | 1 | 232003 | FENG_NATIVE_HCA | 28505 | no | 18494 | N/A |
| nanning | 1 | 232003 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12693 | no | 12326 | N/A |
| nanning | 1 | 232003 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28430.0 | 608.935276 |
| nanning | 1 | 257053 | FENG_NATIVE_HCA | 28506 | yes | 18489 | 367.340279 |
| nanning | 1 | 257053 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28421.0 | 615.560730 |
| nanning | 1 | 283303 | FENG_NATIVE_HCA | 28506 | yes | 18341 | 366.804673 |
| nanning | 1 | 283303 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12690 | no | 12324 | N/A |
| nanning | 1 | 283303 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28430.0 | 607.757052 |
| nanning | 1 | 308081 | FENG_NATIVE_HCA | 28506 | yes | 18388 | 367.373290 |
| nanning | 1 | 308081 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 12691 | no | 12326 | N/A |
| nanning | 1 | 308081 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28436.0 | 605.356770 |
| nanning | 1 | 333667 | FENG_NATIVE_HCA | 28506 | yes | 19029 | 365.384095 |
| nanning | 1 | 333667 | G31_S4_NATIVE_SYSTEM | 28506.0 | yes | 28426.0 | 608.967016 |
| nanning | 1.75 | 104729 | FENG_NATIVE_HCA | 37403 | no | 17817 | N/A |
| nanning | 1.75 | 104729 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 22052 | no | 14130 | N/A |
| nanning | 1.75 | 104729 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19145.0 | 8483.242332 |
| nanning | 1.75 | 130363 | FENG_NATIVE_HCA | 37383 | no | 17885 | N/A |
| nanning | 1.75 | 130363 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19138.0 | 8457.247953 |
| nanning | 1.75 | 155921 | FENG_NATIVE_HCA | 37368 | no | 17749 | N/A |
| nanning | 1.75 | 155921 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19148.0 | 8428.395249 |
| nanning | 1.75 | 181081 | FENG_NATIVE_HCA | 37408 | no | 17809 | N/A |
| nanning | 1.75 | 181081 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 22049 | no | 14125 | N/A |
| nanning | 1.75 | 181081 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19114.0 | 8459.688910 |
| nanning | 1.75 | 205759 | FENG_NATIVE_HCA | 37450 | no | 17928 | N/A |
| nanning | 1.75 | 205759 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19132.0 | 8621.006728 |
| nanning | 1.75 | 232003 | FENG_NATIVE_HCA | 37371 | no | 17846 | N/A |
| nanning | 1.75 | 232003 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19124.0 | 8555.426078 |
| nanning | 1.75 | 257053 | FENG_NATIVE_HCA | 37356 | no | 17720 | N/A |
| nanning | 1.75 | 257053 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 22052 | no | 14126 | N/A |
| nanning | 1.75 | 257053 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19144.0 | 8486.756740 |
| nanning | 1.75 | 283303 | FENG_NATIVE_HCA | 37368 | no | 17866 | N/A |
| nanning | 1.75 | 283303 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19133.0 | 8493.724410 |
| nanning | 1.75 | 308081 | FENG_NATIVE_HCA | 37356 | no | 17687 | N/A |
| nanning | 1.75 | 308081 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 22047 | no | 14126 | N/A |
| nanning | 1.75 | 308081 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19143.0 | 8477.816282 |
| nanning | 1.75 | 333667 | FENG_NATIVE_HCA | 37407 | no | 17858 | N/A |
| nanning | 1.75 | 333667 | G31_S4_NATIVE_SYSTEM | 49765.0 | yes | 19164.0 | 8465.477772 |
| nanning | 2 | 104729 | FENG_NATIVE_HCA | 39043 | no | 19478 | N/A |
| nanning | 2 | 104729 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20988.0 | N/A |
| nanning | 2 | 130363 | FENG_NATIVE_HCA | 39047 | no | 19470 | N/A |
| nanning | 2 | 130363 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20952.0 | N/A |
| nanning | 2 | 155921 | FENG_NATIVE_HCA | 39088 | no | 19449 | N/A |
| nanning | 2 | 155921 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 24484 | no | 16126 | N/A |
| nanning | 2 | 155921 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20980.0 | N/A |
| nanning | 2 | 181081 | FENG_NATIVE_HCA | 39026 | no | 19364 | N/A |
| nanning | 2 | 181081 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20976.0 | N/A |
| nanning | 2 | 205759 | FENG_NATIVE_HCA | 39071 | no | 19418 | N/A |
| nanning | 2 | 205759 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20989.0 | N/A |
| nanning | 2 | 232003 | FENG_NATIVE_HCA | 39024 | no | 19400 | N/A |
| nanning | 2 | 232003 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20997.0 | N/A |
| nanning | 2 | 257053 | FENG_NATIVE_HCA | 39091 | no | 19443 | N/A |
| nanning | 2 | 257053 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 24473 | no | 16120 | N/A |
| nanning | 2 | 257053 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 21014.0 | N/A |
| nanning | 2 | 283303 | FENG_NATIVE_HCA | 38969 | no | 19355 | N/A |
| nanning | 2 | 283303 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 21006.0 | N/A |
| nanning | 2 | 308081 | FENG_NATIVE_HCA | 39033 | no | 19464 | N/A |
| nanning | 2 | 308081 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | 24483 | no | 16123 | N/A |
| nanning | 2 | 308081 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 21013.0 | N/A |
| nanning | 2 | 333667 | FENG_NATIVE_HCA | 39032 | no | 19433 | N/A |
| nanning | 2 | 333667 | G31_S4_NATIVE_SYSTEM | 57012.0 | yes | 20956.0 | N/A |

## Paired aggregate

| map | load | comparison | metric | seeds | status | ref wins/ties/losses |
|---|---:|---|---|---:|---|---:|
| map2 | 1 | FENG_NATIVE_HCA | completed_raw_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | completion_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | missed_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | missed_bag_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | network_backlog_area_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_NATIVE_HCA | on_time_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | on_time_raw_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | population_latency_max_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_NATIVE_HCA | population_latency_mean_seconds | 10 | COMPLETE | 3/0/7 |
| map2 | 1 | FENG_NATIVE_HCA | population_latency_p95_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_NATIVE_HCA | population_latency_p99_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_NATIVE_HCA | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_NATIVE_HCA | tardiness_max_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | tardiness_mean_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | tardiness_p95_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | tardiness_p99_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | tardiness_sum_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_NATIVE_HCA | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_NATIVE_HCA | time_to_95_percent_seconds | 10 | COMPLETE | 7/0/3 |
| map2 | 1 | FENG_NATIVE_HCA | time_to_99_percent_seconds | 10 | COMPLETE | 5/0/5 |
| map2 | 1 | FENG_NATIVE_HCA | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | completed_raw_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | completion_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | missed_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | missed_bag_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | network_backlog_area_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | on_time_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | on_time_raw_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_max_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_mean_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_p95_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_p99_seconds | 10 | COMPLETE | 0/0/10 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_max_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_mean_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_p95_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_p99_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_sum_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_95_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_99_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | completed_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | completion_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | network_backlog_area_seconds | 10 | COMPLETE | 9/0/1 |
| map2 | 1.75 | FENG_NATIVE_HCA | on_time_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | tardiness_p95_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | tardiness_p99_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | time_to_95_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | time_to_99_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_NATIVE_HCA | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | completed_raw_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | completion_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | network_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | on_time_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_max_seconds | 10 | COMPLETE | 6/0/4 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_mean_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_p95_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | population_latency_p99_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_p95_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_p99_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_95_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_99_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 1.75 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | completed_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | completion_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | network_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | on_time_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | tardiness_p95_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | tardiness_p99_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | time_to_95_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | time_to_99_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_NATIVE_HCA | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | completed_raw_bag_count | 10 | COMPLETE | 0/10/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | completion_rate | 10 | COMPLETE | 0/10/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | network_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | on_time_rate | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_p95_seconds | 10 | COMPLETE | 0/10/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_p99_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_95_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | time_to_99_percent_seconds | 10 | COMPLETE | 10/0/0 |
| map2 | 2 | FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | completed_raw_bag_count | 10 | COMPLETE | 3/7/0 |
| nanning | 1 | FENG_NATIVE_HCA | completion_rate | 10 | COMPLETE | 3/7/0 |
| nanning | 1 | FENG_NATIVE_HCA | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | network_backlog_area_seconds | 10 | COMPLETE | 0/0/10 |
| nanning | 1 | FENG_NATIVE_HCA | on_time_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | population_latency_max_seconds | 7 | INCOMPLETE | 0/0/7 |
| nanning | 1 | FENG_NATIVE_HCA | population_latency_mean_seconds | 7 | INCOMPLETE | 0/0/7 |
| nanning | 1 | FENG_NATIVE_HCA | population_latency_p95_seconds | 7 | INCOMPLETE | 0/0/7 |
| nanning | 1 | FENG_NATIVE_HCA | population_latency_p99_seconds | 7 | INCOMPLETE | 0/0/7 |
| nanning | 1 | FENG_NATIVE_HCA | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | tardiness_p95_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | tardiness_p99_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | time_to_90_percent_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | time_to_95_percent_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | time_to_99_percent_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_NATIVE_HCA | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | completed_raw_bag_count | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | completion_rate | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | missed_bag_count | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | missed_bag_rate | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | network_backlog_area_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | on_time_rate | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | on_time_raw_bag_count | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | source_backlog_area_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_max_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_mean_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_p95_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_p99_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_sum_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | total_backlog_area_seconds | 7 | INCOMPLETE | 7/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | completed_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | completion_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | network_backlog_area_seconds | 10 | COMPLETE | 0/0/10 |
| nanning | 1.75 | FENG_NATIVE_HCA | on_time_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | tardiness_p95_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | tardiness_p99_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_NATIVE_HCA | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | completed_raw_bag_count | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | completion_rate | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | missed_bag_count | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | missed_bag_rate | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | network_backlog_area_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | on_time_rate | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | on_time_raw_bag_count | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | source_backlog_area_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_max_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_mean_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_p95_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_p99_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_sum_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 1.75 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | total_backlog_area_seconds | 4 | INCOMPLETE | 4/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | completed_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | completion_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | missed_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | missed_bag_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | network_backlog_area_seconds | 10 | COMPLETE | 0/0/10 |
| nanning | 2 | FENG_NATIVE_HCA | on_time_rate | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | on_time_raw_bag_count | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | source_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | tardiness_max_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | tardiness_mean_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | tardiness_p95_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | tardiness_p99_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | tardiness_sum_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_NATIVE_HCA | total_backlog_area_seconds | 10 | COMPLETE | 10/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | completed_raw_bag_count | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | completion_rate | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | missed_bag_count | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | missed_bag_rate | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | network_backlog_area_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | on_time_rate | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | on_time_raw_bag_count | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | source_backlog_area_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_max_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_mean_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_p95_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_p99_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | tardiness_sum_seconds | 3 | INCOMPLETE | 3/0/0 |
| nanning | 2 | FENG_PAPER_ENV_CIE_DH_NANNING_PORTED | total_backlog_area_seconds | 3 | INCOMPLETE | 3/0/0 |
