# G4IRSF25 新想法与证据日志

> 状态：`FINAL_EVIDENCE_LOG`
> 原则：只记录有证据且能推进“一步式去中心化 + MAPF 局部协调”的简单想法；不新增 planner、模型层或 hash 仪式。

## 1. 已验证并采用

### I1. 把 censor 与 true timeout 分开

状态：`MEASURED_AND_ADOPTED`

最终 observe 口径是：

```text
48,516 = 25,778 completed rejoin + 204 true timeout + 22,534 censored
```

loop/unsafe 为 0，observed arm fraction 为 `0.8125`。旧口径把 `22,534` censored 归为 timeout，会把“bag 已正常结束或新轨迹覆盖”错误解释成“走廊卡住 600 s”。

采用：轨迹终态互斥；只有真实达到 600 s 才更新 timeout。bag goal/failure/runtime stop 和新登记覆盖只记 censor，不污染反馈。

停止线：不为每个罕见终态增加新策略分支；它们只影响标签正确性。

### I2. nominal arm 只是 first-edge intervention，不是未来路径承诺

状态：`MEASURED_AND_ADOPTED`

真实轨迹显示逐接口 S4 常在中间节点改向。例如 1× `6->8` 只有 `1/1,367` 命中旧 rejoin 13，1× `19->18` 只有 `146/4,886` 命中 rejoin 26；这些未命中多数是 censor，不是 unsafe。

采用：保留真实第一跳、实际路径和观察用 rejoin；下一接口继续重新决策。

拒绝：强制走完整 corridor。那会重新引入未来路线和中央规划器式承诺。

### I3. 用 outcome-free checkpoint 采样消除重复 pending wakeup 偏差

状态：`MEASURED_AND_ADOPTED`

早期 pair census 会在同一 bag/branch 的重复 pending wakeup 上重复取样，形成不可用的选择偏差。修正为每个 `(runtime_bag_id, current_node)` 只取最早已登记事件，然后才做 branch/load 平衡；筛选过程不读取未来 outcome。

结果：`1,024` checkpoint groups、`2,048` arm outcomes、固定 `21D` observation，unsafe=0。oracle alternative-win `0.53125`、opportunity mass `2,323,446.867805 bag-seconds`；local ceiling `0.900390625`，高于 S4 `0.46875`。

停止线：不通过在线随机探索补覆盖；同 checkpoint 强制 first edge 后立即恢复 S4/J2/E2 已足够回答当前问题。

### I4. 移除 paired 热路径中的逐事件 SHA

状态：`MEASURED_AND_ADOPTED`

观察：trusted short-horizon pair 原本每个 event 都计算 full-state SHA、seal 和富状态快照，pilot pair 需要 `190.171 s`；算法只推进约 600 个事件，时间却主要耗在安全式审计。

最小改动：在同进程可信 pair 路径使用 next-event time，并用 O(1) 局部 queue/incoming 统计；正常跨边界 checkpoint 校验不变。

结果：同语义 pair 降到 `2.029 s`，约 `93.7×`，结果语义一致。

结论：实验热路径不应反复做与研究目标无关的 SHA/hash。该优化直接释放了 pair census 和正式数据生成时间，没有引入新框架。

### I5. 统一反馈单位，并只让 L3 读取在线反馈

状态：`IMPLEMENTED_AND_AUDITED`

旧文档中的 `short_EWMA - static_duration` 会混淆局部 system cost 与静态旅行时间。当前实现统一使用局部 queue/incoming 的 `bag-seconds`，保存 bounded short/long EWMA 差；只有 L3 在触发后读取它。

L1/L2 的动作不依赖 policy-generated online feedback，避免训练/执行反馈漂移。最终 residual-feedback correlation 为 `0.0`，所以 L3 未触发。

停止线：相关性不达门就保持没有在线层；不做 online backprop、replay buffer 或中央 critic。

