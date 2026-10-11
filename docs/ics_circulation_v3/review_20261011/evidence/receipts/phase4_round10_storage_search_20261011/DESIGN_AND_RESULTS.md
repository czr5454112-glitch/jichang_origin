# Round10 存储搜索：公开日历下界与必要到库事件

2026-10-11。代码仍是固定已公告 release、on-carrier、有限等待节点库位代理；不模拟实际离盘存储设备。此轮只改 storage_routing.py、新增 storage_calendar.py 及路由专属测试，没有更改 runtime 的物理语义、任务最终目的地、K、预算或原业务分母，也没有提交或推送。

当前复验源码：

- storage_routing.py：867018bc951e8afe95840c33dbac42a32f2a2d38e46317e58070534dc502e7e2。
- storage_calendar.py：5b0b5d87aefe954f89d3e00774847a66ef801df49118909624bf2e5fc94f0ed7。
- tests/test_ics_circulation_v3_storage_routing.py：45160a98106d74df8146f92b00a8092d4c8987eb48c04abfd34682fcb6c398da。

## 原件与具体问题

baseline_001 在任何 Round10 源修改前封存了全部 Python 实现、作者测试、原图 business_window_h21600_003/checkpoint_8400.pickle 的副本，以及用原 Round9 源恢复并 advance 到 8881 后观察到的 snapshot/delegate。源 checkpoint SHA 为 e92b230f7153a779ff3bda6ad907518611a8eaae688e873079360886cf45d600。真实目标是 projected:1x:3 / proxy-initial-95，release=19500，最终目的地47，保护卸载截止22200，horizon=21600，原预算10000。独立保存的查询按 engine.candidate_count 使用 **K=4**；窗口日志的某些 fast query 使用 K=1，因此本报告只声称对同一个保存的 K=4 查询做前后比较，不冒称逐字复现每条窗口日志。

同目录保留两张手工图的完整 snapshot/delegate：100 个正时间回路，free_storage 与 busy_storage，K=1、horizon10005、预算500、release10000。后者另一只真实盘占库到10002。原 Round9 是 free413 成功，busy500 耗尽，真实 ID3 10000 耗尽。原 Round9 文件及原窗口未覆盖。

首次查看真实轨迹时，我只注意到 EBS 出边 53→49 的预约 [19500,19576)，错误推断该边被占满、下界应升至19753。这一推断在实施前后的直接核对中被纠正：该边 **capacity=75**，一条预约不构成阻塞。实际候选的失败点为下游 edge35→36@19658，那里达到容量阈值。初版代码正确按容量阈值处理，因而不会采纳这个错误根因；初版只看 EBS 第一条出边的放松下界仍为19677，真实查询继续耗尽。comparison_001 原样保留该失败。最终对整条下游边日历的放松最早到达为 **19678**，仅比静态值晚1tick，但足以使静态低估回路不再压住可行候选。

## 研究依据与本实现的证明边界

