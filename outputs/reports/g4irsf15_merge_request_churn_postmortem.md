# G4IRSF15 merge-request churn postmortem

## Original 1x aggregate

| Metric | Value |
|---|---:|
| Completed movements (segments) | 43,603 |
| Merge requests | 335,770 |
| Arbitration events | 335,770 |
| Active-grant rejections | 178,263 |
| Requests per completed movement | 7.700616930 |
| Rejections per completed movement | 4.088319611 |
| Runtime events per completed movement | 124.877003876 |
| Queue-capacity blocks | 1,337 |
| Live multi-request boundaries | 1 |
| Lifecycle rows dropped | 1,011,439 |

The equality of requests and arbitrations, high active-grant rejection count, and almost absent multi-request live boundary are consistent with churn caused by immediate arbitration against an already active grant.

## Evidence availability

The original-1x destination/hour/source/goal/storage/timing/slack/retry breakdown is **NOT AVAILABLE** because the bounded passive lifecycle trace dropped rows and the committed census retained aggregate counters only. `g4irsf15_merge_request_churn.csv` contains one row per unavailable dimension to make this limitation machine-readable.

The complete Stage-D M0 144-segment lifecycle is audited separately: `666` requests, `224` active-grant rejections, `666` arbitrations, and zero dropped lifecycle rows. Its cohort contains only early, tight-slack, storage-in/out bags from hours 2--3, so it cannot estimate original-1x hotspots.

## Required campaign retention

Every selected intervention and its local lifecycle must be retained with dropped count zero. Non-target runs may retain aggregates plus deterministic min-hash samples. Shards must be streamed, compressed, atomically closed, and content-bound by a manifest. This solves evidence completeness without an unbounded in-memory trace.
