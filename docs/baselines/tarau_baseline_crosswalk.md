# Tarău 文献基线语义对照

## 结论与身份

本文件只固定文献身份、当前代码语义和适配边界，不声明尚未运行的结果。

- `TARAU_LOCAL_2009`、`CIE_DH_2009`、`CIE_DH_REPLICA` 以及 Feng/CIE 对照中的去中心化启发式是同一文献基线家族，不得重复计数或重复运行。
- 当前代码中该家族的唯一可执行实现是 `FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED`；结果中必须使用 `FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED_NOT_EXACT`。
- `TARAU_DISTRIBUTED_2010` 尚不能精确复现。五个离线校准权重、`eta`/路线历史和机械开关状态与翻转时间未恢复。本轮实现并冻结了透明适配 `TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY`；它是 route-only common-runtime adaptation，不是原文 exact replica。

## 证据范围

| 来源 | 识别符 | 本文件采用的最强结论 |
|---|---|---|
| Tarău, De Schutter, Hellendoorn, *Route Choice Control of Automated Baggage Handling Systems* (2009) | DOI `10.3141/2106-09` | 路口所有的在线路线选择；本地启发式与预测控制的质量—计算代价权衡 |
| Tarău, De Schutter, Hellendoorn, *Decentralized Route Choice Control of Automated Baggage Handling Systems* (2009) | DOI `10.3182/20090902-3-US-2007.0036` | 本地输入/输出流与可选的邻居信息；低层安全另行假定 |
| Tarău, De Schutter, Hellendoorn, *Model-Based Control for Route Choice in Automated Baggage Handling Systems* (2010) | DOI `10.1109/TSMCC.2009.2036735`，分布式启发式见第 VIII–IX 节 | 本地启发式加有界邻居预测流；原模型有机械开关与最多两入两出假设 |
| 当前仓库 | `event_driven_junction.hpp` 中 `feng_dh_reimplementation_path_penalty` 和 `FENG_DH` scorer；`run_g4irsf35_full_population.py` 中的标签与配置 | 可执行的 2009 家族适配，但系数不是文献精确系数 |

2009 原式的可核验页码/方程号和 2010 的完整系数表尚未在本轮证据中恢复；下表因此将对应项标为 `missing`，而不伪造页码或精确公式。

## 文献—当前仿真 crosswalk

| 项目 | CIE-DH/Tarău-2009 原文 | Tarău-2010 distributed 原文 | 当前仿真字段 | 复现状态 | 适配理由 |
|---|---|---|---|---|---|
| 决策触发时刻 | 行李在路口离开前选择输出；页/方程锚点 `missing` | 事件驱动的路口控制（VIII–IX） | 节点事件中的 `apply_scorer` / `event_time` | A: `adapted`; B: `adapted` 已实现 | 用现有一次下一跳决策取代 DCV 开关微相位 |
| 路口输入状态 | 当前行李、候选续接路径上的移动/停止占用；精确字段 `missing` | 本地入/出流、行李优先级和邻居预测流（VIII–IX） | A: `scheduled_incoming`、`junction.queue.size()`；B 适配: direct-neighbor beacon 的 live/arrive/drain 投影 | A: `adapted`; B exact: `missing`, adapted spec: `frozen` | A 映射 MOVING/STOPPED；B 仅读 5 s 有界 beacon，不读全局预约 |
| 出口候选 | 当前路口可用输出/偏好路线；页锚点 `missing` | 原模型最多两条输出（VIII–IX） | 有向图中通过公共故障过滤的 `outgoing(u)` 与后续 `outgoing(v)` | A: `adapted`; B exact: `missing`, adapted spec: `frozen` | B 对高出度使用按节点 ID 稳定打破同分的 `argmin`，不硬编码二元开关 |
| 静态优先级 | 有路口/行李优先语义，可执行系数与页锚点 `missing` | 每条入边的静态优先级（VIII–IX） | 当前 Feng-DH scorer 不读取文献静态优先权重 | A: `missing`; B: `missing` | 不把 J2/M3 优先级冒充为文献参数 |
| 动态优先级 | 可执行定义/系数 `missing` | 基于当前流和预测到达的动态比较量（VIII–IX）；`eta` 与路线历史未恢复 | B 适配只使用 `Npred`；合流固定 neutral FIFO | A: `missing`; B exact: `missing`, adapted: `adapted` | 不从 S4/M3 借权重，也不伪造 `eta` |
| 移动/停止占用 | 停止行李惩罚高于移动行李；精确系数未公开 | 本地流/拥堵进入启发式；方程系数 `missing` | MOVING=`scheduled_incoming`；STOPPED=`junction.queue.size()` | A: `adapted`; B: `missing` | A 预先冻结为 moving=1、stopped=2，仅保留序关系 |
| 邻居预测流 | 本地版不使用 | 在有界 `tau_pred` 内从相邻路口预测进入流（VIII–IX）；精确窗口/更新/字段 `missing` | B 适配冻结 `tau_pred=5 s`，动态半径 2，beacon 携带 live/arrive/drain 投影 | A: `exact` 信息边界；B exact: `missing`, adapted spec: `frozen` | `Npred` 只由 direct-neighbor 5 s 有界 beacon 生成，不读全网任务或预约 |
| 预计卸载/到达时间 | 自由流续接时间加移动/停止拥堵惩罚；精确方程号 `missing` | 分布式启发式估计卸载/惩罚代价（VIII–IX）；精确可执行式 `missing` | A 的仓库适配式见下文；B 适配式见下文 | A: `adapted`; B exact: `missing`, adapted spec: `frozen` | 两个仓库式都明示标记适配，不写成原文精确式 |
| 开关翻转成本 | 机械开关语义与当前图不同；精确状态 `missing` | 依赖机械开关状态/翻转时间（VIII–IX） | 当前 runtime 无可对齐的机械状态；B 适配冻结 `switch_cost=0` | A: `adapted`; B exact: `missing`, adapted: `adapted` | B exact 因此阻断；结果必须披露 zero-switch-cost |
| HOLD 条件 | 选中出口的入口位置被停止行李占用时 HOLD；页锚点 `missing` | 依赖可行输出与开关状态（VIII–IX） | 公共物理执行器的入口/服务可行性与 HOLD/retry；B 合流为 neutral FIFO | A/B: `adapted` | 选路策略不得用 S4 第二候选偷换 HOLD，也不得用 M3 冒充 2010 优先级 |
| 故障处理 | 原文假定低层安全，无当前动态故障等价式 | 同样将安全置于低层（VIII–IX） | 公共的故障边过滤、R3 物理互斥和终点语义 | A/B: `adapted` | 安全层在所有 arm 保留，但不归因为文献 scorer 能力 |
| 信息半径 | 候选自由流续接路径上的占用；不应宣称严格一跳 | 本地加有界相邻路口预测（VIII–IX）；精确动态半径 `missing` | A 扫描确定性自由流续接路径；B 适配的 dynamic radius 固定为 2 | A: `adapted`; B exact: `missing`, adapted spec: `frozen` | A 范围大于 S4 一跳；B 必须审计半径与消息字节 |
| 参数与校准 | 只能确定 stopped > moving >= 0；精确系数 `missing` | 五个离线校准权重、`eta`/路线历史和开关语义未恢复 | A 适配值 1/2；B 适配冻结 `tau_pred=5 s`、radius=2、switch_cost=0、neutral FIFO | A/B: `adapted`; exact B: `missing` | 四个正式 cell 上禁止反向调参 |

