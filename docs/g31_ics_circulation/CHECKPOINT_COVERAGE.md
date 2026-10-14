# P1 原生 checkpoint 的覆盖与边界

本实现接续成熟 G31 的 `capture_state_checkpoint` / `restore_state_checkpoint`，没有重放 time=0、没有裸内存复制，也没有第二套 Python 物理推进。`StateCheckpoint` 是运行时产生的只读、进程内对象；没有接受任意 pickle 或未认证文件反序列化的入口。

## 暂停边界

- 支持每次 native 事件被弹出之前的安全边界，完整保留同刻微相位和下一事件序号。一个事件内部的候选计算、PIBT 事务与不可逆发布仍是原子步骤，没有声称支持函数内部 cursor 暂停。
- circulation 额外支持尚未 finalize、事件堆为空的 `Stopped` 静止边界。它可能仍有等盘业务，因此可恢复后提出新控制请求并真实继续。
- 不支持 finalized checkpoint、带剩余事件的事件预算截断 `Stopped` 或暂存事务内状态。旧 legacy 仍只支持原 live pre-pop 边界。

## 状态清单

| 状态族 | 捕获/恢复与身份绑定 |
|---|---|
| native 堆、序号、相位与时钟 | 原事件队列值复制；原有 sequence、time limit、微相位 floor、batch generation 全保留。新模式额外对每个 RuntimeEvent 的 traversal_id 编码，legacy golden 不变。 |
| 原 BagState、source/junction 队列、日历 | 原完整值结构捕获，包含等待/决策/失败、运输和预约累积。 |
| J2 / P2 / first-edge credit | 继续原 capability/controller/credit 专用 codec；重建请求快照、代际与能力，检查 capability bijection，不复制裸指针许可。 |
| 真实与已通知故障、beacon | 原 physical/advertised fault、代际、通知事件及受影响袋索引均复制。未通知故障不因 fork 变成在线可见。 |
| 输入与业务分母 | 完整 circulation node/edge/初始盘/jobs/transfers 值复制，包括未来尚未发生的环境条目、deadline、服务保护合同。属于离线完整状态，不是在线输入。 |
| 盘与工序 | mode、job/leg、驻留、edge from/to、接收授权、hold可用时刻、Storage实际开始、generation、traversal、入边通知已观察状态。 |
| 在途、供给与端口承诺 | transfer 状态/理由/送达/出发/接收时刻、不可撤在途接收位、leg身份、每边持续 next-entry 尾窗、下一 traversal id。 |
| 在线控制 | 版本化 route intents（含 traversal/generation）、待送达/已送达 demand messages、消息内已发布任务快照、条件 service forecasts、空盘 recovery intents、next_control_id，全在 CirculationState 与原生堆中捕获。没有 Python 定时器推进另一份消息队列。 |
| 资源等待与唤醒 | 按 leg 保存的当前 wait、edge/receiving/ranking 三个反向依赖索引、wait generation 及已排队 headway 唤醒均绑定；不能恢复时重新扫描生成一份不同唤醒次序。 |
| 结果、成本与回执 | 原结果累积及 deterministic replay 投影，加完整新生命周期回执与所有未完成业务状态。原来五类 legacy 投影本身仍不能单独代表新模型。 |
| 图、模型与缓存 | 目标 runtime 的图引用保持绑定自身 Graph；恢复前核对完整 topology/节点服务/heuristic 内容指纹。同构独立 Graph 可恢复，内容不同准确拒绝。S4 静态 hops/score 派生量重新初始化并逐项核对。正容量合法域势能/可达性缓存与域版本也逐字段纳入 seal。 |

`circulation_checkpoint.hpp` 显式逐字段编码新状态，以版本 `czr005.circulation.in_process_checkpoint.v1` 绑定到成熟完整状态摘要。`circulation_state_sha256()` 可比较完整停止/最终状态，包含私有未来带，**不得用作在线观察、模型特征、可见事件时钟或条件预测输入**。

mutable vectors/maps/strings 都属于各 runtime 的值对象。checkpoint 自身存储只读；原 J2 codec 对 immutable request identity 进行重建。恢复到以前运行过的目标时，清除本格式不支持的 G16 supervisor/model 可变缓存。G16 在线监督器的 checkpoint 仍明确拒绝。

