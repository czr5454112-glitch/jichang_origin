# native028 独立门禁审查与 C 学习输入边界

结论：未发现阻止已登记的单支 C00 有限校准的实质源码或实测问题。该结论不等于机场完整业务完成、全图无死锁、旧版全部回归通过或完整请求低于 100 ms。

独立标准库审计保存于 `outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/native028_independent_review_001/audit.py` 和 `report.json`；实际执行 458 项检查，没有导入控制器、模型、门禁实现或 native，没有启动 native 或训练。报告 SHA256：`12bf094396a4fdc4d423073014c1fd4740334f1694716c75f6eba9710835e1fe`。证据以 gate002、accepted contract 与 C00 plan 的已保存引用为准。

## 源码和真实门禁

逐项审查七个 C++ 差异：新增 node 字段默认 0；Python 输入拒绝布尔值和非整数，runtime 拒绝负值及 reserve≥capacity；策略检查只位于 pending empty-transfer 的既有 source/receiver/stock/capacity 校验之后、`reception_node` 提交之前。物理 `can_enter`、FIFO、edge headway、原容量和已提交 lease 的后续执行代码没有修改。单次循环依次看到前项实际 reservation，故不是基于过期 sender snapshot 的许可。

默认零的 public node 字段不输出；checkpoint seal 和 planning static digest 仅在有非零策略时增加版本化段。默认零未增加这些摘要的字节，非零策略被摘要绑定。C++ 新单元测试源补了已 departed 自身 reservation 与 loaded 第四槽，但本次 build receipt 明确 `ctest_executed=false`，不能将测试源码存在写成该 C++ 测试已实际执行。

gate002 真实保存的两个隔离 worker 均 exit 0，旧版 1 次构造、新版 8 次构造，合计 9 次，无 fork，无自动重试。新版 8 次包含四个正常参数场景与四个真正触发构造异常的输入，并没有漏算异常构造预算。核对 297 个证据文件 SHA 全部相符。

| 实际场景 | 空盘结果 | 载货与其他证据 |
|---|---|---|
| native027 省略字段 | E1、E2 都 received | loaded 在 t=20 仍在途 |
| native028 省略字段 | 与 027 全输出相同 | checkpoint/static digest/事件/ACK/时间均保留比较 |
| native028 显式 0 | 与省略字段相同 | 仅比较时将输入中的显式零规范为省略 |
| native028 reserve1 | E1 received，E2 以 `receiver_transit_reserve` 拒绝 | loaded 在 1.002 完成；最终接收节点实际容纳 L/E1/P0/P1 四盘；E1 已出发后取消被拒，最终唯一收到 |
| native028 reserve2 | 两个新空盘请求均被 reserve 拒绝 | loaded 完成 |
| -1、capacity=4、1.5、True | 各触发实际 `ValueError` | 原因均为 `invalid_receiver_transit_reserve` |

独立比对比生产门禁更窄：只移除真实出现的 `outputs[].returned.wall_seconds` 和 `outputs[].returned.advance.wall_seconds` 两条诊断路径。未删除模拟时间、事件顺序、租约时间、收发 ACK 或物理状态字段，旧版/新版默认输出仍严格相等。reserve1 在同一 session 上 advance→restore 初始 checkpoint，时钟回到 0 且 seal 一致；这证明该次初始态恢复，不扩展成“任意中途在途 checkpoint 都已实测恢复”。default/reserve1/reserve2 的初始 seal 与 planning static digest 分别三个不同值。

## C00 准备核对

`C00_receiver_admission_001/plan.json` SHA256：`569689ae525b3d5d40ab0d08ff5e8599cfd6ca7d151bc74345c09d496d619789`。105 个来源文件与各自归档 SHA 一致。实际输入删除唯一 node49 的 `empty_receive_transit_reserve=1` 后，与 `C00_cyclic_od_001` 的实际输入逐对象严格相同，包含完整 28506 jobs、22 trays、图、物理容量与全部业务时间。

