# czr005 项目总纲：JunctionShield-MARL for Airport ICS Baggage Routing

生成日期：2026-06-16  
项目目录：`C:\PROGRAMING\czr005`  
Conda 环境：`czr005`  
项目性质：机场 Individual Carrier System / ICS 行李系统的去中心化学习路由、工业仿真与 C++ 高性能执行框架  
源代码起点：`jichang_origin` Java/Eclipse 仿真项目，后续作为 legacy reference，不在原仓库上直接硬改。

---

## 0. 执行摘要

czr005 的目标不是简单“把 A* 改成强化学习”，而是构建一个**面向机场 ICS 行李系统的安全去中心化学习路由框架**：

```text
legacy Java ICS simulator
  -> Python reference simulator
  -> C++ high-performance simulation / routing core
  -> Python learning environment
  -> shielded decentralized policy
  -> C++ runtime / batch replay
  -> paper-grade evaluation
```

核心算法暂命名为：

```text
JunctionShield-MARL
```

中文解释：

> 每件行李在岔路口/汇流口/缓冲点进行局部路由决策；策略网络只给出动作偏好；工业安全 shield 负责强制检查容量、headway、节点时间窗、故障边、merge 冲突和死锁风险；Python 负责学习，C++ 负责高性能仿真、baseline 和 runtime replay。

本项目的第一阶段必须先完成：

```text
Java ICS -> Python reference + C++ core
```

理由：

1. Python 方便接 PyTorch、Gymnasium、PettingZoo、MAPPO / IPPO / imitation learning。
2. C++ 能支撑大规模行李流、高频仿真、多 seed 批量 replay、未来 runtime 部署。
3. 没有可信的 Python/C++ 仿真底座，任何 RL 结果都可能只是仿真口径漂移。
4. 原 Java 项目带 GUI、文件输出和静态流程，适合作为 legacy reference，不适合作为学习环境直接扩展。

正确主线只有一条：

```text
faithful ICS simulator
  -> strong non-learning baselines
  -> safe learning policy
  -> C++ runtime integration
  -> large-scale robustness evidence
```

不要一开始写复杂神经网络。先把仿真、约束、指标、baseline 和 safety gate 固定下来。

---

## 1. 项目边界与基本判断

### 1.1 原项目定位

原项目是机场行李 ICS 仿真，核心代码特点如下：

- Java/Eclipse 工程结构。
- `src/RUN/Main.java` 是入口。
- 使用 `map2.txt` 读取地图、`inputdata.txt` 读取任务流。
- 使用 `ICS_PathFinding` 管理路径、故障边、未完成任务和 saved routes。
- `Astar.research(...)` 是核心单件行李路径搜索方法。
- A* 已经包含节点时间窗约束和故障边过滤。
- `Tasks.generate_tasks(...)` 每个 epoch 生成新任务、故障边、修复边和正在路径上的任务状态。

czr005 对它的态度：

```text
legacy/java 只作为 reference。
Python/C++ 重新实现必须做到 map/task/route/metric 可追踪。
不要在 Java GUI 上继续堆学习逻辑。
```

### 1.2 这个问题不是标准 MAPF

标准 MAPF 通常是：

```text
grid / graph
discrete timestep
agents choose move/wait
vertex conflict + edge conflict
all agents start and end once
```

机场 ICS 行李系统更接近：

```text
directed graph
continuous/event time
asynchronous junction decisions
edge travel time = length / speed
node processing time
finite buffer / capacity
merge headway
fault / repair edges
early baggage storage
STD / deadline pressure
continuous task arrivals
industrial controller executes switch decisions
```

因此本项目的学术定位应写成：

```text
event-driven, directed-graph, deadline-aware, lifelong MAPF-like routing for airport ICS baggage systems
```

而不是直接声称“解决标准 MAPF”。

### 1.3 去中心化的含义

这里的“去中心化”不是说真实机场里每件行李都有独立计算机，而是说：

```text
shared policy πθ
local observation oi
per-bag / per-junction action decision
no global combinatorial replan at runtime
execution can still be called from a central simulator/controller
```

也就是**分布式策略结构 + 中央可部署调用**。

这对工业系统更合理：控制器仍然集中管理设备和安全约束，但每个行李的动作计算只依赖局部可观测状态、目标信息、deadline slack 和轻量全局启发式。

---

## 2. 研究问题

主问题：

> 能否用带安全 shield 的去中心化学习策略，在机场 ICS 行李系统中替代或辅助集中式改进 A*，使大规模动态行李流更快、更稳、更少冲突地到达目标？

具体问题：

1. **扩展性**  
   当 active bags 从几十上升到几百、几千时，A*/reservation 反复规划的耗时如何增长？学习策略的 per-decision latency 是否更稳定？

2. **效率**  
   学习策略能否降低平均运输时间、P95/P99 运输时间、等待时间、拥堵程度和误机/迟到行李数量？

3. **安全性**  
   在 hard shield 存在时，能否保证无非法边、无容量冲突、无 headway 冲突、无节点时间窗冲突？

4. **鲁棒性**  
   在故障边、修复边、任务到达率变化、目标分布变化、早到存储区负载变化时，学习策略是否比 fixed heuristic 更稳？

5. **泛化性**  
   在不同地图规模、不同密度、不同起终点分布、不同故障概率下，policy 是否可迁移？

6. **科学贡献**  
   收益是否来自学习到的局部协作/拥堵预判，而不是来自指标误差、仿真漂移、隐藏全局 planner 或不公平算力？

---

## 3. 相关工作定位与可借鉴路线

本项目应从以下方向吸收方法，但不能照搬问题定义。

### 3.1 MAPF / LMAPF 学习路线

