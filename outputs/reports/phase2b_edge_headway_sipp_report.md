# Phase2B Edge/Headway-Aware SIPP Extension Report

Date: 2026-06-17

## Scope

Extended the Python SIPP baseline with edge reservation constraints:

- `EdgeReservation` and `EdgeReservationTable` in `src/czr005/sim_py/reservation.py`
- exported edge reservations from `czr005.sim_py`
- SIPP optional parameters for edge reservations, edge capacity, and edge headway
- tests for edge-capacity waiting and edge-headway waiting

## Behavior

SIPP now searches for a transition time that satisfies both:

- edge interval capacity/headway constraints
- target node safe interval constraints

If the target node is reserved, SIPP waits before entering the edge so that arrival lands in the next safe node interval. If the edge is occupied or headway is too small, SIPP waits before entering the edge.

## Validation

Target pytest:

```text
14 passed
```

Target CTest:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

## Limitations

- Edge reservations are available to SIPP but are not yet emitted by the rolling-horizon replay.
- Merge groups and full buffer-capacity replay integration are still pending.
- C++ SIPP parity is still pending.
