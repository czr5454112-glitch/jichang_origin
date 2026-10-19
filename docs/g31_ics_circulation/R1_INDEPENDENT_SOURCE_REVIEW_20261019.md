# R1 冻结源码独立审查

结论：`R1_implementation_freeze_001.json` 对应实现未发现静态缓存、动态 guard 或实际提交路径的语义阻断；可以在原登记业务域内做有限性能校准。存在两个计时覆盖限制，不能用这份实现宣称全部 activation、全部 ACK 墙钟与异常请求计时均完整持久化，也不能声称完整请求已达 100 ms。

独立审计：`outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/R1_independent_review_001/audit.py`、`report.json`。标准库实际执行 76 项检查，报告 SHA256 为 `193826a9a3088f9b84dd9be02e098fd69d96c63c69b817898e8e3e35973fde4c`。没有运行 native、训练或选模，没有修改冻结源码。

## 语义核对

七个来源文件均与 freeze001 SHA 相符。以已闭合 formal negative rule 的归档字节为旧版比较基准，五个修改前来源 SHA 均与 freeze001 的 before 字段一致；没有以今天工作目录冒充历史实现。

`foundation_repeated_registry.py` 只保存注册的十个静态 case 的完整业务 ID、13 个原始合同字段及物理合同 canonical string，使用冻结 dataclass 和 scalar/tuple 副本。每次 identify 仍比较当前物理合同、完整业务集合、全部合同值、注册声明和字段顺序；没有缓存当前 observation、source age、TTL、ACK、候选预测、合法 mask 或 guard 结果。初始化在主进程 NativeSession 构造前进行，resident worker 在 ready 之前完成。冷启动成本单列，不能算成凭空消失。

独立 AST 比较确认 domain 除 identify 外的所有原有顶层函数未变，包含 scene 和 evaluate；identify 改成静态匹配查表，原动态 seed/三候选完整完成向量仍逐次构造和校验。另对 registry 实际执行纯数据所有权测试及六类变更反例：物理合同、缺件、增件、字段值、声明、字段顺序均拒绝。

实际 client 仍精确使用原 `LocalTransport` 类型，没有替换 owned/send，也没有 subclass 绕过 `actual_same_session_local_transport_required`。历史 adapter 的同 session、当次 owner root、真实 row alias、完整提交历史校验保留。父 `Transport.send` 的新增代码仅是可选 exact list sink、两次 `perf_counter_ns` 和调用后 append；剥离这些新增语句后，原函数 AST 及 row/payload copy→native call→outbox→call-log 顺序完全相同。非 list（含 callable）不会执行，旧调用默认关闭。

当前 owner/target、0.05 source age、ACK/headway、generation/traversal、完整业务零容忍保护与 local mask 保留；最终 reference digest、native handle、owner activation、当前 view 和 own_outbox 等值复核仍在实际 route dispatch 前执行。模型只排序 enabled 候选，计时数据不进入 actor observation 或证据，不构成授权。

## 测试和历史 parity 的证据层级

核对保存的 JUnit 文件 SHA 与 XML：92 tests、0 failures/errors/skipped，实际测试总时长 18.754 s。测试包括十个注册 case、不可变副本、变更反例、完整字段、exact transport/client ledger gate，以及默认与计时开启时 calls/outbox/creations/ACK 相等。这里是核验该次已保存测试证据，没有另跑全部 92 项。

保存的 parity producer、report 及 29 份历史 raw 哈希均核对一致。报告覆盖去重后的 27 项 evidence，其中 19 supported、8 unknown，完整 report/candidate/per-job guard 相等；未知旧证据没有被缓存“修成通过”。本独立审计没有再运行预测引擎；其支持来自归档来源、完整输出 parity 报告、源码差异和静态匹配测试共同核对。离线 replay 中约 423→32 ms 的 evaluate 时间只表示该顺序重放，不是 native 完整请求延迟或公平主机 benchmark。

## 计时覆盖限制

正常新 cycle/preview 请求由 `begin_new` 在 publication 前开表；ready 后 collect、evaluate、mask、public observation、inference、ranking、require_current、route dispatch 八个区间各自记录。实际 native submit 的 start/end 与包围它的 dispatch 分开。logical wait、open→submit return、open→controller done、ACK read activation envelope、native advance wall/sim 分开，重叠区间不可相加。controller 记录与清理落在 close 前，因此总包围区间覆盖这部分开销，但没有单列第九个 recording stage。当前实现是 wall 计时，并未实现设计中提及的 CPU ns 记录。

1. **初始化和最终收尾不在 OwnerPolicy activation 计时范围。** `foundation_repeated_native.py` 的 `run_branch` 初始化两轮 `client.activate` 与第 759 行开始的 final_outbox_collection/refresh 不经过第 331 行的 OwnerPolicy.activate 包装。若 ACK 首次在最终 refresh 被读到，raw 的 ack_handling 有事实，但 path_timing 不会有对应 read envelope。因此 `all_owner_activations_timed=true` 只能解释为 continuation OwnerPolicy.activate，而不能覆盖全部 client activation roots。该缺口不授予额外动作权能。
2. **异常的计时记录未持久化。** `foundation_repeated_campaign.py:263` 的 except 分支调用旧 capture_partial，另保存 repeated_attempts；两者都未序列化 `client.path_timing.audit()`。path_timing 仅由成功 `run_branch` 返回。纯 Recorder 测试可在内存保留 exception/open，但不能证明原生异常进程也留下可统计的计时数据。异常 run 必须作为 timing-censored failure 保留在实验分母，不能只汇总成功请求后宣称所有状态计时完整。

这两个限制已向 root 和实现代理报告；本审计不修改 freeze001。若加固，应另冻结新版本并重新登记，而非改写该次证据。物理 edge 发生的精确墙钟也没有测量；receipt 的 sim time 不能替代它。

## 历史训练合同

`foundation_multistep_learning.py:453` 仍在读取/重算 episode 之前比较当前 domain 文件 SHA 与登记的 `decision_contract_sha256`；后续还比较 collection registration、inner source archive 和固定 peer policy。R1 domain 从旧 `3bf1f2d5...` 变成 `9bf38e32...`，旧训练合同应拒绝在当前工作目录重新训练。复现旧训练需完整历史归档；新的 collection/training 需要独立登记合同。既有权重消费不等于重新训练，也不允许因性能补丁重选正式测试权重。
