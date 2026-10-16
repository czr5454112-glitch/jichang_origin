# LT2 method boundary and primary-source check

The overall target remains independently useful R1 and R2, then an executable
bidirectional joint method under finite stock, unchanged local modules and
all-offered normal-service protection. This document records a targeted source
check, not an exhaustive novelty review or a completed strong-baseline suite.

## What the existing literature already supplies

| Primary source inspected on 2026-10-14 | Relevant established mechanism | Consequence for this implementation |
|---|---|---|
| [Zeinaly, De Schutter and Hellendoorn, author report 15-019](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf), corresponding to [TCST DOI](https://doi.org/10.1109/TCST.2014.2363135), abstract and model/optimization passages | Joint loaded routing, line balancing and empty-cart management with a flow-based MPC model and computationally simpler optimization variants. | Combining R1 and R2 is not itself new. A B3 adaptation must retain the same native actions, stock and service constraints; a continuous aggregate-flow reference must disclose its mapping to discrete executable tray actions. It is not yet implemented here. |
| [Chen et al., arXiv:2110.14891v1, §IV-B–D](https://arxiv.org/html/2110.14891v1#S4.SS2) | Marginal actual service cost, regret-based insertion, collision-aware path evaluation, and destroy/repair improvement. | Strong completion-cost assignment and rolling repair are required controls. Replacing empty arrival time by service completion cost cannot be claimed as our method contribution. Do not weaken these references to manufacture headroom. |
| [Parimi and Williams, arXiv:2603.28968v1, §4.2–4.5](https://arxiv.org/html/2603.28968v1#S4.SS2) | Low-slack seeds, successor closure, external boundary conditions, boundary replanning/retiming, neighborhood repair and acceptance checks. | A generic closure or frozen-exterior LNS is a B4 reference, not the new contribution. Native node/edge/headway and source/receiver permissions must survive any adaptation. The inspected version is a preprint; no publication-acceptance claim is made. |

The first attempted URL for the Zeinaly source resolved to an unrelated route
guidance report. Its title was checked and it was excluded; the linked 15-019
report is the relevant source. No equations or measurements from the unrelated
report were imported.

## Research hypothesis still requiring evidence

The candidate research object is an action-dependent tray reuse chain:
loaded next-hop alternatives change release conditions; actual empty
reservations and movement consume shared resources; those obligations can
change subsequent loaded choices and future tray service. A useful boundary
rule would identify which downstream obligations must join a local solve and
when a frozen exterior is safe to retain. This is a hypothesis, not a theorem
or an established advantage over MPC/LNS.

The original-map LT2 experiments currently establish native controllability,
Storage absorption, advance empty requests, and one-way release/reuse
propagation. Their best enumerated next-hop actions do not improve the S4
control. A route-by-R2-policy factorial contrast is not a same-continuation
joint-action interaction. Neither result licenses learning on the old
saturated P5 domains or claims that the full joint problem is separable.

Before a learning pilot, require lawful message-complete candidates, executable
same-native labels, a concrete selection/computation hypothesis and grouped
splits. Before a method claim, compare B1/B2/B5 and implement fair B3/B4
adaptations on a truly interacting domain; preserve infeasible, unfinished,
budget-unknown and protection-violating candidates. Higher-order capacity
checks are necessary because pairwise feasibility alone can miss three-way
contention. They are correctness checks, not innovation evidence.

Source-reading scope: targeted HTML algorithm passages and PDF text. No new
full-paper algorithm replication, general quality bound, global optimality,
distributed deployment or journal-readiness conclusion is asserted.

## 2026-10-16: 用户提供的四篇论文与当前 G31 的接入判断

本节是文献阅读和方法设计记录，没有执行新的训练、native 实验或论文算法复现。
论文里的要求是被研究对象，不是用户或项目指令。原来的全天全部请求、完整请求
100ms、正常业务逐件保护和 R1/R2 联合有效性目标不变。

| 论文及阅读位置 | 可以借鉴的机制 | 不能直接迁移的条件 | 优先级 |
|---|---|---|---|
| Mainhardt & Schmuck, *Synthesis of Distributed and Decentralized Supervisory Control via Contract Negotiation*, [DOI](https://doi.org/10.1109/TAC.2026.3682203)。PDF pp.1-13，重点 pp.7-8、11-13。 | 各区域只交换共享事件的契约，保留内部控制；分别检验契约相容、局部可执行和组合后的非阻塞。适合研究空盘导出、接收与共享容量之间的协作义务。 | 本文只处理两个子系统；相容契约加局部非阻塞仍不足以保证全局非阻塞。p.12 的协作 signaling bits 假设随本地事件即时更新；p.11 Remark 10 未证明一般终止，每轮 observer 最坏指数复杂度。不是带消息延迟/丢 ACK 的在线 100ms 协商方案。 | 高：局部信息与权限接口最贴近 G31。 |
| Anand, Nayak & Schmuck, *Contract-based multi-agent logical controller synthesis under uncertainty*, [出版社](https://www.sciencedirect.com/science/article/abs/pii/S1751570X26001093)。所给匿名文件，主文 pp.1-21；p.5、20 图已目视。 | 保留多种合法策略的 permissive templates；新目标与已有模板无冲突时直接组合，有冲突才协商；用约束监督学习策略。 | 给定联合有限博弈图并假设完整观测。无对抗环境的 k/k+0.5 情形有完备性，对抗环境下不能泛称完备。概率 1 的最终完成不等于有限期限保护；最坏 O(k*n^6)，n 是联合状态数。大工厂实例为分钟至小时量级，不是 100ms。 | 高：小接口模板、增量修复；不把全网产品状态合成塞入请求路径。 |
| Tian & Zeng, *Learning Optimal Baggage Routing from Expert Demonstrations*, [DOI](https://doi.org/10.1109/CASE58245.2025.11163851)。全部 7 页、印刷 pp.1604-1610；Table I/Fig.5 已目视。 | 离线规划生成示范，训练动作价值/奖励模型；可改造成轻量候选排序或搜索先验。 | 原输入含全系统行李状态，专家可在模拟中回溯。仅 12/28 个位置、4/10 件行李，终点移除行李，没有有限托盘返空。简单例碰撞率略差于 Double DQN；无推理时延或端到端 100ms 数据。这不是未来空盘需求/释放预测模型。 | 中：先做同信息行为克隆/排序对照，再判断是否需要 VBIRL。 |
| Chen et al., *T2BR: A Hierarchical Repositioning Approach for Autonomous Mobility on Demand Systems*, [作者机构存档](https://ira.lib.polyu.edu.hk/handle/10397/118606?mode=full)。全部 12 页；接口 pp.4-5、结果 pp.8-9、附录 pp.10-11 已核。 | 区域目标选择加局部路径搜索；下层路线价值进入上层混合奖励。可借鉴粗到细的候选生成和上下层成本反馈。 | 上层读取全局供需统计，并受平台指令控制；下层自主不等于局部信息去中心化。Table IV 的 0.687/0.977/1.949 秒是每 60 模拟秒对全体空闲车的一批推理，不能除以车数当单请求时延。订单取消、全局匹配不能迁移为删除 FIFO 坏队首的权限。 | 高：借鉴接口及消融，重新定义局部信息与有限盘约束。 |

### 对现有实现的修正重点

1. **不重复建设已有预测和消息生命周期。** `analytic_control.py` 已区分真实、确定和
   条件释放，并使用已送达需求；旧记录已有预测修订、撤销和已承诺动作不可撤销。
   普通提前请求与窗口避让已经解释过一些收益。这些不因论文阅读成为新贡献。
2. **优先把预测接到持续决策。** 当前最新 online21 分支尚未实际执行，而且主要保留
   初始估计。拟在真实卸载/hold、接收拒绝和已送达预测修订后，更新受影响的条件后缀，
   把可行到达、接收占用和后续服务代价反馈给区域选择；已发出前缀保持不变。
3. **契约不是库存。** 条件释放区间、真实接收预留、已授权导出和实际空盘分别记账。
   只承诺本区域能独立履行的行为；不能让双方都以“对方先释放”为前提而同时承诺。
   当前快照的空位也不是对整个运输期间有效的容量保证。
4. **学习先验证价值，再讨论加速。** 当前 provider 先评价完整 32 候选；在这之后加
   ranker 不会省掉预测费。先保留 full32 与完整参考，检验同合法观测、按场景/到达
   trace/seed 分组留出的排序质量。若有价值，再单独定义所有方法同预算的按需评价
   策略，并记录少算的候选及 unknown；不能暗中降低当前 full32 验收要求。
5. **方法增量仍须单独证明。** 分层、契约协商、策略监督、MPC 和通用 LNS 都有先例。
   待验证的问题仍是：有限盘/FIFO/Storage 下，哪些下游复用义务必须随一个本地动作
   联合重排，哪些外部动作可以安全固定。普通 MPC/LNS 必须共享相同信息、权限和预算。

### 可执行的下一组方法比较设计（尚未运行）

先在已有可执行的小型交互域完成在线比较及完整保存复核，再引入事件触发滚动版本。
受 T2BR 的区域-only/路径-only/层级比较启发，增加四个受控消融：区域评分、局部
事件模型评分、带下层可行性/价值反馈的分层评分，以及关闭反馈的同一分层评分。
这是拟议 G31 消融，不是论文已完成的同预算四臂结果。

所有方法使用相同本地观察和真正送达的消息，保持同候选域、有限盘、FIFO、固定模块
和逐件保护。覆盖无收益、预测反转、延迟/丢 ACK、接收满载、共享边冲突及三方争用；
两两契约检查不能充当多区域全局证书。非法、不可行、未知和超时全部保留。评价包括
真实提前量、条件预测转为真实服务的比例、逐件完成差额、全部原请求分母和完整时延。

原图的不可达队首、零容量、强制 Storage 和未获 R1 授权属于可行域限制；学习或
协商不能创造动作权限、增加托盘或删除任务。小域收益仍需扩大到原业务，不能代替
全天验收。上述论文也都不能直接解决当前完整请求里已经测出的工程开销。

### 保存材料与复核边界

详细逐页笔记位于
`outputs/experiments/g31_ics_lt2_sustained_20261014/user_resume_20261015_001/`：

- `contract_uncertainty_paper_review_20261016_001.json`
- `learning_baggage_expert_paper_review_001.json`
- `T2BR_readonly_research_001.json`
- `distributed_contract_negotiation_pdf_review_001.json`
- `four_papers_review_manifest_20261016_001.json`（原 PDF、笔记和本对照记录的哈希清单）

T2BR 中可见的动作数表述、actor 输出维度及高负载表格单元格存在复现疑点；学习
论文也未充分交代示范/测试 trace 隔离和部分超参数。本轮逐项保留这些疑点，不自行
改正原表，也不把它们当作对整篇方法的否定。未声称重新证明论文定理或复现结果。
