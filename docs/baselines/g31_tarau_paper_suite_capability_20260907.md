# G31 / Tarau 论文实验执行能力审计（2026-09-07）

本审计只审现有实现和新适配接口，不运行完整人口实验，不改变旧源码、旧 runner 或旧结果。两地图、1×/2×、十个共同种子属于新的实验设计；旧六格 Tarau P1 和旧六十格 G31 不能按坐标名称冒充新实验。

## 可以执行什么

| 能力 | 现有接口 | 科学边界 |
|---|---|---|
| 名义速度 1.5 / 2.5 / 3 m/s | `edge_records` 的速度与同速度预计算势函数 | 各系统相同输入速度的基础比较；不是速度偏差 |
| 全天断链 | `fault_windows(u,v,start,repair,delay,drop)` | 需要先冻结断链映射、知情时间、不可达袋口径；不能给不同方法不同源端删袋规则 |
| 观测/调度延迟 | `legacy_observation_bias_max_seconds`, `legacy_observation_bias_seed` | 不是物理运行速度偏差，不能把 1/2/3 秒称为真实 10/20/30% 速度变化 |
| 独立名义预测与随机实际运行速度 | **旧 ABI 没有** | 不得仅改所有边的 effective speed 后宣称实现动态速度实验；需要新冻结的执行器机制 |
| 逐段完整终态 | `summary_only=False` 返回所有 `bags` | 新适配必须原样保存，不能再只归档 summary / PASS 布尔值 |
| 全程事件/决策轨迹 | `trace_limit`, `event_trace_limit`；负值表示不设数量上限 | 内存中保留后返回，整日全量很大；有限采样必须披露截断，不冒充完整路径 |

## 两种旧速度“偏差”都不能直接冒用

`run_g4irsf31_map2_bias.py` 和南宁同族明确冻结 `U(0,k 秒)`，其中 `k=deviation_percent/10`，物理速度仍等于标准速度。其前身 `run_g4irsf27_bias_experiments.py` 明确称为非精确观测延迟重构。

实际 C++ 在 `process_service_complete` 后，按 `(seed, runtime_bag_id, visit ordinal)` 确定性抽样，把后续 `ArriveJunction` 与拥堵广播事件推迟；这不改边的运行速度，而且延迟会推迟控制器下一次处理。它也不是一个已经证明与原论文传感器误差完全一致的模型。

`run_g4irsf26_paper_experiments.build_speed_graph` 曾把物理边统一设为较慢速度、势函数保留标准速度。但运行时候选的直接边成本、预约、提交和到达仍共同调用 `graph.edge(...).travel_time()`。因此它至多分离了预计算势函数的速度；并没有独立的实际边用时与预测边用时，更没有按袋/边/访问号可配对的随机真实扰动。

当前 `cpp_backend.g4irsf11_event_runtime_from_records` 没有 speed-event、realized-travel 或独立 nominal/actual 参数。新物理机制若增加，必须新二进制 SHA、新源码冻结、零扰动等价门以及小规模因果验证；不能继续标成旧 `b00fd178…`。

## G31 与 Tarau 的身份

当前正式 G31 使用 S4、service-aware 静态势、strict local descent、直接邻居 calendar、M3 / JIT fair aging deadline、E2，且到自己的 goal 时完成。过去正式运行二进制 SHA 为 `b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5`。

`configs/baselines/tarau_distributed_2010.yaml` 的正式名是 `TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY`，已明确 `exact_reproduction: false`。原始 switch-in 权重、航班优先级、分支比例、机械 switch 状态均不完整。现有实现包含邻居拥堵 beacon、服务率、静态剩余时间，排除 G31 的 strict descent 与路由评分中的后继 calendar。可行性 shield 仍使用共同执行器的预约约束。

旧 P1 比较为共同 M1 / JIT FIFO 下的路由规则隔离，不是 G31 原生 M3 系统与原始 Tarau 完整系统。旧 P1 Tarau 二进制 SHA 为 `17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279`，不能把其数值和 b00 G31 跨二进制、跨输入拼成 matched pair。

