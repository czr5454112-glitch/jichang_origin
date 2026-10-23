# S4 等待估计候选实现（2026-10-23）

本轮在成熟 `EventDrivenJunctionRuntime` 内增加可关闭的 S4 等待评分。保留逐跳选路、J2 节点预约、E2 事件处理和 PIBT 原子提交；不新增线路容量、节点容量、空托盘、实体尺寸、驱动分区或固定路径执行器。恒速行程 `length / speed`、基础 `service_duration()`、实际服务完成事件和终点规则均沿用原配置。不同评分可能选择不同路线，所以总体实际行程或服务量可以改变；单次设备操作时长不会被预测拥堵拉长。

原生 Java 的规则与论文声明的区别见 [原生等待规则核验](FENG_NATIVE_WAITING_RULES_AUDIT_20261023.md)。本实现是 G31 路由评分候选，不等于重现 Java 的完整路径规划和源侧重试流程，也不证明两者的全部执行细节已经相同。

**旧 G31 已经使用到达时间。** 旧 S4 在 `now + travel` 查询目标服务日历的最早可用窗口；正式 G31 已打开直接合流邻居日历可见性。此次不能描述为“首次加入 ETA”。旧式评分为：

```text
legacy = travel + H + Q + I + entry_wait + calendar_wait
```

`Q` 是目标节点完成服务后等待下一跳的队列长度；`I` 是目标的全部已安排流入数。它们各以每件一秒的数值直接加入旧评分，并非测得的实际等待。新模式的主要区别是替换这一 `Q + I` 项，区分服务窗口等待与服务后的出流等待。正式 R3 没有 corridor 日历，`entry_wait = 0`，因此 `eta_calendar` 与旧正式 S4 的主要差别就是移除 `Q + I`，而不是新增原先不存在的日历机制。

**公式和信息边界。** 设决策时刻为 `t`，旅行时间为 `d`，基础节点服务时长为 `s`，当前入口最早可用时刻为 `e`：

```text
w_entry = max(0, e - t)
a = t + w_entry + d
b = target_calendar.earliest_start(a, s)
w_calendar = max(0, b - a)
r = b + s

eta_calendar = d + H + w_entry + w_calendar
eta_flow = d + H + w_entry + w_calendar + w_post
```

没有对应日历时 `b = a`。新模式直接读取当前一步目标的服务日历；这种可见性属于 ETA 模式本身，不受旧 `enable_s4_direct_neighbor_merge_calendar_visibility` 开关屏蔽。正式比较仍保持该旧开关为 `true`。旧候选字段及执行层许可逻辑不变；新字段只供评分和审计。这里的窗口是当前快照下的预测，不能代替 J2 最终许可，也不预先承诺整条未来路线。

`eta_flow` 只使用目标现有服务后队列，以及该目标日历中已经承诺、将在 `r` 前完成服务的非终点任务数 `C`。当前候选自己被排除，全部 `scheduled_incoming` 不再直接作为一秒罚项。预计服务后等待采用局部流量近似：

```text
w_post = max(0, (Q + C) * h - max(0, r - t))
```

`h` 来自该节点实际成功离开服务后队列的间隔。一次成功离开的样本为 `max(min_gap, depart_time - max(previous_departure, enqueue_time))`，以免把队列空闲时期误当成阻塞；EWMA 的固定系数为 `0.25`。`min_gap = max(dispatch_headway, minimum_service_seconds)`，没有样本时的先验为 `max(min_gap, base_service)`。当前队首尚未离开的时间 `t - max(previous_departure, front_enqueue_time)` 作为 `h` 的下界。到达实际终点不预测服务后队列等待。

