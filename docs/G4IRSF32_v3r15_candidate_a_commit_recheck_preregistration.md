# G4IRSF32 V3R15 Candidate A commit-triggered source recheck

Protocol: `G4IRSF32_V3R15_CANDIDATE_A_COMMIT_RECHECK_20260829`  
Status: `FROZEN_BEFORE_IMPLEMENTATION_OR_V3R15_OUTCOME`

## 1. Why this is a Candidate A correction

V3R13 proved that the closed-loop future-slot action is safe but acts only
2--5 times per real Nanning case and does not move target P95. V3R14 Candidate
B is permanently `NO_GO`: it gives a small Nanning improvement but removes an
ordinary pressure signal that map2 needs. A complete two-map trace also finds
no useful strict-descent-blocked candidate, so Candidate C is not entered.

The remaining Candidate A coverage gap is an event seam. When a source queue
remains ready, its next wake is normally scheduled at the calendar's then
known next-free time. A later external DIRECT/J2 commit can reserve that same
time. That commit updates the destination calendar and emits a congestion
beacon, but it does not cause the ready source to recheck. Candidate A is then
only reached by an unrelated later release, repair, or superseded wake.

## 2. The only production change

Add one append-only mode spelling:

`closed_loop_commit_recheck`

The historical `closed_loop` mode remains unchanged. In the new mode, process
the existing post-commit `incoming_reservation_snapshot` beacon and request an
earlier source wake at the commit epoch only when all of these are true:

- mode is `closed_loop_commit_recheck`;
- the destination has a non-empty ready `source_queue`;
- a source wake is already pending;
- the destination service calendar is currently busy for one local service
  quantum;
- no future local source owner already exists in that calendar.

The beacon runs after DIRECT/J2 transaction success, so no wake can escape a
rolled-back reservation. In E4 it precedes source arbitration in the fixed
microphase order. Use the existing `schedule_source_wakeup` path; it already
replaces a later pending wake by incrementing its generation; the old event is rejected
through the existing supersession rule. The commit seam does not select a
bag, compare priority, or reserve a second slot. The resulting source event
calls the unchanged `try_admit_source`, which remains the sole authority for:

- FIFO/deadline/aging and pending-external ordering;
- finite-capacity and extension compatibility guards;
- destination-resource eligibility;
- the one-future-local-owner bound;
- the actual service-calendar reservation and existing action counters.

There is no new scorer, state field, counter, parameter, model, global scan,
future task read, map-ID condition, path memory, or multi-step reservation.
Off, shadow, and historical `closed_loop` do not schedule this recheck.

## 3. Pre-action gate

Before any real-map outcome, focused native tests must show:

1. a later DIRECT destination commit supersedes a later pending source wake
   and lets the unchanged Candidate A path reserve exactly one next-free local
   slot;
2. the corresponding J2 path keeps the existing priority winner and the same
   one-owner bound;
3. no source queue, no busy calendar, an existing future local owner, and
   off/shadow/historical closed-loop are no-ops;
4. action count equals calendar-mutation count, all bags complete, and
   failed/conflict/physical-fault/full-A*/global/future/model/two-step counters
   remain zero;
5. the existing V3R13 action gate, V3R14 scorer tests, old S4 identity, and
   V3R2 exact-off proof remain passing.

This gate checks the event seam only. It may not alter a real-map case,
threshold, scorer, workload, or fault.

## 4. Fixed real-map screen

Reuse exactly the V3R13 Stage-2 preregistered populations, ordered segment
IDs, ten semantic cases, faults, 2.5 m/s speed, cohort rules, metrics, and
thresholds. Run three fixed arms from one prepared request:

- `off`: original G31-compatible S4, extension absent;
- `candidate_a`: old S4 plus historical `closed_loop` Candidate A;
- `candidate_a_recheck`: old S4 plus `closed_loop_commit_recheck`.

The primary comparison is `candidate_a_recheck / off`. The recheck/A
comparison is attribution-only and does not decide the primary effect gate.

The core screen must retain all existing gates:

- completion and statically reachable timing cohorts do not fall;
- hard safety, one-hop, no-new-starvation, no model/global/future read pass;
- Nanning target P95 is at most 0.98 of off;
- Nanning whole mean is at most 1.005 and P95/P99 at most 1.01 of off;
- source-wait reduction is not transferred to unchanged total latency;
- map2 mean/P95/P99 are each at most 1.005 of off and map2 action is zero;
- events/completed, wall, source queue, junction queue, and destination
  pending peaks are each at most 1.10 of off.

If a core gate fails, V3R15 is NO-GO and Stage 3 remains blocked. If and only
if the core effect passes, add the smallest measurement-only isolated RSS and
exact mixed-origin wait-area support, then rerun the same cases and unchanged
formal thresholds before Stage 3.

Registered outputs:

- `outputs/tables/g4irsf32_v3r15_candidate_a_commit_recheck_screen.json`;
- `outputs/reports/g4irsf32_v3r15_candidate_a_commit_recheck_screen.md`.

## 5. Stop and rollback

- Do not change retry timing, arbitration order, scorer, coefficient, case,
  cohort, or threshold after seeing the result.
- Do not add a second future local owner.
- Any map2 action/regression, safety failure, resource breach, or Nanning P95
  miss is NO-GO.
- Rollback is selecting historical `closed_loop` or `off`; V3R13/V3R14 code
  and outputs remain auditable and are not overwritten.
