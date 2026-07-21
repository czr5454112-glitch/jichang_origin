from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval.g4irsf11_java_cie_boundary import (
    CLOSED,
    EXPECTED_JAVA_SEGMENTS,
    EXPECTED_RAW_BAGS,
    FULL_RUN_SCHEMA,
    PARTIAL,
    PASS,
    audit_legacy_structure,
    audit_repository,
    classify_historical_attempt,
    classify_window_row,
    default_paths,
    validate_full_run_manifest,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]


def test_static_astar_and_project_text_cannot_be_java_cie_runtime() -> None:
    static = classify_historical_attempt(
        {
            "attempt": "run_temp_headless_astar_probe",
            "status": "PASS",
            "command": "java G4IRSF5HeadlessAstarProbe",
        }
    )
    assert static[0] == "JAVA_STATIC_ASTAR_PROBE"
    assert static[2] is True
    assert "not the Java/CIE" in static[3]

    text = classify_historical_attempt(
        {"baseline_id": "original_project_iot_drpa_text_2_5", "status": "PASS"}
    )
    assert text[0] == "ORIGINAL_PROJECT_RESULT_ARTIFACT"
    assert text[2] is False
    assert "not a fresh Java execution" in text[3]


def test_bounded_java_window_is_real_java_but_never_full() -> None:
    row = classify_window_row(
        {
            "runtime": "legacy_java_ics_no_fault_window",
            "generated_count": "64",
            "completed_count": "57",
            "active_route_count": "6",
            "unfinished_count": "1",
            "max_new_tasks": "64",
        },
        source="fixture",
        evidence_sha256="a" * 64,
    )
    assert row["is_real_java"] is True
    assert row["classification"] == "JAVA_CIE_BOUNDED_WINDOW"
    assert row["is_full_scope"] is False
    assert row["accepted_as_full_baseline"] is False

    proxy = classify_window_row(
        {
            "runtime": "cpp_pybind_legacy_no_fault_window",
            "generated_count": str(EXPECTED_JAVA_SEGMENTS),
            "completed_count": str(EXPECTED_JAVA_SEGMENTS),
            "active_route_count": "0",
            "unfinished_count": "0",
            "max_new_tasks": "0",
        },
        source="fixture",
        evidence_sha256="b" * 64,
    )
    assert proxy["classification"] == "NON_JAVA_PROXY"
    assert proxy["is_real_java"] is False
    assert proxy["is_full_scope"] is False


def _valid_full_manifest() -> tuple[dict[str, object], list[dict[str, object]], dict[str, str]]:
    hashes = {
        name: (f"{index:x}" * 64)[:64]
        for index, name in enumerate(
            (
                "legacy_main",
                "legacy_tasks",
                "legacy_scheduler",
                "external_harness",
                "external_runner",
                "legacy_map",
                "legacy_inputdata",
                "source_queue",
            ),
            start=1,
        )
    }
    manifest: dict[str, object] = {
        "schema": FULL_RUN_SCHEMA,
        "status": PASS,
        "runtime_identity": "legacy_java_ICS_PathFinding_external_headless",
        "orchestration_command": "python scripts/eval/run_java_cpp_legacy_window_performance.py",
        "javac_subprocess_command": "javac -d build/java_bench App/*.java Harness.java",
        "java_subprocess_command": (
            "java -Djava.awt.headless=true -cp build/java_bench "
            "LegacyIcsNoFaultWindowBenchmark map2.txt inputdata.txt 8260 90000 0 1 0 routes.csv summary.csv"
        ),
        "returncode": 0,
        "scope": {
            "raw_bag_count": EXPECTED_RAW_BAGS,
            "java_segment_count": EXPECTED_JAVA_SEGMENTS,
            "generated_count": EXPECTED_JAVA_SEGMENTS,
            "planned_count": EXPECTED_JAVA_SEGMENTS,
            "completed_count": EXPECTED_JAVA_SEGMENTS,
            "active_route_count": 0,
            "unfinished_count": 0,
            "max_new_tasks": 0,
            "epochs_run": 3,
        },
        "evidence_hashes": hashes,
    }
    trace = [
        {
            "epoch": 8260,
            "source_queue_count": EXPECTED_JAVA_SEGMENTS,
            "released_count": 1,
            "saved_routes_before": 0,
            "saved_routes_after": 1,
            "constrains_before": 0,
            "constrains_after": 2,
            "unfinished_before": 0,
            "unfinished_after": 0,
        },
        {
            "epoch": 8261,
            "source_queue_count": EXPECTED_JAVA_SEGMENTS - 1,
            "released_count": EXPECTED_JAVA_SEGMENTS - 1,
            "saved_routes_before": 1,
            "saved_routes_after": 1,
            "constrains_before": 2,
            "constrains_after": 1,
            "unfinished_before": 0,
            "unfinished_after": 0,
        },
        {
            "epoch": 8262,
            "source_queue_count": 0,
            "released_count": 0,
            "saved_routes_before": 1,
            "saved_routes_after": 0,
            "constrains_before": 1,
            "constrains_after": 0,
            "unfinished_before": 0,
            "unfinished_after": 0,
        },
    ]
    return manifest, trace, hashes


