# G4IRSF32 V3R22 pending-request head-of-line bypass preregistration

Protocol identity:
`G4IRSF32_V3R22_PENDING_REQUEST_HOL_BYPASS_20260830`.

Frozen on 2026-08-30 (Asia/Shanghai), before implementation, build, or any
V3R22 native outcome.

## 1. Problem and entry evidence

Under E4 with JIT destination-merge grants, an upstream bag remains in its
junction queue after publishing a request.  If the same bag is selected again
while that request is pending, `submit_destination_merge_request` returns
success without publishing another request, and the dispatch reports zero
committed edges.  When the queue still contains unrepresented work, the next
wakeup repeats after the existing 0.25-second retry interval.  This is
request-publication head-of-line blocking; it neither represents physical
service nor advances another ready bag.

Read-only complete Candidate-A stable traces from the existing V3R20 binary
showed:

| slice | duplicate pending-owner selections | duplicates with another unrepresented bag | filtered-first target boundary coverage | filtered-first P95 support coverage |
|---|---:|---:|---:|---:|
| Nanning 1x | 4,205 | 4,029 | 14 / 15 | 2 / 2 |
| Nanning 2x | 11,306 | 11,074 | 18 / 19 | 1 / 2 |
| map2 1x | 1,909 | active; 441 request episodes | n/a | n/a |
| map2 2x | 5,343 | active; 1,058 request episodes | n/a | n/a |

The largest observed pending ages were 184.79631 seconds at Nanning 1x and
659.36229 seconds at Nanning 2x.  An initial probe attributed the 14/15 and
19/19 boundary coverage to repeated pending owners.  Before implementation,
an independent queue replay corrected the action attribution to the
filtered-first values above.  Across pending-request episodes, the first
eligible alternative later used a different destination in 56/336 and 99/817
Nanning episodes (and later used DIRECT in 7 and 15), so the action can expose
independent work rather than merely exchange one destination slot.  Map2 is
also active: 92/441 and 131/1,058 episode-first alternatives later used a
different destination.  These counts prove a material action seam and limited
tail coverage only; they do not predict closed-loop benefit, and map2 remains
a mandatory negative-regression control.

## 2. Frozen single action

Add one append-only junction queue discipline:
`fifo_junction_skip_pending_merge_owner`.

At an ordinary junction dispatch under E4/JIT:

1. inspect only the existing local queue and each queued bag's existing
   destination-merge `pending_request_id`;
2. if at least one bag has no pending request, select the highest-priority such
   bag using the unchanged historical queue comparator and stable tie break;
3. if every queued bag is already represented, retain the historical choice;
4. source queues retain historical FIFO selection.

The rule does not cancel, replace, accelerate, or reprioritize an existing
request.  It does not issue more than one new request or commit more than one
edge per existing dispatch opportunity.  JIT/M3 destination ownership, exact
calendar availability, queue capacity, grant expiry, faults, shields, PIBT,
Candidate A, and the existing retry cadence remain unchanged.

The action is an O(local queue length) scan over existing state.  It adds no
persistent state, coefficient, threshold, model, map/node/type special case,
future route, two-hop observation, global scan, new resource capacity, or new
runtime event.

## 3. Minimum pre-action verification

Use one compact native motif with two ready bags at one upstream junction:

- the historical FIFO owner already has a live JIT merge request whose exact
  destination slot is not yet committed;
- another ready bag has no pending request;
- historical FIFO reselects the represented owner and advances no edge/request;
- the new discipline selects the unrepresented bag while leaving the first
  request, calendar, generation, and destination arbitration intact;
- when no pending owner exists, when all owners are pending, at source queues,
  and with the old queue spellings, behavior remains exact;
- full A*, global scans, future-route reads, future-schedule reads, and more
  than one edge per bag remain zero.

Do not add malformed-input matrices or one test per internal branch.

## 4. Fixed real-map core screen and stop rule

Reuse the exact V3R13 ten cases, populations, target cohorts, faults, metrics,
and thresholds.  Run three fixed arms per case:

- `off`: historical S4 and Candidate A off;
- `candidate_a`: historical S4 plus Candidate A closed loop;
- `candidate_a_hol_bypass`: Candidate A plus only
  `fifo_junction_skip_pending_merge_owner`.

The primary comparison is `candidate_a_hol_bypass / off`; Candidate A is
attribution-only.  Every original completion, hard-safety, resource, Nanning
target-P95, whole-system, map2, starvation, and no-wait-transfer core gate must
pass.  A pending-request peak or any other measured core resource above 1.10
is a failure.  Do not measure isolated RSS or the complete mixed-origin
wait/idle integral unless all core gates pass.

A core pass is only `MEASUREMENT_REQUIRED`, never Stage-3 authorization.  A
core failure is archived as `NO_GO_V3R22_PENDING_REQUEST_HOL_BYPASS`; do not
add destination/node guards, a retry threshold, a same-destination exception,
an immediate multi-dispatch loop, or combine the action with a failed scorer.

Registered append-only outputs:

- `outputs/tables/g4irsf32_v3r22_pending_request_hol_bypass_screen.json`;
- `outputs/reports/g4irsf32_v3r22_pending_request_hol_bypass_screen.md`.
