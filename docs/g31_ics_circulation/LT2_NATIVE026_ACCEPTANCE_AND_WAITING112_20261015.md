# Native026 acceptance and the bounded waiting112 gate

## Accepted native026 scope

Native026 replaces repeated delivered-message selection scans with a derived
delivery journal and binding index. It retains canonical histories, fields,
vector order, checkpoint bytes and public API behavior. Journal allocation
failure is sticky and falls back to canonical scans. Restore/fork rebuild the
derived state; duplicate delivery timestamps are read from canonical state.
The receipt scan guard is the exact disjunction already tested inside the old
loop. Neither change alters routing, FIFO, capacity or the controller policy.

The binary is
`build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd`, SHA-256
`c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943`.
Its build authority is
`outputs/experiments/g31_ics_lt2_sustained_20261014/native026_build_001/receipt.json`
and the adjacent `source/` archive of 67 compiled source files. The build took
70.4913117 seconds, used one compiler job, and did not run CTest.

Evidence under the same output root:

- `observation_index_standalone_001`: standalone derived-structure tests,
  including allocation failure, late delivery, ties, expiry and rollback;
  no NativeSession.
- `native026_focused_001`: 12 actual native tests passed, 4.64465 seconds.
- `native026_legacy_contract_001/ordered_validation.json`: 20 old-contract
  native025/native026 branches passed ordered public-view, state and seal
  comparisons. This does not claim a new v2 planning runtime campaign.
- `delivery_gate_pure_001.xml`: 12 pure evidence/authority rejection tests.
- `native026_acceptance_001`: all three worker arms exited zero, total
  1187.2875079 seconds. `post_gate_identity.json` verifies the binaries,
  all 67 compiled source/archive hashes, the 47-file tested Python closure
  and both separately protected `bounded_local_pibt.hpp` copies.

The late gate replayed actual native024 parts 0–268 from
`full024_resume_native_001`. Before exposing the reconstructed session, it
matched the contemporaneous H54000 seal exactly:
`ba49c0393be8041544a122bb7da45aab57be8419c04c907b950943b6bd18134d`.
Reconstruction took 843.2375985 seconds. Both native026 reference/indexed
continuations then matched the saved next 500-owner shard in ordered raw
semantics and public views. Their final seals were identical:
`fd56f8c06b2eaf9a5ea6b8b3204d021e7fdd06b53c98494f2018733b7e037f4d`.
That next original shard had no contemporaneous exit seal; none is invented.

The same-binary serial continuation pair measured 15.404048 seconds with the
reference selector and 8.1961013 seconds with indexing. A root native024
reconstruction ran concurrently. This single, non-isolated pair is evidence
of a measured reduction in this case, not a stable speedup, full-day completion
or 100 ms certificate. Any later binary migration still requires its own
actual source-cut seal before continuation.

The acceptance parent receipt SHA-256 is
`ec0bf85b9a4be4030ed13209c75656ee2b83910235f76bec652943ae98ba99df`.

## Why a waiting112 experiment is lawful to test

`cpp/ics_core/runtime/circulation_runtime_impl.hpp` checks a route intent's
actual current node, stationary edge state, generation, public traversal,
active leg, owner, business identity and explicit suffix permission. It checks
the next edge, the current stage goal, deadline and `can_enter`. There is no
rule limiting submission to the first 1.5 seconds of junction service. An
accepted intent wakes a matching resource wait through
`cpp/ics_core/runtime/circulation_recovery_impl.hpp`.

This is only eligibility for a native attempt. In
`cpp/ics_core/runtime/event_driven_junction.hpp`,
`apply_circulation_route_preference` changes a candidate score only when the
candidate remains shield-allowed and has no advertised fault. Native junction
arbitration and FIFO still choose the admissible physical action.
`cpp/ics_core/runtime/circulation_protocol_commands_impl.hpp` applies the
route after the protocol's immutable wire delay and enqueues the native route
at zero additional delay. The gate keeps the original two-second wire delay.

