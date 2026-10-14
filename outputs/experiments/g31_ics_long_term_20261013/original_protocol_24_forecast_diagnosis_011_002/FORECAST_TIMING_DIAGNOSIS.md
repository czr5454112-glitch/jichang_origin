# Frozen011 服务预测时序诊断

这是原始执行回执的独立核对，加上 5 场预先声明的小型 native011 边界实验。它不证明原图事件触发控制已经改善，也不构成研究创新。未修改原图合同、2 秒命令延迟、S4 物理顺序或区内模块权限。

## 原图 16 条拒绝

`original_protocol_24_011_001` 的 predictive_r2 和 joint_r1_r2 各有 16 条首次服务预测请求，全部在实际入边之后才到源 owner 执行，拒绝理由均为 `no_local_uncommitted_loaded_service`。逐条请求时间、执行时间、入边时间、对应 bag/tray、合法阶段起点和公开驻留窗保存在本目录 `diagnosis.json` 的 `original_policies.*.rows`。

如果只移除固定周期采样滞后，保留 2 秒通信延迟，分类如下：

| 已观测阶段起点 | 可见驻留时间 | 数量 | 可得结论 |
|---|---:|---:|---|
| Storage 实际释放 | 0.001 秒 | 3 | 即刻合法通知仍严格晚于入边 |
| 实际 LOAD_COMPLETE | 1 秒 | 3 | 即刻合法通知仍严格晚于入边 |
| 实际 EDGE_EXIT | 1.5 秒 | 4 | 即刻合法通知仍严格晚于入边 |
| 实际 EDGE_EXIT | 2 秒 | 6 | 到达时间恰等于入边；必须检查同刻原生顺序 |

所有 24 件输入的装载/卸载时长均为 0、hold 为 1 秒。零时长装载不能创造一个可中断的 loading 阶段；控制必须等整个时间戳处理完毕。16 条中 12 条发给同 owner，4 条跨 owner。

第一版诊断 001 的布尔量检查的是“是否严格早于入边”，不能据其全为 false 推断同刻 6 条必然拒绝。001 保留，002 明确细分并加入真实相等边界实验。

## 五场真实 native011 边界结果

共同 fixture 来自 tiny_cycle：只保留 B1、去掉预置 transfers，将节点 1 的 resource_owner 设为 B，节点 0 保持 A。完成 t=0 全时间戳后，A 向 B 提交 T0 的 next=1 服务预测；command_delay=2、publication_delay=0.5、ACK delay=0.2。仅改变下面预声明的 load 与节点 0 service 参数。

| Load | Service | 源执行结果 | 实际首条 EDGE_ENTER | 旧 entry_estimate |
|---:|---:|---|---:|---:|
| 0 | 0.001 | rejected: tray_not_visible_to_owner | 0.001 | 无 |
| 0 | 1.5 | rejected: no_local_uncommitted_loaded_service | 1.5 | 无 |
| 0 | 2 | delivered | 2 | 4 |
| 0 | 3 | delivered | 3 | 5 |
| 3 | 0.001 | delivered | 3.001 | 3.001 |

相等边界的命令确实能够在 t=2 同刻合流提交前通过。该合成见证不替代原图 6 条分支的实际重放。所有五场通过已有物理事件账一致性审计；完整输入、公开观察、请求、ACK、接收消息和物理结果在 `raw.json.gz`。

## 发现的正确性问题

`publish_circulation_service_forecast` 的 loaded 分支把 `ready` 设为 capture 时刻 `now`，随后再加完整当前节点 service。它没有扣除已经真实消耗的服务时间。上表 2 秒和 3 秒场景直接复现此偏移。即使 ACK 成功，也不能称预测有效：2 秒场景接收者在 2.5 收到消息，实际早已在 2 入边，而旧消息错误表示将在 4 入边。

修正需区分真实 loading、等待源服务 admission、正在服务、服务已完成等待仲裁。实际服务开始/ready 时间必须来自已经发生的本地 admission 或到达事件，并绑定当前 leg/node；checkpoint、seal、恢复和循环回访都需覆盖。源节点专用的 BagState.admitted_time 不能代表之后各节点。不得读取未来事件堆来补算。

对于服务已完成的 junction queue，剩余服务应为 0；对于尚未 admission 的 source queue，LOAD_COMPLETE 不能证明服务已经开始。正确服务剩余时间仍不保证未来资源无冲突，因此消息继续是 conditional。

## 控制与创新边界

下一跳的软服务窗口只覆盖局部条件占用，不能提供整个跨区路线的硬容量保证、最终卸载/hold 后的空盘释放保证、额外导出权限或真实库存。事件触发能减少采样滞后，但不能消除协议延迟、冻结物理微阶段或使未授权 route 合法。应同时报告消息送达、时间有效性、真实预测误差和实际业务结果。

通知的成对测试应固定所有本地可见事实与已送达消息，改变未到业务、未公告故障和无关远区事件，要求本 owner 的通知内容、序号和控制激活时间不变。全时间戳预算中断不得暴露半完成状态，也不得把私有全局下一事件时间当作 owner 唤醒时间。详细测试建议见 `interpretation.json`。

## 身份与复现

冻结 binary SHA256：`19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec`。本轮独立核对时，build011 与 live_validation_009 所登记源文件均与当前字节一致；live009 报告 342 项通过，未替代为本轮重跑。原用户 bounded_local_pibt.hpp SHA256 仍为 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`；两个工作区 staged 均为空。随后其他代理开始正常研发，不能把这一时点核验当作后来工作树完全未变。

复现：在 circulation 工作区运行 `C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_long_term_20261013/original_protocol_24_forecast_diagnosis_011_002/diagnose.py`。五场模拟本身约 0.043 秒；原 Windows 默认权限尝试在加载 binary 前失败，获准本地执行后退出码 0。两次尝试均记入 `execution_receipt.json`。
