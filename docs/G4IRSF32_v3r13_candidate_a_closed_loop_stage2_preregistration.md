# G4IRSF32 V3R13 Candidate A closed-loop and Stage 2 preregistration

Protocol identity:
`G4IRSF32_V3R13_CANDIDATE_A_CLOSED_LOOP_STAGE2_20260829`.

Frozen on 2026-08-29 (Asia/Shanghai), after the formal V3R12 P0 GO and
before any `closed_loop` implementation, build, synthetic action result, or
real-map candidate outcome.

## 1. Authority and scope

V3R12 established all of the following on the same G32 shadow binary:

- immutable Stage 0/1 evidence deep-replayed all 120 safety and 24
  identification cases with PASS;
- both active G31 controls completed 62/62 bags and passed every hard gate;
- both Nanning scales stored one real node-49/upstream-53 mixed-origin
  observation with no action, calendar mutation, future read, or global scan.

This authorizes Candidate A only.  V3R13 does not start Candidate B or C,
change a threshold, revise a historical NO-GO, or claim that the V3R12
engineering canary estimates prevalence or effect size.

## 2. The single closed-loop change

Add the append-only mode `closed_loop` to the existing
`source_aware_destination_service_mode`; `off` remains the default and
`shadow` remains action-inert.

The only new action occurs inside the existing source-admission path at the
current service node.  For the already-selected, already-released local
source head at time `t`, with local service duration `s`:

1. retain the ordinary immediate admission whenever `[t,t+s)` is available;
2. otherwise require that the bag needs the node's destination service and
   that this same node currently records external scheduled incoming or a
   bounded destination-merge pending request;
3. never displace or rewrite an existing calendar interval;
4. if a destination-merge pending request exists, compare its best current
   contender with the local head using the already-configured
   FIFO/deadline/aging ordering and the existing starvation band; a local
   future slot is permitted only when the local head strictly precedes the
   best pending external contender;
5. reserve exactly one owner-bound interval
   `[earliest_start(t,s), earliest_start(t,s)+s)` in the same
   `JunctionState::service_calendar` already used by local, DIRECT, and J2
   work;
6. remove that local owner from `source_queue`, record its actual service
   start as the reserved start, and use the existing service-completion event;
7. let the existing source wakeup logic reconsider the next local head only
   at the next available calendar time.  It must not bulk-reserve the local
   queue.

The calendar remains the sole physical service authority.  There is no local
sentinel edge, self-edge, second arbiter, multi-step reservation, route suffix,
full A*, learned model, global task scan, future-release read, map-ID branch,
or new tuning coefficient.  Existing external reservations and move-only J2
capabilities remain immutable.  Later DIRECT/J2 decisions simply observe the
new exact local owner in the same calendar.

The V3R12 canary can improve its chosen local bag by at most one service
quantum because 60 external slots were already committed before that local
release.  V3R13 must not describe this as removing the entire prior wait.

## 3. Minimum action evidence before Stage 2

The new build must pass all of the following before any real-map candidate
case is run:

- omitted/default `off` remains exact with the frozen G31 call shape and has
  no G32 output;
- explicit `shadow` remains action-inert and preserves ordinary actions,
  completion, timing, calendar, events, and state;
- DIRECT and J2 mixed-origin motifs each produce at least one real
  `closed_loop` action, exact one-owner service intervals, completion of both
  origins, and no duplicate reservation;
- a reverse-priority J2 motif lets the earlier or more urgent external
  contender win;
- no-local, no-external, and immediately-available controls are exact no-ops;
- changing a task whose release is later than the decision time cannot alter
  the action or reserved slot;
- failed, conflict, unsafe, stranded, stale, full-A*, model, global-scan,
  future-route, future-release-read, and reservation-depth violations are
  zero;
- events per completed bag and locally accounted memory stay within 1.10 of
  the paired control.

Reuse the existing action-change and calendar-mutation counters.  Record the
local task/node and reservation interval through the ordinary event trace;
do not add a second large evidence schema merely for the action.

Registered pre-Stage-2 outputs:

- `outputs/tables/g4irsf32_v3r13_closed_loop_stage01.json`;
- `outputs/reports/g4irsf32_v3r13_closed_loop_stage01.md`.

## 4. Outcome-blind Stage 2 slice

The Stage 2 population is selected without reading any Candidate A outcome.
For each 1x/2x canonical workload:

1. take anchor task IDs having at least one segment with
   `19200.0 <= pass_time < 19800.0`;
2. close over those task IDs and retain every lifecycle segment belonging to
   each selected raw bag;
3. preserve canonical segment order and all original releases, goals, roles,
   and services;
4. use exactly the same ordered segment IDs on Nanning and map2.

The frozen expected population is:

- 1x: 540 raw task IDs and 998 lifecycle segments;
- 2x: 877 raw task IDs and 1,599 lifecycle segments;
- Nanning window composition before lifecycle closure: 147 external start-53
  and 42 local start-49 rows at 1x, and 147 external plus 71 local at 2x.

Before Candidate A is executed, an exact-off G31 trace must confirm that the
selected Nanning target traffic traverses `50->25` at least once and traverses
`100->102` zero times.  Failure is a pre-candidate NO-GO; the cases must not be
reselected after seeing a `closed_loop` result.

## 5. Fixed Stage 2 cases

All cases use 2.5 m/s and run paired `off`/`closed_loop` arms with identical
population and fault input.

Nanning, for each scale 1x and 2x:

- `g4irsf32_s2_nanning_{scale}x_stable_2p5`;
- `g4irsf32_s2_nanning_{scale}x_fault_source_chain_active_single_1`, reusing
  registered `single_1`, edge `50->25`;
- `g4irsf32_s2_nanning_{scale}x_fault_source_chain_inactive_single_8`,
  reusing registered `single_8`, edge `100->102`.

Map2, for each scale 1x and 2x:

- `g4irsf32_s2_map2_{scale}x_stable_2p5`;
- `g4irsf32_s2_map2_{scale}x_fault_sentinel_single_1`, reusing registered
  `single_1`, edge `6->12`.

This is 10 semantic cases and 20 paired executions.  The map2 start nodes
have indegree zero and therefore form the structural mixed-origin negative
control; any action change there is a hard failure unless the trace proves an
equivalent genuine mixed-origin service node.

Registered Stage 2 outputs:

- `outputs/tables/g4irsf32_v3r13_stage2_preregistered_cases.json`;
- `outputs/tables/g4irsf32_v3r13_stage2_campaign.json`;
- `outputs/reports/g4irsf32_v3r13_stage2_campaign.md`.

## 6. Unchanged Stage 2 decision gates

Safety and resource gates are the original action-plan gates: completed may
not fall; all safety counters and full A*/model/global scan/future route stay
zero; events/completed, wall, RSS, and peak queue must each be at most 1.10 of
control.

Nanning GO additionally requires target mixed-origin wait-area to fall at
least 5% or idle-while-ready to fall at least 50%, target-cohort P95 to fall at
least 2%, whole-system mean regression no worse than 0.5%, and whole-system
P95/P99 regression no worse than 1%.  A source-wait reduction offset by equal
network wait with unchanged total latency is not a GO.

Map2 mean/P95/P99 may not regress by more than 0.5%, and completed may not
fall.  Any failed hard or performance gate stops before Stage 3; thresholds
and cases are not changed after outcome.
