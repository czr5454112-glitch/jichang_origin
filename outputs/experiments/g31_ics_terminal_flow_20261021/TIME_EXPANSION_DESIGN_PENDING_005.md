# 600 秒时间展开候选：待 005 证据决定的设计

状态：**DESIGN_PENDING；未实现、未注册新实验、未运行原生或大型离线分析。**

本文件仅记录任务书 §6.5 触发后的可选方案。它不宣布触发成立，不宣布性能改善，也不将小规模代理优化称为完整 ICS 最优。冻结 005 与其正在进行的实验保持原样。

## 1. 触发证据与比较边界

应从闭合的 005 证据判断：不同来源 ETA 是否持续改变首动作；运输时长与需求箱宽相当时排名是否不稳定；多盘计划的首批到达是否系统性低估；条件释放或接收空间的时间变化是否决定价值。报告合法菜单、多来源/多目的地、已知评分、排除 pending claim、实际提交及收到的分母，按独立场景区分重复决策。

旧 002 两种箱宽的短门各见同一场景一次 ETA 换源，不能当作两个独立持续事件。旧 003 个别长延迟也不能独自证明时间展开模型会改善服务。005 的变化须使用匹配其冻结演员的重建方法，不借用旧版本解释新演员。

候选继续使用相同公开信息、预测、600 秒主代理及运输接口。900/1800 秒视野、需求箱宽、重算周期、延迟风险费用、预测器变更均应另行登记，不能随时间层方案一起暗改。

## 2. 可复用实现与接线风险

已核对的实现（均位于 `scripts/experiments/g31_ics_circulation/`）：

- `foundation_airport_joint_opportunities.py`：PreparedCurrent、完整共同合法菜单、真实 owner/tray、硬保留/FIFO 保护和 service-aware public travel。
- `foundation_airport_terminal_graph.py`：合法站点弧、公开路径、接收覆盖和容量；不宣称宏观弧具有独立物理容量。
- `foundation_airport_transport_allocation.py`：build_supply_offers、source cap、真实盘资格、来源机会成本、递减接收边际、显式费用；当前 MCF 的派发 profile 在求解后生成。
- `foundation_airport_inventory_projection.py`：PreparedProjection、合法供给事件、simulate_node 的精确事件流体队列；project_action 复核当前真实单动作。
- `foundation_airport_transport_orders.py`：跨 owner 逻辑 claim、实际请求账本和捕获时间支配；pending claim 不是物理库存事件。
- `foundation_airport_transport_control.py`：当前菜单重绑、精确单动作复核、ordinary fallback、缓存与订单创建。

**不能直接把时间层 chosen 列表交给现有适配器。** `choose_next_legal_action` 会遍历所有 chosen，按当前单动作 exact gain 重排；`execution_dispatch_profile` 又从当前时刻重新生成连续槽位。因此它可能把本应等待的未来动作提前，抹去计划中的 HOLD，或者改变时间优化确定的首动作。

若触发实现，须增加独立候选 policy/adapter 分支：仅取当前槽位指定动作，用最新完整菜单重绑并复核；当前槽位 HOLD 时不得挑未来动作补位。未来建议保留原 submit/departure/ETA，重算必须显式生成新版本。当前动作失效时按预先冻结的回退规则处理，并记录失效原因。首动作单独校验可复用既有 project_action；它不能被描述为整份计划价值的独立证明。

真实 demand/necessary clearing/恢复仍由现有优先控制先执行。同 owner/tick 至多一次新尝试、异常也消费额度、同请求 ID 重试和恢复状态继续由原控制器执行。规划器不能自行重置额度，不能因拒绝立刻换盘再发。

## 3. 为什么共享槽位不能直接塞进普通 MCF

例如同一 owner 的盘 A 只允许来源 A→J，盘 B 只允许来源 B→L。若建 `tray → shared owner-slot(capacity=1) → destination`，A 进入共享槽位后可以离开到 L：流已经忘记进入时的来源/盘资格。

令 A 来源机会成本为 0、J 收益为 0，B 来源机会成本为 100、L 收益为 200。合法最优为 B→L、净收益 100；错误网络可以选择 A→L、虚构净收益 200。随后真实菜单拒绝它，不能挽救该优化模型的正确性。

将 slot 复制到每个 tray 层能保存资格，但所有副本总容量 ≤1 是额外耦合约束，普通单边容量无法表达。逐源、逐盘、逐接收端和逐 owner-slot 的多类约束不能普遍视为保持整数性的纯网络流。

应使用始终绑定 `(tray, source, destination, owner, slot)` 的显式选择变量，或者直接枚举这样的完整合法动作元组。若使用 MILP，需明确其侧约束和求解界；若用 MCF 作初始建议或松弛界，只能在证明相应界有效时报告 gap。

