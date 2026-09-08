# G31 通知驱动的故障势修复与原生停车

日期：2026-09-07。状态：实现说明与已执行的 C++ 补充验收；正式二进制及真实地图回归的最终身份由独立构建、回归产物绑定。

## 动机与授权范围

旧 `b00fd178…` 原生 G31 在真实 map2 的 `0→47` 单袋反例中，行李进入 `0→6` 后收到 `6→12` 断线通知。原图势 `H(6)=42.2`、`H(8)=42.6`，严格下降门拒绝仍然可达的 `6→8` 绕行，行李在节点 6 等待至固定时域。该不利原件和完整原生输出保留在 `outputs/evidence/paper_suite_20260907/cpp_bounded_preflight_v2/`，不以新版本覆盖。南宁 `0→16`、在途时刻 2 秒断 `1→2` 的旧版已经可以完成；该例用于安全回归，不冒称旧版失败。

用户据此授权只在故障存在时启用修复，尽量保持正常运行行为。新能力是 G31 系统的明确新增机制；旧二进制、其他方法及既有观测结果不变。它不是对原算法来源真实性的新证明，也不通过关闭严格下降门、替换失败场景或预读未来故障解决反例。

## 输入合同与正常路径

开关为 `enable_s4_advertised_fault_potential_repair`，默认 `false`；新套件方法身份为 `G31_S4_ADVERTISED_FAULT_REPAIR_V1`，不得沿用旧 b00 的方法/二进制身份。支持域限定为当前 G31：S4、严格下降开启、故障通知策略开启、E4 目的节点仲裁、M3、`jit_fair_aging_deadline`，DLP 关闭，源端 admission 关闭且 `local_queue_capacity=0`。新开关拒绝超出该组合的配置；这不承诺其他源端准入、有限本地队列、PIBT 或学习干预组合的恢复能力。

原始请求携带原图的 service-aware H。不得在 Python 中提前按未来断边重写新 G31 的 H。开关关闭时全部新路由分支跳过；开关开启而没有已通知的有效断边时直接读取原 H，不运行全图重建。调度的临时 eligible deque 使用 `optional`，仅存在已停车行李时才构造，正常路径无新增 deque 堆分配。新遥测在绑定层仅对开关开启的结果出现。

源端人口和时钟不变：袋仍按原生 release 排入 source queue，经原有本地服务进入 junction queue；不在请求端删不可达袋，也不新增源端预筛。当前正式源端配置无 first-edge credit/下游准入阻断且本地队列不限长，因此结构不可达停车可在 junction 决策处处理。未释放袋仍保留在原生人口与时域分母中。

## 通知后的势与可达性

实现位于 `cpp/ics_core/runtime/event_driven_junction.hpp`，核心函数 `refresh_s4_advertised_fault_potential`。触发点是 `process_fault_message` 中已经交付的通知更新，含零延迟通知的等价分支。集合只取 `advertised_faults_` 中 `faulted=true` 的有向边，不使用 `physical_faults_`、未交付消息、未来事件窗口或未来 `repair_time` 计算 H。

当有效已通知断边集合改变时，从原图排除这些边，对每个目的节点做反向 Dijkstra：

`H_F(g,g)=0`

`H_F(u,g)=min_(u,v 未被广告禁用) [max(service(u), minimum_service_seconds) + length(u,v)/speed(u,v) + H_F(v,g)]`

这与原 service-aware 势的节点服务归属一致。缓存仅存有限可达的 `(node,goal)`，缓存中不存在该键是独立的不可达标记，不能拿原 H 的大有限哨兵代替可达性。`s4_local_effective_potential` 返回可空值；严格下降仍按最新 H 过滤。不可达候选的旧有限 H 仅可用于原生字段序列化，不能绕过可达性/严格下降门获得提交资格。目的节点自身为零，不会停车。

重叠故障仍按现有广告 generation 和物理 active-count 通知语义处理；旧 generation 的迟到通知不能覆盖新状态。相同有效集合不重建。全部已通知故障修复后直接清空修复缓存并恢复原 H，而非重新估计一个近似的正常 H。

