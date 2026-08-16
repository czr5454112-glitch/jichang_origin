# G30 3× own-source fixed-horizon capacity 报告

状态：`G30_3X_FIXED_HORIZON_PRIMARY_TARGET_MET`。这是固定 **85,518 件 raw bags / 130,809 segments**、epoch 8,260–98,259 的容量报告，不是 release-paired 或 timing-paired 声明。partial inputs 只产生诊断，不预写胜利。

S4 与 HCA 都允许在固定时域结束时只完成 85,518 总体的一部分；该固定分母 numerator 是业务容量结果。只要 case 已通过 portable aggregate 准入，这不表示 CPU 超时或安全失败。

## Table 5.2 — 四速度容量

| speed | S4/HCA completed | capacity verdict | timing status | HCA survivor secondary mean |
|---:|---:|---|---|---:|
| 1.5 | 85518 / 68047 | S4_WIN | NOT_APPLICABLE_BASELINE_INCOMPLETE | 6.2413 |
| 2.0 | 85518 / 58854 | S4_WIN | NOT_APPLICABLE_BASELINE_INCOMPLETE | 4.6533 |
| 2.5 | 85518 / 73081 | S4_WIN | NOT_APPLICABLE_BASELINE_INCOMPLETE | 3.8905 |
| 3.0 | 85518 / 69267 | S4_WIN | NOT_APPLICABLE_BASELINE_INCOMPLETE | 3.2490 |

HCA 未完成固定总体时，正式 timing 为 `NOT_APPLICABLE_BASELINE_INCOMPLETE`；完成者分布只作 `CENSORED_SECONDARY`，不参与胜负。

## Archived/reconstruction context（不驱动 3× primary）

`OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE` 只允许进入 Table 5.3/5.4 上下文；它不形成 fresh HCA timing verdict，也不驱动 3× primary。

Context losses=43，gaps=0；全部显式保留。

### Table 5.3

| metric | S4 3× | archived dispersed/HCA 1× | verdicts | status |
|---|---:|---:|---|---|
| min | 3.1334 | 3.56 / 3.13 | S4_WIN / PAPER_PRECISION_TIE | OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| mean | 7.3885 | 4.43 / 3.96 | BASELINE_WIN / BASELINE_WIN | OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| max | 47.1375 | 8.62 / 5.98 | BASELINE_WIN / BASELINE_WIN | OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |

### Table 5.4 — 12 个 legacy-variant reconstruction cells

| case | completed/85,518 | S4 mean | archived dynamic/static | S4 improvement / paper | verdicts (dynamic/static/improvement) | capacity/timing status |
|---|---:|---:|---:|---:|---|---|
| t5_4_bias_std_1p5_dev_10 | 85518 | 12.3241 | 6.45 / 6.59 | -87.0116 / 2.12 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_1p5_dev_20 | 85518 | 12.3699 | 6.67 / 6.86 | -80.3192 / 2.77 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_1p5_dev_30 | 85518 | 12.3465 | 6.91 / 7.11 | -73.6501 / 2.81 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_2_dev_10 | 85518 | 11.0362 | 4.92 / 5.07 | -117.6765 / 2.96 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_2_dev_20 | 85518 | 10.9743 | 5.16 / 5.36 | -104.7441 / 3.73 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_2_dev_30 | 85518 | 10.8861 | 5.42 / 5.62 | -93.7037 / 3.56 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_2p5_dev_10 | 85518 | 9.3105 | 3.99 / 4.19 | -122.2085 / 4.77 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_2p5_dev_20 | 85518 | 9.0920 | 4.25 / 4.46 | -103.8559 / 4.71 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_2p5_dev_30 | 85518 | 8.8344 | 4.49 / 4.72 | -87.1689 / 4.87 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_3_dev_10 | 85518 | 7.9975 | 3.39 / 3.56 | -124.6490 / 4.78 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_3_dev_20 | 85518 | 7.6933 | 3.51 / 3.72 | -106.8095 / 5.65 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |
| t5_4_bias_std_3_dev_30 | 85518 | 7.4757 | 3.64 / 3.87 | -93.1704 / 5.94 | BASELINE_WIN / BASELINE_WIN / BASELINE_WIN | MEASURED / OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE |

Table 5.4 仍是 `DESCRIPTIVE_UNPAIRED`；legacy 实现、随机流和逐 case 配对未恢复。

## Table 5.5 — 线路中断

**固定 85,518 总体容量比较；不是逐 segment fault-release 配对。**

S4/HCA 的 numerator 都可低于 85,518；这仍是完整固定时域业务 outcome，禁止用幸存者 timing 替代容量比较。

| scenario | S4/HCA completed | topology upper | verdict | status |
|---|---:|---:|---|---|
| single_1 | 85518 / 73369 | 85518 | S4_WIN | MEASURED |
| single_2 | 75939 / 67435 | 75939 | S4_WIN | MEASURED |
| single_3 | 85518 / 66674 | 85518 | S4_WIN | MEASURED |
| single_4 | 72029 / 38070 | 85518 | S4_WIN | MEASURED |
| single_5 | 75370 / 44042 | 85518 | S4_WIN | MEASURED |
| single_6 | 85518 / 66401 | 85518 | S4_WIN | MEASURED |
| single_7 | 85518 / 60556 | 85518 | S4_WIN | MEASURED |
| single_8 | 85518 / 50702 | 85518 | S4_WIN | MEASURED |
| pair_1_7 | 85518 / 61391 | 85518 | S4_WIN | MEASURED |
| pair_2_4 | 66339 / 37110 | 66339 | S4_WIN | MEASURED |
| pair_3_5 | 56742 / 44363 | 56742 | S4_WIN | MEASURED |
| pair_4_5 | 0 / 0 | 0 | TOPOLOGY_CEILING_TIE | MEASURED |
| pair_5_7 | NOT_MEASURED / NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| triple_2_4_6 | 22359 / 21564 | 22359 | S4_WIN | MEASURED |
| triple_3_5_8 | 18918 / 0 | 18918 | S4_WIN | MEASURED |
| triple_4_6_7 | 27705 / 16869 | 27705 | S4_WIN | MEASURED |

`pair_5_7` 固定为 `NOT_MEASURED`，且不进入 19 格 fresh primary。

## 联合判定

target_met=`true`；evidence_complete=`true`；primary wins/ties/losses/gaps=18/1/0/0。

运行时边界仍是 S4/J2/E2 + local FIFO + service-aware static local potential；每个转向点只决定下一跳，没有完整 A*、未来完整路线、HCA 全局预约表或 learning。
