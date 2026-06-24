# Phase2 C++ SIPP Parity Report

Date: 2026-06-17

## Scope

This diagnostic compares the Python SIPP baseline against the new C++ SIPP planner through the pybind in-memory record API. It covers clear routing, node-reservation waiting, edge-capacity waiting, edge-headway waiting, fault-edge blocking, and merge-group waiting, plus first-task routes from the persisted synthetic manifest.

## Metrics

| Case | Start | Goal | Python route | C++ route | Finish diff | Parity | First mismatch |
|---|---:|---:|---|---|---:|---|---|
| line_clear | 0 | 2 | 0->1->2 | 0->1->2 | 0.000000000000 | True | match:none@ |
| line_node_wait | 0 | 2 | 0->1->2 | 0->1->2 | 0.000000000000 | True | match:none@ |
| line_edge_capacity_wait | 0 | 2 | 0->1->2 | 0->1->2 | 0.000000000000 | True | match:none@ |
| line_edge_headway_wait | 0 | 2 | 0->1->2 | 0->1->2 | 0.000000000000 | True | match:none@ |
| line_fault_blocked | 0 | 2 | none | none | 0.000000000000 | True | match:none@ |
| parallel_merge_group_wait | 0 | 4 | 0->2->4 | 0->2->4 | 0.000000000000 | True | match:none@ |
| synthetic_seed7_medium_repair_first_task | 0 | 11 | 0->3->8->11 | 0->3->8->11 | 0.000000000000 | True | match:none@ |
| synthetic_seed11_dense_multi_repair_first_task | 2 | 11 | 2->6->9->11 | 2->6->9->11 | 0.000000000000 | True | match:none@ |
| synthetic_seed17_static_plus_repair_first_task | 0 | 11 | 0->3->8->9->11 | 0->3->8->9->11 | 0.000000000000 | True | match:none@ |
| synthetic_seed23_repeated_repair_first_task | 2 | 11 | 2->5->8->11 | 2->5->8->11 | 0.000000000000 | True | match:none@ |
| synthetic_seed31_merge_buffer_first_task | 2 | 11 | 2->6->8->11 | 2->6->8->11 | 0.000000000000 | True | match:none@ |

CSV: `outputs/tables/phase2_cpp_sipp_parity.csv`

## Gate Status

- C++ SIPP route/timing parity: PASS
- node and edge reservation waiting cases: covered
- merge-group waiting case: covered
- persisted synthetic manifest first-task cases: covered
- rolling-horizon C++ replay: not covered
- full active-bag replay integration: not covered
