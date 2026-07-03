# G4IRSF5 Original Paper Protocol Audit

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `1aff5eb`
paper_docx: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.docx`
original_project_root: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目`
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

## Extracted Protocol

| Item | Status | Value |
| --- | --- | --- |
| paper_protocol_access | OK | C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.docx |
| case_topology | EXTRACTED | {"装载站数量": "7", "卸载站数量": "22", "交叉点数量": "44", "输送线数量": "72", "EBS数量": "1", "时间间隔": "24小时", "每个装载站的行李到达量": "1176，2872，5544，4533，7542，2585，4254", "输送线速度": "1.5，2.0，2.5，3.0米/秒"} |
| daily_baggage_count | EXTRACTED | 28506 |
| main_metric | EXTRACTED | THT average/min/max; TH noted but not central |
| primary_speed | EXTRACTED | 2.5 m/s primary, speed sweep 1.5/2.0/2.5/3.0 |
| primary_method | EXTRACTED | IoT-DRPA / HCA* |
| comparison_baseline | EXTRACTED | 分散启发式方法 |
| dynamic_static_protocol | EXTRACTED | dynamic IoT-DRPA vs static LRA* under 10/20/30% speed deviations |
| fault_protocol | EXTRACTED | 16 fixed interruption scenarios; success rate by baggage count |

## Boundary

The thesis main experiment is a one-day 28506-baggage protocol at 2.5 m/s, evaluated by bag-level THT after summing split segment travel times. G4IRSF4's 348824-task run is therefore an extension, not the paper main protocol.
