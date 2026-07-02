# czr005：Legacy A* / 原 CIE 仿真作为 Teacher 的路线评估与 Codex 推进计划

生成日期：2026-07-02
项目目录：`C:\PROGRAMING\czr005`
远端仓库：`czr5454112-glitch/jichang_origin`
当前背景：G2/G3 已证明当前 EdgeScore 学习策略远弱于 rolling/periodic SIPP；G3 进一步证明 teacher next-hop 在候选集中召回率为 1.000，但 safe-mask 召回率只有 0.319，说明当前 SIPP-as-teacher 路线存在 teacher/action-mask/horizon 语义错位风险。
本文件回答用户提出的新问题：**能否直接用原 CIE 项目的改进 A* 和原仿真轨迹作为 teacher，而不是用 SIPP 作为 teacher？**

---

## 0. 一句话结论

可以，而且应该认真做一轮。

更准确地说：

```text
Legacy A* / 原 CIE 仿真轨迹应该成为 czr005 的第一类 teacher：
  paper-faithful teacher
  baseline-imitation teacher
  large-scale trajectory teacher
  original-method distillation target

SIPP 不应该在此阶段作为唯一 teacher。
SIPP 应该降级为：
  upper-bound oracle
  failure diagnostic
  repair teacher / optional fallback label
  strong non-learning baseline
```

原因：

```text
如果论文主线是“原 CIE 改进 A* 不适合大规模场景，因此我们学习它、加速它、再通过 RL/DAgger 改善它”，
那么 teacher 必须首先来自原 CIE 系统本身，而不是来自另一个更强但问题语义不同的 SIPP teacher。
```

但是不能简单粗暴地“把 Java GUI 跑起来，把 route 当标签就训练”。必须先做一个新的阶段：

```text
G3c Legacy-A* Teacher Fidelity Audit
```

它要回答：

```text
原项目 A* 产生的路线，能不能被提取成每个行李在每个岔路口的可训练动作？
这些动作能否在当前 Python/C++ event environment 里复现原仿真行为？
这些动作在 local safe mask 下是否可执行？
如果不可执行，是仿真语义错位、mask 过严、时间窗不一致，还是 teacher 本身的中心化约束与局部策略不兼容？
```

只有 G3c 通过，才进入：

```text
G4A Legacy-A* Teacher Dataset
G5A Legacy-A* Behavior Cloning / DAgger
G6A Shielded RL Fine-tuning from Legacy-A* BC
```

---

## 1. 为什么这个想法有道理

### 1.1 它和 CIE 文章贡献对齐

原项目不是普通 baseline，而是导师 CIE 文章对应的仿真代码。czr005 的研究故事本来就是：

```text
原 CIE 改进 A* 是可信工程 baseline；
但 centralized / repeated A* 在大规模动态行李流下不够 scalable；
我们将它转成可学习的 decentralized junction policy；
再通过 shield / imitation / RL / DAgger 提升在线运行效率。
```

因此最自然的 teacher 是：

```text
原改进 A* 在原仿真中的 route / movement / reroute 决策。
```

这比直接用 SIPP 更符合论文叙事。

### 1.2 它避免 SIPP teacher 与 event safe mask 语义错位

G3 已经发现：

```text
teacher_next_candidate_recall = 1.000
teacher_next_safe_recall      = 0.319
best local oracle recovered   = 11/47 EdgeScore failures
```

这说明 SIPP teacher 虽然强，但它给出的 teacher next-hop 在当前 event policy / hard shield / reservation timing 下经常不安全。

可能原因：

```text
SIPP teacher 的时间窗等待语义与 event policy 的一步 action mask 不一致；
rolling-horizon SIPP 能整体规划等待，但 local policy 在当前时刻只能 move/hold；
teacher path 是 centralized planned route，local policy state 已经偏离 teacher route；
safe mask 对 edge_capacity/node_reservation/unreachable_goal 的时序处理和 SIPP 不同。
```

用原 CIE A* teacher 可能更自然，因为当前项目 Phase1 已经大量复现 Java A* / scheduler 语义；如果 teacher 来自同一套语义，候选动作和 mask 的冲突应更少。