| 工作线索 | 可借鉴点 | czr005 采用方式 | 禁止误用 |
|---|---|---|---|
| PRIMAL2 | fully decentralized lifelong MAPF，局部观测、持续任务、可扩展到大量 agent | 采用 shared decentralized policy、lifelong task stream、curriculum learning | 不照搬 grid/FOV；ICS 是 directed event graph |
| DHC | shortest-path heuristic + communication + DQN | 借鉴 shortest-time-to-goal、local communication / GNN | 不让通信替代 safety shield |
| SCRIMP | transformer communication、小 FOV、tie-breaking、intrinsic reward | 借鉴局部通信、对称冲突打破、探索奖励 | 不在无 shield 下追求“学会无碰撞” |
| Learn to Follow | planning + RL collision avoidance hybrid | 采用 global guide + local policy + shield | 不把 RL 写成完全替代 planner |
| MAPF-GPT | 大规模 expert trajectory imitation | 用 A*/SIPP/rolling-horizon 产生 imitation dataset | 不以 action imitation 单独作为最终 claim |
| Work Smarter / CS-PIBT | 简单 learned policy + collision shield 可能胜过复杂大模型 | czr005 必须有 one-step / reservation safety shield baseline | 不把 shield 消融掉后比较 |
| SILLM | imitation + global guidance + collision resolution，可做到大规模 LMAPF | 借鉴 global guidance、single-step collision resolution、large-scale throughput metrics | 不宣称同样可 10k unless 真实跑过 |
| LaGAT | learned graph attention guidance + search hybrid，pretrain then fine-tune | 后期可做 GNN policy / learned guide + C++ baseline hybrid | 不在 Phase1 就引入复杂 GAT |
| MAPF-World | future occupancy / temporal dynamics prediction | 后期加入 future congestion auxiliary head | 不让 world model 直接控制安全 |
| HMAGAT / Hypergraph MAPF | dense bottleneck 中 group interaction 比 pairwise 更重要 | Phase7 可做 bottleneck hyperedge / merge group encoder | 只在 simple GNN plateau 后尝试 |

### 3.2 机场与交通系统相关路线

| 方向 | 借鉴点 | 与 czr005 的差异 |
|---|---|---|
| Airport ground handling neural construction heuristic | 多约束机场场景、RL/attention 可提升实时调度 | 它是地面保障 VRP，不是 ICS 行李轨道内 routing |
| Taxiway RL / conflict-aware routing | action masking、下游冲突预判、安全效率 trade-off | 它是飞机滑行路由，ICS 行李更高频、容量更细 |
| Baggage handling team formation/routing | deadline、time window、stochastic travel time | 它处理人力团队/任务，不是每件行李在轨道岔路口决策 |
| Packet routing MARL | 分布式路由、queue/backlog、local link state | 行李不可丢包、不可重排到非法路线，必须有硬安全约束 |

### 3.3 本项目的差异化

可以写成论文贡献的点：

```text
1. 将机场 ICS 行李 routing 建模为 event-driven directed-graph lifelong MAPF-like problem。
2. 设计 per-bag decentralized junction policy，而不是集中式全局重规划。
3. 引入 industrial reservation / headway / capacity shield，保证安全动作。
4. 提供 Python learning + C++ high-performance simulator 的可复现框架。
5. 系统比较 improved A*、reservation/SIPP、rolling-horizon、PIBT-style shield、learned policy。
6. 分析 deadline、early-bag storage、fault recovery、merge bottleneck 等机场 ICS 特有因素。
```

---

## 4. 主方法：JunctionShield-MARL

### 4.1 总体结构

```text
At each event time / junction arrival:

bag i reaches decision node v
  -> construct local observation oi
  -> compute global guide features h(v, goal_i)
  -> policy πθ scores outgoing actions
  -> action mask removes physically impossible actions
  -> safety shield checks reservation/capacity/headway/fault/deadlock
  -> choose highest safe action
  -> reserve edge/node interval
  -> simulator advances event queue
```

策略网络只负责排序：

```text
πθ(oi, ai) -> score
```

真正执行前必须经过：

```text
Shield( state, action ) -> allowed / blocked / fallback
```

### 4.2 Agent

每个行李、托盘或 carrier 是一个 agent：

```text
bag_id
task_id
current_node
next_node / edge
goal_node
entry_time
STD / deadline
slack = STD - current_time
route_history
waiting_time
fault_exposure
early_bag_flag
```

### 4.3 动作空间

在节点 `v` 的动作：

```text
A(v) = outgoing_edges(v) union {hold}
```

特殊动作：

| 动作 | 含义 |
|---|---|
| `take_edge(v,u)` | 进入下一条有向边 |
| `hold` | 在当前可等待节点/缓冲区等待 |
| `storage_route` | 若是早到行李且业务允许，进入早到存储区 |
| `fallback_shortest` | shield 触发时采用最短路安全 fallback，不作为 policy 原始动作 |

动作必须满足：

```text
edge exists
edge not faulted
edge has available capacity / headway slot
target node has reservation slot or buffer
does not violate hard physical constraint
```

### 4.4 观测

最小观测：

```text
current node id / type
goal node id / type
time-to-goal heuristic for each outgoing edge
edge travel time
node service time
edge fault flag
edge queue length
edge reserved occupancy over next H seconds
target node buffer occupancy
bag slack / deadline risk
local active bag count in k-hop neighborhood
recent shield block count
```

推荐分层观测：

```text
ego features:
  current node, goal, slack, elapsed time, waiting time, priority class

candidate-edge features:
  to_node, travel_time, shortest_time_to_goal, queue, reservation load,
  capacity, headway, fault, downstream bottleneck score

local graph features:
  1-hop / 2-hop node occupancy, merge pressure, storage occupancy

global guide features:
  Dijkstra/SIPP time-to-goal, K-shortest route rank, congestion-adjusted distance
```

### 4.5 Reward

基础 reward：

```text
r_i =
  - α * elapsed_time
  - β * waiting_time
  - γ * shield_block
  - η * congestion_entered
  - λ * late_penalty
  + ρ * goal_reached
```

系统 reward：

```text
R_global =
  - mean_transport_time
  - p95_transport_time
  - late_bags
  - unresolved_tasks
  - shield_blocks
  + throughput
```

训练时采用 CTDE：

```text
centralized critic sees global traffic state
decentralized actor sees local observation only
```

执行时只用 actor + shield。

### 4.6 Safety Shield

shield 是本项目的工业核心，不是可选组件。

检查项：

```text
1. edge fault
2. edge capacity
3. edge headway / minimum separation
4. node time-window conflict
5. merge conflict
6. buffer capacity
7. no route to goal after taking edge
8. potential deadlock / cyclic hold pattern
9. deadline-critical priority override
```

