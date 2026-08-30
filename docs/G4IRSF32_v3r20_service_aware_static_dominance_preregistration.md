# G4IRSF32 V3R20 service-aware static-dominance preregistration

Protocol identity:
`G4IRSF32_V3R20_SERVICE_AWARE_STATIC_DOMINANCE_20260829`.

Frozen on 2026-08-29 (Asia/Shanghai), before implementation, build, or any
V3R20 native outcome.

## 1. Why this is a distinct minimal hypothesis

V3R17 required a replacement type-4 neighbour to be strictly better than the
historical non-goal type-2 winner in both `travel + static_potential` and the
next node's immediate service duration.  That guard improved every Nanning
target P95 but reached only about 0.47%--0.98% and missed one of the two 2x
P95 interpolation-support bags.

The frozen G31 potential contract is service-aware:

`H(u,g) = service_duration(u) + min_(u,v)(travel(u,v) + H(v,g))`.

Consequently `travel(current,candidate) + H(candidate,goal)` already includes
the candidate's immediate service and all later non-goal service.  Requiring
the immediate service duration to be lower a second time is not needed to
prove a lower static completion cost.  It excluded a real 2x support-bag
decision whose type-4 base was 0.168 seconds lower even though its immediate
service was one second longer; adding that service again would double count
what `H` already contains.

Read-only complete stable-trace coverage before implementation is:

- Nanning 1x: 516 rankings across 381 segments; 9 of the 15 bags above the
  frozen 2% P95 line, including both interpolation-support bags;
- Nanning 2x: 1,194 rankings across 730 segments; 16 of the 19 bags above the
  frozen 2% P95 line, including both interpolation-support bags;
- map2 1x/2x stable: zero qualifying rankings.

These counts prove only necessary coverage and a cross-map negative-control
direction.  They do not predict a closed-loop result or authorize Stage 3.

## 2. Frozen single action

Add one append-only scorer spelling:
`S4_service_aware_static_dominance_rule_only`.  Default/off and all historical
scorer spellings remain unchanged.

After historical S4 ranking and the existing strict-potential-descent guard,
let the current first candidate be `w`.  The guard acts only when:

1. `w` is shield-allowed, not advertised-faulted, type 2, and is not this
   bag's goal;
2. first-edge credit is not active for this decision;
3. an already-materialized candidate `d` is shield-allowed,
   not advertised-faulted, type 4, and survived the same strict-descent guard;
4. `d.travel_time + d.static_potential` is strictly lower than the same
   service-aware total for `w`.

If one or more candidates qualify, move the minimum tuple
`(travel_time + static_potential, next_node)` to the front.  Do not separately
add or compare immediate service: the frozen potential already includes it.
Do not alter candidate scores, calendars, queues, reservations, merge grants,
fault policy, or later authorities.  If no candidate qualifies, preserve the
historical ranking exactly.

The action scans only the already-materialized one-hop candidates.  It adds no
state, counter, coefficient, threshold, model, map/node special case, future
route, full A*, global scan, reservation, or policy layer.

## 3. Minimum pre-action verification

Use one compact native motif to prove the material behavior:

- historical S4 selects a non-goal type-2 neighbour because of its current
  local pressure score;
- the new spelling selects a type-4 neighbour whose service-aware
  `travel + potential` is strictly lower even though its immediate service is
  longer;
- historical candidate scores remain unchanged, selection is one-hop, and
  full A*, global scans, future-route reads, and future-schedule reads remain
  zero.

Reuse existing regression coverage for faults, escape, merge ownership, and
old scorer spellings.  Do not add malformed-input matrices or one test per
internal branch.

## 4. Fixed real-map screen and stop rule

Reuse the exact V3R13 ten cases, populations, target cohorts, faults, metrics,
and thresholds.  Run three fixed arms per case:

- `off`: historical S4 and extension off;
- `candidate_a`: historical S4 plus Candidate A closed loop;
- `candidate_a_static_dominance`: Candidate A plus only
  `S4_service_aware_static_dominance_rule_only`.

The primary comparison is `candidate_a_static_dominance / off`; Candidate A
is attribution-only.  Core GO still requires every original completion,
safety, resource, Nanning target-P95, whole-system, map2, starvation, and
no-wait-transfer gate.  Do not add RSS or the exact mixed-origin wait/idle
integral unless the core screen passes.  A core pass is only
`MEASUREMENT_REQUIRED`, never Stage-3 GO.

Registered append-only outputs:

- `outputs/tables/g4irsf32_v3r20_service_aware_static_dominance_screen.json`;
- `outputs/reports/g4irsf32_v3r20_service_aware_static_dominance_screen.md`.

Any core failure is archived as
`NO_GO_V3R20_SERVICE_AWARE_STATIC_DOMINANCE`.  After seeing the result, do not
add a service margin, coefficient, node/type list, map exception, or combine
this rule with V3R17/V3R18.  A failure ends this guard family.
