# czr005 G3/G4 大幅推进计划：从 G2 失败诊断走向可证明的学习策略上界、teacher 数据与下一代 EdgeRanker

生成日期：2026-07-02  
项目目录：`C:\PROGRAMING\czr005`  
远端仓库：`czr5454112-glitch/jichang_origin`  
当前工作分支：`codex/czr005-rewrite`  
已复核提交：`495f49e298c8f0db054e0628e6bac306cfce2ef9`  
当前阶段定位：**G2 Learning Gap Autopsy 已完成；下一阶段不要进入 PPO/MAPPO，而要做 G3 Oracle Upper Bound + G4 Teacher Dataset Expansion。**

---

## 0. 当前结果到底是好是坏？

结论：

```text
G2 是好结果，但它证明的是“我们知道学习策略为什么输”，不是“学习策略已经赢”。
```

具体判断：

```text
好：
  1. G2 没有把失败藏起来，而是明确记录 EdgeScore 97/144 vs SIPP 144/144。
  2. 它定位了 47 个 EdgeScore 失败 task-scenario rows。
  3. 它同时记录 fallback 51 个失败 rows、PIBT 105 个失败 rows。
  4. 它把失败拆成 hold_when_sipp_moves、wrong_branch_vs_sipp、repair_window_branch_gap、no_safe_action_at_divergence 等 motif。
  5. 它明确写了 oracle upper-bound analysis: NOT DONE，属于 G3。
  6. README 仍然诚实标注 learning experiments are smoke/prototype，不是 final RL result。

坏：
  1. EdgeScore 仍然明显弱于 rolling_horizon_sipp / periodic_replanning_sipp。
  2. 当前 learned policy 不是 paper contribution，只是 pipeline proof。
  3. 失败主要发生在 merge_group、repair_window、branch/hold 这类非局部约束里，说明当前 observation / teacher / horizon 可能不足。
  4. 当前 G2 仍是解释性诊断，不是可执行改进。
  5. 远端没有 GitHub Actions workflow run 证据，只有本地测试报告。
```

一句话：

```text
czr005 的工程底座继续是好结果；
G2 的研究诊断也是好结果；
学习算法本身还不是好结果。
```

---

## 1. 当前证据摘要

### 1.1 已确认的强点

Phase1 / legacy port 已经可以阶段性接受：

```text
legacy Java reference -> Python reference -> C++ core / pybind
A* core parity
Java/C++ scheduler-window parity
fault/repair and probability-extreme branch coverage
C++ not below Java on recorded legacy gates
```

这些支撑后续 learning 不是建立在 toy simulator 上。

### 1.2 G2 给出的关键事实

G2 report 的核心表：

```text
rolling_horizon_sipp:      144 / 144
periodic_replanning_sipp:  144 / 144
edge_score_event:           97 / 144
fallback_event:             93 / 144
pibt_active_bag_replay:     39 / 144
```

失败库存：

```text
EdgeScore failures vs rolling-horizon SIPP: 47
Fallback failures vs rolling-horizon SIPP: 51
PIBT active-bag failures vs rolling-horizon SIPP: 105
```

Top motifs：

```text
hold_when_sipp_moves
wrong_branch_vs_sipp
repair_window_branch_gap
static_fault_branch_gap
buffer_capacity_branch_gap
no_safe_action_at_divergence
```

解释：

```text
不是安全冲突问题；
是 completion / coordination / horizon / feature / teacher 问题。
```

---

## 2. 下一阶段核心科学问题

G3 必须回答：

```text
在当前 safe candidate set 不变的情况下，
如果有一个 oracle 能看到 SIPP teacher next-hop / teacher rank，
能不能恢复 EdgeScore 47 个失败任务中的大多数？
```

这会决定后续路线：

### 情况 A：local oracle 能恢复大多数失败

说明：

```text
当前问题主要是模型/数据/feature 不足。
```

下一步：

```text
G4 large teacher slices
G5 EdgeRanker-v2 / SIPP-rank imitation
G6 shielded closed-loop validation
```

### 情况 B：local oracle 仍恢复不了

