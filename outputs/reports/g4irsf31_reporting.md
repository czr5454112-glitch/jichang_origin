# G31 原地图与南宁机场跨地图验证报告

状态：`G31_PRIMARY_CAPACITY_MATRIX_READY`。

南宁：`fresh_target_met=true`。
跨地图：`cross_map_target_met=true`。

stable/fault capacity 使用相同 scheduled population 和固定时域，但各自进行 source admission，并非逐 segment release-paired；只有 paired 章节比较 same-HCA-release timing。

Table 5.4 是 `NON_EXACT` 上下文，不驱动上述两个 exact target；map2 证据参与跨地图判定，但不改写南宁自身的 fresh 判定。

## 容量量化摘要

| map | scale | group | strict W/T/strict L | S4-HCA completed | avg percentage points |
|---|---:|---|---:|---:|---:|
| nanning | 1× | stable | 1/3/0 | 1 | 0.00 |
| nanning | 1× | fault | 13/3/0 | 244123 | 53.52 |
| nanning | 2× | stable | 4/0/0 | 71375 | 31.30 |
| nanning | 2× | fault | 16/0/0 | 531355 | 58.25 |
| map2 | 1× | stable | 0/4/0 | 0 | 0.00 |
| map2 | 1× | fault | 6/9/0 | 10002 | 2.34 |
| map2 | 2× | stable | 4/0/0 | 488 | 0.21 |
| map2 | 2× | fault | 13/2/0 | 47658 | 5.57 |

跨地图容量合计：`57W / 21T / 0L`；累计 S4-HCA 完成件数 `905002`；平均 `26.07` 个百分点。

容量先按固定总体比较；时延只使用 same-HCA-release 且双方全人口完成的证据。

## 固定时域容量（8 个稳定速度 + 32 个线路中断）

Verdicts：`{"FULL_POPULATION_CEILING_TIE": 6, "S4_WIN": 34}`。

| case | scale | speed | fault | S4/HCA completed | denominator | verdict |
|---|---:|---:|---|---:|---:|---|
| t5_2_nanning_1x_speed_1p5 | 1× | 1.5 | - | 28506 / 28505 | 28506 | S4_WIN |
| t5_2_nanning_1x_speed_2 | 1× | 2.0 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_nanning_1x_speed_2p5 | 1× | 2.5 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_nanning_1x_speed_3 | 1× | 3.0 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_nanning_2x_speed_1p5 | 2× | 1.5 | - | 57012 / 39060 | 57012 | S4_WIN |
| t5_2_nanning_2x_speed_2 | 2× | 2.0 | - | 57012 / 39272 | 57012 | S4_WIN |
| t5_2_nanning_2x_speed_2p5 | 2× | 2.5 | - | 57012 / 39063 | 57012 | S4_WIN |
| t5_2_nanning_2x_speed_3 | 2× | 3.0 | - | 57012 / 39278 | 57012 | S4_WIN |
| t5_5_nanning_1x_fault_single_1 | 1× | 2.5 | single_1 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_nanning_1x_fault_single_2 | 1× | 2.5 | single_2 | 25886 / 596 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_single_3 | 1× | 2.5 | single_3 | 28506 / 28504 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_single_4 | 1× | 2.5 | single_4 | 27813 / 2091 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_single_5 | 1× | 2.5 | single_5 | 23669 / 560 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_single_6 | 1× | 2.5 | single_6 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_nanning_1x_fault_single_7 | 1× | 2.5 | single_7 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_nanning_1x_fault_single_8 | 1× | 2.5 | single_8 | 27839 / 2183 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_pair_1_7 | 1× | 2.5 | pair_1_7 | 28506 / 28505 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_pair_2_4 | 1× | 2.5 | pair_2_4 | 25193 / 477 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_pair_3_5 | 1× | 2.5 | pair_3_5 | 12186 / 483 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_pair_4_5 | 1× | 2.5 | pair_4_5 | 22976 / 231 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_pair_5_7 | 1× | 2.5 | pair_5_7 | 23669 / 560 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_triple_2_4_6 | 1× | 2.5 | triple_2_4_6 | 25193 / 477 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_triple_3_5_8 | 1× | 2.5 | triple_3_5_8 | 12115 / 483 | 28506 | S4_WIN |
| t5_5_nanning_1x_fault_triple_4_6_7 | 1× | 2.5 | triple_4_6_7 | 27813 / 2091 | 28506 | S4_WIN |
| t5_5_nanning_2x_fault_single_1 | 2× | 2.5 | single_1 | 41043 / 37810 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_2 | 2× | 2.5 | single_2 | 49488 / 1015 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_3 | 2× | 2.5 | single_3 | 38618 / 31709 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_4 | 2× | 2.5 | single_4 | 55626 / 3609 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_5 | 2× | 2.5 | single_5 | 47338 / 1054 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_6 | 2× | 2.5 | single_6 | 55934 / 39659 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_7 | 2× | 2.5 | single_7 | 57012 / 39046 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_single_8 | 2× | 2.5 | single_8 | 55678 / 4251 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_pair_1_7 | 2× | 2.5 | pair_1_7 | 41069 / 37840 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_pair_2_4 | 2× | 2.5 | pair_2_4 | 48531 / 775 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_pair_3_5 | 2× | 2.5 | pair_3_5 | 24372 / 915 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_pair_4_5 | 2× | 2.5 | pair_4_5 | 45952 / 378 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_pair_5_7 | 2× | 2.5 | pair_5_7 | 47338 / 1054 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_triple_2_4_6 | 2× | 2.5 | triple_2_4_6 | 48531 / 775 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_triple_3_5_8 | 2× | 2.5 | triple_3_5_8 | 24230 / 915 | 57012 | S4_WIN |
| t5_5_nanning_2x_fault_triple_4_6_7 | 2× | 2.5 | triple_4_6_7 | 55011 / 3611 | 57012 | S4_WIN |

