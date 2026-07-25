# G4IRSF12 sensor-loss recovery repair evidence

## Scope

This note preserves the failed 2,048-segment diagnostic probe that exposed the
recovery gap and the first direct post-fix verification.  It is intentionally
separate from the formal Phase-H ledger: the diagnostic explains the repair,
whereas the formal ledger is the authoritative runtime result.

## Failure retained before repair

- Case: `H_notification_drop`, repeat 1, 2,048 selected segments / 1,047 raw bags.
- Result: `PARTIAL/FAIL`; 1,990/2,048 segments and 989/1,047 raw bags completed.
- Safety: conflict count 0, unsafe entry count 0, no event limit, no time limit.
- Recovery failure: 53 unresolved deadlocks; only 19/59 affected bags completed.
- Binary SHA-256: `34a1c422c8c164144416acc55cdbaaff429beb0d582b425979691812b65fc3e3`.
- Source-bundle SHA-256: `a123805baeca8150ce27715b87d77ed8d043572becf7cab7c39c02e9462bb9ad`.
- Executor-source SHA-256: `e1b59eecded76f59991a9276f614aea747a573dbaffdf2139cfd9b6096b69971`.
- Case-config SHA-256: `73122a2aa306d1e5d8bb5c101e60a464bc0f7b5e5ad3812bf41c983e65948325`.
- Deterministic-result SHA-256: `641f9dd0b5ce13819e904139444e0ba601ad33ae44b7258b7f5b3160b46bc93f`.

The same probe for `H_fault_policy_off` produced the same completion and
deadlock counts.  That equality identified a real integration defect rather
than random instability: P2 correctly disabled legacy `enable_pibt_lite`, but
the physical-interlock alternative-edge handoff was still hidden behind that
legacy switch.  With notifications dropped, the enabled recovery policy was
therefore behaviorally identical to the policy-off control.

## Repair boundary

After the physical interlock rejects the preferred edge, an enabled recovery
policy may now select one safe alternative from the candidates already
materialized at the current junction.  The policy-off control still holds.
This handoff does not use A*, a global reservation scan, a future route, or a
multi-step reservation, and it does not increment the legacy PIBT-lite
counter.

The evidence schema now records the fault-policy echo, sensor-loss mode,
dropped-notification count, and physical-interlock rejection/hold/reroute
counts separately from advertised-fault policy actions.  Prior evidence with
any of those sensor-loss fields removed or altered is rejected.

## Historical direct post-fix verification

- Case: `H_notification_drop`, 2,048 selected segments / 1,047 raw bags.
- Result: `EXECUTED/PASS`, `DRAINED`; all 2,048 segments and all 1,047 bags completed.
- Safety: conflict count 0, unsafe entry count 0, unresolved deadlock count 0;
  no event limit and no time limit.
- Fault cohort: 117/117 affected bags completed.
- Lost-notification evidence: `sensor_loss_mode_used=true`, exactly 2 dropped notifications.
- Physical interlock: 117 rejections, 0 holds, 117 one-edge local reroutes.
- Binary SHA-256: `09c4979396e50c36fa668d662c4ea8481b8ac3ec41572810aa695a0da1603a6c`.
- Source-bundle SHA-256: `c8f732efd8c0b34fb301fc87cb7fd70e32c0685c8c19aefb54e3af4cb527f057`.
- Executor-source SHA-256: `e1b59eecded76f59991a9276f614aea747a573dbaffdf2139cfd9b6096b69971`.
- Case-config SHA-256: `73122a2aa306d1e5d8bb5c101e60a464bc0f7b5e5ad3812bf41c983e65948325`.
- Deterministic-result SHA-256: `c06d980a005b5466cfdc0f65377c6c30f344e33b6d4981ad3ef44b18adaa9332`.

This direct verification is historical diagnostic evidence only.  It explains
the defect and verifies the local repair, but it is not substituted for the
formal evidence below.

## Current formal Phase-H evidence

The current v4 formal ledger is
[`g4irsf12_fault_recovery_stable_load.csv`](../tables/g4irsf12_fault_recovery_stable_load.csv).
It records all five Phase-H scenarios (`H_stable_no_fault`, `H_immediate`,
`H_delayed_30s`, `H_notification_drop`, and `H_fault_policy_off`) at each of
2,048, 8,192, and 43,603 selected segments.  Every scenario-and-size cell has
five deterministic repeats (75 rows total): each row is `EXECUTED`,
`EXECUTED_RESULT_VALIDATED`, `DRAINED`, and gate `PASS`.

This supersedes the former statement that formal H evidence still needed to
be generated.  The historical failure above remains retained as a diagnostic
negative result; it is not a current formal H row and is not used to weaken or
inflate the v4 result.  A formal `PASS` for the policy-off control means that
its separately specified control gate was satisfied.  It does not license a
claim that disabling recovery policy is equivalent to enabling it, nor does it
alter the always-on physical interlock boundary.
