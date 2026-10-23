# GPTPro 审阅清单：成熟 G31 等待评分与双地图 1x 对照

请审阅本次增量实现、测试及两张地图的独立实验，不把讨论文本当作已核验事实，也不要沿用已撤销的微观输送模型结论。本轮保留成熟 G31/S4/J2/PIBT，双方均不新增线路容量；只运行载货任务，不测试空托盘循环。

本清单给出核对标准，**不代替实验完成回执**。南宁与 map2 的完成状态、数值、命令、输入和二进制哈希，以各自实验目录的 manifest、summary、逐段结果和比较审计为准。若某份结果或校验缺失，应明确列为缺项。

## 1. 先确认实际改动

- 默认必须仍为 `s4_wait_estimator="legacy"`。`eta_calendar` 和 `eta_flow` 是可选候选，没有自动替换成熟基线。
- **旧 G31 已有 ETA 日历等待**：在 `now + travel` 查询目标服务日历，正式配置已打开直接合流邻居日历可见性。本次不能称为首次加入 ETA。
- 正式 R3 无 corridor 日历，入口等待为零。此配置下 `eta_calendar` 的主要消融是去掉旧 `Q + I` 计数压力；不能把它的收益归因于新增的日历读取。
- `Q` 是节点完成服务后等待下一跳的队列。新模式应替换旧 `Q + I`，并把目标操作前的日历等待与操作后的出流等待分开；不得把相同计数再加一遍。
- 检查恒速 `length / speed`、基础 `service_duration()`、J2 许可、事件热路径、原子 PIBT 提交和失败回滚未因新评分被改写。多路线导致经过的节点数量不同，可以改变总服务量；这不等于单次服务时间被拥堵估计拉长。
- 评分状态和未结算预测必须进入新模式 checkpoint/replay。旧模式关闭时，不能只比较完成总数；应检查旧二进制与新 `legacy` 的逐段结果和轨迹等价回执。

源码入口：[运行时](../../cpp/ics_core/runtime/event_driven_junction.hpp)、[纯估计辅助函数](../../cpp/ics_core/runtime/s4_wait_estimator.hpp)、[Python API](../../src/czr005/cpp_backend.py)、[独立 C++ 回归](../../cpp/tests/test_g31_eta_wait.cpp)、[实现及限制说明](S4_WAIT_ESTIMATOR_CANDIDATE_20261023.md)。

## 2. 地图与 1x 任务必须分别绑定

以下数据已直接读取本地规范文件核验。南宁任务是原 map2 任务的 OD 投影，两张地图的任务总量和时间表相同；这不是两份独立采样的客流，也不能混用释放轨迹。本次是固定参数的地图迁移验证：不按 map2 结果重新调参，不据两图结果宣称全局泛化。

| 项目 | map2 | 南宁 |
|---|---|---|
| 规范地图 | `data/processed/maps/map2.json` | `data/processed/maps/nanning_airport_profile.json` |
| 拓扑规模 | 54 节点、69 有向边 | 151 节点、227 有向边 |
| 1x 任务 | `data/processed/tasks/inputdata.jsonl` | `artifacts/tasks/g4irsf31_nanning/nanning_1x_canonical.jsonl` |
| 业务与运输段 | 28,506 业务、43,603 段 | 28,506 业务、43,603 段 |
| 分段构成 | 13,409 direct；15,097 storage_in；15,097 storage_out | 同左，但 OD 不同 |
| EBS 入库终点 | 47 | 53 |
| EBS 出库源点 | 52 | 53 |
| direct 任务终点 | 48、49、50 | 南宁投影后的卸载节点集合 |
| 本轮选定速度 | 全边 2.0 m/s | 全边 2.0 m/s |
| 共同观察窗口 | 8260 至 98259；Java 90,000 个整数周期 | 同左 |
| G31 事件上限 | 60,000,000 | 60,000,000 |
| 工况 | 无故障、无空托盘、不加容量、不筛任务 | 同左 |

