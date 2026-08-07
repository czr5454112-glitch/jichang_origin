# G4IRSF19 joint closed-loop decision

The simplest verified joint controller is:

```text
Source: existing bounded release behavior (no learned ordering promotion)
Route: S4 local queue/calendar-aware one-hop rule
Merge: J2 destination-owned bounded-pending JIT grant
Safety/resource boundary: unchanged R3/P2/Q0/C0 shields
```

This composition completes 1x and 2x. At 2x it cuts mean TTH by 60.34%, p95
by 79.44%, p99 by 69.63%, source wait by 89.12%, and native events by 10.79%
relative to J2/S1. At a 60-second 4x boundary it completes 27,872 bags versus
18,212 for J2/S1, a 53.05% larger live completion frontier, while returning a
bounded partial result instead of hanging outside the native runtime.

This is a meaningful move from centralized full-route planning toward local
MAPF-style decisions and destination-owned arbitration. It does not yet prove a
learned multi-head controller or parallel commit inside one event loop.
