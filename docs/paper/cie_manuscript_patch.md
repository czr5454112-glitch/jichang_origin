# CIE 稿件可直接替换文本

状态：最终写作证据已封口；J2/M3 精确对照明确阻断，E2 v2 与 paired
random robustness 已由最终聚合回填，不再保留证据占位符。

本文件用于人工替换外部论文相应章节，不直接修改外部 Word。下面文本可
直接使用。最终排版时应将
仓库路径改为论文表/图编号，但不得改变协议边界或补写缺失值。

## 摘要（替换稿）

机场行李输送是具有异步释放、有限服务能力、合流竞争和线路中断的有向
服务网络。集中式全路径预约能够显式处理时空冲突，但在大规模持续任务流
中易受到全局搜索、预约维护和重规划开销的限制。本文提出 G31/S4：一种
一跳去中心化的事件驱动路由方法。每个转向点仅在当前合法出口中选择下一
跳，通过服务感知静态势、局部队列与计划流入状态、直接邻居服务日历和
目的资源局部授权协调行李流；运行时不生成完整未来路线，也不维护 HCA
式全局预约表。

实验在 map2 与南宁两张已知拓扑上，使用原始 28,506 件人口及其 2x
57,012 件扩展进行。原论文正式 1x 科目采用相同 HCA segment release 和
完整人口统计：相对 HCA，G31 的 mean/P95/P99/max 在 map2 分别降低
11.532%/17.599%/23.479%/27.101%，在南宁分别降低
24.365%/27.207%/29.495%/71.494%。在 2x 固定时域中，G31 在两图均
完成 57,012/57,012，HCA 在 map2 和南宁分别完成 56,917 和 39,063；
由于 HCA 未覆盖完整 2x 人口，所有正式 2× THT 均保持 N/A，改以完成量、
截止成功、迟到、time-to-X 和积压描述业务结果。完整实验包含 78 个预先
设定的确定性场景配置，而不是 78 次独立随机试验；7 个完整人口 1x
map-speed 场景产生的 35 项相关分布指标中，G31 有 31 项较低、4 项处于
物理时间分辨率平局，不能解释为 31 次独立胜利。

为区分历史复现、路线机制和完整系统能力，本文采用 P0/P1/P2 三层协议。
恢复的 Feng Java HCA 通过冻结聚合回归，但现有源码缺少 native CIE-DH
所需的位置级 moving/stopped、BTI/DDI 和 HOLD 状态，因此 native CIE-DH
记为 N/A；公共执行器中的 CIE-DH 与 Tarău-2010 均明确标为 adaptation。
24 格势函数×动态状态析因、10 格激活普查和 8 格服务压力增强控制表明，服务
感知静态引导在南宁及高服务压力条件下作用更明显。进一步的固定故障同
cohort 单变量实验显示，surviving-graph service-aware DLP 在 4 个场景中
3 个实质改善、1 个持平；strict descent 只在南宁 `single_3` 受益；服务率
归一化与 No-Q/I 均因跨图/跨服务条件方向混合而停止。P2 在正式配置中零
触发并归类为 `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`；E2 v2 在双图
1× 完整物理轨迹等价下将事件数降低 15.8866%/18.0229%，因此只承担
compute-only 角色。五场景 paired random campaign 的 100/100 artifacts
全部通过身份与完整性门；它支持 P1D1-P0D0 联合对比的扰动稳健性，但不
估计 potential×dynamic 交互。结果支持
G31 在两张已知拓扑上的跨图性能与工程可解释性，但不构成未知地图泛化、
动态故障恢复或每个内部组件均独立产生实质收益的主张。

## 主要贡献（替换稿）

本文的贡献归纳为三项。

1. 提出面向异步有向服务网络的一跳去中心化路由与目的资源局部授权
   架构。控制器只读取当前节点、合法直接候选及受限局部状态，在
   `O(outdegree)` 决策边界内完成下一跳选择，不调用运行时完整 A*，不
   物化行李的未来完整路线，也不维护全局预约表。
