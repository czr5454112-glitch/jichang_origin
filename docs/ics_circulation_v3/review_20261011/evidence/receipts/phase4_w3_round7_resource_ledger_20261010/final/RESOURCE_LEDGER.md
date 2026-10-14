# 第七轮资源与失败账

已记录互不重叠 CPU 区间合计 **15742.000000s**，属于本轮总耗时下界。未知分量 14；pending 0。

| 独立调用 | 状态 | 已记录 CPU(s) | 未知分量 | 本调用 wall(s) |
|---|---|---:|---:|---:|
| label_prepare | complete | 5.781250 | 0 | 5.914951699989615 |
| label_historical_prepare | complete | 5.609375 | 0 | 5.7415786999918055 |
| coverage_prepare | complete | 0.750000 | 0 | 0.7692453999770805 |
| shadow_repaired_prepare | complete | 30.656250 | 0 | 31.336806599982083 |
| shadow_selection | complete | 1.218750 | 0 | 1.2374141000036616 |
| terminal_screen_prepare | complete | 1.937500 | 0 | 1.9861244999920018 |
| terminal_screen_all2467_corpus | complete | 13.000000 | 0 | 13.24357229997986 |
| label_collection3 | complete | 147.734375 | 0 | 74.7222414999851 |
| label_normal5 | complete | 149.468750 | 0 | 43.507384399999864 |
| label_pilot16 | complete | 284.812500 | 0 | 51.93129440001212 |
| label_historical48 | complete | 1199.015625 | 0 | 214.6822947000037 |
| label_formal692 | complete | 10053.703125 | 0 | 1702.0977602999774 |
| coverage_collection27 | complete | 1008.875000 | 0 | 353.7654310000071 |
| coverage_pilot | complete | 6.218750 | 0 | 4.287794300005771 |
| coverage_formal | complete | 270.593750 | 0 | 94.03379659997881 |
| terminal_screen_pilot3 | complete | 110.171875 | 0 | 58.61366810000618 |
| terminal_screen_formal27 | complete | 842.546875 | 0 | 294.6061209999898 |
| label_author_1 | failed_tests | 未知 | 1 | 3.0135688 |
| label_author_2 | failed_tests | 未知 | 1 | 3.1613244 |
| label_author_3 | complete | 未知 | 1 | 3.8793846 |
| label_auxiliary_1 | complete | 未知 | 1 | 2.2813898 |
| label_auxiliary_2 | complete | 未知 | 1 | 2.2911678 |
| coverage_author_validation.json | failed | 1.906250 | 0 | 1.9706258000223897 |
| coverage_author_validation_repaired.json | complete | 1.281250 | 0 | 1.4056621999770869 |
| coverage_author_validation_recovery_freeze.json | complete | 1.656250 | 0 | 1.7036974999937229 |
| coverage_author_unmetered_1 | complete | 未知 | 1 | 1.4448135 |
| coverage_author_unmetered_2 | complete | 未知 | 1 | 2.1702418 |
| coverage_recovery_author_failed_test | failed_test | 未知 | 1 | 2.3564129 |
| query_probe_author | complete | 1.453125 | 0 | 1.4664381000038702 |
| terminal_author_validation.json | complete | 1.343750 | 0 | 1.4913347999972757 |
| terminal_author_validation_snapshot_bound.json | complete | 1.406250 | 0 | 1.4189489999844227 |
| terminal_author_unmetered_1 | complete | 未知 | 1 | 1.6555996 |
| terminal_author_unmetered_2 | complete | 未知 | 1 | 1.6326448 |
| terminal_author_unmetered_3 | complete | 未知 | 1 | 1.7993909 |
| terminal_author_unmetered_4 | complete | 未知 | 1 | 2.101779 |
| search_census_initial_failed | failed | 80.171875 | 0 | 81.69543449999765 |
| search_census_repaired | complete | 0.421875 | 0 | 0.4207635999773629 |
| immutable_observation_supplement3 | complete | 91.968750 | 0 | 47.68355019998853 |
| immutable_observation_author | complete | 1.218750 | 0 | 1.2413539999979548 |
| immutable_observation_author_initial_failure | failed_tests | 未知 | 1 | 2.1432736 |
| root_matched_value_analysis | complete | 213.640625 | 0 | 215.53421979999985 |
| analysis:phase4_w3_round7_independent_review_20261010\collection_artifact_audit.json | complete | 59.843750 | 0 | 61.23753809998743 |
| analysis:phase4_w3_round7_independent_review_20261010\focused_extended_validation.json | complete | 2.125000 | 0 | 2.348790700023528 |
| analysis:phase4_w3_round7_independent_review_20261010\focused_initial_validation.json | complete | 1.968750 | 0 | 2.154521999997087 |
| analysis:phase4_w3_round7_independent_review_20261010\full_artifact_audit_v2.json | complete | 188.156250 | 0 | 189.96469019999495 |
| analysis:phase4_w3_round7_independent_review_20261010\full_validation\result.json | complete | 111.171875 | 0 | 112.87721619999502 |
| analysis:phase4_w3_round7_independent_review_20261010\full_validation_terminal\result.json | complete | 101.921875 | 0 | 103.25358649998088 |
| analysis:phase4_w3_round7_independent_review_20261010\initial_binding.json | complete | 0.062500 | 0 | 0.06296670000301674 |
| analysis:phase4_w3_round7_independent_review_20261010\instant_observation_artifact_audit.json | complete | 7.593750 | 0 | 7.6719052999978885 |
| analysis:phase4_w3_round7_independent_review_20261010\normal_resume_artifact_audit.json | failed | 9.765625 | 0 | 9.912284499994712 |
| analysis:phase4_w3_round7_independent_review_20261010\normal_resume_artifact_audit_v2.json | complete | 9.812500 | 0 | 9.983799100009492 |
| analysis:phase4_w3_round7_independent_review_20261010\old12_artifact_audit_v2.json | complete | 35.140625 | 0 | 35.49808020002092 |
| analysis:phase4_w3_round7_independent_review_20261010\pilot_artifact_audit_v2.json | complete | 13.531250 | 0 | 13.667092700023204 |
| analysis:phase4_w3_round7_independent_review_20261010\query_coverage_formal_audit.json | complete | 63.218750 | 0 | 63.875842300010845 |
| analysis:phase4_w3_round7_independent_review_20261010\query_coverage_pilot_audit.json | complete | 208.015625 | 0 | 210.27590799998143 |
| analysis:phase4_w3_round7_independent_review_20261010\terminal_corpus_artifact_audit.json | complete | 62.656250 | 0 | 63.385857099987334 |
| analysis:phase4_w3_round7_independent_review_20261010\terminal_formal_artifact_audit.json | complete | 74.953125 | 0 | 76.31979750000755 |
| analysis:phase4_w3_round7_independent_review_20261010\terminal_pilot_artifact_audit.json | complete | 39.359375 | 0 | 39.72686809999868 |
| analysis:phase4_w3_round7_independent_review_20261010\terminal_screen_binding_validation.json | complete | 0.671875 | 0 | 0.715693200007081 |
| analysis:phase4_w3_round7_independent_review_20261010\terminal_screen_validation.json | complete | 0.671875 | 0 | 0.6868427000008523 |
| analysis:phase4_w3_round7_independent_review_20261010\value_aggregation_audit.json | complete | 25.859375 | 0 | 26.461243300000206 |
| analysis:phase4_w3_round7_query_coverage_analysis_20261010\analysis.json | complete | 1.843750 | 0 | 1.8855321999872103 |
| analysis:phase4_w3_round7_query_coverage_analysis_20261010\local_yield_trace.json | complete | 1.046875 | 0 | 1.063113100011833 |
| analysis:phase4_w3_round7_terminal_analysis_20261010\analysis.json | complete | 0.031250 | 0 | 0.03892459999769926 |
| analysis:phase4_w3_round7_value_analysis_20261010\historical_mechanisms\mechanisms.json | complete | 10.937500 | 0 | 11.096698399982415 |
| analysis:phase4_w3_round7_value_analysis_20261010\visuals\manifest.json | complete | 1.671875 | 0 | 1.764240399992559 |
| analysis:phase4_w3_same_zone_labels_20261010\independent_choice_check\result.json | complete | 150.500000 | 0 | 152.2221819999977 |
| analysis:phase4_w3_same_zone_labels_20261010\independent_choice_check\service_ties_result.json | complete | 30.890625 | 0 | 31.30329310000525 |
| analysis:phase4_w3_same_zone_labels_20261010\summary_authoring_receipt.json | complete | 0.015625 | 0 | 0.0287151999946218 |
| unmetered_auxiliary | complete | 未知 | 1 | None |

并发 wall 不相加；worker lifetime 内存峰值不相加为同时峰值；旧文件复用、label memo 与嵌套 cycle/query 时钟不冒充额外物理工作。

证据核验 79 项，失败 0；账本自身 CPU 0.515625s 另列且未加入上表。
