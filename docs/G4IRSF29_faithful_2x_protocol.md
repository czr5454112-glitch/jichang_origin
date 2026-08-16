# G4IRSF29：遵循原论文业务逻辑的 2× 任务流实验协议

## 目标

本轮保持原论文的地图、业务日、速度科目、速度偏差科目、线路中断科目和固定仿真终点，比较原始集中式 HCA* 与当前局部决策框架：

`S4 route score + J2 destination merge + E2 event hot path + junction-local FIFO + service-aware static potential`

线路中断时，仅增加确定性的节点局部结构故障值。它不是在线 learning，也不生成完整路线。

目标不是制造“所有数字严格更小”的机械结论。成功率已经达到 100%、拓扑可达上限或论文显示精度边界时，合理终点是平局；其余可区分单元要求 S4 胜出，并且整个可测矩阵不出现退化。

## 为什么不是简单复制

论文说明行李及其到达时间来自一天的航班时刻表。原始 raw 输入包含 28,506 件行李，并形成 360 个 `(STD, end, Unloader)` 航班组，分布于 13 条 `(end, Unloader)` 航班序列。

G29 在 raw 行李层扩流：

1. 原始航班和原始行李全部保留。
2. 在同一航班序列的相邻 STD 中点插入一班。
3. 序列末班使用该序列历史正班距的 lower-median 的一半外推。
4. 插入航班复制父航班的完整 source、loader、end、unloader 行李构成。
5. 每件复制行李的 `EntryTime` 与 `STD` 同加同一个时间偏移，因此 `STD-EntryTime`、直达/EBS 分类和 storage-out 提前 2700 秒的规则不变。
6. 原始 task ID 保留；新增行李使用全局唯一 ID。先写 raw txt，再用原有 parser 和 early-bag expansion 从同一 raw 文件生成 canonical JSONL。

这表示在同一个业务日中增加中间航班、提高航班到达强度，而不是把 segment 文件复制一遍并加 0.01 秒偏移。

正式 2× cohort：

- 57,012 件 raw 行李；
- 87,206 个 route segments；
- 720 个航班（360 原始 + 360 插入）；
- 26,818 件直达行李；
- 30,194 件 EBS 行李；
- 各装载站、起点、终点和卸载口总量恰好为原始输入的 2×；
- 最新 EntryTime 为 82,403.72582 秒，最新 STD 为 85,500 秒，仍在同一业务日内。

## 比较规则

### 固定时间边界

- start epoch：8260；
- 运行窗口：90,000 epochs；
- 最后有效 epoch：98,259；
- 不为了让 2× 完成而延长正式窗口。

### 基础速度与 Table 5.3

- 速度：1.5、2.0、2.5、3.0 m/s；
- 每个速度 fresh 运行原 Java HCA*；
- HCA* 每个速度两个独立 Java 进程重复；
- S4 使用该速度 HCA* run 1 的逐 segment release trace；
- 只有当 HCA* 全量释放 87,206 个 segment 时，才把 exact-release 结果签为全量配对；否则只报告固定 57,012 分母的容量结果。

### Table 5.4

遗失的原动态/静态偏差实现不能伪装成 fresh exact baseline。G29沿用已公开的 legacy-variant reconstruction：标准速度决定规划与自由流运动，节点处加入固定 seed 的确定性观测偏差流，并明确标记为 reconstruction。旧的全图整日降速只保留为 stress evidence，不进入原论文精确胜负。

### Table 5.5

- 故障在 epoch 8260 生效并持续到正式窗口结束；
- 地图、16 个论文场景、固定 57,012 分母和成功率定义沿用上一轮；
- `pair_5_7` 的归档来源存在互相矛盾的边定义，继续标记 `NOT_MEASURED`，不人为选择一个有利版本；
- 拓扑不可达行李仍计业务失败；达到删除故障边后的可达上限时记为 ceiling tie。

## 简单性边界

本轮不增加新的规划器、learning 层、全局预约表或完整未来路线。S4 每次仍只给当前转向点的候选出边打分；J2 只处理目标节点的局部合流许可；E2 只减少不必要事件发布。FIFO 与 service-aware potential 都是节点局部规则，故障值也是按目标保存的邻居结构标量。

如果 2.5 m/s 完整 2× 门槛失败，先分解 source wait、route/network 和 merge wait。只有证据明确指向现有局部拥堵项时，才允许对一个已有全局权重做一次很小的三点比较；不叠加新策略层。

## 分阶段执行

1. 生成并审计 2× raw/canonical cohort。
2. 对完整 raw bag 做小规模 HCA*→release→S4 贯通测试。
3. 运行 2.5 m/s 完整 2× 停止门。
4. 停止门通过后再展开其余速度、偏差和线路中断矩阵。
5. 报告所有负结果、上限平局和协议缺口；不把 survivor cohort、归档数据或 reconstruction 写成 fresh exact 胜利。
