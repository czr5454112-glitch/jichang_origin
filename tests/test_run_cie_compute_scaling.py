from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import run_cie_compute_scaling as scaling


def _write(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _common(
    *,
    family: str,
    label: str,
    coordination: str = "neutral_fifo",
) -> dict[str, object]:
    return {
        "schema": "formal.test.v1",
        "status": "COMPLETE",
        "map": "map2",
        "scale": 2,
        "population": {"raw_bag_count": 100, "segment_count": 150},
        "algorithm": {
            "baseline_family": family,
            "reproduction_or_adaptation_label": label,
            "scorer_mode": (
                "S4_queue_aware_rule_only" if family.startswith("G31") else "OTHER"
            ),
            "coordination_protocol": coordination,
        },
        "release_protocol": {"mode": "canonical"},
        "provenance": {
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR",
            "survivor_timing_used": False,
        },
        "execution_integrity": {"pass": True},
        "paper_subjects": {
            "fixed_horizon_capacity": {
                "completed_raw_bag_count": 80,
            },
            "full_population_raw_bag_timing": {
                "survivor_or_common_cohort_used": False,
            },
        },
        "runtime": {
            "wall_seconds": 8.0,
            "cpu_seconds": 6.0,
            "peak_rss_bytes": "NOT_MEASURED",
            "native_summary": {
                "completed_count": 120,
                "event_count": 400,
                "decision_count": 160,
            },
        },
    }


def _hca() -> dict[str, object]:
    return {
        "schema": "czr005.cie_revision.feng_native_cie_dh_audit.v1",
        "identity_contract": {
            "baseline_family": "FENG_NATIVE_HCA",
            "executor_identity": "FENG_NATIVE_JAVA_HCA_SCHEDULER",
            "coordination_protocol": "CENTRALIZED_ASTAR_RESERVATION",
            "release_protocol": "ORIGINAL_JAVA_TASK_RELEASE",
            "reproduction_or_adaptation_label": "FROZEN_AGGREGATE_EXACT_REGRESSION_NOT_TRACE_EXACT",
        },
        "hca_regression": {
            "pass": True,
            "runs": [
                {
                    "run_id": "run_01",
                    "pass": True,
                    "observed": {
                        "raw_bag_count": 100,
                        "segment_count": 150,
                        "complete_raw_bag_count": 100,
                        "completed_segment_count": 150,
                        "wall_seconds": 25.0,
                        "cpu_seconds": "NOT_MEASURED",
                        "peak_rss_bytes": "NOT_MEASURED",
                        "survivor_only": False,
                    },
                }
            ],
        },
    }


def test_hca_java_extracts_measured_wall_and_explicit_nm_reasons(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "hca.json", _hca())

    row = scaling.extract_rows("hca_java", path)[0]

    assert row["identity_status"] == "VERIFIED"
    assert row["executor"] == "FENG_NATIVE_JAVA_HCA_SCHEDULER"
    assert row["language"] == "JAVA"
    assert row["wall_seconds"] == 25.0
    assert row["wall_seconds_per_completed_raw_bag"] == pytest.approx(0.25)
    assert row["cpu_seconds"] == "N/M"
    assert row["cpu_seconds_reason"] == "SOURCE_EXPLICITLY_NOT_MEASURED"
    assert row["event_count"] == "N/M"
    assert row["event_count_reason"] == "JAVA_HCA_EVENT_COUNT_NOT_INSTRUMENTED"
    assert row["events_per_completed_raw_bag"] == "N/M"
    assert row["cross_protocol_complexity_claim_permitted"] is False


def test_g31_native_extracts_common_executor_cost_per_completed_bag(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path / "g31.json",
        _common(
            family="G31_S4",
            label="NATIVE_CURRENT_SYSTEM",
        ),
    )

    row = scaling.extract_rows("g31_native", path)[0]

    assert row["identity_status"] == "VERIFIED"
    assert row["executor"] == "COMMON_CPP_EVENT_EXECUTOR"
    assert row["release_protocol"] == "canonical"
    assert row["map"] == "map2"
    assert row["load_factor"] == 2
    assert row["wall_seconds_per_completed_raw_bag"] == pytest.approx(0.1)
    assert row["cpu_seconds_per_completed_raw_bag"] == pytest.approx(0.075)
    assert row["events_per_completed_raw_bag"] == pytest.approx(5.0)
    assert row["decisions_per_completed_raw_bag"] == pytest.approx(2.0)
    assert row["peak_rss_bytes"] == "N/M"
    assert row["survivor_timing_used"] is False
    assert row["survivor_timing_used_reason"] == "EXPLICIT_SOURCE_FIELD"


def test_g31_activation_schema_is_recognized_as_authoritative_native_identity(
    tmp_path: Path,
) -> None:
    payload = {
        "schema": "czr005.cie_component_activation.run.v1",
        "status": "COMPLETE",
        "native_execution_started": True,
        "map": "nanning",
        "nominal_load_factor": 2.0,
        "population": {"raw_bag_denominator": 57_012, "segment_count": 87_206},
        "request_contract": {"scorer_mode": "S4_queue_aware_rule_only"},
        "provenance": {
            "baseline_family": "G31_S4_NATIVE",
            "reproduction_or_adaptation_label": "NATIVE_CURRENT_SYSTEM",
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
            "release_protocol": "canonical_complete_flight_population",
            "coordination_protocol": "J2_M3_JIT_FAIR_AGING_DEADLINE",
            "peak_rss_bytes": "NOT_MEASURED",
            "survivor_timing_used": False,
        },
        "execution_integrity": {"pass": True},
        "fixed_denominator_business": {
            "detailed": {"completed_raw_bag_count": 57_012}
        },
        "runtime": {
            "wall_seconds": 100.0,
            "cpu_seconds": 90.0,
            "event_count": 1_000,
            "decision_count": 200,
            "summary": {"completed_count": 87_206},
        },
    }
    path = _write(tmp_path / "activation.json", payload)

    row = scaling.extract_rows("g31_native", path)[0]

    assert row["identity_status"] == "VERIFIED"
    assert row["baseline_family"] == "G31_S4_NATIVE"
    assert row["load_factor"] == 2.0
    assert row["coordination_protocol"] == "J2_M3_JIT_FAIR_AGING_DEADLINE"
    assert row["completed_segment_count"] == 87_206
    assert row["peak_rss_bytes"] == "N/M"
    assert row["peak_rss_bytes_reason"] == "SOURCE_EXPLICITLY_NOT_MEASURED"


@pytest.mark.parametrize(
    ("input_label", "family", "identity_label"),
    [
        (
            "cie_dh_common_executor",
            "CIE_DH_2009_COMMON_EXECUTOR_ADAPTATION",
            "ADAPTED_NOT_EXACT_NOT_FENG_NATIVE",
        ),
        (
            "tarau_common_executor",
            "TARAU_DISTRIBUTED_2010",
            "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT",
        ),
    ],
)
def test_common_executor_adaptations_require_explicit_family_identity(
    tmp_path: Path,
    input_label: str,
    family: str,
    identity_label: str,
) -> None:
    path = _write(
        tmp_path / f"{input_label}.json",
        _common(family=family, label=identity_label),
    )

    row = scaling.extract_rows(input_label, path)[0]

    assert row["identity_status"] == "VERIFIED"
    assert row["baseline_family"] == family
    assert row["language"] == "C++_PYTHON_BINDING"
    assert row["cross_protocol_complexity_claim_permitted"] is False


def test_identity_mismatch_redacts_compute_numbers_instead_of_relabeling(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path / "wrong.json",
        _common(
            family="TARAU_DISTRIBUTED_2010",
            label="TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT",
        ),
    )

    row = scaling.extract_rows("g31_native", path)[0]

    assert row["identity_status"] == "REJECTED"
    assert "BASELINE_FAMILY_NOT_G31_S4" in row["identity_reasons"]
    assert row["wall_seconds"] == "N/M"
    assert row["wall_seconds_reason"] == "IDENTITY_NOT_VERIFIED"
    assert row["event_count"] == "N/M"
    assert row["events_per_completed_raw_bag"] == "N/M"


def test_aggregate_writes_csv_reasons_and_cross_language_warning(
    tmp_path: Path,
) -> None:
    hca = _write(tmp_path / "hca.json", _hca())
    g31_payload = _common(family="G31_S4", label="NATIVE_CURRENT_SYSTEM")
    # Absence stays N/M; the extractor must not infer survivor use from scale=2.
    del g31_payload["provenance"]["survivor_timing_used"]  # type: ignore[index]
    del g31_payload["paper_subjects"]["full_population_raw_bag_timing"]  # type: ignore[index]
    g31 = _write(tmp_path / "g31.json", g31_payload)
    table = tmp_path / "compute.csv"
    report = tmp_path / "audit.md"

    count, verified = scaling.aggregate(
        specs=[f"hca_java={hca}", f"g31_native={g31}"],
        table=table,
        report=report,
    )

    assert (count, verified) == (2, 2)
    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    g31_row = next(row for row in rows if row["input_label"] == "g31_native")
    assert g31_row["survivor_timing_used"] == "N/M"
    assert (
        g31_row["survivor_timing_used_reason"]
        == "SOURCE_FIELD_ABSENT_NO_SURVIVOR_INFERENCE"
    )
    text = report.read_text(encoding="utf-8")
    assert "Cross-language and cross-executor wall-time multiples are not causal" in text
    assert "cannot establish pure algorithmic complexity" in text
    assert "No cross-row ratios" in text


def test_input_spec_requires_a_supported_explicit_label(tmp_path: Path) -> None:
    path = _write(tmp_path / "input.json", {})
    label, resolved = scaling.parse_input_spec(f"g31={path}")
    assert label == "g31_native"
    assert resolved == path.resolve()
    with pytest.raises(scaling.ComputeScalingError, match="unsupported input label"):
        scaling.parse_input_spec(f"mystery={path}")