controller 不变；单 session 从 0 warmup 到 57600，后续边界为 58200/58800/59400；预算一支，无预测模型输入，`observed_counts=None`。本审计核对准备资格，不替随后 C00 的执行结果作结论。accepted contract 保留 `legacy44plus21_reexecuted=false`、`complete_request_100ms_certified=false` 与 `global_deadlock_freedom_established=false`。

## 当前 public payload 对六账户的支持

这些是下一版本 adapter 的进入条件，不是已经接入或已训练的声明。当前 `foundation_action_value.py` 是 detached interface；`foundation_airport_observations.py` 被动保存实际 callback 入参/返回，不新增查询或标签。

| 账户 | 合法现有来源 | 必须保留的边界 |
|---|---|---|
| current_free_trays | 本属主当前 tray sensors、node `actual_available` | 逐盘核 empty、无在途、availability≤now，排除已承诺 outbound；跨账户按物理 tray 去重，不能跨 generation 重算供给 |
| known_waiting_jobs | `control_projection.waiting_groups` 的真实 `count` 与 `demand_observed_at` | `jobs` 只是有限 FIFO 代表行，不能按其长度算全部队列；远端已送达 snapshot 只表示捕获时刻，不能标成 now 的完整远端队列 |
| loaded_release_forecast | 本地可见载货 job contract/操作开始事实，或已送达且未失效的 service forecast | 仅条件估计；不变为当前空盘、未来真值或硬供应，保持依赖、generation、时点与来源 |
| committed_inbound | 需要接收方实际可见、能绑定 payload+tray+generation+ACK 的证据 | 当前 callback 的 `transfers` 来自本属主 `client_transfer_ledger`。它不能证明另一属主发来的 inbound 已承诺；本轮不能借全局 result/truth 补齐 |
| committed_outbound | 本属主不可变请求 payload 与实际送达 ACK | 保留原生 `departed` 等状态；必要的 generation 要从提交前合法 observation 绑定；不能把未收到 ACK 的处理结果当已知 |
| unresolved_requests | 本属主已发送 payload 及 pending/缺失最终 ACK 状态 | 未确认不算 inbound；需要保存完整本属主范围和 cutoff，不能用空列表代表所有区域都已确认无请求 |

每个 account×region 分别说明 visible、complete 与 observed_at；未知保留已观测 lower bound，缺少任一必要完整性证据时不计算假定完整的 deficit。当前 coverage 接口自身不是 native 认证，adapter 必须把声明绑定到真实 endpoint 范围与捕获证据。

原生 planning v3 可传递已收到的 source action ACK，但现有 `submitted_physical_actions` 没有完整 tray/source/destination transfer payload；仅凭 request_id/status 仍不足以为接收方构造合规 inbound 账。若需要跨 owner 完整入账，应另立版本化、受权限限制的 payload+ACK 发布或 receiver lease endpoint；不是从离线结果反向补账。

## 进入真实 flight-learning 前还需闭合

1. 先审新 C00 的连续流、未完成业务保留与实际空盘机会。运行到边界不等于全部业务完成；没有合法候选/空盘时不应伪造动作样本。
2. 对实际 recorder 样本做 detached adapter 回放，逐 account×region 检查未知掩码、waiting group 精确计数、时序与物理盘去重。当前 public job payload 没有可验证的 flight/STD 关联键，不得用 private crosswalk、group 总数或 opaque ID 反查来填 `observed_counts`；主接口继续 None。
3. 静态计划及 B1 冻结模型只在合法 freeze cutoff 之后消费，保留研究性的预置可用假设、mapping/business/model/context 哈希。需求预测不创建业务或库存，不能复用小域 FQI 的权重冒称机场模型。
4. 登记动作条件的真实训练采集：提交前合法 observation、完整同预算 candidate mask、动作语义、原生 guard 与 ACK/物理执行、完整业务结果及同 owner 后继。缺失/拒绝/超时保留未知或排除原因，不能 label=0。候选监督与 Bellman 多步训练分别验收。
5. 预登记 parent/episode 级 train/development/holdout 划分及训练预算，先冻结选择规则再接触 holdout；有完整连续数据与不同可选后果才进入 FQI。现有 single-day B1 误差、异步并发证据或小域两 case formal 结果均不能替代这些机场验收。
