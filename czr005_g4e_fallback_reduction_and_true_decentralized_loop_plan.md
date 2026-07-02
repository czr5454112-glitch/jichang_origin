# czr005 G4E Fallback Reduction and True Decentralized Loop Plan

## Objective

Reduce verified CIE/A* fallback calls after G4D and test a true learner-visited decentralized loop where the policy may deviate from the CIE path as long as it reaches the goal safely.

This stage remains constrained:

- No PPO, MAPPO, RL, GNN, Transformer, or broad paper-grade success claim.
- No legacy Java changes.
- `edge_capacity=1` and edge overlap remain diagnostic only.
- The G4D small MLP remains the base scorer; G4E calibrates the risk head and does not downgrade to a simpler lookup model.
- `scenario`, `window_name`, teacher next-hop, full route suffix, future schedule, label source, and post-hoc success remain forbidden model inputs.

## Implemented Work

G4E adds:

- `scripts/eval/run_g4e_fallback_reduction_audit.py`
- `scripts/train/train_g4e_risk_calibrated_policy.py`
- `scripts/eval/run_g4e_true_decentralized_closed_loop.py`
- `scripts/eval/run_g4e_runtime_call_accounting.py`

## Results

Fallback audit:

- G4D fallback calls ledgered: `6786`
- Fallback calls that would have prevented wrong model actions: `1771`
- G4D zero-fallback teacher-planned tasks: `0/4449`

Risk calibration:

- Base scorer: G4D small MLP
- Added risk rules: `16`
- G4E route-exact fallback calls: `6395`
- G4E route-exact planned scope: `4449/4449`
- Node-window conflicts: `0`
- Wrong high-confidence actions: `0`
- Zero-fallback tasks: `76/4449`

True decentralized loop:

- Route-exact with G4E fallback: `4449/4449`
- Goal-reaching model-only diagnostic: `4449/4449`
- Model-only route-exact tasks: `2850`
- Model-only safe deviations from CIE path: `1599`
- Goal-reaching with G4E fallback: `4449/4449`
- Fallback-assisted safe deviations from CIE path: `1372`
- Teacher no-path boundary rows preserved: `47`

Runtime call accounting:

- Original CIE retry A* attempts: `15852`
- G4D fallback A* calls: `6786`
- G4E route-exact fallback A* calls: `6395`
- G4E route-exact A* reduction: `0.59658087`
- G4E route-exact fallback rate: `0.16266884`

## Decision

G4E is a development pass, not a G4F promotion candidate.

It satisfies the development gate:

- Planned count is not below G4D.
- Node-window conflicts remain `0`.
- Fallback calls are lower than G4D.
- Zero-fallback tasks are now nonzero.
- True goal-reaching model-only diagnostics are recorded.

It does not satisfy the promotion gate:

- A* reduction is below `70%`.
- Fallback rate is above `12%`.

The next work should continue fallback reduction and validate the diagnostic model-only local-wait loop in the runtime/export path before C++ promotion.
