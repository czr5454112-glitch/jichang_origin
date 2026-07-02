# czr005 G3h CIE Backpressure / Pre-Reservation Plan

Date: 2026-07-02
Branch: `codex/czr005-rewrite`

## Scope

G3h continues after G3g and keeps the original CIE/Legacy A* project as the primary teacher. It does not train a model, does not create G4A data, does not modify legacy Java, and does not relax the hard runtime shield.

The goal is to answer one narrow question:

```text
Can the original CIE route be made executable by waiting upstream of a full edge,
instead of waiting at the already-congested current node?
```

## Teacher Rule

- Teacher route intent comes from the original CIE/Legacy A* path artifacts only.
- Runtime labels may add upstream wait or CIE-sourced upstream reroute wrappers around that CIE route.
- Non-CIE planners are not used to produce teacher labels.
- Any CIE route that creates real edge/merge conflicts when replayed blindly must remain behind the hard runtime shield.

## Required Work

- Reuse the G3f best pure Legacy executable replay as the current baseline.
- Reuse the G3g current-vs-upstream wait cases to identify the remaining current-node hold-capacity failures.
- Classify each blocked case as:
  - CIE preserves the same bottleneck edge and only needs upstream waiting.
  - CIE reroutes upstream before the bottleneck.
  - CIE still has no path.
- Produce a recovery projection, but do not claim training readiness until a closed-loop replay proves it under the hard shield.

## Outputs

- `scripts/eval/run_g3h_backpressure_pre_reservation_audit.py`
- `outputs/reports/g3h_backpressure_pre_reservation_audit_report.md`
- `outputs/tables/g3h_cie_backpressure_candidate_labels.csv`
- `outputs/tables/g3h_cie_recovered_capacity_projection.csv`
- `outputs/tables/g3h_cie_path_alignment.csv`
- `outputs/tables/g3h_cie_upstream_wait_windows.csv`
- `outputs/tables/g3h_next_step_gate.csv`
- `artifacts/teacher/legacy_astar/g3h_cie_backpressure_teacher_sample.jsonl`
- `outputs/figures/g3h_cie_backpressure_projection.png`

## Gate

G3h is still a diagnostic pass if it:

- keeps original CIE/Legacy A* as the only teacher-label source,
- shows whether upstream waiting can plausibly pass the `115/144` planned-count gate,
- records the raw CIE conflict count so blind route execution is not mistaken for a safe result,
- points to a closed-loop CIE backpressure replay as the next step before G4A/training.

## Expected Next Step

If the projection passes the planned-count gate, implement G3i as a closed-loop CIE backpressure replay under the hard shield. Only after that replay passes with zero real conflicts should the project reconsider a G4A pilot dataset.
