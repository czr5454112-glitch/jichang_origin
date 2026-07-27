# G4IRSF13-E PIBT Contention Analysis

Status: `MATCHED_CONTENTION_EVIDENCE_READY`.

The cohort is derived from actual, uncensored P2 transactions in the F2 full run and reuses unchanged rows from the protected task file on the complete protected map.

## Matched gate

- TTH comparison eligible: `True`.
- Cohort SHA-256: `1df50671e23800809f00eb8a2372850737a67824ed6b13e55021bf6877dc6a46`.
- Complete modes: `E_P0, E_P1, E_P2, E_P3, E_P4`.
- Blockers: `none`.

P0-P4 TTH values are published in the matched table only when every mode drains the identical cohort and clears all hard gates. Survivor timing is never substituted.

## Preference evidence

The dodge variants use one-step local tie-breaking and unique-exit / wait-for-cycle protection. The frozen local regret input is currently an observed contention-risk proxy, not a causal regret estimate; it therefore cannot by itself support promotion.

## Theory boundary

The protected directed graph has merges, splits, bridges, multiple SCCs and sinks. The implementation is accurately described as `PIBT-inspired bounded local priority inheritance and backtracking`; classic PIBT finite-arrival guarantees are not claimed.

Recorded contention result rows: `13`.
