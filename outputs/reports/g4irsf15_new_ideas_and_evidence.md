# G4IRSF15 新想法、证据与决策日志

本日志记录实施过程中形成、被验证或被否证的想法。它不是性能结论；
只有状态为 `RUNTIME_VERIFIED` 或 `EXPERIMENT_VERIFIED` 的条目才可用于正式结论。

## 状态词

- `SOURCE_AUDIT_SUPPORTED`：由源码、冻结产物或输入拓扑审计支持，仍需运行验证。
- `RUNTIME_VERIFIED`：已有原生运行时回归测试支持。
- `EXPERIMENT_VERIFIED`：已有原始 `map2`、原始 1x 任务的实验支持。
- `REJECTED`：验证失败，不进入候选。
- `PENDING`：尚未取得足够证据。

## 决策条目

### NI-001：因果动作证书必须绑定“已提交动作”，不能绑定“已选择意图”

- 状态：`RUNTIME_VERIFIED`
- 发现：旧 I1 在源服务资源检查前记为 applied，旧 I3 在 merge request
  接受或边提交前记为 applied，可能产生 action-changing 假阳性。
- 决策：I1 只在源服务预约和入场事件发布后签发证书；I3 只在目的合流请求
  成功入队或单边移动真正提交后签发证书。未提交的选择意图保持
  `changed_action_count=0`。
- 证据：原生 `test_g4irsf14_causal_intervention` 已覆盖“源资源被占用时 I1
  不得记为 action-changing”，以及 I1/I3 正常提交路径。
- 对方向的意义：训练标签对应可执行的局部动作，而不是中央离线脚本的意图，
  避免把不可落地的动作教给去中心化策略。

### NI-002：I4 应定义为“等待一个局部服务机会”，而不是固定秒数退避

- 状态：`RUNTIME_VERIFIED`
- 发现：固定 `retry_interval` 会把实验旋钮混入动作定义；使用最小 1ms 粒度又会
  制造无意义事件抖动。
- 决策：I4 的处理动作冻结为等待当前节点一个真实服务周期：
  `max(local_service_duration, dispatch_headway)`。证书还必须绑定已发布的局部
  wakeup 时间和 generation。
- 证据：原生回归用 `retry_interval=0.01` 与 `7.0` 两个配置验证，I4 的动作时长
  和证书不变。
- 对方向的意义：动作只依赖当前局部节点的自然节拍，适合后续 supervisor 和
  分布式实现。

### NI-003：H_system 固定为完整原始 1x cohort

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：旧机制允许调用方任意传入“selected system IDs”；用 affected bag
  加一个无关 bag 不能代表系统外部性。
- 决策：G4IRSF15 的 `H_system` 唯一定义为原始 1x 输入展开后的全部 runtime
  segment IDs，并完整 drain/finalize；不得按干预结果改变 cohort。
- 待验证：正式 campaign 必须完成至少 128 个不同 clone group 的完整
  H_system matched pairs。
- 对方向的意义：可测量一个局部动作对其余订单的真实外部性，避免只优化受影响
  行李而把延迟转嫁给系统。

### NI-004：checkpoint bank 采用两遍确定性重放，而不伪造磁盘序列化

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：当前 checkpoint 是持有私有 `CheckpointStorage` 的进程内
  `shared_ptr`，不存在可审计的跨进程序列化协议。
- 决策：第一遍只生成内容寻址 descriptor；第二遍按连续 event ordinal
  shard 在新进程中确定性重放到目标，在同一 checkpoint 上顺序运行 baseline
  与 treatment。每个 shard 原子写出并可从 descriptor 重放恢复。
- 待验证：pilot 对 1/2/4 worker 做吞吐、峰值 RSS、重放一致性比较后再冻结并发。
- 对方向的意义：保留精确配对和可恢复性，同时不把未经验证的 checkpoint 文件
  冒充真实运行时状态。

### NI-005：人口样本与长尾富集样本分离

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：只按高风险尾部富集会高估 oracle coverage，不能代表原始机会总体。
- 决策：用确定性最小哈希保留独立 population sample，并另建 enriched-tail
  sample；记录每层 `N_h/n_h/pi_h`，用于审计覆盖构成。原“人口结论使用抽样权重”
  的提案已被 NI-017/NI-020 部分覆盖：本轮未建模 horizon assignment，且 formal
  frame 受 pilot 历史条件化，因此不发布无条件 population causal effect；权重只作
  post-pilot 条件有限 frame 的 reference sensitivity，区间只描述 realized panel
  对 clone-group 重采样的敏感性。
- 待验证：Stage 15D 产出必须同时报告 population/enriched strata 的 realized-panel
  描述、唯一 clone group 数和每组标签数，并由 validator 拒绝任何总体因果识别声明。
- 对方向的意义：既能集中学习稀有拥堵状态，又不牺牲对大规模订单总体的可解释性。

### NI-006：把直接处理集合与实际系统受影响集合分开

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：一个局部动作的直接 target bags 与最终产生结果差异的 bags 并不等价。
- 决策：每个完整 H_system pair 同时记录 `direct_treatment_set` 和
  `realized_affected_set`，报告外部性大小与 H_bag/H_system 符号不一致率。
- 待验证：128 个 H_system pairs 完成后计算。
- 对方向的意义：这是判断局部自治是否会产生不可接受全局副作用的关键证据。

### NI-007：G2 活跃 token 上限可按“上游前沿”而非订单数界定

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：`map2` 有 54 个节点、69 条有向边、23 个多入边合流节点；本图所有合流
  节点入度均为 2。旧 E4 的 pending request churn 与订单数强相关。
- 决策候选：G2 在每个 `(upstream, destination)` 前沿最多保留一个代表请求，
  使每个目的节点活跃 token/request 上界为入度，而不是上游等待订单数。
- 必须保持：slot-first、work-conserving、一步预约、目的节点所有权、loser 留在
  上游；不得读取未来路线或全局队列。
- 待验证：实现后必须证明
  `eligible_request_exists_but_slot_idle_seconds == 0`，并完成守恒、代次、
  stale/forged token、checkpoint/digest/tamper 回归。
- 对方向的意义：把协议状态复杂度从订单规模解耦到局部拓扑度数，是面向更大订单
  规模的直接结构性改进。

### NI-008：当前“去中心化”结论限定为逻辑与信息作用域

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：当前实现仍在单进程事件循环中；目的节点 controller 的所有权和策略输入
  是局部的，但尚未证明跨进程消息传递、容错一致性或网络部署。
- 决策：正式文档使用“destination-owned / local-information decentralized
  semantics”，不宣称已经完成物理分布式部署。
- 对方向的意义：保持论文和工程声明与证据边界一致，同时为后续真正分布式实现
  保留清晰接口。

### NI-009：所有新协议/监督器状态都必须进入 checkpoint 与确定性摘要

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：若 G2 token、supervisor latch 或代次不进入 checkpoint/digest，
  matched replay 可能表面相同、实际遗漏关键状态。
- 决策：任何新增持久运行时状态必须同时进入 capture/restore、组件 digest、
  aggregate seal、tamper test 和 no-op replay fidelity。
- 待验证：G2/supervisor 实现阶段执行。
- 对方向的意义：确保局部自治机制在并行实验、故障恢复和可复现实验中仍是同一个
  状态机。

## 暂不采纳

### NR-001：把内存 checkpoint 直接称为 sparse checkpoint 文件

- 状态：`REJECTED`
- 原因：源码没有可验证的序列化/反序列化契约，也没有跨进程 seal；这样做会产生
  无法恢复且不可审计的“证据文件”。采用 NI-004 的两遍确定性重放。

### NR-002：未过 2048/128 硬门就训练并发布正式学习模型

- 状态：`REJECTED`
- 原因：这会重复 G4IRSF14 “有 descriptor、没有完成 action-changing label”
  的失败。硬门未满足时只允许输出阻塞证据和机制候选，不得声称学习收益。

