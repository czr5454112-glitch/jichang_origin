# G4IRSF20 event hotpath paired ladder

E0/E1/E2 use the same fixed-map input and frozen A0 + S4 + J2 controls. Event counts may change; 1x/2x action, per-task TTH, and hard-safety semantics may not.
For full rows, completed work is reported as raw tasks over input segments; `COMPLETE` means every raw task finished. Bounded 4x rows report completed segments.
Action parity uses each bag's final/count/last-eight projection, not a full trace; per-task TTH and route-wait projections cover every completed raw task.

| scale | mode | policy | status | completed work / input | events | beacon events | suppressed | events/complete | events/s | mean TTH s | full semantics |
|---:|:---:|:---:|:---|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1x | full | E0 | COMPLETE | 28506 raw tasks / 43603 segments | 4857316 | 1978963 | 0 | 170.396267 | 238905.932967 | 213.912317 | True |
| 1x | full | E1 | COMPLETE | 28506 raw tasks / 43603 segments | 4246986 | 1368633 | 610330 | 148.985687 | 225926.015512 | 213.912317 | True |
| 1x | full | E2 | COMPLETE | 28506 raw tasks / 43603 segments | 4064751 | 1186398 | 792565 | 142.592823 | 221397.831078 | 213.912317 | True |
| 2x | full | E0 | COMPLETE | 57012 raw tasks / 87206 segments | 11388415 | 4620693 | 0 | 199.754701 | 204490.589401 | 337.842709 | True |
| 2x | full | E1 | COMPLETE | 57012 raw tasks / 87206 segments | 10169869 | 3402123 | 1218570 | 178.381200 | 195950.042338 | 337.842709 | True |
| 2x | full | E2 | COMPLETE | 57012 raw tasks / 87206 segments | 9454789 | 2687019 | 1933674 | 165.838578 | 188124.588692 | 337.842709 | True |
| 4x | bounded | E0 | BOUNDED_PROGRESS | 26977 / 174412 segments | 5570560 | 2187615 | 0 | 206.492938 | 92885.122444 | - | - |
| 4x | bounded | E1 | BOUNDED_PROGRESS | 27676 / 174412 segments | 5308416 | 1841584 | 399794 | 191.805752 | 87292.247679 | - | - |
| 4x | bounded | E2 | BOUNDED_PROGRESS | 27760 / 174412 segments | 4915200 | 1433053 | 818146 | 177.060519 | 82213.569997 | - | - |

## Decision

- Status: **SELECTED_EVENT_PUBLICATION_RESEARCH_POLICY**
- Selected policy: **E2**
- Reason: `SEMANTICS_AND_EVENT_MECHANISM_GATES_PASSED`

The 4x row is a bounded live-frontier observation, not a completed-capacity claim. A reduction in events without TTH or 4x progress movement is reported as software-overhead reduction, not physical-capacity improvement.
