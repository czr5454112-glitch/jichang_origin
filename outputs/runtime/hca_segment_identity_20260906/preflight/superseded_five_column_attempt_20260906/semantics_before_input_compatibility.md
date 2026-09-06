# HCA 段身份修复：共同 EBS 合同与独立语义审查

2026-09-06。本文在新 HCA 完整矩阵产生之前核对可读源码，说明本次最小修复的含义与验证边界；不改旧实验、旧科学附注或 2026-09-05 冻结协议。运行安排见[本次 campaign 协议](hca_segment_identity_campaign_protocol_20260906.md)。接纳依据是身份与执行账目正确性，不依据任何方法的排名。

## 共同业务合同的直接证据

当前 G31、V5 与旧 HCA 都将早到行李展开为两个**独立按计划时刻进入调度的段**。`storage_in` 的共同 D 为原始 entry，`storage_out` 的共同 D 为 STD−2700 秒；是否拆段由 STD−entry≥4800 秒决定。这里“独立”仅指没有同袋前段完成后才能释放后段的门槛；两段仍会与其他任务竞争各自执行器的资源，实际释放、规划及入网时间不保证等于 D。

| 实现 | 可复核位置 | 直接支持的结论 |
|---|---|---|
| canonical 展开 | [`legacy_tasks.py`](../../src/czr005/io/legacy_tasks.py)，82–145 行 | 两个 `ExpandedTask` 各有唯一 `segment_id`、独立 `pass_time`，共享原始 `task_id`；没有 predecessor 字段。 |
| G31 输入与原生释放 | [`g4irsf31_map_adapter.py`](../../scripts/eval/g4irsf31_map_adapter.py)，268–297 行；[`event_driven_junction.hpp`](../../cpp/ics_core/runtime/event_driven_junction.hpp)，3156–3184 行 | 每个唯一 segment 建立一个独立 runtime ID，并在各自 `release_time` 排入 `kBagRelease`；原始袋 ID 用于关联，不代替活动段身份。 |
| V5 展开与释放 | [`FengDhBenchmark.java`](../../benchmarks/java/feng_cie_dh_boundary_clearance_v5/App/FengDhBenchmark.java)，556–598 行；[`FengDhSimulator.java`](../../benchmarks/java/feng_cie_dh_boundary_clearance_v5/App/FengDhSimulator.java)，735–760 行 | 第一段、第二段分别使用 `rawId*2`、`rawId*2+1`，到各自 release tick 即释放，没有检查前段是否已完成。 |
| V5 已有显式回归 | 同上 Benchmark，1465–1468、1515 行 | T10 明确检查 outbound admission tick=35、inbound completion tick=40，且前者早于后者；这不是本次身份修复才引入的假设。 |
| 旧 HCA 展开与源端释放 | [`LegacyIcsNoFaultWindowBenchmark.java`](../../benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java)，449–489 行；[`Tasks.java`](../../legacy/jichang_origin_readonly/src/App/Tasks.java)，149–168 行 | 两段分别进入源节点任务表；释放看源端待规划阻塞、每源队头及 `D−epoch<1`，不检查同袋前段完成。 |

因此，本次不能只给新 HCA 增加入库完成后的出库等待。如果将来改为具有物理先后依赖的 EBS 模型，应另立共同业务版本并重新评估三方法的复用资格。当前独立分段也不能被表述为已经验证了真实 EBS 的串行保管过程。正式 THT 继续为每袋各段 `completion−canonical D` 的和，而不是两段时间轴的并集或原始 entry 至最终完成的单一时长。

HCA 的整数 epoch 源端释放规则允许分数 D 在 floor(D) 时满足条件；源端排队又可能造成远超过一秒的延迟。修 ID 不应同时改为 ceil(D)、改变每源释放限额或替换原 `sortTasks` 中 `(int)(left.pass_time−right.pass_time)` 比较器。G31/V5 的原生 admission 与 HCA 的 release/processed 时间不因此成为同一事件。

