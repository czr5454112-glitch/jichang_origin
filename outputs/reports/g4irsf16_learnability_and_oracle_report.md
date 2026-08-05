# G4IRSF16 learnability and oracle report

## Decision

- I3 rare override: `I3_REROUTE_MODEL_NOT_AUTHORIZED`; risk-veto-only remains trainable.
- I4 support authorization: `NOT_AUTHORIZED`. D0 is retained only as a strict support/validation diagnostic and has no deployment authority.
- Final audit remains `SEALED_NOT_CONSUMED`; its label support did not enter authorization, fitting, threshold selection, rule selection, or promotion.

## Support

| Kind | Split | Beneficial | Neutral | Harmful |
| --- | --- | --- | --- | --- |
| I3 | train | 13 | 18 | 623 |
| I3 | calibration | 3 | 5 | 157 |
| I3 | validation | 3 | 4 | 143 |
| I4 | train | 14 | 207 | 457 |
| I4 | calibration | 3 | 46 | 104 |
| I4 | validation | 3 | 50 | 111 |

## Oracle boundary

Oracle rows use realized outcomes only as a non-deployable upper bound on train+calibration+validation. They never enter runtime features, and final audit remains sealed. The risk-constrained oracle activates only rows with observed utility above zero.

Implemented: all selectable-state outcome oracle, top 0.25/0.5/1/2/5% outcome oracles, and the risk-constrained positive-utility oracle. Separate no-node-ID, held-out-source, and held-out-time generalization oracles are `NOT_EVALUATED_SUPPORT_NO_GO`; they are not treated as passes after the pre-audit support gate failed.

## New evidence

The selectable partitions contain only 19 beneficial I3 rows (13/3/3), below the preregistered 24/6/6 pre-audit minima. I4 contains only 20 selectable positives (14/3/3), below the 24-row support gate. The four final-audit positives are sealed and cannot flip authorization. D0 nevertheless provides a deterministic strict-gate diagnostic; it has zero validation activations and remains a formal no-go.
