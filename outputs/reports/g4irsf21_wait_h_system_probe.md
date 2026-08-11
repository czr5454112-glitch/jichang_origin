# G4IRSF21 WAIT H_system probe

Status: **COMPLETE_NO_WAIT_BENEFIT_OBSERVED**

Four protected 1x states were chosen from different existing edge-label and
wait-age strata. Each target used the real I4 action: hold exactly one natural
local service opportunity from the same checkpoint.

- same-state/action-changed/complete/live-safety/certificate: 4/4 PASS
- raw-bag TTH benefit: 0/4
- exact zero system delta: 2/4
- one affected segment delayed by 1 second, with no external benefit: 2/4
- corresponding raw-bag mean increase in those two cases: about 0.00003508 s

Together with the 16 H_bag action sets, this gives no 1x evidence for adding a
WAIT policy: S4 remained locally best, and sampled WAIT actions were neutral or
slightly harmful at system scope. This is deliberately a small probe. It does
not exclude a congestion-specific WAIT benefit in the untested 2x state
distribution, and it does not authorize a learned or closed-loop policy.
