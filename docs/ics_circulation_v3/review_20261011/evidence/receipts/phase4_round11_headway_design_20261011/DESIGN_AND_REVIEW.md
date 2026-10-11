# Round11：入口 headway 的实施边界与隔离原型

2026-10-11。本文是下一轮正式贯通前的设计证据；本轮未给 production 安装 headway，未改生产源码或测试，未提交或推送。四格业务试验仍采用冻结的 Round10 物理规则。承接 [Round8 设计](../phase4_w3_round8_independent_review_20261010/ENTRY_HEADWAY_DESIGN.md)，本次直接校验原始用户材料，复核新增 storage 日历和当前事务实现，并执行纯事件账本与独立 pair-gap 对照。

## 1. 需求来源、资料及缺口

原始《问题及约束说明.docx》由 [capture_requirements.py](capture_requirements.py) 直接读取 OOXML；[原文捕获及 SHA](source_capture_001/result.json) 与 Round8 源 SHA 完全相同：`816b57f9c97bfd456f521669468a7ef19fbd3faac168ed43853009c8a4dc548c`。JSON 保留零基 XML 段号与全文，不把文档中的研究建议当成本轮用户操作指令。

原文要求区域边缘自主调度、单任务更新小于 100 ms、动态按需更新、有限局部故障下保持处理能力；跨区域空盘预平衡须保留区域内部模块，不影响正常行李分拣，考虑大于 2 km 的连接和多连通线平衡，允许修改连通线长度。**原文未给入口 headway 数值、车道配置、变速/合流安全接口或现场校准方法。** 不能从长度、整段容量或营销吞吐量倒推现场 h。首批 h 必须单独声明为研究代理，列秒/tick、来源、舍入和适用边，不降低原研究标准。

第一方资料提供以下边界：

