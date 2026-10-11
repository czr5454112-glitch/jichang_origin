# 第六轮独立同区供盘：实现与作者验证

新源码为 `scripts/experiments/ics_circulation_v3/same_zone_supply.py`，作者专项为 `tests/test_ics_circulation_v3_same_zone_supply.py`。未编辑原 prebalance/runtime/validator/build_engine/C++，未修改默认控制策略，未提交或推送。原有 workspace 的修改不在本任务内回退。

## 接口与行为

`SameZoneSupplyPrebalancer(PredictivePrebalancer)` 保留原构造参数、`plan(snapshot, forecasts) -> PrebalancePlan`、`__call__`、`history`、`last_diagnostics`。新增参数为 `max_same_zone_candidates=32`、`max_guard_work=200000`、`max_guard_demand_units=4096`。同区配额为0时直接调用旧 `plan`，作者4个旧fixture验证 proposals/search调用完全相同。wrapper 的 clock、forecast publication、cursor、routing cache 由调用者保留，类不重建或更改这些对象。

原 `max_candidates=32` 在此类中是跨区专属配额，新32为同区额外配额，合计最多64次 route generator 调用。每个目标中两个候选域轮转查询，各域内维持 tray_id 排序；所有保留候选在 commit 前统一按原 `(max(0,usable_at-need_at), travel_time_sum, tray_id)` 排序。未先接受跨区方案再补近处盘。应与 old32、old64同时比较，不能宣称相同计算预算或相同动作域。

跨区 `_donor_protection` 仍使用旧 `_demand` 聚合需求。新增同区保护使用完整稳定单位账：可见真实 bag identity 优先，已承载/已完成/已观察 identity 不重复引入预测需求；已发布预测仍按旧函数处理版本、取消、TTL、horizon。相同 identity 且相同加载节点/有效释放时间的重复空盘需求只记一次，不同加载节点/有效释放时间冲突则报错；这项跨forecast去重与旧聚合target遍历存在差异，已明确披露，正式输入须核对是否实际含此类重叠。匿名槽有明确 `anonymous:` key，不能冒充真实业务 identity。目标信用只是保护计算中的一次分配，原 FIFO 不因此承诺由指定袋使用指定盘。

## 保护与时间语义

公开 `SameZoneDemand(key,node,at,source,unit_id=None)`、`GuardWorkBudget(limit,used)` 和 `same_zone_service_guard(snapshot,candidate,units,target_key,work_budget=...,horizon_end=...)` 供独立审查。guard只读；完整空路线的实际许可仍须先经原 ExecutionValidator。guard另检查实际可用 donor、完整空路径和 unload/hold 时序，保护来源物流区需求，source/target owner与zone从原拓扑读取，不改标签。

每个真实盘仅贡献一个 `known_supply` first-release。全公开有向正容量图允许途经其他物流区；最短静态 travel 加目标hold计算最早乐观供盘时点，同节点known release不重复加hold。此可达能力忽略动态共享容量，是上界而非联合运输可行证书；候选物理执行始终由原 validator 控制。

类显式传 `horizon_end=now+planning_horizon`。在 `[now,horizon_end]` 内检查需求释放、每个供给到每个需求的最早可用时点、candidate实际usable/目标service时点及两端点。所有其他需求保持原释放时间；仅当前目标使用 `max(need_at,usable_at)`，在该时点前无credit。每个前缀分别要求：其他需求的时序匹配数不降；原节点确定供给对其他需求的匹配数不降；移除donor后的其他匹配加合法目标credit不少于原总匹配。一个盘在每个前缀至多匹配一个单位，已接受目标仍在需求账中，后续scratch里的已承诺供应也只能用一次。

静态距离缓存只存在于一次plan内部，共享该次不变公开网络，hold时序逐candidate重算；不跨snapshot缓存。三项保护都只对这一公开近似和有限规划区间成立，不保证原图全局无死锁、真实任务按时、所有未来需求或成本不增加。

同区增强遇到 visible protected bag 尚无已承诺路线时保守阻断，具体bag IDs落账，旧跨区行为不改变。已有不可撤销 empty plan/empty_target继续覆盖目标；未知终点ETA不编造供给时点，也不派替代盘。latest-departure shift 通过 validator 后再运行同区guard，使用最终真实usable_at。

## 有界计算与失败分类

`max_demand_units` 只限制目标遍历，不截断保护需求账。完整单位账超过 `max_guard_demand_units` 时禁用同区增强，跨区仍按旧完整聚合需求保护。`max_guard_work` 计单位展开、图边/heap/relax、匹配邻接及增广操作；任意不完整计算均以 `same_zone_guard_work_budget` 拒绝新增同区动作，不能把部分检查当作通过。账中分别保留 `demand_expansion_work`、`guard_work`、每个candidate guard前缀/工作量、分域route调用/expansions与候选配额遗漏。

同区生成器的 `exhausted/expansion_budget_exhausted/deadline_exhausted` 归 `same_zone_search_budget_unknown`。其他有界搜索未返回候选为 `same_zone_search_no_candidate`，不称物理不可行证明；仅明确的 `static_unreachable` 独立记录。旧cross诊断原理由保留。计数预算不把一个generator内部搜索变成可中断调用；可选wall预算仍是查询间检查，正式对照设置None。

## 作者测试与失败记录

`authoring_initial.json` 保留首次pytest收集失败：作者验证脚本没有把项目根插入sys.path，导致 `ModuleNotFoundError: scripts.experiments`，没有测试或部署回放完成。该次宿主CPU2.078125秒、wall2.1839781秒。

只修验证脚本导入路径后，`authoring_path_repaired.json` 保存23项作者测试全部通过，宿主CPU1.265625秒、wall1.3097504秒，测试期间绑定源码未变化。覆盖统一排名、禁用回旧策略、真实hold/迟到目标、跨owner、publication/TTL/取消/观察去重、身份冲突、两目标一次供盘、未来来源需求、路径绕别zone、工作/候选预算、完整保护账与目标截断、未接纳protected、既有承诺、接收容量、错误candidate identity、类型和engine-only未来拒绝、明确horizon与搜索预算分类。

独立审查者另有自己的 `test_ics_circulation_v3_same_zone_supply_audit.py` 与第六轮审查目录。其9项guard初测、20项controller初测是分开的已计量运行，不与作者23项混称一次验证；后续最终审查和根完整回归由各自清单记录。作者未运行原图物理实验，后续6格机制/全流对照由独立runner负责。

这里记录设计与测试边界，不能代替后续全量负例、强基线预算对照或部署结果。
