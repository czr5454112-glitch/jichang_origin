# G4IRSF20 已验证的新想法与证据

本文只记录本轮已经落地并经过实跑或自动化测试验证的结论。结论以简单的去中心化 A0 + S4 + J2 主线为边界，不把离线候选写成运行时策略。

## 1. 用精确局部状态消掉冗余 beacon，不增加新调度框架

- **E1** 只省略已知冗余的 source dequeue、service-complete 和成功 dispatch 伴随 beacon。
- **E2** 在 E1 之上，仅当已有等价 beacon、G17/first-edge-credit 未启用，且 purge 前后 `queue length`、`scheduled incoming`、`reserved_until` 都未改变时，省略 hold beacon；原有 pending JIT merge opportunity 仍会调度。因此它复用现有 generation/coalescing 机制，没有增加另一套 wake-up 框架。
- E1/E2 与 G17 beacon extensions 或 first-edge-credit 的组合没有等价性证据，因此配置校验直接拒绝这些组合；不为未验证组合再造一套同步逻辑。
- 1x/2x 全量实跑中，E0/E1/E2 的逐任务 TTH、逐任务 Route wait、硬安全结果及 bounded action projection 一致。这里的 action projection 是每个 bag 的 final/count/last-eight，不等同于完整 action trace。

| 规模 | 策略 | 完成工作 | events | beacon events | mean TTH（秒） |
|---|---|---:|---:|---:|---:|
| 1x full | E0 | 28,506 raw tasks / 43,603 segments | 4,857,316 | 1,978,963 | 213.912317 |
| 1x full | E1 | 28,506 raw tasks / 43,603 segments | 4,246,986 | 1,368,633 | 213.912317 |
| 1x full | E2 | 28,506 raw tasks / 43,603 segments | 4,064,751 | 1,186,398 | 213.912317 |
| 2x full | E0 | 57,012 raw tasks / 87,206 segments | 11,388,415 | 4,620,693 | 337.842709 |
| 2x full | E1 | 57,012 raw tasks / 87,206 segments | 10,169,869 | 3,402,123 | 337.842709 |
| 2x full | E2 | 57,012 raw tasks / 87,206 segments | 9,454,789 | 2,687,019 | 337.842709 |
| 4x bounded 60s | E0 | 26,977 / 174,412 segments | 5,570,560 | 2,187,615 | — |
| 4x bounded 60s | E1 | 27,676 / 174,412 segments | 5,308,416 | 1,841,584 | — |
| 4x bounded 60s | E2 | 27,760 / 174,412 segments | 4,915,200 | 1,433,053 | — |

E2 相对 E0 在 1x/2x 分别减少约 **16.32%/16.98% events per complete**，beacon 分别减少约 **40.05%/41.85%**。4x 的 events per complete 从 206.493 降到 177.061，60 秒完成量提高约 2.90%；这证明了软件事件开销下降，但不是物理容量已突破的证据。

## 2. compact census + deferred target 比预先物化全部状态更简单

- census 只返回 I3 的紧凑地址；Python 选择后，把 `schema / population_group_id / population_selection_id / event_ordinal / horizon` 五字段 deferred target 交回 native。
- native 在精确事件边界重放并封装 descriptor，省掉“先为全部选中样本物化完整 descriptor、再执行 pair”的中间阶段；Route observation 也不重复持久化。
- 对一个真实 H_system deferred pair 的专门验证中，pair 输出从 **48,716,738 bytes** 降到 **34,605 bytes**（约 -99.93%），JSON 序列化从 **0.951 秒**降到 **0.00063 秒**，native 执行从 **54.03 秒**降到 **51.73 秒**。pair 仍为 `ACTION_CHANGED_HORIZON_COMPLETE`，same-state、live safety、formal hard gate 和 pair completion 均通过。
- compact H_system 输出保留 affected runtime-segment delta、segment/raw-bag aggregate cohort metrics、Route observation、invariants 和 hard gates；省略 28,506 行 raw-bag sufficient-statistics、43,603 行 cohort-difference 以及逐 bag realized-externality 明细。旧 H_bag descriptor 路径未启用 compact marker，原有明细仍保留，说明优化没有外溢改变旧路径。

## 3. screening candidate 不等于 eligible causal pair

compact census 只负责低成本筛选，不能把候选数当训练样本数。只有 exact replay 同时满足 `same_state_start`、`action_changed`、`pair_complete`、`live_safety_pass`，并产生有效 direct completion delta，才写入 compact training rows；screening false positive 会保留失败原因，但不会进入训练。正式 campaign 从 174,868 个 I3 census 机会中均匀/long-wait 分层筛选 7,500 个候选，得到 **5,022 个 eligible exact primary pairs**；其中 long-wait 3,147、H_system 520，2,478 个 screening false positive 未进入训练。所有预注册数量门槛均通过，无需补量。

