# G28 原论文实验完成报告

## 联合结论

状态：`MEASURABLE_TARGET_MET_WITH_EXPLICIT_LEGACY_PROTOCOL_GAPS`。采用保持简单的 `S4/J2/E2 + local FIFO + service-aware static local potential`；持久、启动前已知故障继续使用既有 local goal scalar。

当前可测指标均达到或超过比较基线，但不能把缺失协议说成 exact：Table 5.4 仍是非配对描述性重构，Table 5.5 的 `pair_5_7` 仍不可测。

## Table 5.2 — 四种速度

| 速度 | G28 min/mean/max (min) | fresh HCA min/mean/max | verdict min/mean/max | P95 | P99 |
|---:|---|---|---|---:|---:|
| 1.5 | 5.0889 / 5.7162 / 7.2223 | 5.1000 / 6.4199 / 9.6333 | G28_WIN / G28_WIN / G28_WIN | 6.7223 | 6.7890 |
| 2.0 | 3.8667 / 4.3234 / 5.3084 | 3.8667 / 4.9274 / 7.3667 | RESOLUTION_BOUND_TIE / G28_WIN / G28_WIN | 5.0751 | 5.1251 |
| 2.5 | 3.1334 / 3.5092 / 4.6534 | 3.1333 / 3.9452 / 5.9500 | RESOLUTION_BOUND_TIE / G28_WIN / G28_WIN | 4.1201 | 4.2334 |
| 3.0 | 2.6334 / 2.9499 / 3.8056 | 2.6333 / 3.3546 / 5.0500 | RESOLUTION_BOUND_TIE / G28_WIN / G28_WIN | 3.4612 | 3.5112 |

3.0 m/s 最小值为 **158.002 s**；fresh HCA 为 158.000 s。差 0.002 s，判定 `RESOLUTION_BOUND_TIE`，不改计时定义。

## Table 5.3 — 2.5 m/s 算法比较

| 指标 | G28 | paper dispersed | G28 vs dispersed | paper HCA | G28 vs HCA | G28改善率@论文精度 | 论文改善率 | 改善率判定 | archived raw diagnostic |
|---|---:|---:|---|---:|---|---:|---:|---|---:|
| min | 3.1334 | 3.56 | G28_WIN | 3.13 | PAPER_RESOLUTION_TIE | 12.1% | 12.1% | PAPER_RESOLUTION_TIE | 11.8603% |
| mean | 3.5092 | 4.43 | G28_WIN | 3.96 | G28_WIN | 20.8% | 10.6% | G28_WIN | 20.7230% |
| max | 4.6534 | 8.62 | G28_WIN | 5.98 | G28_WIN | 46.1% | 30.6% | G28_WIN | 46.0162% |

`archived raw diagnostic` 来自恢复出的原始分散式输出，只作诊断；正式判定使用论文显示精度，二者不混用。

## Table 5.4 — 观测偏差重构

| case | S4 | archived dynamic | archived static | improvement vs dynamic | G28 improvement vs static | paper improvement | improvement verdict | dynamic verdict | static verdict | evidence |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| t5_4_bias_std_1p5_dev_10 | 5.8459 | 6.45 | 6.59 | 9.366% | 11.292% | 2.12% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_1p5_dev_20 | 5.9511 | 6.67 | 6.86 | 10.778% | 13.249% | 2.77% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_1p5_dev_30 | 6.0533 | 6.91 | 7.11 | 12.397% | 14.862% | 2.81% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_2_dev_10 | 4.4543 | 4.92 | 5.07 | 9.466% | 12.144% | 2.96% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_2_dev_20 | 4.5592 | 5.16 | 5.36 | 11.643% | 14.940% | 3.73% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_2_dev_30 | 4.6631 | 5.42 | 5.62 | 13.966% | 17.028% | 3.56% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_2p5_dev_10 | 3.6333 | 3.99 | 4.19 | 8.939% | 13.285% | 4.77% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_2p5_dev_20 | 3.7396 | 4.25 | 4.46 | 12.010% | 16.153% | 4.71% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_2p5_dev_30 | 3.8412 | 4.49 | 4.72 | 14.451% | 18.620% | 4.87% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_3_dev_10 | 3.0731 | 3.39 | 3.56 | 9.347% | 13.676% | 4.78% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_3_dev_20 | 3.1794 | 3.51 | 3.72 | 9.419% | 14.533% | 5.65% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |
| t5_4_bias_std_3_dev_30 | 3.2822 | 3.64 | 3.87 | 9.830% | 15.189% | 5.94% | G28_WIN | G28_WIN | G28_WIN | DESCRIPTIVE_UNPAIRED |

这 12 项均为 `DESCRIPTIVE_UNPAIRED`，`exact_legacy_variant_recovered=false`；未恢复 legacy 实现、随机流/seed 与逐 case 配对。

## Table 5.5 — 线路中断

15 个可测场景全部达到拓扑上限；对 fresh HCA 为 **6 胜 / 9 个拓扑上限平 / 0 负**。`pair_5_7` 为 `NOT_MEASURED`。

该结果使用同一 canonical population 和固定 28,506 分母，但不是逐 segment release paired。6 胜/9 个拓扑上限平是描述性 completed-bag numerator comparison，不能解释为严格配对因果效果。

## 架构边界

- 这是决策层去中心化：每个转向点只选择一个下一跳动作；证据来自单进程模拟器，不声称已物理分布式部署。
- 每次决策为 `O(outdegree)`；运行时不调用完整 A*，不生成未来完整路线，不维护 HCA 全局预约表。
- G28 只替换静态启发矩阵为 service-aware local potential；没有启用 learning。
