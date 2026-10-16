# Pre-existing occupancy: separate pure mechanism domain

The preceding 96-cell domain did not make the strong reference depend on
later rerouting. Its Storage gate masked the initial detour's extra travel,
which also equalized the time at which the loaded tray became reusable.
This separate domain tests an explicit structural alternative: initial
rerouting can shorten the loaded journey because another real tray already
occupies the default path. It uses no Storage release gate.

A third tray P starts loading a fifth protected job at node 1. That job's
destination is new node 9, reached by new edge 1→9, so P eventually parks
outside the existing shared Storage. Node 9 has capacity 1, service 0.1,
and no export; the new edge has travel 1 and headway 0.5. Every existing
node/edge capacity, FIFO rule and tray remains unchanged. All five jobs and
all three trays are present in every arm. The short-blocker negative control
uses load 0.2; the blocking case uses load 3. Receiver loads remain the
previously declared 3, 5 and 7. These six cases are fixed before projections.

Each case has 32 action tuples: two initial suffixes, four E supply times,
two first-return waits and two first-reuse suffixes. E times include the
previous 0.11 and 2.21, plus the public blocker-clearance and loaded-clearance
bounds, each increased by one 0.001 dispatch quantum. This gives the fixed
initial-route reference explicit new clearance windows rather than denying
it a useful timing action. These times are candidate intents, not proven
native lease or dispatch times. All 192 projections are retained.

The strict, plateau, pair-repair and finite-horizon reference searches all
use the same 32-candidate budget, deterministic ordering, facts and zero
per-job protection threshold. The fifth blocker's completion is included
in every protection check. Fixed-initial-route results cover its sixteen
declared tuples only; no continuous timing optimum is claimed.

The 1→9 edge is an ordinary positive-capacity edge present in every method's
graph. Nodes 1 and 9 have the same source owner A. Enumerating simple paths
shows 1→9 is the only path to P's destination; node 9 has no outgoing edge,
so other jobs cannot use it to reach their different destinations. The pure
model's direct P path is a static route requirement, not a private edge grant.
Actual native authorization remains untested. The preregistration pins all
six configurations and its listed source files before the first projection.
That list did not include the transitive preprocessing import closure.

The mechanism is falsified if initial rerouting does not advance loaded
completion against the protected fixed-route family, or if holding later
suffix 3 leaves the selected completion vector unchanged. Combined modeled
protection fails on any one of the five jobs. A plateau-search tie falsifies
superiority over that ordinary baseline. Missing cube rows leave interaction
unknown. These criteria are declared before outcomes.

The mechanism diagnostic retains all first-R1 / return-R2 / later-R1
factorial contrasts and compares selected later routing with otherwise
identical route-3 continuation. Model results alone cannot establish actual
FIFO, ACK, route authority, receiving reservations or physical protection.
This pure initial-state table is not an online policy input. A native version
would require a new explicit supported-input model and owner-delivery adapter
for five obligations and three trays; the current accepted two-tray adapter
must reject this domain. No original-map input or existing study is changed.

The saved pure campaign `preexisting_occupancy_domain_001` contains all 192
conditional projections, completed in 1.272 seconds with unchanged source
hashes. Thirteen focused pure tests passed before execution. A separate
saved-data audit, `preexisting_occupancy_domain_001_independent_audit.json`,
recomputes configuration and archived-source hashes, every action denominator,
five-job protection, strategy evaluation accounting and both finite optima
without evaluating the model again or calling native code.

| Blocker load | Receiver load | Projected gain versus incumbent | All four strategies select |
| --- | --- | --- | --- |
| 0.2 | 3 | 0.009 | initial 1, supply 2.201, return 0, later 3 |
| 0.2 | 5 | 2.149 | initial 1, supply 2.201, return 0, later 8 |
| 0.2 | 7 | 0.009 | initial 1, supply 2.201, return 0, later 3 |
| 3 | 3 | 4.219 | initial 2, supply 3.101, return 0, later 3 |
| 3 | 5 | 5.219 | initial 2, supply 3.101, return 0, later 8 |
| 3 | 7 | 4.219 | initial 2, supply 3.101, return 0, later 3 |

These are sums of modeled completion-time improvements. Ordinary strict
coordinate search, plateau search, pair repair and complete enumeration all
agree in every case. Thus this study gives no evidence of search-method
superiority. It does identify a candidate physical mechanism for validation:
with the longer pre-existing occupancy, initial route 2 can advance loaded
completion while protecting all five modeled jobs. At blocker 3 / receiver
5, later route 8 improves reuse1 and reuse2 by 0.981 and 0.950 seconds versus
the otherwise identical route-3 continuation. However, that route-3 continuation
still protects every job against the best declared fixed-initial reference.
Later rerouting is therefore useful for the best modeled outcome in this case,
but is not necessary for obtaining any protected gain. The claim remains
conditional on model accuracy and native command execution.

The saved-data audit passed 122 checks. An independent second review also
recomputed all 192 rows. It found a native-input limitation: the pure fixture
appended node 9 after the earlier nine-node potential was prepared, leaving
ten node records but a nine-row heuristic matrix. The projection never reads
that matrix, so its conditional results are retained unchanged. Those saved
inputs must not be passed directly to native. The separately versioned native
gate rebuilds the ten-by-ten service-aware potential, saves every corrected
input, and archives the actual loaded project Python import closure, including
the potential implementation. This is a new preparation contract, not a
retroactive repair of the saved 192-cell study.
