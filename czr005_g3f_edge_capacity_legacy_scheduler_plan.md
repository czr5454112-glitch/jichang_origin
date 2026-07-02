# czr005 G3f 推进计划：Edge-Capacity-Aware Legacy-A* Teacher Scheduler 与训练前语义分离

生成日期：2026-07-02
项目目录：`C:\PROGRAMING\czr005`
远端仓库：`czr5454112-glitch/jichang_origin`
当前分支：`codex/czr005-rewrite`
最新已知提交：`20b34d5 fix: repair downstream fault reachability semantics`

---

## 0. 当前判断：G3d/G3e 是有价值的，但还不能训练

G3d/G3e 的结论不是“Legacy-A* teacher 已经可以大规模训练”，也不是“训练方向失败”。更准确地说：

```text
Legacy-A* 是正确的第一 teacher source；
但 raw route-next label 还不是 executable local-action teacher；
当前最大 blocker 是 edge-capacity / event-horizon / scheduler-timing 语义错位。
```

关键事实：

```text
G3c:
  Legacy-A* teacher candidate recall = 1.000
  Legacy-A* teacher safe recall      = 0.610
  planned                            = 78/144
  blocked/unavailable slices         = 614

G3d:
  best primary Legacy wait/reroute replay = 94/144
  G4A gate target                         = 115/144
  edge-capacity ablation                  = 125/144
  edge-capacity ablation real conflicts   = 491

G3e:
  fixed downstream repair-window reachability bug
  repairable downstream fault no longer makes upstream waiting node permanently unreachable
  best primary replay remains 94/144
```

解释：

```text
1. G3e 修得对，但只修掉一个 repair-window reachability bug。
2. 主要 blocker 仍然是 edge_capacity。
3. 不能用 disable_edge_capacity 的 125/144 当算法结果，因为它产生 491 real-constraint conflicts。
4. 不能直接进 PPO/MAPPO/GNN/大规模 G4A。
5. 下一步应建立 “Legacy route intent” 与 “shield-executable teacher label” 的双层 teacher 语义。
```

---

## 1. 方向性修正：teacher 不是只有一种标签

当前最大混乱来自把三种概念混成一种 label：

```text
A. Legacy-A* route intent:
   原 CIE / Legacy A* 给出的 paper-faithful 路线意图。
   例：当前节点 18，route next = 22。

B. Runtime shield executability:
   当前 event time、node/edge reservation、merge/fault/window 下，
   这个 next 是否现在能走。

C. Local executable training label:
   当前局部策略应该输出什么：
     MOVE_NOW(next)
     WAIT_EDGE_CAPACITY(next, release_time)
     WAIT_NODE_CAPACITY(next, release_time)
     WAIT_MERGE_GROUP(next, release_time)
     REROUTE_NOW(new_next)
     ABSTAIN_TO_FALLBACK
```

G3c/G3d 的失败说明：Legacy-A* route intent 很好，但不能直接等价于 executable action。

从 G3f 开始，项目必须同时维护两类 teacher 文件：

```text
route_intent_teacher:
  学 Legacy-A* 的路线意图；
  允许当前暂时不可执行；
  用于 route-ranking / route preference / global guide。

executable_teacher:
  学当前 shield 下真正该执行的动作；
  包含 hold/wait/reroute/abstain 标签；
  用于 closed-loop imitation / DAgger / RL warm start。
```

严禁再把 `Legacy route next` 直接当作所有场景下的 `MOVE_NOW`。

---

## 2. 为什么 edge-capacity 是科学问题，不只是 bug

原 Java A* 的搜索逻辑主要检查：

```text
- fault edges
- node time-window constraints for next node
- heuristic cost / route cost
```

而当前 czr005 event environment / JunctionShield 额外检查：

```text
- edge capacity
- edge headway
- merge groups
- buffer/node capacity
- reachability under faults/windows
```

因此出现以下现象是合理的：

```text
Legacy-A* 说：下一步走 18 -> 22
event shield 说：18 -> 22 当前 edge_capacity occupied，不能马上进
```

