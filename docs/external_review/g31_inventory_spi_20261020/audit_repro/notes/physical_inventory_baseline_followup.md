# R0 极简当前库存回流：现有公开字段复用与最小 v1 合同

只读源码审阅，固定提交 `1d895da00644c9486568fe74b835e057aa93f8c8`。没有 native/fit。结论：**可先复用已有 planning_snapshot v1 获取对端捕获时刻的实际空盘数量；现有 demand 消息不能替代库存消息，现有公开字段也不能一般性还原跨owner全部已承诺incoming。无需为了第一版R0先建设新的大型规划协议。**

## 现成能力与边界

| 所需信息 | 当前已有字段 | 能诚实声称的语义 |
|---|---|---|
| 本owner节点当前空盘 | `observe_protocol...node_contracts[].actual_available` | 当前本地传感。binding:184–191仅对本owner节点填动态量；远端缺字段不是0。 |
| 对端实际空盘 | `protocol_planning_snapshots(owner)` 返回的 `capture.nodes[].actual_available` | 源端实际执行捕获时刻的空盘数，非接收时刻即时库存。snapshot_impl:127–132调用`empty_stock`。 |
| 对端当前已释放需求 | 现有`demand.jobs` / compact等待组 | 当前已送达需求快照；binding:284–300无库存字段。不能用`waiting_count=0`推断有空盘。 |
| 本方发出的未决分配 | `client_transfer_ledger` | 本方payload+最后已送达ACK；binding:518–535，不能当全部发送方承诺总量。 |
| 已显示的incoming实体/接收承诺 | 本地传感或capture的`trays[].reception_node/edge_to/mode` | 能按实体ID去重的已观察部分。不能覆盖仍在其他owner区域的全部来盘。 |
| 对端未表示占用 | `capture.nodes[].unrepresented_occupancy` | 该节点实际占用中未被源端本地tray集合解释的部分；可能来自远端接收租约/入边。不是确定incoming空盘数。 |

`planning_snapshot` 已有 command→源端native capture→publication_delay→真实接收→ACK链。binding:404–409禁止调用者注入自写body，只允许身份/owner/目标/延迟/有效期。getter:458–472只返回已送达最新revision；最新过期时保留其过期状态，不允许回退到旧库存。capture还带source/target、captured_at、valid_until、publication_sequence、static_contract_sha256、coverage和payload digest（binding:687–740）。可复用`native_planning_adapter.capture_digest`的独立编码函数，不应直接引入要求全局完备的旧联合规划adapter。

v2/v3不是解决完整incoming的捷径。v2的submitted_physical_actions仅传request_id/kind/已送达ACK，没有对应destination/tray payload（snapshot_impl:168–179）；v3额外传真实入边证据，不给未入边全部远端接收承诺。**禁止用 occupancy−actual_available 冒充 incoming_empty；载货、隔离、hold等都可占位置。**

当前机场`foundation_airport_protocol_v2.py`和`protocol_control.py`没有启用planning_snapshot发布/读取，因此要新增明确的控制器接线，不可称已有34支运行已具有该库存信息。

## 可以马上实现的 R0 v1

1. 新建纯函数 `foundation_airport_inventory_rule.py`。输入只含当前owner公开观察、真实已送达库存capture、本方outbox；输出原transfer intent，不访问session的offline接口、result、未来jobs或未来释放估计。
2. 本owner使用实时actual_available；对端使用最新已送达且未过期、owner/node/static-contract匹配的`planning_snapshot`库存。输出每个库存项的value、as_of、source_message_id、fresh/unknown状态；缺失/过期不设0。
3. 初始版以`reported actual stock`排序，用本方未决请求做去重/防重复分配。若将本方outstanding纳入分配覆盖量，字段须称`known_own_assignment_coverage`，不能称远端当前实际库存或全部committed incoming；pending只有未决意图，dispatching/departed才有已送达的接受证据。捕获前的已接收数量与当前outbox不得无条件相加，避免一只盘重复计数。
4. 同owner返回已有静态loader；跨owner无库存快照时，库存均衡保持unknown并回退已送达真实需求服务/合法本地回流。真实当前需求足以触发原规则服务，不应因没有库存snapshot而把实际业务饿死。
5. 复用现有`client.submit(source,"planning_snapshot",{target_owner,message_delay,publication_delay,expiry})`和`session.protocol_planning_snapshots(owner)`，仅增加共享的发布/接收接线及R0输入适配。按已冻结的控制tick或实际库存变化发布，维持每channel单活跃请求及原retry；validity独立命名冻结，不与B1预测期混用。所有对比组采用相同公开消息机制。
6. 现有snapshot会携带所有当前waiting jobs，机场长窗口可能很大。第一版机制门禁应记录bytes/capture/serialize耗时；若开销成为实测瓶颈，再做只含本地stock/deficit/receiver承诺计数的版本化薄消息，共用原消息/身份/送达/ACK框架。不要为了“计数回流”引入全图即时中央状态或新求解器。

## 基本回流和可选均衡必须分开

三类优先级依次是：

1. **当前真实需求服务**：对已到达、已发布的真实排队需求，从满足源FIFO/min-stock的实际空盘中分配；不应用可选均衡的库存差阈值。
2. **基本卸载回流/mandatory clearing**：空盘停在非loader卸载/完成位置，需要返回合法loader维持循环，或已有terminal pressure要求清位。即使源只有1盘、目标loader为0盘，也允许正常回流，不受“差值至少2”或可选冷却阻挡。无需求时的回流理由是`ordinary_return_to_loader`，不是构造一件future job。
3. **无当前需求的loader之间可选均衡**：才使用预先冻结的hysteresis/冷却和库存差阈值，防止两个装载入口把单盘在1↔0之间来回搬运。阈值是此可选动作的规则，不可修改native `export_min_stock`或变成基本回流的附加禁止条件。

所有动作仍保留真实源库存、当前源业务FIFO、接收资格、capacity/reserve、不可撤已承诺租约、原实体首边和ACK。source→destination的actual_available/incoming只用于排序，最终授权仍在真正执行时由原native检查。

## 如确实需要完整committed incoming计数

优先补一个窄的源端本地inventory capture。由**接收节点owner**按自身已授予的空盘接收承诺去重计数，发布`node,actual_empty,waiting_count,accepted_empty_incoming,as_of,valid_until,coverage`；既有未知占用保留，pending未授予意图不算accepted。不要在发送者读取全局transfer真值。新字段须有新schema/digest，不能悄悄改旧v1 payload语义。

已送达receiver计数是捕获时刻事实。若再与sender未决请求合并，必须去重或保留区间/unknown；不能把不同时刻的两个计数直接相加宣称是精确总库存。初版也可只使用receiver计数，把本方未决请求另作发送抑制而不加进实际库存。

## 最小语义门禁

- 非loader卸载点1盘→loader0盘、无未来job：可完成基本回流。
- loader A1/B0、无真实需求：可选hysteresis可抑制1↔0振荡。
- 同一A1/B0但B有真实已发布排队需求：不能因hysteresis阻止服务。
- 对端库存缺失/过期不是0；已送达新revision过期后不得复活旧revision。
- 同一实体的actual/pending/accepted/received标签不得多次计入库存；pending不算已接受承诺。
- 跨owner库存改变但消息未送达，actor结果不得偷偷反映新库存；最终receiver仍可拒绝陈旧方案。
- 共同wakeup修复先验收，R0/C00/C10/RL采用同一修复/恢复/消息策略重新比较，旧C00名称不改写。
