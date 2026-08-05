from __future__ import annotations

import math

import pytest

from czr005.g4irsf16.offline import (
    OfflineContractError,
    activation_summary,
    authorization,
    gate_i4,
    i3_rules,
    selectable_rows,
)


def _row(split: str, label: str, utility: float = 1.0) -> dict[str, object]:
    return {
        "split": split,
        "final_audit_status": "SEALED_NOT_CONSUMED" if split == "final_audit" else "NOT_FINAL_AUDIT",
        "signed_class": label,
        "direct_benefit_seconds": utility,
        "risk_adjusted_utility_seconds": None,
        "other_bag_cvar95_harm_seconds": None,
    }


def test_final_audit_cannot_enter_selection() -> None:
    rows = [_row("train", "BENEFICIAL"), _row("final_audit", "HARMFUL", -1.0)]
    assert len(selectable_rows(rows, "train")) == 1
    with pytest.raises(OfflineContractError, match="FINAL_AUDIT_SELECTION_FORBIDDEN"):
        selectable_rows(rows, "final_audit")


def test_activation_metrics_use_eligible_state_harm_budget() -> None:
    rows = [_row("validation", "BENEFICIAL", 2.0), _row("validation", "HARMFUL", -4.0)]
    metrics = activation_summary(rows, [True, False])
    assert metrics["beneficial_precision"] == 1.0
    assert metrics["harmful_activation_rate"] == 0.0
    assert metrics["activation_coverage"] == 0.5
    assert metrics["target_panel_abstention_rate"] == 0.5
    assert metrics["risk_adjusted_utility_lcb_seconds"] is None


def test_harmful_activation_rate_uses_all_eligible_states() -> None:
    rows = [
        _row("validation", "HARMFUL", -1.0),
        _row("validation", "HARMFUL", -1.0),
        _row("validation", "NEUTRAL_WITHIN_TOLERANCE", 0.0),
        _row("validation", "BENEFICIAL", 1.0),
    ]
    metrics = activation_summary(rows, [True, False, False, False])

    assert metrics["harmful_activation_rate"] == 0.25
    assert metrics["high_confidence_harmful_precision"] == 1.0


def test_i3_authorization_fails_closed_below_split_minima() -> None:
    i3 = []
    i4 = []
    for split, positives in (("train", 23), ("calibration", 5), ("validation", 5), ("final_audit", 5)):
        i3.extend(_row(split, "BENEFICIAL") for _ in range(positives))
        i3.extend(_row(split, "HARMFUL", -1.0) for _ in range(32))
        i4.extend(
            _row(split, "BENEFICIAL")
            for _ in range(0 if split == "final_audit" else 8)
        )
        i4.extend(_row(split, "HARMFUL", -1.0) for _ in range(64))
    result = authorization(i3, i4)
    assert result["i3_rare_override"]["status"] == "I3_REROUTE_MODEL_NOT_AUTHORIZED"
    assert result["i3_rare_override"]["candidate_complete_campaign_authorized"] is False
    assert result["i4_selective_hold"]["status"] == "AUTHORIZED_FOR_OFFLINE_TRAINING"
    assert result["final_audit"]["label_support_read_for_authorization"] is False
    assert result["final_audit"]["row_level_outcomes_used_for_selection"] is False


def test_final_audit_positive_support_cannot_flip_i4_authorization() -> None:
    i3 = [_row("train", "HARMFUL", -1.0)]
    i4 = []
    for split in ("train", "calibration", "validation"):
        i4.extend(_row(split, "BENEFICIAL") for _ in range(7))
        i4.extend(_row(split, "HARMFUL", -1.0) for _ in range(64))
    i4.extend(_row("final_audit", "BENEFICIAL") for _ in range(100))

    result = authorization(i3, i4)

    assert result["i4_selective_hold"]["status"] == "NOT_AUTHORIZED"
    assert "final_audit" not in result["i4_selective_hold"]["support"]
    assert result["final_audit"]["row_count"] == 100


def test_i4_gate_requires_positive_multi_activation_lcb() -> None:
    metrics = {
        "activation_count": 1,
        "activation_coverage": 0.004,
        "beneficial_precision": 1.0,
        "harmful_activation_rate": 0.0,
        "high_confidence_harmful_precision": 0.0,
        "target_panel_abstention_rate": 0.996,
        "risk_adjusted_utility_lcb_seconds": None,
    }
    result = gate_i4(metrics, ece=0.01)
    assert result["status"] == "I4_SELECTIVE_MODEL_NO_GO"
    assert result["checks"]["utility_lcb"] is False
    assert math.isfinite(result["ece"])


def test_i3_r4_accepts_a_real_zero_model_margin() -> None:
    row = {
        "static_potential_delta_seconds": 1.0,
        "target_queue_length": 0.0,
        "target_next_available_wait_seconds": 0.0,
        "deadline_slack_seconds": 1.0,
        "f2_model_margin": 0.0,
        "advertised_fault": False,
        "task_class": "direct",
        "current_node_type": 1,
        "signed_class": "BENEFICIAL",
    }
    r4 = next(rule for rule in i3_rules([row]) if rule.name == "R4")

    assert r4.mask(row) is True
