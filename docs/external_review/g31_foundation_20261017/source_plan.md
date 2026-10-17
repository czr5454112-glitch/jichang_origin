# G31 × ICS：底层建设与 Learning 实施任务书

**版本：2026-10-17 / v1.0**  
**用途：交给 Codex 连续执行；同时保存本轮研究判断、决策理由、代码事实与文献依据。**  
**近期目标：尽快得到可以训练的、具有真实有限托盘循环和区域自主控制的原生环境。**  
**最终目标：完整 R1／R2、严格逐件保护、既定 100 ms 指标、原始工作负载以及有强基线支持的方法贡献。**

本文中的任务与接口是待实施方向，不能当作当前代码已经具备这些功能的声明。本文记录关键判断、决策理由和证据边界。后续会话先读第 0 节的接续指令，再按第 4、5、9 节执行；需要架构细节时查第 1—3 节，文献定位见第 11—13 节。

---

## 0. 给 Codex 的执行指令：先把可学习的系统跑起来

### 0.1 可直接复制的任务指令

> 请依据本任务书，在当前 G31 × ICS 工作树继续实现。先核对实际分支、未提交修改和已有能力，跳过已经完成且仍有效的工作，不从头重写 G31。
>
> 第一优先级是打通“合法局部观察 → 候选 → 原有保护与提交 → 原生物理事件推进 → 下一次观察”的连续闭环，并让有限托盘经历载运、卸载释放、跨区返空、接收和再次装载。提供可以实际运行的 baseline、数据采集和学习入口。
>
> 同时复用已有候选结果启动离线排序学习的数据管道。随后改造提供器，使候选能按需评估；学习器应在昂贵推演之前工作。底层闭环达到本文件 L1 门槛后立即启动受限场景中的闭环 RL／影子学习，不等待全天实验、完整 100 ms 认证或全部异常修复完成。
>
> 保留原拓扑、物理容量、有限托盘、FIFO、合法信息、区内空盘模块职责、不可撤执行前缀和严格逐件保护。模型输出不能直接修改库存、托盘位置或执行权限。
>
> 每轮必须交付实际代码／可运行入口／样本或训练结果中的实质进展，并更新一份简明状态。不要只新增审计文档、milestone 编号或无目的地重跑已封存失败。遇到某项现场语义不明，明确阻塞范围，继续不依赖该问题的离线、影子及已有合法研究域工作。
>
> 现有执行权限、提交和测试门控继续遵守。本任务书调整研发顺序，不授权绕过运行时保护、外发资料或自行 commit／push。

### 0.2 本轮对旧任务书的明确调整

2026-10-16 任务书把 T5“事件后的后缀修复”放在 T6“学习”之前。根据用户本轮“尽快搭底层、进入 learning”的要求，调整为：

- **已有结果 → L0 管道测试、第一次排序训练，可以立即做。**
- **原生多步闭环与有限托盘复用 → L1 离线闭环 RL，可以尽早做。**
- **按需推演、异步刷新、事件修复，与数据采集和学习并行推进。**
- 实际接管与正式认证仍独立过门，不将学习启动解释为执行资格已经满足。
- 不以“尚未证明性能 headroom”为由阻止第一次训练；但在扩大训练预算或宣称算法价值前，必须检查动作空间与强参考是否确实还有改进空间。

旧任务书关于已发动作、信息权限、严格逐件保护、原始分母和既有失败记录的约束保留。旧实验已经冻结的预算、输入和结论不追溯改写；本文件的新实验另命名、另记录。

### 0.3 不变的研究对象

| 项目 | 本项目含义 | 不得偷换 |
|---|---|---|
| R1 | 区域控制器根据当前合法信息，随时按需更新载盘路线；单任务路由更新计算目标在 100 ms 内 | 只做一次初始路线；只有策略网络前向计时 |
| R2 | 根据载盘目的地、路线、卸载／存储过程预测未来空盘可用性，提前进行跨区空盘调度 | 仅统计当前库存；凭预测直接生成可用空盘 |
| 去中心化 | 控制权在合法 owner；观察为本地事实和实际送达消息；跨区接收由有权的接收方决定 | 用全局未来状态调度，再把结果分给多个 owner |
| 有限托盘 | 具有身份的同一批托盘持续载运、释放、返空、接收和复用 | 行李卸下后载具消失；缺盘时凭空补盘 |
| 物理系统 | 沿用成熟 G31 原生运行时、既有路由和 PIBT-lite 回退；不新增运行时全量 A* | 另建简化 Python 仿真替代真实资源语义 |
| 区内空盘模块 | 沿用已有模块职责，通过已有许可接口协调 | 新 R2 悄悄接管原模块内部调度 |
| 场景基准 | 原机场 151 节点、227 条有向边；原始 28,506 件业务、43,603 段，按原规则增流 | 改图、改容量、删任务或加盘制造算法收益 |
| 服务保护 | 按已定义参考和受保护业务逐件比较，保留严格标准 | 用平均 reward、FIFO 正确或截止期满足替代逐件不劣 |
| 论文目标 | 在 TRE／CIE 目标下形成有实证支撑的方法贡献 | 把工程接线、换名称或直接采用已有 RL 当作创新 |

以上项目数据与旧结论的出处见第 12 节。当前配置的现场真实性和全日可行性仍有未确认项，不能因表中写了原始规模就宣称已经校准完成。

---

## 1. 已经确定的判断：后续不再反复从零讨论

### D01：预测不必随每个物理事件完整重算

**成立的是架构判断，不是已经证明的项目性能。** 需求预测、空盘释放预测、候选推演、重规划、实际执行检查、模型参数训练是不同过程，可以采用不同节奏。

可复用旧预测或旧建议的条件是：相关事实仍适用、依赖未失效、已承诺／已发部分被保留，且动作在实际执行入口重新满足当前约束。遇到关键依赖改变，必须更新、修复、拒绝或采用合法回退，不能机械沿用旧方案。

多时间尺度与增量更新有直接文献先例；它们不能证明本项目应每隔某个固定秒数刷新，也不能自动证明 100 ms 达标。[L02][L04][L09][L18][L20][L23][L25][L26]

### D02：当前最直接的计算问题，不是“每次都重新预测订单”

10 月 17 日用户提供的审阅说明记录了 42 次初始 owner 调用：完整调用约 10.34—13.68 秒，中位 11.71 秒，0/42 ≤ 100 ms。整批提供器累计占 93.24%，其中同时包含上下文准备、检查、状态复制、候选推演和封存；不能称为“纯预测耗时”。其他采集、复验、复制和提交仍约 574—964 ms。[S01]

32 指的是 **32 个候选控制方案**，不是 32 件订单或 32 个未来时间点。当前先计算全部 32 个方案，再让选择器查询其中部分；少查询不会自动减少已发生的推演成本。[S01][S04]

**实施决定：先使候选按需评估，再让轻量学习器优先选择值得推演的候选。** 独立增加一个订单预测网络通常不能直接解决这条全 32 推演路径。

### D03：可以先学习，但必须区分四个门槛

| 门槛 | 可以开始的工作 | 必须已有 | 尚不构成准入要求 |
|---|---|---|---|
| **L0：离线管道／排序学习** | 数据导出、损失计算、第一次 ranker 训练 | 合法输入与标签分开；候选和结果可对应；按场景分组 | 动态 repair、100 ms、全日实验、已发现性能增益 |
| **L1：离线闭环 RL／影子学习** | 在隔离原生仿真中连续决策；记录影子提议；研究长期回报 | 合法观察、真实 R1／R2 决策机会、原生时间推进、有限盘复用、真实动作结果、稳定基线和逐件评价器 | 全部异常覆盖、最大规模、100 ms 认证、全域保护证明 |
| **L2：受限场景学习接管** | 学习提议经原保护和提交链实际执行 | 当前源／接收方检查；原逐件保护检查；超时、拒绝和失效处理；本范围配对闭环评估 | 对未测试范围的保证 |
| **L3：正式指标认证** | 对声明范围报告 R1／R2、时延、规模和服务保护结论 | 独立场景、全部分母、逐件结果、完整计时及对应证据 | 不把有限零违例外推为普遍定理 |

已有 3 场景 × 32 候选可用于 **L0 smoke test**，不能作为泛化数据集。禁止把同一场景的兄弟候选随机拆到训练和测试两边。L1 的关键是动作会真实改变后续状态；initial-only 的克隆评估不等于闭环 RL。

失败提议、被拒动作、实际损伤和 unknown 都可以成为隔离实验的研究数据，但不能被清洗成成功，也不能因训练可运行就通过 L2。

### D04：整体有可研究的空间，创新尚须用方法和证据落实

最近文献已经覆盖：示范学习行李路由、区域与路线两层反馈、有限车队重平衡、分布式契约、模板约束下学习、冻结部分轨迹的闭环分解、前序依赖下的局部修复、小网络下一跳路由。[L01]—[L11]

本项目值得集中研究的是：

> **在合法局部信息和真实执行承诺下，把载盘路线改变带来的释放时间／位置变化，与跨区空盘调拨对共享线路和下一轮服务的影响连接起来；利用这套循环依赖，减少必要重算，并学习多次托盘复用后的决策价值。**

这是一项待实现、待验证的贡献候选。实现协议、给依赖图命名或把现成算法串起来，不足以单独证明创新。不能使用“首次同时考虑载运和空载管理”这类与既有 BHS 文献冲突的说法。[L18][L19][L22]

### D05：学习的首个岗位确定，后续 RL 目标保留

第一落点是 **候选代价／排序**，用于在昂贵推演之前筛选；随后开展 **真正多步的 RL**，研究单次排序不能表达的未来复用取舍。

不一开始同时训练需求、释放 ETA、候选价值、通信和底层动作五套网络。PPL 与 DG-PG 都是可以对照和借鉴的既有方法，不是装上后就获得原创性的标签。[L12][L13]

### D06：底层事实、预测、承诺和实际执行分开

实体位置、载空状态、可再次使用的时刻只由 native 执行事实改变。预测输出建议；接收回执表达其实际支持的权限；真正发出和到达另有事实。

预测将在未来释放的空盘不能计入当前可用库存；收到接收 ACK 不等于到达；新计划不能删除已经发出的托盘。

### D07：严格逐件保护需要明确适用条件

在线库存／容量检查和“每件完成时间不劣于参考”不是同一个性质。保留原保护检查；需要后续轨迹才能知道的结果，使用同一外生轨迹和业务身份的配对评价。

一个简单的边界例子：源区只有一个空盘，两个未来在当前观测上无法区分；若现在把盘调走，其中一个未来立即出现本地需求，就可能比保留该盘的参考更慢。因此，不能对这种非平凡调盘策略无条件声称“对任意未知未来逐件不劣”。

应列明保护集合、参考策略、可知信息、时间范围及需求／接收承诺假设。**不得靠缩小既定保护集合或容忍小回归解决该问题。** 现阶段可以保持保守接管和离线研究，并行推进充分条件与反例分析。

---

## 2. 代码事实与最小改造边界

### 2.1 本次核对的版本

