# CZR005 No-A* Runtime API

## Entry Point

`czr005.cpp_backend.g4i_no_astar_batch_replay(...)` calls the C++ pybind runtime loop.

## Required Runtime Inputs

- Graph nodes and directed edges from the verified map.
- A static heuristic-time matrix from the map.
- Window records with optional verified-style fault edges/windows.
- Task records containing start, goal, entry/attempt time, and std time.
- Frozen MLP weights, risk thresholds, historical risk rules, and local fallback rules.

## Runtime Outputs

- `summary`: planned count, conflicts, model/rule calls, full A* calls, diagnostic edge overlap, elapsed time.
- `per_window`: per-window quality and safety statistics.
- `tasks`: optional task-level rows; omitted when `summary_only=True`.
- `trace`: optional decision trace controlled by `trace_limit`.
- `profile`: optional C++ stage timings controlled by `profile_enabled=True`.

## Safety Boundary

The runtime does not call full CIE/A* fallback. Node windows are the primary safety constraint. Edge overlap is diagnostic only.
