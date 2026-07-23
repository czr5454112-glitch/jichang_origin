from __future__ import annotations

from typing import Any

import pytest

from scripts.eval.g4irsf12_phase_a import (
    EXPECTED_HCA_MEANS,
    ROOT,
    collect_phase_a_evidence,
    validate_committed_outputs,
    validate_governance,
    validate_phase_a_evidence,
)


@pytest.fixture(scope="module")
def phase_a_evidence() -> dict[str, Any]:
    return collect_phase_a_evidence(ROOT)


def test_phase_a_frozen_facts_and_protected_inputs_pass(
    phase_a_evidence: dict[str, Any],
) -> None:
    assert validate_phase_a_evidence(phase_a_evidence) == []


def test_phase_a_preserves_authoritative_counts_and_denominator_boundary(
    phase_a_evidence: dict[str, Any],
) -> None:
    assert phase_a_evidence["formal"]["executed_case_count"] == 84
    assert phase_a_evidence["formal"]["expected_case_count"] == 84
    assert phase_a_evidence["formal"]["gate_status_counts"] == {
        "PARTIAL_WITH_EXPLICIT_BLOCKER": 3,
        "PASS": 3,
    }
    assert phase_a_evidence["paper_full"]["complete_raw_bag_count"] == 3114
    assert phase_a_evidence["paper_full"]["completed_segments"] == 12125
    assert phase_a_evidence["paper_full"]["requested_segments"] == 43603

    hca_means = phase_a_evidence["historical_hca"]["means"]
    assert hca_means["processed_segment_attempt_time_tth"] == pytest.approx(
        EXPECTED_HCA_MEANS["processed_segment_attempt_time_tth"]
    )
    assert hca_means["original_entry_time_tth"] == pytest.approx(
        EXPECTED_HCA_MEANS["original_entry_time_tth"]
    )
    assert hca_means["processed_segment_attempt_time_tth"] != pytest.approx(
        hca_means["original_entry_time_tth"], abs=1.0e-3
    )


def test_phase_a_governance_contains_new_fail_closed_rules() -> None:
    assert validate_governance(ROOT) == []


def test_phase_a_committed_reports_are_complete_and_self_consistent() -> None:
    assert validate_committed_outputs(ROOT) == []

    reconciliation = (
        ROOT / "outputs/reports/g4irsf12_prior_evidence_reconciliation.md"
    ).read_text(encoding="utf-8")
    assert "**12,125 / 43,603**" in reconciliation
    assert "**3,114 / 28,506**" in reconciliation
    assert "`processed_segment_attempt_time_tth` | 3.967122711" in reconciliation
    assert "`original_entry_time_tth` | 5.764936746" in reconciliation