- 仓库：<https://github.com/czr5454112-glitch/jichang_origin>
- 研究分支：**codex/g31-ics-v3-circulation**。
- 本次读到该分支指向 **a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef**，提交时间 2026-10-16 04:02:32 UTC。[S04]
- 默认 main 分支仍是初始导入；**不要把 main 当作当前研究工作树。**
- 10 月 17 日计时与后续进度以用户附件为补充。本次没有重新运行 42 条 native 原始记录，也没有读取用户 Windows 上未提供的所有文件。[S01]

Codex 落地时以最新实际工作树为准，先记录与上述版本的差异。不要为回到旧快照覆盖本地修改。

### 2.2 已读入口和要改变的事情

下列路径均相对于仓库根目录，前缀为 scripts/experiments/g31_ics_circulation/，除非另有说明。

| 现有入口 | 已核对事实 | 近期改造 |
|---|---|---|
| live_obligation_online_initial_dispatch.py::choose_and_submit | 做初始观察、选择、复验和提交；不推进 native 时间；返回后 ACK／运输可能仍未结束 | 保留该基线入口；封装多事件生命周期，不能把 initial 对象伪装成事件后的新观察 |
| live_obligation_owned_initial_provider.py::evaluate_declared32 | 16 组 guarded context／前缀、32 个完整图克隆和后缀；全量成本先支付 | 保留 full32 teacher；新增受约束的按需评估通路 |
| live_obligation_owned_same_information_search.py | 使用原选择器，替换 provider／origin 的绑定 | 不只在末端改排序；保证未选候选确实没有被提前推演 |
| live_obligation_initial_decision_adapter_v2.py | 现有初始观察与执行前复验入口 | 查清哪些前提仅对 initial 成立；新增合法当前事件观察适配，不删除 freshness 检查 |
| native_host.py | 装载指定编译产物，使用成熟 G31 预处理和原生运行时 | 薄封装 reset／事件推进／结果读取；不新增 Python 实体库存或第二个物理时钟 |
| CandidateBatch／CandidateQueries、source_proof 等 | 当前有身份、来源和隔离约束 | 可减少重复静态工作；不能借 private token 或绕过构造规则伪造执行权限 |

若最新代码已经解决某项，复用并注明证据，不再次实现同一层。上表中的存在性与具体行为以 [S04] 已读文件及此前审阅记录为依据；未在本次逐文件重读的入口，先用 rg 定位核实。

### 2.3 要保留和优先修复的已知事实

1. 已有托盘身份／守恒、原生接收检查、已发状态与失败 unknown 记录有价值；沿用，不全面重写。
2. 旧保存机制例中，两个局部选择 12／25 拼接为 09，导致 reuse1、reuse2 比 incumbent 04 约晚 0.9 s。它证明条件性局部解不能任意拼接，不能直接称为所有新在线实验的损伤证书。[S02][S03]
3. 严格坐标搜索在旧三个保存场景中均用 14 次查询找到 finite32 最优；这些场景没有证明复杂搜索独有优势。[S02]
4. 原 profile 中全部边容量为 floor(length/2)，0.6 m 的 97→98（ICS103→ICS104）为 0；它是不可停留还是禁止通过等现场语义未明确。不得擅自 0→1。[S03]
5. EBS 的真实设备对应仍未确认；type 7 不自动等于 EBS，代理语义须标注。[S03]
6. 上述现场缺口可能阻塞原始全日认证，**不必阻塞已有合法研究域中的闭环环境与离线学习**。保持同图同物理规则，研究域与原流结果分开，未完成和不可行原任务仍保留在最终账本。

---

## 3. 最小架构：单一物理真值，区域控制持续工作

### 3.1 数据与权限分层

| 对象 | 持有者／可读范围 | 可以做什么 |
|---|---|---|
| NativeTruth | 原生仿真引擎；全局诊断器可只读 | 推进所有真实物理事件，维护托盘身份、线路容量、FIFO、装卸和接收事实 |
| OwnerObservation | 当前区域控制器 | 本地授权状态、静态公开图信息、已经送达的消息及其时间／版本 |
| ForecastAdvice | 由合法观察生成的模型／计划 | 提供到达、释放、代价或调盘建议；没有 native 执行权限 |
| CommitmentState | 有权的源／接收 owner 及原生接口 | 记录真实预留、接受、发出、取消完成和到达状态 |
| EvaluatorRecord | 离线评价器、训练标签生成 | 保存全局诊断、未来结果、逐件对照；不得反向补足 actor 在线观察 |

单进程和单个 native 事件队列不妨碍去中心化仿真；执行信息与权限必须被接口限制。无需先改造成多机微服务或多进程部署才能学习。

除 actor 输入外，还记录 guard_information_scope。预测性保护和候选筛选遵守声明的信息合同；native 对真实物理条件的检查仍使用原有执行权限。如果研发路径保留了读取更广状态的旧保护器，明确标注其范围，不能据此声称整个控制链已经满足局部信息执行。无需为第一次离线训练重写所有旧 guard，但不能用隐藏的全局判断取得允许／拒绝信号后隐去其信息来源。

### 3.2 六个过程使用不同接口和节奏

| 过程 | 首版实现 | 触发原则 |
|---|---|---|
| 原生事实更新 | 原事件队列、装卸、到达、故障、消息送达 | 按原事件语义处理 |
| R1 即时路由 | 既有 G31；之后接入合法局部学习评分 | 到达决策点或按需更新，不能被慢层周期限制 |
| 外生需求预测 | 可先不用；或仅用已知计划／历史统计基线 | 新合法计划、统计变化、周期到期 |
| 内生释放预测 | 从当前载盘、路线、卸载／EBS 和承诺构造未来供给估计 | 相关路线、服务、卸载、在途或承诺变化；周期兜底 |
| R2 预平衡／候选修复 | 简单因果基线 → 按需推演 → 学习排序／RL | 预计缺盘、边界变化、计划失效、周期兜底 |
| 参数训练 | 离线批次、随后影子训练更新 | 数据和验证驱动；不是每个物理事件都训练一次 |

**R2 不依赖先训练一个订单预测网络才能成立。** 当前载盘目的地、路线和服务状态本身就能提供释放预测；可先验证这一条因果链，再研究外生需求预测的额外价值。

### 3.3 必须分开的时钟与版本

- event_time_s：原生事件时间。
- compute_wall_ms：实际单调墙钟测得的计算用时。
- compute_cpu_ms：CPU 工作量，作为资源成本补充，不能和并行墙钟混为同一指标。
- forecast_step_s／forecast_horizon_s：预测离散精度与时域。
- refresh_due_s／max_age_s：刷新计划与允许的信息年龄。
- committed_actions：不可撤的具体动作集合；若用 committed_until_s，必须能映射到实际动作。
- model_version／dependency_versions／plan_generation：逻辑版本，不是物理时间。

离线加速仿真允许暂时同步求解，但须标为 offline_sync；它的轨迹可用于算法和数据研发，不能证明实际异步时效。之后提供 modeled_delay 或 realtime_async 模式。加速仿真跑得快，不代表计算完成前物理世界应多走那么多秒。

### 3.4 事件后的处理顺序

以下是语义伪代码，函数名待映射到现有 native API；不是声称仓库已有这些函数。

~~~python
def consume_event(event):
    # 原生引擎按既定次序应用物理事件且只应用一次；
    # 若回调收到的是已应用事件，这里不得再次推进。
    native.apply_event_once_if_needed(event)
    affected_owners = authorized_recipients(event)

    for owner in affected_owners:
        owner.view.apply_visible_fact_or_delivered_message(event)
        owner.commitments.reconcile(event)
        owner.forecasts.apply_fact_delta_once(event)

        if event.requires_r1_control(owner):
            # 可以读取仍有效的建议，不等待全量后台求解。
            proposal = r1_policy(owner.view, owner.forecasts.valid_advice())
            existing_guard_and_native_submit(owner, proposal)

        if event.is_plan_ready_for(owner):
            # 用返回时状态对齐剩余建议；它还不是已发动作。
            consume_result_at_current_state(owner, event.result)

        if event.requires_receiver_or_source_action(owner):
            # 实际发出入口再次检查；迟到 ACK 不绕过原 native 准入。
            handle_existing_transfer_protocol(owner, event)

        if relevant_refresh_trigger(owner, event):
            owner.refresh_dirty = True

        if owner.refresh_dirty and not owner.worker_busy and budget_available(owner):
            owner.refresh_dirty = False
            submit_immutable_legal_snapshot(owner)
~~~

每 owner 最多一个首版后台求解任务，并保留 dirty 标记合并重复触发。严重失效应立即禁止受影响的未发建议，不能等待 debounce 后才阻止坏动作。R1 的请求可用性不能被 R2 的限频限制。

完成的后台结果按当前状态处理；已经过期、相关依赖失效或没有可执行剩余的结果作废并记录。没有结果时，原控制链继续提供合法行为。**“沿用旧计划”只有通过当前检查的部分才可继续。**

offline_sync、modeled_delay、realtime_async 均经过同一结果消费入口。完成事件只结清对应 job_id，按 plan_generation、依赖和已消费标记检查；迟到或重复结果不能覆盖更新建议，也不能清除其他任务的 busy 状态。早期离线训练不要求先部署并行 worker。

同步 initial 的“整个求解期间原生状态不变”假设不能直接用于后台。异步模型只能读取经授权构造的不可变 as-of 快照；其预测资格与返回时的执行资格分开。需要扩展现有观察／评估接口时保留身份与来源校验，不能直接删除 require_current 或给旧 initial 对象改时间戳来绕过检查。

### 3.5 最小源／接收语义

优先复用 native 已有机制，不另造全局两阶段提交。

- 源方提出软候选；有权且实际可用时才形成有效源侧预留。
- 只有真正控制接收能力的 owner／原模块才能 ACCEPT。若现有接口只表达偏好，不能将其升级为硬预约。
- 发出时，再次检查实体归属、实际可用性、重复承诺、FIFO／共享资源、既有保护条件和有效接收能力。
- request_id 贯穿同一命令；重复消息按身份幂等处理。
- 已发出的动作不能因计划过期或 ACK 丢失改成“未发出”；不清空记录后以新 ID 再发。
- 不确定是否已经发出时保持 unknown／待核对状态，不能直接恢复库存或重发。
- **接收方 ACCEPT 后，不可仅凭本地 TTL 到期回收容量。** 源方可能已经发出而 DISPATCHED 消息仍在途。MVP 可以保留到实际到达或明确取消完成；如要超时回收，另说明延迟、发出截止和恢复条件。
- 源方对同一 request_id 串行决定发出或取消；取消后不因迟到接受而发出。已进入 EMITTED 不再走未发取消分支。

例如计划调 5 盘，已发 2 盘后失效：保留这 2 盘的在途事实和对应接收承诺，只修复或合法取消剩余 3 盘。各 owner 的消息副本不能被加总为额外实体。

### 3.6 缓存的最小正确边界

