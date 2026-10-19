# B1 静态航班计划与需求预测训练

本模块实现用户采纳的 2026-10-19 反馈中 B1 主线。它不修改既有 FlightContext、43/52 维模型或原生环境，不训练策略或执行原生动作。实际训练是否完成，以统一启动器输出目录中的 `receipt.json` 为准；本文件不是训练成功证明。

## 数据和因果边界

- 原件 `legacy/jichang_origin_readonly/inputdata.txt` SHA-256 为 `0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87`。28,506 条记录、360 个 `(STD,end,Unloader)` 历史组、7 个原始入口。已只读核验所有 EntryTime ≤ STD；导出时再次逐条强制核验，违反即停止。
- 静态计划仅暴露不透明组标识和 STD，组类别明确为 `historical_group`。`published_at=None`，实验中假设 `received_at=0`；不能解释成历史真实发布时间。计划从已发生任务中反推，可能遗漏零行李航班，不能声称完整真实时刻表。
- 实际到达时刻、原始注入入口、loader 和原始组关联保存在 `private/flight_label_index.jsonl`。运行时 `foundation_flight_forecaster` 不导入数据读取器或原生对象，也不打开文件。
- 主模型输出 7 个 `legacy_start_0/1/2/3/4/5/53` 区域，表示原始数据注入区域。每个计划组的 `planned_injection_region=None`。这 7 个入口与 151 节点机场 owner 的关系必须另行显式适配；不能用读取最终组袋数的 `balanced_assignment` 当合法预先信息。
- 按父组 STD 切分：训练 STD ≤ 43200，开发 43200 < STD ≤ 57600，测试 STD > 57600，分别 153/75/132 组。训练标签必须在 43200 前闭合；开发/测试分别只评分该集合父组，早到的测试父组也不会进入开发统计。跨开发/测试闭合边界的预测窗口被清除，但没有删除任何物理任务。
- 只有一个历史模拟日，不能报告跨日泛化。三 seeds 用于块自助抽样的不确定性估计，不冒称三次独立训练。

## 模型与接口

`foundation_flight_training.fit` 对训练父组×区域计数矩阵进行一次 Gamma-Poisson 矩估计，包含零计数组；区域历史到达相对 STD 分布仅由训练组估计。Gamma 使用 shape/rate；区域份额已包含在各区域计数先验中，不能再乘一次份额。没有训练样本的区域使用明确标注的汇总回退。CDF 采用 60 秒箱，支持域 [-86400,0]。

运行时调用：

```python
from scripts.experiments.g31_ics_circulation import foundation_flight_forecaster as flight
prediction = flight.predict(context, checkpoint, now=now, owner=owner,
    observed_counts=None, bin_seconds=60, horizon_seconds=1800)
baseline = flight.recent_rate_forecast(checkpoint, now=now, owner=owner,
    arrival_events=delivered_past_arrivals)
```

`predict` 只计算未来 `(now+edge_i,now+edge_i+1]` 的新到达需求，不把预测值写进库存。默认计数 None 保持先验；缺失计数不等于已观测零。计数更新要求公开到达消息已建立组身份、完整历史从 0 开始，并注明真实公开消息或显式合成实验消息。当前没有证明原生公开事件具备组关联，因此主评估采用 `flight_prior_only`。`flight_synthetic_observed_counts` 仅是标明身份字段由实验供给的辅助结果。

返回 schema `g31.foundation.new_demand_forecast.v1`：

- `forecast_origin`、相对 `bin_edges_seconds=[0,60,...,1800]`、绝对 `absolute_bin_edges`。
- `new_demand_mean_by_region` 每区域 30 个箱均值；`uncertainty_by_region` 保存方差和 90% 区间。
- `window_summaries_by_region[region]['60'|'300'|'900'|'1800']` 保存累计窗口 mean/lower/upper/variance/level。累计方差保留共享强度的不确定性，不能直接相加逐箱方差。
- 模型内容 SHA、context SHA/版本、映射版本、时间基准、训练闭合和模型冻结时刻、计划原始接收时刻、计数观测截止时刻。
- `native_execution_authority=False`、`predicted_inventory_is_actual=False`、缺失掩码、校准状态。缺失/过期计划返回 None 向量和缺失掩码，不返回零。

后续 now 变化时重新积分绝对未来区间，保留原接收时刻；不把旧箱改名冒充新预测。90% 区间对多个独立 Gamma-Poisson 项作矩匹配，属于未校准模型区间；报告实际覆盖率，不保证覆盖率。

## 固定预算和产物

`foundation_flight_training.make_plan()` 生成计划，绑定四个源模块的 SHA 和原始数据 SHA。由 root 统一启动器登记后启动：

