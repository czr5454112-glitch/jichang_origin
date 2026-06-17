# Phase5 Shadow And Closed-Loop Smoke Report

Date: 2026-06-17

## Scope

This smoke evaluates the Phase4 MLP-EdgeScore model in shadow mode against the A*-guided safe baseline, then runs a small BC+shield closed-loop replay. The model is trained in-memory from the Phase4 teacher manifest for reproducibility.

## Metrics

| Decisions | Disagreement rate | Unsafe rate | Baseline planned | Base BC closed-loop | DAgger BC closed-loop | DAgger conflicts | DAgger slices |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 78 | 0.025641 | 0.000000 | 8 | 6 | 8 | 0 | 461 |

CSV: `outputs/tables/phase5_shadow_smoke_metrics.csv`
DAgger manifest: `artifacts/teacher/junction_slices_dagger_smoke.jsonl`

## Gate Status

- shadow replay completed: PASS
- closed-loop BC+shield replay completed: PASS
- shadow post-shield conflicts: PASS
- base closed-loop post-shield conflicts: PASS
- DAgger closed-loop post-shield conflicts: PASS
- DAgger closed-loop matches baseline smoke planned count: PASS
- unsafe proposal rate acceptable for smoke: PASS

## Remaining Work

- train/evaluate on larger heldout teacher splits
- add deadline-critical mistake analysis
- compare DAgger BC+shield against Phase2 baselines on larger task sets
- add fault and density shadow sweeps
