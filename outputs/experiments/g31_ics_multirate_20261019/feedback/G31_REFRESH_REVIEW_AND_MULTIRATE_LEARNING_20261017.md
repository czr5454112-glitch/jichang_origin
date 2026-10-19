# G31：服务刷新代码审阅、分层时效与下一步 learning 实施指导

初版日期：2026-10-17；航班信息补充更新：2026-10-18。对象：czr005／G31、去中心化有限托盘 ICS。供 Codex 在研究分支继续实施。

**10 月 18 日补充：把决策时已经收到的航班计划及更新，作为未来区域行李需求的可选先验；与当前载货过程产生的托盘释放预测结合。第 11 节给出源码依据、输入时点、最小接口、验证方法及新增原始文献。这个补充不推迟下述 P0，也不改变原物理合同和逐件保护。**

## 0. 本次结论与对旧指导的修订

**学习插入点已经找到，当前底座足以继续做受保护的初始 learning 闭环；有实际选择作用的多步 RL 尚未成立。上层托盘释放预测、候选推演与跨区预调度，不再统一要求每次完整请求在 100 ms 内完成。应改用动作截止期、预测适用期、数据年龄、前台非阻塞与逐件业务结果验收。**

这是根据用户本次提出的“底层调用和预测粒度不同”作出的架构与指标修订。修订理由来自职责与时间窗口的区别、实际源码结构，以及第 8 节核读文献；不是把当前超时改写为通过。

本文件优先于旧 `G31_LEARNING_UNBLOCK_GUIDANCE_20261017.md` 中“100 ms 最终要求不变”的笼统表述，以及阶段请求中继续把完整预测统一挂在 100 ms 下的要求。旧原始日志、失败标志与历史报告不改。区内单任务更新的原 100 ms 必要计算目标保留并明确其接口边界，端到端响应另受实际物理期限约束；本轮没有证明这一快速接口已达标。

**下一轮最多三个工作项：**

1. P0：接通现有冻结初始模型的实际选择与提交，完成最小原生配对。这是当前主线。
2. P1：建立一个慢预测期间底层持续运行、结果按真实返回时刻复验的最小异步实验。与 P0 并行，不要求先完成跨事件缓存。
3. P2：在 P0 后扩一个有限的自然场景批次，修正转移语义，逐步取得多步动作支持；按第 11 节逐步接入航班需求先验。航班接口、证据／物理 seed 分离仅作为可并行的小工程项，不再以微小复制提速或完整需求模型阻塞初始学习。

原任务持续有效：R1 区内路由与 R2 跨区托盘预平衡都要保留；R2 首先利用**当前载货目的地、路径、卸载／暂存与后续复用预测空盘释放**。未来逐件入流尚不可知，不妨碍使用当时已经收到的航班计划估计需求：建议增加独立、可选的航班需求先验，形成“需求预测＋内生释放预测”。完整需求预测器不是开始 P0 learning 的新前置条件；计划也不能被展开成已发生的未来 job 或真实可用库存。

## 1. 审阅对象与可信度

### 1.1 精确身份

本次实际读取本地附件、解压源码和原始证据，并非只阅读两个概述文件。

| 项目 | 身份 |
|---|---|
| 入口文件 | `G31_给GPTPro的审阅请求_20261017.md`、`SERVICE_REFRESH_EXECUTION_20261017.md`、100 ms 架构审阅请求 |
| 代码证据包 | `G31_20261017_服务刷新与学习阶段审阅证据.zip` |
| ZIP 大小 | 25,499,857 字节 |
| ZIP SHA-256 | `d59a41b3b51b1adfefb3bbef19ce724c75e30aeedeeb9efe1e58b7376c78f23a` |
| 基线提交 | `da8d39ed4e36b6db31e3a7a6b17b0f73b85eed9a` |
| 分支 | `codex/g31-ics-v3-circulation` |
| 新版本状态 | 基线上未提交的工作区字节快照；本包不代表已有新的 GitHub 提交 |
| 当前源码 | ZIP 的 `repo/`；不只依赖 patch 重建未跟踪文件 |

本地审阅根目录：`/workspace/scratch/8bf30cd4abee/review_refresh_execution_20261017/`。下文源码位置均相对于其 `repo/`，以便 Codex 映射回自己的 checkout。

### 1.2 本次做过的检查

完整读过标准库 `verify_bundle.py` 后运行，只核保存原件，没有启动 native、调用项目预测模型或训练。结果 `passed`：

- 2,610 个 manifest 覆盖成员、2,757 项映射引用通过，检查了 26,596 处保存引用。
- 最新最终回归登记的 773 个 Python 源码版本都有确切字节，没有使用历史缺档豁免。
- 核对了保存的测试 XML：844 项、零失败／错误／跳过。**这是保存测试记录的核对，不是本机重新运行 844 项。**
- 两次最新 native 的运行源码归档、主要输入／输出与状态绑定通过。
- 两组 ABBA 各 24 份报告，完整 seed 与候选预测严格一致；时间中位数从保存原件重算，未当作本机新 benchmark。
- B 的两次成功观察、只有后一次进入业务选择、140 条非 publication 物理／命令记录一致，均有原始记录对应。
- 当前关键 Python 执行链、动态 guard、源码 pin、复制隔离与服务刷新逻辑已读审。另只隔离加载 copier 纯函数，核了六类别名／循环对象图及自定义子类拒绝；与标准库 deepcopy 的对象图语义一致，未运行项目模型或 native。

仍有六个旧中间测试／未执行探针草案源码版本缺字节，包内已明确列出；不能声称所有历史阶段都完整可重现。223 项明确未纳入的 native 环境／构建依赖或旁路 sentinel 引用也保留原声明。当前 ZIP 不是可直接在任意机器启动的 Windows native 环境镜像。

**足以判断当前源码和保存实验支持什么、下一步应做什么；不足以独立证明现场硬实时、全机场泛化或任意新动作的逐件保证。** 对前一个判断，无需用户再补一份概述、重复哈希或重新打包。

## 2. 学习插入点：必须区分四件事

| 层次 | 本次判断 | 代码／原始证据 |
|---|---|---|
| 存在能影响业务的合法控制机会 | 已找到初始 R2 择时机会；旧 A04/B12 原生正例仍有效 | 既有 `compatible_initial_native_20261017_004/mechanism/` |
| later 学习器能通过实际执行链提交 | 已接通 | `foundation_later_campaign.choose_learned()` → candidate ID → `foundation_later_control.LaterControl.submit()` |
| 初始学习建议控制实际初始动作 | 尚未接通，当前是明确的 advice-only 设计 | `foundation_native_environment.submit()` 先写 `_advice`，随后 `online.start_owner(..., arm=self._row['method'])` |
| 有真实选择与长期影响的多步 RL | 尚未成立 | 当前 later 两点都只有一个通过保护的候选；六条单场景继续价值记录不支持控制泛化 |

### 2.1 已有初始正例为什么应先用

旧真实 mechanism 对照中，A04/B04 与 A04/B12 的 receiver 完成为 10.120 与 10.001 s，差 0.119 s；其余四件完成不变。B 在约 0.11 s 的实际调拨请求中，E 的 5→1 `earliest_departure` 从 2.210 改为 4.201 s。这是供应择时改善接收冲突的已发生正例，不是本轮新增收益。

正例证据来自既有旧包的实际 `initial_owners.B.selected_action`、submission 和 receipts。兼容处理前的提案索引可能不是最终执行动作，不能只读取原 `selected_index`。也不能将新 task2 的模型建议 12、实际执行 04 误写成“12 被保护拒绝”：该回调本来就只记录建议。

旧正例不自动认证新接口。新接口必须从自己的当前 collection、兼容 mask、已查询候选、当前权限和原生接纳链通过，并跑完实际后续轨迹。结果可以是 04、12 或有理由的拒绝；不要求必须重现 0.119 s 才算接口实现正确。

### 2.2 later 的真实接线与动作支持

`foundation_later_campaign.py` 的 `choose_learned()` 只评分 enabled 候选，然后返回 candidate ID。`LaterControl.submit()` 会重新核对真实 collection、当前 owner admission、current view、outbox 和 local guard，再调用原生返空／路由接口。

旧冻结 learned 原件中，A 约 7.34 s 唯一合法项为 `return_now`，对应真实命令且最终有 ACK；B 约 9.69 s 唯一合法项为 `native_default`，不发新路由命令，也没有伪造 ACK。可以称“学习推理经过真实执行链”，不能称“模型已在多个合法方案之间作出了有收益的选择”。

