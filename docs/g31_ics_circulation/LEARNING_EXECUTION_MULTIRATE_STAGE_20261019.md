# G31：冻结模型实际提交与异步建议验证（2026-10-19）

工作区：`C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`，分支 `codex/g31-ics-v3-circulation`，HEAD 仍为 `da8d39ed`。本轮沿用已有未提交研究改动，未提交、未推送。

**本轮完成初始学习器的真实选择、提交和原生配对。新配对中 receiver 改善 0.119 秒，其他四件不变。独立进程预测期间原生实体持续推进，晚到建议被当前检查拒绝。** 这些结果属于一个机制场景，不是多步 RL、全机场泛化或硬实时认证。

## 1. 反馈采用范围与时间合同

用户要求依据反馈继续优化。三份附件的原始字节保存在本轮输出的 `feedback/`。将其中的设计建议与历史结果作为待核依据；本轮事实来自新源码、运行原件和独立审计。

采用分层验收：R1 区内更新保留 100 ms 必要计算目标；R2 完整释放预测、候选推演与预平衡按适用期、动作截止期及当前接纳条件验收。历史完整请求超时记录保留，不能因此改判通过。当前 `.05` 来源时效合同、拓扑、容量、盘数、FIFO/headway、不可撤命令和五件原参考均未放宽。未重新开展文献核读或提出新的创新性结论。

## 2. P0：模型选择进入实际提交

新增 `foundation_initial_selector.py`，通过显式 `initial_selector` 依次进入 `FoundationNativeEnvironment`、`start_owner()` 和 `choose_and_submit()`。默认 `None` 保持旧路径；`initial_evaluator` 仍为 advice-only。执行侧持有真实 InitialDecision；评分器只读脱离后的公开观察和候选语义，无 session/client、未来任务表或终态标签。

冻结原 task2 的 43 维 linear 模型，SHA-256 为 `caa345a054c8c05c5db528f9b11dfd5343b334c1d6dd977e93f60ad7e2669f78`，没有重训或看新结果选模型。A 仅查 04（K=1/P=1）；学习分支 B 实际 K=4/P=2。模型先安排查询，再从已查询且通过原逐件保护、公开兼容域的候选中按冻结分数选 ID。兼容层只允许该 ID；随后仍执行 first-component 重验、require_current 和原生提交。未调用 full32 教师替代实际 K/P 预算。

新原生 `initial_pair_001`：两分支原输入文件逐字节相同，均运行到 H=40；进程分别 35.469 / 33.938 秒，均在各自 150 秒 Windows Job 硬限内。这两个进程耗时不是性能配对实验。

| 事实 | 新接口固定 04 | 冻结模型 |
|---|---:|---:|
| A 实际选择 | 04 | 04 |
| B 实际查询 | [4] | [4,12,13,5] |
| B 通过保护的已查项 | [4] | [4,12] |
| B 实际选择、兼容后提交 | 04 | 12 |
| E：5→1 earliest_departure | 2.210 | 4.201 |
| 初始命令最终 ACK | rejected / receiving_full | received |
| E 实际进入 5→1 | 4.420（原恢复请求） | 4.301（初始请求） |
| E 实际接收 | 4.720 | 4.601 |

固定 04 的拒绝 ACK 是真实基线事实，后续原 retained recovery 完成服务；没有将拒绝伪装成接收。所有 retry 保留原命令身份和 payload。

| 业务 | 固定 04 完成/s | 模型完成/s | 模型−基线/s |
|---|---:|---:|---:|
| loaded | 7.200 | 7.200 | 0 |
| receiver | 10.120 | 10.001 | −0.119 |
| reuse1 | 13.050 | 13.050 | 0 |
| reuse2 | 18.460 | 18.460 | 0 |
| blocker | 11.350 | 11.350 | 0 |

保存原始浮点数逐项零容忍比较；表格仅作显示舍入。标准库独立审计核查五件、三盘、真实 calls/outbox/ACK/receipts，745 份 campaign 来源归档、每分支 128 份 native 来源归档，以及两个闭合 acceptance。旧 B12 正例没有重复计入：本表来自本轮两个新原生执行。

## 3. P1：后台预测、当前拒绝与计时边界

新增 `foundation_multirate.py` 和 `foundation_multirate_probe.py`。独立 spawn 进程只接合法采集的 JSON evidence；worker 不持有原生对象和提交权能。前台继续原默认 continuation，以非阻塞轮询查看完成标志。返回时读当前 owner view/outbox，检查动作期限、实体代际/已承诺前缀、来源年龄及 ACK；即便隔离语义检查按时通过，仍只返回“需要新 current admission 与完整复验”。

最终 `multirate_002` 为一次真实预测，不注入模拟延迟。`execution_time_mode` 的实际口径为 `offline_event_clock_with_process_async_advice`，`realtime_async=False`，没有把仿真秒转换为墙钟秒。独立进程确实并行，但尚未实现或验证现场实时节拍。

