# CIE reviewer issue closure

Date: 2026-09-02
Status: `FINAL_EVIDENCE_CLOSED`

## Evidence rules

This ledger closes the native-DH, component-ablation, equivalence, and paired
robustness issues against finalized repository artifacts. No result is inferred
from a partial log, survivor-only cohort, or missing field.

- P0, P1, and P2 answer different questions and are never merged into one ranking.
- Every formal 2× cross-algorithm THT is `N/A`, including a cell in which both
  arms complete. Fixed-denominator completion, deadline, tardiness, time-to-X,
  and corrected fixed-horizon backlog remain eligible.
- The random campaign is fixed by the frozen manifest and committed runner:
  five registered scenarios, ten fixed paired seeds, and the same arrival and
  service realization for both arms of a seed.
- `SERVICE_X2` retains the 1× population. It is a service-pressure control, not
  workload 2×.
- `outputs/tables/cie_safety_audit.csv` belongs to old G35 and is not evidence
  for this round. Current safety evidence is per-run `execution_integrity` plus
  strict aggregate identity and completeness gates.
- Activation quantiles, correlations, and hotspot fields not collected because
  they had no decision value are `NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`.
- Corrected fixed-horizon backlog is authoritative; legacy incomplete-tail
  percentages are not used.

## Closure summary

| Issue | Final status | Decision |
|---|---|---|
| Feng-native CIE-DH | `CLOSED_WITH_NATIVE_DH_BLOCKER` | Retain native HCA aggregate regression; do not relabel an adaptation as native DH. |
| P0/P1/P2 boundary | `CLOSED_PROTOCOL_SCOPE` | Report and rank only within protocol. |
| Original-paper G31/HCA subjects | `CLOSED_DETERMINISTIC_PERFORMANCE` | Retain two-map 1× latency and 2× capacity results; 2× THT stays N/A. |
| Potential/dynamic factorial | `CLOSED_CONDITIONAL_FACTORIAL` | Effects are topology/load dependent, not universally additive. |
| Component activation | `CLOSED_ACTIVATION_ONLY` | Activation selects tests; it is not outcome evidence. |
| J2/M3 exact contrast | `BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT` | Current interface cannot isolate merge rule from timing contract. |
| Strict descent | `CLOSED_TARGETED_LOCAL_BENEFIT_NOT_GENERAL` | Retain only Nanning `single_3` local benefit. |
| P2 local buffer | `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY` | Remove from performance claims until physical capacity is grounded. |
| E2 event hotpath | `COMPUTE_ONLY_ROLE` | Strict two-map physical equivalence; event reduction is not physical capacity. |
| Pure fault potential | `CLOSED_PURE_POTENTIAL_3_OF_4_BENEFIT_1_TIE` | Retain only for four registered persistent fixed faults. |
| Service normalization / No-Q/I | `CLOSED_MIXED_STOP` | Mixed cross-map/condition directions; stop both directions. |
| Paired random robustness | `COMPLETE_FROZEN_PAIRED_SEEDS` | Five scenarios, 100/100 artifacts, zero failures, paired 95% CIs. |
| Random fault robustness | `BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE` | No randomized fault effect claimed. |
| Random potential×dynamic interaction | `INTERACTION_NOT_ESTIMATED` | Matrix estimates only P1D1−P0D0 combined contrast. |
| Native HCA mechanism counters | `BLOCKED_NATIVE_HCA_MECHANISM_COUNTERS_NOT_INSTRUMENTED` | Do not infer unavailable HCA activation. |
| Safety and identity | `CLOSED_EXECUTION_INTEGRITY_AND_AGGREGATE_GATES` | Experimental integrity, not formal certification. |
| Paper claims | `FINAL_CLOSED_WITH_EXPLICIT_BLOCKERS` | Final values and explicit blocked/N/M states replace all placeholders. |

## Baseline identity and formal performance

The recovered Feng Java HCA run exactly matches its frozen aggregate: 43,603
segments and 28,506 raw bags complete, with processed-attempt min/mean/max
`3.133333/3.945169/5.950000 min`. Relative to published
`3.13/3.96/5.98 min`, errors are `+0.106%/-0.375%/-0.502%`. This is aggregate
regression, not route-trace identity. No executable position-level native
CIE-DH state machine was recovered. P1 common-executor CIE-DH and Tarău-2010
remain adaptations; P2 is an end-to-end system comparison. Native HCA counters
are `BLOCKED_NATIVE_HCA_MECHANISM_COUNTERS_NOT_INSTRUMENTED`.

G31 improves full-population 1× mean/tail latency and completes the 57,012-bag
2× population on both maps, while HCA leaves 95 map2 bags and 17,949 Nanning
bags incomplete. These are deterministic results on two known topologies. All
formal 2× THT remains N/A. The complete 24-run factorial supports conditional
attribution and interaction diagnosis, not universal additive gains.

## Activation and targeted mechanisms

The registered ten-cell activation scan is complete. Missing activation
quantiles, correlations, and hotspots are
`NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`. J2/M3 activation is visible, but
the exact contrast is `BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT`; the
historical G18 signal is not promoted to a current causal result.

P2 has zero applicability through rollback in every formal cell because formal
capacity is unbounded. It is `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`.
The targeted aggregate admits only 9/12 mandatory runs: three Nanning minus-
Q/I combinations fail `merge_grant_active_bijection`. Failed runs remain
reported but do not enter paper effects; optional WC is dormant/missing.

