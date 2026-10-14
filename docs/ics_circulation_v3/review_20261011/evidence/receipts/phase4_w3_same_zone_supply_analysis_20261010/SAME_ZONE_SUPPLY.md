# 同物流区直接供盘：原图续接策略缺口与最小验证设计

2026-10-10。只读源码和既有实验文件；本记录未调用仿真、候选生成器、validator 或 pickle 重建，未改冻结控制源码。新增物理回放为 0。相关文件 SHA、少量公开字段及本次提取 CPU 另存 `analysis.json`。

## 已确认的机制与边界

原图 counterflow d40 是 t126、node26 的一次载袋决策。既有 693 分支审计中的 c0/c1 成本为 192.4/146.7；当前袋完成从 139 推迟到 157，仍早于 deadline211。c0 在 t139 将 114 的 initial:49:0 承诺空返26；c1 在 t156 由已有 reactive dispatch 使用 46 的 warm_tray，下一袋装载从209提前到169，完成从222提前到182。全期 queue wait 减少40、空载 travel_time 减少57，固定权重下 J 减少45.7。这是已回放的单次当前动作干预结果，不是新方法的部署收益，也不能与同轨迹其他局部 regret 相加。

冻结输入 `phase4_w3_network_role_labels_parallel_20261009/counterflow/counterflow_input.json` 明确给出下一袋预测：`counterflow:round2:flow1`，node26→114，at156，deadline271，**published_at116**。因此它在 t126 已发布；此处原图合成 fixture 使用40tick发布提前量，不能混用小图的20tick设置。原 `PredictivePrebalancer._demand` 先过滤 future publication，再按最新 revision、TTL、planning horizon、实际可见 identity 去重（prebalance.py:166–229）；默认 publication age60、原图 planning horizon180。这只是证明预测条目的公开条件满足，尚未重建实际 slow 调用的完整筛选账，不能用 engine-only future tape 参与候选构造。

d40 JSON 的 cursor 为当前 loaded routing 阶段，`next_slow_trigger_at=127`；**t126 不是 slow 决策检查点**。任何后续验证须在真实 slow 调用进入时捕获状态，并遵守已推进的 slow clock 和实际 cursor，不能直接把 d40 的中途状态当作 t139 的状态。

公开拓扑：26 和46均为 `international`，但 owner 分别为 `synthetic:00`、`synthetic:05`；114为 `domestic`/`synthetic:04`。46→39→40→52→26 的边 travel_time 为2+2+6+3=13，容量分别14、11、54、29。d40时 warm_tray 位于46、empty、available_at87。**13tick 是公开静态路线长度**；既有 c1 证明 t156 的该响应合法，未证明 t127或t139同路线无预约冲突、节点容量冲突或源需求保护冲突。

## 源码中的策略限制与硬许可

| 位置 | 行为 | 含义 |
|---|---|---|
| `prebalance.py:330–331` | donor 和 target 的 logistics_zone 相同即 continue | 这是慢控制候选域限制，并非物理禁止 |
| `prebalance.py:231–249` | 移出 donor 后按来源 zone 与 donor node 检查需求前缀 | 原保护把 tray 当作离开来源区，不能直接用于同区服务并期待正确 credit |
| `prebalance.py:369–377` | 同一目标中按到达迟滞、空载 travel_time、tray_id 排序后才 commit | 最小直接供盘增量应在这个选择之前合并合法同区候选 |
| `runtime.py:350–360` | 仅跨物流区 export 才触发 zone export_min_stock 硬门槛 | 同区运输仍须通过其他 identity、时序、路径、容量、module 检查；W3 现有中央执行器允许同区空调 |
| `runtime.py:1002–1024` | 已接受 empty plan/empty_target 为目标计 reserved_origins；等待袋已被覆盖即跳过另行调拨 | 远处空盘先承诺后，近处供盘不能替换它；既有承诺不可撤销 |

