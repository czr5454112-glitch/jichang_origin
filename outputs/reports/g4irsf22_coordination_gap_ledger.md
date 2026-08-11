# G4IRSF22 matched 2x coordination-gap ledger

Status: `COMPLETE` on the same 57,012 raw bags / 87,206 runtime segments.

## Additive time bank (S4 minus v2-safe)

- Total gap: `90.458043` s/raw bag.
- Source: `54.666355` s/raw bag.
- Inclusive route wait: `43.138709` s/raw bag.
- Arithmetic residual: `-7.347022` s/raw bag.
- Network diagnostic: `35.791688` s/raw bag.

The residual includes motion, service, and uninstrumented coordination. It is not named a pure coordination causal effect. Merge wait is a diagnostic subset of route wait and is never added twice; v2 has no equivalent J2 merge-grant instrument.

## Segment leg diagnostic

These rows are segment-weighted diagnostics; they do not share the raw-bag denominator of the additive time bank above.

| Leg | Segments | Mean total delta (s) | Mean source delta (s) | Mean route-wait delta (s) |
| --- | ---: | ---: | ---: | ---: |
| direct | 26,818 | 2.698107 | 6.004820 | 2.720604 |
| storage_in | 30,194 | 93.723315 | 8.681741 | 88.947820 |
| storage_out | 30,194 | 74.682200 | 89.205289 | -9.910165 |

## Largest raw-task origin source/time-block gaps

`Source` here is the raw task's first-segment/origin source. It must not be read as the later storage_out admission node.

| Origin source | Release block | Raw bags | Mean total delta (s) | S4-slower fraction |
| --- | ---: | ---: | ---: | ---: |
| node_53 | 6 | 835 | 926.888582 | 0.941 |
| node_1 | 6 | 842 | 857.943752 | 0.879 |
| node_2 | 6 | 842 | 663.868714 | 0.787 |
| node_0 | 6 | 840 | 508.253082 | 0.796 |
| node_53 | 7 | 446 | 434.793373 | 0.738 |
| node_5 | 6 | 952 | 218.570186 | 0.488 |
| node_53 | 5 | 967 | 208.854760 | 0.595 |
| node_0 | 4 | 158 | 205.041574 | 0.741 |

## Storage-out admission seam (segment-level)

The true `storage_out` admission seam is `node_52`: block 7 is the largest mean-total-gap cell, and block 8 confirms the same seam. The block-6 raw-task origin rows for `node_53`, `node_1`, `node_2`, and `node_0` above are not `storage_out` admissions.

| Leg | Admission source | Release block | Segments | Mean total delta (s) | Mean source delta (s) | Mean route-wait delta (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| storage_out | node_52 | 7 | 3,600 | 500.838136 | 583.655486 | -62.663073 |
| storage_out | node_52 | 8 | 1,216 | 200.026021 | 200.836349 | -0.352130 |

v2-safe remains an offline comparator only. No v2 route, reservation, or future state is exposed to the decentralized runtime.
