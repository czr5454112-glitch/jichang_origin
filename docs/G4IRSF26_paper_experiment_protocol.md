# G4IRSF26 paper experiment and reporting protocol

## Purpose

G26 reruns the paper scenarios with the exact G24 lifecycle cohort and then reports the result beside the paper values. The reporting step only reads completed JSON artifacts; it never starts either simulator. Its JSON, CSV, and Markdown outputs preserve the provenance of every value and compute each S4 comparison from the value actually measured in that row.

Canonical cohort sizes are 43,603 segments and 28,506 raw bags. A missing, partial, unsafe, conflicting, or noncanonical run is reported as `NOT_MEASURED`; it is not silently filled from another run.

The repeat policy is fixed and intentionally small. Table 5.2 fresh HCA uses
two independent Java-process repeats at each speed; S4 uses one run per Table
5.2 cell. Table 5.4 uses one S4 run per cell. Table 5.5 uses one fresh HCA and
one S4 run for each executable scenario. Early censored or truncated probes
were superseded by their formal reruns and are not counted as additional
repeats.

## Evidence classes

| Label | Meaning |
|---|---|
| `ARCHIVED` | A value transcribed from paper Tables 5.2–5.5 and stored as a reporting constant. |
| `EXACT_FRESH` | A new HCA or S4 result on the canonical lifecycle cohort that passed the safety gate selected for its table and exposes the required metric. |
| `RECONSTRUCTED` | A Table 5.4 result formed from named exact S4 runs, or a registered Table 5.5 line-to-edge mapping. |
| `TOPOLOGY_PROVEN_RECONSTRUCTION` | A Table 5.5 primary success rate whose completed-bag count saturates a safety-admitted directed-topology upper bound; it is not an exact fixed-horizon result. |
| `PROTOCOL_CONTROLLED_RECONSTRUCTION` | A Table 5.5 S4-versus-fresh-HCA comparison on the same canonical population and fixed denominator, but not the same realized per-segment fault-release stream. |
| `NOT_MEASURED` | The required run or metric is absent, incomplete, unsafe, noncanonical, or inconsistent across repeats. |

Lower TTH is better in Tables 5.2–5.4. Higher success rate is better in Table 5.5. The reporter emits `S4_WIN`, `ORIGINAL_WIN`, or `TIE` only after both compared values are available; otherwise it emits `NOT_MEASURED`. No table-wide S4 outcome is assumed.

## Input contracts

### Fresh HCA

The HCA source is `scripts/eval/run_g4irsf24_fresh_hca.py`. A direct run supplies `run_01/metrics.json` with schema `g4irsf24.fresh_hca.metrics.v1`. Because speed and interruption identity are recorded in the sibling `run_01/run_status.json`, the reporter joins those fields while loading the metrics file. It can also read `fresh_hca_summary.json` and join each listed run to its status sidecar.

An HCA speed result is exact only when it is comparison-eligible and reports 43,603 released and completed segments plus 28,506 raw bags. An HCA interruption primary result instead requires a completed run that declares the canonical population (43,603 source segments and 28,506 raw bags) and an exact scenario fault schedule. The fault must start at epoch 8,260 on exactly the registered seed edges, contain no repair, and run through the 90,000-epoch window ending at 98,259; the recorded fault and repair event counts must agree. It does **not** require all 43,603 segments to have been released: an all-day interruption can make later source segments unreachable, and that shortfall is part of the primary result. The success numerator is `canonical_complete_raw_bag_count`; the denominator remains 28,506. This relaxed release gate applies only to Table 5.5 primary success. HCA timing rows retain the strict full-release/full-completion/comparison-eligible gate.

### Fresh S4

The S4 source is `scripts/eval/run_g4irsf26_paper_experiments.py`. Per-case files use schema `czr005.g4irsf26.paper_s4_case.v1`; the aggregate uses `czr005.g4irsf26.paper_s4_aggregate.v1`. The reporter accepts either form.

For Tables 5.2–5.4, an S4 result is exact only when the case status is `COMPLETE`, `protocol.exact_fresh_status` is `EXACT_G24_LIFECYCLE_ALIGNED`, the canonical cohort counts are present, `safety.strict_s4.pass` is true, and the required outcome metric exists. Table 5.5 uses the fixed-horizon or topology-proven admission described below. Conflicting admitted repeats are withheld as `NOT_MEASURED`.

## Table 5.2: speed

The four physical speeds are 1.5, 2.0, 2.5, and 3.0 m/s. Each speed produces min, mean, and max TTH rows in minutes.

| Speed (m/s) | Paper min | Paper mean | Paper max |
|---:|---:|---:|---:|
| 1.5 | 5.10 | 6.44 | 9.68 |
| 2.0 | 3.87 | 4.93 | 7.37 |
| 2.5 | 3.13 | 3.96 | 5.98 |
| 3.0 | 2.63 | 3.37 | 5.05 |

Fresh HCA and S4 values remain separate. Each S4 statistic is compared independently with the archived statistic and, when present, the exact fresh HCA statistic.

