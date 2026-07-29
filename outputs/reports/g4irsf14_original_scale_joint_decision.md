# G4IRSF14 原始规模联合结论（Stage M）

- Stage 状态：`PARTIAL_WITH_EXPLICIT_BLOCKER`。
- 总结论：`PARTIAL_WITH_EXPLICIT_BLOCKER`。
- 架构：同一时刻微阶段、destination-owned merge request/grant、exact clone/no-op 与被动机会计数已有机制测试和绑定证据；这只证明实现/审计能力，不证明原始 1x 性能改善。
- 规则：Stage D 的 M0–M6 在 144 段机制运行中 mean/p95 均同值，没有规则改善证据。
- 学习：0 个 matched causal labels，训练与闭环均未运行，所以没有学习改善。
- 冻结 F2 仍比 v2-safe 慢 `1.134703809870` 秒/袋。
- 因果证据到达 exact clone/no-op fidelity、I1–I5 screening census；尚未到达 action-changing matched H_bag/H_system outcome。
- 根阻塞是尚无正式 Stage E matched-intervention campaign。应先让预注册 exact-binary native campaign 可执行，并对已有 screening支持的 I1/I3/I4 取得完整 H_bag/H_system；同时恢复或重设计 I2主合流支持和 I5 applicable opportunity。只有完整 Stage E 门（至少 2,000 个 complete labels、H_system > 0）通过后才允许训练。

## 第 25 节的 18 个问题

1. **为什么只慢 1.1 秒仍不能胜？** promotion 要求严格快于 v2-safe；1.134704 秒/袋仍是正差，而且学习、故障与证据门未闭合。
2. **为什么差距大多不是走错路？** 冻结报告的分解把差异主要记录在局部等待/服务顺序，而不是路径长度；这是继承的描述性分解，不是 G4IRSF14 已证明的因果解释。
3. **为什么 H1 优先级完全没变化？** 旧证据只显示 H0/Q0 与 H1/Q1 的完整行为投影、路径、合流状态和结果同值；在没有 action-changing matched states 时，不能进一步断言是哪一项特征或并列机制导致同值。
4. **event seq 是否偷偷决定先后？** 设计与机制测试要求先收集同刻事件、再由本地仲裁，seq 只作确定性身份/兜底；但尚无新的原始 1x 闭环候选结果可把它声明为完整性能因果结论。
5. **两阶段同刻处理是什么？** 第一阶段应用同一时间戳的 release/arrival/fault/repair；第二阶段按受影响目的节点各做一次本地仲裁，不人工推进时间。
6. **merge request/grant 像什么？** 像多个上游向目的合流口领同一服务槽的本地票据：request、grant、consume/revoke 都有生命周期。
7. **为什么仍去中心化？** 目的节点只读自己的 pending set、service slot 和一跳状态，不读全机场任务或全局预约。
8. **为什么每袋仍只决定下一边？** grant 只覆盖一个目的槽和一条有向边，reservation depth 固定为 1。
9. **PIBT 负责什么？** 只处理 blocker 可局部移动、存在替代边且需要多袋一步原子协调的异常；不接管普通 merge queue 或多步规划。
10. **为什么旧 V3 标签不够？** 它含 proxy/未配对结果，不能证明改变当前动作导致收益，也可能学到 task ID 或事后信息。
11. **matched clone 如何给更可靠标签？** 从完全相同 checkpoint克隆，只改一个合法动作，分别运行到同一 H_bag/H_system horizon，用完整安全结果的差作为 causal label。
12. **为什么 top 1% 是重点？** 冻结分解显示 top 1% 的 286 袋对全体均值贡献 +1.235566 秒/袋，剩余 99% 则贡献 -0.100862 秒/袋；这说明均值损失高度集中，不等于 top 1% 直接决定 p95/p99。是否由合流、source wait 或 fault 造成必须靠 matched evidence 判定，仍须保留全体与负例。
13. **为什么不能盲目模仿 v2-safe？** v2-safe 是性能比较器，不是逐状态因果 oracle；模仿动作可能复制偶然次序或未来信息。
14. **为什么节点 19/22 不是坏节点？** 节点编号只是高流量上下文的一部分；好坏取决于 ready set、时间、来源/去向和干预结果，不能给节点永久负标签。
15. **故障还需要什么？** 对最终候选做新鲜 matched DDI/BTI、grant issue→fault、prepare/commit→fault、same-timestamp fault和 informative multi-fault；同时验证 stale grant、repair 仅一次、cleanup 完整、P2 prepare/validate/commit/rollback 原子，以及unsafe=0 和 shield 的主动收益。
16. **为什么现在不优化 C++？** 当前缺的是有效动作与因果证据；wall-time 加速不等于 TTH 改善，还会引入新 binary 身份。
17. **什么时候可开始 1.1x？** 严格 v2-safe 胜利、独立学习贡献、fault regression、numeric demand calibration 和原任务生成审计全部通过后；当前 scale gate 锁定。
18. **为什么仍只用原始真实 map？** 本阶段要隔离控制策略的因果作用；固定唯一 map2 与原始 28,506 袋可防止用合成拓扑或任务漂移制造假收益。

生成绑定：`a8db7027c44c66614ac3f7b04f414b10ce7863f066eebcc901177d9cc1ff363a`。
