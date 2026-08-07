# G4IRSF19 新想法与证据日志

本文件只记录已经运行得到的事实，以及由事实直接导出的下一步假设。它不是待办清单，也不把尚未验证的想法写成结论。

## 2026-08-07：Source 排序不是当前主突破口

在 G18 native binary 上复跑 G17 Source policy：

- 144 segments：62 次评估，0 个替代提案，0 次动作突变；
- 512 segments：238 次评估，0 个替代提案，0 次动作突变；
- 8192 segments，`localized_thesis_rule`、`top_k=4`：8335 次评估，0 个替代提案，0 次动作突变；
- 512 与 8192 的 research closed-loop 指标均与 J2 control 相同；
- 候选行显示同一 source 的 top-K bag 在当前 seam 上除 rank 外的 slack、wait 和 leg 特征相同。

结论：继续训练“同一时刻 source 队首排序”会增加模型与授权复杂度，却没有可执行动作自由度。本轮停止该方向，不把零突变 job 当性能实验。

最窄的后续 Source 假设是复用现有 bounded pressure gate，将动作改成 `ADMIT/HOLD one natural opportunity`。只有在独立 bag 的 ADMIT/HOLD 突变数大于零时，才值得训练 Source head。hold retry 次数不能冒充 distinct mutation。

## 2026-08-07：Route 可先复用已有 native scorer

审计发现 E4/J2 在 Python wrapper 与 pybind binding 中被人为锁到 S1；native runtime 已经实现：

- S1：冻结 G4E legal-local 模型；
- S2：去掉绝对 node/goal ID 的同一冻结模型；
- S3：静态最短势能规则；
- S4：当前一跳队列感知规则。

因此最简单且可证伪的 Route 实验不是再造一层策略框架，而是解除外围 S1 锁，保持 R3/P2/Q0/C0/J2 与所有 hard shields 不变，直接做 S1/S2/S3/S4 配对消融。若已有 scorer 能产生 distinct route mutation 和业务差异，再考虑 residual learner；否则先修 action seam。

## 2026-08-07：4× 先要可观测的有界返回

G18 的 4× J0/J1/J2 都在外部 1200 秒 wall boundary 被杀死，没有 native return，无法区分物理积压与软件事件放大。现有完整 runtime checkpoint 是进程内对象，立即扩展成磁盘 codec 会扩大实现面并引入大量与主目标无关的状态维护。

本轮采用更窄实现：event loop 提供 O(1) progress snapshot；binding 支持 wall-bounded native return，并且不对 partial state 调用 `finalize()`。这能给出 simulated time、release/completion/backlog、event-type、heap、stale/retry/wakeup 等真实斜率。完整磁盘续跑只有在这些斜率证明单个 4× job 值得长时间延续后再做。

## 2026-08-07：并行先放在独立完整 rollout

单个 native event loop 没有释放 Python GIL，直接用 Python threads 不会形成可信加速。当前最窄的真实并行边界是独立进程运行固定、完整的 paired jobs：相同 release stream、fault schedule、split 和 arm pair；结果按预注册 job order 合并，而不是按完成顺序合并。

P=1/2/4/8 必须运行同一计划并报告 wall speedup、吞吐、失败/重试和确定性。该结果只支持“数据生成/实验并行”，不能冒充模拟器内部并行提交或机场物理吞吐提升。

## 2026-08-07：队列/本地日历比旧学习特征更有效

完整 8,192 evidence trace 中，S2（去绝对 ID 的冻结模型）和 S3（最短势能）相对 S1 都是 0 route mutation；S4 仅使用候选队列、scheduled incoming、corridor/target next-available 与静态势能，产生 90 次可直接匹配的下一边突变。S4 在 1× 无回退，在 2× 将 mean TTH 从 851.864 秒降到 337.843 秒、source wait 从 502.462 秒降到 54.666 秒。

因此 G19 选择现有 S4 规则作为 research mainline，不再为了“必须有新模型”训练 residual/MLP/set scorer。下一代学习器必须先在同一局部 action seam 上击败 S4，才能增加实现面。

## 2026-08-07：4× 边界是有界的混合瓶颈

J2/S4 的 1×、2× 分别在 20.398 秒、54.472 秒完整结束；4× 在约 60.8 秒 native wall bound 返回 27,872/174,412 完成、14,694 当前 backlog。J2/S1 在同一边界只完成 18,212，且 backlog 为 20,860。S4 将完整可执行前沿从 1× 推到 2×，并把 4× 的完成前沿提高 53.05%，但没有把 4× 伪写成完成。

4× 时单进程 CPU/wall 约 0.98，events/s 从 1× 的 238k 降到约 97k，同时 backlog 增长、congestion beacon 约占 39%。这同时具有单核事件执行压力和物理排队压力，当前应归为混合边界。证据不足以支持立即重写并行 event heap。

## 2026-08-07：进程 rollout 是当前已验证的并行收益

固定 32,768 pair-segment-replica 计划的两次独占重复中，P=2 speedup 为 1.863×/1.966×，P=4 为 3.289×/3.330×，P=8 为 5.247×/5.325×。所有结果都与 P=1 语义一致，retry/failure 均为 0。

这证明独立完整 rollout/data generation 可真实并行；它不等于一个模拟器内部的多线程 commit。真实 BOLT-P checkpoint seam 的 P=1 已严格复现串行，但单 worker 历史内存约 5.27 GiB，本机不安全运行 P=8，因此没有虚构 native P>1 数字。

## 2026-08-07：S4 不削弱已有故障边界

两种受保护的 8,192 段 fault 场景中，J2/S1 与 J2/S4 都 COMPLETE、hard safety 通过、物理 fault-edge entry violation 为 0。受影响行李完成数分别为 10/10 与 3/3，恢复时间在同一场景两边一致；S4 仍保持 mean TTH −1.794 秒和 events −3,269 的配对改善。

这支持在当前单进程、既有延迟通知模型下使用 S4；尚未覆盖 proposal/commit 之间的进程崩溃或跨机器消息乱序，不能扩张成完整分布式容错声明。

## 2026-08-07：现有 Source pressure gate 只作为负结果保留

修正 telemetry 语义后，144 段的 A0/A1/A2 distinct observed HOLD state 为 0/30/30，512 段为 2/137/137；成功 admit 后的服务等待行不再冒充 HOLD。A1/A2 在两个小前缀完全相同并都增加 source wait。

在固定 J2/S4 的 2× 完整运行中，关闭压力门控 A0 的 mean TTH/source wait 为 337.843/54.666 秒；A1 为 345.607/66.526 秒，A2 为 342.780/58.779 秒。三臂安全均通过，但两个门控都比 A0 差，因此不晋级。2× 只保留 summary counters，数万 retry 不被描述成 distinct mutation。

该负结果进一步支持“先保证 action seam 非别名，再训练”的简化原则：G19 不训练 Source learner，也不把 deterministic HOLD 计数写成 learned ownership。
