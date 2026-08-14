# G4IRSF23 最终联合决策

Status: `COMPLETE_LOCAL_ACTION_SUPPORT_NO_GO`. Final label: `TESTED_SEAM_LOCAL_ACTION_CEILING`.

Source, precursor Route Formal 2048, and the preregistered externality neighborhood all returned complete compact no-support labels. This ceiling is limited to the tested Source/precursor/externality seams, not node52 or one-step local control in general.

当前报告只汇总 compact evidence；它不会启动仿真。`PENDING` 表示仍需证据；`NOT_TRIGGERED_BY_*` 表示上游门已明确关闭该阶段。两者都不能被解释为性能通过。

## Claim boundary

- Paper Tables 5.2-5.5 are paper-reported references, not local reproductions.
- The original IoT-DRPA/HCA* 1x result is parsed historical evidence, not a fresh Java rerun; HCA* 2x and 4x remain N/A.
- Processed-attempt, Java-release, and original-entry TTH are separate denominators; cross-denominator winner claims are forbidden.
- F2 pass-time-anchored TTH and the legacy HCA mislabeled field are diagnostics and are not substitutes for missing cells in the three-denominator panel.
- A real and safe local action is not by itself causal support, and causal support is not a closed-loop performance improvement.
- H_system benefit and current-bag direct cost remain separate; no individual-fairness claim follows from system benefit alone.
- No learned-policy, 1x/2x/4x, or fault-performance claim is allowed until its explicit stage has completed.
- Precursor Formal covers 2,048 H_bag groups but only 256 sparse reused H_system groups; 1,792 are H_bag-only and no new H_system group is implied.

## 两个 baseline 的直接事实

### G4IRSF13 F2 frozen — 1x committed control

| Item | Value |
|---|---:|
| Evidence status | `COMMITTED_FROZEN_CONTROL` |
| Raw bags / processed segments | 28506 / 43603 |
| Completed segments | 43603 |
| Complete raw bags / failed segments / conflicts / runtime full A* calls | 28506 / 0 / 0 / 0 |
| Raw original-entry TTH min / mean / max (min) | N/A / 41.514218718 / N/A |
| Raw original-entry TTH p95 / p99 (s) | 7349.348647500 / 10789.015763000 |
| Pass-time-anchored mean diagnostic (min) | 4.143217184 |

### Original centralized IoT-DRPA/HCA* — historical 1x

Evidence status: `HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT`; fresh Java rerun: `False`; scope: `1x / 2.5 m/s`.

| HCA* TTH field | Min (min) | Mean (min) | Max (min) | Meaning |
|---|---:|---:|---:|---|
| processed-segment-attempt | 3.133333330 | 3.967122710 | 5.983333330 | historical parsed denominator |
| Java-release | 3.133333330 | 5.197225150 | 24.316666670 | historical parsed denominator |
| legacy mislabeled field | 3.116848170 | 5.764936750 | 27.149625830 | diagnostic only |
| corrected raw original-entry | N/A | 43.135938280 | N/A | algebraically reconciled mean; range unavailable |

HCA* scale availability: 2x `N/A_NOT_IN_PAPER_PROTOCOL`; 4x `N/A_NOT_IN_PAPER_PROTOCOL`.
各行保留自己的 TTH 分母；legacy mislabeled 字段仅作诊断，不填补比较面板。

## 两个必需 baseline × 三个 TTH 分母

| TTH denominator | G4IRSF13 F2 frozen | Original IoT-DRPA/HCA* | Comparison status |
|---|---:|---:|---|
| processed_segment_attempt_time_tth | `NOT_REPORTED_FOR_F2` | 3.967122710 | `N/A_NOT_COMPARABLE` |
| java_release_time_tth | `NOT_REPORTED_FOR_F2` | 5.197225150 | `N/A_NOT_COMPARABLE` |
| original_entry_time_tth | 41.514218718 | 43.135938280 | `DENOMINATOR_ALIGNED_HISTORICAL_DIRECTION_ONLY` |

数值单位均为 min/complete raw bag。F2 pass-time-anchored diagnostic 为 4.143217184 min；历史 HCA mislabeled diagnostic 为 5.764936750 min。两者均不得填补上表缺失分母。

G23 closed-loop candidate metrics: `NOT_RUN_AFTER_SUPPORT_NO_GO`.

