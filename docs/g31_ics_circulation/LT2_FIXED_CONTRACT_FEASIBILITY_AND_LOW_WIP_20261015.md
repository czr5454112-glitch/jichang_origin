# 固定原流合同：完成上界、下一条可执行候选与100ms边界

本记录只把实际原件、静态必要条件和未运行候选分开。原始28506业务、22盘、FIFO、151节点/227有向边、普通/Storage泊位4、零容量边97→98关闭解释以及原R1权限均不改变。全部业务继续进入分母。不能全完成是当前研究物理合同的一项负结果，不表示保留全分母进行比较的研究任务本身不可能。

## 已确认的结构限制

[原输入](../../outputs/experiments/g31_ics_lt2_sustained_20261014/full_stream_native024_001/full1x/input.json.gz) SHA256为`d37118333de2aa60fb5e9b9d41bab53cccb7ddbab5842862b88a2818e08709a1`。在完整正容量有向图上，24505件的全部必要阶段可达，4001件至少一段不可达。这里检查必经Storage前后各段，不把某条选定路线失败当作全图不可达。原表97→98的容量0原值已核对；将其解释为完全禁止穿越是冻结研究解释，现场语义仍未知。

有限盘和装载FIFO进一步收紧上界。源码`circulation_progress`按已释放任务的`(arrival,business_bag_id)`装载；本实际1×输入没有同origin、同arrival的任务对，因此逐条到达事件不会改变这个源队列前缀顺序。`circulation_leg_failed`保留实际载荷，`recover_empty`明确拒绝`tray.job>=0`，只有目的卸载后的hold完成才释放盘。不可达任务一旦装载，就永久占有一只盘。

在最后一次可达业务完成之前，其自身仍占一只盘，所以至多21件永久不可达任务已经装载。每个loader已装载任务形成FIFO前缀。令`r_i(k)`为源i在第k+1件不可达任务之前的可达任务数，放松所有泊位、时效、路线冲突和返供限制后，求`max Σ r_i(k_i), Σ k_i≤21`。结果是**371件**。这是必要完成上界，不是可实现调度、在线候选或逐件保护证明。

若一个政策绝不装载不可达队首，那么第一件不可达任务之前的可达前缀总和只有39件：

| loader | 0 | 24 | 26 | 49 | 57 | 92 | 95 | 134 | 136 | 138 | 149 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 首个不可达头之前的可达数 |0|0|2|2|2|0|2|0|13|15|3|

[权威原件002](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_carrier_bound_002/receipt.json)保存输入/分析器SHA，压缩分析包含全部28506件的各loader前缀、496个不同必经阶段的完整BFS可达集合/路径、每层DP表和另一种exact-prefix DP。001保留，002新增等arrival守卫。另一代理使用独立bitset传递闭包和exact-prefix knapsack复核全部阶段与数值，得到相同24505/39/371；松弛最大分配为loader24消耗1个不可达盘、loader138消耗20个，其余0。6项纯测试覆盖闭边、替代路径、必经Storage、单盘和未证明到达ties。

该结论绑定这个1×输入和这些条件。若允许目的完成前卸载/放弃载荷、增加盘、跨过FIFO头、改变服务目标或扩大正容量图，证明就失效。2×存在自己的到达排序，未在此复用371。即使显式增加研究R1权限，改路也不能使全正容量图中的不可达义务变可达。

## 实际动力学反例说明了什么

历史`p2_original_offline005_001/fixed_contract_blocking_certificate.json`证明的是一个具体终态：Storage53四盘已在19500释放，队首bag0→99不可达，后方bag2→116可达却不能越过FIFO；其余载货盘向Storage回堵，22盘中没有可用空盘。依赖是112→53、29/137/150/139→112、136→137的回堵链，不能无证据改称循环等待环。

[原图R1配对002](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_tie_streamed_native_002/receipt.json)显式把所有任务的suffix权限设为true，因此属于研究授权域，不能当作原权限策略。四次2秒改道的ACK和实际边均执行，使bag2在9033.022299先于bag0在9043.385453进入Storage；但两臂H22200都0完成。bag2于19500.001出库后到19721.792停在28；29与112均已满。它出库的同一时刻，bag4从112进入53、bag8从29进入112，空位立即被前方其他任务占用。

完整正容量搜索证明：避开28/29仍能从53到116，但避开112后不能到116。因此仅增加一条绕开28/29的路径没有消除必要瓶颈。一次112空位也不保证轮到后方bag2；必须证明真实空位沿29、28持续传播，并最终让出库载荷经过112、113、115到116。

**waiting112准备003尚未执行。**已经实际失败的是更早的1.5秒服务窗干预：2秒线延迟到达时前缀已经执行，返回`stale_executed_prefix`。不能把它写成waiting112失败。等待门检验当前源owner连续观察到稳定的载货盘后，112→113是否真实更新并出边；即使成功也只有可执行性证据。若失败，应保存具体拒绝/未出边原因；若成功，后续多盘分流仍需另行预注册，不能直接宣传业务完成。