另一个原生字段陷阱是 `outputstarttime.txt` 第三列：`Tasks.read` 对四列新任务只赋身份和 OD，没有恢复 `pass_time`，所以规划日志中的该值可为 Java 默认 0，不能当作 canonical D。独立审查已要求新 runner 将其保留为 `legacy_task_pass_time` 诊断字段；D 由精确段映射与 canonical 对照取得，不修改旧 App 填值来伪装日志本来具备该语义。

## 为什么必须修执行身份

旧 HCA 在两个 task 对象上都设置 raw `Task_ID`。这不只是日志别名：[`ICS_PathFinding.java`](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java) 的 150 行以该键 `saved_routes.put`，294–315 行以该键替换同节点预约；[`Tasks.java`](../../legacy/jichang_origin_readonly/src/App/Tasks.java) 的 171–202 行按 `saved_routes.keySet` 生成下一步推进，`ICS_PathFinding` 的 76–88 行再按同键推进或移除完成路径。两个重叠段共享键会破坏真实活动路径及预约的身份隔离。仅重命名 CSV、增加一个完成日志 map 或补造丢失事件都不能修复此问题。

新 [`HcaSegmentIdentityBenchmark.java`](../../benchmarks/java/HcaSegmentIdentityBenchmark.java) 的首轮独立 diff 审查确认：首段沿用 raw ID；出库段按 raw 文件中早到袋顺序分配 `maxRawId+1+earlyOrdinal`，并保存 execution ID→raw ID/leg/OD/D/STD 映射；编号在进入旧 HCA 前就赋给任务，因而贯穿实际活动路径、预约、推进与完成。旧 App 源码、排序、epoch 循环、源端释放和 A* 公式未改。新增四态终账取自实际集合，不以完成数倒推一个“待处理”集合。最终版本身份以本次构建和运行冻结记录为准。

冻结 wrapper SHA256 为 `041899096be424ca15da1d621131e1e6cba078c897770e1d32158c208d67ffd0`；新单格 runner [`run_hca_segment_identity.py`](../../scripts/eval/run_hca_segment_identity.py) 本次只读审查版本 SHA256 为 `77105ac1695576011118e8fc2d3d450e26149cc5a165728fae7962bb4fd46230`。runner 以 execution ID 精确关联全部事件、原生终态成员及 canonical 段，不做旧 raw-ID FIFO completion 匹配；已修正上述第三列时钟误认。计时从共同 D 重算，未单独增加 EBS 依赖。

[六项原生微测试](../../outputs/runtime/hca_segment_identity_20260906/preflight/microtests.json)的重叠案例记录两段均在 epoch 1 释放：入库完成 21，出库完成 3；旧执行只留下一个完成，新执行两段均完成。普通三袋单段案例包含分数 D，四份原生日志逐字节相同。当前重叠案例两条路线使用不同节点，直接证明的是段身份、活动路径及完成事件隔离；同节点预约使用独立键的结论另有 `update_constrain/Contains` 的直接源码依据，不能把该案例夸称穷尽验证了共享节点预约或连续时间碰撞自由。

原循环仍是：每个 epoch 先产生源端新任务和活动任务消息；HCA 先处理活动路径、完成及预约更新，再将新任务追加至既有待规划列表并顺序尝试规划。唯一编号改变了 Java `HashMap` 的桶与遍历行为，也保留了过去可能被覆盖的预约，所以真实路径与完成时间可能变化。不能承诺修复前后 EBS 流量逐字节一致。无 EBS 输入保留同样的 ID、顺序和原生函数，适合做精确轨迹对照；有重叠 EBS 输入应检验两条活动路径和两份预约并存，而不是强求旧错误轨迹。

## 最小必要验证与复用条件

