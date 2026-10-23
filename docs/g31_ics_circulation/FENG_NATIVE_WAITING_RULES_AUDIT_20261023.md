# 冯项目原生等待规则核验（2026-10-23）

本文件记录直接读取论文原件和 Java 源码得到的证据，不把 GPTPro 讨论中的引文当作已核验事实。用户本轮最新范围是：保留成熟 G31/S4/J2/PIBT，沿用恒速、节点通过和等待抽象；原 Java 不实现线路容量，本轮 G31 也不新增容量。空托盘仍不纳入本轮。

## 一、论文说明的是高层抽象

已读取并渲染核对本地稿件：[manuscript-ics 一审修改后查验.pdf](<C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料/CIE/manuscript-ics 一审修改后查验.pdf>)。这是带修改标注的本地稿件；本轮未将它等同于最终出版社排版版本。

| 原件位置 | 直接核验的内容 | 本轮含义 |
|---|---|---|
| PDF 第 14 页，行号 301–311 | 规划经过的节点序列及通过时刻；早于计划通过时刻可在节点前等待；具体低层控制由节点本地处理，不属于该研究范围。 | 可以保留节点预约/等待抽象，不必引入电机分区、车身跨边驱动耦合。该段也没有提供实际等待区几何尺寸。 |
| 第 15 页，行号 331–336 | 约束包括节点通过区间不冲突、线路托盘数不超容量、优先级规则。 | 这是论文模型声明，不能单凭该声明声称本地 Java 已实现容量。 |
| 第 16 页，行号 338–342 | 恒速，忽略加减速；装载站始终有空托盘；卸载后托盘移出系统。 | 与本轮暂不研究空托盘的范围相容；恒速不是微观共驱模型的证据。 |

该 PDF 的 SHA256：`6c317372affd636ad85011f85c939b5cfbe217b2ef1365280acba1122ede59fa`。

## 二、原 Java 实际实现

核验目录：`C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料/ICS项目/代码-ICSsimulation/src/App/`。上一轮原生 Java 运行的 `source_input_manifest.json` 也记录了同一原始项目目录；下列结论来自本次重新读取源码。

