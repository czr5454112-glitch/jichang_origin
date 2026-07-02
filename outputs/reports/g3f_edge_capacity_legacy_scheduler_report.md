# G3f Edge-Capacity-Aware Legacy-A* Teacher Scheduler

Date: 2026-07-02

## 1. Scope and non-claim boundary

This audit builds an execution-layer scheduler around the Legacy-A* route-intent teacher. It does not train a model, does not start PPO/MAPPO/RL, does not create a broad G4A dataset, does not disable edge capacity, and does not modify legacy Java.

- map: `data/processed/maps/map2.json`
- tasks: `data/processed/tasks/inputdata.jsonl`
- teacher source: `python_faithful_legacy_astar_edge_capacity_scheduler_g3f`

## 2. Prior result anchor

| Metric | Value |
| --- | --- |
| G3c planned | 78/144 |
| G3c blocked/unavailable slices | 614 |
| G3c candidate recall | 1.000 |
| G3c safe recall | 0.610 |
| G3d best primary replay | 94/144 |
| G3d disable-edge-capacity diagnostic | 125/144 with 491 real conflicts |
| G3e semantic fix | repair-window reachability fixed; best primary remained 94/144 |

## 3. Legacy route intent vs runtime execution

The original Legacy Java A* route source is paper-faithful route intent: it plans over graph cost, fault edges, and node time-window style constraints. The current Python/C++ event shield adds runtime safety checks for edge capacity, edge headway, merge groups, and buffer/node capacity. Therefore a Legacy next-hop can be a valid route preference while not being executable at the current event time.

| Label family | Rows |
| --- | --- |
| ROUTE_INTENT_LEGACY | 8776 |
| MOVE_NOW_LEGACY | 6397 |
| ROUTE_INTENT_NO_PATH | 1177 |
| LEGACY_NO_PATH | 1166 |
| WAIT_EDGE_CAPACITY | 996 |
| LEGACY_NEXT_TEMPORARILY_BLOCKED | 372 |
| ABSTAIN_NO_TEACHER | 280 |
| LEGACY_NEXT_GLOBALLY_UNSAFE | 194 |
| WAIT_EDGE_QUEUE | 167 |
| REROUTE_NOW_LEGACY | 57 |
| WAIT_MERGE_GROUP | 21 |
| SIPP_REPAIR_MOVE | 11 |

## 4. Edge release and queue audit

G3f records `2091` edge/node/merge block ledger rows and `2091` release-time rows. These rows keep the hard shield active and explain which occupied intervals force WAIT labels.

Top blocked edges:

| Edge | Rows |
| --- | --- |
| 27->28 | 621 |
| 18->22 | 528 |
| 22->24 | 315 |
| 13->23 | 224 |
| 11->13 | 167 |
| 46->36 | 80 |
| 24->27 | 48 |
| 4->17 | 46 |
| 8->11 | 24 |
| 16->21 | 22 |

## 5. Scheduler variants

| Variant | Planned | Branch exec cov | Route intent | Unresolved edge share | Real conflicts |
| --- | --- | --- | --- | --- | --- |
| capacity_wait_budget_10s | 92/144 | 0.963 | 144 | 0.055 | 0 |
| capacity_wait_budget_30s | 92/144 | 0.963 | 144 | 0.055 | 0 |
| capacity_wait_budget_5s | 96/144 | 0.967 | 144 | 0.054 | 0 |
| capacity_wait_budget_60s | 92/144 | 0.963 | 144 | 0.055 | 0 |
| edge_release_wait_scheduler | 88/144 | 0.932 | 144 | 0.078 | 0 |
| fifo_edge_queue_scheduler | 88/144 | 0.932 | 144 | 0.078 | 0 |
| g3d_reroute_anchor | 94/144 | 0.642 | 144 | 0.778 | 0 |
| hybrid_executable_teacher | 92/144 | 0.958 | 144 | 0.059 | 0 |
| route_intent_only_teacher | 0/144 | 0.000 | 144 | 0.000 | 0 |

G3d reroute anchor reproduces `94/144` planned with `0` real conflicts.
Best executable G3f variant is `capacity_wait_budget_5s` with `96/144` planned, `0.967` branch executable coverage, and `0` real conflicts.
Hybrid executable teacher reaches `92/144`; SIPP/fallback labels remain auxiliary and are not counted as primary Legacy labels.
Route-intent-only teacher coverage is `144/144`; it is suitable for route-ranking/global-guide supervision, not closed-loop action imitation.

## 6. Executable label taxonomy

| Taxonomy | Rows |
| --- | --- |
| MOVE_NOW_LEGACY | 808 |
| WAIT_EDGE_CAPACITY | 159 |
| LEGACY_NO_PATH | 150 |
| ABSTAIN_NO_TEACHER | 32 |
| LEGACY_NEXT_GLOBALLY_UNSAFE | 20 |
| REROUTE_NOW_LEGACY | 11 |
| WAIT_MERGE_GROUP | 3 |

## 7. G4A pilot gate

| Variant | Planned | Branch | Route intent | Unresolved | Eligible |
| --- | --- | --- | --- | --- | --- |
| capacity_wait_budget_10s | 92 | 0.963 | 144 | 0.055 | False |
| capacity_wait_budget_30s | 92 | 0.963 | 144 | 0.055 | False |
| capacity_wait_budget_5s | 96 | 0.967 | 144 | 0.054 | False |
| capacity_wait_budget_60s | 92 | 0.963 | 144 | 0.055 | False |
| edge_release_wait_scheduler | 88 | 0.932 | 144 | 0.078 | False |
| fifo_edge_queue_scheduler | 88 | 0.932 | 144 | 0.078 | False |
| g3d_reroute_anchor | 94 | 0.642 | 144 | 0.778 | False |
| hybrid_executable_teacher | 92 | 0.958 | 144 | 0.059 | False |
| route_intent_only_teacher | 0 | 0.000 | 144 | 0.000 | False |

Diagnostic pass: G3f generated the required route-intent/executable-label split and capacity ledger, but the gate is not met. Do not start G4A or training; continue with G3g scheduler semantics alignment.

## 8. Unresolved capacity blocker

Unresolved edge-capacity rows for the best variant: `29`. If the gate fails, the next step remains scheduler-semantics alignment rather than training.

## Artifacts

- Edge block ledger: `outputs/tables/g3f_edge_block_ledger.csv`
- Edge release audit: `outputs/tables/g3f_edge_release_time_audit.csv`
- Edge queue replay summary: `outputs/tables/g3f_edge_queue_replay_summary.csv`
- Route intent vs executable labels: `outputs/tables/g3f_route_intent_vs_executable_labels.csv`
- Wait label taxonomy: `outputs/tables/g3f_wait_label_taxonomy.csv`
- Scheduler variant comparison: `outputs/tables/g3f_scheduler_variant_comparison.csv`
- Hotspot timeline: `outputs/tables/g3f_hotspot_edge_capacity_timeline.csv`
- Unresolved cases: `outputs/tables/g3f_unresolved_capacity_cases.csv`
- G4A pilot eligibility: `outputs/tables/g3f_g4a_pilot_eligibility.csv`
- Route-intent JSONL sample: `artifacts/teacher/legacy_astar/g3f_route_intent_teacher_sample.jsonl`
- Executable wait JSONL sample: `artifacts/teacher/legacy_astar/g3f_executable_wait_teacher_sample.jsonl`
- Hotspot figure: `outputs/figures/g3f_edge_hotspot_timeline.png`