map2 官方入口为 [run_g4irsf31_map2_native.py](../../scripts/eval/run_g4irsf31_map2_native.py)，本轮对应 case `t5_2_map2_1x_speed_2`；不要误用默认原始 2.5 m/s、2x 或故障 case。受保护地图读取由 [g4irsf11_fixed_map.py](../../scripts/eval/g4irsf11_fixed_map.py) 校验，规范 LF 文本 SHA256 为 `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63`。原始字节哈希可能受 Git CRLF/LF 转换影响，应区分文本规范哈希与本次运行原始字节哈希。

本轮 map2 包装入口是 [map2_experiment.py](../../scripts/experiments/g31_feng_alignment/map2_experiment.py)，原 Java 入口是 [java_map2.py](../../scripts/experiments/g31_feng_alignment/java_map2.py)。[请求消融审计](../../scripts/experiments/g31_feng_alignment/audit_requests.py)和[结果汇总](../../scripts/experiments/g31_feng_alignment/summarize.py)用于 map2 时须显式传入 map2 的 `--canonical`，不能依赖其南宁默认值。准备函数与 `inspect` 只构造并核验请求，不启动 native 实验。

需要逐项核对：

- Java map2 使用原项目 `map2.txt` 和原始 `inputdata.txt`；G31 map2 使用对应转换后的规范文件。节点通过时间、边长度、方向和任务映射一致，原始文件/转换文件各自留哈希。
- Java EBS 参数显式为入库 47、出库 52、提前行李阈值 4800 秒、出库提前量 2700 秒。南宁的 53/53 不能带入 map2。
- 两端均显式覆盖全边速度为 2.0 m/s。G31 service-aware potential 必须按本次速度重算，不能只改实际边速度而沿用另一速度的势函数。
- Java `max_new_tasks=0`，无前缀截断；G31 请求必须包含全部 43,603 个唯一 segment_id。不能用“可达任务”“成功任务”或两侧完成交集替代全分母。
- 运行到上限仍未完成的段保留为未完成，记录终止原因；不能把 max_events/horizon 终止写作全量完成。
- 同一地图的各 G31 评分臂使用同一二进制、节点/边/势函数、任务 ID/OD/截止时间、事件上限、日历可见性、源配置；只允许声明的评分字段和释放因子变化。
- 不要仅在 Nanning runner 上改输出目录名称。map2 必须调用 map2 官方 profile/request，并在 manifest 中记录 map2 canonical 文件与地图身份。

## 3. Java 对照保留原语义，差异必须可见

原 Java 核心应直接编译原始来源，或给出仓库镜像与原件的一致性回执。GitHub 中可阅读镜像：[Astar.java](../../legacy/jichang_origin_readonly/src/App/Astar.java)、[ICS_PathFinding.java](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java)、[Tasks.java](../../legacy/jichang_origin_readonly/src/App/Tasks.java)、[Map.java](../../legacy/jichang_origin_readonly/src/App/Map.java)。外部观测包装器是 [LegacyIcsNoFaultWindowBenchmark.java](../../benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java)，不是另写一个 HCA 实现。

- 原 Java 采用恒速路程时间、节点预约冲突和失败源侧重试；虽然论文列过线路容量约束，本地原实现没有容量计数，本轮也不增加。论文证据及其版本边界见 [规则审计](FENG_NATIVE_WAITING_RULES_AUDIT_20261023.md)。本地 PDF 未必在 GitHub 包内，不应把本机绝对路径当作远端可读取证据。
- Java 非终点预约端点相等即冲突；G31 接受首尾相接并有 `1e-9` 容差。这次没有改成相同开闭区间，不可称两侧冲突判据完全一样。
- 两侧均到达终点即完成；Java 汇总必须读 `output.txt` 的完成 epoch，不能读 `routes.csv` 名为 `finish_time` 的末节点 `t2`。
- Java 每秒观察一次且每周期逐任务推进一个下一节点报告；G31 记录连续事件时刻。保留这个时间分辨率差异，不把秒级差异全部归因于算法。
- 成熟 G31 对零服务/极短行程保留 `minimum_service_seconds` 下界。例如 map2 源 52 的原服务时间为 0，G31 下界为 0.001 秒；这是既有细节，不是此次评分新增，也不能宣称与 Java 在每个时间数值上完全相同。
- Java 完整路径规划与 G31 逐跳决策保留各自算法。不得将 Java 规划耗时与仅 native 函数调用墙钟时间直接换算成跨语言 CPU 加速比。

