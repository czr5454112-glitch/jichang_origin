# CIE baseline replacement decision

## Decision

`HISTORICAL_ANCHOR_WITH_SECONDARY_EXECUTABLE_DIAGNOSTICS` — with conditions.

The common-executor CIE-DH adaptation is no longer eligible to stand in the
main table as “the Feng CIE-DH baseline.” The replacement is deliberately not
a single synthetic row. It is a two-layer evidence package:

1. `FENG_PAPER_CIE_DH_HISTORICAL_MEASURED` remains the primary numerical
   reference for the original method at map2 1×.
2. `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION` supplies an executable old-Java
   interface for mechanism, sensitivity, load and map-port experiments, but
   is labelled `SEMANTICALLY_PARTIAL_RECONSTRUCTION` in every table.

`FENG_SOURCE_EXACT_CIE_DH` remains `SOURCE_NOT_RECOVERED`.
`CIE_DH_COMMON_EXECUTOR_ADAPTED` remains a secondary route-policy isolation
control. It is not deleted, because its negative and mixed results are useful;
it is moved out of the historical primary-baseline role.

## Why the executable does not replace the historical measurement

Both rows use the recovered full 28,506-bag, 43,603-segment shared-D Table 5.3
observation contract, but they are not the same scientific object:

| method | min | mean | P95 | P99 | max | status |
|---|---:|---:|---:|---:|---:|---|
| historical measured CIE-DH (s) | 213.3 | 265.592131 | 336.9 | 384.595 | 517.2 | primary historical evidence |
| executable reconstruction (s) | 206.4 | 238.702287 | 285.2 | 300.8 | 326.0 | semantically partial |
| executable relative difference | -3.235% | -10.124% | -15.346% | -21.788% | -36.968% | materially optimistic |

The paper's printed Table 5.3 level is the ordering anchor: HCA reports
3.13/3.96/5.98 min for min/mean/max, while CIE-DH reports
3.56/4.43/8.62 min. HCA is lower on all three. That historical ordering is
exactly the role of CIE-DH as the weaker baseline used to demonstrate HCA in
Feng's paper. Any strong 2× or cross-map result from the partial executable is
a new-state-machine extrapolation; it is not assigned back to the original
CIE-DH method.

The executable completes the full population and activates stopped/hold
mechanics, but its mean and especially its tail remain materially faster than
the workbook. The missing source does not identify the exact node handoff,
penalties or same-tick update semantics. Numerical proximity cannot upgrade
the artifact; conversely, no artificial delay is added to force a fit. This
protects the historical baseline from being assigned either an invented weak
implementation or an invented exact identity.

## Eligibility by comparison layer

| layer | eligible CIE-DH evidence | interpretation |
|---|---|---|
| original historical map2 1× | `FENG_PAPER_CIE_DH_HISTORICAL_MEASURED` | descriptive historical system result; not rerunnable here |
| old-Java executable map2 load curve | `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION` | end-to-end partial-reconstruction system comparison |
| Nanning port and paired random loads | `FENG_PAPER_ENV_CIE_DH_NANNING_PORTED` | ported semantically-partial secondary diagnostic; never back-attributed to Feng's paper |
| shared-executor route isolation | `CIE_DH_COMMON_EXECUTOR_ADAPTED` | secondary mechanism diagnostic only |
| source-exact claims | none | `SOURCE_NOT_RECOVERED` |

The main paper table uses `FENG_PAPER_CIE_DH_HISTORICAL_MEASURED` as the sole
performance anchor for the original CIE-DH, alongside identity-separated HCA
and G31 evidence. The partial old-Java reconstruction and its Nanning port
belong in a separately labelled executable-diagnostic table. No table may
merge historical and executable values, pool different binaries, or form an
unconditional rank across native and common-executor cohorts.

## Current result judgement

### Supported

- The historical Table 5.3 observation formula and full population are
  recovered exactly from the workbook.
- The old-Java CIE-DH reconstruction is executable and complete at map2 1×.
- Its formal identity is semantically partial, with a stable historical-shape
  mismatch across the frozen coefficient envelope.
- G31 has a clear, protocol-matched main result relative to native HCA on both
  original maps: lower full-population 1× mean/tails and higher fixed-horizon
  2× completion.
