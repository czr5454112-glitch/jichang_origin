# Feng DH 执行器语义独立复核（2026-09-05）

当前 Java 最明确的未识别假设是：中间节点 through 完成后立即释放上游占位，行李在边外经历 2 秒 transfer，计时结束后仍可无限期留在边外等待出口。该等待既不占边容量，也不进入路由的 moving/stopped 计数。这是代码可证实的能力；它是否以及多大程度改变 map2 或南宁结果，需要独立实验。零时间修复、优化等价、边格无重叠和全人口完成均不能单独验证这个物理合同。

本审计将原 Java 控制器、legacy HCA、论文文字和新解出的 Demo3D 组件分开。已实施的保留边界、任务身份裁决和次 tick 复用版本是独立假设探针，均不改变冻结生产程序，不按历史均值或 G31 胜负选择。

## 1. 一手文字与原 HCA 能证明的边界

[一手文献审计](feng_dh_primary_semantics_reaudit_20260905.md)记录各 PDF/DOCX 的身份和页码。CIE 一审修订检查稿（未经核实为出版社最终稿）PDF 25–26 页、回复正文 108–114 段明确说明另行从头编写 DH 仿真器；共享地图、参数和需求不等于复用同一个 HCA 物理执行器。所引原文是 Tarău 等的 *Route Choice Control of Automated Baggage Handling Systems*，TRR 2106 (2009), 76–82，DOI `10.3141/2106-09`，不能只凭不同材料中不一致的 2009b/2009c 后缀辨认。英文步骤要求每 0.2 秒更新袋的位置/移动状态，然后在分流口选择出口，在汇入口遇到后继边首位置的 stopped 袋时停在 switch 前。英文逐袋更新措辞与中文措辞的差异不能唯一恢复集合遍历、阶段顺序和原地更新可见性。

| legacy 代码 | 实际行为 | 对 DH 重构的含义 |
|---|---|---|
| `Astar.java:55,80–88` | `source.t2=source.t1+t_source`；孩子 `t1=parent.t2+length/v`、`t2=t1+t_node`；非目标节点若与已预约的闭区间相交就丢弃该候选 | 地图 `t` 是原 HCA 节点时间依据，不能直接证明 DH 的 1 秒 exclusive + 2 秒 overlap 分解。 |
| `ICS_PathFinding.java:135–156,294–306` | 对未完成/新任务逐个计算整条路径；成功即写入全路径节点预约，再处理下一袋；失败重入待处理队列 | 原 HCA 具有全路径提前预约。它不是位置格 DH，也不能当作 DH 的可交换底座。 |
| `Tasks.java:148–170` 与 `RUN/Main.java` 的整数 epoch | 每个源在每个 epoch 最多产生一袋；源上存在未规划成功任务时不继续放新袋；阈值检查为 `pass_time-epoch<1` | 源端按 epoch 取袋与 Java 同时 release 后各自 2 秒非独占诱导不同。使用共享-D 输出对照时仍应明确源端执行合同。 |
| `RUN/Main.java:40,123` | 早到阈值 4800 秒；EBS 第二段按 STD−2700 建任务，不要求第一段完成后才创建 | EBS 独立分段来自 legacy，不是本次 DH 为取得优势新加的能力。若测试段间物理先决条件，应另立实验且各方法同口径。 |
| `Map.java:17–18,108–118` | 读取并提供 AGV 长度/安全间隔字段；在 `src/App` 中搜索这些字段未发现 Astar 使用 | 共享地图字段不证明两执行器使用相同边容量约束；不能仅以相同输入认定物理等价。 |

闭区间预约让同一节点的下一预约起点必须严格晚于上一终点，但这仍是 HCA 的规划约束；不能据此宣称 DH 必须增加一个 tick。V4 将这一点作为观察时刻敏感性的动机，保留假设标签。

## 2. 当前 Java 的能力与需要隔离的假设

