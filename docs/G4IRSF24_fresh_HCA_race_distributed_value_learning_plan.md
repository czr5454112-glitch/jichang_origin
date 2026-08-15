# G4IRSF24 深度主线方案

## 同协议 HCA* 对决与去中心化动态价值路由

- **English subtitle:** **Fresh HCA* Race and Decentralized Learned Delay Potential**
- **Repository:** `czr5454112-glitch/jichang_origin`
- **冻结基线分支:** `codex/g4irsf23-execution`
- **冻结基线提交:** `16d5ed2b65fc853e97dd97c679a940c9908cba9c`
- **建议新分支:** `codex/g4irsf24-execution`
- **建议 Draft PR base:** `codex/g4irsf23-execution`
- **当前 Draft PR:** `#8`，open / draft / mergeable / 未合并
- **当前 GitHub Actions:** Run `#71`，success
- **当前控制基线:** `Source A0 + Route S4 + Merge J2 + Event E2`
- **安全边界:** `R3 + P2 + Q0 + C0 + Shield`
- **固定地图:** `data/processed/maps/map2.json`
- **主任务:** 用去中心化、逐接口、可学习的局部决策替代原项目 HCA*/A* 完整路径规划与全局预约表
- **本轮第一目标:** 在严格同输入、同起算口径、同机器的 fresh 实验中超过原始集中式 IoT-DRPA/HCA*
- **本轮第二目标:** 不再寻找稀有“特殊动作”，而是学习每个局部方向的动态剩余时间，使每件行李在每个接口做更好的单步选择
- **复杂度原则:** 一个小型局部数值表、一跳通信、一个现有安全回退；不新增中央 planner，不引入模型 zoo

---

# 0. 一页决策

## 0.1 G23 是好是坏

G23 的评价必须分开：

| 维度 | 评价 | 原因 |
|---|---|---|
| 科学严谨性 | **好** | Source、前驱 Route、系统外部性三条 seam 都被真实动作和 H_system 检验，没有强行上线不可靠 selector |
| 新算法性能 | **坏 / 未推进** | 没有训练、导出或部署新策略，`A0 + S4 + J2 + E2` 完全不变 |
| 对主线的帮助 | **有价值但已到转向点** | 证明了三个被测试的局部“例外动作 seam”接近上限，但没有否定逐接口去中心化路线 |
| 对论文主张 | **尚不够** | 只有历史、代数对齐的 F2 优势方向，尚无 fresh 同协议 HCA* 胜利 |
| 工程状态 | **健康** | 新 HOLD 很小、同队首、一次机会后回 A0；没有中心规划器、未来路径或全局扫描 |

最准确的总结是：

> **G23 是一次高质量的负结果，但继续用同一种“找一个特殊时刻翻转 S4 动作”的研究方式，边际收益已经很低。**

## 0.2 G20–G23 为什么连续学不出 selector

近期实验一直在问：

```text
在某个被挑中的时刻，
是否应该把 S4 的动作改成另一条边或 WAIT？
```

这会产生三个困难：

```text
绝大多数替代动作本来就有害；
真正有益动作很稀少；
有些动作只在全系统层面有益，当前局部状态却没有稳定可识别特征。
```

因此，模型很容易学成：

```text
永远保持 S4
```

或者：

```text
偶尔改变动作，但把拥堵转移给其他行李
```

G23 的 `TESTED_SEAM_LOCAL_ACTION_CEILING` 应理解为：

```text
Source node52 one-opportunity HOLD
前驱 Route formal seam
G22 externality neighborhood
```

这三个 seam 没有可靠 selector。

它不代表：

```text
所有节点都没有学习空间；
所有逐步决策都没有价值；
去中心化 MAPF 主线失败；
学习无法替换 HCA*。
```

## 0.3 本轮必须改变“学习问题”，而不是堆大模型

原 HCA* 的优势不是某一个神奇 WAIT。

它的优势是：

```text
中央控制器通过 A* 和预约表，
对“从这里到终点还要花多久”有一个未来估计。
```

当前 S4 已经能看：

```text
当前候选边
下一节点队列
scheduled incoming
corridor / target next-available
静态最短距离
```

但它缺少：

```text
这条方向在当前交通状态下，
后面整段通常还要花多久。
```

G24 的核心不是再训练一个动作分类器，而是给每个接口学习一个非常小的“动态路牌”：

```text
走邻居 A，预计还要 180 秒；
走邻居 B，预计还要 145 秒。
```

行李仍然只做一步决定。

## 0.4 新方法一句话

候选名：

```text
DLP — Decentralized Learned Delay Potential
去中心化学习延误势能
```

每个节点只维护：

```text
每条相邻边最近实际花了多久；
从相邻节点到当前目标通常还要多久；
这些估计看过多少真实样本。
```

每次真实行李通过后，局部数值轻量更新。

决策时：

```text
现有 S4 分数
+
学习到的“动态剩余时间相对静态最短路的修正”
```

低样本、低置信或收益不明显：

```text
精确回退 S4
```

这比 HCA* 简单得多：

```text
不生成完整路线
不写未来全局预约
不扫描全机场
不运行 A*
不需要神经网络
```

## 0.5 本轮两条并行主轨

### Track A：Fresh HCA* 对决

直接回答：

```text
在完全相同任务、相同起算口径和相同机器上，
当前去中心化框架到底有没有超过原始 HCA*？
```