不参与确定性比较的内容只有原有 wall-clock 诊断计时：decision latency 与 runtime wall seconds；诊断向量可以在进程内恢复，但不参与业务/物理一致性判断。所有逻辑时间、队列、决策、故障、成本、尾窗和结果分母均参与。

## 实际验证入口

`cpp/tests/test_circulation_checkpoint.cpp`：对正常循环、延迟故障通知、丢故障通知、已过期消息的每个实际 pre-pop 点捕获，构造两个 sibling，先执行 A 一个事件确认 B/parent 不变，再恢复 A 并让 A/B 分别跑到共同结束，比较完整状态摘要。覆盖装载、Storage、卸载、hold、真实在途、通知前提交与活跃 J2 能力。

此外检验：已提交未送达的 route/demand 消息恢复；A 授权取消未承诺返盘后，A 保留等盘任务、B 按原承诺实际完成；物理静止时 fork，只有 A 新提返盘并完成第二件；坏 seal/错误图 fail closed；物理合同与未来带变化使离线 seal 变化。未来带在线不可见由 Session 观察层的成对隔离测试另行验收，不能由离线 seal 相等代替。

闭边回归另含两种真实反例：当前首边容量为0，或短路的下游边容量为0而短后缀已不可达。新模式保留原图方向/边数与原 heuristic 字节，使用共同的 `capacity_positive_service_potential.v1` 静态域；仅依赖声明合同，动态故障或未来事件不参与。S4 首选被 `edge_closed` / `no_static_legal_suffix` 拒绝后可尝试已经生成、通过完整 shield 的合法局部备选。两个反例均要求真实走原有长路并完成，同时检查 checkpoint 重建后结果完全一致。这是修正新物理域的工程适配，不是新算法贡献。

原 `test_circulation_runtime` 的“不支持 checkpoint 应拒绝”断言按已实现能力升级为真实恢复并继续的完整 hash 对照；目的服务拒绝等其他旧断言保留。成熟 `test_g4irsf14_state_clone_protocol` 继续检查 canonical 原图上的队列、故障、能力和 legacy 五类结果不变。

上述是 P1 工程正确性证据，不构成算法创新、最优性或 100ms 单任务更新证明；正式继续策略标签仍须通过信息、候选覆盖与标签诊断。

## 本轮冻结验证

`outputs/experiments/g31_ics_long_term_20261013/p1_checkpoint_validation_001/receipt.json` 实际记录3个目标的6条编译/运行命令均exit=0，头文件与translation unit前后SHA256相同，状态passed。专项5场共有611个安全事件断点，每点恢复两条完整分支；其中46个断点有活跃J2能力，48个断点有真实故障。装载、存储、卸载、hold、原生资源等待/唤醒均经过实际继续验证。附加测试包含在线消息/取消动作分支、静止状态重启、坏seal后控制入口不能复活、错误图、两种闭边合法域反例。

headway场的历史开发轮为358个事件边界、220个边界处于资源wait；定位到成熟dispatch末尾还有一次兜底retry排队。采用circulation限定的已注册resource wait门控后，冻结轮为138个边界、1个实际wait断点，仍完成服务且所有fork等价。开发失败/阶段日志留在`build_lt_checkpoint/`，没有重写成最终通过。减少轮询是执行效率修正，不是主方法收益。

`legacy_parity_001/receipt.json` 又核对原独立基线的pinned可执行文件与fixture SHA256，然后重新执行pinned并实编/执行当前fixture。无故障和真实故障两场的全部五类确定性输出相同，源码未变，三条命令均exit=0。这是固定小图的兼容性对照；`test_g4irsf14_state_clone_protocol`另在canonical原图验证原checkpoint协议。没有把两场对照宣称为全部历史论文工作负载复跑。

随后`native_compat_001/receipt.json`在独立`build_lt_native_compat/native_compat_001`完成全部17个原生程序的clean编译和CTest：15个既有程序、原circulation程序及新增checkpoint程序。配置/编译/测试3条命令exit=0，56份编译来源前后相同，17份可执行文件均有SHA256；JUnit独立数得17通过、0失败/错误/跳过。总195.11秒，CTest实际8.39秒。这是该冻结版本的结果，后续仅新circulation route接收语义修补需保留新构建与定向回归，不能把本轮001回执直接移植到未跑的新源码。