The matching fresh HCA release traces are published as `artifacts/datasets/g4irsf26_release_speed_1p5.csv`, `g4irsf26_release_speed_2p0.csv`, and `g4irsf26_release_speed_3p0.csv`; 2.5 m/s continues to use `artifacts/datasets/g4irsf24_release_compact.csv`. Each contains exactly 43,603 unique segment rows. Reusing the 2.5 m/s release trace at another speed is not admitted because the legacy one-segment-per-source-per-epoch rule changes the realized release sequence. The worker and reporter both reject a case whose recorded release source is not the registered file for its standard speed.

## Table 5.3: historical algorithms

Table 5.3 is an archived algorithm comparison at 2.5 m/s. Its constants are:

| Method | Unit | Min | Mean | Max |
|---|---|---:|---:|---:|
| Dispersed heuristic | minutes | 3.56 | 4.43 | 8.62 |
| IoT-DRPA HCA* | minutes | 3.13 | 3.96 | 5.98 |
| Paper improvement | percent | 12.10 | 10.60 | 30.60 |

The fresh 2.5 m/s S4 TTH statistics may be compared with both historical minute-based methods. Fresh HCA is attached only to the historical HCA* rows. The archived percentage row is never presented as a fresh timing measurement.

## Table 5.4: two-speed reconstruction

For standard speed `v` and deviation `d`, the degraded case uses physical edge speed `v * (1 - d/100)` while the heuristic continues to use standard speed `v`. The nominal reference is the exact Table 5.2 S4 case at `v`. A cell is `RECONSTRUCTED` only when both nominal and degraded cases are exact.

| Standard (m/s) | Deviation | Actual (m/s) | Paper dynamic | Paper static | Paper improvement (%) |
|---:|---:|---:|---:|---:|---:|
| 1.5 | 10% | 1.350 | 6.45 | 6.59 | 2.12 |
| 1.5 | 20% | 1.200 | 6.67 | 6.86 | 2.77 |
| 1.5 | 30% | 1.050 | 6.91 | 7.11 | 2.81 |
| 2.0 | 10% | 1.800 | 4.92 | 5.07 | 2.96 |
| 2.0 | 20% | 1.600 | 5.16 | 5.36 | 3.73 |
| 2.0 | 30% | 1.400 | 5.42 | 5.62 | 3.56 |
| 2.5 | 10% | 2.250 | 3.99 | 4.19 | 4.77 |
| 2.5 | 20% | 2.000 | 4.25 | 4.46 | 4.71 |
| 2.5 | 30% | 1.750 | 4.49 | 4.72 | 4.87 |
| 3.0 | 10% | 2.700 | 3.39 | 3.56 | 4.78 |
| 3.0 | 20% | 2.400 | 3.51 | 3.72 | 5.65 |
| 3.0 | 30% | 2.100 | 3.64 | 3.87 | 5.94 |

The S4 degraded mean is compared with the archived dynamic mean. The reporter also preserves the S4 nominal mean, standard speed, actual speed, deviation, and comparison reference so the reconstruction is auditable.

## Table 5.5: interruptions

Paper interruption identifiers are reconstructed to directed edges as follows:

| ID | Edge | Mapping basis |
|---:|---|---|
| 1 | 6 → 12 | 69-edge reconstruction |
| 2 | 8 → 11 | Strong mapping |
| 3 | 13 → 23 | Strong mapping |
| 4 | 24 → 27 | Strong mapping |
| 5 | 14 → 46 | Strong mapping |
| 6 | 43 → 15 | 69-edge reconstruction |
| 7 | 33 → 44 | 69-edge reconstruction |
| 8 | 31 → 32 | Strong mapping |

Line IDs 1, 6, and 7 are therefore claims about the protected 69-edge reconstruction, not direct identities from the original simulator.

There is one archived-source inconsistency that must remain scenario-local. The
workbook row corresponding to `pair_5_7` is stored in the sheet
`33-44,46-36` and its cached success formula is `13,939 / 28,506 =
0.4889847751`, while the other archived rows bind global line 5 to `14 → 46`
and global line 7 to `33 → 44`. The worksheet supplies only column-B
transport-time samples: `E4` is exactly `COUNT(B:B)`, and `E5` is
`E4/28506`. It does not retain task IDs, the fault application event, or the
complete simulator configuration. A fresh HCA run using the worksheet-label
edges `33 → 44, 46 → 36` completed only 8,013 canonical raw bags
(`0.2810987161`), exactly the same numerator produced by the global
`14 → 46, 33 → 44` reconstruction, and therefore did not reproduce the
cached 13,939 (`0.4889847751`). Consequently this row is
`ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED`: the worksheet edge label is
recorded as a case-specific archival clue, but neither edge interpretation is
admitted as a fresh Table 5.5 comparison. This does not remap global line 5 or
line 7. The row remains `NOT_MEASURED` for fresh HCA/S4 values and verdicts
until the missing source protocol can be recovered.

The archived scenarios are:

