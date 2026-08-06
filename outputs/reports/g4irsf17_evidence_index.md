# G4IRSF17 evidence figure index

Current joint decision: **`TERMINAL_WITH_CAPACITY_CENSORING_ACTIONABLE_PIVOT`**.

| Figure | Status | PNG | Evidence input |
|---|---|---|---|
| wait_reason_stacked | EVIDENCE | [g4irsf17_wait_reason_stacked.png](../figures/g4irsf17_wait_reason_stacked.png) | `outputs/tables/g4irsf17_source_wait_topology_attribution.csv`, `outputs/tables/g4irsf17_source_wait_cause_ledger.csv` |
| source_blocker_time_heatmap | EVIDENCE | [g4irsf17_source_blocker_time_heatmap.png](../figures/g4irsf17_source_blocker_time_heatmap.png) | `outputs/tables/g4irsf17_source_wait_topology_attribution.csv`, `outputs/tables/g4irsf17_source_wait_cause_ledger.csv` |
| i1_effect_distribution | EVIDENCE | [g4irsf17_i1_effect_distribution.png](../figures/g4irsf17_i1_effect_distribution.png) | `outputs/tables/g4irsf17_i1_effects.csv` |
| i1_effect_coverage | EVIDENCE | [g4irsf17_i1_effect_coverage.png](../figures/g4irsf17_i1_effect_coverage.png) | `outputs/tables/g4irsf17_i1_effects.csv` |
| aliasing_before_after | EVIDENCE | [g4irsf17_aliasing_before_after.png](../figures/g4irsf17_aliasing_before_after.png) | `outputs/reports/g4irsf17_state_aliasing_audit.md`, `outputs/tables/g4irsf17_feature_ablation.csv` |
| ladder_tth | BASELINE_ONLY_NO_AUTHORIZED_CANDIDATE | [g4irsf17_ladder_tth.png](../figures/g4irsf17_ladder_tth.png) | `outputs/tables/g4irsf17_closed_loop_ladder.csv` |
| source_network_decomposition | EVIDENCE | [g4irsf17_source_network_decomposition.png](../figures/g4irsf17_source_network_decomposition.png) | `outputs/tables/g4irsf17_closed_loop_ladder.csv`, `artifacts/manifests/g4irsf17_campaign_manifest.json` |
| scale_tth | EVIDENCE | [g4irsf17_scale_tth.png](../figures/g4irsf17_scale_tth.png) | `outputs/tables/g4irsf17_scale_results.csv` |
| scale_compute | EVIDENCE | [g4irsf17_scale_compute.png](../figures/g4irsf17_scale_compute.png) | `outputs/tables/g4irsf17_scale_results.csv` |
| fault_timeline | EVIDENCE | [g4irsf17_fault_timeline.png](../figures/g4irsf17_fault_timeline.png) | `outputs/tables/g4irsf17_fault_results.csv`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__critical_bottleneck.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__delayed_beacon.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__dropped_intermediate_beacon.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__dual_disjoint.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__dual_interacting.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__ebs_outgoing_edge.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__merge_incoming_edge.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__noncritical_edge.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__repair_reopen.json`, `outputs/runstate/g4irsf17_system_campaign/jobs/fault__e4_off__1x__source_first_edge.json` |

`NOT_RUN/NO_EVIDENCE` panels are intentional: they prevent missing campaigns from appearing as zero-effect results.

## Publication boundary

Raw `*.source_wait.json`, `*.raw_bag_timings.csv`, and `outputs/runstate/**` files are local resumable inputs and are intentionally not distributed with the repository. The committed CSV tables, Markdown reports, and rendered figures in this index are the compact publication evidence; any raw runstate path shown in provenance is not a promised repository file.

## G2 matched M1–M6 action screen

Decision: **`CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT`**.

| Screen fact | Observed value |
|---|---|
| Matched comparisons | 20 |
| Segment levels | 144, 512, 2,048, 8,192 |
| Rules | M1 vs M2–M6 |
| All exact competitive boundary counts | 0 |
| All mean TTH/source-wait/network deltas | 0 |
| Hard safety | 20/20 PASS |
| Same-state causal opportunities | 0 |
| Causal follow-up shortlist | 0 |
| Causal authorization | False |

Zero deltas with zero competitive boundaries mean that the eager-token seam exposed no effective rule choice; they are not evidence of successful or equivalent M1–M6 performance.

Next pivot: **strictly-local just-in-time service-slot arbitration over a bounded pending set**. Evidence: `outputs/tables/g4irsf17_g2_matched_pilot.json`.
