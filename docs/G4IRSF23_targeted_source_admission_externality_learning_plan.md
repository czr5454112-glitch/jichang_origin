# G4IRSF23 深度主线方案

## 定向源端准入、系统外部性约束与前驱分流学习

**English subtitle:**<br>
**Targeted Source Admission, Externality-Aware Selective Learning, and Precursor Routing**

**Repository:** `czr5454112-glitch/jichang_origin`<br>
**冻结基线分支:** `codex/g4irsf22-execution`<br>
**冻结基线提交:** `6fed8befd82d744d36bcbccaa0d1ead6cce43c34`<br>
**建议新分支:** `codex/g4irsf23-execution`<br>
**建议 Draft PR base:** `codex/g4irsf22-execution`<br>
**当前 PR:** `#7`，open / draft / mergeable / 未合并<br>
**当前 CI:** GitHub Actions Run `#69`，`success`<br>
**当前生产候选:** `Source A0 + Route S4 + Merge J2 + Event E2`<br>
**唯一真实地图:** `data/processed/maps/map2.json`<br>
**任务生成:** 沿用原项目的真实任务处理和 1×/2×/4× 扩流逻辑<br>
**长期主线:** 每件行李只在当前接口决定 `MOVE` 或 `WAIT`，逐接口替换原项目 HCA*/A* 完整路径规划和未来预约表

---

# 0. 一页结论

## 0.1 G22 到底是好还是坏

G22 的结论可以分成三层：

| 评价层面 | 结论 | 原因 |
|---|---|---|
| 科学判断 | **好** | 证明了“当前路口只看当前 bag 收益”会误导策略；找到了系统外部性；把下一实验定位到真实 `storage_out / node_52 / block 7` |
| 算法性能 | **没有推进** | 没有新策略上线，2× 相对 S4 的改善为 0，v2-safe 差距没有关闭，4× 没有解锁 |
| 项目方向 | **明显变清楚** | 当前 Route 接口通常已经太晚；下一步应在行李从 EBS/存储区重新进入主网络时决定“现在放行还是让一个服务机会” |

因此，G22 不是一次性能胜利，但也不是白做。最准确的评价是：

> **它是一次有价值的负结果和动作位置定位，但还不是面向论文主张的性能进展。**

## 0.2 下一步不应再做什么

不再继续：

```text
当前 Route 节点上的普通 edge/WAIT 分类器
新的固定局部代价公式
大模型
新 planner
新 supervisor
Source top-K 排序
全机场 backpressure
反复的 1% 微优化
大规模哈希/封存工作
```

## 0.3 下一步应该做什么

在 `storage_out / node_52 / block 7`，让当前队首行李面对一个最简单的二选一动作：

```text
ADMIT_NOW
现在进入后续传送网络

HOLD_ONE_NATURAL_OPPORTUNITY
不换另一件行李，不改变完整路径，只让过一个真实的本地服务机会，
随后强制回到 A0/S4/J2/E2 重新判断
```

这仍是“每件行李在当前接口做一步决定”，没有恢复 A*。

## 0.4 G23 最重要的方法修正

G22 的新发现说明：

```text
某个动作可能让当前 bag 慢一点，
却让后面很多 bag 更快。
```

因此，在 Source HOLD 实验中，不能再按下面的错误顺序：

```text
当前 bag 变慢
→ 判定动作有害
→ 不跑系统结果
```

因为 HOLD 本来就会让当前 bag 略慢。

G23 应这样评价：

```text
H_bag：当前 bag 付出了多少代价
H_system：全体 57,012 件 bag 是否真的变快
公平约束：当前 bag 的代价是否被限制在一个自然服务机会内，
          是否产生新的 deadline miss
```

**H_bag 是成本和公平约束，不是 Source HOLD 的正收益筛选器。**

---

# 1. GitHub 与代码状态判断

## 1.1 PR #7 可以继续作为下一阶段基线

当前 PR：

```text
head = codex/g4irsf22-execution
base = codex/g4irsf21-execution
head SHA = 6fed8befd82d744d36bcbccaa0d1ead6cce43c34
state = open
draft = true
mergeable = true
merged = false
```

Run #69 已成功完成。

代码审阅显示，G22 对核心运行时的主要变化是：

```text
读取当前节点的队列长度
读取 scheduled incoming
读取下一可服务时间
累计离线 5/15/30/60 秒局部信息
```

这些内容没有进入生产 scorer，也没有直接修改正常流量动作。

所以：

```text
没有发现阻塞 G23 的线上语义问题。
```

## 1.2 仍需保留的边界

PR #7 有 32 个文件和较多实验数据，适合作为独立研究 PR，不建议继续把 G23 塞进同一个 PR。

建议：

