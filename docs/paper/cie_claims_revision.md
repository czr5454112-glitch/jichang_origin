# CIE 稿件主张修订清单

状态：最终证据已回填。strict descent、fault potential、service
normalization、E2 与 paired random robustness 均由最终聚合封口；J2/M3 的
精确单变量对照因合流规则与计时合同耦合而明确阻断，不再保留待办占位符。

本文件不修改外部 Word 原稿。它给出应保留、改写、删除或暂缓的
论文主张，并把每项主张绑定到仓库最终证据。缺失量只写为 N/A、N/M、
NOT_MEASURED 或明确 blocker，不从中间文件猜测，也不以新模式补做失败方向。

## 1. 全局写作口径

1. 使用“预先设定”“预先固定”或“在读取结果前冻结”，不用“预登记”
   或“preregistered”，除非另有可公开核验的外部时间戳。
2. 使用“map2 与南宁两张已知拓扑上的跨图验证/可移植性”，不用“未知
   地图泛化”。
3. 使用“固定起始（启动前登记）并在整个实验时域持续的线路中断”，不用“动态故障
   恢复”。动态 fault/repair 只在明确的独立实验中讨论。
4. 将 P0、P1、P2 分表、分标题、分结论：P0 是 Feng 原生历史复现，P1
   是公共执行器路线隔离，P2 是完整系统端到端比较。禁止跨协议传递排序。
5. 只有完整正式人口、合法释放协议和非幸存者口径才报告 THT。所有 2×
   正式跨算法 THT 继续为 N/A；2x 只报告固定时域完成量、截止成功、
   time-to-X、迟到和积压。
6. 未报告字段保持 `N/A`、`NOT_MEASURED` 或明确 blocker；不得补成零。
7. 机制激活、业务收益、安全职责和计算收益分别表述。激活计数不是性能
   收益，系统级结果不是单一机制的因果效应。
8. 随机稳健性只使用 frozen manifest、已提交 runner 和十个固定 paired
   seeds；每个 seed 的两臂共享完全相同的 arrival/service 扰动 realization。
9. `SERVICE_X2` 始终是 1× 人口的服务压力控制，不是 workload 2×。
10. `outputs/tables/cie_safety_audit.csv` 仅属于旧 G35 审计，不作为本轮
    安全证据；本轮依据各 run 的 execution-integrity 与 aggregate gates。
11. 激活普查未采集的分位数、相关性和热点分布统一记为
    `NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`，不为机械完整性重跑。
12. backlog 只引用固定时域校正后的数值；legacy last-event 百分比不得进入
    稿件结论。

权威协议说明见 `docs/baselines/baseline_lineage_and_protocols.md`；Feng
native 语义缺口见 `docs/baselines/feng_native_cie_dh_crosswalk.md`。

## 2. 数值与措辞纠正

| 原/高风险表述 | 修订动作 | 可发表替代表述 | 证据 |
|---|---|---|---|
| “累计多完成 905,002 件行李” | 从摘要和结论删除；若保留，只能放在附录解释统计含义 | `905,002` 是 78 个互斥确定性场景配置中 G31-HCA 完成数差值的代数和；同一 28,506/57,012 人口在不同配置中重复出现，不能解释为独立真实行李、累计运营吞吐或样本量 | `outputs/reports/g4irsf31_reporting.md` |
| “78 次实验”或“78 次独立试验” | 改写 | 78 个预先设定的确定性场景配置：两张已知拓扑、稳定/固定线路中断、1x/2x 与固定速度组合；它们不是 78 个独立随机重复 | `outputs/reports/g4irsf31_reporting.md` |
| “31/35 次胜利” | 改写 | 在 7 个完整人口 1x map-speed 场景中报告的 35 项相关分布指标（每格 min/mean/P95/P99/max）里，G31 有 31 项较低、4 项处于物理时间分辨率平局；这些指标共享场景和人口，不是 35 次独立试验 | `outputs/reports/g4irsf31_reporting.md` |
| “预登记实验/门槛” | 改写 | 实验配置、停止规则和比较门槛在读取对应结果前预先设定并固定 | `configs/eval/cie_revision_manifest.yaml` |
| “跨地图泛化” | 降级 | 在 map2 与南宁两张已知拓扑上的方向一致性和可移植性验证 | `outputs/reports/g4irsf31_reporting.md` |
| “动态故障恢复” | 改写 | 对固定起始（启动前登记）、在整个固定时域持续的线路中断进行鲁棒性评价 | `configs/eval/cie_revision_manifest.yaml`; `outputs/reports/g4irsf31_reporting.md` |
| “2x 时延更低” | 删除 | 2× 正式 THT 为 N/A；比较固定时域完成量、截止成功、迟到、time-to-X 与积压 | `outputs/reports/cie_baseline_comparison.md` |
| “P2 提高性能” | 删除 | P2 在当前正式配置中 dormant；所有十个激活格的 applicability/commit/rollback 均为零 | `outputs/tables/cie_component_activation.csv`; `outputs/reports/cie_specialty_mechanism_audit.md` |
| “E2 提高物理容量” | 删除 | E2 v2 在双图 1× 当前协议下通过完整物理轨迹等价并减少事件；它是 `COMPUTE_ONLY_ROLE`，wall/CPU/RSS 仅作单次描述，`event_queue_peak` 为 N/M | `outputs/reports/cie_e2_equivalence_report.md`; `outputs/tables/cie_e2_equivalence.csv` |
| “J2 已被精确消融并产生收益” | 删除 | 现有接口同时改变 merge rule 与 timing contract，精确单变量对照为 `BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT` | `outputs/reports/cie_specialty_mechanism_audit.md` |
| “随机稳健性估计了 potential×dynamic 交互” | 删除 | 随机矩阵只比较 P0D0 与 P1D1 的联合对比，交互为 `INTERACTION_NOT_ESTIMATED` | `outputs/reports/cie_random_robustness_report.md` |

