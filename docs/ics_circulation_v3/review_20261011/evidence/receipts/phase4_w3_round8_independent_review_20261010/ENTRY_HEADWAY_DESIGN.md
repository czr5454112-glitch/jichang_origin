# 显式入口头距：最小贯通方案与实现前反例

2026-10-10，Round8 等待期独立源码审查。**本文件仅为下一轮设计；没有实现新物理规则、修改冻结源或测试、运行额外物理实验。** 所有定位针对当前 `scripts/experiments/ics_circulation_v3/`。既有 933 项回归与历史原件继续代表旧模型，不是本方案的验证结果。源码读取、推导和文档编写属于未完整计量的辅助工作。

## 1. 最窄的可实现语义

为每条既有有向边分别声明：行驶时间 `tau_e > 0`、整边同时占用容量 `C_e >= 0`、入口最小间隔 `h_e >= 0`。时间均为整数 tick；`h_e=0` 禁用新增规则。第一版的 `h_e` 在一次运行中固定，空盘和载盘相同；不同模式、合流间隔、反向共享轨道及动态限速都不由此自动获得支持。

一次真实入边事件 `(tray_id, edge_id, depart)` 同时需要：

- 原物理资源 `edge:e` 的 `[depart, depart + tau_e)` 一单位，容量仍为 `C_e`。
- 当 `h_e > 0` 时，新增 `entry:e` 的 `[depart, depart + h_e)` 一单位，容量为 1。

两者均采用半开窗口：相邻入边恰好相隔 `h_e` 合法。新增窗口不改变该盘抵达时间，不自动改变原容量，不增加、反转连接或重分配 owner。零腿卸载/持盘没有入边事件，不能凭空产生窗口。`C_e=0` 仍关闭边。

这是**单条有向边入口事件的固定时间间隔模型**，并非对连续输送安全距离的完整证明。在同速、不超车的代理条件下它能表达入口间隔；若存在追赶、变速、合流或多车道，则需要另外明确物理语义。2 km/5 km 是长度试验档位，不是头距值。长度、速度、行驶时间、整边容量、头距应分别有单位及假设来源，不能从长度推定现场头距或容量。

| 手算反例 | 整边容量判定 | 入口判定 | 含义 |
|---|---|---|---|
| `tau=10,C=3,h=3`，入边时刻 0、1 | 合法 | 非法 | 容量不能阻止过密入边 |
| 同参数，入边 0、3、6 | 合法 | 合法 | 改成 `C=1` 会不必要地等到 10 才放第二盘，破坏流水输送 |
| `tau=10,C=2,h=3`，入边 0、3、6 | 第三盘非法 | 合法 | 仅头距不能替代整边容量 |
| `tau=2,h=5`，第一盘 0 入、2 到，第二盘计划 3 入 | 第一盘已离边 | 第二盘非法，最早 5 | 到达后不能提前删除剩余入口窗口 |

这些是模型内的确定性反例，不是现场参数测量。`ceil(headway_seconds/tick_seconds)` 才能保守离散化最小间隔；行驶时间亦向上取整，硬 deadline 的舍入另行定义，不能向上放宽后宣称准时保证。

## 2. 数据表示：保留旧默认，同时记住真实事件

当前 `model.Edge:24` 只有 `travel_time/capacity`，`Reservation:58` 只有资源、起止、tray，`InFlight:93` 有原始入边时刻。建议新增 opt-in `HeadwayEdge(Edge)` 和 `EntryReservation(Reservation)`，不改变旧工厂默认产生的 `Edge/Reservation` 类型。前者只增加 `entry_headway`；后者增加稳定 `entry_event` 与真实 `entered` 标志。此命名是建议接口，尚未实现。

采用独立 opt-in record 的原因是：给旧 dataclass 直接追加默认字段虽然可能保持行为，却会改变 `asdict`、checkpoint 指纹和序列化形状。既有历史 SHA 必须保留；默认关闭的兼容桥接仍应产生原 record 和原 cache signature。新配置必须显式选择支持 headway 的 runtime/validator/search/owner 组合，安装检查拒绝任何遗漏，不能让旧候选生成器静默忽略新 Edge 字段。