```text
保留 PR #7 为 draft，不合并
从 6fed8be 新建 codex/g4irsf23-execution
新建 stacked Draft PR，以 codex/g4irsf22-execution 为 base
```

G23 应尽量复用 G22 已有的：

- 2× research profile；
- exact checkpoint；
- H_bag / H_system；
- process-isolated shards；
- Source 局部特征；
- compact output。

不要继续扩张 G22 的 Route binding，除非 Source HOLD 这个动作确实缺少一个最小的原生 intervention。

---

# 2. G22 结果的正确解释

## 2.1 当前 Route 动作确实存在自由度

G22 完成了：

```text
256 个目标组
166 个完整三动作组
332 个非 S4 动作
```

其中：

```text
22 个直接有益
215 个直接有害
95 个中性
```

所以不能说：

```text
所有局部动作都没用。
```

动作自由度仍然存在。

## 2.2 但目前没有可上线的 Route selector

64 个 H_system 组、128 个系统动作中：

```text
15 改善系统均值
83 恶化
30 中性
```

22 个直接帮助当前 bag 的动作中：

```text
只有 5 个也改善系统均值
只有 1 个同时不恶化 p95/p99
该动作仅改善 0.00331 s/bag
```

这意味着：

> 当前 Route 接口上的“局部看起来好”经常只是把拥堵转移给了别的行李。

## 2.3 固定局部公式失败，不等于局部学习理论失败

G22 的固定局部公式：

```text
queue area
scheduled incoming area
next-service deficit
queued wait
```

平均收益为负。

但它只证明：

```text
这一个固定公式不能识别稀有好动作。
```

它没有证明：

```text
所有局部特征都没有价值。
```

真正的 outcome-only action ceiling 仍为正，说明“动作有价值、选择器不会选”才是当前问题。

## 2.4 最强信号来自 Source，不是继续调 Route

2× 差距账本中：

```text
S4/J2/E2 = 337.842709 s/bag
v2-safe  = 247.384666 s/bag
gap      = 90.458043 s/bag
```

真实热点：

```text
storage_out / node_52 / block 7
segments = 3,600
Source delta = +583.655486 s/segment

storage_out / node_52 / block 8
segments = 1,216
Source delta = +200.836349 s/segment
```

这不是说整个 90.458 秒已经被严格因果分解成 Source/Route/Merge，而是说：

> 当前候选系统最明显、最集中的等待发生在 storage-out 重新放行的位置。

因此先测试 Source timing，比再训练一个泛化 Route 模型更符合证据。

---

# 3. 从 G4 到 G22 的项目脉络

| 阶段 | 实际进展 | 没解决的问题 | 对 G23 的启示 |
|---|---|---|---|
| G4A–G4G | 学习 edge scorer、风险门、PIBT-lite，逐步减少 A* | 外层仍有旧中央调度骨架 | 学习一步动作可行，但中央框架替策略提供了隐含协调 |
| G4H–G4IR | C++ no-A* 一步核心、论文任务复刻、性能加速 | 仍不是完整事件式逐接口执行 | 计算速度不再是第一矛盾 |
| G9–G10 | v2-safe 1×–16× 完成、0 冲突、0 A* | 仍连续生成未来路线并写预约窗口 | v2-safe 是强对照，不是最终去中心化方法 |
| G11 | 真正事件运行时第一次大规模失败 | backlog、starvation、低利用率 | 删除中央预约后必须补本地服务协议 |
| G12–G13 | F2 完成原始 1×，只比 v2-safe 慢约 1.135 s/bag | 新学习贡献未证 | 新框架方向本身可行 |
| G14–G15 | exact-state 因果接口、2,172 个动作标签、H_system | 普通换边大多昂贵 | 动作标签必须来自真实提交，不可只模仿意图 |
| G16–G17 | 发现网络时间改善会转移成 Source wait；定位 JIT merge | Source/Route 学习未授权 | 先找正确动作时机 |
| G18 | J2 JIT merge 在 2× 大幅改善；学习 Merge 仅微小收益 | Route/Source 仍未学习 | 简单规则 + 正确 seam 胜过复杂模型 |
| G19 | S4 只改 90 个动作，却把 2× mean 从 851.864 降到 337.843 | S4 仍是规则，不是学习策略 | 少数关键动作具有巨大杠杆 |
| G20 | E2 降低约 17% 事件；5,022 Route exact pairs | 102 有益、4,892 有害，模型未上线 | 普通动作分类会学成“永远保持 S4” |
| G21 | 补齐 edge + WAIT 动作合同 | 1× 小样本中 edge/WAIT 都有害 | 动作空间完整不等于动作时机正确 |
| G22 | 2× 当前点、H_system veto、系统外部性、Source hotspot | 0 新策略、0 gap closure、0 4× 解锁 | 应在更早的 storage-out 放行接口做学习 |

跨阶段最稳定的经验是：

