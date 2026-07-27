# G4IRSF13 Thesis Priority Extraction

Date: 2026-07-27

status: `SOURCE_EXTRACTION_COMPLETE`
implementation_claim: `DESIGN_INPUT_NOT_RUNTIME_PROMOTION`
thesis_sha256: `37e61b8e4d67e56c0fa14c43b230be965e200106704363f06b80a4e6a151e1aa`
map_raw_sha256: `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`
map_semantic_sha256: `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63`
task_raw_sha256: `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f`

## Source boundary

The user-supplied primary PDF was visually reviewed after Poppler rendering. File pages 33, 34, 38, 39, 40, and 46 (printed pages 19, 20, 24, 25, 26, and 32) support the lifecycle, BTI/DDI, fault/repair, formula, and Table 5.5 facts below. The byte identity above prevents an unlabelled source substitution.

The legacy Java and `arc.txt` were read-only inputs. Their recorded hashes are: `{"arc.txt": "1348553fc9a7f0bb6aaa3f823a151502b7fc6beac55c3f6eeb92a59a3758811c", "src/App/ICS_PathFinding.java": "a367fd8e79aba7b3d23b71fc9b4d01f76dd67f291f008401d676ffcbcf53d52a", "src/App/Tasks.java": "dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b", "src/RUN/Main.java": "af7ba8f8224a480f61e4d4b010d0c6fcf5e8798cccfdf6f298d786ac053bf5af"}`.

## Task-list lifecycle extracted from Chapter 4

The thesis task tuple is `(b_k, o_k, d_k, t_k, tau_k)`: bag identity, origin, destination, BHS-entry time, and flight departure time. New tasks, tasks affected by a device interruption, and tasks whose future routes conflict are added to task list F and ranked before planning.

A task with a conflict-free route leaves F. A task with no route remains for a later planning cycle. Affected tasks may continue on the already committed safe portion, and repair places non-complete affected tasks back into the task processing lifecycle.

## Equations 4.2-4.5 and stated ordering

| Record | Exact extraction | Meaning | Local boundary |
| --- | --- | --- | --- |
| equation_4_2 | r_k = p1*T_disrupt_k*I_disrupt_k + p2*T_conflict_k*I_conflict_k + p3*T_departure_k + p4*T_wait_k | Unified task-ranking score. I_disrupt and I_conflict are binary task-class indicators; the four T terms are defined by 4.3-4.5 and the preceding disruption definition. | The thesis gives only an ordinal weight relation, not numeric weights or a scale-normalization rule; the exact scalar score is therefore extracted but not silently calibrated. |
| equation_4_3 | T_conflict_k = t_conflict_k - t | Time from the current instant to the first conflict on the bag's future route. | No future route, teacher path, full A*, or global reservation lookup may be introduced to recreate t_conflict_k. |
| equation_4_4 | T_departure_k = tau_k - t | Remaining time before the bag's flight departure. | The deadline term cannot read a future route or future schedule. |
| equation_4_5 | T_wait_k = t - t_k | Elapsed waiting/age since the task entered the BHS. | Age is a priority signal, not permission to bypass the physical shield, resource calendar, or atomic P2 validation. |
| weight_relation | p1 > p3 > p2 > p4 | The paper states disruption importance above departure, conflict, and waiting importance. | Do not invent numeric p values or claim an exact scalar reproduction without a declared calibration. |
| stated_order_and_tie | fault-affected > nearer departure > conflict > new; first-in-first-out tie | The prose orders disrupted tasks first, near-departure tasks second, future-conflict tasks third, new tasks last, and states first-in-first-out. | Current contention is not the thesis's full-future-route conflict test, so results must be called a bounded local projection. |

The scalar expression is not fully executable from the thesis alone: numeric weights and cross-term normalization are not specified. G4IRSF13 therefore preserves the explicitly stated ordering as a deterministic local projection and reports this limitation rather than inventing p-values.

## BTI and DDI separation

- DDI is device interruption/repair information. It updates which physical conveyor resources are available and identifies tasks potentially affected by the change.
- BTI is baggage tracking information. It supplies the actual bag/node passage state used to update execution state and to identify conflicts/affected bags.
- Localized transfer: DDI becomes a bounded generation-tagged availability overlay; BTI anchors the bag's actual local position. The physical entry interlock remains authoritative.

## Fault propagation and repair re-entry

The thesis removes an affected conveyor set from the available graph, holds bags that cannot safely continue, and restores the set on repair. Bags stopped by the interruption are returned to the task list for priority processing.

Only the lifecycle is transferable. The final runtime must re-enqueue at the current safe node and choose at most one next edge. It must not recreate the thesis HCA*, saved route, global reservation table, or full replan.

## Legacy arc IDs 1-8 mapped to protected map2

| Arc ID | Real map edge | Length |
| --- | --- | --- |
| 1 | 0->6 | 8 |
| 2 | 1->7 | 12 |
| 3 | 2->9 | 9 |
| 4 | 3->16 | 4 |
| 5 | 4->17 | 9 |
| 6 | 5->19 | 4 |
| 7 | 6->8 | 7 |
| 8 | 6->12 | 25 |

All eight are real directed map2 edges. The real-map audit also finds merge node 8, split nodes 6 and 52, and 11 weak-projection bridges; `(0,6)` (arc 1) is one of those bridges.

## Thesis Table 5.5 (paper-reported only)

| Scenario | Interrupted arcs | Affected conveyors | Paper success |
| --- | --- | --- | --- |
| single_1 | 1 | 1 | 1.00 |
| single_2 | 2 | 7 | 0.88 |
| single_3 | 3 | 5 | 1.00 |
| single_4 | 4 | 15 | 0.95 |
| single_5 | 5 | 24 | 0.97 |
| single_6 | 6 | 7 | 0.96 |
| single_7 | 7 | 1 | 1.00 |
| single_8 | 8 | 7 | 0.99 |
| pair_1_7 | 1,7 | 2 | 1.00 |
| pair_2_4 | 2,4 | 22 | 0.76 |
| pair_3_5 | 3,5 | 36 | 0.66 |
| pair_4_5 | 4,5 | 54 | 0.00 |
| pair_5_7 | 5,7 | 12 | 0.48 |
| triple_2_4_6 | 2,4,6 | 36 | 0.26 |
| triple_3_5_8 | 3,5,8 | 51 | 0.05 |
| triple_4_6_7 | 4,6,7 | 30 | 0.26 |

These 16 rows are extracted paper outcomes, not G4IRSF13 runtime results. Stage H may map the listed arc IDs through `arc.txt`, but promotion requires informative exposure and a matched physical-shield control.

## Protected input coverage

The committed input contains `43603` segments for `28506` raw bags. EBS/source/goal details are validated in `g4irsf13_ebs_goal_lifecycle_audit.csv`.
