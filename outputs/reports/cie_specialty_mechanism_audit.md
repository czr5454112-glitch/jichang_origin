# CIE specialty mechanism audit

Date: 2026-09-02
Status: `FINAL_MECHANISM_AUDIT_CLOSED`

## Scope and non-negotiable reporting rules

This audit assigns each specialty mechanism a narrow, evidence-backed role. It
does not rerank complete algorithms or turn every internal switch into a paper
contribution.

- All formal 2× cross-algorithm THT is `N/A`; survivor timing is never used.
- Corrected fixed-horizon backlog is authoritative. Legacy incomplete-tail
  percentages are excluded.
- `SERVICE_X2` uses the 1× population and increases service pressure; it is not
  workload 2×.
- The random matrix is frozen by the committed runner and manifest: five
  scenarios, ten fixed paired seeds, and identical perturbation realization in
  the two arms of each seed.
- The old G35 `outputs/tables/cie_safety_audit.csv` is not current evidence.
  This round relies on `execution_integrity` and strict aggregate gates.
- Uncollected activation quantiles/correlations/hotspots are
  `NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`.

## Final status table

| Mechanism | Final status | Evidence-supported role | Forbidden interpretation |
|---|---|---|---|
| J2/M3 destination arbitration | `BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT` | Current activation-only diagnostic | Isolated current cross-map benefit |
| Strict local potential descent | `TARGETED_LOCAL_BENEFIT_NOT_GENERAL` | Local Nanning `single_3` fixed-fault benefit | General recovery or loop-avoidance gain |
| P2 local buffer | `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY` | Dormant tested interface | Current performance/safety contribution |
| E2 event hotpath | `COMPUTE_ONLY_ROLE` | Strictly equivalent event suppression | Physical capacity improvement |
| Surviving-graph service-aware DLP | `PURE_POTENTIAL_3_OF_4_BENEFIT_1_TIE` | Conditional persistent fixed-fault benefit | Dynamic recovery or universal fault gain |
| Service-rate normalization | `MIXED_NO_GENERAL_GAIN_STOP` | Negative cross-map/control result | General reusable normalization gain |
| No-Q/I but calendar | `MIXED_NO_GENERAL_GAIN_STOP` | Negative cross-map/control result | Proof that Q/I is always redundant |
| Random P1D1−P0D0 contrast | `COMPLETE_FROZEN_PAIRED_SEEDS` | Paired robustness on five registered scenarios | Unknown-map generalization |
| Potential×dynamic random interaction | `INTERACTION_NOT_ESTIMATED` | None; only combined contrast was run | Separate main or interaction effects |
| Random fault treatment | `BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE` | Explicit stopped boundary | Randomized fault robustness claim |
| Native HCA mechanism counters | `BLOCKED_NATIVE_HCA_MECHANISM_COUNTERS_NOT_INSTRUMENTED` | None | HCA component activation inferred from outcomes |

## 1. J2/M3 destination merge arbitration

Current G31 records pre-commit ordering changes, especially at high load, but
`PRE_COMMIT_ORDER_MUTATION` is not a final executed-action change. The stable
1× C_FIFO contrast is identical on Nanning and changes map2 mean by only
`-0.007410721 s`; it changes merge policy and timing together. The historical
G18 map2 2× J2-versus-JIT-FIFO signal uses a different release/timing contract
and remains historical context.

The current interface cannot vary the merge rule while holding its timing
contract fixed. Exact contrast status is therefore
`BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT`. No new mode, scorer, guard, or
parameter is justified solely to remove this blocker.

## 2. Strict local potential descent

Stable same-HCA 1× removal is exactly neutral on both maps. In registered
persistent fixed faults, map2 `single_4`, map2 `pair_2_4`, and Nanning
`pair_3_5` are neutral in completion/deadline outcomes. Nanning `single_3`
changes completion `28,491 -> 28,506`, on-time `25,617 -> 26,018`, missed
`2,889 -> 2,488`, tardiness sum `-31.145%`, and maximum decisions `512 -> 53`.

The corrected backlog result is
`100,322,141.572124 -> 95,914,523.385383 bag-s` (`-4.393465%`). Nanning
`pair_3_5` has a small corrected difference of `-28,077.317 bag-s`
(`-0.003129%`), not an exact backlog tie. Because the `single_3` OFF arm leaves
15 bags incomplete, paired full-population mean/P95/P99/max is N/M.

Decision: retain only the local registered result and stop generalization.

## 3. P2 bounded-local coordination

All ten formal activation cells report zero applicability, activation,
prepare, validate, commit, and rollback because `local_queue_capacity=0`
denotes unbounded capacity. A historical cap-32 sensitivity cohort is not a
physical airport-capacity source and did not produce a latency benefit.

Final status: `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`. P2 may return only
after an engineering-grounded capacity set is frozen; it is not pending work
and contributes no current performance claim.

## 4. E2 event-hotpath suppression

E2 v2 completes an exact current-protocol OFF/ON audit on map2 and Nanning 1×.
For every segment, the complete untruncated move/hold sequence and terminal
state match; release, admission, and completion times match at `1e-9`.

