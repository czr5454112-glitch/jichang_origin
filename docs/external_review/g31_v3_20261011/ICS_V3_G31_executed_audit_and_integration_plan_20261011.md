# ICS V3 实跑复核、G31 整合与研究路线重排

日期：2026-10-11。本文是拿到用户上传的完整 ZIP 后形成的新版审查；与先前两份审查冲突处，以本文的证据层级和路线安排为准。旧报告、旧负结果、用户源码均不覆盖。

**V3 生产基线：** `defd79effe02ee13f1a5bbbbc5143f6d0dce2f63`。  
**上传的发布快照：** `fccd4819532701ee4173ec598822450d962d4e61`。  
**本轮实际定位的成熟 G31 参照：** `46cc46ab6bc121628fd6357e9f3c7636745fd732`，分支 `codex/g4irsf31-nanning-portability`。这不是对其他后续 G31/G32/G34 分支的自动授权或完整审查。

## 0. 执行结论

**需要对上一轮路线作实质修改：不能继续把 V3 建成另一套独立主系统，再把 G31 当作“以后接一个接口”的附属项。优先以成熟 G31 的事件驱动逐跳执行为部署基础，迁入 V3 的有限托盘循环、存储与释放、区域权限、预测预平衡和同模型强参考。两项需求、正常分拣保护与 TRE/CIE 量级研究目标保持。**

本轮同时有四种不同层级的结论：

| 结论 | 证据层级 | 不能扩大的含义 |
|---|---|---|
| 原 1519 项 V3 回归全部通过，211 份源码/测试前后不变 | 本环境真实执行 | 不等于整个仓库或 G31 原生测试全部通过，不等于业务/实时性/创新验收 |
| 新增三个定向问题已复现，其中旧整数参考可给出错误“最早到达”标记 | 本环境小例执行＋源码控制流 | 不能因此宣布历史 44 袋结果、所有 Storage 独审或 G31 结果无效 |
| 上传分支没有成熟 G31 的正式入口，V3 默认控制链不调用它 | ZIP 检索、122 个模块 AST 扫描、独立 G31 源码与分支比较 | 不把任意外部回调或未提供后续分支一并判定为不存在 |
| “循环释放感知的区域逐跳控制＋跨区预平衡＋受影响依赖修复”值得检验 | 新研究假设 | 尚未实现统一系统，尚未证明新颖、占优或满足全部服务合同 |

**当前创新状态应记为“待验证”，不是“已通过”，也不是“没有价值”。** 三层架构、局部信息、空车再平衡、终点腾位、用神经网络给下一跳打分，单独都不足以支撑新颖性。第 7 节给出近邻，第 8 节把创新审查变成进入下一阶段的必要条件。

---

## 1. 本轮实际取得、检查和运行了什么

### 1.1 上传包和源码身份

输入文件 `ICS_V3_full_repository_exact_fccd4819_20261011.zip`：84,897,661 字节，SHA256 为 `4f4973d8441bfb912e048ad2c483e4b058da85e29cb97c1df913da4c273def77`。实际枚举 4360 个文件，展开字节数 540,963,721；CRC、路径越界、重复路径与符号链接检查通过后解压。[E1]

包中没有 `.git`。文件夹名声明了 fccd481…，但不能只凭名字证明整个提交。另对发布清单中的 **122 个生产 Python＋89 个 Python 测试**，逐项重算工作字节 SHA256 和 Git blob SHA1，211 项均匹配冻结清单；清单 SHA256 为 `75c5282050cd45260310796185584cd8d3b9f61275ff6c382be8fbb8ba39ae9c`。[E2]

这证明相关 V3 源码/测试的绑定身份，不声称已从 `.git` 重建整仓历史或逐项对远端树复核 4360 个文件。此前 codeload 的 DNS 失败仍是历史事实，本轮通过聊天附件取得字节，不用本轮成功改写此前日志。

### 1.2 六份完整夹具与原回归

执行包内 `tools/prepare_fixtures.py`，恢复全部六份 JSON：cross_cycle、counterflow、near_full 的 original/cursor 两份，合计 **133,186,733 原始字节**，不是抽样夹具。[E3]

随后在解压目录运行原发布脚本：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python docs/ics_circulation_v3/review_20261011/tools/run_release_tests.py \
  --output /absolute/path/to/a/new/release_run