最新原024完整1×的H86400末片已产生，父任务报告初步读到28506件全部在途/等待且0完成；全量独立验收由父任务进行。本记录不把尚未完成的该验收替代上述已保存历史配对证明。

## 原权限下更直接的最小候选

下一条候选是**启动时先把22只空盘逐只跨区停到非loader，再只放回1只循环盘**。动机是阻止所有盘先变成不可撤销的载货盘，而不是在满载终态强行腾空。它不删除或取消不可达任务，也不越过同一源的不可达FIFO头；这些业务继续等待并计入分母。它可能增加业务等待，未宣称正常业务保护。

必须排除一个不合法的捷径：`circulation_progress`对端点同zone的transfer明确返回`same_zone_transfer_not_authorized`。因此不能把0→1等同区邻接暂存当作现有R2。新停车全是端点跨区；未来若循环盘只看到同区需求，本门不虚构未声明的两段中转。

[独立runner](../../scripts/experiments/g31_ics_circulation/research_original_low_wip.py)与[准备002](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_prepare_002/preregistered_protocol.json)已保存，**0 native执行**。准备001保留为此前未加入最终原件身份绑定的草稿，不能运行当前源码冒充001冻结源码。

具体动作与信息边界如下：

1. 停车候选只读公开节点角色（type1=loader、type7=Storage）、静态边/容量/port合同和预注册初始盘清单；运行时每个源owner必须用自己的t0真实empty观察逐项校验。停车节点互不重复、非loader/Storage、对侧zone、容量至少3。所有22个实际目标容量4，停车后各余3泊位。没有用未到达业务的origins筛选节点。
2. 两owner按公开顺序分段串行。每次源owner只提交自己当前可用空盘的固定请求。收到实际`received` ACK还不够，必须再收到接收owner的typed v2快照，看到该盘实际在指定非loader且empty可用，才允许下一盘。第二owner仅在收到第一owner的全部已送达received ACK覆盖，并在自己的当前本地视图看到全部接收空盘后开始。拒绝、超时、目标变化或源已被本地正常业务装载均不改选目标。
3. 指定最后exporter的第一只盘作唯一token，它停在第一owner辖区。只有22只都完成上述停车证据后，token owner才能使用真实送达的peer完整当前任务合同；普通demand仅有ID/arrival，不能替代这个合同。按每源当前waiting FIFO的最早任务检查完整正容量必经路径，再按arrival/ID选首个允许跨区返回的源。若该源头不可达，保留它并不选其后续任务。
4. 最多22次停车加1次供盘，均保留2秒命令、0.2秒ACK、原生源/接收复验和FIFO。其余21盘永不再调用。有限policy公开约定除此之外没有其他物理命令；native快照本身不认证未来Python计划不存在。供盘后只继续原请求重试/ACK处理，不再做新的物理选择。
5. 共同观察终点H22200、最多2222次10秒公共轮询、每次native事件预算100000、父进程硬上限600秒。全28506件输入字节不改，R1仍false。失败和未闭合均保留。没有fork答案、离线result或未来业务参与在线决策。

静态匹配的22条最短正容量路径自由流时间总和6753.739秒，首件到达8267.845453。该和未包含所有源服务、线延迟、采样及真实native路线/排队，是必要筛查，不是“必定在到达前全部停好”的证明。真实进入若比筛查慢，后续源空盘检查会失败并保留失败，而不是绕过正常业务优先。

本门首先要求**完整原流中的1件真实完成并释放盘**：全部23物理请求received ACK、22停车事实、指定供盘所服务的原job唯一LOAD_START、UNLOAD_COMPLETE、HOLD_COMPLETE、同盘最终empty/job=-1、完整物理审计和H22200都必须成立。若其他盘也自动装载，不能当作预声明低WIP机制通过。只检验第一次完整循环，第二次reuse明确未证明；成功后才另立复用门。

33项纯测试已通过[004 XML](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_pure_004.xml)。覆盖原图全盘停车、同区/库存/闭边拒绝、未到达头、不可达头不跳队、ACK与接收实体双证据、过期/在途不完整快照、完整结果与删失、额外装载、丢ACK、API篡改/缺失、native同刻预算和绝对import闭包。运行依赖66个Python源与67个native026编译源已归档。实际API逐条流式保存，纯重放重新执行各owner策略并逐项匹配所有调用参数/返回、请求、ACK和快照；最终完整native回执再独立物理审计。[独立源码审阅](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_prepare_002_independent_source_review.json)检查跨owner事实、双接收、FIFO和完成门，未发现具体源码阻断，并核对全部归档哈希；该审阅0native。准备通过不是native可行性通过。

执行命令已准备，但本记录没有执行：

```powershell
$env:PYTHONPATH='src;.'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.research_original_low_wip --output outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_prepare_002 --execute
```

## 100ms账本：应优化真实成本，不能改口径

目前有三种不同事实，必须同时保留。

