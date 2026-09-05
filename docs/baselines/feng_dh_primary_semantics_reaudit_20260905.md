# Feng DH 一手机械语义复核（2026-09-05）

本次重新阅读学位论文、CIE 一审修订稿、审稿回复，以及沿参考文献精确定位的 Tarău 原文。结论是：**当前 Java 的零时间正确性和等价优化已通过回归，但这不证明交接缓冲与同 tick 调度恢复了 Feng 的实现。最值得先在 map2 检验的是交接阶段提前释放上游占位、离边等待不进入路由拥堵计数，以及移动/评分的观察时刻。** 这些是有文献动机的可证伪假设，不是已经恢复出的源码事实，也不以 G31 获胜为选择条件。

本文件只做阅读与代码审计，没有改 Java、地图、输入或系数，没有启动模拟。新语义候选须先经过 map2 门，不据本文件启动南宁或完整随机矩阵。

## 1. 资料身份、版本与页码

本地材料根目录为 `C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料`。PDF 页码以下均从第一页开始计数；另列纸面页码时明确说明。DOCX 段号按 `word/document.xml` 中正文直接子元素 `w:p` 顺序计数，包含空段、不包含表内段落。

| ID | 实际阅读资料 | 定位与版本边界 | SHA-256 |
|---|---|---|---|
| F1 | `毕业设计/毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.pdf` | 67 页；DH 步骤和表 5.3 在 PDF 43 页、纸面 29 页；参考文献在 PDF 52–53 页。相关页面已渲染检查。中文字体文本提取失真，以页面图像和同名 DOCX 互证。 | `37e61b8e4d67e56c0fa14c43b230be965e200106704363f06b80a4e6a151e1aa` |
| F1d | 同名 `.docx` | 正文段 221–229 为 DH 步骤与结论；段 279 为参考文献 [14]。它是文本交叉核对来源，不把其段号冒充 PDF 页码。 | `809cadc743e4d13d05f474a18e5b41be46f4608fd43f9f5ab7a17fdc0015756a` |
| F2 | `CIE/manuscript-ics 一审修改后查验.pdf` | 37 页；14–16 页为系统约束，25–26 页为新增加的 DH 实验，36 页为完整引用。已检查渲染页上的修订标红和批注。这是**一审修订检查稿，未经核实为出版社最终稿**。 | `6c317372affd636ad85011f85c939b5cfbe217b2ef1365280acba1122ede59fa` |
| F3 | `CIE/Detailed Response to Reviewers V2.docx` | 段 108–114 逐项说明新实现的仿真过程；段 43、47、57–63、91 说明引用关系；段 120 解释结果。正文参考年份后缀存在重复/不一致，不能单靠 2009b/2009c 识别文章。 | `9e65307ac901b9214f53a6bb6c6a99d2d82974cce4f6576bd1e03dc84758ccb3` |
| T1 | Tarău, De Schutter & Hellendoorn, *Route Choice Control of Automated Baggage Handling Systems*, TRR 2106 (2009), 76–82, DOI `10.3141/2106-09`；作者公开 technical report 09-011 | 从[作者公开 PDF](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf)下载并完整阅读 17 页。封面明确绑定该期刊文章和 DOI；作者稿正文纸面 1–16 页，不能把作者稿的页码当期刊 76–82 页。模型见 PDF 4–6 页，DH 见 PDF 8–10 页，图 2 见 PDF 16 页。 | `16555e1ff48d8d3230295df5f319d0f931e3639845966b5d2ddd9f609f003f82` |
| F4 | `ICS项目/ICS相关文档/分散启发式方法.graffle` | 重新读取 zip 中 `data.plist` 的图形标签；仅含粗流程，没有交接计时、容量、系数或容器迭代说明。 | `688c7121eaf0d0550e7738098165960e3ac5b7504163bee19c41d2f778df262c` |