## Fixed-fault mechanisms and corrected backlog

Strict descent is neutral in three cells. In Nanning `single_3`, completed bags
change `28,491 -> 28,506`, on-time `25,617 -> 26,018`, missed `2,889 -> 2,488`,
tardiness sum `-31.145%`, and corrected backlog
`100,322,141.572124 -> 95,914,523.385383 bag-s` (`-4.393465%`). Because OFF is
incomplete, paired mean/P95/P99/max is N/M. Nanning `pair_3_5` is not an exact
backlog tie: `-28,077.317 bag-s` (`-0.003129%`).

For the isolated surviving-graph DLP contrast, corrected backlog effects are:

| Fixed fault | Completed OFF→ON | Corrected backlog OFF→ON | Effect |
|---|---:|---:|---:|
| map2 `single_4` | 10,248→28,506 | 1,015,984,862.649766→70,452,656.819033 | -93.065580% |
| map2 `pair_2_4` | 5,453→22,113 | 1,287,277,282.705624→419,703,509.738353 | -67.396029% |
| Nanning `single_3` | 17,559→28,506 | 643,431,201.021053→95,914,523.385383 | -85.093274% |
| Nanning `pair_3_5` | 12,186→12,186 | exact corrected tie | 0% |

This is a 3-of-4 persistent fixed-fault result, not dynamic detection, repair,
or recovery.

## Service control and E2 v2

The service study has 12/12 runs and 4/4 matched groups. `SERVICE_X2` is a
1×-population service-pressure control, not workload 2×. Normalization and
No-Q/I reverse direction across maps/conditions; status is
`MIXED_NO_GENERAL_GAIN_STOP`.

E2 v2 is `COMPLETE_STRICT_PHYSICAL_EQUIVALENCE` on both maps at current 1×:
complete untruncated move/hold sequences, terminal state, and
release/admission/completion times match at `1e-9`. Events fall
`4,752,689 -> 3,997,648` (`-15.8866%`) on map2 and
`8,645,838 -> 7,087,605` (`-18.0229%`) on Nanning. The physical causal total is
unchanged. `event_queue_peak` is N/M; wall/CPU/RSS are single-run descriptive
fields. E2 is `COMPUTE_ONLY_ROLE`, never physical capacity.

## Frozen paired random robustness

The committed runner and frozen manifest fix map2 1.00×/1.75×/2.00× and
Nanning 1.00×/2.00×, ten paired seeds, arrival `uniform[-5,5]`, and node-service
lognormal `sigma=0.05`. Both arms of a seed share the same realization. All
100/100 artifacts pass, failure rate is zero, and CIs use 10,000 paired
bootstrap resamples.

Selected P1D1−P0D0 estimates (95% CI):

- map2 1× mean THT `-1.1026 s` `[-1.2508,-0.9492]`, P99 `-11.4297 s`
  `[-13.1169,-9.7246]`, backlog `-9,080.04` `[-10,185.38,-8,058.17]` bag-s;
- map2 1.75× mean THT `-154.531 s` `[-175.721,-135.061]`, backlog
  `-3,396,485.91` `[-4,030,983.87,-2,850,783.85]` bag-s;
- map2 2× missed `-1,264.9` `[-1,592.6,-936.485]`, tardiness mean `-20.7377 s`
  `[-29.651,-13.3073]`, backlog `-9,548,279.66`
  `[-10,893,681.25,-8,220,833.98]` bag-s;
- Nanning 1× mean THT `-12.4931 s` `[-13.9283,-11.2532]`, P95 `-40.8454 s`,
  P99 `-49.8752 s`, backlog `-286,422.905`
  `[-322,726.149,-254,789.454]` bag-s;
- Nanning 2× completion `+9,310.2` `[8,717.765,9,811.305]`, tardiness mean
  `-5,374.284 s` `[-5,942.673,-4,816.932]`, and corrected backlog
  `-307,161,166.735 bag-s` (`-27.242089%`)
  `[-339,857,630.541,-274,746,615.498]`.

The Nanning 2× boundary remains explicit: P95/P99 tardiness CIs cross zero and
maximum tardiness worsens `+2,555.10 s` `[1,027.27,4,083.66]`, 9/10 seeds.
Every formal 2× THT is N/A. Interaction is `INTERACTION_NOT_ESTIMATED`; random
fault is `BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE`.

## Safety, identity, and paper boundary

Final aggregates enforce registered artifact counts, completion,
`execution_integrity`, git/binary/manifest/workload identity, release/admission
cohort, and paired realization where applicable. This supports reproducibility,
not formal verification. Old G35 `cie_safety_audit.csv` is not used here.

The paper may claim strong two-map formal performance, conditional factorial
attribution, the local strict-descent effect, the 3-of-4 pure-potential fixed-
fault result, the mixed normalization stop, E2 compute-only equivalence, and
frozen-seed robustness with its negative tail boundary. It may not claim
unknown-map generalization, dynamic recovery, isolated J2 benefit, active P2
benefit, native HCA mechanism activation, random potential×dynamic interaction,
or randomized fault benefit. Blocked and N/M states are scientific boundaries,
not unfinished writing work.
