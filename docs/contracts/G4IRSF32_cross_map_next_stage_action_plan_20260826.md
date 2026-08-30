# G4IRSF32 跨地图下一阶段独立审计与行动计划

> **审计对象**：`czr5454112-glitch/jichang_origin`  
> **固定审计提交**：`46cc46ab6bc121628fd6357e9f3c7636745fd732`  
> **对应分支**：`codex/g4irsf31-nanning-portability`  
> **审计角色**：独立算法、代码与实验审计者  
> **文档性质**：基于固定提交的静态代码审计、提交内实验产物复核、报告逻辑复算与下一阶段可执行计划  
> **重要限制**：本审计检查了固定提交中的核心代码、测试、协议、CSV/JSON/Markdown 产物及准入逻辑，但没有在当前隔离环境中重新执行需要原 Java/C++ 构建环境和超大事件预算的全部正式矩阵。因此，本文把“提交内产物支持的结果”与“本地重新运行得到的结果”严格区分；本文不声称完成了独立全量复跑。

---

## 0. 执行结论

### 0.1 总体判定

对固定提交 `46cc46a...`，可以作出以下有边界的结论：

1. **地图适配主目标已经实质完成。**  
   HCA 与 S4/J2/E2 均已具备从地图配置加载节点、边、服务时间和业务角色的能力；原始 map2 仍保留兼容入口。南宁适配不是把一张固定路线表写进运行时，而是离线构造地图 profile、业务流和 service-aware potential，运行时仍按当前节点逐边决策。

2. **`57 胜 / 21 平 / 0 负`在其注册协议内可信。**  
   它准确表示：在两张指定地图、固定时域、固定 scheduled raw-bag population、双方各自执行 source admission 的 78 个可测容量单元格中，S4 完成件数 57 格严格高于 HCA，21 格达到全人口或拓扑上限平局，没有一格完成件数低于 HCA。  
   它**不等价于**“57 个统计显著胜利”，也不等价于“逐 segment 同释放下 57 次胜利”。

3. **同 HCA 释放时序、双方全人口完成的时延证据更强。**  
   南宁 15 项中 14 项 S4 更低、1 项为 1 ms 物理分辨率平局；map2 20 项中 17 项 S4 更低、3 项为分辨率平局。合计 **31 项 S4 更低、4 项分辨率平局、0 项实质性 HCA 更低**。这些结论仅覆盖通过同释放和全人口门的 1×稳定场景。

4. **可以说当前新框架在现有正式实验范围内总体超过原始 HCA，但不能说已经普适、全面、精确地击败原论文全部实验。**  
   Table 5.4 仍是 NON_EXACT 描述性重建，南宁 Table 5.3 没有原论文归档精确复现，map2 `pair_5_7` 仍为 `NOT_MEASURED`，而且目前只有两张参与过适配的地图。

5. **当前首要问题已从“能否超过 HCA”转为“修复自身局部服务竞争瓶颈，并把优势扩展成可泛化、可解释、可发表的证据”。**  
   最值得优先处理的是节点 49 一类“外部入流 + 本地已释放 source 流”共同竞争同一服务资源、但图论入度仍为 1 的混合来源竞争。

### 0.2 唯一推荐的下一步

> **只启动候选 A 的 P0 阶段：为现有 J2/服务日历增加默认关闭的“混合来源目的服务竞争”影子观测，并计算无副作用的虚拟插入等待时间。**  
> 先不改变任何动作，不改 strict potential-descent，不改 PIBT，不跑完整矩阵。只有影子证据证明节点 49 等位置确实存在未被统一表示的竞争，并通过局部性、无未来泄漏、无重复计数、资源有界和 map2 零影响门，才允许进入动作阶段。

这是本文唯一建议立即执行的方向。候选 B、C 只是受控后备，不应并行开发。

---

# 1. 对当前项目目标的复述

本项目的真正目标不是在南宁地图上单独“调出一个高分”，而是构建一个可替换机场地图、保持原地图兼容、运行时去中心化且在容量、鲁棒性和全人口时延上优于集中式 HCA 的行李路由框架。具体约束如下。

## 1.1 地图可移植性

- HCA baseline 和 S4/J2/E2 都必须能从输入地图配置中读取节点、边、服务时间、起点、终点和 storage/source 等业务角色；
- 更换地图不得要求修改核心路由算法；
- 原 map2 的历史默认行为必须可回退，新增适配开关必须默认关闭或由显式 profile 激活；
- 允许把任意外部节点标识离线映射为稠密内部 ID，但当前实现仍要求运行时 ID 为 `0..N-1`。

## 1.2 业务流可比性

- map2 和南宁均按原论文实验组织逻辑构造 1×、2×业务流；
- 固定 scheduled raw-bag population 和固定时域用于容量比较；
- 只有逐 segment 使用相同 HCA release trace、双方完成全部 raw bags 的单元格，才允许产生正式跨算法时延结论；
- 不能把 survivor-only、common cohort 或不同 release population 的时延混入正式结论。

## 1.3 去中心化运行时边界

正式 S4 运行时应满足：

- 每次只在当前节点选择一条下一跳边，或选择等待；
- 读取当前节点、直接邻居及局部资源状态；
- 不执行运行时完整路径搜索或全局 A*；
- 不扫描全局任务列表；
- 不维护或读取每件行李的完整未来路线；
- 不做中心化完整路线预约；
- 不使用学习模型；
- 可以离线从输入图重算 goal-conditioned、service-aware potential 和确定性故障后的结构值；
- 运行时仅查询当前节点及候选邻居对应的离线标量，不读取预记忆的特定地图路线。

## 1.4 性能目标

在上述边界内，S4/J2/E2 应在 map2 与南宁的 1×、2×稳定速度和故障场景中：

- 固定时域完成量不低于 HCA；
- 在可进行因果对齐的全人口同释放场景中降低 mean、P95、P99、max 等时延；
- 保持冲突、失败、不安全动作、运行时完整 A* 调用为 0；
- 在更大负载下避免事件膨胀、内存失控和来源饥饿；
- 对第三张未调参地图保持可运行和至少不系统性退化。

---

# 2. 审计方法与证据等级

## 2.1 检查范围

本审计直接检查了以下类型的内容，而不是仅阅读 README 或最终报告：

- 最终报告及其 CSV/JSON；
- 报告生成器中的单元格准入、胜负判定和时延门；
- 南宁地图 profile 的节点、边、业务角色、EBS 声明和假设；
- 南宁地图生成器、工作负载映射器、1×/2×构造逻辑；
- S4 在南宁和 map2 上的正式 runner；
- HCA 输入适配、fresh runner 和 Java benchmark；
- 同 HCA release timing runner；
- C++ S4/J2/E2 运行时、pybind 绑定和 Python backend；
- G31 专项测试，包括 profile、native、paired timing 和 reporting 测试；
- 提交内正式结果中是否存在资源峰值、RSS、普通队列峰值和长期稳定性证据。

## 2.2 四级证据分类

本文中的判断统一使用以下标签。

### A. 已由结果证明

含义：固定提交中的正式 JSON/CSV/Markdown 产物经过报告准入门，且统计可由提交内数据复核。

典型例子：

- 78 个可测容量单元格的 `57/21/0`；
- 35 项同释放全人口时延指标的 `31/4/0`；
- 某个正式单元格中完成件数、分母、固定时域和 verdict；
- Table 5.4 被标为 NON_EXACT，不产生跨算法 verdict。

### B. 由代码证明

含义：核心代码结构、条件分支或配置字段直接决定该事实，不依赖实验猜测。

典型例子：

- S4 分数把 queue count 与秒直接相加；
- J2 目的 merge 触发多处依赖 `incoming_degree(target) > 1`；
- `local_queue_capacity == 0` 时 queue-full 分支不触发；
- direct-neighbour visibility 直接读取候选节点的 service calendar；
- profile loader 要求稠密零基 ID；
- type-7 在 profile 中被明确标注为空托盘 storage，而非已识别真实 EBS。

### C. 合理推断

含义：代码结构和结果共同支持该解释，但缺少直接消融、因果 trace 或专门实验。

典型例子：

- 节点 49 的混合来源竞争很可能是南宁主要长尾来源；
- 原始 queue count 权重可能跨地图失配；
- queue cap 为 0 可能在开放流或更高倍负载下造成内存增长；
- strict descent 可能排除少量有益临时上坡绕行。

### D. 尚无证据

含义：现有代码和正式产物不能支持该结论。

典型例子：

- S4 对任意未知机场地图都优于 HCA；
- type-7 节点 53 等价于真实南宁 EBS；
- 普通 2× own-admission 结果能够证明逐行李时延因果优势；
- queue cap 为 0 的开放时间运行具有渐近有界性；
- 允许一次 detour 一定能改善当前矩阵；
- 当前所有 strict wins 都具有统计显著性。

---

# 3. 已完成、部分完成与未完成事项

## 3.1 已完成

