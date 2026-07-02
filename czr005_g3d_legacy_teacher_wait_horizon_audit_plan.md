# czr005 G3d 推进计划：Legacy-A* Teacher 可用性、等待标签与 Event-Horizon 语义审计

生成日期：2026-07-02
项目目录：`C:\PROGRAMING\czr005`
远端仓库：`czr5454112-glitch/jichang_origin`
当前分支：`codex/czr005-rewrite`
最新已知提交：`891b67c eval: add g3c legacy astar teacher audit`
本文件目的：在 G3c 证明 Legacy-A* teacher 比 SIPP 更贴近当前环境之后，阻止项目过早进入大规模训练，先把 `Legacy-A* route-next label` 转换成真正可用于 imitation / DAgger / RL warm-start 的稳定 teacher 语义。

---

## 0. 当前判断

G3c 是一个重要的方向性验证，但它不是进入训练的许可。

G3c 证明：

```text
Legacy-A* teacher next-hop candidate recall = 1.000
Legacy-A* teacher next-hop safe recall      = 0.610
G3 SIPP teacher safe recall                 = 0.319
post-shield conflicts                       = 0
Legacy vs SIPP shared-decision agreement    ≈ 0.919 - 0.987
```

这说明用户提出的方向是正确的：

```text
原 CIE / Legacy-A* 轨迹应该成为第一 teacher；
SIPP 应作为 upper-bound / repair oracle / strong baseline，而不是默认唯一 teacher。
```

但 G3c 同时证明：

```text
Legacy-A* forced replay planned only 78/144;
remaining blocked/unavailable slices = 614;
all current labels are move labels, no explicit hold labels;
主要 block reason 是 edge_capacity；
branch nodes 的 safe recall 明显低于 linear nodes；
fault / repair / merge scenarios 中 safe recall 更低。
```

因此，当前结论不是：

```text
可以马上用 Legacy-A* labels 训练 BC/RL。
```

而是：

```text
Legacy-A* route-next 是好的 teacher source，
但必须先补齐 wait / reroute / unavailable / event-horizon 语义，
否则直接训练会把暂时不可执行的 move label 当作监督目标，制造错误梯度和 covariate shift。
```

---

## 1. 为什么不能直接进入 G4A 大规模 teacher dataset

### 1.1 Legacy-A* route-next label 缺少等待语义

原 A* 输出的是路线：

```text
v0 -> v1 -> v2 -> ... -> goal
```

而当前 local event policy 需要的是：

```text
MOVE_NOW(next)
HOLD_UNTIL_SAFE(next)
REROUTE_NOW(new_next)
ABSTAIN_TO_FALLBACK
NO_TEACHER_AVAILABLE
```

G3c 的 label coverage 显示当前几乎只有 move labels，没有 hold labels。大量 teacher next-hop 不在 safe mask 里时，正确标签不一定是“不要走这条边”，而可能是：

```text
先 hold 到 edge/node/merge 释放，再继续走 Legacy-A* route-next。
```

如果直接训练：

```text
observation -> next-hop
```

模型会被迫在 unsafe state 里预测 move label；运行时 shield 又会把它 hold 或 block，导致训练分布与执行分布错位。

### 1.2 forced replay 只完成 78/144，说明 raw route labels 不够闭环

Legacy-A* safe recall 高于 SIPP，但 forced replay planned count 只有 78/144。它甚至低于当前 EdgeScore 的 97/144。这并不说明 Legacy teacher 差，而说明：

```text
当前 replay 还没有把 Legacy-A* 的“时间化路线”和 event policy 的“逐步动作”对齐。
```

要先搞清楚：

```text
是 event env 的 edge_capacity 过严？
是 teacher action 本来需要 wait-until-safe？
是 max_decisions / hold step 太短？
是 active route 已经偏离 legacy route 后 teacher 不再有效？
是原 Java scheduler 的任务释放/route update 与当前 event replay 不一致？
```

这些问题不解决，G4A dataset 只会放大错位。

### 1.3 branch-node 是关键瓶颈

G3c 显示 branch 决策 safe recall 明显低于 linear 决策，尤其在 fault/repair/merge 场景中最严重。论文目标是“每个岔路口如何转向”，所以不能只看全局 safe recall。必须单独审计：

```text
branch-node route-next label
branch-node wait-until-safe label
branch-node reroute label
merge/buffer/fault branch label
```

---

## 2. 本轮 G3d 的核心问题

G3d 必须回答：

```text
G3c 中 614 个 blocked/unavailable Legacy-A* teacher slices，到底有多少可以通过等待、时间跳跃、重新查询 Legacy-A* 或更准确的 Java/C++ scheduler trace 修复？
```

进一步拆成 7 个问题：