说明：

```text
当前 action mask、safe candidate construction、reservation timing、horizon 或 event policy semantics 有结构性缺陷。
```

下一步：

```text
修 safe mask / event semantics / horizon；
添加 rolling-reservation guide；
也许需要 two-step / K-step local oracle；
暂不训练更大模型。
```

### 情况 C：teacher next-hop 经常不在 candidate mask 中

说明：

```text
不是 policy 排名问题，而是候选集/安全层/时序建模问题。
```

下一步：

```text
audit teacher-next-in-mask recall；
修 observation/action-mask/shield timing；
不要用 neural policy 掩盖 simulator mismatch。
```

### 情况 D：teacher next-hop 在 mask 中，但 EdgeScore 选择 hold 或错误分支

说明：

```text
适合做 SIPP rank supervision、feature ablation、DAgger。
```

下一步：

```text
扩展 SIPP teacher dataset；
训练 EdgeRanker-v2；
加入 downstream reservation pressure / merge pressure / deadline slack。
```

---

## 3. G3：Oracle Upper Bound and Teacher-in-Mask Diagnosis

### 3.1 目标

G3 不是训练模型。G3 是建立学习策略的可达上界：

```text
policy candidate set + hard shield 不变
只把 action scoring 换成 oracle scoring
测它能否恢复 EdgeScore/fallback 的失败任务
```

### 3.2 必须新增脚本

```text
scripts/eval/run_g3_oracle_upper_bound.py
```

### 3.3 必须输出 artifacts

```text
outputs/reports/g3_oracle_upper_bound_report.md

outputs/tables/g3_teacher_next_in_mask.csv
outputs/tables/g3_local_oracle_replay_summary.csv
outputs/tables/g3_oracle_recovered_failures.csv
outputs/tables/g3_unrecoverable_failures.csv
outputs/tables/g3_oracle_failure_decomposition.csv
outputs/tables/g3_feature_need_summary.csv
outputs/figures/g3_oracle_recovery_heatmap.png
```

### 3.4 必须实现的 oracle 层级

#### Oracle-0：teacher-next-in-mask audit

对每个 G2 failed decision：

```text
current node
policy safe candidates
SIPP teacher next-hop
whether SIPP next-hop is in candidate list
whether SIPP next-hop is safe under same shield
if not safe: exact blocking reason
```

关键指标：

```text
teacher_next_candidate_recall
teacher_next_safe_recall
teacher_next_block_reason_distribution
```

#### Oracle-1：same-step SIPP next-hop oracle

规则：

```text
如果 SIPP teacher next-hop 在当前 safe candidates 中，选它；
否则使用 original EdgeScore/fallback action。
```

输出：

```text
planned_count
recovered_failures
remaining_failures
new_regressions
post_shield_conflicts
```

#### Oracle-2：SIPP rank oracle

规则：

```text
如果 teacher path 中多个下游节点都可选，按 teacher remaining path rank 排序；
否则使用 shortest-to-goal + reservation pressure tie-break。
```

意义：

```text
判断是否只需要 next-hop label，还是需要 rank/utility label。
```

#### Oracle-3：K-step local lookahead oracle

规则：

```text
在不使用完整 rolling-horizon SIPP 的前提下，
用当前 safe action + K-step SIPP/shortest-time rollout 判断动作是否会导致 no-safe-action / max_decisions。
```

K 值建议：

```text
K = 2, 3, 5
```

意义：

```text
判断是否需要 temporal/horizon feature。
```

#### Oracle-4：reservation-pressure oracle

规则：

```text
每个 candidate edge/node 计算 future reservation pressure：
  next 15s / 30s / 60s edge occupancy
  downstream merge occupancy
  buffer remaining capacity
  active fault/repair time
  shortest remaining time to goal
```

意义：

```text
判断 EdgeScore 是否缺少非局部拥堵特征。
```

### 3.5 G3 pass/fail 不按单一标准

G3 的结果有三种都算有效：

#### Development pass A：oracle recovers gap

