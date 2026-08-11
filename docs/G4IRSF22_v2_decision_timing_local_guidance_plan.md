# G4IRSF22-v2 深度主线方案

## 从“当前路口换动作”转向“拥堵形成前的局部引导”：决策时机、局部信息价值与选择性学习

**English subtitle:**<br>
Decision Timing, Local Value of Information, and Selective Congestion Guidance for Decentralized Airport Baggage Routing

**Repository:** `czr5454112-glitch/jichang_origin`<br>
**冻结基线分支:** `codex/g4irsf21-execution`<br>
**冻结基线提交:** `95766fcc7806133de88c883c8d1a6aaed7c47a06`<br>
**建议新分支:** `codex/g4irsf22-execution`<br>
**Draft PR base:** `codex/g4irsf21-execution`<br>
**当前远端状态:** PR #6 open / draft / mergeable；GitHub Actions Run #67 success<br>
**当前正常流量主线:** `Source A0 + Route S4 + Merge J2 + Event E2`<br>
**唯一机场地图:** 原始真实 `map2.json`<br>
**任务流:** 只使用原始项目的任务构造逻辑，在相同地图上扩展 1×、2×、4×<br>
**核心任务:** 用逐接口、严格局部、可学习的一步策略替换原项目 HCA* 完整路线规划，并使系统适应更大的持续任务流

---

# 0. 为什么需要重做 G22 设计

上一版 G22 过早把主线收敛为“训练局部延迟预测器”。这个方向可能有价值，但结合 G11—G21 的完整证据，它还缺少两个更前置的问题：

1. **当前决策点是否真的还有可利用的动作自由度？**
2. **即使提供更准确的局部拥堵信息，当前动作是否还能改变系统结果？**

如果这两个问题没有先回答，直接训练延迟模型可能再次出现：

```text
模型预测得不错
→ 但仍然复制 S4
→ native mutation 为 0
→ 或者改动作后反而有害
```

G20 已经出现过这种问题：

```text
5,022 个 exact-state Route 对照
有益 102
有害 4,892
中性 28
```

G21 又显示，在一批 1× 完整三动作状态里：

```text
另一条合法边：16/16 有害
WAIT：16/16 有害
```

所以真正需要先验证的不是“能否训练更复杂的模型”，而是：

> v2-safe 在 2× 的剩余优势，究竟来自当前路口的动作选择、提前一个路口的动作选择、合流服务顺序，还是它的中央未来预约所提供的信息优势？

G22-v2 的中心思想因此改为：

```text
先定位“动作发生在哪里才有价值”
→ 再测“多看多少局部未来信息才有价值”
→ 最后才训练最简单的学习器去逼近这部分价值
```

---

# 1. 从 G4IRSF9 到 G21 的完整项目脉络

## 1.1 G9/G10：v2-safe 强，但并非真正去中心化证明

v2-safe 在原始任务和更高任务流上表现很强，且不调用完整 A*。但是它仍保留：

- 中央任务循环；
- 一件行李连续生成到终点的未来路径；
- 全局未来时间窗写入；
- `one_per_epoch` 式源端整形。

因此它证明的是：

```text
学习/规则选边可以替换 A* 的搜索部分
```

而不是：

```text
真正的一步事件驱动去中心化框架已经击败中央协调
```

v2-safe 应继续作为强对照和“中央协调补贴”的测量对象，但不能重新进入新方法运行时。

## 1.2 G11：第一次真正事件框架失败，暴露“拆中央协调容易，补局部协调很难”

G11 真正去掉未来路径和全局预约后：

- 只完成 3,114/28,506 件完整行李；
- 完成 12,125/43,603 segments；
- 大量 backlog、deadlock、starvation；
- 最大节点利用率却只有约 16%。

这说明失败不是模型推理慢，而是系统大量时间处于：

```text
资源实际空闲
但局部协议没有让正确行李前进
```

G11 的主要教训：

1. 不能只把中央预约删掉；
2. 必须补上本地服务机会、owner/grant、短 lease 和真实竞争边界；
3. 普通 backpressure 如果未校准，可能比不用更差；
4. 当时所谓 PIBT-lite 只是同一行李扫描备选边，不是真正多行李协调；
5. 资源容量和方向语义若过度保守，会把物理吞吐压低。

