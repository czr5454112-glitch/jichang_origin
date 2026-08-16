# G4IRSF30：遵循航班业务逻辑的 3× 固定窗口实验协议

## 文档定位

G30 把 G29 已验证的航班时刻表扩流方法从 2× 延伸到 3×，在不延长论文仿真窗口的前提下，比较原始集中式 HCA* 与当前局部决策框架的端到端容量。

当前控制框架保持为：

`S4 route score + J2 destination merge + E2 event hot path + junction-local FIFO + service-aware static local potential`

本文只冻结实验协议和可声称的边界，不登记尚未完成的实验胜利。输入或 portable aggregate 不完整时，报告只能是 `G30_3X_PARTIAL_DIAGNOSTIC`。

## 3× 航班 manifest 生成逻辑

原始 raw 输入有 28,506 件行李、43,603 个展开 segment、360 个 `(STD, end, Unloader)` 航班组，并按 `(end, Unloader)` 形成 13 条航班序列。G30 不复制已经展开的 segment，而是在 raw 航班 manifest 层增加班次：

1. 原始航班和原始行李全部保留。
2. 对同一航班序列中的每个非末班，在它与下一班 STD 的三分之一、三分之二位置各插入一班。
3. 对每条序列的末班，以该序列历史正班距的 lower-median 为参考，在三分之一、三分之二位置外推两班。
4. 每个插入班复制父航班的完整 source、loader、end、unloader 行李构成。
5. 每件复制行李的 `EntryTime` 与 `STD` 增加同一个偏移，保持 `STD-EntryTime`、直达/EBS 分类和 storage-out 提前 2,700 秒的生命周期规则。
6. 原始 task ID 保留；两个新增 cohort 使用各自的全局唯一 ID 区间。
7. 生成后的 raw txt 仍是权威输入；canonical JSONL 必须由该 raw 文件重新解析和 early-bag expansion 得到，不能机械复制 canonical segment。

正式 3× cohort 已由 workload manifest 固定为：

- 85,518 件 raw 行李；
- 130,809 个 route segments；
- 1,080 个航班（360 原始 + 720 插入）；
- 40,227 件直达行李；
- 45,291 件 EBS 行李；
- 13 条航班序列；
- 最新 EntryTime 为 82,703.72582 秒，最新 STD 为 85,900 秒，仍在同一个 86,400 秒业务日内；
- source、loader、end、unloader、直达/EBS 和 segment 总量均为原始输入的精确 3×。

协议名固定为：

`SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_3X`

## 固定仿真边界

- start epoch：8,260；
- 运行窗口：90,000 epochs；
- 最后有效 epoch：98,259；
- 每个 native full case 的事件预算：60,000,000，且正式准入要求实际未触及该上限；
- 不为了让 3× 任务完成而延长窗口；
- 所有主容量指标使用固定 85,518 件 raw 行李作为分母。

因此，“尚未被 source 释放”“已经规划但未走完”和“拓扑不可达”都不能从业务分母中删除。
固定窗口结束时仍未完成的行李是容量结果，不自动等同于算法崩溃或安全失败；但若事件预算先耗尽，则该 case 是被计算上限截断，不能进入正式容量胜负。

## Fresh 3× 主比较

### Table 5.2：四个速度容量格

速度仍为 1.5、2.0、2.5、3.0 m/s。原 Java HCA* 每个速度运行两个完整独立进程重复；S4 对应运行一个完整固定窗口 case。

3× 时 HCA* 可能在 epoch 98,259 前没有释放全部 130,809 个 segment。此时不能伪造 exact-release 配对。主比较改为同一 canonical 总体、同一固定时域下的端到端完成容量：

- HCA* 与 S4 各自从 canonical scheduled arrival 驱动自己的 Source admission；
- 不要求 HCA* 全量 release 才登记固定窗口容量；
- HCA* 的两个重复必须各自完整运行，并且 release、plan、segment completion、raw-bag completion 计数在两个重复间一致；
- 主指标是 epoch 98,259 时完成的 raw-bag 数量 / 85,518；
- 该比较明确标记为 `OWN_SOURCE_FIXED_HORIZON_CAPACITY_NOT_RELEASE_OR_TIMING_PAIRED`。

