# czr005 G3i CIE/A* Path-Constrained SIPP Integration Plan

Date: 2026-07-02
Branch: `codex/czr005-rewrite`

## Scope

G3i integrates SIPP into the airport ICS simulation stack without replacing the original CIE/Legacy A* route teacher.

The required behavior is:

```text
CIE / Legacy A* decides where to go.
SIPP-style timing decides when the fixed A* route can safely pass each node/edge.
```

This is not a free-route SIPP teacher and not a training run.

## Implementation Rule

- Preserve the CIE/A* path for every planned route.
- Use SIPP-style reservation timing only to delay traversal when node, edge, or merge capacity is occupied.
- Keep the hard runtime constraints enabled.
- Run on the real airport ICS `map2/inputdata` matched windows.
- Treat remaining no-path cases as CIE/A* route-intent inventory, not as a reason to replace the teacher.

## Outputs

- `src/czr005/baselines/legacy_route_sipp.py`
- `scripts/eval/run_g3i_cie_sipp_integration.py`
- `outputs/reports/g3i_cie_sipp_integration_report.md`
- `outputs/tables/g3i_cie_sipp_integration_summary.csv`
- `outputs/tables/g3i_cie_sipp_path_parity.csv`
- `outputs/tables/g3i_cie_sipp_gate.csv`
- `artifacts/teacher/legacy_astar/g3i_cie_sipp_integration_sample.jsonl`
- `outputs/figures/g3i_cie_sipp_integration.png`

## Gate

G3i passes if:

- the real ICS matched-window replay runs end to end,
- planned routes keep the original CIE/A* path,
- node, edge, and merge conflicts remain zero,
- planned count exceeds the `115/144` pilot gate.

## Expected Next Step

Use the G3i integration as the G4A pilot candidate, but first audit the remaining CIE/A* no-path cases from the repair-window and merge-group windows.