重跑命令（为保留历史须选新output目录）：

```powershell
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_checkpoint_native --output outputs/experiments/g31_ics_long_term_20261013/p1_checkpoint_recheck --vcvars 'C:/PROGRAMING/visual studio/Visual studio/VC/Auxiliary/Build/vcvars64.bat'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_legacy_parity --output outputs/experiments/g31_ics_long_term_20261013/legacy_parity_recheck --vcvars 'C:/PROGRAMING/visual studio/Visual studio/VC/Auxiliary/Build/vcvars64.bat'
```

Windows专项工具使用直接cl实编避免本地化showIncludes造成增量误复用；跨平台注册入口为CMake的`circulation_checkpoint`测试。新模式完整状态只支持上述受控进程内schema；没有实现持久文件版本迁移或任意历史对象加载。

## 后续003冻结与信息审查

`p1_checkpoint_validation_002` 在新增route接收静态后缀/已通知故障检查、ranking依赖、service forecast和在线ID隔离后实编3目标，6条命令全部成功，40份源码前后不变，100.52秒。5场仍为611个断点。附加测试实际确认预测消息的未送达状态可恢复、分支送达隔离、投递后仍保留发送时payload、未到达任务/未来故障不改变预测、非法预测不修改状态，以及不同配置的checkpoint恢复后使用真实恢复配置中的服务时间下界。`legacy_parity_002`另外实编并对照pinned基线，38份源码前后相同，2场全部10类hash一致，26.11秒。

`publish_service_forecast(source_owner,target_owner,tray_id,next_node,delay)`只允许当前owner本地loading/loaded且尚未提交入边的真实盘。loading入口估计取已记录LOAD_START+公开load_seconds+源native服务时间；loaded取now+源服务时间。release_estimate只到下一节点native服务完成，observe明确给出`estimate_scope=next_node_service_completion`、`status=conditional`。它不是最终卸载、hold结束、可用空盘或资源授权。预测消息含bag/tray、from/next、generation/traversal、观察/投递时间；native延迟事件只改变delivered，不刷新snapshot。错误owner、非真实有向边、目标owner不符、已进入边、未观察装载或公开闭边均拒绝。

只读信息审查另发现在线submit/cancel可能查询或取消尚未issued的预装环境transfer。修复明确分离命名空间：预装transfer禁止`live:`前缀；在线提交要求`live:`加非空后缀，语法拒绝先于任何环境查找；cancel忽略尚未issued请求。这样不会靠仅过滤来制造重复身份。`probe_future_transfer_namespace.py --require-fixed`的`future_transfer_namespace_after_002`已在SHA256 `cf6d36e6f146e7e7d028f0e063201b3f524f4e7948d3dcf420347fd49eafa759`本机binary实际通过：不同私有未来带当前observe相等、猜ID提交得到同一格式拒绝、cancel均unknown且不改状态。after_001保留实际沙箱WinError5；未把它冒充代码失败。旧build002的binary已被后续build替换，因此此问题记录为静态发现加真实修复后验证，没有伪造修复前运行回执。

新增`tests/test_g31_circulation_service_forecast.py`由统一Python验证入口实际验收owner可见性、真实延迟、checkpoint继续、payload不可变及未来带隔离。上述均属信息合同/执行正确性接通，不能据此宣称预测控制已有收益、100ms达标或方法创新。allocation failure的跨容器追加事务尚无故障注入证明；常规无效输入与checkpoint校验失败按明确拒绝/Idle fail-closed语义检查。

## 005冻结：已执行的私有计数反例与修复

发现并实际运行了两个独立侧信道反例，原始输入/观察/二进制SHA256均保留：

- `private_message_counter_before_001`：另一owner C只增加C→C的私有需求发布。B的既有观察完全相同，但随后A→B收到的消息ID因全局next_control_id不同而变，泄露无关owner控制活动。
- `private_traversal_counter_before_001`：不相交C子图只增加一次私有运输。A的真实首边入边时刻、盘、bag和其余观察均相同，公开traversal_id却从1变2。原因是直接暴露了全局next_traversal。

