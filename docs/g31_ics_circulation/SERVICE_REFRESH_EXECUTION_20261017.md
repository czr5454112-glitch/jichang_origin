# G31 服务预测刷新：实施结果与证据

日期：2026-10-17。基线提交 `da8d39ed4e36b6db31e3a7a6b17b0f73b85eed9a`，工作分支 `codex/g31-ics-v3-circulation`。这是未提交的工作区源码快照；本轮没有 commit 或 push。

**本轮完成：静态目录复制的小步优化；一次默认原生回归；同一原生 episode、同一 owner 的两次真实成功观察；供独立复核的源码与证据。完整 100ms、跨事件预测缓存、局部后缀修复、有效多动作后续学习仍未完成。**

用户重新提供的两份附件与仓库上一阶段原文逐字节相同，没有新的 Pro 批注：`SERVICE_UPDATE_STAGE_20261017.md` SHA-256 `d95b3879b423e9cae5a79780fcc19adb1919983cec0f5e8a1f1932e91513ae82`；`SERVICE_REFRESH_LITERATURE_20261017.md` SHA-256 `552447be0b5b0140eecf00ffab27aeff268ee28f9c00512acb62a854b1fb9bde`。本轮按用户“据此执行”的请求实施其中下一道验证门，不把文档建议当作已经成立的实验结论。

## 1. 不变的总目标与验收边界

最终目标仍是区域去中心化、有限托盘的 ICS：当前载货服务影响托盘释放，释放预测支持提前返空和下一次装载。保留 FIFO、headway、容量、接收权限、不可撤命令及同一实体盘的多次复用。保护参照仍是原 initial04 的逐件完成向量，零容忍，不能用当前较差预测替换原参照。

没有改拓扑、盘数、负载、服务时长、tick 或原生物理内核；没有向 actor 暴露隐藏未来或即时全局状态；没有增加超时预算。新增双观察是显式 opt-in 研究探针，默认策略没有增加一次采集。预测仍是条件性推演，不是未来事实或资源承诺。

文献适用边界沿用已核原文的 [文献映射](SERVICE_REFRESH_LITERATURE_20261017.md)：可以区分轻量监测与触发求解，但在本项目没有有效性界或外部边界证书前，不能由“短时间内没有业务变化”推导旧预测可直接执行。没有复制论文的秒数或非零误差阈值来放松本项目保护。

## 2. 剩余耗时：测量与最小修改

新入口的离线 profiling 仅用上轮默认原生 A/B 合法 evidence。每个状态一次无插桩调用、一次 cProfile 调用，四次完整 seed/双候选均与保存原件严格一致。Windows Job 2.859s / 60s，来源未变。

无插桩 A/B 为 150.389/182.011ms，样本各一，不是分布。插桩下 31 次完整静态目录 deepcopy 累计约 187.84/185.78ms，全部 deepcopy 约 323.15/366.78ms；严格编码约 89.90/139.65ms；事件循环约 18.14/14.85ms。累计项存在包含关系，不能相加；cProfile 时间不能替代运行延迟。当前公开物理 bundle 只有约 11–12KB，而 evidence/seed 已达约 74–132KB。

仅在新 `foundation_request_context` 的静态目录读取处使用 `foundation_catalog_copy.isolated_copy`：

- 支持精确 builtin dict/list/tuple 和标量；保留值类型、signed zero、容器 alias 与含 tuple 的间接循环语义。
- 每次读取仍给隔离副本；不允许共享可变对象污染下一次读取或另一候选。
- 自定义类型与复制钩子拒绝，不把外部 evidence 交给该内部优化器。
- 全部动态 evidence deepcopy、严格 JSON 校验、两轮动态 guard、候选前后 seed 篡改检查、来源 pin 保留。
- 新模块顶层导入并纳入请求 pin；不重犯上一轮延迟导入漏 native 源归档问题。

因此本轮只是同一请求的静态复制优化，不是跨事件缓存，也不是已经减少预测次数。

## 3. 与“上一轮已优化方法”的增量 ABBA

旧 `foundation_request_context.py` 和 `foundation_later_seed.py` 在修改前按字节归档；ABBA 从其真实归档构造私有模块，不覆盖全局或 sys.modules，不把新实现伪装为旧对照。旧模块路径和 SHA 在每份旧结果中核对。比较对象不再是最慢的原 legacy，而是上一轮 request_shared。

三个已保存实际状态，各两轮 ABBA，24 份双候选报告、48 个完整候选预测全部严格一致；每种方法每状态 4 次。计时包括 evidence/output JSON 脱离、evaluate 的来源检查与全部计算，不含 native 采集、actor、提交、ACK、导入、落盘。

