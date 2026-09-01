# CIE / S4 1× same-HCA ablation report

## Decision

`STOP_AT_1X_NO_ATTRIBUTABLE_DUAL_MAP_SIGNAL`.

Nine independent configurations were evaluated on the full 1× same-HCA raw-bag population on both map2 and Nanning. Every one of the 18 executions completed `28,506/28,506` raw bags (`43,603/43,603` segments), reported `completion_rate = 1.0`, passed its recorded execution-integrity gate, and used the same native binary SHA-256:

```text
884f36f0ceebdb0fd56924fd00fe5c8a1ebef56eb05fac4f53d66306de647155
```

No independent variant produced a clear, attributable improvement on both maps. The descriptive changes around `0.5%` are not labelled statistically significant: these are deterministic single-seed, single-population contrasts without replication intervals, and their signs or affected quantiles do not reproduce across maps. Under the preregistered stopping rule, the ablation matrix therefore does not expand to 2×.

## Evidence and calculation boundary

- Result source: [`outputs/runtime/cie_ablations/same_hca/`](../runtime/cie_ablations/same_hca/). Only each variant's `map2_1x.json` and `nanning_1x.json` is used for measured outcomes.
- Preregistered protocol: [`experiments/cie_baseline_ablation_manifest.yaml`](../../experiments/cie_baseline_ablation_manifest.yaml).
- Variant definitions and structural equivalences: [`configs/ablations/s4_core.yaml`](../../configs/ablations/s4_core.yaml).
- Executable runner: [`scripts/eval/run_g4irsf35_full_population.py`](../../scripts/eval/run_g4irsf35_full_population.py).

The latency subject is the full-population `paper_network_from_admission` distribution in each JSON. No survivor subset or common-completed cohort is used. For metric `m`, every table entry is recomputed as

```text
delta_percent = 100 * (variant_m / same_map_A4_m - 1)
```

Thus negative latency deltas are better. The same-map A4 denominators are:

| Map | A4 mean (s) | A4 P95 (s) | A4 P99 (s) | A4 max (s) |
|---|---:|---:|---:|---:|
| map2 | 210.553057 | 247.202000 | 254.049500 | 279.202000 |
| Nanning | 282.933063 | 475.338500 | 553.465900 | 812.698000 |

## Full-population results relative to A4

### map2 1× same-HCA

| Variant | Completed raw bags | Mean Δ% | P95 Δ% | P99 Δ% | Max Δ% |
|---|---:|---:|---:|---:|---:|
| A0 | 28,506/28,506 | +0.1019% | +0.0000% | +2.0281% | +4.7994% |
| A1 | 28,506/28,506 | +0.0988% | +0.0000% | +2.0281% | +4.7994% |
| A2 | 28,506/28,506 | -0.0007% | +0.0000% | -0.0187% | +0.0000% |
| A4 | 28,506/28,506 | +0.0000% | +0.0000% | +0.0000% | +0.0000% |
| B1 | 28,506/28,506 | +0.0029% | +0.0000% | +0.0010% | +2.3639% |
| B2 | 28,506/28,506 | +0.0988% | +0.0000% | +2.0281% | +4.7994% |
| B5 | 28,506/28,506 | +0.0000% | +0.0000% | +0.0000% | +0.0000% |
| C_FIFO | 28,506/28,506 | -0.0035% | +0.0000% | -0.0187% | -0.3582% |
| F1 | 28,506/28,506 | +0.0000% | +0.0000% | +0.0000% | +0.0000% |

### Nanning 1× same-HCA

| Variant | Completed raw bags | Mean Δ% | P95 Δ% | P99 Δ% | Max Δ% |
|---|---:|---:|---:|---:|---:|
| A0 | 28,506/28,506 | -0.4274% | -0.4600% | -0.1982% | -0.5061% |
| A1 | 28,506/28,506 | -0.4196% | -0.4524% | -0.1213% | -0.5061% |
| A2 | 28,506/28,506 | +0.0710% | +0.0498% | +0.0296% | +0.0000% |
| A4 | 28,506/28,506 | +0.0000% | +0.0000% | +0.0000% | +0.0000% |
| B1 | 28,506/28,506 | -0.0272% | -0.0779% | -0.0086% | -0.1846% |
| B2 | 28,506/28,506 | -0.5203% | -0.5388% | -0.2377% | -0.5061% |
| B5 | 28,506/28,506 | +0.0000% | +0.0000% | +0.0000% | +0.0000% |
| C_FIFO | 28,506/28,506 | +0.0000% | +0.0000% | +0.0000% | +0.0000% |
| F1 | 28,506/28,506 | +0.3225% | +0.4208% | -0.0921% | -0.4762% |

## Structural reuse, not duplicate evidence

The frozen ablation config declares the following executable equivalences. They were not rerun and must not be counted as additional experiments or independent confirmations:

| Requested label | Reused execution |
|---|---|
| A3 H+Q+I+WC | A2 H+Q+I |
| B3 full minus WC | A4 full |
| B4 full minus WS | A2 H+Q+I |

These identities are protocol/config facts, not post-result claims of four additional successful runs.

## Mechanism questions

