# 服务、物理与在线信息合同 LT-1 / on-carrier 开发域

2026-10-13 起生效于长期开发实验；不追改上一阶段结果。

所有 offered jobs 保留业务身份、原到达、目的地、截止与 Storage 工序；业务完成是最终卸载，运输段完成不是业务完成。未观察、等待、未装载、隔离、失败、逾期和预算删失都保留，未完成耗时不能填零。观察使用共同预声明时域。

物理硬约束：真实盘守恒、有限停放/在途/接收/库位、跨周期头距、固定有向图、关闭边、实际装卸/hold与工序先后、不可撤的已入边前缀。调拨只能由源 owner 请求，源模块先加载本区已到等待任务并保留 min_stock，接收模块可拒绝。预测只是意图，不能产生盘或接收授权。

服务义务：`protected_service` 标识须保留的业务义务；不得改目的、截止、工序或取消任务。`allow_suffix_reroute` 是单独的路线修改许可，默认关闭；请求无许可准确拒绝。新方向必须保留当前业务/盘/阶段身份，并通过当前版本、真实容量、JIT 与原生提交检查。静态截止必要界只用于排除不可能候选，**不是所有任务的事前截止保证**。未知未来条件下尚无逐件不增时证书；方法比较必须使用同源/同物理的正常服务成对验收，若退步则不晋升该方法。不得把均值改善或 `deadline_met` 事后统计写成已证明保护。

`updated` 表示当前合法可替换方向偏好已安装，并非全程硬路径、全部未来可行或按时证书。消息到达时位置/代际/入边前缀过期则拒绝；旧合法操作仍由原生G31继续。旧路已经失效时不能声称 valid_old_route。实时性尚待全过程计量，事件耗时不替代100ms。

在线策略仅读取 owner 本地已观察状态及已送达消息；静态拓扑共享。完整任务带、未来故障、未发布任务数、环境事件堆和全状态hash只属环境/离线审计，不进入策略观察。远区需求通过带观测时刻的消息快照到达；不得在目标端即时刷新快照内容。

当前现场未知：节点空/载等待许可、有限泊位、EBS真实服务与固定区内模块接口。明确有限泊位且允许等待的研究代理可以继续算法研发，但不构成现场验收。原表节点服务不重复作为额外装卸；关闭边容量0保持关闭。on-carrier与未来off-carrier保持独立合同。

状态恢复只支持原生事件原子边界；可信进程内 checkpoint 可用于同宿主续跑，未提供任意对象文件反序列化。控制器本身需要有显式状态且纳入共同继续策略；仅复制物理状态不能自动证明任意外部回调/网络模型已被复制。

补充（build005）：原表全部227边容量与 `floor(length/2m)` 一致，零值是已核实源记录；将零解释为关闭是保守研究合同，尚非现场结论。固定FIFO、on-carrier、有限库位与这个解释共同造成的原图回堵，不能归因为机场实际不可运行。不得删不可达业务、绕过队首或扩库存伪造全流成功。

在线 transfer 请求使用 `live:` 非空后缀命名空间，与预置环境请求隔离。公开运输版本按盘计数，消息版本按源/目标通信通道计数；内部全局审计身份不改变。未发布请求查询不泄漏未来带。当前隔离保证针对受信策略接口，不是进程沙箱或实际网络安全认证。

服务预测只针对真实已观察的 loading/loaded 业务，描述条件下一节点占用与服务释放，不表示盘已空或可导出。软预测支持真实延迟、乱序及撤销；撤销不能撤掉已授予的硬接收权、在途盘和已执行路径。