| 事项 | 独立判定 | 主要证据 |
|---|---|---|
| 南宁地图转为可加载 profile | 完成 | `run_g4irsf31_nanning_map.py`；`nanning_airport_profile.json` |
| S4 从 profile 动态读取节点、边和角色 | 完成 | `g4irsf31_map_adapter.py::load_map_profile`、`build_s4_request` |
| HCA 使用可替换地图/任务/hcost/storage 参数 | 完成 | `run_g4irsf31_nanning_hca.py`；`LegacyIcsNoFaultWindowBenchmark.java` CLI |
| 原 map2 仍有独立兼容 runner | 完成 | `run_g4irsf31_map2_native.py`；map2 profile 兼容测试 |
| 南宁 1×/2×业务流确定性构造 | 完成 | `run_g4irsf31_nanning_workload.py`；manifest 固定 28,506/43,603 与 57,012/87,206 |
| 南宁 40 格容量矩阵 | 完成 | `g4irsf31_reporting.json` 的 40 个 admitted primary rows |
| map2 38 个可测容量格 | 完成 | `map2` 报告状态 `COMPLETE_MAP2_CROSS_ALGORITHM_EVIDENCE` |
| 同释放全人口时延准入 | 完成 | 两个 `same_hca_release_timing.py` runner；reporting 的 paired gates |
| Table 5.4 与精确主结论隔离 | 完成 | reporting 中 `NON_EXACT`、`fresh_exact_primary_target_eligible=false` |
| 运行时不调用完整 A* 或学习模型 | 对 G31 配置路径完成 | S4 request 删除 model/DLP artifact；native safety gate 检查 full A* 为 0 |
| 下一跳与一跳资源预约 | 对 G31 配置路径完成 | C++ event runtime；只提交 selected edge 与 destination local resource |
| 报告字节稳定与 headline 回归测试 | 完成 | `tests/test_g4irsf31_reporting.py` |

## 3.2 部分完成

| 事项 | 为什么只是部分完成 |
|---|---|
| 原地图默认行为保持不变 | 配置默认关闭、map2 sentinel 和专项测试支持兼容性；但没有对全部历史阶段和所有旧二进制做逐字节全矩阵回归。 |
| “真正去中心化”证明 | 核心动作是一跳，未见运行时完整路径；但离线 potential 使用全图，局部 calendar 标量包含已预约的未来时段，且缺少专门的远端状态不变性/未来任务扰动测试。 |
| HCA 与 S4 科学公平性 | 固定人口、时域、地图和场景可比；但 2×容量采用 own-source admission，测的是系统级承载而非完全相同实际 release trace 下的纯路由差异。 |
| 高负载可扩展性 | 1×/2×正式矩阵通过；没有提交内充分的开放流、4×以上、RSS、普通队列峰值、event heap 峰值和 backlog slope 证据。 |
| 混合来源公平性 | service calendar 保证物理互斥，但本地 source 与外部 incoming 是否经过统一公平仲裁尚未证明。 |
| 故障泛化 | 注册的全日线路中断矩阵覆盖较多；动态故障、修复、消息延迟和 potential generation 切换在本轮跨地图主结论中不是完整对象。 |
| 南宁业务语义 | 拓扑和节点类型来自资料；真实任务、故障和 EBS 语义缺失，工作负载是确定性投影。 |
| 跨地图泛化 | 两图结果强，但南宁参与了设计与调试，尚无真正 held-out 第三图。 |

## 3.3 未完成

- 南宁 Table 5.3 的原论文归档精确复现；
- Table 5.4 的 matched disturbance HCA 对照；
- map2 `pair_5_7` 路线定义冲突消解；
- 第三张未调参地图；
- 真实南宁 EBS 的业务确认；
- 2×同 release、双方全人口完成的正式时延比较；
- 故障场景下同 release、全人口完成的正式时延比较；
- queue cap 为 0 时的开放流/长期稳定性证明；
- 提交内正式 RSS、普通 junction queue、source queue、event heap 和 backlog slope 审计；
- strict descent 有限绕行候选的真实收益证据；
- 对微小 strict win 的重复运行、扰动稳健性或置信区间；
- arbitrary external node ID 的通用导入层，目前仍需先稠密化。

---

# 4. 逐文件架构审计

## 4.1 地图适配核心

### `scripts/eval/g4irsf31_map_adapter.py`

关键结构：

- `RuntimeMapProfile` 保存动态 `node_records`、`edge_records`、`start_nodes`、`goal_nodes`、`storage_source_nodes`；
- `load_map_profile()` 不固定 54 个 map2 节点，但要求 ID 严格为 `0..N-1`；
- 检查 node outgoing 与 directed edge records 完全一致；
- `build_s4_request()` 离线计算 service-aware potential；
- G31 显式使用：
  - FIFO；
  - `S4_queue_aware_rule_only`；
  - `merge_grant_rule="M3"`；
  - `merge_grant_timing_mode="jit_fair_aging_deadline"`；
  - E2 hotpath；
  - supervisor off；
  - `local_queue_capacity=0`；
  - strict descent 与 direct-neighbour visibility 由显式开关控制；
  - 删除 scorer model 和 learned DLP artifact。

**审计判断**：

- 地图数据结构和运行时图本身已基本地图无关；
- “J2”是报告中的框架级称谓，而 request 中的具体配置值是 M3 + JIT fair-aging-deadline。后续文档应同时记录框架名和实际字段，避免只写“J2”却无法复现实验；
- 稠密 ID 是实现限制，不是算法要求；
- storage role 已配置化，但存在 map2 兼容 fallback `[52]`，第三图必须显式给出角色，不能依赖 fallback。

### `scripts/eval/run_g4irsf31_nanning_map.py`

该文件负责把两份工作簿转成一张 151 节点、227 条有向边的 profile，并处理重复 raw ID `ICS156` 的 workbook namespace。

**代码/产物证明**：

- source/sink 主要由 node type 推断；
- type-7 被标记为 empty-pallet storage；
- EBS 状态明确为 `NOT_IDENTIFIED_IN_SOURCE_WORKBOOKS`；
- 坐标缺失时写入 `x=y=0`，仅用于 routing placeholder；
- 部分服务时间使用明确记录的 imputation；
- 原资料未提供真实 task data 和 fault scenarios。

**结论**：这是可审计的地图数据适配，但不是自动理解任意机场业务语义的通用 importer。

### `data/processed/maps/nanning_airport_profile.json`

关键字段：

- `counts.dense_node_count=151`；
- `counts.directed_edge_count=227`；
- `topology_contract.strongly_connected=true`；
- `business_roles.ebs.status="NOT_IDENTIFIED_IN_SOURCE_WORKBOOKS"`；
- `business_roles.ebs.type_7_is_empty_pallet_storage_not_ebs=true`；
- 节点 49：type 1、service 1.0 s、本地 loader/source、出边到 50；
- 节点 50：type 4、service 2.0 s；
- 节点 53：type 7、service 0、storage proxy、出边到 49；
- 图中服务时间包含 1.0、1.5、2.0、3.0 s 等多个尺度。

该 profile 直接支持风险 1、2、6 的代码级核查。

## 4.2 业务流构造

### `scripts/eval/run_g4irsf31_nanning_workload.py`

主要逻辑：

- 读取旧任务并保持航班时刻/原始 raw-bag 组织；
- 普通 source bucket 与 goal 通过确定性最小负载堆映射到南宁候选节点；
- storage source 映射到预注册的 type-7 proxy；
- proxy 选择使用离线自由流代价聚合，而不是运行时路线记忆；
- 1×固定为 28,506 raw bags / 43,603 segments；
- 2×通过确定性复制形成 57,012 raw bags / 87,206 segments。

**审计判断**：

- 业务流构造可复现；
- 它保留了旧任务的时序组织，但没有证明等价于真实南宁 OD 或峰谷规律；
- “南宁业务实验”应称为“南宁拓扑上的 timetable-preserving projected workload”，不能称为真实机场生产业务复现；
- 2×是精确密度扩展，不是来自真实航班增长模型。

## 4.3 S4 正式 runner

### `scripts/eval/run_g4irsf31_nanning_native.py`

正式配置包括：

- 1×/2×；
- 1.5、2.0、2.5、3.0 m/s；
- 固定结束 epoch；
- 大但有限的 max events；
- storage proxy 53；
- strict potential-descent 开启；
- direct-neighbour merge-calendar visibility 开启；
- complete-on-goal-arrival 开启以对齐 legacy completion seam；
- 故障场景离线重算 surviving-graph potential 和 topology upper bound。

准入检查包括：

- selected population 与 manifest 一致；
- fixed horizon 和 event budget 一致；
- no failed/conflict/unsafe；
- event limit 未耗尽；
- runtime full A* 为 0；
- learned DLP/model 未激活；
- locality contract 字段符合 G31；
- artifact identity/hash 不陈旧。

### `scripts/eval/run_g4irsf31_map2_native.py`

- 使用原 map2 canonical parser；
- 保留 map2 1×原始工作负载；
- 2×确定性复制；
- 使用同一套 S4 flags；
- `pair_5_7` 因历史线路定义冲突明确返回 `NOT_MEASURED`。

**审计判断**：南宁和 map2 是同一核心运行时、不同 profile/manifest 的两套实验壳，不是两份地图专用核心算法。

