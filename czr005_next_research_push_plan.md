# czr005 下一轮大幅探索计划：从“工程底座可验收”推进到“学习策略可证明有研究价值”

生成日期：2026-07-02  
项目：`czr005`  
本地目标目录：`C:\PROGRAMING\czr005`  
远端仓库：`czr5454112-glitch/jichang_origin`  
当前工作分支：`codex/czr005-rewrite`  
已知当前提交：`6d3a358c89a5c18d38f61024ec4c71669c82bcaf`  
核心判断：**Phase1 是好结果；learning/RL 还不是好结果；下一轮必须从“做更多 smoke”切换到“系统性找出学习策略为什么不如 SIPP，并构造能让学习策略追上的数据、teacher、oracle 和评估闭环”。**

---

## 0. 一句话结论

当前结果不能简单说“好”或“坏”。

```text
好：
  Java -> Python/C++ faithful port 已经有较强证据；
  legacy Java parity、C++ core、pybind、baseline/shield/event replay 的工程底座可信；
  项目已经形成 worklog/report/CSV 的证据纪律。

坏：
  学习策略还不强；
  EdgeScore/BC/DAgger 目前只是 smoke/prototype；
  在 matched baseline 上，rolling-horizon SIPP / periodic SIPP 明显更强；
  C++ 并非所有 runtime/baseline family 都显著快；
  还没有真实 heldout airport map；
  没有 Phase6 RL fine-tuning，也没有 Phase7 GNN/hypergraph/world-model 级方法。
```

正确定位：

```text
czr005 已完成“可信仿真与非学习底座”的第一阶段；
现在进入“学习路线失败诊断 + 大规模 teacher/oracle/dataset 构造 + 安全学习策略提升”的研究阶段。
```

---

## 1. GitHub 状态复核摘要

本轮复核依据当前远端仓库内容与已生成报告：

### 1.1 README 当前边界是健康的

README 把项目写成：

```text
legacy Java reference
  -> Python reference parser/simulator
  -> C++ high-performance core
  -> Python learning environment
  -> shielded decentralized policies
```

并且明确标注：

```text
Learning experiments are still smoke/prototype scope, not final paper-grade RL results.
```

这是正确边界。后续 Codex 不得把 smoke/prototype 改写成 final RL result。

### 1.2 当前提交的含义

当前提交：

```text
6d3a358c89a5c18d38f61024ec4c71669c82bcaf
eval: add legacy java cpp acceptance summary
```

它主要新增的是 Java/C++ legacy acceptance summary，而不是新的学习算法。它证明的是：

```text
recorded Java/C++ legacy gates pass;
C++ >= Java on recorded legacy gates;
legacy Java remains read-only reference.
```

### 1.3 CI 状态

GitHub combined status / workflow runs 当前没有发现 GitHub Actions 结果。不能把“远端存在报告”当成“云端 CI 通过”。下一轮应增加本地 strict gate 和可选 GitHub Actions/CI。

### 1.4 Phase1 acceptance 是当前最强证据

Phase1/legacy port 的强证据包括：

```text
A* core:
  Java / Python / C++ path parity;
  8000 map2/inputdata cases;
  C++/Java speedup >= 1.736x.

legacy scheduler windows:
  no-fault window;
  scheduled fault/repair window;
  probability-extreme task generation window;
  all recorded gates PASS;
  C++/Java speedups around 38x-49x on recorded scheduler gates.
```

解释：

```text
这足够支持“Phase1 faithful port / Java -> Python+C++ 工程目标已验收”。
```

### 1.5 Phase9 matched baseline 暴露了真正问题

当前 matched baseline comparison 显示：

```text
rolling_horizon_sipp:      144 / 144 planned
periodic_replanning_sipp:  144 / 144 planned
edge_score_event:           97 / 144 planned
fallback_event:             93 / 144 planned
pibt_active_bag_replay:     39 / 144 planned
```

