# LT2 下一步：从当前证据继续，不重做起点

工作目录：`C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`。
先读 [最新继续进度与问题记录](LT2_CONTINUED_PROGRESS_20261014.md)、[前轮进度](LT2_PROGRESS_20261014.md)、`RESEARCH_STATE.json`、
`NOVELTY_LEDGER.md` 最后数节，按 `RESULT_INDEX.jsonl` 找原始证据。
本轮修改仍在本地，历史推送授权不自动延伸到新修改。

## 当前目标和不能重复的误区

两项需求仍须分别有效，然后验证 **R1 改路→空盘释放→R2 实际返供/占用→后续 R1 响应**。
所有比较保留同盘量、业务、权限、外生事件和必要 Storage 工序；逐件零退化不能用总成本下降替代。
完整请求 ≤100ms 与原始 28,506/57,012 业务规模未通过。

不要重新导入 V3、证明第一条一盘两服务、恢复 truth version、训练旧八个饱和有限域、
使用已撤回的 400 秒严格时序反例，或把原图 32 上下文当作 32 个独立来源任务。
不要将 reactive 与 joint 的不同前缀算成缓存加速比。

## 方法侧的下一项实际工作

1. 先修正合成继续规则的语义：更强96格已发现5格声称保持next3但实际保持next8。
   新版本须检查当前路线，需要变更时真实提交route3并验证ACK/实际边；30格receiving_full
   要有明确拒绝处理策略。两者都是策略改动，先全量重放旧24格，再预声明新参考；保留旧35个unknown。
   新参考成功格中的1.401秒只是成对差，不是认证headroom。详见LT2_STRONGER_TIMING_REFERENCE_20261014.md。
2. 信息审计已确认初始B输入三门相同；32个确定性一次性策略仅4个保护通过且最优仍是原策略。
   不要再直接把离线全信息最优作为在线提案。按LT2_CONTINUED_METHOD_SOURCES_20261014.md
   评估源端捕获、实际送达、有覆盖/有效期的typed planning contract，双方使用相同捕获摘要。
   当前仅设计，尚未实现；额外通信与等待后的检查点和动作域须重新验证。
3. 在合法输入与已修继续规则上实现同模型B3联合滚动MPC和B4资源感知闭合/重定时适配，明确原论文与离散原生动作的映射。
   固定路线费用、普通滚动反馈、公共资源合同和 WAIT 能力必须公平提供给对照。
4. 再在原图新授权档中按静态/因果条件构造多owner复用场景，记录全部排除；检验“哪些后继服务义务必须进入局部联合求解、何时可冻结外部”的具体规则。
   有条件的结构性质、反例与有限原生穷举应互相核验；尚不能把通用闭合命名为新算法。

学习任务保留。小规模诊断须先有合法信息、可执行同宿主标签、按来源任务/机制分组的训练验证划分，
以及明确的候选选择或计算节省假设；不直接重启大批标签/训练。

## 性能侧的下一项实际工作

原图 joint 的 120 秒硬超时保留在 `request_profile_segmented_full1x_001`。
只有 H10800 的三个完整返回分段可靠，尾部没有结果。该段 475 条 outbox 中仅 6 条活跃，
末段 178 次冷却激活没有产生新动作；这不授权删除冷却事件或 ACK 历史。
活跃索引与完整审计历史分离，必须继续验证请求、顺序、字典隔离、恢复和物理结果一致。
原生观察仍可能扫描历史，Python 索引不是完整复杂度问题的解决证明。

同观察路径/窗口/标量构造已优化，一次真实2500激活串行对照18.5488→17.1800秒，
全部599提交、2500区域记录、4611原生边界及物理结果相同；不重复做已解决的深拷贝缓存。
新增 `g31_ics_lt2_continued_20261014/request_profile_full1x_5000_001` 保存5000激活剖析：
public_astar累计20.157秒、原生观察19.851秒、候选14.510秒，嵌套项不可相加。
下一优化应针对区域路径构造和原生历史读取，保持消息/故障/失效边界，先做行为等价对照。
新停点12,249.637986，57件已到达，1186请求含10开放生命周期；输入分母仍28,506，全天指标null。
源码无变化时不把加预算重跑当成优化；此处更长剖析是新源码后的热点检查，不是无cProfile加速比。

有源码变更或具体未解热点时，再运行有界剖析；不要无目的重复已通过的用例。
以下 CLI 已实际执行过同构分段/预算路径。换用从未存在的新输出目录；
Windows 当前环境读取现有 `.pyd` 需要受限的本地执行提权。

```powershell
Set-Location 'C:/PROGRAMING/czr005/.g31_ics_circulation_worktree'
$env:PYTHONPATH='src;.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'C:/PROGRAMING/python3.11.9/python.exe' -m scripts.experiments.g31_ics_circulation.profile_lt2_requests --binary build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd --expected-binary-sha256 af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0 --suite full1x --policy joint --horizon 86400 --segment-seconds 3600 --activation-shard-budget 500 --max-activations 5000 --hard-timeout 120 --cprofile --output outputs/experiments/g31_ics_lt2_20261014/profile_resume_new
```

这条命令**从原输入重建**原生会话，不能接着读取上次 controller JSON 就声称物理恢复。
分片可以包含未排空的 owner 轮次；它们只在同进程原生对象仍存在时继续，状态为预算前缀时 metrics=null。
完整请求计费是保守共享上界；上界超限不直接证明隔离单请求实耗超限，未结束请求的完整上界为 null。
不使用平均值或推理耗时替代 100ms 总要求。

## 完成当前修改后的统一验收

```powershell
& 'C:/PROGRAMING/python3.11.9/python.exe' -m scripts.experiments.g31_ics_circulation.validate_live --binary build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json --output outputs/experiments/g31_ics_lt2_20261014/live_resume_new
```

按 JUnit 的真实计数更新记录；区分当前关联测试、历史 011 反例和跨版本身份测试。
保存失败、source_changed 和 hard_timeout；不要修改旧 receipt 使其显示成功。
检查父工作区 `cpp/ics_core/runtime/bounded_local_pibt.hpp` SHA256 仍为
`b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。

收口时同步 `RESEARCH_STATE.json`、`RESULT_INDEX.jsonl`、`NOVELTY_LEDGER.md` 和本文件。
现场零容量/EBS/盘配置及第二台目标机器只阻塞依赖它们的结论；其余方法研发继续。
不需要为常规本地修复、验证和证据整理重新请求许可。
