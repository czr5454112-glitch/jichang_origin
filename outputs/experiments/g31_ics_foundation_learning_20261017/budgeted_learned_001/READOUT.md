# P3：同一合法当前观察下的按需 K8 对照

## 执行与边界

- 一次原生 `mechanism/incumbent` 会话；父 Windows JobObject 硬上限 90 秒，实际 65.891 秒，正常退出 0，无重试。
- 预登记顺序：A 原 full32；B 共享语义规则 K8；同一 B 当前观察下的留机制场景线性模型 K8；B 原 full32 teacher；原有 retained-policy 继续物理执行。
- 两路 K8 都在 B teacher 之前评分，K 内含 incumbent 04。学习模型仅训练 `insufficient_advance` 和 `no_overlap`，不是事后从模型中择优。
- 两路都只是 advice，未接管 dispatcher、未提交 native 命令。环境检查回调前后 native digest 不变，并再次检查当前来源。
- 125 个导入项目源码及模型、模型副本、folds、训练登记的进入/退出 hash 校验通过。完整原生输入和 receipts/jobs/trays 与既有闭合 incumbent 基线逐字段完全一致。

## 实测结果

| 项目 | 共享语义规则 K8 | 留机制场景线性 K8 | 后置 B full32 teacher |
|---|---:|---:|---:|
| 请求候选数 | 8 | 8 | 32 |
| 独立当前上下文 / prefix engine | 5 | 7 | 16 |
| 实际 prefix resume | 6 | 9 | 23 |
| 实际 fork / suffix resume | 8 / 8 | 8 / 8 | 32 / 32 |
| source proof 使用 / 闭合 | 17 / 成功 | 17 / 成功 | 65 / 成功 |
| 完整 prediction 与 teacher 相同 | 8 / 8 | 8 / 8 | — |
| 未请求且未推演的候选 | 24 | 24 | 0 |
| 计算至封存 wall ms | 4003.4167 | 4888.0145 | 10280.5483 |
| 含导出及最后当前检查 wall ms | 4030.1519 | 4912.6517 | 未按此边界测量 |
| 含导出及最后当前检查 CPU ms | 4015.625 | 4750.000 | 未按此边界测量 |
| 最终建议兼容候选 | 04 | 04 | 原运行方法只查询 04；离线完整域参考另算 |

规则请求 `[4, 0, 2, 1, 16, 3, 18, 17]`；学习请求 `[4, 16, 20, 24, 28, 18, 17, 22]`。

这里的 prefix 数由实际请求集合分组决定，不能仅用 K 推断成本。两路均保留原来源、动态 freshness、完整克隆与隔离、逐件零容差保护及公开组件兼容约束。

## 质量与未实现收益

- full32 条件联合最优为 25，两路均未保留；各自条件保护后最优的 completion-sum regret 均为约 0.319 秒。
- 公开组件合同允许的完整域参考最优为 12，两路建议 04 的兼容域 regret 均为约 0.119 秒。建议 04 相对 incumbent 五件预测端点增量全部为 0。
- 联合条件参考 25 并不是已获对方承诺的可执行联合命令，不能把上述两种 regret 混为一谈，更不能当作实际原生收益。
- 本次没有观察到学习排序的质量收益。学习集合需要更多 prefix，本次测得耗时也更高；固定顺序单上下文不是 ABBA，不给出因果加速结论。
- outer-stage 计时中，规则/学习 `guarded_prefix_clone_and_rollout` 分别为 2373.1795 / 2983.3579 ms，包含嵌套来源检查，不能全部称作纯预测；source preparation+bind+setup 分别 919.7931 / 1005.3987 ms。排序阶段还含当前来源检查，不能当成纯 ranker 延时。
- 仍未达到 100 ms；未实现常驻服务级静态证明摊销、后续 fresh R1/R2 学习动作权或 RL 闭环；不预先降低阈值。

## 证据

- `plan.json`：不可变预登记、顺序、模型与 125 项源码 hash。
- `receipt.json`：父进程硬预算、exit code 和 worker hash。
- `worker_report.json`：逐候选完整 prediction hash 对照、结构计数、成本、regret 与退出 pins。
- `callback_complete.json`：teacher 之前生成的两路完整 advice。
- `native/raw.json.gz`、`native/receipt.json`、`native/acceptance.json`：原生闭合及真实轨迹。
- 专用测试：`../budgeted_001/probe_tests_002.xml`，17 项通过；provider 另有 37 项专用测试。

前一独立 K4 门保留在 `../native_001`，其默认规则权重与本门共享 L0 规则不同；独立对照为 `../budgeted_001/native_001_same_context_comparison.json`，不得用其排序结果冒充本门规则。
