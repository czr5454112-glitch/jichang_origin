# G31 请求内计算优化与服务预测刷新边界

日期：2026-10-17。研究工作区：`C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`，分支 `codex/g31-ics-v3-circulation`，起点仍为 `da8d39ed4e36b6db31e3a7a6b17b0f73b85eed9a`。本轮未提交、未推送。

**结果：在不改变物理规则、原逐件参考和预测结果的前提下，同请求模型段中位耗时降低约 3.90–4.91 倍；重新执行原生分支并通过独立核对；787 项回归全通过。完整 100 ms、跨事件缓存、局部后缀修复和多步 RL 仍未完成。**

用户补充的 `Downloads/LEARNING_NEXT_STAGE_20261017.md` 与工作区上一阶段报告逐字节一致，SHA-256 为 `ead055df5a5ca852e429ac1d451f3762d503b09f89b35271563b47aacec8e6ae`，没有额外的 Pro 批注。本轮落实其中第 7 节的性能、失效条件和历史约束，而不把附件中的建议直接作为实验事实。

## 1. 目标和文献依据

目标仍是有限托盘、区域去中心化 ICS：载货服务影响托盘释放，释放预测支持提前返空，并通过真实接收权限和本地执行闭环验证。保留原拓扑、容量、盘数、FIFO、headway、不可撤命令身份及零容忍逐件保护；不更新较差参考掩盖退化。

