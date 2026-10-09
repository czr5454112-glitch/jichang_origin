# ICS V3 第二阶段运行说明

本阶段在独立目录内继续实现了可恢复仿真、单步干预、门点候选路由、预测预调和轻量价值模型。原 G31/native/Java 未修改；第一阶段 Python 源码保存在 `outputs/experiments/ics_circulation_v3/phase1_source_20261009`，第二阶段首次发现问题时的版本保存在 `phase2_discovery_source_20261009`。

## 可复现命令

从仓库根目录运行，仍使用已有 Python 和 NumPy：

```powershell
$icsV3Tests = Get-ChildItem tests -Filter 'test_ics_circulation_v3_*.py' -File | Select-Object -ExpandProperty FullName
python -m pytest $icsV3Tests --basetemp .tmp/ics_v3_tests

python -m scripts.experiments.ics_circulation_v3.run_routing_comparison --scene-count 24 --repeats 3
python -m scripts.experiments.ics_circulation_v3.nanning_routing_benchmark --od-count 100 --partitions 4 8 16
python -m scripts.experiments.ics_circulation_v3.run_prebalance
python -m scripts.experiments.ics_circulation_v3.run_joint_control --groups 24 --output outputs/experiments/ics_circulation_v3/phase2_joint_corrected_20261009
python -m scripts.experiments.ics_circulation_v3.run_phase2_learning --evaluation-namespace confirm1 --output outputs/experiments/ics_circulation_v3/phase2_learning_confirmatory_20261009
```

学习入口 `--smoke --output <new-directory>` 可缩小到 8/4/4/4 个源场景。正式为 80 训练、20 验证、40 候选测试和另外 40 部署场景；不要用 smoke 代替正式结果。旧 `phase2_learning_20261009` 和 `phase2_joint_20261009` 为修正预测生命周期前的发现结果，保留作审计，不覆盖成成功证据。

## 仿真与授权接口

`Simulation(snapshot, future_bags, route_mode='next_edge', generator_factory=..., route_selector=..., slow_controller=..., reactive_empty_dispatch=True, coordination_order='route_then_prebalance')`：

- `advance(t)` 停在 t 时刻物理/外生事件完成、常规控制尚未执行的边界；`observe()` 完成 FIFO 装载并返回隔离的可见快照。
- `checkpoint()` / `from_checkpoint()` / `fork()` 保存并复制完整账本、已消费到达、在途动作、成本、事件阶段和策略状态。未来轨迹只保存在引擎内，策略只收到 Snapshot。
- `intervene(candidate)` / `branch(candidate)` 先验证完整合法见证，再执行首个可等待节点之前的最小安全前缀；不可等待链不能在中间截断。中间节点不卸载、不执行终点 hold。
- 硬保护载盘保守保留**完整**路径资源承诺，不采用自由逐边重算；两种顺序都先请求其授权。无法接纳时保留任务并记录失败，不把 protected 字段本身当成必然完成证书。
- 非保护任务可在下一个安全节点重新选择，迟到进入统一目标。已进入边、已接受空盘调拨目的地和供应方代理的导出底线不能由策略改写。
- 慢控制器在隔离快照上产生提议；运行器比较变化并再次调用资源所有者复验，不接受任意库存/模块修改。

两种顺序只调换非保护载盘路由和预测预调的先后；FIFO 装载、保护任务优先、反应式空盘调拨及其他权限相同。没有据实验结果偷偷给某个顺序更宽的约束。

## 区域候选

`RegionalCandidateGenerator` 以 control_partition 为已给标签，生成门点宏边及静态物理路径见证，用非负反向 Dijkstra 下界搜索，再做预约感知时间细化。完整候选仍由同一 ExecutionValidator 验证。候选数、展开数和可选墙钟预算均有限；partial/exhausted 不代表真实不可行。

每个区内宏边目前仅保留一个静态最短见证，可能漏掉因动态预约才有价值的同区替代路。控制分区尚不代表独立机器、私有状态权限或实际通信协议。南宁基准只检验真实拓扑上的纯路由代理，没有并发业务流和网络延迟。默认关闭原图记录 capacity=0 的边，必须同时披露其导致的不可达 OD，不能静默提升容量。

## 预测预调

`PredictivePrebalancer` 用真实盘的首次已知可用事件、旧在途和已有承诺匹配累计需求，保护源节点/源区前缀库存；只提交有向网络上可接收、可导出的空盘。它是有预算的贪心策略，不是全局最优 MPC。

已接受的多段空转移若最终 ETA 未知，单独作为调拨义务防止重复发盘；不能将中间安全停靠点的到达误写为最终可用盘。此保守处理可能错失合法替补，是当前能力边界。

有明确 `unit_ids` 的需求按可见到达记录消费。超过预计时刻但未观察到的身份仍是 pending，直到到达、已发布新版本明确取消或预测 TTL 结束；名义时间不等于取消。先取最新已发布版本，再处理取消/过期，防止旧版本复活。普通聚合预测没有身份映射时不能伪造精确消费。样例 TTL 是合成参数，现场仍需定义真实消息和业务规则。

## 学习与统计协议

`TimedAnalyticEvaluator` 在首次库存近似上加入已发布 OD/截止期以及候选的时间化共享边影响，仍忽略未来任务之间的竞争、重复循环和完整远期传播。与旧库存近似并列保留。

`RidgeValueModel` 是线性小模型，分别拟合完整成本和“成对增量减解析增量”。两者用完全相同的可见特征，均能读取解析分数，均通过相减保持基准零点。只在训练源场景上拟合归一化；只在验证源场景上选 ridge 强度。没有训练 MLP，也没有把本实现称为 PPL/DG-PG 原算法。

标签来自先运行到 tick 2 的真实可达中途决策状态，再对 4 个候选、2 条共同未来执行首个安全前缀干预；之后用同一固定因果继续控制器。80/20/40 源场景产生 1,120 次分支回放。另外记录 560 次基于公开预测的参考回放，不能隐去这些额外计算成本。

部署使用另外 40 个源场景和固定的另一外生种子，6 策略完整执行 240 次；预测回放策略中的嵌套模拟次数另记。模型在部署前冻结，部署失败轨迹不回流训练。20/40/80 场景曲线为预定对照，每个规模仍只按验证集选参数，不按测试曲线重选最终模型。

由于首次联合测试发现预测生命周期错误，修正后的最终测试与部署采用 `confirm1` 命名空间生成全新源场景。训练和验证来源保持一致；原联合场景复跑属于回归验证，不能称为新泛化证据。所有数据仍来自同一七节点合成拓扑族，不能外推跨机场或真实运营日。

## 仍待完成

真实供应方空盘模块、物流/控制权限和时间戳消息契约，已确认初始盘/库容/服务参数，真实流量下的区域通信与故障恢复，严格逐件不增时保护，以及南宁整套有限盘动态业务验收。现有纯路由时延不能代替这些验收。
