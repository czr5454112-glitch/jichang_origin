# Runtime005 capture-time repair: pure riskcase

These are reachable synthetic public observations passed through the real
inventory view, PreparedCurrent, PreparedProjection and transport solver. They
are not an allegation that the behavior occurred in the native003 runs. No
native constructor or native session was used by the reproduction or tests.
Frozen003 and frozen004 bytes were not changed. Runtime004 had no successor
native start before its supervisor superseded the waiting workflow.

At physical time 60, a delivered peer capture from time 2 remains legal until
time 122. A tray can therefore have a delivered receipt at time 30 while the
observer still sees an older source or destination capture. Passing message TTL
validation does not make that capture later than the receipt.

1. **Third owner without the sender's request ledger.** B's tray B0 is shown at
   source 1 in capture 2; the coordinator has B's received order for destination
   2 at time 30. Frozen004 orders returned `{}` for the outstanding receiver
   claim and the solver allocated another empty tray E0 from owner A to node 2.
   Working005 returns `{2: 1}` and the same pure solve returns HOLD, with no
   chosen move. A fresh source/destination capture at or after receipt releases
   the claim; a missing receipt time does not.
2. **Sender's own request ledger.** A's request r1 was issued at time 10 and
   received at time 30, but B's still-valid destination capture from time 2
   contains B0 from its earlier cycle. Frozen004 treated this as current stock
   and recorded `commitment_already_covered_by_capture`. Working005 preserves
   raw snapshot identity-count validation (known inventory remains true),
   removes the superseded actual identity from usable stock, and records exactly
   one accepted-inbound event for r1. Stock is 0, inbound is 1; it never adds old
   stock and the receipt twice. A capture at/after receipt instead gives stock 1,
   inbound 0. With unknown receipt time there is no covered or inbound claim;
   captures predating issuance do not become usable current stock.
3. **Retained same-tray request history.** Native030's
   `cpp/ics_core/bindings/circulation_session_binding.hpp:543` iterates every
   owner protocol request and retains historical receipts in both public and
   compact policy ledgers. With old r1 received at 20, later r2 issued at 40
   and confirmed accepted, and valid capture 2, frozen004 raises
   `one_live_accepted_commitment_per_tray`. When both records are received,
   frozen004 instead incorrectly marks both as covered by the old capture;
   the first intermediate time-comparison repair exposed their duplicate
   inbound credits before the final history repair. Working005 explicitly supersedes
   historical r1 using r2's delivered commitment and creates only r2's one
   inbound supply. This works regardless of ledger row order. A pending or
   rejected r2 does not supersede r1 or create new physical supply; two genuinely
   live accepted commitments still fail closed. The superseded old logical
   claim is removed by its separately named audit reason, not fabricated
   capture evidence.

Run `python outputs/experiments/g31_ics_terminal_flow_20261021/claim_capture_fix005_001/reproduce.py`
from the worktree. It reads the immutable frozen004 implementations to reproduce
the before state, then applies the working005 implementations to identical legal
inputs. It prints JSON and does not launch native or mutate Git. The recorded
inputs, selected views, outputs and code hashes are in `riskcase_results.json`.

The repair changed only working `foundation_airport_transport_orders.py` and
`foundation_airport_inventory_projection.py` plus the two focused test files.
There are 31 new parametrized regression cases: cross-owner claim and HOLD
behavior, stale/fresh source and destination captures, missing receipt, own
sender deduplication, one-use stock/inbound conservation, and accepted-request
issuance timing, retained request history and pending/confirmed distinctions.
The combined relevant suite passed **84 tests** including all
24 existing joint-projection cases. Evidence is
`outputs/terminal_claim_capture_fix005_projector.xml`; the first orders-only
pass is `outputs/terminal_claim_capture_fix005.xml` (40 tests).

`test_g31_terminal_transport_claims_before005.py` contains the original test
bytes, restored by reversing this patch and accepted only after matching SHA256
`75d3a721257901328a3f0fd7041796d861e2c4e1b6f1ef0f29d62486e160bb6b`
in runtime004's `pure_gate_001.json`. `provenance.json` binds that gate, the old
test, changed working files and the new evidence. The original test was not
substituted into frozen004 or any active process.

The projector change is shared by all methods. Prior native results retain
their own source binding; behavior equivalence across 004/005 must be tested
strictly, and a failed equivalence bridge must not be waived. This pure riskcase
establishes an engineering defect and its repair, not a native service gain or
a complete ICS optimum.
