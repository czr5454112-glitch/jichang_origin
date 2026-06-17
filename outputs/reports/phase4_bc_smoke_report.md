# Phase4 Behavior Cloning Smoke Report

Date: 2026-06-17

## Scope

This smoke trains the first minimal MLP-EdgeScore behavior-cloning baseline on the Phase4 teacher junction-slice manifest. It is a pure-Python training check, not a final policy result.

## Inputs And Outputs

- Teacher manifest: `artifacts/teacher/junction_slices_manifest.jsonl`
- Model artifact: `artifacts/models/phase4_mlp_edge_score_smoke.json`
- Training history: `outputs/tables/phase4_bc_smoke_history.csv`
- Slices: `78`

## Metrics

- Final training loss: `0.081198`
- Final training top1: `0.974359`
- Safe masked eval top1: `0.974359`

## Gate Status

- teacher manifest consumed: PASS
- model artifact written: PASS
- safe masked top1 smoke threshold: PASS
- closed-loop policy replay: not started

## Remaining Work

- split train/validation teacher data
- add larger and harder teacher manifests
- run shadow replay against baseline actions
- compare BC+shield with SIPP/rolling-horizon/PIBT baselines
