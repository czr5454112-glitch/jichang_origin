# Phase2A Reservation and Shield Report

Date: 2026-06-17

## Scope

Started Phase2A with a deterministic C++ junction shield skeleton:

- `cpp/ics_core/shield/junction_shield.hpp`
- expanded `cpp/tests/test_cpp_core_smoke.cpp`

## Implemented Checks

The initial shield validates a proposed edge action before execution:

- edge must exist
- edge must not be faulted
- edge capacity must have room
- edge entry headway must be respected
- configured merge group must have room
- non-goal target node must have available explicit node/buffer capacity
- taking the edge must not make the goal unreachable

The C++ smoke test covers allowed action, missing edge, faulted edge, node reservation conflict, explicit buffer capacity below/full-capacity behavior, edge capacity conflict, edge headway conflict, configured merge-group conflict, and unreachable-goal rejection.

## Validation

Target CTest result:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

Target Python pytest:

```text
42 passed
```

Target Phase3 env pytest:

```text
8 passed
```

## Limitations

This is a first shield skeleton, not the full Phase2 baseline stack. Remaining Phase2 work includes:

- full merge-group replay integration across every baseline
- full buffer-capacity replay integration across every baseline
- full active-bag PIBT/CS-PIBT-style replay integration
- full event-simulation safety counters
