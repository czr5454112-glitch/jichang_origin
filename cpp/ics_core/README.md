# C++ Core

This directory contains the C++ core for graph loading, task streams, routing, reservation, metrics, shield checks, and pybind smoke bindings.

Implemented so far:

- legacy map/task readers
- A* planner and route smoke parity
- node and edge reservation primitives
- initial junction shield checks, including explicit node/buffer capacity and merge groups
- C++ SIPP planner parity over node/edge reservations and synthetic routes
- C++ rolling-horizon SIPP parity over priority, fault, capacity, headway, and synthetic schedules
- C++ route-discarding periodic SIPP replanning parity over active-bag, capacity, static-fault, repair-window, and synthetic slices
- C++ PIBT-style resolver parity over priority, merge, fault, reservation, hold-duration, bounded recursive handoff, and synthetic slices
- active-bag/replan-cost audit over Python/C++ event traces on persisted synthetic schedules
- header-only MLP edge-score inference and text runtime loader
- compact native C++ EdgeScore replay smoke
- model-unavailable shortest-safe fallback for compact native replay
- first native C++ event-queue replay, trace audit, and Python/C++ parity over persisted synthetic schedules
- Phase8 event replay carries repair windows plus explicit node/buffer capacity and merge-group configuration through Python/C++ parity
- pybind smoke boundary

Paper-grade high-throughput scheduler validation, real heldout-map event parity, full active-bag PIBT-style replay integration, merge-group/buffer-capacity parity across every baseline family, and broad runtime replay validation are still pending.
