# Outlet gate V3 独立实现审查

审查对象为 `derive_feng_dh_outlet_gate_probe.py`、派生的五个 Java 源文件、`OutletGateAudit.java` 和 `feng_dh_outlet_gate_protocol_20260905.md`。原 V3 源码与已运行结果均保留。此次仅运行短机制 fixture，没有全人口或南宁运行。

## 已证实并修复的问题

原 V3 的 `outletStopped()` 使用 tick-start snapshot 评分，却经 `lattice.entryBlocker(...).bag.getStatus()` 读取可变的现场状态。同时，零 through 节点在批准阶段立即调用 `stopPhysicalHandoff()`。两个相邻零 through 节点因而可能读取同一 tick 中不同时间的状态，违背该模拟器的同步计划约定。

新增的 `OutletGateSnapshotAudit.java` 构造 A→B→C 链：A、B 是零 through 节点，A 出口入口处的袋在快照中 moving，B 出口入口处的袋 stopped。B 的 HOLD 会把 A 出口上的袋改为 stopped。保持边和袋编号不变，仅互换 A/B 的节点编号：

| 实现 | 上游节点先处理 | 下游节点先处理 |
|---|---|---|
| 原 V3，现场 status | 上游袋离开边 | 上游袋被阻止离开 |
| V3 snapshot，冻结 status | 上游袋离开边 | 上游袋离开边 |

这是实际执行的对照结果，不只是静态推测。修正只将出口入口 footprint 的停止状态读取改为 `snapshot.occupants()`，并使用独立 METHOD。源目录为 `benchmarks/java/feng_cie_dh_outlet_gate_v3_snapshot/App`，METHOD 为 `FENG_DH_OUTLET_GATE_V3_SNAPSHOT`。

- 五源聚合 SHA-256（CRLF）：`c966079ed11c20328f21e2c601ea30bc8279387668fb9a8819b6955a6a7167fa`。
- 生产 class 聚合 SHA-256：`bbc0f4bd4dba64c144519a111623811dfab2ccfcb365754e6755a99ddf0ab785`。
- 旧 V3 的四个 fixture 同时通过：blocked-zero、blocked-positive、open-ports overlapping transfer、finite-service。前两项完成 tick 均为 67；开放双入口的 timer ready tick 仍为 16/21；有限服务完成 tick 仍为 128。

map2 中间节点均有正 through 时间，其服务者在此前已为 stopped，因此以上零 through 分支次序问题不改变已保存 V3 的 map2 行为。此处没有把机制 fixture 等价说成新增一次 map2 全人口回归。

## 科学解释的边界

代码符合 V3 所注册的窄假设：在正 through 完成释放上游前，或零 through 获准前，检查当时所选出口入口处是否存在 stopped footprint；阻塞则保留上游占位并重试。它没有增加新的固定等待、改动原 1+2 秒时长或重启已经完成的 timer。额外 policy decision 仍按原评分和 frozen snapshot 执行。

该实现仍允许多个袋在离边的 2 秒 transfer 阶段重叠；袋离边后，下游后来阻塞也不会恢复其上游占位。transfer 后继续重新选路，出口未锁存。因此它不是完整有限空间物理模型，也不是仅靠历史均值接近即可证明的原实现。原手稿中 switch 前 HOLD 的描述可以支持调查这个位置问题，但不能唯一推出全部 V3 时序。

另外，新增的 policy 调用包含在总 decision 数中；`PRE_TRANSFER_OUTLET_STOPPED` 使用现有 `stopPhysicalHandoff()`，其 trace 没有保存本次所选出口和 blocker 编号，trace=0 时也没有独立的 gate-hold 计数。现产物可以比较性能和总决策数，不能精确把新增等待逐项归因到具体出口门。`decision == null` 同样返回阻塞并记该理由，需避免把不可达状态误解为物理 stopped；正式 map2 的可达 OD 不受这个分类局限影响。

数值接受范围应服从最新用户要求：可同数量级或适度更慢。此前 5%/10% 的预注册窗口可保留为诊断列，不应继续用作用户授权的硬门槛；本审查未修改原协议或原运行解释。

验证记录和可复制命令在 `outputs/runtime/feng_dh_semantics_reaudit_20260905/outlet_gate_snapshot_fixtures/verification.json` 及同目录 README 中。
