# 原图、完整来源流与物理服务合同

版本：P2-input-v1，2026-10-13。实现：`scripts/experiments/g31_ics_circulation/original_workload.py`。这是研究输入适配与诊断，不是新的仿真器，不自动通过 P2/P7 或方法创新门。

## 已实际核对的来源

调用成熟 G31 的 `run_g4irsf31_nanning_map.load_source_dir/build_profile`，只读两个原始 OOXML 文件，逐值复核 `nodes`、`edges`、`source_resolution`、`business_roles`，与当前 `data/processed/maps/nanning_airport_profile.json` 完全一致。原文件未编辑。

| 来源 | SHA256 | 核对结果 |
|---|---|---|
| `C:/PROGRAMING/czr005/map_nanning/附件：拓扑结构示例1.xlsx` | `802fec3d6640e6a7ed2c087c03cd6a7f4eba1178809789694d621a263b7cd1ce` | 国际57节点、85有向边 |
| `C:/PROGRAMING/czr005/map_nanning/附件：拓扑结构示例2.xlsx` | `3cf4b4ccc8d2a503050d58d6e93684992c81785e7fd9a405d0a32ff33382eb93` | 国内94节点、142有向边 |

合计151节点、227有向边，包含5条源表跨系统连接。两个 `ICS156` 是不同物理行，继续使用 workbook/system 命名空间，不合并。方向、距离和原表2m/s速度全部保留；没有沿用历史 workload 选择代理 EBS 时用于评分的2.5m/s作为新执行速度。

源业务为 `legacy/jichang_origin_readonly/inputdata.txt` 的完整28506袋、360个航班代理组。它是现有历史模拟来源，不冒称南宁现场观测日。原业务节点属于旧54节点机场，不能把相同整数直接解释成南宁物理节点。新适配调用成熟 `run_g4irsf31_nanning_workload` 的既有 lane/flight 投射和 G29 完整航班中间插入规则，不重新发明 OD。原输入及显式投射输入是不同研究因子，旧历史轨道保留。

| 已冻结来源规则 | 1× | 2× |
|---|---:|---:|
| offered业务袋 | 28506 | 57012 |
| 早包 | 15097 | 30194 |
| direct | 13409 | 26818 |
| 旧展开运输段（仅身份对照） | 43603 | 87206 |
| 独立源任务流 | 1 | 1（完整航班合法派生，不是第二运营日） |

每袋保留原 task ID/源行、原 OD 命名空间、投射 OD、是否派生和时移、旧段 ID。`business_crosswalk.jsonl.gz` 包含全分母。业务 ID 为 `projected:<scale>x:<raw_task_id>`；托盘 ID 独立命名为 `initial:<node>:<index>`，原 task ID 不再当有限托盘身份。

## 不得掩盖的原图负结果

源表国内邻接表第7行 `ICS103→ICS104`，映射97→98，长度0.6m，源表 `pallet_capacity=0`。**原数值 confirmed；将0解释为禁止穿越的物理闭边是 research_proxy interpretation，现场语义 unknown。**本轮固定研究合同保留该边与0容量并拒绝进入，不能升为1、删边后宣称原图相同，或改方向绕开。后续原件检查发现F1为“托盘容量（个）”，F7为数值0且无公式，全部227边数值均等于floor(length/2m)；这与可容纳完整盘位数量一致，但本身不足以证明短连接不能连续穿越。成熟G31 adapter此前仅保存此metadata，legacy文本没有per-edge capacity字段。原件见`p2_zero_capacity_semantics_001.json`。

在上述明确闭边研究解释下，有向可达性诊断发现：1×的4001袋、2×的8002袋至少一个必要运输段不可达。它们全部保留在输入和结果分母。拓扑忽略此限制时strongly-connected；两种结果都不能独自认定现场物理能力。其余袋无队列、无限盘松弛下未发现必然超截止；这不是有限库存可行性或最优性证明。

这些不可达袋的目的节点为99/101/103/106/108/110，1×前五个各667袋，最后666袋；各loader都受影响。仅此原图合同给出业务完成上界1×24505/28506、2×49010/57012，实际有限盘/服务限制只会进一步收紧。不能用这个上界作为允许删4001袋的理由。

