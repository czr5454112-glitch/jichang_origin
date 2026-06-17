# Phase8 EdgeScore Runtime Loader Parity Report

Date: 2026-06-17

## Scope

This smoke trains the fault-curriculum MLP-EdgeScore model in Python, exports it to the text runtime artifact format, loads that artifact through the C++ pybind runtime model, and compares scores plus safe-masked predictions on real teacher slices.

## Artifact

- Model text artifact: `artifacts/runtime/phase8_edge_score_runtime_model.txt`
- Feature dimension: `13`
- Hidden dimension: `16`
- Training final loss: `0.291565`
- Compare-slice Python top1: `1.000000`

## Metrics

- Compared slices: `64`
- Max absolute score difference: `0.000000000000`
- Prediction mismatches: `0`
- CSV: `outputs/tables/phase8_edge_score_runtime_loader_parity.csv`

## Gate Status

- Python text export: PASS
- C++ text artifact load: PASS
- score parity tolerance 1e-10: PASS
- masked argmax parity: PASS
- C++ closed-loop replay: not covered

## Remaining Work

- bind the runtime scorer into a C++ shielded replay loop
- measure C++ policy inference latency on larger replay batches
- validate exported checkpoints across heldout maps and fault schedules
