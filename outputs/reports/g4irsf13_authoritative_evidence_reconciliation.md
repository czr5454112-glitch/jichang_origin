# G4IRSF13 Authoritative Evidence Reconciliation

Status: `PASS_BASELINE_FROZEN`.

This report is the single G4IRSF13 authority layer. It does not rewrite any
G4IRSF12 sealed artifact. Older documents remain historical inputs, with
field-scoped supersession recorded in
`outputs/tables/g4irsf13_artifact_freshness_audit.csv`.

## Corrected baseline

| Candidate | Configuration | Original-entry mean | Decision-sensitive mean | v2-safe delta | Hard gates |
| --- | --- | ---: | ---: | ---: | --- |
| F2 frozen | R3/S1/P2/C0 | 41.514218717973 min | 4.143217183651 min | +1.134704 s/bag | PASS |

The corrected raw-entry controls are:

- frozen v2-safe: `41.495306987809 min`;
- parsed historical HCA: `43.135938280418 min`.

F2 therefore beats the corrected historical HCA control, but it does not
beat frozen v2-safe. The old `4.124305453` and `5.764936746` values are
pass-time-anchored control values and must not be compared directly with the
41-minute raw-entry candidate values.

## Reconciled stale statements

1. R3 is no longer `NOT_RUN`: five full F1 repeats and five full F2 repeats
   executed with the R3 runtime echo.
2. Bounded-local P2 integration is no longer merely a design claim: F1/F2
   completed full 1x, while the P0 control retained a censored deadlock
   signature. P0 survivor TTH remains non-comparable.
3. The G4IRSF12 v3 status remains correct that no model was trained, but its
   blanket `MISSING` prerequisite statuses are stale for R3, P2, and 8192.
4. The sealed candidate bundle and full table retain valid execution
   provenance; only their pre-reconciliation performance targets, gates, and
   derived blockers are superseded.

## Claim boundary

F2 is frozen as a control, not silently edited. G4J remains `CLOSED`, phase K
remains `UNKNOWN`, and phase L remains `NOT_RUN` until a new candidate
strictly beats v2-safe, demonstrates independent v3 contribution, passes an
informative fault A/B, and satisfies every original-1x hard gate.