## 实施中新发现

### NI-010：机会普查、统计选样和完整 descriptor 物化必须分成三阶段

- 状态：`RUNTIME_VERIFIED`
- 发现：在每个候选边界计算完整 18 组件状态摘要，会让仅 512 个 segment 的试扫
  超过 120 秒；直接对原始 43,603 segment 运行该算法不可行。
- 决策：第一遍原生运行只发布 outcome-free、无完整状态摘要的轻量 skeleton 人口；
  第二阶段在 Python 中与受保护的 task/tail 元数据连接，按层记录
  `N_h/n_h/pi_h` 并冻结选中 skeleton；第三遍原生确定性重放，只为选中的
  skeleton 计算完整状态摘要和唯一主动作，生成内容寻址 descriptor。
- 后续修订：上述“第三遍为全部选中 skeleton eager seal”已被 NI-030 的 90 分钟
  负结果否定，并由 NI-031 的 target-address frame + executed-pair onsite seal 合同
  取代；第一遍人口普查和第二阶段 outcome-free 统计选样仍保留。此处作为设计演进
  记录，不再代表当前生产路径。
- 必须验证：轻量 skeleton 步骤与正常 no-op 步骤的事件后状态完全一致；人口终止
  必须证明 finalize、43,603 complete、0 failed、无 event-limit；选中 skeleton
  必须在第二遍重放到同一事件并重新成为原生唯一主动作。
- 已验证：Debug/Release tiny canonical map2 链路得到 190 events、18 个 skeleton，
  I1/I3/I4 各物化并完成一个 action-changing H_bag；later-only ordinal 129
  重放精确命中。原生回归证明 full probe 与 skeleton no-op 的事件后状态摘要一致，
  event-cap 截断不能冒充完整 census。原始 43,603 segment 人口仍需正式执行。
- 对方向的意义：人口普查成本随事件数增长，而昂贵状态封装成本随实验目标数增长，
  避免为了扩大订单规模而让证据生成成本二次爆炸。

### NI-011：二进制哈希不能替代“该二进制由这些源码构建”的证明

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：同时记录 `.pyd` SHA 和当前源码 SHA，只能证明两个对象当时存在，不能证明
  二进制确由这些源码编译。
- 决策：正式 campaign 只接受由 clean Release 构建过程生成的 exact-binary
  manifest；它绑定本地传递依赖清单、CMakeCache、编译器/Python/pybind11、
  configure/build argv、Git HEAD、binary diff、staged diff、未跟踪源码和最终
  模块 SHA。源码在构建期间变化则中止。
- 证据：独立生成器和 6 个定向单元测试已实现；实际清单只能在最终接口冻结并完成
  clean build 后发布。
- 对方向的意义：后续局部自治策略、监督器或学习器的收益都能追溯到同一份可重建
  运行时，而不是不可解释的本地二进制。

### NI-012：历史 fail-closed 证据应通过显式 successor transition 延续

- 状态：`RUNTIME_VERIFIED`
- 发现：G4IRSF14 历史校验器把自身及 Stage-E 源码纳入冻结身份；直接修改它来
  “允许新源码”会破坏它自己的证据链，而永远要求当前源码等于旧源码又会阻止合法
  后继开发。
- 决策：保持 G4IRSF14 校验器字节不变。新校验器从冻结 Git commit 重建历史源码
  临时快照并运行原校验器，再验证内容寻址的 G4IRSF14→G4IRSF15 源码过渡清单。
- 证据：合法过渡、successor 源码篡改和 manifest 自哈希篡改 3 个回归均已通过；
  旧校验器仍保持 Git 零差异。
- 对方向的意义：每代去中心化机制都能演进运行时，同时保留上一代负结果和门禁的
  原始含义，避免“为了让 CI 绿而重写历史”。

### NI-013：系统指标必须同时保留 runtime segment 与原始订单两个口径

- 状态：`RUNTIME_VERIFIED`
- 发现：原始 28,506 个订单展开成 43,603 个 runtime segment；只按 segment
  汇总会给多段订单更高权重。现有七元 runtime records 又没有受保护的
  `original_entry_time`，不能从 release 猜测。
- 决策：三个原生 campaign API 接受按 segment 对齐、由受保护 inputdata 重建的
  `original_entry_times`；校验同一 task 值一致且不晚于 release，并同时发布
  43,603 segment cohort 和 28,506 raw-bag original-entry 聚合及 mapping SHA。
- 待验证：真实 exact-pyd 集成测试和 128 个完整 H_system pairs 必须让两种口径
  贯穿 native evidence、label、独立 validator 和最终报告。
- 已验证：Release tiny H_system smoke 已能从完整 cohort difference sidecar
  重算 changed set、realized numeric delta 与 raw-original delta；tiny 输入因不是
  43,603/28,506 protected shape 而被 formal hard gate 正确阻断。
- 对方向的意义：扩展到更大订单规模时，不把拆分较多的订单误当成更多独立需求，
  使局部策略的系统级外部性结论保持业务可解释性。

### NI-014：exact binary 应同时做到内容绑定与字节可复现

- 状态：`RUNTIME_VERIFIED`
- 发现：同一冻结源码、同一 MSVC/LTCG 工具链连续两次 clean Release build 得到
  相同大小但不同 SHA 的 `.pyd`；单纯记录某次二进制哈希可精确重放，却不利于第三方
  从源码复建同一字节。
- 决策：仅对 MSVC 的 `czr005_cpp` MODULE 目标同时增加编译与链接 `/Brepro`；
  不能只设置 shared-linker flags，因为 pybind 目标属于 MODULE。
- 证据：在两个全新独立 build 目录、MSVC 19.41 上分别 clean build，两个
  2,030,080-byte 模块逐字节相同，SHA256 均为
  `c0ffa547cd1ad1bad0418dd29c540c540b97186a89901897bec71202dc638d2e`，
  其中一份通过 pybind smoke。
- 待验证：最终源码提交后由 exact-binary attestor 再执行一次 clean build，并与
  第二个独立目录复核 SHA；正式 manifest 记录最终提交上的哈希。
- 对方向的意义：扩大实验和部署规模后，每个 worker 都能验证自己加载的是同一
  状态机字节，而不只是“由相似源码编译”的模块。

### NI-015：离线人口分层不得参与局部动作排序

- 状态：`RUNTIME_VERIFIED`
- 发现：第一版 skeleton 把全局 merge/fault/queue 计数放进 population group
  hash，又用该 hash 给 I1/I3 候选动作排序；因此远端拥堵变化可能改变同一局部
  boundary 的处理动作，且生产 global-scan 计数不会暴露这条离线审计路径。
- 决策：把 projection 拆成两部分。全局计数只生成 offline population group，
  用于实验分层；primary treatment 完全采用局部稳定数值序：I1 取本地 ready-set
  最小合法 peer，I3 取本地 legal-next 中最小非 baseline 邻边，I4 只有唯一 hold。
  event ordinal、全局 event sequence 和任何 offline strata 都不得参与 action rank。
  因此“runtime no global scan”限定为在线决策执行路径；离线 census 仍可遍历已冻结
  controller/fault/junction 计数做审计分层，但该遍历不属于可部署策略输入。
- 证据：远端 queue/fault/merge strata 扰动回归证明 group/evidence hash 会变化，
  但 I1 peer 与 I3 next-edge 不变；Release CTest 2/2 通过。受保护 map/model 前
  512 segments 的 6,863 个 skeleton（I1=238、I3=1,850、I4=4,775）全部满足
  局部数值序。
- 对方向的意义：离线研究仍可观察总体分层，但未来部署的 destination-owned
  controller 不会因不可见的远端状态改变本地决策，守住逻辑去中心化边界。

### NI-016：因果 campaign 必须执行完整预注册面板，工程门槛不能成为提前停止条件

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：若在累计达到 2,048 个 H_bag 或 128 个 H_system label 后停止，后续 target
  是否被观测将依赖先前 outcome；即使已执行行全部正确，抽样权重、失败率和尾部结论
  仍会产生不可恢复的选择偏差。
