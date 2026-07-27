# G4IRSF13 Localized Legacy Control Design

Date: 2026-07-27

status: `STATIC_DESIGN_READY_FOR_CONTROLLED_AB`
runtime_scope: `ONE_NEXT_EDGE_RESERVATION_DEPTH_ONE`

## What the legacy Java actually does

`RUN/Main.java` sorts each per-source list with `(int)(o1.pass_time-o2.pass_time)`. Java truncates toward zero, so sub-second differences compare equal; `Collections.sort` then retains input order for those ties. This is a coarse pass-time comparator, not equations 4.2-4.5.

`Tasks.generate_tasks` considers at most the head item of each real source per epoch, requires `pass_time-epoch < 1`, and does not generate from a source that already has an unfinished task. `ICS_PathFinding` appends new tasks to `unfinishTasks`, removes from the head, and appends an unplanned task back to the tail.

Fault-affected temporary tasks are also sorted by the coarse integer pass-time comparator. On repair, a non-complete affected task is collected for processing. Legacy code then runs A* and stores a route; only the collect/re-enter lifecycle is eligible for migration.

## Q0-Q3 priority controls

| Variant | Name | Ordered local components | Boundary |
| --- | --- | --- | --- |
| Q0 | current_f2 | frozen current F2 priority | Must remain bitwise/deterministically unchanged. |
| Q1 | thesis_exact_local_projection | fault-affected desc; slack asc; current-contention desc; entry-sequence asc; stable-id asc | Local contention replaces future-route conflict; Q1 is not a numeric reproduction of equation 4.2. |
| Q2 | thesis_type_slack_aging | task-type desc; slack asc; age desc; current-contention desc; stable-id asc | No future route, global task list, or invented thesis weights. |
| Q3 | fault_slack_age_stable_id | fault-generation desc; slack asc; age desc; stable-id asc | Stable ID is a deterministic final tie-break, not a performance feature. |

All keys are deterministic and lower keys run first. Slack and age come from the current bag and event time. Current-contention means contention for a current next-edge candidate, never an inspection of a future route.

## B2 legacy_order_one_step_diagnostic

B2 reproduces only the legacy coarse pass-time order at a ready queue. It then invokes the same bounded candidate enumeration, safety shield, resource semantics, P2 mode, and single-edge commit as the event runtime. A sub-second comparator tie is resolved by preserved enqueue sequence and stable ID.

B2 is diagnostic-only and must report:

- `reservation_depth = 1`;
- one committed next edge per bag decision;
- `runtime_full_astar_calls = 0`;
- `future_routes_stored = 0`;
- `global_reservation_scans = 0`;
- identical physical interlock and atomic P2 validation.

A result produced by calling legacy A*, retaining `saved_routes`, or inspecting the global reservation table is not B2 and must fail closed.

## Repair re-entry contract

1. DDI applies a monotone fault/repair generation to the local overlay.
2. BTI anchors the affected bag at its actual current safe node.
3. Unconsumed credit and uncommitted P2 proposals touching the fault are invalidated.
4. A repaired, non-complete bag is re-enqueued once with its original identity and age.
5. Q1/Q2/Q3 may prioritize it; the physical shield and P2 validation remain authoritative.
6. The decision selects at most one available next edge or holds.

## EBS/source 52 and goal-completion contract

An early raw bag is two runtime segments: storage-in ends at real terminal node 47; storage-out later enters at real source 52 at `STD-2700`. Storage-in completion is not raw-bag completion. The raw bag completes only after storage-out reaches its final goal. A direct raw bag completes after its single segment.

Primary G4IRSF13 TTH uses final raw-bag completion relative to original entry, so EBS dwell appears once. Any legacy segment-sum transport metric that excludes inter-leg dwell must remain separately named.

## Required experiment order

Run deterministic unit checks, real-map merge/split/bridge/EBS motifs, then 144, 512, 2048, 8192, and at most four top full cases. Q0 remains the control. Priority changes cannot be credited when lower source wait is offset by a larger network time or a p95/p99 regression.
