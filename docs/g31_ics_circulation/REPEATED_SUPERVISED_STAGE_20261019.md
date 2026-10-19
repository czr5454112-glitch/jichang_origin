# 重复决策小域：实际候选监督训练阶段（2026-10-19）

已完成一次登记后的真实 CPU 训练：`repeated_supervised_training_001`，3 个 seed、各 200 epochs、64×64 网络，子任务耗时 10.157 秒，父进程 11.485 秒，低于 180 秒硬限。训练完成只表示条件预测标签的监督拟合闭合，不是多步 RL，也不证明原生策略收益。

## 数据和标签

- 训练：`A1_three_prefer3_002` / `three_reuse_blocker_11_1`，2 次实际当前条件预测，3 个候选，共 6 行。
- 开发：`A1_four_prefer3_001` / `four_reuse_blocker_12_5`，3 次实际当前条件预测，3 个候选，共 9 行。
- 每个 split 仅 1 个独立输入案例。同一决策的候选、同一案例的多个决策均相关，不能当作 15 个独立实验。
- 标签为完整业务集合的冻结条件完成预测 `-Σ max(0, predicted_completion - observation.at)`；来源是实际送达信息、当前合法证据及分离的条件预测器。它不是候选真实执行回报、Bellman target 或 native oracle。
- 物理可用但被完整逐件保护拒绝的 `prefer_8` 可用于监督学习其较低分数；实际执行仍必须被保护层拒绝。预测向量和保护参考值不进入 actor 特征。
- 历史 `A1_three_prefer3_001` 只有未知候选预测，得到 0 行训练样本；两次未知报告的排除记录保存在转换审计中并绑定至最终计划，未把 unknown 填成 0。
- 正式测试 `three_reuse_blocker_12_1` 未读取；没有根据开发结果选择 seed 或重新拟合。

## 实际结果

| Seed | 初始训练 MSE | 最终曲线 MSE | 训练 MAE | 开发 MAE | 开发 RMSE |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1701 | 41.068007 | 0.000004432 | 0.001811 | 7.747290 | 9.795796 |
| 1702 | 41.720607 | 0.000010034 | 0.002923 | 7.508492 | 9.590265 |
| 1703 | 25.226384 | 0.000008356 | 0.002527 | 7.424095 | 9.429053 |

误差单位是上述聚合剩余完成时间标签的秒数。训练误差很小，开发外推误差明显较大，不能声称具有可靠跨案例泛化。训练与开发的全部 5 次决策中，允许执行的 `native_default`、`prefer_3` 标签均相同；100% teacher-best match 和 0 regret 因此不证明模型学会了有收益差异的选择。报告明确给出 differentiated decisions=0、相应匹配率=null。

## 权重和来源审计

独立审计重算了 3 个模型的标准库前向推理、全部训练/开发 MAE/RMSE、仅训练数据计算的 123 维 normalization、标签聚合和训练行摘要，验证每个模型有 12,161 个有限参数，21 个真实记录曲线点覆盖 epoch 0 至 200。三个 seed 的参数不同，实际 checkpoint 与评估记录相符。

已核对 278 个父任务源文件 pin 及其归档、模型内容摘要、全部产物文件摘要、真实子进程退出码 0、Windows Job 收容与先收容后放行、原生数据完整闭合和来源不变。审计使用冻结的公开观察 feature extractor，推理与指标算术独立重算；未调用 fit、native 或正式测试。

## 预登记的原生消费模型

下一次受控消费验收固定使用 **seed 1701**，这是读开发指标之前协议中登记的 deployment seed，不能因另外两个 seed 的开发 MAE 较低而替换。

- 文件：`outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_training_001/model_seed_1701.json`
- 文件 SHA256：`9476653bff68c763c846a19069d7d2e42ecc5997fc813be4ebadcc410dff5e44`
- 模型内容 SHA256：`0f8fdbe72a1399793c339614feda54d9f98501fee8c68cbc873dc4e9ec4f97f7`

消费验收须记录当前完整候选 mask、模型分数、实际 chosen、提交后的 ACK/实物事件和逐件业务完成结果。网络只为当前允许动作排序，不能修改或替代完整逐件保护、未知状态处理、源过期检查或真实 native 约束。首先验证“实际消费了固定权重且排序决定 chosen”，其结果不能自动升级为 RL 或策略收益。

后续新增 hold3 等业务案例应另行登记。只有存在真实不同选择、合法同 owner 连续状态、实际事件奖励、完整后继绑定和逐件非退化保护，才能进一步讨论多步 RL；本批监督数据本身尚未提供该证据。

## 可复核文件

- [预登记协议](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_protocol_001.json)
- [冻结训练计划](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_plan_001.json)
- [历史排除与实际转换审计](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_conversion_001/report.json)
- [训练 receipt](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_training_001/receipt.json)
- [全部 seed 评估](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_training_001/evaluation.json)
- [独立审计脚本](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_review_001/audit.py)
- [独立审计报告](../../outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/repeated_supervised_review_001/report.json)