2. 构造由服务感知静态势、局部动态状态和固定故障存活结构组成的在线
   决策机制，并通过 24 格势函数×动态状态析因、10 格激活普查、服务
   压力增强控制和固定故障单变量对照区分主效应、交互、拓扑依赖与
   dormant 状态。本文不将 J2/M3、strict descent、P2 或 E2 一律包装为
   独立性能贡献。
3. 建立分离 P0 历史复现、P1 公共执行器路线隔离和 P2 完整系统比较的
   评价方法，以固定分母容量、完整人口同释放时延、截止/迟到/time-to-X/
   积压和计算开销为互补科目，在 map2 与南宁两张已知拓扑上验证结果，
   并对未完成全人口、协议不可恢复和未报告字段保持 N/A。

## 4.8 基线、协议与正式性能比较（替换稿）

### 4.8.1 P0/P1/P2 比较边界

为避免把执行器差异误当作 scorer 因果效应，我们将基线分为三个协议。
P0 在 Feng 原生 Java 环境中检验历史复现；P1 在公共 C++ 事件执行器、
同一任务人口和 neutral FIFO 下隔离下一跳策略；P2 比较 HCA 与 G31 各自
原生完整系统的端到端业务结果。三个协议独立解释，不传递排序。

P0 审计恢复了 15 个 Java 源文件及 HCA 调用链
`Tasks.generate_tasks -> ICS_PathFinding.ICS_path_finding -> Astar.research`。
Feng-native HCA 完成 43,603/43,603 segments 和 28,506/28,506 raw bags，
processed-attempt min/mean/max 为 3.133333/3.945169/5.950000 min，与冻结
聚合结果精确一致。该审计没有比较逐任务 route/completion trace，因此只
称为冻结聚合回归。恢复源码中不存在足以忠实重建 native CIE-DH 的
moving/stopped、BTI、DDI、HOLD 与 0.2 s 位置级状态；相应单元格报告为
`N/A (BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED)`，不使用公共执行器
adaptation 代填。

Feng-native HCA 同样没有本轮局部机制的原生计数器，故其机制计数字段为
`BLOCKED_NATIVE_HCA_MECHANISM_COUNTERS_NOT_INSTRUMENTED`，不能把 G31/C++
计数投射到 HCA。

P1 中的 `CIE_DH_COMMON_EXECUTOR_FREE_FLOW`、
`CIE_DH_COMMON_EXECUTOR_SERVICE_AWARE` 和
`TARAU_DISTRIBUTED_2010_COMMON_EXECUTOR_ADAPTED` 均为公开差异的适配
基线，不代表 Feng-native exact reproduction。修复版 Tarău 对照只读取
当前候选及其真实一跳后继的事件驱动 queue beacon，不读取 G31 的
scheduled incoming、service calendar、strict descent 或全局未来任务。

### 4.8.2 P2 原论文正式科目

固定时域容量结果如下。1x 两种方法均达到完成天花板，差异主要由完整
人口时延体现；2x 仅比较容量与业务指标。

| 方法 | map2 1x | map2 2x | 南宁 1x | 南宁 2x |
|---|---:|---:|---:|---:|
| HCA native | 28,506/28,506 | 56,917/57,012 | 28,506/28,506 | 39,063/57,012 |
| G31/S4 native | 28,506/28,506 | 57,012/57,012 | 28,506/28,506 | 57,012/57,012 |

1x 正式时延使用相同 HCA segment release、完整 28,506 件人口且不使用
survivor/common cohort。

| 拓扑 | 方法 | min | mean | P95 | P99 | max |
|---|---|---:|---:|---:|---:|---:|
| map2 | HCA native | 188.000 | 238.000 | 300.000 | 332.000 | 383.000 |
| map2 | G31/S4 native | 188.001 | 210.553 | 247.202 | 254.049 | 279.202 |
| 南宁 | HCA native | 49.000 | 374.080 | 653.000 | 785.000 | 2,851.000 |
| 南宁 | G31/S4 native | 48.401 | 282.934 | 475.339 | 553.466 | 812.698 |