## 3. 主张账本

### C1. 原论文正式科目上的 G31-HCA 结果

状态：`RETAIN_WITH_EXACT_PROTOCOL`。

可发表主张：在相同 HCA segment release、完整 28,506 件 1x 人口上，
G31 相对 HCA 的 mean/P95/P99/max 在 map2 分别降低
11.532%/17.599%/23.479%/27.101%，在南宁分别降低
24.365%/27.207%/29.495%/71.494%。在 2x 固定时域中，G31 在两图均
完成 57,012/57,012；HCA 在 map2 完成 56,917，在南宁完成 39,063。

禁止外推：这些结果不证明每个内部组件分别有效，也不构成未知地图泛化。

证据：`outputs/reports/cie_baseline_comparison.md`，
`outputs/reports/g4irsf31_reporting.md`。

### C2. 78 个配置、35 项时延指标与 905,002

状态：`REWRITE`。

可发表主张：78 是确定性场景配置数；35 是 7 个完整人口 1x map-speed
场景中的相关分布统计数；31 项较低、4 项为物理分辨率平局。

必须删除：把 905,002 写成独立行李收益、把 78 写成独立试验、把 31/35
写成独立胜率。

### C3. P0 Feng-native 历史复现

状态：`PARTIAL_WITH_BLOCKER`。

可发表主张：恢复的 Feng Java HCA 在 43,603 segments/28,506 raw bags
完整人口上通过冻结聚合回归，processed-attempt min/mean/max 为
3.133333/3.945169/5.950000 min，与冻结的 188.0/236.710166/357.0 s
精确一致。该审计没有冻结逐任务 release/route/completion trace，因此不是
trace-exact 路线身份声明。

Feng-native CIE-DH 必须报告为
`N/A (BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED)`。恢复出的 15 个 Java
源码包含 HCA 的全路径 A* 预约调用链，但缺少 native DH 所需的
moving/stopped、BTI、DDI、HOLD 和 0.2 s 位置级状态。公共 C++ 执行器中的
CIE-DH 不得填入 P0。

恢复的 native HCA 只提供冻结聚合回归，没有本轮机制所需的原生计数器；
该字段记为 `BLOCKED_NATIVE_HCA_MECHANISM_COUNTERS_NOT_INSTRUMENTED`，不能
用公共 C++ 执行器计数代填。

证据：`outputs/reports/feng_native_cie_dh_reproduction_audit.md`，
`outputs/tables/feng_native_cie_dh_table53_audit.csv`。

### C4. P1 公共执行器基线

状态：`RETAIN_AS_ADAPTED_BASELINES`。

可发表主张：CIE-DH common-executor 与 TARAU_DISTRIBUTED_2010 都是透明
adaptation，而不是 Feng-native exact reproduction。修复版 Tarau 与其配对
G31 使用相同二进制和 neutral FIFO；G31 的 1x mean/P95/P99/max 在 map2
与南宁均较低。2x map2 两者均完成全人口，但 Tarau 的截止成功多 140 件；
2x 南宁 G31 完成 57,012，Tarau 完成 47,707，差 9,305 件。

