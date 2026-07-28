# G4IRSF14 destination-owned merge-grant protocol

Status: `PASS_STAGE_D_PRODUCTION_E4_MECHANISM_EVIDENCE`

This is production E4 mechanism evidence, not a standalone fixture. Every M0–M6 row was executed through the production Python/native entrypoint on the same protected map2 and the same unreordered first 144 input rows. It is **not a performance promotion** and does not authorize a larger tier.

## Frozen evidence identity

- map2 raw SHA-256: `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`
- map2 LF-semantic SHA-256: `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63`
- inputdata raw/semantic SHA-256: `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f`
- exact first-144 prefix SHA-256: `e5688fdd82c93baafe7e78eb93e33410181baf3996317cadfd8e10285d726a94`
- selected raw bag count: `72`
- runtime source bundle SHA-256: `d3ef2a05a55cbc1f0884241c16b5e4641fd5f09ae2da918a11f322fca74876ed`
- loaded native binary: `build/python/czr005_cpp.cp311-win_amd64.pyd`
- loaded native binary SHA-256: `0d82141e8e650d682f812fe18582661ba6feb6dd08c88731c343d3caf07d6a38`

Frozen runtime tuple: `R3/S1/P2/C0/Q0/E4`, scale `1`, no fault, reservation depth `1`, no future route, no global scan, and no runtime A*.
The generator directly verifies the payload and summary loaded-binary path/SHA and the summary/trace echoes for this frozen tuple before admitting any run.

## Same-input mechanism A/B

M0 is the plan-defined current event-sequence / earliest-known control. Each M0–M6 rule was executed independently twice; the two deterministic runtime projections matched exactly before one complete lifecycle copy was published.

| rule | complete | mean seconds | p95 seconds | mean grant wait | requests | consumed | hard gates |
|---|---:|---:|---:|---:|---:|---:|---|
| M0 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |
| M1 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |
| M2 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |
| M3 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |
| M4 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |
| M5 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |
| M6 | 144/144 | 112.764088 | 203.452 | 0.385352292 | 666 | 442 | PASS |

Descriptive 144-prefix conclusion: `NO_RULE_IMPROVED_BOTH_MEAN_AND_P95_VS_M0_ON_144`. Exact deltas and per-run projection hashes are in `outputs/tables/g4irsf14_merge_rule_ab.csv`. Even a descriptive difference here is not independent replication, a promotion gate, or a full-scale result.

Observed mechanism-coverage limit: the maximum pending merge request count was `1` and M0-M6 outcome projections were exactly equal: `true`. With only one pending request at a time, this protected prefix did not elicit a rule-order divergence. These runs therefore prove the production grant path and complete lifecycle, not rule efficacy; native comparator and real-map tests cover the ordering semantics.

## Complete lifecycle and negative evidence

The lifecycle CSV contains every stored production transition for all seven online runs. Every run reports `lifecycle_dropped_count=0`; request/grant identity is retained together with exact directed edge, exact destination service slot, queue/calendar/fault generations, observed consume-time state, reason, and terminal state.
For every request, earliest edge entry equals request time, edge travel equals map2, projected arrival equals request plus travel, and each issued grant starts exactly at that arrival and expires exactly at its R3 slot end; future-shifted slots fail closed.

- `M7`: `REJECTED_FAIL_CLOSED` — `merge_grant_rule M7 is diagnostic-only and cannot run online`
- `M8`: `REJECTED_FAIL_CLOSED` — `merge_grant_rule M8/M9 require a validated model artifact; runtime selection fails closed`
- `M9`: `REJECTED_FAIL_CLOSED` — `merge_grant_rule M8/M9 require a validated model artifact; runtime selection fails closed`

M7 remains diagnostic-only. M8/M9 remain unavailable until a validated model artifact exists. No learned model is trained or promoted by Stage D.

## Reproduction

Run the generator with the exact native extension to be sealed:

```text
python scripts/eval/g4irsf14_merge_grant_protocol.py --binary <path-to-czr005_cpp-extension> --search-path <directory-containing-that-extension>
python scripts/validate_g4irsf14_merge_grant_artifacts.py --binary <same-extension>
```

The validator rejects the obsolete standalone/withheld schema, any input/source/output hash drift, missing online or negative rules, truncated lifecycle rows, row self-hash drift, hard-gate failure, topology escape, or an unauthorized promotion claim.