- 决策：formal plan 冻结全部 target、shard 与顺序；发布必须恰好执行所有预注册
  shard，并为每个 target 保留一行（包括 false positive、horizon incomplete、
  neutral 与 harmful）。任一 shard 缺失、重复或额外出现时，只允许发布
  `INCOMPLETE_PANEL`，不得发布 effect estimate 或 gate pass。
- 证据：generator 与独立 validator 已实现完整 shard inventory、target inventory、
  native pair 到 label 的逐行重建及禁止 outcome-dependent early stop；仍需最终
  exact binary 的完整 formal 运行验证。
- 对方向的意义：大规模场景中的局部策略必须对“没有奏效的局部机会”同样负责，
  不能只保留成功干预，从而为后续 supervisor 和学习器提供可审计的失败边界。

### NI-017：horizon assignment 概率未冻结时，H_system 与混合 horizon 只能作描述性证据

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：当前 H_system target 由 deterministic hash、clone/event 去重和固定预算
  分配；它没有可审计的随机 horizon assignment probability。assigned H_bag 又是
  该分配的补集，因此仅用 descriptor 的抽样比例不能把任一 horizon 的效应升级为
  原始 skeleton 总体的无偏 HT/Hájek 估计。
- 决策：本轮 population effect 明确标记为未识别；H_system、H_bag-only 和混合
  horizon 指标仅发布 complete realized panel 的 descriptive/reference-sensitivity
  结果。下一版若需要总体估计，应按 clone cluster 在预注册 block 内做 SRSWOR，
  再在选中 clone 内均匀选择一个 descriptor，并记录
  `rho=(H_q/G_q)*(1/g_c)`；或让每个 formal target 都发布同定义的 H_bag endpoint。
- 证据：统计审计已给出有限总体与 horizon 两阶段概率合同；独立 validator 正在
  加入“任何未建模 horizon 均不得声称 population causal inference”的篡改回归。
- 对方向的意义：去中心化控制的局部收益和系统外部性被分开陈述，避免用小范围
  局部 endpoint 掩盖全系统代价，也避免以复杂权重制造不存在的总体代表性。

### NI-018：split 连通分量必须合并 I1 的全部直接受影响 raw tasks

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：I1 会在 target 与 peer 两个 ready bag 之间交换本次 source service；若 split
  只按 target task 或 clone group 分组，peer task 可以进入另一数据切分，形成直接
  outcome 泄漏。H_system 的外部性集合若全部并入，则又会把大部分 1x cohort
  不必要地塌缩成单一连通分量。
- 决策：split 使用 clone group 与所有 direct-affected task IDs 的并查集连通分量；
  I1 同时纳入 target 与 peer，I3/I4 纳入各自直接处理 task；H_system externality
  只用于评估，不参与 split 连边。
- 证据：generator 与独立 validator 已分别重建 direct-task union，并要求 split
  contamination 为 0；最终 formal labels 仍需验证实际连通分量规模。
- 对方向的意义：局部动作学习不会通过同一订单的直接反事实结果“偷看”验证集，
  同时保留足够多的独立局部自治单元用于训练、校准和评估。

### NI-019：H_system 原始订单指标需要逐 raw-bag sufficient-statistics sidecar

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：只有 43,603 个 segment 的 outcome hash 和 changed-row 数值，无法从发布
  证据独立重算 28,506 个原始订单的均值、分位数、deadline miss 与完整性；仅核对
  native aggregate 会留下“重哈希 aggregate 与 shard”仍能通过的审计缺口。
- 决策：每个 H_system branch 按 task ID 严格升序发布 raw-bag sufficient statistics：
  runtime ID mapping、完成/失败/deadline 标志、original-entry、release、source-wait、
  network 与 total-system 累计量，并绑定逐行 SHA、全体 content SHA、segment/raw-bag
  mapping SHA。label 只保留 binding；原“每个压缩 shard 保存完整 raw rows”的存储
  条款已被 NI-022 覆盖，改为一份完整 baseline 加每个 treatment 的稀疏 changed rows。
- 证据：原生 sidecar、聚合等价回归、Python 独立重算和定向篡改测试已实现并通过；
  正式 protected 28,506-row H_system 运行、稀疏差分大小与总发布体积仍待实测。
- 对方向的意义：扩展到更多订单和拆分 segment 时，系统指标仍以业务订单为单位，
  且任何 worker、validator 或后续论文分析都能从充分统计独立恢复结论。

### NI-020：pilot 自适应后的权重必须限定为条件有限总体或 reference sensitivity

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：active kind、R2 是否执行和 formal attempt budget 均由 pilot outcome 决定。
  因此把多阶段比例约掉得到 `m_h/N_h`，不能无条件解释为原始 skeleton 总体的一阶
  inclusion probability；blocked kind 的 formal inclusion probability 更是 0。
- 决策：工程 gate 与总体推断分开。本轮若保留权重，只称
  `design-conditional on observed pilot history and active-kind set` 的 post-pilot
  finite-frame reference weight；complete/action-changing responder 的 ratio mean
  不称为所有 opportunity 的 ATE。下一版在 census 时预留互斥 R1/R2，并在 outcome
  前冻结独立 formal randomization seed。
- 证据：统计审计已推导 conditional `pi=m_h/F_h`、responder-domain HT total 与
  Hájek ratio 的适用边界；正式 artifact 与 validator 仍需逐字段验证这些 claim。
- 对方向的意义：框架可以继续利用 pilot 做资源分配和机制筛查，同时不把工程上的
  自适应决策误包装成对所有局部自治状态的无偏因果结论。

### NI-021：R2 必须绑定可解释的 screening 修订，单纯换一批 target 不等于修复

- 状态：`PENDING`
- 发现：若 R1 的 action-changing complete 支持不足，仅从同一 sealed pool 换 64 个
  descriptor，最多证明另一批样本的命中率，不能证明 false-positive screening 已被
  修复。若修订会改变原生动作、descriptor 定义或 binary，旧 census、pool 与 R1
  又全部失去同源性。
- 决策：R2 只接受两种 fail-closed 路径：其一，发布绑定 R1 false-positive taxonomy、
  同一冻结 source/binary/census 的离线 screening-revision manifest，再重建 pool；
  其二，明确发布 `SCREENING_REPAIR_REQUIRED` blocker 而不运行 R2。任何原生源码或
  descriptor 语义变化都必须重建 exact binary、census、pool，并从 R1 重新开始。
- 待验证：只有 R1 出现 `RESAMPLE_REQUIRED` 时才激活该合同；若 R1 全部通过，则该
  路径保持 dormant，不制造虚构的“已修复”证据。
- 对方向的意义：局部机制的稀疏支持会被当作需要解释和修复的结构性信号，而不是
  靠不断重抽样掩盖；这对更大拓扑、更大订单规模下的机制迁移尤其重要。

### NI-022：完整 shard 是运行态，Git 发布应使用单一 baseline 加稀疏 treatment 差分

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：每个完整 H_system pair 若重复保存 43,603-row cohort hash sidecar 和两份
  28,506-row raw-bag sufficient statistics，实测约 10.70 MB zstd；仅 128 个 complete
  pair 就约 1.28 GiB，固定 256 次尝试最坏约 2.55 GiB，虽单 shard 小于 GitHub
  100 MiB 限制，整个证据包仍不可持续推送。
- 决策：完整 native shard 保留为本地、可恢复、内容寻址的 run-state，不直接进入
  Git。正式发布保存一份所有 H_system target 共同的 deterministic baseline：
  全 cohort baseline outcome-hash inventory 与 baseline raw-bag rows；每个 treatment
  只保存 changed segment outcomes 和 changed raw-task rows。validator 以 baseline
  补齐未变化行，重建完整 43,603-row cohort outcome-hash inventory 与 28,506-row
  raw-bag sidecar/content SHA，并从 raw rows 独立重算订单聚合与分位数后再接纳
  label；不从 cohort hashes 虚构 segment 数值聚合。若任一 baseline root 不同，则
  fail closed，禁止去重。