| Question | Evidence | Answer |
|---|---|---|
| Does queue count `Q` help? | A0→A1 is nearly unchanged; removing Q in B1 is slightly worse in map2 but slightly better in Nanning. | No reusable cross-map contribution is identified. Q may alter a few tail decisions, but its sign is map-dependent. |
| Does scheduled incoming `I` help? | B2 (full minus I) is worse on map2 (`+2.0281%` P99, `+4.7994%` max) but better on Nanning (`-0.5203%` mean, `-0.5388%` P95). | I is the clearest topology-dependent term, not a generally beneficial one. |
| Does successor-service wait `WS` help? | B4 reuses A2. Relative to A4, A2 is effectively tied/slightly better on map2 and slightly worse on Nanning. | No clear dual-map WS gain. The WC structural equivalences also mean this matrix supplies no separate active WC effect. |
| Does strict potential descent help? | B5 (strict descent removed) matches A4 exactly on all four reported latency metrics on both maps; its event and decision counts also match A4 in the source JSON. | No observable contribution in these stable 1× cells. This is a zero measured effect, not proof that the guard is irrelevant under faults or other loads. |
| What does the neutral-FIFO coordination contrast show? | C_FIFO is identical to A4 on Nanning and only descriptively better on map2 (`-0.0035%` mean, `-0.3582%` max). | No positive evidence for the full J2/M3 coordination package in these cells. C_FIFO changes merge rule and timing together, so it cannot isolate M3 or aging. |
| Is the raw-count-as-seconds dimensional choice the bottleneck? | F1 service-rate normalization is identical on map2; on Nanning it worsens mean/P95 while improving P99/max slightly. | No. Normalization changes the trade-off on Nanning but does not yield a coherent cross-map improvement. |

## Explicitly unevaluated or partially supported items

| Item | Status | Reason |
|---|---|---|
| C2 M3 aging-only contrast | `NOT_EVALUATED` | C_FIFO changes both merge rule and timing; it is not structurally equivalent to an aging-only switch. No separate C2 implementation was added. |
| D0/D1 fault-filter contrast | `NOT_EVALUATED` | Stable cells contain no active fault, so the D mechanism does not trigger. The manifest forbids treating a no-fault identity as fault evidence. |
| P2 depth/capacity contrast | `NOT_EVALUATED` | The main runtime has `local_queue_capacity = 0` and the preregistered P2 trigger count is zero; only finite-buffer motifs could test this mechanism. |
| C3 | `NOT_EVALUATED` | It was not implemented because it would mix the requested coordination contrast with E4 event/merge semantics and would not isolate a route contribution. |
| E2 routing contribution | `NOT_EVALUATED` | E2 is common to these arms; none of the permitted result JSON files is an E2-off route comparison. No routing benefit is assigned to E2. |
| E2 computation audit | `PARTIALLY_SUPPORTED` | The manifest permits only a predeclared diagnostic because event count and wall time are compute outcomes even when physical traces are expected to match. That diagnostic is outside this result set, so this report supports the audit boundary, not a formal E2 performance estimate. |
| 2× ablation expansion | `NOT_RUN_PREREGISTERED_STOP_RULE` | The config requires an attributable dual-map 1× signal first; none is present. |

## Reproduction commands

Run from the repository root with the exact binary above. The following PowerShell reproduces the nine unique configurations into a new output root and therefore does not overwrite the evidence used by this report. The runner's canonical workload and same-HCA roots may be overridden with its `--nanning-*` and `--map2-*` options when reproducing on another host.

```powershell
$py = 'C:\PROGRAMING\python3.11.9\python.exe'
$bin = 'build_cie_ablation\python\Release\czr005_cpp.cp311-win_amd64.pyd'
$outRoot = 'outputs\runtime\cie_ablations_reproduction\same_hca'
$variants = @(
    @('a0_h_only', 'a0_h_only'),
    @('a1_h_q', 'a1_h_q'),
    @('a2_h_q_i', 'a2_h_q_i'),
    @('a4_full', 'none'),
    @('b1_full_minus_q', 'b1_full_minus_q'),
    @('b2_full_minus_i', 'b2_full_minus_i'),
    @('b5_full_minus_strict_descent', 'b5_full_minus_strict_descent'),
    @('f1_service_rate_normalized', 'f1_service_rate_normalized')
)

foreach ($map in @('map2', 'nanning')) {
    foreach ($variant in $variants) {
        & $py scripts/eval/run_g4irsf35_full_population.py `
            --map $map --scale 1 --arm g31 `
            --s4-ablation $variant[1] --release-mode same_hca `
            --binary $bin `
            --output "$outRoot\$($variant[0])\$($map)_1x.json"
    }
    & $py scripts/eval/run_g4irsf35_full_population.py `
        --map $map --scale 1 --arm g31 `
        --coordination neutral_fifo --s4-ablation none `
        --release-mode same_hca --binary $bin `
        --output "$outRoot\c_fifo\$($map)_1x.json"
}
```

The report tables can then be reproduced directly from each JSON's
`paper_subjects.full_population_raw_bag_timing.metrics_seconds.paper_network_from_admission` object using the formula above and its same-map `a4_full` JSON as denominator.
