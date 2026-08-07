# G4IRSF18 event amplification

This table keeps event work separate from simulated business time. Negative event delta means fewer native events per completed segment than the matched eager arm.

| Scope | Candidate | Events/segment delta | TTH mean delta (s) | Source wait delta (s) | Merge wait delta (s) | Network delta (s) |
|---|---|---:|---:|---:|---:|---:|
| 144 segments | J1_F2_JIT_FIFO | -5.881944444444443 | -0.04164402777817284 | 0.0 | -0.04164402777817284 | -0.04164402777817284 |
| 144 segments | J2_F2_JIT_FAIR_AGING_DEADLINE | -5.881944444444443 | -0.04164402777817284 | 0.0 | -0.04164402777817284 | -0.04164402777817284 |
| 2048 segments | J1_F2_JIT_FIFO | -8.16162109375 | -1.2064329894934571 | 0.0 | -0.42098582616985536 | -1.2064329894934571 |
| 2048 segments | J2_F2_JIT_FAIR_AGING_DEADLINE | -8.244140625 | -1.2064329894934571 | 0.0 | -0.2934978701049178 | -1.2064329894934571 |
| 512 segments | J1_F2_JIT_FIFO | -7.900390625 | -0.3745716406255397 | 0.0 | -0.20206285156303494 | -0.3745716406255397 |
| 512 segments | J2_F2_JIT_FAIR_AGING_DEADLINE | -7.98046875 | -0.3745716406255397 | 0.0 | -0.17441113281303444 | -0.3745716406255397 |