这不一定说明 Legacy-A* teacher 错，也不一定说明 shield 错。它说明需要一个执行层：

```text
Legacy route intent:
  go 18 -> 22 eventually

Executable action:
  wait until 18 -> 22 releases, then move 18 -> 22
```

如果当前 event replay 每 1s hold，并在 max_decisions 之前耗尽，就会把“需要排队等待”的样本误判成 no-path/unplanned。

---

## 3. G3f 核心目标

G3f 不训练模型。G3f 要构造一个 **edge-capacity-aware Legacy execution teacher**，回答：

```text
如果保持 Legacy-A* route intent 不变，
但在执行层加入 edge-capacity-aware waiting / reservation queue，
能否把 94/144 提高到 >=115/144，
同时保持 real_constraint_conflicts = 0？
```

如果可以，进入 G4A pilot。
如果不可以，说明当前 local event framing 仍然与 Legacy scheduler / runtime shield 不匹配，需要继续修 scheduler timing 或重新定义 learning target。

---

## 4. 必须新增脚本

新增：

```text
scripts/eval/run_g3f_edge_capacity_legacy_scheduler.py
```

这个脚本必须重新运行诊断，不允许只读 G3d/G3e CSV 得结论。

---

## 5. 必须输出 artifacts

```text
outputs/reports/g3f_edge_capacity_legacy_scheduler_report.md

outputs/tables/g3f_edge_block_ledger.csv
outputs/tables/g3f_edge_release_time_audit.csv
outputs/tables/g3f_edge_queue_replay_summary.csv
outputs/tables/g3f_route_intent_vs_executable_labels.csv
outputs/tables/g3f_wait_label_taxonomy.csv
outputs/tables/g3f_scheduler_variant_comparison.csv
outputs/tables/g3f_hotspot_edge_capacity_timeline.csv
outputs/tables/g3f_unresolved_capacity_cases.csv
outputs/tables/g3f_g4a_pilot_eligibility.csv

artifacts/teacher/legacy_astar/g3f_route_intent_teacher_sample.jsonl
artifacts/teacher/legacy_astar/g3f_executable_wait_teacher_sample.jsonl

outputs/figures/g3f_edge_hotspot_timeline.png
```

---

## 6. G3f 必须实现的 replay variants

### Variant 0：G3d reproduced baseline

复现 G3d 最佳结果：

```text
reroute_from_current_legacy = 94/144
real_constraint_conflicts   = 0
```

作为 sanity anchor。

### Variant 1：edge-release wait scheduler

规则：

```text
if Legacy route-next is blocked by edge_capacity:
  compute earliest_release_time for that edge;
  if current node can safely hold until release:
      label = WAIT_EDGE_CAPACITY(next, release_time)
      jump ready_time to release_time
      then attempt MOVE_NOW(next)
  else:
      label = WAIT_NODE_BLOCKED or REROUTE_NOW
```

关键：不要用 1s/2s/5s repeated hold 消耗 max_decisions。必须使用 event jump。

### Variant 2：FIFO edge queue

规则：

```text
for each edge capacity conflict:
  maintain edge queue ordered by:
    1. current ready_time
    2. deadline slack / STD urgency
    3. original Legacy route order
    4. segment_id deterministic tie-break

when edge releases:
  first eligible bag moves
  others keep WAIT_EDGE_QUEUE
```

目的：模拟工业输送系统里 bottleneck edge 的排队进入，而不是所有 bag 都在每个 event step 重新竞争。

### Variant 3：capacity-aware reroute after wait budget

规则：

```text
if wait time > threshold:
  query Legacy-compatible A* from current node to goal
  with current fault/repair state and node reservations
  if alternate route next is safe:
      REROUTE_NOW_LEGACY
  else:
      continue WAIT_EDGE_CAPACITY or ABSTAIN
```

阈值 sweep：

```text
max_wait = 5s / 10s / 30s / 60s
```

### Variant 4：route-intent-only teacher

这个 variant 不要求 executable action 成功，而是只输出：

