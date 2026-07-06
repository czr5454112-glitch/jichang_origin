# G4IRSF10 v2-safe High-Flow Matrix Report

Date: 2026-07-06

Completed high-flow rows: `17`.
Blocker/not-run rows: `0`.

| Scenario | Scale | Tasks | Complete | Failed | Conflicts | Full A* | Mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| high_flow_no_fault_1x | 1x | 43603 | 28506 | 0 | 0 | 0 | 3.556593852974151 |
| high_flow_no_fault_2x | 2x | 87206 | 57012 | 0 | 0 | 0 | 4.123077760632622 |
| high_flow_no_fault_4x | 4x | 174412 | 114024 | 0 | 0 | 0 | 74.04123981177706 |
| high_flow_no_fault_8x | 8x | 348824 | 228048 | 0 | 0 | 0 | 590.2170824272421 |
| high_flow_no_fault_16x | 16x | 697648 | 456096 | 0 | 0 | 0 | 1551.3713669968568 |
| high_flow_no_fault_32x_smoke | 32x | 32768 | 32768 | 0 | 0 | 0 | 59.79003730770925 |
| source_wave_peak_4x_compressed | 4x | 174412 | 114024 | 0 | 0 | 0 | 292.4209465792293 |
| storage_release_peak_4x_compressed | 4x | 174412 | 114024 | 0 | 0 | 0 | 180.88702398825043 |
| late_bag_peak_4x | 4x | 174412 | 114024 | 0 | 0 | 0 | 74.04123981177706 |
| speed_deviation_10_8x | 8x | 348824 | 228048 | 0 | 0 | 0 | 587.7644661759479 |
| speed_deviation_20_8x | 8x | 348824 | 228048 | 0 | 0 | 0 | 580.9562490102518 |
| speed_deviation_30_8x | 8x | 348824 | 228048 | 0 | 0 | 0 | 579.8515768635264 |
| static_fault_selected_8x_arc_4_5 | 8x | 348824 | 149697 | 78363 | 0 | 0 | 249.2203851577304 |
| repair_fault_selected_8x_arc_2_4_6 | 8x | 348824 | 124241 | 103835 | 0 | 0 | 142.2083550398234 |
| mixed_fault_smoke_8x_arc_3_5_8 | 8x | 348824 | 163360 | 64688 | 0 | 0 | 281.62314925500226 |
| rolling_2_day_1x | 1x_2d | 87206 | 57012 | 0 | 0 | 0 | 3.556594496712491 |
| rolling_7_day_1x_smoke | 1x_7d | 32768 | 21940 | 0 | 0 | 0 | 3.421655282276637 |

Every generated high-flow task stream keeps the real map unchanged and declares `generation_level`, `release_semantics`, and `tth_denominator`. Rows marked as blocker/not-run are retained explicitly instead of being replaced by smaller hidden samples.

Safety interpretation: the no-fault 1x/2x/4x/8x/16x ladder completed with `0` node conflicts and `0` runtime full A* calls. This is a scale-execution pass, not a blanket high-flow latency win.

| Scenario | Backlog | Max Queue Delay | Mean THT | p99 THT |
| --- | --- | --- | --- | --- |
| high_flow_no_fault_32x_smoke | 420704 | 420703 | 59.79003731 | 149.17691933 |
| high_flow_no_fault_16x | 179744 | 179743 | 1551.371367 | 3773.31410471 |
| high_flow_no_fault_8x | 60556 | 60555 | 590.21708243 | 1496.81279776 |
| speed_deviation_10_8x | 60556 | 60555 | 587.76446618 | 1483.74560219 |
| speed_deviation_20_8x | 60556 | 60555 | 580.95624901 | 1447.62813453 |
| speed_deviation_30_8x | 60556 | 60555 | 579.85157686 | 1429.95302463 |

Negative evidence retained: source queue backlog and THT tails grow sharply at 4x/8x/16x. These rows are the main v3 hard-case data source; they are not promoted as paper-main claims.

Fault diagnostic rows: `3`. Their failed segments are categorized as fault-mode evidence and kept separate from the no-fault v2-safe paper-main claim.