### 1.3 它能把“改进 A* 不适合大规模”变成可学习目标

如果我们只说“改进 A* 慢”，然后直接训练一个跟 SIPP 学的策略，学术故事会变成：

```text
用 SIPP teacher 训练 learned local policy。
```

这和 CIE 文章的关系会变弱。

如果先用原 A* teacher：

```text
1. 复现 CIE A* 的行为；
2. 证明学习策略能模仿原 A* 的 routing decisions；
3. 证明 learned policy 推理更快；
4. 再通过 DAgger/RL/shield 在部分场景超过原 A*；
5. 最后与 SIPP/rolling SIPP 对比，说明与强 baseline 的差距。
```

这条路线更像一篇完整论文。

### 1.4 学习式 MAPF 经验支持“先模仿强/可信 expert，再强化”

PRIMAL / PRIMAL2 这类方法结合 reinforcement learning 与 expert demonstrations；SILLM 这类 Lifelong MAPF 学习方法也不是裸 RL，而是 imitation + global guidance + collision resolution。DAgger 的核心动机也是解决 behavior cloning 在 learner 偏离 expert distribution 后出现 compounding error 的问题。

因此合理路线不是：

```text
直接 PPO/MAPPO
```

而是：

```text
Legacy A* teacher traces
  -> behavior cloning
  -> shadow replay
  -> DAgger from learner-visited states
  -> shielded RL fine-tuning
```

---

## 2. 但不能“直接拿 route 就训练”的原因

你的想法是对的，但需要处理 8 个技术风险。

### 2.1 原 A* 是 centralized/prioritized planner，不是 decentralized policy

原 A* 在 `ICS_PathFinding` 里使用共享约束集合、saved routes、fault routes、unfinished tasks 等全局状态。它规划的是 route，不是每个 agent 在局部观测下独立做 decision。

因此 teacher extraction 要做转换：

```text
global route:
  task_id -> [v0, v1, v2, ..., goal]

转换为 local decision slices:
  at node v_k, with local/global features, label next = v_{k+1}
```

这一步必须记录：

```text
label 是从 global route 后处理得到的；
不是原 A* 本身的 decentralized decision。
```

### 2.2 原 Java 仿真可能只保存 route，不保存每个 epoch 的真实运动

原项目里的 saved route 给的是路径节点和预计时间。每个行李实际“移动”可能通过 GUI repaint / task file generation / saved_routes progression 间接表达。

因此 teacher extraction 不能只读最终 path。必须输出：

```text
planned_at_epoch
task_id / segment_id
current node
next node
arrive time / leave time
route suffix
whether this decision came from new plan / reroute / repair / fault hold
```

### 2.3 A* teacher 可能没有等待动作标签

原 A* 搜索里遇到节点时间窗冲突通常是跳过候选节点，而不是像 SIPP 那样显式等待到下一个 safe interval。它可能返回空路径或绕行，而不是生成 wait-until-safe label。

对于 local policy，等待动作很重要。需要定义：

```text
如果 teacher route 的下一跳当前被 mask 临时阻塞：
  label 可以是 HOLD_UNTIL_SAFE
  或 label_source = legacy_astar_route_next_but_temporarily_blocked
```

不要把这类样本粗暴当作“teacher 错误”。

### 2.4 原 A* teacher 质量可能低于 SIPP

这不是缺点，而是要诚实说明。

原 A* teacher 的作用是：

```text
paper-faithful imitation target
baseline acceleration target
initial policy warm start
```

不是：

```text
最优 oracle
```

SIPP / rolling SIPP 仍可作为：

```text
upper bound
diagnostic oracle
repair teacher
```

但第一阶段训练标签应来自 legacy A*。

### 2.5 直接训练会有 covariate shift

Behavior cloning 只在 teacher 轨迹上训练。一旦 learned policy 走错一步，它进入 teacher 没见过的 state，后面容易越走越偏。

所以必须做：

```text
DAgger-style relabeling
```

在 learner visited states 上重新查询：

```text
Legacy A* from current node to goal under current constraints
```

如果 Legacy A* 查不到，再标记为：

```text
legacy_teacher_unavailable
```

并可选用：