因此下一阶段的核心问题不是“能不能继续写一个 RL 文件”，而是：

```text
为什么学习策略少规划了 47 个任务？
哪些状态/岔路口/故障/merge/buffer 让 EdgeScore 退化？
SIPP teacher 到底提供了哪些 EdgeScore 没学到的信息？
有没有 oracle 上界显示 local policy 能接近 SIPP？
如果没有，学习策略需要增加 observation、temporal memory、global guide 或 world-model 辅助。
```

---

## 2. 质量判定：好在哪里，坏在哪里

## 2.1 好结果：工程底座可信

这是一个罕见的好开局。它不是只有 README 和空目录，而是已经有：

```text
legacy Java read-only copy
Python parser / A* / reference simulator
C++ core
pybind boundary
C++ backend loader
Java/Python/C++ A* parity
Java/C++ scheduler parity
Phase2 baseline/shield stack
Phase8 Python/C++ event replay parity
Phase9 matched comparison diagnostics
```

从研究项目角度，这解决了最危险的问题：

```text
后续 RL 结果不至于完全建立在漂移的 toy simulator 上。
```

## 2.2 坏结果：学习策略目前不是研究贡献

EdgeScore/BC/DAgger 当前价值是：

```text
证明数据管线、模型导出、C++推理、shielded replay 能跑通。
```

但它还没有证明：

```text
学习策略比 rolling-horizon SIPP 更好；
学习策略比 fallback 更稳；
学习策略能泛化到 heldout airport map；
学习策略能在 fault/repair/density/merge/buffer 下提升 throughput 或 travel time；
RL fine-tuning 带来 closed-loop benefit。
```

所以禁止写：

```text
JunctionShield-MARL outperforms improved A*
```

目前只能写：

```text
JunctionShield-MARL stack has a faithful simulator and shielded-learning prototype.
```

## 2.3 更深层的问题

当前代码已经很容易陷入“报告越来越多，但学习没有本质进步”的状态。风险是：

```text
1. Codex 每轮加一个 smoke；
2. 每个 smoke 都 PASS；
3. 最终 learning 方法仍然 planned count 低于 SIPP；
4. 论文写不出强结论。
```

因此下一轮必须切换为：

```text
failure-driven research;
oracle upper bound;
large teacher dataset;
heldout validation;
learning-policy gap closure;
strict promotion gates.
```

---

## 3. 新研究原则：学习策略必须被强 baseline 逼出来

参考学习式 MAPF 的近年趋势，本项目不要急着裸 RL。

应采用：

```text
strong search baseline / teacher
  -> trace-slice dataset
  -> imitation / DAgger
  -> shadow mode
  -> shielded closed-loop
  -> only then RL fine-tuning
```

原因：

```text
MAPF / LMAPF joint action space巨大；
RL exploration 很难；
强 planner teacher + collision shield 是目前更可靠路线；
ICS 是安全关键工业系统，不能让未验证 policy 直接控制冲突。
```

---

## 4. 相关工作给 czr005 的启发

以下不是让项目照搬 grid MAPF，而是提取可迁移的研究模式。

## 4.1 PRIMAL2

启发：

```text
lifelong MAPF + decentralized shared policy 是合理问题形式；
但 PRIMAL2 的 grid/FOV/discrete-time 不能直接照搬到 ICS。
```

czr005 采用方式：

```text
shared policy
local observation
continuous/event time junction decision
deadline-aware baggage task stream
```

## 4.2 Work Smarter Not Harder / CS-PIBT

核心启发：

```text
learned policy 必须配 smart one-step collision shield；
shield+greedy baseline 必须作为强对照；
不要把“无 shield 学会无碰撞”当主要卖点。
```

czr005 采用方式：

```text
JunctionShield 是 hard safety layer；
PIBT-style resolver / rolling SIPP / periodic SIPP 是 mandatory baselines；
所有 learned policy 都必须过 post-shield safety 和 fallback analysis。
```