这是通知事件上的全图预处理，不能宣称整个故障机制只有一跳计算。当前实现逐目标重建，稀疏图上约 `O(V(E+V) log V)` 时间、最多 `O(V²+E)` 空间；另有待提交请求撤销及节点唤醒工作。故障期间候选缓存是有序映射查找；原正常 H 查找路径保留。没有物化行李全程预约，也不扫描全局预约表求路径。

## 未提交请求、在途袋与停车

远处的断线通知也可能使某个已排队的 next-hop 不再严格下降，即使该直接边的 fault generation 未变。因此集合改变时对所有未提交 M3 pending request 使用现有 `reject_destination_merge_request` 完整撤销路径，重评下一步。该路径清除 pending id/lineage、发布原请求的 held 决策并安排重试；保留队列公平年龄，不计成袋路线失败。原生 retry 计数仍反映这一被撤销尝试。

已提交 capability、活动预约和在途边不回滚，不从故障修复函数清 calendar。它们继续使用原有物理互锁与 edge-exit 流程。新严格下降要求约束重新选择/尚未提交的决策，不强迫已提交行程回退。

节点上不可达的袋保持原生 `kJunctionQueue` 状态、当前合法位置、队列占用、身份和等待年龄；加入独立停车集合后停止无意义的定时路线尝试。选择 eligible queue 时排除停车袋，使同一队列中仍可达的其他袋继续使用原有选择规则。整队已停车时不再重复安排 junction wakeup。停车不消耗 max-decisions，不提前 fail，不从袋人口或物理占用中移除。

后续已通知拓扑改变时，重评所有停车袋；当前节点重新可达的袋移出停车集合，唤醒其原队列，包括远离断边上游的节点。若直到固定时域仍不可达，按原生终止流程记录未完成。不能因看到未来永不 repair 而提前永久删除，也不能因预知未来 repair 而提前唤醒。

`reset()` 清空三个新状态容器；checkpoint/restore 直接复制有效断边、势缓存与停车集合，不重新计算或增加重建计数。启用时这些状态进入 fault/scorer digest；关闭时旧摘要路径不新增标记。

## 可审计遥测和限制

新增 summary 字段：

| 字段 | 含义 |
|---|---|
| `s4_advertised_fault_potential_repair_enabled` | 新机制是否启用 |
| `s4_fault_potential_rebuild_count` | 非空有效集合变化后的全目标重建次数 |
| `s4_fault_potential_active_advertised_edge_count` | 当前广告禁用边数 |
| `s4_fault_potential_restore_original_count` | 从非空故障集合恢复原 H 的次数 |
| `s4_fault_potential_relaxation_count` | 重建中扫描的反向前驱边次数 |
| `s4_fault_potential_rebuild_wall_seconds` | 集合变化确认后，重建/恢复、请求撤销与队列唤醒区段的实际 wall time |
| `s4_fault_unreachable_park_count` | 停车事件数，含可能再次停车 |
| `s4_fault_unreachable_wakeup_count` | 因广告拓扑恢复可达而唤醒的事件数 |
| `s4_fault_unreachable_active_parked_count` | 终止前尚在停车集合中的袋数 |

事件原因包括 `s4_advertised_topology_potential_rebuild`、`s4_advertised_topology_potential_restore_original`、`s4_advertised_topology_unreachable_park` 和 `s4_advertised_topology_unreachable_wakeup`。有限 trace 必须披露截断；完整 bags 仍保存。wall-time 遥测不用于声称字节确定性或纯路由选择开销。

独立回归文件为 `tests/test_g31_fault_potential_repair.py`。验收应覆盖真实旧反例、南宁在途安全、同时/先后断边、延迟通知、暂时/永久不可达、repair 后原 H 恢复、无故障 enabled/disabled/旧 b00 对照。另有 `cpp/tests/test_g31_advertised_fault_reset.cpp`（CMake target `test_g31_advertised_fault_reset`）直接调用生产公开 API，验证同对象重复 run、真实停车状态的 checkpoint/restore、同队列可达袋继续和源端支持域拒绝；不使用 testing 宏或开放生产私有状态。无故障比较去掉非确定 wall-time 观测后核对科学字段；不得把有限用例通过外推为所有连续几何碰撞自由或所有故障必定完成。最终原生二进制 SHA、测试清单和补充同对象 reset/checkpoint 证据由构建与验收索引记录。