```text
大收益来自：
正确动作接口
少量关键动作
局部队列/服务信息
严格 fallback

失败通常来自：
动作太晚
标签只看当前 bag
模型只复制基线
把拥堵从一处推到另一处
动作覆盖很高但真正 mutation 很少
```

---

# 4. 与原项目目标的关系

原项目在接收任务后：

```text
任务优先级排序
→ HCA*/A* 生成完整路线
→ 更新全局预约表
→ 根据 BTI/DDI 再重新规划
```

G23 的目标不是复制这一过程的简化版，而是继续替换它：

```text
行李到当前接口
→ 读取当前 bag 和一跳局部状态
→ 选择 MOVE 或 WAIT
→ 安全层提交一步
→ 下一接口再决定
```

最终结构仍是：

```text
学习策略：决定偏好
S4/J2/Source baseline：可靠默认动作
PIBT-like：只处理稀有局部互锁
Shield：禁止不安全动作
```

没有运行时 A*、完整未来路线或全局预约。

---

# 5. 文献只借简单原则

## 5.1 PIBT，IJCAI 2019

可借：

```text
每个时刻只决定一步
局部优先级和回退
运行时可去中心化
```

不借：

```text
把 PIBT 改成普通排队器
把其特定图结构下的到达保证外推到机场有向图
```

## 5.2 RHCR，AAAI 2021

可借：

```text
持续任务不要一次承诺完整未来
只做有限时间/有限机会承诺，然后重新判断
```

G23 的映射：

```text
HOLD 只让过一个自然服务机会
之后强制重新判断
```

不引入中央 Windowed-MAPF solver。

## 5.3 Traffic Flow Optimisation，AAAI 2024

可借：

```text
只按自由流最短路会形成拥堵
少量拥堵引导可能显著提高吞吐
```

G23 的映射：

```text
只在 node_52 的热点状态做准入控制，
不是给全图生成 guide path。
```

## 5.4 Online Guidance Graph Optimization，AAAI 2025

可借：

```text
交通分布变化时，指导信号需要随局部流量变化
```

G23 只使用：

```text
短期 release/admission/service 计数
当前队列
下一服务机会
```

不使用全图动态 guidance graph 或全对最短路重算。

## 5.5 Learn to Follow，AAAI 2024

该工作支持：

```text
局部观测下的去中心化策略可以面向 lifelong MAPF
```

但它仍保留个体路径规划并用学习处理冲突。

本项目不照搬，而是更激进地保持：

```text
运行时不保存完整个体路径
每个接口只做一步动作
```

---

# 6. G23 方法：A23 定向 Source Gate

## 6.1 唯一新增的在线候选

候选名：

```text
A23_TARGETED_STORAGE_OUT_GATE
```

只在：

```text
leg = storage_out
node = 52
eligible local state
```

生效。

## 6.2 动作

### ADMIT_NOW

使用当前 A0 行为：

```text
当前队首 bag 在本地服务与安全条件允许时进入下一段
```

### HOLD_ONE_NATURAL_OPPORTUNITY

定义：

```text
当前队首仍然是当前队首
不选择另一个 bag
不改变其完整路线
不固定等待任意秒数
只跳过一个真实、可验证的本地服务机会
随后回到 A0，重新判断
```

初始候选禁止：

```text
连续多次 learned HOLD
重新排序 top-K bags
把 HOLD 转换成未来预约
跨节点锁定资源
```

## 6.3 为什么这比旧 A1/A2 不同

旧 G19 A1/A2：

```text
对大量 Source 状态使用广泛压力规则
可以产生重复 HOLD retry
2× mean 分别恶化 +7.764 s 和 +4.937 s
```

G23：

```text
只在 storage_out/node_52/block7/8
只比较同一状态下的一次 ADMIT 与一次 HOLD
不换 bag
不连续 HOLD
用 H_system 作为主要收益
```

它是一个新的、窄得多的因果问题，不是重跑 A1/A2。

---

# 7. G23 的目标函数：系统收益 + 个体公平

## 7.1 三个独立量

每个 Source action group 必须保留：

```text
C_bag：
当前 bag 因 HOLD 多等了多久

G_system：
57,012-bag mean / p95 / p99 改变多少

F_fair：
是否新增 deadline miss
是否超过一次自然服务机会
是否发生重复 HOLD
```

## 7.2 标签

### FAIR_SYSTEM_BENEFICIAL

满足：

```text
系统 mean 明确改善
p95/p99 不退化
当前 bag 成本不超过动作合同
没有新增 deadline miss
```

### SYSTEM_BENEFICIAL_BUT_UNFAIR

```text
系统变好
但当前 bag 成本超过上限或产生 deadline miss
```

只作研究证据，不可上线。

### HARMFUL

```text
系统 mean 或尾部明显恶化
```