## 4.3 SILLM

核心启发：

```text
large-scale imitation + global guidance + collision resolution + lifelong setting；
不是靠小 smoke 数据就能得到强策略。
```

czr005 采用方式：

```text
从 SIPP/rolling-horizon/periodic/PIBT event traces 生成大规模 junction-slice dataset；
先 IL/DAgger，再考虑 RL；
使用 global guide features，例如 shortest-time-to-goal、downstream congestion、deadline slack。
```

## 4.4 MAPF-GPT / large imitation

核心启发：

```text
数据规模和 expert trajectory conversion 很重要；
但 foundation-style action model 不是 czr005 第一阶段目标。
```

czr005 采用方式：

```text
做 ICS-junction trace dataset；
不是直接训练大模型；
先训练轻量 EdgeScore / ranking / risk / fallback heads。
```

## 4.5 LaGAT

核心启发：

```text
hybrid search + learned guidance + pretrain then fine-tune + deadlock/fallback；
dense MAPF 中 hybrid route 比纯 learning 更可信。
```

czr005 采用方式：

```text
learning 不替代 safety/routing baseline；
学习输出 junction score / congestion guide / candidate ranking；
SIPP / shortest path / shield 仍然保留。
```

## 4.6 MAPF-World

核心启发：

```text
reactive policy 容易短视；
future occupancy / future congestion / temporal dependency prediction 可能改善 long-horizon coordination。
```

czr005 采用方式：

```text
增加 auxiliary head:
  future node occupancy
  future edge queue
  future blocked decision
  future no-safe-action risk
  deadline miss risk
```

## 4.7 HMAGAT / hypergraph MAPF

核心启发：

```text
dense bottleneck 中 pairwise GNN 不够；
merge group / conveyor bottleneck / shared corridor 是高阶交互。
```

czr005 采用方式：

```text
Phase7 做 hyperedge:
  merge-group hyperedge
  shared downstream corridor hyperedge
  source/goal wavefront hyperedge
  active queue hyperedge
```

## 4.8 Airport / taxiway RL

机场地面/滑行道 RL 工作说明：

```text
airport traffic routing 需要 action mask、downstream conflict awareness、安全效率权衡；
真实机场拓扑和多约束决策是可发表问题。
```

但 czr005 的差异是：

```text
不是 aircraft taxiway；
不是 ground handling VRP；
是 ICS baggage directed graph + per-bag junction routing + industrial shield。
```

---

## 5. 下一轮核心研究问题

下一轮不应该问：

```text
能不能把 PPO 接上？
```

而应该问下面 10 个问题：

1. `EdgeScore planned 97/144` 的 47 个失败任务具体在哪里失败？
2. 失败是因为 action mask 太保守、observation 不足、teacher 过弱、模型过拟合，还是 event semantics bug？
3. SIPP 能计划而 EdgeScore 不能计划的状态，是否存在局部可观测策略能区分？
4. 如果给 EdgeScore 加 shortest-to-goal、downstream reservation、deadline slack、queue forecast，oracle 上界能到多少？
5. 用 rolling-horizon / periodic SIPP 生成 teacher slice，是否比 A*-guided teacher 更强？
6. DAgger 的 model-visited states 是否覆盖了 fault/repair/merge/buffer 的失败状态？
7. 有没有 heldout synthetic maps / randomized topologies 上学习策略退化明显？
8. 学习策略该先学 ranking、risk/fallback，还是直接学 action？
9. RL fine-tuning 前，是否已有 supervised/DAgger policy 接近 SIPP？
10. 如果 learned policy 永远达不到 SIPP planned count，它是否仍能在 latency/throughput/large-scale stress 上有价值？

---

## 6. 新阶段路线：CZR005-G1 到 G8

这不是替代原 Phase0-10，而是当前状态后的研究推进层。

---