## 4.4 HCA baseline

### `scripts/eval/run_g4irsf31_nanning_hca.py`

- 从同一南宁 profile/manifest 生成 legacy map、task、hcost 和 role 参数；
- 固定 scheduled population 与时域；
- 通过 `run_g4irsf24_fresh_hca.py` 构建隔离 Java 运行；
- 记录 release、plan、complete lifecycle；
- 以 completed raw bags 作为固定时域容量 numerator。

### `scripts/eval/run_g4irsf24_fresh_hca.py`

- 从固定仓库源构建 fresh Java benchmark；
- 每个 case 使用隔离目录；
- 生成 run status、metrics 和 lifecycle；
- 对 comparison eligibility、full population 与 survivor-only 做显式区分。

### `benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java`

代码路径仍调用：

- `PathPlan.pathPlanningAStar`；
- `planeTable.lockPath`。

因此 HCA 仍是集中式完整路径搜索与完整路线预约 baseline。地图和 storage roles 已参数化，但算法性质没有被改成 S4 风格。

**公平性解释**：比较的是两个完整系统在同地图/任务/时域下的性能，而不是只替换一个纯路由函数后的微基准。HCA 的集中规划和 source planning 开销属于 baseline 的真实系统行为。

## 4.5 同释放时序 runner

### `run_g4irsf31_same_hca_release_timing.py`

它不会使用普通 S4 own-source timing 直接做 verdict，而是：

1. 检查 HCA `run_01` case identity；
2. 要求 canonical segment release lifecycle 完整；
3. 检查 HCA repeats 的逐 segment release 值一致；
4. 用 HCA release epoch 替换 S4 task row 的 `pass_time`；
5. 要求 HCA 和 paired S4 都完成全部 raw bags；
6. 禁止 survivor/common cohort；
7. 才输出 min、mean、P95、P99、max。

### `run_g4irsf31_map2_same_hca_release_timing.py`

执行同样合同。map2 只对 1×四种速度形成正式时延证据；2× HCA 未完成全人口，严格 N/A。

**独立判断**：这两套 paired runner 是当前结果中因果边界最严格、最值得写入论文的部分。

## 4.6 报告生成器

### `scripts/eval/run_g4irsf31_reporting.py`

关键函数与字段：

- `primary_cells()`：注册南宁 8 个稳定 + 32 个故障单元格；
- `_capacity_verdict()`：
  - S4 completed > HCA → `S4_WIN`；
  - S4 completed < HCA → `HCA_WIN`；
  - 双方完成全部 denominator → full-pop ceiling tie；
  - 双方达到 topology upper → topology upper tie；
- `classify_cross_framework_timing_metric()`：
  - 严格按数值顺序判断；
  - 只有 `min` 且差异不超过 0.001 s 才改记物理分辨率平局；
- `_paired_artifact_summary()`：检查 schema、case、map、full population、HCA trace、HCA timing、S4 safety 和 event limit；
- `_bias_context_summary()`、`_map2_bias_context_summary()`：强制 Table 5.4 保持 NON_EXACT、不得驱动 exact target；
- map2 `pair_5_7` 明确 `NOT_MEASURED`；
- 报告只有在南宁 40 格 + 3 个 paired artifact、map2 38 格 + 4 个 paired artifact 完整后才写正式状态。

**重要审计结论**：报告逻辑没有把 2× own-source capacity 偷换成 paired timing，也没有把 Table 5.4 偷换成 exact win。

---

# 5. 对 `57 胜 / 21 平 / 0 负`的独立判定

## 5.1 复核结果

| 地图/组别 | S4 严格胜 | 平局 | HCA 严格胜 |
|---|---:|---:|---:|
| 南宁 1×稳定 | 1 | 3 | 0 |
| 南宁 1×故障 | 13 | 3 | 0 |
| 南宁 2×稳定 | 4 | 0 | 0 |
| 南宁 2×故障 | 16 | 0 | 0 |
| map2 1×稳定 | 0 | 4 | 0 |
| map2 1×故障 | 6 | 9 | 0 |
| map2 2×稳定 | 4 | 0 | 0 |
| map2 2×故障 | 13 | 2 | 0 |
| **合计** | **57** | **21** | **0** |

平局构成：

- 南宁：6 个 full-population ceiling ties；
- map2：9 个 full-population ceiling ties，6 个 topology upper ties；
- map2 `pair_5_7` 两个尺度未测，不进入 38 格分母。

## 5.2 可靠性等级

### 结论一：计数本身可靠

**等级：已由结果证明。**

原因：

- 正式 JSON 注册并 admitted 78 个单元格；
- 每格有固定 raw-bag denominator；
- HCA 与 S4 numerator 均由对应 admitted artifact 提供；
- reporting 代码存在显式 `HCA_WIN` 分支，不是只允许 S4 win/tie；
- 测试固定校验 headline；
- 负项为 0 是数据结果，不是判定器屏蔽。

### 结论二：它是“系统级固定时域容量优势”，不是逐行李因果优势

**等级：由代码和协议证明。**

容量合同明确为：

`same_scheduled_population_fixed_horizon_each_framework_own_source_admission`

因此它回答：

> 在相同 scheduled population 和时域中，各算法连同自身 source admission、规划、等待和路由机制，最终完成多少 raw bags？

它不回答：

> 如果每个 segment 在完全相同时间同时进入两套网络，S4 是否在每格都完成更多？

### 结论三：大型差距很有说服力，微小差距应降格表述

南宁 2×和多项故障场景差距巨大，难以由 1 ms 边界或单次抖动解释；这些可作为强工程证据。

但以下类型只应称为“本协议 numerator 严格更高”：

- 南宁 1×、1.5 m/s 的 1 件差；
- map2 2×稳定速度中几十至数百件的差；
- 其他非常接近 denominator 的 strict win。

在没有重复运行、扰动稳健性或置信区间前，不应把每个 strict cell 称为统计显著胜利。

## 5.3 可以和不可以说什么

### 可以说

> 在固定提交的 map2 与南宁 78 个可测固定时域容量单元格中，S4/J2/E2 在 57 格完成更多 raw bags，在 21 格达到相同全人口或拓扑上限，没有容量负项。

### 不可以说

- “57 次统计显著胜利”；
- “所有行李都比 HCA 更快”；
- “2×所有格都在完全相同 release trace 下获胜”；
- “原论文全部表格已精确全面超过”；
- “任意未知地图都将保持 0 负项”。

---

# 6. 对同释放全人口时延结果的独立判定

## 6.1 复核结果

| 地图 | eligible 速度/场景 | 指标数 | S4 更低 | 1 ms 分辨率平局 | HCA 更低 |
|---|---|---:|---:|---:|---:|
| 南宁 | 1×，2.0/2.5/3.0 m/s | 15 | 14 | 1 | 0 |
| map2 | 1×，1.5/2.0/2.5/3.0 m/s | 20 | 17 | 3 | 0 |
| **合计** |  | **35** | **31** | **4** | **0** |

南宁 1.5 m/s 因 HCA 未完成全部人口而 N/A；map2 2×四种速度均因 HCA 未完成全部人口而 N/A。

## 6.2 可靠性等级

**等级：已由结果证明，且证据强于普通容量矩阵。**

paired artifact 需要同时满足：

- 同一 HCA release lifecycle；
- 逐 segment release mapping 完整；
- HCA reference 为 corrected complete run；
- HCA 和 S4 都完成全部 raw bags；
- 禁止 survivor-only/common cohort；
- 五项时延均有限；
- S4 safety 通过；
- event budget 未耗尽。

这使 mean/P95/P99/max 的比较具有清晰的因果对齐基础。

## 6.3 仍存在的边界

- 只覆盖 1×稳定场景；
- 没有 2× paired full-pop timing；
- 没有故障 paired timing；
- 目前主要是确定性单组结果，不是多随机种子统计；
- `min` 的 1 ms tie 规则只解决物理语义分辨率，不影响 mean/tail 的严格比较；
- 不能把 HCA 未完成全人口的场景用 survivor timing 补成胜负。

## 6.4 论文级建议表述

> 在满足逐 segment 同一 HCA 释放时序且双方完成全部 raw-bag population 的 35 项时延指标中，S4/J2/E2 有 31 项取得更低值，其余 4 项差异不超过 1 ms 物理时间分辨率；未观察到实质性 HCA 更低项。

---

# 7. 八项重点风险逐项审计

## 7.1 风险一：节点 49 的“本地 source + 外部入流”没有统一进入 J2 仲裁

### 独立判定

**代码缺口成立；其对当前性能的具体贡献为合理推断，尚缺直接因果消融。**

### 代码证据

南宁 profile：

- 节点 53 是 storage proxy，出边 `53→49`；
- 节点 49 同时是 type-1 loader/source，出边 `49→50`；
- 节点 49 图论入度为 1；
- 节点 49 与 50 均有非零 service time。

C++ runtime 多处以以下条件识别 destination merge：

`uses_destination_merge_grants() && incoming_degree(target) > 1`

它影响：