## 当前 Baseline A 适配式

代码实际计算（不是文献精确式）：

```text
J_A(u,v,g,t)
  = travel(u,v)
  + H_service_aware(v,g)
  + sum_{r on deterministic free-flow continuation, r != g}
      q_r * (1 * scheduled_incoming_r + 2 * junction_queue_r)

q_r = max(node_service_time_r, minimum_service_seconds)
```

同分按下一节点 ID 稳定打破。该实现不读取 `source_queue`、`pending_release`、`completed` 或 `failed` 人口；也不读取 S4 的相邻服务日历、计划流入组合项或故障残差。它会读取完整候选续接路径上的实时占用，所以不是严格一跳基线。

## Baseline B 已冻结的 route-only 适配

```text
label: TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY

J_B(u,v,g,t)
  = tau(u,v)
  + min_{w in healthy outgoing(v)} [
      max(tau(v,w), (1 + Npred(v,w,t; 5s)) / mu(w))
      + Hff(w,g)
    ]

terminal special case:
  if w == g, continuation(v,w,g,t) = tau(v,w)

Npred: direct-neighbor 5 s bounded beacon live/arrive/drain projection
tau_pred: 5 s
dynamic_information_radius: 2
switch_cost: 0
merge_policy: neutral FIFO
high_degree_rule: stable argmin, then lowest node ID
eta_and_route_history: omitted because exact terms are unavailable
five_offline_calibrated_weights: omitted because exact values are unavailable
reproduction_label: ADAPTED_BASELINE_NOT_EXACT
```

其中 `mu(w)` 是 common runtime 中节点 `w` 的物理服务率。`Npred` 仅由直接邻居 beacon 中当前 live 数、5 s 内可达数与按 `mu` 可排空数得到；不得查询全网未来任务、预约表或 S4 服务日历。这一定义已在结果前冻结，但仍只是可归因的 common-runtime route-only 适配；缺失的原文项仍阻断 exact reproduction。

终点特例来自共同物理语义 `complete_on_goal_arrival=true`：到达目标即完成，不存在目标节点排队或服务。首轮实现错误地给 `w==g` 加入目标服务项，最小反例证明这会把真实更慢的路径排在更快路径之前；该轮全部结果已隔离，修正后以单一新二进制重跑。公共 `shield_reason()` 仍可读取 corridor/destination calendar 来执行所有方法共享的物理可行性门，但这些值不写入 Tarău 候选记录，也不进入其数值排序。

## 本轮不进入实验的方法

- Sohrt PTW 需要全路径握手/预留架构，与当前一次下一跳 common runtime 的控制边界不兼容，本轮排除，不作为失败运行。
- Sørensen DSP-100 仅放在相关工作中；它不是本轮新增的两个文献基线之一，也不用它替代 Tarău-2010。

## 声明边界

Baseline A 和冻结的 Baseline B 都只能标为 `ADAPTED_BASELINE`。Baseline B 的 exact reproduction 仍为 `BLOCKED`；已实现的 route-only 适配只能作为受控 P1 对照。任何当前 Feng-DH 输出都不能改标为 `EXACT_REPRODUCTION`，也不能把同一 2009 家族的别名包装成多个独立获胜基线。
