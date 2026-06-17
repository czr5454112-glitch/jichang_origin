# Phase2C Rolling-Horizon Baseline Report

Date: 2026-06-17

## Scope

Added a first Python rolling-horizon prioritized baseline:

- `src/czr005/baselines/rolling_horizon.py`
- updated `src/czr005/baselines/__init__.py`
- expanded `tests/test_phase2_baselines.py`

## Behavior

The baseline batches task legs by a fixed pass-time horizon, sorts each batch by deadline slack, and plans each task with SIPP against a shared reservation table.

Current behavior covered by tests:

- tighter deadline slack receives higher priority inside one horizon
- later same-route task waits for the earlier task's node reservation
- shared reservation table remains conflict-free in the smoke case
- faulted downstream edge produces an unplanned event
- output uses the existing `EpisodeResult` and metrics structure

## Validation

Scaffold pytest:

```text
10 passed
```

Target pytest under `C:\PROGRAMING\czr005`:

```text
10 passed
```

Target CTest:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

## Limitations

This is a first rolling-horizon skeleton. Remaining work includes:

- true active-bag replanning
- C++ parity/runtime version
- edge capacity/headway and merge-aware priority
- larger task-stream replay sweeps
- comparison against SIPP-only and A* reference baselines
