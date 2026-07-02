# G4D Risky Branch Audit

Date: 2026-07-02

## Scope

This audit focuses on the four G4C risky branch families. It uses the G4D large-window CIE retry teacher slices and does not train RL or use forbidden route labels as model inputs.

## Summary

- Risky branch cases: `2981`
- Target current nodes: `[6, 11, 16, 19]`

## Teacher Distribution

| Current | Candidates | Cases | Distribution | Diagnosis | Recommendation |
| --- | --- | --- | --- | --- | --- |
| 6 | [8, 12] | 489 | {8: 221, 12: 268} | local_features_overlap_tie_sensitive | risk_head_or_fallback_still_needed |
| 11 | [13, 14] | 1165 | {13: 904, 14: 261} | local_features_overlap_tie_sensitive | risk_head_or_fallback_still_needed |
| 16 | [17, 21] | 670 | {17: 412, 21: 258} | mixed_context_branch_preference | use_enhanced_features_and_calibrated_risk_head |
| 19 | [18, 25] | 657 | {18: 351, 25: 306} | mixed_context_branch_preference | use_enhanced_features_and_calibrated_risk_head |

## Decision

The risky branches are no longer sample-starved in the large-window slice, but several remain mixed-context or locally overlapping. G4D should use the enhanced local features plus a calibrated risk head, not a blanket claim that the branches are fully learned.

## Artifacts

- Cases: `outputs/tables/g4d_risky_branch_cases.csv`
- Feature summary: `outputs/tables/g4d_risky_branch_feature_summary.csv`
- Error modes: `outputs/tables/g4d_risky_branch_error_modes.csv`
- Heatmap: `outputs/figures/g4d_risky_branch_heatmap.png`