shield 输出：

```text
allowed action
or next best action
or hold
or fallback planner action
or emergency reroute
```

所有 learning 结果必须报告：

```text
shield intervention rate
shield-induced fallback rate
policy unsafe proposal rate
post-shield conflict count
```

### 4.7 不允许的做法

```text
不允许 policy 绕开 edge/node/headway constraint。
不允许为了指标好看删除 difficult bags。
不允许无 shield 直接比较 RL 与 A* 并声称可部署。
不允许改动物理仿真语义后仍说与原 A* 同口径。
不允许只报告 mean travel time，不报告 P95/P99、late、conflict、runtime。
```

---

## 5. 工程架构

### 5.1 双语言策略

```text
Python:
  reference simulator
  Gym/PettingZoo environment
  data preprocessing
  training
  offline analysis
  plotting/reporting

C++:
  graph and event simulator
  baseline planners
  reservation table / shield
  high-throughput replay
  pybind11 binding
  optional ONNX/LibTorch inference
```

### 5.2 为什么不要只用 Python

Python 能快速研究，但大规模仿真会卡在：

```text
event queue
reservation checking
many active bags
many seeds
many baseline replays
many RL rollout environments
```

C++ core 可以带来：

```text
deterministic replay
lower latency
batch simulation
future deployment path
solver parity tests
```

### 5.3 为什么不要只用 C++

纯 C++ 不利于：

```text
PyTorch 训练
快速特征迭代
notebook diagnostics
Gym-compatible algorithms
large dataset preprocessing
ablation and plotting
```

因此必须是：

```text
C++ core + Python learning shell
```

### 5.4 推荐目录结构

```text
C:\PROGRAMING\czr005
├── README.md
├── environment.yml
├── pyproject.toml
├── CMakeLists.txt
├── .gitignore
├── legacy
│   └── jichang_origin_readonly
├── data
│   ├── raw
│   ├── processed
│   ├── maps
│   └── tasks
├── cpp
│   ├── ics_core
│   │   ├── graph
│   │   ├── sim
│   │   ├── routing
│   │   ├── reservation
│   │   ├── shield
│   │   ├── metrics
│   │   └── bindings
│   ├── tests
│   └── third_party
├── src
│   └── czr005
│       ├── io
│       ├── sim_py
│       ├── envs
│       ├── baselines
│       ├── datasets
│       ├── models
│       ├── train
│       ├── eval
│       ├── metrics
│       └── viz
├── configs
│   ├── sim
│   ├── baselines
│   ├── il
│   ├── rl
│   └── eval
├── scripts
│   ├── setup
│   ├── convert_legacy
│   ├── smoke
│   ├── train
│   └── eval
├── docs
│   ├── codex-worklog.md
│   ├── implementation-notes.md
│   ├── literature-notes.md
│   ├── design-decisions.md
│   └── safety-spec.md
├── outputs
│   ├── reports
│   ├── tables
│   ├── figures
│   └── logs
└── artifacts
    ├── teacher
    ├── replay
    ├── models
    └── runtime
```

### 5.5 C++ core 模块

| 模块 | 职责 |
|---|---|
| `Graph` | nodes, edges, node type, service time, coordinates, outgoing adjacency |
| `TaskStream` | entry time, STD, start, goal, early storage rule |
| `EventSim` | event queue, bag states, edge traversal, node service, fault/repair events |
| `ReservationTable` | node/edge interval reservation, capacity, headway |
| `AStarPlanner` | faithful improved A* baseline |
| `SIPPPlanner` | safe interval path planning baseline |
| `RollingHorizonPlanner` | periodic replanning baseline |
| `PIBTStyleShield` | one-step conflict resolution / priority tie-breaking |
| `JunctionShield` | hard action validation and fallback |
| `Metrics` | travel time, throughput, late, conflict, runtime |
| `Pybind` | Python bindings for env and replay |

### 5.6 Python 模块

| 模块 | 职责 |
|---|---|
| `czr005.io` | parse legacy map/task files, export normalized JSON/NPZ |
| `czr005.sim_py` | readable reference simulator |
| `czr005.envs` | Gymnasium/PettingZoo-style environments |
| `czr005.baselines` | Python wrappers for C++ planners and simple baselines |
| `czr005.datasets` | expert trajectory, junction slice, replay dataset |
| `czr005.models` | MLP, GNN, attention, risk head |
| `czr005.train` | BC, IL, IPPO/MAPPO, offline RL experiments |
| `czr005.eval` | batch replay, baseline comparison, ablation |
| `czr005.metrics` | one shared metrics implementation |
| `czr005.viz` | route plots, congestion heatmaps, bottleneck maps |

---

## 6. Conda 环境

环境名固定为：

```text
czr005
```

Windows 初始化建议：

```bat
mkdir C:\PROGRAMING\czr005
cd /d C:\PROGRAMING\czr005

conda create -n czr005 python=3.11 -y
conda activate czr005
```

基础依赖建议：

```yaml
name: czr005
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - cmake
  - ninja
  - make
  - git
  - cxx-compiler
  - pybind11
  - numpy
  - scipy
  - pandas
  - matplotlib
  - pyyaml
  - networkx
  - tqdm
  - pytest
  - pytest-cov
  - scikit-learn
  - statsmodels
  - pip
  - pip:
      - gymnasium
      - pettingzoo
      - supersuit
      - tensorboard
      - rich
      - ruff
      - mypy
      - py-spy
```

PyTorch 建议单独安装，按本机 CUDA 版本决定。不要在总纲中假设固定 GPU wheel，实际安装后写入：

```text
outputs/reports/phase0_environment_report.md
```

C++ 构建默认：

```bat
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure
```

---

## 7. Git 管理规范

推荐分支：