`entry_event=(tray_id,edge_id,original_depart)` 不随 `now` 裁剪改变，窗口结束时刻保存原承诺值。相同事件由计划、实际进入记录和 old-in-transit 重复描述时只算一次；**同一盘在不同时间再次进入同一边是两个事件**。`entered` 由实际运动事件标记，不能只依据 `depart <= now` 推测，因为同 tick 的事件准备、控制和实际运动存在不同 cursor 阶段。已入边事件的未过期尾窗不允许取消。

最小实现可把新 record 放进既有 `Snapshot.reservations`，从而沿用 clone/checkpoint 容器；但所有合并、过滤、资源识别处必须显式识别它。进入状态应在原 `_update_motion` 的 actual-entry 事件点同步更新，而非引入第二套物理时钟。该信息是已发生的承诺，不是环境未来任务。规则数值第一版运行内固定；后续若要改 headway，必须另定义生效和旧承诺处理，不能重算并缩短已进入事件的窗口。

## 3. 日历、验证和运行时的必要改点

| 当前定位 | 现行为/风险 | 新规则所需最小改动 |
|---|---|---|
| `runtime.py:48 candidate_reservations` | 只产生 node/edge/reception | 每腿按同一公共函数派生 entry 窗口；完整 witness 和实际提交前缀采用相同规则 |
| `runtime.py:64 _merge_reservations` | 按 `(resource,tray_id)` 合并并重建普通 Reservation | 普通物理资源保留原语义；entry 按事件身份去重，保留原 depart、结束及 entered。不同事件即使同盘也不能合并成一单位 |
| `runtime.py:82 effective_reservations` | 从旧在途补 edge/target/reception | 补真实已进入的 entry，且与显式同事件记录去重；空闲盘占位不能抹掉尾窗 |
| `runtime.py:108 capacity_conflict`、`:612 assert_invariants` | 只识别三个资源族 | 明确 entry 容量 1、合法边/整数窗口/事件一致性；全局 sweep 同时查容量和头距 |
| `runtime.py:286 validate`、`:387 commit` | 以 tray 排除自身已有日历，再原子提交 | 自己的已进入尾窗与不可取消前缀必须保留；仅允许替换对应的未来可替换记录。候选重复描述同一事件只去重，不豁免另一入边事件 |
| `runtime.py:743 _update_motion` | `:768/:801/:817` 在 old-arrive、prefix-arrive、usable 时按 tray 删除全部预约 | 三处都仅释放已完成物理承诺，保留尚未到 end 的已进入 entry 尾窗；统一到 `:1041` 的到期清理才释放 |
| `runtime.py:1067 checkpoint` 及 restore | 已有私有 `_entered_legs`，Snapshot 亦复制 | entry 的进入标志、尾窗、原事件 ID 与 cursor 一起恢复；同 tick 恢复前后必须一致，不通过重新猜测进入状态补写 |

头距尾窗不是“盘还在运输”。一盘可以已经空闲、服务其他边，但仍使原 `entry:e` 暂不可再次入边。不要将 entry 资源套入当前以 `edge:` 判断忙/在途的逻辑，使整盘全局冻结。相反，全周期的资源排空需要等待有限尾窗结束；`network_full_cycle.py:48 cycle_snapshot` 只豁免严格 node/INFINITY 停车记录的规则本来会保留 entry 尾窗为 active，应以专项确认而非扩大停车豁免。

旧在途只足以重建**仍在途**的 entry。若 `h>tau` 且初始化时盘已抵达，只有当前 stock/plan 的旧快照可能已经失去该入边历史。新实验初始化必须提供未过期的真实 entry records，或者从已绑定的合法空系统开始 warm-up；不能将无法恢复的尾窗当零占用。初始化能力检查应拒绝“在 headway 中途启用但历史不明”的状态。

## 4. 承诺、后缀替换和联合提交