```text
SIPP repair label
fallback safe label
hold/abstain label
```

但必须保留 label_source。

### 2.6 原 Java GUI 仿真不适合直接成为大规模 teacher generator

原 `Main.java` 有 GUI、sleep、epoch loop、文件输出等结构，直接跑它生成大规模 teacher 数据不稳定也慢。

推荐路线：

```text
small scale:
  Java read-only headless harness 作为 source-of-truth verifier

large scale:
  用已经 Java-parity 的 Python/C++ legacy scheduler 生成 teacher traces
  再用 Java harness spot-check parity
```

不要把 GUI repaint / Thread.sleep / Swing timing 纳入 teacher。

### 2.7 原 CIE A* teacher 与当前 learning env 需要语义对齐

必须检查：

```text
same map parser
same task split rule
same early-baggage logic
same fault/repair semantics
same route update semantics
same active route advancement
same constraint rebuild semantics
same goal-node conflict convention
same zero-service-time node convention
same edge capacity/headway convention
```

如果不对齐，训练出来的 policy 会学习一个不存在的 teacher distribution。

### 2.8 如果最终目标是“超过 A*”，teacher 不能成为 ceiling

用 Legacy A* 当 teacher 会先学到 A* 的行为。它能帮助 cold start，但不能保证超过 A*。

因此最终阶段必须加：

```text
reward fine-tuning
DAgger hard-case mining
teacher mixture / SIPP repair labels
closed-loop objective
```

最终 claim 也应是：

```text
A* imitation gives a safe, paper-faithful warm start;
RL/DAgger/shield improves selected failure modes or runtime scalability.
```

---

## 3. 新路线：Teacher 分层，不是二选一

不要写成：

```text
Legacy A* teacher vs SIPP teacher，二选一。
```

应该写成：

```text
Teacher-0: Legacy Java/CIE A* teacher
  role: paper-faithful imitation, baseline distillation, initial BC

Teacher-1: Faithful Python/C++ Legacy A* teacher
  role: scalable trace generation, validated against Java

Teacher-2: Rolling/Periodic SIPP teacher
  role: upper bound, repair label, diagnostic, not default training label

Teacher-3: Shield/Fallback teacher
  role: when A* and SIPP labels are unsafe/unavailable, choose safe hold/abstain

Teacher-4: RL reward
  role: improve beyond imitation under closed-loop objective
```

训练标签必须包含：

```text
label_source =
  java_legacy_astar
  cpp_legacy_astar
  python_legacy_astar
  rolling_sipp_repair
  periodic_sipp_repair
  shield_hold
  fallback_safe
  no_label
```

这样后续可以严格做 ablation：

```text
BC from Legacy A*
BC from Legacy A* + DAgger
BC from Legacy A* + SIPP repair
BC + RL
SIPP teacher only
fallback only
```

---

## 4. 推荐新增阶段：G3c Legacy-A* Teacher Fidelity Audit

### 4.1 目标

回答：

```text
原 CIE A* teacher 能否作为 czr005 的主 imitation teacher？
```

不是训练模型，不是 RL，不是 paper claim。

### 4.2 必须新增脚本

```text
scripts/eval/run_g3c_legacy_astar_teacher_fidelity.py
```

### 4.3 必须输出 artifacts

```text
outputs/reports/g3c_legacy_astar_teacher_fidelity_report.md

outputs/tables/g3c_java_teacher_trace_summary.csv
outputs/tables/g3c_cpp_teacher_trace_summary.csv
outputs/tables/g3c_java_cpp_teacher_parity.csv
outputs/tables/g3c_teacher_junction_slices_sample.csv
outputs/tables/g3c_teacher_replay_safety.csv
outputs/tables/g3c_legacy_vs_sipp_teacher_agreement.csv
outputs/tables/g3c_teacher_label_coverage.csv
outputs/tables/g3c_teacher_unavailable_cases.csv

artifacts/teacher/legacy_astar/g3c_legacy_astar_teacher_sample.jsonl
```

### 4.4 必须实现的审计

#### Audit A：teacher source-of-truth

检查两条路线：

