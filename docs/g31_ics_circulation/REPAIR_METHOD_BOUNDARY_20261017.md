# 未发后缀修复：接口边界与可检验性质

日期：2026-10-17。本文件对应 T5 的方法边界工作，不是 T5 原生24格完成报告。先决条件为 T2/T4 的实际执行与保护闭合；未达到时保持24格未执行。

实际接口复核：最小候选触发点是B收到新的v3 pair之后、L已在7且reuse1已经装载、但该路线尚未进入`route_keys`的`decide_pending`。`submitted_physical_actions`、request身份/generation和已送达事件序号可用于固定不可撤前缀。现有`future_later_fork`只从初始预测轨迹的B cut分叉，不是实际新观察后的状态重建；现有`public_preexisting_v3_model`的整数`reuse_next`也不能替代本域`native_default(None)`的动态路由语义。因此仍须先实现同域later-context适配及保护重算，不能仅修改retained元数据或重用不等价模型。这个五任务域的闭包可能覆盖L的两次复用、E/receiver、P/blocker及3/4共享资源，必须如实报告没有局部性优势的情况。

## 目标与文献关系

目标仍是区域自主载盘路由 R1、载盘驱动的有限空盘预平衡 R2，在同信息、同预算的强对照下产生业务、计算或通信收益。当前保存域的严格坐标搜索14查询达到全32最优，不能用这三个静态场景论证复杂搜索或学习的必要性。