### NEUTRAL / ABSTAIN

```text
效果太小或方向不稳定
```

## 7.3 单动作效应的材料性分层

建议：

```text
strong system positive:
mean delta <= -0.05 s/bag

usable system positive:
mean delta <= -0.01 s/bag

weak diagnostic positive:
-0.01 < mean delta <= -0.001 s/bag

neutral:
|mean delta| < 0.001 s/bag
```

弱正例不能单独授权模型，但可用于分析一致性。

---

# 8. Stage 23A：接管与旧 Source 证据复盘

**时间上限：半天。**

只完成：

1. 新建独立 worktree；
2. 从 `6fed8be` 建 `codex/g4irsf23-execution`；
3. 读取：
   - `g4irsf19_source_admission.md`
   - G16/G17 Source 结论
   - G22 gap ledger / final decision / new ideas
   - 现有 I1 source checkpoint；
4. 将 Source seam 机制边界合并记录到 `g4irsf23_new_ideas.md`，不再维护重复单页报告。

必须直接说明：

```text
旧 I1 = Source queue order swap
旧 A1/A2 = broad pressure HOLD
新 A23 = same-front one-opportunity HOLD
```

这一步之后立即进入真实动作实验，不得继续做 Git/hash/格式工作。

---

# 9. Stage 23B：建立 exact ADMIT/HOLD 动作接口

## 9.1 优先复用

复用：

```text
G15/G17 Source opportunity
checkpoint clone
same-state baseline/treatment
H_bag/H_system
P8 process-isolated worker
```

## 9.2 允许的最小原生改动

若现有 I1 只能“换另一个 bag”，允许增加一个新 intervention：

```text
SOURCE_HOLD_ONE_NATURAL_OPPORTUNITY
```

只允许完成：

```text
跳过一个当前 service opportunity
发布下一次本地 source arbitration
保持同一个 front bag
生成 changed-action certificate
```

不得增加：

```text
新 planner
新 supervisor
全局 token
未来 route
新 event loop
第二套 checkpoint
```

## 9.3 exact group 前提

只有以下状态进入实验：

```text
leg == storage_out
node == 52
baseline A0 可以合法 ADMIT
无故障或 stale generation
HOLD 确实改变了一次动作
同一 front bag 保持不变
```

若 baseline 本来就被物理资源阻塞，不能把被迫等待冒充 treatment HOLD。

## 9.4 单点验证

先用 4–8 个真实状态验证：

```text
same state
ADMIT commits
HOLD commits
exactly one action changed
front bag unchanged
HOLD duration = one natural opportunity
then fallback to A0
```

这是机制验证，不是 G23 的科学结论。

---

# 10. Stage 23C：block 7 / block 8 Pilot

## 10.1 样本

目标：

```text
block 7: 192 groups
block 8:  64 groups
total:   256 exact groups
```

每个 runtime bag 只出现一次。

## 10.2 outcome-free 分层

按以下局部量分层，不按 task ID：

```text
source queue length
target queue length
target scheduled incoming
time to next service opportunity
release - admission slope
estimated service rate
bag deadline slack
bag wait age
```

每项至少覆盖低/中/高三个区间。

## 10.3 Horizon

全部：

```text
H_bag
```

系统实验：

```text
至少 128 个 block7 groups
至少  48 个 block8 groups
合计至少 176 H_system groups
```

Source HOLD 不能先按 H_bag 正负筛掉。

## 10.4 Pilot 继续门

满足以下条件才扩展 Source learning：

```text
complete action-changing rate >= 0.80
FAIR_SYSTEM_BENEFICIAL >= 16
block 8 至少有 4 个同向 FAIR_SYSTEM_BENEFICIAL
正例跨越至少 3 个压力/时间子区间
不是只有一个 task 或一个 event neighborhood
```

若不满足，进入 Stage 23I 的前驱 Route，不得直接结束 G23。

---

# 11. Stage 23D：正式 Source 因果数据

Pilot 通过后扩展到：

```text
2,048 complete groups
```

建议构成：

```text
block 7                  1,024
block 8                    512
adjacent blocks 5/6/9      512
```

另外保留一个不参与训练的 1× negative-control panel：

```text
256 groups
```

用途是检查策略是否会在低压环境无意义 HOLD。

## 11.1 H_system 分配

至少：

```text
512 H_system groups
```

包括：

- 全部 Pilot 正例；
- predicted/high-pressure groups；
- 低压负对照；
- block 8 confirmation；
- 模型最不确定 groups；
- 个体成本接近公平上限的 groups。

## 11.2 Split

必须按：

```text
task group
contiguous time block
pressure episode
```

分组切分。

禁止把同一拥堵 episode 的相邻状态分到训练和测试两侧。

## 11.3 数据量不足时的处理