## 1.3 G12/G13：框架能够完整运行，差距收敛到很小的时序协调成本

经过资源语义和事件流程修复，F2 在 1× 完整运行：

```text
28,506/28,506 bags
43,603/43,603 segments
0 conflict
0 unsafe
0 full A*
0 future route
```

相对 v2-safe 只慢约：

```text
1.1347 s/bag
```

这证明：

> 真正的一步事件框架并不是方向错误；它已经能够几乎追平保留中央预约优势的旧栈。

但这时运行的“智能”仍主要是旧 G4E/F2 scorer，新的局部协调并未真正升级。

## 1.4 G14/G15：从“猜动作”转为 exact-state 因果数据

G14 的正式 action-changing labels 为 0，说明没有真正可执行的训练标签。

G15 修复后取得：

```text
2,172/2,172 eligible action-changing labels
I3/I4 各 1,086
H_system 256
0 future leakage
0 safety failure
```

最重要的机制结论：

```text
I3 换边直接代价约 +42.487 s
I4 等一个自然机会直接代价约 +0.354 s
```

同时 56.25% 的 H_system pair 影响了其他 segments，最大传播到 365 个 segment。

教训：

1. 换边是高风险稀有动作；
2. WAIT 是较温和的协调动作，但并不自动有益；
3. 当前行李收益和对邻居的影响必须分开；
4. 不能只看系统全局均值接近零；
5. 学习必须高精度、低覆盖、允许 abstain。

## 1.5 G16/G17：直接学 WAIT/换边和 Source 排序都没有过门

G16 的 H5：

```text
网络时间改善约 0.0585 s/bag
源端等待增加约 0.1496 s/bag
最终慢约 0.0910 s/bag
```

这说明一个局部动作虽然让进入网络后的行李略快，却改变了下游占用节奏，使源端更难放行。

G17 又证明：

- I1 source 模型训练但未授权；
- eager G2 在请求到达时提前占位，导致真实竞争机会为零；
- 4×/8×/16× 被容量或事件执行边界截断；
- in-flight fault lease recovery 是有效的真实成果。

教训：

> 问题主要是服务时机和资源竞争边界，而不是继续换模型结构。

## 1.6 G18：JIT merge 是重要机制胜利，但学习 Merge 几乎没有额外收益

G18 把 Merge 改成：

```text
请求先进入 bounded pending
→ 等自然 service slot 到来
→ 再决定谁先通过
```

J2 在 2× 明显优于 eager J0/J1。

同时 J7 第一次真正接管正常流量 Merge 动作：

```text
43,603 full 中 owned 3,500
真实改变 154
```

但相对 J2：

```text
mean 仅改善 0.004653 s
p95/p99 不变
events +228
```

教训：

1. 正确的动作 seam 比复杂模型更重要；
2. 一个强简单规则可以吸收绝大多数收益；
3. nominal ownership 不等于有价值的 action mutation；
4. 不应继续把大量预算投入 Merge 模型。

## 1.7 G19：S4 用很少局部信息取得最大正常流量突破

S4 使用：

- candidate queue；
- scheduled incoming；
- corridor next-available；
- target next-available；
- travel time；
- static potential。

它只改变了：

```text
90 / 27,418 matched Route actions
约 0.328%
```

却在 2× 将：

```text
mean TTH 851.864 s → 337.843 s
source wait 502.462 s → 54.666 s
p95/p99 同时大幅改善
```

这是项目最重要的正常流量结果之一。

它说明：

> 少数关键分流动作决定了大规模拥堵，而不是每个接口都需要复杂推理。

与此同时：

- learned Source mutation = 0；
- learned S2 Route mutation = 0；
- process-isolated rollout P8 有约 5.3× 加速；
- 单机场内部并行仍未证明。

## 1.8 G20：事件开销下降，但普通 Route 替代动作几乎都不好

E2 在保持 1×/2×业务结果不变时：

```text
总事件减少约 16%–17%
beacon 减少约 40%–42%
```

但 4× 60 秒完成量只提高约 2.9%。

这说明：

```text
软件重复事件是问题的一部分
但不是 4× 的主要全部原因
```

