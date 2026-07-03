# G4I Full C++ Runtime Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `b3d2296`
Contains G4H: `True`
Pushed to upstream at runtime: `True`

## Scope

G4I adds a C++ no-A* batch replay entrypoint. Python serializes graph/window/task records and invokes pybind once; C++ owns the episode loop, node-window reservations, local feature computation, model scoring, risk gating, PIBT-lite fallback, and task statistics.

Training still comes from verified CIE/A* retry teacher data. Runtime full CIE/A* fallback remains disabled.

## Policy Hash

| Component | SHA256 |
| --- | --- |
| model_weights_hash | a1e685fae78ab9e5cd8e2f7b65429341719738860ae7b542dd41c9cff4ed9b04 |
| feature_schema_hash | 7965ae34e408e45b7cc5bf743d5301f441c6f7e1e89f9ee9eb59f9fe44c80d40 |
| risk_head_hash | 85c68c6e71feaaaeac266dd3b0b38462aa7258f39a066a2ec3e00bfb56b82ad7 |
| fallback_config_hash | dcc6a6aadf420f988c293f23ffa28e9310fd0a176a3217b8700cb107740a0b50 |
| combined_policy_hash | 3cfa2dfda51425c96d8442a31234bc273a06bbc5400adebfbe90feed742fe0dd |
