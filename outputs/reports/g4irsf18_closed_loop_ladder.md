# G4IRSF18 closed-loop ladder

Status: **`COMPLETE`** (15/15 jobs).

J0/J1/J2 are real native arms. Prefixes through 8,192 use evidence-trace mode; 43,603 uses capacity mode with opportunity rows disabled. A learned row appears only after an explicit research-only arm configuration passes validation.

| Segments | Arm | Mode | Status | Hard safety | Mean TTH s | P95 s | Source s | Merge s | Network s | Events/bag | Wakeups/opportunity | Pending peak | Mutations |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 144 | J0_F2_EAGER | evidence_trace | COMPLETE | True | 10212.422339 | 11436.123604 | 1.274306 | 0.770705 | 224.253871 | 207.902778 | — | 1 | 0 |
| 144 | J1_F2_JIT_FIFO | evidence_trace | COMPLETE | True | 10212.380695 | 11436.123604 | 1.274306 | 0.729061 | 224.212227 | 196.138889 | 1.004525 | 2 | 0 |
| 144 | J2_F2_JIT_FAIR_AGING_DEADLINE | evidence_trace | COMPLETE | True | 10212.380695 | 11436.123604 | 1.274306 | 0.729061 | 224.212227 | 196.138889 | 1.004525 | 2 | 0 |
| 512 | J0_F2_EAGER | evidence_trace | COMPLETE | True | 8816.721934 | 11183.227207 | 3.126953 | 1.342370 | 228.766524 | 212.769531 | — | 1 | 0 |
| 512 | J1_F2_JIT_FIFO | evidence_trace | COMPLETE | True | 8816.347363 | 11176.475535 | 3.126953 | 1.140307 | 228.391953 | 196.968750 | 1.022886 | 3 | 0 |
| 512 | J2_F2_JIT_FAIR_AGING_DEADLINE | evidence_trace | COMPLETE | True | 8816.347363 | 11175.843132 | 3.126953 | 1.167959 | 228.391953 | 196.808594 | 1.022886 | 3 | 13 |
| 2048 | J0_F2_EAGER | evidence_trace | COMPLETE | True | 6313.742403 | 10876.900579 | 16.739494 | 1.950906 | 239.634890 | 215.156638 | — | 1 | 0 |
| 2048 | J1_F2_JIT_FIFO | evidence_trace | COMPLETE | True | 6312.535970 | 10876.055389 | 16.739494 | 1.529920 | 238.428457 | 199.191977 | 1.040268 | 4 | 0 |
| 2048 | J2_F2_JIT_FAIR_AGING_DEADLINE | evidence_trace | COMPLETE | True | 6312.535970 | 10876.219159 | 16.739494 | 1.657408 | 238.428457 | 199.030564 | 1.040581 | 4 | 134 |
| 8192 | J0_F2_EAGER | evidence_trace | COMPLETE | True | 3443.367007 | 9531.536287 | 35.252144 | 2.605944 | 242.841427 | 199.571662 | — | 1 | 0 |
| 8192 | J1_F2_JIT_FIFO | evidence_trace | COMPLETE | True | 3439.232793 | 9527.658799 | 34.997754 | 1.811778 | 238.961603 | 181.175786 | 1.077671 | 5 | 0 |
| 8192 | J2_F2_JIT_FAIR_AGING_DEADLINE | evidence_trace | COMPLETE | True | 3439.282884 | 9527.676141 | 35.031135 | 2.128532 | 238.978313 | 181.076766 | 1.079291 | 7 | 895 |
| 43603 | J0_F2_EAGER | capacity | COMPLETE | True | 2493.379886 | 7357.773845 | 22.350672 | 2.023924 | 228.769122 | 191.012839 | — | 2 | 0 |
| 43603 | J1_F2_JIT_FIFO | capacity | COMPLETE | True | 2490.631907 | 7344.588737 | 21.657616 | 1.562741 | 226.714199 | 174.976356 | 1.064519 | 6 | 0 |
| 43603 | J2_F2_JIT_FAIR_AGING_DEADLINE | capacity | COMPLETE | True | 2490.662672 | 7348.184715 | 21.684707 | 1.746649 | 226.717873 | 174.897916 | 1.065057 | 7 | 3252 |

## Incremental boundary

All preregistered jobs for this stage have a result artifact.
