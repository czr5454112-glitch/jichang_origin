# G4E Risk-Calibrated Policy Report

Date: 2026-07-02

## Scope

G4E keeps the G4D small MLP candidate scorer and recalibrates only the risk head. It does not replace the model with a simpler lookup, does not use RL/GNN/Transformer, and does not add forbidden inputs.

## Selected Policy

- Candidate type: `hardcase_rules`
- Margin threshold: `1.0`
- Historical-risk threshold: `0.5`
- Bottleneck threshold: `5.0`
- Learned runtime risk rules: `16`
- Planned count: `4449/4449`
- Wrong high-confidence actions: `0`
- Fallback calls: `6395`
- A* call reduction: `0.596581`
- Zero-fallback task share: `0.017082`

## Decision

The selected G4E risk head reduces fallback calls relative to G4D while preserving the verified teacher planned scope and zero wrong high-confidence actions. Promotion still depends on the true decentralized closed-loop and runtime accounting scripts.

## Artifacts

- Sweep: `outputs/tables/g4e_risk_threshold_sweep.csv`
- Model: `artifacts/models/g4e_risk_calibrated_policy.json`