强制默认步骤可以存在于合法 RL 轨迹，不要求每个事件都有至少两个动作。但如果被评估的控制机会全部只有一个选择，就不能从这些轨迹中证明学习带来选择优势。多跑网络训练不能补足缺失的控制自由度。

### 2.3 新 freshpair 提供了什么

同一 episode、同一 B owner 的真实观察从 `9.689999999999994` 推进到 `9.729999999999993`；双方 publication sequence 从 6 到 7。第一观察只记录，第二观察才交给 actor，B 仍只作一次 default 决定。全 episode 仍只有原两次 later 业务选择，没有新增业务动作。

两份 mask 都是 default 通过、prefer8 拒绝。140 条非 publication 记录一致；新增消息的 ACK 不同。约 9.75 s 的服务边界尚未在这两次观察之间发生实际释放。

`foundation_successful_refresh_probe.worker()` 在 native 结束之后才调用 `refresh_audit()`。后者返回 `full_refresh_required`，涵盖全 5 jobs、3 trays、11 nodes、14 edges。它是**对真实新观察的事后保守失效审计**，没有在线缓存执行、局部后缀复用或减少预测调用的证据。

## 3. 代码审阅分类

### 3.1 可接受，建议保留

| 改动／证据 | 为什么可接受 | 声明范围 |
|---|---|---|
| `foundation_catalog_copy.isolated_copy()` | exact builtin、循环与 alias 语义符合所需；每次读有独立可变副本；拒绝自定义 hook | 仅内部静态目录复制，不是外部 evidence 校验器 |
| `foundation_request_context.RequestContext` | 请求内静态 catalog 复用，已知私有函数 globals／alias 显式重绑；没有覆盖原全局模块 | 当前所审 guard 路径，不是通用执行沙箱 |
| `foundation_later_seed.evaluate()` | 一请求一次 seed，仍有两轮动态验证、候选前后 mutation 检查与最终来源检查 | 同请求减少重复工作，不是跨事件状态证书 |
| 增量 ABBA | 旧方法用真实旧源码字节，完整 JSON 类型与预测一致 | 三个保存状态、每方法每状态四次，不是规模泛化 |
| 新默认 native 与 freshpair | 实际请求、publication、ACK、动作与实体结果能相互对应 | 受支持研究域内保存实验事实 |

增量中位数从 171.017／229.072／220.853 ms 降到 156.448／199.945／203.404 ms，加速为 1.093／1.146／1.086 倍。保留这项小优化即可，不把上轮 legacy→request_shared 的大加速再次算成本轮成果。

### 3.2 证据不足，继续如实标注

- 异步执行与慢预测期间的底层非阻塞：当前 `offline_sync` 未证明。
- 跨事件预测复用：当前新 epoch／新 evidence 保守全域失效，未有局部有效性证明。
- 有意义的多步学习：缺实际多步选择支持及独立场景评估。
- 全机场 151 节点／227 边运行、实际 EBS 映射、零容量 ICS103→ICS104 语义与现场约束：仍是后续范围，不能由小域外推；也不应成为首个小型学习接口实验的新门槛。
- 逐件保护普适证书：条件预测筛选、当前权限检查和最终实际完成比较是不同证据。保留 `native_protection_certified=False` 等真实边界。

### 3.3 本次未发现需要撤回复制优化的逻辑错误；以下解释是错误的

1. 把两个 B 观察称为两个 B 学习动作。
2. 把 `native_physics_paused=false` 称为已实现实时并发；它只说明探针没有额外冻结，宿主仍同步调用。
3. 把 seed 编码／identity 未变称为外界在计算期间没有变化。
4. 把 `guard_status=passed` 称为全状态、任意扰动下的逐件保证。
5. 将 309／353 ms 改名后写成原完整 100 ms 通过。

代码还有一个下一阶段必须处理的语义边界：`foundation_native_environment.submit()` 将下一个任意 owner 的 offer 写入尚未闭合 transition 的 `next_observation`，当前可能是 A→B。现有 ridge 没有用它做 TD bootstrap，不能据此指控当前 TD 泄漏；但后续区域 RL 必须改为同 owner 下一决策，或明确定义训练侧联合事件 critic。B 的本地状态不能直接当成 A 在线可见的下一本地状态。

`clone_module()` 的类对象、导入模块及部分默认值仍可能共享；当前路径未靠这些对象承载请求可变状态。未来若新增全局缓存，必须重新检查该具体风险。源码 pin 只说明登记文件字节相同，不等于完整运行依赖或对象深隔离证明。

## 4. 100 ms 的新定义

### 4.1 分层验收表

下表是本项目本次建议采用的设计合同，不是某篇文献规定的通用毫秒标准。

| 工作层／请求对象 | 触发与职责 | 输入／输出 | 计时与期限 | 100 ms |
|---|---|---|---|---|
| 物理互锁与执行 | 实体进入、FIFO 队首、headway、容量／接收事件 | 真实实体／资源→合法执行结果 | 设备与事件实际截止期；持续运行 | 不把它等同于统一 100 ms 控制周期 |
| R1 区内单任务更新／路由 | 当前请求、拥堵／故障／路线相关变化 | 当前合法局部信息→路由或有效续行 | 按请求累计全部必要计算，包括当前复验与必要提交处理；排队／网络／协议等待另列；端到端满足物理期限 | 保留原 100 ms 必要计算目标，尚未证明达标 |
| 状态／适用性监测 | 实际消息、状态变化、已登记到期计时器 | 本地事实／实际送达消息→失效标志或轻量更新 | 在下一被影响动作前发现相关变化；监测与排队成本必须计入 | 不要求每次监测都连带完整预测 |
| R2 载货驱动的托盘释放预测 | 周期上限＋有因果影响的服务／路线／资源事件 | 载货义务、卸载与暂存、已承诺前缀→未来空盘可用性 | 预测适用域、信息年龄、有效时域 | 取消每次完整预测统一 100 ms |
| R2 候选推演／预平衡 | 有效预测和尚未承诺的调拨机会 | 候选／continuation→候选后果与提议 | 结果必须在仍可改变动作的期限前可用；包括交付、复验和必要接纳 | 取消统一 100 ms，改为逐请求预算 |
| 当前提交／接纳／ACK | 真正应用提议时 | 新鲜权能与实际资源／命令身份→接纳、拒绝或未知 | 真实当前复验；协议完成、命令生效、物理完成分别记账 | 仍属于相应快速请求／动作期限，不得因预测降频删去 |
| 航班条件下的未来需求预测 | 已收到的航班版本、入口观测偏差、相关计划变化及最迟刷新计时器 | 合法历史／计划／截至当前的入流→区域新增需盘估计及误差 | 与动作提前量、计划变化及预测适用期匹配；不能用未来真值 | 接口可并行增加；完整模型不阻塞 P0，无统一 100 ms |
| 模型训练 | 离线批次／版本更新 | 数据→冻结 checkpoint | 训练预算、样本支持与验证 | 不适用 |

不要把计算时间、可交付响应、ACK 闭环、实际运输完成四种量合成一个数字。取消预测统一上限不意味着可以隐去后台长计算，或把一批耗时除以覆盖任务数冒充单次快速响应。

### 4.2 当前数据在新合同下意味着什么

新默认原件：

| 切点 | native 读取与 guard ms | 组装 ms | 模型与候选 guard ms | collection→offer ms | collection→决策记录 ms |
|---|---:|---:|---:|---:|---:|
| A 7.34 s | 91.745 | 26.052 | 168.963 | 286.763 | 309.379 |
| B 9.69 s | 98.027 | 31.704 | 185.225 | 314.959 | 352.694 |

前三列包含于后面的累计窗口，不能全加。末列仍不含更早消息交换、启动、返回序列化与后续 ACK。约 92／98 ms 的读取片段也不能单独证明快速接口小于 100 ms。

`LaterControl.collect()` 在回调里同步执行 `evaluate()`；`choose_later()` 又明确检查 actor 窗口 native 状态和物理时钟不变，环境消费完 pending 决策后才 `advance_to_next_decision()`。所以当前数百毫秒是宿主计算，不能直接认为物理过程已经为它留出同样长的窗口。

B 9.69→9.73 s 的 0.04 s 是仿真时差，9.75 s 是特定服务边界，不是测得的墙钟网络延迟或通用刷新周期。对任何拟应用动作，都应按它的真实“最后仍可修改时刻”判断；不能笼统说过了 9.75 后所有动作都非法，也不能认为在 9.73 抓到的状态允许无条件再算 353 ms。

**旧完整 100 ms：历史未达。新上层截止期合同：尚待异步实验验证。快速 R1 合同：尚待专门计量。** 三个结论同时保留。

