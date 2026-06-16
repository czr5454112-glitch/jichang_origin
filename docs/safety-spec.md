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

Phase1A only defines parsed input data. Runtime shield enforcement begins in Phase2.

