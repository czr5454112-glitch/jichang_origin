# G4IRSF17 native fault campaign

Status: **`TERMINAL_WITH_CAPACITY_CENSORING`**. Complete required 1×/4× matrix: **False**. Comparative fault advantage supported: **False**.

| Candidate | Load | Fault category | Status | Affected | Recovery s | In-flight merge recovery | Gate |
|---|---|---|---|---|---|---|---|
| E4_OFF | 1× | no_fault | COMPLETE | 0 | — | 0 | True |
| E4_OFF | 1× | single_noncritical_edge | COMPLETE | 23 | 49.50199999999313 | 1 | True |
| E4_OFF | 1× | single_critical_bottleneck | COMPLETE | 1 | 46.40099999999802 | 0 | True |
| E4_OFF | 1× | merge_edge_or_node | COMPLETE | 22 | 75.50199999997858 | 0 | True |
| E4_OFF | 1× | source_first_edge | COMPLETE | 1 | 201.00099999999657 | 0 | True |
| E4_OFF | 1× | ebs_related_edge | COMPLETE | 0 | — | 0 | False |
| E4_OFF | 1× | two_nonadjacent_faults | COMPLETE | 2 | 89.30199999999604 | 0 | True |
| E4_OFF | 1× | two_propagating_faults | COMPLETE | 2 | 201.00099999999657 | 0 | True |
| E4_OFF | 1× | delayed_beacon | COMPLETE | 22 | 75.50199999997858 | 0 | True |
| E4_OFF | 1× | dropped_intermediate_beacon | COMPLETE | 22 | 75.50199999997858 | 0 | True |
| E4_OFF | 1× | repair_after_fault | COMPLETE | 1 | 46.40099999999802 | 0 | True |
| E4_OFF | 4× | no_fault | CAPACITY_CENSORED_BY_EQUIVALENT_CONTROL | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | single_noncritical_edge | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | single_critical_bottleneck | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | merge_edge_or_node | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | source_first_edge | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | ebs_related_edge | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | two_nonadjacent_faults | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | two_propagating_faults | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | delayed_beacon | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | dropped_intermediate_beacon | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |
| E4_OFF | 4× | repair_after_fault | NOT_RUN_CONTROL_CENSORED | — | — | UNAVAILABLE | — |

Observed exact in-flight merge-generation recoveries: **1** across **11** cells; **11** cells are explicitly unavailable.

Evidence: `outputs/tables/g4irsf17_fault_results.csv`. Censored, uninformative, and missing cells remain non-passes.