| 缓存类别 | 允许复用 | 必须更新／失效 |
|---|---|---|
| 静态图、距离、模型／源码绑定 | 依赖版本不变时常驻复用 | 代码、拓扑、模型、物理合同或绑定依赖改变 |
| 需求预测 | 相同可知信息和未发生部分 | 新已知需求、统计漂移、计划变更；实际到达不能再重复算进预测剩余 |
| 释放预测 | 相关路线、服务、EBS 和承诺仍一致的剩余部分 | 实际卸载、改路、排队变化、故障、接收变化；实际释放移出预测项 |
| 候选推演／代价 | 来源观察、动作、情景、模型和相关依赖均适用 | 相关依赖、动作可变域、时间窗或已发前缀改变 |
| 承诺与已发事实 | 独立于预测存续 | 只能由合法执行／取消／到达事实转移 |

缓存 key 不能只用全局 state_id，否则任何无关事件都导致全部失效；也不能只用 TTL 忽略已经改变的关键依赖。第一版先保证正确，再根据实际命中率细化依赖。

---

## 4. 七个实施工作包：输入、动作、交付、停止条件

所有新接口名称均为建议；能扩展已有文件就复用已有文件。目标是少量清晰入口，不是继续堆叠 v7／v8 wrapper。

### P0：一次性对齐本地能力与任务入口

**输入：** 当前工作树、本文件、第 12 节既有任务书及代码入口。

**动作：**

1. 记录分支、提交、未提交变更和 native 产物版本；确认研究工作树而非 main。
2. 用 rg 定位 reset、原生事件推进、观察、route／transfer 提交、ACK 处理、逐件评价和已有训练入口。
3. 用一张表标注“可复用／需薄封装／确实缺失”；标明哪些旧任务已完成。
4. 挑选已有合法研究域；不要先启动原来已经失败的 H86400 全日运行。

**交付：** 一份简明入口映射和当前状态；直接接着做 P1，不在此停轮。  
**停止条件：** 只有确实缺少运行材料才阻塞对应 native 任务；仍可推进保存数据的 L0。禁止编造缺失输入或换到简化物理系统冒充原实现。

### P1：最小原生学习环境与有限盘循环

**输入：** 现有 native host、G31 策略、合法观察与提交链。

**动作：**

1. 薄封装 reset、observe(owner)、candidates、submit、advance_to_next_decision、outcome。
2. 每一步返回实际执行事实和下一合法决策事件，不能把“提出动作”直接当“动作成功”。
3. 保留单一托盘身份：空盘、载盘、装卸／EBS 占盘、在途和可复用状态的转换均来自 native。
4. 覆盖正常循环、区域缺盘、R1／R2 共享受限线路、两个提议竞争同一资源这四类有区分力的情况。
5. 至少生成一条真实“载运 → 卸载释放 → 空盘跨区 → 接收 → 再次装载”的轨迹，并让后续策略继续被调用。
6. 与当前稳定基线配对读取逐件结果；原始业务身份不因多次运输腿而改变。

**交付：** 可运行的环境入口、基线闭环轨迹、精简字段说明、最小物理失败反例。  
**通过条件：** 托盘守恒与唯一实体成立；队列／接收语义真实；动作影响下一状态；真实多步 R1／R2 决策可观察。  
**停止条件：** 发现 baseline 本身破坏守恒或事件因果时，先修这一处；不扩大训练场景。未完成所有故障模型不阻塞已有效场景进入 L1。

### P2：把区域信息与共同执行接牢

**输入：** P1、原 source／receiver 检查、已知 12／25 混合反例。

**动作：**

1. actor 只获得 owner 允许读取的事实和已送达消息；诊断数据和训练 critic 数据另外传递。
2. 明确每类 R1／R2 动作的控制 owner；保留固定区内空盘模块权限。
3. 复用已有接收能力／预留接口实现第 3.5 节生命周期；无权限保证时，只能给条件性建议、拒绝或原回退。
4. 检验正常消息、迟到／重复 ACK、部分发出后拒绝。返回时复验之后，在真正 native 发出入口仍检查当前状态。
5. 对局部方案组合检查共同执行条件；不能因各自预测逐件安全，就任意取分量拼接。
6. 保留至少一个有实际作用的非默认 R2 动作；不能把所有调盘关掉后宣称联合控制有效。

**交付：** 合法观察和动作权限接口、小型正常／冲突轨迹、明确拒绝／unknown 状态。  
**通过条件：** 已知重复调配／组合问题被正确阻止或明确拒绝；有用调盘可以通过原接口实际发生。  
**停止条件：** 接口不支持的硬保证不虚构。继续当前许可下的可行子集和影子提议，不为补齐协议重建全局控制器。

**P1 与 P2 在声明范围通过，即具备 L1；数据采集和闭环 RL 不再等待 P4、P5 或 100 ms 认证。**

这里的 P2 通过指所声明训练场景内的合法观察、动作权限、原有保护及真实提交／拒绝闭环有效。尚未启用或覆盖的异常场景单列，不阻塞该范围的离线训练；与本次修改直接相关的既有门控仍须通过。

### P3：提供器按需计算，减少结构性开销

**输入：** evaluate_declared32、CandidateBatch／CandidateQueries、source_proof、现有选择器。

**动作顺序：**

1. 保留现有 full32 路径作为 teacher、旧实验复现和质量参照。
2. 新增通过合法当前观察构造的受约束评估器，支持只 evaluate 指定候选或一个必要共享前缀组；记录实际克隆、前缀和后缀数量。
3. 选择器拿到候选描述后先排序，评估预算内的候选。最终候选仍走原必要保护和执行前检查。
4. 候选 batch 封存后只解码一次；普通查询不重复读取整个批次；避免把可变内部对象泄露给调用者。
5. 把可验证的静态依赖绑定放到常驻启动或版本切换阶段；动态状态、消息和已发前缀的检查保留。
6. 先测量 state_clone、rollout、source_check、serialization 等互斥环节，再决定是否优化 native 队列／索引；不凭 93.24% 总占比猜内部最大项。
7. 不把所有实验取证复制强塞到每个请求；分离后仍记录研究成本，且不删除部署必要验证。

**交付：** full32 与 budgeted 两条可选通路；真实候选评估数和完整时间对照；必要隔离／语义回归证据。  
**通过条件：** 请求 K 个候选时，未请求部分没有被提前完整推演；选中候选保护未削弱。  
**停止条件：** 少算导致漏掉有益动作，就改排序、候选或预算，不删保护；若选完仍算 full32，先修接线，不继续扩大模型训练。

### P4：最小滚动释放预测与 R1↔R2 反馈

**输入：** P1/P2 产生的当前载盘、路线、卸载、EBS、接收及在途事实。

**动作：**

1. 输出分区未来释放曲线／ETA 桶和来源依赖，明确“预计释放、已承诺在途、当前可用”。
2. 先用现有运输／排队模型、已知计划和简单需求基线，构建可解释的跨区预平衡策略。
3. R1 改路或卸载时界变化必须更新相关释放预测；R2 实际发出造成的在途库存和线路占用必须影响后续 R1 观察或代价。
4. 实现 periodic、event、hybrid 三种刷新策略的配置；用事实增量更新未发生部分，不每步从零生成所有预测。
5. R2 只生成合法建议并经 P2 执行；预测未释放实体不得提前发出。
6. 不先规定“每 10 秒／60 秒就是项目周期”；按第 7 节测量后在新实验中登记候选参数。

**交付：** 一条 R1 改变释放、R2 改变后续拥堵／供盘的双向因果轨迹；三个刷新模式。  
**通过条件：** 至少一次真实事件之后预测和未发动作更新；物理状态随实际控制变化；单向与双向模式能清楚区分。  
**停止条件：** 当前场景没有复用机会或共享资源竞争，诊断激励与候选自由度；不通过改图、加盘或制造不合法消息来得到正例。

### P5：一个真实事件后的增量后缀修复

**输入：** 原生已发生事件、合法当前观察、已发前缀、未发候选与相关边界条件。

**动作：**

1. 先做卸载／接收时界变化或线路故障中的一个代表性场景。
2. 事件真实发生后，从当前状态修复受影响的可变后缀；不是重新建 initial 状态。
3. 依赖涵盖载盘路线、服务／EBS、空盘释放、跨区接收、下一次装载、FIFO 和共享资源；包括候选新路线可能触及的资源。
4. 冻结不可撤动作，检查跨边界条件；若影响传播，扩大修复范围，必要时退到同信息的更大范围求解或原合法行为。
5. 明确 repair 预算耗尽、无可行补丁、信息不足、承诺不确定时的结果。
6. 与可 warm-start 的滚动方法和义务邻域 LNS 同信息、同预算对照；不人为剥夺基线复用能力。

**交付：** “事件前 → 实际事件 → 新观察 → 后缀改变 → native 后续结果”的样本，及全量／增量成本对照。  
**通过条件：** 受影响处真正重估；已发部分未改写；失败完整保留。  
**停止条件：** 依赖常扩大到全系统就如实记录局部性界限；不截断必要远程影响。全部异常尚未实现，不妨碍 P1/P2 已就绪范围的学习。

### P6：数据、轻量 ranker、闭环 RL 三项连续交付

**输入：** 已有 full32 结果、P1/P2 轨迹、随后接入 P3—P5 的数据。

**动作：**

1. 立即做 L0：旧数据解析、分组、损失和一次训练 smoke test。
2. 按第 5 节生成一小批独立决策组与连续轨迹；不要等“大数据集准备好”。
3. 训练线性评分和小 MLP ranker，接入 P3，在同 K 下比较规则排序与学习排序。
4. 达到 L1 后提供真正闭环 RL 训练入口：策略在后续事件再次决策，动作影响下次释放、调盘和业务服务。
5. 可以先固定成熟 R1、学习 R2，以减小训练不稳定；随后必须补联合 R1／R2 或明确的双向控制实验，不能永久将研究目标缩成 R2 单模块。
6. 在同一环境提供 baseline、shadow、guarded_learning 三模式；shadow 不能改变实际控制轨迹。
7. RL 与 ranker 分别报告。若 RL 在预算内无增益，形成负结果和诊断，不无止境调参，也不把 ranker 改称已经解决长期 RL 问题。

**交付：** 小数据集和字段定义、ranker 模型／训练记录、RL 入口与真实多步 rollout、同预算评价表。  
**通过条件：** 可重放；无未来输入泄漏；至少报告一次独立评价的正／负结果。ranker 若宣称节省推演，必须实际位于昂贵评估之前；首版闭环 RL 不以该接线已经完成为启动条件。  
**停止条件：** 原生语义或数据污染时隔离该批；总 reward 提升但逐件目标退化时保持离线研究，不接管。PPL／DG-PG 无收益不应无限扩复杂度。

### 4.1 并行关系与本轮完成标准

~~~mermaid
flowchart TD
    A["P0 对齐实际入口"] --> B["P1/P2 原生闭环与权限"]
    A --> C["旧数据：L0 排序管道"]
    B --> D["L1 多步数据与 RL"]
    B --> E["P3 按需推演"]
    B --> F["P4/P5 滚动预测与修复"]
    C --> E
    D --> G["L2 接管；L3 单独认证"]
~~~

P3—P5 的后续成果接入同一学习环境，是能力增强，不是 L1 启动的前置条件。

**近期“底层搭好”的定义：** 有同一 native 运行时、有基线、有合法观察与提交、有真实多次托盘复用、有逐件评价、有可连续采样的学习接口。并不等于所有最终指标已认证。

第一轮连续执行至少应交付：

