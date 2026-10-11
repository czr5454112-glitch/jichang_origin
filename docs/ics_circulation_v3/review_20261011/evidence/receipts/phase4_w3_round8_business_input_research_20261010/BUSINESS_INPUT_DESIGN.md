# 持续业务输入：来源核验与下一轮最小实现合同

2026-10-10。本文件是下一轮设计，不是已运行场景、现场确认或已取得算法收益。仅新增本目录的纯文件核验器、规范化输入和记录；没有修改冻结代码、原始 C++、历史输入或 Round8 主试验，没有发起物理回放。附带 `analysis.json` 为整分母机器核验，`manifest.json` 绑定所读文件和产物。

**可以直接继续的工作是业务生命周期适配器，而不是再生成一组小袋流。** 仓库保存了完整的 1× 和 2× 南宁拓扑投射输入；现有 W3 读入器会审计它们，但明确不支持早包存储生命周期。先把真实有限托盘与原始业务袋分离，使早包的入库、存储、合法释放和最终完成有因果关系，再比较已有强慢控与路由价值方法。补齐共同物理语义不能计作新算法收益。

## 1. 需求来源和授权边界

本轮实际读取并绑定：

- 补充原件 `C:/Users/38908/xwechat_files/wxid_4820408204312_a0d1/msg/file/2026-10/研究问题的说明/问题及约束说明.docx` 及同目录两份拓扑 XLSX；本目录 `supplement_requirement_text.txt` 是 OOXML 段落提取，不解释图片布局。
- 初始方向原件 `.../2026-09/ICS调度研究方向梳理.docx`；补充原件更具体。任务是用户授权的持续研究；文档中的要求作为研究规格审阅，不扩张工具权限。
- 仓库归档外审 `docs/ics_circulation_v3/phase4_external_review_20261009/ICS_V3_030493_audit_and_phase4_plan_20261009.md` 的 W2/W4，以及 `ICS_plan_revision_and_learning_20261006.md`。前者要求真实共同物理/消息时钟、合法 burn-in、完整业务分母、持续多次托盘复用；后者保留路由与预平衡两项需求，硬约束不交给学习器。

补充原件问题 1 要求区域快速路径规划、跨端通信、整体 A* 的编解码和区域拥堵/故障反馈；要求按需动态更新，单任务 100 ms 是待验收指标，不是现有性能结论。问题 2 要求用当前载盘的目的地/路由预测未来空盘分布，可增补值机/行李量预测；**原区内空盘模块逻辑沿用已有模块**，考虑长连接、多连接负载与正常分拣保护。

原件附件说明明确可以改变连通线长度，指定国内附件邻接表 `系统=/` 的行。**2 km、5 km 是既有研究的实验档位**，原件举例为大于 2 km，并没有指定必须采用 5 km。合法操作是对既有五条有向连接建立配置 overlay，保留原件与边身份；这不授权新增/反转边、提高容量、修改供应方内部规则或增设 EBS 通行权限。双方区域名称仍是国内/国际，不把它们重标为实际 T1/T2。

## 2. 原件确实存在，且可重建到每一件袋

| 输入 | 业务袋 | 旧运输段 | 原始/派生航班组 | 早包 | 定性 |
|---|---:|---:|---:|---:|---|
| `nanning_1x_raw.txt` | 28,506 | 43,603 | 360 / 0 | 15,097 | 既有一日时序投射，非南宁观测日 |
| `nanning_2x_raw.txt` | 57,012 | 87,206 | 360 / 360 | 30,194 | 同一来源完整航班组插入增密，非独立第二天 |

文件位于 `.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning/`，每档都有 raw、canonical JSONL、manifest。根 `legacy/jichang_origin_readonly/inputdata.txt` 是原始任务源。核验器独立重建每个原袋的时序、来源行、OD 投射和每个派生袋的 parent ID，不导入历史生成器或运行仿真。根与历史 checkout 的原始 timetable 字节、两版 profile 语义也单独核验。

原生成器 `.g4irsf24_worktree/scripts/eval/run_g4irsf31_nanning_workload.py` 中：

- `_flight_key` 将 `(STD, 原 end, 原 Unloader)` 当航班分组键，**这是源数据代理键，不是真实航班号**。投射 raw 用新节点别名替换了 Loader/Unloader，不能只看投射行反推原航班。
- `build_original_projection` 将原 `(Loader,start)` 入口组、完整航班目的组及转机航班组分别以大小降序、确定平局规则，平衡映射到有角色的南宁节点。我们重算全部映射，不按算法结果重新平衡。
- G29 `densify_flight_timetable` 在同一 `(end,Unloader)` 序列的相邻航班中点插入完整清单，最后一班用该序列间隔的下中位数一半。保持每袋相对 STD 时差；先生成 raw，再展开早包段。不是复制运输段，也不是压缩一日时间。
- `select_storage_pair` 以图上静态均值选择 node 53 / IDK1 / ICS54，manifest 明确标为 `EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE`。该节点实际输入角色为 type-7 **空盘存储**，不是已确认的行李早包库。

