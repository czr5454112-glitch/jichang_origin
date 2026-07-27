# G4IRSF13 Thesis-aligned Local Fault Mechanism

Status: `DESIGN_AND_REAL_MAP_MAPPING_COMPLETE`

The implementation keeps six planes separate: an always-on physical entry interlock; generation-tagged local DDI messages; BTI-based affected-bag identification; revocation of unconsumed credit and uncommitted P2 work; one-edge local rerouting/holding; and repair wake-up with temporary affected-bag priority. The protected map file is never changed: faults are dynamic overlays.

Runtime decisions remain one next edge with reservation depth one. No full A*/CIE, future route, global reservation scan, or global replanning is admitted.

## Thesis Table 5.5 mapping

| Scenario | Arc IDs | map2 edges | Paper success | Lost pairs |
| --- | --- | --- | --- | --- |
| single_1 | 1 | 0->6 | 1.00 | 5 |
| single_2 | 2 | 1->7 | 0.88 | 5 |
| single_3 | 3 | 2->9 | 1.00 | 5 |
| single_4 | 4 | 3->16 | 0.95 | 5 |
| single_5 | 5 | 4->17 | 0.97 | 5 |
| single_6 | 6 | 5->19 | 0.96 | 5 |
| single_7 | 7 | 6->8 | 1.00 | 0 |
| single_8 | 8 | 6->12 | 0.99 | 0 |
| pair_1_7 | 1,7 | 0->6,6->8 | 1.00 | 5 |
| pair_2_4 | 2,4 | 1->7,3->16 | 0.76 | 10 |
| pair_3_5 | 3,5 | 2->9,4->17 | 0.66 | 10 |
| pair_4_5 | 4,5 | 3->16,4->17 | 0.00 | 10 |
| pair_5_7 | 5,7 | 4->17,6->8 | 0.48 | 5 |
| triple_2_4_6 | 2,4,6 | 1->7,3->16,5->19 | 0.26 | 15 |
| triple_3_5_8 | 3,5,8 | 2->9,4->17,6->12 | 0.05 | 10 |
| triple_4_6_7 | 4,6,7 | 3->16,5->19,6->8 | 0.26 | 10 |

Paper success rates remain labelled as paper-reported outcomes. They are not copied into the G4IRSF13 runtime result.

## Preventive criticality

| Rank | Arc | Edge | Task reachability loss | Source-goal loss | Bridge |
| --- | --- | --- | --- | --- | --- |
| 1 | 5 | 4->17 | 4887 | 5 | True |
| 2 | 4 | 3->16 | 4887 | 5 | True |
| 3 | 6 | 5->19 | 4886 | 5 | True |
| 4 | 2 | 1->7 | 3193 | 5 | True |
| 5 | 1 | 0->6 | 3200 | 5 | True |
| 6 | 3 | 2->9 | 3199 | 5 | True |
| 7 | 7 | 6->8 | 0 | 0 | False |
| 8 | 8 | 6->12 | 0 | 0 | False |

The maintenance rank is an offline topology/reachability heuristic, not a runtime routing feature and not a causal estimate.