```text
current, goal, legacy_next, route_suffix, route_intent_label
```

用途：

```text
训练 route-ranking / global guide；
不作为 closed-loop action policy teacher。
```

这可以避免把 temporarily blocked move 当错误样本。

### Variant 5：hybrid executable teacher

规则：

```text
1. Follow Legacy route intent.
2. If edge/node/merge temporarily blocked, emit explicit WAIT_* label.
3. If Legacy no-path, attempt Legacy reroute-from-current.
4. If still no teacher, mark ABSTAIN_TO_FALLBACK.
5. SIPP repair label only作为 auxiliary optional，不作为 primary Legacy label。
```

---

## 7. 必须做的审计

### 7.1 Edge block ledger

每个 blocked slice 必须记录：

```text
scenario
segment_id
task_id
current
legacy_next
goal
ready_time
blocked_reason
edge_start
edge_end
occupying_segment_id
occupying_task_id
occupancy_start
occupancy_end
earliest_release_time
wait_needed
can_current_node_hold
node_hold_capacity_reason
merge_group_reason
event_variant
```

### 7.2 Hotspot edge timeline

至少输出 top 10 blocked edges 的 timeline，例如：

```text
edge 18 -> 22
edge 22 -> 24
edge 27 -> 28
...
```

每条 edge 的 timeline 要说明：

```text
which bags occupy it
which bags wait for it
release time
queue length
deadline slack distribution
```

### 7.3 Route intent vs executable labels

必须统计：

```text
route_intent_labels
executable_MOVE_NOW
executable_WAIT_EDGE_CAPACITY
executable_WAIT_NODE_CAPACITY
executable_WAIT_MERGE_GROUP
executable_REROUTE_NOW
executable_ABSTAIN
```

并说明哪些 label 可以进 G4A pilot。

### 7.4 Java/C++ scheduler semantics note

报告必须写清：

```text
原 Java A* 是否显式 edge-capacity-aware？
当前 C++/Python event shield 是否加入了额外 runtime safety？
这些额外约束是新系统 safety layer，还是 legacy parity 目标的一部分？
```

不能模糊说“teacher unsafe”。应区分：

```text
paper-faithful teacher under legacy constraints
runtime-safe teacher under new shield constraints
```

---

## 8. G3f gate

### Development pass

允许进入 G4A pilot 的最低门槛：

```text
best executable Legacy teacher replay planned >= 115/144
real_constraint_conflicts = 0
post_shield_conflicts = 0
branch_executable_coverage >= 0.85
route_intent_coverage >= 130/144
unresolved edge_capacity cases <= 20% of G3d edge_capacity cases
```

### Diagnostic pass

如果不达标，但输出完整 blocked ledger、release-time audit 和语义结论，也算 G3f diagnostic pass。

### Hard fail

以下情况必须停止：

```text
silent constraint relaxation
edge_capacity disabled and called success
real_constraint_conflicts hidden
legacy Java modified
teacher labels without label_source
training started before gate
```

---

## 9. 若 G3f 通过，下一步才是 G4A pilot

G4A 只能是 pilot，不是 broad scaling：

```text
scripts/data/build_g4a_legacy_teacher_pilot.py

artifacts/teacher/legacy_astar/g4a_route_intent_pilot.jsonl
artifacts/teacher/legacy_astar/g4a_executable_wait_pilot.jsonl
outputs/reports/g4a_legacy_teacher_pilot_dataset_report.md
```

不要马上训练大模型。先只生成 dataset，并做 schema / leakage / label distribution audit。

---

## 10. 若 G3f 不通过，下一步不是训练

如果 G3f 仍无法达到 gate，下一轮应进入：

```text
G3g Legacy Scheduler Semantics Alignment
```

重点比较：

```text
original Java scheduler route timing
C++ faithful scheduler route timing
Python event replay route timing
edge capacity as legacy-vs-new-safety divergence
```

并可能调整论文叙事：

```text
Legacy-A* provides route-intent teacher;
new method adds capacity-aware shield/execution scheduler;
learned policy imitates route intent plus learns wait/reroute execution labels.
```

