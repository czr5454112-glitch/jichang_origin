# Round9 ledger audit notes

The final ledger is built only after the parent confirms that all six fixed-window deployments and independent reviews have ended. `build_ledger.py --run-name <new-name> --final` creates a new directory, never overwrites an earlier receipt, and rejects final closure if required evidence is pending or changes while it is read.

`draft_001` and `draft_002` are retained provisional snapshots. In `draft_002`, resource rows and the global explicit-physics sum already included `mechanisms_004`, but its standalone `mechanism_physical_runs` summary still displayed the old hard-coded 126. The final script now derives each mechanism denominator from its saved protocol, checks started/completed counters, and reports 60 + 60 + 6 + 66 = 192. The historical draft is not rewritten.

The ledger adds measured process intervals once. Same-process pytest, physics, scales, queries and continuation-replay intervals are explanatory children, while separately executed bridge children contribute their own CPU. Previous ledger invocations contribute only their own measured construction CPU, never their cumulative upstream total. Current ledger construction CPU is separately displayed. Concurrent wall times are not summed.

Unknown auxiliary CPU and uninstrumented test-physics counts remain unknown. The final source-closure receipt excludes the child Git process and final seal writes; these are explicitly listed as unmetered. Shell inspection, parsing and editing outside measured scripts, including failed path reads, also remain unmetered auxiliary work. A reported zero business batch count is never converted into zero test physics.

Static-domain work reads the original graph, whole source tasks and declared contracts without simulation or destination reassignment. It is a necessary reachability/deadline lower-bound audit, not dynamic feasibility. Its measured process interval and the independently recomputed audit intervals are separate ledger rows.

Six original-endpoint window deployments are preserved, including the four old-source diagnostic deployments and two final-source deployments. Chunked result collection still advances physical time every tick. CPU censoring does not demonstrate infeasibility; the complete 44-task first-hour denominator remains intact in each deployment.