**近似的风险。** `C` 只限定哪些已承诺操作会在 ETA 前结束，没有逐件模拟它们何时入队：公式允许从现在起消化这些工作量，因此对接近 ETA 才完成的流入可能偏乐观。EWMA 也不能预知未来的 J2 竞争、其他源任务、故障或下游路线；长时间阻塞后的样本可能使它短期偏保守。它是秒量纲的路由估计，不是精确未来排程、排队模型证明或保证收益的策略。正式收益必须分别由各地图完整 1× 对照决定，不能从公式形式推断。估计遍历当前邻居队列及本地日历，未扫描全局任务或事件带；局部队列很长时仍可能增加计算量。

**误差审计只覆盖提交后的预测。** 普通离开、J2 离开和成功 PIBT 批量离开都在不可回滚的 `EDGE_ENTER` 发布点更新流量统计。三条路径的进入时刻就是当前提交时刻，不是未来预订时刻；失败或回滚的尝试不会训练 EWMA。

每次已经提交到非终点节点的跳转，重新记录对该节点服务后等待的预测；待该任务下一次成功离开该节点，以 `departure_time - junction_enqueued_at` 得到实际值。对照代理量是提交时目标 `Q` 的一秒/件罚项，**不含 `I`，也不是整个旧 S4 分数**。`eta_calendar` 在这个审计阶段预测的服务后等待为零。

因此 MAE/RMSE 评价的是“已经选中并提交的下一节点的服务后等待”，不包含提交前已经发生的上游 J2 等待，不包含基础服务或旅行时间，不评价所有未选候选，也不等于决策当时整个候选等待分数的校准。样本受所选路线影响。尚未从预测节点离开的任务只计 `censored_forecast_count`，不当作实际等待为零；已结算样本的误差须与截尾数量一起读。`candidate_prediction_count` 是既有候选评分次数，并不是具有真实结果标签的校准样本数。

**接口。** C++ 配置 `EventDrivenJunctionConfig::s4_wait_estimator` 和 Python `czr005.cpp_backend.g4irsf11_event_runtime_from_records(..., s4_wait_estimator=...)` 接受 `legacy`、`eta_calendar`、`eta_flow`。默认 `legacy`，新模式要求 S4。保留既有请求和其余配置，只改变此字段即可形成评分消融：

```python
from czr005.cpp_backend import g4irsf11_event_runtime_from_records

request = dict(existing_native_request)
request["s4_wait_estimator"] = "eta_flow"
result = g4irsf11_event_runtime_from_records(**request)
```

实验入口 [experiment.py](../../scripts/experiments/g31_feng_alignment/experiment.py) 对应参数为 `--s4-wait-estimator`。新模式的候选输出增加 `predicted_entry_wait`、`predicted_merge_wait`、`predicted_post_service_wait`、`projected_arrival`（均为秒）；C++ 另用 `s4_wait_prediction_enabled` 标记。旧输出字段保持原含义。

新模式的 `summary.s4_wait_metrics` 输出 `commit_forecast_count`、`resolved_forecast_count`、`censored_forecast_count`、预测及旧 `Q` 代理量各自的 MAE/RMSE/bias、`actual_post_wait_mean`、`flow_departure_count`、`candidate_prediction_count` 和固定 `ewma_alpha`。bias 定义为预测减实际；没有已结算样本时误差字段为零占位，不能解读成已验证零误差。`legacy` 不输出这组新增字典字段。

实现位于 [event_driven_junction.hpp](../../cpp/ics_core/runtime/event_driven_junction.hpp) 与纯辅助头 [s4_wait_estimator.hpp](../../cpp/ics_core/runtime/s4_wait_estimator.hpp)。新统计及未结算预测按值进入检查点，只有新模式加入确定性摘要。独立回归见 [test_g31_eta_wait.cpp](../../cpp/tests/test_g31_eta_wait.cpp)，覆盖 ETA/日历空隙、服务后队列分离、空闲与阻塞统计、唯一通路下实际 J2 时序不变以及 ETA 状态的检查点续行。全量结果及原版本逐任务等价回执由本轮实验目录记录，本文不预先宣称吞吐优势。
