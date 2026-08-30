# G4IRSF32 V3R13 Candidate A pre-Stage-2 action gate

Status: `PASS_V3R13_CANDIDATE_A_PRE_STAGE2_ACTION_GATE`.

This is the frozen small DIRECT/J2 action suite. It does not report a real-map effect.

| case | topology | action | calendar mutations | events ratio | local-memory ratio | pass |
|---|---:|---:|---:|---:|---:|---:|
| direct_mixed_contention | direct | 1 | 1 | 0.982 | 0.998 | PASS |
| j2_mixed_contention | j2 | 1 | 1 | 0.991 | 0.999 | PASS |
| j2_reverse_priority_external | j2 | 1 | 1 | 0.991 | 1.000 | PASS |
| no_local | direct | 0 | 0 | 1.000 | 1.000 | PASS |
| no_external | direct | 0 | 0 | 1.000 | 1.000 | PASS |
| immediately_available | direct | 0 | 0 | 1.000 | 1.000 | PASS |
| future_release_base | direct | 1 | 1 | 0.986 | 0.998 | PASS |
| future_release_perturbed | direct | 1 | 1 | 0.986 | 0.998 | PASS |

## Decision

Stage 2 is authorized.

Failed gates: none
