# G4IRSF5 Baseline Protocol Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `1aff5eb`
paper_docx: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.docx`
original_project_root: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目`
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Baseline | Status | Mean THT | Boundary |
| --- | --- | --- | --- |
| original_project_iot_drpa_text_2_5 | PASS | 3.9671227110082086 | Parsed original-project flat result; not a fresh Java GUI rerun. |
| static_astar_lower_bound_processed_segments | PASS | 1.0408152669613415 | Shortest-path lower bound only; no queue, node-window, HCA*, Java/CIE, or dynamic behavior. |
| paper_dispersed_heuristic_reported | PAPER_REPORTED_ONLY | 4.43 | Reported paper baseline, not rerun as executable code. |
| original_java_run_main_headless | BLOCKED |  | Full Java GUI runtime blocked if headless run fails. |
| temp_headless_java_astar_probe | PASS |  | Static A* probe only; validates dependency/run path but not paper-grade scheduler. |

## Java Attempts

| Attempt | Status | Notes |
| --- | --- | --- |
| dependency_inventory_original_project | PASS | Read-only inventory from original project path. |
| compile_original_project_java | PASS | Class output stays in a temp directory; original project is not modified. |
| run_original_project_RUN_Main_headless | BLOCKED | Swing GUI entrypoint is expected to block paper-grade Java runtime in headless mode. |
| run_temp_headless_astar_probe | PASS | This proves static Java A* can run headlessly; it is not the full Java/CIE scheduler baseline. |