```

实际结果：**1519 passed，0 failed，0 errors，0 skipped；89 个测试文件；pytest exit=0；source_changed=[]。** 测试调用区间 process CPU 32.149810513 秒、wall 32.74657241899999 秒。[E4]

本环境为 Python 3.13.5、Linux、NumPy 2.3.5、pytest 9.0.2、Pygments 2.20.0，并关闭自动发现外部 pytest 插件、把 BLAS/OMP 线程设置为 1。没有为通过测试修改生产源码或删测试。作者的 Windows/Python3.11.9 环境与这里不同，**不能比较两次耗时后宣称算法加速**。此计时不是整轮审查总成本；测试内部物理调用数与子进程 CPU 未完整仪表化，保持未知。[E4–E5]

### 1.3 定向探针

新探针在原源码上执行，没有修复生产文件。最终可复现脚本为 `reproduce_audit_probes.py`，原始完整观测在 `evidence/probes/portable_run_001.json`。[E6]

```bash
python reproduce_audit_probes.py --root /path/to/jichang_origin --output fresh_probe.json
# Codex 修复后可用：
python reproduce_audit_probes.py --root /path/to/fixed_checkout --output fixed_probe.json --require-fixed
```

默认 exit=0 表示探针执行成功，**不表示生产没有缺陷**；`--require-fixed` 在三个目标缺陷仍被观测到时返回 1。最终探针本次用了两次显式 `Simulation.advance`，只推进小例，没有原业务回放或 G31 原生执行。最终调用区间 CPU 0.043090918 秒、wall 0.043322302 秒；不把此前诊断尝试和本次复核算成新的独立业务样本。

保留了第一次普通 K 探针未触发差异的输入：同一控制分区只有一个静态宏见证，不能检验四候选默认值；随后改成四条跨锚点路径再测试。旧 attempt_001 报告将显式 advance 次数误填 3，脚本实际为 2；最终脚本按调用递增计数并保留旧件，未将此元数据错误掩盖。

### 1.4 阅读边界

211 文件哈希检查、122 文件 AST 扫描、1519 项回归执行，不等于逐行审完所有源码。沿用此前已读 V3 控制流，本轮重点实际定位如下（V3 文件前缀为 `scripts/experiments/ics_circulation_v3/`）：

| 文件/范围 | 本轮用途 |
|---|---|
| `routing_reference.py` 74–111、246–306 | 状态合并、Storage 未拒绝、最早与穷尽标记 |
| `terminal_capacity_screen.py` 76–90、142–169 | 普通默认 K、可变工厂账本、安装路径 |
| `runtime.py` 423–480、761–775、934–948、1132–1170；运行探针对应运动/终点逻辑 | 保护后缀、生成器、检查点对象复制与物理占用 |
| `storage_terminal_screen.py` 69–73、160–193 | 已修默认 K、纯工厂、慢层安装限制 |
| `storage_routing.py`、`storage_contracts.py` 的相关生成与合法性入口 | 与旧整数参考区分；阶段义务 |
| `partition_observation.py::observe_partition` 53–82；`joint_reference.py::solve_joint` 233–331 | 显式拒绝边界，小例实际触发 |
| `tests/test_ics_v3_storage_search_audit.py` 114–162 | 独立 Storage oracle 已有 passed 状态，不能误判为 N1 对象 |
| 包内发布 runner、source manifest、fixture manifest | 真实执行与身份验证 |
| 最新 screen 格完整 `results.json` 的 44 行 task_rows | 补齐上次中段缺读并重算，不是重新执行世界 |

成熟 G31 的外部只读范围：[G1–G5] 中 `g4irsf31_map_adapter.py` 全文、`run_g4irsf28_service_potential.py` 1–230、`run_g4irsf31_nanning_map.py` 1–225、`event_driven_junction.hpp` 85–260。正式 reporting 曾请求 1–130，但响应截断，按部分报告处理，不据其重报整批性能已核验。未编译/运行成熟 G31，未展开其庞大 native header 的所有调度路径。

---

## 2. 新增确定问题：先小范围修复，不把修复本身当论文创新

### N1 / P0 / 正确性：旧整数参考在 Storage 状态上错误认证最早到达

**版本/调用链。** V3 `FullGraphReferenceGenerator._generate`（routing_reference.py 261–306）→ `EventTimeSearch.paths`（74–111）→ `_proposal` → `ExecutionValidator`。直接调用旧参考时未拒绝 Storage，而搜索合并键是 `(node,tick)`，不含必须经过的存储阶段。生成器见到第一个通过末端验证的候选，就设置 `earliest_arrival_certified=True`。

**真实反例。** 单盘、无其他占用，S、A、W、X、G 均可等待；W 为必须通过的 Storage，release=0。S→A、S→W、A→X、W→X、X→G 各耗时 1，另 W→G 耗时 4。H=6、K=1、work 上限 200000、无墙钟截断。S→A→X 与 S→W→X 均到达 X@2，但前者没经过 W，后者经过了 W。旧键会丢掉后者。

返回 `S→W→G`，到达 **5**、卸载 **6**，并标记最早已认证；独立手工见证 `S→W→X→G` 到达 **3**、卸载 **4**，原 validator 接受。搜索只用 30 个计数单位，不能归因于预算耗尽。移除 W→G 后，旧参考返回空而标记有限时域穷尽，手工可行见证仍在。K=2/3 在这个小例找到早路，**不代表增 K 是正确修复**。[E6]

**作用域。** 是直接旧 FullGraph 参考 API 的模型能力/证书错误；独立 `test_ics_v3_storage_search_audit.py::oracle` 已包含 `passed`。当前业务通过 StorageCandidateGenerator 的路径，以及禁止 Storage 的 solve_joint，不能被追溯断言受此错误影响。

**修复。** 立即在旧参考入口显式拒绝不支持的 Storage 模型，连同诊断证书适用域一起绑定。随后用真正的阶段积状态参考支持新模型；状态至少区分存储进出、接收/服务义务，接入头距后还须区分自身未过期进入历史。不能把不完备代表状态搜索更名成精确，也不能只把成功标志改 False 却继续被上游当 oracle 使用。

**验收。** 保留以上有短路、有长备选、无解、超预算、普通模型和多 K 反例；旧普通域结果不变；新域最优与独立完整状态参考一致，截断明确 unknown。必须检查所有消费 earliest/exhausted 标记的调用者。无需 GPU；先小图整数域，不能直接用大图穷举代替接口修复。

### N2 / P1 / API 兼容：普通筛查默认 K=4，而被包装器默认 K=3

**位置。** `TerminalScreenGenerator.generate`（terminal_capacity_screen.py 86）与 `RegionalCandidateGenerator.generate`（routing.py 249）；不是 StorageTerminalScreenGenerator——后者已修为 3。

**真实结果。** 四条可行宏路径的普通图，不显式传 K：原 generator 返回 3，普通 screen 返回 4。前 3 条对应，第四条来自错误默认值；筛查本应透明，却改变候选/标签和预算语义。[E6]

**修复。** 普通默认值同步为 3；显式 K 保留调用者值，普通/Storage/空盘包装分别回归。别通过减少原路径、强行固定所有调用 K=1、删默认 API 来掩盖兼容差异。

**验收。** 不只比首选，比较完整有序候选、状态、实际语义动作和冷/热缓存预算路径；无证书委托应与原调用一致。最新原实验显式 Storage K=1，不因此重新解释其结果。此修复为工程正确性，不是研究主贡献。

### N3 / P1 / 回放隔离：普通筛查工厂让已保存检查点的账本继续变化

**位置。** `TerminalScreenFactory`（142–147）持可变 `ScreenAccounting`；`Simulation.checkpoint`（1132–1139）深拷贝 generator，却直接保留 factory 引用。Storage 的纯工厂不能自动修复普通工厂。

**真实结果。** 保存 checkpoint 后，其 generator/factory 账本行数为 `(0,0)`；从原 engine 的 factory 创建 generator 并执行一次查询后，**保存的 checkpoint 变成 `(0,1)`**，恢复后的两份计数也是 `(0,1)`。检查点不是保存时的账本状态。[E6]

**作用域。** 已证账本隔离错误；没有证明本例物理轨迹被污染。既有把 `(wrapper,factory)` 整体 deepcopy 的测试与 `Simulation.checkpoint` 分别复制字段不是同一对象图，不能替代真实入口测试。

**修复。** 优先把普通 factory 改成配置-only 的纯工厂，每个新 generator 自有账本，显式汇集当次计量；或一次性复制完整相关对象图并证明别名关系正确。不要无差别 deepcopy 任意 callback 以为解决全部闭包状态。

**验收。** 真实 checkpoint→原引擎后续调用→恢复两个兄弟分支；fast/slow、新建 generator 与已有缓存均检查；不同分支的账本不交叉，原先要求累计的计量不能因隔离而漏记。失败、缓存预算和重复调用同样入账。

---

## 3. 对上一轮判断的保留、收紧与撤回

| 旧说法或易误解点 | 本轮准确结论 |
|---|---|
| 尚未取得可执行源码、1519 仅作者回执 | 更新：已取得上传字节、恢复完整夹具并亲自运行 1519；仍不是全仓/G31/全业务验证 |
| Storage 业务、观察、参考、screen 串成一条失败链 | 收紧：是并列能力缺口，不是实跑串行链；两个拒绝入口已用小例确认 |
| Storage 无法带慢控制器 | 撤回泛化。本轮 Storage 引擎带 no-op slow callback 实际推进并完成小例，slow_calls=6。只证明回调兼容，不等于真实预测控制已贯通；screen 安装仍拒绝 slow |
| 保护任务不允许后缀替换是实现 bug | 保持上次纠正：现行合同有意禁止，新需求须显式授权扩展。本例复现拒绝，未证明它导致 0/44 |
| 卸载就可删除终点占位 | 明确不允许。小例中卸载后 plan 被移除，空盘仍真实停在 G，effective_reservations 继续覆盖到 INFINITY |
| 有 backlog 的旧有限域成本最优不成立 | 不作此判断。旧成本问题可合法有 backlog；新的全任务服务可行性必须另建合同与参考，保留 WAIT/no-action |
| 再多跑 58 tick 就能证明业务解决 | 不成立。44 袋保存结果仍为 CPU 删失，预定卸载不是实际完成，首件完成也不是持续循环 |
| 后面再接 G31，先把独立 V3 做完 | 本轮重排：G31 整合变为近期主交付，防止继续积累不兼容的第二套主系统 |

完整保存结果 44 行已实际读取和重算：观察 44、完成 0、已装盘 11、停止时未完成且已过 deadline 为 0；实际 Storage 进 7、出 6；停止 19620；selection_calls=0、slow_calls=0、carrier_reuses=0。[E7] 这是对作者保存文件的复算，不是新部署结果。原输入长窗 18/44 的历史结果也必须保留，不能把全部格写成零完成。

0/44 的竞争解释仍需区分：计算删失、长 release、11 盘下的 FIFO 装载、持盘存储/库位、目的地投射集中、终点停车承诺，以及真正物理能力。N1–N3 的小例没有建立这些解释的因果排序。新的共同时间终点实验与因子对照应单独设计，不能借修复消去原负结果。

---

## 4. G31 与 V3：不是已经合起来，只缺一张架构图

### 4.1 版本分叉是实质问题

上传包里没有 `g4irsf31_map_adapter.py` 等 G31 正式入口。122 个 V3 生产模块的 AST 扫描没有发现指向 czr005/cpp/G31 的导入；默认物理宿主是 Python `runtime.Simulation`。上传的 native `event_driven_junction.hpp` blob 为 `04ac47c6f8842210cdebb4266c0f5fd0389d8ebf`，而固定 G31 文件为 `1a1ae6f326f03dc7d69622a05cdf0884b864a096`。[E8、G1–G4]

GitHub compare 返回两提交 **diverged**：以 G31 为 base，V3 head ahead_by=6、behind_by=44，共同祖先 `966a063573f0419df1324708db75211c521d59db`。[G0] 这是提交关系，不是 44 个算法缺失，也不应把 compare 提供的有限文件列表当全树逐项对照。

因此，不能把上传包内较早的 native 头文件当作已验证的成熟 G31；也不建议一条无检查的整分支 merge。应在独立整合工作区固定两条线，迁入必要代码与接口，并对同名功能/参数逐项识别。用户另有未提交 C++ 改动，不在本包，不能覆盖或假定已测。

### 4.2 成熟 G31 已有什么，必须保留

实际读取 G31 `build_s4_request` 可见：[G1]

```text
queue_discipline                  = fifo
scorer_mode                       = S4_queue_aware_rule_only
merge_grant_rule                   = M3
merge_grant_timing_mode            = jit_fair_aging_deadline
g4irsf20_event_hotpath_policy      = E2
g4irsf16_supervisor_mode           = off
local_queue_capacity              = 0
```

它构造服务感知静态势，并显式移除 `scorer_model_path`、`g4irsf24_dlp_artifact`。因此应将该 G31 配置看成**免训练 S4 逐跳选择＋即时合流仲裁＋事件执行及服务感知先验**，不能说已有 G31 的优良成绩来自尚未启用的 learning。

G28 的服务势已计算 `H(g,g)=0`、`H(u,g)=service(u)+min[travel(u,v)+H(v,g)]`；在线只为直接邻居读取标量，不物化完整未来路径。[G2] 重新写一次 reverse Dijkstra、再加节点服务，不是新贡献。PIBT 类保底只保留实际已验证、被授权的局部入口，不把包内另一个 PIBT 文件名或没有触发的模块当普遍无死锁证明。

### 4.3 不能直接拼接的语义

| 冲突 | 已见依据 | 统一系统应怎样处理 |
|---|---|---|
| 一次运输段 vs 长期托盘实体 | G31 bag_records 有 segment/task/release/start/goal；已读 EventRuntimeBagRequest 无 tray_id。V3 Bag/Tray 分离 | 独立 business_bag_id、transport_leg_id、tray_id、traversal_id；完成行李不删除盘 |
| G31 逐跳/JIT vs V3 全路线承诺 | G31 直接邻居接口；V3 原 validator/whole-route 资源预约 | 区分意图、预测、硬授权；不能先硬锁全路又让 G31 私自转弯 |
| 连续事件秒/毫秒 vs 整数 tick | G31 double time、最小服务 1e-3；V3 整数 travel | 定义单一 ClockSpec；兼容模式保留原事件顺序，研究离散化另列，不把 1ms 服务凑成 1s |
| 软件队列上限 0 vs 有限物理容量 | G31 adapter 声明 local_queue_capacity=0；EdgeRecord 无 V3 容量字段 | 0 是未额外限软件袋数的原合同，不是现场无限缓冲证据；分别建服务、边容盘、入口间隔、接收缓冲 |
| 早包多段记录 vs 真实进出库 | G31 段级入口与 V3 Storage 合同 | 第二段只有实际满足工序后才可执行；保留原段身份，不把未入库早包在预定时刻变成另一件任务 |
| 全局 Snapshot vs 区域自治 | V3 中央评分/搜索与分区 API 并存 | 物理环境可保全局，局部策略只获本地和已送达消息；接入 G31 不自动取得 OS 级隔离 |
| 两种“E2”/同名计数器 | 不同 lineage 的枚举、热路径标志 | 按源码语义和冻结配置识别，不按字符串相同判断功能相同 |

---

## 5. 建议的一套算法系统：保留 G31 的快速执行，补上循环后果

### 5.1 物理层只能有一个权威

**部署首选：成熟 G31 native 事件内核为唯一物理执行宿主。** V3 成为可复用的循环模型、控制/审查原型和离线参考；迁移其正确机制，而不是在同一部署时钟上再运行一个有独立托盘/队列的 Python 世界。

先做 read-only shadow bridge 可以，但 shadow 不得发实际资源承诺或把其未来轨迹当真实状态。Python 可用于慢层优化和离线参考，最终热路径避免每个节点都跨进程生成完整 JSON、复制全网、加载模型或重建历史。

新循环物理一定会改变旧开放式业务的行为，不能要求新合同所有结果与旧 G31 相等。应分成两个模式：

- `legacy_g31`：原合同、原配置、原段输入，输出/动作和原版桥接；用于保护已有成果。
- `circulation`：显式新业务物理与权限合同。所有新控制器和强基线使用同一合同，再比較算法增量；不得把物理模型变化产生的改善算作算法收益。

### 5.2 控制职责与信息流

**快速节点层。** 保留 S4 的直接邻居候选和原生服务/仲裁热路径。可选的新循环价值修正只改变已授权候选的排序，不直接写资源表。关掉修正后，排序退回相同物理合同下的 G31 基准。

**区域层。** 维护本地实际任务、资源日历、故障、边界消息和经授权的时间窗口。负责按需路由更新及与系统级 A* 编解码；发布路由/交接意图，不假装已经取得远端资源。中央 A* 的旧完整路线可作为参考/回退见证，意图版本和路段状态必须能往返编码；实际进入前缀不因重新编码被抹去。

**跨区慢层。** 基于载盘路线/阶段预测未来可用盘，选择调拨方向、数量、连接线和出发窗口。通过供应方固定区内模块的查询、导出、接收接口执行，不能用新中央调度取代区内空盘规则。

**硬授权与执行。** 同一资源只能有明确 owner；由本地 owner/JIT 资源路径复验并产生幂等回执，物理事件确认实际进入、卸载和释放。不同资源 owner 与物流区、控制区域不是同一个标签。离线参考可有全状态，但其更多信息必须单独标注，不能冒充同信息在线 baseline。

### 5.3 最小新增接口（设计名称，不声称现已实现）

```text
CarrierLedger
  tray_id, mode, node_or_edge, bag_id_or_none, available_at,
  storage_stage, actual_entry_ids, module_claims

