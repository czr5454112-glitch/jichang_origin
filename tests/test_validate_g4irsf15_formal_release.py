from __future__ import annotations

from pathlib import Path

from scripts import validate_g4irsf15_causal_campaign as validator
from scripts import validate_g4irsf15_formal_release as release_validator


def test_formal_null_round_is_normalized_only_for_compact_path_helper(
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_collect(
        root: Path,
        campaign: str,
        plan: dict[str, object],
        **kwargs: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        observed.update(
            root=root,
            campaign=campaign,
            plan=plan,
            kwargs=kwargs,
        )
        return [], []

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_COLLECT_COMPACT_EVIDENCE_LABELS",
        fake_collect,
    )
    original_plan: dict[str, object] = {
        "schema": validator.PLAN_SCHEMA,
        "campaign": "formal",
        "pilot_round": None,
    }

    result = (
        release_validator
        ._collect_compact_evidence_labels_with_formal_null_round(
            Path("repo"),
            "formal",
            original_plan,
            evidence_bindings=[{"evidence_index": 0}],
            baseline_binding={"path": "baseline"},
            run_state_attestation={"status": "EPHEMERAL"},
        )
    )

    assert result == ([], [])
    assert original_plan["pilot_round"] is None
    assert observed["plan"] is not original_plan
    assert observed["plan"]["pilot_round"] == 1
    assert observed["campaign"] == "formal"


def test_formal_non_null_round_fails_closed(monkeypatch) -> None:
    def unexpected_collect(*args: object, **kwargs: object) -> object:
        raise AssertionError("frozen collector must not be called")

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_COLLECT_COMPACT_EVIDENCE_LABELS",
        unexpected_collect,
    )

    try:
        release_validator._collect_compact_evidence_labels_with_formal_null_round(
            Path("repo"),
            "formal",
            {
                "schema": validator.PLAN_SCHEMA,
                "campaign": "formal",
                "pilot_round": 1,
            },
            evidence_bindings=[],
            baseline_binding=None,
            run_state_attestation={},
        )
    except validator.ValidationError as exc:
        assert str(exc) == "FORMAL_RELEASE_COMPAT_PLAN_DRIFT"
    else:
        raise AssertionError("non-null formal round must fail closed")


def test_pilot_round_and_plan_identity_are_unchanged(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_collect(
        root: Path,
        campaign: str,
        plan: dict[str, object],
        **kwargs: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        observed["plan"] = plan
        return [], []

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_COLLECT_COMPACT_EVIDENCE_LABELS",
        fake_collect,
    )
    pilot_plan: dict[str, object] = {"pilot_round": 2}

    release_validator._collect_compact_evidence_labels_with_formal_null_round(
        Path("repo"),
        "pilot",
        pilot_plan,
        evidence_bindings=[],
        baseline_binding=None,
        run_state_attestation={},
    )

    assert observed["plan"] is pilot_plan
    assert pilot_plan["pilot_round"] == 2


def test_formal_compact_namespace_is_round_independent() -> None:
    assert validator.compact_evidence_path(
        "formal", 7, pilot_round=1
    ) == validator.compact_evidence_path("formal", 7, pilot_round=999)
    assert validator.compact_evidence_path(
        "pilot", 7, pilot_round=1
    ) != validator.compact_evidence_path("pilot", 7, pilot_round=2)


def test_main_restores_frozen_collector(monkeypatch) -> None:
    original_collect = validator.collect_compact_evidence_labels
    original_validate_label = validator.validate_label
    monkeypatch.setattr(validator, "main", lambda argv: 0)

    assert release_validator.main([]) == 0
    assert validator.collect_compact_evidence_labels is original_collect
    assert validator.validate_label is original_validate_label


def test_empty_realized_outcomes_are_narrowly_normalized(monkeypatch) -> None:
    observed: dict[str, object] = {}
    original_strict_int = validator.strict_int

    def fake_validate_label(row: dict[str, object]) -> None:
        observed["row"] = row
        observed["compat_count"] = validator.strict_int(
            0,
            "label.realized_outcome_deltas_binding.row_count",
            1,
        )

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_VALIDATE_LABEL",
        fake_validate_label,
    )
    empty_sha = validator.canonical_fields_sha256(
        [
            (
                "schema",
                "s",
                "czr005.g4irsf15.realized_outcome_deltas.v1",
            ),
            ("row_count", "u", 0),
        ]
    )
    row: dict[str, object] = {
        "schema": validator.LABEL_SCHEMA,
        "kind": "I4",
        "horizon": "H_system",
        "action_changed": True,
        "eligible_causal_label": True,
        "horizon_complete": True,
        "evidence_complete": True,
        "realized_affected_set_observable": True,
        "system_externality_observation_status": "OBSERVED_AT_H_SYSTEM",
        "realized_affected_runtime_bag_ids": [],
        "realized_direct_runtime_bag_ids": [],
        "externality_runtime_bag_ids": [],
        "direct_affected_runtime_bag_ids": [7],
        "realized_outcome_deltas_sha256": empty_sha,
        "realized_outcome_deltas_binding": {
            "row_count": 0,
            "content_sha256": empty_sha,
        },
        "cohort_difference_sidecar_binding": {
            "schema": (
                "czr005.g4irsf15.full_cohort_outcome_difference.v1"
            ),
            "row_count": validator.FULL_SEGMENT_COUNT,
            "changed_count": 0,
            "complete_coverage": True,
            "runtime_id_order": "CONTIGUOUS_ZERO_BASED_INPUT_ORDER",
            "content_sha256": validator.canonical_sha256("cohort"),
        },
    }
    row["label_sha256"] = validator.canonical_sha256(row)

    release_validator._validate_label_with_empty_realized_outcomes(row)

    assert row["realized_outcome_deltas_binding"]["row_count"] == 0
    assert observed["row"] is row
    assert observed["compat_count"] == 1
    assert validator.strict_int is original_strict_int