```text
Oracle-1 or Oracle-2 recovers >= 70% of EdgeScore 47 failures
new regressions = 0
post_shield_conflicts = 0
```

解释：

```text
进入 G4 teacher data and EdgeRanker-v2。
```

#### Development pass B：oracle cannot recover but identifies structural blocker

```text
teacher_next_safe_recall < 0.70
or
unrecoverable failure dominated by no_safe_action / mask timing / horizon
```

解释：

```text
先修 safe mask / event horizon / observation before model。
```

#### Development pass C：mixed

```text
部分是 model/data，部分是 horizon/mask。
```

解释：

```text
G4 dataset + G3b structural audit 双线并行。
```

Promotion 不在 G3。G3 只是决定下一步路线。

---

## 4. G4：SIPP Teacher Slice Dataset Expansion

只有 G3 证明 local oracle 有足够 recovery potential，才进入 G4。

### 4.1 目标

把 G2/G3 的 failure slices 扩展成可训练数据，而不是继续用 78-slice smoke dataset。

### 4.2 必须新增

```text
scripts/data/build_g4_sipp_teacher_slices.py
outputs/reports/g4_sipp_teacher_dataset_report.md
artifacts/teacher/g4_sipp_junction_slices_manifest.jsonl
```

### 4.3 数据来源

必须覆盖：

```text
real map2/inputdata matched windows:
  legacy_first16
  legacy_first16_buffer2
  legacy_first32
  legacy_offset32_static16
  legacy_offset64_repair32
  legacy_offset64_merge32

synthetic manifest cases:
  phase8 persisted synthetic maps
  dense PIBT stress seeds
  random-topology matched scenarios
```

### 4.4 样本字段

每个 decision slice 至少包含：

```text
scenario_id
map_id
task_id / segment_id
current node
goal node
candidate edge list
safe mask
unsafe reasons
executed EdgeScore action
SIPP teacher next-hop
SIPP teacher rank over candidates
rolling-horizon SIPP route suffix
periodic SIPP action if available
deadline slack
heuristic remaining time
edge travel time
node service time
active fault edge
active repair window remaining time
node capacity remaining
merge group id
merge group current occupancy
edge reservation pressure 15/30/60s
node reservation pressure 15/30/60s
downstream k-hop congestion
no-safe-action risk within K steps
event policy terminal outcome
teacher completion outcome
```

### 4.5 数据 split

禁止只做 same-window train/test。

必须至少有：

```text
train:
  some real windows + some synthetic cases

validation:
  heldout task offsets from map2/inputdata
  heldout synthetic seeds

test:
  random-topology heldout cases
  selected fault/repair/merge stress cases
```

如果没有真实第二机场地图，也必须明确写：

```text
real heldout airport map unavailable
synthetic/topology heldout is not equivalent to real airport heldout
```

### 4.6 G4 report 必须回答

```text
number of slices
number of failed-case slices
teacher_next_in_mask rate
teacher action distribution
hold/action imbalance
fault/repair/merge/buffer coverage
deadline slack distribution
train/val/test leakage audit
```

---

## 5. G5：EdgeRanker-v2，不是 RL

### 5.1 为什么不是 PPO/MAPPO

当前失败不是 reward fine-tuning 能直接解决的问题。G2 显示：

```text
policy often holds when SIPP moves
policy chooses wrong branch
fault/repair/merge contexts are under-modeled
```

这些更适合：

```text
teacher rank supervision
risk/fallback head
feature ablation
DAgger-like failure-state aggregation
```

### 5.2 模型定位

命名建议：

```text
EdgeRanker-v2
```

它不是最终 RL policy，而是：

```text
SIPP-guided candidate ranking model
+
hard shield
+
fallback/abstention
```

### 5.3 输入

候选 edge-level features：

```text
current node one-hot / embedding
next node embedding
goal embedding / shortest-time-to-goal
edge travel time
node service time
deadline slack
candidate safe mask
blocked reason code
downstream reservation pressure
merge-group pressure
buffer capacity pressure
fault/repair state
teacher rank if training
```

Graph/context features：