# G1：Truth Audit / Reproducibility Hardening

目标：

```text
把已有 PASS 变成可一键复现的 PASS。
```

必须完成：

```text
scripts/eval/run_all_phase1_legacy_acceptance.py
scripts/check_phase1_acceptance.ps1
outputs/reports/g1_phase1_repro_audit_report.md
outputs/tables/g1_acceptance_regeneration_manifest.csv
```

要求：

```text
1. 从 clean build 或至少 clean artifacts 开始；
2. 重新跑 Java harness；
3. 重新跑 Python reference；
4. 重新跑 C++ Release pybind；
5. 重新生成底层 performance/parity CSV；
6. 再生成 summary；
7. 报告 commit、branch、dirty status、compiler、Python、conda env、CZR005_CPP_PYTHON_PATH。
```

Gate：

```text
strict_cpp=true
no skipped C++ acceptance tests
Java/Python/C++ A* parity exact
Java/C++ scheduler parity exact
C++ >= Java on recorded legacy gates
```

禁止：

```text
只读旧 CSV 生成新报告；
跳过 C++ backend 后仍然 PASS；
把 Debug timing 当 Release timing。
```

---

# G2：Learning Gap Autopsy

目标：

```text
解释 EdgeScore / fallback / PIBT 为什么输给 SIPP。
```

必须生成：

```text
outputs/reports/g2_learning_gap_autopsy.md
outputs/tables/g2_failed_task_inventory.csv
outputs/tables/g2_decision_failure_slices.csv
outputs/tables/g2_policy_vs_sipp_counterfactual.csv
outputs/figures/g2_failure_heatmap.png
```

分析维度：

```text
task_id
task source/goal
decision index
node / outgoing candidates
chosen action
teacher action
shield rejection reason
no_safe_action reason
fault/repair active state
node capacity state
merge group state
edge headway state
deadline slack
shortest remaining time
downstream reservation pressure
planned/unplanned
travel time gap
```

必须对比：

```text
rolling_horizon_sipp
periodic_replanning_sipp
edge_score_event
fallback_event
pibt_active_bag_replay
A*-guided scripted policy
```

核心输出：

```text
Top 10 failure motifs
Top 10 bottleneck nodes/edges
failure share by reason
whether failures are observation-limited or model-limited
whether SIPP success requires nonlocal planning beyond current observation
```

Gate：

```text
不能只说“planned count 差”；
必须定位每个 failed task 的 first divergence；
必须给出下一步 dataset/feature/teacher 修复建议。
```

---

# G3：Teacher / Oracle Upper Bound

目标：

```text
在训练前知道 local learned policy 的可达上限。
```

必须生成：

```text
outputs/reports/g3_teacher_oracle_upper_bound.md
outputs/tables/g3_teacher_family_comparison.csv
outputs/tables/g3_oracle_action_ranking.csv
outputs/tables/g3_oracle_observation_ablation.csv
```

Teacher family：

```text
A* guided safe policy
rolling-horizon SIPP teacher
periodic SIPP teacher
PIBT/CS-PIBT teacher
oracle best among available safe candidates
oracle best travel-time candidate
oracle best completion candidate
```

Observation ablations：

```text
local only
local + shortest-time-to-goal
local + deadline slack
local + reservation table summary
local + downstream 2-hop congestion
local + future SIPP hint
local + global queue pressure
```

问题：

```text
如果 oracle local candidate ranking 也达不到 SIPP planned count：
  说明问题需要 horizon / future occupancy / memory。

如果 oracle local candidate ranking 接近 SIPP：
  说明模型/数据不足，值得扩充 IL/DAgger。
```

Gate：

```text
必须报告 oracle gap；
没有 oracle gap 分析，不进入更大模型。
```

---

# G4：Large Junction Trace Slice Dataset

目标：

```text
从 smoke teacher 变成可训练数据资产。
```

必须生成：

