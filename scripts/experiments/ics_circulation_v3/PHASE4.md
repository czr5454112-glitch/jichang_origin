# Phase4：动态更新与循环耦合起步

本轮依据用户提供的 `docs/ics_circulation_v3/phase4_external_review_20261009/` 审核继续实施。冻结审核对象为 `030493a399cdcac3fc005fe2f2cd8ec30fc96277`，本分支从交接提交 `8ccc195672b2cd331a384f3da0d5d95b78c54b3f` 开始。文档内容是需求与审查材料；外部探针及历史结论均经实际代码核对，不把作者自检当成本机执行。

当前完成 W0 入口保护和 W1 主要单所有者接口，W2 只完成同控制构造与持续循环机制。W2 的多所有者共享时钟、强联合控制参照以及 W3/W4 尚未完成。完整结果和证据路径见 `outputs/reports/ics_v3_phase4_progress_20261009.md`。

## 运行入口与数据身份

所有以下命令在仓库根目录执行，输出目录必须不存在或为空；不要复用已产生结果的目录。

```powershell
python -m scripts.experiments.ics_circulation_v3.run_phase4_routing --output outputs/experiments/ics_circulation_v3/phase4_routing_replay_new
python -m scripts.experiments.ics_circulation_v3.run_phase4_semantics --output outputs/experiments/ics_circulation_v3/phase4_semantics_replay_new
python -m scripts.experiments.ics_circulation_v3.run_phase4_coupling --output outputs/experiments/ics_circulation_v3/phase4_coupling_replay_new
```

`experiment_protocol.py` 提供输出拒绝覆盖、集合清单和源组复用记录。原有十个 run 入口及南宁路由 benchmark 使用输出保护；`audit_nanning` 默认用包内地图并独占创建输出文件。输出保护不等于多进程事务锁。

完整 `development / reproduce / fresh-confirmation` 生命周期只接入 `run_scene_configuration`，没有宣称所有历史实验入口均改完。复现需要显式历史协议/清单，恢复其源组、数量和种子，新增独立样本为零；新确认要求新的验证/测试源组，训练复用另行申明。ID 注册不能检测改名后的同一数据或未登记的历史使用。复现旧算法请使用旧提交，不能把当前源码重跑称作字节一致的旧表复现。

## 动态路线与参考域

`RegionalCandidateGenerator(dynamic_local=True)` 按到达宏锚点时的资源日历搜索多个区内时间化见证。Phase4 服务和统一控制构造显式启用它；类的默认值仍保留旧单见证行为，便于历史复现。容量零表示未来入口关闭，负容量非法，不把关闭边偷偷改成可用边。

局部候选先验证终点，再在共享预算内最多探测 `4 * local_label_limit` 个有效标签，按物理路径和时间窗分配有限输出配额。输出 K 与局部上限没有为修复反例调大。该方法有截断，不能声称一般候选域完整。冷启动预处理计入协作式预算，仍无硬实时保证。

`routing_reference.FullGraphReferenceGenerator` 提供全图事件搜索；`integer_ticks=True` 提供有限整数时域枚举，允许等待和循环。最早到达证书针对完整 `whole_route` 资源见证；物理路径覆盖结论还要求队列完整耗尽且没有标签截断。它不是 next_edge 最优性证书，也不是多任务联合控制精确参考。

当前两个规划器仍读取全局资源日历，包括跨区不可等待链；`remote_calendar_access=True` 明示这一权限。`partition_observation.py` 新增可分区的观察接口，但尚未接入分布式规划流程。

## 后缀替换协议

`RouteRequest.intent` 有四种语义：

| intent | 含义 |
|---|---|
| `ensure_route` | 兼容旧入口；已有有效承诺则保留 |
| `new_route` | 申请新承诺，不替换已存在路线 |
| `keep_valid` | 只检查、保留现有有效承诺 |
| `update_suffix` | 显式申请替换可修改的未执行后缀 |

更新需在权威 `Snapshot.replaceable_trays` 中明确授权；默认空元组，拒绝修改。只支持带袋、非保护、无已接纳空盘义务、非旧在途盘。`prepare_replacement` 冻结已进入边以及直到首个可等待点的不可等待链，生成脱离原状态的规划视图；真正物理时钟和托盘位置不前进。

规划与授权可在未来安全锚点计算，特征与策略评分必须读取请求的真实观察时刻，避免未来消息提前暴露。`replace_suffix` 对源版本、状态指纹、身份、已冻结段、候选预约和不变量完成复验后一次发布；失败不释放旧资源。未知 intent 在所有者边界也被拒绝，不能绕过服务前端。幂等请求指纹含 intent/reason；丢失回执后重试不二次提交。

`updated_route_success` 和 `suffix_update_failed_old_route_kept` 独立记录；回执丢失即使所有者已提交也先计 `communication_failure`，恢复记录另列。

## 条件释放与权限

`ConditionalRouteForecast` 独立保存完整见证、剩余段、预计卸载/可用时刻、来源版本、依赖、修订链和失效原因。安全前缀提交不再抹掉其余路线的预测；执行、故障、模块变化或新合法承诺会修订/使其失效。失效预测不会自动复活。

`known_supply` 仍只提供确定供给；`conditional_supply` 提供单独标记的条件预测，不重复确定供给。条件预测不能作为空盘导出的权限凭据。`ConditionalTimedAnalyticEvaluator` 可用它评分，但候选自身盘需先排除再加入自己的释放，避免重复。

`actual_action_key` 包含实际提交前缀及会留存、影响后续评分的条件见证/依赖；诊断候选 ID 不构成不同干预。相同前缀但不同保留预测可以有不同 key；必须另查是否真正改变后续行为，不能靠候选数量证明学习机会。评分日志记录预测值差异，同时明确尚未测得真实继续价值差异。

## 同一继续控制入口

`phase4_control.ControlSpec / build_engine` 统一候选生成、路由选择、预测预调、反应式派发、执行模式、协调顺序及独立慢周期。控制合同记录信息集、继续控制和完整已声明实现依赖哈希，包含实际参与动态搜索的 `routing_reference.py`。内置评分器与慢层都按真实观察时刻过滤发布时间；未来事件带只交给仿真引擎。外部回调的 manifest 是调用方声明，不是任意代码无泄漏的证明。

checkpoint 保留慢层相位；43 次引擎包装回调中只有22次实际慢触发，两者分别计数。此入口供以后标签与部署共享，本轮没有重新生成学习标签或训练模型。

三个持续场景含有限盘重复使用、保护任务 burn-in、长边、不可等待点和资源竞争。它们是开发机制例，反复修正及重跑均新增零个独立源组。盘充足例同时增加 B 的库存与容量，不是单因素消融。观测到节点满容量本身不证明回压；实际 J-B 占用差异和后续载盘见证变化才是本轮耦合证据。

## 接下来须补齐

先做两资源所有者、共同物理/消息事件时钟及延迟期间的合法更新，接入分区观察；再做同权限的有限小规模联合精确参考、滚动 MPC 和一轮真实路由—预调反馈。将候选覆盖、无动作/无价值差异和真实决策机会分开统计。之后才在同一预测控制下做 paired-direct/residual、2/8/32 未来样本标签稳定性及冻结后独立确认。南宁连续业务流、现场参数和生产时限验收仍需独立完成。