| 主题与代码位置 | 审计结论 | 有意义的独立夹具或对照 |
|---|---|---|
| `FengDhBagState.beginNodeService:353`；Simulator through commit | 转入 `AT_LOADING_OR_JUNCTION` 时 edge/position 均为 −1；原节点 through identity 已释放。timer 到期后 HOLD 不恢复上游占位，没有中间存储容量上限 | 持续阻塞出口，检查 timer 到期后的袋是否仍占上游、后随袋是否回压、是否进入 stopped 评分。V2 已覆盖。 |
| `FengDhPolicy.choose:152–157` | 只累计 snapshot 边上的 moving/stopped；边外中间等待对任何候选都不可见 | 保留边界会同时恢复物理回压和既有边计数的可见性，两者来自同一空间表示变化。不得宣称它仅改了一个纯计时常数。 |
| `candidatePaths:207–231` | 每个出边接一条静态自由流最短后缀，再沿整条候选计拥堵；没有 HCA 未来预约。后缀虽为简单最短路，加入首边后并未显式禁止回经当前节点 | 全路径上的计数范围有 Feng 直接依据：学位论文正文段 225、修订稿第 26 页步骤 (b)、回复正文段 112。改成一跳会改变已披露控制律；这不证明当前候选后缀、并列路径、回路或 HOLD 重选规则就是原实现。 |
| Simulator `step:286` 与 `planInternalMovement:635` | 全 tick 使用同一初始 snapshot，局部提出意图，确定腾空后集中提交；避免取决于 Java 容器碰巧遍历次序 | 是理想同步执行假设，未实现多袋联合目标或未来调度优化。可用已停止链与移动链分开检验。 |
| `planInternalMovement:662–664` | 对原状态 STOPPED 的紧前袋，后随袋按它的旧位置判断；只有 MOVING 紧前袋使用计划位置 | 当前已经保留 stopped 启动传播延迟。不能再用“禁止跟随刚启动的 stopped 袋”冒充新修复。论文明确允许跟随 moving 袋，普遍禁止复用旧占位会新增不受支持的移动延迟。 |
| `nodeServiceOrder:906`、`entryOrder:884` | 物理到达 tick、release tick、task ID、上游边依次裁决；through 本 tick 完成时允许下一袋同 commit 获得服务 | 是重构 FIFO 与同步复用规则；原始精确仲裁未披露。身份优先探针和 V4 次 tick 复用分别检验这两项。 |
| 源入网与 EBS | 原始 release 独立诱导且无每源 1 Hz 的统一服务门；目标到达直接完成；EBS 两段按共享-D 独立启动 | 论文明确移出的是卸载后释放的 tote；这不单独证明目标到达即可完成，也不规定卸载排队能力。不能由此推导中间节点具有无限容量。 |
| 每次 ready/HOLD 的 `policy.choose` | 同袋可以在后续 tick 根据新 snapshot 重选出口；自由流项不含 through/transfer 服务时间 | 下一跳锁定或服务感知势函数都改变路由合同，应分别命名。先用两条等长分叉、阻塞随 tick 变化的夹具证明是否发生再选择。 |

最有依据的物理问题是 switch 前 HOLD 的空间位置。将转运建成 `v×2s=5m`、容量 5 袋的管道，或给每个入口一袋缓冲，均需要新几何依据；目前文献步骤不能唯一确定它们。将完整 3 秒当作单一节点独占服务同样没有被这段文字证明。此前 ledger 中以首 1000 袋变慢而停止 retained 假设的记录只说明当时的实验选择，不能反向证明其物理合同错误；完整人口才是可比的数值对照。

## 3. 新解出的 Demo3D 组件：独立代码阅读

本节阅读的是 `tmp/pdfs/feng_primary_reaudit/demo3d_container/native/025_BaggageHandling.3/ToteSystems/` 内嵌 C#；已读逻辑属于设备/目标输送控制，没有恢复出 Feng DH 的 moving/stopped 评分器。完整本机路径对应工作树根下的上述 `tmp` 目录；[容器、绑定及短摘录证据](../../outputs/runtime/feng_dh_semantics_reaudit_20260905/primary_model_evidence/README.md)可直接审阅。此结论不从 DLL 字符串未命中进一步推断所有二进制中绝无 DH。本节独立读过组件控制流，并核对实际源文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `IntersectionControllerCS.cs` | `9f04fe12b6b9d1c4bc9995068aa9fd5dba3429ff60c25e64bbed306b97bfadd0` |
| `FlowControlCS.cs` | `c3c3c41becfa784ba912ec66b5d9b72e72cd48bfdc8a6fda6b90f3ac5edfa3a4` |
| `StationCS.cs` | `ae93874a003936cd8e6dc5b1ebeabc3ce805e8a9c480e79748c28fdf99f3f6c4` |