| 分支 | 用途 |
|---|---|
| `main` | 始终可构建、文档齐全、阶段成果稳定 |
| `phase0-project-hygiene` | 初始化目录、环境、legacy import、文档 |
| `phase1-python-cpp-port` | Java -> Python/C++ faithful translation |
| `phase1a-parity-speed` | parity tests and C++ speed benchmark |
| `phase2-baselines` | A*/SIPP/reservation/rolling/PIBT-style baselines |
| `phase3-learning-env` | Gym/PettingZoo env and observation/action/reward |
| `phase4-teacher-data` | expert trajectory and junction-slice datasets |
| `phase5-imitation` | BC/GNN imitation policy and shadow evaluation |
| `phase6-rl-finetune` | IPPO/MAPPO/value-decomposition RL |
| `phase7-advanced-models` | graph/hypergraph/world-model extensions |
| `phase8-runtime` | C++ inference, ONNX/LibTorch, high-throughput replay |
| `phase9-paper-eval` | large-scale experiments, ablations, paper figures |

Commit 前缀：

| 前缀 | 用途 |
|---|---|
| `docs:` | 指南、报告、worklog、literature notes |
| `deps:` | conda、cmake、third-party |
| `legacy:` | legacy Java import / converter |
| `io:` | map/task parser and schema |
| `sim:` | simulator |
| `cpp:` | C++ core |
| `bind:` | pybind11 |
| `baseline:` | A*/SIPP/reservation/PIBT baselines |
| `shield:` | safety shield |
| `env:` | Gym/PettingZoo env |
| `data:` | teacher dataset / manifest |
| `model:` | policy/risk/GNN models |
| `train:` | training scripts |
| `eval:` | evaluation pipeline |
| `metrics:` | metrics implementation |
| `test:` | tests/smoke/parity |
| `fix:` | bug fix |

禁止提交：

```text
build/
__pycache__/
.venv/
large raw logs
large replay datasets
checkpoints
tensorboard event dumps
temporary GUI screenshots
generated task/*.txt explosions
```

可以提交：

```text
small sample data
schemas
manifests
summary CSV
figures
reports
config files
unit tests
```

---

## 8. Markdown 研究纪律

沿用 czr004 的纪律，但针对 czr005 增加 safety 和 parity 要求。

强制规则：

```text
没有 docs/codex-worklog.md 条目，不开始写核心代码。
没有 outputs/reports/exp_*.md 草稿，不跑重要实验。
没有 parity report，不承认 Python/C++ port 完成。
没有 safety report，不承认 RL policy 可比较。
没有 seed/config/map/task/runtime metadata，不进入主表。
```

每次 worklog 至少包含：

```markdown
## YYYY-MM-DD HH:MM - short title

- Request:
- Branch:
- Files changed:
- Commands run:
- Key observations:
- Tests / validation:
- Safety / parity notes:
- Follow-up:
```

实验报告模板：

```markdown
# exp_YYYYMMDD_HHMM_name

## Question

## Code State
- commit:
- branch:
- dirty files:

## Config
- map:
- task stream:
- method:
- active bags:
- seeds:
- fault setting:
- time horizon:
- hardware:

## Results

## Safety
- conflicts:
- shield blocks:
- illegal action proposals:
- fallback count:

## Interpretation

## Repro Command
```

Bug 报告模板：

```markdown
# bug_YYYYMMDD_name

## Symptom
## Scope
## Suspected cause
## Minimal repro
## Fix
## Validation
## Remaining risk
```

---

## 9. 数据格式与 schema

### 9.1 Normalized map schema

将 `map2.txt` 转换为：

```json
{
  "map_id": "map2",
  "nodes": [
    {
      "id": 0,
      "type": "source",
      "service_time": 0.0,
      "x": 30,
      "y": 0,
      "out": [6]
    }
  ],
  "edges": [
    {
      "from": 0,
      "to": 6,
      "length": 20.0,
      "speed": 2.5,
      "capacity": 1,
      "headway": 0.0
    }
  ],
  "special_nodes": {
    "early_storage_entry": 47,
    "early_storage_exit": 52
  }
}
```

### 9.2 Normalized task schema

```json
{
  "task_id": 1,
  "bag_id": 1,
  "entry_time": 8260.0,
  "std": 13000.0,
  "start": 0,
  "goal": 48,
  "priority": "normal",
  "early_bag": false
}
```

### 9.3 Event trace schema

```json
{
  "time": 8265.0,
  "bag_id": 1,
  "event": "junction_decision",
  "node": 6,
  "goal": 48,
  "candidate_edges": [[6, 8], [6, 12]],
  "policy_scores": [0.3, 0.7],
  "masked": [false, false],
  "shield_result": "allowed",
  "chosen_edge": [6, 12],
  "reservation": {
    "edge_interval": [8265.0, 8270.0],
    "node_interval": [8270.0, 8271.0]
  }
}
```

### 9.4 Replay manifest

```json
{
  "run_id": "20260616_smoke_001",
  "commit": "...",
  "config_hash": "...",
  "map_id": "map2",
  "task_file": "inputdata.txt",
  "method": "astar_cpp",
  "seed": 61,
  "horizon": 8260,
  "hardware": "..."
}
```

---

## 10. 指标锁定

所有方法必须共享同一个 metrics 实现。

### 10.1 业务效率指标

| 指标 | 方向 | 说明 |
|---|---:|---|
| `mean_transport_time` | 越低越好 | 从进入系统到到达目标 |
| `p95_transport_time` | 越低越好 | 长尾体验 |
| `p99_transport_time` | 越低越好 | 极端拥堵 |
| `mean_waiting_time` | 越低越好 | 节点/缓冲等待 |
| `throughput_bags_per_hour` | 越高越好 | 系统吞吐 |
| `late_bag_count` | 越低越好 | 超过 STD 或业务 deadline |
| `early_storage_overflow` | 越低越好 | 早到存储压力 |
| `unresolved_bags` | 越低越好 | 仿真结束仍未完成 |

### 10.2 安全指标

| 指标 | 方向 | 说明 |
|---|---:|---|
| `post_shield_conflicts` | 必须为 0 | shield 后实际冲突 |
| `illegal_action_count` | 必须为 0 | 进入不存在/故障/容量满边 |
| `headway_violation_count` | 必须为 0 | 违反最小间隔 |
| `node_capacity_violation_count` | 必须为 0 | 节点/缓冲容量 |
| `deadlock_count` | 越低越好 | 无进展循环 |
| `shield_intervention_rate` | 诊断 | 越低通常越好，但不是硬目标 |
| `unsafe_policy_proposal_rate` | 越低越好 | policy 原始动作的安全性 |