这可能是最快得到真正论文结论的路线。

### Track B：DLP 动态价值学习

直接回答：

```text
把 S4 的静态未来估计换成从真实交通中学习的动态剩余时间，
能否进一步改善 1×、2×，并在 4× 提高吞吐？
```

两条轨道必须同时推进；不能只复刻 baseline 后结束。

---

# 1. 当前 GitHub 状态与分支策略

## 1.1 已确认状态

```text
PR #8
head = codex/g4irsf23-execution
base = codex/g4irsf22-execution
head SHA = 16d5ed2b65fc853e97dd97c679a940c9908cba9c
state = open
draft = true
mergeable = true
merged = false
Actions Run #71 = success
```

G23 没有发现需要先停下主线修复的阻塞问题。

## 1.2 G24 不继续堆进 PR #8

建议：

```text
保留 PR #8 为独立 G23 负结果证据
不自动合并
从 16d5ed2 新建独立 worktree
创建 codex/g4irsf24-execution
新建 stacked Draft PR
base = codex/g4irsf23-execution
```

这样可以：

```text
保持 G23 结论可复查；
让 G24 的新算法改动保持清楚；
避免一个 PR 继续膨胀；
必要时可以单独撤回 DLP。
```

---

# 2. 从 G4 到 G23 的真正项目脉络

| 阶段 | 真正推进 | 暴露的问题 | 对 G24 的启示 |
|---|---|---|---|
| G4A–G4G | 学习 edge scorer、风险头、PIBT-lite，A* 调用逐步归零 | 外层仍带中央规划留下的隐含协调 | 学习一步动作可行，但必须在真正事件式系统中验证 |
| G4H–G4IR | C++ no-A* 动作核心、论文任务复刻、1×–16× 工程压力 | v2-safe 仍连续生成未来路线/预约 | v2-safe 是强诊断，不是最终方法 |
| G11 | 真正事件运行时在大流量下暴露 backlog/starvation | 移除中央预约后缺乏局部协调协议 | 框架改造不能只删 A* |
| G12–G13 | F2 让事件式去中心化框架在 1× 完成 | 与原 HCA* 的比较口径没有 fresh 对齐 | G24 必须先做同协议对决 |
| G14–G15 | exact-state 单步因果接口 | 普通替代动作多数有害 | 不应把主要资源继续投入稀有反事实分类 |
| G16–G18 | 找到 Source wait 转移与 J2 JIT merge | 学习 Merge 只提供很小增益 | 正确的简单机制可胜过复杂模型 |
| G19 | S4 只改变约 90 个动作，却把 2× mean 大幅降低 | S4 是规则，未来估计仍是静态/一跳 | 少量关键路径选择很有杠杆 |
| G20 | E2 降事件，5,022 Route exact pairs | 102 有益、4,892 有害，模型趋向“不改变” | 稀有动作分类不是理想监督信号 |
| G21 | 补全合法 edge + WAIT | WAIT 没有显示系统收益 | 不再把 WAIT 当默认学习方向 |
| G22 | 发现当前 bag 与全系统收益可能相反 | 局部固定公式无法识别外部性 | 评价必须看系统，但不能再靠极少 H_system 标签训练 |
| G23 | Source / precursor / externality 三 seam 完整收口 | 有系统收益动作，但 held-out 局部 signature 失败 | 改学“长期交通代价”，不再学“稀有例外动作” |

跨阶段最稳定的事实是：

```text
动作自由度存在；
少数动作可以带来巨大系统收益；
安全执行框架已经成熟；
真正缺少的是稳定、密集、可泛化的未来代价信号。
```

---

# 3. 当前基线离原论文究竟有多远

## 3.1 原论文 HCA* 的公开主表

论文 Table 5.2 / Table 5.3 在 `2.5 m/s` 下报告的 IoT-DRPA/HCA*：

```text
min  = 3.13 min = 187.8 s
mean = 3.96 min = 237.6 s
max  = 5.98 min = 358.8 s
```

Table 5.3 的分散式启发式为：

```text
min  = 3.56 min
mean = 4.43 min
max  = 8.62 min
```

因此，`8.62 min` 是分散式启发式的最大值，不是另一个“静态方案均值”。

## 3.2 当前数字已经提示“可能早已超过”，但不能直接宣称

G19 当前 S4/J2 的 1× 数字为：

```text
mean = 213.912 s
p95  = 252.004 s
p99  = 281.004 s
```

单看数值：

```text
213.912 s < 237.6 s
```

名义上低约：

```text
23.688 s
约 9.97%
```

但 G23 已正确指出：

```text
processed-attempt
Java-release
raw-entry
```

三种起算口径不能混用。

所以当前最重要的不是继续猜，而是：

> **让原始 Java HCA* 与当前去中心化基线读取同一批任务，并由同一个 G23 口径解析器输出三套指标。**

## 3.3 G23 已有的历史方向证据

同为历史 raw-entry 代数对齐时：

```text
F2 = 41.5142 min/bag
HCA* = 43.1359 min/bag
方向差 = 97.3 s/bag
约 3.76%
```

这说明 fresh 胜利很有可能。

但它仍不是：

```text
同一输入
同一程序版本
同一机器
同一时间运行
同一逐 bag 原始记录
```

所以 G24 必须把它变成 fresh 证据。

---

# 4. Track A：Fresh HCA* 同协议对决

