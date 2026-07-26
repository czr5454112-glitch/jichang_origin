from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_denominator_reconciliation as audit
from scripts.eval import g4irsf12_reproducible_harness as harness


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FORMAL_SOURCE_BUNDLE_SHA256 = (
    "eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7"
)


def test_reconciliation_preserves_formal_execution_provenance() -> None:
    assert audit.RECONCILIATION_SCRIPT_PATH not in harness.FORMAL_SOURCE_PATHS
    assert (
        harness.source_bundle_sha256(harness.FORMAL_SOURCE_PATHS, root=ROOT)
        == EXPECTED_FORMAL_SOURCE_BUNDLE_SHA256
    )


def test_reconciliation_corrects_only_the_comparator_denominator() -> None:
    payload = audit.build_reconciliation(ROOT)
    assert payload["status"] == "VERIFIED_DENOMINATOR_MISMATCH"
    assert payload["runtime_rerun_required"] is False
    assert payload["sealed_execution_evidence_rewritten"] is False

    input_evidence = payload["input_evidence"]
    targets = payload["corrected_targets"]
    assert input_evidence["segment_count"] == 43_603
    assert input_evidence["raw_bag_count"] == 28_506
    assert input_evidence["leg_counts"] == {
        "direct": 13_409,
        "storage_in": 15_097,
        "storage_out": 15_097,
    }
    assert math.isclose(
        targets["scheduled_pre_release_offset_minutes"],
        37.371001534322,
        rel_tol=0.0,
        abs_tol=5.0e-13,
    )
    assert math.isclose(
        targets["v2_safe_raw_entry_target_minutes"],
        41.49530698780892,
        rel_tol=0.0,
        abs_tol=5.0e-13,
    )
    assert math.isclose(
        targets["historical_hca_raw_entry_target_minutes"],
        43.13593828041816,
        rel_tol=0.0,
        abs_tol=5.0e-13,
    )


def test_reconciled_finalist_decision_is_hca_pass_v2_fail() -> None:
    payload = audit.build_reconciliation(ROOT)
    rows = {row["candidate_id"]: row for row in payload["finalists"]}
    assert set(rows) == {"J_F1", "J_F2"}

    assert rows["J_F1"]["executed_full_repeat_count"] == 5
    assert rows["J_F2"]["executed_full_repeat_count"] == 5
    assert rows["J_F1"]["v2_safe_raw_entry_gate"] == "FAIL"
    assert rows["J_F2"]["v2_safe_raw_entry_gate"] == "FAIL"
    assert rows["J_F1"]["corrected_hca_raw_entry_gate"] == "PASS"
    assert rows["J_F2"]["corrected_hca_raw_entry_gate"] == "PASS"
    assert rows["J_F1"]["safety_termination_gate"] == "PASS"
    assert rows["J_F2"]["safety_termination_gate"] == "PASS"
    assert rows["J_F1"]["strict_joint_promotion_gate"] == "FAIL"
    assert rows["J_F2"]["strict_joint_promotion_gate"] == "FAIL"
    assert math.isclose(
        rows["J_F1"]["delta_vs_v2_seconds"],
        2.966485279734,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    )
    assert math.isclose(
        rows["J_F2"]["delta_vs_v2_seconds"],
        1.134703810134,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    )

    decision = payload["decision"]
    assert (
        decision["new_framework_plus_decentralized_vs_historical_hca"]
        == "PASS"
    )
    assert (
        decision["new_framework_plus_decentralized_vs_frozen_v2_safe"]
        == "FAIL"
    )
    assert (
        decision["new_framework_plus_decentralized_vs_pibt_off_control"]
        == "PASS"
    )
    assert decision["strict_joint_promotion_gate"] == "FAIL"
    assert decision["g4j_status"] == "CLOSED"
    assert decision["phase_k_multiplier"] == "UNKNOWN_NOT_COMPUTABLE"
    assert decision["phase_l_status"] == "BLOCKED_NOT_RUN"