### 10.3 算法与系统指标

| 指标 | 方向 | 说明 |
|---|---:|---|
| `decision_latency_us` | 越低越好 | per junction decision |
| `sim_steps_per_second` | 越高越好 | 仿真吞吐 |
| `planner_runtime_ms` | 越低越好 | A*/baseline 规划耗时 |
| `replan_count` | 越低通常越好 | 重规划频率 |
| `cpp_vs_python_speedup` | 越高越好 | C++ core 收益 |
| `memory_mb` | 越低越好 | 大规模仿真 |
| `training_samples_per_second` | 越高越好 | rollout 数据采集效率 |

### 10.4 学习诊断指标

| 指标 | 说明 |
|---|---|
| `bc_action_accuracy` | imitation 诊断，不是最终指标 |
| `safe_top1_rate` | policy top1 是否 shield allowed |
| `safe_topk_recovery_rate` | top-k 中是否有 safe action |
| `regret_to_expert_action` | 与 expert route cost 差距 |
| `value_loss / policy_loss` | RL 训练诊断 |
| `OOD_score` | 是否超出训练分布 |
| `fallback_reason_histogram` | 为什么回退到 baseline |

最终论文只以 closed-loop system metrics 为主，不以 offline accuracy 单独作为贡献。

---

## 11. Baseline ladder

Baseline 必须从简单到强逐层建立。

| 层级 | 方法 | 用途 |
|---:|---|---|
| B0 | Original Java improved A* | legacy reference |
| B1 | Python faithful A* | 可读 reference |
| B2 | C++ faithful A* | 快速 baseline |
| B3 | Reservation-table A* | 显式容量/时间窗 baseline |
| B4 | SIPP / safe interval path planning | 连续时间/安全间隔强 baseline |
| B5 | Rolling-horizon prioritized A* | 大规模动态任务 baseline |
| B6 | Shortest-path + queue-aware routing | 简单可部署 heuristic |
| B7 | PIBT / CS-PIBT-style one-step shield | 学习策略必须比较的 shield baseline |
| L1 | BC policy + shield | imitation 最小学习 baseline |
| L2 | GNN policy + shield | 图结构学习 baseline |
| L3 | IPPO/MAPPO fine-tuned policy + shield | 主 RL candidate |
| L4 | world-model / hypergraph policy + shield | 后期 advanced candidate |
| O1 | oracle best of baselines | 只作诊断，不作可部署方法 |

任何学习方法必须至少同时比较：

```text
B2 C++ faithful A*
B4/SIPP or reservation A*
B5 rolling-horizon
B6 queue-aware heuristic
B7 shield baseline
```

---

## 12. 阶段路线

## Phase0：项目卫生、环境和 legacy 固定

目标：建立 `C:\PROGRAMING\czr005`，创建 `czr005` conda 环境，固定 legacy reference 和文档纪律。

必须完成：

```text
1. 创建项目目录 C:\PROGRAMING\czr005
2. 初始化 git
3. 创建 conda env czr005
4. 创建 README.md / environment.yml / .gitignore
5. 创建 docs/codex-worklog.md 第一条
6. 创建 outputs/reports/phase0_startup_plan.md
7. 导入 jichang_origin 到 legacy/jichang_origin_readonly
8. 记录 legacy commit / file hash / source repo URL
9. 写 docs/implementation-notes.md，说明原 Java GUI 和文件输出不会作为学习接口
```

Gate：

```text
git status clean
conda activate czr005 works
cmake --version works
python -c "import numpy" works
legacy source hash recorded
```

---

## Phase1：Java -> Python reference + C++ core faithful port

这是用户明确指定的第一阶段，也是整个项目最重要的地基。

目标：

```text
把原 Java ICS 仿真逻辑拆成 headless Python reference 和 C++ high-performance core。
```

### Phase1A：Legacy parser and schema

必须实现：

```text
src/czr005/io/legacy_map.py
src/czr005/io/legacy_tasks.py
scripts/convert_legacy/convert_map2.py
scripts/convert_legacy/convert_inputdata.py
```

输出：

```text
data/processed/maps/map2.json
data/processed/tasks/inputdata.jsonl
outputs/reports/phase1_legacy_schema_report.md
```

Gate：

```text
node count equal
edge count equal
source/end/storage nodes equal
heuristic table parsed or recomputed
task count equal
early-bag split rule matched
```

### Phase1B：Python reference simulator

必须实现：

```text
src/czr005/sim_py/graph.py
src/czr005/sim_py/task_stream.py
src/czr005/sim_py/event_sim.py
src/czr005/sim_py/astar.py
src/czr005/sim_py/reservation.py
src/czr005/sim_py/metrics.py
```

要求：

```text
headless
deterministic
no GUI dependency
no hidden file writes during step()
all outputs through structured logs
```

Gate：

```text
small route tests pass
A* route on known pairs matches Java or is explained
event transition tests pass
fault edge test pass
early storage test pass
```

### Phase1C：C++ core

必须实现：

```text
cpp/ics_core/graph
cpp/ics_core/task_stream
cpp/ics_core/event_sim
cpp/ics_core/astar
cpp/ics_core/reservation
cpp/ics_core/metrics
cpp/tests
```

要求：

```text
C++17 or C++20
deterministic random seed
no GUI
no global mutable singleton
all core data serializable
```

Gate：

```text
ctest passes
C++ parser equals Python parser
C++ A* equals Python A* on smoke cases
C++ sim equals Python sim on small deterministic task stream
```

### Phase1D：pybind11 boundary

必须实现：

```text
cpp/ics_core/bindings
src/czr005/cpp_backend.py
```

Python 能调用：

```python
Graph.from_json(...)
Simulator(...)
planner.plan(...)
sim.step_until(...)
sim.run_episode(...)
```

Gate：

```text
pytest tests/test_cpp_binding_smoke.py passes
1000-step smoke no crash
deterministic seed replay equal
```

### Phase1E：Parity and speed report

输出：

```text
outputs/reports/phase1_python_cpp_port_report.md
outputs/tables/phase1_parity_cases.csv
outputs/tables/phase1_speed_benchmark.csv
```

Gate：

