# G4IRSF21 complete local Route action sets

Status: **COMPLETE_ACTION_SET_TARGET_MET**

The controller is unchanged: `Source A0 + Route S4 + Merge J2 + E2`.
Each retained group labels S4, every other shield-legal one-hop edge,
and one native I4 WAIT from the same pre-action state.

- requested complete H_bag groups: 16
- screened groups: 24
- fully complete groups before quota: 24
- persisted complete groups: 16
- distinct original tasks: 8
- executed real treatments: 48
- NEXT_EDGE labels: `HARMFUL=16, NEUTRAL=16`
- WAIT labels: `HARMFUL=16`

Utilities are measured in seconds as baseline completion minus treatment
completion; positive values are better.

WAIT has no fabricated edge feature vector. No native pair rows, full-system
outcomes, learned model, or runtime policy are persisted or promoted.
The 16 groups cover 8 distinct original tasks. The `split_group` metadata enables
a later grouped split to keep one task's runtime segments together.
Selection keeps the earliest eligible events within each wait stratum, so this
is a small 1x H_bag contract check, not a representative performance sample.
Any future learning campaign must use grouped-even sampling by original task;
these rows do not support a learned-policy or performance claim.