```text
python -m scripts.experiments.g31_ics_circulation.foundation_flight_training --plan <B1_plan_001.json> --output <fresh output directory> --admission <token>
```

worker 在读取计划/数据前阻塞 stdin admission；父启动器负责硬超时。固定总预算 600 秒，拟合 120 秒，60 秒×30 箱，评分步长 300 秒。先验和参数选择预先冻结，测试不参与选择。Bootstrap seeds 1701/1702/1703，各 200 次，以连续 6 个预测起点（1800 秒）的循环移动块保留窗口重叠关系；仍不支持独立日置信声明。

每次运行必须使用全新输出目录，保留原件。产物包括 public/static_flight_plan.json、private/flight_label_index.jsonl、flight_split_manifest.json、flight_forecaster_checkpoint.json、training_history.json、forecast_predictions.jsonl、private/forecast_evaluation_labels.json、forecast_evaluation.json 和 receipt.json。评估分别列出各区域/60、300、900、1800 秒窗口 MAE、偏差、低估量、计数 NLL、90% 覆盖率和区间宽度；预测分布 NLL 明示矩匹配及 `1e-12` 概率下限。无计划基线使用合法已收到的区域到达消息和冻结历史率，不消费 STD。

完整原生闭环消费、机场 owner 映射和真正多步策略改进需要另外的原生证据，本训练成功本身不能替代这些验收。

## 首轮实际训练和独立审计

统一预算启动器已完成 `outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/B1_training_001`。`receipt.json` 状态为 `completed_forecaster_training_and_causal_evaluation`，总墙钟 127.189 秒，其中闭式拟合 0.03794 秒；计入训练的是 153 个父组、12,549 袋。后续时间主要用于生成和评分预测。训练历史保留七个区域的计数 NLL（2.910–3.609）与实际拟合参数。它是一次闭式统计模型拟合，不是三次神经网络训练。

独立标准库审计 `cycle_001/B1_review_001/audit.py` 和 `audit_report.json` 通过 104,599 项检查：原件、公共计划、私有标签、父组切分、源文件/产物 SHA、全部原始任务身份、训练零计数组、Gamma 矩参数、训练 CDF 和预测的时点/缺失/无权能声明。审计没有导入项目训练器、预测器或原生模块。定向单元测试共 62 项通过，其中新预测模块 28 项、原 FlightContext 34 项。

开发集统计人口为 75 个父组、5,658 袋、43 个预测起点；测试集为 132 个父组、10,299 袋、91 个预测起点。以下是七区域的等权平均 MAE（袋/区域/起点），不是原生 owner 实现的业务收益：

| 集合与方法 | 60 秒 | 300 秒 | 900 秒 | 1800 秒 |
|---|---:|---:|---:|---:|
| 开发：冻结航班先验，计数 None | 1.738 | 4.427 | 7.227 | 11.446 |
| 开发：无计划近期率 | 1.949 | 6.498 | 12.799 | 22.887 |
| 测试：冻结航班先验，计数 None | 1.632 | 5.059 | 12.304 | 23.458 |
| 测试：无计划近期率 | 1.810 | 6.026 | 15.493 | 30.836 |
| 测试：合成组关联计数辅助结果 | 1.437 | 4.005 | 7.188 | 12.636 |

测试 1800 秒平均 MAE 差值为 -7.377 袋（表面下降 23.93%）。但三个 seed 的移动块 90% 自助抽样区间分别为 [-15.408,+1.073]、[-15.037,+1.585]、[-15.153,+0.637]，全部跨零。不能声称已证明稳定优于基线。更不能把这些同一天、重叠窗口的统计推成跨日泛化或原生动作收益。

区域结果有明显差异：测试 1800 秒，原始入口 0/1/2 的航班先验 MAE 为 27.86/27.97/27.81，差于无计划基线 22.43/22.47/22.41；入口 3/4/5/53 才较好。因此不能按测试误差挑有利 owner 来证明 C 线成功，后续 receiver 选择必须沿用独立冻结规程。

测试 1800 秒主先验偏差为 +4.026 袋，90% 区间实际覆盖率为 71.43%，平均宽度 53.972 袋，区间尚未校准。合成计数组关联辅助结果不能当成原生当前可用结果。统计评估中两种方法收到的到达消息均限定于所属父组子群；这种 evaluator 供给的子群消息流不是已经证明存在的原生公开消息接口。真实闭环必须从公开、已收到的 owner 消息构造输入。

流程上先审查开发结果，随后明确冻结首模型、暂不实施替代校准，再读取测试误差。本轮不回写参数、不按测试表现重选模型。固定首模型可用于后续 C 线动作消费验证，但上述误差和可见性限制必须保留。