修前实际运行保存在 `outputs/experiments/g31_ics_long_term_20261013/p2_original_native_before_zero_edge_001/receipt.json`：旧最终 binding `897f6e…` 对完整原图返回 `circulation:invalid_edge_contract`。这是 native 尚不接受关闭边合同，不能通过改输入扩容消掉；原生负责人在共同模型中支持零容量后再执行同输入。

## 服务、容量与等待口径

`nanning-on-carrier-proxy-v1-n4-s64-t2` 显式默认研究组：普通节点4个泊位，Storage53为64个泊位，11个有需求 loader 各2个初始盘（总22盘），边容量完全取源表，入口头距1秒，业务完成后的 hold=1秒。所有值有限；这些节点泊位/盘数/头距/hold不是现场标定值，也不表示64库位有业务来源支持。CLI 另立Storage4/16/64、普通泊位1/4、盘量等敏感性组，完整参数有独立SHA256，不覆盖历史组、不能靠调大参数宣称算法收益。

三种身份不混用：`zone` 保留源表 `system_key`，控制分区显式派生为 `partition:system_<system_key>`，资源权威显式派生为 `owner:system_<system_key>`。后两者的来源等级是 derived/research_proxy；现场控制辖区和owner权限未确认。各算法共用同一固定映射，不能把默认兼容回填zone当成三者语义相同。

| 量 | 来源等级 | 实施/边界 |
|---|---|---|
| 图连接、长度、速度、边容量、设备命名 | confirmed（与本地源表一致） | 源表本身是否最新现场图仍未知 |
| 数值节点服务时间 | confirmed（源表） | 保留 native 节点服务；额外 load/unload 均0，避免同一源表服务重复收费 |
| 6个 `/` 节点服务 | research_proxy（成熟G31既有补值） | 0秒源值，native最小服务1ms；未假称设备零服务 |
| Storage53 | research_proxy | 源表是空盘库位，真实EBS未识别；冻结为 on-carrier 研究代理，实际 release 才生成后段 |
| 早包判定与发布释放 | 既有模拟来源合同 | STD-arrival≥4800秒；release=STD-2700秒；不预建第二段实体 |
| deadline | research_proxy | STD减显式lead，默认lead=0；不把事后 deadline_met 当逐袋不增时保证 |
| 节点可停位置、空/载等待许可 | unknown现场；research_proxy研究组 | 仅显式 `finite_berth_waiting_research_proxy` 可执行；未实现无等待链安全承诺，其他合同准确拒绝 |
| 节点泊位/库位/初始盘数/入口头距/hold | research_proxy | 有限且版本化，不能称现场容量 |
| 模块 port allow/deny/min_stock | research_proxy | 当前固定代理接口；真实区内模块查询/导出/接收权限尚无现场接入 |
| `capacity=0`是否允许连续穿越短边 | unknown现场；research_proxy interpretation研究组 | 源表0原值confirmed，当前研究合同视为关闭；“零缓存短连接＋两端接收/尾窗”需明确空间占用模型，未实现未运行 |
| off-carrier EBS | unknown/未实现 | 不与 on-carrier 合并。需要真实袋库位、释放盘、检索服务及实际接载盘方可晋升 |

当前 native 在 storage_in 目标完成时执行节点服务；storage_out 从同点开始时再次执行源节点服务。研究定义是两个运输段的处理访问；所选Storage53源表服务0，仅有两次1ms下限。若后续要解释成一次连续设备处理，必须先定义并实现服务结转，不能在报告中把两次服务当成已证明只收费一次。终点 native 处理已承担源表 unloader 服务，故额外卸载为0是去重，而不是把卸载物理服务删掉。

全部任务保留已接受服务义务，后续区域改路须检查原工序、截止和权限。这里的完整流入口本身不构成事前逐袋服务保护证书；成对基线及在线 ServiceObligation 仍由主线实现。

## 实际准备、回归与可续运行

