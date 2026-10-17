# 请 GPTPro 独立审阅：G31 基础闭环、按需预测与首次学习阶段

日期：2026-10-17。本文是待核查的阶段汇总与下一轮决策请求，不是验收证书。请先核验源码、原始输出及来源 hash，再判断下面的主张是否成立；不要只复述我们的结论。

**版本边界：**本轮工作树基线为 `a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef`（简称 `a7f7821f`）。该基线不是本轮新增实现的最终提交。最终 commit、分支及 GitHub 验证以 ZIP 顶层 `publication.json` 为准，包内文件 hash 见 `MANIFEST.sha256.json`；提交前白名单与 hash 见仓库 `docs/external_review/g31_foundation_20261017/RELEASE_SCOPE.json`。本文撰写时不宣称推送已经完成。旧原件、失败和被替代草稿保留，不用新结果覆盖旧结果。

## 1. 最终目标与本轮定位

目标仍是**去中心化、有限托盘循环 ICS**：区域控制器在合法本地事实及实际送达消息下执行 R1 载盘路由更新；根据载盘目的地、路线、装卸／存储过程预测释放，执行 R2 跨区空盘预平衡；保留原区内空盘模块职责、实体守恒、FIFO、线路与接收容量、不可撤已发动作及严格逐件完成保护。最终还要在原始工作负载和强基线下证明业务、计算或通信价值，而不是只把实验跑通。

本轮依据 `G31_ICS_CODEX_FOUNDATION_LEARNING_20261017.md`，先交付可复用原生基线、L0 排序学习和昂贵推演前的按需候选评估。**当前 32 候选只是一个历史有限域与 teacher，不是最终系统必须固定为 32 的要求。**本轮没有实现完整联合 R1/R2 自由决策、滚动释放预测、真正在线后缀 repair 或闭环 RL。

## 2. 已有证据与准确范围

| 产物 | 实际完成 | 不能推出的结论 |
|---|---|---|
| `native_001` | 原生薄封装一次闭合，进程 54.219 秒；5 件完成、3 盘守恒、18 次边进入／退出闭合。同盘 L 三次装卸、两次跨区返空后再装载；4 次 shadow 的 native hash 不变，完整 receipts/jobs/trays 与既有 incumbent 基线一致 | 只是正常机制场景。后续仍是 retained-policy，反复激活不等于新学习动作；独立回放也不覆盖全部隐藏预约状态及未来安全 |
| `l0_002` | 3 个保存场景、6 个 owner 初始决策组、192 条候选记录；43 维合法观察／动作语义特征，标签分离；按场景留组，CPU 训练实际 7.983 秒 | 不是 192 个独立场景，不是新闭环采集或泛化证明；标签是条件因果推演，不是实际 native 保护证书 |
| `budgeted_001` | 新增真正按需 provider，保留 full32；37 项专用测试。真实 B 的 K4 请求为 `[4,0,1,16]`，4 条完整 prediction 与后置同上下文 teacher 完全一致 | 这个默认规则与 L0 共享规则权重不同，不可混用其 regret 或排序结果 |
| `budgeted_learned_001` | 同一合法 live B 观察下，规则 K8→留机制场景线性模型 K8→原 full32；一次 90 秒硬上限，65.891 秒正常闭合；17 项 probe 测试，125 项源码及模型等 pins 进入／退出一致 | 只是 advice，未由学习器发命令；固定顺序单上下文不是 ABBA，也没有测得学习控制收益 |
| `pilot_001` | 统一 CLI smoke 64.516 秒完成原生基线、保存数据导出、排序训练；另有保存 held-out 评价回放 | `full_plan_complete=False`；`train-rl` 明确 `blocked_L1_not_certified`、`training_started=False`，不是训练失败也不是训练完成 |
| `final_validation_001` | 560 项测试，0 failure／error／skip；81.125 秒，180 秒硬预算，686 项源码 pins 不变 | 单元／集成回归通过不代替真实闭环学习、泛化、性能认证或安全定理 |

L0 的 K8 保存表结果：规则／线性／MLP 条件最优保留分别为 **2/6、4/6、5/6**；平均条件 regret 分别约 **0.212667、0.106333、0.018167 秒**。但三类评分器的原始首选各有 **4/6 不满足条件逐件保护**，因此不能跳过预测后保护门，更不能将 MLP 表内优势宣称为线上收益。`l0_001` 是已保留的早期草稿，当前结论使用 `l0_002`。

## 3. 按需路径的结构与负结果

新通路先用当前合法观察及动作语义排序，K 包含 incumbent 04；只为请求集合建立必要共享前缀，只克隆／继续所需 suffix。原来源、动态 freshness、隔离与逐件零容差检查保留。私有 runner 只明确改变 `CHOICES` 子集，另记来源合同，不借原 full32 的固定计数为新语义背书。结果只有 advice，无原生提交权。