## 4. 按正确观察单位读结果

- 主指标为全部 43,603 个独立排程运输段的 `finish - canonical pass_time`，同时报告均值、p95、p99、最大值和完成/未完成数。
- 把源生成延迟、实际入网前延迟、入网后时间分开。Java 的 generator release 与成功规划 epoch 不同；same-Java-release 对照只能用前者，不能用成功规划时间消掉 Java 的等待。
- 同释放对照要校验每个 `segment_id/task_id/start/goal` 和完整集合；保留原截止时间和其他任务字段，只替换 release。map2 和南宁即使 segment_id 相同，OD 不同，轨迹也不可互用。
- 对于 EBS 两段，分别报告因果违规数量，即出库段是否在入库段完成前进入网络。只要有违规，就不能把未加依赖的“最终段完成减业务首次到达”称为物理有效的端到端链；运输段指标仍可在明确边界下报告。
- 不得把两段用时相加称作业务端到端时间，也不能用剔除失败者、剔除 EBS 违规者后的幸存者均值冒充全体结果。
- 完成样本的 MAE/RMSE 必须连同未结算预测数阅读。这里评价的是**实际选中并提交后的目标节点服务后等待**，不是所有候选分数、提交前 J2 等待或整条路线的准确率；对照的旧代理量仅为 Q，不是完整旧 S4 分数。

通用指标核验入口：[metrics.py](../../scripts/experiments/g31_feng_alignment/metrics.py)。

## 5. 检查新估计的因果性和近似风险

- 仅不可回滚的真实 `EDGE_ENTER` 提交更新流量；失败候选、PIBT 回滚和未来尚未发生的预约不能更新 EWMA。
- 已服务队列和将于候选准备离开前完成服务的已承诺流入应为不同状态集合，且排除当前候选本身。
- 流出样本应去掉队列空闲时间；无样本时的有限先验、最小间隔、当前队首停滞下界与固定 EWMA 系数均应明确。
- `max(0,(Q+C)*h-(ready-now))` 是流量近似：它没有逐件模拟 C 何时入队，可能过早假定工作量已经开始消化。请检查是否出现系统性乐观、阻塞后过度保守或局部队列扫描的计算成本。
- 预测更准不必然路线更好，路线更快也不证明预测已校准；请分别评价物理执行回归、预测误差和全量路线结果。

## 6. 最终审阅结论应逐地图给出

请分别回答 map2 与南宁的以下问题，再判断是否值得扩大实验范围：

1. 新 `legacy` 是否与旧成熟 G31 等价，且评分开关没有改执行规则？
2. 纯日历替代与流量估计分别比旧 S4 改善或恶化了哪些全量指标？尾部、超期数是否与均值方向一致？
3. 与原生 Java 的优势在各自源策略下有多少；在同 Java generator release 下还剩多少？哪些部分由源释放策略而非路由产生？
4. 两图是否出现相反结果，或收益仅集中在某些 OD/瓶颈？仅有一张图获益时，不推荐据此更改默认策略。
5. 现有测试和本次单次、无故障、2.0 m/s、1x 客流是否足以支持结论？请明确尚未覆盖的速度、负载、故障与空托盘场景，避免把南宁结果推广成普遍结论。

建议输出“可确认事实、具体代码问题、比较口径问题、候选策略取舍、下一步最小实验”五类意见。不要要求为本轮评分候选重建实体托盘/驱动系统，也不要把本次 GitHub 发布理解为候选策略已经合并或默认启用。发布包使用基于 `9f23c25` 的独立审阅分支，以包内 README、REVIEW_PROMPT、差异及全量归档证据确认实际提交范围；本机论文原文不加入公开包。