`p2_original_1x_prepare_001` 和 `p2_original_2x_prepare_001` 已实际完成全流适配、源表验证与静态诊断；两目录不是 native 完成结果。`p2_adapter_tests_001.xml` 记录14项实际通过；002新增同刻事件预算截断的观测分母检验，共15项通过。覆盖原全流与冻结 manifest 分母/OD边际相等、完整父身份、原图/服务/零容量保持、不可达全分母和删失计量。旧准备回执对应其自身adapter哈希，后续owner字段/观测口径改动不反写旧回执。

```powershell
$env:PYTHONPATH='src;.'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& C:/PROGRAMING/python3.11.9/python.exe -m pytest tests/test_g31_circulation_original_workload.py -q
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.original_workload --scale 1 --binary build_g31_circulation/python/czr005_circulation.cp311-win_amd64.pyd --max-events 10000 --horizon 86400 --output outputs/experiments/g31_ics_long_term_20261013/p2_original_1x_native_next
```

每次使用新输出目录。完整源一直在分母，`max-events` 是计算预算、不是截取前N袋。`summary.json` 同时记录offered、真正执行到达的observed、loaded、completed、on_time、全部未完成、尚未观察、实体最终状态和接收租约；实际clock不足共同horizon时标记删失，不跨时域直接排名。完整逐袋结果及物理账以gzip流式落盘，默认不重复写完整native JSON，避免低磁盘条件下扩张日志。

适配器默认 `transfers=[]`，是无调拨控制组，不能冒充跨区预测运行。P3应对同一 `build_input` 返回数据启用实际 live controller，通过新请求驱动返供；没有预写答案。P2持续循环门还需该运行证据、权限恢复以及等待合同覆盖；P7还需完整1×/2×的足够预算观察、原规则压力组、同模型强参考和服务保护。输入工程、测试数和源表核对均不计论文主创新。

## 原图真实执行先导与失败诊断

新宿主 binding SHA256 `444832db5903092c29889b9084442ecef43af72a945fb8091abefbed617fff4e` 已接受原始零容量边；以下原件均包含全28506袋输入身份、逐袋结果gzip、完整物理回执gzip和独立盘/资源重放审计。目录根为 `outputs/experiments/g31_ics_long_term_20261013/`。

| 原件目录 | 库位因子 | 事件预算/实耗 | 实际观察时钟 | observed/loaded/completed | native调用wall |
|---|---:|---:|---:|---:|---:|
| `p2_original_1x_s4_native_001` | 4 | 10000 | 9893.931484 | 6/6/0 | 0.2043秒 |
| `p2_original_1x_s64_native_001` | 64 | 10000 | 10119.226620 | 12/11/0 | 0.2108秒 |
| `p2_original_1x_s4_100k_001` | 4 | 100000 | 13141.912150 | 105/16/0 | 0.9586秒 |
| `p2_original_1x_s4_100k_S3_reference_001`（同模型S3） | 4 | 100000 | 13141.912150 | 105/16/0 | 0.9558秒 |

`p2_reference_comparison_001.json` 直接解压比较100k事件S4/S3两场的物理事件账与全部逐袋结果，SHA256分别逐项相同；在这个共同删失时钟没有策略收益差别。它是同模型可行/失败轨迹对照，仍不是强优化参考或全日最优证明。

均触发计算事件预算，未到86400秒公共观察终点，不是完整日结果。库位4组实际占满4；库位64组只进入5，说明放大代理库位不能解决当前闭边/候选/接收与计算问题，且两组实际clock不同，不可用聚合J直接排序。无主动调拨基线不可能证明持续循环目标已完成。

100k组最终4盘Storage，12个未完运输段被一次性 `run()` 的 `finalize` 标为 `event_limit_reached` 并隔离，89袋等待真实空盘，28401袋尚未执行到达；这些全部在分母。**这12次是计算删失，不是物理不可行/故障恢复失败证据。**10k两组对应预算隔离分别2/6。新summary显式统计原因及budget-censored legs；旧回执不回写，原物理账保留相同原因可复核。

