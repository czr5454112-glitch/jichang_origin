# G28 Service-Aware 线路中断结果

G28 先应用 service-aware static local potential；对持久、启动前已知故障，既有 G27 local goal scalar residual 接管。该 residual 以新的 service-aware 矩阵为参考，不恢复旧 travel-only potential。

比较使用同一 canonical population 和固定 28,506 分母，但不是逐 segment release paired；6 胜/9 个拓扑上限平属于描述性 completed-bag numerator comparison，不能解释为严格配对因果效果。

| 场景 | 线路 | affected conveyors | 论文 completed | fresh HCA completed | G28 completed | topology upper | G28 vs fresh HCA | G28 vs paper |
|---|---|---:|---:|---:|---:|---:|---|---|
| single_1 | 1 | 1 | 28506 | 28506 | 28506 | 28506 | TIE | TIE |
| single_2 | 2 | 7 | 25085 | 25313 | 25313 | 25313 | TIE | G28_WIN |
| single_3 | 3 | 5 | 28506 | 28506 | 28506 | 28506 | TIE | TIE |
| single_4 | 4 | 15 | 27081 | 28471 | 28506 | 28506 | G28_WIN | G28_WIN |
| single_5 | 5 | 24 | 27651 | 28484 | 28506 | 28506 | G28_WIN | G28_WIN |
| single_6 | 6 | 7 | 27366 | 28506 | 28506 | 28506 | TIE | G28_WIN |
| single_7 | 7 | 1 | 28506 | 28506 | 28506 | 28506 | TIE | TIE |
| single_8 | 8 | 7 | 28221 | 28497 | 28506 | 28506 | G28_WIN | G28_WIN |
| pair_1_7 | 1,7 | 2 | 28506 | 28506 | 28506 | 28506 | TIE | TIE |
| pair_2_4 | 2,4 | 22 | 21665 | 22083 | 22113 | 22113 | G28_WIN | G28_WIN |
| pair_3_5 | 3,5 | 36 | 18814 | 18914 | 18914 | 18914 | TIE | G28_WIN |
| pair_4_5 | 4,5 | 54 | 0 | 0 | 0 | 0 | TIE | TIE |
| pair_5_7 | 5,7 | 12 | 13683 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| triple_2_4_6 | 2,4,6 | 36 | 7412 | 7453 | 7453 | 7453 | TIE | G28_WIN |
| triple_3_5_8 | 3,5,8 | 51 | 1425 | 0 | 6306 | 6306 | G28_WIN | G28_WIN |
| triple_4_6_7 | 4,6,7 | 30 | 7412 | 5635 | 9235 | 9235 | G28_WIN | G28_WIN |

对 fresh HCA：6 胜、9 个拓扑上限平、0 负；对论文：10 胜、5 平、0 负。`pair_5_7` 仍为 `NOT_MEASURED`。

`affected conveyors` 是原表的场景/拓扑描述列，已完整保留，但不是算法结果，不计入胜负。

架构仍为决策层去中心化：每个转向点只选择下一跳；运行时不使用完整 A*、未来完整路线、HCA 全局预约表或 learning。