主论文全天故障合同是首次路由时所有方法同时已知、整日无恢复的断线适应。该合同在本反例发现前依据原文设置选定；新 G31 通过时刻零的通知获得信息，仍须核对首路由前的事件顺序。中途未知故障是独立能力探针，不拿全天已知的结果冒称未知故障重规划结果。用户最终缩小的正式故障比较仅包含 G31 与 HCA、2.5 m/s；基础速度比较仍包含四种方法。

## 已执行的 C++ 补充验收

最终 HPP SHA256 为 `6a5aed6ebf6b594fa066531cefc82ba5451b281578cb07e48ea09f4c4c52f990`。实际执行 `test_g31_advertised_fault_reset.exe` 返回码 0，四项均通过：同对象重复运行、停车状态 checkpoint/restore、同队列可达同行李继续完成、拒绝三种不支持的源端配置。源测试 SHA256 为 `6a5485734e501fe99c3c9415d350008b6b351d4d27d08bc91da5b9e9c080eb8f`。

可执行文件、源测试副本、真实 stdout/stderr 和逐文件哈希已固定于 `outputs/evidence/paper_suite_20260907/g31_advertised_fault_repair/reset_checkpoint_v1/`；`verification.json` SHA256 为 `800cf05cded6147cae37c01b28e53f21eecb23901bc5e00023c1a0bc18ee535b`。这是三/四节点合成图的真实生产 C++ API 验收，范围不同于另一个代理的真实 map2/南宁有界回归，也不是全人口实验。

最终原生二进制 SHA256 `38b07ddfbc661c5243ab62a4963d84514405a87b11afa41538a94a42d2665b20` 的真实地图有界回归为 14/14 通过，无失败或跳过；索引为 `outputs/runtime/g31_fault_potential_repair_20260907/microtests/38b07ddfbc661c52/microtests.json`。两图各一组 1×、seed 104729 的无故障 on/off 全人口对照也已通过，每组 43,602 段全部完成、完整逐袋原生字段逐值相同；对应 `outputs/runtime/g31_fault_paper_suite_validation_20260907/normal_full_v1/comparison.json`。共同 D 的平均 THT 分别为 map2 `245.8608527969567` 秒、南宁 `624.6038851227836` 秒。单组 wall-time 起伏不据此称为加速或退化；该比较也不是全部种子/负载的性能证明。

首次全人口 off 结果曾被有限 lifecycle 日志的截断总门拦下。保留原生字节后，独立读码将执行状态结构不变量与日志完整性分列重新审计；没有修改 native 或把原 `protocol_integrity=false` 改写成 true。完整生命周期日志达到上限，或固定时域结束时仍有合法在途 grant/pending，均可能使要求“日志完整且最终静止”的总标记为 false。因此后续套件必须分别保留原标记、丢行数、在途/pending 数和结构性安全断言；只有全人口完成时才要求最终静止，不能以日志缺失或仍在途作为自动的物理违规证明，也不能反过来把这些限制隐去。

Tarau 的基础新旧二进制对照另见 `outputs/evidence/paper_suite_20260907/tarau_native_identity_equivalence_v2/verification.json`：两图三速度的完整单袋，以及两图持 COMMITTED grant 的固定时域截断，共 8 个 paired case，逐袋、决定、事件、held 尝试及 merge lifecycle 科学字段均相同。12 个完整时长 native controls 保留于 v1、4 个新增截断记录保留于 v2。两个截断例都满足 runtime-owned、exact-slot、conservation、bijection 四个结构不变量与 postcommit compensation，同时 `final_active_unconsumed=1`、pending=0、native 总标记 false。新旧标记在此相同，不冒称新版本修正了该例的原生 boolean；这是区分结构正确与最终静止的实证。最终 Tarau 使用 38b 的默认关闭分支，不能借此宣称其启用 G31 故障修复。
