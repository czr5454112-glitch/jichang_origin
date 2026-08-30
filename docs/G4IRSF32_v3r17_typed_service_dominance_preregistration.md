# G4IRSF32 V3R17 typed service-dominance preregistration

Protocol identity:
`G4IRSF32_V3R17_TYPED_SERVICE_DOMINANCE_20260829`.

Frozen on 2026-08-29 (Asia/Shanghai), before implementation, build, or any
V3R17 native outcome.

## 1. Why this is the only next candidate

V3R15 proved that Candidate A's commit recheck was outcome-identical to the
historical Candidate A. V3R16 proved that adding uncovered local-source work
to historical S4 changed no committed route in the ten Stage-2 cases.
Complete V3R14 trace decomposition then showed that its Nanning benefit and
map2 harm both came from globally deleting `target_scheduled_incoming`.
Queue, uncovered-work, calendar-covered, goal-conditioned, and FIFO-to-aging
alternatives did not separate the two maps and are not continued.

The remaining observed Nanning benefit has one parameter-free typed-service
structure. Historical S4 sometimes selects a non-goal type-2 unloader even
though a legal type-4 diverter neighbour is strictly better in both static
remaining travel cost and destination service duration. This condition is
absent from both stable map2 slices. It is a Pareto-dominance guard, not a
node ID, map ID, learned model, coefficient, or route suffix.

Read-only complete-trace counts before implementation are:

- Nanning 1x: 288 guarded rankings across 184 segments; 51 target decisions;
- Nanning 2x: 800 guarded rankings across 401 segments; 62 target decisions;
- map2 1x/2x stable: zero guarded rankings;
- the current P95 interpolation boundary is touched in both Nanning scales.

These counts only establish applicability. They do not predict closed-loop
latency or authorize Stage 3.

## 2. Frozen single action

Add one append-only scorer spelling:
`S4_typed_service_dominance_rule_only`. Default/off and every historical
scorer spelling remain unchanged.

After historical S4 ranking and the existing strict-potential-descent guard,
let the current first candidate be `w`. The guard acts only when all of the
following are true:

1. `w` is shield-allowed, not advertised-faulted, type 2, and is not this
   bag's goal;
2. first-edge credit is not active for this decision;
3. an already-materialized one-hop candidate `d` is shield-allowed, not
   advertised-faulted, type 4, and survived the same strict-descent guard;
4. `d.travel_time + d.static_potential` is strictly lower than the same sum
   for `w`;
5. `service_duration(d)` is strictly lower than `service_duration(w)`.

If one or more candidates qualify, move the minimum tuple
`(travel_time + static_potential, service_duration, next_node)` to the front.
Do not alter any candidate score, calendar, queue, reservation, fault policy,
or later authority. If no candidate qualifies, preserve the historical
ranking exactly.

The rule performs no global scan, future-release read, full A*, model call,
multi-hop reservation, map special case, or configurable threshold. Its work
is bounded by the already-materialized outgoing candidates.

## 3. Minimum pre-action verification

Before real-map execution, verify only the essential contracts:

- old scorer spellings retain their existing focused tests;
- one typed motif changes from a dominated non-goal type-2 winner to its
  strictly better type-4 neighbour;
- equal or slower type-4 service is an exact no-op;
- a goal type-2 winner is an exact no-op;
- a shielded/faulted alternative and active first-edge credit are no-ops;
- the action still selects at most one adjacent edge and never invokes full
  A*, a model, a global scan, or a future route.

Do not add repeated malformed-input or impossible-state tests.

## 4. Fixed real-map screen and gates

Reuse the exact V3R13 ten cases, populations, target cohorts, fault inputs,
and thresholds. Run three fixed arms per case:

- `off`: historical S4 and extension off;
- `candidate_a`: historical S4 plus Candidate A closed loop;
- `candidate_a_dominance`: Candidate A plus only the new scorer spelling.

The primary comparison is `candidate_a_dominance / off`; Candidate A remains
attribution-only. Core GO still requires every original completion, safety,
resource, Nanning target-P95, whole-system, map2, and no-wait-transfer gate.
Do not add RSS or the exact mixed-origin wait/idle integral unless this core
screen passes. A core pass is only `MEASUREMENT_REQUIRED`, never Stage-3 GO.

Any core failure is archived as
`NO_GO_V3R17_TYPED_SERVICE_DOMINANCE`; the rule is not widened, tuned, or
converted into node-specific exceptions after seeing the outcome.