- destination merge request 的提交；
- merge credit；
- source wait 原因；
- PIBT 对 merge edge 的识别；
- selected edge 是否进入 destination merge pending。

因此，来自 53 的外部流进入 49 时，不会仅因 49 还有本地 source 流而被识别为图论 merge。

### 不能过度推断的部分

这不等于 service calendar 完全失效。节点服务日历仍可阻止重叠服务，direct-neighbour visibility 也可让 53 看到 49 的现有 calendar scalar。真正缺失的是：

> 本地 source ready work 与外部 incoming/pending work 是否作为同一目的服务资源上的共同竞争者，接受统一的 FIFO/aging/deadline 仲裁。

现有代码没有证明这一点。

### 影响

- 外部流可能只被动等待本地 source 已写入的 calendar；
- 本地 source 可能看不到外部 pending 的公平性需求；
- 两种来源的等待可能由不同入口路径累计；
- 节点 49 的 service calendar 可能成为容量足够但排序不公平的单点长尾；
- 该问题不会必然产生物理冲突，却可能产生 mean/P95/P99/max 恶化。

### 证据等级

- “J2 触发依赖图论入度”：**由代码证明**；
- “49 是 mixed-origin service node”：**由 profile 证明**；
- “这是南宁主瓶颈”：**合理推断**；
- “修复后一定提高全矩阵”：**尚无证据**。

---

## 7.2 风险二：S4 把件数直接加入秒单位分数

### 独立判定

**量纲隐含系数问题成立；简单乘 service time 不应恢复。**

### 代码证据

S4 的核心排序等价于：

`travel_seconds + potential_seconds + queue_count + scheduled_incoming_count + corridor_wait_seconds + target_calendar_wait_seconds`

因此 queue 和 scheduled-incoming 的隐含系数是约 `1 second / bag`。

### 为什么这是跨地图风险

map2 与南宁的节点 service time 分布不同；南宁存在 1.5、2、3 秒服务节点。相同 queue count 在不同节点代表的潜在工作量不同。

### 为什么 `count × service_time` 可能反而变坏

简单相乘可能同时引入：

1. **重复计数**：calendar wait 已包含已预约工作的等待；
2. **把所有排队件视为在候选之前**：真实 J2/FIFO/aging 顺序未必如此；
3. **对慢节点过度惩罚**：引发不必要绕行；
4. **忽略已服务进度与空闲缝隙**；
5. **无法区分已入 calendar 与尚未表示的 ready backlog**。

因此此前 canary 恶化是合理现象，不应机械回滚。

### 更合理的量

应估计候选在当前直接邻居服务资源上的**边际虚拟插入等待秒数**，只包含：

- 已存在的 service-calendar intervals；
- 当前已经释放并 ready、但尚未被 calendar 覆盖的本地工作；
- 当前已经提交的 local pending work；
- 不读取未来 release；
- 不创建真实预约；
- 不扫描全局任务。

### 证据等级

- “公式混合 count 和 seconds”：**由代码证明**；
- “跨地图尺度可能失配”：**合理推断**；
- “虚拟插入一定优于 raw count”：**尚无结果证据，需 canary**。

---

## 7.3 风险三：strict potential-descent 排除有限绕行

### 独立判定

**风险在理论上成立，但当前没有结果证明放宽会更好。strict guard 目前仍应保留。**

### 当前 guard 的价值

当 goal-conditioned effective potential 在固定 surviving graph 上严格下降时，每次 MOVE 都减少一个下界有界的标量。若：

- 图有限；
- 每条有效边/服务代价为正；
- 每个非 goal 节点至少有一个下降后继；
- 同一 segment 的 potential 在运行期间固定；

则 committed MOVE 不可能形成无限循环。

在 G31 的全日故障场景中，potential 在 scenario 启动前离线重算，条件较清晰。

### 它可能损失什么

局部拥堵下，有时最优动作可能是：

- 先走一条 potential 略高的边；
- 绕开长 service calendar；
- 随后重新进入下降路径。

strict guard 会在评分前排除该动作。

### 可证明终止的有限绕行机制

候选 C 可使用**一次性 detour token**。

对每个 segment 维护：

- `b∈{1,0}`：是否还有一次上坡权限；
- `H`：当前 effective potential。

采用字典序排名：

`R = (b, H)`，并规定 `0 < 1`。

- 普通动作：要求 `H(next) < H(current)`，`b`不变；
- 唯一上坡动作：从 `b=1` 变为 `b=0`，即使 H 上升，第一维严格下降；
- token 用完后所有 MOVE 必须严格下降；
- token 只在新 segment 初始化，不能因等待、重试或普通重访补充；
- 动态 fault generation 若允许重置，必须有单独的有限 generation budget，否则终止证明失效。

这可证明 MOVE 次数有限，但不能单独证明永久资源故障下的 wall-clock liveness。

### 为什么不应作为当前第一步

- 没有证据显示当前错误来自“缺少上坡边”而非节点 49 服务竞争；
- 会扩大 legal action set；
- 可能增加事件数和回访；
- 会增加每包状态和新的策略 seam；
- 会复杂化论文主线。

### 证据等级

- strict descent 会禁止上坡：**由代码证明**；
- 上坡可能有益：**合理推断**；
- token 机制可保证有限 MOVE：**由数学结构证明，条件式**；
- 它能改善当前数据：**尚无证据**。

---

## 7.4 风险四：`local_queue_capacity=0`

### 独立判定

**现有解释正确：它只取消软件件数上限及 queue-full backpressure，不取消 service calendar、R3 或 J2。它提高当前固定人口实验的可扩展性，但留下资源有界性和真实缓冲语义缺口。**

### 代码证明

配置注释明确：

`zero means no configured queue cap`

多处 queue-full、capacity-block 和 capacity-triggered PIBT 条件都要求：

`local_queue_capacity > 0`

因此为 0 时：

- 不会因普通 queue occupancy 达到件数上限而拒绝；
- queue-capacity blocker owner 分支不触发；
- capacity-triggered PIBT relief 不触发；
- 但 corridor/service calendar、destination merge controller、fault interlock 和其他 PIBT/重试路径仍存在。

### 公平性风险

固定时域容量比较仍然有效，因为比较对象是完整系统；但应明确：

- S4 允许把更多已 admission 的行李存入软件队列；
- 如果 HCA 具有不同的隐式或显式缓冲约束，完成量差异包含 admission/buffering 机制差异；
- 不能把结果解释成纯 next-hop scorer 的独立贡献；
- 未给出真实南宁每节点物理缓存容量，因此部署语义未闭合。

### 内存风险

对当前有限 1×/2×人口，普通队列最多受输入人口约束；这不等于开放流有界。

提交内没有足够证据证明：

- RSS 峰值；
- ordinary junction queue 峰值；
- source queue 峰值；
- event heap 峰值；
- backlog slope；
- 长时运行中 pending/queue 是否达到稳态。

### 高负载退化风险

queue cap 为 0 可能：

- 把 source backpressure 转移成 network backlog；
- 增加 queue scan/aging 成本；
- 增加重试和 beacon；
- 使局部公平性更依赖 J2/aging；
- 让固定时域完成量看起来更高，但系统末端积压更大。

### 证据等级

- queue-full 分支关闭：**由代码证明**；
- 当前 1×/2×安全完成：**已由结果证明**；
- 开放流内存或 backlog 有界：**尚无证据**。

---

## 7.5 风险五：direct-neighbour merge-calendar visibility 是否仍为一跳局部

### 独立判定

**代码层面通过一跳边界；没有发现运行时完整路线或全局预约。仍建议增加专门的无远端泄漏测试。**

### 代码证据

候选记录构造时：

- `candidate` 来自 `graph_.outgoing(current)`；
- 直接访问 `junctions_[candidate]`；
- 读取其 queue、scheduled-incoming；
- 对该候选节点的 `service_calendar` 计算 `earliest_start(arrival, service)`；
- scorer 只使用返回的一个时间标量；
- J2/merge controller 仍是唯一实际 grant/reservation authority；
- scorer 本身不为后续多边写入完整路线。

### 它读取的“未来”是什么

它读取的是直接邻居已存在的局部 service-calendar intervals，并计算候选到达时的最早服务时刻。这是：

- 局部资源的已承诺未来占用；
- 不是行李完整未来路径；
- 不是全图 task scan；
- 不是为当前行李创建多步预约。

在本项目定义下，这属于允许的一跳局部资源状态。

### 剩余风险

- calendar scalar 可能间接汇总来自多个邻域的状态；
- `purge()` / `observe_local_state()` 是否会在只读评分中产生可观察副作用，应由测试锁定；
- diagnostic/beacon 结构中仍存在 two-hop 字段，虽然当前 S4 公式没有使用它们；
- 需要验证改变两跳外未释放任务、同时保持当前和直接邻居状态不变时，当前动作不改变。

### 结论

可写“direct-neighbour calendar visibility 在实现上是一跳局部”，但不宜写成“已形式化证明完全不存在任何间接远端信息传播”。

---

## 7.6 风险六：节点 53 只是 EBS 代理

### 独立判定

