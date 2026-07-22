from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.eval.g4irsf11_experiment_protocol import (
    EXTENSION_PROTOCOL_VERSION,
    system_extension_cases,
    system_extension_manifest,
)
from scripts.eval.run_g4irsf11_system_extensions import (
    _consolidation_complete,
    _continuity_audit,
    _load_rows,
    _write_report,
    extension_protocol_manifest,
)
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_RELATIVE_PATH,
    CANONICAL_MAP_SHA256,
)


class _ReleaseRows(Sequence[dict[str, Any]]):
    def __init__(self, count: int, span: float) -> None:
        self.count = count
        self.span = span

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, index: int) -> dict[str, Any]:
        if index < 0:
            index += self.count
        if index < 0 or index >= self.count:
            raise IndexError(index)
        return {"release_time": index * self.span / max(1, self.count - 1)}


def test_extension_protocol_is_exact_and_never_smoke_limited() -> None:
    cases = system_extension_cases()
    assert [
        (case.case_id, case.workload_mode, case.scale, case.fault_profile)
        for case in cases
    ] == [
        (
            "extension_rolling_2day_full",
            "rolling_multiday_carryover",
            2.0,
            "no_fault",
        ),
        (
            "extension_rolling_7day_full",
            "rolling_multiday_carryover",
            7.0,
            "no_fault",
        ),
        (
            "extension_synchronized_8x_full",
            "synchronized_replica_worst_case",
            8.0,
            "no_fault",
        ),
        (
            "extension_synchronized_16x_full",
            "synchronized_replica_worst_case",
            16.0,
            "no_fault",
        ),
        (
            "extension_fault_delayed_16x_full",
            "empirical_interarrival_jitter",
            16.0,
            "single_delayed_30s",
        ),
    ]
    assert all(case.segment_limit is None for case in cases)
    manifest = system_extension_manifest()
    assert manifest["protocol_version"] == EXTENSION_PROTOCOL_VERSION
    assert manifest["case_count"] == 5

    bound = extension_protocol_manifest()
    assert bound["fixed_real_map_only"] is True
    assert bound["canonical_map"] == {
        "fixed_real_map_only": True,
        "repo_relative_path": CANONICAL_MAP_RELATIVE_PATH.as_posix(),
        "sha256": CANONICAL_MAP_SHA256,
        "sha256_semantics": "utf8_text_with_crlf_normalized_to_lf",
        "topology_mutation_allowed": False,
    }


def test_rolling_seven_day_audit_requires_all_rows_and_six_boundaries() -> None:
    base = {
        "case_id": "extension_rolling_7day_full",
        "execution_status": "EXECUTED",
        "run_id": "run-seven-day",
        "workload_segment_count": 305_221,
        "arrival_span_seconds": 6 * 86_400.0 + 1.0,
        "continuity_status": "PASS",
        "continuity_single_runtime_invocation_pass": True,
        "continuity_runtime_instance_id": "run-seven-day",
        "continuity_boundary_count": 6,
        "continuity_carry_over_observed": False,
        "continuity_input_audit_status": "PASS",
        "continuity_input_expected_copy_count": 7,
        "continuity_input_workload_row_count": 305_221,
        "continuity_input_base_segment_count": 43_603,
        "continuity_input_coverage_sha256": "a" * 64,
        "continuity_blockers": "",
    }
    exact_rows = _ReleaseRows(305_221, 6 * 86_400.0 + 1.0)
    audited = _continuity_audit(base, workload_rows=exact_rows)
    assert audited["no_smoke_substitution_pass"] is True
    assert audited["continuity_evidence_pass"] is True
    assert audited["carry_over_observed"] is False
    truncated = dict(base, workload_segment_count=32_768)
    assert _continuity_audit(truncated, workload_rows=exact_rows)["no_smoke_substitution_pass"] is False
    one_day_rows = _ReleaseRows(305_221, 86_399.0)
    assert _continuity_audit(base, workload_rows=one_day_rows)["no_smoke_substitution_pass"] is False


def test_rolling_audit_fails_closed_on_unbound_or_incomplete_continuity_evidence() -> None:
    base = {
        "case_id": "extension_rolling_2day_full",
        "execution_status": "EXECUTED",
        "run_id": "run-two-day",
        "workload_segment_count": 87_206,
        "continuity_status": "PASS",
        "continuity_single_runtime_invocation_pass": True,
        "continuity_runtime_instance_id": "different-run",
        "continuity_boundary_count": 1,
        "continuity_input_audit_status": "PASS",
        "continuity_input_expected_copy_count": 2,
        "continuity_input_workload_row_count": 87_206,
        "continuity_input_base_segment_count": 43_603,
        "continuity_input_coverage_sha256": "b" * 64,
        "continuity_blockers": "",
    }
    rows = _ReleaseRows(87_206, 86_401.0)
    assert _continuity_audit(base, workload_rows=rows)["continuity_evidence_pass"] is False
    bound = dict(base, continuity_runtime_instance_id="run-two-day")
    assert _continuity_audit(bound, workload_rows=rows)["no_smoke_substitution_pass"] is True
    bad_coverage = dict(bound, continuity_input_coverage_sha256="not-a-digest")
    assert _continuity_audit(bad_coverage, workload_rows=rows)["no_smoke_substitution_pass"] is False