约 1 ms 的最小值差异属于物理/计时分辨率，不作胜负解释。map2 2x 的
HCA 少完成 95 件；南宁 2x 的 HCA 只完成 39,063/57,012，且其释放也未
覆盖完整 2x segment 人口。因此所有方法的正式 2× THT 一律为 N/A，不能
用 G31 自有 release timing 或 HCA survivor timing 补齐。

78 个场景是稳定与固定线路中断、两张拓扑、两个负载及固定速度组合形成
的确定性配置，不是独立随机重复。跨这些互斥配置求和得到的 905,002 只是
完成数差值的描述性代数和，同一人口在不同配置中重复出现，本文不再把它
写入摘要或解释为累计多运输的真实行李数。7 个完整人口 1x map-speed 格
中的 35 项相关 min/mean/P95/P99/max 指标里，G31 有 31 项较低、4 项为
物理分辨率平局；它们共享人口和场景，也不构成独立胜率。

### 4.8.3 P1 adapted baseline 结果

在修复版 G31/Tarău 同二进制 neutral-FIFO cohort 中，map2 2x 两者都
完成 57,012，但 Tarău 截止成功 57,012、G31 为 56,872；该 Tarău 正结果
必须保留。南宁 2x G31 完成 57,012，Tarău 完成 47,707，差 9,305 件；
截止成功分别为 20,963 和 20,767。1x 完整人口同释放时延中，G31 的
mean/P95/P99/max 在两图均低于 Tarău：map2 的相对降幅为
0.332%/0.242%/3.053%/6.707%，南宁为
3.905%/7.246%/7.516%/13.225%。

在另一冻结 CIE-DH adaptation cohort 中，CIE-DH 在南宁 1x 的部分时延
略优于同 cohort G31，但南宁 2x 只完成 49,038/57,012；map2 2x 的
CIE-DH 截止成功则比 G31 多 140 件。不同二进制/适配谱系不合并排序。
因此 P1 支持拓扑与负载相关的权衡，而不是 G31 对所有 adapted baseline
的每格严格支配。

## 4.9 析因、激活与专项机制证据（替换稿）

### 4.9.1 势函数×动态状态的 24 格分解

我们在 neutral FIFO 公共执行器中预先固定 `H_FF/H_SA × dynamic
off/full`，形成 16 个 S4 格；另用 8 个 CIE-DH common-executor 格检验
将 H_FF 替换为 H_SA 对 adapted baseline 的影响。24 个运行均正常结束，
其中 12 个满足正式完整人口时延条件。2x 时延不因候选自身完成而升级，
仍保持 N/A。

S4 四格的关键结果如下；1x 行报告完整人口 mean，2x 行报告固定时域完成
量和截止成功。

| 拓扑/负载 | 指标 | H_FF/off | H_SA/off | H_FF/full | H_SA/full |
|---|---|---:|---:|---:|---:|
| map2 1x | mean THT (s) | 211.249 | 210.767 | 211.026 | 210.546 |
| map2 2x | completed | 57,012 | 57,012 | 57,012 | 57,012 |
| map2 2x | on-time | 55,641 | 56,186 | 55,849 | 56,872 |
| 南宁 1x | mean THT (s) | 293.479 | 281.724 | 287.536 | 282.933 |
| 南宁 2x | completed | 47,864 | 57,012 | 57,012 | 57,012 |
| 南宁 2x | on-time | 20,482 | 20,334 | 20,910 | 20,963 |

在 map2 1x，H_SA 的平均主效应为 mean `-0.480827 s`、P95 `-0.5 s`、
P99 `-4.8 s`、max `-10.0 s`；在南宁 1x，相应主效应扩大为 mean
`-8.17925 s`、P95 `-23.273 s`、P99 `-24.5542 s`、max
`-65.4285 s`。南宁 2x 中 H_FF/off 未完成全人口，而 H_SA/off 与两个
dynamic-full 格完成全人口，说明 H_SA 与局部动态状态具有替代和交互，
不能把各项效应写成在所有拓扑上可相加的独立增益。