- 一个能运行的原生 baseline 闭环入口；
- 一份可训练样本及 L0 训练结果；
- P1/P2 的实际状态与一个明确缺口，或它们通过后的 L1 RL 启动记录；
- full32 与按需评估的接线改造结果，或明确的剩余依赖；
- 一页以内的下一步说明。

如某项确实被输入／权限阻塞，报告事实，不编造完成；完成其他已具备条件的项再停。

---

## 5. Learning 的具体合同

### 5.1 先提供共享候选评分接口

~~~python
scores = learner.score_candidates(
    observation=owner_observation,
    candidates=locally_proposable_candidates,
    model_version=model_version,
)
~~~

“可提议”不等于“已经获得执行许可”。R1 候选来自当前合法下一跳；R2 候选来自当前允许申请的跨区动作和时间选择。源方的 proposal mask 不能代替接收方 ACCEPT。

首版输入使用已有可靠特征：当前可用／预留空盘、FIFO 队首与等待、装卸／EBS 占用、已知在途量、释放 ETA、候选源／目的／预计占用、已送达接收摘要、信息年龄与缺失 mask。只保留当时允许读取的字段。

静态公开拓扑与预处理距离可以用；其他 owner 未公开队列、未来订单事件队列和未来真值拥堵不可以用。任意 ID 主要用于关联，不作为无含义的连续数值特征。

首版工程起点：线性模型，加一个约 32—64 维输入、两层 64 单元的小 MLP。候选使用共享评分，避免把固定 vector_00…31 当成最终固定动作空间。上述维度是实施假设，不是文献给出的最优参数。[L08][L11]

### 5.2 排序标签与轨迹标签分开保存

**决策组数据：**

~~~json
{
  "episode_id": "...",
  "decision_id": "...",
  "owner_id": "...",
  "observation_time_s": 0.0,
  "observation_schema_version": "...",
  "information_scope": "owner_local_delivered",
  "guard_information_scope": "...",
  "owner_observation": {},
  "observation_missing_mask": {},
  "snapshot_version": "...",
  "candidate_id": "...",
  "candidate_semantics": "...",
  "candidate_features": {},
  "proposal_mask": {},
  "conditioned_peer_behavior": {},
  "scenario_set_id": "...",
  "teacher_mode": "causal_rollout",
  "objective_version": "...",
  "cost_components": {},
  "per_job_outcomes": [],
  "protection_status": "passed|failed|unknown|not_checked",
  "evaluation_status": "completed|infeasible|unknown|truncated",
  "evaluated_candidate_count": 0
}
~~~

同一决策组的候选用相同外生随机带或情景组，防止噪声差异冒充动作效果。控制引起的内生事件可以不同。保留每项成本和逐件结果，不只存一个加权总分。

示例中的特征对象在实际数据中必须有可训练内容；也可存到可持久读取的独立特征记录，并保存其引用。只有 snapshot_version／哈希和标签，不能视为数据集已经可训练。

执行资格与价值标签完整性分开：保护失败或未知不得视为通过；代价评价截断／未知只表示长期价值尚未算完，不自动否定一个已经通过既有必要保护的动作。不得用回报 bootstrap 补成“保护通过”。

teacher_mode 至少区分：

- causal_rollout：只用决策时合法信息生成的预测情景；
- oracle_future：离线使用真实未来或其他特权信息的参考；
- realized_native：实际执行后观察到的结果。

可以用未来完成结果作监督标签／回报；不能让其进入对应决策时的输入。特权 teacher 可以单列实验，但不能与普通因果基线混在同信息主表。

旧 full32 中含完整组合方案时，必须保留它所条件化的对方行为与执行假设。模型不能从“这个组合预测好”直接推断自己有权提交所有 owner 的分量。

**时序轨迹数据：**

~~~text
episode_id, decision_id, owner_id, event_time_s
observation, observation_schema_version, legal_action_mask
proposed_action, submitted_action, executed_action, guard_outcome
request_id, protocol_status, action_origin, policy_version
next_observation, delta_sim_time_s
realized_cost_components, per_job_results
terminated, truncated, unknown_reason
runtime_mode, delay_model_version, compute_accounting
~~~

延迟执行的动作通过 request_id 关联。proposal 被拒或由回退替换时，不能把提议写成实际执行。算法若把“提议”作为 agent action，环境转移必须明确包含 guard／fallback；若训练执行动作价值，需保存对应行为来源，不把两种定义混用。

### 5.3 第一阶段：学代价或排序，真实减少推演

1. 先回归相对当前基线的代价差；必要时增加同一决策组中有明确差异的候选对排序损失。
2. 对硬不合法、保护失败、unknown 分别标记；不能将 unknown 填 0 成本。
3. 首个新预算实验可以试 K=8，之后再试 K=4；**K 是工程试验值，不是已批准的最优部署配置。**
4. 将基线候选纳入预算，或明确报告“Top-K 加基线”为 K+1；不能少报实际评估数。
5. 按需评估后的最终动作仍走原必要保护与 native 当前检查。
6. 保留一小部分独立 full32 评价，观察最优／近优候选保留率、决策 regret、计算量和逐件结果。
7. 在线不继续生成 full32 后再使用 ranker；那样不能获得声称的推演节省。

### 5.4 第二阶段：真正的连续决策 RL

优先使用现有可运行的离散 actor–critic／Q 学习实现，采用合法动作 mask 和小模型；没有明确瓶颈前不增加大型 GNN、Transformer 或跨 GPU 训练。执行角色不同的 R1／R2 可以使用角色特征或独立动作头，避免强迫它们共享无意义的动作编号。

环境应是连续事件决策过程；不同决策之间的物理时间间隔不等。必须记录 delta_sim_time_s，说明折扣与奖励按时间还是按决策步定义。可用时间相关折扣，或固定观察步长，但不能因事件密度不同给某方法凭空更多回报。

第一版回报可使用同一物理时间内的等待成本积分、已发生延误、空盘行程和计算成本；保留各分量。**硬约束不因加入大罚分就被替代。** 截断时保留未完成任务与在途盘；不能按已完成部分排名，或把尾部价值默认成 0。

至少有部分轨迹跨越两次完整复用；策略在后续合法事件继续决策。若短片段训练，保留状态连续性，并明确 bootstrap 或延续评价。原固定 H40 回归仍按旧定义执行，不能拿 H40 自动代表所有新场景都覆盖复用。

集中训练 critic 可在明确标注的训练实验中使用额外状态；actor 推理严格遵守 owner 观察合同。不要把“各 owner 各调一次全局模型”写成局部信息执行。

### 5.5 数据划分与预算

- 同一 episode、需求／故障外生轨迹及同一决策的所有候选放在同一数据分区。
- 旧 3 场景只做 smoke／机制检查；训练分布必须逐步加入独立场景，不能靠重复复制增加“独立样本量”。
- 新增训练场景沿用既定物理合同和原始生成规则；压力、盘数、故障等配置变体明确单列，各方法一致。
- 首次增量数据可目标为 200—500 个独立决策组，并设 **2 小时数据生成墙钟上限，先到即停做一次训练检查**；这是启动预算，不是统计充分性要求。达不到目标组数仍交付已有有效样本及吞吐瓶颈。
- 继续沿用上一任务书首轮单种子不超过 2 GPU 小时的上限。候选行、独立决策组和 RL transition 分别计数，第一轮不超过 2 万训练行／transition，避免用单位混淆扩大预算。
- 资源按 **一台 RTX 4070 电脑＋一台 RTX 5080 服务器**设计；CPU、RAM、软件环境由 Codex 实测登记。小模型先单卡训练，另一设备可独立验证，不要求双卡联合。
- 推演生成的 CPU／native 成本另记。若瓶颈是 Python 事件循环或状态复制，GPU 不会自动解决。
- 在线小批量评分同时测 CPU／GPU；不能假定 GPU 必快。先交一次学习曲线和结果，再扩大多种子实验。

### 5.6 PPL 与 DG-PG 的使用边界

PPL 处理离线策略学习中的覆盖／不确定性，相关保证要求其统计与行为概率条件；当前数据没有行为概率时，不能声称直接满足 PPL 保证。先可将悲观评分作为明确命名的启发式对照。[L12]

DG-PG 用解析参考引导策略梯度，需要参考方向与真实目标的关系及相应假设。库存平衡可能与逐件服务相冲突，不能未经验证用“更均衡”取代项目目标。其去中心化执行用语也不自动满足本项目 owner 信息权限。[L13]

先比较简单模型与标准 RL。只有明确发现候选覆盖、长时域价值或训练方差瓶颈，才增加这些方法；不得以方法名字较新作为采用理由。

---

## 6. 最少但有辨识力的验证

### 6.1 底层定向检查

不为每个低影响文档或封装改动新增测试。以下检查针对真实剩余风险；有现成对应测试则复用：

| 检查 | 要识别的问题 |
|---|---|
| 有限盘复用轨迹 | 释放、返空、再次装载是否真实；实体是否守恒 |
| 尚未送达信息 | 一条未送达库存消息、一个未发生订单是否泄漏到 actor |
| 重复／迟到 ACK | 是否重复发出、重复预留或错误释放容量 |
| 部分已发计划失效 | 是否只改可变后缀，保留在途事实 |
| 后台求解延迟 | 求解期间 native 事件是否正常发生；晚到结果是否按当前状态处理 |
| 影子隔离 | shadow 提议是否悄悄改变 native 控制轨迹 |
| 候选结构计数 | K 预算下是否仍预计算全部 32 |
| 已知局部组合反例 | 局部条件性保护是否被误当共同执行保证 |

后台延迟检查在 modeled_delay／realtime_async 模式下开展；不是 L0 的前提。初期 L1 可用明确标注的 offline_sync 模式研究控制，但不据此报告异步时效。

### 6.2 对照分组，避免一次铺开巨大矩阵

**A. 先验证计算岗位：**

- full32 同信息推演；
- 现有规则／坐标方法；
- 确定性顺序 Top-K 加同一推演器；
- 学习 Top-K 加同一推演器。

固定候选、预测情景、物理模型和目标。full32 不是与 Top-K 相同的计算预算，应作质量／成本参照；真正同预算比较在规则 K 与学习 K 之间。

**B. 再验证控制耦合：**

- 固定基线；
- 仅 R1 可变、R2 保持既定基线；
- 仅 R2 可变、R1 保持既定基线；
- 两者可变但只有 R1→R2 释放反馈；
- 两者可变且双向反馈。

保持观测、可执行动作与硬约束一致。比较新增反馈信息时要明确它就是被操纵因素，不能把信息增加和算法改进混为一项收益。

**C. 验证刷新与修复：**

- 每次相关决策全量重估；
- 周期更新；
- 事件更新；
- 周期＋事件；
- 同信息全范围 warm-start 与增量后缀修复。

先正常、需求变化、释放／接收变化、共享线路故障、延迟消息／部分发出各一个有区分力场景，再扩展。旧已冻结实验保持原输入预算，不重新包装成新结果。

**D. 验证 learning 的独立价值：**

- 原基线；
- 简单规则／线性评分；
- MLP ranker；
- 标准闭环 RL；
- 有必要时才加 PPL 式悲观排序或 DG 引导。

