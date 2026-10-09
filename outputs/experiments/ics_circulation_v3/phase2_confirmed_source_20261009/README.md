# ICS V3 有限盘循环机制原型

**本页保留第一阶段说明。第二阶段已增加可恢复仿真、单步干预、门点候选、预测预调和轻量学习对照，当前接口与运行方法见 [PHASE2.md](PHASE2.md)。**

本目录是 2026-10-06 V3 需求的首阶段实现，用来检查循环状态、资源权限、候选增量成本和配对标签是否有明确对象。它保留旧 G31，不依赖 native 构建，也没有改动旧基线。当前为六节点、两个物流区、四个控制分区标签的**合成代理实验**；分区标签尚未实现区域独立状态和通信。

## 运行

在仓库根目录执行，使用项目已有 Python 3.11；不安装额外依赖：

```powershell
python -m scripts.experiments.ics_circulation_v3.run_pilot
python scripts/experiments/ics_circulation_v3/audit_nanning.py --profile .g4irsf24_worktree/data/processed/maps/nanning_airport_profile.json --output outputs/experiments/ics_circulation_v3/nanning_data_audit.json
python -m pytest tests/test_ics_circulation_v3_runtime.py tests/test_ics_circulation_v3_evaluation.py tests/test_ics_circulation_v3_nanning.py --basetemp .tmp/ics_v3_tests
```

`run_pilot --output <directory>` 可另存实验；默认运行 24 个初始条件 × 3 个合法候选 × 4 条共同外生轨迹，即 288 次分支回放。额外三类反例单独执行，不计入这 288 次。所有分支共享同一初始盘集合、同一固定模块和同一因果继续策略。噪声由场景、对象、字段和种子索引，改路不会改变随机数消费顺序。

## 代码与接口

| 文件 | 职责 |
|---|---|
| `model.py` | 分开的 Tray/Bag、节点/有向边、旧在途、固定局部模块、版本快照、RouteCandidate |
| `runtime.py` | 有限预算的时间标记路径搜索、资源所有者复验和提交、固定 FIFO 继续控制及实体循环 |
| `evaluation.py` | CirculationFootprint、AnalyticDeltaEvaluator、PairedRolloutLabeler、可关闭的 ResidualCandidateScorer |
| `scenarios.py` | 明确合成的 24 个初始条件、独立发布的需求预测和仅供事件引擎读取的未来真值 |
| `counterexamples.py` | 卸载后尚不可用、相同库存不同在途、共同资源不能重复消费的可执行见证 |
| `audit_nanning.py` | 只读核对真实拓扑及来源哈希，报告缺失业务参数；不静默修补零容量边 |
| `run_pilot.py` | 运行、计时、记录全部候选和分支、导出结果与源码哈希 |

## 物理语义与明确限制

- 时间为整数 tick；合成边采用单位速度，空盘运输成本中的 `empty_distance` 等于新进入边的长度（数值等于该边旅行 tick），不是机场米数。已在途的过去成本为分支共同常数，不重新计费。
- 空满盘走同一有向图；身份集合守恒，缺盘时行李保留在入口队列。装载在本版为零时长，卸载与后续 hold 分开；接收资源保守地覆盖卸载和 hold。
- 已在途状态具有具体边与剩余时间。源端仅允许静止托盘发起新路线；已接受整条路线保守冻结到完成，不能撤回已进入边或偷改既定计划。尚未支持真实在线未执行后缀改路。
- 候选生成是有时间标记、简单路径约束和展开预算的统一代价搜索（A* 的零启发式特例），**尚非区域门点 A* 的全程编解码实现**。搜索耗尽、有限模型搜索结束与真实不可行不混用。保守末端长期占位可能排除可协调的可行解，不主张完整性。
- 每个事件检查身份、边/节点/接收容量以及预约；半开时间区间允许资源在同一 tick 释放再使用。提交由单线程资源所有者序列化、复验版本和容量。此处没有分布式网络事务实现。
- 固定局部代理采用 FIFO 装载、最早可行路由和已到达需求触发的空盘转运。`export_min_stock`、接收容量和 hold 规则不会被评分器改变；**没有预测式主动预平衡，也没有供应方原模块集成**。
- 合成初始状态全部可观察。真实未来仅在事件引擎中按时注入，不交给控制器。区域部分可见性、摘要通信、过期消息、实际模块私有状态仍待实现。
- 候选保护目前为逐件截止期，尚未实现“严格逐件不增时”模式；模型之外的故障恢复仍待实现。

## 标签、解析近似与学习门槛

本轮标签是**整条路线承诺后的有限时域成对成本**。它比 V3 推荐的单步/下一边干预更窄，不能把本轮结果当成任意快照、任意后续改路策略的 Q 值。继续控制器固定，真实回放排名只作离线候选集内参照。

共同成本为：`tray_wait + nonprotected_tardiness + 0.1*empty_distance + 10*terminal_backlog + 2*terminal_inflight`。等待累计到装载或时域末尾；迟到对未完成任务截断到时域末尾；所有未完成行李计入终端积压，运动中的托盘另计在途惩罚。已载盘未完成任务可能同时贡献积压和在途项，这是显式终端处理。

解析评分使用同样权重，但只做一次可用空盘供给匹配，预测后续空盘运输和下游迟到为零，忽略再循环和后续路径竞争。因此解析与回放的差是明确的模型近似误差，不能解释成安全余量。δo 直接采用执行授权的资源区间差；δR 按真正 usable 时刻计算。

残差接口实现 `ΔJ_ana + f(features(a)) - f(features(a0))`，基准严格为零。默认关闭，没有拟合权重，不安装 MARL 框架。本轮仅报告候选空间、排序误差及可观察场景因素之间的描述性关联；没有训练/验证/测试划分、泛化或低样本优势结论。将来同一源场景全部快照和分支必须同组划分。

## 结果文件

默认输出到 `outputs/experiments/ics_circulation_v3/pilot_20261009`：

- `summary.json`：分母、结果、成本权重、局限、机器环境和源码 SHA256。
- `candidates.jsonl` / `candidate_results.csv`：每个候选的解析增量、平均成对标签、残差、可见特征、路线和 footprint。
- `rollouts.jsonl`：全部分支成本分项、未完成/等待 ID、约束检查次数与回放耗时。
- `scenes.jsonl`：可复核初始状态、预测、与特征隔离的未来轨迹。
- `timings.jsonl`：生成、特征、评分、复验、提交及本地完整请求时间；网络/排队端到端字段为 `null`。
- `scene_results.json` / `counterexamples.json`：场景级候选选择结果和三类反例。

这些计时仅覆盖本机合成小图，不能通过网络推理耗时或该小图的请求耗时宣布真实机场 100 ms 达标。南宁原图只进行数据审计，未用于这 288 次回放。

下一阶段先补原状态的中途快照/下一边干预和循环预测接口，再独立推进区域路由与主动预平衡两条验收；在相同可观察信息和候选集内比较改进解析模型、直接成本拟合、解析加残差。当前共享通道误差也可能用更好的解析模型消除，不能据此断言需要神经网络。
