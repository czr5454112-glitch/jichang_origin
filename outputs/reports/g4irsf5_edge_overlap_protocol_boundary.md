# G4IRSF5 Edge Overlap Protocol Boundary

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `1aff5eb`
paper_docx: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.docx`
original_project_root: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目`
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

The original thesis protocol reports THT, dynamic/static THT, and device-interruption success rate. It does not define edge-overlap as the primary claim metric.

G4IRSF4 recorded the full edge-overlap diagnostic as resource-blocked and kept node-window conflicts as the primary safety audit. G4IRSF5 therefore runs paper-protocol no-A* replay with edge diagnostics disabled and records edge overlap only as a non-paper diagnostic boundary.
