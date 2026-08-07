# G4IRSF19 feature aliasing

## Source

The existing Source ordering seam has no useful action freedom on the tested
workloads. It produced 0 alternative proposals and 0 action mutations after 62,
238, and 8,335 evaluations at 144, 512, and 8,192 segments. Within one source
opportunity, the top-K rows shared the same slack, wait, and leg features apart
from rank. Training a larger model on that seam would fit aliases rather than
control a different action.

## Route

Removing absolute node/goal identifiers from the frozen scorer (S2) changed
0 of 27,775 matched multi-action decisions and all measured business metrics
were identical to S1. A shortest-potential-only scorer (S3) was also identical
on the same trace.

The only effective feature group was S4's small local congestion summary:
candidate queue length, scheduled incoming count, corridor next-available time,
and target next-available time, added to travel time and static potential. This
group created 90 directly observed one-hop mutations at the 8,192 prefix and
large improvements at full 2x load.

Decision: keep the useful local queue/calendar features and stop expanding
absolute-ID or Source-ranking features until a non-aliased action seam is
observed.
