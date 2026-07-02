# G4D Policy Training Report

Date: 2026-07-02

## Scope

This trains a small G4D MLP candidate scorer plus a calibrated risk head. It is not RL, PPO/MAPPO, GNN, Transformer, or a paper-grade replacement claim.

## Training Result

- Final training loss: `0.170904`
- Final training top1: `0.934949`
- All-split top1: `0.954951`
- Shortest-time heuristic top1: `0.861496`

## Selected Risk Head

- Margin threshold: `5.0`
- Historical-risk threshold: `0.95`
- Bottleneck threshold: `99.0`
- All fallback rate: `0.172615`
- All wrong high-confidence actions: `0`

## Decision

The trained artifact is eligible for G4D closed-loop cost accounting. Promotion depends on the true closed-loop and A* call report, not this offline result alone.

## Artifacts

- Model: `artifacts/models/g4d_cie_retry_policy.json`
- Offline accuracy: `outputs/tables/g4d_offline_accuracy.csv`
- Risk calibration: `outputs/tables/g4d_risk_head_calibration.csv`
- Abstain sweep: `outputs/tables/g4d_abstain_policy_sweep.csv`
