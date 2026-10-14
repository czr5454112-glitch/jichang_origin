# Phase4 第十一轮：显式投射运行与入口头距边界

2026-10-11。承接[第十轮](PHASE4_STORAGE_SEARCH_AND_PROJECTION.md)，本轮继续处理原业务停滞，保留原始44袋对照、完整来源、用户C++及历史失败；本地未提交/推送。下面结果按实际证据补齐，不把设计、必要可达条件或原型通过写成现场能力。

## 1. 为什么需要显式适配

Round10尾界28500仍18/44完成，11只盘分别持原静态不可达袋。已实现的整父航班投射保存了原final与新final，但故意不被旧runtime接受。本轮增加独立运行类型，保持原runtime默认，只在明确研究合同下将已审核的投射目的地交给环境。投射改变输入版本，任何完成差异必须作为输入结构研究报告，不能称同OD的算法改善。

适配前完整重读raw/canonical/规范化来源和输入合同，固定Round10外部投射声明及内容SHA，再重算完整父航班域和选择。原任务所有字段、来源、截止、保护、release、旧段及有限盘保持；新目的地另列。输出来源账和完整映射属于环境信息，不进入policy参数；每件任务只在真实arrival后可见。运行最终卸载秒必须与投射必要截止界使用的秒一致，不能只检查ceil后tick相等。

## 2. 开发协议

预先保存 `phase4_round11_validation_20261011/PROTOCOL.md` 与冻结投射输入SHA。完整1×源先核验再按原第一到达秒起3600秒右开窗取全部44袋，不先切窗口再选择final。原输入/投射输入各h80/h21600，共四格；每格physics600 CPU秒/900wall秒、尾界28500、原11盘、K1实际请求/合同K4、10000work预算、固定FIFO/reactive代理、whole_route、原容量及同盘库位。chunk60tick检查，所有超界/失败保留。仅真实全部业务与盘义务排空记完成，不以无在途或预算结束代替。

保存同tick10080/11760/24180/28500原件（仅达到时）、周期与最终checkpoint、完整query和物理事件。原格同tick与Round10逐物理字段比较；投射格与原格仅描述不同输入版本，不用不同停止时刻J作收益比较。

## 3. 实现、反例及实跑结果

新增 `business_projection_runtime.py`，原 `business_runtime.py`、`business_inputs.py`、`business_projection.py` 均未修改。`build_projected_business_runtime` 强制完整source_inputs、外部投射声明、runtime声明和六项SHA运行合同；重读原始来源并逐对象比较，重新计算完整投射，再复用旧适配器建原公共初态，仅替换私有Bag的destination。精确卸载秒一致性单独检查，末尾重hash来源防止读取过程中漂移。输出为独立ProjectedBusinessRuntime，原任务及两目的地保存在环境侧。

作者44项通过，独审55项通过；独审自建2父族×early/direct×2×共8袋来源，包含闭边、混合保护、Decimal边界及两实体盘。攻击同时更改并重封original/projection/外部声明/runSHA，仍不能绕过原raw重读；另核对未来隔离、手算真实入库4/release251/最终卸载+hold和恢复。首次完整回归 **1399 passed / 0 failed / 0 error / 0 skipped，87测试文件**；parent CPU88.875秒内含pytest87.796875，普通四场景及恢复16分支child CPU0.578125另列。本数字对应首次适配器冻结，后续新增screen须另行验证，不以此冒充后续源全测。

全源1×28506/43603旧段、2×57012/87206旧段适配通过，早包15097/30194，360父族、360/720实例、11盘，初始公开0袋。4001/8002袋改final，其余保持，投射contentSHA与Round10完全一致。CPU187.984375秒包含1×64.5625及2×123.40625，不重复加；0物理。首次full_adapter_001错用历史manifest['outputs']而失败，CPU5.9375原件保留，修driver索引后另目录重跑，未改生产逻辑。Root未导入作者实现，对85518映射严格复算Bag并对旧独审来源，598680项通过、CPU7.96875；独审另从raw文本以Fraction重算时钟/保护/Bag，CPU10.0。两次审核有同产物比对重叠，不是新业务样本。