**Transfer 并非通用节点 1+2 秒。** Intersection 的 `TransferTime` 在第 103 行是配置属性，无硬编码 2 秒。侧向进入使用几何距离 `dist / TransferTime` 设移动速度，再等待 `MoveTo` 完成（988–1005）；侧向送出也独立使用该配置（890–924）。主线直行的 `GetInboundLocation` 返回零向量，走正常输送与到达位置等待（966–984），不强制这一固定 transfer。进入主线再分流可能先后执行两段几何动作，因此既不能将它等同每个图节点统一加 2 秒，也不能将 2 秒简单乘皮带速度解释成一段隐藏缓冲区。

**等待对象仍有真实几何状态。** `OnBlockedFifo:648–685` 把 PhysicsObject 加入等待列表；队列或 processing 非空时将新袋设为 Kinematic，并可能 `StopInfeed`。后者通过上游 controller 的 ReleaseEnabled 和输送机 motor 开关传播阻塞（806–826）。`Dieback` 在不能送往目标时保持该对象等待（879–883）；没有将该对象移到 edge=−1 的抽象存储池。Kinematic 对接触响应的全部细节依赖 Demo3D 引擎，不能仅凭这些行就证明任意场景绝不重叠，但组件明确使用袋的现有位置、包围盒和速度。

**存在受几何约束的重叠处理，未见固定全节点容量一。** 相同 infeed 的下一袋可再次 Dispatch（676–677）。`_Dispatch` 不以 `_p.Count==0` 为必要条件，而用 `InboundDestinationClear` 检查（787–802）。`IsReceiveDestinationClear:952–964` 遍历 processing 袋的包围盒后缘；发生几何冲突时，仅在速度一致且前袋速度非零的条件下允许接收（1058–1064）。`target.IsBusy` 从等待到达分流中心前开始，至侧向移动完成结束，锁的是特定 outfeed，不能解释为所有入口共享的固定 3 秒服务器。`_p/_px` 的释放由实际传感器 OnCleared 触发（728–748），不只看固定计时结束。

**Passive 模式的长度公式是主线观察区域。** LeaderSensor 宽度为 `2 × motorSpeed × TransferTime`（316–333），用于优先通过主线来袋；它不是 transfer 队列长度或存储容量的定义。用这个公式推导“隐藏通道可容纳 5 袋”没有代码依据。

**订单列表无限不等于物理空间无限。** `FlowControlCS:588–628` 的 FifoChannel 可无限登记 load 引用；Station 仍将 load 留在当前 station，受 DispatchOutEnabled、TransferState 和 Kinematic 控制（Station 134–177、231–252）。FlowControl 删除 load 时还更新 station 的 CapacityInUse/ReadyForIncoming（419–429）。这些容器表示逻辑订单，不构成离边占用消失的证据。`SimpleFlowCS` 默认 ReleaseDelay=1 秒，但只有实际绑定和过程启用后才生效，不能仅凭默认值移植到 DH。

**场景激活条件是关键限制。** Intersection 在 `DisableForLinPhys=true` 且 Scene `PhysicsEnabled=false, SimulationLinearPhysics=true` 时把 sensor 改为 VisualOnly（160–169、204），源码历史也指出 Linear Physics 自带自动合流。独立场景解析报告：77 个 intersection 的 TransferTime 均为 0.6，DisableForLinPhys 均为 1，目标阻塞模式均为 Dieback；场景恰是上述 Linear Physics 模式。47 个 custom TransferDuration=2 的对象是 Lift 子件，不能和 Intersection.TransferTime 混用。当前阅读已抽查 compact 绑定文件，完整枚举身份和 .2 DLL/独立脚本版本差异以绑定审计为准。因而这些组件说明了几何控制的可能机制，但不能直接据 .3 库实现宣称本场景实际执行 0.6 秒交叉口动作。仍应追踪启用的 Sensor/lift/native transfer 分支和 Demo3D Linear Physics 路径。

