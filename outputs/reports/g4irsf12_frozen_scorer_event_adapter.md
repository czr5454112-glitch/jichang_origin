# G4IRSF12-E Frozen G4E Event Adapter

**Status: `OOD_DIAGNOSTIC_ONLY_NOT_CLOSED_LOOP`.**

This stage supplies a legal-local Python adapter and an offline scorer-isolation diagnostic. It is **not** the required closed-loop S0-S4 A/B: the trace cannot recreate counterfactual queues, reservations, completions, throughput, or THT.

## Frozen identities

- G4E model: `artifacts/models/g4e_risk_calibrated_policy.json` / `4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca`
- Canonical map raw SHA-256: `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`
- Canonical map semantic SHA-256: `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63`
- Decision trace: `artifacts/datasets/g4irsf11_decision_trace_sample.jsonl` / `bc22ae4d618eb193c3a7342eba04315a85d5940833ba91df95a3b90da432ca4f`
- Trace scope: **9,397** decisions and **14,544** candidate scores from the committed G4IRSF11 diagnostic sample, not all 43,603 original input segments.

## Adapter boundary

The adapter verifies the exact 22-feature order and 22x22 frozen MLP. S1 retains the frozen `w1/b1/w2/b2`; S2 changes only the two absolute node-ID inputs to zero. Both are OOD diagnostics.

The source bundle contains **16** learned hardcase rules and identifies its selected candidate as `hardcase_rules`. Those rules are quarantined: they are training-derived absolute current/goal/candidate tuple lookups, not a portable event feature with a 22-dimensional lineage. The training-only historical-risk feature is also explicitly zero. The portable risk diagnostic uses only the frozen margin threshold and the locally reconstructed bottleneck; the physical safety shield remains external.

Metadata, recorded model outputs, the recorded selected action, and outcome data are not model inputs. Changing a metadata scenario label cannot change a feature vector. Unknown candidate features and teacher/future/post-hoc keys fail closed.

## Complete 22-feature lineage

| # | Frozen feature | S1 resolution | S1 source/default | S2 change |
|---:|---|---|---|---|
| 1 | `candidate_shortest_time_to_goal_scaled` | EXACT_LEGAL_STATIC | `candidate_records[].features.static_potential` | same as S1 |
| 2 | `candidate_travel_time_scaled` | EXACT_LEGAL_STATIC | `candidate_records[].features.travel_time` | same as S1 |
| 3 | `candidate_service_time_scaled` | EXACT_LEGAL_STATIC | `canonical_map.nodes[candidate].service_time` | same as S1 |
| 4 | `candidate_node_type_scaled` | EXACT_LEGAL_STATIC | `canonical_map.nodes[candidate].node_type` | same as S1 |
| 5 | `candidate_faulted` | LEGAL_EVENT_OBSERVATION | `candidate_records[].features.advertised_fault` | same as S1 |
| 6 | `candidate_is_goal` | EXACT_LEGAL_STATIC | `candidate_records[].next_node == goal_node` | same as S1 |
| 7 | `time_slack_scaled` | EXPLICIT_DEFAULT_MISSING | default `0.0` | same as S1 |
| 8 | `current_node_scaled` | EXACT_LEGAL_EVENT_STATE | `current_node` | EXPLICIT_DEFAULT_ID_ABLATION / default `0.0` |
| 9 | `goal_node_scaled` | EXACT_LEGAL_STATIC | `goal_node` | EXPLICIT_DEFAULT_ID_ABLATION / default `0.0` |
| 10 | `out_degree_scaled` | EXACT_LEGAL_STATIC | `len(candidate_next_nodes)` | same as S1 |
| 11 | `is_branch_node` | EXACT_LEGAL_STATIC | `len(candidate_next_nodes) > 1` | same as S1 |
| 12 | `local_node_pressure_scaled` | EXPLICIT_DEFAULT_NON_EQUIVALENT | default `0.0` | same as S1 |
| 13 | `candidate_node_pressure_scaled` | EXPLICIT_DEFAULT_NON_EQUIVALENT | default `0.0` | same as S1 |
| 14 | `candidate_downstream_node_pressure_2hop_scaled` | EXPLICIT_DEFAULT_NON_EQUIVALENT | default `0.0` | same as S1 |
| 15 | `candidate_downstream_node_pressure_3hop_scaled` | EXPLICIT_DEFAULT_MISSING | default `0.0` | same as S1 |
| 16 | `candidate_static_remaining_hops_to_goal_scaled` | EXACT_LEGAL_STATIC_RECONSTRUCTION | `canonical_map directed adjacency BFS` | same as S1 |
| 17 | `candidate_static_second_best_gap_scaled` | EXACT_LEGAL_STATIC_RECONSTRUCTION | `(travel_time + static_potential) - minimum candidate value` | same as S1 |
| 18 | `candidate_bottleneck_score_scaled` | LEGAL_LOCAL_RECONSTRUCTION | `canonical candidate out-degree + advertised_fault` | same as S1 |
| 19 | `candidate_goal_direction_score_scaled` | EXACT_LEGAL_STATIC_RECONSTRUCTION | `canonical current potential - candidate static_potential` | same as S1 |
| 20 | `candidate_historical_risk_from_training_only_scaled` | EXPLICIT_DEFAULT_TRAINING_ONLY | default `0.0` | same as S1 |
| 21 | `source_retry_pressure_scaled` | EXPLICIT_DEFAULT_MISSING | default `0.0` | same as S1 |
| 22 | `unfinished_task_queue_size_near_current_source_scaled` | EXPLICIT_DEFAULT_MISSING | default `0.0` | same as S1 |

The pressure-related legacy fields are deliberately not populated from similarly named event queue fields. Reservation-overlap pressure and bounded queue summaries are not equivalent quantities. The detailed reasons are in `outputs/tables/g4irsf12_feature_lineage_event_adapter.csv`.

## Same-observation offline replay

| Scorer | Agreement with recorded model | Agreement with recorded action | Predicted candidate shield-allowed | Risk abstain |
|---|---:|---:|---:|---:|
| `S0_current_handwritten_static_score` | 100.000% | 94.881% | 94.881% | 5.119% |
| `S1_frozen_g4e_legal_local_adapter` | 98.734% | 93.615% | 94.520% | 3.544% |
| `S2_frozen_g4e_without_absolute_node_ids` | 98.734% | 93.615% | 94.520% | 3.544% |
| `S3_shortest_potential_only` | 99.617% | 94.498% | 94.509% | 0.000% |
| `S4_queue_aware_rule_only` | 99.851% | 94.732% | 94.732% | 0.000% |

S1 and S2 disagree on **0 / 9,397** recorded observations (0.000%). These are behavioral agreement statistics, not action accuracy and not evidence of improved completion.

## Missing closed-loop A/B and promotion boundary

The plan requires S0-S4 to run with identical resource semantics, queue discipline, and PIBT/pressure settings. That experiment was not executed in this Python-only adapter stage. Consequently, `outputs/tables/g4irsf12_scorer_isolation_ab.csv` leaves `completion_rate` and `original_entry_time_tth` blank for every scorer.

No S1/S2 result here may be promoted to a final model, and no policy-regression or resource/coordination attribution may be made until a controlled event-runtime closed-loop A/B is executed.