```text
Python reference accepted
C++ core accepted
known deviations documented
C++ speedup measured
```

不完成 Phase1，不进入学习。

---

## Phase1a：Legacy A* 复现与大规模瓶颈诊断

目标：证明“改进 A* 不适合大规模”的说法不是主观判断，而是有复现数据支撑。

必须完成：

```text
1. 原始 map2 / inputdata 下 Java/Python/C++ 三者行为对齐。
2. 构造任务密度 sweep：1x, 2x, 4x, 8x, 16x。
3. 构造地图规模 sweep：原图、复制扩展图、随机 ICS-like 图。
4. 记录 planner runtime、unfinish queue、replan count、conflict avoidance delay。
5. 分析 A* 开销来自 open list、reservation constraints、replan、fault handling 还是 task backlog。
```

输出：

```text
outputs/reports/phase1a_astar_scalability_diagnosis.md
outputs/tables/phase1a_astar_scalability.csv
outputs/figures/phase1a_runtime_vs_active_bags.png
```

Gate：

```text
A* bottleneck has quantitative evidence
large-scale target for RL is defined
baseline unfairness risk documented
```

---

## Phase2：强 baseline 和 safety shield

目标：在 RL 前建立足够强的非学习 baseline 和工业安全 shield。

必须实现：

```text
ReservationTable
SIPPPlanner
RollingHorizonPlanner
QueueAwareShortestPath
PIBTStyleOneStepResolver
JunctionShield
```

### Phase2A：Reservation model

约束：

```text
edge interval
node interval
capacity
headway
buffer
fault edge
merge conflict
```

Gate：

```text
no false allowed conflict
no false blocked on simple safe cases
interval arithmetic unit tests pass
```

### Phase2B：SIPP / safe interval path planning

目标：

```text
用 safe intervals 替代简单节点时间窗扫描，作为强 baseline。
```

Gate：

```text
SIPP solves cases where naive A* over-waits
SIPP never violates reservation
runtime recorded
```

### Phase2C：Rolling-horizon prioritized baseline

目标：

```text
周期性重规划 active bags，作为大规模非学习 baseline。
```

Gate：

```text
works under task stream
fault recovery works
replan cost reported
```

### Phase2D：PIBT / CS-PIBT-style shield baseline

目标：

```text
建立 one-step conflict resolution baseline。
```

ICS 适配：

```text
candidate = outgoing edge / hold
priority = deadline risk + waiting time + local congestion
backtracking = recursively resolve merge/next-node conflicts
```

Gate：

```text
one-step shield works
can run without learning policy
learning policy must beat or match this baseline
```

输出：

```text
outputs/reports/phase2_baseline_and_shield_report.md
```

---

## Phase3：学习环境定义

目标：构建可训练、可 replay、可诊断的 Python learning environment。

必须实现：

```text
src/czr005/envs/ics_junction_env.py
src/czr005/envs/vectorized_ics_env.py
src/czr005/envs/observation_builder.py
src/czr005/envs/reward.py
src/czr005/envs/action_mask.py
```

接口建议：

```python
obs, info = env.reset(seed=...)
obs, reward, terminated, truncated, info = env.step(policy_actions)
```

多 agent 格式可以支持：

```text
PettingZoo ParallelEnv
or custom batched junction-decision dataset
```

但不要为了兼容某个 RL 框架牺牲仿真语义。

Gate：

```text
random safe policy runs
shortest-path policy runs
queue-aware policy runs
no post-shield conflicts
episode logs complete
```

输出：

```text
outputs/reports/phase3_learning_env_report.md
```

---

## Phase4：teacher 数据与 imitation learning

目标：先学 strong baseline 的行为，再考虑 RL fine-tuning。

### Phase4A：Expert source

可用 expert：

```text
faithful A*
reservation A*
SIPP
rolling-horizon planner
queue-aware shortest path
PIBT-style resolver
oracle-best diagnostic
```

### Phase4B：Dataset

样本单位：

```text
junction decision slice
```

字段：

```text
obs
candidate_edges
action_mask
expert_action
expert_rank
expert_cost_to_goal
future_delay
shield_result
```

输出：

```text
artifacts/teacher/junction_slices_manifest.jsonl
outputs/reports/phase4_teacher_dataset_report.md
```

### Phase4C：BC baselines

模型顺序：

```text
MLP-EdgeScore
DeepSets-CandidateEncoder
GraphSAGE-JunctionPolicy
GAT-JunctionPolicy
```

第一版只做：

```text
MLP-EdgeScore + shield
```

Gate：

```text
offline safe top1 >= baseline threshold
safe topk recovery good
shadow replay does not increase unsafe proposals drastically
closed-loop with shield no conflict
```

---

## Phase5：Shadow mode 与 shielded policy replay

目标：学习策略先在 shadow mode 运行，不直接影响系统，观察它会做什么。

Shadow mode：

```text
baseline executes action
policy proposes action
shield evaluates policy action
log disagreement
log whether policy action would be safe
log local cost delta
```

必须报告：

```text
policy-baseline disagreement
unsafe proposal rate
safe improvement opportunity
would-have-waited vs would-have-progressed
deadline-critical mistakes
```

只有 shadow pass 后，policy 才能进入 closed-loop replay。

Gate：

```text
zero post-shield conflict
unsafe proposal rate acceptable
no catastrophic deadline-critical mistakes
closed-loop L1 policy at least matches simple queue-aware baseline on smoke
```

输出：

```text
outputs/reports/phase5_shadow_and_closed_loop_smoke.md
```

---

## Phase6：RL fine-tuning

目标：在 imitation 的基础上做安全 RL，不从零随机探索。

候选算法顺序：

```text
1. IPPO + action mask + shield
2. MAPPO centralized critic + decentralized actor
3. VDN/QMIX-style value decomposition for local graph groups
4. DQN only for small discrete candidate experiments
```

训练原则：

```text
start from BC checkpoint
curriculum density
fault curriculum
deadline curriculum
domain randomization
early stopping by safety and closed-loop metrics
```

奖励不要只用终点奖励，必须含：

```text
travel time
waiting
deadline risk
shield block penalty
congestion penalty
goal reward
late penalty
```

Gate：

