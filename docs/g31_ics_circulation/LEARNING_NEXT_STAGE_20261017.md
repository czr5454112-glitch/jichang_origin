# G31：真实后续动作、兼容预算与首次后续价值学习

日期：2026-10-17。起点提交：`da8d39ed4e36b6db31e3a7a6b17b0f73b85eed9a`。

本轮按用户“请开始”及随后“不降低要求、核对历史、围绕整体目标”的要求实施。依据是用户提供的 `G31_ICS_REVIEW_da8d39ed_LEARNING_NEXT_20261017.md`，SHA-256：`86cb48f19d9e42ddcb35eda81cf0cebdfd1a941b707e26026a09ce23d1121658`。该审阅是方案与待验证判断，不直接当成实验结果。

**结论：完成真实 later 评估接口、兼容预算修复、6 条新原生数据的监督价值更新及冻结模型的新 episode；没有完成受保护非默认接管、多步 RL、动态局部修复或机场规模验收。** 所有执行为 `offline_sync`。本轮未提交、未推送 GitHub。

## 1. 不变的目标与历史约束

- 最终目标仍是考虑有限托盘循环的区域去中心化 ICS。R1 路由与 R2 释放预测、提前返空需要形成实际反馈，而不是仅提高保存表排序分数。
- 原逐件保护参考保持不变，零容忍，不把新 incumbent 或平均回报替换原参考。预测与实际库存、原生命令和接收承诺严格分开。
- 同一托盘的装载、卸载、Storage、返空、再装载仍走原生执行、FIFO/headway/capacity 和接收裁决。不改拓扑、容量或底层运行时策略制造改善。
- 完整必要请求 ≤100 ms 目标未降低。不能把小网络推理时间当完整请求时间。
- 已核对历史 `live_obligation_recollection_native_v2_prepare_001/branch_ledger.json` 中 04/05/06/07、12/13/14/15 的负结果。本轮没有重复旧 96 分支穷举，而是用新接口做最小真实配对，并保留相同负结论。
- 本轮不改 C++ 物理核心。用户主工作区 `cpp/ics_core/runtime/bounded_local_pibt.hpp` 保持原 SHA-256：`b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。

## 2. 真实 later 观察—模型—动作接口

实现入口：

- `scripts/experiments/g31_ics_circulation/foundation_later_control.py`
- `scripts/experiments/g31_ics_circulation/foundation_later_seed.py`
- `scripts/experiments/g31_ics_circulation/foundation_native_environment.py`
- `scripts/experiments/g31_ics_circulation/foundation_later_episode.py`
- `scripts/experiments/g31_ics_circulation/foundation_later_campaign.py`

新 `later_actor.v1` 只给 actor 当前本地观察、真实已送达的 v3 消息及身份/新鲜度、本方 outbox。保留原 v1 观察语义。v3 原始状态是 `conditional`，送达由实际 `delivered_at` 和能力链验证，不伪改为 `delivered`。

真实 `NativeCollectionAttempt` 仍由执行侧持有，actor 只返回绑定当前事件的 candidate ID。提交前再验证 collection、owner、时刻、目标托盘、generation/在途状态和本方已发动作；没有“拒绝后偷偷执行 retained”的回退。每次新 actor 回调另记录前后 native SHA 和物理时钟相等，hash 不提供给 actor。

新 seed 从合法 evidence 重新验证当前生命周期，保留完成前缀、在途 entry/退出推导、装卸/Storage 服务边界、当前资源占用、ACK 和适用的已发偏好。只替换成熟条件物理模型的初始播种段，复用原事件循环；不删除 initial guard，不读取隐藏原生事件堆，不把 `FutureLaterFork` 改名。空 FIFO/无 pending 只在现有完整窄域验证成立时允许，未覆盖状态明确 unknown。

支持动作：A `return_now / return_not_before_7_84`；B `native_default / prefer_8`。A 的延迟是绝对不早于 **7.84**，不是 `now + 0.5`。B 默认是 no-command，不等于强制走 3，也不清除已安装偏好。

### 新原生配对结果

全部同一机制域、相同输入、H=40；每分支独立 Windows Job 硬限 150 秒，无自动加时。

| 新分支 | A 动作 | B 动作 | reuse1 相对默认完成差 | reuse2 相对默认完成差 | 其余三件 | 定性 |
|---|---|---|---:|---:|---:|---|
| guarded_default | 立即返空 | 默认 no-command | 0 | 0 | 0 | 原默认保护通过 |
| diagnostic_prefer8 | 立即返空 | prefer_8 | +0.9 s | +0.9 s | 0 | 原逐件门拒绝；仅隔离诊断 |
| diagnostic_absolute_return | 绝对不早于 7.84 | 默认 no-command | +0.09 s | +0.09 s | 0 | 原逐件门拒绝；仅隔离诊断 |
| guarded_learned_value | 冻结模型选立即返空 | 冻结模型选默认 | 0 | 0 | 0 | 两点各仅一项 enabled，无学习业务收益 |

关键因果证据：

- B 配对在 9.69 选择前的 **95 条完整 receipt 精确相同**。默认没有命令/ACK，L 在 10.15 走 7→3；诊断命令 `live:1:B:later-route-0` 的 ACK 为 updated，9.72 送达，L 在 9.75 实际进入 7→8。两次复用均被推迟约 0.9 秒。
- A 配对在 7.34 选择前的 **66 条完整 receipt 精确相同**。请求的 earliest_departure 确为 7.84，L 在 7.94 走 6→7，10.04 收到，ACK 在 10.09 送达。
- A 延期后，B 的新实际决策点变成 **10.22**，不是保存的 9.69。新 current seed 预测默认完成 13.14/18.55，仍对原 13.05/18.46 参考判拒绝；没有刷新参考抹掉退化。
- 每个 episode 都记录 A→B 的真实 next observation、非等间隔 Δt、terminal/truncated、命令/ACK、下一 EDGE_ENTER 和同 L 的后续再利用。默认分支与上一阶段全部 input/receipts/jobs/trays 精确一致。
- A `return_now` 的预测以未来 B 默认为条件，**不能声称它也准确预言了后来改成 prefer_8 的诊断终态**。这一条件与实际结果分开保留。

任务 1 当前验收范围是“真实评估能力与严格拒绝”，不是“已找到通过保护且改善业务的新后续动作”。两个非默认动作的实际状态差异存在，但仅发生在明确标记的隔离诊断中。

## 3. 兼容域前置与前缀预算

修改既有 `foundation_budgeted_provider.py`，新增 `foundation_compatible_probe.py`，没有重写 provider。公共 mask 在评分与昂贵推演前执行：A 仅 04；B 为 `[0,1,4,5,8,9,12,13]`。候选预算与 prefix 预算分开；增量成本规则是新 prefix 1 单位、suffix 1 单位，不伪称毫秒模型。

`foundation_budgeted_probe.py` 的 exact parity 改为规范 JSON/类型敏感比较参与通过，新增 bool/int 等负例；不推翻历史未篡改预测本身的相等性。

新真实同 B context：五种方案先执行，之后才有同信息 full32 教师；旧线性/MLP 固定为 mechanism-heldout 模型，未看新结果后调参。

| 方法 | 实际候选 / prefix | 最终兼容建议 | 兼容域条件 regret | provider through-seal |
|---|---:|---:|---:|---:|
| 兼容 8 穷举 | 8 / 4 | 12 | 0 s | 3127.44 ms |
| 规则 K4/P2 | 4 / 2 | 04 | 0.119 s | 2140.35 ms |
| 增量前缀成本 K4/P2 | 4 / 2 | 04 | 0.119 s | 2166.73 ms |
| 冻结线性 K4/P2 | 4 / 2 | 12 | 0 s | 2191.97 ms |
| 冻结 MLP K4/P2 | 4 / 2 | 04 | 0.119 s | 2167.97 ms |

五路 24 个 requested prediction 与 full32 对应项严格一致；未请求项没有 prediction。K8 实际 4 个 context、8 次 suffix fork/resume、17 次 proof；每个 K4 为 2/4/9。full32 through-seal 9832.88 ms。

这些计时包含 provider 内必要检查，部分内部计时嵌套，不能相加。表格不含 callback 前采集、模块/模型加载、后置 teacher、实际提交/ACK，也不含表格边界之外的结果落盘。固定顺序单 context **不证明速度优越、泛化或实际业务改善**。实际 A/B 仍执行 04，完整原生轨迹保持基线；新线性结果仅说明本次紧预算条件质量优于所列规则。

## 4. 已实际执行的学习，而不是只加入口

新增 `foundation_later_learning.py` 和统一 CLI 的 `train-later-value`，配置 `configs/g31_ics_circulation/learning_next_value_v1.json`。旧初始 43 维 ranker 不变；新 later 使用独立 schema 的 **52 个合法状态/动作特征**。

- 训练来自上述前三个新闭合原生 episode，共 **6 条真实动作数据**，其中 4 条属于诊断行为。拒绝而未执行的候选没有伪造反事实标签，未完成 -1 不转换为零成本。
- 标签是观察到的未完成业务的实际终态剩余完成时间均值；有限 episode、不折扣，Δt 单独记录。标签、guard 模型分数和终态真值不进入 actor 特征。
- CPU ridge，alpha=1，真实拟合与冻结 checkpoint 已完成。训练约 0.0807 秒；训练窗口检查 30 秒，外层进程硬限 60 秒。
- checkpoint SHA-256：`2ef12fa029fbc38719114276d8e9e723958fb21b9da2c5f139ccb0c9ec2eb979`。训练内 MSE 为 0.0175813534 s²；这是重代入拟合误差，不是收益或泛化指标。
- 三个确定性干预只有 **1 个独立场景**。没有伪造训练/测试独立样本数，没有场景外验证结论。相同 A 观察和动作可能因后续 B 行为不同而具有不同终态标签；这里学习的是记录行为下的继续价值，不能解释为孤立 A 动作的因果价值或目标策略 Q 值。
- 冻结后另跑了第 4 个新原生 episode：两个合法推理值分别 6.1191455712、3.6111906102，推理记录约 0.421/0.304 ms；两个位置各只有一个默认动作通过门，完整物理结果与基线一致。因此不能把推理接入成功称为策略改善。
- 独立脚本不导入项目 learner，重提取全部 52 维特征、重新计算 ridge 均值/尺度/截距/系数与新 episode 两次推理，全部一致。

实际运行 `train-rl` 的新证据审计：三个 episode 各有 2 个实际时序点，但有多个受保护候选的决策点均为 0、受保护执行的非默认行为为 0。结果保持 `blocked_L1_not_certified`，没有运行或声称多步 RL。这是任务书允许的监督/value 分支，不是通过放宽保护取得“RL 就绪”。

## 5. 失败保留与回归

1. 首轮三个分支的前两个成功，第三在创建 native 会话之前因 Windows source 归档路径过长失败，4.469 秒即停，未超时。
2. 修复 `archive_sources`：归档使用短索引文件名，原绝对路径、字节 SHA 与归档映射完整保留；原接受器继续逐文件验证。没有删除来源绑定、改变物理逻辑或提高时限。
3. 新计划明确只补跑 `diagnostic_absolute_return`，仍 150 秒；前两个成功分支不重复。原失败 campaign 保留 unknown，不改写成成功。训练 manifest 显式引用两个原闭合 receipt 和一个补跑闭合 receipt。
4. 最终 **699 项测试、0 fail/error/skip**，pytest 100.791 秒，完整子进程 102.875 秒 / 180 秒硬限，697 个来源 pin 保持不变。
5. 中间 696 项全通过记录保留；归档修复后第一次全量的 1 个失败是测试夹具自身源文件路径过长（发生在被测函数前），缩短夹具后重跑最终全量。其失败 XML 未覆盖。

## 6. 证据入口

以下路径相对于工作区 `C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`。统一实验前缀：`outputs/experiments/g31_ics_learning_next_20261017/`。

| 内容 | 前缀下路径 |
|---|---|
| 五路兼容域 live | `task2_001/live_001/worker_report.json`、`receipt.json`、`callback_complete.json`、`native/raw.json.gz` |
| 兼容域独立核查 | `task2_001/independent_live_review_001.json` |
| 新默认 / B 诊断原生 | `later_episodes_001/guarded_default/episode/native/`、`later_episodes_001/diagnostic_prefer8/episode/native/` |
| 保留的长路径失败 | `later_episodes_001/diagnostic_absolute_return/worker_report.json` |
| A 补跑原生 | `later_repair_001/diagnostic_absolute_return/episode/native/` |
| 六行源 manifest | `later_native_training_manifest_001.json` |
| 实际数据 / 模型 / 学习报告 | `later_value_001/train-later-value/models/rows.json`、`checkpoint.json`、`report.json` |
| 冻结模型新 episode | `later_frozen_evaluation_001/guarded_learned_value/episode/native/`、同分支 `worker_report.json` |
| 后续物理与学习独立核查 | `independent_later_review_002.json`、`verify_later_evidence_001.py`、`verify_later_learning_001.py` |
| 基于新数据的 RL 未就绪 | `later_value_001/train-rl/result.json` |
| 最终完整回归 | `final_validation_003/tests.xml`、`plan.json`、`receipt.json` |

每个 native 目录含不可覆盖 raw、closed acceptance、原生 receipt、来源哈希/归档和输入。请先读独立核查与 receipt，不需要重新运行旧 96 分支或全机场长时域实验。

运行入口可通过各模块 `--help` 查看。新 native 使用 `foundation_later_campaign --prepare --output <新目录>` 后 `--launch`；单分支补跑在 prepare 时显式 `--only-branch`；冻结评估在新的 prepare 中使用 `--evaluate-checkpoint`。训练使用 `run_learning_pipeline train-later-value --config <新run_id配置> --dataset <真实episode manifest>`。已有输出目录不可复用。

## 7. 尚未完成及下一步判据

1. **不是完整新方案全部完成。** 任务 1 已有真实评估/执行接口，但尚无通过保护的非默认后续改进；任务 2 的最小 live 对照完成；任务 3 仅完成允许的首次监督更新及新原生推理验证。
2. **100 ms 未达。** 新默认 A/B 的采集到 offer 墙钟约 860/926 ms，其中模型与保护约 738/803 ms；前者已经包含后者，不能重复相加，也尚不覆盖全部 wrapper/提交链。小网络亚毫秒不能掩盖必要计算超标。本轮也未新增峰值内存和跨独立场景的 p95/p99 计量，不构成完整性能指标验收。
3. 当前只在两个支持的真实切点重算，不把每次 retained activation 算新预测/学习动作。跨事件预测缓存、固定间隔与事件刷新三组对照、服务依赖范围内的局部后缀修复 **尚未实现与验证**。下一步应围绕本次 A→B 真实服务/到达变化建立来源与失效条件，对照完整后缀 warm-start 与普通后继闭包；若影响范围扩到全域，应报告无局部性收益。
4. 在不改原图容量/拓扑、不扩大托盘库存、不丢业务的前提下，寻找自然需求/冲突差异产生的受保护有效选择。必须先有通过逐件门且实际改变轨迹的非默认实例，才推进真正多步 RL；不再仅对这六条记录反复调网。
5. 原机场 151 节点/227 边、既定负载规则、零容量边 ICS103→ICS104 通行/存储语义和实际 EBS 映射仍未验收。本轮 CPU 运行，不声称使用 4070/5080 训练或完成机场规模。
6. 本轮新增证据是工程接口与有限域实测，不新增文献原创性保证。服务依赖边界与严格逐件保证的论文贡献仍需后续方法和公平对照支撑。
