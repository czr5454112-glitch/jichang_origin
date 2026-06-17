# Phase2C Edge Reservation Replay Integration

Date: 2026-06-17

## Scope

This update wires the Phase2 edge reservation table into the rolling-horizon SIPP replay baseline. Planned routes now reserve traversed directed edges after node reservations are accepted, and later task legs plan against both shared node reservations and shared edge capacity/headway constraints.

## Checks

- Python test suite: `16 passed`
- C++ CTest suite: `2/2 passed`
- Phase2 baseline smoke: PASS

## Smoke Replay Result

On the first `128` expanded task legs from `inputdata.jsonl`, the replay smoke planned all `128` rolling-horizon SIPP task legs with zero reservation conflicts.

CSV: `outputs/tables/phase2_baseline_smoke_metrics.csv`

## Notes

The edge reservation search remains a deterministic baseline implementation. It is sufficient for the current capacity/headway regression tests and smoke replay, but it is not yet a full interval-capacity optimizer. Merge groups, full buffer-capacity replay integration, full active-bag replanning, recursive PIBT replay integration, C++ SIPP parity, and multi-seed density/fault sweeps remain open.