Route 因果实验：

```text
5,022 exact-state pairs
有益 102
有害 4,892
中性 28
```

且直接 segment label 与 raw-bag/system 方向存在约 11.35% 不一致。

三类学习模型都未获得正式授权。

## 1.9 G21：动作合同补完整，进一步证明 1× 普通状态不应乱动

G21 证明：

- G20 的 5,022 个状态已经覆盖全部合法 edge；
- 真正缺少的动作只有 native WAIT；
- 24/24 group、48/48 treatment 完成；
- 保留的 16 组三动作中，另一边和 WAIT 都全部有害；
- 4 个 H_system WAIT 没有系统收益；
- lean-S4 和 scalar-beacon 约 1%–2%，被撤回。

因此最新稳定主线仍是：

```text
A0 + S4 + J2 + E2
```

---

# 2. 从整个轨迹得出的五个核心判断

## 判断一：框架方向基本正确，当前不是“重新造框架”的时刻

G11 的框架失败已经被 G13、G18、G19 大幅修复。

当前已经具备：

- 一步事件决策；
- 本地 owner/grant；
- JIT merge；
- 安全 shield；
- 有界 PIBT fallback；
- fault lease recovery；
- 1×、2×完整运行；
- 独立 rollout 并行。

所以 G22 不应：

```text
再重写一套事件循环
再造第二套 supervisor
再恢复中央路径规划
```

## 判断二：当前主要矛盾不是模型太小，而是学习目标和决策时机不对

G20/G21 的数据说明：

```text
在当前决策点随便改边或WAIT，通常已经太晚或没有必要。
```

v2-safe 的优势可能来自：

1. 更早知道某条走廊未来会堵；
2. 更早改变上游分流；
3. 更早改变 source release；
4. 通过未来预约提前改变 merge 顺序。

因此 G22 必须先找“有价值的干预发生在哪里”。

## 判断三：不能再用普通动作分类作为主学习目标

有益样本过少，普通 accuracy 会奖励“永远保持 S4”。

学习应改为：

```text
先预测局部短期代价/拥堵价格
再只在高置信、高价值状态偏离 S4
```

但必须先证明“准确的局部短期信息确实有价值”。

## 判断四：需要在训练前做“局部信息价值上界”

如果给策略一个完美的 15/30/60 秒局部未来摘要，仍然无法从所有合法动作中选出比 S4 更好的动作，那么：

```text
再训练任何局部预测模型都不会解决问题。
```

这个上界实验比直接训练模型更便宜，也更有辨识力。

## 判断五：剩余差距必须被拆成 Route、Merge、Source 和未来预约四部分

当前只知道：

```text
S4 2× = 337.843 s
v2-safe 2× = 247.385 s
gap = 90.458 s/bag
```

但不知道这 90.458 秒主要来自：

- 上游分流时机；
- 合流服务顺序；
- source release；
- 多步未来预约；
- 资源语义；
- 或物理容量。

G22 的主要任务是建立这个“协调优势账本”。

---

# 3. 文献给出的最小、可转移启发

本轮只借鉴原则，不搬复杂算法。

## 3.1 PIBT：一步局部动作和优先级继承是合理的，但只适合保底

PIBT 证明了：

- 每一步只决定相邻动作；
- 优先级继承可处理局部阻塞；
- 具备去中心化实现可能。

但其有限到达保证依赖特殊图结构。当前机场是有向、带服务时长和容量的真实输送网络，不能移植其完备性结论。

因此：

```text
PIBT继续作为稀有互锁恢复
不作为普通拥堵调度器
```

## 3.2 RHCR：有限视窗和频繁修正有价值，但不能引入中央 Windowed-MAPF solver

RHCR 的可借鉴部分：

```text
不必一次承诺完整未来
只看有限时间范围
不断滚动修正
```

不采用：

```text
中央Windowed MAPF solver
全体agent路径
周期性全局重规划
```

## 3.3 TFO：自由流最短路会制造拥堵，轻量 guidance 可能比复杂搜索更重要

TFO 的主要启发：

- 只看自由流距离会让大量 agent 聚集到相同走廊；
- congestion-aware edge guidance 可以提高 lifelong throughput；
- PIBT 仍可保持一步执行。