## 4.1 原则

不重新实现 HCA*。

只使用：

```text
仓库或原始项目中已经存在的 Java HCA*/IoT-DRPA 入口
现有 map2
现有原始任务处理规则
G23 已完成的 baseline parser
```

只允许做：

```text
路径适配
依赖恢复
命令行封装
结果导出
明显的环境兼容修复
```

禁止修改：

```text
HCA* 搜索逻辑
任务优先级
预约表逻辑
冲突规则
业务速度
输入任务
```

## 4.2 首先定位并记录原始入口

Codex 必须在报告中明确写出：

```text
Java 工程实际路径
main / runner 入口
地图路径
任务输入路径
配置文件
输出文件
JDK 与构建命令
是否需要最小兼容补丁
```

如果原始 Java 代码不在当前 Git worktree，但在用户已有原项目目录中：

```text
只读取和调用
不复制大工程到 G24 PR
```

## 4.3 四个对照

### B0：原始集中式 HCA*

```text
IoT-DRPA/HCA*
完整路径
全局预约表
原始优先级
```

### B1：冻结 F2

```text
G4IRSF13_F2_FROZEN
```

用途：

```text
保留框架演进中间参照
```

### B2：当前去中心化基线

```text
A0 + S4 + J2 + E2
```

这是 G24 的主要内部 baseline。

### C1/C2：G24 学习候选

```text
DLP-EWMA
DLP-TD
```

## 4.4 输入对齐

主实验必须满足：

```text
同一 map2
同一原始任务记录
同一 task_id / segment_id 集合
同一 release/pass time
同一设备速度
同一故障开关
同一时间范围
```

不允许：

```text
HCA* 用论文旧结果
G24 用新生成任务
然后直接比较。
```

## 4.5 三种时间口径全部输出

严格复用 G23 定义：

```text
processed-attempt
Java-release
raw-entry
```

不要重命名、重解释或代数猜测。

主论文比较：

```text
processed-attempt
```

工程运营比较：

```text
Java-release
raw-entry
```

三者必须在同一表中并列，绝不混成一个数字。

## 4.6 业务指标与计算指标分开

业务：

```text
complete / failed
mean
p50
p95
p99
max
deadline miss
source wait
network time
```

计算：

```text
planning wall time
simulation wall time
CPU time
peak RSS
events/completed
```

不能用：

```text
C++ 跑得快
```

冒充：

```text
行李业务时间更短
```

也不能用：

```text
HCA* 规划慢
```

冒充：

```text
HCA* 行李路径质量差
```

## 4.7 Fresh 1× 实验

至少：

```text
HCA* fresh full ×2
F2 full ×2
S4/J2/E2 full ×2
```

若业务结果严格确定性相同，第二次主要验证环境和 wall time。

## 4.8 Fresh 胜利标签

### `FRESH_HCA_STRICT_WIN`

```text
同一 processed-attempt 口径
G24/S4 mean < fresh HCA* mean
p95 不退化
完成率不退化
0 安全回归
```

### `FRESH_HCA_CLEAR_WIN`

在 STRICT WIN 基础上：

```text
mean 至少改善 5%
```

### `PAPER_TABLE_MEAN_WIN`

```text
processed-attempt mean < 3.96 min
```

### `PAPER_TABLE_RANGE_WIN`

```text
processed-attempt mean < 3.96 min
processed-attempt max <= 5.98 min
```

论文没有在这张主表中报告 p95/p99；fresh 实验仍需额外报告 p95/p99，但不能把它们伪装成论文原始列。

不能用 paper table win 代替 fresh win；两者分别报告。

## 4.9 对 baseline 工作量设上限

Baseline 是关键，但不能吃掉整轮：

```text
代码/环境定位与修复 <= 总工作量 15%
```

若原始 HCA* 因缺失依赖无法在合理范围运行：

```text
记录准确阻塞
保留历史表
继续 DLP
不得为了复活旧 Java 工程重写一套 HCA*
```

---

# 5. Track B：DLP 去中心化学习延误势能

## 5.1 最容易理解的类比

HCA* 像：

> 一个中央调度员给每件行李提前画完整路线，并给后面所有路段预约时间。

S4 像：

> 行李只看眼前一两个路口，选择当前看起来不堵的方向。

DLP 像：

> 每个路口都有一块会根据真实交通自动更新的路牌，告诉行李“从这个方向到目标，通常还要多久”。

路牌不是完整路线。

行李下一站仍会重新判断。

## 5.2 每个节点只保存两类数值

### A. 边的实际一步时间

```text
E(u,v)
```

含义：

```text
从节点 u 提交走向 v，
直到在 v 进入下一次合法决策/服务状态，
最近通常花多少秒。
```

它来自真实完成的移动，不来自未来预测。

### B. 节点到目标的学习剩余时间

```text
V(v,g)
```

含义：

```text
从节点 v 到当前 segment goal g，
根据历史真实交通，通常还要多少秒。
```

### C. 支持度

```text
N_edge(u,v)
N_value(v,g)
```

用于判断这个估计是否可信。

## 5.3 静态初始化

不使用 HCA* teacher。

初始化：

```text
E0(u,v) = 物理边时间 / 已有静态一步代价
V0(v,g) = 当前 static potential h(v,g)
```

因此在没有学习证据时：

```text
DLP 精确退化到 S4 的静态方向判断。
```

