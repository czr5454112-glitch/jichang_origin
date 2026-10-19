# C00 cyclic OD 独立原生审计

本次运行到达 59400，证据链闭合；它没有证明完整流完成或持续循环。28,506 件中实际观察 20,924 件，装载 19 件，完成 7 件，12 件在途，20,905 件已到达但等待空盘，7,582 件尚未到达。原生 `completed_count=29` 是 17 次入存储、7 次业务卸载、5 次空盘返回，不能称 29 件业务完成。

`audit.py` 只用标准库读取原始回执、公共观察和历史归档，不导入控制器、模型或原生模块。102 份源归档与各自 pin 一致，574 个 acceptance 绑定文件字节一致；输入、计划、原始结果、观察归档和 worker 回执关联通过。这里只核验保存的闭合证据，没有重新执行旧 verifier 或原生仿真。

## 真实停滞与资源环

最后 EDGE_ENTER 在 21380.124，最后 EDGE_EXIT 在 21386.479；之后至 59400 没有边移动，停滞 38013.521 秒。最后业务完成在 20886.597，最后 storage release 在 22200，最后资源唤醒/等待在 22200.001。系统继续接收业务和协议消息，并非时钟停止。

| 节点 | 物理托盘 | 远端接收预留 | 主要等待 |
|---|---:|---:|---|
| 49 | 0 | 4 | 容量 4 全被空盘目的地预留占用 |
| 53 | 4 | 0 | 四件载货盘，唯一出口 53→49 被挡住 |
| 112 | 4 | 0 | 最早到达的空盘 initial:138:0 要经 53 才能到 49 |
| 29 | 4 | 0 | 队首先前 RESOURCE_WAIT，偏好通往已满的 112 |
| 28 | 4 | 0 | 唯一出口 28→29 |
| 40 | 2 | 0 | 偏好出口 40→28 被挡住 |
| 137 | 2 | 0 | 唯一出口 137→112 |
| 116 | 1 | 0 | 真空盘 initial:26:0，反复请求 49 被拒绝 |
| 136 | 1 | 0 | initial:136:1 已隔离，不能当作可用空盘 |

节点 49 的四项接收预留分别属于 initial:138:0、initial:138:1、initial:24:0、initial:0:0，授予时刻为 11342、11342、20863.652、20942。它们全部真实 departed，尚未 received。原生 occupancy 同时计物理占位、在途下一跳和远端接收预留，每个托盘只计一次。49 的唯一入边是 53→49；因此空盘持有 49 的名额却仍在 53 的上游，而 53 载货盘需要 49 才能离开。四预留把共享出口彻底封死。

原始结果 `trace_limit=0` 没有输出全部候选评分和内部队列。表中的 FIFO 队首与偏好链由实际入边/等待事件和已冻结 FIFO/S4 源语义推断，不能冒充导出的完整调度器状态。53→49 的唯一出口、四项接收预留和容量闭锁则可直接核实。逐盘证据保存在 `tray_wait_for.json`。

## 唯一失败与旧控制器处理

请求 `live:21:owner:system_domestic:transfer:115` 在 11342 获准把 initial:136:1 从 136 运往 26。首次物理入边 136→137 一直无法执行；当时 137 已被四只真实托盘占满。11839.48900001 出现 `departure_lease_expired_before_physical_entry`，未使用的 node26 接收预留释放，但真实托盘留在 136，模式变为 quarantined。请求重发保持相同 payload；失败 ACK 在 11882.2 实际送达。此后没有恢复操作。

旧 controller 排除 quarantined 托盘并保留失败，不会伪造空盘。虽然原生有 `recover_empty_tray`，其绑定要求 legacy 模式；当前 owner protocol 模式会拒绝该端点，而协议命令白名单没有 recover。不能绕过 R2 直接调用旧接口，也不能取消已 departed 的接收预留。完整不可变重试和 ACK 证据在 `failed_request.json`。

## 公共观察及 C10 的实际可达分支

被动采集实际保存了 946 条 owner callback 输入和原始返回，时间为 43200..59400；owner 本地托盘范围、消息 delivered_at、own client ledger、sequence、artifact SHA 均核验。记录包含有范围与时效的公共需求分组和候选，未产生 conditional outcome label；这一已停滞段不能证明学习优化或多步 RL。

真实可用空盘并非全零：domestic owner 可见 initial:26:0@116。它有 642 次 116→49 的 receiving_full 拒绝。国际 owner 没有实际空盘。

激活后的 57660..59400 共 105 条实际 callback：45 条已有 baseline intents，60 条没有 intents 且没有可导出 actual_available supply；没有一次进入新 planner 的 forecast 调用分支。因此当前 C10 在这些状态上不改变动作。`counterfactual_C10_gate_from_actual_observations.json` 保存逐条分支判定；这是只读条件检查，**不是 C10 原生实验**。本轮不再消耗一次相同 C10 原生运行。

## 下一项明确版本化实验

在同 151 节点、227 边、22 盘、28,506 件、物理容量 4、FIFO、服务、租约和 R2 下，从物理 0 开始共同启用 receiver admission policy：只对 node49 的新 empty-transfer 预留保留一个通行槽。现有原生事务在提交 `reception_node` 之前，用真实 occupancy 检查 `occupancy < capacity - 1`；loaded 的物理 `can_enter` 继续使用 capacity=4。默认 reserve=0 必须逐事件、输入、ACK、checkpoint 与旧 native027 一致。

这足以阻止本次第四远端预留占满 49 的具体条件；不等于全网无死锁证明，下游和 FIFO 阻塞仍需新原生基线检验。不能事后改变本次记录，也不能先宣称预测收益。新模型 B1 冻结于 43200，早于该时刻的自然空盘窗口不能直接使用 B1；可预登记新基线共同热身到 43200 后的连续窗口，或另立有合法历史数据的更早模型合同。