* `request_bundles_full1x_5000_002`的原图5000激活前缀有3818个no-action根、1172个已闭合有消息根、10个open根。最坏已闭合上界3.86075秒包含全共享owner工作3.0699032秒、scheduler0.445674秒、整段native0.2398241秒、必要output0.1053487秒。它是保守owner-update归因：旧pending请求生存期间相关整段工作全部收费，不是独占business请求计算实测，也不是542.2秒逻辑运输时间。>100ms上界不能独自证明实际孤立请求超限；把该上界除以请求数也不合法。
* `request_native_timing_full1x_5000_001`真实测到两个owner outer activation为125.4233/123.0053ms，inner为124.8764/122.1649ms，CPU均125ms；其中一个no-action。嵌套native仅2.6557/2.8394ms，所以不能把这两个尖峰全部归因native验证。该次没有GC callbacks，不能猜定GC原因。晚期023另一次cProfile中6次gen2 GC合计951.1051ms，最大215.1708ms，但其GC行无根时间戳，不能将具体暂停嫁接到另一次运行。
* tiny installed-operation原件经setup修正后8个closed根初始化宿主界限2.3491–8.7324ms，仍有1个open。含全部case壁钟setup敏感性为309.5863–440.8651ms，whole-worker为每根完整5.6883344秒不摊薄。它是tiny的一次实验性operation合同，不是原business全请求100ms通过；原现场admission口径仍未被此替换。

真实重复开销的优先级由已有phase证据支持。在native022原图5000前缀，6146次policy observation合计8.8203306秒，5000次demand signature0.5379979秒；11889次transfer query加4226次command query合计0.1490425秒。最多查询的单身份1628次查询共22.6334ms。ACK轮询是实际continuation成本，但不是该记录首要热点，不能为漂亮数字把查询从原请求移除。

应先继续已有等价优化路线：`circulation_session_binding.hpp`的合法投影/派生送达索引、`regional_control.py`和`analytic_control.py`的静态公共图复用与候选重复构建、`ProtocolClient`实际复制/历史扫描，以及lossless诊断流式导出减少活跃对象图。native026的500-owner同二进制reference/indexed短段观察为15.4040→8.1961秒且原件逐字段相同，但并发环境不同，不是稳定硬实时证明。公共旅行池已有5000前缀25.037→19.645秒的语义一致对照，也不是单请求100ms证书。GC不应关闭或从收费区间减去，native物理推进和未标注余量也继续收费。

完整原图通知根试验另已准备`original_notification_prepare_001`：真正通知到达前声明bundle，包含no-action、拒绝、丢ACK与未闭合；setup全收费、API实际重放、源/接收/ACK/输出不遗漏。它仍是更保守的实验性通知bundle，不能单靠换根名成为用户的原始business admission。新低WIP候选仅回答业务可行性，完全不承担速度证明。
# 2026-10-15 后续实测补充

`original_low_wip_prepare_005`在133.534547秒内完成原生运行与保存带独立回放（10305 API记录）。输入仍为28506件、22盘、原R1权限false；H22200时已到达3998件，仅装载并完成1件。不能把“保留28506件输入”写成“28506件都已到达此有限门”。所有22次停车和1次供盘都收到真实received ACK，最后token为空；逐件保护、第二次复用、100ms均未证明。

唯一完成链为：domestic在8890从112发出空盘供给国际26；依据8882捕获、8884送达的队首消息选择`projected:1x:2`；9262.488开始装载，9419.694进入Storage，19500释放，19772.592在116卸载，19773.592结束HOLD，同一`initial:0:0`返空。源文件、原输入、物理约束未漂移。004在H14060的日志替换异常保留；005仅给该IO动作加入有界PermissionError重试，没有改物理策略来取得成功。

后续实验须在真实返空后再依据当前送达的队首消息供盘，并要求同盘第二次LOAD/UNLOAD/HOLD；不从离线已知未来任务中挑选目标。队首不可达仍阻断该源的后续件，其他源按原先规则独立检查，原业务分母不删除。

文献核查（2026-10-15）：Spearman与Zazanis研究了限制在制品与拥塞控制的关系，支持把有限在途量作为一个可检验的控制因素；其可解析生产模型不证明本项目的FIFO、保管、跨区ACK或逐件期限性质。[原论文与摘要](https://pubsonline.informs.org/doi/10.1287/opre.40.3.521)

近期输送系统研究组合固定WIP、排序与路由，说明固定库存下的控制仍可影响吞吐；但它研究同质make-to-stock业务，没有逐件延误KPI，不能借用其排序自由度或吞吐结果证明本任务严格保护。[Castiglione等，2026，§2–3](https://arxiv.org/html/2609.29461v1)

本项目停车的21个盘始终占据真实节点和库存；“只让一个盘承担装载业务”是当前可执行性实验，不是改变22盘总量，也不是新的CONWIP理论。1990年CONWIP出版站全文本轮返回403，未按未读全文引申结论。