## 4. 最小身份与容量模型

对当前 owner 的实际可调盘 r，固定 `source(r)`、`owner(r)`、`source_category(r)` 和完整合法目的地集合。仅为菜单中真实动作建立二元变量 `x[r,d,k]`。未来公开可见库存不等于当前 owner 有权调度的供给。

主视野为 `[now, now+600]`。槽位从控制器的 next eligible tick 开始，每 60 秒一个，最多 10 个视野内新提交槽位；不能在已经消费的当前 tick 再分配槽位。不同 owner 的容量不能互借。第一版仍按当前 owner 求解，跨 owner 只使用合法已送达报价/claim；不增设可直接替远端发命令的中央执行器。

显式约束：

1. 每个真实盘：`sum(d,k) x[r,d,k] + HOLD[r] = 1`，最多调拨一次，不在视野内把它再导出第二次。
2. 每个来源：`sum(r at source,d,k) x[r,d,k] <= source_cap[source]`；上限来自原真实未承诺盘、FIFO 和硬保留，不从预测补货扩张当前供给。
3. 每个 owner-slot：`sum(r owned by owner,d) x[r,d,k] <= 1`。
4. 每个接收端：第一版使用当前保守接收槽位总上限，先按原规则扣除尚未被物理 coverage 覆盖的 claims；不能对同一已覆盖盘重复扣容量。
5. 盘的目标资格、可用时刻、已知路径和 owner 权限均约束同一个变量；不得在共享节点后重新匹配来源。

HOLD 是合法结果。这里按所有菜单真实盘定义 HOLD，数量口径与旧 MCF 按 source_cap 流量单位统计的 HOLD 不完全相同，输出须同时记录菜单盘数、source_cap、计划移动数与 HOLD 分母，不直接混比。

ordinary return 保留原类别及保护顺序，不能靠更高预测收益挤掉。可采用分层/词典序目标：先满足当前可行 protected return 并保护它的最早合法机会，再在剩余容量中优化 optional。当前 receiver 未覆盖时，仍由原普通回流 C00 fallback 做当前动作选择；不能凭预测生成一个未来可用接收槽位。无合法目标则明确 deferred。

若要建随时间变化的接收槽位，只能来自合法公开且时间明确的容量/释放证据，并与既有 reserve/ACK 去重；未来预测需求消耗不是接收槽位已释放的事实。这是第一版之外的显式扩展。

## 5. 时间、供给事件和来源机会成本

每个计划动作计算：

```
submit  = next_eligible_tick + k * 60
depart  = max(actual_available_at, action.earliest_departure,
              submit + command_delay_seconds)
arrival = depart + public_service_aware_complete_travel_seconds
```

保留分数秒 ETA，**不向 60 秒箱首下取整**。60 秒只表示提交机会；库存模拟的事件切点包含需求边界、合法供给事件和实际估计到达时刻。若用粗层承载容量而不得不取整，容量只能保守向后处理，并另存原 ETA 供真实事件评分。

这里“精确”指公开模型内精确事件时点，不意味着预测原生排队、故障、接收拒绝或真实到达时刻。未来优先业务和拒绝还可能推迟后续槽位，建议时刻仍是乐观下界。

已有 accepted inbound / conditional_next_release 事件只在 PreparedProjection 允许的估计时刻进入站点代理。它们不能自动成为当前 build_supply_offers 中可下令调出的真实盘。新订单仍须等待对应 owner 的新鲜合法菜单与实际盘身份。不能把未来未知空盘或 forecast 需求变成调拨供给。

最小可复用评分：对整份计划，每个受影响站点只调用一次 `simulate_node`，使用原合法事件加上计划到达事件，比较计划与 HOLD baseline 的 backlog area；同一站既调出又调入时联合计算。这样不会把多个独立单盘收益直接相加、重复覆盖同一需求。所有缺失覆盖保持 unknown，不能填零后赋予正收益。来源成本仅来自同一合法 PreparedProjection，不读取未来标签或其他 owner 未送达信息。

为复用原数量代理的来源边际，最小版可保守地在评分中从 now 扣除所有计划调出的当前真实盘，视作“计划内提前预留”的来源机会成本；这不写 native reserve，也不创建未来订单承诺。该假设限制了等待期间本地利用，必须写入模型名和 assumption flags。

若希望未来提交前仍能本地消耗那些盘，必须另实现带时刻扣除、库存不足拒绝和真实身份依赖的事件模型。当前 `simulate_node` 只接受非负供给，不能塞负 supply 假装支持延迟调出。未来盘是否仍存在必须重新核验。第一版实际盘/提前预留模型能处理 ETA 与派发序列，不宣称已经解决条件释放后再调拨的全过程；若 §6.5 的决定性触发正是后者，应另行界定扩展范围。

