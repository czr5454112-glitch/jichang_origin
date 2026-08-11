# G4IRSF21 文献证据与下一步简化方向

## 结论先行

五篇原始论文共同支持的不是“把 HCA* 换成另一个大型 MAPF 求解器”，而是：面向持续到达的取送任务，用短视窗/一步局部决策、邻接资源仲裁和有限通信换取实时性与扩展性。因此当前主线明确是 **A0 + S4 + J2 + E2**，应保持不变。文献启发的 **稀疏、慢更新、可关闭 directed-edge flow penalty** 仅是算法层后续候选；它必须先通过影子证据门，不能直接成为运行时控制器。

代码证据曾指向 **guarded scalar beacon payload**，但 G21 的交叉顺序短测只得到约 1–2% 的 events/s/完成量变化，events/completed 还略差，未达到 5% 保留线；该候选已撤回。这个负结果来自本项目实验，**不是上述文献的直接结论**。

当前最窄的数据推进是补齐真实 `WAIT` 反事实。G20 的 5,022 个 eligible Route 状态都恰有两条合法边，已有 S4 baseline 与 primary treatment 已覆盖全部合法 next-edge；缺口不是再造模型，而是用同一 checkpoint 上原生 I4 安全等待补成“全部一跳边 + 合法 WAIT”的局部选择集。

## 原始文献到当前主线的最小映射