所有学习方法经过同一执行链；报告提议被拒率与回退率，避免坏提议靠回退维持结果却被称为好策略。

### 6.3 必报结果

业务：原始任务数、完成／未完成／失败／unknown、逐件完成时刻与参考差、缺盘等待、迟到、尾部服务时间、EBS 占盘、空盘行程。

控制：R1／R2 实际动作数、真正预调盘次数、至少两轮复用的比例、拒绝／回退、重复承诺、冲突、受影响修复规模、消息数量／字节。

计算：实际候选与情景数、克隆与事件推进量、预测／推演／选择／检查／提交分项、后台资源占用、前台完整请求、信息年龄、截止期错失。

学习：独立组数、数据来源、训练时间、候选召回、regret、各项业务收益；不只给 RMSE、top-1 或 reward。

统计：小样本先报每个配对差异和失败原因；扩大后按 episode／外生轨迹做置信区间，不能把同一批候选视为独立统计样本。最大观测时延与样本量一并报告，不能用有限样本最大值冒充最坏情况证明。

---

## 7. 更新周期怎么选：先测，再登记实验参数

不把任何文献中的 0.5 s、10 s、20 步或 60 s 直接变成本项目周期。

至少测量：

1. 空盘从源到目标的运输时间及分布；
2. 接收申请、送达与必要确认的延迟；
3. 当前库存可覆盖本地需求多久；
4. 载盘预计释放与实际释放的偏差；
5. 高峰需求变化和缺盘的时间尺度；
6. 一次预测／推演的实际完成时间及 CPU 竞争影响；
7. 剩余动作的最早执行期限和真正不可撤部分。

可用下式作为**工程筛选关系**，不当稳定性定理：

\[
\text{发现缺口的剩余提前量}
>
\text{计算与确认延迟}
+
\text{调运提前量}
+
\text{误差余量}.
\]

若刷新后才发现缺口已经来不及到达，单纯降低预测频率没有意义。预测时域至少覆盖需要研究的调运／释放链；研究多次复用价值时，应覆盖相应循环或采用明确的延续价值。

| 事件 | 首先更新 | 何时升为重新求解 |
|---|---|---|
| 新订单／FIFO 队首变化 | 当前需求、等待与局部可行动作 | 缺口／服务风险明显改变，或当前建议不再可行 |
| R1 改路、卸载进度变化 | 相关托盘 ETA 和释放依赖 | 后续预调盘／接收／下一次装载计划受影响 |
| 实际释放、发出、到达 | 实体账本和预测剩余 | 实际与预测差异改变后续决策 |
| 故障、容量或接收改变 | 立即禁止相关非法未发动作 | 修复相关后缀，必要时扩域 |
| 晚到／拒绝／不确定 ACK | 请求生命周期和可兑现条件 | 尚未发动作无法继续；不能重发不确定实物 |
| 周期到期、小变化累积 | 标记 refresh_dirty | 合并后预算允许时刷新；关键失效不等待 |

第一轮比较的周期、阈值、max_age、时域、K、随机种子和外层预算在运行前写进配置。失败不临时加大预算后覆盖原记录。不要为了避免触发风暴延迟即时安全处理。

---

## 8. 100 ms 与后台计算的计量合同

### 8.1 保留历史目标，不通过改名字缩小范围

原需求明确单任务路由更新计算 100 ms 以内且请求可随时提出。旧长期任务书又要求按业务 request_id 和因果链计算完整必要处理。[S05][S06]

本文件允许研发阶段将前台、后台和训练分开实现，但**不自动批准把既有完整请求要求缩成网络前向或搜索内核**。

| 对象 | 计量要求 | 当前结论 |
|---|---|---|
| R1 按需路由更新 | 观察整理、特征／必要推理、候选、必要求解、当前复验及提交等完整必要计算 | 保留 100 ms 目标，尚未认证 |
| 请求同步等待预测／规划 | 该计算确实由请求必须完成，则保留在因果链 | 不能移出计时块后宣称达标 |
| 独立后台预测／R2 求解 | 单次计算、最大用时、总资源、队列和对前台的影响单报 | 可设计独立节奏；不据此自动豁免旧合同中适用的请求要求 |
| ACK／结果处理 | 归属请求的处理计算计入对应完整计算；必要等待进入响应／闭环时延 | 不能把返回 pending 当确认完成 |
| 实际运输 | 业务服务／交付指标 | 不把运输时间算成 CPU 求解，也不从服务指标删掉 |
| 参数训练 | 单独训练和数据生成预算 | 与请求计算区分，资源竞争仍需记录 |

如最终要为具体 R2 API 采用独立截止期，必须列“原要求→新接口→新增／改变的范围”，作为单独的合同解释或变更事项；未完成前不能在报告中擅自宣称它不受原要求约束。

### 8.2 同时保存四种时间

1. **完整控制计算**：原口径内的实际计算区间；嵌套区间不重复相加。并行时保留时间线、关键路径与 CPU 总量，不能把并行 CPU 总量直接当请求墙钟。
2. **可交付／可提交响应时间**：请求进入到取得有效决定／提交条件；包括相应排队及必要等待。
3. **协议确认闭环时间**：实际必要 ACK 和结果处理结束；pending／unknown 单列。
4. **物理服务完成时间**：运输、等待、卸载与最终业务完成。

必须区分冷启动、首次请求、常驻暖请求和一次性关闭。不能把 10 秒批次除以 100 个订单宣称单件 100 ms；也不能把只发生一次的服务退出成本机械加到每次暖请求。

### 8.3 后台是否真正独立的检查

如果后台任务被故意延迟或没有新结果，前台仍应能在当前合法信息下由现有控制链作出有效行为；若某请求必须等待新结果，它就具有同步依赖。

报告每个 owner 和全系统的后台调用次数、最长求解、累计 CPU／GPU、阻塞、前台 P50/P95/P99/最大值、超时数、信息年龄与陈旧结果丢弃率。0 个观测超时只能说明测试范围结果，不能代替硬实时证明。

现有 42 次计时中其余环节本身仍超过 100 ms，因此“把提供器放后台”不是完整性能解决方案。[S01]

---

## 9. 交付组织与继续执行规则

### 9.1 建议一个统一 CLI，避免很多不可发现入口

优先扩展现有 runner；若没有合适入口，建议新增：

- scripts/experiments/g31_ics_circulation/learning_env.py
- scripts/experiments/g31_ics_circulation/run_learning_pipeline.py
- configs/g31_ics_circulation/learning_pilot_v1.json

这些是**建议的新路径，不是已经存在或测试通过的文件**。功能边界为环境适配、统一入口和配置；底层模型、协议、评估器尽量复用已有实现。

统一入口至少支持以下子命令；具体参数按现有代码规范实现并在 --help 说明：

~~~bash
python -m scripts.experiments.g31_ics_circulation.run_learning_pipeline smoke --config CONFIG
python -m scripts.experiments.g31_ics_circulation.run_learning_pipeline collect --config CONFIG
python -m scripts.experiments.g31_ics_circulation.run_learning_pipeline train-ranker --config CONFIG
python -m scripts.experiments.g31_ics_circulation.run_learning_pipeline train-rl --config CONFIG
python -m scripts.experiments.g31_ics_circulation.run_learning_pipeline evaluate --config CONFIG
~~~

以上是需交付的命令规范；CONFIG 为实际生成的配置路径，当前不得声称命令已经可执行。

配置至少记录：物理合同／数据版本、合法信息范围、原生版本、run_mode、baseline、learner、刷新机制、候选／情景预算、时域、随机带、保护参考、计算延迟模式、日志位置。

### 9.2 最少交付文件

沿用现有 docs/g31_ics_circulation/NEXT_ACTION.md，增加或复用一份 LEARNING_READINESS.md，记录 L0—L3 各自证据与范围即可。结果文件集中放入一个新实验目录，保存：

- 配置与输入身份；
- 事件／动作／学习样本；
- 逐件结果与计时摘要；
- 模型和训练摘要；
- 一份正／负／unknown 结论。

不要求为了每个小补丁创建新的大审计目录或长篇报告。版本与出处用于重现，不应成为替代实现进展的工作。

### 9.3 三轮连续推进的产出

| 连续执行轮次 | 主任务 | 结束时必须能看到的实质产出 |
|---|---|---|
| 第 1 轮 | P0，P1/P2 薄封装，旧数据 L0，启动 P3 | baseline 闭环或明确的最小缺口；小样本；第一次训练 smoke；按需提供器进度 |
| 第 2 轮 | L1 连续轨迹，P3 学习 Top-K，P4 最小释放预测 | 真正多步 RL 入口及首轮结果；R1→释放→R2→后续状态的轨迹 |
| 第 3 轮 | P5 一个事件修复，双向与同预算对照 | 独立场景正／负结果；L2 范围判断；100 ms 剩余瓶颈 |

这是依赖顺序，不是未经测量的天数保证。已有成果可以直接跨过相应工作。

### 9.4 什么时候停、什么时候继续

- 相同失败输入无实现变化：不原样重跑。
- 场景没有区分力：诊断需求／复用／候选是否有作用，不调 reward 硬造提升。
- 当前有限候选集与既定时域内的全量参考无增益：记录该范围的饱和，不外推为整个 RL 问题没有长期价值。继续已准入的首次闭环训练，并用原约束内的多次复用轨迹检查更长时域。
- 输入语义不明：阻塞对应全域主张，继续已声明研究域与离线工作。
- 学习提议过多被拒：报告并修正动作生成／奖励，不隐藏回退成本。
- 本轮达到学习准入：立即训练一次，不再新增无关准入条件。
- 已有门控直接关系本次语义修改：完成必要检查；不能以“尽快 learning”为理由绕开。
- 仅理论普适性未证明：继续实现和有限范围实验，结论保持条件化。

每轮汇报固定四项：**改了什么；实际跑了什么；结果和局限是什么；下一项最具体的动作是什么。**

---

## 10. 创新定位与文献到实施的映射

| 近邻工作 | 已有重合 | 本项目需要另外证明的内容 |
|---|---|---|
| CASE 2025 [L01] | 规划示范、行李路由学习 | 有限载具循环、合法局部信息和载空联合执行 |
| T2BR 2025 [L02] | 区域重定位＋路线选择、两层反馈、学习 | 托盘释放的内生依赖、共享线路／FIFO、实际接收权和逐件保护 |
| TAC 2026 [L03] | 私有事件、分布式控制、FIFO／容量、契约协商 | 延迟消息下的物理兑现，以及时限／逐件服务性质 |
| NAHS 2026 [L04] | 增量契约、许可模板、约束下学习 | 连续到达有限盘循环、实际已发前缀与计算时限 |
| GRAND 2026 [L05] | 有限车队、RL 指导供给分布、重平衡与局部匹配 | owner 信息边界和承诺、多轮释放依赖、相同服务目标下收益 |
| FICO 2026 [L06] | 有限时域、冻结兼容轨迹、冲突组分解与扩展 | 载运／卸载／返空服务依赖及边界条件是否带来额外方法价值 |
| 前序 LNS 2026 [L07] | successor closure、边界重定时、指派与路径修复 | 在线局部可知信息下的增量结构；不能只将 task 改叫 tray |
| OHT 2026 [L08] | 共享小网络、局部下一跳、离线初始化与在线学习 | 双向 R1/R2 和有限托盘供给循环，而非只有路由 |
| OnlineGGO 2025 [L09] | 慢速更新引导图、快速逐步行动 | 面向释放／接收风险的触发条件和实际收益 |
| Choi 2024 [L11] | 学习行程代价以减少完整路径计算 | 局部合法特征、真实按需推演和相同预算控制效果 |
| BHS 综合 MPC [L18] | 载运、空载管理、EBS、有限容量的联合控制 | 去中心化条件下可执行的循环优化／学习方法 |

