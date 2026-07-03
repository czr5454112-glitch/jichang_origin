# G4IRSF5 Claim Boundary Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `1aff5eb`
paper_docx: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.docx`
original_project_root: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目`
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

## Allowed Claims

- The thesis protocol was readable and extracted into CSV inventories.
- The original project flat 2.5m/s result aligns with the paper's 3.96-minute average THT after summing split segment durations by task_id.
- G4IRSF5 runs the no-A* runtime on the paper inputdata-derived processed JSONL with no runtime full CIE/A* fallback.
- G4IRSF4's 348824-task result remains a high-flow extension only.

## Disallowed Claims

- Do not call static A* a Java/CIE, HCA*, or paper-grade dynamic baseline.
- Do not call the no-A* runtime the original IoT-DRPA/HCA* implementation.
- Do not promote G4J from this pass; G4J remains closed until an explicit paper-protocol comparison supports it.

Apples-to-apples rows with winner_allowed=true: `2`.
Fault-aware diagnostic rows completed: `34`.