```text
artifacts/teacher/junction_slices_v2_manifest.jsonl
artifacts/teacher/junction_slices_v2_sample.jsonl
outputs/reports/g4_junction_trace_dataset_report.md
outputs/tables/g4_dataset_coverage.csv
outputs/tables/g4_slice_schema_validation.csv
```

数据来源：

```text
real map2/inputdata windows
persisted synthetic manifests
random topology DAG-like maps
dense PIBT stress maps
fault/repair schedules
buffer capacity scenarios
merge group scenarios
high-density source collisions
heldout-like synthetic maps
```

规模建议：

```text
pilot:
  >= 100 windows
  >= 10,000 task legs
  >= 100,000 decision slices

expanded:
  >= 1,000 windows
  >= 100,000 task legs
  >= 1,000,000 decision slices
```

Slice schema：

```text
context:
  map_id
  scenario_id
  task_id
  current_node
  goal
  pass_time
  ready_time
  deadline/std if available
  slack
  active_faults
  node_capacity_config
  merge_config

candidate:
  edge_from
  edge_to
  edge_travel_time
  service_time_next
  shortest_time_to_goal
  queue_ahead
  reservation_count_node
  reservation_count_edge
  merge_group_pressure
  fault_window_active
  shield_status
  teacher_rank
  oracle_rank

labels:
  expert_action
  expert_source_family
  teacher_rank_margin
  safe_mask
  completion_label
  delay_delta
  no_safe_action_risk
  fallback_should_abstain
```

Split policy：

```text
train:
  map2 early windows + selected synthetic maps

validation:
  map2 heldout offsets + synthetic heldout seeds

test:
  randomized topology family not used in training
  fault/repair schedules not used in training

future:
  separate real airport heldout map if obtained
```

Gate：

```text
no train/test leakage by task offset, map seed, scenario id;
schema validation pass;
coverage report includes failure states, not only successful easy slices.
```

---

# G5：Supervised Policy Ladder Before RL

目标：

```text
把 EdgeScore 从 smoke 模型推进到可竞争的 supervised policy。
```

模型 ladder：

```text
M0: existing pure-Python MLP EdgeScore smoke
M1: sklearn / numpy MLP with proper train/val split
M2: PyTorch MLP edge scorer
M3: candidate-set DeepSets / attention scorer
M4: graph-local GNN scorer over 2-hop subgraph
M5: risk/fallback head + rank head multi-task model
```

训练目标：

```text
masked cross entropy for teacher action
pairwise ranking loss for teacher rank
margin loss for high-confidence SIPP choices
risk BCE for no-safe-action / failure states
abstention calibration loss
travel-time/regret auxiliary loss
```

必须对比：

```text
A*-teacher only
SIPP-teacher only
mixed teacher
DAgger model-visited relabeling
fault-curriculum teacher
risk/fallback multi-task
```

报告：

```text
outputs/reports/g5_supervised_policy_ladder.md
outputs/tables/g5_policy_offline_metrics.csv
outputs/tables/g5_policy_shadow_metrics.csv
outputs/tables/g5_policy_closed_loop_metrics.csv
outputs/tables/g5_ablation_teacher_feature_model.csv
```

Gate：

```text
closed-loop planned count must approach SIPP on at least one heldout-like family;
must beat fallback_event on planned count or travel time;
must have zero post-shield conflicts;
must report when it underperforms SIPP.
```

禁止：

```text
只报告 train top1；
只在 8-task smoke 上报告；
无 heldout split 就宣称 learning works。
```

---

# G6：RL Fine-tuning Only After Supervised Gate

目标：

```text
只在 supervised policy 足够强时做 RL fine-tuning。
```

允许条件：

```text
G5 closed-loop policy >= fallback_event on heldout windows;
G5 policy has zero post-shield conflicts;
failure autopsy shows reward shaping can target remaining gap;
SIPP oracle gap suggests local policy can improve.
```

