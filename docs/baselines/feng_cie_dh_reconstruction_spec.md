# Feng paper-environment CIE-DH reconstruction specification

## Scientific identity and evidence layers

The historical primary reference and the executable reconstruction are two
different evidence objects:

- `FENG_PAPER_CIE_DH_HISTORICAL_MEASURED` is the original Table 5.3 workbook
  measurement. It is the primary numerical reference, but it is not an
  executable artifact in this repository.
- `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION` is an independent Java executable in
  the Feng map2 environment. Its formal level is
  `SEMANTICALLY_PARTIAL_RECONSTRUCTION`.
- `FENG_SOURCE_EXACT_CIE_DH` remains `SOURCE_NOT_RECOVERED`. Neither the Java
  executable nor its numerical agreement may be described as recovered DH
  source.

The reconstruction consumes the protected
`legacy/jichang_origin_readonly/map2.txt`, the historical demand, and the
recovered shared-D segment schedule. It does not call the C++ common executor,
G31, or any new-project calendar, merge, fault, E2, or P2 mechanism.

## What is explicit and what is reconstructed

The paper explicitly supports the common input and parameters, speed
`2.5 m/s`, a `0.2 s` update, moving and stopped physical bag states, free-flow
shortest continuation plus different moving/stopped congestion penalties,
stopped penalty greater than moving penalty, and waiting when a stopped bag
occupies the chosen outgoing entrance. The original workbook independently
recovers the Table 5.3 population, shared-D timestamps, and `sum(E-D)` timing
formula.

The unavailable DH source does **not** identify the numerical penalties,
carrier discretization, same-tick mutation order, tie-break, exact node
handoff state machine, or transfer duration. The recovered HCA source shows
that the old environment carries `Vertex.t` and node constraints, but it does
not prove that DH used HCA's closed reservation interval or the same service
server.

The executable therefore freezes the following reconstruction choices:

- movement quantum `0.5 m` per tick and a two-cell carrier footprint;
- ceiling edge discretization and ceiling release-to-tick mapping;
- snapshot/plan/conflict-resolution/simultaneous-commit updates;
- lexicographic equal-route tie-breaking and deterministic local FIFO;
- `alpha_move=0.4 s`, `beta_stop=0.8 s`, physically anchored but undisclosed
  by the paper and **not** recovered from source;
- the source and intermediate handoff semantics below.

## Frozen handoff state machine

At a source, every bag first completes a fixed `2.0 s` per-bag induction timer.
The timer is nonexclusive. On expiry, the bag competes for the real outgoing
edge entrance. The `2.0 s` value is supported only as a reconstruction
inference from the 25 historical one-bag OD lower envelopes. The archived
Demo3D `TransferDuration=2` property is not independent validation of the DH
state machine and is not used as proof.

At each non-goal intermediate map2 node:

1. The map-defined `throughTime=1.0 s` is a graph-node-local exclusive junction
   stage.
2. During that one-second stage, the bag retains its upstream edge footprint
   and is physically `STOPPED`; a competing bag records a junction-busy hold.
3. When the one-second stage completes, the bag leaves the upstream edge and
   starts a fixed `2.0 s` per-bag transfer timer. These timers overlap and add
   no independent node-wide capacity.
4. When the timer completes, the bag competes for the actual outgoing edge
   entrance using FIFO `(physical_node_arrival_tick, release_tick, task_id,
   upstream_edge_id)`. It waits if the physical entrance or FIFO arbitration
   prevents admission.

The goal has no through-time or reconstructed transfer service. Completion is
the deterministic instant at which the final-edge footprint exits into the
goal.

This is neither a fully nonexclusive node model nor a single exclusive
three-second server. Only the map one-second through stage is locally
exclusive; the following two-second timer is per bag and overlapping.

## Routing and physical update

At release and each decision vertex, each legal outgoing edge is combined with
its stable free-flow shortest continuation. The tick-start score is

```text
ETA = free_flow_seconds
    + alpha_move * moving_bags_on_continuation
    + beta_stop  * stopped_bags_on_continuation
```