| 当前状态 | 上轮共享中位数 ms | 本轮复制中位数 ms | 前者/后者 |
|---|---:|---:|---:|
| 默认 A 7.34s | 171.017 | 156.448 | 1.093 |
| 默认 B 9.69s | 229.072 | 199.945 | 1.146 |
| 延迟返空分支 B 10.22s | 220.853 | 203.404 | 1.086 |

硬限 60s，实际进程 9.156s。只能称本机单机制域这些样本的温和增量改善，不能把上轮 3.90–4.91 倍再当成本轮收益；没有 p95/p99、峰值内存、机场规模或总 episode 同倍加速结论。

## 4. 默认真实原生与连续计时

`native_001` 实际完成 52.390s / 150s。不导入模型或执行器的独立脚本完成 **327 项核对**：全部 153 条 receipts、5 件业务、3 个盘、calls/outbox/创建记录、切点 evidence/seed/完整预测、原参考、非计时 transition 与上轮最终默认原件一致。两个 actor 窗口状态和物理时钟未改变。

| 当前切点 | 原生读取与原 guard ms | evidence/actor 数据组装 ms | 模型与候选 guard ms | 采集至 offer ms | 采集至决策记录 ms |
|---|---:|---:|---:|---:|---:|
| A 7.34s | 91.745 | 26.052 | 168.963 | 286.763 | 309.379 |
| B 9.69s | 98.027 | 31.704 | 185.225 | 314.959 | 352.694 |

前两段连续且不重叠；前三段包含在采集至 offer 中，不能把所有列相加。采集至决策记录另含 actor/wrapper/提交；仍排除更早的真实消息采集、启动、返回序列化和后续 ACK。这个较窄窗口已经超过 100ms，**完整请求目标明确未达到**。实际瓶颈仍是模型验证/大 evidence 处理，以及当前原生采集与 guard，不是毫秒级 actor 本身。

原生单次之间的时间差不是配对性能实验，因果加速结论仅限第 3 节 ABBA 范围。初始 full32 未在本轮优化，不能以 later 改进代表所有决策都满足要求。

## 5. 首次同 owner、同 episode 两次成功当前观察

`freshpair_001` 是单独预登记 opt-in 原生探针，54.187s / 150s：

1. B 在真实 9.689999999999994s 得到第一份合法 offer，只保存完整观察、候选和预测，不执行，不增加 transition。
2. 在原实际 admission 内发新的 publication，复用原有消息、capture、peer 回复、接收与 current guard；不把成功伪装成失败重试，不改命令身份，也不手工推进一个参数冒充新观察。
3. B 在真实 9.729999999999993s 得到第二份合法 offer，双方 publication sequence 都由 6 增至 7。自身捕获 9.66→9.70s，对方捕获 9.68→9.72s；服务边界仍约 9.75s。
4. 只有第二份 B offer 交给 actor 并实际选择 `native_default`；该动作不发路线命令，不制造 ACK。整个 episode 仍只有原两次 later 业务选择。

两次 B 的 default 都通过原逐件门，prefer8 都被拒绝。五件实际完成时间全部与默认一致；140 条保守物理及命令结果记录逐字段相同，包含 LEG、等待/唤醒、模块请求、transfer 结果及 route ACK，不只比较 18 次入边。额外 publication 的通信 ACK 不同，因此不能声称全部协议轨迹等同。

两次观察相隔约 0.04s 是 `offline_sync` 的仿真事件时间；宿主计算期间原生时钟不推进。探针的 `native_physics_paused=false` 仅指没有额外冻结物理或修改 tick，不证明真实在线系统能在 40ms 内完成消息往返、采集和预测。

原生结束后才运行只读 refresh_audit，episode 以原 raw SHA 关联，仍保留“caller-supplied 身份不是原生 capability”的限制。结果为 `full_refresh_required`：新时刻、旧 source freshness 过界以及 source/ACK/outbox/collection 等依赖变化。全 5 jobs、3 trays、11 nodes、14 edges 保持在影响域，没有复用任何后缀。服务稳定性记录变化不等于这 0.04s 内发生了新的服务释放。

这是“实际第二观察与保守失效判定”的证据，不是局部修复、预测调用节省、新业务收益或两步 RL。不能据此选定任意周期，也不能把该探针作为默认在线策略。

## 6. 验证、失败与可重算性

静态复制专项 45 项、阶段定向 175 项全通过。最终冻结后完整回归 **844 项，0 failure/error/skip**；pytest 113.814s，Windows Job 116.125s / 180s，774 个源码/测试/旁路 sentinel pin 全部未变。三个数字是不同验证范围，不能相加当作独立场景数。