修复保留内部全局traversal身份和完整离线事件账，在线`traversal_id`改为盘内`public_traversal_version`；route的expected_traversal接收/执行比较与forecast快照都使用同一公开版本。消息ID改用(source_owner,target_owner)通信通道序号；`publication_sequence`让同刻乱序消息仍能按发送顺序处理，不以不透明ID字典序伪造因果。新增公开版本与通道计数逐字段纳seal。

005 pyd SHA256为`0ff16d8ce3bdf7826773b8b187210e6d5458090da8e1543748ed92b9876c21a5`。`private_message_counter_after_001`、`private_traversal_counter_after_001`、`future_transfer_namespace_after_003`三项`--require-fixed`都实际exit0；前两项均确认原反例的before/after完整观察现在相等。没有掩码、随机化或去掉正常分拣身份检查。

`withdraw_service_forecast(source_owner,original_message_id,delay)`只撤发送者自己的条件估计。它通过原生延迟事件向原target投递immutable `kind=service_forecast,status=withdrawn,supersedes=原ID`，不改原forecast、不撤硬transfer或接收承诺。首次publish/withdraw返回message_id；重复撤销无新事件或计数增长。tombstone可先于原消息到达，接收器须保留它来抑制迟到原快照；具体保护收益仍需同信息实验，不能从接口存在直接推断。forecast的发布序号和supersedes也纳seal。

每个source→target的online demand现仅暴露最新已送达快照，按(observed_at,publication_sequence)选择，迟到旧快照不会覆盖新状态；完整消息历史继续保存在原生状态与checkpoint，service/tombstone未被错误裁剪。这减少在线历史任务重复复制，是否达到100ms仍以完整pipeline实际计时为准。

`offline_diagnostics()`明确标为离线审计接口，导出实际native junction/source队列、leg等待依赖与三种逆索引、tray.active_leg及内部/公开traversal。它不进入observe。`offline_wait_identity_001`实际检查两个真实等待：满接收位上的runtime_id=0，以及同盘复用后的runtime_id=3（仅2个业务job，不能误当job index）。队列成员、active_leg、edge合同索引、反向generation双向一致；fork恢复相同，导出修改不改变native state。

资源wait的单候选ranking wake修正后，`p1_checkpoint_validation_003`实际单目标通过，38份来源无变化，43.49秒。所有005新增状态/撤销流程后的`p1_checkpoint_validation_004`再次实编单目标，38份来源无变化，46.59秒；611个安全断点完整双分支继续、新撤销先到/幂等/硬物理不变/恢复一致均通过。旧17/17、三目标002和legacy parity002各自绑定其冻结版本；没有冒称它们已经针对005所有新源码整套重跑。

## 006冻结：同刻终点完整性

独立参考审查发现真实005在H=.1耗完单次预算后仍有8个同刻事件，却仅按clock==H报告reached。006 binding现在同时要求内部无time≤H事件，返回显式`horizon_complete`；内部下一事件时刻不进入在线observe。严格区分“预算恰用完但全部到期事件已执行”与“同H微阶段截断”，不改物理事件顺序或checkpoint状态内容。

`p1_build_006` clean构建50.13秒通过；`p1_checkpoint_validation_005`实编单专项42.57秒通过，38份来源前后相同、611个安全边界仍完整分支等价。真实Python回归检查同刻继续、checkpoint重放、全局event limit以及无剩余事件的正例。详细修复前后回执、有限参考传播修补和独立65项/29组证据见`ANALYTIC_INDEPENDENT_REVIEW.md`。这些是完整性修复，不新增最优性、方法创新或100ms证明。

## 009冻结：真实 ACK、重试与 owner 不可用

opt-in `owner_protocol` 把 transfer 请求的 ACK、超时、重试和 owner down/up 放入同一个 native 事件堆。`circulation_protocol_impl.hpp` 中的协议配置、客户端已知请求、已送达 ACK 快照、请求 attempt、ACK emission sequence、待回应 attempt、丢包计数及 owner 不可用计数均加入 checkpoint seal；已有堆保存相应的事件相位和顺序。disabled 默认模式不增加协议摘要段，保留既有默认 circulation 的状态身份。