```text
local 2-hop / 3-hop subgraph degree
active-bag density
task arrival pressure
recent no-safe-action counts
future occupancy summary
```

### 5.4 输出

```text
candidate score
fallback/abstain score
no-safe-action risk
future blockage risk
```

### 5.5 Loss

```text
listwise ranking loss over safe candidates
pairwise teacher_next vs nonteacher margin loss
unsafe candidate penalty
fallback calibration loss
future no-safe-action auxiliary loss
```

不要只做 hard top1 cross entropy。

### 5.6 Offline gates

Development gate：

```text
teacher-next top1 >= 0.70 on heldout decision slices
teacher-next top3 >= 0.90 if degree allows
unsafe raw top1 rate <= current EdgeScore
failure-slice recall improved over EdgeScore-v1
```

Promotion-candidate gate：

```text
heldout failed-slice teacher-next top1 >= 0.75
fault/repair/merge/buffer subgroups each improve over EdgeScore-v1
calibration ECE reported
abstention reasons logged
```

---

## 6. G6：Shadow and Closed-loop Recovery

G6 才允许 closed-loop，但仍然不是 paper claim。

### 6.1 Shadow mode

```text
Run EdgeRanker-v2 on the same G2 matched windows.
Do not execute its action first.
Compare:
  EdgeRanker-v2 predicted rank
  EdgeScore-v1 predicted action
  SIPP teacher action
  fallback action
```

Artifacts：

```text
outputs/reports/g6_shadow_edge_ranker_report.md
outputs/tables/g6_shadow_predictions.csv
```

### 6.2 Closed-loop smoke

Run with shield:

```text
EdgeRanker-v2 + shield
EdgeScore-v1 + shield
fallback + shield
rolling_horizon_sipp
periodic_replanning_sipp
```

Gate A：development

```text
EdgeRanker-v2 planned_count >= EdgeScore-v1 + 10 on 144 matched tasks
post_shield_conflicts = 0
no regression on legacy_first16
```

Gate B：promotion candidate

```text
EdgeRanker-v2 planned_count >= 125 / 144
post_shield_conflicts = 0
mean travel time not worse than fallback by > 20%
```

Gate C：strong candidate

```text
EdgeRanker-v2 planned_count >= 135 / 144
post_shield_conflicts = 0
improves EdgeScore-v1 on fault/repair/merge/buffer subgroups
```

即使 Gate C 通过，也不能说 beat SIPP unless it actually beats SIPP on matched metrics。

---

## 7. G7：才考虑 RL fine-tuning

只有满足以下条件才进入 RL：

```text
G3 oracle shows local learnability
G4 dataset has heldout split and coverage
G5 EdgeRanker-v2 improves offline rank metrics
G6 closed-loop recovers a meaningful part of the 47 failures
```

RL 初始路线：

```text
Conservative offline RL / advantage-weighted behavior cloning
not free exploration PPO first
```

可选：

```text
IPPO/MAPPO only after supervised policy is strong
reward shaping from SIPP regret
safety shield always on
fallback always on
```

禁止：

```text
unshielded exploration
claiming RL success on same 8-task smoke
training only on map2 first16
```

---

## 8. G8：高级 GNN / communication / hypergraph 路线

只有当 EdgeRanker-v2 MLP 明显 plateau 后才进入。

### 8.1 可尝试

```text
GNN over ICS graph
candidate-edge attention
merge-group hyperedge encoder
future occupancy world-model auxiliary head
local communication-style aggregation over active bags
```

### 8.2 必须先证明

```text
MLP EdgeRanker-v2 not enough
oracle gap remains
failure motif is nonlocal/group interaction dominated
dataset has enough samples
```

不要为了“看起来像顶会”直接上 Transformer/GNN。

---

## 9. 下一轮 Codex 主任务：G3，不是 G4/G5/G6

### 9.1 本轮目标

```text
Implement G3 oracle upper-bound and teacher-in-mask diagnosis.
Do not train a model.
Do not run PPO/MAPPO.
Do not claim learning success.
```

### 9.2 必做文件