```text
Q1. teacher next-hop 被 edge_capacity block 时，earliest safe time 是多少？
Q2. 如果执行 HOLD_UNTIL_SAFE(next)，planned count 能从 78/144 提升到多少？
Q3. 如果把 hold step 从 1s 改成 jump-to-earliest-safe-time，是否消除 max_decisions / blocked cascade？
Q4. 如果 learner/current state 偏离 route，重新从 current node 查询 Legacy-A* 能否恢复？
Q5. 如果 legacy_astar_no_path 出现，是故障/约束导致无路，还是 route/state 对齐错误？
Q6. Java/C++ faithful scheduler 的 route timing 是否与 Python event replay timing 一致？
Q7. 哪些样本适合进入 G4A teacher dataset，哪些必须标成 temporarily unsafe / unavailable / repair-needed？
```

---

## 3. G3d 必须新增的脚本与报告

### 3.1 主脚本

新增：

```text
scripts/eval/run_g3d_legacy_teacher_wait_horizon_audit.py
```

不得修改 legacy Java。若需要 Java 验证，只能通过外部 read-only harness 或已有 acceptance artifacts 做 spot-check。

### 3.2 必须输出

```text
outputs/reports/g3d_legacy_teacher_wait_horizon_audit_report.md

outputs/tables/g3d_blocked_slice_ledger.csv
outputs/tables/g3d_earliest_safe_time_labels.csv
outputs/tables/g3d_teacher_replay_variant_summary.csv
outputs/tables/g3d_wait_until_safe_recovered_tasks.csv
outputs/tables/g3d_still_blocked_after_wait.csv
outputs/tables/g3d_legacy_reroute_from_current.csv
outputs/tables/g3d_branch_vs_linear_recall.csv
outputs/tables/g3d_edge_capacity_hotspots.csv
outputs/tables/g3d_teacher_label_taxonomy.csv
outputs/tables/g3d_g4a_eligible_slice_manifest.csv

artifacts/teacher/legacy_astar/g3d_legacy_astar_wait_labels_sample.jsonl
outputs/figures/g3d_block_reason_heatmap.png
```

### 3.3 报告必须回答

报告必须有以下章节：

```text
1. Scope and non-claim boundary
2. G3c recap
3. Blocked slice root-cause ledger
4. Earliest-safe-time / wait-until-safe audit
5. Replay variants and planned-count comparison
6. Reroute-from-current audit
7. Branch vs linear decision breakdown
8. Label taxonomy for G4A
9. Decision: enter G4A, run more G3d, or fix event semantics first
```

---

## 4. Replay variants：必须至少比较 6 种

G3d 不能只读 G3c CSV。必须重新运行或重放 teacher policy variants。

### Variant 0：G3c baseline

保持 G3c 原逻辑：

```text
Legacy-A* route-next if safe;
otherwise shield hold / mark unplanned.
```

用于复现：

```text
planned = 78/144
safe recall = 0.610
blocked = 614
```

### Variant 1：wait-until-safe label, fixed hold step

规则：

```text
如果 Legacy next-hop 当前不 safe，但仍在 candidate set：
  不把它当失败；
  label = HOLD_UNTIL_SAFE(next)
  每次 hold_seconds = 1.0 / 2.0 / 5.0 做 sweep
  直到 next-hop safe 或 max_wait_seconds 超限
```

输出：

```text
planned_count
mean_wait_inserted
max_wait_inserted
new_unplanned_count
post_shield_conflicts
```

### Variant 2：jump-to-earliest-safe-time

规则：

```text
用 reservation table / shield reason 计算 teacher next-hop 的 earliest safe entry time；
直接把 ready_time 推进到 earliest safe time；
再执行 Legacy next-hop。
```

目的：

```text
区分“真的无路”与“1s hold step 导致 max_decisions / horizon artifact”。
```

### Variant 3：reroute-from-current Legacy-A*

规则：

```text
如果当前 state 已偏离 original Legacy route 或 teacher_next no longer valid：
  query Legacy-compatible A* from current node to goal under current fault/constraint state
  如果找到 path，则 label = REROUTE_NOW(new_next)
  否则 label = LEGACY_NO_PATH
```

注意：必须保留 label_source：

```text
legacy_route_next
legacy_wait_until_safe
legacy_reroute_from_current
legacy_no_path
fallback_safe
sipp_repair
```

### Variant 4：capacity/merge diagnostic ablation

只作诊断，不作训练：

```text
A. disable edge_capacity block only
B. disable merge_group block only
C. increase edge capacity to 2 for selected hotspots
D. jump-to-release-time for edge capacity
```

目的：

```text
判断 614 blocked slices 是否主要来自真实安全约束，还是来自 replay timing / capacity interpretation。
```

严禁把 ablation 结果当最终算法结果。它只用于定位问题。