这是 transfer 协议子闭环。`observe_protocol` 只提供本地物理投影、客户端请求状态与实际收到的 ACK，不把尚未收到的模块处理结果或 owner 版本暴露给客户端。ACK 的 status 是发出时的快照；`acknowledged` 不代表托盘已经收到。旧 ACK 可晚于新 ACK 到达，不能按最后到达包的 attempt 判断是否收到最新尝试的回应；实际 delivered attempt 和不可变 ACK 记录一并保留。离线完整结果、状态哈希和 checkpoint 仍仅用于可信诊断，不是在线特征。

请求 ID 采用带 UTF-8 字节长度的 owner 命名空间 `live:<length>:<owner>:<suffix>`。同 ID、同 payload 的迟到重试（包括原出发租约过期之后）不会新增实体转运；冲突 payload 在写状态前拒绝。owner 不可用期间，源端或接收端都不能新增授权；已经授权出发的运输和本地正常分拣继续。半开时间窗与已处理的不可用计数共同覆盖同刻微阶段、相邻及重叠 outage，不依赖恰巧先处理 down 事件。

`owner_protocol_tests_001/receipt.json` 为009上的21项专项全部通过，覆盖未送达状态不可见、same-clock恢复、稳定重试、重复 ACK、溢出前拒绝及跨配置恢复的静态 owner 索引。`owner_protocol_native_002/receipt.json` 有10场真实事件账：正常、首次 ACK 丢失、65秒迟重试、旧 ACK 重复、源/接收 owner 不可用、相邻 outage、已出发承诺、恢复时重复 wire、拒绝 ACK 丢失。每场实际 checkpoint 后 fork/restore 的全部未来结果相同；9场完成同盘两服务，拒绝场保留第二件未服务业务，零授权。没有把拒绝场计作业务成功。

009源码另经 `p1_checkpoint_validation_006` 实编三个原生目标，6条编译/执行命令成功，82.73秒，source_changed=[]；原5场611个事件边界仍双分支等价。`legacy_parity_003` 对照成熟46cc46基线，两场、每场五类确定性投影一致，21.65秒。`live_validation_006` 为当前 circulation 和关联模型回归277项通过、零失败/错误/跳过，16.47秒；它不是全仓1519项复跑。

协议模式目前拒绝旧 observe/submit/cancel/route/demand/forecast 在线入口，避免绕过其观测边界。因此既有解析 R1/R2 控制器尚未接入这个新通信故障模式，不能宣称已完成两控制层的故障恢复。后续须显式增加各消息族的合法投递/确认接口，并在同一模式下运行强基线和主方法。

## 010追加：消息族与显式控制器状态接通

以上009段保留其冻结时的 transfer-only 范围；本段记录010的新实现，不把010能力追记到009回执。010 pyd SHA256 为 `079eaaeae53671d1a7d2a26437478850b329db80ec8eebc58b1fa70f5f0ddb7f`。旧默认关闭协议的入口继续保留；启用协议时仍拒绝旧在线入口，由 `submit_protocol_transfer` 和新增 `submit_protocol_command` 执行控制，不能切回旧入口读取未收到的结果。

`submit_protocol_command` 支持 `route`、`demand`、`service_forecast`、`withdraw_service_forecast`、`cancel_transfer`。命令的 wire、timeout、ACK及owner恢复都在唯一G31原生事件堆中执行。请求ID使用相同owner命名空间，跨消息族和transfer的ID冲突也拒绝；重试使用同ID、同payload，不能重新发布一份需求或重复安装一次路由。route的最终ACK来自真实原生校验结果，pub/withdraw的最终ACK来自目标owner实际收到消息，cancel只能撤尚未承诺的transfer。

协议seal段升级为 `native_owner_command_protocol.v2`，逐字段包含命令payload、源端执行状态与时刻、真实完成状态与时刻、客户端状态、到达attempt、待恢复attempt、ACK发出和送达序号、丢ACK计数、等待源/接收owner的标记，以及全部不可变ACK快照。transfer ACK另保存实际实体 `received_at`，仅在其快照状态为received时有效。既有原生堆继续保存所有未投递消息、ACK副本、timeout和恢复事件的时刻、相位与sequence。静态owner及签名排序索引属于派生缓存，initialize/restore后重建；未发布未来业务仍须经当前真实状态过滤，不因建索引进入在线观察。