**可能形成的方法贡献应至少落实其中一项，并与适配后的强方法比较：**

1. 能明确表示多次托盘复用和已承诺服务依赖的紧凑状态／边界摘要，并解释为何足以支持某类局部修改；
2. 在声明假设下的可执行补丁条件或合理分解方法，测得较少重算／通信且保持服务表现；
3. 学习候选／延续价值后，在相同信息与预算下获得强规则、warm-start MPC／LNS 无法同样得到的收益。

第一项问题建模、第二项方法、第三项实验相互支持。基础系统先复用成熟方法搭好；不要为了抢“新算法”名称延误可运行环境，也不要因底层已跑通就宣称创新已经成立。

---

## 11. 文献台账：近年重点、支持范围与不能推出的结论

本节与第 13 节保存本轮已经使用的研究依据。**FULL** 表示本轮研究链中取得并核读原文；**PARTIAL** 表示摘要／导言／特定章节；**META** 表示只确认元数据。并非本次生成文件时重新逐篇复现。公开预印本采用所列版本，正式出版状态单独注明。

页码按核读的 PDF 文件计算；不能把不同版本页码混用。没有可靠定位的内容用章节说明；未报告的运行频率／时延不补猜。文献参数是原论文实验参数，不是项目新合同。

### L01 — 行李路由的示范学习，2025（FULL）

**Tian, Keyu; Zeng, Li.** *Learning Optimal Baggage Routing from Expert Demonstrations.* IEEE CASE 2025, 1604–1610.  
DOI：<https://doi.org/10.1109/CASE58245.2025.11163851>

核读：用户上传 7 页全文；重点 §III-A—C（PDF 3—4 页）、§IV（5—6 页）。全局行李状态与联合分流器动作；Dijkstra／回溯示范后学习 VBIRL。12／28 节点、4／10 件行李，到达目的地后移除。支持先用规划示范学习，未建立有限盘回收和区域局部执行。未报告可用于本项目的实际推理硬件／100 ms 保证。

### L02 — T2BR 两层重定位，2025（FULL）

**Chen, Taijie; Liu, Jingyun; Feng, Siyuan; Qiu, Jiandong; Ke, Jintao.** *T2BR: A Hierarchical Repositioning Approach for Autonomous Mobility on Demand Systems.* IEEE TITS 26(12), 23139–23150, 2025.  
DOI：<https://doi.org/10.1109/TITS.2025.3620346>

核读：用户上传 12 页全文；§IV（PDF 4—5 页）区域 MAAC 与路线 MCTS，底层收益反馈；使用平台全局区域供需。§VII-C（9 页）每 60 仿真秒批量决定空闲车重定位；表 IV 为系统批次 0.687／0.977／1.949 s，不能当单任务 100 ms。实验含 32 区域、4,474 节点、65,955 订单；i9-10900X、128 GB、两张 4090。有限车队复用已有，但不是本项目严格逐件保护和接收权限模型。

### L03 — 分布式／去中心化监督控制，2026（FULL）

**Mainhardt, Ana Maria; Schmuck, Anne-Kathrin.** *Synthesis of Distributed and Decentralized Supervisory Control via Contract Negotiation.* IEEE TAC 71(9), 5892–5907, 2026.  
DOI：<https://doi.org/10.1109/TAC.2026.3682203>；[正式入口](https://ieeexplore.ieee.org/document/11477111)

核读：用户上传 16 页全文。§I-A（PDF 1—2 页）有私有事件、FIFO 缓冲、容量和不同控制者；§VI（7—9 页）说明兼容不自动等于非阻塞。§VII-C Remark 10 不提供一般终止保证；§VIII 的信号假设不能直接搬到延迟／乱序消息。§IX 报的是离散控制器综合计算，不是机场请求 100 ms；非阻塞也不等于逐件时限／不劣。

### L04 — 不确定性下的契约与增量学习约束，2026（FULL）

**Anand, Ashwani; Nayak, Satya Prakash; Schmuck, Anne-Kathrin.** *Contract-based multi-agent logical controller synthesis under uncertainty.* Nonlinear Analysis: Hybrid Systems 62, 101783, 2026.  
DOI：<https://doi.org/10.1016/j.nahs.2026.101783>；[出版商](https://www.sciencedirect.com/science/article/pii/S1751570X26001093)

核读：用户上传 30 页全文。§7.2（PDF 19 页）新目标兼容时可复用并合取模板，不必重新协商；§7.3（20—21 页）约束学习策略。给定联合博弈结构，不是本项目的局部库存 API。不同算法变体的完备性条件不同；几乎必然最终满足不能当有限业务时限。M1 Pro／16 GB、部分综合 300 s 超时，不能支持请求 100 ms。

### L05 — GRAND，2026（FULL；正式期刊）

