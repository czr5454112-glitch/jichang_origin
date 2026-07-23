# G4IRSF12-I v3 Training Report

Status: `BLOCKED_NOT_RUN`.

No model is considered a runtime result in this report. Training is allowed only after every hash-bound Phase-I prerequisite passes.

## Current blockers

- G4IRSF12 v3 source manifest is missing: artifacts/datasets/g4irsf12_v3_source_manifest.json
- pre-training gate manifest is missing: artifacts/gates/g4irsf12_v3_pretraining_gate_manifest.json

## Data preparation audit

- Decision rows: `0`
- Outcome rows: `0`
- Rank-eligible rows: `0`
- Hard rows: `0`
- Easy rows: `0`

Failure, loop, and dead-end actions remain risk evidence. They are never inverted into an unobserved correct next edge. Teacher suffixes, future schedules, post-hoc success, and absolute node IDs are not legal model inputs.

A future offline candidate must pass every seed and held-out split. Even then it remains `CLOSED_LOOP_REQUIRED` and cannot be activated by this tool.
