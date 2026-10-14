# Round11：显式存储终点容量筛查

2026-10-11。四个基线窗口全部封存、root 明确解除本次新增模块/测试的 freeze 后实施。保留旧文件和默认工厂；只新增 `scripts/experiments/ics_circulation_v3/storage_terminal_screen.py` 与作者测试 `tests/test_ics_v3_storage_terminal_screen.py`。未提交/推送，未扩容量、删任务或放宽 witness。

## 1. 解决的具体问题

[诊断与证明](../phase4_round11_projection_query_diagnosis_20261011/DIAGNOSIS.md)已保存原 projected_h21600 checkpoint10800：两袋 projected:1x:7、:10 的最终 node47 被四个其他盘的完整路线驻留占满。原 K1/h21600/work10000 查询各耗尽 10000，唯一完整候选均因 node47 容量拒绝。

每个存储完整 witness 仍终止于不变 final destination，并预约 `[final_arrival,INFINITY)`；final_arrival 不晚于 now+horizon。所以在公共子区间 `[now+horizon,INFINITY)` 发现其他盘已满容量，足以排除此查询域全部完整 witness。中途 waypoint/release、有限库位、零驻留经过均不改变这个后缀必要条件。证书只描述当前公开日历；未来其他盘被调走后必须重新判定，不能宣称任务永久不可行。

## 2. 新 API 与隔离规则

`StorageTerminalScreenGenerator(inner, accounting=None, *, max_records=200000)` 继承 `StorageCandidateGenerator`，inner 必须是 exact 原 StorageCandidateGenerator，内层 delegate 必须是 exact Regional、isolated_replay_v1、deadline_ms=None。它保存完整 inner，并让 generator 属性别名指向同一 Regional/cache；deepcopy 保留真实缓存和别名关系。新类身份使 `Simulation._make_generator` 不会再在其外面加一层 storage 而绕过 screen。

普通 bag、empty、storage 均使用同一完整终点必要条件。查询先保留原请求和 storage 合法性边界：invalid request、未发布/非法 contract、无真实 ingress、错误 progress、未到达 bag 等交回 inner，保留原诊断。证书未知或 record cap 不足时也原样 delegate。只有完成充分证书时返回空候选及 `terminal_capacity_certificate`；不预热 cache。每次 query 再验证 cache/deadline/alias，不能构造后篡改绕过确定性合同。

`StorageTerminalScreenFactory(inner_factory, max_records=200000)` 是冻结纯工厂，接受 exact ReplayRegionalFactory 或 BusinessGeneratorFactory，每次生成 `Regional → Storage → Screen`。它不持有 mutable accounting，避免原 `Simulation.checkpoint` 不 deepcopy factory 所造成的兄弟分支串账；每个新 generator 有自己的 ledger。

`install_storage_terminal_screen(engine, *, max_records=200000)` 只接受已知中央 storage Simulation、上面已知 generator/factory，拒绝任意未知 wrapper、重复安装、slow controller。W2/slow 并未因这个优化获得支持。安装一次返回当前 generator 的 ScreenAccounting。业务 runner 可逐 query 将 rows 写流后清空 rows，累计 screen_work/screen_cpu/observation_cpu 不清；恢复则从恢复后的 generator 取得自己的账本。

复用既有 `terminal_capacity_certificate` 和 `TerminalScreenGenerator._record` 账本方法，没有伪装类型以绕过原 wrapper 的支持检查。旧 TerminalScreenGenerator 仍保持普通 Regional 的原明确支持域。

## 3. 预算和证据声明

本实现与旧 `TerminalScreenGenerator` 一样，**原 inner 搜索预算保持 10000，screen_work/CPU 另外明确计量**，不是相同总工作量 10000 的比较。certificate 扫描、effective slots、事件插入/访问列在 screen ledger；观察快照哈希 CPU 另列；最终 query/parent CPU 包含全部实际工作。screen budget 的 record cap 只会导致 unknown + delegate，不会因预算中断虚构证书。