| Map | Events OFF | Events ON | Change |
|---|---:|---:|---:|
| map2 | 4,752,689 | 3,997,648 | -15.8866% |
| Nanning | 8,645,838 | 7,087,605 | -18.0229% |

The physical causal total is unchanged. `event_queue_peak` is N/M and the
single complete-trace wall/CPU/RSS values are descriptive only. Final role:
`COMPUTE_ONLY_ROLE`. E2 does not increase physical service capacity.

## 5. Surviving-graph service-aware DLP under fixed faults

Each of four registered pairs holds binary, workload, release, reference
request, native admission cohort, edge filtering, and unreachable recognition
fixed; the surviving-graph DLP artifact is the sole treatment.

| Cell | Completed OFF→ON | Tardiness effect | Corrected backlog OFF→ON | Corrected effect |
|---|---:|---:|---:|---:|
| map2 `single_4` | 10,248→28,506 | -100.000% | 1,015,984,862.649766→70,452,656.819033 | -93.065580% |
| map2 `pair_2_4` | 5,453→22,113 | -71.333% | 1,287,277,282.705624→419,703,509.738353 | -67.396029% |
| Nanning `single_3` | 17,559→28,506 | -98.357% | 643,431,201.021053→95,914,523.385383 | -85.093274% |
| Nanning `pair_3_5` | 12,186→12,186 | 0% | exact tie | 0% |

Final status: `PURE_POTENTIAL_3_OF_4_BENEFIT_1_TIE`. This is limited to
fixed-onset persistent 1× faults; it does not establish dynamic detection,
notification, repair, or recovery.

## 6. Service normalization and No-Q/I controls

The study has 12/12 runs and 4/4 identity-matched groups across
`RAW_COUNT_AS_SECONDS`, `SERVICE_RATE_NORMALIZED`, and
`NO_QI_BUT_CALENDAR`. `SERVICE_X2` preserves the 1× task population and changes
service pressure only.

Normalization ties map2 real service and improves map2 under pressure, but
worsens Nanning real service and does not complete the Nanning pressure cell's
full population. No-Q/I also reverses direction by map, condition, and metric.
Incomplete full-population timing remains N/M.

Decision: `MIXED_NO_GENERAL_GAIN_STOP`; stop both directions without adding a
replacement score or condition.

## 7. Activation and admissibility audit

Activation identifies declared decision opportunities, not causal benefit.
The requested activation quantiles, correlations, and hotspot breakdowns were
not collected because they would not alter any test decision; status is
`NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`.

The targeted ablation runner executed all 12 mandatory cells, but only 9 pass
the complete integrity/admissibility gate. Nanning minus-Q, minus-I, and
minus-H+Q+I fail `merge_grant_active_bijection` and do not enter paper effect
estimates. Optional WC is dormant/missing, explicitly reported, and not
converted to zero.

## 8. Frozen paired random robustness

The committed runner and frozen manifest register map2 1.00×/1.75×/2.00× and
Nanning 1.00×/2.00×, ten seeds, arrival `uniform[-5,5]`, node-service lognormal
`sigma=0.05`, and identical arm-paired realizations. All 100/100 artifacts pass;
all five scenarios are `COMPLETE_FROZEN_PAIRED_SEEDS`, failure rate is zero,
and intervals use 10,000 paired bootstrap resamples.

Key P1D1−P0D0 results (95% CI): map2 1× mean THT `-1.1026 s`
`[-1.2508,-0.9492]` and P99 `-11.4297 s` `[-13.1169,-9.7246]`; map2 1.75×
mean `-154.531 s` `[-175.721,-135.061]`; map2 2× missed `-1,264.9`
`[-1,592.6,-936.485]`; Nanning 1× mean `-12.4931 s`
`[-13.9283,-11.2532]`; Nanning 2× completion `+9,310.2`
`[8,717.765,9,811.305]` and corrected backlog `-307,161,166.735 bag-s`
(`-27.242089%`) `[-339,857,630.541,-274,746,615.498]`.

Negative boundary: Nanning 2× max tardiness worsens `+2,555.10 s`
`[1,027.27,4,083.66]` in 9/10 seeds, while P95/P99 CIs cross zero. Every
formal 2× THT stays N/A. The matrix estimates only P1D1−P0D0, so interaction is
`INTERACTION_NOT_ESTIMATED`. Random fault is
`BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE`.

## Publication decision

Retain: strong formal G31/HCA outcomes, conditional factorial evidence, the
localized strict-descent result, the 3-of-4 pure-DLP fixed-fault result, E2's
compute-only equivalence, the mixed normalization stop, and frozen-seed random
robustness with its Nanning tail boundary.

Do not claim: isolated J2 benefit, active P2 benefit, native HCA mechanism
counters, random potential×dynamic interaction, randomized fault recovery,
unknown-map generalization, or formal safety certification. Current safety
rests on execution-integrity and aggregate gates; old G35 safety CSV is not
used. The explicit blockers close those directions without another patch.
