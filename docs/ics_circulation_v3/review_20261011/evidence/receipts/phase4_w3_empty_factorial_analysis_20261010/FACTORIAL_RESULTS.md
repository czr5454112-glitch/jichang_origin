# 空盘选择：延续模型 × 同分规则的完整开发消融

固定 36 条原始 deployment tape，四格全部报告，共 144 次。实际控制均为 timed K4；候选构造、mandatory greedy/no-transfer、depth2、动作预算12、score40、搜索配额与公共 point proxy 不变。earliest/reactive 格保持共同 planning20/K4/真实 cursor，因此不宣称等同旧 legacy 内部 K1/planning40/snapshot-restart 模型。

全部 144/144 controller_quiescent；源码漂移为零，失败/截尾为零。纯文件核验 35730 项，错误 0；原默认格 36/36 复现旧 empty12_h40 的两端点完整物理 result（仅忽略 policy 毫秒字段）、路由历史和慢层动作。

| proxy continuation / tie | final J | on time / scheduled | worker invocation CPU(s) | proxy calls | internal queries / work |
|---|---:|---:|---:|---:|---:|
| timed_greedy__incumbent | 384.6 | 163/198 | 358.641 | 2015 | 6860 / 260656 |
| timed_greedy__fewest_physical | 370.5 | 166/198 | 369.250 | 2070 | 7105 / 270507 |
| earliest_reactive__incumbent | 384.6 | 163/198 | 206.266 | 2015 | 6689 / 253152 |
| earliest_reactive__fewest_physical | 368.4 | 167/198 | 205.812 | 2021 | 6665 / 253080 |

所有格 198/198 完成；h80 与完整 drain 的聚合成本/准时数一致。完整本次 worker invocation CPU 1139.969s，协调器 wall 259.954s（6 workers）。CPU 是本机同时实验负载下的测量，不能解释为可移植实时延迟。

| paired change (B minus A) | final delta J | delta on time | better / equal / worse tapes |
|---|---:|---:|---:|
| timed_greedy__incumbent → timed_greedy__fewest_physical | -14.1 | +3 | 3/33/0 |
| timed_greedy__incumbent → earliest_reactive__incumbent | +0.0 | +0 | 0/36/0 |
| timed_greedy__incumbent → earliest_reactive__fewest_physical | -16.2 | +4 | 4/32/0 |
| timed_greedy__fewest_physical → earliest_reactive__incumbent | +14.1 | -3 | 0/33/3 |
| timed_greedy__fewest_physical → earliest_reactive__fewest_physical | -2.1 | +1 | 1/35/0 |
| earliest_reactive__incumbent → earliest_reactive__fewest_physical | -16.2 | +4 | 4/32/0 |

两因素的完整配对 interaction（earliest 下 tie 效果减 timed 下 tie 效果）合计 -2.1 J。逐 tape 数值与首动作分歧的 snapshot SHA、候选、proxy 成本和实际动作全部保存在 analysis.json。这里没有只保留收益样本，也不根据本结果宣称已选出部署配置。

| versus legacy reference | delta J | delta on time | better / equal / worse |
|---|---:|---:|---:|
| timed_greedy__incumbent | +16.2 | -4 | 0/32/4 |
| timed_greedy__fewest_physical | +2.1 | -1 | 0/35/1 |
| earliest_reactive__incumbent | +16.2 | -4 | 0/32/4 |
| earliest_reactive__fewest_physical | +0.0 | +0 | 0/36/0 |

earliest/incumbent 与 timed/incumbent 成本相同；对同分规则的改变才产生这批流上的行为收益。timed/fewest 改善但还留一个 +2.1 J / −1 准时的 legacy 差额；earliest/fewest 的成本/准时达到旧强对照，因此这次消融解释了现有缺口，不能包装为超过强对照。所有 36×4 结果、各格与 greedy/legacy/public-fast/原 new 的配对分母均保留。

候选覆盖和省略以 JSON 原始计数为准。若 depth2 为零、预算未饱和，只能说此开发族未激活联合两转移的机制；不能将动作预算或联合规划记为贡献。首分歧 snapshot SHA 相同的比较可解释选择规则在相同状态上的变化，后续总轨迹仍是各自重复部署的结果，不是固定续接下的单步因果差值。

运行异常另账：首次 preflight 因 tuple/list 对照失配，0 仿真；第二次历史 JSON 比较假失败中止，保留 74 个已结束 episode（其中18条被旧 runner 错标 execution_failure，物理计算已完成但完整记录被异常处理覆盖），可恢复成功记录的 deployment CPU 下界239.375s，额外失配和在途 CPU 未知。当前144全量重跑未复用这些结果；总研究成本不可只记本次1139.969s。详见旧目录 preflight_failure.json / aborted_run.json。

这份分析不运行模拟、不调整方法、不筛种子，不证明真实未来上的 dominance、稳定性或统计泛化。