RouteIntent
  request_id, bag_id, tray_id, authority_scope,
  irreversible_prefix, target_portal_or_goal, preferred_window,
  service_obligation_id, intention_version

ReleaseForecast
  tray_id, destination_zone, time_profile,
  status={conditional,committed_under_contract,physically_usable},
  dependencies, observation_time, producer, revision

LocalModulePort
  query_supply_envelope(...), request_export(...), request_reception(...),
  accepted_or_denied, permitted_window, observed_physical_completion

OwnerGrant / ExecutionReceipt
  request_id, attempt, owner, resource_intervals, traversal_ids,
  deadline_or_lease, immutable_prefix, accepted/rejected/unknown
```

`ReleaseForecast` 的概率/预测区间不自动等于确定上下界；只有经真实模块与授权合同证明的量才能作为保证。未来盘可以参与条件计划，但在实际卸载/hold/接收后才成为可执行库存。同一盘不能在多个未来分支被重复计成独立供给。

### 5.4 头距、存储与终点不能另起三套账

G31 原生已有服务与入边/合流机制，先查清并复用，不默认它与 V3 新头距合同等价。入口间隔 h 与整段容盘量 C 都要检查；同盘两次经过同边按 traversal 区分。已离边不代表 headway 尾窗到期，卸载也不消去旧进入记录。

检查点同时保存原生事件队列/同 tick 顺序、仲裁代际、未过期尾窗、固定模块响应、托盘与行李身份、区域请求、慢层相位、私有缓存和评估外生带；策略观察中不得出现私有未来。

终点泊位要靠实际离开或经确认模块接管释放。不能以 unload_complete 清空实体，也不能把 off-carrier 当数值开关：独立 EBS 库位、卸盘服务、取回与再次配盘必须有自己的真实事件。未确认现场结构时保留 on-carrier 基准与独立声明的 off-carrier 代理，两者不是同一算法消融。

### 5.5 保护服务与局部改路的张力

原 protected 不可改路合同保留用于历史复现。新合同允许的范围必须由 owner 明确给出：可改未进入后缀，但不得破坏实际不可撤前缀、存储义务、原 deadline 或其他任务的硬资源权利。

不能一边要求 G31 任意逐跳改路，一边只凭一次历史全路可行见证承诺所有后续都准时。对必须保证的任务，可由已授权走廊/时窗限定合法分支，并维护仍可执行的回退见证；尚不能证明的分支不获得硬许可。这样可能减少候选自由度，必须作为方法的计算—可行域代价测量，不能隐藏成“既完全自由又完全保证”。

正常分拣保护必须由合作方选定明确合同：已接纳义务的截止期、预留服务窗口、源端供应包络，或在共同外生带下逐件不增时的离线评价。对任意未知未来到达，非零预调与绝对逐件不增时不可能无条件同时保证：两个当前不可区分的未来，一个即将在供区需要最后一盘，另一个在受区需要盘，当前同一外调不能对两者都无代价。该不可区分性说明需要假设/拒绝机制，不是降低正常服务要求；不能事后换保护集合或让标量权重补偿硬违约。

---

## 6. 研究方法主线：不能仅“上层预测＋下层 G31”

### 6.1 首选研究对象

**研究假设 H1：在有限托盘与共享连接下，区域动作对后续供盘的影响应由“有时间的循环释放变化＋共享资源占用变化”描述，不能仅用固定终点价值；依据这种变化只修复必要的时间化依赖，可以在不接管原区内模块的前提下，取得更好的质量—计算折中。**

这是要被反例和强基线检验的假设，不是已发现的新定理。部署保持 G31 直接邻居选择；新增机制必须真实改变其合法动作，或在相同服务质量下显著降低必要在线计算。

### 6.2 先定义可被算法利用的耦合量

对当前局部可观察信息 `o_t` 和合法动作 a，构造短期、有限次循环的预测增量：

\[
\mathcal F(o_t,a)=\bigl(\Delta \widehat R_{z,\tau},\ \Delta \widehat O_{r,\tau},\ \Delta \widehat S_{b,\tau}\bigr).
\]

它们分别表示实际可用盘释放轮廓、共享资源占用轮廓和正常服务后果的预测变化。每个量标注条件/承诺/实际三种状态，输入只能是已公开信息与固定模块允许的响应；不能用真实未来解释标签再偷偷作为策略特征。

快速候选成本可写成：

\[
Q_{\mathrm{fast}}(o_t,a)=Q_{\mathrm{G31}}(o_t,a)+\widehat{\Delta V}_{\mathrm{circ}}(\mathcal F(o_t,a),o_t).
\]

这只是清晰的接口分解，不是新学习算法。如果简单地给同一行李的每条候选都加相同 `V(final_zone)`，常数会抵消，根本不能改变动作；必须检查到达/释放时刻、途经连接及受影响供需是否真的使候选不同。

慢层用有限盘的条件循环链而非无限新增流量，选择跨区调拨；本地请求改变释放轮廓时，反馈给慢层，慢层占用连接又反馈给节点/区域评分。无新到达预测时，已存在载盘的当前目的地和可观察路线仍可产生预测，这正是原需求二的重要信息源。

### 6.3 求解机制应当深入的一条线

建议深入 **“按时间化资源—供给依赖的局部修复”**，不是任意半径内重算：从动作改变的入边窗口、终点释放、源端保护与接收资源出发，沿共享容量、固定模块响应、队列回压、已有承诺和后续盘复用追踪受影响子问题。只有闭合依赖边界，才保留外部原承诺/原评价。

未闭合或超预算时必须扩大范围或返回 unknown/保留仍合法动作，最坏可以扩到全系统。不能提前声称更新代价与规模无关。早包库位、不可等待链、多 owner 消息和长线尾窗都是必须加入的跨边界依赖。

理论目标可选择：在显式确定性、消息新鲜度与依赖闭合条件下，局部修复保持外部承诺合法，且对声明的受限修复域不比全量同域修复少解；分析边界扩大和预算失败。**通用版本锁或“没变的变量不用重算”本身不算主理论**；需要特殊的循环依赖表示、修复算法与质量/计算证据共同支撑。

滚动参考可用约束优化＋已有可行解热启动；分解主问题的对偶只能在适用的连续松弛下解释。MILP 的启发式价格、有限差分或受限 master 值，不可直接当成原完整问题全局下界/对偶最优证书。

### 6.4 学习放在确有价值的位置

保留强时间化解析、线性/小树、paired-direct、residual，以及额外预算公开预测 rollout；不预设某个网络必须赢。可学习昂贵的循环边际评价或搜索优先级，不学习安全许可，不把固定 supplier 模块改成可训练动作。

学习前依次检验：合法动作覆盖→公开信息能否区分→共同未来标签稳定→真实 G31 继续策略匹配→拟合能力。小 K 内平局不能证全域无价值；oracle 差距小也不能自动宣布课题结束。反过来，动作、信息都充分且强解析稳定追平时，停止那个残差优越主张，把资源转到同等质量的修复/分解机制，而不是换弱基线制造学习收益。

迁入 G31 后，原 V3 候选、checkpoint、继续策略价值标签和模型验证不能直接晋级。原始业务源可复用，物理后果与标签必须重生成。共同随机数共享的是外生到达/故障，不是不同动作影响后的内生拥堵与释放。

---

## 7. 本轮近邻：哪些思想已经有人做过

本节是针对“G31 整合后能否成为新方法”的定向查新，不冒充重新核验此前全部 CASE、TAC、PPL、DG-PG 的全文/定理。未读到机制全文的近邻保留为待排查，不能按“不像标题”排除。

| 原始来源与本轮范围 | 已有机制，压缩描述 | 对本项目的约束与仍待证明差异 |
|---|---|---|
| [L1] Zeinaly 等，2015，TCST；作者报告15-019，模型假设及相关队列/控制段，PDF第5页图文核对 | 路由、线平衡与空车联合 MPC；连续车流近似，已有有限队列/EBS | 不能称 BHS 从未联合或没有容量；逐盘工序/所有权/在线修复的增量须另证 |
| [L2] Beojone 等，2024，TRC 104717；出版社§3及相关建模文字 | 上层宏观 MPC、中层车辆分配、下层节点覆盖控制；保留匹配模块的灵活性 | 三层架构和不重写全部旧模块都不是独占新点；需证明循环依赖修复的差别 |
| [L3] Gu 等，arXiv2608.30512v1，2026-08-31；§II-E、III、IV有关方法段 | 工业 OHT 的局部候选下一跳、共享小网络、轨迹初始化、在线 Double-Q与局部修正，安全机制外置 | 给 G31 加小网络/邻域拥堵特征不足以主张新；应强调新的可验证决策耦合机制，不以“机场”换场景抵扣 |
| [L4] Daszczuk 等，PRT 作者稿 arXiv1710.06331（稿内标2016期刊版），§1–3 | 有限车/泊位、预期到车、本地通信、预平衡以及为来车腾空泊位 | “预测有车要来”“满终点让空盘离开”也不是新思想；不能将物理正确性修复升格为首创 |
| [L5] Wollenstein-Betech 等，arXiv2003.04335，§II-A/B及讨论 | 流量模型联合路由与再平衡，显式考虑其对旅行时间的内生影响 | 内生拥堵/反馈本身已有；本题的个体阶段、离散授权与局部修复仍需实际方法区分 |
| [L6] Ahn & Park，IISE 2021，10.1080/24725854.2020.1851823；出版社/KAIST摘要，仅近邻定位 | 图表征＋去中心化 OHT 区域再平衡学习 | 未核全文，不能排除其覆盖拟议区域学习；不先上大型 MARL 与之重复 |
| [L7] Guo 等，TRB 2026，103411；出版社/机构摘要和方法概述 | 面向再平衡的 decision-focused predict-then-optimize | “预测服务优化”非新；本文没深核其全部求解/理论，不继承保证 |

[L2] 的交通近似会在部分建模中把 RHV 对总体交通的影响视作较小；我们的封闭输送网络不能未经验证照搬。但 [L5] 已直接研究内生影响，因此不能把对 [L2] 某假设的不同写成整个领域都没做过。

**创新结论。** 可以明确排除若干宽泛“首次”主张；还不能从当前原型确认拟议核心算法的新颖和有效。必须让真实代码与强对照说明：为何新的阶段化循环释放表示＋依赖修复，不只是现成 MPC/区域学习的改名。现场代理模型、求解机制、学习机制、工程接入四类贡献分开记。

---

## 8. 持续创新门：每到关键阶段都检查，不到投稿时才回头补

创新门不是增加哈希或每周写空报告。每个主要方法变更保留一页证据，说明已有工作、此次新增的实际决策、可反驳差异和实验结果。

| 门 | 进入条件与检查对象 | 通过所需证据 | 未通过时如何调整而不降整体目标 |
|---|---|---|---|
| I0：开发新主机制前 | G31/V3两版本与最近邻机制表 | 明确旧 G31 已有项、纯接入项、至少一个新求解假设；不是“三层＋MLP” | 重选耦合/修复对象，接入作为必要基础保留但不算创新完成 |
| I1：第一套统一闭环后 | 新机制是否产生真实动作差异 | 开/关机制、同输入同权限；正例与无收益/失败例；变化不是换物理或扩大候选预算 | 先诊断候选、信息与场景，不能先删区域或预平衡功能 |
| I2：大规模训练/实验前 | 相对强解析/一轮反馈/滚动参考的增量 | 质量—计算前沿、覆盖与排序损失、完整周期和服务代价；不是只胜旧弱贪婪 | 停掉无效残差主张，转可证实的分解/修复机制；工作量和强对照不降 |
| I3：W4冻结前 | 贡献↔实际代码↔独立确认设计 | 每个主张都有独立可证伪测试，主要差异不是信息/权限/模型不公平；检索新增近邻 | 修改贡献边界或方法，不把开发集重命名为新测试 |
| I4：写作/投稿前 | 结果、保证与文献是否仍一致 | 不主张未证实时性、无死锁或新颖；负结果与计算代价公开 | 收回不成立的局部主张，不包装旧工程成新理论 |

配套 `NOVELTY_LEDGER_20261011.md` 提供可直接更新的字段。当前所有拟议新方法主张均为 hypothesis/yellow；已有 G31 成绩可以保留为上一部分研究成果，但不能把同一贡献重复计算为本章新增。

---

## 9. 重排后的路线与首个实质交付

以下时间只是约 2–3 个月计划的工作块估计，不是完成承诺。源码维护、查新和理论反例可并行；首轮已完成的 1519 回归不要求 Codex 无意义重复许多次。

| 阶段 | 输入与实际实现 | 验证/交付 | 停止该方案的条件与替代 |
|---|---|---|---|
| A，开始约2–3工作日 | 定点修 N1–N3；固定 G31/V3两源；读取成熟native实际commit/取消/回放链 | 修后反例＋相关回归；legacy接口桥接清单；I0 | 缺能力先拒绝，不能伪造oracle；不要耗整周只做版本账 |
| B，约第1–2周 | G31宿主迁入永久tray身份、真实装卸/存储/返供、单时钟和模块port；建立legacy/circulation模式 | **同一托盘真实完成第一袋→卸载/hold→合法跨区返回→装第二袋**；对照原G31兼容路径 | 若native迁移局部困难，先做G31策略接到明确共享宿主的过渡版，但标不继承原native性能并给出迁移终点，不能永远双模拟器 |
| C，约第3–5周 | 区域观察/请求/A*编码、跨owner授权、headway与服务义务改路；同物理小域参考并行 | 故障、陈旧/丢回执、原已进入动作持续、no-wait链；I1 | 无法取得合法授权就拒绝/上报；不偷偷升级中央权限 |
| D，约第4–7周 | 有时间的循环释放＋跨区滚动分配＋反馈；受影响依赖修复 | 两需求分验与联合增量，强解析、一轮反馈、同信息约束参考；回到原图业务 | 若有限K平局先审覆盖；若全域可观测差距小，研究等质量更低计算，不借扩大/删减任务造差异 |
| E，约第7–9周 | 必要时训练小模型近似昂贵循环评价；G31继续策略下重采标签 | paired-direct/residual/解析，状态分组和标签稳定性；I2 | 无稳定计算/业务增量则停该学习主张，不删两个功能 |
| F，约第10–12周 | 冻结方案、W4新来源、统计分析与论文机制论证 | I3/I4；全任务/全请求、算力账、失效边界 | 新确认失败不回流调参后仍称确认；新版本需新确认来源 |

### 首个交付包，不可退化成“再写一份计划”

至少包括：两源版本固定；三个边界修复；G31-host 实际状态接口；一个真实有限盘重复服务闭环；一种接收满载拒绝、一种晚到消息、一个无收益对照；对应小域可行参考/明确unknown；同输入 legacy 桥接。可先关闭学习与screen，**不能关闭真实载盘预测后就宣称需求二完成**。第一个闭环只证明接入，之后必须扩展至原图完整业务与机制增量。

### 资源安排

按用户目前较保守资源“一台 RTX4070 电脑＋一台 RTX5080 服务器”安排，不默认有旧4090/5090。CPU核数、内存和4070形态未确认；主要负载是仿真、候选与参考，不是小网络训练。

先测代表性 branch 的 CPU、wall、峰值 RSS 和并行效率；并行数以实际核心与可用内存决定，避免两个进程各自把 BLAS/求解器线程开满。首个探索可从约200–500个真实决策状态入手，按小图oracle和2/8等共同未来逐步增加；这是预算起点，不是正式研究样本上限或独立运营日数。达到覆盖、方差与业务效应的辨别需要后再扩大。完整原业务不按这个状态采样数删任务。

缓存允许真实节省工作，但资源计量须区分冷/热、实际消耗与逻辑重放；从 V3 迁入 native 后不可继承 Python 标签预算或历史平均时延。

---

## 10. 统一系统的正式验证，不把旧 G31 成绩抹掉

### 10.1 两条基准轨道

**轨道 H：历史机制复现。** 保留原 G31、HCA、CIE-DH 等各自可信版本和物理/释放口径；完整读到并运行才记复现通过。HCA 原生结果不能被新执行器替换后仍叫 paper-faithful native HCA。没有得到新来源前，不在本报告重报其全部性能已确认。

**轨道 C：新循环物理的算法比较。** 共同的固定模块、有限盘、存储/接收、headway、控制信息和失败分母，比较：

| 基线/方法 | 作用 |
|---|---|
| G31-circulation＋合理反应式空盘 | 隔离迁入物理的影响，保留强逐跳基准 |
| ＋当前最强同权限解析预测预平衡 | 不用刻意弱贪婪放大学习收益 |
| ＋单向释放预测/固定调拨反馈 | 测是否只是多了预测信息 |
| ＋一轮真实反馈 | 已有强机制，不假装没有做过 |
| 同信息滚动约束优化/小域精确解 | 检验新求解机制，报告incumbent/bound/gap/unknown |
| 新依赖修复＋循环反馈，无学习 | 核心求解机制增量 |
| 同机制＋小模型 | 学习的独立业务或计算增量 |

必要动作（WAIT、同区模块可用服务、合法原子入场）与基础权限公平提供；方法独有的依赖修复/学习核心不免费赠予基线后又说完全一样。不同权限的中央同区主动派发另列，不能接管原固定模块后叫公平消融。

### 10.2 两需求分别验收

需求1：没有跨区预平衡需求、关闭学习时，区域更新仍可执行。统计新路线成功、仍合法旧路线、已接纳后缀更新、搜索耗尽、证实不可行、通信失败、提交失败、unknown；原路线已被故障破坏时不能计有效回退。

需求2：固定同一载盘路由策略，比较载盘目的地/路线驱动的预测预平衡；量化真实空盘可用、缺盘等待、接收回压、长线在途和多次复用。区内模块相同，不以另一模块替换带来收益。

联合：显示区域决策改变未来可用盘、预平衡反馈又改变合法逐跳选择/连接使用；如果只是并排运行而没有相互影响，记系统接入，不记联合方法增量。

### 10.3 全任务、实时性与统计

预先固定原任务分母、正常服务合同、主要终点、模型选择和统计单位。正式主要终点应兼顾完成/准时/积压，不能只在已完成子集计算均值；无法完成或预算删失不给虚假完成时间。计算删失与物理不可行区分，报告尾部、未到达任务、终点持盘和在途义务。

单任务更新计算仍要求≤100ms；分解排队、传输、观察、候选生成、特征/评分、owner复验、提交与回执。所有请求在分母，冷/热缓存、并发/突发和失败请求都纳入；小模型单次推理或平均值不能代替完整路由更新。

原图拓扑不随意加边/改方向。2km/5km连通线是明确研究参数档，按原许可位置调整；盘量、容量、headway、卸载/库位资料未知时做单独代理敏感性，不冒充实测。必须有预测反转、长连接多线、满缓冲回压、连续盘复用、盘充足/无共享瓶颈等无收益场景。

同源2×、多个种子、多个checkpoint或随机未来，不自动增加独立机场日。真实独立来源不足时，可以预先保留未参与开发的合成情景族作确认，但只能称合成确认。来源/父航班家族和同一业务日的各变体隔离；重采训练源是开发操作，不改名为test。配对统计以独立来源/情景单元为主，先导估计方差再定样本量；置信区间、效应量、最差服务和预算失败共同报告，不把大量相关逐袋记录当大量独立样本。

---

## 11. 仍缺的资料与不应继续投入的事情

### 11.1 不用再补这份 V3 完整 ZIP

该包已取得并成功测试。但 **成熟 G31 的完整固定源码/相应 native 构建和运行资产**不在该分支快照中；本轮通过 GitHub 读到了必要入口，未下载并运行其完整版本。Codex 进入整合时应取得选定 G31 提交及实际原实验入口，后续成熟分支需先换成新的明确冻结对象。

44 袋保存结果齐全不等于可恢复世界。库存索引中的以下原件仍未在本包取得（共同前缀 `phase4_round11_validation_20261011/projected_h21600_screen_001/`）：

| 文件 | 索引声明字节数 | 用途 |
|---|---:|---|
| `environment_tape.json` | 15080 | 原私有外生带，仅环境使用 |
| `initial_snapshot.json` | 71856 | 精确业务初态 |
| `final_checkpoint.pickle` | 547869 | 指定原 continuation 恢复；可信源核验后才可反序列化 |
| `final_result.json.gz` | 61605 | 最终完整物理/轨迹比对 |
| `full_window_source_tasks.json` | 44110 | 原业务来源与全部44袋 |
| `screen_cert_states.jsonl.gz` | 230206006 | 18,317份证书全状态复算 |

完整原图业务 raw/canonical/父航班来源、真实模块权限、存储类型、节点缓冲/边容盘/headway/服务、初始盘量与分区 owner，仍按各用途取得。供应方权限必须由合作方确认才可称现场；结构性算法研究可以在清楚标注代理下前进，不必全部停等实测。

### 11.2 停止无效投入，保留高标准

不要继续把“增加筛查数、继续扩K、延长时间、补回归、调旧MLP”当完整研究主线；不要为了合流覆盖成熟 G31、已有负结果和用户工作区；不要将本轮三个 bug 的修复包装成论文创新。相反，持续推进同一宿主下的真实循环、区域控制和跨区预平衡，带着强对照与可证伪的方法差异工作。

**最终目标不是两份代码互相 import，而是：G31 的快速逐跳执行在新的有限托盘业务中保留下来，新增循环预测与区域协调确实改变决策，并能说明为何比已有联合/分层方法更适合本题、在哪些条件下更好、在哪些条件下无收益或失败。**

---

## 附录 A：证据与来源定位

### 本轮实际运行记录（本报告同包内的相对路径）

- [E1] `evidence/archive_receipt.json`。
- [E2] `evidence/source_identity_before.json`、`evidence/source_identity_after.json`。
- [E3] `evidence/fixture_restoration.json`、`evidence/pre_run_verified.json`。
- [E4] `evidence/release_run_001/results.json`、`junit.xml`、`runner.py`、`source_before.json`、`source_after.json`、`evidence/release_run_001.stdout.log`。
- [E5] `evidence/environment.json`。
- [E6] `evidence/probes/portable_run_001.json`、对应stdout/exitcode；开发探针、首次不足输入与更强反例分别保留。
- [E7] `evidence/latest44_saved_rows_recomputed.json`；其原结果路径及SHA已列入该文件。
- [E8] `evidence/g31_integration_inventory.json`、`evidence/github_comparison_metadata.json`（工具响应关键字段的摘录，不冒充完整原始HTTP响应）。

### G31 固定源码（GitHub只读，不是本环境native执行）

- [G0] `https://api.github.com/repos/czr5454112-glitch/jichang_origin/compare/46cc46ab6bc121628fd6357e9f3c7636745fd732...fccd4819532701ee4173ec598822450d962d4e61`，提交关系元数据；未按有限文件列表宣称全部diff已读。
- [G1] `https://github.com/czr5454112-glitch/jichang_origin/blob/46cc46ab6bc121628fd6357e9f3c7636745fd732/scripts/eval/g4irsf31_map_adapter.py`，全文，重点build_s4_request。
- [G2] 同提交 `scripts/eval/run_g4irsf28_service_potential.py`，1–230。
- [G3] 同提交 `scripts/eval/run_g4irsf31_nanning_map.py`，1–225。
- [G4] 同提交 `cpp/ics_core/runtime/event_driven_junction.hpp`，85–260。
- [G5] 同提交分支的 `outputs/reports/g4irsf31_reporting.md`，部分/响应截断，不据此宣称全部结果复算。

