# Phase8 EdgeScore C++ Runtime Parity Report

Date: 2026-06-24

## Scope

This smoke verifies that the new C++ MLP-EdgeScore inference kernel and pybind wrapper match the Python scorer on real teacher-slice feature rows. It uses deterministic synthetic weights to isolate runtime parity from training quality.

## Metrics

- Compared slices: `32`
- Max absolute score difference: `0.000000000000`
- Masked prediction parity: `PASS`
- CSV: `outputs/tables/phase8_edge_score_cpp_parity.csv`

## Gate Status

- C++ scorer callable from pybind: PASS
- score parity tolerance 1e-12: PASS
- masked argmax parity: PASS
- production text model loader: covered by `outputs/reports/phase8_edge_score_runtime_loader_report.md`
- latency and closed-loop runtime smoke: covered by `outputs/reports/phase8_cpp_runtime_report.md`

## Remaining Work

- keep runtime parity covered when replacing the text MLP artifact with ONNX/LibTorch/GNN runtime formats