RL candidates：

```text
IPPO with shared policy
MAPPO centralized critic
DQN/QR-DQN for discrete outgoing edge actions
offline RL / conservative Q-learning from teacher traces
DAgger + policy gradient hybrid
```

Reward：

```text
- travel time
- waiting / hold cost
- shield rejection penalty
- no_safe_action risk
- late/deadline penalty
+ completion reward
+ throughput/global sparse reward
```

Safety:

```text
shield always on
unsafe action never executed
shield intervention logged
abstention/fallback allowed
```

Artifacts:

```text
outputs/reports/g6_rl_finetuning_plan.md
outputs/reports/g6_rl_reward_ablation.md
outputs/tables/g6_rl_vs_bc_vs_sipp.csv
outputs/tables/g6_rl_safety_interventions.csv
```

Gate：

```text
RL must improve over BC/DAgger policy in closed-loop heldout diagnostics;
if RL does not improve, keep RL as negative result and return to G4/G5.
```

---

# G7：Advanced Graph / Hypergraph / World Model Route

目标：

```text
只有在 G5/G6 plateau 后才进入高级模型。
```

候选：

```text
GNN over ICS graph
candidate-edge attention
merge-group hypergraph encoder
future occupancy / queue world-model auxiliary head
temporal GRU/Transformer over recent local decisions
deadline-aware value head
```

必须先做 oracle/diagnostic：

```text
pairwise GNN 是否解决不了 merge group？
future congestion prediction 是否和 failure reduction 相关？
hypergraph encoder 是否降低 bottleneck failures？
```

Artifacts：

```text
outputs/reports/g7_advanced_model_memo.md
outputs/tables/g7_world_model_auxiliary_metrics.csv
outputs/tables/g7_gnn_hypergraph_ablation.csv
```

Gate：

```text
advanced model must beat MLP/DeepSets under same dataset and same shield;
must justify added runtime overhead.
```

---

# G8：Paper-Grade Evidence Package

目标：

```text
把工程结果变成可写论文的 claim ledger。
```

必须生成：

```text
outputs/reports/g8_claim_ledger.md
outputs/reports/g8_main_experiment_plan.md
outputs/reports/g8_limitations.md
outputs/tables/g8_claim_to_artifact_map.csv
outputs/tables/g8_final_baseline_comparison.csv
outputs/figures/g8_runtime_scaling.png
outputs/figures/g8_quality_tradeoff.png
```

Claim categories：

```text
faithful port claim
scalability claim
safety claim
learning benefit claim
robustness claim
runtime claim
generalization claim
```

每个 claim 必须对应：

```text
artifact path
command
commit
scenario set
baseline set
metric
statistical test
known limitation
```

---

## 7. 新的 Gate 体系

沿用 czr004 中 layered gate 的精神，但改成 czr005 版本。

## 7.1 Development Gate

用途：

```text
判断方向是否值得继续。
```

允许：

```text
small smoke
same-map validation
single local machine
soft thresholds
negative result accepted
```

禁止：

```text
称为 final result
写成 paper claim
删除失败样本
```

## 7.2 Promotion-Candidate Gate

用途：

```text
判断是否值得更大训练/更多场景。
```

要求：

```text
heldout windows
nontrivial density/fault/repair coverage
closed-loop replay
comparison against fallback_event and one SIPP family
zero post-shield conflicts
failure analysis
```

## 7.3 Runtime / Paper Gate

用途：

```text
判断是否能作为最终论文结论。
```

要求：

```text
rolling/periodic SIPP strong baselines
A* baseline
fallback baseline
BC/DAgger baseline
RL if applicable
heldout synthetic topologies
real map2 offsets
separate real airport map if available
multi-seed
paired stats
hardware metadata
claim ledger
```

---

## 8. 下一轮 Codex 不应做什么

不要让 Codex 继续：