```text
RL fine-tune improves at least one closed-loop metric
no safety regression
no severe overfit to map2
compares against BC+shield and PIBT-style shield baseline
```

输出：

```text
outputs/reports/phase6_rl_finetune_report.md
```

---

## Phase7：高级模型路线

只有在 Phase5/Phase6 简单模型 plateau 后再进入。

### Route A：GNN local graph policy

输入：

```text
k-hop local graph
edge occupancy
reservation load
candidate edge features
goal direction features
```

输出：

```text
candidate edge score
risk/fallback score
```

### Route B：Communication / transformer policy

借鉴 SCRIMP / SILLM：

```text
local agent embedding
neighbor message
bottleneck message
global guide token
```

### Route C：Future congestion auxiliary model

借鉴 MAPF-World：

```text
predict next-H-second edge occupancy
predict merge queue
predict future shield blocks
predict deadline risk
```

### Route D：Hypergraph bottleneck encoder

借鉴 HMAGAT：

```text
merge group hyperedge
shared corridor hyperedge
storage contention hyperedge
deadline-critical group hyperedge
```

Gate：

```text
simple GNN beaten
ablation proves advanced component useful
runtime overhead acceptable
```

---

## Phase8：C++ runtime integration

目标：把训练好的 policy 放回 C++ replay/runtime。

可选路线：

```text
ONNX Runtime
LibTorch
TorchScript if supported
C++ MLP hand export for simple model
```

优先级：

```text
1. Export MLP-EdgeScore to pure C++ for latency baseline
2. ONNX Runtime for GNN/attention
3. Python server only as diagnostic, not final runtime
```

Gate：

```text
C++ inference equals Python within tolerance
latency measured
batch replay works
fallback when model unavailable works
no safety constraint depends on neural output
```

输出：

```text
outputs/reports/phase8_cpp_runtime_report.md
```

---

## Phase9：主实验与论文级评估

目标：形成可投论文的实验包。

实验维度：

```text
map scale:
  original map2
  enlarged ICS-like graphs
  synthetic hub-and-spoke graphs
  bottleneck-heavy graphs
  random directed conveyor graphs

task density:
  low / medium / high / overload

fault:
  none
  random edge fault
  clustered fault
  long repair time
  repeated fault/repair

deadline:
  loose
  normal
  tight
  mixed STD

storage:
  no early storage
  finite early storage
  overloaded early storage
```

必须比较：

```text
A*
reservation A*
SIPP
rolling-horizon A*
queue-aware heuristic
PIBT-style shield
BC+shield
RL+shield
advanced model if available
```

必须报告：

```text
mean/P95/P99 transport time
throughput
late bags
unresolved bags
waiting
shield intervention
post-shield conflicts
runtime
latency
memory
replan count
statistical significance
```

Gate：

```text
learning method beats or safely matches strong baselines in at least one meaningful regime
large-scale runtime advantage documented
no conflict/safety regression
negative cases honestly reported
```

---

## Phase10：论文与开源收尾

必须交付：

```text
README.md
environment.yml
docs/implementation-notes.md
docs/safety-spec.md
docs/literature-notes.md
outputs/reports/final_experiment_report.md
outputs/reports/final_claim_ledger.md
outputs/tables/main_results.csv
outputs/figures/*.png
artifact manifest
repro commands
```

论文 claim ledger：

| Claim | Required evidence |
|---|---|
| Python/C++ simulator faithful | Phase1 parity report |
| A* scalability bottleneck | Phase1a scalability report |
| Shield guarantees safety | Phase2 safety tests and zero post-shield conflicts |
| Policy reduces congestion | Phase9 paired closed-loop metrics |
| Runtime scalable | C++ latency and large-scale replay |
| Generalizes | heldout map / density / fault experiments |

---

## 13. Safety gates

### 13.1 Hard safety gate

任何方法进入主表前必须满足：

```text
post_shield_conflicts == 0
illegal_action_count == 0
headway_violation_count == 0
node_capacity_violation_count == 0
```

若不满足，只能写成 failed diagnostic，不能和 baseline 做性能 claim。

### 13.2 Baseline fairness gate

学习方法比较前必须确认：

```text
same map
same task stream
same seeds
same fault schedule
same capacity/headway rules
same time horizon
same metrics implementation
same hardware or normalized runtime
```

### 13.3 No hidden central planner gate

若 policy 在执行时使用全局未来路径或完整全局 reservation table，必须明说。不能把 central planner 包装成 decentralized policy。

允许使用：

```text
precomputed shortest-time-to-goal
local reservation window
local k-hop occupancy
global scalar congestion summary
```

不允许未经声明使用：

```text
full future optimal route
oracle future task arrivals
baseline expert action at runtime
global replan output as policy input
```

### 13.4 Learning promotion gate

从 BC 到 RL，从 Python 到 C++ runtime，每一步都需要单独 gate：

```text
offline fit
shadow safety
closed-loop smoke
multi-seed validation
heldout density/map
runtime latency
```

---

## 14. 推荐模型路线

### 14.1 第一模型：MLP-EdgeScore

输入每个候选边特征，输出 score：

```text
score_e = MLP([ego, edge, local traffic, guide])
```

优点：

```text
easy export
fast
easy debug
good ablation baseline
```

### 14.2 第二模型：GraphSAGE-JunctionPolicy

输入 k-hop local graph，输出候选边 score。

优点：

```text
matches graph nature
better bottleneck awareness
still manageable
```

### 14.3 第三模型：GAT/Transformer Communication

用于 dense / bottleneck 场景：

```text
candidate-edge tokens
neighbor-bag tokens
bottleneck tokens
goal-guide token
```

### 14.4 风险/回退头

所有模型都建议输出：

```text
policy action score
risk score
fallback score
```

如果 risk 高：

```text
defer to shield baseline / queue-aware / SIPP local repair
```

不要让 policy 在 OOD 场景强行决策。

---

## 15. 训练策略

### 15.1 Curriculum

```text
Stage A: no fault, low density, loose deadline
Stage B: medium density
Stage C: high density / bottleneck
Stage D: random fault/repair
Stage E: tight deadline / early storage pressure
Stage F: heldout maps
```

### 15.2 Imitation first

流程：