## 5. 预测频率如何科学确定

### 5.1 先分开七个参数

物理事件推进、轻量监测间隔、完整预测刷新间隔、优化启动间隔、预测时域、单次计算预算、动作接续／执行窗口必须独立记录。策略推理频率与模型权重训练频率也不能混为一谈。

内部模型把未来时间网格变粗，不等于降低真实世界重算频率；减少完整求解次数，也不等于非触发时没有任何估计或校验。[L1–L5]

### 5.2 用动作可用期限给预算，不先指定几秒一次

先选择一项实际可提前安排的动作，确定其最后可变更时刻、需要托盘时刻、可确认的卸载释放／运输／接收时间，以及当前承诺的有效范围。

在已经明确仿真时间与墙钟时间关系的运行模式下，为该请求定义可用截止期 D_use，并验证：

$$
T_{queue}+T_{capture}+T_{predict}+T_{select}+T_{deliver}+T_{recheck}+T_{accept}
\le D_{use}-t_{start}.
$$

这里的所有量必须落在同一可比较时钟上。D_use 由该动作的最后有用修改时刻、接续方案适用期和执行必需权能的期限等共同决定。需要等确认才能形成有效承诺时，T_accept 包括该段确认；其余协议／物理结果仍分别报告。这是本项目的必要时效约束，不是逐件安全的充分定理。

例如预计需要托盘的时刻为 t_need，如果有受支持的保守运输／接收时长界，可推导最晚有效调拨时刻；还要满足盘确实能在此前释放。只有均值／分位数时，应称经验可用率或带风险预算的设计，不能冒充确定性最坏界。

预测输入的年龄从真正 captured_at 算起，不能从 worker 启动重新清零。当前 observation 的严格 freshness 与“基于历史信息生成的未来计划是否仍适用”是两种契约；不能用前者的旧 capability 直接授权慢结果，也不能把所有预测一律强制在原 snapshot 的短 TTL 内完成后又宣称已分层。

当前 `foundation_service_refresh.transition_reasons()` 含 `current_at - captured_at > .05` 的来源新鲜度条件。B 第二观察时，旧自身来源约 9.66→9.73 已是约 70 ms，因而失效。这是现有 collection 合同，**本文件没有授权把 .05 放大、回填时间或把旧观察改成新观察。** 应让慢结果作为没有提交权限的建议，在应用时取得新鲜的原生权能，并验证从旧切点到当前／未来接续点的因果适用性。

### 5.3 初版采用事件＋最大刷新间隔

建议先实现混合触发：实质依赖事件触发重估，同时设置按有效期推导的最迟刷新计时器。最大间隔、触发阈值和提前量由训练／开发场景的观测与保守界选择，冻结后到留出场景评估。暂不指定唯一秒数。

| 事件 | 立即做的工作 | 是否一定完整重算 |
|---|---|---|
| 无关遥测、与受保护未来无交集的消息 | 验证并更新本地账本 | 有独立性证明才可跳过；仅凭“看起来无关”不足 |
| 载货改路、卸载延迟、暂存释放、盘变空、下一次复用开始 | 更新相关盘生命周期和受影响资源 | 无有效边界时重算支持域；以后有证明才局部更新 |
| 新需求或需求撤销／变化 | 更新合法可见义务，检查供盘覆盖 | 只影响需求层不代表一定不影响路线／资源 |
| 航班延误／取消／新增，或航班到入口的映射版本变化 | 按实际收到时间更新相关航班需求先验，检查关联调盘建议 | 先更新受影响航班；没有影响域依据时扩大重评估。计划变化不自动取消已存在行李或改写其原 deadline／EBS 释放合同 |
| FIFO 队首、接收容量、共享边／节点变化 | 快层处理当前动作，慢层失效相关预测 | 必須含候选新增路线的资源，不能只看旧最短路 |
| ACK 拒绝／不确定、在途动作变化、peer 承诺变化 | 保留原命令身份并重新判断知识状态 | 不把预计收到或偏好 ACK 当资源预留；边界不清则 unknown／重评估 |
| 没有新消息，但来源／服务界／接续有效期到期 | 定时器触发失效或提前刷新 | 必须处理；无消息不等于远端不变 |
| 故障、owner／tray generation 改变、影响域不闭合 | 快层用仍合法的应对，慢层扩展影响域 | 扩到完整受支持模型域；不是向 actor 开放隐藏全局状态 |

合并尚未开始的重复请求，给每个 owner 限制在途预测数量，避免事件风暴。可以作废过时计算任务，不能因此撤销已提交的 native 命令或换新 ID 重派同一实物。

## 6. 最小异步接口与复用条件

### 6.1 两种对象，执行权限明确

**区域快层**维护真实库存、身份、FIFO、接收能力、outbox／ACK、已发不可撤前缀和有效续行。只有它通过当前原生检查取得执行权限。

**区域慢层**只接收合法可见的脱离数据，输出 ForecastAdvice：owner、模型／候选版本、来源捕获时刻、tray generation、已承诺前缀、预测接续点、适用依赖、预计释放／到达、候选 ID 和预测覆盖域。它没有 session、client 或提交权能。

建议增加的记录字段是新 schema 设计，不声称现有代码已有：

```text
timing_contract = multirate_v1
prediction_uniform_100ms_required = false
r1_required_compute_target_ms = 100
execution_time_mode = offline_sync | simulated_latency | realtime_async
prediction_started_wall_ns / prediction_ready_wall_ns
capture_sim_time / ready_sim_time / admit_sim_time
advice_id / owner / model_version / tray_generation
source_captured_at / continuation_id / immutable_prefix_id
planned_handoff_time / use_by / dependency_scope
admission_result / rejection_reason / current_capability_id
```

不把 `realtime_async` 设为默认真值。deterministic 模拟延迟能测协议语义，但不等于当前硬件真实并发已测。必须把模拟注入延迟与实际 worker 墙钟分开报告。

每个 owner 可使用一个常驻隔离 worker；这是简单候选实现，不要求立即分布式部署基础设施。异步化必须让慢函数离开 `LaterControl.collect()` 的前台同步路径，不能在调用点 `.result()` 再等回去。CPU、共享锁、GIL、序列化和文件 I/O 若仍拖住快层，同样计入阻塞。

### 6.2 不重算或局部重算需要的充分性结构

下述是待实现的条件式证明结构；当前包尚未满足跨事件版本，不能直接把它设为 passed。

1. **身份和输入域正确。**模型、候选语义、原参考、owner／盘代际、信息权限与来源版本已绑定。
2. **已执行前缀不可更改。**新 current 中实际发生的命令／实体前缀，与旧方案的已承诺 continuation 一致；不一致就更新并重评估，不能只比较旧对象是否自洽。
3. **影响域闭合。**覆盖载货→释放→空盘路线→接收→后续装载／二次复用，包含共享 FIFO/headway、候选新增绕行和所有可能反作用的受保护业务。
4. **域外影响有可兑现边界。**他区轨迹、释放／接收承诺、容量或到期条件必须是可验证且有权作出的边界；预测值不等于预留。没有边界则扩大依赖闭包，不凭一跳邻域宣布独立。
5. **时间与接续可行。**计算期间实际状态仍受支持，返回后新未来部分从实际 handoff 条件可行；到期与无消息时变化都被覆盖。
6. **逐件保护依据没有漂移。**在这些条件内，预测或保守上界对每件满足原参考，且完成／未完成／unknown 分母完整。若模型只是点预测，则其结论仍是条件筛选，不冒充任意扰动保证。
7. **应用时再次取得当前资格。**当前 source／receiver 权限、资源和命令身份有效，旧 Advice 不持有提交权能；ACK 不确定时不将预期结果计入真实库存。

上述条件成立时，复用的应是“不受影响部分的语义与未来条件”，不是简单的旧 JSON 对象。未能证明时，采取完整受支持域的当前重评估、拒绝旧建议或返回 unknown；不能删去受保护对象让局部域看起来成立。

**回退的特殊约束：**一旦执行过非默认动作，原默认轨迹未必还可行或逐件不劣。WAIT 可能保持物理安全却损害服务，所以“超时就 wait／default”不是普适证书。初版异步实验优先让未改变的基线继续运行；慢结果晚到则不增加动作。对已经接纳新计划后的异常，需要验证剩余 continuation 的当前可行性，业务失败／未知也要诚实记账。

## 7. Codex 下一轮具体实施

### P0：初始模型实际控制，先结束 advice-only 的主线停滞

目的：证明冻结学习器能在真实当前初始上下文中选择合法调拨参数，并影响之后的实体循环。无需先训练新网络或把上层完整请求压到 100 ms。