| Scenario | Line IDs | Affected conveyors | Paper success |
|---|---|---:|---:|
| `single_1` | 1 | 1 | 1.00 |
| `single_2` | 2 | 7 | 0.88 |
| `single_3` | 3 | 5 | 1.00 |
| `single_4` | 4 | 15 | 0.95 |
| `single_5` | 5 | 24 | 0.97 |
| `single_6` | 6 | 7 | 0.96 |
| `single_7` | 7 | 1 | 1.00 |
| `single_8` | 8 | 7 | 0.99 |
| `pair_1_7` | 1, 7 | 2 | 1.00 |
| `pair_2_4` | 2, 4 | 22 | 0.76 |
| `pair_3_5` | 3, 5 | 36 | 0.66 |
| `pair_4_5` | 4, 5 | 54 | 0.00 |
| `pair_5_7` | 5, 7 (archived worksheet label only: 33→44, 46→36; fresh protocol unresolved) | 12 | 0.48 |
| `triple_2_4_6` | 2, 4, 6 | 36 | 0.26 |
| `triple_3_5_8` | 3, 5, 8 | 51 | 0.05 |
| `triple_4_6_7` | 4, 6, 7 | 30 | 0.26 |

An admitted fixed-horizon S4 interruption artifact has status `COMPLETE_FIXED_HORIZON`, `safety.admission.pass=true`, and admission mode `TABLE_5_5_FIXED_HORIZON_SAFETY`. Its requested runtime limit is 98,259 seconds, derived from the fresh Java full window `8260 + 90000 - 1`; the repair lies after this limit. The artifact must also state that business and safety axes are separate and that a business failure is not itself a safety failure. The legacy strict-completion view remains available for reference and may be false when bags legitimately fail to finish within the fixed horizon.

The final ceiling for an unsaturated fault run is 60,000,000 events. It is not part of the routing policy or success definition. A case that reaches this ceiling before the fixed horizon is censored and cannot supply a completion rate unless the separately computed topology upper bound has already been saturated. Earlier cases that reached the fixed horizon below 20,000,000 events are unchanged; the previously censored `pair_4_5` result also remains valid because its independently computed upper bound and observed completion count are both zero.

A severe interruption may instead produce `COMPLETE_TOPOLOGY_SATURATED` with admission mode `TABLE_5_5_TOPOLOGY_SATURATION_EVIDENCE`. The reporter accepts its primary success rate only when `safety.topology_saturation_fault.pass=true`, the topology-reachable raw-bag upper bound equals the completed raw-bag count, and the artifact explicitly limits its claim to `TABLE_5_5_PRIMARY_SUCCESS_RATE_ONLY`. This value is labeled `TOPOLOGY_PROVEN_RECONSTRUCTION`, never `EXACT_FRESH`. Its TTH distribution and both deadline views are censored and remain `NOT_MEASURED`.

The primary fresh success rate is `completed raw bags / 28,506`. Two secondary views are retained without replacing that primary definition:

- `finish <= STD`
- literal `finish <= STD - 2700`

Only the primary rate is used for the S4-versus-paper verdict.

The Table 5.5 S4-versus-fresh-HCA verdict is a
`PROTOCOL_CONTROLLED_RECONSTRUCTION`, not an exact release-paired comparison.
Both arms use the same canonical input population and the fixed 28,506-bag
denominator. S4 replays the registered 2.5 m/s no-fault HCA release trace,
whereas a faulted Java/HCA run realizes its own release stream and may release
fewer than 43,603 segments because the interrupted source cannot admit later
work. The primary rates may therefore be compared under the declared protocol,
but the report must not describe them as paired by per-segment fault-release
epoch.

## Reporting command and outputs

Example using only the compact evidence paths committed in the repository:

```powershell
python scripts/eval/run_g4irsf26_reporting.py `
  --hca-input outputs/runtime/g4irsf26_hca_evidence `
  --s4-input outputs/runtime/g4irsf26_paper_experiments
```

These are repository-relative, clone-reusable inputs. The reporter discovers
the nested HCA campaign summaries and the per-case S4 JSON without requiring
the ignored local `build/` directories.

Default outputs are:

- `outputs/tables/g4irsf26_reporting.json`: structured tables, summary counts, input paths, and evidence policy.
- `outputs/tables/g4irsf26_reporting.csv`: 49 normalized rows (12 speed statistics, 9 historical-algorithm statistics, 12 two-speed cases, and 16 interruption cases).
- `outputs/reports/g4irsf26_reporting.md`: compact human-readable comparison.

The reporter can be run before every experiment is complete. Available admitted rows are emitted with their evidence class and every unavailable row remains explicitly `NOT_MEASURED`.

The runner aggregate treats `pair_5_7` as an explicitly archived-only,
not-executed case because its source protocol is unresolved. When all other 31
executable cases are admitted, the aggregate status is
`COMPLETE_WITH_ARCHIVED_ONLY_GAP`; this means 31/31 executable cases completed
with one declared archival gap, not 32/32 fresh experiments.