`observe_protocol` 与 `observe_protocol_control` 不导出旧transfer真值、route/recovery请求真值或旧owner版本。两者的 `client_transfer_ledger` 只由本人已提交payload和实际送达的ACK推导；已收到的取消命令ACK可证明相应未承诺请求已取消。紧凑投影的incoming抵扣也使用这个同一客户端账，不读取隐藏的模块处理阶段。超时或仅收到pending/granted快照不能释放未决盘承诺；`received_at` 不能用较晚的ACK `observed_at` 代替。

### 原生与Python一起续跑的已实现边界

`scripts/experiments/g31_ics_circulation/protocol_control.py` 现在显式保存所有该控制器用到的公开控制tick状态：配置、起始时刻、下一tick、已发布需求签名、区域路由记录、预测及撤销生命周期、预测历史，以及客户端owner序号、不可变outbox payload、已知ACK、终态和下一retry时刻。JSON往返只保存这份Python控制状态；实际物理、消息队列和未送达ACK仍由同一原生checkpoint恢复。正常续跑必须同时恢复两部分，并使用完全相同的控制配置。

验证允许在已完整推进的时域端点切分，包括两个公开tick之间的H；续跑从保存的下一tick开始，不能在任意切分H额外插入一次refresh而改变历史。正常、丢ACK、重复ACK和owner不可用的完整运行与 native checkpoint＋JSON controller state 的分支续跑，比较业务、托盘、transfer、事件账、leg身份、完整状态摘要及controller state。它是本显式控制器的继续合同，不是任意外部回调、学习策略或网络服务都已支持恢复的声明。

若事件预算在一个控制tick/同刻微阶段截断，则返回 `budget_exhausted`、`result=None` 和 `control_boundary_complete=False`，保留真实已处理前缀与诊断。该失败分支不会调用 `result_at` 隐性补跑，也不能将这份部分tick控制器状态当作可继续的完整状态；再次传入会明确拒绝。原生安全事件断点与Python完整控制边界不是同一概念。没有实现跨进程的持久checkpoint文件、崩溃恢复、任意pickle加载或009对象向010的持久版本迁移；可序列化Python状态本身并不提供这些能力。

### 010已核对证据与统计口径

`live_validation_008/receipt.json`、JUnit和原始stdout记录 **320项通过，0失败/错误/跳过，exit=0，19.912秒**，`compiled_source_mismatch=[]`、`source_changed=[]`。先前 `live_validation_007` 的真实失败原件保留：320项中1项在pytest临时目录fixture建立时发生 `PermissionError: [WinError 5]`，路径为用户Temp下的 `pytest-of-38908`，0断言失败、1错误、exit=1；008改用本轮独立工作区临时目录后完整重跑，不把007改写为成功。

`protocol_command_tests_010_001` 与独立重复留档 `owner_command_tests_001` 各记录同一组68项通过：新commands20、旧transfer21、projection8、regional9、service forecast10。**这68项已包含在320项中，技术重复及009历史21项均不得再次累加。** 320是当前相关回归范围，不是全仓1519项重跑。

`protocol_control_native_010_001` 预先声明7场×4策略，全部推进到共同H=50且物理账审计通过，保留各场 `run.json.gz`、输入、审计及已送达观察。实际业务结果并非全部成功：ordinary的joint完成2/2且只有1次真实返盘；receiver_refuses的四策略均只完成1/2、0次实体返盘，第二件仍等盘；known_service_ack_loss的R1-only只完成1/3，而三种带R2的基线完成3/3。该已知服务场后三种基线成本同为26.1，不能将工程接通写成新增预测收益。`reached`只说明到达共同H，`audit=passed`只说明账的约束一致，均不等于全部业务完成。

这些结果支持010通信接口、解析R1/R2基线及显式续跑的正确性接通；不构成主方法创新、全局最优或P7完整100ms通过。本段不借用009的legacy/checkpoint运行结果替010做认证；010的新全日性能、原生checkpoint重编和成熟legacy对照由其各自独立回执另记。

## 011追加：实际需求快照身份、route ABA与严格时域