```text
A1. Java headless harness:
    编译 read-only legacy Java
    外部 harness 调用 ICS_PathFinding / Tasks / Astar
    不修改 legacy Java 源码
    输出 route/decision JSONL

A2. C++ faithful scheduler:
    使用已通过 Java/C++ parity 的 native C++ legacy scheduler
    生成大规模 teacher traces
    用 Java harness 对小窗口 spot-check
```

如果 Java harness 很难做，先允许：

```text
C++ faithful teacher as generator
Java route parity as verifier
```

但报告必须写明：

```text
teacher_source = cpp_faithful_legacy_astar
java_spotcheck = pass/fail
```

#### Audit B：route-to-decision conversion

对每条 route 转换成 junction slices：

```text
task_id
segment_id
epoch
current_node
next_node
goal_node
ready_time
leave_time
route_suffix
action_label = next_node
label_kind = move / hold / reroute / no_path
label_source = legacy_astar
fault_state
repair_state
constraint_summary
```

#### Audit C：teacher replay in current env

把 Legacy A* teacher actions 强制 replay 到当前 Python event env：

```text
force teacher next if safe
if not safe, hold until safe or mark blocked
record divergence
```

输出：

```text
teacher_action_safe_recall
teacher_action_candidate_recall
teacher_replay_planned_count
teacher_replay_conflicts
teacher_block_reason_distribution
```

#### Audit D：legacy vs SIPP teacher agreement

不是用 SIPP 训练，而是比较：

```text
Legacy A* teacher next
SIPP teacher next
same current node / task / goal
agreement rate
where they differ
which one completes
which has lower travel time
```

这能回答：

```text
SIPP 的改进主要在哪些 motif 上？
Legacy A* 是否缺少等待/绕行/repair handling？
```

#### Audit E：teacher coverage

统计：

```text
how many tasks have legacy labels
how many decisions per task
how many labels are move / hold / reroute / no_path
how many labels occur under fault/repair/merge/buffer
how many current nodes are branch nodes vs linear nodes
```

如果大部分标签只是线性节点，没有足够岔路口样本，就需要扩展任务窗口或合成数据。

---

## 5. 如果 G3c 通过：G4A Legacy-A* Teacher Dataset

### 5.1 目标

构造 paper-faithful imitation dataset：

```text
artifacts/teacher/legacy_astar/legacy_astar_junction_slices_manifest.jsonl
```

### 5.2 数据来源

优先顺序：

```text
1. real map2/inputdata full task stream
2. deterministic fault/repair windows
3. probability-extreme fault/repair branches
4. synthetic ICS-like maps only after real teacher route is stable
```

### 5.3 样本字段

```text
scenario_id
teacher_source
teacher_version
java_commit_or_sha
cpp_commit_or_sha
task_id
segment_id
source_line
start
goal
current
next_label
route_suffix
candidate_next_nodes
safe_mask
label_in_candidate
label_in_safe_mask
label_block_reason
ready_time
service_time
edge_travel_time
deadline_slack
shortest_time_to_goal
active_fault_edges
active_repair_windows
node_reservation_summary
edge_reservation_summary
merge_group_state
buffer_capacity_state
route_replan_reason
teacher_path_cost
teacher_finish_time
```

### 5.4 不要训练所有节点

行李系统中很多节点只有一个 outgoing edge。训练这些节点会让模型学到“无脑走唯一边”，稀释岔路口学习。

建议 split：

```text
all_decision_slices:
  所有动作记录，用于 replay/coverage

junction_slices:
  out_degree >= 2 的节点
  作为主要训练集

blocked_or_hold_slices:
  teacher next temporarily unsafe / hold / no path
  作为 hard-case set
```

---

## 6. 如果 G4A 通过：G5A Legacy-A* BC / DAgger

### 6.1 Behavior cloning baseline

训练：

```text
LegacyAStarEdgeRanker-v1
```

输入：

```text
candidate edge features
current-goal shortest time
deadline slack
local reservation pressure
fault/repair features
merge/buffer features
route-progress features
```

输出：

```text
score(candidate next)
```

loss：

```text
cross entropy over safe candidates
pairwise ranking loss against teacher next
abstain/hold auxiliary loss
no-safe-action risk auxiliary loss
```

