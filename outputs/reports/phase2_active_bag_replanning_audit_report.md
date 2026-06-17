# Phase2 Active-Bag Replanning Audit

Date: 2026-06-17

## Scope

This diagnostic samples the Python and C++ event-queue replay traces into fixed 5.0s ticks so Phase2C active-bag/replan-cost behavior is visible in a reproducible table. It reports active-bag pressure, decision ticks, decision throughput, task accounting, and post-shield safety on the persisted synthetic manifest.

Manifest: `data/processed/phase8/phase8_synthetic_replay_cases.json`

This is an active-bag periodic audit over the event scheduler, not a route-discarding periodic global replanner and not recursive PIBT.

Route-discarding periodic SIPP replanning is tracked separately in `outputs/reports/phase2_periodic_replanning_parity_report.md`.

## Metrics

| Case | Policy | Tasks | Py/C++ planned | Peak active Py/C++ | Active ticks Py/C++ | Decision ticks Py/C++ | C++ decisions/s | Tick parity | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| synthetic_seed7_medium_repair | edge_score_event | 18 | 18/18 | 4/4 | 14/14 | 13/13 | 7676.418 | True | True |
| synthetic_seed7_medium_repair | fallback_event | 18 | 18/18 | 4/4 | 14/14 | 13/13 | 9093.464 | True | True |
| synthetic_seed11_dense_multi_repair | edge_score_event | 24 | 16/16 | 9/9 | 11/11 | 10/10 | 9352.896 | True | True |
| synthetic_seed11_dense_multi_repair | fallback_event | 24 | 16/16 | 9/9 | 11/11 | 10/10 | 12848.457 | True | True |
| synthetic_seed17_static_plus_repair | edge_score_event | 20 | 12/12 | 6/6 | 13/13 | 12/12 | 10546.917 | True | True |
| synthetic_seed17_static_plus_repair | fallback_event | 20 | 12/12 | 6/6 | 13/13 | 12/12 | 13219.942 | True | True |
| synthetic_seed23_repeated_repair | edge_score_event | 22 | 20/20 | 8/8 | 11/11 | 10/10 | 10235.784 | True | True |
| synthetic_seed23_repeated_repair | fallback_event | 22 | 19/19 | 8/8 | 11/11 | 10/10 | 13345.196 | True | True |

CSV: `outputs/tables/phase2_active_bag_replanning_audit.csv`

## Gate Status

- active-bag task-stream audit: PASS
- Python/C++ binned active-bag parity: PASS
- post-shield safety under active bags: PASS
- fault/repair schedule rows included: `8`
- replan cost reported: PASS

## Remaining Work

- add real heldout airport-map fixtures when available
- carry active-bag cost metrics into Phase9 comparisons