如果没有足够公平系统正例：

```text
不使用过采样伪造支持
不降低系统门
不把 weak positive 当 strong positive
```

直接进入前驱 Route pivot。

---

# 12. Stage 23E：局部特征精简

现有 G17 Source context 很丰富，G23 不应全部照搬。

## 12.1 第一组：当前 bag

```text
deadline slack
wait age
storage dwell / release urgency
是否已被 learned HOLD 过
```

## 12.2 第二组：node_52

```text
source queue length
release count 10/30/60s
admission count 10/30/60s
queue slope 10/30/60s
time to next service opportunity
recent service completions / estimated service rate
```

## 12.3 第三组：下一局部资源

```text
target queue length
target scheduled incoming
target next available
first-edge credit slack
merge pending count
```

## 12.4 默认禁止

```text
two-hop pressure
absolute task ID
absolute event ID
absolute block ID codebook
future route
global queue
global reservation
post-hoc result
v2 action
```

二跳只在一跳状态出现明确 state aliasing 后，作为一次受控 ablation 加入。

---

# 13. Stage 23F：最简单的 selector 序列

## F0：可解释阈值

最多 3 个条件，例如：

```text
下游短期服务缺口高
且 Source 当前积压不高
且当前 bag slack 足够
```

不允许逐 node/task codebook。

## F1：单调线性 / Logistic

目标：

```text
预测 HOLD 是否为 FAIR_SYSTEM_BENEFICIAL
预测 current-bag cost 是否超过公平上限
```

建议方向约束：

```text
bag 更紧急，不应更倾向 HOLD
source queue 更长，不应更倾向 HOLD
下游服务缺口更大，可更倾向 HOLD
下一服务机会更远，可更倾向 HOLD
```

## F2：Tiny MLP

仅在以下条件都满足时运行：

```text
formal fair-positive >= 40
held-out fair-positive >= 12
线性模型存在稳定非线性 regret
```

建议：

```text
12–20 个输入
两层小 MLP
一个 benefit head
一个 unfair-risk head
```

不做：

```text
GNN
Transformer
PPO/MAPPO
多智能体 RL
online weight update
model ensemble zoo
```

## F3：不训练的情况

如果 action support 不足：

```text
不为了“主线是 learning”强行训练。
```

主线的正确含义是最终策略可学习，不是每个阶段都必须导出一个无效模型。

---

# 14. Stage 23G：离线门

模型必须在真正 held-out 的 block/time/episode 上满足：

```text
FAIR_SYSTEM_BENEFICIAL precision >= 0.75
applied harmful rate <= 0.05
tail-safe rate = 1.00
至少 10 个 held-out fair positives 被选择
block 8 中方向一致
低压 1× negative-control HOLD rate 很低
```

并报告：

```text
coverage
precision
harmful rate
mean predicted utility
mean realized system utility
individual cost distribution
abstention
```

普通 accuracy 不作为主要指标。

低置信：

```text
ABSTAIN → exact A0
```

---

# 15. Stage 23H：原生闭环

## 15.1 冻结其他头

```text
Route = S4
Merge = J2
Event = E2
Safety = R3/P2/Q0/C0 + Shield
```

只改变 Source admission。

## 15.2 Runtime hard guard

```text
每个 storage_out segment 最多一次 learned HOLD
HOLD 后下一次机会强制回 A0
deadline slack 不足时禁止 HOLD
fault/stale generation 时禁止 HOLD
模型无效/OOD/低置信时 A0
```

## 15.3 Coverage ladder

```text
shadow
1%
5%
10%
25%
full eligible coverage
```

每一级都必须产生真实 native HOLD mutation。

## 15.4 完整运行

至少：

```text
1× full
2× full
```

候选和 A0 使用完全相同任务流。

## 15.5 报告

```text
eligible Source opportunities
proposed HOLD
committed HOLD
unique held bags
abstentions
fairness blocks
deadline guards
source wait
network time
mean/p50/p95/p99/max
complete bags/segments
events/completed
wall/CPU/RSS
```

---

# 16. 2× 正式晋级门

当前基线：

```text
337.842708763 s/bag
```

## Direction pass

满足任一：

```text
mean <= 331.085855 s/bag  （改善 2%）
或
mean <= 332.842709 s/bag  （改善至少 5 秒）
```

同时：

```text
p95/p99 不退化
1× mean 退化 <= 0.1%
0 新增 deadline miss
0 safety regression
events/completed 增加 <= 5%
个体 HOLD 成本满足公平合同
```

## Gap milestones

```text
Gap-10: mean <= 328.796904
Gap-25: mean <= 315.228198
Gap-50: mean <= 292.613687
Strict v2 win: mean < 247.384666
```

---

# 17. Stage 23I：Source 不通过时的强制前驱 Route

