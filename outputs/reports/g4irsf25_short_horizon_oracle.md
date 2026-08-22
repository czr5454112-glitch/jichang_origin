# G4IRSF25 short-horizon corridor oracle

This campaign reuses the existing exact same-checkpoint causal runner.  The
only treatment is a registered first edge; both branches then return to the
ordinary S4/J2/E2 controller and stop at reconvergence plus settling, or at the
retained 600 second cap.

After the registered-arm legality screen, census sampling keeps only the
earliest event ordinal for each `(runtime_bag_id, current_node)`.  That row is
the bag's new merge-request decision; later wakeups belong to the already
created request and cannot change its first edge.  This filter uses no branch
result or future outcome.

- Status: `TARGET_MET`
- Complete independent checkpoints: 1,024
- Complete by load: {"1": 512, "2": 512}
- Complete by branch: {"16": 256, "19": 256, "6": 256, "9": 256}
- Failed/incomplete checkpoints: 0
- Arm labels: 2,048
- Retained timeout arms: 483
- Unsafe arms: 0

## Action ceilings from the same paired data

- Full-state mean possible local-system improvement: 2268.991082 bag-seconds
- Full-state mean improvement fraction: 56.209%
- Alternative-win fraction: 53.125%
- Opportunity mass: 2323446.867805
- Local-observation pairwise ranking ceiling: 90.039%
- Local-observation mean regret ceiling: 73.771719 bag-seconds

## Leakage and scope

The 21 model inputs are reconstructed only from the decision-time Route
candidate observation.  A native checkpoint has no preceding G25 feedback
stream, so short EWMA, long EWMA and trend are explicitly zero; feedback age is
600 seconds, sample count is zero and timeout rate is zero.  Counterfactual
outcomes never enter the input vector.  Checkpoint, task and event identities
are retained only under `identity_metadata` for grouping and audit.

Private cost is affected-bag time to reconvergence.  Local-system cost is the
online integral of queue plus scheduled incoming over the union of the two
registered corridors plus the canonical map's outgoing neighborhood at their
rejoin node.  This is the same fixed node domain for every arm in a checkpoint;
it is not a runtime global scan.  Timeout examples remain finite high-cost
examples and are not dropped.  This is a local short-horizon oracle, not an
H_system claim.