`runtime.py:405 prepare_replacement` 保留原权限边界：只有显式授权的非保护载盘后缀可改；空盘目标、保护任务、旧在途不放宽。`:458` 当前删除自己的全部预约，`:463 _replacement` 又把冻结预约一律截到 `anchor_time`。这两处对新尾窗都不成立。

规划视图必须带上截至安全 anchor 仍未过期的已进入 entry 窗口，以及不可中断 no-wait 前缀中的未来 entry 承诺。冻结腿的窗口即使越过 anchor 也完整保留。仅尚未进入、属于合法可替换后缀的 entry 可撤销；实际合并提交时仍在同一版本锁内核验所有保留窗口和新窗口。不能在规划克隆中删掉限制，随后靠最终失败充当正确搜索。

类似的全 tray 排除还出现在 `joint_transactions.py:18 _stage`（`:33/:44`）和 `dependency_admission.py:139`。节点同时腾空的依赖规则不能顺带消除这些 tray 已发生的 entry 尾窗。联合事务需先区分可释放的 node/未来后缀与不可释放 entry，再将所有新增窗口一起检查、一起提交；失败不得留下半个 entry 承诺。

`runtime.py:140 _forecast_dependencies` 的 edge 指纹应包含启用后的头距。条件完整 witness 的再次验证也要查 entry 资源；next-edge 仍是“完整 witness 已验证，只提交安全前缀”，不能只验第一条 entry 就把未走后缀当必达。头距本身不扩大保护准入或取消权限。

## 5. 候选搜索必须真的会等待到合法入口

仅在 validator 加拒绝会使旧搜索漏掉简单合法解。最小贯通涉及四条路径：原整数候选 `runtime.CandidateGenerator`；固定空间 witness 的 event refinement；dynamic regional 本地和 crossing edge；full-graph/reference。

- `routing.py:158 _ResourceView` 应明确 entry 容量和事件身份，不把未知种类落入 reception 分支，也不能排除当前 tray 的未过期尾窗。
- `routing.py` 的固定 witness refinement（约 `:280–340`）除了 edge 可用，还检查 `[depart,depart+h)`。上游可等待节点的 departure 集需要加入下游 entry 窗口结束时刻减去**到该边入口**的 travel offset。不能减到边出口的 offset。
- `routing_reference.py:45 EventTimeSearch.departures` 同样补 entry endpoints 的 no-wait 链投影；`:74 paths` 的每次扩展和 `:157 dynamic_regional_candidates` 的跨区单边扩展都联合检查 edge 与 entry。no-wait 节点仍只能立即走，延迟必须前推到实际可等节点。
- 静态最短路继续按非负 travel 时间作下界；忽略额外等待仍是下界，但不是拥堵/头距可行证书。整边容量为 0 的边仍不进入拓扑。

需要特别处理**路径自身的历史窗口**。若同一盘绕行后再次入同一边，前一次 entry 可能仍未到期，不能只查查询开始时别人的日历。扩展 label 至少携带仍未过期的自身 entry 事件，检查和下一步传播这些窗口。

这也影响有限整数参考：当前 `EventTimeSearch.paths` 按 `(node,time)` 保留有限 K 条标签。加入头距后，到达相同 node/time 的两条路径可能有不同的自身尾窗，后续可行性不相同，不能直接沿用其 earliest 声明。建议小图参考采用有限 horizon 内全部整数 departure、正 travel 有界的 walk、包含自身未过期窗口的状态；只在相同充分状态下去重/支配。预算耗尽、标签截断均不给不可行/最早证书。regional 的 K、local-label cap 保留为明确启发式限制，不能把它们重新包装为证明。

## 6. 所有者和共享消息时钟

`distributed_clock.py:205 owner_of` 和 `partition_observation.py:43 resource_owner` 当前只认识 node/edge/reception。新 `entry:e` 由**原 directed edge 的 source control_partition** 所有，与原 edge 一致；这不新增供应方权限或把 logistics_zone 当 owner。

