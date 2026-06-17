# Phase2 Active-Bag Replanning Audit

Date: 2026-06-17

## Scope

This diagnostic samples the Python and C++ event-queue replay traces into fixed 5.0s ticks so Phase2C active-bag/replan-cost behavior is visible in a reproducible table. It reports active-bag pressure, decision ticks, decision throughput, task accounting, and post-shield safety on the persisted synthetic manifest.

Manifest: `data/processed/phase8/phase8_synthetic_replay_cases.json`

This is an active-bag periodic audit over the event scheduler, not a route-discarding periodic global replanner and not recursive PIBT.

## Metrics

| Case | Policy | Tasks | Py/C++ planned | Peak active Py/C++ | Active ticks Py/C++ | Decision ticks Py/C++ | C++ decisions/s | Tick parity | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| synthetic_seed7_medium_repair | edge_score_event | 18 | 18/18 | 4/4 | 14/14 | 13/13 | 5068.237 | True | True |
| synthetic_seed7_medium_repair | fallback_event | 18 | 18/18 | 4/4 | 14/14 | 13/13 | 5664.147 | True | True |
| synthetic_seed11_dense_multi_repair | edge_score_event | 24 | 16/16 | 9/9 | 11/11 | 10/10 | 8908.473 | True | True |
| synthetic_seed11_dense_multi_repair | fallback_event | 24 | 16/16 | 9/9 | 11/11 | 10/10 | 9943.711 | True | True |
| synthetic_seed17_static_plus_repair | edge_score_event | 20 | 12/12 | 6/6 | 13/13 | 12/12 | 9309.557 | True | True |
| synthetic_seed17_static_plus_repair | fallback_event | 20 | 12/12 | 6/6 | 13/13 | 12/12 | 7914.943 | True | True |
| synthetic_seed23_repeated_repair | edge_score_event | 22 | 20/20 | 8/8 | 11/11 | 10/10 | 7104.944 | True | True |
| synthetic_seed23_repeated_repair | fallback_event | 22 | 19/19 | 8/8 | 11/11 | 10/10 | 11832.663 | True | True |

CSV: `outputs/tables/phase2_active_bag_replanning_audit.csv`

## Gate Status

- active-bag task-stream audit: PASS
- Python/C++ binned active-bag parity: PASS
- post-shield safety under active bags: PASS
- fault/repair schedule rows included: `8`
- replan cost reported: PASS

## Remaining Work

- implement a true route-discarding periodic SIPP replanner if needed for a separate baseline
- add real heldout airport-map fixtures when available
- carry active-bag cost metrics into Phase9 comparisons
