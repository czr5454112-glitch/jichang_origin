# G4IRSF16 Stage 16L fault supervisor contract regression

## Scope

This is a synthetic, deterministic state-machine regression against the real Python supervisor contract. It is not a native runtime fault campaign, full closed-loop experiment, TTH measurement, or active multi-fault benefit claim.

## Results

| Case | Events | Terminal state | Stale rejects | Repair entries | PIBT commit | Unsafe | Pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| no_fault | 1 | F2_NORMAL | 0 | 0 | 0 | 0 | True |
| physical_shield | 1 | FAULT_RECOVERY | 0 | 0 | 0 | 0 | True |
| delayed_message | 4 | FAULT_RECOVERY | 2 | 0 | 0 | 0 | True |
| dropped_message | 4 | F2_NORMAL | 0 | 1 | 0 | 0 | True |
| repair_reopen | 3 | F2_NORMAL | 0 | 1 | 0 | 0 | True |
| i4_hold_fault | 4 | F2_NORMAL | 0 | 1 | 0 | 0 | True |
| i3_prepare_fault | 4 | F2_NORMAL | 0 | 1 | 0 | 0 | True |
| pibt_transaction_fault | 4 | PIBT_RECOVERY | 0 | 1 | 2 | 0 | True |
| full_astar_request_forbidden | 1 | SAFE_HOLD | 0 | 0 | 0 | 0 | True |

## Enforced invariants

- `unsafe = 0` under the published local contract definition.
- Delayed physical-fault and node-generation messages are rejected; a dropped intermediate generation cannot keep an old token alive.
- Repair re-entry occurs exactly once per simulated fault episode, including I4 hold, I3 prepare, and PIBT transaction interruption.
- A fault between PIBT prepare and consume aborts the whole old batch; a fresh post-repair batch commits completely and can be consumed once.
- Full A* is not an action source and every request is rejected to SAFE_HOLD with `used_full_astar = false`.

## Interpretation boundary

Passing this report establishes only the listed supervisor-level fault contracts. Native event transport, BTI/DDI integration, traffic performance, and original-scale closed-loop safety still require their separate campaigns.