```text
1. 再加一个 tiny smoke 然后说 PASS；
2. 直接上 PPO/MAPPO；
3. 只增加 README 状态；
4. 只汇总旧 CSV；
5. 在没有失败诊断的情况下训练更大模型；
6. 把 EdgeScore planned 97/144 写成 learning success；
7. 把 C++ 在部分 family 变慢的事实隐藏起来；
8. 无 heldout split 做模型评价；
9. 改 Java legacy；
10. 跳过 worklog/report。
```

---

## 9. 直接给 Codex 的长周期 Prompt

下面这段可以直接复制给 Codex。它不是让 Codex 一次做完，而是要求 Codex 进入长周期探索模式，每轮都必须留下报告和下一步。

```text
你现在继续 czr005 项目，仓库路径是 C:\PROGRAMING\czr005，GitHub 分支是 codex/czr005-rewrite。先执行 git status --short，并读取 README.md、czr005_project_master_plan.md、docs/codex-worklog.md、outputs/reports/java_cpp_legacy_acceptance_summary_report.md、outputs/reports/phase9_matched_baseline_comparison_report.md、outputs/reports/phase9_matched_runtime_scaling_report.md。

本轮不是做一个小 smoke 后结束，也不是直接进入 PPO/MAPPO。你要把项目从“Phase1 工程底座可验收”推进到“学习策略为什么不如 SIPP、怎样让它接近或超过强 baseline”的系统探索阶段。

核心事实必须承认：
1. Java -> Python/C++ faithful port 阶段是好结果，Phase1 可以验收。
2. Learning/RL 还不是好结果；EdgeScore/BC/DAgger 只是 smoke/prototype。
3. Phase9 matched baseline 中 rolling_horizon_sipp 和 periodic_replanning_sipp planned 144/144，而 edge_score_event 只 planned 97/144，fallback_event 93/144，pibt_active_bag_replay 39/144。
4. 不能把 smoke/prototype 写成 final RL 或 paper-grade result。
5. 下一阶段必须 failure-driven，不允许只做容易 PASS 的新增脚本。

请按以下顺序推进。不要试图一次完成所有 G1-G8；每一轮最多完成一个 G 阶段或一个 G 阶段的可审计子任务，并在 docs/codex-worklog.md 中写清楚未完成项。

第一优先级 G1：reproducibility hardening
- 新增或完善一键 acceptance runner，不只是 summary old CSV。
- strict C++ mode：C++ backend 缺失时 acceptance 必须 fail，不能 skip 后 PASS。
- acceptance 报告必须记录 commit、branch、dirty status、compiler、Python、conda env、build type、CZR005_CPP_PYTHON_PATH、完整命令。
- 产出 outputs/reports/g1_phase1_repro_audit_report.md。

第二优先级 G2：learning gap autopsy
- 解释 EdgeScore/fallback/PIBT 为什么输给 rolling_horizon_sipp 和 periodic_replanning_sipp。
- 生成 failed task inventory、decision failure slices、policy-vs-SIPP counterfactual 表。
- 找 first divergence，不要只汇总 planned count。
- 按 node/edge/fault/repair/merge/buffer/deadline slack/downstream congestion 归因。
- 产出 outputs/reports/g2_learning_gap_autopsy.md。

第三优先级 G3：teacher/oracle upper bound
- 比较 A*-guided teacher、rolling-horizon SIPP teacher、periodic SIPP teacher、PIBT teacher、oracle safe candidate。
- 做 observation ablation：local only、local+shortest-to-goal、local+deadline、local+reservation summary、local+downstream congestion。
- 判断学习策略的上限是 local observation 不足，还是模型/数据不足。
- 产出 outputs/reports/g3_teacher_oracle_upper_bound.md。

第四优先级 G4：large junction trace dataset
- 把 teacher slices 从 smoke 扩成 junction_slices_v2。
- 数据必须覆盖 success 和 failure，不能只覆盖 easy successful routes。
- 加 train/validation/test split，避免 map/task/window leakage。
- 产出 artifacts/teacher/junction_slices_v2_sample.jsonl、outputs/reports/g4_junction_trace_dataset_report.md。

第五优先级 G5：supervised policy ladder
- 在 RL 前先做 supervised/DAgger policy ladder。
- 比较 A*-teacher、SIPP-teacher、mixed teacher、fault-curriculum teacher、risk/fallback multi-task。
- 至少跑 offline metrics、shadow replay、closed-loop replay。
- 必须与 fallback_event 和 SIPP family 比较。
- 产出 outputs/reports/g5_supervised_policy_ladder.md。

只有当 G5 的 closed-loop policy 在 heldout windows 上至少超过 fallback_event 并接近 SIPP，才能写 G6 RL fine-tuning plan。否则不要做 RL；先回到 G2-G5。

硬约束：
- 不修改 legacy Java reference。
- 不删除或弱化 safety shield。
- 不把 smoke 写成 paper claim。
- 不隐藏负结果。
- 不把 C++ slower family 写成 speed success。
- 不提交 build 目录、大 checkpoint、大 raw data。
- 每次实验必须有 outputs/reports/*.md 和 outputs/tables/*.csv。
- 每次结束必须写 “Interpretation / Next blocking question / Follow-up”。

本轮建议先做 G1 或 G2，不要直接做 G4/G5/G6。你可以自行选择 G1 或 G2 中更高杠杆的一项，但必须解释选择理由，并留下下一轮可继续的问题。
```