The unchanged research input is
`original_tie_streamed_native_002/input.json.gz`, SHA-256
`eb4f9baab3dc772d4812134341a2741187fc8258756f304020d719f771e62b68`:
28,506 jobs, 22 initial trays, original physical contracts and communication,
with the already declared all-job suffix permission. It is not a claim that
the original permission-disabled input has been repaired. Nodes 112 and 113
are both owned by `owner:system_domestic`; node113 capacity is four and the
112→113 edge capacity is one. The saved no-chain control has a long wait at
112 beginning after 9553.737986. This is an offline motivation only; no bag ID,
future waiting time or saved result is used to choose the gate action.

## Prepared experiment, not yet run

`scripts/experiments/g31_ics_circulation/research_original_waiting112.py` is a
separate opt-in driver. It neither edits nor patches the frozen production
controller or native implementation. At complete native boundaries, it samples
the current source-owner view on a predeclared 60-second cadence before
submission. In the first qualifying snapshot it orders candidates by arrival,
business ID and tray ID. It requires two stationary observations with identical
tray/job/generation/traversal/prefix, at least `2 + service(112) = 3.5` seconds
apart, a loaded pre-Storage53 job, explicit suffix permission, and current local
113 occupancy below capacity. Public static positive-capacity reachability
113→53 must exist without returning through112. This reachability check is not
a reservation or a guarantee that native shielding will accept the edge.

The driver submits one immutable 112→113 route request with two-second delay;
retries repeat that request only. It continues the ordinary R2 controller with
routes disabled, forecasts/predictive/prebalance enabled, 60-second control and
retry periods, 0.5-second publication delay and 120-second leases. It injects
none of the earlier four-chain commands. H12000, 100,000 owner activations,
the native event bound and a 600-second parent timeout are fixed in advance.

Success requires both a delivered updated ACK and an actual current inflight
edge with a native `edge_exit_at` derived from its matched, already observed
`EDGE_ENTER` receipt, or a newly completed `EDGE_EXIT` prefix proving 112→113
for the same tray/job/generation. `edge_to` alone is a reservation and may be
published before entry actually occurs; it is recorded separately and cannot
pass the gate. An updated ACK alone is insufficient. A terminal outcome stops after the
current returned 500-activation raw shard is persisted. Every returned raw
controller shard and every gate API observation/query/submission is retained.
The saved API tape is replayed purely through the real ProtocolClient and gate
logic; source, input, compiled authority and output hashes are checked.

`tests/test_g31_circulation_waiting112.py` passed 48 pure cases with command:

```text
python -m pytest tests/test_g31_circulation_waiting112.py -q --basetemp=outputs/experiments/g31_ics_lt2_sustained_20261014/pytest_waiting112_004 --junitxml=outputs/experiments/g31_ics_lt2_sustained_20261014/waiting112_pure_004.xml
```

The prepared archive is
`outputs/experiments/g31_ics_lt2_sustained_20261014/original_waiting112_prepare_003`.
The earlier `_001` and `_002` archives remain unchanged and unexecuted. R1's
independent source review found that those versions could mistake a future
reservation for actual entry. Version `_003` fixes that evidence gate; seven
additional cases reject reservation-only or invalid entry timing and permit
later proof through a completed edge prefix. The expanded second test run
retains one Windows PermissionError during an atomic diagnostic manifest
replacement (`waiting112_pure_002.xml`). The new driver now retries only that
error at most six times, with 150 ms total maximum diagnostic delay, then
propagates failure while preserving the complete temporary file. The final
suite tests transient and permanent failure, actual ProtocolClient same-ID
immutable retries, changed-payload rejection, updated-ACK/other-edge and
updated-ACK/no-edge cases. No policy clock or physics is changed by this
diagnostic retry.
No NativeSession has been run for this gate. Its result is currently unknown.
Even a future successful execution would prove only this bounded action's
executability, not business benefit, all-offered protection, deadlock freedom,
solver novelty or 100 ms compliance. No multi-hop reservation, capacity increase
or FIFO amendment is included.
