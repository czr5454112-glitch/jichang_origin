# C++ Core

This directory contains the C++ core for graph loading, task streams, routing, reservation, metrics, shield checks, and pybind smoke bindings.

Implemented so far:

- legacy map/task readers
- A* planner and route smoke parity
- node and edge reservation primitives
- initial junction shield checks
- header-only MLP edge-score inference and text runtime loader
- compact native C++ EdgeScore replay smoke
- model-unavailable shortest-safe fallback for compact native replay
- first native C++ event-queue replay and trace audit over persisted synthetic schedules
- pybind smoke boundary

Paper-grade high-throughput scheduler validation, event-level Python parity, C++ SIPP baseline, C++ rolling-horizon baseline, recursive PIBT-style resolver, and broad runtime replay validation are still pending.
