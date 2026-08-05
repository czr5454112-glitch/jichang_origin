# G4IRSF16 I4 selective-hold training

Offline result: `I4_SELECTIVE_MODEL_NO_GO`.

Validation metrics: `{"activation_count": 0, "activation_coverage": 0.0, "beneficial_activation_count": 0, "beneficial_precision": 0.0, "beneficial_recall": 0.0, "direct_benefit_mean_seconds": null, "direct_benefit_sum_seconds": 0.0, "externality_cvar95_max_seconds": null, "externality_cvar95_mean_seconds": null, "harmful_activation_count": 0, "harmful_activation_rate": 0.0, "high_confidence_harmful_precision": 0.0, "neutral_activation_count": 0, "neutral_activation_rate": 0.0, "risk_adjusted_utility_lcb_seconds": null, "risk_adjusted_utility_mean_seconds": null, "risk_adjusted_utility_sum_seconds": 0.0, "row_count": 164, "target_panel_abstention_rate": 1.0}`

Validation benefit ECE: `0.003254801`.

D0 is a cluster-bootstrap ensemble of calibrated linear heads with utility LCB, harmful UCB, OOD abstention, and an exact ID-free feature schema. Failure of any preregistered check is a formal no-go, not a request to tune on validation or audit.