- The common-executor adaptation is not the Feng historical baseline.
- The final-identity deterministic map2 critical curve is complete. G31 has
  lower full-population mean/P95/P99/max than the executable partial CIE-DH at
  every eligible 1.00--1.75× cell, while both complete 57,012 bags at 2× and
  CIE-DH has higher on-time rate (98.89% versus 53.03%) and lower total backlog
  AUC (1.563e8 versus 2.935e8 bag-s). This is a mixed system result.

### Mixed or negative evidence that must remain visible

- The executable CIE-DH is faster than the original measured row; it is not a
  source-exact numerical reproduction.
- Existing adapted cohorts contain cells where CIE-DH or Tarău beats G31 on a
  subset of metrics. Different cohorts cannot be pooled to erase those cells.
- The random 2×2 component factorial has topology- and load-dependent main
  effects and interactions; it does not establish independent universal
  gains for every G31 component.
- At Nanning 2×, P1D1 completes more bags in all 10 frozen seeds but worsens
  maximum tardiness by 2,555.10 s on average, CI [1,027.27, 4,083.66], in
  9/10 seeds. The 20 validated maximum-bag replays are all DIRECT with zero
  source wait and junction queues accounting for 100% of local wait. The
  worst-one-percent populations are dispersed over 25 P0D0 and 32 P1D1 ODs
  (top-five shares 48.4% and 43.4%). The supported diagnosis is therefore
  `EXPECTED_CAPACITY_TRADEOFF_WITH_JUNCTION_WAIT_DOMINATED_TAIL`, not a source
  admission shift or a single-OD artifact.
- The targeted ablation has 12/12 required valid cells, but Q/I/ws do not have
  uniform cross-map standalone effects; wc remains dormant because activation
  was zero.

### Not identified or not applicable

- The source-exact CIE-DH implementation and coefficients are not recovered.
- All 20 Nanning 2× detail replays pass the binary, workload, paired-realization,
  completion, maximum-tardiness and denominator gates, but the first causal
  policy divergence remains `NOT_IDENTIFIED_NO_TRACE_REPLAY`: the frozen runs
  did not retain decision/hold traces and bag-result replays cannot identify
  priority starvation, route oscillation, a particular node/scorer or the
  first policy divergence.
- J2/M3 separation is an interface result, not a performance estimate.
- All formal 2× population THT values are `N/A`; no survivor timing may be
  substituted.

## G31 claim decision

`CONDITIONAL_NOT_UNIVERSAL`.

The paper may state that G31 clearly leads native HCA on the completed original
formal subjects. It may state a G31–CIE-DH direction only for a named evidence
layer, map, load, metric and completed protocol. It may not state that G31 has
beaten the unavailable original implementation, that G31 is strongest among
all baselines, or that random experiments prove universal external dominance.

The executable reconstruction is intentionally not weakened to help G31. Its
optimistic historical mismatch makes it a conservative executable comparator
for G31, while the original workbook remains the authoritative record of
Feng's reported CIE-DH level.

## External campaign gate

The deterministic map2 critical curve now passes the final Java source/class
identity (`99bf...14d8`/`d611...0286`) and is accepted with the mixed result
above. The 2026-09-05 shutdown checkpoint contains `166/180` normalized cells:
all map2 and Nanning HCA/G31 cells, plus `16/30` Nanning CIE-DH-port cells. Its
gate remains 180/180 strict normalized cells
(2 maps × 3 loads × 10 seeds × 3 methods): 60 byte/SHA-matched map2 HCA/G31
cells may be strictly reused and renormalized, 60 final-identity DH cells are
rerun, and all 90 Nanning native cells are newly executed. Until
`cie_external_baseline_robustness.md` and its CSV pass the final Java identity,
workload, denominator, per-cell 10/10 seeds and 180/180 matrix gates, no
randomized external G31-versus-reconstructed-DH ranking is promoted. The
interim report and exact shutdown boundary are recorded in
`cie_external_baseline_checkpoint_20260905.md`; earlier smoke and
superseded-source rows are audit history only.

FINAL_BASELINE_DECISION: HISTORICAL_ANCHOR_WITH_SECONDARY_EXECUTABLE_DIAGNOSTICS

FINAL_G31_CIE_DH_CLAIM: CONDITIONAL_NOT_UNIVERSAL