本目录 `business_tasks_1x.jsonl.gz` 和 `business_tasks_2x.jsonl.gz` 每原始 raw ID 只写一条规范化业务记录，保存 raw SHA、source line、parent 源 SHA/ID、航班代理键、派生标记、精确秒级时钟和旧段 ID。`physical_tray_id`、`deadline_contract`、`protected_contract`、`storage_carrier_policy` 留空；它们是 **设计输入，尚不可作为运行配置直接执行**。所有不连通、单向无回路和早包记录仍保留，没有为通过实验删除任务。

图核验只用正容量有向边，151 节点/227 原始边，其中一条容量为 0 保持关闭。11 个装载点、42 个卸载点、10 个空盘存储点；462 个完整装卸 OD。`analysis.json` 给出全部 OD 类别、实际任务各类数量和每条跨线的静态最短运输段覆盖。静态覆盖是结构信息，**不是实际分流、容量可行、等待预测或输送负载证据**。

## 3. 已有能力与缺口

| 事项 | 已有源码/证据 | 下一步不可省略的部分 |
|---|---|---|
| 业务数据入口 | `phase4_network_workloads.read_projected_tasks` 校验完整 raw/canonical/manifest 和 OD | 不把 importer 当 EBS 实现；其 early 分类就是 unsupported |
| 有限真实托盘与回流 | `model.Tray`、`runtime.Simulation`、`same_zone_supply` 可重复装卸、空盘计划、在途占用 | 旧 canonical `pallet_id=task_id` 不是有限实体；需独立库存输入及逐盘生命周期账 |
| 到达/卸载/可用分离 | `candidate_reservations` reception 到 usable，`_update_motion` 在卸载完成后放盘/hold | EBS 中间段不能调用普通最终完成逻辑后凭固定时间再生袋；持盘存储不能产生空盘信用 |
| 接收回压 | `ExecutionValidator` + `effective_reservations` 节点/边/接收半开预约、旧在途合并 | 现 uniform `reception_capacity=1`/unload=1tick 是代理；EBS 库存/转存/检索服务器是新增真实资源合同，不能靠无限队列掩盖 |
| 动态入口 | `future_bags` 在 `_prepare_events` 到点加入，FIFO 从可用真盘装载 | 装载服务/外部入口容量无完整现场模型；下游堵塞时原袋保留为未 admit/排队，不丢分母 |
| 多连接共用路网 | 五条有向跨区边、原长度/速度/记录容量，空满盘同图 | 各方向能力不同；不能强行等流量，也不能默默将加长后的 floor(length/2) 当已授权容量增长 |
| 路由/库存所有者 | W2 `distributed.py`、`distributed_local.py` 有真实消息时钟、owner 校验/提交协议；W3 中央强策略 | 供应方模块/API/权限未提供；synthetic owner≠现场黑箱。不能将 W3 全局 Snapshot 直接交给受限 W2 控制器 |
| 发布预测 | `RoutingDemandForecast` publication/TTL/revision/identity 去重已有 | 原 timetable 没有观测/预测发布时间，也没有误差历史；完整未来 tape 只归环境，不能在 online 公共特征出现 |
| 原始角色/服务 | profile 记录工作簿/行号、速度、长度、类型、少数服务 | node cap、初盘数、headway、模块模式许可、protected/截止规则未确认；6 个缺失服务填 0 不是现场 0 秒 |
| 性能 | Round8 有同仪器 screen 配对和工作量账 | 不推出单任务硬实时 100 ms；继续随到请求、拥塞/消息/多机端到端尾部测试，算法计时与观察成本分离 |

当前 `projected_window` 只读取既定短窗直接袋，排除早包并继承人工 burn-in/有限注入盘，不能称完整投射持续业务。其 arrival/deadline 均 ceil 到 10s 的做法也不应无条件延伸：硬截止向上取整会放宽条件，下一接口要明确原始秒/离散 tick 及保守舍入误差。

## 4. 可实现的最小输入接口

建议独立新模块 `business_inputs.py`（未来实现名，不修改本轮 source）提供纯函数 `load_business_workload(raw, canonical, manifest, source_timetable, graph_profile, contract) -> BusinessWorkload`。读取阶段禁止构造 Simulation。返回：

