# G4IRSF32 V3R14 Candidate B minimal preregistration

Protocol: `G4IRSF32_V3R14_CANDIDATE_B_UNCOVERED_WORK_20260829`  
Status: `FROZEN_BEFORE_IMPLEMENTATION_OR_CANDIDATE_B_OUTCOME`

## 1. Why Candidate B starts

V3R13 Candidate A completed its frozen 10-case/20-execution Stage 2 and is
`NO_GO_V3R13_CANDIDATE_A_STAGE2`.  It preserved completion and safety and was
exact on map2, but Nanning target P95 improved in zero of six cases.  This is
the original action plan's condition for starting Candidate B after A proved
mechanically valid but insufficient.

Candidate C is not started.  No Stage 3 or Stage 4 run is authorized.

## 2. The only Candidate B production change

Add one append-only scorer spelling:

`S4_uncovered_local_work_seconds_rule_only`

It remains in the existing S4 family and keeps the existing one-hop
potential-descent guard, direct-neighbour calendar visibility, J2 authority,
fault shield, tie break and reservation depth.

For a direct candidate neighbour `v` and current bag goal `g`:

`uncovered_local_work_seconds(v,g)` is zero when `v` does not use destination
service under the active resource contract.  Otherwise it is the service
work represented by `v.source_queue` at that instant.

This queue is the existing local source queue.  Its members are already
released and ready, and they have not received a service-calendar
reservation.  The quantity is therefore obtainable in O(1) from queue size
and the existing node service quantum.  It excludes ordinary junction queue,
scheduled incoming, in-service and J2 pending work, all of which would either
represent a different resource or duplicate existing calendar wait.

The Candidate B score is exactly:

`travel + potential + corridor_wait + target_calendar_wait + uncovered_local_work_seconds`

The coefficient is fixed at 1.  The old
`target_queue_length + target_scheduled_incoming` term is replaced, not added.
There is no new parameter, stateful planner, model, global scan, future task
read, map ID branch or multi-step reservation.

The old `S4_queue_aware_rule_only` path remains byte-for-byte unchanged.
Candidate A `closed_loop` remains unchanged and may be combined with the new
scorer; once A reserves a local source bag it leaves `source_queue`, while the
existing calendar wait represents the reservation, preventing double count.

## 3. Minimal pre-action gate

Before any real-map Candidate B outcome:

1. A pure native helper must return 0/1/2 and 0/3/6 work-seconds for 0/1/2
   ready local bags at 1 s and 3 s service.
2. A future-release bag must not contribute before release.
3. After Candidate A reserves one local bag, uncovered work must fall by one
   service quantum and the existing calendar wait must carry the reservation.
4. The new scorer's raw score must equal the frozen formula and must change a
   synthetic ranking when two legal neighbours differ only in uncovered work.
5. Old S4, default-off and G31 regression tests must remain exact.
6. All bags complete with zero failed/conflict/unsafe/full-A*/model/global/
   future-route counters and one-hop depth.

Failure stops before a real-map screen.  This gate is a fixed mechanism check,
not a parameter search.

## 4. Outcome-blind real-map screen

Reuse, without reselecting, every population, case, fault and threshold from
V3R13 Stage 2.  Run three fixed arms from the same prepared request:

- `off`: original G31-compatible S4, Candidate A absent;
- `candidate_a`: old S4 plus Candidate A `closed_loop`;
- `candidate_a_b`: new Candidate B scorer plus Candidate A `closed_loop`.

The primary effect comparison is `candidate_a_b / off`; `candidate_a_b /
candidate_a` is attribution only.  This is an ablation, not a parameter grid.

The core screen uses the unchanged gates that current payload can measure:

- completion does not fall and all statically reachable timing cohorts match;
- hard safety and no-new-starvation pass;
- Nanning target P95 is at most 0.98 of off;
- Nanning whole mean is at most 1.005 and P95/P99 at most 1.01 of off;
- source-wait reduction is not merely transferred to network wait with total
  latency unchanged;
- map2 mean/P95/P99 are each at most 1.005 of off;
- events/completed, wall and each ordinary queue peak are at most 1.10 of off.

The start-49 source-wait proxy is reported but cannot sign the full
mixed-origin integral.

If any core performance or safety gate fails, archive Candidate B as NO-GO
without first building an RSS worker or continuous mixed-origin tracker.  If
and only if the core screen passes, add the smallest measurement-only support
for isolated peak RSS and exact mixed-origin wait-area/idle-while-ready, then
rerun the same cases and unchanged formal thresholds.  Stage 3 remains blocked
until that formal measurement pass.

Registered screen outputs:

- `outputs/tables/g4irsf32_v3r14_candidate_b_screen.json`;
- `outputs/reports/g4irsf32_v3r14_candidate_b_screen.md`.

## 5. Stop and rollback

- Any map2 regression, target-P95 miss, safety failure or resource breach is
  a Candidate B NO-GO and stops before Stage 3.
- Do not tune the coefficient, change the cases or select a different cohort.
- Rollback is selecting the old scorer spelling; Candidate A and all V3R13
  outputs remain intact.
- Candidate C may be considered only after the B result and only if trace
  evidence shows the strict descent guard, rather than another bottleneck,
  is blocking useful legal candidates.