```text
scripts/eval/run_g3_oracle_upper_bound.py
outputs/reports/g3_oracle_upper_bound_report.md
outputs/tables/g3_teacher_next_in_mask.csv
outputs/tables/g3_local_oracle_replay_summary.csv
outputs/tables/g3_oracle_recovered_failures.csv
outputs/tables/g3_unrecoverable_failures.csv
outputs/tables/g3_oracle_failure_decomposition.csv
outputs/tables/g3_feature_need_summary.csv
docs/codex-worklog.md update
README.md status update
```

### 9.3 复用 G2

G3 应复用：

```text
scripts/eval/run_g2_learning_gap_autopsy.py 的 scenario plan
G2 failed task inventory
G2 decision slices
Phase9 matched baseline scenario definitions
existing event replay infrastructure
rolling-horizon SIPP teacher
```

但不要只读 G2 CSV 做静态表。G3 必须执行 oracle replay。

### 9.4 必须记录

```text
teacher_next_in_candidate
teacher_next_in_safe_mask
teacher_next_block_reason
oracle_selected_action
oracle_recovered_failure
oracle_new_regression
oracle_remaining_failure
post_shield_conflicts
decision_count_delta
mean_travel_delta
```

---

## 10. 给 Codex 的长 prompt

下面这段可以直接复制给 Codex。

```text
继续 czr005，路径 C:\PROGRAMING\czr005，分支 codex/czr005-rewrite。先执行 git status --short，并确认当前 HEAD 是 495f49e 或更新。读取 README.md、docs/codex-worklog.md、outputs/reports/g2_learning_gap_autopsy.md、outputs/tables/g2_family_summary.csv、outputs/tables/g2_failure_motif_summary.csv、scripts/eval/run_g2_learning_gap_autopsy.py。

本轮不要做 PPO/MAPPO，不要训练 GNN/Transformer，不要把 G2 failure diagnosis 写成 learning success。当前事实是：G2 已经定位 EdgeScore 97/144 vs rolling_horizon_sipp 144/144 的 gap，EdgeScore 有 47 个 failed task-scenario rows，fallback 有 51 个，PIBT active-bag 有 105 个。G2 已明确 oracle upper-bound analysis: NOT DONE，属于 G3。

本轮目标：实现 G3 Oracle Upper Bound and Teacher-in-Mask Diagnosis。回答一个核心问题：在当前 safe candidate set 和 hard shield 不变的情况下，如果 oracle 能选择 rolling_horizon_sipp teacher next-hop 或 teacher-ranked safe candidate，能否恢复 EdgeScore 47 个失败任务中的大多数？

请新增 scripts/eval/run_g3_oracle_upper_bound.py，复用 G2 的 scenario definitions 和现有 event replay / rolling_horizon_sipp teacher。不要只静态读 G2 CSV；必须重新运行或重放 oracle policy。至少实现以下 oracle：

Oracle-0 teacher-next-in-mask audit:
  对每个 failed decision 记录 SIPP teacher next-hop 是否在 candidate list、是否在 safe mask、如果不在安全候选中，记录 block reason / candidate_count / safe_candidate_count / current / ready_time / scenario_context。

Oracle-1 same-step SIPP next-hop oracle:
  如果 SIPP teacher next-hop 在当前 safe candidates 中，选择它；否则回退到原 event policy/fallback safe action。报告 recovered EdgeScore failures、remaining failures、new regressions、post_shield_conflicts、planned count。

Oracle-2 SIPP-rank oracle:
  对 safe candidates 按 SIPP route suffix / shortest-to-goal / downstream pressure 近似排序。若 teacher next-hop 不可用，选择 teacher-rank best safe candidate。报告同样指标。

Oracle-3 K-step lookahead diagnostic:
  K=2/3/5，评估当前候选是否会在短视 rollout 中导致 no_safe_action 或 max_decisions。先做 diagnostic table 即可，不要求成为 policy。

必须生成：
  outputs/reports/g3_oracle_upper_bound_report.md
  outputs/tables/g3_teacher_next_in_mask.csv
  outputs/tables/g3_local_oracle_replay_summary.csv
  outputs/tables/g3_oracle_recovered_failures.csv
  outputs/tables/g3_unrecoverable_failures.csv
  outputs/tables/g3_oracle_failure_decomposition.csv
  outputs/tables/g3_feature_need_summary.csv
  outputs/figures/g3_oracle_recovery_heatmap.png 如果容易生成，否则报告中说明未生成原因。

报告必须包含：
  1. G2 baseline recap
  2. teacher_next_candidate_recall
  3. teacher_next_safe_recall
  4. EdgeScore 47 failures 中 Oracle-1/2/3 各恢复多少
  5. 哪些失败不可恢复，原因是 mask/shield/timing/horizon/feature
  6. 按 no_fault/static_fault/repair_window/merge_group/buffer_capacity 的 breakdown
  7. 按 motif 的 breakdown
  8. 结论：下一步是 G4 teacher dataset，还是先修 mask/horizon/observation
  9. Next Blocking Question
  10. Follow-up

Gate 解释：
  如果 oracle recovers >=70% of EdgeScore failures 且 new_regressions=0 且 post_shield_conflicts=0，则 G4 teacher dataset 是下一步。
  如果 teacher_next_safe_recall <70% 或不可恢复失败主要来自 no_safe_action/mask timing，则先做 mask/shield/event-horizon audit，不要训练模型。
  如果结果 mixed，则报告双线计划。

同时更新 docs/codex-worklog.md 和 README.md。README 只能写 G3 oracle diagnosis，不得写 learning success。跑：
  python scripts/eval/run_g3_oracle_upper_bound.py
  python -m py_compile scripts/eval/run_g3_oracle_upper_bound.py
  python -m pytest

如果 pytest 中 C++ backend 被 skip，要在报告里写清楚；不要把 skip 写成 pass。所有负结果都必须记录，不能隐藏。
```