1. **不可变 BusinessTask**：`business_bag_id, source_reference, arrival_seconds, std_seconds, final_destination, origin, flight_surrogate, lifecycle, scheduled_release_seconds`。`std_seconds` 原样保留；另由显式 `deadline_policy` 定义 final deadline，不擅称 STD 等于真实行李交付截止期。保护标签也必须有公开产生规则；不能为避难保护而全取消。
2. **OperationContract**：`version, evidence_status, graph_sha, tick_seconds, capacity_by_resource, service_by_module, wait_permission_by_node_and_mode, edge_mode_permissions, initial_trays, initial_storage, export_import_interfaces, ebs_contract, forecast_publication_stream, fault_publication_stream`。每参数带 `source_ref/assumption_id/units`；缺失必报待定项，不填无限/零值。`confirmed` 模式拒绝缺证字段；`proxy_research` 模式允许明确数值假设且要求标题、manifest、结果同时标明。
3. **Forecast/PublicEventTape** 与 **EnvironmentTape** 分离：原始未来真袋/真故障保留在环境端。发布流定义身份、版本、available_at、TTL、取消；已知实际观测优先。EBS release 的外部授权有单独版本；计划出库时刻不等于已收到授权。不用旧 Nanning 小流误差 seed 当新业务误差校准。
4. **TopologyOverlay**：`base_sha, edge_id, length_m_override` 仅允许本轮已核五条连接；原图/2000m/5000m 显式取值，保持端点/方向/权限。`capacity_policy` 必填：例如固定原记录容量的受控长度敏感性，或独立授权 headway 模型；前者避免暗加容量但不是现场长线容量，后者须有来源。速度是否保持也显式。
5. **Scope/StopContract**：选取规则只看时间/来源/结构特征，不看 J；原输入、筛选窗内、合法 warm-up、窗后 tail 的身份账分开；所有入域袋在 terminal business ledger 中保留。设置 wall/CPU/query/guard/physical tail cap，各种退出分类明确；耗尽不作为物理不可行，不补数字最优值。

现有 `model.Edge` 只有 `travel_time/capacity`，没有物理 length/speed/headway；内核限制的是整段半开时间内同时占用量，不是逐次入段最小头距。新增长线接口要把 `length_m / speed_mps → travel_seconds → ceil(tick)`、整段可容盘数、入口最小间隔分别记录。当前可直接表达前两者的代理，不能把 capacity=1 的整段独占当真实连续输送线；2km 后它会把每盘吞吐间隔变成整段旅行时间。若要固定入口头距，需要另一个入口资源/时间窗口约束及与整段占用联合校验，不能用调大 capacity 等价替代。无等待链、合流、安全间距和终端接收回压也分别声明。固定原 capacity 的长度敏感性只是在现有预约抽象下隔离运输时长，人工产生的瓶颈不能被包装成现场或算法收益。

时钟建议保留精确源秒，初个共同模型用 1s tick：arrival/旅行/完成服务向上取整，硬 deadline 向下取整，发布时间不提前。模型与旧 10s 明确不同，绝不将量化变化归给算法。也可继续 10s 做兼容桥接，但需统一全策略并报告最大误差，不能悄悄采用双标准。任何 bag 的保护最终约束都作用于完整生命周期；不能只证明 storage-in 到达准时就当最终分拣已保护。

## 5. EBS 不是两个互不相干的 OD：两种明确合同

初始 parser `src/czr005/io/legacy_tasks.py:expand_tasks` 以 `STD-entry>=4800s` 识别早包，独立生成入库段及 `STD−2700s` 出库段。它不检查入库是否完成，没有提供载具保留规则、存储容量或出库授权。父业务袋必须只有一次最终完成和迟到统计。

供应商第一方资料存在**持盘储存**接口，详情见邻近 `phase4_w3_round8_stability_analysis_20261010/EBS_CARRIER_SEMANTICS_SOURCES.md` 与其中 BEUMER PDF。这里仅使用“可能持盘”的接口事实，不移用厂商吞吐指标，不判断南宁现场类型。

两种合同都必须实现为不同显式值，禁止自动推断：

- `on_carrier`：同一 bag/tray 身份贯穿入库、存储、出库和最终卸载。中间 waypoint 不产生 `completed`，不解绑载具，不发布空盘 supply。存储真实占用载具和库位，release 之后仍是同盘带同袋。需要独立 storage resource 与经过许可的出库动作；不能用“临时 empty 再 load 同 ID”绕过容量。
- `off_carrier`：入库需要合法转存/卸载 service；实际完成后，袋占用库位，真盘仍需完成 hold 才能成为空盘。出库资格为 `max(actual_ingress_complete, scheduled_release, authorized_release)`；真正离库还需合法检索/装载服务与可用真盘，未获得盘时继续占库存和业务分母。原释放时间已过但入库未完成时不在过去生成事件。禁止凭已有目标预约给未知到达盘即时信用。

