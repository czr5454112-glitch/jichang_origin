# C10 independent partial audit

C10 hit the 150-second hard limit. The last persisted segment reaches 58800, while the planned final boundary is 59400. There is no worker report, final raw, or closed native acceptance. This is an incomplete run; no final same-endpoint comparison or benefit is established.

The complete 28506-job input bytes match C00. All 99 archived source files match their own prepared hashes. The reported 57600 warmup state hash matches C00, and the independently decoded persisted warmup results match except for measured advance.wall_seconds (7.3e-06 versus 7.4e-06). At the shared saved 58800 boundary, jobs/trays/transfers/receipts equality is {'jobs': True, 'trays': True, 'transfers': True, 'receipts': True}. This limited observation does not close C10 acceptance.

Saved forecast records: 34, from 57660.0 through 58800.0, across both owners. All records retain legal model cutoffs, current forecast origin and matching owner. All 34 have zero supplies; candidate count totals 0, and all return local_wait. There are 0 new forecast-preposition transfer submissions. Existing-rule new transfer calls after warmup: 6; retry calls: 154.

Recorded planner compute totals 40.815 seconds across the saved forecast records (includes preparation, not a standalone model benchmark). Computing a full forecast with no available supply adds overhead without enabling an action in these records. A future performance revision can short-circuit at zero supply, but must be a new source/run identity; this audit changes no frozen code.

At 58800: true completed business jobs 0; job statuses {'in_transit': 18, 'waiting_for_tray': 20654, 'unreleased': 7834}. Tray modes {'loaded': 18, 'empty_transit': 4}. Edge entries/exits remain 209/209, last exit 11395.634000000004. Native completed_count 6 counts legs, not completed business jobs. The 4001 unreachable jobs and physical bottleneck are detailed in C00_review_001; no input correction was applied.

No claims are made about the unsaved final segment. This partial run remains retained as a failure and cannot justify C01/C11 training or an airport optimization claim.