**该边界在 profile 和协议中记录正确；论文与报告必须继续保留。**

### 数据证据

`business_roles.ebs` 明确写明：

- EBS 未在源工作簿中识别；
- type-7 是 empty-pallet storage，不是真实 EBS；
- proxy 需要 workload 显式预注册；
- adapter 不把 proxy 自动提升为真实 EBS。

### 三类问题必须分开

#### 算法问题

在给定 source/storage 角色下，S4 如何处理 source release、service calendar、merge 和故障。

#### 数据建模问题

选择哪个 type-7 节点代表 storage injection，如何把旧 workload 投影到南宁 starts/goals。

#### 机场业务语义问题

真实南宁 EBS 的位置、容量、入出库规则、提前量和控制逻辑。

当前结果只支持前两类实验结论，不支持第三类部署结论。

### 可写表述

> 在由南宁拓扑资料构建的 151 节点有向图上，使用明确标注的 type-7 empty-pallet-storage proxy 作为实验性 storage injection，S4 取得……

### 禁止表述

> 在真实南宁机场 EBS 部署中已证明……

---

## 7.7 风险七：2×容量的因果边界

### 独立判定

**报告生成器始终保持了该边界，未发现将 2× own-source timing 写成正式跨算法时延 verdict 的逻辑。**

### 报告/代码证据

协议字段明确：

- `capacity_release_alignment = same_scheduled_population_fixed_horizon_each_framework_own_source_admission`
- `capacity_is_segment_release_paired = false`
- `own_source_timing_cross_algorithm_verdict_allowed = false`
- paired timing 只来自 same-HCA-release full-pop artifacts；
- 2× timing slot 被标记未注册或 N/A；
- fault release pairing 为 false。

### 可以从 2×得出的结论

- 在固定 scheduled population 和时域下，哪个完整系统完成更多 raw bags；
- 哪个系统在高负载下更能完成任务；
- HCA 是否因规划/admission/route reservation 机制未完成全人口。

### 不能从 2×直接得出的结论

- 同一行李在同一实际 release 时刻下 S4 的 mean/P95 必然更低；
- S4 的纯 routing rule 单独导致全部完成量差；
- survivor 集合的时延可公平比较。

### 审计结论

G31 报告的因果边界是合格的。后续报告器必须继承同样 fail-closed 逻辑。

---

## 7.8 风险八：未知地图泛化与硬编码

### 独立判定

**当前只证明“两张指定地图上的跨地图可移植和性能”，未证明未知地图泛化。**

## 真正地图无关的核心

- C++ graph 根据传入 node/edge records 构造；
- S4 只枚举当前节点出边；
- service calendar、corridor calendar、fault windows 和 merge controller 按节点/边实例化；
- goal-conditioned service-aware potential 从输入图离线重算；
- storage source nodes 可配置；
- pybind/backend 接收动态图；
- 没有在 S4 scorer 中硬编码南宁节点 ID 或路线。

## 仍是实验壳/配置硬编码

- 稠密零基 ID；
- node type 与 loader/unloader/storage/recode 的业务解释；
- transfer loader 的 alias 规则；
- type-7 proxy 候选及最终选择 53；
- 旧 workload 到南宁 OD 的确定性负载均衡；
- 1×固定人口和 2×精确复制；
- 速度集合、固定结束 epoch、max events；
- 注册故障边和组合；
- map2 `pair_5_7` 标签；
- complete-on-goal-arrival seam；
- Table 5.3/5.4 的实验语义；
- HCA legacy map/task/hcost 文本格式。

## 第三图前必须补的通用层

- arbitrary external ID → stable dense internal ID remapper；
- 显式 role schema；
- OD/task schema；
- fault scenario schema；
- storage/EBS semantics 字段；
- profile validation；
- 不依赖 node type/alias 猜业务角色的 fail-closed 模式。

---

# 8. 当前主要瓶颈排序

| 排名 | 瓶颈 | 预计影响 | 可信度 | 为什么排在这里 |
|---:|---|---|---|---|
| 1 | 混合来源目的服务竞争未统一表示 | 高 | 高（代码缺口）；中高（性能因果） | 直接对应 53→49→50 和 source 49 的资源竞争，且可在不改变路由层的情况下修复。 |
| 2 | 证据闭环与第三图缺失 | 极高（论文可信度） | 极高 | 不一定立即提高性能，但决定“跨地图方法”能否成立，而不是两图工程结果。 |
| 3 | queue count 与时间项的隐式 1 s/件尺度 | 中高 | 高（公式）；中（性能因果） | 跨 service-time 图可能失配，但已有简单乘法负结果，必须谨慎。 |
| 4 | queue cap 0 下的资源、缓冲和长期稳定性未证明 | 中高 | 高（分支行为）；低到中（已发生退化） | 当前固定人口通过，但部署与更高负载风险未被测量。 |
| 5 | strict descent 缺少有限绕行 | 中 | 高（动作限制）；低（当前收益） | 有理论改进空间，但尚无证据它比混合来源竞争更重要，且会增加策略复杂度。 |

direct-neighbour visibility 本身不列为首要瓶颈，因为代码审计未发现超出直接邻居的完整路线读取；其主要缺口是缺少专门无远端泄漏测试，而非已确认的算法错误。

---

# 9. 下一阶段最多三个候选算法改进

## 9.1 候选 A：混合来源目的服务竞争 + 无副作用虚拟插入等待

### 状态

**首选；唯一建议立即启动的候选。**

### 是否增加新策略层

**不增加。**  
它扩展现有 destination service/J2 资源语义，使“本地 source ready work”和“外部 incoming/pending work”由同一局部服务资源观测。排序仍使用现有 FIFO/aging/deadline 合同，不新增 planner、supervisor 或学习器。

### 核心设计

先实现影子模式，定义节点 `v` 在时刻 `t` 的 mixed-origin contention：

- `external_ready(v,t)`：已有一跳 incoming、scheduled incoming 或 destination pending；
- `local_source_ready(v,t)`：节点本地 source queue 中已经 release 且达到服务条件的工作；
- 只有两者同时为真时才标记 mixed-origin；
- 只能从节点 `v` 自己维护的 O(1) counters/queue head 获取；
- 禁止扫描所有 bags；
- 禁止读取 `release_time > t` 的未来任务；
- 禁止把 source bag 伪装成多步 route；
- 禁止在 scorer 中写 calendar。

计算：

`virtual_insertion_wait_seconds(v, arrival, service)`

它表示当前候选若在现有局部服务合同下插入，预计需要等待的秒数。影子阶段只记录，不改变 S4 分数或 J2 grant。

### 为什么先影子而不是直接动作

当前代码已保证 service calendar 物理互斥。尚未证明性能问题来自统一仲裁缺失，而不是 workload 本身或下游 50。影子 trace 应回答：

- mixed-origin 事件实际出现多少次；
- 49 上本地与外部工作是否同时 ready；
- calendar 是否出现 `ready work > 0` 但服务空闲；
- 哪一来源等待显著更长；
- virtual wait 与真实后续 wait 是否相关；
- 当前 S4/J2 是否重复计数或遗漏工作。

### 最小修改文件

核心最小集：

1. `cpp/ics_core/runtime/event_driven_junction.hpp`
   - 新 config flag，默认 false；
   - 节点局部 O(1) mixed-origin counters；
   - pure virtual wait helper；
   - shadow telemetry；
   - state fingerprint 纳入 flag/counters；
2. `cpp/ics_core/bindings/czr005_cpp.cpp`
   - 绑定 flag 和新增 summary/trace；
3. `src/czr005/cpp_backend.py`
   - request 校验、默认值、结果转换；
4. 新增 `tests/test_g4irsf32_source_aware_service_contention.py`；
5. 新增 `scripts/eval/run_g4irsf32_source_aware_canary.py`；
6. 新增 G32 canary JSON/Markdown reporting。

**不应修改** G31 已提交结果和默认 runner 的正式 flags。G32 用新 runner 显式 opt-in。

### 预计影响

- 直接减少 53→49 到达时对本地 source service calendar 的误判；
- 降低 source/incoming 一方的长尾；
- 改善节点 49、50 的 queue-area、P95/P99；
- 1×稳定全人口容量大概率不变，时延可能改善；
- 2×和故障下可能提高完成量，但不能预先承诺。

### 失败风险

- local source work 与 calendar interval 重复计数；
- 把尚未 ready 的 source 工作误计为竞争者；
- source 与 incoming 一方饥饿；
- scorer 读取触发 calendar mutation；
- pending/event churn 增加；
- map2 无 mixed-origin 节点却被意外影响；
- 为了“公平”降低总吞吐。

### 可逆方式

- 单一 flag 默认 false；
- off 路径必须通过 action、state hash、summary 和 artifact 的精确兼容测试；
- shadow 和 action 分开两个 mode；
- G31 artifacts 不覆盖；
- 任一 gate 失败，删除 G32 opt-in，不改现有正式算法。

---

## 9.2 候选 B：用局部边际工作秒数替代 raw queue count

### 状态

**后备；只有候选 A 证明存在量纲误差且 mixed-origin 修复不足时才启动。**

