# G29 fresh 2× primary target 报告

状态：`G29_FRESH_2X_PRIMARY_TARGET_MET`。这是 **fresh 2× fixed-horizon primary target**，不是“原论文所有科目 exact 全胜”的声明。固定总体为 **57,012 件原始行李 / 87,206 个 segment**；缺失 primary 证据保留为 `NOT_MEASURED`。

固定窗口从 epoch **8,260** 开始，共 **90,000 epochs**，最后有效 epoch / native `max_simulation_time` 为 **98,259**；native 31 格汇总及每格 request/summary 时域回显必须通过准入。当前 native 固定时域汇总准入：`true`。

2× 流量由原航班时刻流的中间航班加密产生，不是复制已经展开的 segment。稳定速度与偏差重构要求完整 exact HCA release；线路中断只比较同一 57,012 分母的业务完成结果，**不是逐 segment 故障 release 配对**。

## Table 5.2 — 四种速度

| speed | completed S4/HCA | capacity verdict | S4 min/mean/P95/P99/max | full-pop HCA min/mean/P95/P99/max | HCA censored secondary min/mean/P95/P99/max | time verdict min/mean/max | timing status |
|---:|---:|---|---|---|---|---|---|
| 1.5 | 57012 / 56822 | S4_WIN | 5.0889 / 5.7251 / 6.7445 / 6.8820 / 8.4723 | NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED | 5.1000 / 6.6554 / 8.1167 / 8.9167 / 9.6333 | NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE | NOT_APPLICABLE_BASELINE_INCOMPLETE |
| 2.0 | 57012 / 56992 | S4_WIN | 3.8667 / 4.3224 / 5.0751 / 5.1126 / 5.6792 | NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED | 3.8833 / 5.0328 / 6.1833 / 6.7833 / 7.3667 | NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE | NOT_APPLICABLE_BASELINE_INCOMPLETE |
| 2.5 | 57012 / 56917 | S4_WIN | 3.1334 / 3.5445 / 4.1467 / 5.0293 / 6.8967 | NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED | 3.1333 / 4.1050 / 5.0333 / 5.5167 / 5.9833 | NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE | NOT_APPLICABLE_BASELINE_INCOMPLETE |
| 3.0 | 57012 / 56829 | S4_WIN | 2.6334 / 2.9702 / 3.4612 / 3.9772 / 5.5223 | NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED / NOT_MEASURED | 2.6333 / 3.4680 / 4.2667 / 4.9453 / 5.0667 | NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE / NOT_APPLICABLE_BASELINE_INCOMPLETE | NOT_APPLICABLE_BASELINE_INCOMPLETE |

若 HCA 在固定窗口内已释放完整 57,012 件但没有全部完成，而 S4 完成 100%，该速度由容量结果形成完整主决策；fresh timing 标为 `NOT_APPLICABLE_BASELINE_INCOMPLETE`。HCA 完成幸存者分布只登记为 `CENSORED_SECONDARY`，不参与时间胜负。S4 自身完整总体 timing 仍可用于 Table 5.3/5.4 的归档上下文比较。

`computational_throughput_diagnostic` 是实现/运行时诊断，不等同于模拟时钟中的业务吞吐；不进入正式胜负。

## Archived/reconstruction context（不驱动 fresh 2× primary）

Context 当前明确记录 **3 个 loss**、**0 个 gap/NOT_MEASURED**；这些结果不隐藏，也不冒充 fresh 2× 配对证据。

## Context A — Table 5.3 archived 1× 算法比较

| metric | S4 2× | fresh HCA 2× verdict | HCA censored secondary | archived dispersed 1× | archived HCA 1× | context verdicts |
|---|---:|---|---:|---:|---:|---|
| min | 3.1334 | NOT_APPLICABLE_BASELINE_INCOMPLETE | 3.1333 | 3.56 | 3.13 | S4_WIN / PAPER_PRECISION_TIE / improvement BASELINE_WIN |
| mean | 3.5445 | NOT_APPLICABLE_BASELINE_INCOMPLETE | 4.1050 | 4.43 | 3.96 | S4_WIN / S4_WIN / improvement S4_WIN |
| max | 6.8967 | NOT_APPLICABLE_BASELINE_INCOMPLETE | 5.9833 | 8.62 | 5.98 | S4_WIN / BASELINE_WIN / improvement BASELINE_WIN |

归档分散式/HCA 数字属于 1× 论文上下文；与 2× S4 的关系按论文显示精度登记，但不是同流量因果配对。