CIE-DH adaptation 分解进一步显示，将 H_FF 换成 H_SA 在 map2 1x 对
mean 的影响仅 `+0.003736 s`，而在南宁 1x 将 mean/P95/P99 分别降低
`6.556/14.714/15.928 s`，同时 max 增加 `85.416 s`；南宁 2x 的完成量
从 49,158 降至 49,038。服务感知底座会实质改变 adapted baseline，且
结果方向混合。因此 common-executor service-aware CIE-DH 只能用于 P1
adaptation 分解，不能作为 Feng-native 复现或 H_SA 的独立外部验证。

### 4.9.2 十格激活普查

激活普查覆盖 map2 与南宁的 1.00/1.25/1.50/1.75/2.00x 十格。Q、I 和
successor-service wait 在两图均产生 raw-argmin action changes，但强度
明显不同：Q 从 map2 1x/2x 的 74/798 次增至南宁的 19,626/210,337 次；
I 为 879/4,630 对 57,674/119,980；successor-service wait 为 169/649
对 4,491/13,791。corridor-wait 在当前实现与状态下为零激活。这些计数是
同状态、可行性判断前的 counterfactual argmin 诊断，不是最终动作或业务
收益。

strict descent 在 map2 1x/2x 分别过滤 196,311/463,573 个决策，在南宁
为 467,695/1,502,461，且 empty ranking 均为零。J2/M3 在 map2 1x/2x
记录 296/1,361 次 `PRE_COMMIT_ORDER_MUTATION`，在南宁为 11/15。该比率
以 multi-candidate opportunity 为分母；map2 2x 为
`1,361/2,404 = 56.6140%`，南宁 2x 为 `15/66 = 22.7273%`。exact-slot
overlap 分别为 1,465/5，单列且不作分母；所有 mutation 均为
`final_action=False`，不能解释成最终动作改变。E2 在四个端点格分别抑制
755,041、1,663,742、1,558,233 和 3,740,711 个事件。
P2 在全部十格的 applicability、activation、prepare、validate、commit、
rollback 都为零，故正式归类为 dormant。

激活普查没有保存决策值分位数、组件相关性或真实热点分布；这些字段统一
写为 `NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`。现有计数已足以支持停止
零机会方向，不为补齐机械诊断而重跑。

### 4.9.3 稳定 1x 删除实验

9 个配置×两张地图的稳定 1x 同释放实验给出的是条件性和负证据。Q 与
successor-service wait 没有跨图一致净收益；删除 I 后 map2 变差、南宁
反而改善，显示拓扑依赖；删除 strict descent 后两图的 completion、
mean/P95/P99/max、event 和 decision 完全不变；将 J2/M3 联合换成 neutral
FIFO 后南宁不变、map2 mean 仅改善 0.007411 s，因此不能给 J2 或 M3
分配正向因果收益。简单 service-rate normalization 在 map2 完全相同，
在南宁使 mean/P95 增加 0.912388/2.00025 s，同时使 P99/max 减少
0.50985/3.87 s，并增加 85,534 个事件；该方向混合，不支持通用改善。

这些结果构成停止规则：若一个机制没有新的明确瓶颈和可归因的双图收益，
不继续叠加 scorer、guard、模式名、排序条件或参数。

### 4.9.4 服务压力增强控制

服务压力增强控制保持 topology、tasks 和 release 不变，仅将非终点服务时间
乘以 2。8 个 map/cell 运行均为 `COMPLETE`，其中 7 个满足完整人口时延。map2
四格均完成 28,506，H_SA 的平均主效应为 mean `-87.1861 s`；南宁的
H_FF/off 只完成 24,107，而 H_SA/off、H_FF/full 和 H_SA/full 都完成
28,506。该结果支持“服务感知势与动态状态在服务压力增强时发生实质交互”。