一次典型不可延续位置是97：入边97→98容量0保留关闭，图势仍含这条静态不可用捷径。静态闭边合法域应提前进入候选/后缀判断；单在最后入口拒绝会留下大量无效唤醒。这不证明所有105袋当前都物理不可行，必须与满库、后续可释放接收和事件预算区分。下一步优先原生权限安全的事件驱动wake与Session固定H分块，避免盲加数亿事件；不据0.2秒tiny进程时间认证完整100ms路由请求。

## 真实资源等待与本轮原图反证

`circulation_recovery_impl.hpp` 已实现实际资源依赖反向索引和generation去重：入边容量由真实EDGE_EXIT释放，目的泊位由真实离开释放，头距由已提交的next_entry到期唤醒，静态闭边/无合法后缀保持未服务状态。没有读取环境未来来安排重试，没有扫描全部队列做定时轮询。resource wait、两类物理索引及代际已进入native checkpoint封印。

`p1_build_002` 的二进制SHA256为 `a5a05762bca414f4d86d2470a823533e47d3f83ed96870d4e62b7437ccc1ada1`。`p2_recovery_after_001.xml` 的6项真实回归通过，包括10000秒满泊位后真实离开、长头距、长在途容量、闭边无忙等、两个等待点的parent/restore/sibling完整继续一致。修前5项失败保存在 `p2_recovery_before_001.xml`；不能把这些小夹具通过当成原图阶段通过。

同一新宿主的 `p2_original_1x_live_s4_001` 使用NativeSession分块100k，时钟仅14238.16044、observed154、loaded22、completed0，4盘Storage与18盘loaded全部保留，无`finalize`预算隔离。`p2_original_1x_live_trace_001/polling_diagnosis.json` 的10000事件诊断有4637次JUNCTION_ARBITRATION、4484次beacon，集中Storage入口112及29：成熟S4只尝试首选，无same-bag handoff时另一条物理可用候选不会自动被选；原等待域要求全部候选阻塞，因而仍0.25秒忙等。

后续补丁按真实首选候选登记依赖，并对所有一跳候选的实际queue/incoming/calendar变化登记排名唤醒。它仅在S3/S4时间罚项均已归零时停车；尚有连续时间评分项则保留原native调度，未假称已经证明所有评分交叉时刻。故障通知和合法route intent仍可触发重算。`p2_preferred_wait_before_001.xml` 保留了修前两项真实失败：可用但未选的备选导致预算耗尽；队列变化场仍产生884事件，超出<500的回归门槛。修后结果须以对应新构建原件为准。

deadlock escape边界也已阅读源码：当前circulation强制FIFO、S3/S4、DLP/G16关闭，escape的统一分数减项被S3/S4覆写，shield不据escape扩权，其余效果是让已经被选择的FIFO队首保有优先权。因此暂停无状态变化的重试不增加或删减该合同的合法动作；retry/deadlock计数与legacy不能混比。未来若放开非FIFO、S0或其他策略，必须重新证明等待域或加入明确阻塞阈值事件，不能沿用这份结论。

以上均是执行正确性和工程成本改进，不计新调度方法创新。

## 空盘返程拓扑与固定区内模块权限

`p2_return_contract_001.json` 对42个业务终点与11个loader的462对完整枚举，逐对保留正容量有向路径见证：200对满足跨区端点及当前固定port开关；226对有路径但端点同区，当前中央transfer不授权，必须由原区内模块实现；36对有向不可达（均返回loader92）。全部42个终点都至少有一个跨区可达loader，不存在整批终点均无合法拓扑返程的结论。

这些只是图和固定开关必要条件，真实导出还要盘已空闲、源库存下限、接收泊位、在途占用和正常业务保护。一个同区返程即使路径经过异区，仍不能据此冒充跨区授权。适配器未增加同区中央调拨、未修改原区内模块、未扩容。`return_contract_diagnostics()` 与新增两组来源回归已运行，`p2_adapter_tests_return_001.xml` 共17项通过。