### 是否增加新策略层

**不增加。**  
仅改变现有 S4 score 中 pressure term 的定义。

### 设计

不使用：

`queue_count × node_service_time`

而使用：

`uncovered_local_work_seconds`

其中只计：

- 当前已释放；
- 当前 local ready；
- 尚未被现有 service calendar wait 覆盖；
- 位于候选直接邻居；
- 通过 O(1) 累计或 bounded local pending inventory 维护。

建议分数：

`travel + potential + corridor_wait + explicit_calendar_wait + uncovered_work_seconds`

系数固定为 1，不做大规模参数网格。原 raw count term 在候选模式中被替换，而不是叠加，避免重复惩罚。

### 最小修改文件

- `event_driven_junction.hpp` 的 candidate record 与 S4 scorer；
- binding/backend；
- G32 score unit tests；
- 新的 ablation runner；
- 不修改 map profile 或 workload。

### 预计影响

- 使不同 service-time 地图上的压力项具有秒单位；
- 减少慢服务节点的隐式低估；
- 比简单 `count×service` 更少双计数。

### 失败风险

- virtual work estimate 与真实 J2 顺序不一致；
- 候选之间分数差过大，产生过度绕行；
- calendar 已覆盖工作判断错误；
- map2 当前良好平衡被破坏。

### 可逆方式

- scorer mode append-only；
- 旧 S4 exact-off；
- 只在候选 A 之后单独消融；
- 任一 map2 sentinel 退化即停止。

---

## 9.3 候选 C：一次性有限 detour token

### 状态

**最后后备；不应与 A/B 并行。**

### 是否增加新策略层

**会增加一个极小的新策略状态。**  
每个 segment 增加一个不可补充的 detour token 和一个严格 eligibility guard。它不是完整路径规划器，但比 A/B 更改动主线。

### 设计约束

- token 初值 1；
- 只允许一次非下降 MOVE；
- 非下降幅度 `ΔH` 必须小于固定、预注册上限；
- 只在当前候选的 local calendar saving 足够大时允许；
- 禁止立即回边、短历史重复和 faulted edge；
- token 消耗后恢复 strict descent；
- WAIT 不消耗，也不补充；
- 新 segment 才重置；
- 不使用全路径、模型或 global scan。

### 终止性

使用前述字典序排名 `(token_remaining, H)`。唯一 detour 消耗 token，使第一维下降；之后每次 MOVE 使 H 严格下降。因此 committed MOVE 数有限。

### 最小修改文件

- `BagState` / event runtime；
- scorer guard；
- binding/backend config；
- state clone/fingerprint；
- strict proof tests；
- loop/adversarial canary。

### 预计影响

- 在有环图中保留一次局部绕行机会；
- 可能改善极端 calendar congestion；
- 对正常路径影响应很小。

### 失败风险

- 事件和回访增加；
- token 在 fault/reset 中被错误补充；
- detour 后回到原节点但未改善；
- 论文方法复杂化；
- 大多数场景无 action change。

### 可逆方式

- append-only guard mode；
- 默认 strict；
- 单 token；
- 未出现稳定 action-changing positive 前不进入完整矩阵。

---

## 9.4 候选比较

| 候选 | 新策略层 | 局部性 | 终止保证 | 预期收益证据 | 优先级 |
|---|---|---|---|---|---|
| A 混合来源服务竞争 | 否，扩展 J2/日历语义 | 一跳 | 不改变现有 route guard | 中高 | 1 |
| B 局部工作秒数 | 否，改变 S4 pressure term | 一跳 | 不改变 strict descent | 中 | 2 |
| C 单 detour token | 是，最小 per-bag 状态 | 一跳 | 条件式可证明 | 低 | 3 |

---

# 10. Canary 阶梯与 GO/NO-GO 门

## 10.1 Stage 0：合同与 exact-off

### 必做测试

1. flag=false 时：
   - selected actions 完全一致；
   - completion/timing 完全一致；
   - state fingerprint 完全一致；
   - committed G31 request identity 不变；
2. shadow=true 时：
   - action 完全不变；
   - calendar reservation 不变；
   - event publication 不变，除独立 telemetry sidecar；
3. locality：
   - helper 只能读取当前服务节点和直接邻接上下文；
   - 禁止迭代全体 bags/tasks；
4. no-future-leakage：
   - 任意修改 `release_time > t` 的任务，时刻 t 之前的 shadow feature 与 action 必须不变；
5. no-double-count：
   - 已存在 calendar interval 的工作不能再次进入 uncovered ready work；
6. transaction：
   - rollback 后 counters/calendar generation 精确恢复；
7. safety：
   - failed/conflict/unsafe/full A*/global scan/future route 均为 0。

### GO

全部硬门通过。

### NO-GO

任何一项不满足，停止；不得运行真实地图 canary。

---

## 10.2 Stage 1：合成 mixed-origin motif

### 固定微拓扑

- storage proxy `S→L→D`，模拟 `53→49→50`；
- `L` 同时拥有本地 source；
- `L` service time 分别固定测试 1.0、1.5、2.0、3.0 s；
- 不增加第二条图入边，保证 `incoming_degree(L)=1`；
- 下游保留一个分流节点和一个 goal，验证路由完整。

### 固定流型

- 仅外部；
- 仅本地；
- 同时到达；
- 本地 burst 后外部；
- 外部 burst 后本地；
- 交替；
- 一方持续 backlog、另一方稀疏；
- 8、32、128 bags 三个规模。

这不是参数网格搜索，而是覆盖必要机制边界的固定 canary 集。

### 硬门

- 全部可达 bags 完成；
- 0 calendar overlap；
- 每 bag 恰好一次对应 node-service；
- 0 duplicate grant/reservation；
- 两种来源均被服务，不允许永久饥饿；
- pending controller 不超过配置上限；
- events/completed ≤ control 的 1.10 倍；
- peak local accounted bytes ≤ control 的 1.10 倍；
- shadow predictor 对真实随后 service wait 的排序方向不能系统性反号。

### 继续到动作模式的 GO

同时满足：

- mixed-origin shadow 事件数 > 0；
- 至少四种流型中发现当前路径没有统一表示的 ready work；
- virtual insertion wait 与真实额外等待具有正方向关系；
- no-source 和 no-external negative controls 为零或精确 no-op。

否则：

`NO_GO_MIXED_ORIGIN_HYPOTHESIS_NOT_SUPPORTED`

不得修改正式动作。

---

## 10.3 Stage 2：两图小规模真实 slice

### 固定案例

- 南宁：
  - 1×、2×；
  - 2.5 m/s 稳定；
  - 一个 source-chain-active 单故障；
  - 一个 source-chain-inactive 负对照；
- map2：
  - 同规模、同速度；
  - 至少一个稳定 sentinel；
  - 一个故障 sentinel。

案例必须在查看 candidate outcome 前按 control trace 中是否经过 mixed-origin node 预注册。

### 硬门

- 完成件数不得下降；
- 0 safety regression；
- full A*/model/global scan/future route 为 0；
- map2 无 mixed-origin 负对照的 action mutation 必须为 0，或有明确可解释的等价 mixed-origin 事件；
- events/completed、wall、RSS、peak queue 任何一项不得超过 control 10%。

### 性能 GO

南宁 target cohort：

- node-49 mixed-origin wait-area 至少下降 5%，或 idle-while-ready 时间至少下降 50%；
- target cohort P95 至少下降 2%；
- 全系统 mean 不得恶化超过 0.5%；
- 全系统 P95/P99 不得恶化超过 1%；
- 不得把 source wait 简单转移成 network wait 且总时延不变。

map2：

- mean/P95/P99 均不得恶化超过 0.5%；
- completed 不得下降。

未通过即停止，不得跑完整正式矩阵。

---

## 10.4 Stage 3：选择性 full run

只有 Stage 2 通过后运行：

- map2 与南宁；
- 1×、2×；
- 稳定 1.5 和 2.5 m/s；
- 每图一个高影响故障、一个 topology-ceiling 负对照；
- 1× eligible stable cells 生成 same-HCA-release paired timing。

### GO

- 所有 capacity cell 无 loss；
- paired mean/P95/P99/max 无超过 0.5% 的回归；
- 至少两个南宁 full cells 的 mean 或 P95 改善 ≥2%；
- events/completed、RSS、peak ordinary queue ≤ control 1.10 倍；
- 0 新 deadline miss、starvation、unsafe、failed、conflict；
- exact-off map2 regression 通过。

### NO-GO

任一硬门失败，候选 A 保持 shadow-only 或完全撤回。不得进入全矩阵。

---

## 10.5 Stage 4：完整矩阵

只有 Stage 3 GO 后才允许执行：

- 南宁 40 格；
- map2 38 个当前可测格；
- paired 1× timing；
- 完整资源遥测；
- current G31 与 G32 candidate 同时保留；
- 报告不能覆盖 G31 历史产物。

任何直接跳过 Stage 0–3、先运行 78 格完整矩阵的做法均违反本计划。

---

# 11. 下一阶段实验矩阵

