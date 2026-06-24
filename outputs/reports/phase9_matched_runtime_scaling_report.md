# Phase9 Matched Runtime Scaling Diagnostic

Date: 2026-06-24

## Scope

This diagnostic repeats the Phase9 matched baseline comparison calls on the same real legacy `map2/inputdata` scenario rows. It reports Python and C++ elapsed-time means, standard deviations, and approximate 95% confidence intervals for every matched baseline family.

It is a repeated local timing gate with hardware metadata, not a cross-machine paper benchmark.

## Environment

- repeats per row: `3`
- platform: `Windows-10-10.0.26200-SP0`
- machine: `AMD64`
- processor: `Intel64 Family 6 Model 170 Stepping 4, GenuineIntel`
- CPU count: `22`
- Python: `3.11.15`
- timer: `perf_counter` resolution `1e-07` seconds

## Metrics

| Scenario | Family | Tasks | Config | Py seconds mean+/-95% CI | C++ seconds mean+/-95% CI | C++ elapsed speedup | Parity |
|---|---|---:|---|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | 0.019890+/-0.023104 | 0.020762+/-0.000635 | 0.958 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 0.047219+/-0.000295 | 0.123673+/-0.002347 | 0.382 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 5.414498+/-0.115700 | 5.473058+/-0.356821 | 0.989 | True |
| legacy_first16 | edge_score_event | 16 | none | 0.123991+/-0.018419 | 0.046289+/-0.010349 | 2.679 | True |
| legacy_first16 | fallback_event | 16 | none | 0.045894+/-0.000963 | 0.037728+/-0.008442 | 1.216 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | nodes=28:2;47:2 | 0.011044+/-0.001199 | 0.023807+/-0.003231 | 0.464 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | nodes=28:2;47:2 | 0.060772+/-0.007504 | 0.153118+/-0.009644 | 0.397 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | nodes=28:2;47:2 | 5.391243+/-0.046775 | 5.481962+/-0.137094 | 0.983 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | nodes=28:2;47:2 | 0.119199+/-0.008253 | 0.046354+/-0.005939 | 2.572 | True |
| legacy_first16_buffer2 | fallback_event | 16 | nodes=28:2;47:2 | 0.044722+/-0.000251 | 0.043014+/-0.006198 | 1.040 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 0.023227+/-0.001016 | 0.057958+/-0.010656 | 0.401 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 0.138183+/-0.011389 | 0.373462+/-0.041650 | 0.370 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 9.470341+/-0.080322 | 9.304883+/-0.274150 | 1.018 | True |
| legacy_first32 | edge_score_event | 32 | none | 0.239753+/-0.008393 | 0.090031+/-0.021339 | 2.663 | True |
| legacy_first32 | fallback_event | 32 | none | 0.099485+/-0.011601 | 0.072585+/-0.016259 | 1.371 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | none | 0.009503+/-0.000449 | 0.034048+/-0.002611 | 0.279 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | none | 0.059918+/-0.008484 | 0.204520+/-0.022839 | 0.293 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | none | 6.622970+/-0.147272 | 6.584405+/-0.077422 | 1.006 | True |
| legacy_offset32_static16 | edge_score_event | 16 | none | 0.145410+/-0.006885 | 0.043164+/-0.006948 | 3.369 | True |
| legacy_offset32_static16 | fallback_event | 16 | none | 0.052189+/-0.003912 | 0.047887+/-0.012981 | 1.090 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | none | 0.027259+/-0.004919 | 0.074276+/-0.015058 | 0.367 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | none | 0.143764+/-0.018990 | 0.467732+/-0.024789 | 0.307 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | none | 8.881198+/-0.239395 | 8.864358+/-0.669878 | 1.002 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | none | 0.213086+/-0.011407 | 0.066690+/-0.008639 | 3.195 | True |
| legacy_offset64_repair32 | fallback_event | 32 | none | 0.090541+/-0.010912 | 0.070375+/-0.022678 | 1.287 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.033552+/-0.005796 | 0.097435+/-0.017881 | 0.344 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.185649+/-0.024613 | 0.533252+/-0.108590 | 0.348 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 8.886932+/-0.251120 | 8.687420+/-0.235647 | 1.023 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.220820+/-0.008091 | 0.068428+/-0.010076 | 3.227 | True |
| legacy_offset64_merge32 | fallback_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.097645+/-0.008410 | 0.060767+/-0.004428 | 1.607 | True |

CSV: `outputs/tables/phase9_matched_runtime_scaling.csv`

## Gate Status

- scenarios: `6` (legacy_first16, legacy_first16_buffer2, legacy_first32, legacy_offset32_static16, legacy_offset64_merge32, legacy_offset64_repair32)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- repeated timing rows: `30`
- matched runtime summary parity: PASS
- matched runtime post-shield safety: PASS
- median C++ elapsed-time speedup: `1.004x`
- repeated local timing with environment metadata: YES
- confidence intervals for every compared family: YES

## Remaining Work

- add a separate real heldout airport map when fixture data is available
- expand timing to hardware-normalized multi-machine runs before paper-grade speed claims
