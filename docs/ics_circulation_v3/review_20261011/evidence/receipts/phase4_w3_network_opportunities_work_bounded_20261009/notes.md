# Fixed-work follow-up on original-topology opportunities

This retains the first `phase4_w3_network_opportunities_20261009` record, including all six wall-limited runs. Before this follow-up, the same three development flows and two policies were declared again with unchanged algorithms, candidate count, dynamic search, modules, forecast schedule, true evaluation tape, and deterministic search budgets. Only the wall safeguards changed to 300 seconds per run and 1,200 seconds total. This is budget completion on the same sources, not an independent confirmation sample or tuning result.

All six runs reached their fixed horizons; all 48 scheduled bags completed. No work/call/wall cap was exhausted. Source hashes stayed unchanged. The actual work was 456 searches and 128,824 search-work units; recorded total time was 173.04 seconds on a shared workstation. Full visible-state records were kept; no opportunity or failed-search denominator was thinned to reduce recording work.

| Scene | Horizon | Completed per policy | Actual selector calls per policy | More than one physical prefix | Zero-candidate loaded searches | Baseline cost | Timed cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_cycle | 244 | 7 / 7 | 51 | 28 | 0 | 29.7 | 29.7 |
| counterflow | 352 | 10 / 10 | 72 | 47 | 0 | 192.4 | 192.4 |
| near_full | 244 | 7 / 7 | 51 | 27 | 6 | 13.7 | 13.7 |

The aggregate denominator is 360 loaded searches: 348 actual selector calls and 12 zero-candidate queries. Every selector call occurred after the burn-in initial state. All 348 calls had multiple `actual_action_key` values, which include retained conditional witnesses; 204 calls had multiple immediately committed physical prefixes and 144 shared one immediate prefix. The latter signatures use the owner's `_safe_prefix` geometry and times and do not replace authorization keys. This distinction prevents treating alternate conditional suffixes as distinct immediate physical movements.

Baseline and timed chose identical action-key traces, always the first supplied candidate, and had identical physical-state projections at all 243/351/243 observed ticks respectively. Their final costs are equal. Counterflow retained one binding committed-empty capacity query per policy; this is a read-only capacity-subtraction diagnosis, not permission to retract old transfers. The data establish that multiple actual routing opportunities exist on these proxy streams, while providing no evidence that this timed scorer changes their behavior or improves cost. There are no candidate rollout labels, optimality claims, new trained models, or new independent sources.

The original Nanning graph is unchanged. Workload, inventory, service, wait and permission proxies retain the gaps recorded in the topology and workload manifests. These six synthetic runs do not replace the original 28,506-task source denominator or implement its 15,097 early-storage bags; node 53 permissions are still unverified.

Exact command, using a fresh output directory:

```powershell
@'
from scripts.experiments.ics_circulation_v3.run_network_opportunities import run
from scripts.experiments.ics_circulation_v3.run_workload_diagnostics import DiagnosticBudget
s = run('outputs/experiments/ics_circulation_v3/phase4_w3_network_opportunities_work_bounded_rerun',
        budget=DiagnosticBudget(max_search_calls=300, max_search_work=300000,
                                per_search_work=3000, max_wall_seconds=300,
                                total_wall_seconds=1200))
raise SystemExit(int(bool(s['not_executed'] or s['source_changed_during_run']
                         or s['status_counts'].get('execution_failure'))))
'@ | python -
```

The four dedicated opportunity tests passed before both runs. No source or earlier output was changed between the first diagnosis and this fixed-work follow-up.