- Zeinaly、De Schutter、Hellendoorn 的 BHS 控制论文使用聚合 DCV 流量近似和有限队列，低层控制另行实现。这支持把流量近似与逐盘安全义务区分，但没有给本项目可直接使用的入口 h 公式。[作者发布论文，PDF 第 4、7 页](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf)。
- Hanssen 在 Vanderlande 开展的 TU/e 学位研究描述 release gap、下游载具距离、控制器反应时间和减速过程；多个接口规则需同时满足，样本周期影响实际间距。这说明仅固定入口间隔并不覆盖连续运动安全；该论文也不是本拓扑的供应方安全认证。[TU/e 原始论文，PDF 第 28–31、78–81 页](https://pure.tue.nl/ws/portalfiles/portal/218081823/0900580_AMBDapproachToImproveTheDesignProcedureOfTheTubtraxBHS.pdf)。
- [Vanderlande TUBTRAX 官方介绍](https://www.vanderlande.com/systems/transportation/tubtrax/)未提供可用于本场景的数值 headway。另一个作者 PDF `08_012.pdf` 访问遇到验证页/服务错误，未读到全文，未据其推导模型。

## 2. 首批语义与必须维持的不变量

每条有向边有原行驶时间 `tau > 0`、整段容量 `C`，另有运行内固定的 `h >= 0`。第一版同边空/载盘 h 相同；多车道、反向共享轨道、合流优先级、变速追赶和运行时改 h 不在这一代理合同内。`h=0` 保持旧路径，既不新增事件记录，也不改变旧 dataclass/asdict/checkpoint 形状。

一条腿于 d 入边时，同时预约原 `edge:e [d,d+tau)`（容量 C）和 `entry:e [d,d+h)`（h>0 时容量 1）。两者是半开区间，恰好相差 h 合法。新规则不改变到达时间、原容量、盘身份、终点、存储 release 或保护截止。`C=0` 仍不可走；零腿动作没有入边事件。若声明秒值，最小间隔采用 `ceil(h_seconds/tick_seconds)`，不能用同样的上取整去放宽硬截止。

| 最小反例 | 原整边容量 | 新入口间隔 |
|---|---|---|
| tau=10,C=3,h=3；d=0,1 | 允许 | 拒绝 |
| 同参数；d=0,3,6 | 允许 | 允许；把 C 改成 1 会错误取消流水能力 |
| tau=10,C=2,h=3；d=0,3,6 | 拒绝第三盘 | 允许；入口约束不能替代容量 |
| tau=2,C=3,h=5；d=0,3 | 第一盘已离边，允许 | 拒绝；最早 d=5 |
| 同盘 e@0 后绕回再 e@3，h=5 | 必须另算第二次占用 | 拒绝；按 tray 合并会漏冲突 |

稳定事件 ID 为 `(tray_id, edge_id, original_depart)`，记录保存原始 d 和 d+h，不因 now、到达、安全 anchor、卸载或重新装袋而裁剪。相同事件的重复描述只计一次，但不同 d 的同盘事件计两次。相同 ID 不同不可变窗口必须拒绝。

实际 `entered` 只能来自已接受腿的物理进入回调，不能用 `depart <= now` 推测；控制、提交、运动的同 tick cursor 不等价。已进入事件在 `end > now` 时不可取消。未进入但属于冻结前缀的窗口亦必须完整保留，即使其尾部跨过安全 anchor。只能撤销经现有权限证明属于可替换后缀的未进入事件。

入口尾窗不等于盘仍忙：盘已到达并卸载后可以走其他边；原边入口限制独立到期。系统完全排空则仍应等待尾窗结束。中途启用时若 h>tau，当前空闲 stock 不能证明近期没有入边；必须有真实未过期入口历史，或从已绑定合法初始状态 warm-up，未知历史不能当空日历。

## 3. 可独立实现的模块与尚未解决的生产边界

建议新增 `entry_headway.py`，提供 opt-in `HeadwayEdge(Edge)`、`EntryReservation(Reservation)`、事件派生/去重/保留/容量检查。把新记录装进原 reservations 容器可避免再改 `Snapshot` 默认形状，也能与 `StorageSnapshot` 组合。默认关闭必须返回原 Edge/Reservation；仅字段默认 0 的新子类仍会改变 asdict，不是严格桥接。

固定每边 h 的配置应有 schema、完整 map/hash、单位和代理来源。边参数合法不代表现有 generator/validator/分区 owner 支持：安装时校验支持矩阵，遗漏明确拒绝。原型只研究合法域内的事件关系；不验证 caller 的取消权限、事件来源或全局每边配置一致性。

当前 [headway_ledger_prototype.py](headway_ledger_prototype.py) 完全独立，未被 ICS 导入：

- `canonical` 依事件 ID 去重，entered 单调为真；不按 tray 合并，也不改原时间。
- `conflicts` 对不同事件作半开容量 1 sweep。
- `record_actual_entry` 只接受匹配的已承诺记录及物理 tick；已进入记录的重复通知幂等。
- `retain_for_replacement` 保留 actual/frozen/未获取消授权事件，不自行推断授权。
- `self_tail_signature` 只表达此固定 h 模型的自身历史，不足以替代完整路由/存储/资源状态。

生产接入还须处理“记录已过期清除后再次收到同一通知”：由 checkpoint 恢复的物理 cursor/已进入 ID 识别迟到重复消息并忽略，不能复活旧窗口，也不能把未知旧通知当新入边。当前纯 live-ledger 原型没有实现这个消息协议；它对没有承诺记录的实际通知会拒绝。此限制与清除后幂等测试须在正式接入时单列，不能把现有原型通过说成分布式幂等完成。

## 4. 按当前源码定位的贯通清单

定位以 `prototype_002/source_snapshot/scripts/experiments/ics_circulation_v3/` 保存的 11 个核心文件为证据；其余文件为当前只读审查，正式实现前重新绑定完整源 manifest。行号是此次读取定位，不应跨版本机械套用。

| 文件/位置 | 当前风险 | 所需变更与验证 |
|---|---|---|
| `runtime.py` candidate_reservations:54、_merge_reservations:70、effective_reservations:88 | 按 `(resource,tray)` 合并并裁剪 now；重建普通 Reservation | entry 单独按原事件 ID 去重；已在途重建须与实际事件吻合，不丢原 start/entered；物理资源旧合并规则保留 |
| `runtime.py` capacity_conflict:114、validate:299、commit:403 | 仅认识 node/edge/reception；验证与提交移除所有 own tray 预约 | entry 显式容量 1；只排除可撤的对应事件，保留历史尾窗、不可取消前缀；全 witness 与提交前缀同源派生 |
| `runtime.py` prepare_replacement:424、_replacement:483 | planning 删所有 own 预约；frozen 一律截到 anchor | 保留不可撤事件完整尾窗；计划、锁内再验、实际提交使用相同保留函数；保护/空盘/旧在途权限保持 |
| `runtime.py` _update_motion:784、advance:1090、checkpoint:1132/from:1142 | old-arrive、prefix-arrive、usable 三处按 tray 清空 | 实际入边 cursor 点标 entered；三处保留未过期尾窗，到期才释放；公共 state 与私有 entered/cursor 恢复同一事实 |
| `runtime.py` 条件预测依赖；`conditional_evaluation.py`、`public_rollout.py` | 旧 forecast、memo 与值标签可能漏新物理约束 | 绑定 h 配置/语义和完整日历；重新验证 entry；新标签不能冒充旧物理的 continuation 标签 |
| `joint_transactions.py` _stage:33/44 | 按本次所有 tray 或当前 proposal tray 去掉预约 | 保留所有历史/frozen entry，新增 bundle 全部一起 sweep；失败不留半个承诺 |
| `dependency_admission.py` proposal view | 删除可腾空 peers 的 tray 身份及所有预约 | 节点同时腾空不能释放历史 entry；也不能只留下 entry 却删其 owner 身份而触发未知 tray。需要保留身份/不可撤账本，只放松经过证明的 idle node 占位 |
| `routing.py` _ResourceView:158；`routing_reference.py` | own tray 全排除；未知资源可能落 reception；事件投射只含旧资源 | 显式 entry dispatch，检查自身尾窗与新增 legs；入口 end 减“到入口”的 offset 投射到可等上游；no-wait 不在本地偷等 |
| `storage_calendar.py`、`storage_routing.py` | 新 Round10 日历仍只认识旧资源且排除 own；label 为 node/time/stage | entry 必须贯通整段 availability 与 release/下游事件的二层反投射；满 EBS 的零驻留合法性保留，但每条正行驶腿仍有 entry 窗口；自身尾窗加入 label 状态 |
| `joint_reference.py`、FullGraph integer reference | 某些节点/时刻标签可能丢掉自身历史；强参考支持域受限 | 小图采用全部有界正 travel walk/整数 departure 或证明充分状态；预算耗尽/截断为 unknown，headway 未支持组合明确拒绝 |
| `distributed_clock.py` owner_of:205、footprint:213、_conflict:227、prepare/authorize、物理同步及 checkpoint | duplicated footprint、按 tray 合并、lease 释放、重复消息 | entry owner 同原 edge source partition；公共纯派生函数一致，校验 proposal 不得漏 entry/owner；lease 与已提交/actual 尾窗分开，迟到 ACK 不取消尾窗 |
| `partition_observation.py` resource_owner:44、observe_partition:54 | 仅旧资源；本地 tray 按位置裁剪 | entry 尾窗可能留在已离开的 owner 区域，需有限事件 owner 身份，不能为修补漏接口而暴露远程行李或未发布未来 |
| `distributed_local.py` service/source guard | 根据所有 lease slots 的 tray 判断忙 | 历史 entry 不能把已空闲盘全局冻结；新计划仍校验同边重入 |
| `routing_cache_contract.py`、network signature | 静态 topology signature 只含旧 edge 字段；checkpoint 有私有 cache | travel-only 下界数学上可复用，但新物理配置/候选语义须单独签名；无未绑定的 entry 日历 memo；新增扫描/投射/去重全部计量 |
| `network_full_cycle.py` cycle_snapshot:48 | 仅豁免 node 的无限停车项 | 保留这一精确豁免；entry 尾窗应计未排空义务，不以盘已空/已到达替代 |

## 5. 搜索与参考的证明义务

同盘两条路径可同时到达 A@2：第一条使用 e@0 后返回，另一条绕不同边到达。若 e 的 h=5，同一 e@2 后缀只对第二条合法。故 node/time（存储再加 stage）不足以决定后续可行性。不能在旧 K 标签桶上仍宣称全局 earliest/exact；自身未过期 entry 历史至少必须进入状态，完整外部资源/阶段/权限仍需一致。区域 K、local cap 和预算继续如实声明，不能加预算或降 K 来掩盖漏解。

Round10 的 relaxed storage→final FIFO Dijkstra 可扩成同时满足 `edge [d,d+tau)` 与 `entry [d,d+h)` 的 earliest departure：在公开固定日历上，时间向后只缩小可选 departure 集，联合最早到达仍 FIFO。实现需交替推进至两种资源均可用、计全部扫描工作。放松图继续允许任意等待、忽略 node/reception、忽略路径新生成的自身历史，所以只给乐观下界；不能据此生成实际 witness，亦不能给 already-departed storage elsewhere 标签强加必须再过库的 floor。

事件投射不能只加 `release` 或当前边入口 end。需要把下游 entry 的可用时刻按到**下游边入口**的 offset 回传，并继续覆盖满库零驻留/no-wait 链的二层投射；入口容量和 edge 整段容量都要查。正式测试须重跑 Round10 的全部修复反例，新增自身循环和入口尾窗交互，而非用改进一种约束换掉另一种约束。

reference 对小 horizon 全整数枚举，另写 pair-gap 和原容量 oracle。只在相同充分状态可合并；含 K cap 或预算截断不能报不可行。普通、存储、空盘、joint、W2 必须同物理合同比较，不可给某算法放松 h。初期若某组合尚未贯通，安装即拒绝该组合，不能默默沿用忽略 h 的路径。

## 6. 执行证据、失败与资源账

[run_prototype.py](run_prototype.py) 的 pair-gap oracle 独立采用每边固定 h 下的 `abs(d1-d2) < h`，对事件 ID 去重后逐对比较，没有调用被审 canonical/sweep。枚举 h=1..5、两个 tray、两条边、d=0..6、每组 0..3 事件、now=0/3/7，共 55,245 次 oracle 对照；这不是 55,245 个生产运行，也不是性能优越性证书。手算案例另覆盖 suffix/frozen 跨 anchor、真实 entered 不可由时间推测、self-history、pickle/cursor 与兄弟分支隔离。

| 主 receipt | 结果与范围 | CPU 秒 | wall 秒 |
|---|---|---:|---:|
| [prototype_001](prototype_001/result.json) | 55,279 checks 通过；冻结旧原型源 | 1.781250 | 1.881670 |
| [source_capture_001](source_capture_001/result.json) | 原始 docx SHA 与 OOXML 捕获通过 | 0.015625 | 0.010125 |
| [clock_probe_001](clock_probe_001/result.json) | **3 个非法 clock 均错误接受**，独审发现后保存的真实失败 | 0.000000 | 0.000141 |
| [clock_probe_002](clock_probe_002/result.json) | 同 3 个反例全部拒绝 | 0.000000 | 0.000117 |
| [prototype_002](prototype_002/result.json) | 修后 55,289 checks 通过；含额外 10 个严格时钟检查 | 2.046875 | 2.094020 |

总已计量 CPU **3.843750 秒**，0 物理运行、0 standalone routing query；重复回归不是新增独立场景。原型源从 `0b17de05a188ecd9c3e447d78c66d59e99c2e0a01aaa40182788d9944f21ba78` 修为 `2485b74a894349be40a5811e852f8e0b9e994a74c6a1ba9724cc3a0044747a6d`，仅加 `type(now) is int and now >= 0` 的严格入口检查。修前 `now=True` 会与 depart=1 相等，已 entered 事件甚至接受负数/None；现在失败原件和修后结果均保留。

两个 prototype receipt 中生产 source SHA 前后一致；storage_routing=`867018bc951e8afe95840c33dbac42a32f2a2d38e46317e58070534dc502e7e2`，storage_calendar=`5b0b5d87aefe954f89d3e00774847a66ef801df49118909624bf2e5fc94f0ed7`。checkpoint SHA 两次均为 `1a29da20111c5bbd49e130da8d10202ecc1ed94c0fc8ee66fa78ebe428ec4c60`。

源码阅读、网页检索、设计/编辑、工具编排、执行前 source snapshot 捕获为未完整计量的辅助工作，不计入算法 CPU。若干只读查询用了无效 Windows glob/猜测文件名而失败，随后以 rg --files 定位；未运行物理或改生产。首次 docx 控制台显示受 CP936 编码影响，UTF-8 JSON 原件正确，再以 `python -X utf8` 核对全文；这不是原文损坏。

## 7. 正式实现的最小验收顺序

1. 固定 opt-in schema/每边 h 来源、初始化历史证书与支持矩阵；h=0 完整默认桥严格相等。
2. 纯事件模块、真实入边与三处清理、尾窗和 checkpoint 先闭合；同盘新装袋走别边允许，同边太早重入拒绝。
3. 单路线全 witness/安全前缀、合法 suffix 与联合依赖原子提交闭合；保留 frozen 跨 anchor 尾窗及 owner 身份。
4. 普通/存储搜索和独立有界整数 oracle 对照；保留原预算/K，计算预处理、entry 扫描、事件投射、validator 全部工作及失败。
5. W2 prepare/authorize/消息 cursor/重放/迟到重复与已清除记录幂等专项；有限本地观察不变相读取全局未来。
6. 全归回、原拓扑、空盘及联合强参考同物理合同测试；2/5 km 参数实验另列 h 与容量代理。只有贯通并达到相应验收，才能声称这些模式支持入口 headway；本轮隔离原型不能代替上述步骤。