`run_original_control.py` 提供完整原图的单NativeSession反应/预测同模型基线入口，按真实观测生成请求，源码输入仍`transfers=[]`。控制周期和wall/event预算是显式研究因子；默认300秒只是预算先导组，不认证完整100ms更新性能。逐控制边界落盘精简统计与真实请求，保留全部逐袋和物理账；进程退出后的controller JSON不是可恢复物理checkpoint，receipt明确需要重跑。R1安全合同、同区区内模块以及跨区预平衡论文机制仍须在主线独立完成。

## 共同终点、完整流负例及真实FIFO证据

`p2_original_1x_live_s4_002` 在build003 (`cf6d36e6…`) 以30877个native事件实际到H=86400，28506袋全部observed，22盘装载、0业务完成，独立191次完整traversal审计通过。计算轮询已解除，业务结果仍是负例；没有因到达H就把不成功认作完成，也没有预算隔离。

build005 (`0ff16d8ce3bdf7826773b8b187210e6d5458090da8e1543748ed92b9876c21a5`) 的 `p2_original_offline005_001` 重放同一完整输入hash `d9e065f51c4eb056e18fdbc7abb7dcacec938ff1e1e38010101de751ad52a30d`，再次到H=86400，wall30.84秒。准确offline原件显示Storage53队列runtime_id=[22,23,24,25]，依次为袋0→99、袋2→116、袋1→99、袋3→47；19500已全部实际release，只有头袋0的等待为`static_blocked=true`。不能把后面的可达袋2/3也称不可达。

真实接收依赖为112→53；29/137/150/139→112；136→137，共7个非空native队列、22盘。它是不可达FIFO头造成的链式回堵，没有证据称循环等待环。`native_offline_diagnostics.json`提供完整native队列/等待索引/leg-tray-bag映射，仅用于离线审核；在线controller没有得到该全局状态。后续不能通过跳FIFO、删首袋、擅自卸到未知异常区或扩容宣称解除。

`p2_same_horizon_control_comparison_001.json` 汇总build004同源控制器hash `ba9557…` 的固定H21600、900秒控制周期、原22盘完整输入对照：

| 组 | 全offered / observed | 反应与预测loaded / completed | 实际导出 / 接收 | 反应 / 预测owner compute峰值 |
|---|---|---|---|---|
| 完整1× | 28506 / 3485 | 均18 / 0 | 均6 / 2 | 33.56 / 138.65ms |
| 完整2× | 57012 / 6449 | 均17 / 0 | 均6 / 1 | 49.95 / 123.15ms |

四场盘/工序/资源独立审计都过，所有未到达袋保留分母。每个规模中两政策的全分母restricted-sojourn严格相同，预测产生更多请求和拒绝，不能写成业务收益。表内是预先固定发展观察窗，**不是完整日观察**。另 `p2_original_1x_reactive_001` 试跑完整H86400时在120秒wall预算后停止，实际H79200、总125.21秒（含收尾），owner compute峰818.2ms；该场明确删失，且控制器版本较早，不能与上表直接作算法优劣比较。当前完整100ms要求未通过，主线须优化并重测完整测量范围，不能改要求。

## 同源原图机制见证的独立研究域

`original_mechanism.py` 的选组规则在运行前固定：完整原151节点/227边、边容量与方向、节点4/Storage4/port合同全部不变，仅按真实完整业务各段与回到原loader的正容量静态可达性及跨区端点选择；按真实到达时刻选最早有足够合格袋的loader，再取该loader前N袋。母流28506条crosswalk全部记录资格理由/是否选中，不以仿真成功筛选。另立单盘因子，从原22盘中保留该loader原有的一盘，不增加物理资源。

静态资格统计：10320袋合格，15297同区需要原区内模块、1228返程不可达、740Storage阶段不可达、921直接阶段不可达。这些条件是顺序互斥分类，不是另一个全流不可达统计。首loader为26，2袋见证取原袋2/6，真实arrival=8875.816299/10062.62162、原目标116、Storage53、deadline22200均不改；24袋组按同规则扩大。`p2_original_mechanism_selection_001.xml` 两项来源完整性与全图不变回归通过。执行结果须看后续各机制目录，不能用这个子组替换上面的全流负例或宣称P7通过。