建议先完成 `on_carrier` 的反例与最小持盘路径表达，再实现 `off_carrier` 作为显式敏感性，理由是前者不能利用卸袋增供盘这一有利假设；**这不是确认现场持盘，也不是为收益挑政策**。未实现的政策只能列待实现，不能声称两者等价或完整现场 EBS。代理 node53 只在 `proxy_research` 下显式授权为 EBS 试验位置，现场分支必须等待真实角色/接口。

**固定已公告 release 的轻量实现可以先复用现有内核，不必先新增整套 stage runtime。** 保持 `Bag.destination=final_destination`，把已公开 EBS waypoint 和 release 下界加入独立 `StorageWaypointContract`。候选完整路线经过该节点，在节点持盘等待到合法 release 后再出发；`candidate_reservations` 已能对腿间空档预约节点，`_update_motion` 在非终点不卸载，因此同一实体可以全程 loaded，最终硬 deadline 仍由原 validator 校验。这种代理只用现有节点容量表示持盘库位，不等同真实立库/检索服务器。

但现有 generator/validator 都没有“必须访问 EBS、不可提前离开”语义，不能仅在 generator 中加等待就称硬保证。最小新层仍要：公开 waypoint/release 合同；对所有候选、owner 提交、替换和 next-edge 完整 witness 做相同 waypoint/release 校验；用真实经过事件记 `waypoint_visited/released`，checkpoint/cache/forecast 绑定此状态；拒绝绕过 EBS 或未到 release 的后续 replanning。若原候选 horizon 不覆盖数小时 release，显式分类 horizon/budget unknown，不让路径搜索穿透未来信息或把它算不连通。完整 witness 固定预约直到 release 的保守性/算力也要记录。

此轻量路径仅适合 release 已合法公告、库位就是可等待节点、无中间卸载/专用检索服务的固定代理。动态 release 可变/撤销、先入库后才收到出库授权、独立库位/设备资源、off-carrier 拆装和多 stage 的 owner 事务仍需下述更完整 stage 接口。先按这条窄合同桥接可以减少实现范围，但不能删掉随后上述业务边界。

一般状态机建议：`not_arrived → waiting_origin → transporting_to_storage → storage_admission/service → stored → release_eligible → retrieval/loading → transporting_to_final → final_unload → business_completed`，直接袋跳过存储子链。每转移记录真实时钟、bag/tray IDs、owner/version/receipt、资源占用，持盘/转存分支分别保持对应守恒。若中间阶段真有卸载或业务 endpoint 转换，由于当前 `Bag.destination` 不可变和 `Simulation` 把卸载视作 final，需要独立新的 `BusinessSimulation`/stage adapter 与 validator 扩展，**不能只靠 prebalance 子类补齐**；固定公开持盘等待代理则优先采用上面的窄扩展。

业务最终目的地和当前合法 stage endpoint 同时保留。只有 stage owner 在前置事件完成后才能原子推进 endpoint，快层仍只能为当前合法段改未执行路线，不能把业务袋自由改目的地或用中间节点终止既有保护。载具在入库前承诺的资源必须兑现；新存储资源不被旧 validator 识别时必须 fail closed 并进入新显式接口，禁止绕过 validator 手改 snapshot。

关键运行接口：`next_public_stage_events(now)` 只取到时事件；`try_stage_transition(event, snapshot)` 做同一版本原子校验；`public_supply_events(now)` 只公布合法确定的真实可用供给；`business_result()` 对父袋统计；`checkpoint()`/clone 同时保留业务 stage、release version、库存、接收预约、真盘绑定、cursor 与缓存契约。延迟消息与物理同 clock，旧已进入连接/已提交承诺不可回滚。

## 6. 目标、服务和资源账如何保持一致

保持既有权重与硬约束，先补正确对象，不在此轮调权重。原运行时 `tray_wait` 是未装袋每 tick，`empty_distance` 实际累加空盘行驶的 travel ticks；它不是米。早包设计必须区分 **预定存储等待**、存储/接收容量等待、检索等待、已具备释放资格后缺盘等待与行驶/卸载时间。