## 4. 按 task_id 分组切分，H_system 用 raw-bag 口径

- train/audit split 优先按原始 `task_id` 分组，缺失时才回退 `runtime_bag_id`，避免同一原始行李的不同 runtime segments 跨越训练集和审计集。该 ID 只用于切分，不进入 model-visible features。
- primary-pair 的直接标签仍是 affected runtime segment completion delta，避免偷换训练目标。
- H_system 的系统诊断优先使用 raw-bag `original_entry_mean_minutes` 差并换算为秒；仅在 raw-bag 聚合不可用时回退 segment cohort completion mean。H_bag 明确标记系统诊断不适用。对应自动化测试已验证同一 `task_id` 得到同一 split group，并验证 raw-bag H_system 差值优先。

## 5. 局部标签可以研究，但不足以接管完整 Route 动作

- 5,022 个 primary pairs 中，102 个 alternative 有益、28 个中性、4,892 个有害；全部 102 个有益 alternative 都出现在 wait age <30 秒的样本中，3,147 个 long-wait 组没有有益 alternative。这是描述性线索，不是可直接上线的规则。
- H_system 的 segment-cohort 与 raw-bag 聚合诊断 520/520 同号，但 affected runtime-segment 直接标签与 raw-bag 系统诊断有 59/520（11.35%）反号。这个差异证明局部 segment 收益不能冒充整件行李收益，raw-bag 只作为 veto/诊断。
- 三类正式模型都完成 grouped audit。最佳探索性结果是 tiny-MLP/F2：audit 3/3 proposal 有益、平均优势 +0.013793 秒、LCB90 +0.000136 秒，但支持数 3 低于门槛 5。更重要的是数据只覆盖 S4 对一个 primary alternative，没有覆盖每条合法边和 WAIT，因此结论是 `PRIMARY_PAIR_DATA_CONTRACT_NO_GO`，没有导出 policy，也没有运行 learned closed loop。
- 这不是“学习失败”。最窄下一步是先补完整 legal-edge + legal-WAIT 标签和独立 2x audit；在此之前继续堆模型、lookahead 或新控制框架都没有证据收益。

## 6. 小矩阵训练避开 tiny-BLAS 病态开销

本轮的小型线性、MLP 和 set scorer 运算规模很小，实测通用 BLAS 的 tiny-matrix 调用开销不合算。训练/推理热段改为数学等价的 `numpy.einsum(..., optimize=False)`，不改变模型结构、特征或优化目标；F0–F5 与三个正式模型 family 的自动化 campaign 测试通过。Standalone scorer 只保留复用接口，本轮不做第四套正式训练；该改动只针对小矩阵，不引入新的并行层。

## 7. 4x 门槛未过，因此不扩 BOLT-P，也不动 Source

既定 full-4x 解锁门槛是 60 秒至少完成 50,000 segments；当前最好的 E2 是 **27,760**。因此本轮只确认“事件开销下降且 bounded progress 未退化”，不运行或宣称 full-4x 容量闭合，不扩展共享单实例 BOLT-P，也不把 rollout farm 当作运行时并行框架。Route 学习尚无 closed-loop promotion 证据，所以 Source 仍保持冻结 A0；这是主动控制复杂度，而不是遗漏实现。

## 8. 故障证据只覆盖即时通知

两个受保护的 8,192-segment-prefix 即时通知故障回归都完整结束：pending-inflight repair 的受影响任务为 10/10，exact-lease repair 为 3/3；E0/E2 的逐任务 TTH 和 bounded action projection 一致，硬安全通过，events 分别减少 145,629 和 145,645。两例 physical fault-edge entry 都为 0。

这个证据边界只覆盖**即时故障通知**。延迟通知和丢失通知在 G4IRSF20 中仍明确为 `NOT_EVALUATED`，不能由上述结果外推。

## 当前边界

正式 Route campaign 已完成。本文件不把 7,500 个 screened 候选写成 7,500 个 eligible 样本，不把 5,022 个 primary S4-vs-one-alternative pairs 说成完整 legal action set，也不宣称 learned Route、Source 或 BOLT-P 已获提升资格。下一研究主线仍是 A0 + S4 + J2 + E2；E2 是事件发布优化，不是容量或业务 TTH 胜者。