优先接口：

| 文件／函数 | 要做的最小改动 |
|---|---|
| `scripts/experiments/g31_ics_circulation/foundation_native_environment.py`：`submit()` | 新增显式 initial selector 入口；保持原 `_initial_evaluator` advice-only 语义，避免改写旧实验 |
| `research_live_obligation_initial_methods.py`：`start_owner()` | 复用原建立 retained policy 的链，传递明确的学习提案／选择对象 |
| `live_obligation_online_initial_dispatch.py`：`choose_and_submit()` | 学习选择进入原 collect→compatibility→first-component 重验→require_current→submit；最后权限仍由执行侧持有 |
| `foundation_budgeted_provider.py`：`public_compatible_indices()`、`evaluate_budgeted()` | 沿用公开兼容集合与实际 K/P 预算，不因接线又先计算 full32 |
| `foundation_compatible_probe.py`：`validate_models()`、`make_callback()` | 复用已有冻结 43 维 initial 模型，保持模型／特征版本与来源对应 |

执行侧持有真实 `InitialDecision`。模型只看允许的特征／候选，返回 ID 或排序；不能将 session、全局评价状态、未来 input tape 或终态标签交给 actor。A 保持 04，B 用冻结模型选择，later 暂沿用原默认，所有后续 observation 必须来自这一条新实际轨迹。

最小验证：先做新桥接接口的 04 对照与冻结模型配对；若需要区分接口故障和模型选择，再增加固定 12 诊断。记录实际查询集合、mask、模型选择、兼容后动作、提交参数、ACK／执行和五件完成差。任一检查拒绝就保存原因，不松保护以制造正结果。

P0 的完成标准是解释清楚“模型选择→实际提交→实际后果”链，而不是保证选 12。旧 0.119 s 只作为待复验参考。一个场景的一次有效选择只能证明接口与机制，不能称泛化优势或多步 RL。

**航班补充与 P0 的关系：**可并行增加独立的 `FlightContext` 适配入口，默认 `None` 时保持原路径和已冻结模型的输入语义。P0 继续使用原 43 维模型；不能把新字段直接追加到旧 checkpoint 的输入，也不能要求先收齐航班数据才接通 initial selector。

### P1：最小快慢并行与期限实验

目的：实际回答“数百毫秒预测是否仍来得及预调度”，不继续仅在冻结物理时间的回调里压性能。

先固定原物理图、盘数、任务与默认 continuation。选择一个尚未发出的未来动作，注册预测输入、可能 handoff 与最后可用期限；底层在 worker 运行时继续处理原有物理／消息事件。结果返回时取得当前观察，重新检查其适用域；前台不等待完整预测。

首轮至少覆盖三种结果交付情形：

| 情形 | 预期可观察结果 |
|---|---|
| 结果在期限前返回，相关依赖仍成立 | 可以进入当前复验；不是仅以旧结果“ready”就提交 |
| 结果晚于动作可变更期限，或来源／盘代际／不可撤前缀已不相容 | 不覆盖当前计划、不重复派盘；记录拒绝原因，快层继续当前有效行为 |
| 无新消息但有效期到期，或 ACK 状态不确定 | 计时器／协议状态触发失效；不虚构库存、ACK 或新鲜度 |

共享资源／新绕行及回退失效反例可先作隔离语义检查；只有它们改变原生执行时才补原生实验。没有必要把所有故障组合一次铺满。

联合报告：每次计算及尾部、后台总 CPU／墙钟、worker 队列、快层阻塞与完整必要计算、端到端响应、source age、提交／生效时刻、截止期错失、结果废弃、unknown／拒绝、逐件完成和缺盘／拥堵。首轮少量样本不称 p99 或硬实时上界。冷启动／常驻首次／暖请求／退出单独记，不能把一次退出成本机械加在每次暖请求上，也不能隐藏必需冷成本。

**P1 可先在原默认继续执行时验证晚到拒绝，不要求先有可保护的新 later 动作。** 真正预调收益可从 P0 已有初始择时或更早的合法预测切点逐步接入。若当前 50 ms collection 合同导致任何旧 offer 都不能跨计算复用，应明确保留这一拒绝，并实现 Advice／新 current admission 的分离；不得偷偷放大 TTL。

### P2：自然服务差异与真实多步数据

先越过真实服务变化／下一次复用观察，而不是再添加一对服务未变的短间隔 snapshot。保留原模型和物理约束；若 `first_reuse_route` 窗口已结束，应定义相应新 phase／generation，不能让旧 phase 永远有效。

按原业务生成规则预先限定小批场景，覆盖载货服务影响释放、二次盘复用、共享资源与候选新绕行。需求／服务输入变体必须经过显式 scenario manifest 和原合同验证；不能删输入校验或改边长来制造“同图自然差异”。若允许的原生成器本身不包含某类服务扰动，则先标为额外实验域，不暗中修改。

每个场景冻结自己的原参考策略和外生输入，先获得该输入的逐件参考向量，整个 episode 不重置。既有 no_overlap 可作开发对照；旧 insufficient_advance 含边长改动，不能放进只变需求的固定图泛化集合。

保持 initial 43 维和 later 52 维 schema 独立。对当前六条续值数据核 continuation 标签定义与相同输入的行为差异，不把行为续值直接改名为最优 Q。后续区域转移采用同 owner 的下一决策，或正式定义训练侧联合事件过程；异步间隔必须保存 Δt。

航班需求模块先以独立、版本化输出参与规则／候选对照，具体见第 11 节。确有新增输入和独立验证数据后，再训练对应新 schema 的 actor／价值模型；区分需求预测改善与学习决策改善，不把提供更多未来计划信息造成的优势全部归给 RL。

区间回报可按实际未完成业务数积分构造，使任务等待成本与物理经过时间一致；有限 episode 可先用无折扣。若后续使用时间折扣，按实际 Δt 统一，不能因多发了 publication 就多折扣一步。未完成、进程超时和执行未知不是零后继成本。训练／评价侧可以读取终态构造标签，actor 仍不能读取未来真值。

场景及同前缀干预分支分组划分训练／验证／测试，不随机拆六行。存在无选择步骤很正常；首批结束仍没有多步控制机会，就明确报告所覆盖域和原因，停止无上限搜索，不靠放宽逐件参照得到“可学习”标签。`rl_support()` 当前是 blocked 占位，不通过改布尔值宣称新阶段已认证。

### 可并行的小工程项：分离审计 evidence 与物理 seed

profile 指向大量复制与严格编码：物理 bundle 约 11–12 KB，evidence／seed 约 74–132 KB；这些大小与 profile 来自保存报告，不是本机新分布。不要把嵌套累计时长相加，也不要预先断言改表示一定有几倍提速。

建议入口仍完整校验 evidence，封存规范不可变审计字节；候选仅接收引擎真实需要的私有、版本化物理 seed。保留每候选可变状态隔离、完整可触及模型状态的 mutation 检查，以及提交时的真实 current／来源检查。必须输出的审计封装／序列化成本仍进入相应总账。

必要反例只覆盖具体剩余风险：候选污染 at／entry／retained preference；原 evidence 外部修改；default no-command 错清已发偏好；current view／admission 已变却试图提交旧结果。与完整评估作同输入、同候选、同参照的对照即可，无需新造大测试框架。

## 8. 文献依据与创新边界

本轮重点补充近期原文，并重新核对直接相关旧 BHS 工作。下列参数属于相应论文；没有为 G31 照抄刷新周期。未核到的硬件／周期／完整权能约束不补猜。

### 8.1 时序与预测方法

