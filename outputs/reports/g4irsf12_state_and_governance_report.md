# G4IRSF12-A State and Governance Report

Date: 2026-07-23

Phase-A gate: `PASS`.

This gate freezes identities and claim boundaries.  It does not claim that the
G4IRSF11 algorithm passed capacity, service, or recovery gates, and it does not
open G4J.

## Starting Git snapshot

| Item | Value |
| --- | --- |
| Branch | `codex/czr005-rewrite` |
| HEAD | `259608cd536f8ca2f6651a01b7d842675f63a9f7` |
| Upstream | `origin/codex/czr005-rewrite` |
| Upstream HEAD | `259608cd536f8ca2f6651a01b7d842675f63a9f7` |
| Worktree before Phase-A writes | clean |
| Start commit is current-HEAD ancestor | `true` |

`legacy/`, `data/processed/maps/map2.json`, and `data/processed/tasks/inputdata.jsonl` had no
worktree diff at the snapshot and remain protected by the Phase-A validator.

## Frozen identities

| Item | Frozen value |
| --- | --- |
| Map raw SHA-256 | `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4` |
| Map semantic SHA-256 | `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63` |
| Map dimensions | 54 nodes, 69 directed edges, 54x54 heuristic |
| Input raw/semantic SHA-256 | `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f` |
| Input rows | 43,603 segments |
| Original bags | 28,506 unique task IDs |
| Formal cohort | 84/84 executed |
| Implementation SHA-256 | `92c7e4588a902770fd14ffd87c4924f7f7af9246a42b00dfc523616591e04ba9` |
| Source-bundle SHA-256 | `99758e68f445d97c00b876e2edb788df2fdb51eb2443af42e9384b66ebd801e5` |

Raw hashes are byte hashes.  Semantic hashes normalize CRLF/CR newlines to LF;
they do not canonicalize or rewrite JSON.

## Governance added

`docs/czr005_project_governance.md` now contains:

- `Original-Scale-First Rule`;
- `Real-Demand Scaling Rule`;
- `Framework Variable Isolation Rule`;
- fail-closed map/input identity requirements; and
- an explicit denominator boundary: historical `3.967122711` minutes is
  processed-segment-attempt THT, not original-entry THT.

No 2x-or-higher full run is authorized until a new event candidate passes the
complete 1x gate.  No multiplier may be called real demand before a committed
demand-calibration report exists.

## Validation boundary

The machine-readable audit is
`outputs/tables/g4irsf12_git_and_identity_audit.csv`.  Prior-result
reconciliation is in
`outputs/reports/g4irsf12_prior_evidence_reconciliation.md`.