[Phillips 与 Likhachev 的 SIPP 原文（ICRA 2011）](https://www.cs.cmu.edu/~maxim/files/sipp_icra11.pdf) 用配置和安全区间减少时间状态，其早到支配依赖能够在相同区间等待等假设。[AAAI 2023 的运动约束 SIPP 研究](https://ojs.aaai.org/index.php/AAAI/article/view/26453) 讨论附加约束下的搜索问题。这里只借鉴时间区间表示，不继承这些论文的完整性或最优性结论。

当前 ICS 有禁等节点、半开驻留区间、边上的整段占用、最终接收与长期盘驻留，还有 K>1 候选覆盖需求。因此真实搜索仍保留 `(node, tick, storage_stage)` 精确时间标签及原 caller K，不进行 safe-interval 的早到支配，不删除回路或物理路径族。

新增下界是单独的**放松问题**。对本次尚未通过存储的路径，或当前确实位于存储节点的已到库路径，令 `s0=max(snapshot.now, release)`。从存储节点于 s0 出发，计算一个时间依赖 Dijkstra：每条边必须满足当前公开有效预约的整段容量；每个节点都允许任意等待，忽略节点驻留、禁等、接收和最终长期停车约束。边长仍为真实正整数。

对于边 e，令 `D_e(t)` 为不早于 t 且整段 travel 可用的最早出发时刻。t 增大只会缩小可选择的 departure 集合，所以 `D_e(t)+travel_e` 单调不减，满足该放松图中的 FIFO 条件。故每节点最早 label 的 Dijkstra 在**放松问题内部**合法。任意真实完整 witness 的存储后缀也是这个放松问题的一条可行路径，其存储出发不早于 s0，因此放松最早最终到达 F 不大于真实最终到达。

真实 product search 只把优先级/界限改成 `max(原静态到达下界, F)`。F 每 query 计算一次，没有在每个 late label 上重复运行整个 Dijkstra。实际已经出库且当前在别处的 progress 不再施加这个存储起点下界；不能要求它重新访问存储。查询中从当前存储起点再离开或尚未到库后再离开的后缀，则都受同一个必要 F 约束。超过 horizon/保护最终卸载截止只报告当前有界查询未找到候选，不声称系统永久不可达。

## 半开容量与晚到事件

CapacityCalendarView 只读 effective_reservations，排除当前候选盘，保留其他盘、旧在途和已承诺占用。资源容量大于1时，用叠加预约达到 capacity 的区间判定“不能再容纳一只盘”；合并同 tick delta 后形成半开阻塞区间。边需整个 `[depart, arrive)` 可用，不能只检查开始时刻。

现行 runtime 对中间节点只预订正时长驻留，零驻留到达后立即离开不消耗 node interval。此轮不改变该物理约定。因此满库到10002仍可有 release10000 的零驻留 witness；把“点到达时库位满”直接作为拒绝条件会错删合法路径。真正卸载/hold/长期终点驻留继续由共同 ExecutionValidator 审核。

原 event search 投射预约 end，却缺少“恰好 release 到库”。现在 release 作为 storage arrival 事件沿上游禁等链逆投到前一个可等待节点。独审随后发现仅补 release 仍不足：库位满到6、release3，下游禁等链的满边 [4,6) 使 EBS 需要在5离开。保护截止10时，唯一及时见证是在5到库并零驻留离开；等库存结束6会晚1tick。

为此 StorageEventTimeSearch 把存储节点自身的原始下游 departure 事件（从禁等链资源端点反投而来，且不早于 release），连同 release，一并作为 storage arrival 事件继续投向上游。原预约事件全部保留；raw 投射和二次必要事件投射分开缓存于 query 内，避免递归自调用。它不把所有有预约的可等待节点都强行当禁等节点，也不声称已经覆盖所有一般日历场景。

## 预算、缓存与桥接

同一个原 expansion_limit / wall deadline 覆盖：静态拓扑和 reverse lower、有效预约条目、按需资源 slot 建索引、聚合端点、非空阻塞区间扫描、放松 Dijkstra pop 和每条展开边、原 event projection、新事件组合、真实 product labels、完整 witness validation。空区间没有可扫描条目，常数查找包含在其所属搜索/投射步骤及整次 wall/CPU 中。logical work unit 是上述明确阶段的算法单位，不冒称逐 CPU 指令计数。有效预约函数本身的构造、签名/排序、Python 对象处理和 validator 内部细节都包含整次 wall/CPU；完整 validator 的逻辑单位仍沿用原每 witness 一次。

Static unreachable 查询只复用 delegate 已存在的 isolated_replay_v1 topology/lower cache，不新增持久 memo，不缓存动态结论。所有 warm 命中仍逐一消耗原 cold-equivalent 拓扑与 reverse 单位，actual/reused 分开记录；缓存导出已有 network signature、lower distance、work 和 LRU。日历、下界 F、事件集合每 query 新建，不进入任何隐藏全局缓存。隔离合同下每 query 再次拒绝非 None wall deadline，防止初始化后修改配置绕过重放约束。普通袋与空盘仍严格委托原 generator。

Root 对 mixed ordinary/empty/storage 的每个预算截断、拓扑变化、日历/release 变化、checkpoint/显式恢复、兄弟隔离及运行中 deadline 修改做独立桥测。首轮 cache_bridge_001 是中间版9/9通过，其耗时属于 root 记录，不在本子任务重复计入。最终桥测与独审结果由各自原件记录。

## 已执行结果与保留的失败

| 执行 | CPU 秒 | 结果 |
| --- | ---: | --- |
| baseline_001 | 3.421875 | 冻结源与原件；1次8400→8881部分物理续跑、3个独立查询。续跑CPU2.46875及查询CPU为嵌套数，不能另加。 |
| authoring_001 | 1.265625 | 32例中30过、2失败；旧满库测试错误地预期零驻留不可行，新夹具预约 owner 不存在。保留失败与源。 |
| comparison_001 | 0.3125 | 3查询；busy432成功，真实ID3仍10000耗尽。执行记录生成成功不等于目标已解决。 |
| authoring_002 | 1.03125 | 32/32通过；修正语义预期和夹具身份，整段下游边下界落地。 |
| comparison_002 | 0.109375 | 3查询；busy436成功，真实ID3 843取得4候选。 |
| authoring_003 | 0.984375 | 新增满库与下游禁等链deadline边界；33/33通过。 |
| comparison_003 | 0.09375 | 3查询；free418、busy438、真实ID3 847，均返回原K数量且共同validator全接受。 |

截至此表本子任务新增计量 CPU 合计 **7.21875 秒**，含1次部分物理续跑、12个单独查询（baseline3 + comparison三轮各3）；作者测试内部查询不再按单独批次重复计。所有正式执行均保存完整源快照、前后 SHA、wall、失败和查询 diagnostics。Windows 单查询 CPU 偶有0为时钟量化，不等于无成本；这些测量不支持一般100ms或吞吐承诺。

另有一次诊断 shell 在核查 capacity75 时直接执行了1个临时作者查询及手写候选 validator 检查，未单独计 CPU，也没有独立运行产物；工具输出保留于对话，明确列为 **auxiliary unknown**。其他人工阅读、浏览文献、代码/文档写入、源码哈希与拓扑查看也属于未计辅助成本，不把它们伪装成0或加入精确CPU总量。

comparison_003 的同输入对照保持 snapshot 字节不变：busy在10000入库并立即出库，10002卸载；真实ID3的新4个完整候选都在19679卸载，原预算10000中使用847个工作单位。改善来自候选生成和必要下界，未降低K、删袋、改OD、加horizon或预算。独审的整数小图域与真实窗口后续结果仍须各自审核；全局可行性、K路径族完整性、任意日历完备性与业务吞吐提升均未被证明。

## 冻结与收据复核补记

独审 agent 已对上述最终源码执行 attempt005：127例通过，无失败/跳过/源漂移，CPU1.46875；包含其另写逐tick oracle、792个容量区间/最早整段可用对照、11个FIFO下界对照，以及原来缺失的满库与下游禁等链的两个保护分支。其7次微型物理运行与CPU归属 phase4_round10_independent_review_20261011，不计进本子任务资源小计。root 收到后正式冻结生产源码和作者测试，继续独立缓存桥、机制与窗口；本子任务只补文档和收据绑定。

本目录 resource_bindings_002.json 通过 **902 项**收据/源/输入绑定检查，确认上述7份主收据 CPU7.21875、1次部分物理续跑、12个单独查询，检查所有 source snapshot 的实际 SHA、前后稳定、每查询 stage work 之和等于 expansions、输入绑定和原预算。该收据审计新增 CPU0.171875、0查询/0physics。

首次资源审计 resource_bindings_001.json 在894项检查后因 Windows manifest 使用反斜杠、查找键使用正斜杠而报 KeyError，CPU0.21875，0查询/0physics。失败原件保留；修正仅归一化审计脚本的路径键，没有改生产源、原数据或测试。resource_audit_sources 保留两版审计脚本，失败版由修改前内容重建并验证 SHA 与失败收据精确一致。

因此本子任务当前全部**已计量**新增 CPU 为 **7.609375 秒**（主7.21875 + 失败收据审计0.21875 + 通过收据审计0.171875）。汇总时只加7份主 result.json 与 resource_bindings_001/002 各自顶层 cpu_seconds；resource_bindings_002 内的 main_receipt_cpu_seconds 是引用小计，不能再次相加。所有嵌套 query/replay 数以及 root/独审引用亦不重复计费。仍保留上文 auxiliary unknown，不把已计量小计说成完全总资源。