def test_extension_audit_fails_closed_when_retained_exact_input_is_missing() -> None:
    row = {
        "case_id": "extension_rolling_7day_full",
        "execution_status": "EXECUTED",
        "workload_segment_count": 305_221,
        "arrival_span_seconds": 7 * 86_400.0,
    }
    assert _continuity_audit(row)["no_smoke_substitution_pass"] is False


def test_extension_consolidation_exit_contract_rejects_mixed_or_inexact_rows() -> None:
    exact = {
        "execution_status": "EXECUTED",
        "no_smoke_substitution_pass": True,
    }
    assert _consolidation_complete([exact]) is True
    assert _consolidation_complete([]) is False
    assert _consolidation_complete([exact, dict(exact, execution_status="FAILED")]) is False
    assert _consolidation_complete(
        [exact, dict(exact, no_smoke_substitution_pass=False)]
    ) is False


def test_extension_consolidation_reports_corrupt_descriptor_as_failed(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = system_extension_cases()[0]
    paths = {
        "execution": tmp_path / "execution.json",
        "result": tmp_path / "result.json",
        "workload": tmp_path / "workload.jsonl",
    }
    paths["execution"].write_text('{"status":', encoding="utf-8")
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "scripts.eval.run_g4irsf11_system_extensions.system_extension_cases",
        lambda: [case],
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "scripts.eval.run_g4irsf11_system_extensions._case_paths",
        lambda ignored: paths,
    )
    rows = _load_rows(
        source_sha256="a" * 64,
        map_sha256="b" * 64,
        implementation_digest="c" * 64,
    )
    assert len(rows) == 1
    assert rows[0]["execution_status"] == "FAILED"
    assert rows[0]["return_code"] == "DESCRIPTOR_DECODE_ERROR"
    assert "descriptor could not be decoded" in rows[0]["blocker"]
    assert rows[0]["no_smoke_substitution_pass"] is False


def test_extension_consolidation_reports_semantically_corrupt_workload_as_failed(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = system_extension_cases()[0]
    paths = {
        "execution": tmp_path / "execution.json",
        "result": tmp_path / "result.json",
        "workload": tmp_path / "workload.jsonl",
    }
    paths["workload"].write_text('{"missing_release_time": 1}\n', encoding="utf-8")
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "scripts.eval.run_g4irsf11_system_extensions.system_extension_cases",
        lambda: [case],
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "scripts.eval.run_g4irsf11_system_extensions._case_paths",
        lambda ignored: paths,
    )
    rows = _load_rows(
        source_sha256="a" * 64,
        map_sha256="b" * 64,
        implementation_digest="c" * 64,
    )
    assert len(rows) == 1
    assert rows[0]["execution_status"] == "FAILED"
    assert rows[0]["return_code"] == "WORKLOAD_DECODE_ERROR"
    assert "workload could not be decoded" in rows[0]["blocker"]
    assert rows[0]["retained_workload_row_count"] == 0
    assert rows[0]["no_smoke_substitution_pass"] is False


def test_extension_report_keeps_unrecovered_fault_as_negative_evidence(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "extension-report.md"
    _write_report(
        [
            {
                "case_id": "extension_rolling_2day_full",
                "execution_status": "EXECUTED",
                "exact_segment_count_pass": True,
                "continuity_evidence_pass": True,
                "carry_over_observed": True,
                "day_boundary_pass": True,
                "completed_segment_count": 87_206,
                "workload_segment_count": 87_206,
                "capacity_pass": True,
                "fault_window_count": 0,
                "fault_recovery_pass": True,
                "fault_recovery_unobserved_count": 0,
                "blocker": "",
            },
            {
                "case_id": "extension_fault_delayed_16x_full",
                "execution_status": "EXECUTED",
                "exact_segment_count_pass": True,
                "continuity_evidence_pass": True,
                "carry_over_observed": False,
                "day_boundary_pass": True,
                "completed_segment_count": 697_647,
                "workload_segment_count": 697_648,
                "capacity_pass": False,
                "fault_window_count": 1,
                "fault_recovery_pass": False,
                "fault_recovery_unobserved_count": 1,
                "fault_recovery_times_seconds_json": "[null]",
                "fault_backlog_before_fault_json": "[17]",
                "fault_backlog_at_repair_json": "[23]",
                "fault_recovery_gate_failures": "window_0:recovery_time_pass",
                "blocker": "",
            }
        ],
        report_path=report_path,
    )

    text = report_path.read_text(encoding="utf-8")
    assert "Fault recovery" in text
    assert "NOT_RECOVERED_BY_RUN_END" in text
    assert "| N/A | N/A |" in text
    assert "| False | 1 |" in text
    assert "Temporal Fault Detail" in text
    assert "| [null] | [17] | [23] | window_0:recovery_time_pass |" in text