### Variant 5：hybrid Legacy-A* + fallback / SIPP repair

规则：

```text
优先 Legacy-A* teacher；
若 Legacy route-next temporarily blocked -> HOLD_UNTIL_SAFE；
若 Legacy no-path -> query SIPP repair or fallback safe shortest action；
所有样本必须记录 label_source。
```

目的：

```text
为 G4A dataset 确定多源 teacher schema。
```

---

## 5. Teacher label taxonomy：G4A 前必须固定

G3d 必须把所有 teacher slices 标为以下之一：

```text
MOVE_NOW_LEGACY
HOLD_UNTIL_SAFE_LEGACY_NEXT
REROUTE_NOW_LEGACY
LEGACY_NO_PATH
LEGACY_NEXT_GLOBALLY_UNSAFE
LEGACY_NEXT_TEMPORARILY_BLOCKED
FALLBACK_SAFE_MOVE
SIPP_REPAIR_MOVE
ABSTAIN_NO_TEACHER
```

每个样本必须至少包含：

```text
scenario
segment_id
task_id
current
goal
ready_time
candidate_next_nodes
safe_next_nodes
legacy_route_suffix
legacy_next
label_kind
label_next
hold_until_time
hold_duration
block_reason
block_reason_detail
label_source
post_label_safe
teacher_finish_time
replay_variant
branch_or_linear
fault_state
repair_state
merge_state
buffer_state
```

G4A 只能使用：

```text
MOVE_NOW_LEGACY
HOLD_UNTIL_SAFE_LEGACY_NEXT
REROUTE_NOW_LEGACY
```

作为 primary Legacy labels。

以下只能作为 auxiliary / exclusion / repair data：

```text
LEGACY_NO_PATH
LEGACY_NEXT_GLOBALLY_UNSAFE
FALLBACK_SAFE_MOVE
SIPP_REPAIR_MOVE
ABSTAIN_NO_TEACHER
```

---

## 6. G3d 判断标准

### 6.1 Development pass：可以进入 G4A 小规模 teacher dataset

需要满足：

```text
wait/reroute-aware Legacy replay planned_count >= 115/144
post_shield_conflicts = 0
branch safe/effective label coverage >= 0.75
LEGACY_NO_PATH / ABSTAIN slices clearly separated
no uncontrolled regression relative to G3c
```

解释：

```text
Legacy-A* teacher 语义足够稳定，可以进入 G4A pilot dataset。
```

### 6.2 Diagnostic pass：先继续修 semantics

如果：

```text
planned_count < 115/144
or branch coverage < 0.75
or most blocked slices remain edge_capacity with unclear timing
or reroute-from-current changes behavior unpredictably
```

解释：

```text
继续 G3d/G3b，先修 event-horizon / capacity / mask semantics。
```

### 6.3 Hard stop：不能进入训练

如果出现：

```text
post_shield_conflicts > 0
or Java/C++/Python route parity breaks
or label_source 无法追踪
or dataset mixes Legacy and SIPP labels without source
or legacy Java modified
```

解释：

```text
停止并修工程底座。
```

---

## 7. 后续路线图

### 如果 G3d pass

进入：

```text
G4A Legacy-A* Teacher Dataset Pilot
```

内容：

```text
生成 10k-100k junction slices；
包含 MOVE/HOLD/REROUTE labels；
train/val/test split by scenario/time window/synthetic map；
训练 EdgeRanker-Legacy-v1；
只做 shadow + closed-loop smoke，不做 RL。
```

### 如果 G3d partial

进入：

```text
G3e Legacy Teacher Semantics Repair
```

内容：

```text
fix edge_capacity timing;
add earliest-safe-time API;
align C++/Python event replay;
increase max_decisions only with justification;
add explicit no-path/repair labels.
```

### 如果 G3d fail

重新定义 teacher：

```text
Legacy-A* as route-level teacher only;
SIPP/rolling SIPP as execution-level repair teacher;
learned policy becomes hybrid route-following + shielded wait/reroute assistant.
```

---

## 8. Codex 执行要求

Codex 本轮不要：

```text
不要训练模型
不要做 PPO/MAPPO
不要做 GNN/Transformer
不要扩大 teacher dataset
不要修改 legacy Java
不要把 G3d 诊断写成 learning success
```

Codex 本轮必须：

```text
先 git status --short
确认 HEAD 在 891b67c 或更新
读取 README、worklog、G3/G3c 报告和 G3c CSV
实现 G3d script
生成报告与表格
跑 py_compile
跑 pytest
更新 README 和 codex-worklog
记录所有负结果
```

---

## 9. 给 Codex 的长 prompt