---

## 10. 推荐当前立即执行的 Codex Round

如果只选一个最优任务，我建议：

```text
G2 Learning Gap Autopsy
```

原因：

```text
Phase1 已经够好；
G1 虽然重要，但不会直接推进学习；
G2 能直接告诉我们 EdgeScore 为什么不如 SIPP；
没有 G2，后面 G4/G5/G6 都可能是在盲目堆模型。
```

最小可交付：

```text
scripts/eval/run_g2_learning_gap_autopsy.py
outputs/reports/g2_learning_gap_autopsy.md
outputs/tables/g2_failed_task_inventory.csv
outputs/tables/g2_first_divergence_by_task.csv
outputs/tables/g2_policy_vs_sipp_decision_slices.csv
outputs/tables/g2_failure_motif_summary.csv
```

验收问题：

```text
能不能指出 EdgeScore planned 97/144 中失败的 47 个任务，分别第一次在哪个节点、哪个动作、哪个 mask/shield/teacher divergence 出现问题？
```

如果这个问题答不上来，项目不应进入 RL。

---

## 11. 给论文方向的判断

如果后续 G2-G5 顺利，论文主线可以是：

```text
A shielded decentralized learning-routing framework for airport ICS baggage systems,
trained from strong planning teachers and deployed with C++ event replay,
showing scalable low-latency local decisions while preserving hard safety constraints.
```

如果学习策略始终不如 SIPP，论文也不一定失败，但主线要改成：

```text
A faithful open simulation / benchmark / baseline suite for airport ICS routing,
with evidence that strong SIPP-style planning remains hard to beat,
and a diagnosis of where learning-based decentralized policies fail.
```

但真正更有价值的目标还是：

```text
Learning policy in large-scale high-density windows gives better latency / throughput tradeoff
than repeated centralized planning, while SIPP remains oracle/teacher baseline.
```

---

## 12. 当前项目总评

我的判断：

```text
当前结果：中上，偏好。
工程质量：好。
研究结果：还不够好。
方向选择：仍然对。
下一步难点：不是代码量，而是把 learning gap 逼清楚。
```

项目现在最该避免的是“继续刷 PASS 报告”。最该做的是：

```text
让 Codex 长时间围绕失败样本、teacher 上界、dataset 覆盖、policy gap、heldout 泛化做系统探索。
```