这 8 格仍全部使用 `raw_count_as_seconds`，不是服务率归一化专项。不得把
它们写成 `RAW_COUNT_AS_SECONDS`、`SERVICE_RATE_NORMALIZED` 与
`NO_QI_BUT_CALENDAR` 三臂结果，也不得据此声称 Q/I 与服务日历的重复
计量已经被识别。

### 4.9.5 Strict descent 与纯故障 DLP 专项

Strict-descent 专项在 map2 `single_4/pair_2_4` 和南宁
`single_3/pair_3_5` 上各做 OFF/ON 单变量配对。四组均保持同 commit、
加载二进制、工作负载、release、reference request 与 native admission
cohort。map2 两组和南宁 `pair_3_5` 的完成、准点、missed 与固定时域迟到
不变；仅南宁 `single_3` 受益：完成 `28,491 -> 28,506`，准点
`25,617 -> 26,018`，missed `2,889 -> 2,488`，固定时域迟到总量下降
`31.145%`，校正后 backlog area 从 `100,322,141.572` 降至
`95,914,523.385 bag-s`（`-4.393465%`），单件最大决策数由 `512` 降至
`53`。因此 strict descent 是局部有益、非跨地图通用的故障机制。

纯势专项的两臂共同使用 surviving graph、相同 rejected/unreachable
recognition 和相同 native admission cohort，唯一请求差异是是否提供
surviving-graph service-aware DLP artifact。结果为：

| 拓扑/场景 | 完成（edge filter -> DLP） | missed | 固定时域迟到变化 | backlog area 变化 |
|---|---:|---:|---:|---:|
| map2 `single_4` | 10,248 -> 28,506 | 18,258 -> 0 | -100.000% | -93.065580% |
| map2 `pair_2_4` | 5,453 -> 22,113 | 23,053 -> 6,393 | -71.333% | -67.396029% |
| 南宁 `single_3` | 17,559 -> 28,506 | 10,968 -> 2,488 | -98.357% | -85.093274% |
| 南宁 `pair_3_5` | 12,186 -> 12,186 | 16,320 -> 16,320 | 0.000% | 0.000% |

backlog 百分比来自固定时域校正视图；对应前三格的校正面积分别为
`1,015,984,862.650 -> 70,452,656.819`、
`1,287,277,282.706 -> 419,703,509.738` 和
`643,431,201.021 -> 95,914,523.385 bag-s`，不得引用 legacy last-event
百分比。

因此纯 DLP 在 3/4 场景产生实质改善，在 source-unreachable 主导的南宁
`pair_3_5` 持平。只有完整 1x 全人口才报告时延：DLP 的 map2
`single_4` mean/P95/P99/max 为 `268.620/386.748/454.094/566.264 s`，
南宁 `single_3` 为
`1,500.531/8,308.623/10,516.194/17,068.734 s`。相应 edge-filter 基线
未完成全人口，故配对时延差保持 N/M；所有不完整格均未使用 survivor 或
common-cohort timing。该证据只适用于预先固定、启动前即存在并持续整个
时域的线路中断，不支持动态检测、通知、repair 或恢复主张。

### 4.9.6 服务率归一化与 No-Q/I 专项

三臂专项包含两图 × `REAL_SERVICE/SERVICE_X2` ×
`RAW_COUNT_AS_SECONDS/SERVICE_RATE_NORMALIZED/NO_QI_BUT_CALENDAR` 共 12 个
运行，均正常结束，4/4 matched groups 通过身份与完整性门。`SERVICE_X2`
仍使用 1x 人口，只增强服务压力，不是 2x 工作负载。

相对 raw，归一化在 map2 实际服务下运输指标完全相同；在 map2 服务压力
增强下 mean/P95/P99/max 分别改善
`24.852%/38.658%/32.086%/30.068%`，missed `135 -> 31`。但在南宁实际
服务下上述四项分别恶化 `3.432%/5.341%/4.970%/6.354%`，missed
`111 -> 285`；南宁服务压力增强下归一化只完成 `28,505/28,506`，所以
全人口时延 N/M，固定时域迟到 mean/P99 仍恶化 `1.342%/1.469%`。