如果 HCA* 没有完成全部 85,518 件行李，它的完成者时延属于删失后的 `CENSORED_SECONDARY`，不能进入正式时延胜负。只有双方都完成固定总体时，全总体时延分布才可以作为正式 timing 证据；无论 timing 是否可测，G30 fresh primary 的四个速度格只由固定窗口容量作决定。

### Table 5.5：线路中断容量格

- 故障在 epoch 8,260 生效并持续到窗口结束；
- 保留论文列出的 16 个故障场景；
- 其中 15 个边定义明确的场景可 fresh 执行，并各自形成一个主容量格；
- `pair_5_7` 的归档边定义仍相互矛盾，固定登记为 `NOT_MEASURED`，不进入主目标；
- 比较固定 85,518 总体的完成数和成功率，不是逐 segment fault-release 配对；
- 拓扑不可达行李仍计业务失败；双方达到相同拓扑可达上限时允许 `TOPOLOGY_CEILING_TIE`。

## 归档与 reconstruction 上下文

### Table 5.3

论文归档的 1× 分散式/HCA* min、mean、max 只作跨规模描述性上下文。3× own-source 结果不是它们的配对复现，Table 5.3 的胜负或缺口不能驱动 fresh 3× 主目标。

### Table 5.4

原论文动态/静态速度偏差实现缺少足够源码和参数，因此 G30 只能运行 12 个已公开的 legacy-variant reconstruction case：标准速度控制规划与自由流运动，节点处使用固定 seed 的确定性观测偏差流。

报告必须完整列出每个 reconstruction cell 的结果、相对归档 dynamic/static 的描述性胜负和缺口；但它们保持 `DESCRIPTIVE_UNPAIRED_LEGACY_VARIANT_RECONSTRUCTION`，不得冒充 fresh exact 3× 证据，也不得被总状态隐藏。

## 19 格 fresh primary 判定

Fresh primary 只包含：

- 4 个速度固定窗口容量格；
- 15 个可测线路中断固定人口容量格。

判定规则：

- 有可区分余量时要求 S4 胜过 fresh HCA*；
- 双方均为 100% 时允许 `100_PERCENT_CEILING_TIE`；
- 达到相同拓扑、物理或论文显示精度上限时允许相应 ceiling/precision tie；
- 不允许 baseline loss；
- 不允许普通的、无法解释的 sub-ceiling tie；
- 任一主格缺少准入证据，或 portable aggregate 仍为 partial，总状态只能是诊断，不能预写胜利。

这一定义是“fresh 3× 固定窗口主容量目标”，不是“原论文所有科目都已 exact 全胜”。Table 5.3、Table 5.4 的 loss 和 gap 单独统计。

## 去中心化与简单性边界

S4、J2、E2 是三个协作机制，不是三层规划器：

- S4 在当前转向点只给当前可选出边打分并提交下一跳；
- J2 在目标节点的真实服务时刻处理局部 pending 合流许可；
- E2 合并同时间戳的不必要事件发布，减少事件开销而不规划路线。

节点局部 FIFO、service-aware static potential 和故障时的确定性局部结构值都只使用当前接口可见的邻域状态。运行时继续保持：

- 无完整 A*；
- 无完整未来路线物化；
- 无 HCA* 式全局时空预约表；
- 无 DLP 或其他在线 learning；
- 每个转向点只决定一个下一跳动作。

G30 不为 3× 另外叠加规划层、学习层或复杂保护规则。发现退化时，先用已有的 released / planned / completed-segment / completed-raw-bag 计数定位 Source、网络或合流瓶颈。

## 产物与验证

最终报告只依赖三个可提交的小型输入：workload manifest、portable HCA aggregate、portable native aggregate。报告器据此重建 JSON、CSV 和 Markdown；`--validate-committed` 做逐字段、逐文本核对，不依赖 runtime 目录或大 canonical 文件。

若旧 case 已完成同一固定窗口、终端业务计数闭合、60,000,000 事件预算未触发，且 A*、全局扫描、未来路线、预约冲突和故障边进入等结构门全部通过，可以只把旧的“全完成才算成功”标签重分类为固定窗口容量结果。重分类不得重跑或改写 completed/failed/event 等业务数据；写盘前仍必须通过当前完整准入。

长实验尚未完成时可以生成 partial diagnostic，但不能生成正式胜利结论。CI 先运行 G30 聚焦测试；只有最终 G30 reporting 产物提交后，才执行 committed portable report 验证。