不采用：

- 为所有行李生成 guide path；
- FOCAL search；
- LNS refinement；
- 全局路径流量反复重算。

## 3.4 OGGO：实时交通可用于更新 guidance，但全图动态权重和全对最短路太重

OGGO 表明：

- 最近 edge usage 和当前任务分布可用于更新 guidance；
- 动态 guidance 在任务分布变化时可能优于静态 guidance；
- 但频繁重算启发表会显著增加运行时。

因此本项目只借：

```text
最近局部使用量
+ 短期到达需求
→ 一个有界局部 guidance scalar
```

不借：

```text
全图 guidance graph
全对 shortest-path table
大参数优化管线
```

## 3.5 对本项目的最简映射

```text
TFO/OGGO 的 congestion guidance
        ↓ 简化为
每个候选下一节点的局部短期服务缺口

RHCR 的 bounded horizon
        ↓ 简化为
15/30/60 秒离线 value-of-information 和线上短期预测

PIBT 的 local coordination
        ↓ 保持为
真正互锁时的 bounded fallback
```

---

# 4. G22-v2 的总体方法

建议阶段候选名：

```text
S5-LG
Selective Local Guidance
选择性局部引导
```

它不是一个全新框架，而是在 S4 上加一个很小的局部 residual：

```text
score(candidate)
=
S4_score(candidate)
+
local_guidance(candidate)
```

其中 `local_guidance` 可以依次来自：

1. 简单确定性公式；
2. 单调线性模型；
3. tiny MLP。

任何不确定状态：

```text
local_guidance = 0
保持 S4
```

模型不输出完整路线，只评价当前合法邻边或 WAIT。

---

# 5. G22-v2 的四层因果定位阶梯

这是本轮最核心的设计。

## Layer A：当前 Route 决策点

在 2×真实拥堵状态：

```text
S4 edge
其他所有合法 edge
WAIT one natural service opportunity
```

回答：

> 行李已经到达这个路口时，还有没有更好的动作？

## Layer B：前一个真实分流点

若 Layer A 无收益：

```text
回溯该行李之前最近一次有多个合法动作的真实 Route decision
```

从该 exact checkpoint 比较所有合法动作。

回答：

> 是否应该在拥堵形成前一个路口就分流？

注意：

```text
这是改变更早的一步动作
不是规划两步路线
```

## Layer C：目标 Merge 服务顺序

若 Route A/B 都无收益：

```text
在真实 J2 pending set 中比较谁获得下一 service slot
```

回答：

> 路线已经对了，问题是不是谁先通过？

## Layer D：Source ADMIT/HOLD

仅当 gap attribution 显示 source release 仍是主要原因时：

```text
ADMIT current front
或 HOLD one natural opportunity
```

不重新做已经证明 0 mutation 的 top-K bag reorder。

---

# 6. Stage 22A：建立 2× 协调优势账本

## 6.1 目的

先回答 v2-safe 的 90.458 秒优势来自哪里。

## 6.2 对齐边界

使用完全相同的：

- 真实地图；
- 原始任务生成逻辑；
- 2×输入；
- bag/task identity；
- release semantics记录。

v2-safe 只作离线对照。

禁止把 v2 未来路线或预约表作为新策略输入。

## 6.3 输出四类差异

### Source

- 入网时间；
- source wait；
- admission顺序；
- 同一source的短期放行节奏。

### Route

- path hops；
- 第一次方向分歧；
- branch热点；
- detour；
- network travel/wait。

### Merge

- 到达merge时间；
- pending竞争；
- service winner；
- merge wait。

### Coordination/Reservation residual

在 source/route/merge解释后仍剩余的差异。

## 6.4 Congestion episode

不只看孤立状态。

对每个主要热点建立：

```text
拥堵开始
→ 队列增长
→ 峰值
→ 排空
```

每个 episode 记录：

- owner/node；
- 开始/峰值/结束时间；
- queue slope；
- incoming ETA；
- service rate；
- S4/v2 divergence；
- 受影响 bags；
- upstream branch；
- merge winner变化。

## 6.5 最低覆盖

目标：

```text
至少 32 个真实 congestion episodes
覆盖至少 6 个热点 owner
覆盖多个 time blocks
覆盖 direct/storage-in/storage-out
```

