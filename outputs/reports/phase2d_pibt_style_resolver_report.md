# Phase2D PIBT-Style One-Step Resolver Report

Date: 2026-06-17

## Scope

Added a deterministic one-step conflict resolver inspired by PIBT / CS-PIBT:

- `src/czr005/baselines/pibt.py`
- updated `src/czr005/baselines/__init__.py`
- expanded `tests/test_phase2_baselines.py`

## Behavior

The resolver handles one simultaneous junction-decision slice:

- ranks agents by deadline slack, waiting time, ready time, and task id
- tries outgoing edges by shortest heuristic-to-goal
- rejects faulted edges
- rejects same-slice target-node conflicts
- rejects same-slice same-edge conflicts
- rejects existing node reservation conflicts
- rejects next-hop choices that make the goal unreachable
- falls back to `hold` when no safe edge is available

## Validation

Target pytest:

```text
12 passed
```

Target CTest:

```text
1/2 Test #1: cpp_core_smoke ... Passed
2/2 Test #2: pybind_smoke ... Passed
100% tests passed
```

## Limitations

This is a compact one-step resolver, not a full recursive PIBT implementation. Remaining work:

- recursive priority inheritance/backtracking
- edge capacity/headway inside Python resolver
- merge-group semantics beyond shared target nodes
- integration into full rolling-horizon replay
- C++ parity/runtime implementation