建议业务主账：final tardiness 每业务袋一次；business backlog 每未最终完成袋一次（含未 admit、库内未释放、在途）；空盘 travel 只记真实盘的实际行驶；原 tray-wait 成本应用于实际运输段“已具备合法装载资格而未装”的等待，保留出库释放后等待，不把按规则必须等待的数小时库存 dwell 当缺盘。持盘存储本来没有第二次取盘，不能人为收费。旧 stage J 继续旁路记录用于桥接，**不得直接与业务 J 互比声称收益**；成本口径变更需合同测试与全策略共用，原权重不改但计数对象的修正仍要显式披露。

每袋报告 arrival/ingress/store/release/load/final completion、实际 tray 链和 deadline；每盘报告 occupied-storage、loaded/empty/hold、服务袋数和复用次数。总体至少保留吞吐、全分母准时/未完成/拒收、逐袋早/晚差、最大连续无盘、回压资源占用、多线方向负荷、在途不可撤回量、接收拒绝/过期/版本原因。J 平局仍可有服务退化，不能只报总成本。

## 7. 下一步固定执行顺序（尚未运行）

1. **纯输入与合同**：采用本次全量规范化文件及显式 `OperationContract`；先通过缺字段/错误权限拒绝测试。初始化盘只来自一个固定库存账，盘总数不得等于袋数自动生成。旧原图、source SHA 和 ID 绑定后再定义实验组。
2. **最小物理语义桥接**：direct-only case 新/旧行为应严格相等；早包入库晚于释放、入库不可达、满库存、接收已满、持盘到最终、off-carrier 重取盘、跨区旧在途、重复 release/取消/revision、存储期间 checkpoint 恢复、同 tick release/acquire、未来发布隐藏等手算反例。每项不需大规模仿真，但要覆盖守恒与最终业务保护，不靠只看最终 J。
3. **持续业务开发集**：建议第一完整入口为 1× 原投射的**完整第一小时有到达窗口**，窗口按原始到达时间固定，无 bag thinning；从一天开始合法推进到窗口，前缀任务仍照原合同进入，窗口任务全部保留并排空至各自释放/完成或独立 tail cap。必要时有更小的接口 smoke，但它不能代替完整窗口。每个时间窗口只是同一天的相关片段，不叫独立样本。随后固定整日 1×、2×（压力）而不是按收益再截窗。
4. **容量/长线合同**：原图、2km、5km 对同一完整任务源；原记录容量固定版先作为长度隔离实验，单独列出并非现场容量。有限盘总量/初始分布、接收/库位/服务可形成预声明 nominal/near-full/ample 敏感性，但数值必须先落假设表，不按算法输赢修改。容量不可行/closed OD 的任务留在全部输入账与未服务统计，不能排除后报成功率。
5. **两项需求分开验收，再联合**：路由强基线在固定同一空盘模块/供盘策略下，比较同信息合法候选、强参考/预算状态、单任务与端到端时延；预平衡在固定同一路由下对原 greedy、强同区供盘、公开信息 MPC/rollout；联合组使用同一物理/信息/候选域公开说明额外能力。W2 至少两个 owner、消息占用真实时钟，不与 W3 全局状态方法冒称同信息。MLP 仍须对完整 continuation 标签稳定残差才有监督目标，不能用 EBS 新模型的错误来创造学习收益。
6. **确认来源缺口**：当前只核到一日源和派生增密，没有新的独立运行日、真实南宁任务历史或供应方模块合同。下一大批可称结构/负载开发压力，不能用随机重排/另一 seed 将同源派生改称 W4 独立确认。发现可信新来源时按来源/完整轨迹做 holdout，不能拆同航班袋到训练/确认两边。

本设计没有默认填现场盘数、库位、接收率、故障分布或模块权限。仍可马上实现和审查业务输入、两种 EBS 状态机与代理合同；现场缺口限制的是外推和最终验收，不是停止当前研发的理由。

## 8. 资源与失败记录

`inventory.py` 的计时覆盖纯文件读取、独立全量投射/时间/生命周期核验、静态有向最短路径、规范化 gzip 写出及输入末次 SHA；没有导入 Simulation，也没有 routing generator。计时从 Python 标准库导入后到 `analysis.json`/`manifest.json` 最后写出前，因此属于明确区间 CPU 下界。前期人工读文件、一次全 repo 定位时若干旧 pytest 目录权限拒绝、文档编写、消息与哈希定位未完整计时，记 Round8 unknown auxiliary；没有物理失败/重跑。

2× 与 1× 是独立**文件审计**，不是两个物理日。静态路径计算的工作在本次审计 CPU 内，不计为路由查询/仿真。主 Round8 的 4352 logical/2468 physical、边界补证 2+24 和性能 12+108 分母都不因本设计改变。最终本目录 direct CPU 单列进入 Round8 资源账；不将任何预算上限或并发 wall 求和当实际 CPU。
