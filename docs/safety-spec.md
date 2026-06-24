# Safety Specification

The safety shield is not optional. Learning policies may rank actions, but execution must pass through deterministic hard checks.

## Hard Constraints

- Edge exists.
- Edge is not faulted.
- Edge capacity is available.
- Edge headway is respected.
- Target node or buffer capacity is available.
- Node time-window conflicts are rejected.
- Merge conflicts are rejected.
- A selected action must not make the goal unreachable.

## Promotion Gate

A planner or policy cannot be promoted into main experiments unless:

```text
post_shield_conflicts == 0
illegal_action_count == 0
headway_violation_count == 0
node_capacity_violation_count == 0
```

## Implementation Status

Phase2A has started with a C++ junction shield skeleton in `cpp/ics_core/shield/junction_shield.hpp`.

Currently covered by C++ smoke tests:

- edge existence
- faulted edge rejection
- edge capacity conflict
- edge headway conflict
- merge-group conflict
- node reservation conflict
- explicit node/buffer capacity below/full-capacity behavior
- next-hop reachability to goal

Currently covered by Python baseline tests:

- SIPP waits for safe node intervals
- SIPP waits for edge capacity/headway slots
- rolling-horizon SIPP priority and reservation reuse
- PIBT-style one-step merge conflict resolution
- PIBT-style fault-edge fallback
- PIBT-style active-bag replay with recursive handoff
- action masks respect explicit node/buffer capacity
- action masks reject configured merge-group conflicts

Currently covered by Phase8 event replay parity:

- Python and C++ event replay both carry explicit node/buffer capacities.
- Python and C++ event replay both carry configured merge groups.
- Persisted synthetic schedules include a merge/buffer case with zero post-shield conflicts.
- Real legacy `map2/inputdata` task windows match on Python/C++ event replay summaries and decision traces with zero post-shield conflicts.

Currently covered by Phase2 active-bag PIBT replay parity:

- Python and C++ active-bag PIBT replay match on summary metrics and event streams.
- Static-fault, repair-window, recursive handoff, and persisted synthetic slices stay at zero post-shield conflicts.

Currently covered by Phase9 dense active-bag PIBT stress:

- Additional fixed random dense synthetic task streams match on Python/C++ summary metrics.
- Static-fault, repair-window, repeated-repair, buffer-capacity, and merge-group stress rows stay at zero post-shield conflicts.

Still pending:

- event-simulation safety counters
- separate real heldout airport-map safety evidence
- broader randomized graph topologies and task-source distributions