必须保留的负/混合证据：在旧同二进制 CIE-DH cohort 中，CIE-DH adapted
在南宁 1x 的部分时延略优于 G31，且 map2 2x 截止成功达到 57,012、比
G31 多 140 件。不同 P1 构建不得合并成无条件三臂排序。

证据：`outputs/reports/cie_baseline_comparison.md`。

### C5. P2 原生完整系统比较

状态：`RETAIN_AS_SYSTEM_LEVEL`。

可发表主张：Feng-native HCA 与 G31/S4 native 的差异是完整系统端到端
业务差异。1x 使用完整人口同释放时延；2x 使用固定时域容量与业务指标。

禁止外推：P2 系统差距不能全部归因于 scorer、势函数、J2/M3、E2 或任何
单一模块。

### C6. 24 格 potential x dynamic 析因

状态：`RETAIN_WITH_CONDITIONAL_INTERPRETATION`。

24 个完成运行由 16 个 S4 neutral-FIFO 2x2 格和 8 个 CIE-DH
common-executor H_FF/H_SA adaptation 格组成。只有 12 格满足正式完整人口
时延条件；2× THT 仍为 N/A。

S4 的可发表结论：

- map2 1x 四格均完成全人口，H_SA 的平均主效应为 mean `-0.480827 s`、
  P95 `-0.5 s`、P99 `-4.8 s`、max `-10.0 s`；作用较小但方向一致；
- map2 2x 四格均完成 57,012，H_SA 与 dynamic state 对截止、迟到和网络
  backlog 有条件性改善，P1D1 截止成功为 56,872；
- 南宁 1x 四格均完成，H_SA 的平均主效应为 mean `-8.17925 s`、P95
  `-23.273 s`、P99 `-24.5542 s`、max `-65.4285 s`；
- 南宁 2x 的 H_FF/off 只完成 47,864，而其余三格完成 57,012，说明静态
  服务引导和动态状态在该已知拓扑高负载下存在替代/交互，不能拆成普适
  独立加法收益。

CIE-DH adaptation 的可发表结论：H_SA 在 map2 近乎中性，在南宁 1x
降低 mean/P95/P99 但提高 max，在南宁 2x 比 H_FF 少完成 120 件。该结果
证明 common-executor service-aware adaptation 会改变基线表现，也说明它
不能独立检验本文 H_SA 贡献；它不是 native Feng DH。

证据：`outputs/reports/cie_potential_factorial_report.md`，
`outputs/tables/cie_potential_factorial.csv`，
`outputs/tables/cie_potential_factorial_effects.csv`。

### C7. 十格激活普查与稳定 1x 消融

状态：`RETAIN_AS_ACTIVATION_AND_CONDITIONAL_EVIDENCE`。

可发表主张：10 个 map-load 格显示 Q、I、successor-service wait、strict
descent、J2/M3 与 E2 在不同程度上激活；corridor-wait counterfactual 在
当前定义下未激活；P2 全部 dormant。Nanning 的 Q/I 动作改变明显高于
map2，支持拓扑依赖，而不是所有组件普适有效。

J2/M3 的 `PRE_COMMIT_ORDER_MUTATION` 率以 multi-candidate opportunity
为分母：map2 2x 为 `1,361/2,404 = 56.6140%`，南宁 2x 为
`15/66 = 22.7273%`。exact-slot overlap 分别为 1,465/5，单列且不作
分母；mutation 全部为 `final_action=False`，只能证明提交前排序变化，
不能写成最终动作改变或业务收益。

该普查没有保存决策值分位数、组件相关性或真实热点分布；这些补充诊断均
记为 `NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`。现有计数已足以停止零机会
方向并选择最小专项，缺失诊断不构成为相同结论重跑全矩阵的理由。

稳定 1x 删除实验的正确结论：Q 和 successor-service wait 没有形成双图
净收益；I 的方向随拓扑改变；strict descent removal 两图结果完全相同；
J2/M3 到 neutral FIFO 的联合替换在 Nanning 相同、map2 略好；简单
service-rate normalization 方向混合。停止继续为这些负方向增加 scorer、
guard、参数或模式。