`distributed_clock.py:213 footprint` 必须与 runtime 共用相同 entry 派生语义，`:227 _conflict` 使用事件去重和容量 1。participant prepare/revalidate、lease 日历、`:755 _atomic_authorize`、`:850 _proposal_contract` 的重新计算都纳入 entry；漏报 entry 或漏 owner 的提案拒绝。owner 本地观测应看到其 entry 尾窗，不向其他参与方额外开放未发布业务未来。

准备租约只是临时资源承诺，实际进入标志只能由物理事件产生。放弃或到期的未提交 lease 可释放；已经提交/进入的尾窗不得随事务超时消失。安全 anchor、旧在途与 suffix replacement 同样适用于分布式最终提交。单个容量检查函数通过不能代替消息延迟、版本失效、两 owner 冲突及部分提交故障验证。

## 7. 缓存、恢复和已有强对照

`routing.py:30 network_signature` 明确只列出五个 edge 字段；新增头距若不入签名，就会错误复用旧拓扑/搜索配置。建议关闭分支继续返回旧签名；启用分支用新 schema 和完整 edge 参数签名，并同步 `_StaticTopology` 的解码。静态距离可复用数学结果，但不同 schema 的私有 cache/continuation 不能假称字节相同。

`routing_cache_contract.py:23` 的原 `isolated_replay_v1`、ReplayRegionalFactory、checkpoint/active-continuation 绑定保留。新启用版本必须声明物理 schema、头距 map/hash、实现 SHA、logical-work 计量与私有 cache 状态。新增 entry 查询/事件投影不能在预算里隐形；memo 仍要求完整 state/cursor/cache/candidate/exact tape/continuation 相同。不能用旧 Round7/8 值标签直接给新规则训练。

`same_zone_supply` 的静态可达保护上界在加入非负等待后仍只是上界，不能因此升级成容量保障。terminal-capacity certificate 是终点必要条件，加入额外入口约束不会让其拒绝证明失效，但包装器对新 generator 类型/规则的支持必须显式注册和验证。公平比较须让全部策略使用同一新物理内核；新模型减少冲突不算控制算法收益。

## 8. 下一轮必要验证与交付顺序

先做小而完整的实现闭环，验证重点为实际事件和守恒，不追求测试数量。

1. **默认桥接**：全头距关闭时沿用旧 record/factory，旧完整 result、每 query/search/cache、候选顺序、事件/瞬时 trace 和恢复严格相等；原件 SHA 不改。启用新 Edge 却装旧运行器必须在入口拒绝。
2. **手算窗口**：本文件四个反例；恰好 h 和 h−1；零腿；capacity=0；unknown/非整数/负 h；同事件重复导入不双算、同盘第二事件不能免检。
3. **执行尾窗**：old-arrive、prefix-arrive、unload/hold-release 后 `h>tau` 的尾窗仍在；期间重新装袋/换边允许；原 entry 到期才释放。mid-tick checkpoint 恢复与 old-in-transit 初始化等价；缺失历史显式拒绝。
4. **承诺与 owner**：进入边/no-wait 冻结前缀尾窗跨 anchor 保留；合法 suffix 只撤未来部分；保护/空盘原拒绝不变；两 owner 同窗口原子冲突、过期/重复消息、失效 lease、联合依赖/部分失败不漏限制。
5. **搜索与参考**：下游 no-wait 入口只能由上游等到合法时刻；跨区边和本地区段都受限；有回路、自身尾窗不同的同 node/time 标签不误合并；小图穷举整数参考核对最早完成及预算 unknown。
6. **原图小批**：固定真实业务身份与可审代理参数，不按收益挑时窗；先兼容桥接，再新规则所有策略共用的短 full-cycle pilot。记录 entry/edge 使用、逐袋服务、盘守恒、完整任务分母和计算/删失。完成这些后才扩 2/5 km 持续业务，而不是先跑大规模再补日历语义。

本方案没有要求先重写区内供应方模块，也没有声称中央 Snapshot 对照完成 W2 私有自治接入。入口日历由现有 edge owner 的明确接口实施；真实供应方 API/许可仍待来源确认。可先完成代理共同物理和反例，再对现场边界进行验证。
