# G4IRSF18 feature ablation

The JIT merge trace does not contain the complete historical 22D/39D/60D/89D feature blocks. Those comparisons remain `NOT_EVALUATED`; unavailable values are never filled or inferred. Evaluated rows use the same J3 linear-residual family and opportunity-disjoint validation split.

| Group | Status | Features | Validation top-1 | Validation regret | Reason |
|---|---|---:|---:|---:|---|
| F2_OLD_22 | NOT_EVALUATED | 22 |  |  | merge trace lacks the frozen map-coded/training-risk block; zero fill is forbidden |
| G17_LOCAL_39 | NOT_EVALUATED | 39 |  |  | merge trace lacks the complete G17 source-front observation |
| RICH_LOCAL_V1 | NOT_EVALUATED | 60 |  |  | merge trace exposes only the native merge candidate subset, not the complete 60D contract |
| LEGACY_PLUS_RICH | NOT_EVALUATED | 89 |  |  | neither the legacy 29D block nor complete RICH_LOCAL_V1 is reconstructible |
| MERGE_TRACE_LOCAL_V1_FULL | EVALUATED | 18 | 0.9629629629629629 | 2.45356481481323e-05 | all directly observed and candidate-set-relative merge-local fields |
| MERGE_TRACE_LOCAL_V1_WITHOUT_TIMING_AND_URGENCY | EVALUATED | 14 | 0.9629629629629629 | 2.45356481481323e-05 | drop timing_and_urgency |
| MERGE_TRACE_LOCAL_V1_WITHOUT_SERVICE_AND_PRESSURE | EVALUATED | 15 | 0.9629629629629629 | 2.45356481481323e-05 | drop service_and_pressure |
| MERGE_TRACE_LOCAL_V1_WITHOUT_ROUTE_AND_STATIC_PROGRESS | EVALUATED | 16 | 0.9629629629629629 | 2.45356481481323e-05 | drop route_and_static_progress |
| MERGE_TRACE_LOCAL_V1_WITHOUT_TASK_AND_LEG | EVALUATED | 15 | 0.9629629629629629 | 2.45356481481323e-05 | drop task_and_leg |
| MERGE_TRACE_LOCAL_V1_WITHOUT_CANDIDATE_SET_RELATIVE | EVALUATED | 12 | 0.9629629629629629 | 2.45356481481323e-05 | drop candidate_set_relative |