## 受限合同阻塞证书与修复结果

`certify_original_blocking.py` 对实际输入与build005全日末态作独立正容量图搜索，再核验真实FIFO/资源/任务阶段。`p2_original_offline005_001/fixed_contract_blocking_certificate.json` 的13个条件全部成立：Storage53四泊位全部被FIFO队列[22,23,24,25]覆盖；头leg22是原袋0的storage_out、目标99不可达；其他18盘全部仍需进入同一Storage；实际接收依赖链末端为53；没有空闲空盘、在途盘、接收租约、故障带或外部调拨带。

证书结论仅为 `proved_under_listed_fixed_contract`：保持原阶段目标、不可越头FIFO、on-carrier持盘、零容量视关闭、有限固定资源、不任意卸载/取消/创造盘时，当前22盘不能产生业务完成和可用空盘。它不是机场现场不可行性证明，也不是算法全局最优证明。破坏任一必要证据即退回unknown；`p2_blocking_certificate_tests_001.xml` 的6项包含空盘出现、可达头、FIFO缺项、故障带和任务阶段反例。

等待机制最终8项实编验证已纳入 `p1_p2_build004_subset.xml`；此前build003的7/8失败原件 `p2_recovery_after_002.xml` 保留。该失败为单候选额外登记排名依赖，提前改变实际唤醒原因；修复限定多候选才登记排名域，没有放宽原断言。事件驱动等待、状态封印、来源适配和这份证书属于正确性/工程，不计新求解方法。

## 原图同盘24次真实服务与时效缺口

build005 的 `p2_original_mechanism_2_005_001` 两法均2/2完成、一次真实返供，同一原托盘 `initial:26:0` 再次装载第二件；成对目标成本完全相同，保留无收益结论。

`p2_original_mechanism_24_005_001` 两法均24/24完成、23次真实跨区返供，独立物理事件审计通过，`source_changed=[]`。`actual_same_tray_event_table.md` 与JSON列出两法各24行的原袋ID、源arrival/deadline、前次导出、空盘接收、装载、真实Storage进入/释放、卸载及返程leg身份。第一件在8875.816299装载、9033.022进入Storage、19500实际释放、19772.592卸载；反应控制19802实际导出、20382.599实际接收后才装第二件，20812.397卸载。第二段没有提前创建可用空盘。

**两法均只有5件按时、19件超期。**有限单盘组的持续循环成立，不代表时效目标已达成，也不能用缩小原任务量获得的可行见证替代完整母流。反应/预测总arrival-to-unload为418514.272581/414198.867581秒，预测减少4315.405秒（约1.031%），每袋未比反应更差。这是普通解析预测匹配在一个预声明机制组的实验增量；没有主方法创新、普适正常分拣保护、现场能力或完整100ms认证。

## 最新同来源/同宿主完整流对照

`p2_same_horizon_control_comparison_006_001.json` 对build006二进制 `0bdd31835d8e9b7269bb2d45e14484054aad73abf3a10dc989f3574230b16190` 与解析控制器 `35d06c712c7cb24958dacab5b82099d7b7dcd23315a914f25908c12288f05a1a` 的四组作逐字段比较。每组独立完整输入、900秒同控制周期、H21600共同观察窗、Storage4和原22盘；全部到达H且源码运行前后不变。目录为 `p2_original_{1x|2x}_{reactive|predictive}_H21600_006_001`。

| 输入 | observed / 全offered | 反应/预测 loaded / completed | 反应/预测 owner compute峰值 | 配对目标差 |
|---|---|---|---|---|
| 完整1× | 3485 / 28506 | 均18 / 0 | 34.791 / 41.117ms | 0 |
| 完整2× | 6449 / 57012 | 均17 / 0 | 31.684 / 64.992ms | 0 |

四组全部业务结果与全部物理事件字段分别与build004对应组完全相同，0差异；同规模反应/预测的业务全字段也相同。优化降低解析成本，未产生业务收益。各1×有2次、2×有1次真实返供接收，仍各有一条 `departure_lease_expired_before_physical_entry` 失败保留；更多预测请求不能算改善。H21600只覆盖原来源前六小时，不是全日运行完成。