## 4. 已隔离实现与机制验证

保留边界 V2 的五个生产源位于 `benchmarks/java/feng_cie_dh_retained_boundary_v2/App`。through 1 秒仍单独独占；该计时到期立即释放服务身份，随后 2 秒 transfer 及任何出口 HOLD 都保留原上游物理占位，直到真实后继边入网。新增 retained 状态保证服务只执行一次。目标与源处理不变。直接边交接恢复了之前边外交接不需要执行的“已获准腾空—重新规划跟随—继续批准入口”闭包；它从确定腾空开始，不凭空允许全满 stopped 环路旋转。

| 项目 | 可重复证据 |
|---|---|
| V2 source aggregate | `1bcc8a4dbebf7f934dda270b0af5ed9038ba1b404947f757544bedc739ea0709` |
| V2 33-class aggregate | `28f8b4576c6c752a331c3f28312ae625c4951bae47cd34677762f5c95c5c8aba` |
| 单袋与源/目标 | 零中间 through 完成 tick 28；正 through 完成 tick 33；源 admission tick 10；真实南宁 130→57→58 单袋完成 tick 251。 |
| 阻塞与回压 | timer ready tick 11 后仍留上游至 tick 31；后随袋受物理间距阻挡；实际腾空后同 commit 可交接。 |
| 两入口节点资源 | through starts 为 ticks 1、6，transfer ready 为 16、21；说明完整 3 秒未被做成全节点独占。 |
| 同一入口后随 | through starts 为 ticks 1、18，即 3.4 秒；这是保留空间的可测后果，不能预设为 3.2 秒。 |
| 计时/死锁 | 长有限计时不会误判 idle 死锁；全满 stopped 环无初始腾空时不旋转，timer 结束后真实 deadlock。 |
| 再现 | RB1–RB10 运行两次全 PASS，JSONL 及全部 10 份 trace 逐字节相同；每步检查身份、边所有权、间距与 retained 状态。 |

详细命令及证据在 `outputs/runtime/feng_dh_semantics_reaudit_20260905/retained_boundary_fixtures/identity_and_verification.json`；测试类为 `tests/java/App/RetainedBoundaryAudit.java`。独立编译目录是 `build/feng_dh_retained_boundary_v2`，原生产类目录未覆盖。V2 保留全部 2 秒上游占位仍是一项假设；它没有恢复 Demo3D 的实际几何运动。

任务身份裁决探针及 V4 次 tick 服务复用探针分别见 [身份裁决预结果合同](feng_dh_id_order_probe_preregistration_20260905.md)和[次 tick 预结果合同](feng_dh_next_tick_service_preregistration_20260905.md)。它们各自用自然推进的竞争场景证明预期行为差异和最终完成，所有生产父版本保持冻结。独立版本的命名、源码/类身份和完整 trace 已归档；它们都没有被描述成完整异步执行器。

## 5. 后续辨识顺序与接受边界

当前证据优先级应是：核实真实启用的 Demo3D 分支与物理位置合同；保持完整 map2、shared-D 和逐袋输出；再解释预注册探针产生的变化。次级可分离假设包括选出口前 stopped 检查、一次到达锁定下一跳、位置更新后评分、严格定义的逐袋更新；各项应先用能触发首次差异的夹具确定语义，再比较全人口。只移动可观察时刻或仲裁顺序时，不同时改变空间容量、路径范围或罚项。

这些微测试只验证各自声明的机制，未证明原作者精确实现。完整 28,506 袋/43,603 段的 map2 结果由主实验任务独立产生，本文件不从首批样本推断全人口结论，也不将慢、deadlock 或数值接近历史本身作为保留/拒绝物理假设的充分证据。所有方法的 THT 必须同口径，EBS 原始袋按各段 `completion − shared scheduled release` 求和；入网后 latency 单列。若历史分布仍不匹配，保留偏差和来源未识别标签，不选择对某方法最有利的执行器。