def test_empty_realized_outcomes_content_drift_fails_closed(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_VALIDATE_LABEL",
        lambda row: None,
    )
    wrong_sha = validator.canonical_sha256([{"unexpected": True}])
    row: dict[str, object] = {
        "horizon": "H_system",
        "action_changed": True,
        "eligible_causal_label": True,
        "horizon_complete": True,
        "evidence_complete": True,
        "realized_affected_set_observable": True,
        "system_externality_observation_status": "OBSERVED_AT_H_SYSTEM",
        "realized_affected_runtime_bag_ids": [],
        "realized_direct_runtime_bag_ids": [],
        "externality_runtime_bag_ids": [],
        "realized_outcome_deltas_sha256": wrong_sha,
        "realized_outcome_deltas_binding": {
            "row_count": 0,
            "content_sha256": wrong_sha,
        },
    }
    row["label_sha256"] = validator.canonical_sha256(row)

    try:
        release_validator._validate_label_with_empty_realized_outcomes(row)
    except validator.ValidationError as exc:
        assert str(exc) == (
            "FORMAL_RELEASE_COMPAT_EMPTY_REALIZED_OUTCOMES_DRIFT"
        )
    else:
        raise AssertionError("non-empty content hash must fail closed")


def test_empty_realized_delegate_failure_restores_strict_int(
    monkeypatch,
) -> None:
    original_strict_int = validator.strict_int

    def failing_validate_label(row: dict[str, object]) -> None:
        assert validator.strict_int is not original_strict_int
        raise validator.ValidationError("DELEGATED_FAILURE")

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_VALIDATE_LABEL",
        failing_validate_label,
    )
    empty_sha = validator.canonical_fields_sha256(
        [
            (
                "schema",
                "s",
                "czr005.g4irsf15.realized_outcome_deltas.v1",
            ),
            ("row_count", "u", 0),
        ]
    )
    row: dict[str, object] = {
        "schema": validator.LABEL_SCHEMA,
        "kind": "I4",
        "horizon": "H_system",
        "action_changed": True,
        "eligible_causal_label": True,
        "horizon_complete": True,
        "evidence_complete": True,
        "realized_affected_set_observable": True,
        "system_externality_observation_status": "OBSERVED_AT_H_SYSTEM",
        "realized_affected_runtime_bag_ids": [],
        "realized_direct_runtime_bag_ids": [],
        "externality_runtime_bag_ids": [],
        "direct_affected_runtime_bag_ids": [7],
        "realized_outcome_deltas_sha256": empty_sha,
        "realized_outcome_deltas_binding": {
            "row_count": 0,
            "content_sha256": empty_sha,
        },
        "cohort_difference_sidecar_binding": {
            "schema": (
                "czr005.g4irsf15.full_cohort_outcome_difference.v1"
            ),
            "row_count": validator.FULL_SEGMENT_COUNT,
            "changed_count": 0,
            "complete_coverage": True,
            "runtime_id_order": "CONTIGUOUS_ZERO_BASED_INPUT_ORDER",
            "content_sha256": validator.canonical_sha256("cohort"),
        },
    }
    row["label_sha256"] = validator.canonical_sha256(row)

    try:
        release_validator._validate_label_with_empty_realized_outcomes(row)
    except validator.ValidationError as exc:
        assert str(exc) == "DELEGATED_FAILURE"
    else:
        raise AssertionError("delegated failure must propagate")

    assert validator.strict_int is original_strict_int


def test_nonempty_realized_outcomes_are_passthrough(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_validate_label(row: dict[str, object]) -> None:
        observed["row"] = row

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_VALIDATE_LABEL",
        fake_validate_label,
    )
    row: dict[str, object] = {
        "realized_outcome_deltas_binding": {
            "row_count": 1,
            "content_sha256": "unused-by-passthrough-test",
        }
    }

    release_validator._validate_label_with_empty_realized_outcomes(row)

    assert observed["row"] is row


def test_boolean_zero_is_not_treated_as_empty_count(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_validate_label(row: dict[str, object]) -> None:
        observed["row"] = row

    monkeypatch.setattr(
        release_validator,
        "_ORIGINAL_VALIDATE_LABEL",
        fake_validate_label,
    )
    row: dict[str, object] = {
        "realized_outcome_deltas_binding": {
            "row_count": False,
            "content_sha256": "must-reach-frozen-validator",
        }
    }

    release_validator._validate_label_with_empty_realized_outcomes(row)

    assert observed["row"] is row