以下任一发生时进入前驱 Route：

```text
Pilot fair positives不足
formal selector不过门
native 2×没有 Direction pass
```

不能直接结束 G23。

## 17.1 Target

针对：

```text
storage_out/node_52/block7/8
最终高等待或 v2 明显更快的 bags
```

找到它们在到达 node_52 之前最近一次：

```text
candidate_count >= 2
```

的真实 Route decision。

## 17.2 动作

```text
S4 edge
所有其他合法 edge
WAIT
```

只改该接口一步，后续仍回 S4/J2/E2。

## 17.3 样本

```text
Pilot: 512 groups
Formal: 2,048 groups
H_system: >= 256 groups
```

## 17.4 目标

回答：

```text
当前 node_52 才 HOLD 是否太晚？
是否应在上一个分流口提前绕开 storage-out 峰值？
```

若有足够公平系统正例，再运行与 Source 相同的：

```text
规则 → 线性 → tiny MLP → 1×/2× closed loop
```

---

# 18. Stage 23J：G22 系统减负动作的邻域复核

这是一个次级、低代码成本的研究轨道。

G22 发现两个动作：

```text
当前 bag 变慢
但系统 mean 和 tails 改善
```

G23 可以复用已有 Route exact seam，围绕其**结果之前可观察到的局部特征**构造：

```text
256 个 outcome-free neighborhood groups
```

这里的 256 是固定的 **attempted execution panel**，不是预先保证 256 次动作都能
改变。原生 guard 若返回
`SCREENING_FALSE_POSITIVE / NOT_APPLICABLE_ACTION_PRECONDITION_FAILED`，应把它记录成
一次完成的 applicability abstain：不重跑、不按结果补样，也不能冒充 changed-action
certificate。必须分别报告：

```text
attempted / identity-covered / missing / unknown
action-applied / guard-abstain / action-changing rate / abstain reasons
```

效应、fairness 和 held-out signature 只使用真正 action-changing 且 H_system 完整的
applied pairs。文件级 256/256 coverage 不能写成 256/256 effect certificates。

为保持这个 fallback 简单，邻域选择只读取备选边的一跳
`target_queue_length >= 16`，并固定分成 `q16_23 / q24_31 / q32_plus`。
`two_hop_queue_pressure` 不参与候选筛选、分层、held-out signature 或阈值；只有在一跳状态经结果证明存在 state aliasing 时，才允许另开一次受控 ablation。

系统 tail 硬门只使用 `p95/p99 <= baseline + 1 ms`；`raw_bag_max_delta_seconds`
必须进入 CSV、compact summary 和报告，但只作为诊断，不能改变 `system_safe`、
`system_beneficial` 或 continuation。单次 max 极值不应否决一个 p95/p99 与 deadline 均安全的局部动作。

要求：

- 固定覆盖 blocks 22--29，并以 blocks 22--25 discovery、26--29 held-out；
- 不使用 event/task ID；
- 不使用二跳、未来路线或全局压力；
- 全部运行 H_system；
- 不与 Source 训练数据混合。

继续条件：

```text
complete action-changing rate >= 0.80
>= 20 个 fair/system-beneficial actions
跨 >= 3 block × 一跳 target-queue cells
存在一跳 pressure-only held-out local signature
```

否则关闭该轨道。

这一步不应阻塞 Source 主线，也不增加线上 Route 模型，除非证据门通过。

---

# 19. Stage 23K：4× 规模实验

## 19.1 解锁条件

安全 2× 候选至少满足：

```text
mean 改善 >= 1%
```

才运行 4× 60 秒 matched ABBA。

满足 Direction pass 才允许 180 秒或 resumable full。

## 19.2 60 秒 ABBA

至少：

```text
baseline → candidate → candidate → baseline
```

报告中位数：

```text
completed
released
backlog
simulated-time progress
events/completed
wall/CPU/RSS
```

## 19.3 延长条件

任一：

```text
completed +10%
simulated progress +10%
backlog -10%
events/completed -10%
```

才运行 180 秒。

180 秒保持收益后，才运行 resumable 4× full。

## 19.4 业务和计算必须分开

同时报告：

```text
业务时间/等待
模拟器墙钟时间
```

不能把“计算完成”冒充“业务更快”。

---

# 20. 并行与故障

## 20.1 并行

继续使用已验证的：

```text
P=1/2/4/8 process-isolated exact-pair farm
```

单实例并行只有：

```text
live independent width >= 2
且模型/特征计算 >= 10% CPU
```

才运行。

Source 二分类器很轻，默认不值得加线程。

## 20.2 故障

故障工作不超过本轮约 10%。

最终候选回归：

```text
HOLD 后立即 fault
等待机会期间 fault
repair 后重新放行
stale generation
pending/in-flight lease
```

硬门：