| 同一 B 上下文 | 共享规则 K8 | 留机制场景线性 K8 | 后置 full32 |
|---|---:|---:|---:|
| 新上下文／prefix engine | 5 | 7 | 16 |
| prefix resume | 6 | 9 | 23 |
| suffix fork／resume | 8／8 | 8／8 | 32／32 |
| source proof 使用且成功关闭 | 17 | 17 | 65 |
| 计算至封存 wall ms | 4003.4167 | 4888.0145 | 10280.5483 |
| 含导出及最后当前检查 wall ms | 4030.1519 | 4912.6517 | 此边界未测 |

两路各 8/8 完整 prediction 与 teacher 一致，各 24 条未请求候选没有推演。proof 使用次数不是预测次数。两路均建议兼容候选 04，五件预测端点相对 incumbent 增量均为 0；均未保留条件联合最优 25，条件保护后最优的 regret 同为约 **0.319 秒**。公开组件合同可行的完整域最优为 12，实际建议 04 的兼容域 regret 同为约 **0.119 秒**。联合条件参考 25 不等于取得对方承诺的可执行联合命令。

**本次没有学习收益，且学习集合需要更多前缀，本次测得更慢。**不能事后换成表现更好的 MLP 来重写这次预登记结果。K 相同不保证共享前缀成本相同，应同时计 prefix、clone、resume、source 校验和封存。

较早真实 K4 门为 3 个 prefix、4 个 suffix、9 次 proof；至封存 2637.8042 ms，同场后置 teacher 9720.5178 ms。它也未达到 100 ms，且条件 regret 2.419 秒、兼容域 regret 0.119 秒。两门均不是严格速度因果实验。

## 4. 100 ms 与“完成一次计算”不能偷换

保留单任务路由更新完整必要计算 **100 ms** 目标，不因本轮耗时较长而降低要求。当前 `initial_call_wall_ms` 包含合法观察采集、候选提供、选择、当前复验及提交调用返回；**不等待托盘物理运输完成，也不是完整异步 ACK 生命周期已经结束**。归属请求的后续 ACK／结果处理计算仍应单列并按原因果链计费；排队、必要等待、协议闭环和实际业务完成分别报告。

历史 42 次 initial 调用为 10.3426～13.6794 秒，0/42 达到 100 ms；provider 累计占约 93.24%，但包含来源绑定、复制、模型推进、校验与封存，不能写成“纯预测占 93%”。本轮 K8 的 `guarded_prefix_clone_and_rollout` 规则／学习分别为 2373.1795／2983.3579 ms，也包含嵌套检查；source preparation+bind+setup 为 919.7931／1005.3987 ms。尚不能据此完整拆分各内部根因。

冷启动、首次请求、常驻暖请求和一次性退出要区分。不能把十秒批次除以订单数得到“单件 100 ms”，也不能把网络前向或表内选择耗时当完整请求。旧 18 次闭环探针与当前 initial 调用边界不同，不组成同口径加速序列。

## 5. 尚未完成的门与必须记住的历史坑

- **L1 不是“还差全域认证”。**真正缺口是：后续当前观察下新的受约束 R1/R2 动作机会、会真实改变下一状态的授权动作链、配对多步原生转移与学习器接线。已有有限盘复用和稳定基线是必要进展，但 initial 克隆评估及 retained-policy 不满足这些缺口。满足有效范围 P1/P2 后应尽快进入 L1，不必等所有故障、100 ms 或全天实验。
- **P4/P5 尚未实现。**没有新的周期／事件触发释放预测服务，没有 R1 改路→释放修订→R2 实发→后续 R1 反馈的学习闭环；没有由新送达事件引发的真正未发后缀 repair。旧初始 future fork 不能冒充当前重建。首复用点剩余二元动作域还可能没有复杂搜索优势。
- **去中心化不等于独立建议可任意拼接。**当前保守域固定 A 的 incumbent 分量，B 只能使用已查询、逐件受保护且与 A 分量兼容的候选；不能宣称完整联合域已恢复。预测的 peer 行为是条件，不是预约／接收承诺。
- **不能简化物理或权限换通过。**`native_default(None)` 不是固定走某条边；卸载、返空接收、再装载必须由实际事件闭合，不能提前生成空盘。已发或可能已发但缺 ACK 的命令不可重命名后重复派发。
- **少查询不等于少推演。**原 full32 后再选 Top-K 只能测试排序；本轮才验证所选集合在昂贵推演之前确定。保存 JSON 不恢复 live capability；actor 不能读原生全局隐藏状态、未来标签或未送达消息。
- **严格保护与证据纪律不变。**总和改善不能抵消一件退化，任意正退化不能用容差抹掉；timeout、unknown、实际拒绝及失败继续留分母。source proof／动态检查不能为性能删掉；测试数、正常 exit code、模型结果和真实 native 闭合分别核查。

## 6. 请给出下一轮明确判断，而不是泛泛鼓励

