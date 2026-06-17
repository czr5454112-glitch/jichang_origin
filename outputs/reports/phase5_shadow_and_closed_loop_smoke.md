# Phase5 Shadow And Closed-Loop Smoke Report

Date: 2026-06-17

## Scope

This smoke evaluates the Phase4 MLP-EdgeScore model in shadow mode against the A*-guided safe baseline, then runs a small BC+shield closed-loop replay. The model is trained in-memory from the Phase4 teacher manifest for reproducibility.

## Metrics

| Decisions | Disagreements | Disagreement rate | Unsafe proposals | Unsafe rate | Improvement opportunities | Baseline planned | Closed-loop planned | Closed-loop conflicts |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 78 | 2 | 0.025641 | 0 | 0.000000 | 0 | 8 | 6 | 0 |

CSV: `outputs/tables/phase5_shadow_smoke_metrics.csv`

## Gate Status

- shadow replay completed: PASS
- closed-loop BC+shield replay completed: PASS
- shadow post-shield conflicts: PASS
- closed-loop post-shield conflicts: PASS
- unsafe proposal rate acceptable for smoke: PASS

## Remaining Work

- train/evaluate on larger heldout teacher splits
- add deadline-critical mistake analysis
- compare closed-loop BC+shield against Phase2 baselines on larger task sets
- add fault and density shadow sweeps
