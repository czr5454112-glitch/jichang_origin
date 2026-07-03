# G4IRSF5 Original Project Flow Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `1aff5eb`
paper_docx: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.docx`
original_project_root: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目`
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Flow Element | Coverage | Notes |
| --- | --- | --- |
| original_project_access | PASS | Main claim blocked if missing. |
| raw_inputdata_day | PASS | Header + 28506 raw bag rows expected. |
| early_bag_split_to_ebs | PASS | THT must sum storage-in and storage-out segment durations. |
| topology_and_arc_ids | PARTIAL | Paper conveyor count and executable arc rows differ; keep this boundary explicit. |
| primary_no_fault_2_5_result | PASS | Parsed original-project text aligns with paper THT. |
| speed_sweep_files | PARTIAL | Primary replay remains 2.5m/s. |
| dispersed_heuristic_baseline | AVAILABLE_AS_PROJECT_ARTIFACT | No executable dispersed heuristic rerun in this pass. |
| fault_scenario_artifacts | AVAILABLE_AS_PROJECT_ARTIFACT | Metric scope differs: paper baggage success vs processed-segment success. |
| java_gui_entrypoint | BLOCKED_HEADLESS_EXPECTED | RUN.Main calls ICS_GUI.showmap(), so headless full runtime is blocked. |