build005历史对照保留在 `p2_same_horizon_control_comparison_005_001.json`：1×对的源为531ea…，2×对为仅增加continuation状态字段的35d06…；不能谎称四组同源码。真实预测2×目录为 `_005_002`，其owner compute峰100.744ms；误漏 `--predictive` 的 `_005_001` 原件明确 `predictive=false`，作为重复反应组保留且排除预测结论。最新006四组按同一脚本顺序执行，避免本任务内部并发计时污染；仍存在普通主机抖动。

上述owner计时包含observe、预测/匹配及提交调用，尚缺需求出版序列化、接收端native复核/确认和跨进程传输。完整100ms要求仍未认证，不能因本次四个局部峰低于100ms就降格定义或覆盖旧超时证据。

## 原图首返供强参考：当前边界零headroom

`validate_original_reference.py` 按预声明规则读取固定60秒控制网格上的真实owner观测，选首个可见实际空盘且解析反应策略提出跨区返供的边界，不按分支收益选时点。24件组实际选中t19800、owner domestic；共同native checkpoint及已出版需求缓存保持，各分支替换同一当前epoch，后续next_tick与反应继续策略完全一致。仅六动作：WAIT、解析请求、出发时间增加1/15/30/60秒；偏移规则和相应expiry平移均在运行前声明，未用未来输入构造候选。

`p4_original_first_return_reference_006_001` 在build006上6/6真实分叉都完成H86400，修正后的参考器同时检查外层续跑状态、实际/请求时钟及native `horizon_complete=True`，独立物理审计全部通过，parent封印不变，源码不变。五种不同物理结果：解析请求J=418514.272581，+1秒被2秒消息延迟覆盖而相同；WAIT、+15、+30、+60分别增加60/13/28/58秒，且均不通过逐件不退化条件。六支均24完成、19超期。

因此参考headroom、候选池loss和排序loss在该有限域均为0，最优仅为 `optimal_in_enumerated_domain`，全局native最优unknown。它否定了在这个首返供边界仅靠这些合法时间偏移取得收益的预期，不能外推整个原图没有改进空间，更不能作为扩大残差训练的理由。后续须诊断真正耦合状态、候选覆盖和同信息强参考，保留区域自主与跨区预平衡两项要求。

## 全天迟时热点验收：100ms当前未达到

H21600不能覆盖旧818.2ms峰所在的76500秒。为核验这个已知热点，仅追加同一完整1×输入的反应组 `p2_original_1x_reactive_H86400_006_001`：仍用build006/35d06解析源码，900秒控制周期、Storage4/22盘、120秒wall与100000事件预算，不调物理参数、不延长失败预算。运行72.142秒实际到H86400，31276事件，28506袋全部observed且完整落盘；18loaded、0completed、28488等待空盘，所有28506袋已过截止。实际6次导出、2次接收、一条出发租约过期失败及3盘empty_transit均保留，独立资源/事件审计通过，`source_changed=[]`。

`late_compute_diagnostics.json` 直接读取逐控制日志并保留旧原件对照：同t76500、international owner、27975公开需求、0供应、0候选，由旧818.200ms降至136.725ms，其中observe43.404ms、预测/匹配处理93.317ms；同刻domestic为200.637ms。新全日峰为t83700的domestic：**211.262ms=observe87.080ms＋预测/匹配124.178ms**，28485需求、0供应、0候选。194次owner调用中75次超过100ms。

因此完整100ms要求目前**未达到**，不是仅仅缺少认证：已经测量的owner子集就超过门槛，尚未纳入的接收端确认等成本只会增加测量范围。旧热点显著缩小，但观察投影和无供应时处理全公开等待表仍有线性成本；不能以早时窗32–65ms峰替代此负证据。本次延长观察仅用于已知工程热点验收，不计研究方法工作量或算法收益。与全日无控制组同源/同H，但控制策略和宿主版本不同：无控制22loaded、本反应组18loaded、两者0业务完成，不要求轨迹等同、不从wall时间作算法速度比。