No-Q/I 也没有一致方向：map2 实际服务的 mean/P95/P99/max 全部恶化；
南宁实际服务的 mean/P95/P99 改善但 max 恶化；两个服务压力增强格在
准点、迟到均值和尾部之间继续出现冲突。由此归一化与 No-Q/I 均按停止
规则关闭，不增加新 scorer、guard、参数或模式。不完整人口时延保持 N/M，
未使用 survivor/common-cohort timing。

### 4.9.7 J2、E2 与冻结随机稳健性封口

J2/M3 当前接口把 merge rule 与 timing contract 一起改变，无法在不新增
模式的条件下形成 exact single-variable contrast，因此最终状态为
`BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT`。本文保留以 multi-candidate
opportunity 为分母的 activation-only 诊断，不把历史 G18 或 coupled FIFO
对照写成当前双图 J2 因果收益，也不再为该失败方向增加模式。

E2 v2 在 map2 与南宁当前 G31 1× 协议中均通过完整物理轨迹等价：逐 segment
terminal state、release/admission/completion time（1e-9 s 容差）和完整未截断
move/hold 序列一致。事件数由 `4,752,689 -> 3,997,648`（`-15.8866%`）和
`8,645,838 -> 7,087,605`（`-18.0229%`），故 E2 定位为
`COMPUTE_ONLY_ROLE`。`event_queue_peak` 仍为 N/M，wall/CPU/RSS 只作带完整
trace 的单次实现描述；该结果不表示物理容量或路由质量提高。

冻结 paired random campaign 使用 committed runner、manifest 固定的十个
seeds、arrival `uniform[-5,5] s` 与 node-service
`lognormal(sigma=0.05)`，两臂对每个 seed 使用完全相同的扰动 realization。
map2 1.00/1.75/2.00× 与南宁 1.00/2.00× 共 100/100 artifacts，五场景均
10/10 有效配对、失败率 0；95% CI 来自 10,000 次 paired bootstrap。

map2 1× 的 mean/P95/P99/max 变化为
`-1.103/-3.044/-11.430/-16.983 s`，南宁 1×为
`-12.493/-40.845/-49.875/-134.065 s`，各自 95% CI 均不跨 0。map2
1.75× 的校正 backlog area 减少 `3.396e6 bag-s`，map2 2×平均准点增加
`1,264.9`、校正 backlog 减少 `9.548e6 bag-s`。南宁 2×平均完成增加
`9,310.2`（CI `[8,717.765,9,811.305]`）、校正 backlog 减少
`307.161e6 bag-s`（CI `[-339.858e6,-274.747e6]`），但最大迟到增加
`2,555.1 s`（CI `[1,027.275,4,083.657]`）；因此不能写成所有尾部科目均
改善。所有正式 2× THT 仍为 N/A。

该随机矩阵只估计 P1D1-P0D0 联合对比，potential×dynamic 为
`INTERACTION_NOT_ESTIMATED`。随机 fault 因 cohort 与 treatment 无法同时
隔离而记为 `BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE`。P2 local buffer
最终为 `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`。

## 讨论（替换稿）

### 性能提升来自系统组合，而非模块数量

G31 在原论文正式科目上的主要优势表现为：1x 完整人口时延尾部明显收缩，
2x 固定时域完成量尤其在南宁明显提高。势函数析因表明，H_SA 在 map2
1x 的平均作用较小，在南宁和服务压力增强条件下作用明显；固定故障纯 DLP
对照又在 3/4 场景产生实质完成、迟到与 backlog 改善。与此同时，strict
descent 只在南宁 `single_3` 有局部收益，服务归一化与 No-Q/I 没有跨图、
跨服务条件的一致改善。稳定消融也不支持把 Q、I、successor-service wait
和 J2/M3 全部写成独立增益。更准确的解释是：G31 是一个在两张已知拓扑
上稳健的简单组合，各组件承担路径引导、拥堵响应、公平/安全或计算职责，
并非每项都降低 mean。

