# Original-topology workload diagnostics, 2026-10-09

This is development mechanism evidence on the original Nanning directed topology. It is not a Nanning operating-day replay, a held-out performance study, W2 acceptance, or a supplier-module integration.

## Input findings and full denominators

- The packaged profile contains 151 nodes and 227 directed edges. The existing capacity-zero edge `97→98` remains closed. All 226 positive edge capacities and directions are retained; no reverse edge was synthesized.
- Of all 11×42 = 462 loader/unloader pairs, 396 have a directed loaded path. Only 360 also have an empty return to the original loader. There are 66 outbound-unreachable pairs and 36 outbound-reachable/nonreturnable pairs. Static cycles do not establish dynamic schedulability or stable throughput.
- The existing `nanning_1x_raw.txt`, `nanning_1x_canonical.jsonl` and `nanning_1x_manifest.json` were supplied explicitly. Every canonical segment was reconciled to its raw task identity, endpoints and original clock; full counts and OD marginals match the manifest: **28,506 original bags, 43,603 segments, 13,409 direct bags and 15,097 early-storage bags**. The manifest records 360 flights; raw rows do not carry flight identity, so that count is attributed to the manifest, not independently reconstructed.
- In the complete 28,506-bag source, 21,833 have a directed loader/unloader return cycle; 4,001 are outbound-unreachable and 2,672 lack a return. These are preserved source denominators, not silently filtered samples.
- The source is a timetable-preserving demand projection from another map. It is not observed Nanning OD history.
- **The 15,097 early-storage bags remain an unsupported lifecycle.** Their old canonical projection uses node 53 / IDK1 as an EBS proxy, while the original source identifies it as empty-tray storage. This experiment does not grant EBS/module permission, convert these bags to direct bags, or claim their service was simulated.
- The fixed `[36000,36060)` projected window contains 31 bags: all 13 direct bags are admitted to the input tape without thinning; 18 early-storage bags remain explicitly unsupported. Another 28,475 bags are outside the window. The direct-window engine denominator is 14 including one synthetic burn-in bag. It completed 4/14 before its computation budget stopped; this is not successful full-window or full-day acceptance.

Full source hashes, counts and mapping provenance are in `../phase4_w2_workloads_20261009/projected_task_audit.json`. The topology classification of every OD is in that directory's `topology_audit.json`. The three original task files are referenced and hashed, not bundled here; replay of that audit requires those explicitly supplied inputs.

## Explicit operational proxies

The time step is 10 seconds, with each original edge travel time rounded up independently. Node capacity is normally 2; reception capacity and unloading duration are 1. Twenty-seven documented type-4 nodes with dense ID divisible by 3 are designated nonwaitable as a sensitivity proxy. Real wait permissions, supplier passage rules, initial stock and calibrated service semantics are missing. Transit/loading service is not a complete source-service model. Both tray modes use the positive directed graph.

The unchanged `FixedLocalModule` and `ExecutionValidator` own authorization. Every scene begins from a real protected loaded-route admission and one physical burn-in tick. No route calendar was invented. Integer-time whole-route commitments remain irrevocable. The ample-stock condition increases both stock and all node capacities to allow legal initial/final parking; it is **not a stock-only ablation**.

All forecasts are synthetic publications. Only the event engine and offline ledger receive actual future bags. No dataset forecast record is fabricated for the projected window, which runs reactive control only.

## Preserved 29-run matrix

`../phase4_w2_workloads_20261009` retains the original 14-condition paired matrix plus one projected-window run. Its source snapshot and manifests describe the source used then; these historical files were not rewritten after adding counterflow diagnostics.

- 29/29 planned runs executed: 19 completed all scheduled bags; 10 exhausted a bounded search/work/call/wall budget. No execution exception or state-invariant failure was recorded.
- The aggregate mechanism ledger is 139/176 completions across repeated scenarios and policies. It is not a field success-rate estimate.
- Work used: 1,833,197 search units and 2,780 search calls. Elapsed wall time was 151.57 seconds on a shared machine, not a latency/throughput conclusion.
- Each run had limits of 300 search calls, 300,000 total search work, 3,000 work per query and a 15-second wall safeguard. Total wall safeguard was 180 seconds. Missing candidates under these bounds do not prove infeasibility. Separate static OD certificates explain the deliberately unreachable cases.