### I6. 先 prefix screen，再花 full-run 成本

状态：`MEASURED_AND_ADOPTED`

T0 在 144/512/8192 三个 native screen 都是 0 mutation。按预设规则立即停止；它的 full 1×/2×/4× 保持 `NOT_MEASURED`，没有把 0 mutation 包装成安全收益。

这证明阶段门能减少无效实验，而不需要复杂 rubric：候选必须先有安全的非零 changed action，才值得完整闭环。

## 2. 已验证但未晋级

### I7. 高负载局部改道信号真实存在

状态：`MEASURED_SIGNAL; NOT_PROMOTED`

L1 offline test ranking 为 `0.8293`；native 2× mean/p95/p99 相对 S4 为 `-7.549/-48.801/-207.381 s`。4× bounded progress 也一致：

| window | S4 completed/backlog | L1 completed/backlog |
|---:|---:|---:|
| 60 s | 25,218 / 14,211 | 25,724 / 13,554 |
| 180 s | 50,584 / 20,619 | 56,696 / 17,089 |

但 L1 1× mean/p95/p99 为 `+5.921/+25.398/+21.400 s`，违反不退化门。当前证据支持“负载条件很重要”，不支持把 L1 全局上线。

最简单后续方向只是在未来数据中检验一个清晰的 load abstain/calibration 门；本轮不追加 selector，也不改 active policy。

### I8. 更大的 tiny MLP 没有解决跨负载问题

状态：`MEASURED_NO_GO`

L2 虽被 train+validation oracle 触发，但 test ranking 只有 `0.5463`；native 1× 退化，2× mean 也 `+1.821 s`。4× bounded progress 通过不能覆盖完整 1×/2× gate。

结论：当前问题不是再增加模型容量。停止 L2 扩展，不再加隐藏层、ensemble 或 selector-of-selectors。

## 3. 规模证据对设计的影响

Fresh HCA 4× fixed window 只释放 `117,626/174,412` segments（`67.441%`），但 released cohort 完成 `117,270/117,626`（`99.697%`）。因此集中式瓶颈主要在 admission/planning throughput。

采用：规模实验优先报告 released、completed、backlog 和 events/completed；canonical population 未完成时，full TTH 必须写 `NOT_MEASURED`。

同样，S4/L1 4× 只有 60/180 s bounded progress，不能把它改名为完整 mean/p95/p99/max 延迟。

## 4. 已明确拒绝的复杂方向

| 想法 | 决定 | 原因 |
|---|---|---|
| 强制完整 corridor | 不做 | 违反逐接口一步重决策 |
| 全局 MAPF/CBS/HCA reservation | 不做 | 恢复中央吞吐瓶颈 |
| GNN/Transformer/ensemble | 不做 | L2 已证明容量不是当前答案 |
| branch-specific if 树 | 不做 | 会把有限证据固化为脆弱规则 |
| online backprop/中央 replay | 不做 | L3 correlation 为 0，且增加中央状态 |
| 大范围阈值 sweep | 不做 | 容易追逐 validation 偶然性 |
| survivor-only TTH | 不做 | incomplete population 下有选择偏差 |
| paired 每 event SHA/seal | 不做 | 已测得约 93.7× 无谓开销 |

## 5. 最终状态

```text
active = S4
decision = DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE
T0 = ZERO_MUTATION_SCREEN_STOP
L1 = HIGH_LOAD_SIGNAL_BUT_1X_FAIL
L2 = NATIVE_NO_GO
L3 = NOT_TRIGGERED_CORRELATION_ZERO
H_system/fault = NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER
```

本轮最重要的新认识不是“再加一个模型”，而是：保持一步式去中心化框架，正确区分 censor/timeout，用无结果泄漏的同 checkpoint pair 测真实动作机会，并把与算法无关的逐事件 hash 热点移除。它们让证据更可信、实验更快，也没有把项目改复杂。