| 源文件和位置 | 实际规则 |
|---|---|
| [Astar.java:55](../../legacy/jichang_origin_readonly/src/App/Astar.java#L55) | 源节点结束时刻为起点时刻加该节点通过时间。 |
| [Astar.java:80](../../legacy/jichang_origin_readonly/src/App/Astar.java#L80) | 下一节点到达时刻为当前节点结束时刻加 `length / v`，其结束时刻再加下一节点通过时间。没有按拥堵动态延长基础通过时间。 |
| [Astar.java:83](../../legacy/jichang_origin_readonly/src/App/Astar.java#L83) | 非终点候选若与已有节点预约区间重叠，就跳过该邻居；没有为这个候选节点插入额外等待动作。终点明确豁免此项冲突检查。区间端点相等也被视为冲突。 |
| [ICS_PathFinding.java:137](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java#L137) | 新任务加入 `unfinishTasks`；规划失败就保留，后续周期以新的 `tasks.cur_time` 从源节点重试。新任务的主要等待表现为源侧推迟成功规划。 |
| [ICS_PathFinding.java:172](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java#L172) | 当前选用的静态更新路径将 `bias_time` 固定为 0；随机偏差和动态更新存在另外的代码，但不能说当前无故障基准使用了它们。 |
| [ICS_PathFinding.java:294](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java#L294) | 预约以节点为键，保存任务 ID、节点进入时刻 `t1` 和离开时刻 `t2`。 |
| [Edge.java:2](../../legacy/jichang_origin_readonly/src/App/Edge.java#L2) | 边只有起终点、长度、速度、故障状态，没有容量字段或边占用计数。全 `src` 检索也没有 `capacity` / `Capacity` / `容量` 的实现。 |
| [Map.java:30](../../legacy/jichang_origin_readonly/src/App/Map.java#L30) | 读入 `AGV_length` 和 `safe_length`，但全 `src` 的其他引用仅是 getter/setter；Astar 没用它们计算边容量或车身间距。 |

为便于 GitHub 审阅，表中源码链接指向仓库只读镜像；原件来源和哈希仍以上述目录及本轮 manifest 为准。镜像与原件的 App 文件核验一致，其中 Astar 仅换行规范化后相同，其余上述核心文件字节相同。

因此，原生 Java 基准应描述为“恒速路程时间、节点预约冲突、规划失败源侧重试”。不能称其为已验证的有限线路容量或微观停车模型。用户最新指令已明确本轮双方均不增加容量。

源码 SHA256：

| 文件 | SHA256 |
|---|---|
| Astar.java | `b2b7e001d55fd9cb265f73792918611b6d18aeea3b93bb0ebf36b975020c43f8` |
| Edge.java | `45fc16634244acfd5d3303a8689bb7ed410b4835b5e08a3758b8c50606a94cce` |
| Map.java | `3e2af71a17d204fdc6639feb2fa8efd252881d6b18b0b15f5248ba68e0d6ece6` |
| ICS_PathFinding.java | `a367fd8e79aba7b3d23b71fc9b4d01f76dd67f291f008401d676ffcbcf53d52a` |

## 三、旧 G31 已有 ETA 日历等待，本轮不是补上这个能力

成熟代码的 `candidate_record()` 已经用 `target.service_calendar.earliest_start(time + travel, service)` 求下一节点可开始服务的时刻。旧 S4 随后加入 `max(0, target_next_available - (time + travel))`；这本身就是按预计到达时刻计算的剩余日历等待，不能描述成错误地把“当前剩余忙碌时间”全部收费。可查 [event_driven_junction.hpp:14921](../../cpp/ics_core/runtime/event_driven_junction.hpp#L14921) 和 [原 S4 分支:9853](../../cpp/ics_core/runtime/event_driven_junction.hpp#L9853)。

南宁正式入口也已设置 `enable_s4_direct_neighbor_merge_calendar_visibility=True`，同时开启 `complete_on_goal_arrival=True`：[run_g4irsf31_nanning_native.py:501](../../scripts/eval/run_g4irsf31_nanning_native.py#L501)。因此不能把原来的性能问题归因为正式实验没有看见直接邻居的合流日历。

本轮新增的是可关闭的**拥堵成本替代实验**。`legacy` 默认保留旧 S4：旅行时间、静态势、`Q + scheduled_incoming` 压力和已有入口/日历等待。`eta_calendar` 以入口等待和到达后日历等待替代原计数压力；`eta_flow` 在此基础上加入完成服务后队列的流出时间估计。新模式不把同一份 `Q + scheduled_incoming` 再加回来。`eta_flow` 是基于已发生流出的近似估计，并非已证明准确的未来等待时间；是否有收益必须由实验决定。直接邻居日历在新模式中明确定义为可读，正式对照两侧均保持原可见性开关开启。

## 四、成熟 G31 的队列含义

`event_driven_junction.hpp` 的 `process_service_complete()` 先累计一次真实 `service_duration(node)`，再发出 `kArriveJunction`；`process_arrive()` 随后才将非终点任务加入 `JunctionState::queue`。因此这个队列是**已经完成该节点服务、等待下一跳的队列**。

本轮预计延误必须分开处理：

1. 到达目标节点时的服务窗口竞争，由已有日历/J2 预约描述。
2. 完成节点操作后等待下一跳的积压，可由队列和历史实际流出估计。

把目标队列长度再次乘该节点基础服务时间，或者在原 S4 的队列/预约压力之上再加一遍相同拥堵，会混淆阶段或重复计数。预计延误只影响候选评分，不得更改 `service_duration()`、预约区间、`kJunctionServiceComplete` 发生时刻或实际已完成服务累计。

## 五、两侧仍有的时间边界差异

**节点区间端点。** 原 Java [Astar.java:83](../../legacy/jichang_origin_readonly/src/App/Astar.java#L83) 以 `!(t1 > old_t2 || t2 < old_t1)` 判冲突。因此 `[5,7]` 与 `[7,9]` 在非终点属于冲突。G31 [LocalCalendar::available:1940](../../cpp/ics_core/runtime/event_driven_junction.hpp#L1940) 以 `start < old_end - epsilon && old_start < end - epsilon` 判冲突，`epsilon=1e-9`；`earliest_start()` 也用相同容差。因此 G31 接受首尾相接，并容忍不超过容差的边界重叠。两者都用节点通过区间，但**不是完全相同的区间开闭规则**。本轮等待评分开关没有改此边界，也不能将同样“无冲突计数”说成两侧判据完全一致。

**终点完成事件。** 原 Java [Tasks.java:173](../../legacy/jichang_origin_readonly/src/App/Tasks.java#L173) 在 `epoch >= next.t1` 时发节点通过消息；路径仅剩两节点时，该消息直接报告终点。随后 [ICS_PathFinding.java:79](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java#L79) 移除完成任务，[写输出方法:484](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java#L484) 将当前 `epoch` 写入 `output.txt`。因此实际完成判定使用**到达终点**，没有再等待终点的 `t2`。

Java 包装器的 [routes.csv 导出:395](../../benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java#L395) 确实把路径末节点 `t2` 命名为 `finish_time`，但正式生命周期汇总 [run_g4irsf24_fresh_hca.py:395](../../scripts/eval/run_g4irsf24_fresh_hca.py#L395) 解析的是 `output.txt`，再将实际完成消息的 `finish_epoch` 写入结果。不能拿导出的路径 `finish_time` 代替本轮完成时间。

G31 在 [process_edge_exit:15691](../../cpp/ics_core/runtime/event_driven_junction.hpp#L15691) 对终点直接完成，不再预约或执行终点服务。因此终点事件类型已经对齐；**时间观测分辨率仍不同**：Java 基准每秒运行一个 `epoch`，每周期至多为一个任务报告其当前下一节点，G31 记录连续事件时刻。Java 完成输出是整数周期观察值，不能声称与连续到达时刻完全相同；连续短边还可能造成多个周期的报告推进滞后，而不只是单次小于一秒的取整。

本轮保留这些成熟执行规则，仅替换候选评分的可选分支。托盘总量、ID、申请和返空守恒机制不在该评分改动范围；实验仍只运行载货任务，不把这些实验解释为空托盘循环验证。

## 六、回归验收边界

独立测试源 [test_g31_eta_wait.cpp](../../cpp/tests/test_g31_eta_wait.cpp) 覆盖：

- **到达时刻对齐**：当前时刻 100、服务忙至 105；旅行 10 秒时到达 110，剩余日历等待为 0；旅行 2 秒时到达 102，剩余等待为 3 秒。
- **日历空隙**：已有区间 `[5,7]`、`[20,22]`；到达 8 且需服务 2 秒时可立即开始，不能把最晚预约尾 22 当成连续忙碌时间。
- **服务后队列分离**：修改目标已服务队列的预测流出只能改变后服务延误分量，不能再次增加该节点实际服务；已有预约描述的任务不能再按同一计数重复收费。
- **关闭等价**：关闭新模式时，同一输入的路线、逐任务结果、事件/决策顺序与旧 S4 等价；不以总完成数一致代替逐任务等价。
- **真实服务不变**：固定唯一通路下，开关评分不改变每次基础服务时长、总已完成服务量或 J2 预约有效性；多路线场景若总服务量因所选节点数变化，应按实际节点逐次检查。
- **因果统计与退化**：仅使用已发生的实际流出与合法可见预约；无流出样本、陈旧或不足样本时走明确有限回退，不偷看未来实际离开时刻，不生成 NaN/无穷评分。
- **新状态恢复**：`eta_flow` 已积累真实流出观测、仍有未结算预测时捕获 checkpoint；恢复后全部任务/事件轨迹、预测误差指标、确定性 replay hashes 必须相等。

到达时刻与日历空隙测试是在锁定已有语义，不能作为“旧 G31 没有 ETA”的证据。服务后队列反例独立设置 `Q=1`、目标服务日历空闲，旧 S4 候选分数为 `14.1`、纯日历替代为 `13.1`；唯一通路上真实完成时间仍为 `31.0` 秒，真实服务合计 `10.2` 秒，后服务等待 `16.8` 秒仅结算一次。

最新统一构建已运行包含上述六组场景的测试目标，`g31_eta_wait` 通过（0 failures，5.31 秒），包括修复测试夹具 Graph 对象寿命后的新模式 checkpoint 场景。记录：[eta_tests_final.xml](../../outputs/experiments/g31_feng_alignment_20261023/eta_tests_final.xml)。这证明该组执行与状态边界回归通过，不等于证明候选拥堵估计在南宁全量中优于旧 S4。
