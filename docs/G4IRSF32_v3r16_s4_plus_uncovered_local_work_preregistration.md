# G4IRSF32 V3R16 S4 plus uncovered local work

Protocol: `G4IRSF32_V3R16_S4_PLUS_UNCOVERED_LOCAL_WORK_20260829`  
Status: `FROZEN_BEFORE_IMPLEMENTATION_OR_V3R16_OUTCOME`

## 1. Evidence for this correction

V3R15 added no observable behavior on the fixed real slices: historical A and
A+recheck have identical actions, deterministic events, queues, safety and
performance in all ten cases. More DIRECT/J2 wake choreography is therefore
not supported.

V3R14 supplies a narrower positive signal. Replacing the old S4 pressure term
with ready source work lowered every Nanning target P95 by about 0.56%--1.39%,
but it also removed ordinary target queue/scheduled-incoming pressure and
caused map2 regressions. The ready `source_queue` is disjoint from those old
pressure fields and contains only released work without a service reservation;
Candidate A removes an item when it obtains a future slot. The smallest
correction is therefore to retain the old S4 signal and add only the missing,
already-implemented uncovered source work.

## 2. The only production change

Add one append-only scorer spelling:

`S4_queue_aware_plus_uncovered_local_work_seconds_rule_only`

Its score is exactly historical S4 plus:

`source_queue.size() * service_duration(candidate.next_node)`

through the existing pure `uncovered_local_work_seconds` helper and only when
the candidate uses the destination service calendar. Historical S4 and the
V3R14 replacement spelling remain unchanged.

No new state, counter, queue, coefficient, planner, model, scan, map-ID branch,
future input, route memory or reservation is allowed. Candidate A stays the
historical `closed_loop`; this revision changes only the scorer term.

## 3. Pre-action gate

Before a real-map outcome:

1. an empty source queue is score-identical to historical S4;
2. one and multiple ready source items add exactly one local service quantum
   per item, including non-1-second service times;
3. a Candidate-A reserved item is no longer in `source_queue` and is not
   counted twice;
4. a fixed small graph shows the intended ranking change while a no-source
   graph is exact;
5. old S0--S4, the V3R14 spelling, exact-off, safety, one-hop and zero
   global/future/model counters remain passing.

## 4. Fixed real-map screen

Reuse the V3R13 Stage-2 registration without changing cases, populations,
faults, speed, cohorts or thresholds. Run exactly three arms:

- `off`: historical S4, extension absent;
- `candidate_a`: historical S4 plus historical `closed_loop`;
- `candidate_a_plus_work`: new scorer plus historical `closed_loop`.

The primary comparison is `candidate_a_plus_work / off`; the comparison with
historical A is attribution only. Retain every existing completion, safety,
one-hop, no-model/global/future, no-new-starvation, map2 and 10% resource gate.
The Nanning gates remain target P95 at most 0.98 of off, whole mean at most
1.005, whole P95/P99 at most 1.01, and no source-to-network transfer with
unchanged total latency. Map2 mean/P95/P99 remain at most 1.005 of off.

If any core gate fails, V3R16 is NO-GO and Stage 3 remains blocked. Only if the
core effect passes may the smallest isolated RSS and exact mixed-origin
wait-area measurement be added and the same cases rerun before Stage 3.

Registered outputs:

- `outputs/tables/g4irsf32_v3r16_s4_plus_uncovered_local_work_screen.json`;
- `outputs/reports/g4irsf32_v3r16_s4_plus_uncovered_local_work_screen.md`.

## 5. Stop rule

Do not tune a coefficient, case, cohort or threshold after outcome. Do not
remove either historical scorer signal. Any map2 regression, safety/resource
breach or Nanning P95 miss is NO-GO; preserve the result and do not build
nonessential telemetry for a failed core.