1. **核查本轮是否真的达到 L0、真实按需评估和声明范围的物理基线。**重点查特征／标签隔离、按场景留组、同上下文 parity、24 条未请求不推演、prefix 实际计数和失败传播；找出夸大或漏洞，给精确反例。
2. **怎样最小且诚实地达到 L1？**请指定一个当前 later-context 数据桥／同语义 seeder／授权动作入口，以及能够改变实际未来状态的最小正例和必须拒绝的反例。不要把“等待所有异常解决”作为无限期门槛，也不要把重复执行旧策略算作新动作。
3. **预测与预调度是否应多时间尺度？**区分外生订单预测、由现有载盘内生推导的释放 ETA、候选推演和即时 R1。提出周期兜底＋送达事件触发的首版规则、依赖失效范围、合并触发、结果年龄及陈旧丢弃条件；不要直接指定未经验证的固定周期。
4. **100 ms 的接口合同怎样解释而不降低？**逐项列原要求→前台／后台 API→计时起止和同步依赖；如果建议变更 R2 截止期，明确标为待用户批准的变更，不能自行豁免。后台延迟时前台能否仍合法运行应有可验证测试。
5. **学习下一步应优化什么？**本次线性无收益，是否先让排序目标／采样包含共享前缀成本、兼容动作域和不确定性，再扩展真正独立场景？如何避免只学到固定候选表或为学习制造弱规则？请给同预算强基线及停止条件。
6. **贡献是否站得住？**结合任务书已有文献台账实际核读关键原文，区分已有多速率、增量修复、有限车队与契约思想及本项目尚待证明的增量；不要以实现协议、引入神经网络或改名宣称原创。

请返回：①证据逐项通过／不通过／未知；②最重要的三项风险；③下一轮最多三项可编码任务，含入口、禁止改动、最小实验、完整计费和失败停止条件；④哪些现有结论应撤回或缩小。明确哪些判断来自实际核查，哪些只是建议。

## 7. 证据索引与建议核查顺序

本机工作树根目录为 `C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`。以下是**相对该根目录**的可移植索引；文件是否随发布包提供以发布清单为准，缺失应报告，不假称已读取。

ZIP 支持离线审阅与保存证据重算，**不保证 fresh clone 即可重新执行 native**：原 acceptance 依赖外部解释器、native026/027 构建二进制等，未全部随包。证据中的绝对 C 盘路径原样保留；审阅使用独立相对路径映射，不修改原始 plan／receipt 来制造可复现通过。离线重算通过不能改写成新 native 执行。

实验共同前缀：`outputs/experiments/g31_ics_foundation_learning_20261017/`。

| 先读内容 | 前缀下路径 |
|---|---|
| 最终回归与 pins | `final_validation_001/receipt.json`、`plan.json`、`tests.xml`、`pytest.log` |
| 原生实体与复用证据 | `native_001/independent_physical_audit.json`、`receipt.json`、`acceptance.json`、`raw.json.gz` |
| L0 数据与真实训练 | `l0_002/collect/`；`l0_002/models/registration.json`、`folds.json`、`training_report.json`；`l0_002/heldout_replay.json` |
| K4 独立对照与专用回归 | `budgeted_001/native_001_same_context_comparison.json`、`tests_003.xml`、`probe_tests_002.xml` |
| 预登记同预算学习门 | `budgeted_learned_001/plan.json`、`receipt.json`、`worker_report.json`、`callback_complete.json`、`native/raw.json.gz`、`READOUT.md` |
| CLI 与诚实的 RL 阻塞 | `pilot_001/smoke/receipt.json`、`result.json`；`pilot_001/train-rl/result.json`；`pilot_001/evaluate/receipt.json` |

源码重点：`scripts/experiments/g31_ics_circulation/` 下的 `foundation_native_environment.py`、`foundation_learning_data.py`、`foundation_ranker.py`、`foundation_budgeted_provider.py`、`foundation_budgeted_probe.py`、`run_learning_pipeline.py`，以及原 `live_obligation_owned_initial_provider.py`、`live_obligation_component_compatibility.py`、`live_obligation_online_initial_dispatch.py`。对应专用测试在 `tests/test_g31_foundation_*.py` 与 `tests/test_foundation_learning.py`，具体命令／收集范围见最终测试 plan，不把通配文件数当测试数。

历史边界：`docs/g31_ics_circulation/LEARNING_READINESS.md`、`NEXT_ACTION.md`、`REPAIR_METHOD_BOUNDARY_20261017.md`、`COMPONENT_COMPATIBILITY_CONTRACT_20261017.md`、`GPTPRO_100MS与多时间尺度预测调度审阅请求_20261017.md`；新任务书原始文件名为 `G31_ICS_CODEX_FOUNDATION_LEARNING_20261017.md`。历史 21 格／42 initial 结论应追溯原审计，不用本轮三次机制场景会话替代原分母。
