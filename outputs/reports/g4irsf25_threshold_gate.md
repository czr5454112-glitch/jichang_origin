# G4IRSF25 T0 threshold gate

Status: TRAINED_FROM_PAIRED_EVIDENCE

## Evidence inputs

- Paired dataset: `artifacts/datasets/g4irsf25_short_horizon_pairs_compact.jsonl`
- G24 corridor source: `outputs/tables/g4irsf24_decision_summary.json#reconvergent_corridor.corridors`

## Frozen G24 residual

- Contract: `FROZEN_G24_NO_PAIRED_REFIT`
- Source: `outputs/tables/g4irsf24_decision_summary.json#reconvergent_corridor.corridors`
- G25 paired labels select only the gate and fairness cap; they do not refit the eight G24 arm residuals.
- Per-arm private estimates remain the frozen G24 `dynamic_duration_seconds` values.

## Selected bounded gate

- Metric: `target_queue_plus_incoming`
- Single threshold: `20.350000`
- Exit threshold: `20.350000` (equal to entry; no sparse-offline hysteresis reconstruction)
- Registered fairness-cap search: `30.000000, 60.000000` seconds
- Selected private cap: `30.000000` seconds
- Threshold candidates: `4`

## Held-out protocol

- Selection folds: `train, validation`
- Held-out test used for selection: `false`
- The chronological test tail is evaluated once after threshold/cap selection.

| split | system MAE (s) | ranking | beneficial precision | harmful mutation rate | regret (s) | mutations | safety failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| validation | 1423.564349 | 0.404878 | 0.000000 | 0.000000 | 2198.643365 | 0 | 0 |
| test | 1046.833472 | 0.429268 | 0.000000 | 0.000000 | 1528.140888 | 0 | 0 |