## Context B — Table 5.4 observation-bias reconstruction

| case | S4 2× mean | archived dynamic/static 1× | verdict dynamic/static/improvement | status |
|---|---:|---|---|---|
| t5_4_bias_std_1p5_dev_10 | 5.9760 | 6.45 / 6.59 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_1p5_dev_20 | 6.0272 | 6.67 / 6.86 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_1p5_dev_30 | 6.1113 | 6.91 / 7.11 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_2_dev_10 | 4.4608 | 4.92 / 5.07 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_2_dev_20 | 4.5656 | 5.16 / 5.36 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_2_dev_30 | 4.6659 | 5.42 / 5.62 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_2p5_dev_10 | 3.7152 | 3.99 / 4.19 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_2p5_dev_20 | 3.7852 | 4.25 / 4.46 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_2p5_dev_30 | 3.8805 | 4.49 / 4.72 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_3_dev_10 | 3.1046 | 3.39 / 3.56 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_3_dev_20 | 3.2055 | 3.51 / 3.72 | S4_WIN / S4_WIN / S4_WIN | MEASURED |
| t5_4_bias_std_3_dev_30 | 3.3047 | 3.64 / 3.87 | S4_WIN / S4_WIN / S4_WIN | MEASURED |

Table 5.4 是 deterministic observation-bias reconstruction；原 legacy variant、随机流和逐 case 配对未恢复，因此 `exact_legacy_variant_recovered=false`。
Table 5.3、Table 5.4 及所有 archived 1× 比较仅统计为 unpaired descriptive context；其胜负不会驱动 2× fresh `target_met`。

## Table 5.5 — 线路中断

**醒目边界：这是固定 57,012 人口的容量描述比较，不是逐 segment release 配对，也不是逐行李 timing 因果比较。**

| scenario | S4/HCA completed (of 57,012) | topology upper | S4 vs HCA | S4 vs paper rate | status |
|---|---:|---:|---|---|---|
| single_1 | 57012 / 56894 | 57012 | S4_WIN | 100_PERCENT_CEILING_TIE | MEASURED |
| single_2 | 50626 / 50583 | 50626 | S4_WIN | S4_WIN | MEASURED |
| single_3 | 57012 / 57006 | 57012 | S4_WIN | 100_PERCENT_CEILING_TIE | MEASURED |
| single_4 | 57012 / 42592 | 57012 | S4_WIN | S4_WIN | MEASURED |
| single_5 | 57012 / 50520 | 57012 | S4_WIN | S4_WIN | MEASURED |
| single_6 | 57012 / 56817 | 57012 | S4_WIN | S4_WIN | MEASURED |
| single_7 | 57012 / 56932 | 57012 | S4_WIN | 100_PERCENT_CEILING_TIE | MEASURED |
| single_8 | 57012 / 55349 | 57012 | S4_WIN | S4_WIN | MEASURED |
| pair_1_7 | 57012 / 56938 | 57012 | S4_WIN | 100_PERCENT_CEILING_TIE | MEASURED |
| pair_2_4 | 44226 / 39566 | 44226 | S4_WIN | S4_WIN | MEASURED |
| pair_3_5 | 37828 / 37751 | 37828 | S4_WIN | S4_WIN | MEASURED |
| pair_4_5 | 0 / 0 | 0 | TOPOLOGY_CEILING_TIE | UNRESOLVED_TIE | MEASURED |
| pair_5_7 | NOT_MEASURED / NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| triple_2_4_6 | 14906 / 14906 | 14906 | TOPOLOGY_CEILING_TIE | S4_WIN | MEASURED |
| triple_3_5_8 | 12612 / 0 | 12612 | S4_WIN | S4_WIN | MEASURED |
| triple_4_6_7 | 18470 / 11252 | 18470 | S4_WIN | S4_WIN | MEASURED |

`pair_5_7` 固定为 `NOT_MEASURED`：其 archived-only 来源协议仍未解决。100%、有证据的拓扑上限、物理分辨率和论文显示精度可以平局；普通平局不算达标。

## 联合判定与架构边界

target_met=`true`；evidence_complete=`true`；zero_baseline_losses=`true`；zero_unresolved_ties=`true`；context_evidence_complete=`true`；context_losses=`3`（context 不驱动 2× fresh 门）。

运行时仍是 S4/J2/E2 + 节点局部 FIFO + service-aware static local potential：每个转向点只决定下一跳；不调用完整 A*，不生成未来完整路线，不使用 HCA 全局预约表，也没有启用 learning。
