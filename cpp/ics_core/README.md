# C++ Core

This directory contains the C++ core for graph loading, task streams, routing, reservation, metrics, shield checks, and pybind smoke bindings.

Implemented so far:

- legacy map/task readers
- A* planner and route smoke parity
- node and edge reservation primitives
- initial junction shield checks
- C++ SIPP planner parity over node/edge reservations and synthetic routes
- header-only MLP edge-score inference and text runtime loader
- compact native C++ EdgeScore replay smoke
- model-unavailable shortest-safe fallback for compact native replay
- first native C++ event-queue replay, trace audit, and Python/C++ parity over persisted synthetic schedules
- pybind smoke boundary

Paper-grade high-throughput scheduler validation, real heldout-map event parity, C++ rolling-horizon baseline, recursive PIBT-style resolver, and broad runtime replay validation are still pending.