## 11.1 主矩阵

| 地图 | 负载 | 稳定速度 | 故障容量 | 正式时延 |
|---|---|---|---|---|
| map2 | 1× | 1.5/2.0/2.5/3.0 | 当前可测 single/pair/triple；`pair_5_7` 仍 NM | 同 HCA release，双方 full population |
| map2 | 2× | 1.5/2.0/2.5/3.0 | 当前可测 single/pair/triple | 只有 HCA 完成全人口后才注册 |
| 南宁 | 1× | 1.5/2.0/2.5/3.0 | 当前 16 个注册故障 | 仅 eligible speeds，同 HCA release |
| 南宁 | 2× | 1.5/2.0/2.5/3.0 | 当前 16 个注册故障 | 暂不产生正式 verdict，除非补齐 full-pop HCA release |
| 第三图 | 1× | 冻结后的固定速度组 | 预注册结构故障 | 能 full population 才比较 |
| 第三图 | 2× | 同上 | 同上 | 同一 release/full-pop 才比较 |

## 11.2 每个正式 case 必须新增的资源指标

业务：

- completed raw bags / fixed denominator；
- source wait、junction wait、calendar wait、network time；
- mean、P50、P95、P99、max；
- deadline miss；
- per-origin wait；
- node 49/50 queue area；
- detour/revisit/hops。

运行时：

- wall time；
- events total、events/completed；
- event heap peak；
- ordinary junction queue peak；
- source queue peak；
- destination pending peak；
- service calendar interval peak；
- RSS peak；
- locally accounted bytes peak；
- backlog at fixed horizon；
- backlog slope in final 10%/25% window；
- retry、stale wakeup、PIBT activation；
- mixed-origin shadow/action counts。

安全/边界：

- failed、conflict、unsafe、stranded；
- full A*；
- global task scan；
- future route read；
- model use；
- max edges selected per decision；
- reservation depth；
- no-future-leakage canary hash。

## 11.3 报告原则

- capacity 与 timing 分表；
- own-admission 只产生 capacity verdict；
- full-pop same-release 才产生 timing verdict；
- topology upper tie 单独显示；
- 微小 strict win 同时报告 absolute difference 和 percentage points；
- 每个结果标出 evidence level；
- 资源回归可以否决业务小幅改善；
- 未完成单元格不得用 survivor 数值填充。

---

# 12. 缺失证据补齐计划

## 12.1 Table 5.3

### 目标

确认原论文 Table 5.3 的：

- 原始输入；
- source release；
- 地图版本；
- HCA 二进制/源码；
- 参数；
- 重复与随机种子；
- 指标分母。

### 执行

1. 搜索原论文归档、作者电脑、旧仓库、附件和构建产物；
2. 生成 provenance manifest 和 SHA256；
3. 先在 map2 精确复现；
4. 只有精确 map2 复现通过，才定义南宁对应实验；
5. 若任一核心输入缺失，永久标记：
   - `TABLE_5_3_ARCHIVE_UNAVAILABLE_NON_EXACT_RECONSTRUCTION`
6. NON_EXACT 结果只能描述，不得写“精确复现后胜出”。

## 12.2 Table 5.4

### 当前问题

现有 24 格只对 S4 重建 observation bias 上下文，没有同扰动 HCA arm。

### matched 设计

- 同一 segment；
- 同一 perturbation seed；
- 同一 `U(0,k)` 样本；
- 同一扰动施加位置；
- 扰动只影响 observation，不改变真实 service/edge/release；
- HCA 与 S4 都完成全人口；
- 同一 denominator；
- 不允许 unperturbed HCA 作为 matched arm。

若 legacy HCA 没有等价 observation seam，应明确：

`NO_MATCHED_HCA_SEAM_TABLE_5_4_REMAINS_DESCRIPTIVE`

不能人为把扰动加到不同语义位置。

## 12.3 `pair_5_7`

### 当前问题

历史线路标签与边集合定义冲突，两个尺度均 NM。

### 关闭流程

1. 从原论文表、Java fault code、旧配置和运行日志追踪 fault 5/7 的精确 directed edges；
2. 保存 provenance；
3. 如果存在两个合理定义，做双定义 sensitivity；
4. 在 provenance 唯一前保持 NM；
5. 不得选择对 S4 更有利的一版作为“正确版”。

## 12.4 第三张未调参地图

### 选择原则

- 在 G32 candidate 参数冻结后才导入；
- 拓扑结构与 map2/南宁明显不同；
- 包含有向环、不同 merge 分布、不同 service-time 尺度；
- 尽可能有明确 source/sink/storage 语义；
- 禁止根据结果调 scorer、guard 或 proxy。

### 前置工程

- arbitrary external ID remapper；
- explicit role schema；
- fail-closed storage/EBS；
- generic workload importer；
- generic fault schema；
- 自动 profile validation。

### 预注册结论门

第三图只允许三类结论：

- `UNSEEN_MAP_PASS`：可运行、安全、无系统性负项；
- `UNSEEN_MAP_MIXED`：部分退化，报告失败；
- `UNSEEN_MAP_FAIL`：不可运行或安全/容量退化。

不得因结果不好替换第三图。

---

# 13. 论文、工程与探索性结论边界

## 13.1 当前可写入论文的结果

1. 两图可移植框架与 profile/config 架构；
2. S4 运行时一跳 next-edge 决策、无运行时完整 A*、无学习模型；
3. 78 个可测固定时域容量单元格的 `57/21/0`，但必须写清 own-source admission；
4. 35 项同 release/full-pop 时延的 `31/4/0`；
5. 南宁 2×和故障下的大幅容量优势；
6. map2 兼容结果；
7. Table 5.4 被隔离为 NON_EXACT 的科学边界；
8. type-7 EBS proxy 的明确限制；
9. pair_5_7 的 NM，而不是补值；
10. offline potential 与 runtime local decision 的分离。

## 13.2 只能作为工程结论

- 当前 profile loader 处理 151 节点南宁图；
- fixed-horizon 800M event budget 下正式 cases 未耗尽；
- queue cap 0 在当前 1×/2×人口下可运行；
- type-7 proxy 53 的实验可用性；
- complete-on-goal-arrival seam；
- 当前 Python/C++ binding 能传递动态地图配置。

## 13.3 只能作为探索性结论

- 节点 49 是主要因果瓶颈；
- virtual insertion wait 会改善全系统；
- service-seconds pressure 比 raw count 更优；
- 一次 detour 会改善拥堵；
- queue cap 0 在开放流中会失控；
- direct-neighbour visibility 完全没有任何间接远端依赖。

这些必须通过 G32 专项实验后再升级。

## 13.4 当前禁止写入论文的表述

- “原论文全部表格已精确全面胜出”；
- “真实南宁 EBS 部署已验证”；
- “S4 对未知机场地图普适优于 HCA”；
- “57 个统计显著胜利”；
- “所有 2×行李时延更低”；
- “系统已证明在任意负载下内存和 backlog 有界”；
- “去中心化性质已形式化证明”；
- “学习模型贡献”，G31 正式路径没有学习模型。

## 13.5 建议论文主结论文字

> 本文构建了一个基于输入机场有向拓扑离线计算服务感知势函数、并在运行时仅依据当前节点、直接邻居及局部资源状态选择单条下一跳边的无学习路由框架。在 map2 与一张由南宁机场拓扑资料适配得到的 151 节点图上，固定时域容量矩阵的 78 个可测单元格中，该框架有 57 格完成量严格高于集中式 HCA，21 格达到相同全人口或拓扑上限，未出现容量负项；在逐 segment 使用相同 HCA 释放时序且双方完成全部人口的 35 项时延指标中，31 项更低，4 项处于 1 ms 物理分辨率内。南宁业务流和 storage 节点为明确标注的实验投影与代理，结果不等价于真实机场部署验证。

---

# 14. 可直接交给编码代理的 P0/P1/P2 行动清单

## P0：只做候选 A 影子证据，不改变动作

### P0.1 分支与冻结

- 从 `46cc46ab6bc121628fd6357e9f3c7636745fd732` 创建独立分支；
- 不修改或覆盖 G31 committed outputs；
- 写入 G32 protocol，先冻结 canary 与 gates；
- 每个输出记录 base commit、binary hash、profile hash、manifest hash。

### P0.2 C++ config

在 `EventDrivenJunctionConfig` 增加 append-only 字段：

- `source_aware_destination_service_mode = "off"`；
- 允许值仅：
  - `off`
  - `shadow`
  - 后续才增加 `closed_loop`
- 默认必须是 `off`。

### P0.3 局部状态

在每个 junction/source controller 维护 O(1) 或 bounded local 状态：

- released source ready count；
- released source uncovered service work seconds；
- external scheduled incoming；
- destination pending count；
- oldest local/external wait age；
- service calendar next-free scalar；
- generation。

禁止：

- 扫描全任务；
- 查询未来 release；
- 读取两跳以上节点；
- 保存 route suffix；
- 保存地图特定 ID policy。

### P0.4 helper

实现并单元测试：