def test_safety_and_control_signatures_fail_closed_on_metric_drift() -> None:
    admitted = audit.load_result_ledger(ROOT / audit.LEDGER_PATH, root=ROOT)
    finalist = next(
        row for row in admitted if row.get("candidate_id") == "J_F1"
    )
    control = next(
        row
        for row in admitted
        if row.get("candidate_id") == "J_CTRL_PIBT_OFF"
    )
    assert audit._finalist_safety_termination_pass(finalist)
    assert audit._pibt_off_censored_deadlock_signature(control)

    finalist_mutations = {
        "conflict_count": 1,
        "unsafe_entry_count": 1,
        "unresolved_deadlock_count": 1,
        "event_limit_reached": True,
        "time_limit_reached": True,
        "summary_only_contract_pass": False,
        "termination_reason": "PARTIAL",
        "comparison_eligible": False,
        "failed_segment_count": 1,
        "repeat_consistency": "MISMATCH",
    }
    for field, value in finalist_mutations.items():
        mutated = {**finalist, field: value}
        assert not audit._finalist_safety_termination_pass(mutated), field

    control_mutations = {
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": True,
        "termination_reason": "DRAINED",
        "complete_raw_bag_count": audit.FULL_SIZE_BAGS,
        "summary_only_contract_pass": False,
        "event_count": int(control["event_count"]) - 1,
    }
    for field, value in control_mutations.items():
        mutated = {**control, field: value}
        assert not audit._pibt_off_censored_deadlock_signature(mutated), field


def test_decisions_are_derived_from_safety_and_control_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = audit.build_reconciliation(ROOT)
    finalists = copy.deepcopy(baseline["finalists"])
    sealed = copy.deepcopy(baseline["sealed_phase_j_evidence"])

    for row in finalists:
        row["v2_safe_raw_entry_gate"] = "PASS"
        row["corrected_hca_raw_entry_gate"] = "PASS"
        row["safety_termination_gate"] = "PASS"
    finalists[0]["safety_termination_gate"] = "FAIL"
    sealed["pibt_off_control"]["censored_deadlock_signature_gate"] = "PASS"

    def altered_candidate_rows(*args: object, **kwargs: object) -> object:
        return finalists, sealed

    monkeypatch.setattr(audit, "_candidate_rows", altered_candidate_rows)
    unsafe = audit.build_reconciliation(ROOT)
    assert (
        unsafe["decision"][
            "new_framework_plus_decentralized_vs_historical_hca"
        ]
        == "FAIL"
    )
    assert (
        unsafe["decision"][
            "new_framework_plus_decentralized_vs_frozen_v2_safe"
        ]
        == "FAIL"
    )
    assert unsafe["decision"]["strict_joint_promotion_gate"] == "FAIL"

    for row in finalists:
        row["safety_termination_gate"] = "PASS"
    sealed["pibt_off_control"]["censored_deadlock_signature_gate"] = "FAIL"
    no_control_win = audit.build_reconciliation(ROOT)
    assert (
        no_control_win["decision"][
            "new_framework_plus_decentralized_vs_pibt_off_control"
        ]
        == "FAIL"
    )
    report = audit._report_bytes(no_control_win).decode("utf-8")
    assert "does not establish a completion/deadlock advantage" in report


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        (audit.LEGACY_TABLE_PATH, "legacy denominator table SHA drift"),
        (
            audit.LEGACY_RECOMPUTE_SOURCE_PATH,
            "legacy denominator reducer SHA drift",
        ),
        (audit.LEDGER_PATH, "sealed Phase-J ledger SHA drift"),
        (
            audit.CANDIDATE_BUNDLE_PATH,
            "sealed Phase-J candidate bundle SHA drift",
        ),
    ],
)
def test_pinned_evidence_sha_drift_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: Path,
    message: str,
) -> None:
    original_file_sha256 = audit._file_sha256
    target = (ROOT / relative_path).resolve()

    def drifted_file_sha256(path: Path) -> str:
        if path.resolve() == target:
            return "0" * 64
        return original_file_sha256(path)

    monkeypatch.setattr(audit, "_file_sha256", drifted_file_sha256)
    with pytest.raises(audit.ReconciliationError, match=message):
        audit.build_reconciliation(ROOT)


def test_committed_reconciliation_outputs_are_current() -> None:
    assert audit.validate_committed_outputs(ROOT) == []
