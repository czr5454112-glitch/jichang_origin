# 第七轮可选终点筛查部署验证

3 条 nominal pilot 和 27 条正式输入均独立完成，全部排空。正式 2467 次查询的实际公开 Snapshot SHA、身份、K 和完整有序候选池保持一致，物理 tick/事件/任务/实际 slow proposals 也保持一致。

正式筛中 93 条。原逻辑 search work 1666386 → 1387386，减少 279000（16.743%）；额外 screen record work 73465 单列，不能把两种不同工作单位机械相减。

最终 cache 状态相同 27/27；这只是实测结果，包装器并不保证省略查询后仍逐字段相同。

正式 worker 调用 CPU 839.890625s，parent 2.656250s，wall 294.606121s。其中 screen CPU 0.359375s、Snapshot hash 观察 CPU 56.421875s 均为嵌套区间。没有公平的端到端 CPU speedup 测量，不能拿不同观测器的旧批作速度倍率分母。

筛查仍只是当前固定 Snapshot/H 的完整 witness 必要条件；不是未来任务不可服务，也没有放宽执行 validator 或改默认策略。

纯文件汇总核验 73 项，失败 0；直接 CPU 0.031250s。