009新增可选 `owner_protocol`，transfer 的 ACK 延迟/丢失/重复、超时重试、owner 不可用与恢复均由 native 事件驱动，配置及可变状态可 checkpoint。不可用区间拒绝新增源/接收授权，既有在途义务及本地正常业务仍继续；这不是实际主机进程崩溃重启、网络服务部署或现场故障模型。只有实际收到的 ACK 可进入客户端观察，ACK是响应时快照，不代表最终接收。稳定的带owner字节长度请求ID支持租约过期后的同payload幂等查询/重试。10场事件账及21专项回归见 `CHECKPOINT_COVERAGE.md`。新模式目前拒绝旧 observe/route/demand/forecast/submit/cancel 入口，现有R1/R2控制器尚未接入该协议；不能把transfer子闭环称为完整两层算法的故障恢复。

有限参考只有真正到达共同目标H的 native 继续分支才能进入成本与最优性比较。已执行前缀通过物理审计并不证明运行完整；预算删失、缺失/矛盾完整性证据均保留 unknown。认证范围仅为给定单次动作域和固定继续策略，不是全局最优。

## 010追加合同：受限消息族、实际ACK与控制继续

上文009的transfer-only与“R1/R2尚未接入”是当时的历史边界。010已通过新增命令接口及显式 `protocol_control.py` 接通解析R1/R2基线，仍保留旧默认模式；并没有把旧接口直接放开到故障协议模式。

| 协议入口/消息族 | 实际处理和确认合同 |
|---|---|
| `submit_protocol_transfer` | 真实请求须经源/接收模块可用性及原权限检查；ACK为处理时快照。已入边运输、已兑现接收lease及正常区内服务不因控制owner停机而撤销。 |
| `submit_protocol_command(kind=route)` | source owner实际处理后排入原生route校验；最终ACK为 `updated` 或 `rejected`，不是“请求入队即更新”。Storage阶段、当前bag/tray/generation/traversal及服务修改许可仍复验。 |
| `kind=demand` / `service_forecast` | controller→source的 `message_delay` 后，source必须实际可用才采样；快照 `observed_at` 等于该真实执行时刻，不能用旧提交时钟标记未来采样。再经 `publication_delay` 向recipient投递；recipient停机则等真实恢复，`delivered_at` 取实际接收时刻，不刷新原快照。最终ACK为 `delivered` 或 `rejected`。 |
| `kind=withdraw_service_forecast` | 引用确切 `original_message_id`，或引用本人已经实际发布预测的 `forecast_request_id`，后者可用于原发布ACK丢失时。只产生指向原消息的软预测tombstone；实际recipient收到后ACK为 `delivered`。不能撤掉硬transfer、lease或已执行前缀。 |
| `kind=cancel_transfer` | 用 `transfer_request_id` 指向本owner命名空间内的请求，source实际可用时才处理。只取消undelivered/pending请求；已承诺则 `rejected:already_committed`，不得用丢ACK或取消重试释放在途义务。 |

上述command请求ID与transfer共享冲突检查，同ID不同kind/payload拒绝；同ID同payload重试仅重新查询/回应原处理，不重复执行物理动作或发布消息。未完成处理的重试可收到 `pending_execution` / `pending_delivery` 快照。`acknowledged`仅表示相应transport ACK真实送达，不自动等于业务完成或托盘接收。

已从source真实发出的消息可由recipient独立接收并产生交付ACK，即使source随后进入不可用窗口；这是peer delivery ACK合同，不要求已发消息回到source重新执行。源端尚未执行的命令仍必须等待source恢复。ACK的延迟、丢失、重复和超时均为native事件，不能通过共享truth查询假装已确认。

`protocol_command`、`protocol_request`及协议观察只暴露本人客户端状态和实际已送达ACK。ACK字段中 `executed_at` 是source真实处理时刻，`completed_at` 是实际route校验或peer交付时刻，`observed_at` 是ACK快照产生时刻，`delivered_at` 是该ACK首份副本实际收到的时刻；transfer ACK的 `received_at` 则是实体托盘实际接收时刻，仅received快照有效。晚来的旧attempt可能拥有更高ACK发出sequence，不能以最后到达包的attempt大小倒推物理结果。