- 证据：尺寸测量已完成；compact producer、独立 validator 与定向 tamper tests
  已实现并通过。baseline continuation 的最终 cohort/raw roots、首个真实 sparse
  change-set 密度及 256-pair 总 Git 体积仍须在正式 protected 面板中逐 pair 验证。
- 对方向的意义：证据体积从“订单规模 × 干预数”中的重复 baseline 项移除，保留
  与真实外部性变化量近似成正比的增量；这是框架面向更大订单规模时同样重要的
  数据平面去中心化与可扩展性改进。

### NI-023：分片内容正确还不够，发布物必须绑定可审计的执行 profile

- 状态：`RUNTIME_VERIFIED`
- 发现：单独验证 shard 内容不能证明 worker 采用新进程、受到内存上限约束、持续
  存活或执行了完整预注册面板；人工 tmux 日志也无法形成便携的内容寻址契约。
- 决策：使用 bounded fresh-process orchestrator。每次执行发布原子、自哈希 profile
  与 heartbeat，绑定 plan/binary/build/worker/orchestrator SHA、精确 argv、整棵
  worker process-tree RSS、强制 cap、时间戳和 shard 结果。pilot/formal finalizer
  只接受一个或多个互斥 profile，且其 requested shard 并集必须精确等于计划全集；
  profile 只能发布到非忽略的专用目录，portable validator 不依赖原主机二进制路径。
- 证据：Windows process-tree RSS 实测、cap 超限/不可观测/快速退出/TERM 升级、
  周期 heartbeat、覆盖缺口/重叠、源码与输入篡改、外部二进制删除后复制仓库验证等
  回归均已通过；真实 protected pilot 的 1/2/4-worker 吞吐与峰值仍待运行。
- 对方向的意义：扩大订单与并行度时，资源边界、恢复语义和完整执行面板成为正式
  证据的一部分，避免“算法可扩展”被不可复现的进程管理或隐式内存过载掩盖。

### NI-024：native formal shape 门可进一步绑定 pinned cohort 身份

- 状态：`PENDING`
- 发现：当前 native `protected_full_1x_shape` 直接检查 43,603/28,506 数量；精确
  runtime/raw/original-entry mapping SHA 与 protected input SHA 由外层 plan、pair
  attestation 和独立 validator 绑定。该组合已 fail closed，但 native 单层仍是数量门。
- 候选改进：后续把 pinned runtime/raw/original-entry mapping SHA 作为只读配置传入
  native formal gate，使数量相同但身份不同的 cohort 在原生层也立即失败。这个改动
  会改变 binary/source identity，不能在本轮 census 之后热补。
- 证据边界：本轮由双层 Python provenance 与逐 pair mapping SHA 提供完整身份保证；
  native pinning 仅作为纵深防御候选，不冒充已实现功能。
- 对方向的意义：多站点或更大订单规模下，不同 cohort 可能具有相同计数；把身份门
  下沉能减少跨部署误接数据集的风险，同时保持局部运行时不读取全局未来信息。

### NI-025：资源上限应产生结构化 blocker，而不是通用异常

- 状态：`RUNTIME_VERIFIED`
- 发现：event cap 恰好落在 nonzero candidate-mask 顶部时，旧 skeleton probe 会因
  `event_processed=false` 抛通用 invalid-step 异常；它虽不会伪造完成，却丢失了可
  审计的截断原因。
- 决策：只在 event/time limit 已被 runtime 明确置位时返回
  `SKELETON_PROBE_SKIPPED_RUNTIME_LIMIT`，要求 observed set 为空、事件计数不增长，
  scan 终止并发布不完整 census；其他 `event_processed=false` 仍抛错。未处理的顶部
  不计入 processed candidate 统计。
- 证据：新增“完整 skeleton census 与普通 drain 的五项 terminal replay hash/计数
  完全一致”回归，以及“cap 精确落在首个 nonzero mask”回归；原生测试和三 API
  pybind smoke 均通过。
- 对方向的意义：当更大规模运行触碰资源边界时，框架能输出机器可判定的负证据并
  安全恢复，而不是留下无法区分算法错误、资源截断和真实不可行性的模糊失败。

### NI-026：发布级因果证据应在异构操作系统上复验

- 状态：`PROPOSED`
- 发现：Windows 生成端的盘符绝对路径若在 Linux 校验端直接交给宿主 `Path`，
  会被误判为相对路径；CMake 与 worker argv 的 basename 也存在同类生产端语义
  丢失风险。本机生成与本机复验都通过，仍不足以证明证据包可移植。
- 决策：build manifest、orchestrator profile 与 portable validator 按生产端
  Windows/POSIX 词法解释路径；GitHub Ubuntu workflow 在相应产物存在时分别执行
  scan、pilot R1/R2 或 formal 的静态内容复验，不依赖重新打开生成机上的外部
  binary。源码阶段无产物时允许显式跳过，不能据此把本条升级为已验证。
- 现有证据：Windows 聚焦回归、纯 Windows producer-path 的跨主机词法回归、外部
  binary 删除后复制仓库复验均已通过；只有当 Ubuntu CI 对已提交 protected
  artifacts 的条件分支实际通过后，状态才可升级为 `RUNTIME_VERIFIED`。
- 对方向的意义：去中心化、跨 worker、跨站点的大规模执行天然会遇到异构部署；
  把跨 OS 复验纳入发布门禁，能避免把生成机文件系统偶然性误当成算法证据的一部分。

### NI-027：输入身份应绑定原生适配后的语义记录，而不是猜测原始字段名

- 状态：`RUNTIME_VERIFIED`
- 发现：首次真实 census 在干预前 fail closed；冻结 `inputdata.jsonl` 使用 `std`
  表示 deadline，且允许省略 `source`，而 workload identity 重建误读了不存在的
  `deadline`/`source` 字段。合成 fixture 同时提供这两个字段，因而没有暴露偏差。
- 决策：producer 与独立 validator 都按既有 G4IRSF12 native adapter 的精确定义
  重建记录：`deadline=std`，`source=source or node_<start>`；原始 JSON SHA 仍先固定，
  随后再对适配后的有序 runtime cohort 做 canonical hash。新增直接读取全部 43,603
  条冻结记录的回归，并要求 producer/validator 的 segment、raw-task、runtime mapping、
  original-entry mapping 与 workload identity 逐项一致。
- 证据：真实输入回归通过，修复后的聚焦冻结集 106 项全部通过；首次失败发生在
  census 读入阶段，没有产生 descriptor 或因果 label。完整 census 仍须在新源码提交
  和新 exact binary 上重跑，旧 build manifest 明确作废。
- 对方向的意义：面向更多站点和订单 schema 时，去中心化 worker 必须对“进入本地
  决策器的实际请求语义”达成一致；把 adapter 后的语义身份作为契约，可避免不同节点
  因字段别名或默认值不同而悄然处理不同 workload。

### NI-028：发布级资源见证必须使用显式 ABI，而不是 ctypes 默认签名

- 状态：`RUNTIME_VERIFIED`
- 发现：修复输入 schema 后，正式 census 在首个内存快照处 fail closed。旧 Windows
  实现通过 `ctypes.windll` 调用 `GetCurrentProcess`/`GetProcessMemoryInfo`，没有声明
  64-bit HANDLE、参数和返回类型；在当前 64-bit Python 上真实调用失败。orchestrator
  的同类 process-tree sampler 因显式声明 Win32 ABI 而可正常工作。
- 决策：campaign sampler 使用 `WinDLL(..., use_last_error=True)`，并为
  `GetCurrentProcess` 与 `GetProcessMemoryInfo` 固定 `argtypes`/`restype`；结构字段
  使用 `wintypes.DWORD` 与指针宽度的 `c_size_t`。新增真实进程取样回归，要求 peak
  RSS 为正，且可用的 current RSS 不大于 peak RSS。
