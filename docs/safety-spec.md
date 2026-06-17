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
- node reservation conflict
- next-hop reachability to goal

Currently covered by Python baseline tests:

- SIPP waits for safe node intervals
- SIPP waits for edge capacity/headway slots
- rolling-horizon SIPP priority and reservation reuse
- PIBT-style one-step merge conflict resolution
- PIBT-style fault-edge fallback

Still pending:

- explicit buffer capacity
- merge conflict groups
- event-simulation safety counters
- C++ SIPP integration
- full recursive PIBT-style baseline integration