`observe_protocol` / `observe_protocol_control` 保留本地真实传感和已送达需求/预测，去除旧transfer/route/recovery真值及旧owner事件版本。`client_transfer_ledger`和compact FIFO incoming抵扣使用相同的本人payload＋已送达ACK知识。预测释放不能产生可用空盘；pending、timeout_unknown或尚未终结的ACK不能撤销outbox中的未决盘承诺。完整结果、私有未来和全状态hash继续仅供可信离线审计。

`protocol_control.py` 保存明确的public tick相位、需求签名、路由和预测/撤销生命周期、owner请求序号、不可变outbox、已收ACK和下一retry时刻。完整native checkpoint和这份JSON状态须一起恢复，才能续接下一公开tick；JSON本身不包含物理状态。预算截断tick返回 `result=None` / `control_boundary_complete=False`，不隐式补跑，且拒绝把部分tick状态用于普通resume。能力限于受控进程内恢复与已实现的显式控制器，不包括持久跨进程恢复、主机崩溃重启、任意外部策略/网络模型或现场部署。

010验证口径见 `CHECKPOINT_COVERAGE.md`：`live_validation_008` 为320项通过；007因pytest用户Temp访问权限失败的stdout/JUnit原件仍保留。68项协议及相关专项是320项的子集，两个68项留档为技术重复，不累加。7场×4策略实际执行保留拒绝、未完成和无收益结果：接收拒绝场仍有一件业务等盘；known_service_ack_loss的R1-only为1/3，带R2三基线为3/3且成本相同。运行完整、物理审计通过与业务全完成分别报告，不以接口或测试数量替代创新证据，也不据此宣称P7完整100ms达标。

## 011追加合同：确认实际发布内容与当前控制意图

需求的执行时采样合同不变，但提交时本地签名不得作为“远端已发布该内容”的证据。011仅在demand的delivered ACK真实到达后附加 `captured_demand_signature` 及其真实观察时刻、发布序号；内容来自ACK已引用且已seal的不可变历史消息，经ID、owner、target及实际时刻匹配后推导。匹配失败fail closed，不以当前队列补齐；旧pending ACK不因后来消息完成而获得额外信息。仅作加速的digest缓存不属于协议物理状态，restore清空，返回对象修改不能污染缓存。

`g31.protocol_controller_state.v2` 按每个owner→target通道保留一份未确认publication；确认后比较ACK中的实际采样签名与当前本地签名，内容不同才提交新publication，拒绝则按声明retry节拍另提新intent。丢ACK保持unknown和同ID重试，不把执行时采样改成提交时冻结，也没有用周期心跳掩盖签名的含义。永久通信失败时不承诺信息自动新鲜；仍由实际恢复与收到的回执推进。

区域路由的历史 `updated` ACK只证明该次操作曾完成，不能证明当前仍安装该方向。控制器维护当前业务/盘/阶段的active intent，前一结果未知时保持串行等待；收到结果后才按当前公开路径/故障重新比较。路径A→B→A必须在B已安装后真实提出新的A，即使旧A租约尚未过期。旧v1 controller state不能正确表达这些关系，故明确拒绝，不自动解释成v2。

公开tick按精确声明时域执行：不得用epsilon跨越H，H早于当前物理时刻必须无推进地拒绝。native＋v2 JSON状态的完整边界续跑保留；partial tick预算失败仍不支持普通resume，也仍不能持久跨进程恢复。实际需求capture、route ABA、生命周期及nextafter时域反例的修复后探针均已passed，7项新增binding专项通过；完整回归数量及性能以其独立后续回执为准，不从这些正确性修复推导方法创新、业务全成功或100ms认证。

随后 `live_validation_009` 在上述011二进制上实际完成342项相关回归，0失败/错误/跳过，编译来源匹配且测试前后源码未变。新增7项binding、11项原图runner、三项probe及此前68项均为其子集，不另行加总；010的320项仍作为历史版本记录保留。342项通过不扩大现场、恢复或P7保证范围。