| 文献与核读版本 | 实际支持什么 | 对 G31 的边界 |
|---|---|---|
| [L1] Dirckx 等，ASAP-MPC，2024 arXiv v2；正式扩展版 Autonomous Robots 2025 | v2 §III-D/E、Algorithm 3：快速反馈与异步轨迹优化分离，新轨迹在未来 handoff 接续，要求计算赶在接续前完成；超时有应用专用处理 | 机器人跟踪假设不等于离散盘 FIFO／接收／逐件完成保证；正式版此次核了元数据／摘要，技术定位依据公开 v2，不冒充已读正式全文 |
| [L2] Liu、Alan、Shi、De Schutter，2026-09-08 v1，Asynchronous MPC Under Model Mismatch | §II-C 式(6)、§V-B Theorem 2：允许非每步更新，最大间隔与时域／模型误差联合受约束；文中 1≤m_j≤M≤N−1 | 预印本；不是后台求解延迟补偿实现。二维数值例，无硬件墙钟结论；分布式扩展列未来工作，不能拿来认证 G31 |
| [L3] Li 等，Automatica 2022，Event-based MPC with dynamic disturbance | Algorithm 1（PDF 第5页）每步测量并构造扰动／状态／续行估计，只在触发时重解 OCP | 支持减少重优化，不支持“非触发时完全不预测”；其辅助续行允许触发间隔超过原时域，不能与所有 horizon-expiry 规则混用 |
| [L4] Schroth 等，Multi-Timescale MPC for Slow-Fast Systems，2025-11-18 v1 | §III：同一预测时域内逐步粗化积分网格、切换模型，降低求解量 | 这是模型内部离散粒度，不能直接当作墙钟异步刷新频率证据；成本容差与近似模型不等于本项目零逐件退化 |
| [L5] Zeinaly、De Schutter、Hellendoorn，IEEE TCST 2015，Integrated BHS MPC | §II–III 将载货路由、line balancing、空车管理纳入联合预测；流量决策与底层开关实现区分 | A3 用连续 DCV 流近似，A4 将旅行时间离散为采样倍数，卸载队列有简化；不等于可识别有限盘全循环／局部权能／严格逐件保护 |

10 月 18 日对 [L5] 补核：控制器使用给定的未来 OD 行李需求与时间窗；全文没有交付航班更新到需求预测的完整估计器。作者稿物理 PDF 第 16 页 §V，把结合旅客分布、行李额与预定航班表的逐 DCV 精确旅行模型比较列为未来工作。可据此支持“预测需求进入载空联合控制”，不能写成已验证的实时航班预测模块。

L1 的 v2 无人机实验为 Jetson TX2／Fatrop，快速对照 50 Hz（20 ms），求解中位 45 ms、观测最大 542 ms（§V，PDF 第9–10页）。它说明优化耗时可超过快反馈步长；首个求解被剔除、观测最大也不是硬上界。这些数值绝不是 G31 的新预算。L2 的二维数值例 N=25、M≤8（§VI，PDF 第7页），未报告实时求解性能。

这些原文共同支持职责分层，同时限制任意降频的推断。它们没有提供“每 1 秒预测”或“300 ms 一定够用”的 ICS 通用定理。

### 8.2 近期重合工作：不能靠关键词组合宣称首创

| 近期原文 | 已有重合 | G31 应实证的区别 |
|---|---|---|
| [L6] Mallick 等，RL with Distributed MPC for Fuel-Efficient Platoon Control，2026-01-26 v1，§IV–V | 学习策略选离散方案，分布式 MPC 处理余下连续优化／约束 | 分布式 MPC＋RL 本身已有；G31 的盘释放、共享输送资源、执行权限与逐件保护需形成具体方法 |
| [L7] Gaber 等，GRAND，初稿2025，核读 v3 2026-03-04，摘要／§V–VI | RL 输出自由 agent 的期望分布，经区域最小费用流再平衡与局部分配执行 | 学习＋区域再平衡／局部分配已有；该全局 guidance 结构不等于本项目局部信息与真实跨区权能，也不提供 G31 的服务释放／实体盘保护合同 |
| [L8] Cheng、Sharif Azadeh，Meal Delivery Dispatching and Idle Fleet Steering，2025-01-10 v1，§4 | 显式短期需求预测作为输入，DRL 联合订单派发与空闲运力再分布 | 预测需求＋RL 提前配置空闲运力已有；不应声称跨领域无人做过。机场有限盘物理过程及内生释放耦合须单独证明 |

本轮可支持的表述：**在目前核读的这些文章中，尚未见与 G31 全部具体约束和拟议方法完全相同的已核实现；但这不是文献穷尽证明，也不能保证论文创新性。**

更有辨识度的研究主张应落在：局部合法信息下，把当前载货造成的未来托盘释放与跨区预调／后续复用联合起来；学习影响尚未承诺的可保护动作或继续价值；处理预测适用性、真实接纳与不可撤前缀；在固定物理合同及逐件保护下测量服务与计算收益。

“采用多时间尺度”“用了 RL＋MPC”“空闲资源提前再平衡”各自都不足以构成首创。本轮 deepcopy 提速、两次 snapshot、一个旧 B12 正例也不是论文级方法贡献的替代物。真正的贡献需要后续有效动作支持、独立场景和公平消融。

当前应准确称为“模型驱动的托盘释放预测＋学习辅助调拨选择”。航班模块是 10 月 18 日新增设计方向，尚不能写成当前已实现能力。完成该模块后，可称“航班先验驱动的区域需求预测与托盘释放预测，辅助去中心化学习调拨”。只有在确实训练并验证了相应预测模块后，才把预测误差改善归给学习；只拟合排序／价值不宜称“RL 已经预测了未知未来订单”。另见第 11 节 [F5]：航班相关负荷、RL 路由与入口空盘储备已有明确重合，不能保证无人做过。

### 8.3 原始来源清单

