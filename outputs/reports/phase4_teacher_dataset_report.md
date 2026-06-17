# Phase4 Teacher Dataset Smoke Report

Date: 2026-06-17

## Scope

This smoke exports the first shielded teacher junction-slice manifest from the Phase3 environment. The expert source is an A*-guided safe scripted policy executed through the same action mask and hard shield used by the environment.

## Dataset

- Manifest: `artifacts/teacher/junction_slices_manifest.jsonl`
- Summary CSV: `outputs/tables/phase4_teacher_dataset_summary.csv`
- Expert source: `astar_guided_safe`
- Task legs: `8`
- Slices: `78`
- Planned task legs: `8`
- Unplanned task legs: `0`
- Reservation conflicts: `0`
- Fallback actions: `0`
- Unsafe proposals: `0`

## Slice Fields

`obs`, `candidate_edges`, `action_mask`, `proposed_action`, `expert_action`, `expert_rank`, `expert_cost_to_goal`, `future_delay`, `shield_result`, `unsafe_proposal`, `reward`, and `reached_goal`.

## Gate Status

- teacher manifest written: PASS
- action masks included: PASS
- expert actions included: PASS
- post-shield conflicts: PASS
- BC training: not started

## Remaining Work

- collect larger multi-density teacher datasets
- add rolling-horizon/SIPP and PIBT-style teacher sources
- add train/validation split metadata
- train the first MLP-EdgeScore behavior cloning baseline
