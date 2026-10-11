# 第五轮实际资源与失败账

只读已落盘记录；实际耗时与预算分开。完整值只对明确的计量区间成立，整个第五轮CPU仍不完全可知。已知CPU可按互不重叠的区间相加；并发壁钟不得相加。

| invocation | state | recorded complete CPU(s) | extra lower bound(s) | unknown components | individual wall(s) |
|---|---|---:|---:|---:|---:|
| empty pilot 28 | complete | 120.890625 | 0.000000 | 0 | 23.675 |
| empty full 252 | complete | 1836.171875 | 0.000000 | 0 | 323.063 |
| factorial first preflight failure | failed_preflight | unknown | 0.000000 | 1 | unknown |
| factorial aborted artifact-comparison run | aborted | unknown | 239.375000 | 1 | unknown |
| factorial separate default replay diagnostic | complete | 4.390625 | 0.000000 | 1 | 4.465 |
| factorial full rerun 144 | complete | 1140.968750 | 0.000000 | 0 | 259.954 |
| public scenario pilot 16 | complete | 389.000000 | 0.000000 | 0 | 132.908 |
| public scenario full 144 | complete | 5694.921875 | 0.000000 | 0 | 1073.826 |
| network initial interrupted pilot | aborted | 73.078125 | 343.937500 | 1 | unknown |
| network corrected pilot 12 | complete | 219.750000 | 0.000000 | 0 | 101.880 |
| network full 2176 requests | complete | 20276.765625 | 0.000000 | 0 | 3519.235 |
| network opportunity census | complete | 77.375000 | 0.000000 | 0 | 38.716 |
| nominal first collection and denominator preflight | failed_preflight_after_collection | 106.796875 | 0.000000 | 1 | unknown |
| nominal repaired collection reuse | reused_artifact | 0.000000 | 0.000000 | 1 | unknown |
| nominal pilot 12 | complete | 159.890625 | 0.000000 | 0 | 32.584 |
| nominal full 693 | complete | 8863.203125 | 0.000000 | 0 | 1571.996 |
| regression suite 700 | complete | 94.515625 | 0.000000 | 1 | 98.988 |
| regression suite 717 | complete | 110.750000 | 0.000000 | 1 | 136.615 |
| two post-717 injected failure tests | complete | unknown | 0.000000 | 1 | unknown |
| empty authoring integration smoke | complete | 0.796875 | 0.000000 | 1 | unknown |
| early authoring and focused tests | complete | unknown | 0.000000 | 1 | unknown |
| phase4_w3_empty_factorial_analysis_20261010/analysis.json | complete | unknown | 0.000000 | 1 | unknown |
| phase4_w3_empty_improvement_analysis_20261010/analysis.json | complete | unknown | 0.000000 | 1 | unknown |
| phase4_w3_empty_scenarios_analysis_20261010/analysis.json | complete | 7.437500 | 0.000000 | 0 | 7.501 |
| phase4_w3_empty_scenarios_pilot_analysis_v2_20261010/analysis.json | complete | 1.562500 | 0.000000 | 0 | 1.736 |
| phase4_w3_round5_independent_review_20261010/empty_final_audit.json | complete | 3.093750 | 0.000000 | 0 | 3.186 |
| phase4_w3_round5_independent_review_20261010/empty_pilot_audit.json | complete | 0.515625 | 0.000000 | 0 | 0.623 |
| phase4_w3_round5_independent_review_20261010/final_validation_supplement_binding.json | complete | unknown | 0.000000 | 1 | unknown |
| phase4_w3_round5_independent_review_20261010/full_cycle_analysis_comparison.json | complete | 49.859375 | 0.000000 | 0 | 52.107 |
| phase4_w3_round5_independent_review_20261010/full_cycle_final_audit.json | complete | 143.109375 | 0.000000 | 0 | 147.743 |
| phase4_w3_round5_independent_review_20261010/full_cycle_pilot_audit.json | complete | 18.203125 | 0.000000 | 0 | 18.473 |
| phase4_w3_round5_independent_review_20261010/full_cycle_pilot_search_audit.json | complete | 16.718750 | 0.000000 | 0 | 16.949 |
| phase4_w3_round5_independent_review_20261010/initial_review.json | complete | unknown | 0.000000 | 1 | unknown |
| phase4_w3_round5_independent_review_20261010/nominal_checkpoint_binding_audit.json | complete | 23.734375 | 0.000000 | 0 | 24.105 |
| phase4_w3_round5_independent_review_20261010/scenarios_final_audit.json | complete | 6.218750 | 0.000000 | 0 | 6.346 |
| phase4_w3_round5_independent_review_20261010/scenarios_pilot_audit.json | complete | 1.765625 | 0.000000 | 0 | 1.868 |
| phase4_w3_same_zone_supply_analysis_20261010/analysis.json | complete | 0.046875 | 0.000000 | 0 | 0.046 |
| phase4_w3_network_nominal_analysis_20261010/audit_and_values.json | complete | 56.953125 | 0.000000 | 0 | 57.743 |
| phase4_w3_network_nominal_analysis_20261010/feature_coverage.json | complete | 3.453125 | 0.000000 | 0 | 3.752 |
| phase4_w3_network_nominal_analysis_20261010/mechanisms.json | complete | 1.515625 | 0.000000 | 0 | 1.531 |
| phase4_w3_empty_scenario_mechanisms_20261010/analysis.json | complete | 2.656250 | 0.000000 | 0 | 2.654 |
| phase4_w3_empty_scenario_mechanisms_20261010/shared_tick_evidence.json | complete | 0.140625 | 0.000000 | 0 | 0.138 |
| phase4_w3_network_full_cycle_analysis_20261010/summary.json | complete | 53.015625 | 0.000000 | 0 | 54.739 |
| all_configurations/manifest.json | complete | 1.546875 | 0.000000 | 0 | 1.645 |
| other unmetered development and analysis | complete | unknown | 0.000000 | 1 | unknown |
| previous resource ledger generation preview | complete | 0.375000 | 0.000000 | 0 | 0.403 |

已完整计量区间的CPU小计：39561.187500s；另外可恢复的CPU下界：583.312500s；两者合计的已知工作下界：40144.500000s。此数不含尚未完成/未知区间，也不含本汇总器自身0.437500s的已记录计算。禁止称为第五轮完整总CPU。

待完成：无主批次待完成。本次绑定44份证据，变化0份。

父进程与worker分别保留；已含在worker内的branch/collection CPU不再次加入。nominal首采集复制到repaired目录仅记一次；12pilot与full693实际独立运行，身份相同不代表复用。full-cycle memo alias和SAA重复情景请求保留请求权重，但不算新增物理分支。

700与717是两次独立全套验证；新增2例在717完成后单独运行，保留717+2边界。验证计量为pytest宿主CPU，子进程CPU未包括；旧失败试验的失配记录与中断工作不会零填。

所有路径、字段、计量范围、失败原因、重复计数排除规则与SHA见ledger.json。各行wall只属于其运行，不提供跨并发相加的总wall。
