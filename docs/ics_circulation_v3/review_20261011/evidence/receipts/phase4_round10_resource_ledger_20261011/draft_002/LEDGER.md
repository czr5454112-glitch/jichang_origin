# Round10 resource ledger — provisional

已知、去重后的上游 CPU **1859.218750 秒**；本次账本构建 CPU 0.328125 秒另列。
待封存项：0。全部工作的精确 CPU 与精确物理运行总数均未知。

| 目录 | 已知 CPU 秒 |
|---|---:|
| phase4_round10_business_projection_20261011 | 187.562500 |
| phase4_round10_independent_review_20261011 | 101.687500 |
| phase4_round10_storage_search_20261011 | 7.609375 |
| phase4_round10_validation_20261011 | 1562.046875 |
| prior_round10_ledger_builds | 0.312500 |

明确计数的物理运行 122 次，包含机制 66、独立桥 16。测试内未仪表化物理次数继续未知。
明确独立路由 query 12 次；query不等同物理运行。

| 窗口 | 状态 | 实测 CPU 秒 |
|---|---|---:|
| business_window_h21600_001 | cpu_cap_censored | 613.9375 |
| business_window_h21600_tail_001 | fixed_tail_cap_censored | 280.640625 |
| business_window_h80_001 | cpu_cap_censored | 642.96875 |

父进程CPU包括同进程pytest/physics/query/scale；这些区间不重复加入。单独bridge child按原始receipt另计。CPU cap不是消耗；预算删失不是物理不可行。
若有tail续跑，其额外预算、原停止点和checkpoint单列；不能把新增预算当成原固定预算的算法比较，也不能把重复前缀合并成新的独立数据。
失败尝试、逐项SHA、重复排除依据、未知辅助和待封存项见ledger.json。不能将并发wall相加。