## Same-HCA-release 全人口时延

1.5 m/s 因 corrected HCA 未完成全人口而严格 N/A；2.0、2.5、3.0 m/s 各比较 min/mean/P95/P99/max。min 差值不超过 1 ms 只记物理语义分辨率平局。

Verdicts：`{"PHYSICAL_SEMANTICS_RESOLUTION_TIE": 1, "S4_LOWER": 14}`。

| speed | metric | S4/HCA seconds | verdict |
|---:|---|---:|---|
| 2.0 | min | 59.001 / 59.000 | PHYSICAL_SEMANTICS_RESOLUTION_TIE |
| 2.0 | mean | 342.991 / 448.053 | S4_LOWER |
| 2.0 | p95 | 573.148 / 769.000 | S4_LOWER |
| 2.0 | p99 | 640.887 / 922.950 | S4_LOWER |
| 2.0 | max | 811.093 / 4042.000 | S4_LOWER |
| 2.5 | min | 48.401 / 49.000 | S4_LOWER |
| 2.5 | mean | 282.934 / 374.080 | S4_LOWER |
| 2.5 | p95 | 475.339 / 653.000 | S4_LOWER |
| 2.5 | p99 | 553.466 / 785.000 | S4_LOWER |
| 2.5 | max | 812.698 / 2851.000 | S4_LOWER |
| 3.0 | min | 41.334 / 42.000 | S4_LOWER |
| 3.0 | mean | 243.135 / 319.608 | S4_LOWER |
| 3.0 | p95 | 413.380 / 559.000 | S4_LOWER |
| 3.0 | p99 | 510.293 / 677.950 | S4_LOWER |
| 3.0 | max | 660.063 / 4051.000 | S4_LOWER |

## 原地图 map2 固定时域容量（8 个稳定速度 + 30 个可测线路中断）

状态：`COMPLETE_MAP2_CROSS_ALGORITHM_EVIDENCE`；Verdicts：`{"FULL_POPULATION_CEILING_TIE": 9, "S4_WIN": 23, "TOPOLOGY_UPPER_TIE": 6}`。

`pair_5_7` 的两个尺度均因既有线路标签冲突记 NM，不计入 38 个可测 cell。

