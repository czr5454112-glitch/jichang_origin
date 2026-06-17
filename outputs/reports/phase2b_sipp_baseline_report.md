# Phase2B SIPP Baseline Report

Date: 2026-06-16

## Scope

Added a first Python safe-interval path planning baseline:

- `src/czr005/baselines/sipp.py`
- `src/czr005/baselines/__init__.py`
- `tests/test_phase2_baselines.py`

## Behavior

The baseline keeps the Phase1 Python graph semantics but allows waiting before edge traversal so that arrival at the target node lands in the next safe reservation-free interval.

The current implementation covers:

- directed graph routing
- node service time
- target-node reservation intervals
- fault-edge rejection
- route reconstruction with timed nodes

## Validation

Scaffold pytest:

```text
8 passed
```

Target pytest under `C:\PROGRAMING\czr005`:

```text
8 passed
```

Target CTest:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

The main SIPP test reserves node `1` at `[2.0, 3.0]` on a three-node line graph. The legacy-compatible A* returns no route, while SIPP waits past the reserved interval and reaches the goal.

## Limitations

This is a minimal Phase2B baseline, not the final simulator baseline stack. Remaining work:

- C++ SIPP parity or binding
- edge reservation/capacity-aware SIPP
- buffer and merge constraints
- rolling-horizon baseline
- PIBT/CS-PIBT-style one-step resolver
- full task-stream event replay
