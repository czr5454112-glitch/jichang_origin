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
- Python: `3.11.9`
- timer: `perf_counter` resolution `1e-07` seconds

## Metrics

| Scenario | Family | Tasks | Config | Py seconds mean+/-95% CI | C++ seconds mean+/-95% CI | C++ elapsed speedup | Parity |
|---|---|---:|---|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | 0.017129+/-0.019231 | 0.021014+/-0.001456 | 0.815 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 0.039994+/-0.001246 | 0.123583+/-0.005025 | 0.324 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 4.477094+/-0.081805 | 5.118390+/-0.050057 | 0.875 | True |
| legacy_first16 | edge_score_event | 16 | none | 0.092180+/-0.010478 | 0.042315+/-0.001144 | 2.178 | True |
| legacy_first16 | fallback_event | 16 | none | 0.034432+/-0.001621 | 0.035067+/-0.000998 | 0.982 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | nodes=28:2;47:2 | 0.007669+/-0.000678 | 0.021098+/-0.001314 | 0.364 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | nodes=28:2;47:2 | 0.041917+/-0.001339 | 0.123514+/-0.002730 | 0.339 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | nodes=28:2;47:2 | 4.349557+/-0.044915 | 5.014463+/-0.038680 | 0.867 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | nodes=28:2;47:2 | 0.089798+/-0.001860 | 0.042310+/-0.000886 | 2.122 | True |
| legacy_first16_buffer2 | fallback_event | 16 | nodes=28:2;47:2 | 0.033859+/-0.001190 | 0.035400+/-0.002824 | 0.956 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 0.018569+/-0.000077 | 0.054420+/-0.001007 | 0.341 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 0.104229+/-0.000938 | 0.301526+/-0.004548 | 0.346 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 8.085821+/-0.030667 | 9.189207+/-0.160361 | 0.880 | True |
| legacy_first32 | edge_score_event | 32 | none | 0.202032+/-0.026935 | 0.105542+/-0.020364 | 1.914 | True |
| legacy_first32 | fallback_event | 32 | none | 0.083657+/-0.013313 | 0.102091+/-0.021442 | 0.819 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | none | 0.011443+/-0.000428 | 0.041291+/-0.005453 | 0.277 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | none | 0.053622+/-0.007973 | 0.201431+/-0.044404 | 0.266 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | none | 5.756049+/-0.179738 | 7.232646+/-0.345710 | 0.796 | True |
| legacy_offset32_static16 | edge_score_event | 16 | none | 0.121391+/-0.011463 | 0.059740+/-0.000361 | 2.032 | True |
| legacy_offset32_static16 | fallback_event | 16 | none | 0.053107+/-0.001074 | 0.052085+/-0.005544 | 1.020 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | none | 0.022789+/-0.002815 | 0.070361+/-0.005991 | 0.324 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | none | 0.138523+/-0.010793 | 0.512115+/-0.046332 | 0.270 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | none | 11.737593+/-0.242907 | 13.932004+/-0.132094 | 0.842 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | none | 0.186859+/-0.010646 | 0.078834+/-0.019343 | 2.370 | True |
| legacy_offset64_repair32 | fallback_event | 32 | none | 0.074405+/-0.002036 | 0.078506+/-0.010178 | 0.948 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.030215+/-0.005219 | 0.094002+/-0.018388 | 0.321 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.155515+/-0.028036 | 0.524836+/-0.053653 | 0.296 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 11.344402+/-0.167173 | 13.424489+/-0.235170 | 0.845 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.205285+/-0.015249 | 0.083723+/-0.012908 | 2.452 | True |
| legacy_offset64_merge32 | fallback_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0.076002+/-0.001572 | 0.058397+/-0.001449 | 1.301 | True |

CSV: `outputs/tables/phase9_matched_runtime_scaling.csv`

## Gate Status

- scenarios: `6` (legacy_first16, legacy_first16_buffer2, legacy_first32, legacy_offset32_static16, legacy_offset64_merge32, legacy_offset64_repair32)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- repeated timing rows: `30`
- matched runtime summary parity: PASS
- matched runtime post-shield safety: PASS
- median C++ elapsed-time speedup: `0.844x`
- repeated local timing with environment metadata: YES
- confidence intervals for every compared family: YES

## Remaining Work

- add a separate real heldout airport map when fixture data is available
- expand timing to hardware-normalized multi-machine runs before paper-grade speed claims