### 6.2 BC gate

在 teacher distribution 下：

```text
teacher top1 accuracy on junction nodes
teacher top3 recall
label-in-safe-mask coverage
closed-loop replay planned_count
conflicts = 0
```

不要要求它超过 SIPP。第一目标是：

```text
match Legacy A*
```

### 6.3 DAgger route

如果 closed-loop BC 偏离 teacher：

```text
roll out BC+shield
collect learner states
query Legacy A* from current node to goal under current constraints
append labels
retrain
```

如果 Legacy A* no path：

```text
label_source = legacy_no_path
optional repair_label = SIPP / shield_hold
```

必须保留 label source，不能混成一个 teacher。

---

## 7. RL 如何接在后面

不要从零 RL。

推荐：

```text
Legacy A* BC checkpoint
  -> shielded closed-loop replay
  -> DAgger repair
  -> reward fine-tuning
```

reward：

```text
+ goal completion
- travel time
- waiting
- deadline lateness
- shield intervention
- max decision exhaustion
- entering high downstream congestion
```

RL 的作用是：

```text
在保持 Legacy A* behavior prior 的基础上，
学习在大规模/高密度/fault/merge 情况下比 A* 更好的局部选择。
```

不要写成：

```text
RL learns from scratch to solve ICS routing.
```

---

## 8. 论文叙事建议

### 8.1 最强叙事

```text
We distill the CIE improved-A* ICS simulator into a decentralized junction policy.
The original A* provides paper-faithful teacher trajectories.
A hard safety shield preserves industrial constraints.
DAgger and RL fine-tuning address covariate shift and congestion/failure cases.
The learned policy approximates legacy A* route quality while offering faster per-decision inference and scalable online execution, and can be further compared with SIPP-style upper-bound baselines.
```

### 8.2 不能写的 claim

```text
SIPP teacher proves our method is aligned with the original CIE system.
```

不对。SIPP 不是原文章 teacher。

```text
BC from Legacy A* is enough to beat A*.
```

不一定。BC 只会模仿 A*，超过 A* 需要 RL/DAgger/teacher mixture/closed-loop reward。

```text
Original A* trajectories are automatically decentralized.
```

不对。它们是 centralized plan-to-local-slice conversion。

```text
If teacher trace is safe in Java, it must be safe in Python/C++ event env.
```

不一定，必须审计 mask/timing semantics。

---

## 9. 与当前 G3/G3b 的关系

当前 G3b 计划仍有价值，但优先级应调整：

```text
Old next:
  G3b audit SIPP mask/horizon mismatch

New next:
  G3c audit Legacy A* teacher feasibility
  then compare:
    Legacy A* teacher safe-mask recall
    SIPP teacher safe-mask recall
```

如果 Legacy A* teacher safe-mask recall 高：

```text
说明 SIPP mismatch 主要是 teacher problem；
进入 G4A Legacy-A* dataset。
```

如果 Legacy A* teacher safe-mask recall 也低：

```text
说明 current event env / shield / horizon 语义本身有问题；
先做 G3b mask/horizon audit。
```

因此新顺序：

```text
G3c first
G3b conditional
G4A after teacher fidelity passes
```

---

## 10. 给 Codex 的长 prompt

