# G4IRSF18 bounded-pending JIT mechanism

Decision: **`JIT_REAL_NATIVE_CHOICE_CONFIRMED`**.

A true opportunity requires at least two still-valid local requests at the natural service boundary. A proposal or a request-time score does not count.

| Scope | Candidate | Multi-candidate | True competition | Order mutations | Choice seam |
|---|---|---:|---:|---:|---|
| 144 segments | J1_F2_JIT_FIFO | 0 | 0 | 0 | False |
| 144 segments | J2_F2_JIT_FAIR_AGING_DEADLINE | 0 | 0 | 0 | False |
| 2048 segments | J1_F2_JIT_FIFO | 74 | 74 | 0 | False |
| 2048 segments | J2_F2_JIT_FAIR_AGING_DEADLINE | 138 | 138 | 134 | True |
| 512 segments | J1_F2_JIT_FIFO | 10 | 10 | 0 | False |
| 512 segments | J2_F2_JIT_FAIR_AGING_DEADLINE | 13 | 13 | 13 | True |