1. **段映射与输入**：execution ID 唯一、无整数溢出；每个 canonical 段恰有一行映射；raw ID、leg、OD、D、STD 全匹配。重复 raw/segment、重复完成、未知完成 ID 应拒绝。袋数按 raw 人口，段数按每格实际抖动后展开，不能硬套未抖动的 43603 段。
2. **真实执行与先后合同**：普通单段与旧 wrapper 对照；构造同袋两段同时活动的案例，验证两条活动路径、相关节点预约以及两个完成事件均独立存在；应包含后段已可调度而前段尚未完成的场景，确认未暗加 EBS 等待。保留原生日志和明确 ID 映射，不能只断言汇总计数。
3. **终态全人口守恒**：每段恰在未释放、已释放待规划、活动路径、已完成之一；集合互斥且并集等于输入段集合。另检查 `generated=completed+active+unplanned`，以及输入段数=generated+not_released。有限时域允许未完成；不能以“最后残差为零”替代逐 ID 集合核验，也不能把四态账目通过等同于全部连续时间物理约束已证明。
4. **完成与指标**：每完成事件唯一对应执行段；原始袋只在全部业务段完成时计入 TH。`completion−D` 使用共同 canonical 时钟，原生 release/processed 单列。2× THT 始终 N/A；其他负载未全完或缺种子时，不用幸存者或可用种子子集估计正式全人口 THT。
5. **冻结与完整矩阵**：先过微测和协议指定的五个全人口预检，再以同一 source/class/JDK/命令/输入身份补齐全部 60 个新 HCA 格；不能只替换旧 43 个异常格。保留所有失败和有限时域结果；重试须核验版本并避免覆盖冲突档案。

G31、V5 各 60 格可以复用的条件是：逐格 map/raw/canonical/identity 实际文件 SHA、地图/负载/种子、分段与人口、98259 秒共同绝对时域、方法与构建身份保持一致；其完整段/袋证据与最终档案 manifest 仍可核验。本次只是改变 HCA 内部 execution ID，不改共同 canonical 字节或其他两执行器，故不要求为编号修复本身重跑 G31/V5。任何新的 EBS 前置等待、输入重排、地图/速度/时域变化都应先重新判断此条件，不能沿用旧表而称同一比较。

复用来源为 [`feng_dh_boundary_clearance_v5_20260905/campaign_manifest.json`](../../outputs/evidence/feng_dh_boundary_clearance_v5_20260905/campaign_manifest.json)，SHA256 `133808d1c2fb94149f2ec5e717d14f7384faea957ab3386deedabfef5c8f8f40`。历史 HCA 的 43/60 正残差科学附注及其余 17 格“未检出正残差不等于充分验证”的边界，继续保留在[原附注](../../outputs/runtime/cie_external_baseline_boundary_clearance_v5/control_completion_notes.json)；不把旧标记贴到新 HCA，也不以新运行覆盖旧档案。旧日志不能无歧义恢复被覆盖段的真实完成事件。

## 本次引用源码的字节身份

以下为本次只读核对的文件 SHA256；它们不恢复历史 HCA 运行时缺失的 class 身份。

| 文件 | SHA256 |
|---|---|
| `src/czr005/io/legacy_tasks.py` | `3e1a01fdf7b0bd3aa8a1293d7f63b37823a0d1bdf360ccb5e4697fe70133d93f` |
| `scripts/eval/g4irsf31_map_adapter.py` | `878c0ee31788ab6ff9fb87e8306fe45f90dc2905a9e32356e55f17f2214b95f6` |
| `cpp/ics_core/runtime/event_driven_junction.hpp` | `8c6a15fe60ca60cb8a50af28d534de882da5bf557154012e0f0df4da2b8fbd97` |
| V5 `App/FengDhBenchmark.java` | `052176456427fe90a8d536448fca082d3ae65cfef086a419fa837a68a51a03d9` |
| V5 `App/FengDhSimulator.java` | `43e4dac5f7f79f03e1a630c1e4f327169d568a7433d92edf0a05083810b18d93` |
| `benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java` | `28beeb2cd62f931bb2d911465cea3b5f7728effea8e06da32cd7f1ac62303a10` |
| legacy `App/Tasks.java` | `dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b` |
| legacy `App/ICS_PathFinding.java` | `a367fd8e79aba7b3d23b71fc9b4d01f76dd67f291f008401d676ffcbcf53d52a` |