**Gaber, Johannes; Alharbi, Meshal; Gammelli, Daniele; Zardini, Gioele.** *GRAND: Guidance, Rebalancing, and Assignment for Networked Dispatch in Multi-Agent Path Finding.* IEEE RA-L 11(5), 5470–5477, 2026.  
DOI：<https://doi.org/10.1109/LRA.2026.3673902>  
核读版本：[arXiv 2512.03194v3](https://arxiv.org/html/2512.03194v3)，2026-03-04；初稿 2025-12-02。

§IV—VI：全局 GNN／SAC 指导空闲车分布，最小费用流重平衡，区域匹配。有限车队持续接续任务，不能说它没有复用。§IV 的 1 s 是调度与路径规划共享的系统步预算。§VII 最高 500 agents；评估 Ryzen 7 5825U、单线程、16 GB，训练 RTX 8000。目标为吞吐，既有全局信息与固定任务积压，不等价于本项目合法局部信息及逐件保护。

### L06 — FICO，2026 版本（FULL；预印本）

**Li, Jiarui; Zanardi, Alessandro; Pecora, Federico; Zhang, Runyu; Zardini, Gioele.** *FICO: Finite-Horizon Closed-Loop Factorization for Unified Multi-Agent Path Finding.*  
[arXiv 2511.13961v3](https://arxiv.org/html/2511.13961v3)，2026-01-06；初稿 2025-11-17。未在本轮确认正式发表。

核读完整正文，重点 §IV—V。有限时域兼容轨迹、冻结外部部分、按冲突／可达影响分组，受阻时扩大组，已很接近“局部后缀修复”的一般结构。可借鉴闭环分解，但其 MAPF 假设不能直接推出托盘库存、owner 承诺或逐件保护性质。本文不把其算例时间换算为本项目 deadline。

### L07 — 前序约束下 LNS，2026（FULL；预印本）

**Parimi, Viraj; Williams, Brian C.** *Large Neighborhood Search for Multi-Agent Task Assignment and Path Finding with Precedence Constraints.*  
[arXiv 2603.28968v1](https://arxiv.org/html/2603.28968v1)，2026-03-30。AAAI 模板／版权字样不视作接收证明。

核读全文，重点 §2.2、§3、§5.2。离线已知任务和前序关系；successor closure、外部冻结占用、边界重定时与指派／路径修复。Local-PBS 的 local 是搜索范围，不代表局部控制权。实验 LNS 循环 60／180／300 s，另有初解和后处理；i9-14900K、C++。89.1% 是改善实例比例，不是改善幅度。属于必须正面对照的方法近邻。

### L08 — OHT 神经 Double Q 路由，2026（FULL；预印本）

**Gu, Cheng; Zhao, Qiusheng; Liu, Anbang; Lin, Shaochong; Shen, Max Z. J.** *Trajectory-Initialized Neural Double Q-Routing for Large-Scale Overhead Hoist Transport Systems.*  
[arXiv 2608.30512v1](https://arxiv.org/html/2608.30512v1)，2026-08-31。投稿标记不等于正式发表。

核读完整 HTML／PDF，重点 §III—VI（PDF 5—8 页起）。分叉事件的共享下一跳评分、小网络 5,825 参数、轨迹初始化，在线每 4 条 transition 更新。测试 3,684 节点／4,257 有向边、100／150／200 OHT。任务派发固定，未做预测空车预平衡；无实际端到端在线硬件时延证据。支持轻量实现，不证明我们的 100 ms。

### L09 — OnlineGGO，2025（FULL）

**Zang, Hongzhi; Zhang, Yulun; Jiang, He; Chen, Zhe; Harabor, Daniel; Stuckey, Peter J.; Li, Jiaoyang.** *Online Guidance Graph Optimization for Lifelong Multi-Agent Path Finding.* AAAI 39(14), 14726–14735, 2025.  
DOI：<https://doi.org/10.1609/aaai.v39i14.33614>；[原文 PDF](https://ojs.aaai.org/index.php/AAAI/article/download/33614/35769)；[代码](https://github.com/zanghz21/OnlineGGO)

核读全文，重点 §3 与实验。历史边流量／当前目标驱动引导图；CMA-ES 优化不能写成 RL。on+PIBT 等实验引导更新间隔 m=20 仿真步，底层仍逐步行动。它直接支持“较慢指导更新与较快行动可分离”的可行先例；不提供有限托盘接收协议或本项目更新周期。

### L10 — 制造任务与路径联合，2024（FULL）

**Liu, Shuo; Feng, Bohan; Bi, Youyi; Yu, Dan.** *An Integrated Approach to Precedence-Constrained Multi-Agent Task Assignment and Path Finding for Mobile Robots in Smart Manufacturing.* Applied Sciences 14(7), 3094, 2024.  
DOI：<https://doi.org/10.3390/app14073094>；[出版商全文](https://www.mdpi.com/2076-3417/14/7/3094)

核读全文，重点 §2—3 和实验。有限机器人、空驶取货＋载运、机器时隙、任务前序、路径成本反馈已有。集中贪心与 RSS／LBS、静态已知任务，不是异步 owner 权限。13×18 布局、5／10 机器人；某 60 任务配置 0.254 s 不可推广为最坏 100 ms。2024 文为会议工作的扩展。

### L11 — DNN 行程代价近似，2024（FULL）

**Choi, Jaewon; Yu, Taeyoung; Choi, Dong Gu.** *Dynamic OHT Routing Using Travel Time Approximation Based on Deep Neural Network.* IEEE Access 12, 6900–6911, 2024.  
DOI：<https://doi.org/10.1109/ACCESS.2024.3351225>  
[核读的公开原始全文](https://www.researchgate.net/publication/377248097_Dynamic_OHT_Routing_using_Travel_Time_Approximation_based_on_Deep_Neural_Network)

重点 §III—VI。近端 k=5 边 Dijkstra＋远端 DNN 代价估计；输入含全网占用／任务统计，局部搜索不等于局部信息。固定派车，空闲车外环行驶；未做预测预平衡。60／165 车实验报告 100 次路由批次平均小于 0.5 s，不是单次最坏保证。IEEE PDF 直读失败，使用上述公开原文。

### L12 — PPL，2025 修订版（PARTIAL；重点方法核读）

**Jin, Ying; Ren, Zhimei; Yang, Zhuoran; Wang, Zhaoran.** *Policy learning “without” overlap: Pessimism and generalized empirical Bernstein’s inequality.*  
[arXiv 2212.09900v4](https://arxiv.org/abs/2212.09900v4)，2025-06-05；初稿 2022。这里记录所读修订稿，不补猜期刊状态。

用户上传 PPL(1).pdf，61 页。重点 §2（PDF 5 页）、§3（9—11 页）：离线上下文 bandit、行为倾向概率与悲观价值选择；无覆盖行动不能凭经验给保证。政策期望价值保证不是每件业务保证，也不是通用 MDP 订单预测算法。实施时先检查数据条件，不能只借方法名称。

### L13 — DG-PG，2026（PARTIAL；重点方法／输入核读，预印本）

**Yang, Shan; Liu, Yang.** *Descent-Guided Policy Gradient for Scalable Cooperative Multi-Agent Learning.*  
[arXiv 2602.20078v4](https://arxiv.org/html/2602.20078v4)，2026-09-26。

用户上传 v4，36 页；重点 §4（PDF 3—5 页）、§6（9 页）、附录 I.2（29—30 页）。解析参考引导、方向对齐与局部影响假设，参考可只在训练使用。实验 actor 的全局向量／摘要需与本项目权限区分。不要混用早期版本的 agent 数／复杂度；它不是订单预测，也不提供 ICS 时延保证。

### L14 — MapEx，2025（FULL；仅方法借鉴）

**Ho, Cherie; Kim, Seungchan; 等。** *MapEx: Indoor Structure Exploration with Probabilistic Information Gain from Global Map Predictions.* ICRA 2025, 13074–13080.  
DOI：<https://doi.org/10.1109/ICRA55743.2025.11128862>；[项目与论文](https://mapex-explorer.github.io/)；[arXiv](https://arxiv.org/abs/2409.15590)

用户上传 2409.15590v3.pdf，7 页，2025-07-16。未知室内地图探索、地图预测集合与信息增益，不是托盘调度、MAPF 或上述两篇学习方法之一。保留概率预测／不确定性思路，不列为本项目主要调度基线。

### L15 — 多组件契约协商，2025（META）

**Mainhardt, Ana Maria; Schmuck, Anne-Kathrin.** *Distributed Contract Negotiation for Decentralised Supervisory Control beyond Two-Component Architectures.* IEEE CDC 2025.  
DOI：<https://doi.org/10.1109/CDC57313.2025.11312105>；[作者研究页](https://cossy.mpi-sws.org/research/assume-guarantee-sct/)

确认正式条目，未取得全文。不能详细断言其算法／性能；但已有 beyond two-component 研究，故不能仅用“两区域扩到多区域”声称创新。作者页题名存在 Two-Components 的写法差异，引用最终正式元数据时核对。

### L16 — HarmonyRouting，2026（PARTIAL）

**Kang, Younkook; Im, Kwangyoung; Lee, Sangmin; Cho, Sungzoon.** *HarmonyRouting with traffic impact prediction based on graph neural network for large-scale semiconductor fabrication.* Engineering Applications of Artificial Intelligence 167, 113850, 2026.  
DOI：<https://doi.org/10.1016/j.engappai.2026.113850>；[出版商入口](https://www.sciencedirect.com/science/article/pii/S0952197626001314)

取得出版商元数据、摘要／导言，未全文核读。系统交通影响预测与分区 GNN 和本项目计算／拥堵主题相关；此处不填其完整权限、周期、硬件或安全机制。不得将它从重合分析中抹去，也不声称已经完成方法复现。

### L17 — 项目相关的 IoT 行李路由，2023（PARTIAL）

**Yang, Xiuqing; Feng, Ruchen; Xu, Pengcheng; Wang, Xiaorui; Qi, Mingyao.** *Internet-of-Things-augmented dynamic route planning approach to the airport baggage handling system.* Computers & Industrial Engineering 175, 108802, 2023；在线 2022。  
DOI：<https://doi.org/10.1016/j.cie.2022.108802>；[出版商入口](https://www.sciencedirect.com/science/article/pii/S0360835222007902)

本轮取得摘要／导言等部分；集中 HCA* 动态路由框架。冯汝琛 2022 学位论文另已核读，不能将学位论文某项假设直接当成期刊每个版本的已核实细节。现有 G31 路由与该研究的关系保留，期刊完整有限盘管理／具体更新机制待全文确认。

## 12. 项目材料与结论出处

| 编号 | 材料 | 核读／使用范围 |
|---|---|---|
| S01 | GPTPRO_100MS与多时间尺度预测调度审阅请求_20261017.md | 本次直接读全文；42 次计时、当前 full32 和咨询边界；原始 raw 本次未重跑 |
| S02 | G31_Codex_下一轮任务书_20261016.md | 本次读全文与 T4—T6 原文；保留约束，调整离线／影子学习排序 |
| S03 | G31_独立审阅与下一阶段决策_20261016.md | 前序已核读；保存反例、物理语义、热路径与创新判断 |
| S04 | 研究分支 a7f7821f… 的 dispatch、provider、owned search、native_host、NEXT_ACTION.md | 本次读取指定版本；分支指向本次再核对 |
| S05 | G31_ICS_LT2_LONG_TERM_CODEX_PLAN_20261014.md | 前序已核读；原需求追溯、长期方向和完整计算口径 |
| S06 | 问题及约束说明.docx；设备故障处置建议及紧急自动处理问题说明(3).docx | 前序核读原始需求；R1 100 ms、R2 释放预测和跨区预平衡、保留区内模块 |
| S07 | 冯汝琛硕士论文《基于物联网的机场行李处理系统动态路由规划方法》 | 原稿为 2022 年 5 月；学号 2019210484 不是发表年份；该版装载时总有空载具、卸载后移除的假设不能直接充当有限闭环底层 |
| S08 | 用户本轮指示：保存研究记录、生成 Codex MD、尽快底层进入 learning | 本文件调整研发顺序的依据；不自动授权改变目标或推送代码 |

重要代码／旧长期计划的稳定链接：

- [dispatch](https://github.com/czr5454112-glitch/jichang_origin/blob/a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef/scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py)
- [provider](https://github.com/czr5454112-glitch/jichang_origin/blob/a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef/scripts/experiments/g31_ics_circulation/live_obligation_owned_initial_provider.py)
- [owned search](https://github.com/czr5454112-glitch/jichang_origin/blob/a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef/scripts/experiments/g31_ics_circulation/live_obligation_owned_same_information_search.py)
- [native_host](https://github.com/czr5454112-glitch/jichang_origin/blob/a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef/scripts/experiments/g31_ics_circulation/native_host.py)
- [长期任务书](https://github.com/czr5454112-glitch/jichang_origin/blob/a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef/docs/external_review/g31_ics_lt2_20261014/G31_ICS_LT2_LONG_TERM_CODEX_PLAN_20261014.md)

若 Codex 缺少旧上传文件，先使用本文件明确摘录的事实和边界继续；确实需要其原始数据的任务标为缺材料。不要假称可以访问另一个窗口或用户本地未提供的路径。

## 13. 基础文献与保留线索

### 13.1 直接 BHS 建模基础：老文献仍用于排除错误“首次”主张

**L18 — Zeinaly, Yashar; De Schutter, Bart; Hellendoorn, Hans. (2015).**  
*An Integrated Model Predictive Scheme for Baggage-Handling Systems: Routing, Line Balancing, and Empty-Cart Management.* IEEE TCST 23(4), 1536–1545.  
DOI：<https://doi.org/10.1109/TCST.2014.2363135>；[作者原文](https://www.bartdeschutter.org/publications/15-019-integrated-model-predictive-scheme/15-019-integrated-model-predictive-scheme.pdf)

**FULL**，作者稿 17 PDF 页含封面，重点系统模型、MPC 与 Table II。集中式有限流／容量、载空共享线路、EBS 占载具、卸载回供已有。13 节点案例，Ts=0.5 s、Np=8；LP 平均 0.1902 s、最大 0.3299 s，迭代 LP 平均约 1.0185 s；E8400 3 GHz／4 GB。软时间成本不等于逐件不劣，旧解初始化不等于旧计划当前仍合法。

**L19 — Zeinaly, Yashar; De Schutter, Bart; Hellendoorn, Hans. (2012).**  
*A Model Predictive Control Approach for the Line Balancing in Baggage Handling Systems.* IFAC CTS 2012, 45(24), 215–220.  
DOI：<https://doi.org/10.3182/20120912-3-BG-2031.00043>；[作者原文](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/12_032.pdf)

**FULL**，重点模型、§3、§5。有限 120 DCV、2 装载点与车库，可在需求脉冲前调拨；控制步长 10 s、Np=5。物理队列事件可发生在控制间隔内。固定运输／返程延迟，未解决真实拥堵路由、局部权限和完整 EBS；不直接给本项目周期。

**L20 — Tarău, Alina N.; De Schutter, Bart; Hellendoorn, Hans. (2009).**  
*Hierarchical Route Choice Control for Baggage Handling Systems.* IEEE ITSC 2009, 679–684.  
DOI：<https://doi.org/10.1109/ITSC.2009.5309846>；[作者原文](https://www.bartdeschutter.org/publications/09-039-hierarchical-route-choice-control/09-039-hierarchical-route-choice-control.pdf)

**FULL**，重点 §II-B、§V。网络、道岔和车辆分层；案例网络层 60 s，道岔动作网格 2 s，但优化一次推进 15 步控制块，不能写成每 2 s 完整重算。存在上级监督，不等于目标去中心化闭环。

**L21 — Tarău, Alina N.; De Schutter, Bart; Hellendoorn, Hans. (2010).**  
*Predictive Control for Baggage Handling Systems Using Mixed Integer Linear Programming.* IFAC MCPL 2010, 16–21.  
DOI：<https://doi.org/10.3182/20100908-3-PT-3007.00004>；[作者原文](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/10_041.pdf)

**FULL**。集中载运行李路由，20 s 采样、8 步／160 s 预测时域，物理推进与预测离散分开。不能用来支持有限空盘回收、EBS 或本项目需求预测的刷新规则。

**L22 — Zeinaly, Yashar; De Schutter, Bart; Hellendoorn, Hans. (2013).**  
*A Model Predictive Approach for Baggage Handling Systems.* IEEE ITSC 2013, 687–693.  
DOI：<https://doi.org/10.1109/ITSC.2013.6728311>；[作者原文](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/13_031.pdf)

**FULL**。集中流模型包含有限堆栈、卸载返空延迟、EBS 和载空路径。Ts=0.5 s、Np=55；求解平均 0.7202 s、最大 1.8564 s。不能把采样周期当已证明的求解截止期。

### 13.2 事件触发、多速率和共享约束：理论可借鉴，适用条件不搬运

**L23 — Lehmann, Daniel; Henriksson, Erik; Johansson, Karl H. (2013).**  
*Event-Triggered Model Predictive Control of Discrete-Time Linear Systems Subject to Disturbances.* ECC 2013.  
DOI：<https://doi.org/10.23919/ECC.2013.6669580>；[作者原文](https://people.kth.se/~kallej/papers/event-triggered_ecc13.pdf)

已核读原文的触发设计与假设。支持在明确模型与扰动条件下按事件重新计算；离散线性系统性质不能直接移植到有限托盘、FIFO、异步承诺和逐件时限。

**L24 — Lu, Liang. (2015).**  
*Asynchronous Separable Self-triggered Model Predictive Control based on Relaxed Dynamic Programming.* IFAC-PapersOnLine, 2015.  
DOI：<https://doi.org/10.1016/j.ifacol.2015.09.092>；[公开原文](https://skoge.folk.ntnu.no/prost/proceedings/adchem2015/media/papers/0249.pdf)

已核读方法与假设。不同子系统可异步自行触发，但可分约束前提不等于共享托盘、接收容量和线路竞争。不能因为标题有 asynchronous 就认为已经解决项目消息协议。

**L25 — Farina, Marcello; Zhang, Xinglong; Scattolini, Riccardo. (2018).**  
*A hierarchical multi-rate MPC scheme for interconnected systems.* Automatica 90, 38–46.  
DOI：<https://doi.org/10.1016/j.automatica.2017.12.036>；[作者稿](https://arxiv.org/pdf/1705.08818)

已核读原文的多速率层级、兼容与稳定性条件。慢优化和快反馈可以分工，但不能把所有低层控制都称为快速重优化，更不能在缺少条件时移植稳定性保证。

**L26 — Gräfe, Alexander; Trimpe, Sebastian. (2025).**  
*Event-triggered Robust Model Predictive Control under Hard Computation Resource Constraints.* ECC 2025, 465–470.  
DOI：<https://doi.org/10.23919/ECC65951.2025.11187035>；[arXiv 2504.19540](https://arxiv.org/abs/2504.19540)；[机构正式记录](https://publications.rwth-aachen.de/record/1020179)

已核读原文的计算资源约束与算例条件。提醒触发频率还受计算预算影响；集中资源分配／独立无人机不是共享 ICS 资源协议，不直接提供机场 100 ms 结论。

**L27 — Picasso, Bruno; Zhang, Xinglong; Scattolini, Riccardo. (2016).**  
*Hierarchical Model Predictive Control of independent systems with joint constraints.* Automatica 74, 99–106.  
DOI：<https://doi.org/10.1016/j.automatica.2016.07.030>

**PARTIAL／替代材料**：核读的是 [Zhang 2018 博士论文](https://www.politesi.polimi.it/bitstream/10589/137898/1/2018_02_PhD_Zhang.pdf)第 2 章，未把它写成独立期刊 PDF 全文阅读。共享约束的采样端点与例中 slack 处理都有适用边界，不能直接当作每一物理时刻的严格安全证明。

### 13.3 交通重平衡与 MAPF：保留信息范围和时间口径

**L28 — Zhang, Rick; Rossi, Federico; Pavone, Marco. (2016).**  
*Model Predictive Control of Autonomous Mobility-on-Demand Systems.* ICRA 2016.  
DOI：<https://doi.org/10.1109/ICRA.2016.7487272>；[作者稿](https://arxiv.org/pdf/1509.03985)

**FULL**，重点需求模型、MPC 变体与实验。6 s 控制、2 min 需求重采样、15 min 时域；40 车／15 区，迭代中位 5.5 s。MPCS 因果预测与 MPCF 真实未来参考必须区别。无限道路容量、不含本项目 FIFO，不能直接迁移安全或时限。

**L29 — Wallar, Alex; van der Zee, Menno; Alonso-Mora, Javier; Rus, Daniela. (2018).**  
*Vehicle Rebalancing for Mobility-on-Demand Systems with Ride-Sharing.* IROS 2018, 4539–4546.  
DOI：<https://doi.org/10.1109/IROS.2018.8593743>；[作者原文](https://autonomousrobots.nl/assets/files/publications/18-wallar-iros.pdf)

**FULL**。30 s 批次、100 个粒子估计、61 区域、1,000—3,000 车辆；均值 2.08／3.31／3.85 s。预测时域未报告则不补猜。未服务／取消订单的指标不能等同全部任务逐件保护。

**L30 — Chen, Zhe; Harabor, Daniel; Li, Jiaoyang; Stuckey, Peter J. (2024).**  
*Traffic Flow Optimisation for Lifelong Multi-Agent Path Finding.* AAAI 38(18), 20674–20682.  
DOI：<https://doi.org/10.1609/aaai.v38i18.30054>；[正式入口](https://ojs.aaai.org/index.php/AAAI/article/view/30054)；[论文 PDF](https://ojs.aaai.org/index.php/AAAI/article/download/30054/31856)

**PARTIAL**，取得原始摘要／论文入口，保留流量引导与 lifelong MAPF 基线线索；本文不补充未核读的参数，也不据此断言具体安全性质。

**L31 — Chen, Zhe; Alonso-Mora, Javier; Bai, Xiaoshan; Harabor, Daniel D.; Stuckey, Peter J. (2021).**  
*Integrated Task Assignment and Path Planning for Capacitated Multi-Agent Pickup and Delivery.* IEEE RA-L 6(3), 5816–5823.  
DOI：<https://doi.org/10.1109/LRA.2021.3074883>；[arXiv 与正式元数据](https://arxiv.org/abs/2110.14891)

**PARTIAL**，本次确认原始摘要和正式元数据。边际代价指派、LNS、可多载机器人任务与路径耦合已有；详细机制仍需全文核读，作为后续强基线来源，不作为本文件执行保证。

### 13.4 更早的相关线索：保留记录，不算已完成全文对照

**L32 — Hallenborg, Kasper. (2007).**  
*Decentralized Scheduling of Baggage Handling Using Multi-agent Technologies.* In *Multiprocessor Scheduling, Theory and Applications*.  
DOI：<https://doi.org/10.5772/5232>；[出版商条目](https://www.intechopen.com/chapters/630)

**META**，已确认正式题名、作者和日期，未在本轮全文核读。不使用其细节判断有限托盘或实际保障；仅说明去中心化 BHS 并非新概念。

**L33 — Mukhutdinov, Dmitry; 等。 (2019).**  
*Multi-agent deep learning for simultaneous optimization for time and energy in distributed routing system.* Future Generation Computer Systems 94, 587–600.  
DOI：<https://doi.org/10.1016/j.future.2018.12.037>；[出版商摘要](https://www.sciencedirect.com/science/article/abs/pii/S0167739X18309087)

**PARTIAL**，本次核到出版商摘要与元数据，涉及分布式路由和行李系统应用；未把它当成本轮已经逐项复现的有限盘算法。

**L34 — Sørensen; Nielsen; Karstoft. (2020).**  
*Routing in congested baggage handling systems using deep reinforcement learning.*  
DOI：<https://doi.org/10.3233/ICA-190613>

**历史线索，全文未核读。** 保留论文身份；不填未经核准的周期、硬件、权限、空盘回收或保护机制。若要作为正式强基线，先取得原文并补齐适配边界。

### 13.5 文献使用规则

- 2024—2026 近邻支撑创新对比；较早论文支撑物理模型和控制概念的来源。
- 正式论文、预印本、学位论文和摘要线索分开标注。
- 全局观察、中央求解、局部搜索、局部控制权是不同概念。
- 车辆有限不自动等于托盘库存模型，但不能反过来声称其他研究没有有限资源复用。
- 求解周期、动作周期、预测时域、训练更新和运行耗时分别引用。
- 引用时给出实际采用的版本；不把论文假设当项目已满足条件。
- 新增文献按“题名／作者／年份／链接／核读范围／支持／限制”补入本表；不因引用数量多就宣布创新成立。

---

## 14. 下次接续时只需先确认这九件事

1. 实际工作树是否仍基于研究分支，哪些 P0—P6 已经完成？
2. L0／L1／L2／L3 分别到哪一层，证据覆盖什么范围？
3. 是否已经有真实的载运—释放—跨区空盘—再次装载轨迹？
4. actor 的输入是否仍只有合法本地事实和送达消息？
5. 按需路径实际推演多少候选，是否仍在后台偷偷算 full32？
6. 学习器是在昂贵推演之前起作用，还是只替换最终表内搜索？
7. 新事件是否改变过未发后缀，已发托盘和接收承诺是否保留？
8. 最新独立评价相对强基线是什么结果，哪些失败仍未解决？
9. 下一轮能交付的一个最具体功能／实验是什么？

**默认下一步：先运行可复用的基线与数据入口，尽快取得第一次可解释的学习结果；同时保留最终 R1／R2、严格逐件保护与实时性目标。**

[L01]: https://doi.org/10.1109/CASE58245.2025.11163851
[L02]: https://doi.org/10.1109/TITS.2025.3620346
[L03]: https://doi.org/10.1109/TAC.2026.3682203
[L04]: https://doi.org/10.1016/j.nahs.2026.101783
[L05]: https://doi.org/10.1109/LRA.2026.3673902
[L06]: https://arxiv.org/html/2511.13961v3
[L07]: https://arxiv.org/html/2603.28968v1
[L08]: https://arxiv.org/html/2608.30512v1
[L09]: https://doi.org/10.1609/aaai.v39i14.33614
[L10]: https://doi.org/10.3390/app14073094
[L11]: https://doi.org/10.1109/ACCESS.2024.3351225
[L12]: https://arxiv.org/abs/2212.09900v4
[L13]: https://arxiv.org/html/2602.20078v4
[L14]: https://doi.org/10.1109/ICRA55743.2025.11128862
[L15]: https://doi.org/10.1109/CDC57313.2025.11312105
[L16]: https://doi.org/10.1016/j.engappai.2026.113850
[L17]: https://doi.org/10.1016/j.cie.2022.108802
[L18]: https://doi.org/10.1109/TCST.2014.2363135
[L19]: https://doi.org/10.3182/20120912-3-BG-2031.00043
[L20]: https://doi.org/10.1109/ITSC.2009.5309846
[L21]: https://doi.org/10.3182/20100908-3-PT-3007.00004
[L22]: https://doi.org/10.1109/ITSC.2013.6728311
[L23]: https://doi.org/10.23919/ECC.2013.6669580
[L24]: https://doi.org/10.1016/j.ifacol.2015.09.092
[L25]: https://doi.org/10.1016/j.automatica.2017.12.036
[L26]: https://doi.org/10.23919/ECC65951.2025.11187035
[L27]: https://doi.org/10.1016/j.automatica.2016.07.030
[L28]: https://doi.org/10.1109/ICRA.2016.7487272
[L29]: https://doi.org/10.1109/IROS.2018.8593743
[L30]: https://doi.org/10.1609/aaai.v38i18.30054
[L31]: https://doi.org/10.1109/LRA.2021.3074883
[L32]: https://doi.org/10.5772/5232
[L33]: https://doi.org/10.1016/j.future.2018.12.037
[L34]: https://doi.org/10.3233/ICA-190613