- B 在约 9.690 s 采集，既有来源最早约 9.660 s；不从 worker 启动重置年龄。
- 真实预测计算区间内有 22 个原生观察采样，仿真从 9.810 推进到 10.710 s，包含 8 条实体生命周期事件。
- 动作最后可变更期限由原 `now + .01 < service_ready_at` 推导，约 9.740 s。结果在真实观察到返回的 10.810 s 被拒绝，原因包括 deadline missed、目标/前缀变化、旧来源过期；没有新增路线命令。
- 到期检查使用既有 B 激活点，保存实际到期时刻、观察时刻和检测延迟；不声称新增了精确原生计时器。无新消息到期及 ACK 不确定由专用语义反例覆盖。
- 140 条非 publication 的物理/命令记录、全部五件业务和三盘终态与原默认一致。

| 计时项 | 本次观测 |
|---|---:|
| worker 冷启动并 ready（native 前） | 2026.571 ms |
| 前台序列化并入队 | 4.692 ms |
| worker 队列等待 | 33.000 ms |
| evaluate 预测段墙钟 | 172.977 ms |
| worker 计算总墙钟 / CPU | 174.916 / 187.500 ms |
| 入队至前台观察到 ready | 221.968 ms |
| 627 次轮询总墙钟 / 单次观测最大 | 15.093 / 1.846 ms |
| native 结束后的 join | 0.035 ms |

这些窗口有包含关系，不能全相加。全部原生 activation 和原 collect/capture 成本另保存在报告中，不能只用 4.692 或 1.846 ms 认证完整 R1 100 ms。CPU 计时是当前平台累计采样，少量样本不提供 p99 或硬上界。

首轮 `multirate_001` 原件保留。独立代码审查发现原验收只核 seed 状态、且推进事件集合含协议记录；本轮新增完整双候选五件结果/source-exit 检查，以及严格实体生命周期事件门槛和 9 项反例，重新登记并执行 002。最终异步结论引用 002；001 不回写。P0 运行时的归档仍保留原 P1 审计器字节，P0 实际执行的选择/模型/提交链没有因后续 P1 验收修正而改变。

## 4. 区域转移与航班接口

later transition 升为 v2：仅连接同 owner 的下一实际决策，保存真实 Δt；末步连接真实 native terminal clock。导出时再次将 next_observation 绑定到同 episode 的下一同 owner 记录，拒绝跨 owner、自环、跳过后继、伪造选择时刻或终止间隔。历史 v1 原件不改，仍可用于原终态续值回归，但明确 `eligible_for_local_td=False`。这没有构成新的 TD/RL 训练。

`owner_transition_001` 新原生复跑在 50.406 / 150 秒内闭合，receipts/jobs/trays 与保存默认轨迹完整一致。新导出的 A 7.34 s、B 9.69 s 两条 v2 记录均没有下一同 owner 决策，分别以 Δt=32.66 / 30.31 s 连接 H=40；没有 A→B 的本地后继。导出校验通过，仍明确没有同 owner 多步选择支持，也未训练。

可选航班适配器与数据审计见 [FLIGHT_CONTEXT_20261019.md](FLIGHT_CONTEXT_20261019.md)。原始数据有 28,506 条逐件任务和 360 个历史分组，没有独立计划发布时间、owner 接收时间和更新历史。新接口默认 `None`，验证本地实际收到版本与时间基准，拒绝事后真值字段；未改变旧 43/52 维 checkpoint，未制造未来 jobs 或可用库存。真实需求预测、释放/需求联合账户与收益消融尚未实施。

## 5. 验证与证据入口

本轮统一输出前缀：`outputs/experiments/g31_ics_multirate_20261019/`。

| 证据 | 入口 |
|---|---|
| P0 登记、冻结模型、两次原生闭环 | `initial_pair_001/plan.json`、`receipt.json`、两个分支 `native/` |
| P0 标准库独立核验 | `independent_initial_001/report.json`、`verify_initial_pair.py` |
| 最终 P1 与完整双候选预测 | `multirate_002/worker_report.json`、`prediction.json`、`probe_observations.json`、`native/` |
| P1 独立核验 | `independent_multirate_001/` |
| v2 区域转移原生验证 | `owner_transition_001/` |
| 最终回归与来源字节 | `final_validation_001/plan.json`、`tests.xml`、`receipt.json`、`source/` |
| 机器可读阶段汇总 | `stage_summary_001.json` |

最终 **943 项回归通过，0 failure/error/skip**；pytest 154.215 秒，完整子进程 156.594 / 180 秒硬限，783 份来源 pin 在运行前后未变并保存了实际字节。P1 标准库独立审计通过 2,077 项检查和 1,277 次文件哈希核对，同时核了 23 次物理调用、7 个物理请求及最终 ACK/outbox 的基线一致性。单独定向测试曾因系统默认临时目录权限失败，改为工作区内独立 basetemp 后通过；最终登记回归没有该环境错误。

用户主工作区 `bounded_local_pibt.hpp` SHA-256 保持 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。

## 6. 下一道门

P0 接线与单场机制已经得到新原生证据。后续优先用预登记的固定图自然需求场景取得有限多场配对与实际后续选择支持；继续验证按时建议的新 current admission 和接续可行性。当前 P1 只证明默认持续与晚到拒绝，不能声称按时新动作接纳、预调收益或跨事件后缀复用。完整 R1 100 ms、全机场/EBS 映射、跨日航班预测、保护普适证书与多步 RL 仍开放。