### 本轮定向查新原件

- [L1] Zeinaly, De Schutter, Hellendoorn. *An Integrated Model Predictive Scheme for Baggage-Handling Systems: Routing, Line Balancing, and Empty-Cart Management*. TCST, 2015. DOI `10.1109/TCST.2014.2363135`。作者稿 `https://www.bartdeschutter.org/publications/15-019-integrated-model-predictive-scheme/15-019-integrated-model-predictive-scheme.pdf`。
- [L2] Beojone, Zhu, Sirmatel, Geroliminis. *A hierarchical control framework for vehicle repositioning in ride-hailing systems*. TRC 168, 104717, 2024. DOI `10.1016/j.trc.2024.104717`。出版社 `https://www.sciencedirect.com/science/article/pii/S0968090X24002389`；使用出版社正文检索返回，不以作者主页的误链DOI代替正式条目。
- [L3] Gu, Zhao, Liu, Lin, Shen. *Trajectory-Initialized Neural Double Q-Routing for Large-Scale Overhead Hoist Transport Systems*. `https://arxiv.org/html/2608.30512v1`。预印本，不按正式录用论文表述。
- [L4] Daszczuk, Mieścicki, Grabski. *Distributed Algorithm for Empty Vehicles Management in Personal Rapid Transit (PRT) network*. 作者稿 `https://arxiv.org/pdf/1710.06331`；稿内 DOI `10.1002/atr.1365`，本轮读§1–3，不复现其仿真或参数搜索。
- [L5] Wollenstein-Betech 等. *Congestion-aware Routing and Rebalancing of Autonomous Mobility-on-Demand Systems in Mixed Traffic*. 作者稿 `https://arxiv.org/pdf/2003.04335`，本轮读模型/联合目标与讨论，不按另一扩展正式版页码引用。
- [L6] Ahn & Park. *Cooperative zone-based rebalancing of idle overhead hoist transportations using multi-agent reinforcement learning with graph representation learning*. IISE Transactions 53(10), 1140–1156, 2021. DOI `10.1080/24725854.2020.1851823`。本轮只取得出版社/KAIST摘要，方法全文仍需后续排查。
- [L7] Guo 等. *A smart predict-then-optimize framework for vehicle rebalancing problem*. TRB206,103411,2026. DOI `10.1016/j.trb.2026.103411`。出版社与HKUST机构条目，未深核26页全部方法/证明。

**访问/执行小失败边界。** session模式工具启动失败不是测试失败；一次GitHub带编码斜杠的分支URL被拒绝，改用git/ref入口后成功；个别出版社网页直接打开cache miss，后用正式DOI/出版社检索正文定位。一个普通screen测试名检索少写了`circulation`导致文件不存在，随后定位了正确文件。这些不作为仓库逻辑缺陷；上述三项缺陷另有可执行独立反例支持。