---

## 11. 给 Codex 的长 prompt

```text
继续 czr005，路径 C:\PROGRAMING\czr005，分支 codex/czr005-rewrite。先 git status --short，确认当前 HEAD 包含 20b34d5 或更新。读取 README.md、docs/codex-worklog.md、outputs/reports/g3c_legacy_astar_teacher_fidelity_report.md、outputs/reports/g3d_legacy_teacher_wait_horizon_audit_report.md、outputs/reports/g3e_event_semantics_repair_report.md、outputs/tables/g3d_edge_capacity_hotspots.csv、outputs/tables/g3d_blocked_slice_ledger.csv、outputs/tables/g3e_matched_gate_after_repair.csv。

本轮不要训练模型，不要 PPO/MAPPO，不要 GNN/Transformer，不要大规模 G4A。G3d/G3e 已证明 best primary replay 仍是 94/144，disable edge capacity 虽到 125/144 但有 491 real-constraint conflicts。下一步只做 G3f Edge-Capacity-Aware Legacy Teacher Scheduler。

核心目标：把 Legacy-A* route intent 与 executable local action label 分开。保持 Legacy route source 不变，增加执行层 edge-capacity-aware wait/queue/reroute 语义。不要放宽 hard shield。不要修改 legacy Java。

必须新增 scripts/eval/run_g3f_edge_capacity_legacy_scheduler.py，并生成：
outputs/reports/g3f_edge_capacity_legacy_scheduler_report.md
outputs/tables/g3f_edge_block_ledger.csv
outputs/tables/g3f_edge_release_time_audit.csv
outputs/tables/g3f_edge_queue_replay_summary.csv
outputs/tables/g3f_route_intent_vs_executable_labels.csv
outputs/tables/g3f_wait_label_taxonomy.csv
outputs/tables/g3f_scheduler_variant_comparison.csv
outputs/tables/g3f_hotspot_edge_capacity_timeline.csv
outputs/tables/g3f_unresolved_capacity_cases.csv
outputs/tables/g3f_g4a_pilot_eligibility.csv
artifacts/teacher/legacy_astar/g3f_route_intent_teacher_sample.jsonl
artifacts/teacher/legacy_astar/g3f_executable_wait_teacher_sample.jsonl

必须实现至少这些 variants：
1. reproduce G3d baseline
2. edge-release wait scheduler
3. FIFO edge queue scheduler
4. capacity-aware reroute after wait budget sweep
5. route-intent-only teacher output
6. hybrid executable teacher

报告必须明确：
- Legacy A* 是否原生 edge-capacity-aware
- 当前 edge capacity 是 paper-faithful constraint 还是 added runtime safety layer
- 哪些 slices 适合 route-intent teacher
- 哪些 slices 适合 executable wait/reroute teacher
- 是否达到 G4A pilot gate

G3f 通过条件：
best executable Legacy teacher replay planned >= 115/144
real_constraint_conflicts = 0
post_shield_conflicts = 0
branch_executable_coverage >= 0.85
route_intent_coverage >= 130/144

如果不通过，也要完整报告原因，不得继续训练。跑：
python scripts/eval/run_g3f_edge_capacity_legacy_scheduler.py
python -m py_compile scripts/eval/run_g3f_edge_capacity_legacy_scheduler.py
python -m pytest
git diff --check
确认未修改 legacy Java
更新 README.md 和 docs/codex-worklog.md。
```

---

## 12. 给 Codex 的短 prompt

```text
继续 czr005。不要训练模型。做 G3f Edge-Capacity-Aware Legacy Teacher Scheduler：把 Legacy-A* route intent 和 executable local labels 分开，加入 edge-release wait、FIFO edge queue、capacity-aware reroute、route-intent-only teacher、hybrid executable teacher。目标是在不放宽 edge capacity、不产生 real conflicts 的前提下把 best executable Legacy replay 从 94/144 提到 >=115/144。若达不到，写清 blocker 并停止，不许进入 G4A/训练。
```