预声明四格均达到物理CPU预算停止，实际结果：

| 输入 / horizon | 停止tick | 观察 / 完整袋数 | 完成 / 完整袋数 | physics CPU秒 | parent CPU秒 |
|---|---:|---:|---:|---:|---:|
| original / 80 | 11760 | 41 / 44 | 0 / 44 | 600.65625 | 610.328125 |
| original / 21600 | 23880 | 44 / 44 | 18 / 44 | 600.375 | 610.421875 |
| projected / 80 | 11760 | 41 / 44 | 0 / 44 | 604.359375 | 661.171875 |
| projected / 21600 | 11640 | 41 / 44 | 0 / 44 | 609.125 | 666.28125 |

全部44袋均protected。投射仅改变16件final，源窗内有3件在短窗停止时尚未观察，仍在分母内。两个短窗同tick11760均J29427、0完成；两个长窗唯一预存共同tick10080均J879.5、0完成，完整Snapshot不同final字段仍各自保留。原输入10080/11760与Round10同horizon全部physical_result严格一致（仅_ms测量字段原函数统一排除）。不能拿投射11640的J21436.5和原输入23880的J387304.2相减当优化收益。原长窗18件均准时，但另外26件未完成、其中11件截止已过，不能以已完成子集宣称全服务满足。

Root四格原件763001项审核通过，CPU7.28125；独审容量/身份/真实存储与服务/成本/未来隔离/checkpoint审核CPU6.6875、0物理。独审两次工具失败CPU0.3125/0.296875保留：初误认为checkpoint.trace与result.trace形状相同，随后按源码识别result额外追加唯一当前tick显示标记后重新审核；没有改生产事件。另一个独审启动错误把pytest nodeID当路径，pytest尚未开始，CPU未知、工具wall0.657秒独列。Root逐袋配对/剩余状态分析另外计量，未观察任务未填0完成时刻。

## 4. 从投射长窗负结果继续修复

静态可达不保证共享容量可行。投射长窗出现2357次预算耗尽，到11640仍0完成。10200检查点11盘均有计划；明确追加10800检查点后发现袋7/tray92、袋10/tray138无计划，两条实际K1/h21600/原cache/10000work查询均耗尽，每条只验证一次完整候选，均被 `capacity:node:47@19684` 拒绝。另4盘已预约final47从19677/19678/19681/19682到INFINITY，恰满capacity4；不是库位53满容量，也不是原不可达任务没有被投射。

每条合法full witness的终点到达不晚于now+H，且终点节点预约到INFINITY，因而必含[now+H,INFINITY)；该尾区间已有他盘满容量即足以排除本查询域。存储路径增加中途约束，不改变这一必要条件。两条10800查询各有screen_work332的证书；实际完成/供盘/改路后必须重算，不能永久缓存成业务无解。诊断的两个原查询加两个记录validator原因的重放共4单独query、0物理，parent CPU1.265625；10200无可诊断loaded/no-plan，CPU0.421875/0query原件也保留。

原终点筛查包装只接受Regional，当前Simulation会自动套StorageCandidateGenerator，直接复用会拒绝或落入内层而绕过存储查询。因此新增显式存储筛查层与纯factory，保留完整inner、原cache和普通/空盘行为；未获证书或证书记录预算未知时仍交原搜索。安装限制、非法合同和恢复必须独审。另发现checkpoint深拷贝generator但保留factory：factory若持可变accounting将使恢复兄弟分支串账，因此采用纯冻结factory，每次新建独立账本。