### 固定分母优先于幸存者时延

高负载下，未完成任务本身就是业务结果。只对已完成子集统计 THT 会奖励
拒绝困难任务的方法。因此本文优先报告 28,506/57,012 固定分母完成量、
截止成功、全人口迟到下界、time-to-90/95/99%、源端/网络内积压和 backlog
area。只有共同释放且完整完成人口时才报告 mean/P95/P99/max。该规则使
南宁 2x 的差异可见，同时防止用 survivor timing 制造性能胜利。

### 基线身份决定结论含义

P0 HCA 回归说明恢复的原生 Java 调度器仍可复核，但不能填补 native
CIE-DH 的缺失状态机。P1 common-executor CIE-DH 和 Tarău-2010 的价值
在于提供透明、可执行的适配比较，而不是恢复历史原义。尤其是 CIE-DH
H_FF/H_SA 分解显示，服务感知势会改变基线表现；若不分谱系，本文的机制
会被提前赠送给基线。P2 的 HCA-G31 差距则是完整系统差距，不能反向拆解
为单一 scorer 的因果贡献。

### 已知拓扑可移植性而非未知地图泛化

map2 的正服务时间基本同质，南宁具有更多节点、1-3 s 的服务异质性和不同
高负载临界行为。两图方向一致的正式 HCA-G31结果支持跨已知拓扑的工程
可移植性；组件激活和删除实验的差异同时说明，局部状态的作用受拓扑和
负载影响。在完成独立随机图或未见机场图评价前，本文不声称统计意义上的
未知地图泛化。

### 故障、P2 与 E2 的职责边界

固定故障矩阵中的线路中断固定起始（启动前登记）并持续整个实验时域。
同 cohort 单变量专项已经隔离出 surviving-graph service-aware DLP：4 格中
3 格实质改善、1 格持平；strict descent 则只在南宁 `single_3` 受益。该
结论仍不等于在线检测、消息延迟下的一致收敛或动态 repair 恢复。P2 因
正式容量为 unbounded 而零触发，最终状态为
`DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`。E2 v2 已在 map2 与南宁 1x
通过逐 segment 完整 move/hold 序列、终态及 release/admission/completion
time 的严格物理等价；事件分别减少 15.8866% 和 18.0229%。它仅承担
`COMPUTE_ONLY_ROLE`，不解释物理容量；`event_queue_peak` 为 N/M，单次
wall/CPU/RSS 只作描述。

### 计算开销与停止规则

G31 的运行时决策不调用完整 A*。相反，S5 global oracle 在南宁 2x 执行
8,403,557 次 runtime full-A* 和 4,593,068 次全局扫描，wall/cpu 达
13,386.460/13,034.016 s，仍只完成 47,058/57,012；该方向被明确停止。
墙钟值受语言、实现、编译和硬件影响，本文只作实现诊断，不将跨语言倍数
解释为纯算法复杂度。负结果用于停止低价值分支，而不是触发新一轮策略
堆叠。

## 限制（替换稿）

第一，Feng-native CIE-DH 的一手实现没有恢复。现有 Java 源码只支持 HCA
聚合回归，公共执行器 CIE-DH 与 Tarău 均为 adaptation；因此本文不能给出
P0 native HCA-vs-DH 的新鲜胜负，也不能把 adapted 数值写成历史精确复现。

第二，跨图证据来自 map2 与南宁两张已知拓扑。它们覆盖不同规模和服务
异质性，但不等于未知机场或随机拓扑泛化。

第三，正式故障矩阵是固定起始（启动前登记）、整个时域持续的线路中断，
不是动态故障检测、延迟通知、repair 或异步一致性实验。纯 DLP 已在四个
固定故障同 cohort 配对中隔离为 3 个实质改善、1 个持平，但这不能外推到
其他故障或动态恢复。strict descent 只在南宁 `single_3` 受益；当任一臂
未完成全人口时，配对 mean/P95/P99/max 保持 N/M，未使用幸存者时延。