```text
expert replay
junction slice dataset
BC train
shadow replay
closed-loop smoke
```

### 15.3 RL second

流程：

```text
initialize from BC
action mask
shield
centralized critic
domain randomization
evaluate every N updates
early stop on safety regression
```

### 15.4 Offline / safe fine-tuning optional

如果真实 closed-loop RL 太不稳定，可先做：

```text
advantage-weighted behavior cloning
conservative Q-learning diagnostic
decision transformer diagnostic
```

但最终必须回到 closed-loop replay。

---

## 16. 可能的论文题目

中文：

```text
面向机场 Individual Carrier System 的安全去中心化多智能体学习路由
```

英文备选：

```text
JunctionShield-MARL: Safe Decentralized Learning for Dynamic Baggage Routing in Airport Individual Carrier Systems

Shielded Decentralized Junction Routing for Event-Driven Airport Baggage Handling Systems

Learning to Route Baggage at Scale: A Safe Multi-Agent Framework for Airport Individual Carrier Systems
```

---

## 17. 顶会/顶刊口味判断

### 17.1 AAAI / IJCAI / ICAPS / SOCS / MAPF workshop

喜欢：

```text
clear problem formulation
strong search/planning baselines
safety guarantees
ablation
runtime scaling
honest failure cases
```

不喜欢：

```text
weak baseline
only offline accuracy
unclear collision semantics
claim RL solves everything
```

### 17.2 ICRA / IROS / RA-L

喜欢：

```text
realistic simulator
industrial constraints
safety fallback
runtime deployment path
robustness under faults
```

不喜欢：

```text
pure toy grid
unbounded neural controller
no latency measurement
```

### 17.3 NeurIPS / ICML / ICLR / AAMAS

喜欢：

```text
learned policy with strong generalization
large-scale datasets
OOD / ablation / negative controls
communication or graph inductive bias
calibration / uncertainty / safety
```

不喜欢：

```text
hand heuristic disguised as learning
small single-map experiment
no randomized controls
no heldout maps
```

最现实的投稿定位：

```text
first paper:
  CIE / Transportation Research Part C/E / IEEE T-ITS / Expert Systems with Applications / Computers & Operations Research
  or ICAPS/SOCS/MAPF workshop first

stronger version:
  ICRA/IROS/AAAI if simulator, baselines, safety and scaling evidence are strong
```

---

## 18. 禁止事项

```text
不要在 Java GUI 上直接塞 RL。
不要跳过 Python/C++ parity。
不要只做 toy grid MAPF。
不要无 shield 训练后直接 claim safe。
不要把 expert action accuracy 当作最终结果。
不要只和旧 A* 比，必须有 SIPP/rolling/PIBT-style/queue-aware baseline。
不要隐藏 failure/fallback。
不要让 C++ 和 Python 指标各写一套。
不要提交大 raw logs/checkpoints。
不要把 exact CIE paper title/official reproduction 写死，除非后续确认论文信息。
```

---

## 19. 直接给 Codex 的首轮任务

```text
Project: czr005
Path: C:\PROGRAMING\czr005
Conda env: czr005

This is a planning + Phase0/Phase1 setup round.

Tasks:
1. Create the project directory and git repo.
2. Create conda environment czr005 with Python 3.11.
3. Add README.md, environment.yml, .gitignore, pyproject.toml, CMakeLists.txt.
4. Add docs/codex-worklog.md with the first entry.
5. Add docs/implementation-notes.md and docs/safety-spec.md skeletons.
6. Import the original Java ICS project into legacy/jichang_origin_readonly or document the exact source path if not copied.
7. Implement only legacy parsers first:
   - parse map2.txt
   - parse inputdata.txt
   - export normalized JSON/JSONL
8. Add pytest tests for parser counts and schema.
9. Do not write RL code in this round.
10. Do not modify legacy Java files.
11. Output outputs/reports/phase0_startup_plan.md and outputs/reports/phase1_legacy_schema_report.md.
```

---

## 20. 近期执行顺序

最合理顺序：

```text
1. Phase0 project hygiene
2. Phase1A legacy parser/schema
3. Phase1B Python reference simulator
4. Phase1C C++ core
5. Phase1D pybind11
6. Phase1E parity/speed report
7. Phase1a A* scalability diagnosis
8. Phase2 baselines and shield
9. Phase3 learning env
10. Phase4 teacher data + BC
11. Phase5 shadow and closed-loop smoke
12. Phase6 RL fine-tune
13. Phase7 advanced graph/hypergraph/world-model
14. Phase8 C++ runtime
15. Phase9 paper eval
```

czr005 的核心品味应该是：

```text
先仿真可信，再 baseline 强，再 learning 安全，最后才讲大规模和论文。
```

---

## 21. 参考线索清单

后续写 `docs/literature-notes.md` 时建议整理 BibTeX：

```text
PRIMAL2: Pathfinding via Reinforcement and Imitation Multi-Agent Learning -- Lifelong
DHC: Distributed Heuristic Multi-Agent Path Finding with Communication
SCRIMP: Scalable Communication for Reinforcement- and Imitation-Learning-Based Multi-Agent Pathfinding
Learn to Follow: Decentralized Lifelong Multi-agent Pathfinding via Planning and Learning
MAPF-GPT: Imitation Learning for Multi-Agent Pathfinding at Scale
Work Smarter Not Harder: Simple Imitation Learning with CS-PIBT
SILLM: Deploying Ten Thousand Robots / Scalable Imitation Learning for LMAPF
LaCAM / LaCAM*: Lazy Constraints Addition Search and anytime extension
LaGAT: Graph Attention-Guided Search for Dense Multi-Agent Pathfinding
MAPF-World: Action World Model for Multi-Agent Path Finding
HMAGAT: Hypergraph Neural Networks for Multi-Agent Pathfinding
Continuous-time Lifelong MAPF / CPLP
Neural Airport Ground Handling
Conflict-aware Taxiway Routing with value-decomposed RL
Airport baggage handling team formation and routing with stochastic travel times
Packet routing with graph-attention multi-agent RL
```

这份清单只作为路线灵感。czr005 的主问题仍然是：

```text
airport ICS baggage junction routing with hard industrial safety shield
```