后续独审实际复现了010控制器的两种缓存问题：需求提交时缓存的空队列签名，不等于延迟到source执行时实际采样的队列；队列在两次公开tick之间经历空→Y等待→Y真实装载→空后，远端可能永久保留Y。区域路由则可能经历A→B→A，而历史A的成功ACK被误当作A仍在安装中的证明。原010源码、二进制和失败前探针保留，不能以本段修复抹去其边界。

011 native改动仅位于binding，pyd SHA256为 `19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec`。实际已送达且status为delivered的demand ACK新增 `captured_demand_signature`、`captured_demand_observed_at`、`captured_demand_publication_sequence`。它们由ACK `result_id`所引用的已seal、不可变 `CirculationDemandMessage.jobs` 推导，不查询当前队列；先严格核对native索引、消息ID、source/target、执行和交付时刻，匹配失败明确拒绝。仍在pending或尚未送达的旧ACK不能因后来实际发布完成而获得这些字段。

当前本地队列签名与历史快照签名共用相同排序、字节编码和SHA256 helper。binding仅缓存历史消息的digest字符串，每次返回新的Python字典；它是可重建派生缓存，不增加原生协议状态或checkpoint seal字段，initialize/restore时清空，fork通过restore重建。修改返回字典不能改变后续ACK或原生状态；恢复到同索引但不同内容的checkpoint不能复用旧digest。

控制器schema升级为 `g31.protocol_controller_state.v2`。需求按owner→target分别跟踪至多一项未确认publication，同ID重试仍指向原采样；只有实际delivered ACK中的captured签名等于当前本地签名，才允许省略下一份发布。终态拒绝按重试间隔等待后提出新intent。区域路由另外保存当前业务/盘/阶段的active intent，在前一个结果明确后比较当前实际请求，而不是遍历历史成功路由来决定是否跳过A→B→A的最后一次更新。历史v1 controller state因结构和语义不兼容而显式拒绝，未做无证据的自动迁移；Python客户端outbox自身版本仍独立管理。

控制tick只在 `tick_time <= horizon` 时执行，不再用epsilon授权推进超过请求H的事件；请求H早于当前物理时间在推进前拒绝。`protocol_tick_boundary_after011_001` 实际以 `nextafter(.61,-inf)=.6099999999999999` 验证未提前执行.61的tick，split返回物理时间不超过H，继续后与完整运行一致，过去H拒绝且状态不变。部分tick预算截断仍保留 `result=None` / `control_boundary_complete=False` 并拒绝普通resume；严格时域修复没有扩大这一恢复范围。

`protocol_demand_capture_after_011_001`、`protocol_route_aba_after_011_001`、`protocol_controller_after_011_001`及上述tick探针均实际passed且source_changed=[]。需求探针确认真实装载后远端被纠正；ABA探针确认首次A租约仍有效时也真实提交并完成新的A更新。`demand_ack_signature_tests_004`另有7项新binding专项通过，覆盖真实空→等待→装载变化、未送达/旧pending ACK隔离、丢ACK重试、接收停机、Unicode/有符号零的canonical一致性、历史快照不刷新与派生缓存恢复。001—003的测试开发失败日志保留：非法同区调拨、空fleet以及把EDGE_EXIT时刻误当真实接收/装载开始；最终断言依据完整native事件账分别核对.35真实接收与LOAD_START、.45装载完成，没有修改物理权限或生产实现来通过fixture。

`p1_checkpoint_validation_007`的42份编译来源与`legacy_parity_004`的40份编译来源在011 binding修复后逐项核对仍无差异；这两份既有原生回执各自passed、source_changed=[]。该核对说明其实际编译的C++ runtime范围未被011改动，不声称它们在011后重新执行，也不能代替新binding/controller回归。011完整回归计数、新全日性能和业务比较须依据后续对应回执另记，本段不预报通过数量或P7结论。

随后完成的 `live_validation_009/receipt.json` 与JUnit实际记录011相关回归 **342项通过，0失败/错误/跳过，exit=0，20.642秒**，binary SHA256与上述011相符，`compiled_source_mismatch=[]`、`source_changed=[]`。7项binding、11项原图runner、三项新增probe回归以及此前68项专项都已包含在342中，不叠加计数；这也不是全仓1519项重跑。测试通过不改变前述部分tick、持久恢复、业务未完成及完整100ms认证的边界。