已核读五篇原始来源，定位和适用边界见 [服务预测刷新文献核验](SERVICE_REFRESH_LITERATURE_20261017.md)。联合行李路由与空车管理有 [Zeinaly 等 2015 的原始研究](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf)；[ECC 2013 事件触发 MPC](https://people.kth.se/~kallej/papers/event-triggered_ecc13.pdf) 将状态偏差、时域耗尽与重算关联；[Automatica 2022](https://doi.org/10.1016/j.automatica.2022.110533) 区分每步监测与触发时求解。[FICO v3](https://arxiv.org/html/2511.13961v3) 和 [CDCBS v1](https://arxiv.org/html/2604.00428v1) 要求冻结边界或回退证书满足相应前提，其总成本性质不能转成逐件不劣。

据此采取的工程方案是先共享同一请求内确定不变的静态数据，并建立保守失效判定。没有凭空设定“每几秒预测一次”，没有引入非零业务容差，也没有宣称上述论文已证明本项目安全或创新。

## 2. 实际瓶颈及修复

保存的真实 A/B 当前证据 profiling 显示：单次原 `build_seed` 重建固定合同目录 31 次，调用静态 service-aware potential 620 次。原控制入口先 build 一次，再由两个 `predict` 各重建一次；两候选的 profiled 时间约 98% 在 seed 重验中。单候选事件循环无插桩约 3.6–4.1 ms，不是主要耗时。cProfile 的插桩耗时没有当作实测运行速度。

新增 `foundation_request_context.py`，为一次调用创建私有函数命名空间，静态目录仅生成一次，每次读取给隔离副本。没有全局 monkeypatch，没有跨请求静态缓存，也没有复用上次事件预测。

新增 `foundation_later_seed.evaluate(evidence, action_ids)`：

- 接受原始 evidence，不能拿外部 seed 字典绕过验证；同请求 fresh seed 内部供两个独立推演使用。
- 原 build 内两轮动态 endpoint/lifecycle 校验保留；候选前后核对 seed 规范字节，突变使整次请求 unknown。
- 每请求实际计数为 **1 次静态目录构造、31 次隔离读取、2 次动态 later_context 校验**。
- 原公开 `build_seed/predict` 保留原行为，直接作为未优化对照；没有改继承的物理循环。
- 请求级来源 hash 明确只是部分依赖 pin，外层来源集合及原生归档另外检查；来源或文件异常不返回成功候选。

控制器接入新批量入口，但提交前的真实 capability、当前 owner view、own outbox、目标与本地接纳检查均保留。未知预测不因与旧 unknown 相同而通过基准；失败预测先保存原件，再停止。

## 3. 冻结后 ABBA 对照

最终记录为 `abba_002`。三个真实保存上下文，每个执行两轮 ABBA，共 24 份双候选报告、48 个候选预测；每种方法每上下文 4 次。全部 seed、完整预测和规范 JSON 类型严格一致，输入只取合法 evidence，不把终态结果传给模型。

| 保存的当前上下文 | 原路径中位数 | 请求内共享中位数 | 原路径 / 共享 |
|---|---:|---:|---:|
| 默认 A，7.34 s | 794.735 ms | 161.883 ms | 4.91 |
| 默认 B，9.69 s | 876.097 ms | 224.782 ms | 3.90 |
| 延迟返空后的 B，10.22 s | 942.816 ms | 232.162 ms | 4.06 |

计时包含 evidence 复制、该入口的来源检查、seed/候选计算和 JSON 脱离；不含原生采集、actor、提交、ACK、模块启动和报告落盘。它证明本次单机制域三个状态下的模型段改进，不是端到端或机场规模性能认证。没有 p95/p99 或峰值内存结论。

## 4. 新原生执行与独立核对

最终 `native_002` 同原输入、相同默认动作、H=40，Windows Job 56.391 s / 150 s 硬限。独立脚本不导入模型或执行器，325 项核对通过：完整 **153 条 receipts、5 件业务、3 个托盘**，calls/outbox/创建记录、两切点 evidence/seed/全部预测、原参考及非计时 transition 与上一阶段默认轨迹一致。两个 actor 窗口的原生状态与物理时钟均未改变。

| 新原生切点 | 当前采集到 offer | 其中模型与保护 | 采集入口到决策记录 |
|---|---:|---:|---:|
| A first_return | 303.935 ms | 176.111 ms | 329.001 ms |
| B first_reuse_route | 329.741 ms | 198.185 ms | 368.975 ms |

“其中模型与保护”已包含在第一列中，不能相加。最后一列新增连续墙钟计量，包括其间 actor/wrapper 与提交，但仍不含更早的消息采集、启动、返回序列化和后续 ACK。**这个较窄窗口已经超过 100 ms，因此完整目标明确未达到。** 当前采集与证据组装等前段分别约 127.8/131.6 ms，模型阶段仍约 176.1/198.2 ms，后续应分别 profiling，而不是只继续优化几毫秒的事件循环。

本轮没有新业务收益：两个 later 非默认仍被原逐件门拒绝，默认轨迹不变。原生整段进程墙钟还包含初始 full32 等未优化工作，不把局部加速解释为整 episode 同倍加速。

## 5. 服务刷新判定与仍然缺少的证据

新增 `foundation_service_refresh.py`，只做 supplied-data 审计，不接管原生调度：同 owner、同 episode、原参考身份不变；两份原始证据均重新构建；检查不可变提交前缀、来源顺序、任务、盘身份、资源、服务边界、命令/ACK、outbox 和完整原始 evidence。

任何依赖或未分类字段变化均保守全域失效；缺少可证明的外部边界时不截断影响范围。推进一个时钟参数不能让旧快照变成当前状态。重复数据通过重验只标为 duplicate，不认证新的观察或缓存执行。

`refresh_audit_001` 实际执行五个保存数据检查：A/B 原件重复两例重验通过；给旧快照推进时钟、跨实际 episode、同 episode 跨 owner 三例均明确拒绝。没有执行预测或 native，没有节省跨事件计算的声明。

现有证据没有“同一 owner、同一 episode 的两个成功 later current contexts”。默认 B9.69 和延迟分支 B10.22 属于不同反事实 episode，不能当成实际前后缓存；A7.34 与 B10.22 又属于不同 owner。A→B 服务依赖变化是真实的，但还不是局部后缀可复用证书。固定间隔、事件刷新与完整重算的在线公平对照，以及实际局部后缀修复均未完成。

## 6. 历史澄清与失败保留

初始候选 **12 并不是保护失败例**。旧固定向量 ledger 和在线兼容门已经有 A04+B12 的真实结果：receiver 改善约 0.119 s，其余四件不退化；上一阶段 task2 因预登记为 advice-only 才仍执行 04。本轮没有重复该收益实验，也没有把旧收益算成新收益。不能把初始 12 与 later 的 delay/prefer8 退化混为一谈。

历史入口：`outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_recollection_native_v2_prepare_001/branch_ledger.json`；`compatible_initial_native_20261017_004`；`compatible_initial_native_20261017_006_remaining12`；`audit/review_20261017/independent_native003_physical_audit_003.json`。

本轮保留三个问题的原记录：

1. profiling 首探针误用只接受 dict/list 的严格输入编码器处理模型内部 tuple，快速失败；新目录修复探针，原输出不覆盖。
2. 请求上下文测试首轮 26 通过、7 个测试端同类编码失败；只修测试比较器为规范 JSON，专用第二轮 33 项通过。
3. `native_001` 物理与预测一致，但独立审计发现 `foundation_request_context.py` 在第一次 evaluate 才延迟导入，漏进早期 native 源码归档。该文件已有 campaign pin，仍不因此放宽归档验收。将 import 移到模块顶层，新增子进程导入/归档回归；重新登记 `abba_002/native_002`，相同硬限重跑。`independent_native_001` 保持 unknown，`independent_native_002` 严格通过，原归档未补写。

## 7. 测试与证据入口

最终 **787 项测试，0 failure/error/skip**；pytest 122.182 s，子进程 124.656 s / 180 s 硬限，768 个固定来源 pin 未变化。此前定向 120/121 项及两个专用轮次均单独保留。不改用户主工作区 `bounded_local_pibt.hpp`，其 SHA-256 仍为 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。

以下统一相对前缀为 `outputs/experiments/g31_ics_service_update_20261017/`：

| 用途 | 入口 |
|---|---|
| 瓶颈测量 | `profiling_001/repaired_002/report.json` |
| 最终 ABBA 与完整候选原件 | `abba_002/report.json`、`receipt.json`、各 `*.json.gz` |
| 最终原生闭合证据 | `native_002/guarded_default/episode/native/` |
| 最终独立原生/模型核对 | `independent_native_002/report.json`、`independent_native_review.py` |
| 保留的归档缺口 | `native_001/`、`independent_native_001/report.json` |
| 只读刷新判定 | `refresh_audit_001/report.json`、`review_refresh.py` |
| 最终回归 | `final_validation_001/plan.json`、`tests.xml`、`receipt.json` |
| 本轮机器摘要 | `stage_summary_001.json` |

下一步优先分离当前采集/验证/证据复制的剩余成本，并在自然负载差异中寻找通过原逐件门的有效后续选择。没有新有效选择前不重复调这六条数据上的网络、不伪报 RL；没有完整依赖边界前不启用跨事件预测缓存。原机场零容量边、实际 EBS 映射、151 节点/227 边全流与最终 100 ms 验收门继续保留。