因此这是一个**可定位的续接策略盲点**：loaded 绕行改变卸载时刻，间接改变 slow 的供盘承诺。它支持优先研究直接供盘；尚不能声称新直接策略必然消除45.7差额，也未证明某条共享边本身是容量瓶颈。此成本没有独立 loaded travel 项，当前袋绕行仍准时，解释必须保留该目标函数条件。

## W2 可复用概念，但不能直接开启开关

`distributed_local.py:39–115` 的 `local_service_guard` 要求目标与 donor 属同一 owner（第47行）；本例46→26跨 owner，所以 W2 `local_dispatch=True` 的本地服务增量不适用于此路径。它的有效思想是：目标只能在 candidate 的真实 usable_at 获得 credit，且其他已知需求每一前缀的匹配能力不能下降；实际 waiting、已发布预测与已装载 identity 分开处理，不把移走 donor 当作无条件破坏或无条件改善。

W2 原 `distributed_slow.LocalClockController` 的远端需求筛选（第190–200行）按不同 control_partition，并未按 logistics_zone 排除；原则上它能提出同zone跨owner请求，然后经过 owner 协议、源保护和预约执行。但将整个 W2 控制器替换进 W3 会同时改变消息可见性、TTL/status 延迟、prepare/authorize/lease、departure lead、时钟与调拨次序。它可作未来独立协议对照，不能包装成信息与时序完全相同的最小基线。

## 拟议独立基线与低成本验证

先做只读/私有内存候选诊断，尚未执行：在原执行真实 slow 调用处保存当前 snapshot、cursor、next slow、已发布 forecast/revision/TTL、known_supply、全部源需求和既有承诺。原 cross-zone 路径与同-zone 路径在同一次公开状态下构造、检查和排序；日志保留所有拒绝原因、前缀保护账、候选查询/expansion及预算耗尽，预算耗尽不能写成不可行。不能先提交远处原选择再追加近处候选。

独立同区增量应保持旧 cross-zone guard，另写可审查的同区服务保护：绑定一个已知目标 identity，候选完整空路径/真实 usable_at 才能兑现目标供盘；其他需求的可匹配供给前缀不得减少，不能假定远处库存瞬时可达；不动旧不可撤销承诺，不取消 source 保护，不改变 validator/fast K4/权重。需覆盖只有一个可服务其他需求的 donor、未来 publication、撤销/过期预测、已观察 identity 去重、共享占用、迟到目标、同zone跨owner等负例。若只在中央 W3 Snapshot 权限内实现，可与原中央基线保持信息边界一致；若改为 W2 owner 协议则必须单列信息/延迟差异。

候选拓展与旧 greedy 对照并列保留，明确披露候选域扩大，不能称为“完全相同的保守动作域”。保留原目标排序及迟滞/距离/tray_id 排序规则；预声明有限搜索预算、公平 donor 顺序和各查询实际耗费，不用已知 c1 成功反向挑路径、时刻或预算。

随后最小4格物理验证方案（尚未运行）：同一 d40 实际 checkpoint 的当前 fast 动作 c0/c1 × 后续 slow 原样/允许同区直接服务。每格从同一当前状态、同一未来任务流、同一硬约束续接到完整排空；新 slow 只在真实触发点用当时公开信息。比较 c1−c0 在两种续接下的变化，并报告四格全部分项、服务时刻、承诺链、终态、query/CPU及失败。用途仅是验证当前动作与 continuation 的交互机制，**不是独立部署确认**，不可把局部4格结果推广为总体收益。

若机制成立，冻结算法与预算后扩展到既有 cross_cycle、counterflow、near_full 全3条完整原图流；从原始初始状态重跑原/新策略并保留所有结果，fast 控制保持原设置。需要评价原图全实际机会时重新采集新轨迹，不能沿用旧174状态分母当作新部署分母。仍属开发验证、共享合成来源；没有新增真实运营数据或独立外部确认。对全部流的零收益、负收益、未排空和预算失败一并记录。

已有物理证据见 `phase4_w3_network_nominal_analysis_20261010/NOMINAL_MECHANISMS.md`、`NOMINAL_ALL12_TABLE.md`、`mechanisms.json`（74检查、0错误）。本记录提供下一步设计，不改变任何冻结结论。