```text
0 failed
0 conflict
0 unsafe
0 stranded
0 unresolved deadlock
0 full A*
0 future route
0 global scan
```

---

# 21. 防止 Codex 很快“做完”

以下任何单项都不能结束 G23：

```text
Git/CI
一页复盘
4–8 个机制测试
256-group Pilot
一个 block 7 结果
block 8 确认
一个规则 no-go
一个线性模型 no-go
一个 tiny MLP
shadow
144/512
一份报告
4× 60 秒
fault pass
```

## 路线 A：Source 成功

```text
exact Source action
→ Pilot
→ formal 2,048
→ fair system labels
→ simple selector
→ native 1×/2×
→ 4×
```

## 路线 B：Source 有机制信号但学不会

```text
exact Source action
→ fair positives
→ selector no-go
→ 可解释 deterministic mechanism
→ native 1×/2×
→ 若仍无收益，进入 precursor
```

## 路线 C：Source no-go

```text
Source Pilot/formal no-go
→ precursor Route 512/2,048
→ selector
→ native 1×/2×
```

## 路线 D：两者均 no-go

```text
Source充分no-go
→ precursor充分no-go
→ externality neighborhood充分no-go
→ LOCAL_ONE_STEP_CONTROL_CEILING_AT_NODE52
```

只有路线 D 完成后，才可以说该热点的一步局部学习接近上限。

---

# 22. 时间与工作量预算

建议比例：

```text
Git/构建/历史校验          <= 3%
Source exact + data        35%
H_system + externality     25%
模型/规则                  15%
closed-loop                12%
4×/fault/最终报告          10%
```

禁止出现：

```text
做了一整天，主要产物是 hash、manifest、格式检查。
```

每个阶段最多一个主报告、一个表、一个可再生 runner。

---

# 23. 建议提交序列

```text
G23-A  exact storage-out ADMIT/HOLD seam
G23-B  block7/block8 causal pilot
G23-C  formal Source externality dataset
G23-D  deterministic/linear/tiny selector
G23-E  native 1x/2x Source closed loop
G23-F  mandatory precursor Route pivot if needed
G23-G  4x/fault/final joint decision
```

不要为每一次预筛或格式修正单独提交。

---

# 24. 主要交付物

始终发布当前决策所需的小型证据：

```text
docs/G4IRSF23_targeted_source_admission_externality_learning_plan.md
docs/g4irsf23_new_ideas.md

outputs/reports/g4irsf23_source_pilot.md
outputs/reports/g4irsf23_precursor_route.md
outputs/reports/g4irsf23_final_joint_decision.md

outputs/tables/g4irsf23_paper_baselines.json
outputs/tables/g4irsf23_source_pilot.csv
outputs/tables/g4irsf23_source_pilot_summary.json
outputs/tables/g4irsf23_precursor_route_actions.csv
outputs/tables/g4irsf23_precursor_route_summary.json
outputs/tables/g4irsf23_decision_summary.json
```

只有上游 gate 触发时才发布对应阶段产物。当前 fallback 路径使用以下真实文件名：

```text
# Source no-support 后触发 precursor Formal
outputs/reports/g4irsf23_precursor_route_formal.md
outputs/tables/g4irsf23_precursor_route_formal_actions.csv
outputs/tables/g4irsf23_precursor_route_formal_summary.json

# precursor Formal sufficient no-go 后触发 externality neighborhood
outputs/reports/g4irsf23_externality_neighborhood.md
outputs/tables/g4irsf23_externality_neighborhood_actions.csv
outputs/tables/g4irsf23_externality_neighborhood_summary.json

# 仅在相应 causal-support / promotion gate 通过后
outputs/reports/g4irsf23_source_learning.md
outputs/reports/g4irsf23_closed_loop.md
outputs/reports/g4irsf23_scale_fault.md
outputs/tables/g4irsf23_learning_ablation.csv
outputs/tables/g4irsf23_closed_loop.csv
artifacts/datasets/g4irsf23_source_compact_groups.jsonl
artifacts/models/g4irsf23_source_*.json
artifacts/policies/g4irsf23_source_*.json
```

未触发的阶段只在 `g4irsf23_final_joint_decision.md` 与
`g4irsf23_decision_summary.json` 中记录 `NOT_TRIGGERED_BY_*`，不制造空报告、空模型或占位表。
大 raw pair/census/cache 留在隔离 worktree，不上传 GitHub。

---

# 25. 最终必须直接回答的 30 个问题