最终 fixed-fault strict-descent 专项由 4 个同 cohort 单变量配对组成。map2
`single_4/pair_2_4` 与南宁 `pair_3_5` 的完成、准点、missed 与固定时域迟到
没有业务变化；只有南宁 `single_3` 受益：完成 `28,491 -> 28,506`，准点
`25,617 -> 26,018`，missed `2,889 -> 2,488`，固定时域迟到总量下降
`31.145%`，校正后 backlog area 从 `100,322,141.572` 降至
`95,914,523.385 bag-s`（`-4.393465%`），单件最大决策数由 `512` 降至
`53`。因此 strict descent 是有激活、在一个南宁故障格有实质收益的局部
机制，不是跨地图通用增益。该配对的 OFF 臂未完成全人口，故配对
mean/P95/P99/max 为 N/M；不得用 ON 臂或幸存者时延代替配对效应。

证据：`outputs/reports/cie_component_activation_audit.md`，
`outputs/reports/cie_ablation_report.md`，
`outputs/reports/cie_specialty_mechanism_audit.md`。

### C8. 八格服务压力增强控制

状态：`RETAIN_AS_H_POTENTIAL_SERVICE_PRESSURE_CONTROL_ONLY`。

可发表主张：服务压力增强控制共有 8 个 map/cell 运行，运行状态均为
`COMPLETE`，其中 7 个具备完整人口时延。该控制保持 topology、tasks 和
release 不变，仅将非终点服务时间乘以 2。map2 四格均完成；H_SA 的平均主效应为 mean
`-87.1861 s`，并改善平均截止成功。Nanning H_FF/off 只完成 24,107，
而 H_SA/off、H_FF/full、H_SA/full 均完成 28,506；该控制说明服务引导与
动态状态在服务压力增强条件下具有实质交互。

必须说明：这 8 格全部仍使用 `raw_count_as_seconds`，比较的是 H_FF/H_SA
和 dynamic off/full，不是 `RAW_COUNT_AS_SECONDS`、
`SERVICE_RATE_NORMALIZED`、`NO_QI_BUT_CALENDAR` 三臂归一化实验。

证据：`outputs/reports/cie_service_heterogeneity_control.md`，
`outputs/tables/cie_service_heterogeneity_factorial.csv`。

#### C8.1 三臂服务率专项

状态：`MIXED_NO_GENERAL_GAIN_STOP`。

正式专项的 12 个运行（两图 × `REAL_SERVICE/SERVICE_X2` × 三臂）均正常
结束，4/4 matched groups 通过同 commit、同加载二进制、同地图工作负载、
topology/tasks/release 与 reference-request 身份门。`SERVICE_X2` 是仍使用
1x 人口的服务压力增强条件，不是 2x 工作负载。

`SERVICE_RATE_NORMALIZED` 相对 `RAW_COUNT_AS_SECONDS` 在 map2 实际服务下
完成量与 mean/P95/P99/max 完全相同；在 map2 服务压力增强下分别改善
`24.852%/38.658%/32.086%/30.068%`，missed 由 `135` 降至 `31`。但在
南宁实际服务下 mean/P95/P99/max 分别恶化
`3.432%/5.341%/4.970%/6.354%`，missed 由 `111` 增至 `285`；在南宁
服务压力增强下只完成 `28,505/28,506`，全人口时延为 N/M，且固定时域
迟到 mean/P99 分别恶化 `1.342%/1.469%`。`NO_QI_BUT_CALENDAR` 也在两图
与两种服务条件间出现均值、尾部、准点和迟到方向冲突，未形成可复用信号。

结论：归一化与 No-Q/I 两个方向均停止，不新增 scorer、guard 或参数。
不完整人口时延保持 N/M，全部比较均未使用 survivor/common-cohort timing。

证据：`outputs/reports/cie_service_normalization_report.md`，
`outputs/tables/cie_service_normalization_summary.csv`。

### C9. P2 bounded-local buffer

状态：`DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`。

当前 G31 `local_queue_capacity=0` 表示未配置有限容量；十个激活格中 P2
applicability、activation、prepare、validate、commit、rollback 全为零。
地图和恢复 Java 代码没有提供可作为全节点物理容量的权威值。P2 只能
作为已实现设计/未来工作，不得进入摘要性能贡献。

证据：`outputs/reports/cie_specialty_mechanism_audit.md`，
`outputs/reports/g4irsf12_buffer_semantics_boundary.md`。

### C10. E2 event hotpath

状态：`COMPUTE_ONLY_ROLE`。