| case | scale | speed | fault | S4/HCA completed | denominator | verdict |
|---|---:|---:|---|---:|---:|---|
| t5_2_map2_1x_speed_1p5 | 1× | 1.5 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_map2_1x_speed_2 | 1× | 2.0 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_map2_1x_speed_2p5 | 1× | 2.5 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_map2_1x_speed_3 | 1× | 3.0 | - | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_2_map2_2x_speed_1p5 | 2× | 1.5 | - | 57012 / 56822 | 57012 | S4_WIN |
| t5_2_map2_2x_speed_2 | 2× | 2.0 | - | 57012 / 56992 | 57012 | S4_WIN |
| t5_2_map2_2x_speed_2p5 | 2× | 2.5 | - | 57012 / 56917 | 57012 | S4_WIN |
| t5_2_map2_2x_speed_3 | 2× | 3.0 | - | 57012 / 56829 | 57012 | S4_WIN |
| t5_5_map2_1x_fault_single_1 | 1× | 2.5 | single_1 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_map2_1x_fault_single_2 | 1× | 2.5 | single_2 | 25313 / 25313 | 28506 | TOPOLOGY_UPPER_TIE |
| t5_5_map2_1x_fault_single_3 | 1× | 2.5 | single_3 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_map2_1x_fault_single_4 | 1× | 2.5 | single_4 | 28506 / 28471 | 28506 | S4_WIN |
| t5_5_map2_1x_fault_single_5 | 1× | 2.5 | single_5 | 28506 / 28484 | 28506 | S4_WIN |
| t5_5_map2_1x_fault_single_6 | 1× | 2.5 | single_6 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_map2_1x_fault_single_7 | 1× | 2.5 | single_7 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_map2_1x_fault_single_8 | 1× | 2.5 | single_8 | 28506 / 28497 | 28506 | S4_WIN |
| t5_5_map2_1x_fault_pair_1_7 | 1× | 2.5 | pair_1_7 | 28506 / 28506 | 28506 | FULL_POPULATION_CEILING_TIE |
| t5_5_map2_1x_fault_pair_2_4 | 1× | 2.5 | pair_2_4 | 22113 / 22083 | 28506 | S4_WIN |
| t5_5_map2_1x_fault_pair_3_5 | 1× | 2.5 | pair_3_5 | 18914 / 18914 | 28506 | TOPOLOGY_UPPER_TIE |
| t5_5_map2_1x_fault_pair_4_5 | 1× | 2.5 | pair_4_5 | 0 / 0 | 28506 | TOPOLOGY_UPPER_TIE |
| t5_5_map2_1x_fault_triple_2_4_6 | 1× | 2.5 | triple_2_4_6 | 7453 / 7453 | 28506 | TOPOLOGY_UPPER_TIE |
| t5_5_map2_1x_fault_triple_3_5_8 | 1× | 2.5 | triple_3_5_8 | 6306 / 0 | 28506 | S4_WIN |
| t5_5_map2_1x_fault_triple_4_6_7 | 1× | 2.5 | triple_4_6_7 | 9235 / 5635 | 28506 | S4_WIN |
| t5_5_map2_2x_fault_single_1 | 2× | 2.5 | single_1 | 57012 / 56894 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_2 | 2× | 2.5 | single_2 | 50626 / 50583 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_3 | 2× | 2.5 | single_3 | 57012 / 57006 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_4 | 2× | 2.5 | single_4 | 57012 / 42592 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_5 | 2× | 2.5 | single_5 | 57012 / 50520 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_6 | 2× | 2.5 | single_6 | 57012 / 56817 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_7 | 2× | 2.5 | single_7 | 57012 / 56932 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_single_8 | 2× | 2.5 | single_8 | 57012 / 55349 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_pair_1_7 | 2× | 2.5 | pair_1_7 | 57012 / 56938 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_pair_2_4 | 2× | 2.5 | pair_2_4 | 44226 / 39566 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_pair_3_5 | 2× | 2.5 | pair_3_5 | 37828 / 37751 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_pair_4_5 | 2× | 2.5 | pair_4_5 | 0 / 0 | 57012 | TOPOLOGY_UPPER_TIE |
| t5_5_map2_2x_fault_triple_2_4_6 | 2× | 2.5 | triple_2_4_6 | 14906 / 14906 | 57012 | TOPOLOGY_UPPER_TIE |
| t5_5_map2_2x_fault_triple_3_5_8 | 2× | 2.5 | triple_3_5_8 | 12612 / 0 | 57012 | S4_WIN |
| t5_5_map2_2x_fault_triple_4_6_7 | 2× | 2.5 | triple_4_6_7 | 18470 / 11252 | 57012 | S4_WIN |

## 原地图 map2 same-HCA-release 全人口时延

1× 四种速度各比较 min/mean/P95/P99/max；min 的绝对差不超过 1 ms 记物理语义分辨率平局。2× HCA 未完成全人口，因此四种速度的时延均严格 N/A。

Verdicts：`{"PHYSICAL_SEMANTICS_RESOLUTION_TIE": 3, "S4_LOWER": 17}`。

