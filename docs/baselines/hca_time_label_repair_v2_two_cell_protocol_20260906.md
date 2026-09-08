# HCA A* time-label repair: two-cell diagnostic protocol, 2026-09-06

The user authorized an isolated repair and exactly one map2 1x and one Nanning 1x simulation, followed by comparison with existing G31 and HCA results. Both use the already frozen seed 104729 inputs. No other loads, seeds, algorithms or repeated full simulations are part of this diagnostic.

## Implementation identity and preservation

Method: `HCA_TIME_LABEL_REPAIR_V2`. Original user project, repository read-only mirror, V1 wrapper/runner/classes, workloads, old tables and evidence remain unchanged. The new App/GUI source lives under `benchmarks/java/hca_time_label_repair_v2`. Its only algorithm change is assigning `n.t1 = t1; n.t2 = t2;` when the A* open-node path is improved, so the saved timestamps match the already checked candidate and new parent. No comparator, closed-set, waiting, reservation, heuristic, release, speed or EBS rules are changed. The wrapper copy changes only its METHOD string. Execution-ID repair and population accounting remain the same as V1.

The new runner is a copy of `scripts/eval/run_hca_segment_identity.py`; changes are isolated source paths, V2 method/schema names, this protocol path, native wrapper identity verification, and an exact two-cell input/output guard. A pre-run freeze binds source, classes, runner, protocol, tests, inputs, comparison controls and preservation hashes. Completed output is immutable; reuse only verifies it and never runs Java again. A failed cell is retained and not silently rerun.

## Fixed run contract

- Maps: `map2`, `nanning`; load 1.0; seed 104729; existing workload identities under `data/processed/workloads/cie_external_robustness`.
- Each input has 28,506 raw bags and 43,602 canonical segments after the existing ±5-second arrival perturbations. Inputs are not regenerated.
- Same map, raw, canonical and identity SHA256 as the paired V1/G31 cells.
- Native start epoch 8260, 90,000 epochs, final horizon 98259; one repetition, zero warmups, no faults; speed 2.5 m/s. Storage map2 47/52, Nanning 53/53; thresholds 4800/2700 seconds.
- Use the exact same Java benchmark argument contract and JDK 18. G31 and old HCA use frozen results, not new executions.
- Separate Java microtests check the old defect, repaired recurrence on a small graph and real-map controls, plus reservation consistency. These are unit probes, not extra full simulations.

## Acceptance and reporting

Before simulation, the old five-node counterexample must exhibit inconsistent time labels; its repaired version must pass. Actual `update_constrain` must reserve corrected time intervals and reject a conflicting later request. After simulation, verify native mapping/release/planning/completion/terminal records against every canonical segment and every raw bag. Independently check every exported route's duration equals all node through-times (including source and goal) plus all edge travel times on that exact path, within 1e-7 seconds. Incomplete populations retain TH but receive no full-population THT. Do not extend the horizon or cherry-pick successful bags.

Report TH and raw-bag THT min/mean/max under both existing clocks: (1) sum of segment completion minus canonical scheduled release D, and (2) sum of completion minus successful planning for HCA or native admission for G31. Native clocks are not established as identical physical start semantics across systems. Compare old versus repaired HCA using identical accounting, with G31 fixed. A smaller value is better; G31 relative reduction is `(HCA - G31) / HCA * 100%`, and negative values mean G31 is slower. Report absolute gap in seconds and percentage-point change to avoid denominator ambiguity.

All findings are limited to these two paired instances. Do not infer ten-seed significance, entire-campaign validity or exhaustive physical correctness from this probe. Keep existing V1 evidence intact and identify its time-label defect explicitly.
