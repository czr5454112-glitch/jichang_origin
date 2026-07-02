# czr005 G4C Failure-Driven Decentralized Policy Plan

## Objective

Use the G4B failure inventory to build a small failure-driven data aggregation pass for the verified CIE retry teacher.

This stage is deliberately constrained:

- No PPO, MAPPO, RL, GNN, Transformer, or broad architecture work.
- No legacy Java changes.
- `edge_capacity=1` and edge overlap remain diagnostic only.
- `scenario` is metadata only and must not be used as a model input.
- Verified CIE/A* retry remains the fallback and relabeling source.

## Implemented Scope

G4C adds two scripts:

- `scripts/eval/run_g4c_failure_driven_data_aggregation.py`
- `scripts/eval/run_g4c_learner_visited_closed_loop.py`

The data aggregation pass:

- Re-audits G4A/G4B feature hygiene and keeps `scenario` out of model inputs.
- Clusters the `14` G4B wrong high-confidence interface decisions.
- Records learner-visited states after each wrong move.
- Relabels both original failure slices and learner-visited off-route states with verified CIE/A* retry.
- Trains a minimal round1 scorer and writes a calibrated abstain configuration.

The closed-loop pass:

- Compares G4B, G4C without calibration, G4C with failure-cluster abstain, old EdgeScore, fallback-event, and the CIE retry teacher upper bound.
- Reports planned count, node-window conflicts, wrong high-confidence actions, fallback usage, learner-visited state count, and runtime cost.

## Result

Key metrics:

- G4B wrong high-confidence interface decisions: `14`.
- Failure clusters: `4`.
- Relabel rows: `28`.
- Round1 without calibration: `132/144` planned, `14` wrong high-confidence actions.
- Round1 with cluster abstain: `144/144` planned, `0` node-window conflicts, `0` wrong high-confidence actions.
- Fallback calls: `114/1186` interface decisions.
- Fallback rate: `0.09612142`.
- Per-interface A* fallback calls saved: `0.90387858`.

## Decision

G4C passes the gate for G4D large-window teacher expansion. It is not a final paper-grade learned-policy result and not a reason to start RL yet.

The next step should expand the verified CIE retry teacher and repeat the failure-driven audit on larger windows before considering RL or larger model families.
