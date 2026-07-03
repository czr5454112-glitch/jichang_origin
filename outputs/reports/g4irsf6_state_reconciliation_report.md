# G4IRSF6 State Reconciliation Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

## Audit

| Item | Status | Details |
| --- | --- | --- |
| branch | PASS | Expected branch is codex/czr005-rewrite. |
| g4irsf5_generation_vs_commit | RECORDED | G4IRSF5 artifacts were generated at 1aff5eb and committed in de3e5e2; G4IRSF6 reports now carry generation/commit/remote heads. |
| remote_equal_local_before_generation | PASS | This captures pre-G4IRSF6 remote state; final push is checked after commit. |
| legacy_java_diff_empty | PASS | Legacy Java is read-only; Java attempts use temp class/output directories. |
| main_map_diff_empty | PASS | Speed sweeps use artifacts/maps/g4irsf6 derived maps, not data/processed/maps/map2.json edits. |

G4IRSF5 state mismatch is explicitly preserved: artifacts were generated at `1aff5eb`, then committed and pushed in `de3e5e2`. G4IRSF6 artifacts include the generation, commit-at-generation, and remote heads in their reports.
