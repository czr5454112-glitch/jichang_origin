# G4IRSF11 Feature Lineage Audit

Generated: `2026-07-23`.

| Lineage | Field declarations |
| --- | --- |
| label | 7 |
| metadata | 21 |
| runtime | 63 |

Status: `PASS`.

Runtime observations, experiment/task metadata, and post-hoc labels have explicit lineage. Label rows are stored in a separate outcome artifact and are never merged into the decision trace. Full/future path suffixes, teacher fields, and post-hoc success fields are recursively rejected.

`short_history` is bounded to at most eight already-visited nodes. It cannot contain a future route suffix.