不是为了统计漂亮，而是为了防止所有实验只落在一个节点或一段时间。

---

# 7. Stage 22B：2× current-point 完整动作集

## 7.1 Pilot

```text
256 exact-state groups
```

四层各约 64：

- high target queue；
- high calendar wait；
- high merge contention；
- S4/v2 divergence 或 near-tie。

## 7.2 每组动作

```text
S4 baseline
所有其他 shield-legal edge
合法 WAIT
```

## 7.3 Horizon

全部：

```text
H_bag
```

至少 64：

```text
H_system
```

## 7.4 信号门

不是机械要求某个精确比例，但至少应看到：

```text
>= 8 个明确 beneficial treatment
分布于 >=3 个热点
分布于 >=2 个时间块
H_system 不持续反号
```

### 有信号

扩展到：

```text
1,024–2,048 groups
```

### 无信号

不训练 current-point action classifier，立即进入 Layer B。

---

# 8. Stage 22C：提前一个真实分流点

## 8.1 目标

针对：

- current-point 全部动作无益；
- 最终进入 2× p95/p99；
- v2-safe 明显更快；

的行李，找到之前最近一次 multi-action Route decision。

## 8.2 Pilot

```text
256 precursor groups
```

## 8.3 动作

仍是：

```text
S4 edge
其他合法 edge
WAIT
```

后续全部回到 S4+J2。

## 8.4 需要回答

- 当前点无解的状态，有多少在前一决策点可解？
- 改善来自 reroute 还是 WAIT？
- 改善是否只是把拥堵移到另一处？
- raw-bag/system是否同向？
- 是否能解释 v2-safe优势的可观比例？

## 8.5 有信号后扩展

```text
1,024–2,048 groups
H_system >= 128
```

---

# 9. Stage 22D：Merge service-order 因果实验

只在 Route current/precursor 都无足够信号时运行。

## 9.1 真实动作集

在一个自然 JIT service opportunity：

```text
J2 winner
其他 pending request
```

不制造不存在的候选。

## 9.2 最多三个规则

```text
J2 baseline
oldest-first
deadline/slack + age
```

可增加一个：

```text
downstream-clearance + age
```

但不超过四个。

## 9.3 Pilot

```text
256 real contention groups
```

若真实 candidate_count>1 不足：

```text
MERGE_ACTION_FREEDOM_INSUFFICIENT
```

不训练模型。

---

# 10. Stage 22E：局部信息价值上界

这是训练前必须完成的门。

## 10.1 目的

回答：

> 如果我们能够完美知道未来几十秒的局部拥堵，能否选出比 S4 更好的当前动作？

如果答案是否定的，训练预测器没有意义。

## 10.2 离线 oracle 信息

只在反事实实验中使用，禁止作为 runtime 输入：

```text
未来 5 秒候选节点 queue area
未来 15 秒 queue area
未来 30 秒 queue area
未来 60 秒 queue area
未来 service completions
未来 incoming count
未来 next-service deficit
```

## 10.3 Oracle ranking

对每个 action group，比较：

```text
S4 ranking
perfect 5s local oracle
perfect 15s local oracle
perfect 30s local oracle
perfect 60s local oracle
```

## 10.4 关键输出

- oracle 是否选择真正 beneficial action；
- 不同 horizon 的 precision；
- 可获得的 mean utility上界；
- 能关闭多少 v2 gap；
- 当前点和 precursor 的差异；
- 一跳和二跳局部 oracle 的差异。

## 10.5 决策

### Oracle 无价值

若即使 30/60 秒完美局部信息也几乎无法超过 S4：

```text
关闭局部预测学习
```

说明限制来自：

- 动作自由度；
- 资源服务机制；
- 或需要更早动作。

### Oracle 有价值

找最短有效 horizon 和最小有效 radius。

例如：

```text
15秒一跳已有大部分上界
```

则禁止训练 60秒二跳大模型。

---

# 11. Stage 22F：只训练最简单的局部 guidance

只有 oracle gate 通过后启动。

## 11.1 G0：确定性 service-deficit 公式

```text
guidance
=
current queue / recent service rate
+ short ETA demand / recent service rate
+ current calendar wait
```

