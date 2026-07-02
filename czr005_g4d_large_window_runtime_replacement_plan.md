# czr005 G4D Large-Window Runtime Replacement Plan

## Objective

Expand the verified CIE/Java retry teacher beyond the 144-task pilot, train an enhanced small per-interface policy, and measure true A* call reduction against the original CIE retry baseline.

This stage remains constrained:

- No PPO, MAPPO, RL, GNN, Transformer, or broad paper-grade replacement claim.
- No legacy Java changes.
- `edge_capacity=1` and edge overlap are diagnostic only.
- `scenario` and `window_name` are metadata only, not model inputs.
- Teacher next-hop, full CIE route suffix, future schedule, label source, and post-hoc success are forbidden model inputs.

## Implemented Work

G4D adds:

- `scripts/data/build_g4d_cie_retry_large_window_dataset.py`
- `scripts/eval/run_g4d_risky_branch_audit.py`
- `src/czr005/models/g4d_cie_retry.py`
- `scripts/train/train_g4d_cie_retry_policy.py`
- `scripts/eval/run_g4d_true_closed_loop_and_astar_cost.py`

## Results

Teacher expansion:

- Windows: `8`
- Window sizes: `144`, `256`, `512`, `1024`
- Total window tasks: `4496`
- Verified CIE retry planned: `4449/4496`
- Node-window conflicts: `0`
- MOVE interface slices: `39313`
- Source retry slices: `962`
- Negative teacher rows: `47`, all preserved in the high-density `g4d_offset2048_1024_high_density` window.

Risky branch audit:

- Risky branch cases: `2981`
- Target branch families: `6->{8,12}`, `11->{13,14}`, `16->{17,21}`, `19->{18,25}`
- Diagnosis: no longer sample-starved, but still mixed-context and tie-sensitive enough to require a calibrated risk head.

Small model:

- Model type: small enhanced MLP candidate scorer plus calibrated risk head.
- All-split top1: `0.954951`
- Shortest-time heuristic top1: `0.861496`
- Selected risk margin: `5.0`
- Wrong high-confidence actions after risk head: `0`

Runtime cost:

- CIE retry baseline A* attempts: `15852`
- G4D verified fallback A* calls: `6786`
- Aggregate A* call reduction: `0.57191522`
- G4D planned: `4449/4496`
- Node-window conflicts: `0`

## Negative Results

G4D is not a final replacement claim.

- One high-density 1024-task window preserves `47` CIE retry teacher no-path rows under the current `60s` retry horizon.
- Several small no-fault windows have per-window A* call regressions because conservative interface fallback can exceed the original task-level CIE retry call count.
- G4D therefore passes the safety and aggregate-cost gate for G4E/C++ runtime evaluation, but it does not prove final paper-grade replacement.

## Decision

Proceed to G4E C++ runtime / latency evaluation and fallback-reduction audit. Do not start RL yet.
