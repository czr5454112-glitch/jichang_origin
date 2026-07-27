# G4IRSF13 v3 Closed-Loop Report

Status: `NOT_RUN`.

This Stage-F implementation deliberately does not modify the C++ runtime,
binding, or backend. The required 144 -> 512 -> 2048 -> 8192 -> full ladder has
not executed for any residual candidate. The companion CSV records every
required control/candidate row as `NOT_RUN` with empty performance fields.

Therefore no claim is made that v3 beats F2 (`41.514218717973` min) or
frozen v2-safe (`41.495306987809` min), and the existing
`1.134703810` s/bag gap remains open.