使用截断和简单归一化。

## 11.2 G1：单调线性模型

要求方向合理：

- queue更多不应预测更少延迟；
- incoming更多不应预测更少延迟；
- service rate更高不应预测更多延迟；
- next-service更晚不应预测更少延迟。

## 11.3 G2：tiny MLP residual

只在 G1 明显欠拟合时运行。

建议：

```text
20–30 inputs
2 hidden layers
small width
delay head
harm head
uncertainty
```

## 11.4 G3：小型 candidate-set scorer，条件式

只在：

- candidate_count>2 的真实状态足够；
- 或 WAIT/多动作支持足够；

时运行。

## 11.5 不采用

- 大 GNN；
- Transformer；
- PPO/MAPPO；
- full RL；
- guide paths；
- 全图 guidance graph；
- all-pairs shortest path重算；
- LNS/FOCAL；
- 多步 online search。

---

# 12. 学习数据设计

## 12.1 稠密 observational 数据只作辅助

每次 S4 实际动作可提供：

- local queue；
- incoming；
- service rate；
- realized next-resource wait。

它可以训练延迟预测器。

但它只覆盖 S4 选择过的动作，存在选择偏差。

因此：

```text
不能只用 observational data 训练 policy
```

## 12.2 exact-state counterfactual 是动作授权依据

未选择动作的收益必须来自：

```text
same checkpoint
same future releases
same fault schedule
one action changed
```

## 12.3 两类数据分工

### Dense chosen-action rows

用于：

```text
延迟预测预训练和校准
```

### Exact action groups

用于：

```text
action advantage
harm risk
policy authorization
```

## 12.4 H_system 只作稀疏 veto

不是每个动作都跑 full system。

优先：

- predicted high benefit；
- predicted high harm；
- model uncertainty；
- local/system可能反号；
- v2 divergence；
- precursor high leverage。

---

# 13. Runtime feature contract

## 13.1 S4 core

- candidate queue；
- scheduled incoming；
- corridor next-available；
- target next-available；
- travel time；
- static goal progress。

## 13.2 新增最小趋势

- queue utilization；
- 10s/30s queue slope；
- recent service rate；
- capacity-block rate；
- time to next service。

## 13.3 ETA bins

- 0–5s；
- 5–15s；
- 15–30s；
- 30–60s。

## 13.4 Bag features

- deadline slack；
- wait age；
- leg type；
- recent reverse/repeat；
- detour count；
- previous hold/override count。

## 13.5 二跳摘要

默认关闭。

只有 oracle 证明二跳相对一跳有明显增益时开启：

- max service deficit；
- max pressure；
- TTL age。

## 13.6 禁止

- absolute task ID；
- bag ID；
- absolute source/goal ID 作为 codebook；
- future full route；
- future reservation；
- global queue；
- post-hoc TTH；
- teacher action作为运行时输入。

---

# 14. 离线评价

## 14.1 不以普通 accuracy 为主

主要看：

- beneficial precision；
- harmful applied rate；
- expected utility；
- regret；
- calibration；
- held-out hotspot/time/leg；
- outside-target S4 preservation。

## 14.2 基础授权建议

```text
beneficial precision >= 0.80
harmful applied rate <= 0.02
outside-target S4 preservation >= 0.99
utility lower bound > 0
至少多个独立热点有正支持
```

不需要高覆盖率。

## 14.3 低置信

```text
guidance correction = 0
保持 S4
```

---

# 15. Research closed-loop

## 15.1 固定其余部分

```text
Source A0
Merge J2
Event E2
R3/P2/Q0/C0
Supervisor/Shield
```

只改变被因果证据支持的那一层。

## 15.2 候选

```text
C0 S4
C1 deterministic guidance
C2 monotonic linear guidance
C3 tiny MLP guidance
```

若真正信号在 Merge 或 Source，则候选层相应移动，不同时修改三个层。

## 15.3 Ladder

```text
144
512
2,048
8,192
1× full
2× full
4× 60s bounded
```

## 15.4 Coverage

```text
1%
5%
10%
25%
```

仅在持续稳定时增加。

稀有高杠杆动作不要求 100% ownership。

## 15.5 必须报告