## Stage 状态

| Stage | Evidence | Decision |
|---|---|---|
| `23A_baseline_and_takeover` | `COMPLETE` | `DUAL_BASELINE_CONTRACT_FIXED` |
| `23B_exact_source_action` | `COMPLETE` | `VALIDATED` |
| `23C_source_pilot` | `COMPLETE` | `TARGETED_SOURCE_NO_SUPPORT` |
| `23D_source_formal` | `NOT_TRIGGERED` | `NOT_TRIGGERED_BY_SOURCE_PILOT_CONTINUATION_GATE` |
| `23E_feature_reduction` | `NOT_TRIGGERED` | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` |
| `23F_selector` | `NOT_TRIGGERED` | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` |
| `23G_offline_gate` | `NOT_TRIGGERED` | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` |
| `23H_native_closed_loop` | `NOT_TRIGGERED` | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` |
| `23I_precursor_route` | `COMPLETE` | `NO_GO_PRECURSOR_FORMAL_SUPPORT` |
| `23J_externality_neighborhood` | `COMPLETE` | `NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT` |
| `23K_scale_and_fault` | `NOT_TRIGGERED` | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` |

## 23I Precursor 分层证据

| Layer | Evidence | Decision | H_bag groups | H_system groups | Scope |
|---|---|---|---:|---:|---|
| Pilot | `COMPLETE` | `NO_GO_PRECURSOR_PILOT_SUPPORT` | 512 | 256 | 512-group discovery/pilot |
| Formal | `COMPLETE` | `NO_GO_PRECURSOR_FORMAL_SUPPORT` | 2048 | 256 | sparse reused H_system; H_bag-only=1792; new H_system groups=0 |

Precursor Formal handoff: `COMPLETE` / `NO_GO_PRECURSOR_FORMAL_SUPPORT`. H_bag complete groups: `2048`; sparse reused H_system groups: `256`; H_bag-only groups: `1792`; new H_system groups: `0`. This is never described as 2,048 system labels. Formal fair-promotion gate: `6` / `16`; block-8 Formal support gate: `0` / `4`.
Tiny-MLP unlock is a separate gate: `False`; Formal fair positives `6` / `40`; held-out fair positives `0` / `12`; stable nonlinear regret evidence `NOT_RUN`.
Execution provenance: published precursor raw pairs used a runtime-only ordinary-baseline reuse shortcut whose checkpoint continuation was equivalence-audited; the shipped runtime keeps ordinary G22 per-target baseline semantics.

## Source component decomposition

全部是 treatment − baseline，单位 s/complete raw bag。该表是因果 H_system 描述值，不是未运行的 closed-loop candidate 结果。

| Scope | Component | Count | Min | Mean | Median | Max |
|---|---|---:|---:|---:|---:|---:|
| All | Source wait | 176 | -0.000056988 | -0.000000892 | +0.000000018 | +0.000001649 |
| All | Network time | 176 | -0.004780502 | -0.000081247 | -0.000000018 | +0.000007753 |
| All | Scheduled pre-release wait | 176 | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| Block 7 | Source wait | 128 | -0.000056988 | -0.000001316 | +0.000000018 | +0.000000035 |
| Block 7 | Network time | 128 | -0.004780502 | -0.000112093 | -0.000000018 | +0.000000105 |
| Block 7 | Scheduled pre-release wait | 128 | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| Block 8 | Source wait | 48 | +0.000000018 | +0.000000238 | +0.000000018 | +0.000001649 |
| Block 8 | Network time | 48 | -0.000001649 | +0.000001011 | -0.000000018 | +0.000007753 |
| Block 8 | Scheduled pre-release wait | 48 | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |

## Precursor Pilot H_system effect/cost distribution

完整 panel 为 512 actions / 256 groups；fair promotions 为 6 actions / 6 groups。全部 delta 是 treatment − baseline；current-bag cost/headroom 是单 bag 秒数，其余 mean/source/network 是 s/complete raw bag。

| Metric | Panel min | mean | median | max | Promotion min | mean | median | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mean TTH delta | -8.530958395 | +0.979877288 | +0.000021925 | +23.860560058 | -8.530958395 | -3.609646215 | -3.885528485 | -0.016610538 |
| Source-wait mean delta | -3.871171859 | +0.872872707 | +0.000000000 | +19.157225672 | -3.871171859 | -1.988924115 | -2.517682681 | +0.000000000 |
| Network-time mean delta | -6.522600505 | +0.107004582 | +0.000021925 | +4.703334386 | -6.522600505 | -1.620722099 | -0.858521013 | -0.016610538 |
| P95 delta | -54.432500000 | +6.376816406 | +0.000000000 | +150.747500000 | -54.432500000 | -26.384166667 | -31.782500000 | +0.000000000 |
| P99 delta | -9.378500000 | +1.347072266 | +0.000000000 | +24.893500000 | -9.378500000 | -5.785083333 | -8.444000000 | +0.000000000 |
| Max delta (diagnostic) | -95.800000000 | +12.210058594 | +0.000000000 | +532.000000000 | +0.000000000 | +86.266666667 | +68.600000000 | +238.000000000 |
| Current-bag cost | +0.150000000 | +249.969238281 | +38.425000000 | +5344.400000000 | +112.000000000 | +753.050000000 | +808.425000000 | +1495.400000000 |
| Pre-action deadline headroom | +3632.169260706 | +8160.879495081 | +7398.444260706 | +14176.419260706 | +4968.629260706 | +6019.839260706 | +5721.749260706 | +8263.419260706 |

Externality fairness handoff: `COMPLETE` / `NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT`. Execution attempts/identity coverage: `256`/`256`; applied/guard-abstain: `243`/`13`; action-changing rate: `0.94921875`; guard reasons: `{'NOT_APPLICABLE_ACTION_PRECONDITION_FAILED': 13}`. Effect/fairness/signature use applied action-changing pairs only. Fair system-beneficial groups: `17` across `10` cells; system-beneficial but costly: `15`; system-beneficial but unfair: `0`; individual fairness evaluated: `True`; contract: `FROZEN_PRE_ACTION_DEADLINE_HEADROOM_AND_TREATMENT_CURRENT_BAG_OUTCOME`. Selection scope: `ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY`; bins: `['q16_23', 'q24_31', 'q32_plus']`; two-hop pressure used: `False`. System tail hard gate: `p95/p99 <= +0.001 s`; raw-bag max delta diagnostic only (not a hard gate): `count=243, min=-165.8000000000029, mean=45.610493827158095, median=0.0, max=596.0 s`. Held-out local signature scope: `SYSTEM_BENEFICIAL_ONLY`; individual fairness used by held-out signature: `False`. Fair cell coverage remains a separate continuation gate.

## 规范 30 问

状态只有三类语义：`COMPLETE`（compact evidence 已直接回答）、`NOT_TRIGGERED_BY_<gate>`（上游门已关闭）、`PENDING`（仍需证据）。

| # | 问题 | 状态 | 直接答案 | Evidence |
|---:|---|---|---|---|
| 1 | PR #7 与 G23 CI 是否绿色？ | `PENDING` | 冻结方案记录 PR #7 的 GitHub Actions Run #69 为 success；本次 G23 的 CI 成功证据尚未写入 compact handoff，状态保持 PENDING，推送后以 GitHub check 为准。 | GitHub handoff |
| 2 | 新 Source HOLD 与旧 I1/A1/A2 有什么本质区别？ | `COMPLETE` | G23 只在 storage_out/node52 对同一队首跳过一次自然服务机会，随后强制回 A0；不换 bag、不重排 top-K、不改完整路线。I1 换源队列服务顺序，旧 A1/A2 是广泛压力门且可产生重复 retry。 | 23B/23C |
| 3 | block 7 有多少 exact applicable groups？ | `COMPLETE` | Source H_system exact groups: 128; block 8: 48; total exact interventions: 256. | 23C |
| 4 | block 8 是否复现方向？ | `COMPLETE` | 否。block 8 promotion-eligible fair positives = 0；Source 报告未复现 block 7 的弱诊断方向。 | 23C |
| 5 | HOLD 给当前 bag 增加多少时间？ | `COMPLETE` | treatment-baseline current-bag cost: mean +0.000085227s, max +0.001000000s；上限为一次 0.001s 自然机会。 | 23C |
| 6 | HOLD 对 57,012-bag mean 有多少影响？ | `COMPLETE` | 176 个完整 H_system 标签的 treatment-baseline mean-effect panel 均值为 -0.000082139s/complete raw bag，范围 [-0.004837473, +0.000007770]；效应低于可用门槛。 | 23C |
| 7 | p95/p99 是否同向？ | `COMPLETE` | p95 mean/min/max = +0.000000000/+0.000000000/+0.000000000s；p99 = +0.000000000/+0.000000000/+0.000000000s，均未显示同向收益。 | 23C |
| 8 | 有多少 FAIR_SYSTEM_BENEFICIAL？ | `COMPLETE` | 诊断标签 3，但 promotion-eligible usable/strong fair positives = 0；不能把弱诊断标签当作晋级正例。 | 23C |
| 9 | 有多少 SYSTEM_BENEFICIAL_BUT_UNFAIR？ | `COMPLETE` | 0 | 23C |
| 10 | 正例跨多少压力区间和时间区间？ | `COMPLETE` | promotion-eligible positives = 0，故可晋级压力/时间覆盖均为 0；仅有 2 个弱诊断 strata，时间标记 ['t28']，不足以训练。 | 23C |
| 11 | 哪些局部特征最有用？ | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` | Source causal-support gate 未通过，因此没有制造 feature ranking、rule/linear/tiny MLP、held-out precision 或线上模型 HOLD 数字。 | 23E |
| 12 | 二跳信息是否真的必要？ | `COMPLETE` | 二跳没有用于筛选、分层或 held-out signature；一跳 signature pass=False，因此本轮没有证据证明二跳必要。 | 23J |
| 13 | 规则、线性、tiny MLP 谁最好？ | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` | Source causal-support gate 未通过，因此没有制造 feature ranking、rule/linear/tiny MLP、held-out precision 或线上模型 HOLD 数字。 | 23F |
| 14 | held-out precision 和 harmful rate 是多少？ | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` | Source causal-support gate 未通过，因此没有制造 feature ranking、rule/linear/tiny MLP、held-out precision 或线上模型 HOLD 数字。 | 23F/23G |
| 15 | 模型实际提交多少 HOLD？ | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` | Source causal-support gate 未通过，因此没有制造 feature ranking、rule/linear/tiny MLP、held-out precision 或线上模型 HOLD 数字。 | 23H |
| 16 | 有多少 HOLD 被公平约束拒绝？ | `NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE` | Source causal-support gate 未通过，因此没有制造 feature ranking、rule/linear/tiny MLP、held-out precision 或线上模型 HOLD 数字。 | 23H |
| 17 | 是否出现重复 HOLD？ | `COMPLETE` | 没有；256 个 intervention 中 repeated HOLD groups = 0，且每次 HOLD 后强制回 A0。 | 23B/23C |
| 18 | 1× 是否保持？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23H/23K |
| 19 | 2× mean/p95/p99 如何？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23H/23K |
| 20 | Source wait、network time 如何重新分配？ | `COMPLETE` | 因果 H_system 描述值（非闭环候选）：source wait -0.000000892s/bag，network -0.000081247s/bag，scheduled pre-release wait +0.000000000s/bag；总效应极小且不跨 block 复现。 | 23C |
| 21 | 关闭多少 v2-safe gap？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23H/23K |
| 22 | 是否达到 Direction/Gap-10/25/50？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23H/23K |
| 23 | Source 不通过时，前驱 Route 是否有正例？ | `COMPLETE` | Pilot mutations=512/512，fair promotions=6（block8=0），H_system actions=512, mean=+0.979877s, p95=+6.376816s, p99=+1.347072s, current-bag cost mean +249.969s / max +5344.400s, fair promotions=6/6, mean effect -3.609646s, cost mean/max +753.050/+1495.400s；Formal fair promotions=6/16（block8=0/4），H_system actions=512, mean=+0.979877s, p95=+6.376816s, p99=+1.347072s, current-bag cost mean +249.969s / max +5344.400s, fair promotions=6/6, mean effect -3.609646s, cost mean/max +753.050/+1495.400s，Formal decision=NO_GO_PRECURSOR_FORMAL_SUPPORT。tiny MLP unlock=False（Formal fair positives=6/40，held-out=0/12，stable nonlinear regret=NOT_RUN）。 | 23I Pilot + Formal |
| 24 | 前驱 Route 改的是哪个真实上游接口？ | `COMPLETE` | 改 storage_out/node52 之前、对应 storage_in 行李最近一次真实多动作 Route 接口的一步 NEXT_EDGE/WAIT；后续立即回 S4/J2/E2，不增加 planner。 | 23I |
| 25 | G22 两个 cohort-relief 动作是否可泛化？ | `COMPLETE` | 256-group neighborhood: fair system-beneficial=17 across 10 cells; continuation=False。这就是对 G22 cohort-relief 可泛化性的限定答案。 | 23J |
| 26 | 4× 60 秒是否改善？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23K |
| 27 | 是否解锁 180 秒或 full？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23K |
| 28 | 单实例并行是否有必要？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23K |
| 29 | 故障是否安全？ | `NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE` | 无 causally supported G23 candidate，故未触发闭环/规模/故障 claim。 | 23K |
| 30 | 下一阶段最窄、最有价值的问题是什么？ | `COMPLETE` | 停止扩张 node52 HOLD/Route 模型；下一窄问题仅应是更早一个真实 merge-token 接口的一步 MOVE/WAIT 是否有因果支持。 | final decision |

## 原论文对比面板

论文：[Internet-of-Things-augmented dynamic route planning approach to the airport baggage handling system](https://doi.org/10.1016/j.cie.2022.108802)（DOI `10.1016/j.cie.2022.108802`）。以下均为 `PAPER_REPORTED_ONLY`，并非本仓库重跑结果。

### Table 5.2 — speed sweep

| Speed (m/s) | Min (min) | Avg (min) | Max (min) |
|---:|---:|---:|---:|
| 1.5 | 5.10 | 6.44 | 9.68 |
| 2.0 | 3.87 | 4.93 | 7.37 |
| 2.5 | 3.13 | 3.96 | 5.98 |
| 3.0 | 2.63 | 3.37 | 5.05 |

### Table 5.3 — IoT-DRPA/HCA* vs dispersed heuristic

| Method | Min | Avg | Max | Unit |
|---|---:|---:|---:|---|
| dispersed_heuristic | 3.56 | 4.43 | 8.62 | minutes |
| iot_drpa_hca_star | 3.13 | 3.96 | 5.98 | minutes |
| improvement | 12.10 | 10.60 | 30.60 | percent |

### Table 5.4 — dynamic IoT-DRPA vs static LRA*

| Speed (m/s) | Deviation | Dynamic | Static | Improvement |
|---:|---:|---:|---:|---:|
| 1.5 | 10% | 6.45 | 6.59 | 2.12% |
| 1.5 | 20% | 6.67 | 6.86 | 2.77% |
| 1.5 | 30% | 6.91 | 7.11 | 2.81% |
| 2.0 | 10% | 4.92 | 5.07 | 2.96% |
| 2.0 | 20% | 5.16 | 5.36 | 3.73% |
| 2.0 | 30% | 5.42 | 5.62 | 3.56% |
| 2.5 | 10% | 3.99 | 4.19 | 4.77% |
| 2.5 | 20% | 4.25 | 4.46 | 4.71% |
| 2.5 | 30% | 4.49 | 4.72 | 4.87% |
| 3.0 | 10% | 3.39 | 3.56 | 4.78% |
| 3.0 | 20% | 3.51 | 3.72 | 5.65% |
| 3.0 | 30% | 3.64 | 3.87 | 5.94% |

### Table 5.5 — 16 fault scenarios

| Failed arc(s) | Affected conveyors | Baggage success rate |
|---|---:|---:|
| 1 | 1 | 1.00 |
| 2 | 7 | 0.88 |
| 3 | 5 | 1.00 |
| 4 | 15 | 0.95 |
| 5 | 24 | 0.97 |
| 6 | 7 | 0.96 |
| 7 | 1 | 1.00 |
| 8 | 7 | 0.99 |
| 1,7 | 2 | 1.00 |
| 2,4 | 22 | 0.76 |
| 3,5 | 36 | 0.66 |
| 4,5 | 54 | 0.00 |
| 5,7 | 12 | 0.48 |
| 2,4,6 | 36 | 0.26 |
| 3,5,8 | 51 | 0.05 |
| 4,6,7 | 30 | 0.26 |

## 当前可直接回答的结论

- Candidate promotion authorized: `False`.
- Learned policy deployed: `False`.
- Closed-loop performance claim: `NOT_RUN`.
- HCA* 2x/4x: `N/A_NOT_IN_PAPER_PROTOCOL`.