建议新四方法主表诚实名为“G31 系统 / 修复 HCA / CIE-DH V5 披露假设重构 / Tarau 路由适配 + 共同 C++ 执行与 M1 仲裁”。这是工程系统比较；不能称四个原论文完整系统的精确复现。若另做纯路由 P1，G31 也切换到相同 M1，且必须作为单独消融身份，不代替主表 G31。

## 故障公平合同必须显式选择

旧 `run_cie_fault_specials.py` 不是任意四算法通用故障驱动。它仅限原始 1× 的四个注册故障，并在一些比较中把“surviving graph structural values + 源不可达预拒”作为共同条件。源不可达预拒保留固定分母但减少实际送入 C++ 的段集合；它不能被隐蔽地只赠给 G31。

新合同应逐格记录：有向断边集合、发生/修复时刻、可知时间、地图对应关系、是否事先使用 surviving graph。建议主实验全天已知断链时四方法拥有相同静态可用拓扑信息，全部原始袋仍在固定分母。若实际执行层预拒不可达段，必须由共同调度层生成、单独标为拒绝证据，不能伪造 native bag 行。若采用各方法自己的故障发现和恢复策略，则需要报告不同机制，并把结果解释为系统比较。

## 新适配与审计要求

拟新接口 `scripts/eval/run_g31_tarau_paper_suite.py`，仅写新的 `paper_suite` 输出命名空间。输入 spec 绑定 workload identity 原始字节 SHA、raw/canonical/map SHA、两地图与负载/种子、方法/仲裁、速度、场景及协议 SHA、二进制 SHA、轨迹限额和固定终止时刻。未实现物理扰动必须拒绝运行，不能降级替换。

新归档至少保存完整 `native_payload.json.gz` 与独立 `bags.jsonl.gz`，其中保留 native `task_id / segment_id / runtime_bag_id / start / goal / final_node / release / admitted / finish`、等待/旅行/服务分解、`short_history`，以及全部实际返回的 events / decisions / hold attempts 等字段。`short_history` 默认只保留最近 8 节点，绝非全程路径。完整 payload 的未压缩内容 SHA 和压缩文件 SHA 都应保存。

独立审计按 canonical segment ID 精确 join，拒绝缺段、重段、外来段、task/OD 不一致及已完成袋错误 goal。原始袋只有全部业务段完成才完成；主 THT 为每原始袋各段 `finish - canonical D` 的和，native `finish - admitted` 另列。任何未完成时全人口 THT 不用幸存者均值代替；2×是否无条件 NA 必须在新协议中明确，不能无声继承旧 180 表政策。TH 使用固定终止时刻和全部原始袋分母。

档案 PASS 仅表示身份、段集合、目标、终态账目和选定指标可重算；不是连续物理几何安全或每 tick 无碰撞证明。

## 只读依据

- `src/czr005/cpp_backend.py:631`：ABI 与单一 edge speed。
- `cpp/ics_core/graph/graph.hpp:26`：`travel_time = length / speed`。
- `cpp/ics_core/runtime/event_driven_junction.hpp:7333`：服务完成后的观测延迟；`:7396` 确定性抽样。
- `cpp/ics_core/bindings/czr005_cpp.cpp:4732`：逐袋字段与短历史。
- `scripts/eval/g4irsf31_map_adapter.py:300`：速度覆盖、service-aware potential 与 G31 请求。
- `scripts/eval/run_g4irsf35_full_population.py:57`：Tarau 路由差异与 neutral M1；`:463` 明确应用规则差异。
- `scripts/eval/run_cie_fault_specials.py:310`：故障结构值、预拒集合及比较边界。
- `scripts/eval/run_g4irsf26_paper_experiments.py:294`、`scripts/eval/run_g4irsf31_map2_bias.py:1`：两种旧非精确速度协议。
