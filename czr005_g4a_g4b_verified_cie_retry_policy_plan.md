# czr005 G4A/G4B Verified CIE Retry Policy Pilot Plan

## Objective

Convert the verified G3k CIE/Java retry teacher into per-interface decision data, then train and evaluate a minimal decentralized junction-policy pilot.

This stage is intentionally small and gated:

- G4A builds data only.
- G4B trains only if all G4A dataset gates pass.
- No PPO, MAPPO, RL, GNN, Transformer, or broad learning claim is allowed.
- `edge_capacity=1` and edge overlap remain diagnostic only.
- Legacy Java remains read-only.

## G4A Result

G4A uses `java_retry_tick_1s_max_delay_60s` from G3k and emits:

- `1186` per-interface `MOVE_TO_NEXT_CIE` slices.
- `17` source-admission `WAIT_AT_SOURCE_RETRY` slices.
- Branch-node coverage: `533` slices.
- Train/val/test split.
- Forbidden-feature audit: pass.
- Teacher replay parity: `144/144`, `0` node-window conflicts, no primary edge capacity.

## G4B Result

G4B trains a minimal pure-Python MLP candidate scorer using only allowed runtime features.

Key pilot metrics:

- Offline all-split top-1: `0.98819562`.
- Shortest-time heuristic top-1: `0.85581788`.
- Shadow disagreements: `14/1186`.
- Unsafe fault-edge predictions: `0`.
- Conservative route-exact replay: `132/144`.
- Node-window conflicts: `0`.
- Old EdgeScore comparison: `132/144` vs `97/144`.
- Fallback comparison: `132/144` vs `93/144`.

## Decision

The pilot is a G4C data-aggregation candidate. It is not a paper-grade learned-policy success and not a final replacement for CIE/A*.

The next step should collect learner-visited states from the `14` logged disagreements, relabel with verified CIE/A* where possible, and retrain before considering larger models or RL.
