# G4IRSF32 GitHub audit snapshot

This branch is a GitHub-compatible audit snapshot of the complete local implementation head 91ddc43818246a3120dad74638441f86bae49aba (91ddc43). Its commit is intentionally parented to the already-published G4IRSF31 branch so the oversized intermediate G4IRSF32 history is not transferred to GitHub.

The snapshot preserves the current code, action plan, audit evidence pack, execution ledger, preregistrations, reports, and formal result tables. Only these archived early failed-run raw artifacts are omitted:

- outputs/tables/g4irsf32_v3r5_nanning_p0_control_selection_attempt1_audit_failed.json (307.26 MB; exceeds GitHub's per-file limit)
- outputs/tables/g4irsf32_v3r6_nanning_p0_control_selection_attempt1_audit_failed.json (60.33 MB; paired historical failed-run raw artifact)

Their decisions and downstream handling remain recorded in docs/G4IRSF32_execution_ledger.md and the corresponding addenda. The remote snapshot commit hash therefore differs from the complete local-history head, but its audit scope differs only by the two files listed above.