当前协议 1× E0/E2 v2 专项在 map2 与南宁均通过
`COMPLETE_STRICT_PHYSICAL_EQUIVALENCE`：逐 segment terminal state、
admission/release/completion time（绝对容差 1e-9 s）以及完整未截断 move/hold
物理序列一致。事件数分别由 `4,752,689 -> 3,997,648`（`-15.8866%`）和
`8,645,838 -> 7,087,605`（`-18.0229%`）。wall/CPU/进程生命周期 RSS 是带
完整 trace 的单次实现描述，不是方差控制的生产速度主张；`event_queue_peak`
未暴露并保持 N/M。允许表述仅为“严格物理等价下的 compute-only 事件削减”，
不得写成物理容量、路由质量或跨协议性能收益。

证据：`outputs/reports/cie_e2_equivalence_report.md`，
`outputs/tables/cie_e2_equivalence.csv`。

### C11. 固定故障与单变量 surviving-graph 势证据

状态：`PURE_POTENTIAL_3_OF_4_BENEFIT_1_TIE`。

可发表主张：G31 完整系统在两张已知拓扑、固定起始（启动前登记）且持续整个时域的
故障矩阵中表现稳健。故障格汇总为 Nanning 1x 13W/3T/0L、Nanning 2x
16W/0T/0L、map2 1x 6W/9T/0L、map2 2x 13W/2T/0L。

新增的 4 个纯势配对均固定 28,506 件原始人口、同 commit/二进制/工作负载/
release/reference request 和同一 native admission cohort；两臂共同使用
surviving graph 与相同 rejected/unreachable recognition，唯一请求差异是
是否提供 surviving-graph service-aware DLP artifact。相对
`EDGE_FILTER_ONLY`，DLP 在以下 3/4 场景产生实质改善：

- map2 `single_4`：完成 `10,248 -> 28,506`，missed `18,258 -> 0`，
  固定时域迟到下降 `100%`，校正后 backlog area 从
  `1,015,984,862.650` 降至 `70,452,656.819 bag-s`（`-93.065580%`）；
- map2 `pair_2_4`：完成 `5,453 -> 22,113`，missed
  `23,053 -> 6,393`，迟到下降 `71.333%`，校正后 backlog area 从
  `1,287,277,282.706` 降至 `419,703,509.738 bag-s`（`-67.396029%`）；
- 南宁 `single_3`：完成 `17,559 -> 28,506`，准点
  `17,538 -> 26,018`，missed `10,968 -> 2,488`，迟到下降 `98.357%`，
  校正后 backlog area 从 `643,431,201.021` 降至
  `95,914,523.385 bag-s`（`-85.093274%`）；
- 南宁 `pair_3_5` 两臂均完成 `12,186`、missed `16,320`，业务结果持平。

只有完整 1x 全人口才报告时延：DLP 在 map2 `single_4` 的
mean/P95/P99/max 为 `268.620/386.748/454.094/566.264 s`，在南宁
`single_3` 为 `1,500.531/8,308.623/10,516.194/17,068.734 s`。对应
edge-filter-only 基线未完成全人口，因此配对时延差为 N/M；pair 故障中的
source-unreachable 行李也不转成 survivor timing。

允许外推到的范围仅是：对这 4 个预先固定、启动前即存在并持续整个时域的
故障，纯 DLP 在 3 格改善、1 格持平。它不证明动态故障检测、通知、repair
或恢复，也不保证所有故障组合都受益。

证据：`outputs/reports/g4irsf31_reporting.md`，
`outputs/reports/cie_fault_specials.md`，
`outputs/tables/cie_fault_specials.csv`，
`outputs/reports/cie_specialty_mechanism_audit.md`。

### C12. 计算可扩展性与负候选

状态：`RETAIN_AS_DESCRIPTIVE_COMPUTE_EVIDENCE`。

S5 global oracle 在南宁 2x 只完成 47,058/57,012，wall/cpu 为
13,386.460/13,034.016 s，并执行 8,403,557 次 runtime full-A* 和
4,593,068 次全局 scorer 扫描；它是 NO-GO 诊断，不是论文候选。G31
对应格完成全人口且不依赖该全局 oracle。

所有 wall/CPU 数值是单次实现诊断；不同语言/执行器的墙钟差不能解释为
纯算法复杂度或统计显著排名。缺少 neighbor message/payload 字段时不得
虚构通信开销。

证据：`outputs/reports/cie_baseline_comparison.md`。

### C13. 安全性