如果下一步要求一个共享总 work 上限，需另实现可中断的 certificate consume 协议并验证边界；不能把本实现的额外筛查偷偷排除后宣称严格等总预算。整个窗口仍由 root 按同物理 CPU/wall 限额评估。

## 4. 作者验证与真实失败查询对照

[authoring_001/result.json](authoring_001/result.json)：23 项全部通过，CPU1.156250s、wall1.206858s，0 physics。40 个外层 generator 入口尝试含 invalid 请求，计数 instrumentation 不重复内层 delegate；这是验证计数，非 40 条现场任务。

覆盖存储/普通/empty 的满终点证书、不认证/record cap 时与原候选和 cache 精确等价、storage 错误诊断、checkpoint/兄弟分支/新工厂 accounting 隔离、rows 流式清空保留累计、运行时 deadline/cache/alias 篡改和不支持的安装入口。计数插桩开销包含在作者总 CPU，不用这组 CPU 宣称算法加速。

[comparison_001/result.json](comparison_001/result.json)直接使用已封存原 checkpoint10800，SHA `dc7dfa5a51ba9b28826ef95ea02a59d7aba622c2dd9901cea9b4cd0b6c42d02b`，保留原 cache，真实默认 K1、h21600、inner work10000。旧未筛查查询引用诊断原件，不在本 receipt 重跑或重复计费。所有既有生产文件 SHA 与原诊断一致。

| bag | 旧查询结果 / CPU s | 新查询结果 / CPU s | 新 search work / screen work |
|---|---|---|---|
| projected:1x:7 | 预算耗尽、空 / .156250 | 终点容量证书、空 / .015625 | 0 / 332 |
| projected:1x:10 | 预算耗尽、空 / .187500 | 终点容量证书、空 / .015625 | 0 / 332 |

新旧候选结果一致，public state 和 private cache 不变。新 CPU 包含快照观察和筛查，并不是零计算；它是同一保存查询上的改善，不是完整业务吞吐量或现场 100ms 验收。新 receipt CPU .437500s、wall .480116s，2 queries、0 physics；包含 source snapshot、读取、SHA、imports、恢复、query、state/cache检查和序列化，嵌套 query/screen CPU 不再相加。

## 5. 独审发现的默认 K 缺口及修复

独审 [attempt_004](../phase4_round11_independent_review_20261011/attempt_004) 保存了真实失败：新 wrapper 初版沿用普通 Screen 的默认 K=4，但 StorageCandidateGenerator 默认 K=3，无显式 K 的四条合法路径调用会改变候选数量。修复仅将新模块 generate 默认值改成 3；业务运行显式 K1，故原 comparison_001 不受影响，不为这次接口修复重复跑它。

作者补充四路径默认调用的完整候选 tuple/工作量/K 账本桥接。[authoring_002/result.json](authoring_002/result.json) 24/24 通过，CPU1.109375s、wall1.229258s，42 外层 query 入口尝试、0 physics；修前 authoring_001 原件保持，不能把原未覆盖的默认 K 错误说成初版已验证。

当前新模块 SHA 为 `1102bc17b60c9bc3bd4829a055bb3569d24bdbe0849a4cd99daf4c6ec9744b05`，作者测试 SHA 为 `f2a92e53b28365328fdae33dd0db109241d92ade433a46dec0b9f9a4df0a7937`。三项本目录主 receipts 合计已计量 CPU **2.703125s**、84 个外层 query 入口尝试、0 physics；作者重复回归不是新增业务场景。独审资源由独审 base 另计，不加进此小计。

独审 [attempt_005](../phase4_round11_independent_review_20261011/attempt_005) 已完成：96/96 通过，包括 67 个整数证书 oracle 及半开边界、多容量、重复 owner、old-in-flight、零驻留与默认 K 完整 tuple；CPU1.421875s、2 个 tiny 物理运行、源码无漂移。这部分由独审账单独计量，不重复纳入上述本目录 2.703125s。

未计量辅助工作包括源码阅读、实现/测试编辑、工具编排。新模块、作者和独审 tests 已通知 root 冻结；后续全回归及额外 screen 业务部署由 root 执行，本文件不把尚未完成的部署写成已通过。