## 5.4 局部更新

行李在时间 `t0` 从 `u` 选择 `v`。

到达 `v` 并形成下一个真实决策状态的时间为 `t1`。

实际一步时间：

```text
d = t1 - t0
```

边时间更新：

```text
E(u,v) <- (1-alpha_e) E(u,v) + alpha_e d
```

节点价值更新：

```text
target = d + V(v,g)

V(u,g) <- (1-alpha_v) V(u,g) + alpha_v target
```

终点：

```text
V(g,g) = 0
```

这就是一个非常小的时序差分更新。

不需要：

```text
神经网络
反向传播
GPU
全局 reward
集中 critic
完整 episode 回传
```

## 5.5 决策分数

当前 S4 已有：

```text
物理/静态路径代价
候选队列
scheduled incoming
corridor next-available
target next-available
```

DLP 不删除 S4。

只增加一个残差：

```text
learned_remaining(u,g,v)
  = E(u,v) + V(v,g)

static_remaining(u,g,v)
  = E0(u,v) + V0(v,g)

residual
  = learned_remaining - static_remaining
```

最终：

```text
score_DLP
  = score_S4 + beta * residual
```

分数越低越优。

## 5.6 为什么使用残差而不是完全替换 S4

这样可以：

```text
保留 G19 已验证的巨大 S4 收益；
学习只修正静态未来代价；
未见状态自动回到 S4；
避免 DLP 重新学习安全和物理规则；
减少参数量。
```

## 5.7 只改变 Route MOVE 排序

G24 初始版本：

```text
只在现有 shield-legal MOVE 候选之间排序
```

不学习：

```text
Source HOLD
Route WAIT
Merge grant
PIBT recovery
fault action
```

原因：

```text
G21/G23 已经给 WAIT 和 Source HOLD 足够负证据；
J2 已是简单强机制；
本轮应集中在 HCA* 最核心的“路线未来代价”替代上。
```

## 5.8 置信门

只有同时满足：

```text
候选下一节点的 V 支持度足够
边时间支持度足够，或边使用可靠静态时间
最佳 DLP 动作相对 S4 有明确 margin
动作满足原 shield
没有 fault/stale state
```

才允许改变 S4。

否则：

```text
exact S4
```

## 5.9 循环与绕路保护

学习值不能无限诱导绕路。

保留：

```text
现有 shield
现有 PIBT-like recovery
物理合法边
静态 detour cap
```

建议只允许：

```text
候选静态剩余路程 <= S4 候选静态剩余路程 + 固定小 detour allowance
```

detour allowance 必须由真实图边长度解释，不能逐节点手调。

## 5.10 去中心化语义

概念部署中：

```text
节点 u 保存自己的 E 和 V；
节点 v 只向相邻上游提供 V(v,g) 一个标量；
行李只读取当前节点和候选邻居；
更新只发生在真实相邻转移后。
```

单机模拟器可以把数组放在同一个 runtime 对象里，但报告必须证明：

```text
决策没有全图扫描；
没有读取非相邻队列；
没有计算完整未来路线；
复杂度 O(out-degree)。
```

---

# 6. 为什么 DLP 比继续做 seam 分类更有希望

## 6.1 标签从稀疏变为密集

G20/G23：

```text
只有被选中的少量反事实组有标签；
大部分替代动作有害；
H_system 极昂贵。
```

DLP：

```text
每一次真实边移动都产生 d；
每一次到达都能更新 E；
每一次安全完成转移都能更新 V。
```

不再需要从：

```text
5,000 个动作里找 100 个正例
```

而是从：

```text
几十万次真实转移中学习连续时间。
```

## 6.2 学的是 HCA* 真正提供的能力

HCA* 提供：

```text
未来路线代价估计
```

DLP 也提供：

```text
未来剩余时间估计
```

区别是：

```text
HCA* 通过中央搜索和预约表算；
DLP 通过局部真实交通逐步学。
```

## 6.3 固定地图反而是优势

项目地图固定为真实机场拓扑。

因此：

```text
节点 ID 和目标节点是合法物理状态；
不是 task ID codebook；
小型 node-goal 表可以稳定积累大量样本；
不需要 GNN 来泛化到任意地图。
```

## 6.4 计算复杂度很低

每个动作：

```text
遍历当前节点 2–4 条候选边
查几个数组
做加法比较
```

每个转移：

```text
两次 EWMA/TD 更新
```

不会成为 4× 的主要 CPU 瓶颈。

---

# 7. 文献只借最简单、最匹配的部分

## 7.1 Q-routing，NIPS 1993

Boyan 与 Littman 的 Q-routing：

```text
每个网络节点只用局部通信；
学习不同下一跳到目的地的预计传输时间；
在动态负载下可优于预计算静态最短路。
```

G24 借：

```text
局部下一跳价值
真实传输时间更新
动态负载适应
```

不借：

```text
无约束在线探索
通用网络协议栈
```

## 7.2 PIBT，IJCAI 2019

借：

```text
每步只决定一次移动；
局部优先级和 backtracking；
可去中心化执行。
```

继续把 PIBT-like 放在：

```text
稀有局部互锁保底
```

而不是主路线价值学习器。

## 7.3 Traffic Flow Optimisation，AAAI 2024

该工作说明：

```text
只追求 free-flow 最短路会产生拥堵；
拥堵感知的 guidance 可以提高 lifelong throughput。
```

