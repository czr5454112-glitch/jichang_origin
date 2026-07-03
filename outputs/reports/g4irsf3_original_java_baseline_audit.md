# G4IRSF3 Original Java Baseline Audit

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Run Attempts

| Attempt | Status | Notes |
| --- | --- | --- |
| locate_original_ics_project | PASS | C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目\代码-ICSsimulation |
| locate_javac | PASS | Java compiler needed for read-only baseline attempt. |
| compile_original_java_read_only | FAIL | compiled 15 source files into temporary directory; original tree not modified |

The original Java tree was treated as read-only. Compile output, if any, was written only to a temporary directory. A blocked headless run means the complete Java/CIE runtime baseline is still not available for paper-grade speed claims.