- 证据：失败发生在 native scan 调用之前，没有产生 descriptor/label；修复后的
  Windows 真实 sampler 回归通过；workflow 已加入最小 `windows-latest` ABI job，
  其远端结果仍待新提交触发。完整 campaign census 仍须在新提交与新 exact manifest
  上重跑，不能沿用修复前的资源见证。
- 对方向的意义：去中心化多 worker 的可扩展性结论不仅依赖算法输出，也依赖可信的
  资源边界；显式 ABI 能避免监控层因平台调用约定而失真，从而让内存 cap、恢复和
  跨主机执行 profile 成为可审计证据。

### NI-029：完整 census 应按有序内容分片发布，而不是依赖单个大文件

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：首次完成 747,962 条 skeleton 的正式 census 后，单个 level-9 zstd 文件为
  136,032,811 bytes，超过 GitHub 100 MiB 硬限制前的 95 MiB 安全门；计算是完整的，
  但单文件发布拓扑不适合更大订单规模。
- 决策：descriptor manifest 升级为 v2；完整 population 按固定有序行区间写成编号
  zstd parts，每块独立绑定 path、SHA、byte count、row start/end/count 与 canonical
  content SHA，并保留整个有序数组的流式 canonical SHA。独立 validator 要求块编号、
  连续区间和并集精确一致，拒绝缺块、额外块、换序、重复 skeleton/group 或内容篡改；
  每个 part 仍必须严格小于 95 MiB。
- 证据：真实 747,962-row 数据按 200,000 行试分为 4 块，最大块 36,631,949 bytes，
  总计 135,984,998 bytes；流式全局 SHA 与原 canonical list SHA 等价，顺序/残留块/
  malformed inventory 回归和完整 108 项聚焦回归通过。正式 v2 census manifest 仍须
  在本次源码提交后的 exact binary 上重新生成并独立验证，通过后再升级状态。
- 对方向的意义：这把一个中心化“大证据文件”改造成可并行传输、校验和恢复的有序
  数据平面；未来不同站点或 worker 可独立持有 census 分区，同时通过全局内容根证明
  它们属于同一预注册总体，契合去中心化 MAPF 风格框架的扩展路径。

### NI-030：descriptor seal 是离线控制面成本，不能混入在线局部决策路径

- 状态：`RUNTIME_VERIFIED`
- 发现：基于提交 `3d027de` 的旧式正式 6,144-target eager materialization 即使完成
  747,962-row census 四块，
  并去除非选中事件的重复 skeleton probe、在第二次 replay 前释放 population，仍在
  5,404 秒外层预算耗尽时没有发布 descriptor manifest、pool、checkpoint 或 coverage。
  该进程消耗约 88.6 CPU 分钟；早期 working set 约 6.6 GiB，稳定 private bytes 约
  4.4 GiB。I1/I3/I4 分别选中 1,650/1,789/2,705 个目标；总计 6,144 个目标对应
  6,137 个不同 event ordinal，只有 7 组同 ordinal 双目标。因此按事件批处理最多仅
  减少 7 次、约 0.11% 的完整状态遍历，仍需约 6,137 次 seal，不能消除主成本。
- 根因证据：每次完整 seal 都要复制/排空 event heap，并遍历 43,603 个 bag/history、
  queue/calendar、corridor、credit、merge grant、fault、counter、scorer、beacon 与
  microphase 状态；这是全局审计遍历，不是局部动作选择所需的在线信息。90 分钟失败
  运行留下的四个 census part 只是临时重放副产物，不作为可接纳或可提交的正式证据。
- 本轮决策：拒绝继续扩大 eager-scan 预算，也不缩小 6,144 预注册目标面板。扫描阶段
  改为发布 outcome-free 的局部 target address，完整 state/boundary seal 只在某个已
  预注册 pair 真正执行并唯一匹配现场边界时生成；具体合同与等价证据见 NI-031。
- 对方向的意义：在线去中心化 MAPF 风格路由仍只读取局部状态并提交局部动作；昂贵的
  全局审计 seal 被明确隔离在离线控制面。下一步扩展订单规模时，应横向扩展证据生成，
  而不是把中心化全状态哈希开销重新带回在线 runtime。

### NI-031：用局部 target address 预注册，完整 G14 seal 延迟到实际执行现场

- 状态：`RUNTIME_VERIFIED`
- 设计：census/scan 只冻结输入 runtime cohort、event ordinal/seq/time、node、局部
  ready/legal/action 投影、selection key、prepopulation group 与 H_bag/H_system 两个
  horizon address hash；明确禁止 runtime-state、boundary、intervention 和 component
  hash 注入。因此 scan 的完整状态 digest 计数按合同为 0。worker 到达该本地地址后，
  先按 cohort、事件与局部 population/action 唯一解析；只有唯一匹配才在现场生成原
  G14 完整 descriptor，并从同一 checkpoint 克隆 baseline/treatment。缺失或多重匹配
  都作为预注册的 `SCREENING_FALSE_POSITIVE` attempt 留在分母中，绝不静默丢弃或任取
  第一个候选。
- 等价证据：native A/B 回归对同一 H_bag/H_system 边界分别执行 legacy eager seal 与
  deferred resolution，要求 resolved descriptor、18 个状态 component、aggregate
  runtime-state、clone group、boundary 和两种 intervention hash 精确相等。Python
  generator 与独立 validator 各自重算 canonical target address、prepopulation group、
  horizon hash 和现场 seal，且覆盖局部字段、cohort、当前 horizon、state component、
  intervention 以及额外字段注入篡改。当前聚焦 Python 98 项与 Release CTest 11/11
  全部通过。
- 证据边界：以上证明的是实现合同、eager/deferred 字节级等价及 fail-closed 行为；
  新提交对应的完整 protected scan、pilot/formal 实跑尚未完成，因此本条不宣称正式
  因果结果或规模 gate 已通过。生产 scan 仍必须从 exact committed binary 生成，并由
  独立 validator 接纳后才能进入 pilot。
- 对方向的意义：预注册和分片所需的身份只依赖局部冲突边界，而全局状态证明按实际
  执行量付费。随着订单数增长，证据成本从“候选目标数 × 全局订单状态”收敛为一次
  局部 frame 加“实际执行 pair 数 × 完整封印”，更贴近去中心化 MAPF 的局部协商单位。

### NI-032：不可回退的 state generation 可安全复用同一 checkpoint 摘要

- 状态：`PROPOSED`
- 想法：每个 runtime 维护不可回退的 `state_generation`；任何持久状态变更以及
  checkpoint restore 都产生新 generation。digest cache 只在
  `(runtime instance, generation)` 完全相同时复用，因而可消除一个实际 pair 内
  capture、source probe 与 matched-state 对同一状态的重复全量查询，同时保持旧 G14
  seal 的字节语义。checkpoint 可携带已验证 digest，但 restore 后必须先核对 checkpoint
  identity，再把该 digest 绑定到新的当前 generation，禁止恢复旧计数后误用分支缓存。
- 接纳门：实现前必须列举每条进入 G14 seal 的 mutation path，新增 supervisor/token
  状态也必须触发 generation；需加入 shadow full-recompute、随机 mutation、restore/
  branch、clone、fault、no-op 与漏失 invalidation 篡改回归。cache 不确定时必须
  fail closed 回退全量 seal，不能把普通 SHA 描述为跨不同状态的增量哈希。
- 本轮边界：本轮没有实现该优化，因为 NI-031 已移除 scan 阶段的主要重复封印，同时
  保留已审计的 G14 现场 seal；在因果证据链稳定前引入跨所有 mutation path 的缓存，
  风险高于当前可验证收益。