```text
继续 czr005，路径 C:\PROGRAMING\czr005，分支 codex/czr005-rewrite。先运行 git status --short，确认工作树干净，HEAD 是 891b67c 或更新。读取 README.md、docs/codex-worklog.md、outputs/reports/g3_oracle_upper_bound_report.md、outputs/reports/g3c_legacy_astar_teacher_fidelity_report.md、outputs/tables/g3c_teacher_replay_safety.csv、outputs/tables/g3c_teacher_unavailable_cases.csv、outputs/tables/g3c_teacher_label_coverage.csv。

本轮目标是 G3d Legacy-A* Teacher Wait/Horizon Audit。不要训练模型，不要做 PPO/MAPPO，不要做 GNN/Transformer，不要进入 G4A 大规模 teacher dataset，不要修改 legacy Java。G3c 已证明 Legacy-A* teacher 比 SIPP 更贴近当前环境：candidate recall 1.000，safe recall 0.610，高于 SIPP 0.319；但 forced replay 只 planned 78/144，并有 614 blocked/unavailable slices。因此本轮必须解释这些 blocked slices，而不是把它们直接训练成 move labels。

新增脚本 scripts/eval/run_g3d_legacy_teacher_wait_horizon_audit.py。必须重新运行或重放 teacher policy variants，不要只静态读 G3c CSV。至少实现以下 replay variants：

1. G3c baseline replay reproduction。
2. fixed-hold wait-until-safe，hold_seconds sweep = 1.0 / 2.0 / 5.0。
3. jump-to-earliest-safe-time replay。
4. reroute-from-current Legacy-compatible A* replay。
5. diagnostic capacity/merge ablations，只作诊断，不作算法 claim。
6. hybrid Legacy-A* + fallback/SIPP repair label audit，必须保留 label_source。

必须输出：
outputs/reports/g3d_legacy_teacher_wait_horizon_audit_report.md
outputs/tables/g3d_blocked_slice_ledger.csv
outputs/tables/g3d_earliest_safe_time_labels.csv
outputs/tables/g3d_teacher_replay_variant_summary.csv
outputs/tables/g3d_wait_until_safe_recovered_tasks.csv
outputs/tables/g3d_still_blocked_after_wait.csv
outputs/tables/g3d_legacy_reroute_from_current.csv
outputs/tables/g3d_branch_vs_linear_recall.csv
outputs/tables/g3d_edge_capacity_hotspots.csv
outputs/tables/g3d_teacher_label_taxonomy.csv
outputs/tables/g3d_g4a_eligible_slice_manifest.csv
artifacts/teacher/legacy_astar/g3d_legacy_astar_wait_labels_sample.jsonl
outputs/figures/g3d_block_reason_heatmap.png

报告必须明确给出：
- Legacy-A* raw route-next labels 有多少是 MOVE_NOW。
- 有多少 blocked labels 可以转成 HOLD_UNTIL_SAFE。
- earliest-safe-time 后 planned_count 是否显著高于 78/144。
- reroute-from-current 能恢复多少 legacy_astar_no_path。
- branch vs linear 的 label coverage 是否达到 G4A 要求。
- 哪些 slices 可以进入 G4A primary teacher dataset。
- 哪些 slices 必须排除或作为 auxiliary repair labels。
- 下一步是 G4A，还是继续 G3d/G3b 修 event semantics。

判定标准：
如果 wait/reroute-aware Legacy replay planned_count >= 115/144，post_shield_conflicts = 0，branch effective coverage >= 0.75，则允许建议进入 G4A pilot dataset。否则建议继续修 mask/shield/event horizon。任何 post_shield_conflicts > 0 或 legacy Java 被修改都必须 hard stop。

运行：
python scripts/eval/run_g3d_legacy_teacher_wait_horizon_audit.py
python -m py_compile scripts/eval/run_g3d_legacy_teacher_wait_horizon_audit.py
python -m pytest
git diff --check

更新 README.md 和 docs/codex-worklog.md。所有负结果必须保留。不要把本轮诊断写成 learning success claim。
```

---

## 10. 给 Codex 的短 prompt

```text
继续 czr005。本轮做 G3d Legacy-A* Teacher Wait/Horizon Audit。G3c 证明 Legacy-A* teacher candidate recall=1.000、safe recall=0.610，高于 SIPP 0.319，但 forced replay only 78/144 且有 614 blocked/unavailable slices。不要训练模型，不要进 G4A，不要改 legacy Java。实现 wait-until-safe、jump-to-earliest-safe-time、reroute-from-current、capacity/merge diagnostic ablation、hybrid repair label audit。输出 g3d 报告、blocked ledger、earliest-safe labels、replay variant summary、G4A eligible slice manifest。若 wait/reroute-aware replay >=115/144 且无冲突，再建议 G4A；否则继续修 mask/horizon。
```
