# Phase1B Python Reference Simulator Report

Date: 2026-06-16

## Scope

Implemented the first headless Python reference simulator layer:

- `src/czr005/sim_py/graph.py`
- `src/czr005/sim_py/task_stream.py`
- `src/czr005/sim_py/event_sim.py`
- `src/czr005/sim_py/astar.py`
- `src/czr005/sim_py/reservation.py`
- `src/czr005/sim_py/metrics.py`

This round still avoids reinforcement learning, GUI dependencies, and hidden file writes.

## Legacy Semantics Captured

- Directed graph and service times come from `map2.txt`.
- A* uses node arrival/departure times:
  - `t1 = previous.t2 + edge.length / edge.speed`
  - `t2 = t1 + node.service_time`
- Non-goal nodes are rejected when their `[t1, t2]` interval overlaps an existing node reservation.
- Fault edges can be passed as a set and are skipped by A*.
- Task stream uses the Phase1A expanded JSONL output and Java-equivalent early-bag split rule.

## Smoke Parity

Python A* is checked against legacy path output for selected map2 routes:

| Route | Expected legacy path |
|---|---|
| `0 -> 47` | `0 6 12 13 23 24 27 28 47` |
| `52 -> 49` | `52 29 30 31 32 37 49` |
| `53 -> 50` | `53 20 10 15 14 46 36 44 50` |

`3 -> 49` is kept as a structural smoke case rather than a hard path oracle because the legacy output file disagrees with the current Java A* semantics implied by `Astar.java` and `map2.txt` tie-breaking/heuristic behavior.

## Known Limits

This is a Phase1B reference layer, not yet a full reproduction of `ICS_PathFinding` fault repair and route-update behavior. Current replay plans task legs sequentially with reservations and returns structured logs. Full Java/Python/C++ route-update parity remains part of Phase1E.

## Gate Status

- Headless: yes.
- Deterministic: yes.
- No GUI dependency: yes.
- No hidden file writes during `run_episode()`: yes.
- Structured logs: yes, via `EpisodeResult.to_log()`.
- Tests: `C:\Users\38908\.conda\envs\czr005\python.exe -m pytest` in the target repo passed `6 passed`.