- `has_released_local_source_work(node, time)`；
- `has_external_destination_work(node, time)`；
- `mixed_origin_service_contention(node, time)`；
- `virtual_destination_service_wait(node, arrival, service)`。

helper 必须无 reservation 副作用。允许清理已过期 local calendar interval，但必须保证在同一 event epoch 的调用顺序不改变 action。

### P0.5 telemetry

新增 G32 sidecar：

- node/time/generation；
- local source ready count/work seconds；
- external incoming/pending；
- existing calendar wait；
- virtual insertion wait；
- selected action；
- actual subsequent source/junction/calendar wait；
- origin；
- action_changed=false；
- future-release-read-count=0；
- global-scan-count=0。

### P0.6 binding/backend

- pybind 暴露 mode；
- Python request default off；
- 结果 schema append-only；
- unknown mode fail closed；
- off path fingerprint 精确回归。

### P0.7 测试

至少新增：

- exact-off parity；
- mixed-origin indegree-one motif；
- no-local-source negative control；
- no-external negative control；
- future release perturbation invariance；
- distant graph state invariance；
- calendar no-mutation；
- no double count；
- rollback/generation；
- bounded local memory；
- map2 sentinel。

### P0.8 输出与停止门

输出：

- `outputs/tables/g4irsf32_source_aware_shadow.json`
- `outputs/reports/g4irsf32_source_aware_shadow.md`

只有 Stage 0/1 GO 才进入 P1。

---

## P1：候选 A 动作阶段与选择性 full

### P1.1 动作边界

优先方案：

- 复用现有 destination service/J2 authority；
- mixed-origin 节点把本地 source head 与外部 incoming request 作为同一局部服务机会的候选；
- 继续使用现有 FIFO/aging/deadline；
- 每次只授予当前节点的一次服务/一条相邻边；
- 不创建未来路线。

如果现有 controller 不能安全表示 local-source origin，则不要用 sentinel edge 强行塞入。应增加明确 `origin_kind`，但仍复用同一 authority，而不是创建第二套 arbiter。

### P1.2 硬性不变量

- 一个服务机会一个 owner；
- 同一 bag 不得同时拥有 source service 和 incoming service reservation；
- source 与 incoming 均可等待；
- no starvation；
- exact calendar generation；
- one-hop；
- reservation depth 1；
- full A*=0；
- model=0；
- future task read=0。

### P1.3 实验

严格按 Stage 2、3 执行。未通过不得完整矩阵。

### P1.4 资源遥测

补齐：

- RSS；
- event heap；
- ordinary/source queue；
- calendar intervals；
- pending；
- backlog slope；
- per-origin fairness。

### P1.5 证据补齐支线

在不阻塞候选 A canary 的情况下：

- Table 5.3 archive search；
- Table 5.4 matched seam feasibility；
- pair_5_7 provenance；
- 第三图 importer。

---

## P2：只有 P1 完成后才允许

按顺序：

1. 若 mixed-origin 修复通过但量纲残差仍明显，启动候选 B；
2. 若 trace 显示 strict guard 经常屏蔽有益局部候选，且 A/B 不足，启动候选 C；
3. 冻结最终算法和配置；
4. 导入第三张未调参地图；
5. 完成全矩阵和论文 report；
6. 若第三图失败，报告失败，不回到两图调参后重选第三图。

P2 禁止：

- 深度学习；
- 强化学习；
- global A*；
- 中央完整路径规划；
- 多步未来预约；
- map-ID codebook；
- 大规模参数网格；
- 同时并行 A/B/C 造成无法归因。

---

# 15. 唯一下一步

**推荐立即执行：候选 A 的 P0 影子阶段。**

准确任务是：

> 在不改变任何 S4/J2/E2 动作、不改变 strict descent、不改变 queue capacity 和 PIBT 的前提下，为直接邻居目的服务资源增加 mixed-origin shadow telemetry，并实现只读的 virtual insertion wait；用 `53→49→50 + node49 local source` 合成 motif、南宁小 slice 和 map2 sentinel 证明该状态真实存在、局部、无未来泄漏、无重复计数且可能解释长尾。只有这些证据通过，才允许把它接入现有 J2 authority。

不推荐此时：

- 直接把 queue count 乘 service time；
- 直接放宽 strict descent；
- 直接恢复有限 queue cap；
- 直接跑 78 格完整矩阵；
- 同时实现多个候选；
- 引入学习、全局搜索或中心 planner。

---

# 附录 A：证据定位索引

| 审计主题 | 文件 | 关键函数/字段/产物 |
|---|---|---|
| 最终容量与时延 headline | `outputs/reports/g4irsf31_reporting.md` | `57W/21T/0L`、paired verdicts、NON_EXACT boundary |
| 机器可读结果 | `outputs/tables/g4irsf31_reporting.json` | `protocol`、`primary_rows`、`input_diagnostics`、cross-map summaries |
| 单元格复核 | `outputs/tables/g4irsf31_reporting.csv` | 每格 denominator、S4/HCA completed、verdict |
| 实验合同 | `docs/G4IRSF31_nanning_protocol.md` | own admission、paired timing、EBS proxy、workload projection |
| profile loader | `scripts/eval/g4irsf31_map_adapter.py` | `load_map_profile`、`build_s4_request`、`G31_LOCAL_QUEUE_CAPACITY` |
| 南宁 profile 生成 | `scripts/eval/run_g4irsf31_nanning_map.py` | namespace、role inference、EBS status、service imputation |
| 南宁 profile | `data/processed/maps/nanning_airport_profile.json` | 151/227、node49/50/53、`business_roles.ebs` |
| 工作负载 | `scripts/eval/run_g4irsf31_nanning_workload.py` | storage proxy、deterministic load balancing、1×/2× |
| 南宁 S4 | `scripts/eval/run_g4irsf31_nanning_native.py` | flags、fixed horizon、fault potential、safety admission |
| map2 S4 | `scripts/eval/run_g4irsf31_map2_native.py` | canonical map2、2×、pair5_7 NM |
| 南宁 HCA | `scripts/eval/run_g4irsf31_nanning_hca.py` | generated legacy inputs、roles、fixed population |
| fresh HCA | `scripts/eval/run_g4irsf24_fresh_hca.py` | isolated Java runs、lifecycle、eligibility |
| HCA core behavior | `benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java` | `pathPlanningAStar`、`lockPath` |
| 南宁 paired timing | `scripts/eval/run_g4irsf31_same_hca_release_timing.py` | exact release trace、full-pop gates |
| map2 paired timing | `scripts/eval/run_g4irsf31_map2_same_hca_release_timing.py` | 1× eligible、2× N/A |
| 报告逻辑 | `scripts/eval/run_g4irsf31_reporting.py` | `_capacity_verdict`、paired gates、NON_EXACT exclusion |
| S4/J2/E2 core | `cpp/ics_core/runtime/event_driven_junction.hpp` | candidate score、indegree merge gate、calendar visibility、queue cap branches、strict guard |
| C++ binding | `cpp/ics_core/bindings/czr005_cpp.cpp` | dynamic graph/config/flag binding |
| Python backend | `src/czr005/cpp_backend.py` | request validation/native call |
| profile tests | `tests/test_g4irsf31_map_adapter.py` | dense IDs、roles、flags、map2 default |
| native tests | `tests/test_g4irsf31_nanning_native.py` | registered cases、safety/locality contract |
| reporting tests | `tests/test_g4irsf31_reporting.py` | headline、boundary、byte stability |

---

# 附录 B：审计者的最终判定标签

```text
MAP_PORTABILITY_CORE: PASS_WITH_CONFIGURATION_BOUNDARY
MAP2_REVERSIBILITY: PASS_AT_G31_TESTED_SCOPE
NANNING_WORKLOAD_SEMANTICS: PROJECTED_NOT_REAL_OPERATIONAL
RUNTIME_ONE_HOP_DECISION: PASS_FOR_G31_CONFIGURED_PATH
RUNTIME_NO_FULL_ASTAR: PASS_FOR_ADMITTED_G31_ARTIFACTS
DIRECT_NEIGHBOR_CALENDAR_LOCALITY: CODE_PASS_TEST_GAP_REMAINS
CAPACITY_57_21_0: RELIABLE_WITHIN_FIXED_HORIZON_OWN_ADMISSION_PROTOCOL
PAIRED_TIMING_31_4_0: STRONGEST_CURRENT_CROSS_ALGORITHM_EVIDENCE
TABLE_5_3: INCOMPLETE
TABLE_5_4: NON_EXACT_NO_MATCHED_HCA
PAIR_5_7: NOT_MEASURED
REAL_NANNING_EBS_DEPLOYMENT: NOT_SUPPORTED
UNKNOWN_MAP_GENERALIZATION: NOT_PROVEN
OPEN_FLOW_RESOURCE_BOUNDEDNESS: NOT_PROVEN
PRIMARY_ALGORITHM_BOTTLENECK: MIXED_ORIGIN_DESTINATION_SERVICE_CONTENTION
UNIQUE_NEXT_STEP: SOURCE_AWARE_J2_SHADOW_PLUS_PURE_VIRTUAL_WAIT
```