状态：`PARTIALLY_SUPPORTED`。

当前进入主表的产物通过各自已实现的 execution-integrity、人口、事件
预算、reservation conflict 和 aggregate 身份门；没有已报告的非零违规。
但部分结果没有逐项给出全部七个目标安全字段。允许写“已报告安全门
通过”，禁止写“完成形式化安全认证”或把未报告字段补零。

`outputs/tables/cie_safety_audit.csv` 是旧 G35 产物，只可作为历史背景，
不得作为本轮 targeted/random/E2 的安全依据。

### C14. 冻结 paired random robustness

状态：`COMPLETE_FROZEN_PAIRED_SEEDS`。

已提交 runner 按 frozen manifest 完成五个非故障场景：map2
`1.00/1.75/2.00×` 与南宁 `1.00/2.00×`，每格固定 10 个 paired seeds，
两臂共享 arrival `uniform[-5,5] s` 与 node-service `lognormal(sigma=0.05)`
realization；共 100/100 artifacts，失败 seed 率均为 0，置信区间使用 10,000
次 paired bootstrap。

P1D1 相对 P0D0 的主要正式结果为：map2 1× mean/P95/P99/max 分别变化
`-1.103/-3.044/-11.430/-16.983 s`，95% CI 均不跨 0；南宁 1×分别为
`-12.493/-40.845/-49.875/-134.065 s`，95% CI 也均不跨 0。map2 1.75×
平均准点增加 `119.5`（CI `[76.4,163.802]`），校正 backlog area 减少
`3.396e6 bag-s`（CI `[-4.031e6,-2.851e6]`）；map2 2×平均准点增加
`1,264.9`（CI `[937.397,1,592.5]`），校正 backlog area 减少
`9.548e6 bag-s`（CI `[-10.894e6,-8.221e6]`）。南宁 2×平均完成增加
`9,310.2`（CI `[8,717.765,9,811.305]`），校正 backlog area 减少
`307.161e6 bag-s`（CI `[-339.858e6,-274.747e6]`），但 tardiness max
增加 `2,555.1 s`（CI `[1,027.275,4,083.657]`），必须保留这一尾部代价。

所有正式 2× THT 仍为 N/A。该矩阵只估计 P1D1-P0D0 联合对比，
potential×dynamic 为 `INTERACTION_NOT_ESTIMATED`；随机 fault 因无法同时
保持 cohort 与隔离处理而记为
`BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE`，不伪造故障置信区间。

证据：`outputs/reports/cie_random_robustness_report.md`，
`outputs/tables/cie_random_robustness_summary.csv`，
`configs/eval/cie_revision_manifest.yaml`，
`scripts/eval/run_cie_random_robustness.py`。

## 4. 最终专项封口

- J2/M3 精确单变量对照：`BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT`；
  保留 activation-only 诊断，不新增模式绕过合同。
- E2：`COMPUTE_ONLY_ROLE`，双图 1× 完整物理轨迹等价通过。
- Paired random robustness：`COMPLETE_FROZEN_PAIRED_SEEDS`，五场景均为
  10/10 有效配对且失败率 0。
- P2 local buffer：`DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`。
- native HCA 机制计数器：
  `BLOCKED_NATIVE_HCA_MECHANISM_COUNTERS_NOT_INSTRUMENTED`。
- 激活分位数/相关/热点：`NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`。

## 5. 最终主贡献口径

建议最终压缩为三项，不把每个内部开关包装成独立创新：

1. 面向异步有向服务网络的一跳去中心化路由与目的资源局部授权架构；
2. 由服务感知静态引导、局部动态状态和固定故障存活结构组成的在线
   决策机制，并通过析因与激活证据说明各部分的条件性作用；
3. 以固定分母容量、完整人口同释放时延、截止/迟到/积压以及明确
   P0/P1/P2 边界为核心的两张已知拓扑评价方法。

J2/M3 保留 activation-only 且精确对照被合同耦合阻断；E2 的最终角色为
compute-only。冻结 paired random 在五个场景支持 P1D1 联合对比的稳健性，
但不估计 potential×dynamic 交互。Strict descent 只在
南宁 `single_3` 显示局部故障收益，纯 DLP 在固定故障 3/4 格实质改善、
1/4 格持平，服务归一化与 No-Q/I 已按混合结果停止。P2 已单独固定为
dormant，不是待回填 targeted 项；不得把这些机制统一写成跨地图通用的
独立实质性能贡献。
