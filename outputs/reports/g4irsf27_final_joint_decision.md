# G27 最终联合决策

## 决策

采用保持简单的组合策略：正常运行继续使用 `S4/J2/E2 + local FIFO`；仅在持久、启动前已知的线路故障下，额外启用 local goal scalar。无需新增另一套规划框架。

## 三组证据

- Table 5.2：FIFO 的 min/mean/max 对 fresh HCA 共 9 胜、2 个分辨率边界平、1 负；四种速度的 mean 和 max 均胜。
- Table 5.4：在 `LEGACY_VARIANT_RECONSTRUCTION` 下，12 个场景对 archived dynamic 为 12/12 胜，对 archived static 为 12/12 胜。这不是原缺失 legacy variant 的 exact fresh 复跑。
- Table 5.5：对 fresh HCA 为 6 胜、9 个拓扑上限平、0 负；对论文存档值为 10 胜、5 平、0 负。`pair_5_7` 仍为 `NOT_MEASURED`。

## 口径与架构边界

- Table 5.4 的 bias 是为重构论文观测偏差所做的实验扰动，不是 learning，也不作为在线学习模块启用。
- Table 5.5 与 fresh HCA 仍属于 `PROTOCOL_CONTROLLED_RECONSTRUCTION`；达到拓扑上限的 source-local reject 仍按业务失败计入，不会被隐藏为成功。
- 当前框架不调用运行时完整 A*，不生成行李未来完整路线，也不维护 HCA 全局预约表。
- 它是决策层去中心化：每个转向点只做下一跳动作；当前证据来自单进程模拟器，不声称已经物理分布式部署。