第四，所有 2× 正式跨算法 THT 都是 N/A。map2 HCA 少完成 95 件；南宁
HCA 的释放和完成都未覆盖完整 2x 人口。本文使用固定分母完成、截止、
迟到、time-to-X 和积压补充高负载信息，但不报告 survivor timing。

第五，78 个配置是确定性场景，不是随机重复；35 项时延统计也共享场景与
人口。另行完成的 paired random campaign 由 frozen manifest 与 committed
runner 固定五个场景、十个 paired seeds 和两臂同一扰动 realization，共
100/100 artifacts、零失败并报告 10,000 次 paired bootstrap 95% CI。它只
覆盖两张已知拓扑上的 arrival/service 微扰；不能外推到未知拓扑。该矩阵
只估计 P1D1-P0D0 联合对比，potential×dynamic 为
`INTERACTION_NOT_ESTIMATED`，且南宁 2x 的 max tardiness 显著恶化。

第六，P2 为 `DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`；strict descent、
fault potential 与 service normalization 专项已经封口，分别形成局部条件
收益、3/4 纯 DLP 收益和混合停止结论。J2/M3 精确对照因 merge rule 与
timing contract 耦合而记为
`BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT`；E2 v2 只形成
`COMPUTE_ONLY_ROLE`。随机 fault 因 cohort 与 treatment 无法同时隔离而为
`BLOCKED_COHORT_AND_TREATMENT_NOT_ISOLATABLE`。

第七，墙钟与 CPU 主要来自单次实现运行，跨语言/执行器比较没有重复置信
区间；部分产物也未逐项报告全部目标安全和通信字段。因此本文只声明本轮
execution-integrity 与 aggregate identity gates 通过，不声称形式化安全认证
或完整通信复杂度。`outputs/tables/cie_safety_audit.csv` 仅属于旧 G35，
不作为本轮安全证据。激活普查未采集的分位数、相关和热点诊断统一为
`NOT_MEASURED_NO_DECISION_VALUE_FOR_RERUN`。

## 结论（替换稿）

本文提出的一跳去中心化 G31/S4 在 map2 与南宁两张已知拓扑上改善了原
论文正式业务科目：1x 完整人口同释放 mean 与尾部时延均低于 HCA，2x
固定时域在两图完成全部 57,012 件，而 HCA 在 map2 和南宁分别少完成 95
和 17,949 件。该结果来自固定分母和明确协议，不依赖幸存者时延；所有
正式 2× THT 仍保持 N/A。

新的证据分层同时收窄了主张。P0 只确认 Feng-native HCA 的冻结聚合回归，
native CIE-DH 因源码语义缺失而 N/A；P1 只比较明确标注的 common-executor
adaptation；P2 只解释完整系统差距。24 格析因和 10 格激活普查支持
H_SA、dynamic state 与若干局部机制的条件性、拓扑依赖和交互；固定故障
纯 DLP 在 3/4 场景实质改善、1/4 持平，strict descent 仅有一个南宁场景
收益，归一化与 No-Q/I 则因方向混合停止。P2 为
`DORMANT_NO_ENGINEERING_GROUNDED_CAPACITY`；J2 精确对照为
`BLOCKED_COUPLED_MERGE_RULE_AND_TIMING_CONTRACT`；E2 v2 在双图严格物理
等价下减少事件，仅承担 `COMPUTE_ONLY_ROLE`。冻结随机稳健性矩阵的五个
场景全部完成并给出 paired 95% CI，但不估计 potential×dynamic 交互；这些
固定故障结论不构成动态恢复证明。

因此，本文的核心贡献不是不断扩张策略栈，而是以简单的一跳局部决策、
服务网络语义和可检查的实验边界取得跨两张已知拓扑的真实性能推进。后续
工作应优先验证未知拓扑稳健性；若没有方向一致的业务信号，应停止该机制，
而不是增加新的 scorer、guard、参数或模式。