G24 借：

```text
动态交通代价应该修正静态最短路。
```

不借：

```text
全图 guidance graph 优化器。
```

## 7.4 Online Guidance Graph Optimization，AAAI 2025

借：

```text
交通分布变化时，指导应随实时流量变化。
```

G24 只用局部 EWMA/TD 值实现，不做全局在线图优化。

## 7.5 Learn to Follow，AAAI 2024

该工作支持：

```text
没有中央全状态时，agent 可以基于局部观测顺序决策。
```

但它保留个体路径规划并使用神经策略。

G24 不照搬，仍坚持：

```text
无完整个体路径
无大型神经网络
一步一决策
```

---

# 8. G24 候选序列

## P0：冻结基线

```text
A0 + S4 + J2 + E2
```

## P1：DLP-EWMA

只替换动态一步时间：

```text
E(u,v) + static V0(v,g)
```

目的：

```text
验证“真实走廊时间”本身是否比静态边时间更有价值。
```

没有 TD bootstrap。

## P2：DLP-TD

主候选：

```text
E(u,v) + learned V(v,g)
```

目的：

```text
验证局部学习剩余时间能否替代 HCA* 的未来代价功能。
```

## P3：Tiny residual（条件式）

只有 P2 已经在原生 1×/2× 显示稳定业务收益，且误差分析证明固定表存在明确非线性残差时，才允许：

```text
<= 16 个输入
1–2 层 tiny MLP 或单调树
```

输入仅可包括：

```text
DLP residual
支持度
当前/目标队列
scheduled incoming
next-available
bag slack / wait age
```

P3 不能在 P2 没有真实收益时启动。

---

# 9. Stage 24A：接管与 fresh baseline

**目标时间占比：不超过 15%。**

1. 从 `16d5ed2` 建独立 worktree；
2. 核查 PR #8 与 Run #71；
3. 定位原始 Java HCA* 入口；
4. 复用 G23 baseline parser；
5. 生成一批统一 1× 输入；
6. fresh 运行 HCA* / F2 / S4；
7. 输出三种时间口径；
8. 写 `g4irsf24_fresh_hca_race.md`。

这一步即使已经证明 S4 超过 HCA*，也不能结束 G24。

---

# 10. Stage 24B：密集转移数据

## 10.1 不再生成大规模 action-pair 作为主数据

主数据来自正常基线轨迹：

```text
每次 Route decision
选择的 edge
decision time
next decision-ready time
current node
next node
segment goal
static edge/potential
S4 local terms
complete/safe flag
```

不保存：

```text
整套未来事件
全系统逐 bag sidecar
无关 hash
所有候选的完整调试对象
```

## 10.2 数据规模

至少收集：

```text
1× full baseline ×2
2× full baseline ×2
```

若 2× full 已存在完全相同可复用轨迹，可复用；但必须验证字段齐全。

预期应得到：

```text
数十万到百万级真实 transition labels
```

## 10.3 Split

优先使用：

```text
连续时间块
不同任务流 seed / day
不同负载
```

例如：

```text
train：1× day/seed A + 2× 前 60%
validation：2× 中间 20%
test：2× 后 20% + 独立 1×/2× run
```

禁止随机把相邻事件拆到 train/test 两侧。

## 10.4 合法身份特征

允许：

```text
current node
next node
segment goal
leg type
```

因为它们是固定机场物理拓扑。

禁止：

```text
task ID
runtime bag ID
event ordinal
absolute time block codebook
post-hoc outcome ID
HCA* chosen path
```

---

# 11. Stage 24C：P1 DLP-EWMA

## 11.1 离线训练

对每条真实 edge：

```text
统计 actual step delay
EWMA
median
p90
support
```

主值只保留一个 EWMA 或稳健均值；其他统计只用于分析，不进入运行时。

## 11.2 Shadow replay

在不改变动作时报告：

```text
多少决策 P1 与 S4 相同
多少决策会改变
改变集中在哪些物理分支
支持度
预计 margin
```

## 11.3 快速原生门

```text
144 smoke
512 smoke
1× full
```

P1 必须产生真实 native Route mutations。

0 mutation：

```text
不是成功
```

## 11.4 P1 继续门

满足：

```text
1× real mutations >= 20
mean 改善 >= 0.5% 或 >= 1.0 s
p95/p99 不明显退化
0 safety regression
```

则进入 2×。

不满足也不能结束，继续 P2。

---

# 12. Stage 24D：P2 DLP-TD

## 12.1 最小参数

只允许一个小网格：

```text
alpha_v ∈ {0.05, 0.10, 0.20}
beta    ∈ {0.5, 1.0}
min_support ∈ {8, 32}
margin_seconds ∈ {0.5, 2.0}
```

不能全组合暴力跑完。

先根据 validation 依次筛：

```text
alpha
support
margin
beta
```

最多保留：

```text
6–8 个离线候选
2 个原生候选
```

## 12.2 冻结优先

第一阶段：

```text
offline chronological train
freeze table
native closed loop
```

不允许在线探索。

若冻结 P2 已赢，才追加一个：

```text
small-alpha online adaptation
```

作为独立 ablation。

## 12.3 Artifact

建议一个紧凑 JSON 或二进制表：

```text
goal set
edge residual
node-goal value residual
support
fixed margin
fixed beta
```

目标：

```text
< 1 MB
```