- opportunity；
- eligible；
- applied；
- distinct mutation；
- beneficial/harmful mutation；
- S4/J2/A0 fallback；
- abstention；
- shield reject；
- mean/p95/p99；
- source/route/merge/network；
- events；
- wall/CPU/RSS。

模型被调用但不改变动作，不算性能实验。

---

# 16. 2× 的正式胜负门

当前：

```text
S4 2× mean      = 337.842709 s
v2-safe 2× mean = 247.384666 s
gap             = 90.458043 s
```

## Direction pass

至少：

```text
相对 S4 mean 改善 >= 2%
p95/p99不恶化
```

## Gap-10

```text
mean <= 328.797 s
```

## Gap-25

```text
mean <= 315.228 s
```

## Gap-50

```text
mean <= 292.614 s
```

## Strict v2 win

```text
mean < 247.384666 s
```

同时：

- 1×不明显退化；
- 全量完成；
- 0 conflict/unsafe/deadlock；
- 0 full A*；
- 0 future route/global scan。

---

# 17. 4× 和并行的正确优先级

## 17.1 先改善 2×，再投入 4× full

G11 已经证明在基础算法不稳定时直接扩规模会浪费大量时间。

因此：

```text
没有 Direction pass
→ 不跑完整 4×
```

只允许 60 秒 matched slice。

## 17.2 4× bounded 指标

- completed；
- released；
- backlog；
- simulated-time progress；
- events/completed；
- CPU category；
- RSS；
- top bottleneck owners。

## 17.3 解锁更长 4×

候选相对 baseline 至少：

```text
completed +10%
或
events/completed -10%
或
simulated progress +10%
```

才跑 180 秒或 resumable full。

## 17.4 Rollout parallelism继续使用

P1/P2/P4/P8 用于：

- action groups；
- oracle；
- H_system；
- model evaluation。

这是已验证的真实收益。

## 17.5 单实例并行条件式

只有：

```text
live independent width >= 2
且
feature/model compute share >= 10%
```

才做 P1 parity → P2/P4。

不要为了“去中心化应该并行”而强行给轻量 S4 加线程。

---

# 18. 故障机制

当前 fault lease recovery 是已验证资产。

G22 只需对最终候选回归：

- pending fault；
- in-flight fault；
- WAIT期间fault；
- guidance stale generation；
- proposal后fault；
- repair re-entry。

故障工作不超过本轮约 10%。

硬门：

```text
0 failed
0 conflict
0 unsafe
0 stranded
0 unresolved deadlock
0 A*
0 future route
0 global scan
```

---

# 19. 当前明确不应再做的事情

根据 G11—G21 证据，本轮禁止重复：

1. 普通 Source top-K 排序模型；
2. 继续增加 Merge learned ownership；
3. 深化 PIBT 作为普通排队解决方案；
4. 在 1×普通状态随机换边；
5. 只做 primary-pair action classifier；
6. 直接训练缺乏 oracle 上界的局部延迟模型；
7. 连续测试约 1% 的微优化；
8. 提高 event/wall cap冒充扩展性；
9. 新建大而全分布式 runtime；
10. 新地图；
11. 全图 guidance；
12. 恢复中央 future reservation。

---

# 20. 预注册 Pivot

## Pivot A：current point 有信号

训练 current-point selective guidance。

## Pivot B：current point无信号，precursor有信号

学习提前一个真实路口的 guidance。

## Pivot C：Route无信号，Merge有信号

只改 J2 排序，不动 Route。

## Pivot D：Source有信号

只做 ADMIT/HOLD，不做 bag reorder。

## Pivot E：oracle有信号，现实特征不足

训练最简单预测器。

## Pivot F：oracle也无信号

形成：

```text
ONE_STEP_LOCAL_INFORMATION_CEILING
```

说明当前一步动作和局部信息无法解释 v2优势。

下一阶段只能研究：

- 更早 action seam；
- bounded 2-hop forecast；
- resource semantics；
- physical capacity。

不是继续堆模型。

---

# 21. 防止忙而无功

以下任何一项都不能单独视为 G22 完成：

- Git/CI；
- 新 census；
- 256 pilot；
- dataset；
- oracle report；
- model file；
- offline accuracy；
- shadow；
- 144/512；
- 4× 60 秒；
- fault pass；
- no-go报告。