1. PR #7 与 G23 CI 是否绿色？
2. 新 Source HOLD 与旧 I1/A1/A2 有什么本质区别？
3. block 7 有多少 exact applicable groups？
4. block 8 是否复现方向？
5. HOLD 给当前 bag 增加多少时间？
6. HOLD 对 57,012-bag mean 有多少影响？
7. p95/p99 是否同向？
8. 有多少 FAIR_SYSTEM_BENEFICIAL？
9. 有多少 SYSTEM_BENEFICIAL_BUT_UNFAIR？
10. 正例跨多少压力区间和时间区间？
11. 哪些局部特征最有用？
12. 二跳信息是否真的必要？
13. 规则、线性、tiny MLP 谁最好？
14. held-out precision 和 harmful rate 是多少？
15. 模型实际提交多少 HOLD？
16. 有多少 HOLD 被公平约束拒绝？
17. 是否出现重复 HOLD？
18. 1× 是否保持？
19. 2× mean/p95/p99 如何？
20. Source wait、network time如何重新分配？
21. 关闭多少 v2-safe gap？
22. 是否达到 Direction/Gap-10/25/50？
23. Source 不通过时，前驱 Route 是否有正例？
24. 前驱 Route 改的是哪个真实上游接口？
25. G22 两个 cohort-relief 动作是否可泛化？
26. 4× 60 秒是否改善？
27. 是否解锁 180 秒或 full？
28. 单实例并行是否有必要？
29. 故障是否安全？
30. 下一阶段最窄、最有价值的问题是什么？

---

# 26. 正式结果标签

```text
TARGETED_SOURCE_CAUSAL_SUPPORT
TARGETED_SOURCE_NO_SUPPORT

SOURCE_ADMISSION_DETERMINISTIC_GAIN
SOURCE_ADMISSION_LEARNED_GAIN
SOURCE_ADMISSION_SELECTOR_NO_GO

FAIR_SYSTEM_EXTERNALITY_SELECTOR_GAIN
FAIR_SYSTEM_EXTERNALITY_SELECTOR_NO_GO

PRECURSOR_ROUTE_CAUSAL_SUPPORT
PRECURSOR_ROUTE_LEARNED_GAIN
PRECURSOR_ROUTE_NO_SUPPORT

FOUR_X_SCALE_GAIN
FOUR_X_RUNTIME_BLOCKED
FOUR_X_PHYSICAL_OVERLOAD

LOCAL_ONE_STEP_CONTROL_CEILING_AT_NODE52
```

---

# 27. 用最容易理解的话概括

原来的 HCA* 像是：

> 每件行李刚进来，就由一个中央调度员提前把后面整条路排好。

我们的新系统像是：

> 每件行李每到一个岔路口，只看附近情况，决定下一步怎么走。

G22 发现：

> 行李已经走到堵点再换方向，通常太晚；<br>
> 看起来让当前行李更快的动作，还可能让后面很多行李更慢。

G23 要做的是：

> 在行李从存储区重新进入主传送网络之前，先决定“现在放它进去”，还是“让一个服务机会再进去”。

这个动作非常简单，但位置更早，可能更有杠杆。

若它有效，再让一个很小的模型只在少数确定状态下执行 HOLD；其余时候全部保持 A0/S4/J2/E2。

若它无效，就继续向前找上一个真实分流口，而不是回头堆更大的模型。

---

# G23 双基线与原论文一致口径（追加约束）

G23 的 Source 因果实验仍以 `A0 + S4 + J2 + E2` 作为仅改变 Source
动作的 matched control；最终性能结论必须另外同时报告以下两个主 baseline：

1. `G4IRSF13_F2_FROZEN`：仓库冻结的去中心化框架基线。名称必须写全，
   避免与本方案 Stage F 的 tiny MLP 层级混淆。
2. `original_project_iot_drpa_hca_star`：原项目集中式 IoT-DRPA/HCA*
   基线。1× 使用已提交的原项目真实输出解析证据，并明确标注为历史解析结果，
   不是新的 Java GUI/HCA* 重跑。

原论文为 *Internet-of-Things-augmented dynamic route planning approach to the
airport baggage handling system*，DOI：
[10.1016/j.cie.2022.108802](https://doi.org/10.1016/j.cie.2022.108802)。

论文一致的主口径是：1×、28,506 个原始 bag、2.5 m/s、按原始 bag 汇总拆分
segment 的 THT，并报告 min/mean/max 与完整处理量。还需保留表 5.2 的
1.5/2.0/2.5/3.0 m/s 速度表、表 5.3 的分散启发式、表 5.4 的动态
IoT-DRPA 与静态 LRA*、表 5.5 的 16 个故障场景，且区分“论文报告值”和
“本项目实际运行值”。

`processed_segment_attempt_time_tth`、`java_release_time_tth` 与
`original_entry_time_tth` 必须分列；禁止跨分母宣布胜负。原论文没有 2×/4×
HCA* 协议，因此这两档必须写为 `N/A_NOT_IN_PAPER_PROTOCOL`，不得复制 1×
数字、以 v2-safe 替代或用静态 A* 冒充 HCA*。
