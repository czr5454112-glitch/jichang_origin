# G4IRSF25：情境化局部走廊学习执行与结果

> 状态：`EXECUTION_COMPLETE`
> 证据冻结日：`2026-08-22`
> 最终 active policy：`S4`
> 最终决策：`DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE`

## 1. 目标与边界

G25 的目标是用简单的一步式去中心化框架替代原项目的集中式 HCA*/A* 完整路径规划：每件行李只在当前接口选择下一跳，到下一接口再决策；多行李只通过局部队列、JIT 合流、深度一预约和 PIBT-lite/shield 协调。

新增的 CLCR（Contextual Local Corridor Routing）只对 S4 已生成的合法一步候选作局部重排，不是第二个 planner，也不保存未来路线：

```text
当前分支 -> S4 合法一步候选 -> CLCR 局部重排或精确回退 S4
         -> 提交一个下一跳 -> 下一接口重新决策
```

运行时保持以下停止线：无完整 A*、无全局预约表、无全图队列扫描、无中央 critic、无 GNN/Transformer/ensemble、无 branch-specific 规则树。证据不够时直接回退 S4。

## 2. 已完成的最小实现

- 原生 ABI 固定为 `czr005.g4irsf25.clcr.v1`，支持 `off/observe/t0/l1/l2/l3`。
- 输入为固定 21 维局部特征：12 个候选相对 S4 的局部差值，加 9 个当前 bag 与 branch-arm 的有界状态量。
- 轨迹从真实 first-edge 提交后开始，记录真实路径、rejoin、local queue/incoming 面积、private cost、redecision、timeout、censor、loop 与 unsafe。
- 同一条轨迹的三个互斥终态是：命中登记 rejoin、真实 600 s timeout、或因 bag 完成/目标结束/新登记覆盖等原因被 censor。
- 每个 branch-arm 只维护常数个局部反馈量。local-system 反馈和模型目标统一使用 `bag-seconds`；只有 L3 读取该反馈并形成有界 EWMA 差，L1/L2 不读取在线反馈，不发生策略反馈漂移。
- `off/observe` 保持 S4 动作语义；所有策略继续通过现有 locality/safety/shield 门。

## 3. 真实轨迹证据

1×/2× observe 共记录 `48,516` 条真实 trajectory，严格分解为：

```text
48,516 = 25,778 completed rejoin
       +    204 true timeout
       + 22,534 censored
```

loop/unsafe 为 `0/0`；16 个 scale-arm cell 中 13 个有观察，observed registered-arm fraction 为 `0.8125`。runtime full A*、future-route input 和 G25 runtime global scan 均为 0。

| scale | started | completed rejoin | true timeout | censored |
|---:|---:|---:|---:|---:|
| 1× | 16,172 | 8,197 | 0 | 7,975 |
| 2× | 32,344 | 17,581 | 204 | 14,559 |
| 合计 | 48,516 | 25,778 | 204 | 22,534 |

这纠正了旧口径：`22,534` 不是 timeout。大量 nominal arm 在逐接口重决策后由 bag 正常到达其他目标而被 censor；这正是去中心化一步决策的正常行为，不能为了旧 corridor 标签而强制未来完整路线。

## 4. 同 checkpoint paired oracle

最终数据包含 `1,024` 个独立 branch decision、`2,048` 个 forced-first-edge arm、固定 `21D` 局部 observation；每组保持相同 checkpoint、未来 release 与后续 S4/J2/E2，仅第一条合法 edge 不同。

- alternative-win fraction：`0.53125`；
- useful opportunities：`544/1,024`；
- opportunity mass：`2,323,446.867805 bag-seconds`；
- mean possible improvement：`2,268.991082 bag-seconds`；
- local-observation pairwise/majority ceiling：`0.900390625`；
- 同一数据上固定 S4 action accuracy：`0.46875`；
- local regret ceiling：`73.771719 bag-seconds`；
- unsafe forced arms：`0`。

结论是动作空间和局部 observation 确有信号，但这只是同 checkpoint 短程上限，不等于完整 native 闭环收益。

## 5. T0/L1/L2/L3 结果

| 层 | 离线/触发结果 | native 结论 |
|---|---|---|
| T0 | test ranking `0.4293`，离线 mutation 为 0 | 144/512/8192 prefix 均 0 mutation，按门停止，full `NOT_MEASURED` |
| L1 | test ranking `0.8293`，明显高于 S4 `0.46875` | 2× 和 4× 有益，但 1× 明显退化，不晋级 |
| L2 | train+validation 触发；test ranking `0.5463` | 1×、2× 不通过，`NO_GO` |
| L3 | residual-feedback correlation `0.0` | 未触发、未导出、未运行 |

L1 的完整 native paired repeats：