精确引用链为：F1 的 [14] → 文章标题 *Route Choice Control of Automated Baggage Handling Systems*；F2 25 页的 Tarău et al. (2009b) → F2 36 页的 TRR 2106:76–82；F3 段 57 还直接给出 DOI `10.3141/2106-09`。本地 `CIE/manuscript/manuscript-ics.bib` 的 `tarau2009route` 也给出该标题和期刊，但其作者字段与年份后缀不能替代上述交叉核对。出版身份由[出版社 DOI 页](https://journals.sagepub.com/doi/10.3141/2106-09)和作者稿封面确认。

特别避免三个混同：

- 本地 `参考文献/DCV相关文献-物流/08_025.pdf` 是同题的 TRB 2009 会前稿（15 页，封面注明 paper 09-0432）；本次没有用它代替精确指向 TRR 的 T1。
- 2010 年 *Model-Based Control for Route Choice in Automated Baggage Handling Systems*（341–351 页）以及 2009 年 distributed control 文章都是相关后续材料，不能冒充 F1 [14]。
- 本地 `CIE/manuscript/manuscript-ics.pdf` 为另一份 32 页稿，SHA `053d4471fd17594061b007df7f1f1b6a73c31aa9902492b96ee2009a90e2e8aa`；不能把旁边的 TEX/BIB 当成 F2 37 页修订稿的逐字源码。本文 DH 机械步骤以 F1/F2/F3 相互印证。

## 2. Tarău 原始 DH 与 Feng 简化 DH 不是同一个控制律

T1 §4.3（PDF 8–10 页）是 junction-local switch-in/switch-out 控制：入边静态/动态优先级决定 switch-in；出边当前排队与释放率、静态续接距离和到达时间成本决定 switch-out；当前开关位置和最小切换间隔 `τx` 进入约束/代价。权重在 §4.3.3 离线校准。其运动底座是连续时间事件推进，局部防碰撞控制负责安全距离；并非 Feng 的 0.2 s moving/stopped 路径计数器。[T1 原文](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf)

F2 25–26 页与 F3 108–114 段明确描述的是另行开发的简化比较器：每 0.2 s 更新袋状态，按最短路径自由流时间加 moving/stopped 袋数惩罚选择出口，在出口第一位置有 stopped 袋时 HOLD。全路径范围的直接定位是 F1d 段 225、F2 第 26 页步骤 (b)、F3 段 112；三处均说最短路径上的每个移动/停止袋，而非仅直接出边的袋。它没有给出 T1 的 switch 状态、`τx`、入边航班优先级权重或排队释放率公式。因此：

1. T1 能说明“原始 DH 不是无限快、无记忆的任意换路器”，但不能证明 Feng 实验仍保留全部开关约束。
2. 不能把 T1 的一组离线权重或切换等待硬填成 Feng 的 `alpha_move/beta_stop` 或每袋固定 transfer。
3. “只看直接相邻边”适用于 T1 的动态信息边界；Feng 的文字却明确说统计最短路径上的 moving/stopped 袋。缩成一跳计数会改变 Feng 已披露的控制律，不能据此称更忠实。

## 3. 支持什么，尚未支持什么

| 主题 | 一手证据 | 当前 Java 的关系 | 审计判断 |
|---|---|---|---|
| 原地图、原需求、2.5 m/s、0.2 s | F1 纸面 29 页；F2 25–26 页；F3 108–111 段 | 使用原 map2/raw 需求和固定 tick | 明确支持；不可用改地图/OD 过滤修复数值形态。 |
| 移动与 STOPPED | 有空间或紧前袋为 moving 时可向下一位置移动，否则原地 STOPPED | 保持位置/状态及物理间距约束 | 粗规则支持；0.5 m cell、1 m footprint、安全距离细值及端点取整未由这些步骤唯一识别。 |
| 更新顺序 | F2 25 页、F3 111 段为 “one by one”；F1 中文为“一次更新所有行李” | `step` 用 tick-start snapshot、plan、局部 resolve 和集中 commit | 英文支持逐袋处理，不足以证明集合遍历次序、原地更新可见性、(a)(b)(c) 是全局三阶段还是逐袋串行；同步方案仍是未识别假设。 |
| 评分时刻 | 步骤 (a) 更新位置/状态，随后 (b) 选出口 | `policy.choose` 读取 tick-start snapshot，而非移动后的视图 | 当前观察时刻不是步骤文字明确给出的唯一选择；应单独做时序语义诊断。 |
| 评分信息范围 | F1d 段 225、F2 第 26 页步骤 (b)、F3 段 112 均提到最短路径上的移动和停止袋及更高停止惩罚 | 每个出口接一条自由流最短续接，沿其边累计占用 | 全路径计数范围有 Feng 的直接文字支持；具体候选集、并列最短路、tie-break、每个拥堵袋是否只计一次、准确观察时刻和可见延迟未完全识别。 |
| 全局协调能力 | F1/F2/F3 称局部 junction 独立处理 | 当前程序全图遍历，但竞争分组按节点/目标边，规则为局部 FIFO；没有多袋联合目标、未来预约或 G31 scorer | 不能因程序持有全图对象就叫集中优化。其无冲突同步腾空可提供理想化同 tick 协作，但量级须测量。 |
| 出口阻塞时的物理位置 | F1 29 页：在节点处等待；F2 26 页/F3 113 段：在 switch 前停止；F2 14 页也说明低层可在 junction 前停车 | through 结束后，袋脱离原边、进入 `AT_LOADING_OR_JUNCTION`，即使出口继续堵塞也不恢复上游占位 | 文献没有给出这样的离边存储区。它可能切断回压，应作为首要可证伪的缓冲假设。 |
| 节点服务及缓冲容量 | F2 15 页要求同 junction 通过区间不冲突、弧容量不超限；具体低层控制在 14 页被留在研究范围外 | 正 through 局部独占；之后每袋 2 s timer 可重叠，候出口队列没有节点容量上限 | 1 s + 2 s 的分解、2 s timer 的空间位置及容量均非恢复出的 DH 源码。一般冲突约束也不足以证明整个 3 s 必须独占。 |
| transfer 等待的路由可见性 | F2/F3 的停止袋应产生较高拥堵惩罚；没有描述“离边袋不算拥堵”的豁免 | 进入 timer/节点待入口的袋不在 edge snapshot moving/stopped 计数里 | 与提前释放占位共同形成潜在额外能力；需要同时记录物理回压和评分中遗漏的等待袋，不能只看 mean 是否变慢。 |
| 每袋服务时长/开关时长 | T1 的 `τx` 是开关改变之间最短间隔，Feng 简化步骤未给值 | 当前固定 2 s 来自历史单件 OD 下包络推断 | 不得把开关最小驻留、地图 throughTime、每袋 transfer 和源端诱导视为同一种时间。 |
| 目的站/空 tote | F2 16 页假设始终有空 tote，卸载后释放的 tote 立即移出系统 | goal 到达直接完成 | 明确支持已卸载空 tote 的移出；不单独确定卸载服务时间或排队能力，更不能据此推广为中间节点无限缓冲。 |

这里 F2 15 页的通用约束属于其系统/IoT-DRPA 模型描述；将其用作 DH 的物理一致性核对有明确理由，但**不能据此声称已经读到 DH 的完整节点实现**。F2 对低层实现的留白正是本次假设需要保留标签的原因。

## 4. 当前实现的具体能力来源

本轮代码阅读对象是已通过零时间修复与等价优化的版本，生产 source aggregate 为 `809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f`。先前等价优化证明其输出与正确性版一致；以下质疑的是更早的物理合同，不是性能缓存改变了策略。

- [Simulator `step`](../../benchmarks/java/feng_cie_dh/App/FengDhSimulator.java) 在开始时取 snapshot。到达目标、正 through 完成和零 through 获准完成者加入 `guaranteedDepartures`；`planInternalMovement` 按每条边从下游向上游规划，再用计划后入口空间仲裁。它避免穿越并能在同一 commit 使用已证明腾空的格子。这是理想同步执行假设，**不是**利用未来多个 tick 的全局路线优化。
- 正 through 完成者在后继入口是否有空位尚未解决时就释放原边，随后 `beginNodeService` 将 `currentEdgeId` 与 `positionCell` 设为 `-1`。timer 到期后仍可留在该状态等待任意多 tick；释放 through 服务器后，后续袋可以继续进入。故“边上始终不重叠”不能证明不存在未建模的节点等待空间。
- [Policy `choose`](../../benchmarks/java/feng_cie_dh/App/FengDhPolicy.java) 对每个候选续接遍历 `edgeIds`，只加 `Snapshot.movingCount/stoppedCount`。离边 timer/入口队列不会计入任何候选路的 stopped 成本。这种存储与不可见性可能共同影响物理拥堵和选路，不能只把它归为计时常数。
- 当前没有 switch-in/out 的机械位置记忆和 `τx`；但这是“与 T1 原始控制不同”的证据，尚不是“违背 Feng 已披露简化器”的充分证据。把它们加回来会构造另一种 Tarău 参考实现，应单独标识。

因此，当前实现的风险表述应为“交接缓冲和同步调度的未识别假设可能使重构偏乐观”，而不是“已经证明全局 snapshot 使 DH 强于真实算法”或“原算法必然慢于 G31”。

## 5. 有证据动机的 map2 检验假设

所有候选在运行前固定合同、输入身份与接受条件；先保留原始 1× shared-D 全人口控制及逐袋 trace，再做单轴变化。不要按接近历史均值或有利于 G31 的程度择优选实现。

| 优先级 | 候选假设与动机 | 必须保持 | 需要观察的证据；不能声称的结论 |
|---|---|---|---|
| H1 | **无额外离边等待空间**：在既有 through/transfer 计时过程中保留物理边界占位；计时完成后若下游入口不允许接收，继续占位，直到真实进入后继边。依据是 F1/F2/F3 的 switch 前/节点等待及 F2 的容量约束。 | 原 1 s through 与每袋 2 s timer 时长分别保持；1 s 节点服务器按原时刻释放，不把所有 3 s 变成单一节点独占服务器；出口 scorer/系数、工作负载不变。 | 单袋自由流时刻是否不变；阻塞双袋/合流/循环图是否守恒无重叠；离边等待量、上游回压、stopped 计数与首次分叉。性能方向未知；即便数值接近，也仍是候选重构语义。 |
| H2 | **按步骤 (a) 后的状态评分**：对照目前 tick-start 快照和完成位置/状态更新之后的观测，检验 (a)→(b) 的时序影响。 | H1 是否采用先固定；不同时改路径集、处罚权重和装载时刻。 | 保存首次产生不同候选分数/选择的 tick；分解因位置变化还是 MOVING/STOPPED 标签变化导致；不把“当前序”认定为已证实的原作者集合遍历。 |
| H3 | **更新可见性敏感性**：仅在 H1/H2 分离后，检验一个预定逐袋更新方案与同步方案；必要时用反向固定次序作顺序敏感性诊断。 | 安全/守恒断言和同一任务人口；固定次序在看结果前声明，不选择最贴历史的遍历顺序。 | 顺序依赖是否显著、同 tick 腾空是否为差异来源；没有作者容器/实现证据时，不能把某一次序升级为 faithful。 |

H1 的出发点是避免凭空提供空间，不是为校准增加等待。实现 H1 时必须明确：保留的是物理边界占位，不能悄悄把经过时间的定义改成额外节点资源占用。若它带来真实环路回压或未完成，保留结果并定位，不能以“必须完成”作为事后放宽条件。

评估数值须始终同口径：历史 DH 的 `sum(E-D)` 与当前 shared-D 重构对照；入网后、统一 scheduled-release 和无抖动 `same_hca` 科目另列。不能把某列 G31 最快值与另一列 DH 最慢值拼成 THT 胜负。map2 控制应确认 28,506 袋和 43,603 段，保存 min/mean/P95/P99/max 和逐袋误差形态；若一个物理合同只改善均值但破坏单袋语义或产生不明截断，不得进入新扩展矩阵。

## 6. 本次检索停止点与仍未识别项

本次在材料目录扫描本地参考 PDF 的封面/标题，精确排除了“同题会前稿 = 所引期刊原文”的混同；新读取 T1 全文而非引文摘要。重新检查直接相关的 Graffle zip，其标签仅为初始化、位置/状态更新、到节点判定、选择出口、完成判定，不能恢复内部容器更新或缓冲机制。随后新增的 Demo3D 容器线索已继续展开，结果见第 7 节；只扫描 `.java` 或只看模型的 `Source` 字段会漏掉其 `NativeSource` 和可视化脚本，不能用先前扫描范围声称不存在其他源码。

仍未找到 Feng DH 源码、数值罚项、交接空间/容量、容器迭代次序、MOVING 标记变化的精确时点、并列规则或作者给定的 switch/transfer 参数。因而本次可交付的是**更严格的一手证据边界和先做 map2 的机制假设**；任何数值吻合和正确性 PASS 均不能合并成 source-exact PASS。

## 7. Demo3D 内嵌代码与工程文档的新增实查

此次实际打开 `ICS项目/地图模型/ICS_algorithm-2.demo3d` 的 ZIP 成员，再解析 70,958,379 字节的 `ICS_algorithm.demo3d` XML；外层 SHA-256 为 `f2c0b6172c1ec9e501b0e142215253e45021b145b6a9acedf625031c9eddd04f`，XML 成员 SHA-256 为 `fada6fe7d027b8301f0ae5eb4f034b2d21ad54205fb4d5ea384e25aed0602f1a`。没有执行模型、脚本、DLL、工程或网络连接。可重复提取器为 [extract_feng_demo3d_semantics_evidence.py](../../scripts/eval/extract_feng_demo3d_semantics_evidence.py)，[紧凑证据索引](../../outputs/runtime/feng_dh_semantics_reaudit_20260905/primary_model_evidence/README.md)保存成员/源码 hash、实例绑定、参数、原行号短摘录和文档段号；完整模型、厂商库与含 IP 的通信源码只保留在本机 `tmp`。

### 7.1 找到了工程实现，但没有恢复出 Feng DH 路由器

模型有 73 个脚本容器、3,267 个场景对象直接脚本绑定。`BaggageHandling.3` 内嵌可读 C# 工程，与 `BaggageHandling.4` 对应 39 个非 csproj 文件逐 hash 相同；“许有于 2020-04-15 修改”的容器时间戳不能证明厂商库算法被作者改写。名为 `BaggageHandling` 的包只包含 csproj/DLL，127 个实际绑定对象均为 `Demo3D.Components.BaggageHandling.Controllers.SensorControllerCS`，不是从名字就能识别的 DH 比较器。

可读工程中的 `IntersectionControllerCS.FindDefaultDeliveryConnector`、`Utils.IsTargetInRoute` 和 `FlowControlCS.TargetIsReachable` 使用 `ConnectedRoutingDijkstra`。没有在已读逻辑中找到 Feng 的“自由流路径时间 + moving/stopped 袋数”评分或逐袋状态更新函数。不能从 DLL 的字符串未命中进一步证明所有二进制中绝无 DH；本次静态证据足以确认的，是已绑定且可读的路由逻辑属于目标站输送/设备控制。

更具体的联动证据是 `FlowControl1`：它绑定 `FlowControlComponent`，`MainProcedureEnabled=1`；初始化入口按此开关执行可视化过程。`PLC` 属性指向 `QC13/Sensor4`，后者绑定 `SensorScript.2`。该传感器发 RFID/BTM 信息，收到 `rfid,port` 后更新 `table`。可视化 `GetTarget(rfid)` 从此表取 `port`，再由 `GetVisual` 映射到 `V_1..V_4`，`ConveyBySource` 将袋送往该目标。因此这不是“只有未绑定模型目录”的发现，但也不能跳过外部目标映射直接称其为独立 DH。

模型 AST 中确有 `wait 0.2`，但其所在过程是 `UpdateTargetFromBIMS`：反复将硬编码 `('abcdefg1213', 2)` 写入目标表后等待。静态 `ProcCallControl` 调用链为 `MainProcedure → Dispatch → ConveyBySource → GetTarget → GetVisual`，没有调用这个 0.2 秒过程；即使它经别的机制启动，函数内容也不是更新全袋位置/状态。`ConveyBySource` 另有 0.01 秒等待。故**此处 0.2 数字不能充当论文 DH tick 的实现证据**。

### 7.2 2 秒、0.6 秒与物理占位不能互换

| 保存的实际场景配置 | 对应实现及可推断范围 |
|---|---|
| 47 个 `TransferDuration=2` 自定义属性 | 全在 `RollerLiftTable/ChainLiftTable` 的 `Lift` 子件；同对象原生 `TransferDuration` 保存为 `0`。父对象绑定 `PalletLiftTable`，不能将这个同名自定义属性直接解释成全部普通 junction 每袋固定停 2 秒。 |
| 77 个 `IntersectionController` 实例均 `TransferTime=0.6` | 46 个绑定 `.3` 可读工程、16 个绑定 `.2` DLL、15 个绑定独立可读脚本。62 个 Fifo、15 个 Passive；全部 `TargetBlockedMode=Dieback`。参数来自场景实例，不是库默认值。 |
| 77 个实例均 `DisableForLinPhys=1`；Scene 保存 `PhysicsEnabled=0`、`SimulationLinearPhysics=1` | 可读版本的初始化调用 `OnDisableForLinPhysUpdated`，在这组条件下将自身设为 `VisualOnly`。所以有绑定且有参数也不能证明保存的 linear-physics 模式实际执行了该传感器控制路径；引擎底层运动源码未恢复。 |
| 可读独立控制器 `SimulateOntoConveyor`（原行 1062–1104） | 先 `ReleaseInfeed`，后按几何距离除 `TransferTime` 得到速度，`MoveTo` 并等移动完成；直行分支按 conveyor 距离推进。它提供了“转运时间对应空间运动，且释放上游可先于转运结束”的具体实现例子。 |
| 同控制器 `StopInfeed/WaitToAccept/SimulateLoad`（原行 893–1019） | 下游停机/忙/禁用时可进入 Dieback，停止或锁定真实物理载荷；分流目标有 busy 标记。它不能支持无界离边缓冲，也不能支持“整段 transfer 必须占住上游最后一格且 STOPPED”。 |

由此需要修正证据权重：当前重构的固定 2 秒仍属于历史单袋时刻的推断；Demo3D 的一个同名属性不能把它升级为已恢复参数。新发现支持将“几何转运”和“入口堵塞时的实际停车占位”分别核对，**没有支持把 0.6 秒直接替换进 Java、给所有节点加 2 秒 STOPPED、或因释放上游而允许无限中间等待**。第 5 节 H1 是隔离潜在缓冲收益的诊断合同，整段计时保留上游最后一格不是已经由原工程证明的物理事实。

### 7.3 工程文档确认了外部路由的边界

以下段号与前面 F1d/F3 的口径不同：这里按正文全部后代 `w:p` 计数，包含表格内段落。原文件 SHA 和逐段摘录保存在 `engineering_document_excerpts.json`。

- `系统设计说明书.docx`（SHA `ea6c8ac57ff08315b982bd476954839e2b7fffa7c5049f949acbe461b7b85e42`）段 60、65–84、104–117、127：外部通信收任务与故障信息，保存全局路径/约束，通过 A* 比较节点预计到离时间与已有约束。这是该工程的路线规划模块，机制上接近已有预约式 Java 系统；不能据文件所在目录宣称它实现了独立 DH。
- `用户使用手册.docx`（SHA `a03edc637ec0a5e2ae8b2197653bde7df024b46af6f0cde1a400334a2a753cce`）段 37、46：每 1 秒收取服务端任务/空消息并返回路径。这是通信周期，不能代替 DH 0.2 秒物理步长。
- `系统安装手册.docx`（SHA `73a0e25f11ffb4291c7f1a512bdfd1f9cdbb1ed671470912e209a7aec8018ae5`）段 63–69：地图记录托盘长、安全距离、节点通过时间、弧长度和速度。没有另外声明所有路口必须增加同一个 2 秒 transfer。
- `仿真报告.docx`（SHA `6529a7658df104ba981441bde80b58eacda7b6fedfe11cccec3cbf0f92779f64`）表 3/段 104–126：装载站 1,800 tote/h、静态卸载站 1,200 tote/h、预分拣环 3,600 tote/h。表 4/段 158–176 在 2.5 m/s 下给出 min/mean/max 为 3.13/4.16/6.72 分钟。它研究天府 T2 的工程模型，包含 EBS/空托盘过程，未把这些结果标为论文 DH；这些容量与时间只能说明该工程存在不同设备吞吐和转运过程，不能拿来拼接论文 DH 的目标分布。

新增资料为“有几何占位与外部路由的工程模型”提供了可定位证据，也揭示了先前检索遗漏；尚不足以恢复论文比较器的独立运动引擎。后续 map2 诊断应保持路线、输入、评分与单袋时间不变，区分 boundary 的离开时刻、实际转运空间和下游拒收时的回压。历史汇总量只用于检查同量级及误差形态；候选的选择仍须由逐袋/逐 OD 时间签名与可辩护的机械语义支撑，不按 G31 胜负选择。
