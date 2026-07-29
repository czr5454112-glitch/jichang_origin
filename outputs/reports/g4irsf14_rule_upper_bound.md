# G4IRSF14 规则上界门（Stage F）

- 状态：`NOT_RUN_UPSTREAM_CAUSAL_GATE`。
- Stage D 在 144 段机制样本上执行了 M0–M6；安全门通过，但 mean/p95 相对 M0 的变化均为 0。
- Stage F 预注册的 14 个规则（R-M0..R-M7、R-S0..R-S5）均未运行，formal eligible count = 0。Stage D 与 Stage F不是完整一一同义；仅 R-M0/R-M1/R-M2 有明确参考映射。
- Stage E 的正式 matched H_bag/H_system 标签数为 0，因此不能把 144 段规则同值外推成原始 1x 上界，也不能声称规则有收益。
- Stage D 的 M7–M9 已按设计拒绝在线执行；这不能替代 Stage F 的 R-M7 评估，本阶段没有运行新的候选。

生成绑定：`a8db7027c44c66614ac3f7b04f414b10ce7863f066eebcc901177d9cc1ff363a`。