[FICO v3 第V-B节](https://arxiv.org/html/2511.13961v3#S5.SS2)已明确要求分解后的轨迹与保留轨迹兼容；其冲突自由组合性质不能直接推出本项目跨多次复用的逐件完成保护。不能将“固定外部轨迹、重算相关部分”作为独立创新。

新查阅的[Certificate-Driven Closed-Loop MAPF](https://arxiv.org/html/2604.00428v1)使用完整回退轨迹和剩余成本预算过滤闭环更新，并利用预算进行跨时步分解。这意味着“保留可行回退证书再接受改进”也已有直接近邻。本项目必须额外处理有限盘实体复用、装卸/暂存服务、FIFO、异步已发请求与实际模块权限；总成本改进本身不足以满足严格逐件保护。此处是设计比较，不是已证新颖性或对该文定理的迁移。

[MPI-SWS 的契约式分布监督控制研究](https://cossy.mpi-sws.org/research/assume-guarantee-sct/)将相容的局部假设和保证作为协调基础。本项目首先必须区分可兑现义务与条件性预测：没有接收/资源保证权限的 owner 只能提供 offer，不能生成具有预约效力的 promise。

## 依赖对象与影响闭包

依赖图的顶点至少包含：托盘实体和generation、运输leg与不可撤前缀、路线候选、装卸/暂存服务、空盘释放和接收、下一次装载、FIFO前驱、共享资源时窗、控制权及已发命令身份。因果边表示：上游内容变化可能改变下游可行性或受保护完成时刻。

图必须覆盖本次允许的候选动作域，而不只是旧计划已占用的资源。可选绕行首次占用一个共享资源时，也必须加入该资源及其他使用者的影响边。否则“旧路径无冲突”会漏掉新路径的外部影响。

`apply_delivered_event`只消费实际交付给该owner并通过原生来源/版本验证的事件。重复事件按稳定身份去重，过期或乱序事件不回退已确认状态。先定位变化顶点，再递归扩张所有可能受影响的服务与资源依赖，直至达到不动点；不设置一跳或固定半径截断。闭包可覆盖全系统，届时必须报告局部性失败并与全状态warm-start MPC比较。

`propose_suffix_patch`只生成未发动作的候选修改。已经提交但未收到ACK的命令属于“可能已执行”，连同明确已执行部分一并冻结；丢ACK不能使其重新成为可修改后缀，也不能换新ID再派同一实体。`validate_boundary_contracts`检查所有跨闭包边界义务的实际owner、来源版本、时间条件和授权范围。接收保证不存在或仍待ACK时返回unknown/拒绝，而非构造一个本地token替代权限。

## 有限时域充分条件（待实现检查器）

以下是本项目拟检查的充分条件，不是已实现的通用安全定理：

1. 在固定有限时域和同一外生事件带下，旧计划具有已验证的可执行见证；所有受保护任务及其原完成承诺均完整列出。
2. 影响图覆盖候选域内所有可能改变完成时刻的资源、服务、实体与FIFO依赖，且修改集合对未由有效边界契约隔离的影响边封闭。
3. 跨边界契约由实际具有权限的owner兑现，其有效时界覆盖本次补丁；环境变化未超出契约约定。未知或未授权接收不满足此项。
4. 补丁保持所有已发/可能已发动作、原实体身份与同时间事件顺序不变；闭包内按相同严格逐件规则验证，任意正退化都拒绝。

在这些条件下，若闭包外某个受保护服务首先偏离旧承诺，其首个不同的输入只能来自外生变化、被修改的上游依赖或已发前缀。前两者分别被同外生带/有效边界和依赖封闭排除，第三者被前缀不变排除，故不能出现这样的首个偏离。该推理要求依赖覆盖完备和契约真实兑现；单靠图遍历成功、完成时刻预测一致或偏好ACK都不能建立这些前提。

必须保留三个反例：遗漏第二次盘复用导致远端服务延迟；绕行使用旧图未包含的共享资源；ACK丢失后误把在途命令当成未发。这些反例用于检查前提，不通过删除远端依赖或扩大误差容忍修复。

## 下一轮固定实验入口条件

先完成当前T4先行9格。如果缺少实际同信息上下文、动作兑现或共同执行保护，则先定位该缺陷，不将其包装成滚动方法失败，也不直接上学习。

进入T5后按任务书冻结三种事件变化、每种两个外生种子、四个方法的24格。四个方法共享原生执行器、可行动作域、信息权限、warm-start与静态缓存条件。每格60s、每owner32次预测；100ms完整请求单列。新增微型证明域不能替代南宁原图性能实验，no_overlap与原图不可行继续保留为负对照。当前尚未为这些运行声明结果。

## 20261017只读接线复核：入口已经存在，真正的later预测还没有

本节在先行原生004的源冻结期间补充，只修改本文档。下述内容是实现方案，不是新控制器、T5完成记录、24格结果或性能结论。T4九格即使成功，也只消除当前初始联合执行的一项前置障碍，不能自动证明三个新增事件域已受支持。

### 精确源码入口与缺口

以下路径相对工作树根目录，行号对应本次复核时源码。

| 入口 | 已有能力 | 不能据此宣称的能力 |
|---|---|---|
| `scripts/experiments/g31_ics_circulation/live_obligation_recollection_policy.py:277`，`OwnerPolicy.decide_pending` | 等待真实own ACK及peer message，调用真实owner collector，保留一次重收集与reply预算，再执行本地动作 | `fixed_choice`仍按初始向量取动作，没有收到新事件后重估 |
| `scripts/experiments/g31_ics_circulation/live_obligation_historical_adapter.py:111`，`collect_native`；同文件150行，`OwnerCollectionAdapter` | 绑定同一native/session/owner/client、实际三端点、自己不可变提交历史及当前admission；采集后再次检查 | 复制其JSON输出不能重建live authority；不能读peer私有队列或peer预测表 |
| `scripts/experiments/g31_ics_circulation/live_obligation_delivered_context.py:83`，`later_context`；120行，`revalidate` | 已有pure later-data入口，完整检查own calls、历史发布、v3 pair、quiet与lifecycle，并逐次重验 | 只生成`SuppliedContext`，没有初始化当前同语义预测器或原生提交权 |
| `scripts/experiments/g31_ics_circulation/live_obligation_delivered_context.py:135`，`initial_projection_bundle`；`public_live_obligation_communication_projection.py:389`，`predict` | 当前通信/物理模型从initial context构造新engine | 入口仍限定initial，不能将later bundle塞入初始构造器，不能复用旧初始预测的frame冒充当前观测 |
| `scripts/experiments/g31_ics_circulation/public_preexisting_v3_model.py:207`，`predict`；`public_preexisting_model.py:440`，`candidates` | 旧later模型会从受支持公开状态seed，候选为整数3/8及return delay | `reuse_next=3`是明确路线选择，不等于本域`native_default(None)`；旧模型还具有自己的tick与请求语义，不能仅改动作标签当作新模型 |
| `scripts/experiments/g31_ics_circulation/live_obligation_lifecycle_state_v2.py:122`，`later_bundle`；138、142行 | 检查完整实体、服务、移动entry receipt、capture union与已发动作；拒绝own pending action及未支持故障 | 当前不支持任意新服务合同、故障或未决动作；`live_obligation_domain_guard.py:34`仍只识别三个精确公开合同 |

`live_obligation_online_retained_policy.py`只改变保留初始估计的元数据与执行标志，其模块说明和source proof明确`later_model_reestimation=False`。不能在该类中把`retained_initial_estimate_vector`重新命名为repair结果就算T5。

### 最小可实现数据流

1. **唯一初版触发点。** 在B的`first_reuse_route`真实新v3 pair完成采集之后、`fixed_choice`之前介入。要求L实际已在7、`reuse1`已装载、无在途边、generation/traversal与本次源观察一致；并同时检查`route_keys`、own outbox、submitted physical action清单，目标前缀尚未执行或可能执行任何路线提交。仅缺少`route_keys`不是未发证明，因为提交后返回/记账可能失败。
2. **独立当前决策来源。** 从本次`OwnerCollectionAdapter`的活跃采集能力构造新的later-decision对象，绑定session、owner、admission、采集时刻、发布/接收稳定身份、v3 digest、own calls前缀和target identity。纯数据层使用已有`later_context`与`revalidate`；生产提交层每次另查实际活跃来源。允许保存证据，但保存文件不能重建该对象或提交权。
3. **显式从新信息重建。** 新later seeder只用此次已验证bundle、已送达terminal/entry receipts、公开合同与声明的共同策略条件，重建当前物理模型的jobs/trays、服务与占用、边进入头距/FIFO、未完成服务事件及owner协议状态。使用当前模型的物理/通信处理函数，不调用`future_later_fork`取得旧初始engine、frame、calendar或predicted capture。缺少某个影响未来的计数器、FIFO前驱、在途请求或外部义务时明确unknown，不用“合理默认值”补齐。
4. **先完整模型，再研究增量。** 用同一新context分别计算保留初始后缀和可行修复后缀；只复用静态source proof和不含现场信息的合法元数据。不同事件版本不得复用旧预测结果。完整warm-start MPC先作为同信息参照，之后LNS和增量方法只改变候选/影响闭包的重算范围，不改变模型、来源守卫、保护规则或信息权限。
5. **递归影响闭包。** 从实际送达变化扩张至所有候选可访问的资源/服务及两次盘复用，包含新绕行资源和其使用者。闭包外未获实际owner兑现的边界不得按硬保证固定；闭包全域化必须如实记为无局部性优势。原有严格逐件完成约束不改成总和约束或带容差比较。
6. **先验证再提交一个授权分量。** 提案携带本次来源身份、固定已发前缀、模型代际、候选动作和逐件证据。提交前重采当前local view、own outbox/ACK及target identity，确认无新增/可能已发动作、服务窗口足以覆盖wire、静态/动态约束仍成立；只由目标owner使用原`client.submit`发其本地分量。实际ACK、边进入和完成证据仍由native后续闭合，模型通过不升格为原生保护证明。

原保护承诺和“在新事件下重算的保留后缀”应分别记录。若外生变化已经使原承诺不可兑现，只优于新的较差基线不能宣称保住原承诺；需输出环境/承诺失效和unknown/拒绝，不能在每次repair中静默抬高逐件参照。

### native动作语义不能省略的边界

- `cpp/ics_core/runtime/circulation_online_impl.hpp:90`登记route要求live session、owner protocol入口、合法时间/expiry、来源owner、不可重复request ID；它不是撤销接口。
- `cpp/ics_core/runtime/circulation_runtime_impl.hpp:491`在实际交付时复核bag/tray、generation/traversal、当前stationary前缀、owner、`allow_suffix_reroute`、有向边、可达性、已知故障、必要deadline及`can_enter`。检查通过的`updated`只表示偏好接收，不是硬接收/服务时窗预约。
- `cpp/ics_core/runtime/event_driven_junction.hpp:14697`只对仍通过shield且无已知故障的候选施加偏好；最新accepted intent可以覆盖同前缀旧偏好。T5未发后缀合同应比该能力更保守：冻结已经提交或可能提交的命令，不借覆盖能力假装撤回旧动作。
- `research_live_obligation_native_domain.py:128`中的`None`只记录`native_default_no_command`并让原执行器动态选择；它既不是固定走3，也不是清除已安装偏好。已有同实体pending/updated route时，不得用`None`伪装恢复默认。
- 允许的`prefer_8`仍须满足B本地8节点接收条件和wire窗口；已知满节点不能当作成功默认。所有retry沿用原request ID/payload；丢ACK不能发新ID重复派盘。

### 最小测试矩阵与升级门

| 层 | 必须保留的正例 | 必须拒绝或明确unknown的反例 |
|---|---|---|
| 实际来源/版本 | 同owner本次新pair、单调消息身份、当前admission与own提交前缀一致 | saved JSON/伪造typed对象；旧初始decision；旧future fork/capture；重复/乱序/过期消息；错误owner或代际 |
| later重建 | 受支持的stationary与已证moving entry；显式seed后首事件、服务时界、FIFO与原生有限参考一致 | 没有terminal receipt却按计时器宣布完成；缺FIFO/占用/移动entry；缺失或未支持协议状态时悄悄补默认值 |
| 动作同域 | `native_default`保留动态选择；`prefer_8`只安装本地合法偏好 | 将None转3；将已有route覆盖/失ACK视作未发；业务身份/generation/traversal变化；服务已越过wire窗口 |
| 已发前缀 | 原request身份、payload、已发/可能已发动作和同时间顺序保持不变 | 提交抛错后换ID重发；ACK缺失回退状态；已进入边后改变当前leg；误把`route_keys`缺项当未发证明 |
| 完成保护/闭包 | 完整五任务逐件无正退化，含两次盘复用；闭包达到真正不动点 | 漏掉第二次复用、候选新共享资源、远端FIFO；总和变好但单件变差；新增边界offer当promise；静默提高原承诺 |
| 成本/公平性 | 四方法同信息、同合法静态缓存/seed、同外生带与每owner最多32次预测；全部构造/close/提交/ACK计费 | 隐藏模型warmup、只给增量法缓存、把logical query当model call、超时/unknown删分母、以组件时间宣称100ms |

需用调用计数或fail-fast替身证明新触发后不调用旧初始frame/future-fork入口；仅有输出数值看似改变不足以证明用了新信息。另需一个确定的新送达事件使新context及至少一个候选预测确实改变，在相同新context上重算保留后缀，避免只修改trace标签。

九格通过之后，仍须依次完成：当前later输入/seed的纯正负门；同语义有限事件级parity；一次真实新pair触发且未发动作合法改变的受限原生门；再冻结三事件×两种子×四方法的24格。新增服务/故障域若与当前精确合同冲突，应另立明确授权、哈希冻结的合同版本及边界测试，保留旧拒绝域；不能直接放宽known-fault/pending-action等谓词。未实现的同域seeder、未完成的动作闭合或未覆盖的新合同应标记为未执行/unsupported，不包装成某方法的质量失败。

### 两动作的真实限制与下一件可编码工作

在上述B首复用触发点，原32向量中的initial action、首次空盘出发和首次return delay已经成为不可撤前缀；合法剩余自由度只有`native_default`与`prefer_8`两种。此时四种方法很可能都只需两次预测，不能用24格的名称或填充重复候选制造LNS/增量搜索headroom。该两动作域首先用于证明“新信息→同域重建→真实未发动作”的正确性；若闭包全域或强基线等价，明确报告。扩大到未来多次授权决策前应单独冻结动作域、来源及跨owner边界，不能让B在模型中决定A已发或无权承诺的return动作。

**下一件独立最小编码任务：**在新模块实现当前later-decision到不可变`LaterSeedSpecification`的数据桥，并配套一个专用测试文件，暂不接入online dispatcher、不发native。入口由活跃同owner collector提供信息与当前own提交前缀；纯层复用`later_context`/`revalidate`，输出当前epoch、target identity、固定已发前缀、完成receipts、稳定服务/entry事件、占用/FIFO证据和准确的二元later动作域；缺字段立即unknown。测试首先覆盖本节前四行和“旧初始future对象不能进入”的结构断言。该桥完成后下一步才实现消费这份specification的显式同语义later engine seeder及事件级parity；桥本身不算预测器、repair成功或T5完成。
