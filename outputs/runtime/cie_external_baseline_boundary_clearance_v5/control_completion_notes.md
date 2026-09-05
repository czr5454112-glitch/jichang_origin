# 历史 HCA 控制的段账目异常：只读追踪

**南宁 1× 三个格各少一袋，不应解释为固定时域的普通排队。** [证据 JSON](control_completion_notes.json)保存原始文件路径/SHA、三袋 canonical 与日志摘录、源码定位及全部 60 个 HCA 末态汇总；未改旧记录、归一化、资格或协议，未运行模拟。

| seed / 原始袋 | 两次成功规划 epoch | 首次导出路径预计完成 | 唯一原始 ID 完成事件 |
|---|---|---:|---:|
| 155921 / 2806 | storage_out 28240；storage_in 28435 | 28503.332 | 28708 |
| 181081 / 2806 | storage_out 28275；storage_in 28431 | 28538.332 | 28643 |
| 232003 / 2838 | storage_in 31349；storage_out 31551 | 31560.136 | 31735 |

观察事实：三格均覆盖全部 canonical 段及 release；每袋两段都出现成功规划日志，但只有一个 `task_id, finish_epoch` 完成事件。第二次规划比首次导出路径的预计完成分别早 68.332、107.332、9.136 秒。到 epoch 98259，三格的 native `active_route_count=0`、`unfinished_count=0`，而 generated 比 completed 多一段。保留 28,505/28,506 的原始袋完成计数符合现存事件；不能以“一袋很少”补全。

静态机制：wrapper 的 `readTaskList`（467、481 行）给 EBS 两段相同 raw task ID；`ICS_PathFinding` 的 `saved_routes` 以该整数为键（21 行），成功规划直接 `put`（150 行）；同 ID 的约束也会替换（294–315 行）。`Tasks.generate_tasks` 从该 map 生成后续进度/完成（171 行），因此覆盖影响实际执行，不只是导出遗漏。`recordNewRoutes` 只记录新 key（369–398 行），第二条路径未保存；Python 又按同 raw ID 的成功规划 FIFO 匹配完成（311–319 行），所以 lifecycle 中具体哪个段被标成未完成存在归属歧义。

这组记录强烈支持“重叠 EBS 段覆盖活动路径”的解释。旧运行没有 class SHA，逐 epoch 文件也已清理，不能把当前可读源码当成已恢复的当时二进制，或从仅含 raw ID 的完成日志证明真实完成了哪一段。既有日志不能无歧义恢复丢失路径及其反事实完成时间。

| HCA 组 | 正残差格数 | `generated − completed − active_routes − unfinished` |
|---|---:|---:|
| map2 1× | 0/10 | 0 |
| 南宁 1× | 3/10 | 0–1 |
| map2 1.75× | 10/10 | 24–42 |
| map2 2× | 10/10 | 77–125 |
| 南宁 1.75× | 10/10 | 9–44 |
| 南宁 2× | 10/10 | 12–22 |

合计 **43/60 格存在生成段无法由末态账户解释的缺口**。其他 40 格仅查到汇总残差，未逐袋证明与三例相同的根因。建议这 43 格另标 `INVALIDATED_HCA_SEGMENT_ACCOUNTING_DEFICIT_FOR_PHYSICAL_PERFORMANCE_COMPARISON`：保留数值作为历史执行/日志观测，但不作为无丢失物理 HCA 基线的性能或容量证据。尤其不能把南宁 1× 平均 0.3 袋差解读为 G31 容量优势。剩余 17 格此次未见残差，不等于已消除构建身份缺口或证明全部物理语义正确。本页仅提出旁车建议，没有改写冻结结果。

只改完成追踪 key 不能修复这一机制。可考虑的最小新实现是在 wrapper 向 HCA 交任务前分配唯一 segment execution ID，并保存它到 raw ID/leg/OD 的映射，让现有活动路径、进度与约束统一使用唯一 ID；不必因此改 A* 公式，但它改变真实执行，仍须独立标识，不能回填旧日志。ID 改变可能影响 HashMap 遍历；EBS 两段物理先后依赖也不会自动恢复，另加先后等待属于额外语义改变。当前不实施或重跑。
