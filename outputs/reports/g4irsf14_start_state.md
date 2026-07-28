# G4IRSF14-A Start State

Date: 2026-07-28

Status: `PASS_BASELINE_FROZEN`.

Stage 14A records the starting identities and references G4IRSF13 evidence
without rerunning it. Any identity, self-hash, provenance, or protected-file
drift is `FAIL_CLOSED`.

## Exact Git snapshot

| Item | Frozen value |
| --- | --- |
| Branch | `codex/czr005-rewrite` |
| HEAD | `750a14ca52755df99fa5f6f0952f04e014ff2274` |
| Upstream | `origin/codex/czr005-rewrite` |
| Upstream HEAD | `750a14ca52755df99fa5f6f0952f04e014ff2274` |
| HEAD equals upstream HEAD | `true` |
| Tracked worktree before Stage-14A writes | clean |

Descendant commits are valid only while `750a14ca52755df99fa5f6f0952f04e014ff2274` remains an ancestor and
the protected inherited paths have no worktree or committed drift.

## Protected real-map workload

| Item | Frozen value |
| --- | --- |
| Map | `data/processed/maps/map2.json` |
| Map raw SHA-256 | `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4` |
| Map semantic SHA-256 | `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63` |
| Map shape | 54 nodes / 69 directed edges / 54x54 heuristic |
| Task source | `data/processed/tasks/inputdata.jsonl` |
| Task raw SHA-256 | `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f` |
| Task semantic SHA-256 | `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f` |
| Task counts | 43,603 segments / 28,506 raw bags |

Raw hashes cover exact bytes. Semantic hashes decode UTF-8 and normalize only
CRLF/CR newlines to LF; JSON is not rewritten or semantically reordered.

## Frozen controls

| Control | Frozen result |
| --- | --- |
| F2 configuration | `R3 / S1 / P2 / C0 / Q0`, reservation depth 1 |
| F2 raw-entry mean | `41.514218717973` min |
| Frozen v2-safe raw-entry mean | `41.495306987809` min |
| Corrected historical HCA raw-entry mean | `43.135938280418` min |
| F2 delta vs v2-safe | `+1.134703809870` s/bag |
| F2 delta vs historical HCA | `-97.303173746685` s/bag |
| Final F2 binary SHA-256 | `814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7` |
| Final F2 source-bundle SHA-256 | `95026955f7ff96f9894220b2c4fea17b1ed2270b39ca59bd9feded8e4b7423e3` |
| Frozen model SHA-256 | `4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca` |
| F2 case-config SHA-256 | `60c91e937f3c8f14ff4a80f685ec3294da6e22196cdf254eea998acb677becf1` |

The earlier sealed F2 artifact names a different execution generation
(`82f15f08a8cff0e887447f017f0aa03fffabe9bfb3a79a563b16d779219d8222` binary and
`eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7` source bundle). It remains frozen and is
recorded separately; it is not presented as the final five-repeat binary.

## G4IRSF13 decision and scale lock

- Final decision: `HISTORICAL_ONLY_PASS`.
- Deployment: `KEEP_F2_FROZEN_CONTROL_NO_NEW_CANDIDATE_PROMOTION`.
- Strict win versus frozen v2-safe: `false`.
- Independent V3 contribution proven: `false`.
- Fault control: `FAULT_DISCRIMINATING_PASS` (13 executed, 12 informative,
  zero hard failures, aggregate unsafe entry 0).
- G4J: `CLOSED`; phase K: `UNKNOWN/CLOSED`; phase L: `NOT_RUN`.
- Scale execution count: `0`.

No scale workload is materialized or executed by Stage 14A.

## Machine-readable authority

- Baseline registry: `artifacts/gates/g4irsf14_baseline_registry.json`
- F2 control: `artifacts/policies/g4irsf14_f2_frozen_control.json`
- Fault control: `artifacts/policies/g4irsf14_fault_frozen_control.json`
- Git/identity ledger: `outputs/tables/g4irsf14_git_identity.csv`
- Registry self-hash: `67c3494d6d47ad89a8bcd73489346e6c121d4863f7ddcff49727132a1b655a51`

All new Stage-14A artifacts use the `g4irsf14_` namespace.
No G4IRSF12 or G4IRSF13 artifact is rewritten.
