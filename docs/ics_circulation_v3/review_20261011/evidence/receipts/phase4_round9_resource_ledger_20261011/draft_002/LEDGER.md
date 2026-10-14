# Round9 resource ledger — provisional

已记录、不重复计入的上游 CPU：**1488.906250 秒**；这是已知区间之和，不是含全部辅助工作的精确总量。
本次账本自身 CPU：0.218750 秒，另列。待完成记录：4 项。

| 工作目录 | 已知 CPU 秒 |
|---|---:|
| phase4_round9_business_input_independent_audit_20261011 | 17.484375 |
| phase4_round9_business_inputs_20261011 | 109.906250 |
| phase4_round9_independent_review_20261011 | 103.328125 |
| phase4_round9_storage_lifecycle_20261011 | 1227.640625 |
| phase4_round9_storage_release_plateau_20261011 | 3.468750 |
| phase4_round9_storage_routing_20261011 | 3.750000 |
| round9_resource_ledger_auxiliary | 23.140625 |
| round9_resource_ledger_prior_builds | 0.187500 |

明确计数的机制试验 126 次，直接桥接 32 次。
全部明确计数的 physical runs 当前为 227；测试内部物理运行次数未知，不能把它当作精确总分母。

parent CPU 已包含同进程 pytest；physics/scales 子区间和汇总字段均不重复相加。bridge child 单独计入。
窗口 001 的每 tick result 采集、002 的 chunk60 采集及003修复后部署均保留；chunk60仍逐 tick 物理推进。CPU cap 不是实际已用 CPU；预算删失不是物理不可行。

| 窗口部署 | 状态 | 已知总 CPU 秒 |
|---|---|---:|
| business_window_h80_001 | cpu_cap_censored | 608.9375 |
| business_window_h21600_001 | cpu_cap_censored | 608.703125 |
| business_window_h80_002 | pending | None |
| business_window_h21600_002 | pending | None |
| business_window_h80_003 | pending | None |
| business_window_h21600_003 | pending | None |

未知辅助、失败、每项输入 SHA、重复排除依据和未完成列表均在 ledger.json；未计量不填 0。
没有把并发 wall 相加成总历时，没有把同源重试或增密当作独立运行日。