- 对方向的意义：若后续 formal pair 数或 cohort 继续增长，这是一项不改变现有证明
  schema 的低风险优化，可先减少每个 executed pair 的重复审计成本；跨状态的局部
  内容证明则作为 NI-034 的独立长期协议升级处理。

### NI-033：target-address frame 是局部冲突单元，不等于已完成物理分布式部署

- 状态：`SOURCE_AUDIT_SUPPORTED`
- 发现：target address 以 node、同一事件的 ready population、合法动作与被选动作
  描述可干预边界；prepopulation group 把同一局部竞争集合绑定为抽样簇。它天然适合
  按地址内容根分片、由不同 worker 独立执行，并用缺失/多重解析的显式 attempt 合并。
- 判断：这已经把原 HCA* 加中心化 supervisor 的“全局候选描述/证据生成”拆成 MAPF
  风格的局部冲突与协商单元，并让证据平面可横向扩展；但当前 runtime 仍在单进程内
  重放冻结 cohort，尚未证明跨机器消息传递、异步一致性、网络分区恢复或真正无中心
  协调。因此文档与结论应称“去中心化就绪的局部决策/证据框架”，不能夸大为已经完成
  物理分布式系统。
- 下一步证据：在保持 target-address 与 onsite-seal 合同不变的前提下，原型化多个
  planner owner 的异步 proposal/commit；比较中心重放与乱序消息、重复消息、节点失联
  后的最终动作和安全不变量，并测量通信量随局部冲突度而非全局订单数增长。
- 对方向的意义：明确“算法/证据去中心化”与“部署去中心化”的边界，可让后续工作把
  精力放在真正缺失的分布式所有权、冲突协议和恢复证明上，同时复用本轮已验证的局部
  MAPF 地址与因果审计接口。

### NI-034：长期状态证明可迁移到版本化 Merkle/content-addressed 局部状态

- 状态：`PROPOSED`
- 候选设计：按局部所有权把 destination controller、queue/calendar、corridor、
  credit/grant、fault、event frontier 与 bag/history 分成稳定叶节点；局部 mutation
  只重算受影响叶及其到根路径。checkpoint 保存根与内容寻址分区引用，未变化分区可
  跨 checkpoint、worker 和实验分支去重；执行节点只交换冲突相关叶与证明路径。
- 迁移边界：新 root 必须使用新 schema/version，不能声称与旧线性 G14 SHA 逐字节
  相同。迁移期应双重发布 legacy G14 seal 与新 Merkle root，并验证确定性排序、
  checkpoint restore、跨 worker 合并、缺叶、换序、重放和篡改 fail-closed；只有
  所有生产 mutation 类型的证据闭合后才允许升级正式门禁。
- 与 NI-032 的关系：generation cache 是保持旧 G14 字节语义的短期同状态复用；本条
  是改变证明表示的长期协议升级。两者不应混为“普通 SHA 可跨状态增量更新”。
- 对方向的意义：局部 agent 可以持有和更新自己的状态叶，而全局根仅承担离线审计与
  一致性控制。证明成本将更接近发生变化的局部分区数，而不是全局订单数，更适合多站点、
  更大规划空间和更大订单规模的去中心化 MAPF 风格框架。

### NI-035：provenance validator 必须区分 Git object ID 与内容 SHA-256

- 状态：`RUNTIME_VERIFIED`
- 发现：提交 `3418de2` 的 fresh exact build 与完整 scan 均成功，但首次 strict scan
  validator 在 build/publication ancestor 门 fail closed。manifest 的 build HEAD 与
  当前 HEAD 实际完全相同；失败来自验证器用 64 位 `is_sha256()` 检查标准 Git SHA-1
  仓库产生的 40 位 commit object ID，导致任何合法祖先都无法进入 `merge-base` 结果门。
- 修复：新增严格 Git object-ID 判定，只接受小写十六进制 40 位 SHA-1 或 64 位 SHA-256；
  在调用 `git merge-base --is-ancestor` 前先拒绝空值、错误长度、非十六进制和 option-like
  输入。artifact/content hash 仍只接受 64 位 SHA-256，二者不再混用。
- 证据边界：第一次 scan 的 747,962-row census、6,144 地址和零 eager full-state digest
  是有效诊断证据，但因 strict validator 未完成，不进入 pilot 或正式发布。修复会改变
  validator/source bundle，故必须从新提交重新 exact build、scan 和严格接纳，不能修改
  manifest 或绕过祖先门沿用旧产物。
- 对方向的意义：去中心化 worker 与跨主机证据链会同时处理 Git identity、内容根和
  状态承诺；明确各命名空间的算法与长度，可避免不同站点把“合法但不同类型的摘要”
  当成损坏证据，也避免为了通过校验而弱化来源祖先关系。

### NI-036：构建字节身份与 Git repository blob 身份必须双重绑定

- 状态：`RUNTIME_VERIFIED`
- 发现：NI-035 修复后 strict validator 正确进入 source-tree 门，但 Windows worktree
  的 `CMakeLists.txt` 为 5,678 个 checkout 字节，`git show` 返回 5,537 个 repository
  blob 字节；`core.autocrlf=true` 且历史混合换行使全量 smudge 结果也不是原工作树字节。
  因此直接要求“本机编译字节 SHA-256 == Git raw blob SHA-256”会把 clean tree 误判为
  篡改；简单把 LF 全换成 CRLF 同样不可靠。
- 修复：exact builder 对每个 native source 和 builder producer 同时记录两种身份：
  原始 checkout `sha256/byte_count` 证明本机实际读取的字节，`repository_blob` 则绑定
  build HEAD 下 Git object ID、raw blob SHA-256 与 byte count。生产 generator 在同一
  主机逐项复核两者，并把 builder producer 加入 dirty-source paths；独立 portable
  validator 通过 Git object database 重算 repository blob，不依赖宿主换行转换，只有
  `--strict-host-provenance` 时才额外要求 checkout 原始字节相同。正式发布同时要求
  inventory 与 producer 的 tracked/staged diff 为空且无 untracked source。
- 合同硬化：manifest 升级为 v2；dirty state 绑定 source path 的精确数量与 canonical
  path-set SHA，防止 clean 空 diff 掩盖漏记 producer。builder 在 configure 前冻结
  HEAD、branch、全部 native input 与 producer 原始快照，build 后要求它们逐项不变；
  任一 source dirty 状态直接拒绝生成 publication `COMPLETE` manifest。
- 篡改边界：repository blob 行进入 inventory bundle/self hash；换 path、OID、blob
  内容、工作树源码、builder producer 或 dirty diff 任一项都会 fail closed。该合同
  不把 EOL 差异忽略成“任意文本等价”，而是分别证明“实际构建字节”与“提交语义内容”。
- 证据边界：已增加强制 `eol=crlf` 的临时 Git 仓库回归，证明 generator 与独立
  validator 在 checkout SHA 不同于 blob SHA 时仍对同一 repository binding 达成一致；
  修复后的 exact build/scan/strict 链仍需重新生成，前两次未接纳 scan 不进入 pilot。
- 对方向的意义：跨 Windows/Linux worker 时，本地 checkout 表示可以不同，但参与同一
  去中心化实验的节点必须指向同一提交 blob。双重身份让本机可追责性与跨站点可移植性
  同时成立，而不是牺牲其中一项来通过校验。

### NI-037：campaign source identity 也应从 raw-only 迁移到双重身份

- 状态：`PROPOSED`
- 发现：NI-036 修复的是 exact native build inventory 与 builder producer；scan manifest
  中更宽的 `source_identity`（generator、validator、worker script、模型等）仍以 checkout
  raw SHA/byte count 为唯一 bundle 行。当前 Windows strict 链可完整复验，但换到 Linux/LF
  checkout 后，内容相同的文本仍可能在 `SOURCE_DRIFT` 被拒，不能据此宣称整个 campaign
  已完成跨 EOL portable validation。