独审先保留 attempt_004 的86通过/2失败：新包装器省略K时默认4，而原StorageCandidateGenerator默认3，这是实际兼容性缺口；另一个失败来自独审误把policy墙钟generation_ms当作确定物理字段。作者修默认3并加4路径完整候选tuple桥，独审仅按既有physical_result规则排除*_ms后，attempt_005的96项全部通过。含67次独立整数oracle、1256个exact状态及228次query，覆盖普通/存储/空盘、半开、多容量、同owner去重、zero-dwell、非法请求原诊断、预算与cache、factory/checkpoint/兄弟分支。作者第二次24项通过，旧23项和失败版本都保留。未显式K修复不影响此前显式K1真实查询，未为此重复运行同一诊断。

最终postfix全回归 **1519 passed / 0 failed / 0 error / 0 skipped，89测试文件**，parent CPU80.890625秒内含pytest79.96875秒，普通四场景/恢复16物理分支child CPU0.515625秒另列。最终212个源码/测试/C++文件与冻结快照一致；Round10原206文件全部未改，仅新增两个生产模块及四个测试文件。自有两份独审测试在本次full中有4个明确物理分支，其他旧测试内部物理次数未知，不能把1519测试数当运行次数。

追加实验先另写SCREEN_PROTOCOL.md，明确是在上述负结果后设计的开发修复，不重写原四格。inner仍10000搜索work，screen_work额外计入，不能称严格等总工作预算；新增部署仍受独立600physics CPU/900wall、原44袋/28500尾界约束。完整query/有序原候选/筛查账逐条绑定，certified另存当时完整公开Snapshot及SHA，真实状态序列化、压缩与哈希开销都包含在physics CPU中。正常返回每个query恰一账本行；异常中断则以execution_failure和最终checkpoint保留，不能声称异常路径也已写完整query流。

追加screen格最终在 **19620** 因CPU预算停止：全44已观察、0/44完成、44未完成、0件已过deadline；真实7次入库/6次出库、0托盘复用，J284171.5。physics CPU602.71875秒、wall616.810537秒；含完整全源准备的parent CPU654.921875秒。600秒上限按既定60tick块检查，超出2.71875秒计入消耗；没有跳时钟、放宽库位/截止或删除任务，未自动增加预算。原off止于11640的0完成与此格0完成均保留，不能因为物理时间推进更远就声称业务完成率提升。

Root `screen_window_audit_001` 共303379检查通过，CPU1.609375秒、0物理。共同10080及11640的完整physical_result严格相等；共同前缀2394条query逐一同时间、身份、目的和授权候选数，37条未筛查询的status及逻辑work相同。另2357条旧10000work耗尽空结果均由容量证书替代，前缀search work **23597364→27364**，额外screen work **790538**；旧query流没保存完整有序raw候选，不能把这一桥接写成全流raw候选相等，非空全候选保真由独立机制测试及物理桥另支持。

全追加窗口共18354次query：37次candidate_limit_reached、18317次证书排除，0次搜索budget_exhausted；累计额外screen_work6074458。筛查CPU9.453125秒、观察SHA CPU176.1875秒均已包含在physics中，不再相加。完整Snapshot额外保存和压缩成本也在其中；此批没有等仪器配对或随机执行顺序，不报告CPU加速倍率，不作为端到端100ms证据。可复核的改善是此类搜索不再反复花满原10000预算，业务完成率仍待更长完整周期证据。

只读 `backlog_analysis_001` CPU0.515625秒核对最终checkpoint/state/trace/非计时policy统计与raw一致：11盘全持袋，9有完整计划（6在途）、2无计划，33袋尚未装盘。改final的16袋为3有计划/1无计划/12等待，未改28袋为6/1/21，均未完成；两只无计划盘的当前终点47仍有满容量必要证书，44袋没有投射后静态路径缺失，也没有静态保护时间必要下界已超截止。库位53当前由bag `projected:1x:5` 持盘等待公开release20400；当前库存占用不是永久堵塞证据，仍有待执行合法计划。该分析不跑物理或候选查询，不将CPU删失或必要条件分类写成联合不可行证明。

