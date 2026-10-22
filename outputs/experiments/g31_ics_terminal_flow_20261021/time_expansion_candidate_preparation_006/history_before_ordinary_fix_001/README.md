# Pending 时间层纯参考原型

**未启用，未登记为新实验，不构成对 005 是否触发 §6.5 的判断。** 本目录只有独立原型、极小纯测试及测试回执。没有修改 scripts/src、冻结 005、driver、模型或账本，也没有运行 native、读取真实 DEV、进行大型性能测试。

`pending_time_solver.solve_pending` 接受已有共同菜单、真实供给 offers、接收 contract、PreparedProjection、未记账 claim/物理 coverage、明确 next eligible tick 和显式 Config。没有生产默认参数、CLI 派发入口或 native/controller import。该接口检查完整输入菜单的每个真实动作与 offers 一致，并记录完整菜单 digest；它没有重新执行原共同菜单构建器，不能自行证明调用者没有伪造菜单。

## 已实现的最小语义

- 600 秒代理、60 秒 owner 提交槽，保留分数秒 departure/arrival；HOLD 可占每个槽。当前 tick 已消费时返回当前 HOLD，未来动作仍在原 submit_at，不提前、不压缩。
- 每个选择始终绑定真实 tray/source/destination/owner/slot。一个真实盘最多一次、来源总 cap、接收端总剩余 cap、当前 owner 每槽一次。只接受本 owner 当前实际盘；跨 owner 可见盘不作为可直接下令的供给。
- 普通回流按“最大可行数量、尽早槽位”的词典序保护，然后比较整计划代价。若当前普通回流未得到可用建议，明确要求原基线继续履行保护，不能将原型局限当成关闭普通回流的命令。
- 用冻结 005 原 `simulate_node` 对每个受影响站点的整计划计值；同时考虑同站调出和调入，保留原已确认承诺供给事件的 ETA。读取并校验原文件 SHA，仅加载其 `require` 和 `simulate_node` 原 AST 函数及 stdlib defaultdict，没有加载演员/native 依赖。
- 计划选中的源盘从 now 起在代理内保守预留；这只影响评分，不产生真实订单、reserve 或 native 承诺。来源机会成本与接收收益来自同一合法公开投影。没有盘循环、未来重新调出或未知盘供给。
- 所有费用和搜索上限均由 Config 显式提供。延迟罚项若启用是额外登记正则，不能冒称另一份物理等待成本。

## 明确不支持的情况

**存在任意未时序化 logical claim 时返回 `unsupported_claim_timing`。** 同时提供扣除尚未被 coverage 代表的 claim 后的接收容量审计，但不搜索、不增加 pending 实体库存、不发明需求覆盖收益界。`current_slot_action=None`、`baseline_fallback_required=true`，这不是 HOLD 指令；未来调用者必须保留受保护 ordinary/基线回退，不能因原型未支持 claim 而改合同。

普通回流涉及未知接收覆盖或未知代理状态时，同样返回 `unsupported_protected_coverage` 和明确基线回退。可选动作涉及未知覆盖时保留在完整菜单和排除审计中，不参与已知代理评分，不补零/猜造接收空间。

原型只支持当前单 owner 调度，未实现跨 owner 的联合时空资源模型。原生共享瓶颈、故障、真实 priority、拒绝和未来实际盘可用性仍未建模；公开精确事件 ETA 不等于真实到达保证。next eligible tick 是调用者必须从真实配额状态取得的输入，原型不消费额度、不重试、不改请求 ID。

## 搜索与结果解释

实现为显式动作元组的穷举参考，尚无 beam/MILP。分支包含全部覆盖可评分的合法动作以及 HOLD，**不使用单动作得分正负剪枝**。极小纯例证明：两个单独非正收益动作可能通过补偿来源库存而获得正的整计划代理收益。

来源/盘/接收容量不满足的分支只作硬可行性排除。完整枚举具有指数复杂度；不能在菜单较大、事件每 tick 失效、cache 命中为零的运行中直接部署。显式 `max_expanded_nodes`、`max_completed_plans` 和 `max_wall_seconds` 约束搜索；时间限制从基线评分后搜索入口起计，不能宣称硬限制整个调用的准备/文件校验时间。单次站点模拟不可中断，限制在搜索节点边界检查。

穷尽所声明的覆盖可评分动作/槽集合后标记 `optimal_within_declared_proxy_and_slot_grid`；触及任一限制则 `capped_approximate`。报告完整菜单动作/盘数、可评分动作数、实际槽时刻、展开节点数、完整计划数、重复可行性拒绝、截断原因及耗时。不存在已证明的目标界，因此 gap 为 null。初始全 HOLD 可行解单列，未混入完整枚举计划分母。没有宣称原生 ICS 最优或服务提升。

`dispatch_profile` 保留原始槽位和 HOLD；`current_slot_action` 仅表示当前指定元组，仍不是授权执行动作。`current_slot_standalone_score` 同时报告首动作单独的代理代价。联合补偿纯例的首动作可能单独非正，因而不能假称已通过旧控制器的正单动作复核；未来是否保留/变更该接线合同须另外明确登记。

**禁止接入旧适配器直接使用。** 旧 `choose_next_legal_action` 会即时重排 chosen，旧 `execution_dispatch_profile` 会重新压成连续槽；这会破坏本原型的指定首动作和等待安排。未来实现需新接口分支并再次完整验证 ordinary、真实 priority、同 tick 异常消费、同 ID 重试、当前菜单重绑、恢复和缓存，而本原型未实现这些执行层行为。

## 纯测试范围

测试仅使用 1–3 只合成盘和 10 个槽的小例，涵盖共享 slot 偷源反例、真实盘重复、owner 配额、来源 cap、共享接收 cap、分数 ETA、多来源时序排名、来源机会成本、两个非正单动作的联合补偿、ordinary 优先、unknown/claim fallback、已消费当前 tick、未来原槽位、已有承诺 ETA、600 秒外到达、搜索预算及无输入修改。没有真实 DEV 结论或大规模算量估计。

待 005 完整触发证据后，再决定是否扩展 timed claim、采用更有界的搜索/整数模型或不晋级。任何生产实现必须新 source manifest、明确方法与比较合同、纯验证和预算准入；本目录不授权修改 005 或新启动实验。