The junction timer is not an additional scorer. Physical bags in the
one-second through stage retain their upstream edge footprint and are counted
as stopped there; bags in the subsequent two-second transfer timer have left
the edge and are not counted as edge occupancy. Same-tick proposals are built
from one snapshot and committed together only when final footprints remain
disjoint. A stopped predecessor never exposes its cells.

The numerical penalties remain a frozen inference. The pre-frozen envelope
is `alpha/headway in {0.5,1,2}` by `beta/alpha in {1.5,2,3}`. Results produced
under an earlier handoff state machine are stale and may not be reused as the
sensitivity result for this final semantic branch; the nine cells require a
fresh rerun before any envelope-wide claim.

## Historical workload and Table 5.3 timing

The recovered schedule contains all `43,603` segment rows for `28,506` raw
bags. Every shared D timestamp agrees across the HCA and DH workbook sheets.
An early bag may have independently released inbound and outbound legs,
matching the recovered historical construction. The Table 5.3 raw-bag value
is

```text
sum over that raw bag's segments of (segment completion E - shared schedule D)
```

Thus the planned EBS gap between two legs is excluded, while fixed source
induction and any source admission wait after D are included. First-edge
admission is a diagnostic timestamp only and is never substituted for D.

The historical measured primary reference is:

| evidence | min | mean | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|
| original workbook, seconds | 213.3 | 265.592131 | 336.9 | 384.595 | 517.2 |

## Final executable result

The accepted semantic branch completed `28,506/28,506` raw bags and
`43,603/43,603` segments:

| evidence | min | mean | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|
| partial reconstruction, seconds | 206.4 | 238.702287238 | 285.2 | 300.8 | 326.0 |

It recorded `1,872,897` stopped ticks and `2,282,929` holds, comprising
`49,194` junction-through-busy, `361,338` following-footprint, `243,122`
entry-stopped, `112,599` entry-moving, and `54,311` outgoing-entry FIFO holds.
Mean segment source wait was `2.089076440 s`; that quantity includes the fixed
two-second source timer plus occasional physical admission wait.

Relative to the historical workbook, the executable is faster by `3.235%` at
the minimum, `10.124%` at the mean, `15.346%` at P95, `21.788%` at P99, and
`36.968%` at the maximum. This is useful semantic-scale evidence, not proof
that the missing DH implementation has been recovered.

## Preregistered semantic sensitivity and rejected interpretations

These alternatives test one handoff-semantic hypothesis at a time. They are
not post-result parameter fitting:

| interpretation | population | mean / P95 / P99 / max (s) | determination |
|---|---:|---:|---|
| all intermediate timing per-bag nonexclusive | full | 232.810952 / 271.0 / 271.2 / 273.6 | rejected: removes edge-stopped propagation; only 5,296 holds |
| entire three seconds node-exclusive | full | 1057.2419 / 4363.15 / 6177.7 / 8767.2 | rejected: undocumented capacity collapse; 117,181,154 holds |
| entire boundary footprint retained | first 1,000 | 350.8922 / 551.01 / 674.458 / 742.8 | rejected after the bounded prefix; full run stopped early |
| source-minimal executable extrapolation | full | 210.104876 / 246.4 / 249.6 / 260.0 | diagnostic only; not historical measurement or final reconstruction |

The final hybrid branch is accepted as the simplest falsifiable partial
reconstruction: it preserves the old map's explicit one-second local junction
resource without converting the inferred two-second transfer duration into a
new fixed-capacity server. It must be rejected or revised if source evidence
contradicts that state machine; Table 5.3 proximity alone cannot select it.

## Reporting and completion gates

Formal min/mean/P95/P99/max are written only for the complete fixed raw-bag
population and the scheduled-D observation contract. In incomplete or
fixed-horizon-ineligible runs, survivor timing is `N/A`; completion and backlog
retain the full denominator. Historical measured rows and executable
extrapolations must remain separately named in every table and narrative.
