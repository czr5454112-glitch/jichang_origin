# 第六轮资源与失败账

各数只代表明确计量区间；已知 CPU 合计是整个第六轮的下界。未知值不填零，预算上限不当耗时，并发 wall 不相加。

| 独立调用 | 状态 | 已记录 CPU(s) | 未知分量 | 本调用 wall(s) |
|---|---|---:|---:|---:|
| prepare_initial | complete | 0.718750 | 0 | 0.744043 |
| prepare_repaired | complete | 0.734375 | 0 | 0.775581 |
| initial_mechanism6 | complete | 143.234375 | 0 | 50.259562 |
| repaired_mechanism6 | complete | 139.718750 | 0 | 49.929853 |
| nominal_pilot9 | complete | 384.562500 | 0 | 134.148171 |
| formal81 | complete | 3482.109375 | 0 | 1197.251079 |
| author_authoring_initial.json | failed_test_collection | 2.078125 | 0 | 2.183978 |
| author_authoring_path_repaired.json | complete | 1.265625 | 0 | 1.309750 |
| author_freeze.json | complete | 0.000000 | 0 | 0.005663 |
| review_initial9 | complete | 0.015625 | 1 | 1.324329 |
| review_tests_controller_initial_validation.json | complete | 0.859375 | 0 | 0.909993 |
| review_tests_independent_focused_validation.json | failed_test_fixture | 2.953125 | 0 | 3.172311 |
| review_tests_independent_focused_repaired_validation.json | complete | 1.359375 | 0 | 1.415424 |
| review_tests_full_validation/result.json | complete | 70.109375 | 0 | 72.744987 |
| repair_test_attempt_1 | failed_test_fixture | unknown | 1 | 3.380893 |
| repair_test_attempt_2 | complete | unknown | 1 | 2.626375 |
| early_helper6_1 | complete | unknown | 1 | 2.421439 |
| early_helper6_2 | complete | unknown | 1 | 2.331369 |
| unmetered_auxiliary | complete | unknown | 1 | unknown |
| review_final_comparison_premature | failed_analysis_missing_file | unknown | 1 | 1.103697 |
| analysis:phase4_w3_round6_analysis_census_check_20261010\analysis.json | complete | 17.531250 | 0 | 17.714349 |
| analysis:phase4_w3_round6_analysis_initial_20261010\analysis.json | complete | 5.531250 | 0 | 5.785643 |
| analysis:phase4_w3_round6_final_analysis_20261010\analysis.json | complete | 158.796875 | 0 | 162.774671 |
| analysis:phase4_w3_round6_independent_review_20261010\final_analysis_comparison.json | complete | 0.000000 | 0 | 0.014986 |
| analysis:phase4_w3_round6_independent_review_20261010\formal_artifact_audit.json | complete | 129.156250 | 0 | 132.398914 |
| analysis:phase4_w3_round6_independent_review_20261010\mechanism_initial_audit.json | complete | 9.234375 | 0 | 9.527285 |
| analysis:phase4_w3_round6_independent_review_20261010\mechanism_repaired_audit.json | complete | 9.421875 | 0 | 9.586080 |
| analysis:phase4_w3_round6_independent_review_20261010\nominal_observation_overlap.json | complete | 16.078125 | 0 | 16.470550 |
| analysis:phase4_w3_round6_independent_review_20261010\nominal_pilot_audit.json | complete | 19.156250 | 0 | 19.630530 |
| analysis:phase4_w3_round6_pilot_analysis_20261010\analysis.json | complete | 23.765625 | 0 | 24.216171 |
| analysis:phase4_w3_round6_visuals_20261010\metadata.json | complete | 0.890625 | 0 | 0.891051 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\chain_evidence.json | complete | 0.031250 | 0 | 0.033327 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\formal_chain_evidence.json | complete | 0.031250 | 0 | 0.027987 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\formal_tradeoffs.json | complete | 7.203125 | 0 | 7.624866 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\full\analysis.json | complete | 228.421875 | 0 | 234.769512 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\initial_repaired_consistency.json | complete | 30.484375 | 0 | 31.081931 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\mechanism\analysis.json | complete | 20.250000 | 0 | 20.976373 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\nominal_pilot\analysis.json | complete | 45.234375 | 0 | 46.254593 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\repaired_mechanism\analysis.json | complete | 24.343750 | 0 | 24.898791 |
| analysis:phase4_w3_same_zone_supply_mechanisms_20261010\service_regressions.json | complete | 3.765625 | 0 | 3.853394 |
| analysis:phase4_w3_same_zone_supply_repair_diagnostic_20261010\diagnosis.json | complete | 2.390625 | 0 | 2.439441 |

互不重叠的已知 CPU 区间合计 **4981.437500 秒**；这是下界，不能称完整总 CPU。汇总器自身另计 0.265625 秒，未加入上述合计。

初始 6 格、修复后 6 格、9 pilot 与正式 81 均实际独立运行；即使身份重复也没有跨批复用。case invocation 包含 cycle，777 总时钟包含 test 子区间，均只加最外层已记区间。初始旧策略两格的 cache tuple/list 误报与修复、两次测试 fixture 问题、各次独立审计均保留。

old64 与 new32+32 只有候选查询数上限相同。新方法额外 guard 工作不在 CASE_BUDGET.search_work 内；逐例 queries、search_work、guard_work、CPU 与触顶信息另列于 JSON 的 nonadditive_budget_detail。

777 全套在比较器修复前完成；后来 11 项为独立受影响回归，不能写成 779 全套。早期 9 项 guard 测试只记父 CPU，pytest 子 CPU 未测；tool wall 不代替 CPU。

绑定 39 份证据，变化 0，检查失败 0。待完成批次：无。

第五轮 same_zone_supply_analysis 设计诊断已经入第五轮账，未重复加入。所有字段、范围、来源 SHA 与额外未计量工作见 ledger.json。