---

## 11. 短 prompt 版本

```text
继续 czr005。不要进 PPO/MAPPO。G2 已定位 EdgeScore 97/144 vs SIPP 144/144 的 47 个失败 rows。现在做 G3 Oracle Upper Bound：在当前 safe candidate set 不变的情况下，用 SIPP teacher-next / teacher-rank oracle 测是否能恢复这些失败。新增 run_g3_oracle_upper_bound.py，输出 teacher-next-in-mask、oracle recovered failures、unrecoverable failure decomposition、feature need summary 和 g3_oracle_upper_bound_report.md。结论必须决定下一步是 G4 teacher dataset 还是先修 mask/horizon/observation。更新 README/worklog，跑脚本、py_compile、pytest。不要写 learning success claim。
```

---

## 12. 禁止事项

```text
不要直接开始 RL。
不要用 G2 结论证明 learning 有效。
不要再做一个 8-task smoke 就结束。
不要绕过 SIPP baseline。
不要只报告 planned_count，不报告 failure motifs。
不要只跑 same-map first16。
不要修改 legacy Java。
不要隐藏 C++ backend skip。
不要把 synthetic heldout 说成 real heldout airport map。
不要让 neural policy 绕过 hard shield。
```

---

## 13. 本阶段成功的真正标志

不是多一个 PASS，而是得到以下一种清晰结论：

### 结论 1：学习可行

```text
Teacher next-hop usually lies in the safe candidate set;
local oracle recovers most EdgeScore failures;
failure is mostly feature/model/data-limited.
```

这时进入：

```text
G4 SIPP teacher slice expansion
G5 EdgeRanker-v2
```

### 结论 2：学习暂不可行

```text
Teacher next-hop often absent/unsafe;
local oracle cannot recover;
failure is horizon/mask/shield/event semantics-limited.
```

这时进入：

```text
G3b mask/horizon/event semantics audit
```

### 结论 3：需要混合架构

```text
Some failures recover by ranking;
some need future occupancy/horizon;
some are repair/merge/buffer-specific.
```

这时进入：

```text
G4 dataset + G3b structural fixes in parallel
```

任何一个清晰结论都比“又一个 smoke PASS”更有价值。
