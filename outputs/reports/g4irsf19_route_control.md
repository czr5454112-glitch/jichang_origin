# G4IRSF19 Route control

G19 did not add another routing framework. It exposed the four one-hop scorers
already implemented by the native runtime under the existing E4/J2 boundary,
while keeping R3/P2/Q0/C0 and every hard safety shield unchanged.

| Arm | Controller | 8,192 matched branch mutations | Result |
|---|---|---:|---|
| S1 | frozen G4E legal-local model | baseline | risk fallback remained active |
| S2 | same frozen model without absolute node/goal identifiers | 0 / 27,775 | identical to S1 |
| S3 | shortest-potential rule | 0 / 27,775 | identical action and business metrics |
| S4 | local queue/calendar-aware rule | 90 / 27,418 | small but real action change and benefit |

The evidence trace was complete and matched decisions by task, current node,
goal, and candidate set. S4 reduced the 8,192-prefix mean TTH by 1.794 s, p99
by 15.869 s, route wait by 1.668 s, and event count by 3,269 with zero loops
and all hard gates passing.

The full-scale result is much stronger. Against S1, S4 reduced 2x mean TTH
from 851.864 s to 337.843 s, p95 from 4,669.424 s to 960.004 s, p99 from
7,386.187 s to 2,242.954 s, source wait from 502.462 s to 54.666 s, and event
count by 1,376,967. The 1x case also improved, so the result is not purchased by
a low-load regression.

Conclusion: promote J2+S4 as the G19 research mainline. S4 is a deterministic
decentralized local rule, not a learned-controller claim. The frozen learned
S1/S2 family did not earn normal-flow promotion.