不要新增模型注册系统或 hash family。

## 12.4 原生动作归属

必须报告：

```text
eligible Route decisions
DLP-supported decisions
DLP proposals
committed mutations
fallback to S4
shield rejection
OOD/low-support abstention
```

---

# 13. Stage 24E：原生闭环阶梯

顺序：

```text
single-point native parity
144 smoke
512 smoke
1× full
2× full
4× 60s ABBA
```

## 13.1 single-point

至少验证：

```text
DLP 与 S4 值相同时动作完全相同
高 residual 时能改变真实 edge
仅改变候选排序
shield 仍拥有最终提交
无 full route
无 global scan
```

## 13.2 1× full

对照：

```text
HCA* fresh
F2
S4
P1
P2
```

最多两个 DLP arm，不运行 model zoo。

## 13.3 1× DLP 晋级门

相对 S4：

```text
real mutations >= 20
mean 改善 >= 1% 或 >= 2 s
p95 不退化超过 0.1%
p99 不退化超过 0.1%
0 failed
0 deadline regression
0 safety regression
events/completed 增加 <= 3%
```

若 S4 已 fresh 超过 HCA*，DLP 允许：

```text
保持 S4 业务性能
但显著改善 2×/4×
```

## 13.4 2× DLP 晋级门

当前 S4 参考：

```text
mean ≈ 337.843 s
```

要求：

```text
mean 改善 >= 2%
或至少改善 5 s/bag
p95/p99 不退化
0 failure
events/completed 增加 <= 5%
```

## 13.5 关闭当前 S4-v2-safe 差距

按 G22 口径继续报告：

```text
Gap-10
Gap-25
Gap-50
strict v2 win
```

但 G24 主 baseline 是 HCA*，v2-safe 只做强诊断，不是论文主对照。

---

# 14. Stage 24F：Fresh HCA* 主结论

最终必须形成一个完全独立的表：

| Arm | Centralized full route | Runtime A* | Global reservation | Learning | processed mean | p95 | p99/max | wall | complete |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| HCA* | yes | yes | yes | no | | | | | |
| F2 | no/历史边界 | no | no | learned/rule mix | | | | | |
| S4/J2/E2 | no | no | no | no | | | | | |
| DLP | no | no | no | local table | | | | | |

报告必须直接写：

```text
是否 fresh 超过 HCA*
超过多少秒
超过百分之多少
尾部是否同时更好
规划计算是否更快
在 2×/4× 谁还能继续运行
```

不允许只写“方向性证据”。

---

# 15. Stage 24G：4× 与扩展规模

## 15.1 4× 60 秒 ABBA

顺序至少：

```text
S4 → DLP → DLP → S4
```

必要时第二天反序一次。

报告中位数：

```text
completed
released
active backlog
simulated-time progress
events/completed
events/s
wall/CPU/RSS
```

## 15.2 延长门

满足任一：

```text
completed +10%
simulated progress +10%
backlog -10%
events/completed -10%
```

且安全不退化，才运行：

```text
180s
```

## 15.3 4× full

只有：

```text
180s 收益稳定
或候选具有 resumable progress 的明显领先
```

才运行 full。

## 15.4 HCA* 规模比较

HCA* 在 2×/4×：

```text
先设置相同 wall / memory budget
```

输出：

```text
是否生成完整可行计划
规划完成率
已规划任务数
wall
RSS
```

如果 HCA* 超时：

```text
报告 CENTRALIZED_PLANNING_BUDGET_EXCEEDED
```

不能把未完成 HCA* 的业务 TTH 与完整 DLP 直接混算。

---

# 16. Stage 24H：收益后再做因果审计

G20–G23 的问题之一是：

```text
在业务候选还没显示收益前，
就花大量时间生成 exact pair。
```

G24 改成：

```text
先获得 native closed-loop business signal；
再审计真实发生变化的动作。
```

只有 P1/P2 通过 1× 或 2×门后，抽：

```text
64–128 个真实 mutated decisions
```

运行：

```text
H_bag
H_system
```

用途：

```text
确认收益不是转移拥堵；
分析哪些局部值修正有效；
定义论文解释。
```

这不是训练主数据。

---

# 17. Stage 24I：P2 无收益时的强制简单 Pivot

P2 无收益不能立刻结束。

进入：

```text
Reconvergent Corridor Delay
重汇合走廊实际时间
```

## 17.1 思路

只研究：

```text
从一个分支节点出发，
两条方向最终在下游重新汇合的局部走廊。
```

每条走廊学习：

```text
从 branch commit 到 reconvergence 的实际时间 EWMA
```

决策：

```text
走廊实际时间
+
汇合点到目标的静态/学习价值
```

这比通用 DLP 更窄，也更容易解释。

## 17.2 为什么是合理 Pivot

G19 的巨大收益来自极少数 Route 动作。

这说明：

```text
真正高价值的地方可能是几个替代走廊，
不是所有节点。
```

## 17.3 数据与闭环

```text
至少覆盖所有可识别 reconvergent branch pairs
train / validation / test 按时间分开
1× full
2× full
```

仍不做：

```text
完整 route
top-K future path
global guidance graph
```

## 17.4 Pivot 终止门

如果：

```text
DLP-TD 充分 no-go
且 reconvergent corridor 充分 no-go
```

才允许暂时关闭“动态路线价值”方向。

---

# 18. Stage 24J：Tiny model 的唯一解锁条件

