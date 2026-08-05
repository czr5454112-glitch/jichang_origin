# G4IRSF16 sparse externality model

Status: `DIAGNOSTIC_SMALL_HEAD_NOT_INDEPENDENTLY_PROMOTED`.

The 232 selectable H_system rows support a small local-proxy diagnostic only. B0/B1/B2 budgets are fixed in the model metadata; B2 is diagnostic-only. Extra deadline miss is zero throughout the selectable panel, so that head is explicitly not trainable.

The B1 CVaR95 threshold is preregistered metadata, not a passed gate: this release has no calibrated CVaR upper-bound head. Status is `NOT_EVALUATED_NO_CVAR_UCB_HEAD`, so externality promotion remains forbidden.

Final-audit externality outcomes are excluded from the published risk table and remain `SEALED_NOT_CONSUMED`.

Validation externality ECE: `0.193309200`.
