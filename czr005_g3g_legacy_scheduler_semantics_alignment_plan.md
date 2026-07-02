# czr005 G3g Legacy Scheduler Semantics Alignment Plan

Date: 2026-07-02
Branch: `codex/czr005-rewrite`

## Scope

G3g continues after G3f. It does not train a model, does not create G4A data, does not modify legacy Java, and does not relax the hard shield. Its purpose is to explain why the G3f best executable Legacy scheduler still plans only `96/144` despite high branch label coverage and zero conflicts.

## Required Work

- Compare the Legacy Java/Python node-window route scheduler, the G3f local executable replay, and the full-route SIPP runtime scheduler.
- Classify the G3f unresolved edge-capacity cases by concrete timing semantics.
- Determine whether remaining blockers are edge release errors, current-node hold occupancy conflicts, or route-scope/backpressure mismatches.
- Preserve the distinction between paper-faithful Legacy route intent and runtime-safe executable labels.

## Outputs

- `scripts/eval/run_g3g_legacy_scheduler_semantics_alignment.py`
- `outputs/reports/g3g_legacy_scheduler_semantics_alignment_report.md`
- `outputs/tables/g3g_scheduler_semantics_matrix.csv`
- `outputs/tables/g3g_hold_conflict_taxonomy.csv`
- `outputs/tables/g3g_current_vs_upstream_wait_cases.csv`
- `outputs/tables/g3g_scheduler_replay_comparison.csv`
- `outputs/tables/g3g_full_route_alignment.csv`
- `outputs/tables/g3g_backpressure_edge_hotspots.csv`
- `outputs/tables/g3g_next_step_gate.csv`
- `artifacts/teacher/legacy_astar/g3g_scheduler_semantics_trace_sample.jsonl`
- `outputs/figures/g3g_scheduler_semantics_gap.png`

## Gate

G3g is a diagnostic pass if it:

- classifies all G3f unresolved edge-capacity cases,
- explains whether they require local hold, upstream backpressure, or full-route reservation timing,
- confirms no G4A/training should start unless the executable scheduler reaches the planned-count gate without real conflicts.

## Expected Next Step

If G3g confirms a scheduler-scope mismatch, continue with a backpressure-aware executable teacher or route pre-reservation semantics audit before any G4A pilot.
