# Original-topology routing opportunity diagnosis

This is a development diagnosis of three existing synthetic sustainable-flow proxies on the unchanged Nanning directed graph. It does not constitute operational Nanning traffic data, a label-value study, independent confirmation, or a learned-policy performance result. The supplier inventory, wait/service and empty-tray passage assumptions documented in `topology_audit.json` and each workload manifest remain assumptions. It does not implement the 15,097 early-storage bags or establish node 53 storage permissions.

The declared six runs used `next_edge`, four requested candidates, dynamic local routing with three local labels, prediction horizon 180, and the same greedy predictive slow controller with period two. Each run was bounded by 300 searches, 300,000 search-work units, 3,000 work units per search, and a 20-second wall safeguard; total wall safeguard was 180 seconds. These settings were announced before running. Neither true future bags nor labels entered the selectors or slow controllers.

`selector_calls` contains the candidates actually supplied by the runtime, after prior same-tick commitments, plus the visible state without the repeated static graph. No externally enlarged candidate pool is called an actual decision. The search log separately retains calls returning no candidates. Action keys include retained conditional witnesses. `physical_prefixes` instead use the execution owner's safe-prefix result and retain only geometry, times, endpoint and service/prefix fields; they are diagnostic signatures and never replace authorization keys.

| Scene | Actual selector calls per policy | Calls with more than one physical prefix | Zero-candidate loaded queries per policy | Completed / all scheduled per policy | Common observed ticks / different physical projections |
| --- | ---: | ---: | ---: | ---: | ---: |
| cross_cycle | 51 | 28 | 0 | 7 / 7 | 219 / 0 |
| counterflow | 57 | 36 | 0 | 8 / 10 | 193 / 0 |
| near_full | 51 | 27 | 6 | 7 / 7 | 214 / 0 |

Across six runs, all 318 selector calls occurred after the initial burn-in state. All had more than one action key, but only 182 had more than one immediate physical prefix. Thus 136 calls had several conditional witnesses while sharing one immediate commitment. Candidate count alone overstates immediate physical choice. Counterflow produced one binding committed-empty resource query per policy under the read-only capacity-subtraction diagnostic; it did not execute a cancellation or a capacity-violating counterfactual.

Every run hit the wall safeguard before its fixed horizon. The complete planned and executed bag denominator is 48, with 44 completed; counterflow retained two unfinished bags per policy. Cross-cycle and near-full completed all their bags, but their runs still did not reach the fixed horizon. All six are labeled `budget_exhausted`, no comparable total costs are reported, and no failed search is treated as proof of infeasibility. The three paired policies had identical physical projections at every common observed tick; this diagnosis provides no evidence that timed scoring improved these streams.

There were 426 searches and 120,444 search-work units in 128.86 seconds including recording. Individual process CPU times were about 19.75–20.00 seconds. Here the wall safeguard was binding before the declared work ceiling; observed stopping ticks therefore depend on recording overhead and shared-machine load. This is not a latency benchmark. Raw records and failures are retained; no thresholds were tuned against these outcomes. No labels were generated and the independent-source count is zero.

Reproduction uses a fresh output directory:

```powershell
python -m scripts.experiments.ics_circulation_v3.run_network_opportunities --output outputs/experiments/ics_circulation_v3/phase4_w3_network_opportunities_rerun
python -m pytest tests/test_ics_circulation_v3_network_opportunities.py -q --basetemp .tmp/ics_v3_network_opportunities_tests_new
```

The four dedicated tests passed. All recorded source hashes remained unchanged during the six runs. Previous workload and label outputs were not modified.
