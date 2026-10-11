# Round11 resource ledger — final

已知、去重后的上游 CPU **3717.421875 秒**；本次账本构建 CPU 0.390625 秒另列。
待封存项：0。全部工作的精确 CPU 与精确物理运行总数均未知。

| 目录 | 已知 CPU 秒 |
|---|---:|
| phase4_round11_headway_design_20261011 | 3.843750 |
| phase4_round11_independent_review_20261011 | 289.250000 |
| phase4_round11_projection_query_diagnosis_20261011 | 1.687500 |
| phase4_round11_projection_runtime_20261011 | 197.437500 |
| phase4_round11_storage_terminal_screen_20261011 | 4.484375 |
| phase4_round11_validation_20261011 | 3220.484375 |
| prior_round11_ledger_builds | 0.234375 |

明确计数的物理运行 49 次，包含机制 0、独立桥 32。测试内未仪表化物理次数继续未知。
显式报告的独立 query 入口调用/attempt 92 次；作者测试可包含故意非法调用，按各行 scope 解读，不是成功路线数，不等同物理运行。

| 窗口 | 状态 | 实测 CPU 秒 |
|---|---|---:|
| original_h21600_001 | cpu_cap_censored | 610.421875 |
| original_h80_001 | cpu_cap_censored | 610.328125 |
| projected_h21600_001 | cpu_cap_censored | 666.28125 |
| projected_h21600_screen_001 | cpu_cap_censored | 654.921875 |
| projected_h80_001 | cpu_cap_censored | 661.171875 |

父进程CPU包括同进程pytest/physics/query/scale；这些区间不重复加入。单独bridge child按原始receipt另计。CPU cap不是消耗；预算删失不是物理不可行。
头距 ledger 原型和枚举 oracle 的检查数单列，不是完整业务物理运行，也没有接入本轮四格窗口。显式 null CPU 的启动失败保留为未知。
若有tail续跑，其额外预算、原停止点和checkpoint单列；不能把新增预算当成原固定预算的算法比较，也不能把重复前缀合并成新的独立数据。
失败尝试、逐项SHA、重复排除依据、未知辅助和待封存项见ledger.json。不能将并发wall相加。