- **[L1]** Dries Dirckx、Mathias Bos、Bastiaan Vandewal、Lander Vanroye、Wilm Decré、Jan Swevers. *ASAP-MPC: An Asynchronous Update Scheme for Online Motion Planning with Nonlinear Model Predictive Control*. [2024 v2 全文](https://arxiv.org/html/2402.06263v2)、[v2 PDF](https://arxiv.org/pdf/2402.06263v2)；正式扩展版 *Autonomous Robots* 49, article 8，2025-03-07，[DOI 10.1007/s10514-025-10192-w](https://link.springer.com/article/10.1007/s10514-025-10192-w)。
- **[L2]** Changrui Liu、Anil Alan、Shengling Shi、Bart De Schutter. *Asynchronous Model Predictive Control Under Model Mismatch: Stability and Performance Guarantees*. arXiv:2609.08836v1，2026-09-08，[原始 PDF](https://arxiv.org/pdf/2609.08836)。
- **[L3]** Pengfei Li、Tao Wang、Yu Kang、Kun Li、Yun-Bo Zhao. *Event-based model predictive control for nonlinear systems with dynamic disturbance*. *Automatica* 145, 110533，2022，[DOI](https://doi.org/10.1016/j.automatica.2022.110533)、[实验室原始 PDF](https://www.niclab.ac.cn/assets/pdf/2022-Event-Based%20Model%20Predictive%20Control%20for%20Nonlinear%20Systems%20with%20Dynamic%20Disturbance.pdf)。
- **[L4]** L. M. Schroth 等. *Multi-Timescale Model Predictive Control for Slow-Fast Systems*. arXiv:2511.14311v1，2025-11-18，[原文](https://arxiv.org/html/2511.14311v1)。
- **[L5]** Y. Zeinaly、B. De Schutter、H. Hellendoorn. *An Integrated Model Predictive Scheme for Baggage-Handling Systems: Routing, Line Balancing, and Empty-Cart Management*. *IEEE Transactions on Control Systems Technology* 23(4), 1536–1545，2015，[DOI](https://doi.org/10.1109/TCST.2014.2363135)、[作者公开 PDF](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf)。
- **[L6]** Samuel Mallick、Gianpietro Battocletti、Dimitris Boskos、Azita Dabiri、Bart De Schutter. *Reinforcement Learning with Distributed MPC for Fuel-Efficient Platoon Control with Discrete Gear Transitions*. arXiv:2601.18294v1，2026-01-26，[原文](https://arxiv.org/html/2601.18294v1)。
- **[L7]** Johannes Gaber、Meshal Alharbi、Daniele Gammelli、Gioele Zardini. *GRAND: Guidance, Rebalancing, and Assignment for Networked Dispatch in Multi-Agent Path Finding*. arXiv:2512.03194，核读 v3，2026-03-04，[原文](https://arxiv.org/html/2512.03194v3)。
- **[L8]** Jingyi Cheng、Shadi Sharif Azadeh. *Real-Time Integrated Dispatching and Idle Fleet Steering with Deep Reinforcement Learning for A Meal Delivery Platform*. arXiv:2501.05808v1，2025-01-10，[原文](https://arxiv.org/html/2501.05808v1)。仅依此预印本版本，不推断当前正式出版状态。

## 9. 下一次给审阅者什么，不必再补什么

当前材料已经足够完成本轮源代码／保存证据审阅。需要补的是新实现运行后的结果：

1. **P0 的真实链：**冻结模型选什么、实际提交什么、ACK 与实体结果、五件完成差、若拒绝则原因；加相关修改源码／版本即可。
2. **P1 的时间链：**capture、worker start／ready、物理推进、当前复验、提交／生效、截止期前后结果，以及快层有无阻塞。模拟延迟与真实墙钟分开。
3. **P2 的有限数据支持：**独立场景清单、实际可选动作比例、同 owner／联合事件转移定义、固定逐件参考、负例与 unknown。做到了才交，不必为了凑齐标题重复训练旧六行。

每轮保留真正执行的源码字节和原始日志，足够定位改动与复核；无需再把大量历史材料重复打包。另一个窗口未提供的具体论文若需要逐篇精确对照，补标题／DOI 或原文即可；无需因此阻塞已经明确的 P0/P1。

航班模块开始验证时，再补一份最小数据说明：可提前取得的航班表及历史更新版本、行李实际入系统记录及可用的航班关联、入口／区域映射、各字段的发布时间与接收时点。先检查现有原始数据是否已具备，缺失项如实列出；只有全天完成后的统计表，不能据此宣称已获得可部署的提前航班信息。

## 10. 可直接交给 Codex 的执行摘要

> 依据本次 G31 审阅，保留已验证的静态复制优化与当前 guard。上层释放预测／候选推演／预平衡取消统一完整 100 ms 门槛，改为逐动作有效期与截止期；保留 R1 区内更新的 100 ms 必要计算目标和实际物理响应期限，旧超时事实不改。先做 P0：新增显式 initial selector，复用冻结 43 维模型和实际 K/P 预算、公开兼容域，进入现有当前重核与原生提交链，A04/B 学习选择跑完整配对，解释实际动作和逐件结果。不要把旧 advice-only 暗中改名为执行，也不要重训六条 later 数据伪造多步 RL。并行做 P1：预测移出同步快层，底层持续推进，慢结果没有提交权能，按真实返回时刻取得 current admission，验证接续／依赖／期限，覆盖按时、晚到、无消息到期／ACK 不确定。保留 offline_sync、模拟延迟与真实异步三种证据边界。P0 后再用原生成规则的小批自然场景取得真实多步支持并修正同 owner 转移。跨事件缓存、局部后缀理论、全机场扩展都不再作为 P0 的前置关卡。不要改拓扑、盘数、FIFO/headway、原逐件参照、信息权限或不可撤命令来换正结果。

> 10 月 18 日追加：并行加入默认可缺省的航班信息适配器，将“当时已收到的未来计划”与“未来行李真值”分开。先用航班类型／预计件数与历史入流时间曲线估计区域剩余需盘量，再同当前载货的预计释放结合；预测值不能创造库存或接纳权限。旧 43／52 维模型不扩维冒用，新模型另建 schema。先比较同一控制器有无航班先验，再在相同信息下比较规则与学习。保留固定图、原任务生成规则、全部逐件参照与本地权限；航班更新本身不能改写已存在业务。第 11 节是接口、数据与验收依据，不是要求先完成全机场预测平台才开始 learning。

## 11. 航班信息补充：从计划先验到有限托盘预调度（2026-10-18）

### 11.1 设计结论与证据级别

**应允许预测模块读取决策时已经收到的航班计划及更新。** 航班的计划起降／到离位时刻属于可提前知道的信息；某件行李实际何时进入哪个入口仍是待预测量。使用前者不违反“不得读取未来 input tape”，但不能因为历史数据有一个 STD 字段，就推断同一行上的所有最终统计在较早时刻也已知。

本节做的是读取现有源码、核对原始文献并修订实施合同；没有改动项目源码、运行新的 native 或训练。下列模块名／结构均为建议接口，不是声称仓库已经实现。

拟议 R2 同时利用两条信息链：

| 信息链 | 预测对象 | 必须保留的区别 |
|---|---|---|
| 已收到的航班计划／更新＋截至当前的入口观测 | 尚未进入系统的行李，何时在哪个装载入口产生新增需盘量 | 航班起飞／到位时间不等于行李入系统时间；预计件数不等于已到件数 |
| 当前载货托盘、目的地、路线、卸载／暂存与承诺 | 哪些已有托盘何时在何处释放，并能否送到需求区 | 释放时间取决于系统状态和候选动作；预计释放不等于真实可调库存 |

这是基于机场业务及 G31 约束提出的设计推导。[F1–F4] 支持航班／运行信息可用于行李或资源需求预测，[L5] 支持预测需求与载空联合控制；这些来源没有共同构成 G31 完整机制的既成证明。

### 11.2 当前代码已经有什么，尚缺什么

下列位置相对于第 1 节的 `repo/`，本轮逐项读取。当前审阅包没有提供可据以核验全部真实行数据的完整原始 `inputdata.txt`／航班计划表；结论针对解析和构造代码，不外推为机场已提供的字段清单。

| 位置 | 已核事实 | 实施含义 |
|---|---|---|
| `src/czr005/io/legacy_tasks.py`：`RawLegacyTask`、任务解析 | 有 `entry_time`、`std`、`start`、`end`、`loader`、`unloader`；`task_id` 是任务身份 | 可复用 STD 的时间语义；它不是完整航班信息服务，也不自动给出真实航班号 |
| `scripts/eval/run_g4irsf29_workload.py`：`_flight_key()` | 按 `(std, end, unloader)` 构造航班分组 | 明确标为历史／合成分组；未经核实不能当作真实 `flight_id` |
| 同文件：`_flight_row()` | `raw_bag_count`、`first_entry_time`、`last_entry_time`、`source_counts`、`loader_counts` 由该组完整实际任务汇总 | 可以作离线标签和历史分析；直接暴露给较早 actor 会提前知道尚未发生的实际袋量、时刻或区域分布 |
| `scripts/eval/run_g4irsf31_nanning_workload.py`：`build_original_projection()` | 对 `Loader == "T"` 与其他入口作不同映射 | 只能证明当前输入投影，尚不是含入港／出港航班连接关系的完整中转模型 |
| `scripts/experiments/g31_ics_circulation/original_workload.py`：任务构造及对 `workload.select_storage_pair()` 的调用；该函数定义在 `scripts/eval/run_g4irsf31_nanning_workload.py` | STD 用于构造 deadline，早到件有 `std - 2700` 的 storage 释放合同；产出的 jobs 没有独立航班版本字段。storage pair 按研究图自由流距离选择 | 不从 deadline 反推出完整可提前订阅的航班表；不把研究 EBS 选择称为已核实的机场现场映射 |
| 同目录 `foundation_later_learning.py`：actor view | 排除 `arrival > now` 的任务，并记录 `future_arrivals_included=False`；存在业务 deadline、storage 计划时刻和已观测事件时刻 | 保留未来 job 的信息屏障。航班上下文另接，不通过把未来任务塞进 `jobs` 实现“预知” |

`storage_release_at` 是现有业务合同中的计划边界，`storage_released_at` 是实际发生后才有的观测；二者不能混用。已有任务的 deadline 也不能仅因新航班先验预测了延误就自动放宽。

### 11.3 当时可见输入的合同

对于 actor 在本地时刻 t 使用的每个消息版本，记录并验证：

$$
t_{published}\le t_{received,owner}\le t.
$$

这里限制的是消息何时可知，**不是**要求消息中描述的计划事件已经发生；计划离港可以在 t 之后。时间基准、单位、机场时区到仿真时间的映射必须明确，不能把 STD、ETD、ETA、SIBT、AIBT 混成一个含义不明的 `time`。发布时间缺失时保留缺失事实，不能补成零以通过检查；静态预先给定计划可作为单独、明示的数据假设，不能冒充历史更新回放。

| 数据 | 允许用途 | 时点与不确定性 |
|---|---|---|
| 计划离港／到港、计划到离位、航班类型、机型／座位等 | 建立未来负荷先验 | 只使用实际已提供且已收到的版本；STD 的精确定义按本项目数据字典确认 |
| 预计离港／到位更新、取消或入口分配变更 | 修订尚未发生的需求及相关建议 | 以各区域实际收到时间生效，不能用当天最后版本回填全部早期预测 |
| 旅客量／预计袋量／行李系数 | 估计尚未进入的袋量 | 区分预测、已确认记录和最终实际总量；没有提前来源时，用训练历史估计并标注误差 |
| 已观测入流、已经载货、卸载／暂存状态 | 修订剩余需求与托盘释放 | 截止当前且符合 owner 权限；已到未服务需求另列，不能再算作未来新增需求 |
| 全天最终入流、未来任务清单、最终实际到位／离港、最终每航班袋量 | 环境输入、离线标签、明确标注的神谕对照 | 不作为较早时刻可部署 actor 的输入；训练时可用标签不等于执行时可看答案 |

航班到入口的映射也要有版本。出港目的地／卸载站不是自动对应的新行李注入入口；入口或区域无法辨认时，保留机场级预测或未知标志，不能伪造精确区域需求。

多个区域订阅同一航班信息源，与去中心化调盘并不矛盾。共同的计划上下文不授予中央托盘执行权，也不授予 actor 读取全机场当前私有库存的权限；区域仍根据自己的事实及实际送达的 peer 消息生成建议，源／接收 owner 继续确认实际资格。没有收到的航班新版本也不能因为其他区域已收到而自动视为本地已知。

### 11.4 先把机场业务映射对，再选择预测器

| 业务 | 可用先验与必要映射 | 对需盘／释放的影响 |
|---|---|---|
| 出港值机行李 | 航班计划、预计件数、值机入口分配、历史“距计划离港多久进入”的分布 | 在装载入口产生新需盘量；不能把起飞时刻直接当作入口到达时刻 |
| 中转行李 | 入港预计／实际到位、卸载运输时间、入港到出港连接关系、转运注入口 | 可能成批到达；只知道出港 STD 不足以确定这批行李何时进入 |
| 到港提取 | 当时可得的到位信息、卸载／地面运输及提取流程 | 只纳入确实经过本 ICS 的路径；提取带首／末袋时间不是托盘释放时刻的替代物 |
| 早到行李暂存与出库 | 原业务合同、实际 EBS 结构与状态 | 必须确认袋盘是否绑定入库。带盘暂存与脱盘存储的空盘收支不同，不能默认每次出库都新消耗一只盘 |

同一载袋托盘跨区行驶通常仍是同一资源生命周期，不能在每个经过区域重新记一次“装载消耗”。当前小域先落实已支持业务路径；未建立现场映射的到港／中转／EBS 分支明确留作扩展，不强行扩大本轮实验域。

建议先做可解释的历史分布基线。令 `B_remaining(f, t)` 为根据当时信息估计的、尚未进入系统且仍预期会进入的航班 f 行李数，`p(f, r, k | t)` 为这些剩余行李在未来时间箱 k 从入口区域 r 进入的条件份额：

$$
\widehat D^{new}_{r,k\mid t}
=\sum_f \widehat B^{remaining}_{f\mid t}\,p_{f,r,k\mid t}.
$$

对完整剩余时域和入口集合，份额归一；只截取有限预测时域时，总和可以小于 1。先用训练历史中同类航班的交运提前量曲线、地区／入口份额及预计旅客量乘行李系数估计，并用已观测袋量更新；历史不足时采用更粗分组并显式表达不确定性。已到未装袋量另作当前队列，避免两处累计。时间箱和预测时域由真实调盘提前量与数据分辨率确定，不照抄 [F2] 的 15 分钟，更不压缩原物理时间来适配示例。

航班延误不意味着旅客已经交运的袋子可以被移回未来；剩余行李是否随延误平移，应从相应历史／观测估计。取消航班也不等于已进入系统的行李自动消失。计划变化先修订预测，业务撤销、改目的地或 deadline 变化仍须走原业务语义，并在同外生输入的参考策略中一致处理。

在明确区域账户与候选动作 a 后，可用预测收支评估提前调盘价值：

$$
\widehat E_r(\tau\mid t,a)
=E^{free}_r(t)
+\widehat R_r(t,\tau\mid a)
+\widehat I_r(t,\tau\mid a)
-\widehat C_r(t,\tau\mid a)
-\widehat O_r(t,\tau\mid a).
$$

各流量项是从 t 至未来时刻 τ 的累计值：进入可用空盘池的释放 R、空盘流入 I、装载消耗 C、空盘调出 O。R 包括当前载货的释放，以及同一预测时域内随后装载后的再次释放；若 C 已计入一次新装载，其后发生的释放也不能遗漏。按托盘身份、generation 和释放事件去重，并与跨区流入／流出、已预留／在途盘采用互斥记账，避免一只盘在两个区域被同时预支。该式是规划估计，不是可立即提交的库存证书；实际调盘仍依赖当前真实盘、合法命令及接收条件。

需要时再比较小型正则化回归或树模型；使用 4070 电脑／5080 服务器的现有预算即可规划首阶段，不提出新硬件采购或先训复杂深网。先完成可复核的预测与控制闭环，再决定是否值得增加模型复杂度。

### 11.5 最小接口与执行顺序

建议把计划信息与当前 actor 物理观察保持独立，示意如下；最终名称以仓库现有风格为准：

```text
FlightContext                         # 可选；None 保持原实验路径
  schema_version, source_id, version
  published_at, received_at, owner_scope
  time_basis, validity_policy
  entries[]
    flight_ref, identity_kind         # real_flight 或显式 historical_group
    scheduled_event_type, scheduled_event_at
    estimated_event_type?, estimated_event_at?
    available_bag_count_estimate?, estimate_source?
    planned_injection_region?, mapping_version?

RegionalDemandForecast                # 独立输出，不是假装已到的 jobs
  schema_version, forecast_origin, information_cutoff
  context_version, observation_version, model_version
  region, bin_edges, horizon
  remaining_new_demand, uncertainty_or_scenarios
  known_unserved_demand, validity_dependencies
```

计划事实的有效性策略与 current admission 的短 TTL 分开：静态计划可以长期保留，但由它生成的调盘建议仍受新版本、状态偏差及动作截止期约束。缓存不能替代收到更新时的失效处理。数据缺失时返回 `None`／有来源的粗先验，不伪造零需求或填入全天实际总量。

具体工作顺序：

1. **当前主线 P0 继续。**接通冻结 initial selector 的实际提交，不要求先训练航班模型。
2. **并行做适配与数据审计。**可新增 `flight_context.py`，读取独立计划源，验证接收时点、字段语义和本地权限；默认缺省保持旧路径。确认哪些原始字段可提前获得，哪些仅是事后标签。
3. **有合适历史数据后做简单需求先验。**可新增 `flight_demand_prior.py`，先输出区域剩余需求曲线，同载货释放预测组成 R2 输入。先让固定规则／既有候选机制消费预测，再接新版本学习器。
4. **在 P1 的时效链上使用慢输出。**初始计划加载、相关航班／入口映射更新、入口预测误差和最迟刷新计时器触发重估；快层不等待。仅航班数据源更新不要求无条件重训权重，也不要求每个包裹到达都从头预测所有航班。
5. **P2 再比较学习收益。**新增维度必须有新 schema、训练数据和 checkpoint；旧 initial 43 维／later 52 维权重继续按原输入解释。预测模块可以是统计／监督学习，RL 学习何时、向哪里及以何种合法参数调盘；不要把两类训练目标混称为同一算法已完成。

### 11.6 最小科学验证与必要反例

需要分别回答“航班先验是否有用”和“给定相同信息后学习是否有用”。建议围绕同一受支持场景集合安排以下消融；这是后续评估设计，不是要求 P0 先完成四套新训练。

| 信息条件 | 固定规则／原控制器 | 学习辅助控制器 |
|---|---|---|
| 当前已观测业务与载货释放预测 | 原基线 | 对应当前信息 schema 的学习器 |
| 同上＋当时可得航班需求先验 | 测信息增益 | 测相同信息下的学习增益 |

四组的物理图、有限盘数、外生任务、合法信息边界、候选预算和原逐件保护保持可比；每场景固定自己的参考。最终未来轨迹神谕如有需要另列为不可部署对照，不把它当正常预测器或与在线算法混算。

按独立运行日／场景和真实或合成的母航班分组、按时间向前验证。2x 加密复制的 parent flight、同前缀干预及同一天的相邻时间箱不得分别混入训练和测试。标准化、历史曲线、填补缺失与超参数只在训练／开发侧估计。如果目前只有一个历史运行日，就明确只能做接口与机制验证，不能声称跨日泛化。最终 `DEPARTED` 筛选的历史子集不等于上线时已知谁必然离港，取消／严重扰动覆盖需另行说明。

首批只需覆盖与新增接口有关的具体风险：旧航班版本晚到／缺失、真实入流偏离曲线、入口映射变化、相同托盘释放被两区预测引用。另核“已到袋量不重复算未来”“消息未收到不能先用”“无计划可继续原路径”。不为此新造全机场故障组合或无限搜索正例。

预测端报告决策所需时域上的区域件数误差、低估缺口及不确定性校准；控制端报告真实缺盘等待、空盘运输、拥堵、全部逐件完成差与未完成／unknown，以及结果年龄和截止期错失。预测误差变小不自动代表系统收益变好，额外预调本身也占用共享输送能力。

分位数可以表达经验风险，不能替代逐件保护；多个时长或区域的同等级分位数也不能直接相加当作联合分位数。对没有确定界的未知未来入流，不能声称保证所有可能未来都无退化。保留原全任务参照与最终实际核验，不把保护分母缩成当前已观察任务，也不把未来截止时刻按预测重置。

### 11.7 新增文献：直接支持、可借鉴与尚未核实

页码按下列链接物理 PDF 页数计算；所有论文中的分箱、提前量和实验参数均属于原论文，未据此给本项目设置新周期。为保持可复核性，明确区分全文、学位论文和仅摘要。

| 来源 | 核读内容与实际任务 | 对本项目的支持与限制 |
|---|---|---|
| **[F1] De Keijzer，2023，TU Delft 硕士论文，全文相关章节** | §III-C，PDF 第 26 页，分别使用历史袋流／航班资料和含未来航班计划、预计旅客量的数据；预测航班袋量并进入 make-up area／人员资源分配，研究 7／30／60 天尺度 | 最直接支持计划信息可作提前预测输入及后续配置依据；不是分钟级空托盘调度，也不是同行评议期刊证据 |
| **[F2] Gozuacik 等，ICECCE 2025，全文** | §III–IV、表 I，合集 PDF 第 2–4 页：用 `SCHEDULED_TIME + FLIGHT_CODE` 对齐离港前行李记录，构造 15 分钟量；最终 13 项主要是日历／时段和国内国际类别 | 可借鉴航班参考时刻与袋流样本构造；表 I 未显示完整未来航班表／ETA／ETD 特征，不能把样本对齐说成已验证动态航班预测。15 分钟是分箱，不是刷新周期；五折验证未交代完整当时版本回放 |
| **[F3] De Falco 等，SESAR Innovation Days 2025，官方全文** | §III-A、表 I，PDF 第 3 页：在飞机实际到位 AIBT 时，以当时可用袋数／旅客数、机型、机位、地服、延误等预测到首袋及首至末袋时长；使用分位数回归 | 支持明确预测起点、输入可得性和不确定性；目标是到港提取带交付，不能代替到位前袋量预测或 ICS 托盘释放模型 |
| **[F4] Pisinger、Rude，2020，同行评议作者稿全文** | PDF 第 6 页：按航班类别回归／分组资源需求并安排出港滑槽；第 9–10 页：首／末袋 ML 预测进入到港提取带分配 | 支持机场预测结果用于实际资源优化；研究传统 BHS，作者指出 ICS 可能有不同瓶颈，未给出有限盘预调或统一刷新周期 |
| **[F5] Sørensen、Rosenberg、Karstoft，ISCSIC 2021，仅官方摘要** | 带航班时刻及真实机场袋流分布的 BHS 仿真；集中式 RL 学习路由并平衡入口等待空托盘 | 是必须正视的相近工作。摘要未列 actor 观察，不能确定它提前读取未来航班计划；不能据标题推断已完成我们的预测／权限机制，也不能说 RL＋空盘储备从未有人做过 |
| **[F6] Jiang 等，Aerospace 2024，原文副本全文相关章节** | §4.2、表 1–2，PDF 第 12 页：月度数据，包含旅客量、起降架次及日历／宏观因素；§4.5 按前后 70%／30% 划分 | 支持行李量与客流／运行因素有关；不是逐航班分钟级预测，不能证实预测时已知当月最终实际指标 |
| **[F7] Jiang 等，TRR 2026-04-28，仅官方摘要** | IPSO-BPNN 多因素行李流量预测 | 更新检索已覆盖至 2026 年；未读到全文，不补写逐航班字段、预测提前量、实时版本或验证划分 |

完整原始来源：

- **[F1]** Mitchell de Keijzer. *Enhancing Baggage Handling Operations at Hub Airports through Sequential Forecasting and Resource Allocation*. MSc thesis, TU Delft, July 2023. [TU Delft 原文](https://repository.tudelft.nl/file/File_d54898c3-edfd-4b30-9d11-b75afc8db1ea)。
- **[F2]** Necip Gozuacik, Engin Sag, Onur Adiguzel, Adem Tekinbas, Sibel Malkos. *Short-Term High-Resolution Prediction of Airport Baggage Volume Using AI-Based Approaches*. ICECCE 2025, 27–28 August 2025. [DOI 10.1109/ICECCE67514.2025.11257932](https://doi.org/10.1109/ICECCE67514.2025.11257932)；[ITEA 项目方公开论文合集](https://itea4.org/project/workpackage/deliverable/document/download/1026/D5.5%20Academic%20Publication%20Series.pdf)，本篇位于合集开头。
- **[F3]** Paolino De Falco, Pablo Gasco Casado, Ivan Baruta, Hanna Wulkow. *Quantile-based Machine Learning Predictions of Luggage Arrival Time at Airport Reclaim Areas: A Data-Driven Approach Using Operational Data from Munich Airport*. SESAR Innovation Days 2025. [SESAR 官方全文](https://www.sesarju.eu/sites/default/files/documents/sid/2025/papers/SIDs_2025_paper_60-final.pdf)。原文未见 DOI，不补猜。
- **[F4]** David Pisinger, Samuel í Hjøllum Rude. *Advanced algorithms for improved baggage handling*. Journal of Airport Management 14(3), 280–290, 2020. [DTU 官方同行评议作者稿](https://backend.orbit.dtu.dk/ws/portalfiles/portal/266090005/PisingerRude.pdf)；作者全名按 [DTU 正式记录](https://orbit.dtu.dk/en/publications/advanced-algorithms-for-improved-baggage-handling/) 核对。
- **[F5]** René A. Sørensen, Jens Rosenberg, Henrik Karstoft. *Baggage Routing with Scheduled Departures using Deep Reinforcement Learning*. ISCSIC 2021, 13–19. [DOI 10.1109/ISCSIC54682.2021.00014](https://doi.org/10.1109/ISCSIC54682.2021.00014)；[Aarhus 官方摘要](https://pure.au.dk/portal/en/publications/baggage-routing-with-scheduled-departures-using-deep-reinforcemen/)。本轮未取得全文，策略输入仍待核对。
- **[F6]** Bo Jiang, Jian Zhang, Jianlin Fu, Guofu Ding, Yong Zhang. *Research on Check-In Baggage Flow Prediction for Airport Departure Passengers Based on Improved PSO-BP Neural Network Combination Model*. Aerospace 11(11), 953, 2024. [正式论文与 DOI 10.3390/aerospace11110953](https://www.mdpi.com/2226-4310/11/11/953)；[本轮核读的出版原文副本](https://www.researchgate.net/journal/Aerospace-2226-4310/publication/386006089_Research_on_Check-In_Baggage_Flow_Prediction_for_Airport_Departure_Passengers_Based_on_Improved_PSO-BP_Neural_Network_Combination_Model/links/67eb0bda9b1c6c48776a0dcd/Research-on-Check-In-Baggage-Flow-Prediction-for-Airport-Departure-Passengers-Based-on-Improved-PSO-BP-Neural-Network-Combination-Model.pdf)。
- **[F7]** Bo Jiang, Jian Zhang, Guofu Ding, Jianlin Fu. *Short-Term Forecasting of Checked Baggage Flow in Airports Using a Hybrid Improved Particle Swarm Optimization-Back Propagation Neural Network Model*. Transportation Research Record, first online 28 April 2026. [官方摘要／DOI 10.1177/03611981261441276](https://journals.sagepub.com/doi/abs/10.1177/03611981261441276)。

### 11.8 对创新主张的修订

不能以“机场航班可提前知道”“用了预测”“RL＋空盘”“分布式 MPC＋RL”等组合保证首创。[F5] 已有很近的航班相关负荷与空盘 RL 工作；[L5] 已有载空联合 MPC；第 8 节也已列出预测驱动空闲运力再分布。

更适合检验的研究问题是：**在固定机场 ICS 物理结构与有限托盘循环中，区域控制器只使用合法本地信息及当时收到的航班先验，联合评估未来需盘和载货过程造成的托盘释放，让学习改善仍可执行的跨区预调度，并保留原逐件参照和真实接纳规则。** 其中释放是动作与拥堵共同决定的内生量，预测更新与快速执行的频率可以不同，但有效性和当前权限需要衔接。

这是一项值得继续验证的方向，尚不是创新性认证。下一阶段用具体机制、有效动作、信息公平的消融、独立场景和实际逐件结果支撑差异；文献未报告的接口不能擅自解释为对方没有实现。本轮核读范围内，未找到已证实与上述全部具体条件相同的实现，但不作不存在相同工作的保证。

---

本文件记录本次可公开复核的结论、证据与实施决策；不声称已修改仓库、启动新训练、重新运行 native、完成现场部署或证明文献不存在相同工作。