继续显式记录 transport_penalty_weight、command_delay、slot_seconds 和 minimum_net_gain。原 delay 近似是否保留为额外正则须事先登记：精确 ETA 已进入 backlog 评分，不能悄悄重复计作同一等待代价，也不能在时序对照中隐含改权重。晚于某次缺盘的动作可能仍减少后续等待；不能永久删除该 OD。超出 600 秒的到达不在本轮视野内提前增加库存。

## 6. 搜索方式、预算和标签

推荐先做小规模显式计划搜索，并将 MILP 作为另一种可选实现。SciPy>=1.13 已列在 pyproject 的 research 可选依赖中，但这不证明当前运行环境已具有指定 MILP 能力；采用时需冻结实际版本、选项和求解器状态。

**完整菜单的全计划 enumeration 一般不可行。** 候选多、10 个槽位、HOLD 与多目的地使组合数快速增长。旧运行 cache 命中为 0，不能假设昂贵搜索只偶尔执行；事件失效可能每 tick 发生。不能先实现无界搜索再寄望缓存降低成本。

共同菜单必须完整生成、完整计数并绑定 digest。若搜索采用 top-K、beam、限定总移动盘数、候选分组或节点数上限，必须只作为优化器内部限制，保留 `full_legal_menu` 与 `searched_subset` 的独立审计，记录被排除的真实盘/OD及规则。不得用 forecast 裁剪共同菜单并伪称所有方法使用同一完整菜单。只有完全同 owner/来源/目的资格/可用时刻/依赖的盘才可作等价分组，输出前证明逐盘匹配并保留身份。

在注册中明确 `max_expanded_nodes`、`max_wall_seconds`、`beam_width`、`max_plan_moves`（若使用）、候选限制和确定性 tie break。值须根据小规模公开样本的纯离线成本及剩余预算确定，本文件不授权任何具体算量。限制到达后返回已有可行计划或 HOLD；不得自动扩大预算或重试。

输出至少包括完整/搜索候选数、展开节点数、各阶段耗时、截断原因、求解状态和实际返回可行性。只有真正穷尽所声明候选/时序集合才可称该代理集合内最优；beam 或截断搜索标为 `capped_approximate`。没有有效上/下界时 gap 为 unknown，不能填 0。即便 MILP 对所给线性目标求得最优，也不等于精确流体整计划目标，更不等于原生 ICS 最优。

简单 MILP 可表达上述身份与容量约束，但把单盘预计算收益作为线性系数仍是分离代理，不能自动处理多次到达的递减价值。要声称等价于 `simulate_node`，需另证明有限服务率、库存/排队和强制服务规则的分段约束。第一版枚举完整计划并直接调用事件评分，模型边界更容易审计。

## 7. 实现前的必要小测试

- A/B 盘共享 slot 的反例：绝不能输出 A→L；每盘资格和来源成本始终绑定。
- 一来源多盘但 source_cap=1；同 owner 同 slot 两动作；两个 owner 各一个 slot；都检查正确容量口径。
- HOLD 在 slot0、动作在 slot1 时，适配器不得提前；精确复核失效不能改变已消费 tick；异常与同 ID retry 保持既有合同。
- ETA 位于需求边界前/后分数秒，库存只在 arrival 后增加；600 秒外到达不提前计入。
- 两盘到同一目标、两来源竞争同一需求，以及同站既出又入，整计划收益不重复覆盖需求。
- 已覆盖与未覆盖 claim 分别只扣一次；pending 不作库存；ordinary return 不被 optional 挤占，unknown 接收端使用显式 fallback/deferred。
- 未到期的条件释放/accepted inbound 不成为当前可调盘；同盘不在一个计划中二次导出。
- 全候选小样本穷举与优化结果一致；搜索截断保持可行、标签正确、菜单审计不丢失；恢复 JSON 后 slot/HOLD/身份/版本不变化。

## 8. 登记与停止条件

等 005 完整触发证据后决定是否实现。若实现，新增独立模块及显式 policy/method 标识，形成新的 source manifest、测试证明和预注册比较合同；不修改 005 冻结字节，不把新求解器接到旧 source 的报告里。

新方法使用同信息、同接口、同 parent/有效窗的对照，并说明只改变规划时序。涉及公共控制变化时，保留严格基线等价门禁；不通过则保留失败，另做同新 source 的完整配对，不能放宽行为等价以复用旧对照。

预算、硬件/资源准入和科学晋级条件先登记。无触发证据、代理改进不足、执行落地不足或没有服务改善均应如实报告；不预先承诺扩大视野、进入 TEST 或获得性能收益。本文不新增任何 native start，也不改变当前 005 的有限串行流程。