node47此时尚无实际停盘，满容量来自四盘的将来完整承诺；最早承诺卸载19678比停止19620晚58tick，尚未发生，不能用预测替代实际完成。原44袋终点最大份额8/44，投射后node47有10/44（该点原3袋），HHI从0.072314升至0.084711。静态必要域和固定SHA排名没有保证容量平衡，这一输入结构负结果继续保留；不能根据已见结果修改固定映射后仍称原协议。

独立 `screen_window_review_001` 以最终冻结源核查容量、真实阶段事件、成本、未来隔离和checkpoint，CPU1.09375秒通过。另 `certificate_review_001` **逐条审核全部18317份证书、18354条query，没有抽样**，CPU91.46875秒、0物理；未导入生产calendar/validator，从完整候选和实际commit trace重新构造node/edge/reception预约，合入真实idle与旧在途占用，校对当时完整公开Snapshot SHA、按owner去重的半开容量及witness_slots。全部证书对应final47，首次query38@10434；累计screen工作与CPU均逐行相符，并再次验证共同10080/11640物理相等。

## 5. 入口头距：与边容量不同的义务

原用户材料没有给出现场入口头距数值、车道或供应方安全接口，因此h必须先作为独立声明的研究代理参数。单纯整段边占用不能表达最短进入间隔，不能从长度或容量倒推现场值。设计研究保留edge占用 `[d,d+travel)` 与entry占用 `[d,d+h)` 两种限制，尤其h大于travel时尾窗在盘离边后继续存在。已执行进入记录不可因同盘新路线或后缀替换而删除；同盘重入、幂等事件、checkpoint及兄弟分支须各自审核。