```text
继续 czr005，路径 C:\PROGRAMING\czr005，分支 codex/czr005-rewrite。先 git status --short，读取 README.md、docs/codex-worklog.md、czr005_project_master_plan.md、outputs/reports/g2_learning_gap_autopsy.md、outputs/reports/g3_oracle_upper_bound_report.md，以及 Java legacy 相关代码路径 legacy/jichang_origin_readonly/src/App/Astar.java、ICS_PathFinding.java、Tasks.java、RUN/Main.java。

用户提出新的研究判断：不要把 SIPP 作为默认 teacher。原项目是导师 CIE 文章对应的改进 A* 仿真，应该直接用原项目 A* / 原仿真轨迹作为 paper-faithful teacher，然后追溯每个行李在每个岔路口的移动/转向作为 imitation / RL teacher。SIPP 只能作为 upper-bound / diagnostic / repair oracle，不应替代原 CIE A* teacher。

本轮不要训练模型，不要做 PPO/MAPPO，不要做 GNN，不要把任何结果写成 learning success。实现 G3c Legacy-A* Teacher Fidelity Audit，回答：原 CIE A* teacher 能否作为 czr005 的主 imitation teacher？

必须新增：
scripts/eval/run_g3c_legacy_astar_teacher_fidelity.py

必须生成：
outputs/reports/g3c_legacy_astar_teacher_fidelity_report.md
outputs/tables/g3c_java_teacher_trace_summary.csv
outputs/tables/g3c_cpp_teacher_trace_summary.csv
outputs/tables/g3c_java_cpp_teacher_parity.csv
outputs/tables/g3c_teacher_junction_slices_sample.csv
outputs/tables/g3c_teacher_replay_safety.csv
outputs/tables/g3c_legacy_vs_sipp_teacher_agreement.csv
outputs/tables/g3c_teacher_label_coverage.csv
outputs/tables/g3c_teacher_unavailable_cases.csv
artifacts/teacher/legacy_astar/g3c_legacy_astar_teacher_sample.jsonl

核心要求：
1. 不修改 legacy Java 源码；如果需要 Java headless harness，放在独立 harness/tools 目录。
2. 如果直接 Java harness 过重，允许先用已通过 Java parity 的 C++ faithful legacy scheduler 生成 teacher traces，但必须用 Java spot-check 验证 route parity。
3. 把 legacy A* route 转成 per-task / per-junction decision slices：
   task_id, segment_id, current, next_label, goal, ready_time, route_suffix, label_source, replan_reason, fault/repair state。
4. 强制 replay teacher actions 到当前 Python event env，统计 teacher_action_candidate_recall、teacher_action_safe_recall、teacher_replay_conflicts、teacher_block_reason_distribution。
5. 对比 Legacy A* teacher 与 SIPP teacher 的 action agreement，不用 SIPP 训练，只做诊断。
6. 判断下一步：
   A. 如果 Legacy A* teacher safe-mask recall 明显高于 SIPP，并 replay clean，则进入 G4A Legacy-A* teacher dataset；
   B. 如果 Legacy A* teacher 也大量被 safe mask 阻塞，则先做 G3b mask/shield/event-horizon audit；
   C. 如果 Java/C++ teacher parity 不足，则先修 legacy teacher extraction，不许进入训练。

跑：
python scripts/eval/run_g3c_legacy_astar_teacher_fidelity.py
python -m py_compile scripts/eval/run_g3c_legacy_astar_teacher_fidelity.py
python -m pytest

更新 README.md 和 docs/codex-worklog.md。报告必须写 Interpretation、Next Blocking Question、Follow-up。所有负结果必须保留。不要隐藏 Java harness 失败、teacher unavailable、safe-mask recall 低等问题。
```

---

## 11. 给 Codex 的短 prompt

```text
继续 czr005。本轮不要用 SIPP 当默认 teacher，也不要训练模型。做 G3c Legacy-A* Teacher Fidelity Audit：从原 CIE Java/C++ faithful legacy A* 仿真提取每件行李的 route->junction action labels，验证 Java/C++ teacher parity，把 teacher actions replay 到当前 event env，统计 label candidate/safe recall、block reasons、teacher coverage，并对比 Legacy A* teacher vs SIPP teacher agreement。输出 g3c_legacy_astar_teacher_fidelity_report.md 和 CSV/JSONL。若 Legacy A* teacher replay clean，则下一步进入 G4A Legacy-A* teacher dataset；若也被 mask 阻塞，则先做 G3b mask/horizon audit。不要做 RL/GNN/训练，不要修改 legacy Java，不要把诊断写成 success claim。
```

---

## 12. 当前推荐决策

我建议立即执行：

```text
G3c Legacy-A* Teacher Fidelity Audit
```

而不是继续：

```text
G3b only
G4 SIPP teacher dataset
PPO/MAPPO
GNN
```

因为用户的判断是正确的：如果原项目就是 CIE 文章的改进 A* 仿真，那么它应该成为 teacher hierarchy 的第一层。SIPP 是强对照和上界，不应抢走 paper-faithful teacher 的位置。
