# G31 all-day fault preflights, 2026-09-07

Four isolated full 1x runs: map2/nanning, scenarios 01/02, speed 2.5 m/s, seed 104729. All requested raw bags and segments were executed without source prefiltering. These outputs do not occupy the formal matrix namespace.

`orchestration.json` binds the original commands, frozen input specs and generating runner SHA. Each cell preserves the complete returned native payload, all native bag records, full raw population table, normalized metrics and archive hashes.

`preflight_verification.json` records four accepted population/archive audits and independent surviving-topology reachability counts. Scenario 02 has 3193 (map2) and 2620 (nanning) unreachable segments; exactly those remain parked, and every reachable segment completed. Timing is N/A for those incomplete populations. All four have zero forbidden-edge entries, no event-budget exhaustion and valid native active-state accounting. The bounded lifecycle log is truncated; the observed full-protocol flag remains false and no full-trace proof is claimed.

The original loader falsely rejected reloaded fault provenance because JSON edge pairs are lists while reconstructed pairs were tuples. The first failure receipt and its auditor are retained. No native run or result was changed. `loader_source_binding.json` binds the exact runner that generated these runs, the accepted population-audit receipt, both auditor source copies, and an AST check proving the subsequent production source change is restricted to the read-only load_completed function.

To repeat the read-only audit from the same worktree (no simulation):

    python tmp/audit_g31_fault_preflights_20260907.py

The replay helper is also preserved byte-for-byte in tools. Its ROOT resolution expects its original worktree/tmp location; it is source evidence, not a standalone portable environment. The original source snapshots and absolute input/build references still require the documented workspace dependencies.