def test_future_full_manifest_requires_java_identity_hashes_scope_and_state_trace() -> None:
    manifest, trace, hashes = _valid_full_manifest()
    assert validate_full_run_manifest(manifest, trace, actual_hashes=hashes) == ()

    rejected = dict(manifest)
    rejected["java_subprocess_command"] = "python noastar_proxy.py"
    rejected["returncode"] = 1
    violations = validate_full_run_manifest(rejected, trace, actual_hashes=hashes)
    assert any("java_subprocess_command" in value for value in violations)
    assert any("returncode" in value for value in violations)

    broken_trace = [dict(row) for row in trace]
    broken_trace[-1]["saved_routes_after"] = 2
    violations = validate_full_run_manifest(manifest, broken_trace, actual_hashes=hashes)
    assert "trace ends with active saved_routes" in violations


def test_legacy_structure_proves_gui_boundary_and_non_gui_external_wrapper() -> None:
    structure = audit_legacy_structure(default_paths(ROOT))
    assert structure.main_gui_coupled
    assert structure.main_calls_generate_tasks
    assert structure.main_calls_ics_path_finding
    assert structure.tasks_one_head_per_source_epoch
    assert structure.scheduler_has_saved_routes
    assert structure.scheduler_rebuilds_constrains
    assert structure.scheduler_has_unfinished_retry
    assert structure.external_harness_valid


def test_current_repository_is_explicit_partial_and_g4j_stays_closed() -> None:
    audit = audit_repository(ROOT)
    assert audit.status == PARTIAL
    assert audit.g4j_status == CLOSED
    assert audit.metadata["accepted_full_baseline"] is False
    checks = {check.criterion: check for check in audit.checks}
    assert checks["protected_legacy_map_input_clean"].status == PASS
    assert checks["legacy_java_lifecycle_identified"].status == PASS
    assert checks["external_non_gui_java_cie_wrapper"].status == PASS
    assert checks["java_source_queue_trace_complete"].status == PASS
    assert checks["first_n_epoch_real_java_cie_evidence"].status == PASS
    assert checks["first_n_java_source_saved_routes_constrains_trace"].status == "FAIL"
    assert checks["full_java_cie_scope"].status == "FAIL"
    assert checks["accepted_headless_java_cie_full_baseline"].status == "FAIL"
    assert checks["g4j_closed"].status == PASS
    assert all(not row["accepted_as_full_baseline"] for row in audit.attempts)
    assert any(
        row["runtime_identity"] == "cpp_pybind_proxy"
        and row["classification"] == "NON_JAVA_PROXY"
        for row in audit.attempts
    )
    assert "--max-new-tasks 0" in audit.commands["required_full_java_cie_attempt"]


def test_output_artifacts_preserve_blockers_commands_and_closed_boundary(tmp_path: Path) -> None:
    audit = audit_repository(ROOT)
    attempts = tmp_path / "attempts.csv"
    gates = tmp_path / "gates.csv"
    inventory = tmp_path / "inventory.csv"
    report = tmp_path / "report.md"
    status = tmp_path / "status.json"
    write_outputs(
        ROOT,
        audit,
        attempt_table=attempts,
        gate_table=gates,
        inventory_table=inventory,
        report_path=report,
        status_path=status,
    )
    payload = json.loads(status.read_text(encoding="utf-8"))
    assert payload["status"] == PARTIAL
    assert payload["g4j_status"] == CLOSED
    assert payload["g4j_opened"] is False
    assert payload["blockers"]
    assert "required_full_java_cie_attempt" in payload["commands"]
    assert "Python/C++ proxy" in payload["claim_boundary"]
    with attempts.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert any(row["classification"] == "JAVA_CIE_BOUNDED_WINDOW" for row in rows)
    assert not any(row["accepted_as_full_baseline"] == "True" for row in rows)
    assert "G4J: `CLOSED`" in report.read_text(encoding="utf-8")