- 候选改进：下一 schema 为每个 tracked source-identity 行加入 generation HEAD 下的
  `repository_blob`，本机生成端同时保留 raw checkout 身份，portable validator 只用
  Git blob 复核提交内容，strict-host 再复核 raw；模型或确需逐字节固定的数据文件继续
  要求 raw SHA 跨平台相同。source bundle 应分别发布 checkout root 与 repository root，
  不能用一个名称混合两类语义。
- 接纳门：Windows CRLF 生成 → Linux LF clone 的 scan/pilot/formal 静态复验必须真实通过；
  同时覆盖 blob/path/HEAD/raw 模型篡改。完成前 NI-026 的 Ubuntu 条件门仍是待验证项，
  本轮只声明 generation-host strict provenance。
- 对方向的意义：多站点 planner 需要在不同 checkout 表示下确认“运行的是同一协议”，
  同时对模型与二进制数据保持逐字节一致。拆分两个 root 能让跨站点共识更精确。

### NI-038：进程树资源取证必须容忍短命子进程竞态，但持续不可读仍须 fail closed

- 状态：`RUNTIME_VERIFIED`
- 失败证据：第一次真实 pilot R1 的 shard 0 在 3.79 秒内取得 63 次底层 RSS 样本，
  其中 62 次成功，峰值 209,559,552 bytes，远低于 17,179,869,184-byte cap；唯一一次
  `unavailable` 先触发 orchestrator 终止，随后才记录 `return_code=1`。因此该返回码是
  Windows `TerminateProcess` 路径的结果，不是 worker 自身先失败，也没有 RSS 超限证据。
- 根因：exact-build provenance 复核会为 inventory 文件启动大量极短寿命的
  `git rev-parse`/`git cat-file` 子进程。Toolhelp 先枚举进程树，再逐 PID 调用
  `GetProcessMemoryInfo`；子进程可在两步之间正常退出，旧实现却把“任一已枚举 child
  不可读”等同为整棵活进程树不可取证，并在同一瞬时样本上立即终止 worker。
- v2 反例：最多 3 次即时重采样先使真实 1-worker profile 的 4/4 shards 在约 955.6 秒内
  完成；但随后的 2-worker profile 中，shard 10 启动 0.644 秒后仍连续撞中 3 个短命
  child。该 shard 已有 6/9 次成功样本、峰值仅 52,609,024 bytes，却被正确按当时合同
  终止；其余 shards 1/4/7 均自然返回 0。故 bounded retry 是必要缓冲，但不能把正常
  child churn 与真正不可读的存活进程区分开，v2 profile 不能作为最终 campaign 证据。
- 最终修复：orchestrator profile 升为 v3。单次 Windows tree sample 显式先读 root；
  root 不可读立即失败。对初始快照中不可读的 child 只做一次完整二次枚举：若该 PID
  仍属于 root tree，则判存活 child 不可读；若已离树，则按正常退出从该时点样本剔除。
  `Process32NextW` 只有以 `ERROR_NO_MORE_FILES` 结束才算完整快照，其他截断错误均抛错，
  防止把枚举失败伪装成 child 已退出。外层仍保留 3 次、0 ms 逻辑重试，处理 root 退出
  窗口、snapshot/API 瞬态和仍存活 child 的临时读取失败；底层 attempt 全部计数，零次
  成功样本、超过 cap 或持续不可读仍 fail closed。producer 与独立 validator 对 v3 schema
  和重试合同对称校验。
- 量化证据：3 秒高频短命子进程实验中，单次采样 309 个逻辑周期有 54 次假不可读
  （17.48%）；最多 3 次即时重采样的 174 个逻辑周期为 0 次不可读，最多 5 次也为
  0/182，未显示额外收益，因此保留 3 次、0 ms；2-worker 反例则直接推动了 snapshot-aware
  child 分类。回归分别覆盖 vanished child、仍存活但不可读 child、不可读 root、二次枚举
  异常、transient recovery、persistent failure、零样本 fast-exit、cap exceeded 以及
  producer/independent contract 篡改；最终 G4IRSF15 聚焦回归 106/106 通过，另一次真实
  3 秒 child-churn 压测为 219/219 成功、0 unavailable。v1/v2 profiles 只作为负诊断
  证据；正式 pilot 必须
  在 v3 新提交的新 exact chain 上从头重跑，不能把旧 shard 改写成成功。
- 证据边界：该值是各采样时点“可见存活进程各自 lifetime peak working-set 之和”的最大值，
  对成功读取的成员偏保守，但不覆盖完全落在采样间隔内、读取前已经退出的 child；因此是
  操作系统观测式 RSS 取证，不是整个进程树生命周期的连续内核 hard limit。若未来要对
  不受信 worker 提供不可绕过的强制内存边界，应另行评估 Windows Job Object/Linux
  cgroup，并使用新 profile schema；这不是本轮可信 campaign 的阻断项。
- 对方向的意义：去中心化 worker 会并发启动本地校验、传输或辅助进程。监控面若把正常
  子进程 churn 误判为算法失败，规模越大假失败概率越高； bounded retry 把瞬态拓扑变化
  与持续不可取证分开，同时保留 fail-closed 资源边界，使多 worker/MAPF 风格执行证据
  能随节点数扩展而不被中心化监控竞态主导。

### NI-039：Git provenance 应批量复核，而不是为每个文件重复创建短命进程

- 状态：`PROPOSED`
- 发现：当前每个 fresh worker 都必须独立复核 exact manifest，这是正确的信任边界；
  但逐文件各运行一次 `rev-parse` 和 `cat-file` 同时增加启动时延、重复 Git 对象读取和
  NI-038 暴露的短命子进程 churn。简单跳过哈希或只信父进程结论会削弱 shard 的独立
  可审计性，不能作为优化。
- 候选改进：在单个 worker 内用一次 `git ls-tree -rz` 解析所有 path→object ID，再用
  单个 `git cat-file --batch` 流读取全部 blob；仍逐项重算 SHA-256/byte count 并与
  manifest 比较。若引入跨 shard 缓存，缓存必须绑定 generation HEAD、source path-set、
  repository root 和 validator schema，且每个 worker 在使用前验证不可变签名或内容根。
- 接纳门：batch 与当前逐项实现对 SHA-1/SHA-256 Git 仓库、CRLF/LF checkout、缺失 path、
  type 非 blob、换 object ID/blob/path/HEAD 以及并发 source drift 必须逐项等价 fail closed；
  再以 worker 启动时间、Git 子进程数和 RSS sampler retry 数证明实际收益。本轮先保留为
  后续优化，不在 pilot 前扩大 provenance 变更面。
- 对方向的意义：减少的是重复进程和重复对象访问，不是完整性证明。批量内容寻址更接近
  多站点去中心化节点交换 manifest/root 的方式，可让证据开销随文件集合线性流式增长，
  而不是被每文件进程启动成本与中心化验证抖动放大。

### NI-040：极端局部竞争是 I1 precondition false-positive 风险层，不是充分筛选器

- 状态：`EXPERIMENT_VERIFIED`
- 决策：唯一允许的 R2 screening revision 使用 outcome-free 局部字段
  `candidate_action_count >= 100`；阈值只由 R1 聚合诊断选择一次，在 R2 前冻结，不读取
  descriptor ID、单 target outcome 或因果 label，并保持 source、binary、census 与地址定义不变。
- R1 证据：该压力层包含 10/37 个 I1 precondition false positives，但也包含 3/27 个完成
  attempts；过滤后仍有 1,256 个非 R1 I1 replacement candidates，且不删除任何 I3/I4。
- R2 反证边界：完全不重叠的 64-target replacement panel 中，I1 仍只有 28 个 complete
  action-changing pairs，另有 36 个 `NOT_APPLICABLE_ACTION_PRECONDITION_FAILED`，未达到每
  kind 30 的门槛。R1 的 27/64 与 R2 的 28/64 不是随机 A/B，不能把一个 attempt 的差异
  解释为筛选收益。
