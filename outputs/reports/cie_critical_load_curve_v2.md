# CIE map2 critical-load curve v2

All five cells are the unjittered, whole-flight, schedule-preserving map2 ladder. HCA and the Feng paper-environment DH reconstruction consume the same raw bytes; G31 preserves that raw population, topology, destinations and deadlines, while its canonical `pass_time` alone is aligned by segment ID to the corresponding native HCA run_01 release epoch. This is the frozen original-paper `same_hca` G31 timing protocol, not a policy or parameter change. Every result uses the absolute 98,259 s horizon and the full raw-bag denominator.
The frozen formal 1x reference is `C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_ablations\same_hca\a4_full\map2_1x.json` (SHA-256 `e145815e9ab7efa3513e5a6e3dab94ccd41e67e213a33d623f710eaea942a13d`); the rerun reproduces its G31 network mean at 210.553057356 s versus 210.553057356 s (absolute delta 0.000000000000 s).
The G31 cells use final repaired native binary SHA-256 `b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5`.
The DH cells use reconstruction source SHA-256 `99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8` and compiled-class aggregate `d611967f0433dfc08f67d92c89e9b13dcb5b8ac5ace3d3abec9c098dba360286`.

## Critical-load summary

| Method | First incomplete load | Completion-rate AUC | Capacity-deficit-rate area | 2x completed / population | 2x on-time rate | 2x source backlog end / peak | 2x source AUC (bag-s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FENG_NATIVE_HCA | 1.75 | 0.999651 | 0.000349 | 56917 / 57012 | 0.5268 | 0 / 7403 | 283212498.3 |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | N/A | 1.000000 | 0.000000 | 57012 / 57012 | 0.9889 | 0 / 4135 | 132445291.4 |
| G31_S4_NATIVE_SYSTEM | N/A | 1.000000 | 0.000000 | 57012 / 57012 | 0.5303 | 0 / 7401 | 283090930.4 |

## Complete curve

| Method | Load | Completion | On-time | Capacity deficit | Source backlog end / peak | Source / network / total backlog AUC | t95 (s) | t99 (s) | Timing status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| FENG_NATIVE_HCA | 1.00 | 1.0000 | 1.0000 | 0 | 0 / 2193 | 66900502.7 / 5894683.0 / 72791092.2 | 67287.2 | 71130.2 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_NATIVE_HCA | 1.25 | 1.0000 | 0.9814 | 0 | 0 / 3100 | 90257592.3 / 7447756.0 / 97701186.3 | 66965.2 | 71235.2 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_NATIVE_HCA | 1.50 | 1.0000 | 0.9083 | 0 | 0 / 3947 | 117692609.9 / 9071184.0 / 126759610.0 | 67583.2 | 71626.2 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_NATIVE_HCA | 1.75 | 0.9994 | 0.8131 | 28 | 0 / 5570 | 167513834.3 / 12493949.0 / 180003927.6 | 67987.2 | 71921.2 | NOT_MEASURED_FULL_POPULATION_INCOMPLETE |
| FENG_NATIVE_HCA | 2.00 | 0.9983 | 0.5268 | 95 | 0 / 7403 | 283212498.3 / 17595470.0 / 300804701.4 | 69639.2 | 72788.2 | FORMAL_2X_TIMING_NA_BY_PROTOCOL |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.00 | 1.0000 | 1.0000 | 0 | 0 / 2195 | 64955298.8 / 5849708.8 / 70805007.6 | 67313.4 | 71140.6 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.25 | 1.0000 | 1.0000 | 0 | 0 / 2793 | 81460390.7 / 7758925.4 / 89219316.1 | 66961.6 | 71261.8 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.50 | 1.0000 | 1.0000 | 0 | 0 / 3212 | 98174250.8 / 10844880.0 / 109019130.8 | 67600.4 | 71602.8 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.75 | 1.0000 | 0.9988 | 0 | 0 / 3671 | 114718859.0 / 15556396.8 / 130275255.8 | 67896.6 | 71728.8 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 2.00 | 1.0000 | 0.9889 | 0 | 0 / 4135 | 132445291.4 / 23853312.6 / 156298604.0 | 67675.8 | 71609.8 | FORMAL_2X_TIMING_NA_BY_PROTOCOL |
| G31_S4_NATIVE_SYSTEM | 1.00 | 1.0000 | 1.0000 | 0 | 0 / 2193 | 66873538.2 / 5252372.1 / 72125910.3 | 67287.2 | 71121.6 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| G31_S4_NATIVE_SYSTEM | 1.25 | 1.0000 | 0.9828 | 0 | 0 / 3099 | 90214332.3 / 6571928.5 / 96786260.7 | 66934.4 | 71234.8 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| G31_S4_NATIVE_SYSTEM | 1.50 | 1.0000 | 0.9095 | 0 | 0 / 3944 | 117630847.0 / 7916658.4 / 125547505.4 | 67576.2 | 71580.2 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| G31_S4_NATIVE_SYSTEM | 1.75 | 1.0000 | 0.8149 | 0 | 0 / 5566 | 167424826.6 / 9158282.2 / 176583108.8 | 67875.8 | 71704.6 | FULL_POPULATION_PROCESSED_ATTEMPT_TIMING |
| G31_S4_NATIVE_SYSTEM | 2.00 | 1.0000 | 0.5303 | 0 | 0 / 7401 | 283090930.4 / 10360712.5 / 293451642.9 | 69481.4 | 72611.6 | FORMAL_2X_TIMING_NA_BY_PROTOCOL |

## Shared processed-attempt timing under the original-business protocol

| Method | Load | Mean (s) | P95 (s) | P99 (s) | Max (s) |
|---|---:|---:|---:|---:|---:|
| FENG_NATIVE_HCA | 1.00 | 236.7102 | 299.0000 | 330.0000 | 357.0000 |
| FENG_NATIVE_HCA | 1.25 | 239.2847 | 299.0000 | 331.0000 | 359.0000 |
| FENG_NATIVE_HCA | 1.50 | 242.1369 | 302.0000 | 332.0000 | 359.0000 |
| FENG_NATIVE_HCA | 1.75 | N/A | N/A | N/A | N/A |
| FENG_NATIVE_HCA | 2.00 | N/A | N/A | N/A | N/A |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.00 | 241.5789 | 294.4000 | 321.2000 | 373.4000 |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.25 | 269.6307 | 482.2000 | 674.1360 | 831.4000 |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.50 | 370.9618 | 1360.1400 | 1632.8760 | 1845.0000 |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 1.75 | 549.8232 | 2457.1600 | 2988.3440 | 3245.4000 |
| FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION | 2.00 | N/A | N/A | N/A | N/A |
| G31_S4_NATIVE_SYSTEM | 1.00 | 210.5531 | 247.2020 | 254.0495 | 279.2020 |
| G31_S4_NATIVE_SYSTEM | 1.25 | 211.1071 | 247.6020 | 261.6020 | 329.8020 |
| G31_S4_NATIVE_SYSTEM | 1.50 | 211.5715 | 247.8020 | 271.4020 | 334.8020 |
| G31_S4_NATIVE_SYSTEM | 1.75 | 212.4369 | 248.8020 | 290.8020 | 368.6020 |
| G31_S4_NATIVE_SYSTEM | 2.00 | N/A | N/A | N/A | N/A |

## Interpretation contract

- `capacity_deficit_raw_bags` is the frozen raw population minus completed raw bags at 98,259 s.
- Completion-rate AUC is trapezoidal integration over the complete frozen 1.00–2.00 load ladder. Capacity-deficit-rate area integrates `1 - completion_rate` over that same interval; no cell is selected or omitted.
- Source-backlog AUC integrates every not-yet-fully-admitted bag to its admission or the fixed horizon; incomplete tails are not dropped.
- `t95`/`t99` are elapsed from the first raw arrival and are N/A when the full-denominator target is not reached.
- 2x THT is always N/A. At lower loads THT is published only for a method whose entire raw population completed; no survivor or common-success cohort is used.
- G31 `execution_canonical_sha256` identifies the audited same-HCA-release projection. Its `canonical_sha256` remains the shared base workload identity; the alignment audit proves every non-`pass_time` field is byte-value identical by segment.
- DH remains the explicitly labelled paper-environment reconstruction with undisclosed original coefficients, not recovered source-exact Feng DH.