| Development condition | Reactive cost | Predictive cost | Completion in both |
|---|---:|---:|---:|
| cross_cycle | 109.7 | 33.7 | 7/7 |
| near_full | 106.7 | 13.7 | 7/7 |
| ample | 0 | 0 | 7/7 |
| reversal | 106.7 | 35.7 | 7/7 |

The shared-receiver case retained a negative result: reactive completed 2/7 and predictive 5/7 before budget exhaustion. Both costs are unavailable for a common-horizon comparison. The reversal is worse than the matched accurate-forecast near-full predictive case, but it still beats reactive in this constructed instance; it is not evidence that every reversal harms reactive-relative performance.

## Counterflow supplement and active shared-edge constraint

This directory contains two additional runs with three opposing real loader/unloader flows. The selected static paths share `28→29`; its original capacity remains **2**. Arrival phases align two loaded witnesses with the nominal latest empty-return witness using only static path travel times. This is an explicitly constructed mechanism challenge, not a sampled operating day.

Both policies completed 10/10 scheduled bags and reused all four tray identities. Reactive cost was 297.0; predictive cost was 212.4, with six accepted advance empty transfers. The pair used 10,319 search work units in 42 calls and 12.89 seconds of shared-machine wall time. Limits were 400 calls, 500,000 work units, 3,000 per search, 20 seconds per run and 50 seconds total.

The predictive record contains a direct capacity witness:

1. At tick 36, loaded request `counterflow:round0:flow1:0` has a static earliest witness requesting `edge:28→29` at tick 42.
2. Including the accepted empty-transfer calendar makes that witness violate capacity at tick 42.
3. A **read-only capacity subtraction diagnostic** removes only the committed empty calendar from the tested reservation set; the conflict on that resource disappears. No tray or reservation is removed from the executable state, and no counterfactual is committed.
4. The actual authorized loaded candidate delays unloading by one tick relative to the static witness. `binding_empty_edge_queries=1`.

See `counterflow__predictive_True.json`, especially `capacity_subtraction_diagnostics`. Capacity-only subtraction is not a legal cancellation action or a complete route-feasibility proof. Simultaneous occupancy counts alone would not prove constraint activity; capacity-one conflicts should instead produce delay/rerouting/rejection.

## Reproduction and remaining work

Current counterflow command:

```powershell
python -m scripts.experiments.ics_circulation_v3.run_workload_diagnostics --scenes counterflow --max-search-work 500000 --max-search-calls 400 --max-wall-seconds 20 --total-wall-seconds 50 --output outputs/experiments/ics_circulation_v3/NEW_COUNTERFLOW_DIRECTORY
python -m pytest tests/test_ics_circulation_v3_network_workloads.py -q --basetemp .tmp/NEW_NETWORK_TEST_DIRECTORY
```

The 25 dedicated tests pass, including original topology/capacity preservation, all-OD classification, raw/canonical identity and denominator validation, legal burn-in, actual tray reuse, nonwaitable-node safety, explicit unfinished future denominators, output preservation and a capacity-one subtraction/delayed-route regression.

The current default matrix also includes the new counterflow condition. Reproducing the historical 29-run matrix requires its recorded source/explicit original 14-name list; do not overwrite that directory. Every runner rejects nonempty output directories. Work limits are the primary reproducible cutoff; wall safeguards may stop at different points under shared-machine contention.

Remaining gaps include true early-bag storage semantics and node-53 permissions, measured module authorization/service/capacity/inventory, realistic forecast errors and revisions, wider operating workloads, terminal empty-stock drainage, and integration with the independent distributed-clock/joint-control work. These results do not complete those tasks.