| speed | metric | S4/HCA seconds | verdict |
|---:|---|---:|---|
| 1.5 | min | 305.334 / 306.000 | S4_LOWER |
| 1.5 | mean | 342.966 / 386.549 | S4_LOWER |
| 1.5 | p95 | 403.335 / 486.000 | S4_LOWER |
| 1.5 | p99 | 407.335 / 536.000 | S4_LOWER |
| 1.5 | max | 433.335 / 612.000 | S4_LOWER |
| 2.0 | min | 232.001 / 232.000 | PHYSICAL_SEMANTICS_RESOLUTION_TIE |
| 2.0 | mean | 259.402 / 297.727 | S4_LOWER |
| 2.0 | p95 | 304.502 / 373.000 | S4_LOWER |
| 2.0 | p99 | 307.502 / 417.000 | S4_LOWER |
| 2.0 | max | 318.502 / 771.000 | S4_LOWER |
| 2.5 | min | 188.001 / 188.000 | PHYSICAL_SEMANTICS_RESOLUTION_TIE |
| 2.5 | mean | 210.553 / 238.000 | S4_LOWER |
| 2.5 | p95 | 247.202 / 300.000 | S4_LOWER |
| 2.5 | p99 | 254.049 / 332.000 | S4_LOWER |
| 2.5 | max | 279.202 / 383.000 | S4_LOWER |
| 3.0 | min | 158.001 / 158.000 | PHYSICAL_SEMANTICS_RESOLUTION_TIE |
| 3.0 | mean | 177.002 / 202.786 | S4_LOWER |
| 3.0 | p95 | 207.669 / 257.000 | S4_LOWER |
| 3.0 | p99 | 211.414 / 295.950 | S4_LOWER |
| 3.0 | max | 228.335 / 372.000 | S4_LOWER |

## 原地图 map2 Table 5.4 NON_EXACT 上下文

状态：`NON_EXACT_CONTEXT_AVAILABLE`；protocol=`LEGACY_VARIANT_RECONSTRUCTION_NON_EXACT`；admitted=24/24；all_safety_pass=true；只报告 S4 自身描述性结果，不把 unperturbed HCA 当作 matched arm，也不生成跨算法胜负。

| case | scale | speed | label | U(0,k s) | S4 completed/denominator | percent | timing status |
|---|---:|---:|---:|---:|---:|---:|---|
| t5_4_map2_1x_std_1p5_dev_10 | 1× | 1.5 | 10% | 1.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_1p5_dev_20 | 1× | 1.5 | 20% | 2.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_1p5_dev_30 | 1× | 1.5 | 30% | 3.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_2_dev_10 | 1× | 2.0 | 10% | 1.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_2_dev_20 | 1× | 2.0 | 20% | 2.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_2_dev_30 | 1× | 2.0 | 30% | 3.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_2p5_dev_10 | 1× | 2.5 | 10% | 1.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_2p5_dev_20 | 1× | 2.5 | 20% | 2.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_2p5_dev_30 | 1× | 2.5 | 30% | 3.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_3_dev_10 | 1× | 3.0 | 10% | 1.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_3_dev_20 | 1× | 3.0 | 20% | 2.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_1x_std_3_dev_30 | 1× | 3.0 | 30% | 3.0 | 28506/28506 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_1p5_dev_10 | 2× | 1.5 | 10% | 1.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_1p5_dev_20 | 2× | 1.5 | 20% | 2.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_1p5_dev_30 | 2× | 1.5 | 30% | 3.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_2_dev_10 | 2× | 2.0 | 10% | 1.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_2_dev_20 | 2× | 2.0 | 20% | 2.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_2_dev_30 | 2× | 2.0 | 30% | 3.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_2p5_dev_10 | 2× | 2.5 | 10% | 1.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_2p5_dev_20 | 2× | 2.5 | 20% | 2.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_2p5_dev_30 | 2× | 2.5 | 30% | 3.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_3_dev_10 | 2× | 3.0 | 10% | 1.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_3_dev_20 | 2× | 3.0 | 20% | 2.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |
| t5_4_map2_2x_std_3_dev_30 | 2× | 3.0 | 30% | 3.0 | 57012/57012 | 100.00 | S4_FULL_POPULATION_DESCRIPTIVE |

## 证据边界

- Table 5.4 bias：`NON_EXACT_CONTEXT_AVAILABLE_BOTH_MAPS`，仅上下文，不产生跨算法胜负。
- map2：`COMPLETE_MAP2_CROSS_ALGORITHM_EVIDENCE`；只有 38 个容量 cell 与 4 个 1× paired artifact 全部齐备后才形成跨地图结论。
- 运行策略固定为 S4/J2/E2 + 节点局部 FIFO + service-aware static potential；每个转向点只决定下一条边，不使用运行时完整 A* 或 learning。
