# G4B CIE Retry Training Notes

Date: 2026-07-02

## Scope

This trains a minimal pure-Python MLP candidate scorer on the G4A verified CIE retry interface slices. It is a pilot model, not a paper-grade learning result. No GNN, Transformer, PPO, MAPPO, or RL is used.

## Training Result

- Final training loss: `0.044844`
- Final training top1: `0.989038`
- All-split model top1: `0.988196`
- All-split shortest-time heuristic top1: `0.855818`

## Feature Ablation

| Ablation | All top1 |
| --- | --- |
| none | 0.988196 |
| no_slack | 0.962057 |
| no_node_pressure | 0.979764 |
| no_fault_flag | 0.985666 |
| no_branch_flag | 0.988196 |
| no_candidate_distance | 0.978078 |

## Artifacts

- Model: `artifacts/models/g4b_cie_retry_edge_ranker_smoke.json`
- Training history: `outputs/tables/g4b_training_history.csv`
- Offline accuracy: `outputs/tables/g4b_offline_accuracy.csv`
- Feature ablation: `outputs/tables/g4b_feature_ablation.csv`