- 结论：该字段可保留为 MAPF 风格 agent 可观察的 stress stratum，但不能替代原子动作
  提交协议；replacement round 已用尽，不得继续按 outcome 调阈值或静默删除失败地址。

### NI-041：I1 blocked 表示缺少可识别执行支持，不表示 source admission 无效

- 状态：`EXPERIMENT_VERIFIED`
- 证据：I1 在 R1 为 27/64，在唯一 R2 为 28/64；两轮未完成项全部是动作提交前的
  `NOT_APPLICABLE_ACTION_PRECONDITION_FAILED`，而非 treatment 执行后的有害结果。R2
  hard-gate fail 为 0、clone fidelity 为 1.0，但支持量仍低于冻结门槛。
- 决策：本轮将 I1 标记为 `INTERVENTION_KIND_BLOCKED`，formal 只激活 I3/I4；原 I1
  的 label 预算按预注册规则重分，使 I3/I4 各为 1,086 attempts、合计 2,172。
- 边界：formal 最终通过也只能支持冻结 frame 内 I3/I4 的 matched-state 结论，不得外推
  到 I1、全部 source admission 或完整去中心化调度器。当前证据说明“地址经常未形成已提交
  动作”，不能据此断言该动作若可提交时无效或有害。
- 后续候选：下一 source/version 研究 source-owner 维护的 generation-bound capability、
  lease 或原子 compare-and-commit，使地址解析与动作提交共享局部版本；必须重新 source
  freeze、exact build 与 pilot，不能热补当前 formal campaign。

### NI-042：H_bag-only replacement panel 可用大 shard 摊销固定 provenance 与进程成本

- 状态：`EXPERIMENT_VERIFIED`
- 发现：R2 仅有 64 个 I1/H_bag targets。使用 `shard_size=64` 后形成单 shard，733.965 秒
  完成，峰值 RSS 703,090,688 bytes，1/1 shard 成功且无资源或取证失败。
- 收益边界：若沿用 R1 的 `shard_size=16`，至少需要 4 个 fresh workers；单 shard 从拓扑
  上把 source identity、binary/build-manifest 复核、Python/pybind 启动与初始状态 replay
  的固定次数从至少 4 次降为 1 次。没有执行 size-16 counterfactual，因此不发布虚构的
  时间加速倍数。
- 完整性边界：优化未跳过 required hash。单 worker 仍独立完成 source、repository blob、
  binary、build manifest 与 result validation；减少的是重复进程和固定工作。H_system 仍受
  每 shard 4-target 内存门限制，本条不能外推为增大 formal dense shard。

### NI-043：formal 并发先做时间轴端点校准，再在同一资源合同下扩到 4 workers

- 状态：`EXPERIMENT_VERIFIED`
- 计划：formal 固定为 2,172 attempts（I3/I4 各 1,086），其中 H_bag 1,916、H_system
  256；64 个 contiguous event-ordinal shards，每 shard 最多 4 个 H_system。
- 端点校准：shard 0 与 63 以单 worker 完成，耗时 306.634/1,127.257 秒，process-group
  peak RSS 为 1,905,258,496/1,920,446,464 bytes，均无失败。两 shard target 数不同，
  耗时差不单独归因于 event ordinal；用途是覆盖早期/末期状态并校准 dense 内存量级。
- 扩并发：四个互斥 bulk profiles 覆盖 shards 1--16、17--32、33--48、49--62，均以
  4 workers `COMPLETE`；合计 62/62 成功、0 失败，最大 process-group peak 为
  5,805,199,360 bytes。六个 profile 的 shard 集合互斥且并集精确为 0--63。
- Finalizer：`PASS_CAUSAL_GATE`；2,172/2,172 预注册 pairs 全部成为 eligible
  action-changing labels，I3/I4 各 1,086，H_system complete/dense 为 256/256，action
  changed rate 与 clone fidelity 均为 1.0，hard/safety failures、future leakage、split
  contamination 均为 0。signed labels 为 beneficial 47、harmful 1,770、neutral 355。
- 独立验收：发布兼容入口完成全链验证并返回 `PASS_CAUSAL_GATE_VALID`；learning 只对
  I3/I4 授权。weighted-effect artifact 明确 `population_effect_identified=false`，聚合效应
  只描述完整 realized panel，不得写成总体平均因果效应。
- 运行建议：更大 campaign 继续采用“早/晚端点单 worker → 按实测峰值选择 bulk 并发”；
  当前只证明本机 4 workers 可承载，不证明任意主机、跨机器或网络分布式部署。

### NI-044：冻结后验证修复必须外置为窄兼容层，不能改写 source-bound validator

- 状态：`RUNTIME_VERIFIED`
- 第一个缺陷：formal plan 按合同记录 `pilot_round=null`，冻结 validator 却在选择 compact
  path 前执行 `int(null)`；formal namespace 实际完全忽略 round，payload 校验仍要求 null。
- 第二个缺陷：生成器以 `row_count=len(realized_rows)` 发布 realized sidecar，dense sidecar
  validator 也接受空列表；6 个 I4/H_system action-changing labels 合法得到零 realized/
  externality rows 与 typed empty hash `61090c80331138c49fbbfe5abbd96003ad002529606c7225b53df74d05c099d3`，
  但冻结 `validate_label` 孤立地要求 row_count 至少为 1。
- 决策：不修改 SHA-256 为 `7e43047065f1d9ec253f2ecf1f0c562af51e849e13749120d3df6516cfdf5615`
  的冻结 validator，也不重封 source bundle。新增 post-freeze release entry point，只对精确
  formal schema/campaign/null-round 与上述 6 条、独立重推导出的 I4 空集合标签做进程内
  兼容；原 plan/label 字节、self hash、payload-null 检查及其余 validator 逻辑均不改变，
  临时函数绑定通过 `finally` 恢复。
- 证据：兼容回归 10/10、全部 2,172 labels 快速验证、split/weighted post-collect preflight
  与最终完整独立验收均通过。完整命令、边界和结果记录于
  `outputs/reports/g4irsf15_formal_release_validation.md`。
- 后续：下一 campaign 把显式 formal/pilot 分支与合法 zero-cardinality 分支纳入新冻结
  validator，再从新 source identity 运行全链；不能把外置兼容层偷偷并入当前 source bundle。

### NI-045：局部代价与稀疏外部性应成为两个独立学习/协调目标

- 状态：`EXPERIMENT_VERIFIED`
- realized-panel 证据：direct-affected completion delta 总体为 +21.420 秒；I3 为
  +42.487 秒（clone-bootstrap 95% sensitivity interval [40.500, 44.474]），I4 仅
  +0.354 秒（[0.171, 0.498]）。I3 的额外成本同时表现为约 +5.260 hops、+35.960 秒
  edge travel 与 +2.259 秒 merge wait；I4 path/edge/node-service delta 为 0，更接近轻量
  局部 hold 协调原语。
- H_system 证据：256 pairs 的 direct-affected completion delta 为 +22.820 秒，但全
  43,603-segment cohort completion mean delta 仅约 +0.0000495 秒且区间跨零。与此同时
  144/256 pairs（56.25%）存在非空 externality set，平均 23.090 个 segments、最大 365；
  I3 平均 39.922，I4 平均 6.258。全 panel 的 deadline-miss delta 为 0。
- 结论：全系统均值接近零不能替代局部公平性或传播尾部审计。下一阶段的去中心化 MAPF
  学习器应把“本地动作代价”与“邻域外部性预算/尾部”作为两个目标：I3 与 I4 分开建模，
  本地 agent 可用 H_bag 快速决策，但高风险动作需要邻域 proof/credit 或稀疏 H_system
  审计触发；不应重新引入一个读取全局未来的中心化 supervisor。
- 边界：horizon assignment probability 未建模，HT/Hájek population estimates 被明确
  禁止；以上均值和区间只量化冻结 realized panel 的机制与敏感性，不能外推全部地址或负载。
