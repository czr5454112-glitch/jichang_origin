# C++ Core

This directory contains the C++ core for graph loading, task streams, routing, reservation, metrics, shield checks, and pybind smoke bindings.

Implemented so far:

- legacy map/task readers
- A* planner and route smoke parity
- node and edge reservation primitives
- initial junction shield checks
- C++ SIPP planner parity over node/edge reservations and synthetic routes
- C++ rolling-horizon SIPP parity over priority, fault, capacity, headway, and synthetic schedules
- C++ PIBT-style one-step resolver parity over priority, merge, fault, reservation, hold-duration, and synthetic slices
- header-only MLP edge-score inference and text runtime loader
- compact native C++ EdgeScore replay smoke
- model-unavailable shortest-safe fallback for compact native replay
- first native C++ event-queue replay, trace audit, and Python/C++ parity over persisted synthetic schedules
- pybind smoke boundary

Paper-grade high-throughput scheduler validation, real heldout-map event parity, active-bag rolling replanning, recursive PIBT-style priority inheritance/backtracking, and broad runtime replay validation are still pending.