历史失败原件保留：上轮 profiling/测试编码错误，以及 native_001 延迟导入导致源码归档缺口；它们不被上轮最终 native_002 的成功覆盖。本轮独立双观察核查 001 首次失败，因为审计器只识别 planning_snapshot 而漏了实际 planning_snapshot_v3。差异精确定位为两条新增 v3 publication 的 COMMAND_ACK，均与实际 outbox 的 terminal/delivered 记录绑定，不是物理差异。保存旧审计器字节后修正，002 通过，继续收紧未知类型处理后 003 独立复核通过；全部原件、旧版本与失败保留，没有重写 native 或增加一次原生重跑。

未修改主工作区 `bounded_local_pibt.hpp`，SHA 仍为 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`；冻结物理模型 `research_live_obligation_native_domain.py` SHA 仍为 `d065cb78e6a37f1ae31d6a7a1a08f42c5f5e31ff746e7d765f5a15159d2a577c`。

证据统一前缀 `outputs/experiments/g31_ics_refresh_next_20261017/`：

| 证据 | 入口 |
|---|---|
| 本轮 profiling | `profiling_001/report.json`、`FINDINGS.md` |
| 旧方法确切字节 | `preoptimization_source_001/manifest.json` |
| 增量配对对照 | `incremental_abba_001/plan.json`、`report.json`、24 份 gzip 原件 |
| 默认原生闭合证据 | `native_001/guarded_default/episode/native/` |
| 默认独立核对 | `independent_native_001/report.json` |
| 同 owner 两次真实观察 | `freshpair_001/native/`、`probe_observations.json`、`refresh_audit.json` |
| 双观察独立核对及首轮失败 | `independent_freshpair_003/report.json`、`independent_freshpair_001/report.json` |
| 最终回归 | `final_validation_001/receipt.json`、`tests.xml` |
| 机器摘要 | `stage_summary_001.json` |

交付 ZIP 保留原路径/身份/换行/浮点及失败原件，附逐字节 manifest、路径映射与标准库复核器；当前源以 `repo/` 为准，不能只靠 Git patch 重建未跟踪文件。隔离 import 与保存数据核查不等于重跑原生；Windows 解释器、native 二进制和历史准入环境不是完整可移植镜像。

打包首轮在历史源码闭包处失败，原件保留。已知编辑能恢复且 SHA 完全相同的旧源码单独归档，没有按近似内容补写；仍有 **6 个历史登记版本缺少原始源码字节**：旧 later_campaign 测试 `46bbc80c…`、旧 later_control 测试 `02e1fbd9…`、旧 native_environment 测试两版 `42673ffb…/af236400…`、旧 request_context 测试 `e90a1176…`，以及仅被 catalog 专项的宽来源清单登记、未用于本轮原生运行的 probe 草案 `8c9145e6…`。完整路径、hash 和引用位置见包内 `HISTORICAL_SOURCE_GAPS.json`；这些历史源码不能独立逐字节复核，不能声称所有旧阶段的源码都可重现。

这不是本轮验收豁免：最新 844 项回归登记的全部项目 Python 来源，以及本轮两次原生归档来源，必须在包内真实存在并精确匹配，不能使用历史缺档声明通过。完整回归后只调整了打包/标准库验包工具，另行 12 项 artifact-only 测试通过；生产代码未再修改。以后测试除了登记 hash，还应在执行前封存对应源字节，避免仅留 pin 又丢失历史版本。

## 7. 下一阶段建议，不冒充已完成

优先对当前采集/验证和大 evidence 复制分别建立同样严格的配对证据，避免只优化事件循环。研究动态数据最小化或同请求验证结果复用时，必须保留真实 capability、不可撤前缀、来源覆盖与最终当前状态检查。

事件触发或周期性预测须另有有效时域、服务边界和未受影响外部轨迹的充分条件。下一道方法验证应在自然负载差异下出现真实服务变化与非平凡耦合，保留“无消息但到期”、第二次盘复用、候选绕行新增共享资源、ACK 不确定和原回退失效反例；没有边界证明则全域重算，不能截断闭包制造优势。

历史 initial12 的 receiver 约 0.119s 改善仍是旧已验证正例，不是 later 退化例，也不算本轮新收益。当前 later 非默认仍无可保护有效选择，不重训六条旧样本来伪报 RL。原机场 151 节点/227 边全流、零容量 ICS103→ICS104 语义、实际 EBS 映射和完整 100ms 继续待验证。