只有满足全部：

```text
P2 或 corridor rule 已在 native 1×/2× 有正收益；
真实 mutations >= 50；
存在重复、稳定的残差误差；
表格/线性修正无法解决；
held-out time blocks 同向。
```

才可训练 tiny model。

目标不是直接预测动作，而是预测：

```text
DLP remaining-time residual
```

损失：

```text
Huber / MAE remaining-time regression
```

不是：

```text
稀疏 beneficial/harmful classification
```

原因：

```text
连续时间标签密集；
比稀有正例分类稳定；
输出仍可解释为秒。
```

---

# 19. 安全与故障

## 19.1 正常动作边界

DLP 只：

```text
给合法 MOVE 候选重新排序
```

不拥有：

```text
reservation commit
merge grant
PIBT transaction
fault recovery
```

## 19.2 回退

以下全部回 S4：

```text
value missing
support low
artifact invalid
goal unknown
fault active
stale generation
score margin too小
shield reject
```

## 19.3 故障测试顺序

只有候选通过 1×/2× 后才做：

```text
选择前 fault
选边后、进入前 fault
edge fault during transit
repair 后恢复
```

故障工作量：

```text
<= 总工作量 8%
```

不为极低概率情形新增大框架。

---

# 20. 并行

## 20.1 保留已经验证的并行方式

```text
独立 run / seed / candidate process farm
P=2/4/8
```

用途：

```text
baseline repeats
参数候选
1×/2× paired runs
```

## 20.2 不做单事件循环并行化

除非 profiler 明确显示：

```text
DLP 计算或某个单一函数 >= 20% CPU
```

否则不新建：

```text
parallel event heap
owner shards
lock-free queue
```

DLP 本身应是数组查找，不能成为新瓶颈。

---

# 21. 复杂度硬边界

本轮线上最多增加：

```text
一个局部 delay-potential 数据结构
一个 compact artifact loader
一个 S4 residual score path
少量计数器
```

禁止：

```text
新 planner
新 supervisor
第二 event loop
全图 guidance optimizer
GNN
Transformer
PPO/MAPPO
MCTS
central critic
LNS/CBS/RHCR solver
未来完整路径
全局预约
运行时 HCA/v2 teacher
模型 ensemble
自动特征搜索
逐节点手工规则表
```

## 21.1 参数数量

最终 active artifact 的自由参数不超过：

```text
alpha 或 frozen table
beta
min_support
margin
detour allowance
```

不允许几十个独立阈值。

## 21.2 文件与框架

每个阶段最多：

```text
一个主 runner
一个主报告
一个主表
```

不要复制 G15/G20/G23 的完整框架。

---

# 22. 工作量预算

建议：

```text
Git/构建/基本回归            5%
fresh HCA 对齐               15%
dense transition + DLP       25%
native 1×/2× closed loop     25%
4×/规模                      15%
causal解释/fault              8%
最终报告                      7%
```

禁止：

```text
主要时间花在 hash、seal、manifest、格式核对；
跑了一天却没有 fresh baseline 或 native business run。
```

---

# 23. 防止 Codex 很快“做完”

以下任何单项都不能结束 G24：

```text
PR/CI 状态检查
找到 Java 入口
复刻论文表
一次 fresh HCA run
离线 DLP 表
shadow action comparison
144/512 smoke
P1 no-go
P2 第一个 no-go
1× 一个 arm
一份模型 artifact
一个 profiler
一个报告
4× 60s 单次切片
```

## 路线 A：当前 S4 已 fresh 超过 HCA*

必须继续：

```text
fresh 胜利认证
→ DLP-EWMA
→ DLP-TD
→ 1×/2×
→ 4×
→ 原因审计
```

## 路线 B：S4 未超过 HCA*，DLP 有信号

```text
fresh 差距定位
→ P1/P2
→ 最小参数筛选
→ 1×/2×
→ strict HCA race
→ 4×
```

## 路线 C：通用 DLP no-go

```text
P1 sufficient no-go
→ P2 sufficient no-go
→ reconvergent corridor
→ 1×/2×
```

## 路线 D：DLP 与 corridor 都 no-go

此时才可以：

```text
保留 fresh HCA 结论
记录动态局部价值上限
选一个 profiler-confirmed、预期 >5% 的结构性 scale 问题
```

不能回到：

```text
任意新 hotspot seam + 256 groups + 结束
```

---

# 24. 建议提交序列

```text
G24-A fresh HCA same-protocol runner and table
G24-B dense local transition dataset
G24-C DLP-EWMA shadow/native
G24-D DLP-TD frozen artifact
G24-E 1x/2x HCA race
G24-F reconvergent pivot if needed
G24-G 4x/fault/causal explanation/final
```

每个主提交必须至少包含一项：

```text
fresh baseline
真实 dense labels
真实 native mutations
业务性能结果
规模结果
```

不为 hash 或格式单独提交。

---

# 25. 主要交付物