本轮入口头距研究先限独立原型及逐整数pair-gap参考，不混入业务物理运行。直接重读原docx与历史SHA一致；查阅[作者BHS控制论文](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf)和[TU/e原始研究](https://pure.tue.nl/ws/portalfiles/portal/218081823/0900580_AMBDapproachToImproveTheDesignProcedureOfTheTubtraxBHS.pdf)，记录其聚合流量/低层安全分工和release gap边界，未拿外部吞吐指标推现场h。

最终原型55289检查通过（含55245独立pair-gap对照），覆盖同盘重入、h>travel、不可撤销/后缀、重复通知、checkpoint和分支隔离。初版55279项虽通过，独审仍找到非法now=True/负数/None被接受的问题；先保存clock_probe_001真实失败，再增加严格整数检查和10项回归。全部五个计量原件共CPU3.84375秒、0业务物理/0路由query，重复穷举不算新增场景。清除过期记录后的迟到重复消息协议仍未实现，原型不是生产或W2幂等验收。详细影响矩阵、原文来源和全部反例见 `phase4_round11_headway_design_20261011/DESIGN_AND_REVIEW.md`。正式接入还必须贯通普通/存储路由、validator、提交与替换、实际执行、恢复、空盘控制、联合参考和W2权限；只改一个搜索器或只加validator并不完成头距支持。

## 6. 资源、范围与后续目标

最终源码闭合212文件：Round10原206份源码/测试/C++全部原样，新增两个生产模块和四个测试文件；独审closure CPU0.84375秒、Root源码closure CPU0.3125秒均另列在资源原件。HEAD仍为 `a23cf1c066d1087571b31733f0577c602040aa8d`，用户 `bounded_local_pibt.hpp` SHA仍为 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。最终只读复核无源码漂移，whitespace检查通过；Git提示C++未来换行转换不代表本轮已改其字节，本轮未触碰该文件。

资源对账中另保留一次失败：`final_001`误将screen比较目录复制的 `old_result.json` 当成新调用，多计诊断原件CPU1.265625秒和4次query。以复制文件SHA、比较receipt的baseline_result_sha256和原diagnosis路径共同证明同一次调用后，明确排除此复本；不对所有数值或SHA恰相同的独立运行泛化去重。原错误账本及其构建CPU0.390625秒保留，修后账本使用新目录，不能覆盖旧总数让问题消失。

修正资源账 `phase4_round11_resource_ledger_20261011/final_002/LEDGER.md` 已封存，pending0。已知去重上游CPU **3716.546875秒**（含两次draft构建0.234375秒及失败final_001构建0.390625秒），当前final_002构建CPU **0.3125秒**另列。49次明确物理调用为5部署+32普通桥+12独审tiny；旧full测试内未仪表化物理次数仍未知。88次显式独立query入口attempt为screen作者/比较84+诊断4，含故意非法测试调用，不等于88条成功路线，不包含所有测试或物理窗口内部query。嵌套pytest、physics、scale、screen、观察计时不重复加，启动失败的CPU、阅读/编辑/编排及最终文档核对开销未知，不能用已知和冒充完整项目总量；并发wall不相加。

完整来源适配不等于完整日物理运行；同源2×不是独立运营日。后续继续完整日/2×、off-carrier与独立库位/检索服务、同权限强参考、W2受限信息和联合学习评价；现场参数、逐件服务、端到端100ms及W4未验收，原两需求和TRE/CIE研究目标保持。

后续实现顺序仍以可复核结果为准：先从完整44袋原件区分计算截断、终点预约与有限盘/库位拥堵；投射静态必要域不能代替容量平衡，若研究另一映射须另存合同与版本，不能覆盖本轮预固定负结果。随后实现入口头距的实际执行/不可撤尾窗、checkpoint与取消权限，再贯通普通/存储搜索和同物理强参考，最后进入W2消息与权限验证。off-carrier与独立EBS服务仍需作为新物理合同处理，不能靠删除持盘任务或扩容回避。学习评价继续保留逐件protected服务与全周期成本，不能只以已有候选的标量平局宣布全动作域最优。

## 7. 审核证据入口

以下均为本地证据，等待用户之后明确命令再准备推送及网页GPT Pro交接包；未执行提交或推送。

| 内容 | 证据目录 / 关键文件 |
|---|---|
| 显式适配、完整1×/2×来源及失败 | `phase4_round11_projection_runtime_20261011/` 的 `full_adapter_001`、`full_adapter_002`、`FAILURES.md`、`manifest.json` |
| 两阶段全回归与独立攻击 | `phase4_round11_independent_review_20261011/attempt_003`、`attempt_004`、`attempt_005`、`attempt_006` |
| 原预声明四格及追加协议 | `phase4_round11_validation_20261011/PROTOCOL.md`、`SCREEN_PROTOCOL.md`、四格及 `projected_h21600_screen_001` |
| 全源85518条另审与四格原件核查 | validation 的 `full_runtime_tape_audit_001`、`window_audit_001`；independent_review 的 `full_adapter_review_001`、`window_review_003` |
| 真实终点失败定位 | `phase4_round11_projection_query_diagnosis_20261011/diagnosis_001`、`diagnosis_002` |
| 存储终点筛查、默认K失败与修复、仪器边界 | `phase4_round11_storage_terminal_screen_20261011/DESIGN_AND_RESULTS.md`、`RUNNER_REVIEW.md` |
| 入口头距原始来源、独立原型、时钟反例和正式接入矩阵 | `phase4_round11_headway_design_20261011/DESIGN_AND_REVIEW.md` |
| 最终源码闭合 | validation 的 `source_closeout_001/results.json`、independent_review 的 `attempt_006/source_snapshot/` |
| 全量screen证书与最终剩余任务 | independent_review 的 `certificate_review_001`、`screen_window_review_001`；storage_terminal_screen 的 `BACKLOG_DIAGNOSIS.md` |
| 最终去重资源账及错误账本保留说明 | `phase4_round11_resource_ledger_20261011/final_002/LEDGER.md`、同base的 `FAILURES.md`；`final_001`已作废 |

这些目录都位于 `outputs/experiments/ics_circulation_v3/`。每份计量原件以自身脚本/输入/源码SHA约束；重跑使用新的目录名，不覆盖历史失败。测试快照、source manifest与完整源代码用于审核实现，不能仅凭本MD数字通过验收。
