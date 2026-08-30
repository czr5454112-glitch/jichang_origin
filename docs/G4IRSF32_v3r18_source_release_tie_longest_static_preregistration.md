# G4IRSF32 V3R18 source release-tie longest-static preregistration

Protocol identity:
`G4IRSF32_V3R18_SOURCE_RELEASE_TIE_LONGEST_STATIC_20260829`.

Frozen on 2026-08-29 (Asia/Shanghai), before implementation, build, or any
V3R18 native outcome.

## 1. Why the next action moves out of the scorer

V3R17 was cross-map safe and improved all six Nanning target P95 values, but
only by about 0.47%--0.98%, below the unchanged 2% gate. Complete stable-1x
bag/event inspection shows that the old P95 boundary is dominated by the
simultaneous storage-source burst at start 53. Representative bags spend
about 29--35 seconds before source admission and 221--263 seconds in junction
queues at nodes 53/49. Their later multi-candidate decisions already select
the shorter type-4 path in most cases. Another route score cannot remove the
dominant wait.

Historical FIFO resolves bags with the same source enqueue time by runtime bag
ID. A read-only permutation reused each bag's observed first-edge commit slot
and observed post-commit residual, changing only which simultaneously released
bag receives which already-existing slot. Ordering the longer static remainder
first gave these diagnostic P95 ratios:

- Nanning 1x: 0.9053;
- Nanning 2x: 0.9685;
- map2 1x: 0.9437;
- map2 2x: 0.9554.

The diagnostic mean ratio is exactly 1 by construction because the same slots
and residuals are merely permuted. These values are not a closed-loop outcome
or a GO claim; they establish a cross-map, parameter-free reason to test one
source-order tie-break.

## 2. Frozen single action

Add one append-only queue-discipline spelling:
`fifo_source_longest_static_tie`. Default `fifo` and every historical spelling
remain unchanged.

At an existing local source queue under Q0, choose the minimum tuple

`(source_enqueued_at, -static_potential(current_node, goal_node), runtime_bag_id)`.

Consequences are deliberately narrow:

1. an earlier source enqueue always remains ahead of a later enqueue;
2. only an exact source-enqueue timestamp tie uses the longer precomputed
   static remainder;
3. every junction queue retains historical FIFO ordering;
4. the existing escape-token authority remains ahead of this comparator;
5. scorer ranking, source service, first-edge ownership, calendars, merge
   grants, faults, reservations, and physical timing are unchanged.

The action uses the already materialized local source queue and immutable
static potential. It adds no state, counter, coefficient, threshold, model,
map/node special case, future route, full A*, global scan, or new reservation.

## 3. Minimum pre-action verification

Verify only the material contracts:

- two same-time source bags choose the longer static remainder first;
- an earlier source enqueue remains first regardless of static remainder;
- the same two bags in a junction queue preserve historical FIFO;
- historical `fifo` remains exact and the run stays one-hop with zero full A*,
  global scan, and future-route reads.

Do not add malformed-input matrices or one test per internal branch.

## 4. Fixed real-map screen and gates

Reuse the exact V3R13 ten cases, populations, target cohorts, faults, and
thresholds. Run three arms per case:

- `off`: historical S4 and extension off;
- `candidate_a`: historical S4 plus Candidate A closed loop;
- `candidate_a_source_tie`: Candidate A plus only
  `fifo_source_longest_static_tie`.

The primary comparison is `candidate_a_source_tie / off`; Candidate A is
attribution-only. Core GO still requires every original completion, safety,
resource, Nanning target-P95, whole-system, map2, and no-wait-transfer gate.
Do not add RSS or the exact mixed-origin wait/idle integral unless the core
screen passes. A core pass is only `MEASUREMENT_REQUIRED`, never Stage-3 GO.

Registered append-only outputs:

- `outputs/tables/g4irsf32_v3r18_source_release_tie_screen.json`;
- `outputs/reports/g4irsf32_v3r18_source_release_tie_screen.md`.

Any core failure is archived as `NO_GO_V3R18_SOURCE_RELEASE_TIE`; the order is
not widened to later releases, applied to junction queues, weighted, or made
map-specific after seeing the result.