| scale | mean ΔS4 | p95 ΔS4 | p99 ΔS4 | max ΔS4 | 结论 |
|---:|---:|---:|---:|---:|---|
| 1× | `+5.921 s` | `+25.398 s` | `+21.400 s` | `-111.950 s` | 低负载回归，FAIL |
| 2× | `-7.549 s` | `-48.801 s` | `-207.381 s` | `-141.850 s` | 高负载改善，PASS |

负值为更快。L1 虽然验证了“局部改道在高负载有价值”，但违反 1× 不退化门，因此不能取代 S4。L2 在 1× mean/p95/p99 分别 `+4.716/+14.400/+21.000 s`，2× mean 又 `+1.821 s`，所以不再叠模型。

## 6. 4× bounded progress

4× canonical workload 为 174,412 segments；60/180 s 均只报告 bounded progress：

| policy | window | completed | backlog | events/completed | mutations |
|---|---:|---:|---:|---:|---:|
| S4 | 60 s | 25,218 | 14,211 | 176.717 | 0 |
| L1 | 60 s | 25,724 | 13,554 | 180.884 | 3,127 |
| S4 | 180 s | 50,584 | 20,619 | 193.043 | 0 |
| L1 | 180 s | 56,696 | 17,089 | 187.259 | 5,030 |

L1 在两个窗口都完成更多、backlog 更少，且 safety/locality 通过。这是有价值的 scale signal；但 population 未完整完成，所以 S4/L1 4× mean/p95/p99/max TTH 全部保持 `NOT_MEASURED`，不能用 bounded progress 代替完整延迟。

## 7. S4 与 fresh HCA

1× 同 exact-release 完整 population：

| 方法 | Mean | P95 | P99 | Max |
|---|---:|---:|---:|---:|
| Fresh HCA | 236.710166 s | 299.000 s | 330.000 s | 357.000 s |
| S4 | 210.769735 s | 247.204 s | 254.004 s | 407.404 s |

S4 mean 改善 `25.940432 s`（`10.958732%`），p95/p99 也更好，completion 相同；max 比 HCA 慢 `50.404 s`，因此不声称 all-tail dominance。

Fresh HCA fixed-window capacity：

| scale | canonical segments | released | completed | complete raw bags | incomplete raw bags | full TTH |
|---:|---:|---:|---:|---:|---:|---|
| 2× | 87,206 | 87,206 | 87,111 | 56,917 | 95 | `NOT_MEASURED` |
| 4× | 174,412 | 117,626 | 117,270 | 70,018 | 44,006 | `NOT_MEASURED` |

4× 只释放 `67.441%` canonical segments，而 released cohort completion 为 `99.697%`；瓶颈主要在集中式 admission/planning throughput。不能用 survivor latency 或 parent wall 代替 full-population TTH。

## 8. 已验证的实施优化

paired runner 最初在每个 event 做 full-state SHA 和富快照审计；这不是算法语义，却成为主要热点。移除该安全式热路径，改用可信的 next-event time 与 O(1) 局部 queue/incoming 统计后，同语义 pilot pair 从 `190.171 s` 降到 `2.029 s`，约 `93.7×`；结果语义保持一致。

这项改动直接落实“少做与算法无关的 hash/防御准备工作”的要求。正常可验证 checkpoint 路径仍保留；短程同进程可信实验不再逐事件计算 SHA，也没有引入新框架。

## 9. 最终决策

```text
active = S4
decision = DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE
reason = NO_ELIGIBLE_CHANGED_ACTION_WINNER
```

T0 没有 mutation；L1 虽在 2×/4× 显示收益，但 1× 回归；L2 native no-go；L3 未触发。因此没有 eligible changed-action winner，winner-only H_system/fault 为 `NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER`。这不是学习方向被否定，而是当前学习尚未在跨负载闭环上给 S4 增量。

G25 的已完成成果是：一步式去中心化 S4 已在原始 1× 超过集中式 HCA，并在 HCA 2×/4× 出现容量边界时保持可扩展执行；CLCR 证明局部动作机会和高负载收益存在，但尚不满足统一上线门。

## 10. 证据索引

- 真实轨迹：`outputs/reports/g4irsf25_corridor_trajectory.md`
- paired oracle：`outputs/reports/g4irsf25_short_horizon_oracle.md`
- T0/L1/L2/L3：`outputs/reports/g4irsf25_threshold_gate.md`、`outputs/reports/g4irsf25_contextual_learning.md`
- native 1×/2×：`outputs/reports/g4irsf25_native_closed_loop.md`
- native 4×：`outputs/reports/g4irsf25_scale.md`
- HCA capacity：`outputs/reports/g4irsf25_hca_scale.md`
- 最终选择：`outputs/reports/g4irsf25_final_joint_decision.md`