G22 必须完成一条完整链：

## 有信号链

```text
gap/episode定位
→ action timing找到正收益
→ oracle证明信息有价值
→ 简单guidance
→ native mutation
→ 2× full
→ v2 gap结果
```

## 无信号链

```text
current point no-go
→ precursor no-go
→ merge/source条件式 no-go
→ local oracle no-go
→ ONE_STEP_LOCAL_INFORMATION_CEILING
```

不能在 WAIT 再次失败后结束。

---

# 22. 建议提交序列

```text
G22-A  2× coordination-gap ledger + congestion episodes
G22-B  current-point complete action sets
G22-C  precursor action sets
G22-D  conditional Merge/Source causal screen
G22-E  local value-of-information oracle
G22-F  deterministic/linear/tiny guidance
G22-G  native closed-loop ladder
G22-H  1×/2× full and v2-gap decision
G22-I  conditional 4× and parallel
G22-J  fault regression and final decision
```

每个主提交必须至少带来：

- 新业务归因；
- 新 exact-state action证据；
- 新 oracle上界；
- 新模型；
- normal-flow mutation；
- 2×结果；
- 4×进展；
- 有证据的 pivot。

不能只有文档、hash、seal或重复测试。

---

# 23. 最终必须回答的 25 个问题

1. PR #6 与 G22 CI 状态；
2. v2 90.458秒差距按 Source/Route/Merge/Residual如何分解；
3. 主要 congestion episodes 在哪里；
4. current-point有多少 beneficial动作；
5. WAIT在2×是否有益；
6. alternative edge在2×是否有益；
7. precursor是否比current point更有信号；
8. 改善是否来自更早reroute；
9. Merge顺序是否还有收益；
10. Source ADMIT/HOLD是否有收益；
11. 5/15/30/60秒local oracle上界；
12. 最短有效horizon；
13. 一跳和二跳信息差异；
14. oracle能够关闭多少v2 gap；
15. dense observational数据只如何辅助；
16. deterministic guidance结果；
17. monotonic linear结果；
18. tiny MLP结果；
19. native action mutations；
20. beneficial/harmful比例；
21. 1×结果；
22. 2×结果及gap关闭比例；
23. 4×是否获得有意义改善；
24. 是否需要单实例并行；
25. 最终是 learning gain、mechanism gain，还是 local-information ceiling。

---

# 24. G22-v2 的成功定义

## SUCCESS-A：SELECTIVE_LOCAL_GUIDANCE_GAIN

简单 guidance 在 2× 严格优于 S4，1×和尾部不退化。

## SUCCESS-B：GAP_25 / GAP_50 / STRICT_V2_WIN

按上述阈值关闭中央协调差距。

## SUCCESS-C：MECHANISM_LOCATION_FOUND

即使模型尚未赢，也明确证明收益位于 precursor、Merge 或 Source，并产生可执行下一步。

## SUCCESS-D：ONE_STEP_LOCAL_INFORMATION_CEILING

current、precursor、Merge/Source和perfect local oracle均无足够收益，证明现有动作和局部信息已接近上限。

这同样是重要进展，因为它阻止项目继续在错误模型上消耗时间。

---

# 25. 最终战略结论

项目已经完成的不是“一个普通学习选路器”，而是一套逐步成熟的去中心化运行底座：

```text
事件驱动一步执行
+ JIT merge
+ S4局部Route
+ E2低通信
+ 本地安全和fault recovery
+ exact-state因果实验
```

当前真正欠缺的是：

> 找到中央 v2-safe 提前协调所提供的那部分价值，究竟在什么时间、什么接口、需要多少局部信息才能被简单去中心化策略重现。

因此 G22-v2 不应从“再训练一个模型”开始。

它应从：

```text
决策时机
→ 局部信息价值上界
→ 最小 guidance
```

开始。

这条路线：

- 直接吸收 G11—G21 的成功和失败；
- 保持真实机场地图；
- 保持原始任务逻辑；
- 不恢复 HCA*；
- 不引入大型算法；
- 保留 learning 主线；
- 也允许用严格 no-go 证明停止错误方向。