```text
docs/G4IRSF24_fresh_HCA_race_distributed_value_learning_plan.md
docs/g4irsf24_new_ideas.md

outputs/reports/g4irsf24_fresh_hca_race.md
outputs/reports/g4irsf24_dense_transition_data.md
outputs/reports/g4irsf24_dlp_ewma.md
outputs/reports/g4irsf24_dlp_td.md
outputs/reports/g4irsf24_native_closed_loop.md
outputs/reports/g4irsf24_reconvergent_corridor.md
outputs/reports/g4irsf24_scale.md
outputs/reports/g4irsf24_causal_explanation.md
outputs/reports/g4irsf24_final_joint_decision.md

outputs/tables/g4irsf24_fresh_hca_race.csv
outputs/tables/g4irsf24_transition_summary.csv
outputs/tables/g4irsf24_dlp_ablation.csv
outputs/tables/g4irsf24_closed_loop.csv
outputs/tables/g4irsf24_scale.csv
outputs/tables/g4irsf24_decision_summary.json

artifacts/datasets/g4irsf24_transition_compact.jsonl
artifacts/policies/g4irsf24_dlp_*.json
```

大型逐事件/逐 bag 原始文件：

```text
留在隔离 worktree
不上传 GitHub
```

---

# 26. 最终必须直接回答的 40 个问题

1. PR #8 与 Run #71 是否保持绿色？
2. 原始 Java HCA* 实际入口在哪里？
3. fresh HCA* 是否完整运行？
4. HCA* 是否与 S4 使用完全相同任务？
5. 三种起算口径是否由同一 parser 输出？
6. fresh HCA* processed-attempt min/mean/max 以及额外 p95/p99 是多少？
7. fresh S4 processed-attempt min/mean/max 以及额外 p95/p99 是多少？
8. 当前框架是否已经严格超过 HCA*？
9. 超过多少秒、多少百分比？
10. 是否达到 paper mean 3.96 min？
11. 是否达到 paper min/mean/max range win？
12. HCA* 与 S4 的 wall/CPU/RSS 分别是多少？
13. HCA* 在 2×/4× 是否还能完成规划？
14. dense transition 有多少条？
15. 覆盖多少 edge/node/goal？
16. train/validation/test 如何按时间隔离？
17. P1 学到的 edge delay 与静态时间差多少？
18. P1 改变多少真实动作？
19. P1 的 1×/2× 业务收益多少？
20. P2 的 TD value 是否收敛稳定？
21. P2 的支持度覆盖多少决策？
22. P2 改变多少真实动作？
23. fallback 到 S4 的比例是多少？
24. 哪些物理分支贡献最大？
25. 是否出现绕路或循环？
26. detour guard 拦截多少？
27. 1× mean/p95/p99 如何？
28. 2× mean/p95/p99 如何？
29. source wait 与 network time如何变化？
30. 相对 S4-v2 gap 关闭多少？
31. 4× 60s completed/progress/backlog 如何？
32. 是否解锁 180s/full？
33. DLP 的每动作 CPU 成本多少？
34. 是否仍为 O(out-degree)？
35. 是否读取任何非相邻状态？
36. 64–128 个 changed actions 的 H_system 是否支持闭环收益？
37. DLP no-go 时，reconvergent corridor 是否有收益？
38. fault 下是否保持安全？
39. 最终 active candidate 是什么？
40. 下一阶段最窄、最有价值的问题是什么？

---

# 27. 正式结果标签

```text
FRESH_HCA_STRICT_WIN
FRESH_HCA_CLEAR_WIN
PAPER_TABLE_MEAN_WIN
PAPER_TABLE_RANGE_WIN
FRESH_HCA_NOT_BEATEN

DLP_EWMA_GAIN
DLP_EWMA_NO_GO
DLP_TD_GAIN
DLP_TD_NO_GO
DLP_ONLINE_ADAPTATION_GAIN
DLP_ONLINE_ADAPTATION_NO_GO

RECONVERGENT_CORRIDOR_GAIN
RECONVERGENT_CORRIDOR_NO_GO

TWO_X_BUSINESS_GAIN
FOUR_X_SCALE_GAIN
CENTRALIZED_PLANNING_BUDGET_EXCEEDED
DISTRIBUTED_LOCAL_VALUE_CEILING
```

---

# 28. 论文可形成的最强叙事

若成功：

```text
原 IoT-DRPA/HCA*：
集中式完整路径 + 全局预约

本文：
局部真实延误学习 + 一跳 MOVE + JIT merge + PIBT-like shield
```

主张：

```text
不依赖运行时 A*
不生成完整未来路线
不维护全局预约表
以 O(out-degree) 单步决策运行
在原机场真实拓扑和同任务协议下超过 HCA*
在更大任务流下保持更好的计算扩展性
```

学习贡献不是：

```text
深度网络预测一个稀有动作
```

而是：

```text
每个局部接口从真实交通中学习动态剩余时间，
以密集反馈修正静态最短路。
```

这比继续增加 seam 和 classifier 更统一，也更容易写成一篇完整论文。

---

# 29. 最容易理解的最终概括

G23 已经告诉我们：

> 在几个特殊位置，问“现在要不要临时换边或等一下”，很难找到可泛化规律。

这不代表学习没用。

真正的问题是，我们一直让模型猜一个非常稀有的例外动作。

G24 改成让每个路口长期学习：

> 从这条路走，真实情况下后面还要多久。

这相当于把 HCA* 的“未来路线估计”压缩成每个相邻方向的一个时间数字。

中央 HCA*：

> 先规划整条路线。

G24：

> 只看相邻路口的动态路牌，走一步，再判断一步。

目标仍然完全不变：

```text
每件行李
每个接口
局部学习
一步 MOVE
无运行时 A*
可面对更大任务规模
```
