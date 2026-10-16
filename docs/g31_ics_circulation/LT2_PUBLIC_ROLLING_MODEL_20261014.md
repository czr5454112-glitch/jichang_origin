# Later-state rolling model and declared request lineage

This is a new pure finite-domain implementation, not a native-validated rolling
controller. The earlier initial-checkpoint model, its 117 validation rows, and
the initial/native feedback campaigns are unchanged. No native future state,
offline completion table, gate label, or fork enters proposal selection.

`public_rolling_reuse_model.py` supports two explicitly different checkpoints:
the first empty L return opportunity at node6, and the first loaded reuse1
service at node7. It projects the remaining real L returns, loading, route,
edge/headway contention, receiving capacity, FIFO, unloading and hold events.
The two decision dimensions are reuse1 next3/next8 and a nonnegative delay for
the next L6→7 return. Only the first action is a proposal for the current owner;
future decisions are nonbinding predictions and require a new lawful solve.

The common candidate domain uses public service, headway, travel and known
receiver loading-completion breakpoints, including ±0.001 seconds from the
public control period divided by50. This is a timing candidate offset, not a
protection tolerance. All methods use the same actions, objective, lexicographic
tie order, evaluation budget, and strict per-job predicted completion guard.
Strict coordinate, neutral-plateau coordinate, and coupled route/window repair
remain explicit comparators. Unevaluated, invalid and unfinished projections
remain unknown in the candidate denominator. A model guard is not physical
protection; every proposal states that native feasibility, native protection,
delivered online information and a model error bound are uncertified.

## Supported contract and preserved counterexample

The first version accepted an altered `message_delay=1`, `ack_delay=1`, or
`retry=9` while retaining the engine's original timing. The pure counterexample
is preserved in
`outputs/experiments/g31_ics_lt2_sustained_20261014/rolling_contract_counterexample_001/evidence.json`,
including the pre-fix source hash. It is an implementation defect, not evidence
that the new timings work.

Version `public-first-reuse-rolling-v2-strict-fixture` admits only the exact
declared synthetic nine-node topology, outgoing order, service durations,
capacities, all edge headways, four static obligation contracts, and original
protocol values. It additionally requires declared native FIFO/R3/E4/S4/M3
semantics and the 0.001-second minimum service. Unsupported contracts return
unknown before projection; the module does not claim generic network support.
This restriction also prevents clearing historical edge calendars under an
unbounded changed headway. With the fixed fixture, completed-prefix passage
and current stationary states bound the relevant old resource intervals.

The input requires complete source-authorized job/tray/resource coverage, no
unrepresented occupancy, no known faults, and explicitly empty relevant pending
source action lists. Capture and delivery times must be causal, unexpired and
within0.05 seconds. That age limit alone is insufficient: the model checks that
loading, committed service, hold or empty readiness could not have crossed an
autonomous transition between capture and decision. Unknown readiness, an
inflight tray, a receiving lease, conflicting terminal facts or a missed route
window keeps the result unknown. Source metadata in this pure API is declared,
not authenticated; caller-provided provenance cannot set online delivery true.

## Minimal next online facts and causal validation

The existing native `planning_snapshot` contains local waiting/carried jobs,
trays, resource occupancy, public contracts and source-known ready epochs. It
omits completed obligations. The later model therefore cannot truthfully be
connected to it by filling completed-prefix times from offline results.
The smallest additional information is a retained, actually delivered terminal
fact for each completed protected obligation: job identity, destination/source
authority, completion status and epoch, plus immutable capture/delivery identity.
A lawful prior execution ledger with those facts can also supply them. Absence
from a newer planning snapshot is not a completion receipt. Equal completed
prefix costs can cancel only after their shared identities and outcomes have
been established through lawful information.

Relevant unresolved route/transfer operations also need explicit source-local
coverage or a proved restricted continuation. Current planning snapshots do
not carry the Python outbox, so an adapter must not invent an empty list from
silence. Source-known loading completion can support an interval projection
beyond0.05 seconds only after excluding intervening actions/faults that could
invalidate it; this extension is not yet implemented. The old source forecast
captured6.52 and delivered6.53 in the outage gate6 case is a real lawful input,
but alone does not establish a complete later snapshot or all-job outcome vector.

New validation should retain all healthy/outage gates0/6/12, both supported
phases and missing/expired/asymmetric information cases. Compare frozen later
action, one-step coordinate, neutral-plateau coordinate and resource-pair repair
with the same captured information and budget. A causal ablation must suppress
only the new solve or feedback while retaining the same physical checkpoint,
publication traffic, execution semantics and later continuation. First validate
predicted versus native remaining completions and actions on every row, then
assess actual zero-regression against matched controls. No new beneficial case
or outcome-derived parameter has been selected to rescue the current domain.

## Request lineage implementation

`rolling_request_lineage.py` is a declared sidecar contract for future wiring,
not a retrospective interpretation of old controller traces. Admission occurs
before observation and requires scope, a finite one-shot update goal, owner,
trigger, subjects and explicit continuation parents. An independent update may
read an old reservation without continuing its request. Fallback/replacement
must link the unresolved predecessor; a fresh protocol ID does not erase it.

Each submitted operation declares its required terminal statuses. Retries keep
the same payload, operation contract, identity and parents. Actual delivered
ACK handling, including duplicate reads, is timestamped. A final disposition
seal follows all mandatory fallback decisions and registered child completion;
only then may native timestamp drain and returned output close the root. The
limited API requires children to be registered before the seal and rejects
post-seal reopening. Unknown classification remains unknown.

The reported duration is `elapsed_envelope_ms`, acceptance through return,
including waits. This helper has no compute-span or shared-work accounting
ledger and explicitly reports both as unmeasured. It certifies neither complete
runtime instrumentation nor the100ms requirement. The broader distinction and
current controller source census are in
[the lineage design](LT2_BUSINESS_REQUEST_LINEAGE_20261014.md).
