# CIE component activation audit

Status: **COMPLETE**; observed 10/10 registered map-load cells.

The scan uses complete G31 S4 with H_SA, M3/J2, strict descent, direct-neighbour calendar visibility, E2 and goal-arrival completion. Counters are same-state streaming diagnostics; no candidate trace or survivor-only timing is used.

| Map | Load | Component | Opportunities | Pre-feasibility raw-argmin changes | Rate | Classification |
|---|---:|---|---:|---:|---:|---|
| map2 | 1.00 | Q | 28263 | 74 | 0.002618 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.00 | I | 366645 | 879 | 0.002397 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.00 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| map2 | 1.00 | ws | 119412 | 169 | 0.001415 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.25 | Q | 43660 | 151 | 0.003459 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.25 | I | 499750 | 1490 | 0.002981 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.25 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| map2 | 1.25 | ws | 182886 | 265 | 0.001449 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.50 | Q | 62669 | 293 | 0.004675 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.50 | I | 644314 | 2271 | 0.003525 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.50 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| map2 | 1.50 | ws | 258320 | 374 | 0.001448 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.75 | Q | 88528 | 516 | 0.005829 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.75 | I | 798479 | 3335 | 0.004177 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.75 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| map2 | 1.75 | ws | 347484 | 504 | 0.001450 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 2.00 | Q | 121605 | 798 | 0.006562 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 2.00 | I | 979452 | 4630 | 0.004727 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 2.00 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| map2 | 2.00 | ws | 458735 | 649 | 0.001415 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.00 | Q | 192308 | 19626 | 0.102055 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.00 | I | 879767 | 57674 | 0.065556 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.00 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| nanning | 1.00 | ws | 493725 | 4491 | 0.009096 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.25 | Q | 329706 | 44287 | 0.134323 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.25 | I | 1301789 | 73139 | 0.056183 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.25 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| nanning | 1.25 | ws | 811081 | 7199 | 0.008876 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.50 | Q | 538639 | 112581 | 0.209010 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.50 | I | 1820698 | 83345 | 0.045776 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.50 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| nanning | 1.50 | ws | 1230070 | 9602 | 0.007806 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.75 | Q | 699505 | 165326 | 0.236347 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.75 | I | 2267232 | 101795 | 0.044898 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.75 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| nanning | 1.75 | ws | 1574996 | 11919 | 0.007568 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 2.00 | Q | 835654 | 210337 | 0.251703 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 2.00 | I | 2677076 | 119980 | 0.044818 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 2.00 | wc | 0 | 0 | 0.000000 | NOT_ACTIVATED |
| nanning | 2.00 | ws | 1877589 | 13791 | 0.007345 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |

`ACTIVATED_NO_CLEAR_OUTCOME_EFFECT` means that the component changes the raw local argmin often enough to justify a paired ablation; it is not itself evidence of business benefit. `LOAD_DEPENDENT` means the material threshold was first crossed above 1x.

## J2/M3 pre-commit ordering diagnostic

The `PRE_COMMIT_ORDER_MUTATION` rate uses the count of service opportunities with at least two ready candidates as its denominator. `EXACT_SLOT_OVERLAP` is a separate, narrower physical-overlap diagnostic and is never used as that denominator. The mutation is observed before owner, queue-generation, fault-generation, calendar, capacity, exact-slot, and commit checks; it is not a final executed action or committed-grant change.

| Map | Load | Service opportunities | Multi-candidate opportunities (denominator) | EXACT_SLOT_OVERLAP (separate) | PRE_COMMIT_ORDER_MUTATION vs FIFO | Rate | Classification |
|---|---:|---:|---:|---:|---:|---:|---|
| map2 | 1.00 | 153592 | 627 | 475 | 296 | 0.472089 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.25 | 192659 | 918 | 663 | 443 | 0.482571 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.50 | 231976 | 1319 | 905 | 687 | 0.520849 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 1.75 | 268765 | 1828 | 1148 | 1005 | 0.549781 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| map2 | 2.00 | 308837 | 2404 | 1465 | 1361 | 0.566140 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.00 | 296353 | 34 | 15 | 11 | 0.323529 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.25 | 368663 | 36 | 12 | 8 | 0.222222 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.50 | 438191 | 28 | 5 | 5 | 0.178571 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 1.75 | 509506 | 42 | 5 | 9 | 0.214286 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
| nanning | 2.00 | 584213 | 66 | 5 | 15 | 0.227273 | ACTIVATED_NO_CLEAR_OUTCOME_EFFECT |