| 原始论文 | 可转移的简单原则 | 对当前主线的支持 | 不能外推的边界 |
|---|---|---|---|
| [PIBT, IJCAI 2019](https://www.ijcai.org/proceedings/2019/0076.pdf) | 只协调相邻移动；短时间窗；冲突组互不影响时可并行；近邻通信即可。 | 支持 S4 的一步候选和 J2 的局部 owner/grant 边界，也支持 E2 减少无状态变化的重复通信。 | 论文的有限到达性质要求相邻节点处于长度至少 3 的环等拓扑条件；本机场有向图不能据此声称 PIBT 完备、无死锁或有限到达。当前 J2 也不是完整 PIBT。 |
| [RHCR, AAAI 2021](https://ojs.aaai.org/index.php/AAAI/article/view/17344) | Lifelong MAPF 不必一次规划到终点；只消解有限时间窗内冲突并周期适应新目标。 | 支持“有限承诺、持续修正”，而不是恢复全局 HCA* 长预约。 | RHCR 仍由集中式 Windowed-MAPF solver 重规划多 agent 路径；其最多 1,000-agent 仓库结果不能转移为本框架的去中心化或机场容量结果。 |
| [Traffic Flow Optimisation for LMAPF, AAAI 2024](https://ojs.aaai.org/index.php/AAAI/article/download/30054/31856) | 最短路本身会聚集流量；方向流、节点拥塞和反向流可作为轻量 guidance；在线 guidance 可 lazy 初始化和分批更新。 | 支持在 S4 之上研究一个很小的 edge-flow 修正项，并保持本地即时动作选择。论文也显示全量 heuristic 重算会超时，反而支持慢更新。 | 论文使用全体 agent guide paths、FOCAL Search 和迭代 refinement；其 10,000+ agent 结果不能证明本机场实现有效，也不授权复制完整 guided-PIBT 管线。 |
| [Distributed Planning with Asynchronous Execution with Local Navigation, AAMAS 2023](https://www.ifaamas.org/Proceedings/aamas2023/pdfs/p914.pdf) | carrier 独立规划；当前 node 只向相邻 node 请求下一资源；结果只有 move/detour/wait；延迟发生时异步局部修正。 | 与 J2 destination-grant 最直接一致：物理资源 owner 作邻接仲裁，Route 不读全局未来路径。E2 的按状态变化发布也符合有限局部通信。 | 论文依赖图定向、双连通主区加小树等条件，并引入 node-agent 表述；不应据此新增 actor 系统、重定向整张机场图或声称异步完备。 |
| [MAPD, AAMAS 2017](https://www.ifaamas.org/Proceedings/aamas2017/pdfs/p837.pdf) | 机场行李更接近持续到达的 pickup-and-delivery，而非一次性 MAPF；解耦方法在实时预算下可优于复杂集中方法的运行成本。 | 支持 A0 把持续订单送入系统、S4/J2 在线逐段处理，并把 service time、吞吐和积压作为主要证据。 | TP 的 token 实际保存所有 agent 路径、任务和分配；保证只适用于 well-formed MAPD。不能把 token、完整路径表或该完备性移植到当前有向输送网络。 |

这里的“支持”仅表示设计原则相容，不表示 A0、S4、J2 或 E2 等价于论文算法，也不表示论文数值在机场数据上复现。

## 明确不采用的复杂机制

- 不引入全局 token、全 agent 未来路径表、任务交换递归或同步 timestep barrier。
- 不引入 RHCR + PBS/ECBS、CBS、全局 Windowed-MAPF 或重新包装的 HCA*。
- 不补齐完整 PIBT 递归继承/回溯，也不为获得论文定理而重构机场拓扑。
- 不引入全体 guide path、FOCAL Search、LNS refinement、逐 agent 全图 heuristic 重算或新的训练/服务进程。
- 不为 AAMAS 2023 的“node agent”另造 actor 框架；现有 junction/resource owner 就是足够的逻辑边界。
- 不因文献报告大规模 agent 数就宣称本项目已获得相同容量；仍以本地 1x/2x/4x 完成量、TTH、积压、事件成本和故障安全为准。

## 算法层后续候选：稀疏慢更新 edge-flow penalty

最小形式是在 S4 已有候选分数上加入一个**有界非负小项**：只读取已实现中可直接累计的 directed-edge 近期通过量、等待/反向流证据；只在很慢的固定间隔更新少数高拥塞边，其他边保持零。Route 仍只选下一条边，J2 仍拥有最终 grant，A0/E2 不变；不保存未来路径，不新增全局预约，也不调用学习模型。

进入控制 A/B 前必须依次满足：

1. **机制门**：shadow 中 penalty 非零只集中于重复拥塞/反向流边；更新与读取开销相对 E2 主线可忽略，无逐 bag/逐 event 全图扫描。
2. **反事实门**：在 exact-state legal-action 对照中，受罚边的替代动作有足够支持，且不是 G20 那种仅 primary-pair、遗漏 WAIT/其他合法边的数据合同；局部收益不得被 raw-bag/system 诊断持续反号。
3. **安全门**：即时故障回归、物理 fault-edge entry、冲突/失败状态和 J2 grant 不回归；penalty 只能排序，不能绕过 shield/grant。
4. **业务门**：固定种子 1x 不恶化 mean/p95/p99；2x 必须改善 Route/network 时间或 raw-bag TTH，而不只是减少事件；再看 4x 有界完成量和 events/completed。
5. **简化门**：实现应是一个小状态表、一个低频更新点和一个 scorer 加项。若需要新线程、全局 future plan、复杂模型或第二套协调协议，直接停止。

若任一门失败，结论就是保持 **A0 + S4 + J2 + E2**，记录负证据，不继续调参。若全部通过，也只晋级为可关闭的研究策略，随后才做 1x/2x 闭环 A/B；文献本身不构成晋级证据。

## 不能外推的总边界

- 论文主要使用同步网格、无向图、仓库/机器人或特定定向图；本项目是有向机场输送网络、连续事件时间、服务时长、源队列与故障语义。
- 文献证明或实验不覆盖当前 E4/R3/P2/Q0/C0 资源边界，也不证明 v2-safe TTH gap、完整 4x 或真实机场容量。
- “去中心化”在不同论文中可能只是解耦规划、局部通信或可分布式实现；本项目仍需用实际全局读取、通信、事件和 owner/grant 计数证明，而不能只靠命名。
