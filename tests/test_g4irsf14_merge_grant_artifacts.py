from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
from typing import Any

import pytest

from scripts.eval import g4irsf12_reproducible_harness as g12
from scripts.eval import g4irsf14_merge_grant_protocol as protocol
from scripts import validate_g4irsf14_merge_grant_artifacts as validator


ROOT = Path(__file__).resolve().parents[1]


def _passing_summary() -> dict[str, object]:
    return {
        "requested_count": 144,
        "completed_count": 144,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "unresolved_deadlock_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "priority_global_scan_count": 0,
        "microphase_runtime_global_scan_count": 0,
        "priority_future_route_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "priority_teacher_input_count": 0,
        "reservation_depth": 1,
        "two_step_reservation_count": 0,
        "max_edges_selected_per_arrive": 1,
        "release_selected_edge_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "stale_arbitration_event_count": 0,
        "artificial_batch_delay_seconds": 0.0,
        "merge_grant_lifecycle_dropped_count": 0,
        "merge_grant_lifecycle_complete": True,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "merge_grant_runtime_owned_capability": True,
        "merge_grant_exact_slot_no_future_shift": True,
        "merge_grant_protocol_integrity_pass": True,
        "merge_grant_final_active_unconsumed": 0,
        "merge_grant_outstanding_request_count": 0,
    }


def _copy_artifacts(target: Path) -> None:
    for relative in (
        validator.CONFIG_PATH,
        validator.REPORT_PATH,
        validator.LIFECYCLE_PATH,
        validator.RULE_AB_PATH,
    ):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)


def test_protocol_is_exact_real_input_production_e4_mechanism_stage() -> None:
    assert protocol.PREFIX_SEGMENTS == 144
    assert protocol.ONLINE_RULES == tuple(f"M{i}" for i in range(7))
    assert protocol.NEGATIVE_RULES == ("M7", "M8", "M9")
    assert protocol.CONTROL_RULE == "M0"
    assert protocol.RUNTIME_REPEAT_COUNT == 2
    assert protocol.FROZEN_CONTROLS["event_semantics"].startswith("E4_")
    assert protocol.FROZEN_CONTROLS["resource_semantics"].startswith("R3_")
    assert protocol.FROZEN_CONTROLS["scorer_mode"].startswith("S1_")
    assert protocol.FROZEN_CONTROLS["pibt_mode"] == "P2"
    assert protocol.FROZEN_CONTROLS["priority_mode"] == "Q0"
    assert protocol.FROZEN_CONTROLS["admission_mode"] == "off"
    assert protocol.FROZEN_CONTROLS["scale"] == 1.0
    assert protocol.BOUNDARY["fault_windows"] == []
    assert protocol.BOUNDARY["reservation_depth"] == 1
    assert protocol.BOUNDARY["reads_future_route"] is False
    assert protocol.BOUNDARY["reads_global_task_list"] is False
    assert protocol.BOUNDARY["reads_global_reservation_table"] is False
    assert protocol.BOUNDARY["runtime_astar_allowed"] is False
    assert all("tests/" not in path.as_posix() for path in protocol.SOURCE_PATHS)
    assert Path("CMakeLists.txt") in protocol.SOURCE_PATHS
    assert (
        Path("cpp/ics_core/runtime/bounded_local_pibt.hpp")
        in protocol.SOURCE_PATHS
    )


def test_source_semantic_hash_allows_crlf_only_and_rejects_real_drift(
    tmp_path: Path,
) -> None:
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    drift = tmp_path / "drift.txt"
    lone_cr = tmp_path / "lone-cr.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    crlf.write_bytes(b"alpha\r\nbeta\r\n")
    drift.write_bytes(b"alpha\nBETA\n")
    lone_cr.write_bytes(b"alpha\rbeta\n")

    expected = protocol.semantic_text_sha256(lf)
    assert protocol.semantic_text_sha256(crlf) == expected
    assert validator.semantic_text_sha256(lf) == expected
    assert validator.semantic_text_sha256(crlf) == expected
    assert protocol.semantic_text_sha256(drift) != expected
    assert validator.semantic_text_sha256(drift) != expected
    with pytest.raises(protocol.ProtocolError, match="lone CR"):
        protocol.semantic_text_sha256(lone_cr)
    with pytest.raises(
        validator.ProtocolValidationError,
        match="lone CR",
    ):
        validator.semantic_text_sha256(lone_cr)


def test_runtime_binary_identity_is_checked_in_payload_and_summary() -> None:
    binary = Path(__file__).resolve()
    digest = protocol.file_sha256(binary)
    payload = {
        "loaded_cpp_binary_path": str(binary),
        "loaded_cpp_binary_sha256": digest,
    }
    summary = dict(payload)
    protocol._validate_loaded_binary_identity(
        payload,
        summary,
        expected_binary_path=binary,
        expected_binary_sha256=digest,
    )

    wrong_summary = dict(summary)
    wrong_summary["loaded_cpp_binary_sha256"] = "0" * 64
    with pytest.raises(protocol.ProtocolError, match="summary.*SHA-256"):
        protocol._validate_loaded_binary_identity(
            payload,
            wrong_summary,
            expected_binary_path=binary,
            expected_binary_sha256=digest,
        )

    wrong_payload = dict(payload)
    wrong_payload["loaded_cpp_binary_path"] = str(ROOT / "CMakeLists.txt")
    with pytest.raises(protocol.ProtocolError, match="payload.*path"):
        protocol._validate_loaded_binary_identity(
            wrong_payload,
            summary,
            expected_binary_path=binary,
            expected_binary_sha256=digest,
        )


def test_frozen_runtime_echo_rejects_material_tuple_drift() -> None:
    expected = validator._expected_runtime_echo("M3")
    protocol._validate_frozen_runtime_echo(
        expected["summary"],
        expected["trace_context"],
        rule="M3",
    )
    mutations = (
        ("summary", "scorer_model_sha256", "0" * 64),
        ("summary", "pibt_max_depth", 1),
        ("summary", "pressure_mode", "C1_absolute_downstream_queue_penalty"),
        ("summary", "fault_event_count", 1),
        ("trace_context", "scale", 2.0),
        ("trace_context", "enable_source_admission", True),
        ("trace_context", "event_semantics", "E3_batch_event_microphase"),
    )
    for scope, field, value in mutations:
        changed = {
            name: dict(fields) for name, fields in expected.items()
        }
        changed[scope][field] = value
        with pytest.raises(protocol.ProtocolError, match=field):
            protocol._validate_frozen_runtime_echo(
                changed["summary"],
                changed["trace_context"],
                rule="M3",
            )


def test_exact_request_timing_rejects_invented_future_shift() -> None:
    row: dict[str, object] = {
        "grant_id": 7,
        "request_time": 10.0,
        "earliest_edge_entry": 10.0,
        "exact_edge_travel_seconds": 3.2,
        "projected_arrival": 13.2,
        "slot_start": 13.2,
        "slot_end": 14.2,
        "grant_expiry": 14.2,
    }
    protocol._validate_exact_request_timing(
        row,
        expected_travel=3.2,
        expected_service=1.0,
    )
    mutations = (
        ("earliest_edge_entry", 10.1),
        ("exact_edge_travel_seconds", 3.3),
        ("projected_arrival", 13.3),
        ("slot_start", 13.3),
        ("grant_expiry", 14.3),
    )
    for field, value in mutations:
        changed = dict(row)
        changed[field] = value
        with pytest.raises(protocol.ProtocolError):
            protocol._validate_exact_request_timing(
                changed,
                expected_travel=3.2,
                expected_service=1.0,
            )


def test_online_rules_require_two_identical_independent_projections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = g12.load_input_prefix(144, root=ROOT)
    calls: dict[str, int] = {}

    def executor(**kwargs: object) -> dict[str, object]:
        rule = str(kwargs["merge_grant_rule"])
        calls[rule] = calls.get(rule, 0) + 1
        return {"rule": rule, "repeat": calls[rule]}

    def stable_validation(
        payload: dict[str, object],
        *,
        rule: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        del payload
        return {
            "deterministic_result_sha256": hashlib.sha256(
                rule.encode("ascii")
            ).hexdigest()
        }

    monkeypatch.setattr(
        protocol, "validate_runtime_payload", stable_validation
    )
    results = protocol.execute_online_rules(
        executor=executor,
        prefix=prefix,
        binary=Path(__file__),
        search_path=Path(__file__).parent,
        root=ROOT,
    )
    assert calls == {rule: 2 for rule in protocol.ONLINE_RULES}
    assert all(result["repeat_count"] == 2 for result in results.values())
    assert all(
        result["repeat_determinism_pass"] is True
        for result in results.values()
    )
    assert all(
        len(set(result["repeat_deterministic_sha256"])) == 1
        for result in results.values()
    )

    calls.clear()

    def unstable_validation(
        payload: dict[str, object],
        *,
        rule: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        suffix = int(payload["repeat"]) if rule == "M3" else 0
        return {
            "deterministic_result_sha256": hashlib.sha256(
                f"{rule}:{suffix}".encode("ascii")
            ).hexdigest()
        }

    monkeypatch.setattr(
        protocol, "validate_runtime_payload", unstable_validation
    )
    with pytest.raises(protocol.ProtocolError, match="M3 deterministic"):
        protocol.execute_online_rules(
            executor=executor,
            prefix=prefix,
            binary=Path(__file__),
            search_path=Path(__file__).parent,
            root=ROOT,
        )


def test_hard_gate_projection_rejects_each_material_escape() -> None:
    passing = _passing_summary()
    assert all(protocol._hard_gates(passing, expected_segments=144).values())

    mutations: list[tuple[str, Any]] = [
        ("completed_count", 143),
        ("reservation_conflicts", 1),
        ("physical_fault_edge_entry_violation_count", 1),
        ("unresolved_deadlock_count", 1),
        ("runtime_full_astar_calls", 1),
        ("global_reservation_scan_count", 1),
        ("priority_future_route_input_count", 1),
        ("reservation_depth", 2),
        ("two_step_reservation_count", 1),
        ("event_limit_reached", True),
        ("stale_arbitration_event_count", 1),
        ("merge_grant_lifecycle_dropped_count", 1),
        ("merge_grant_protocol_integrity_pass", False),
        ("merge_grant_final_active_unconsumed", 1),
    ]
    for name, value in mutations:
        changed = dict(passing)
        changed[name] = value
        gates = protocol._hard_gates(changed, expected_segments=144)
        assert not all(gates.values()), name


def test_csv_rows_use_canonical_strings_and_fail_closed_self_hash() -> None:
    row = protocol._sealed_row(
        {"name": "M1", "count": 3, "pass": True, "value": 0.25},
        ("name", "count", "pass", "value", "row_sha256"),
    )
    validator._verify_row_self_hash(row, "unit")
    assert row["count"] == "3"
    assert row["pass"] == "true"
    assert row["value"] == "0.25"

    tampered = dict(row)
    tampered["count"] = "4"
    with pytest.raises(
        validator.ProtocolValidationError,
        match="self-hash mismatch",
    ):
        validator._verify_row_self_hash(tampered, "unit")


def test_m7_m9_are_exercised_as_production_entrypoint_negatives() -> None:
    prefix = g12.load_input_prefix(144, root=ROOT)
    seen: list[str] = []

    def rejecting_executor(**kwargs: object) -> dict[str, object]:
        rule = str(kwargs["merge_grant_rule"])
        seen.append(rule)
        if rule == "M7":
            raise ValueError(
                "merge_grant_rule M7 is diagnostic-only and cannot run online"
            )
        raise ValueError(
            "merge_grant_rule M8/M9 require a validated model artifact; "
            "runtime selection fails closed"
        )

    evidence = protocol.execute_negative_rules(
        executor=rejecting_executor,
        prefix=prefix,
        binary=Path(__file__),
        search_path=Path(__file__).parent,
        root=ROOT,
    )
    assert seen == ["M7", "M8", "M9"]
    assert set(evidence) == {"M7", "M8", "M9"}
    assert all(row["fail_closed"] is True for row in evidence.values())
    assert all(
        row["production_entrypoint"]
        == "czr005.cpp_backend.g4irsf11_event_runtime_from_records"
        for row in evidence.values()
    )


def test_validator_rejects_obsolete_standalone_schema_before_other_claims() -> None:
    with pytest.raises(
        validator.ProtocolValidationError,
        match="obsolete/unexpected schema",
    ):
        validator._validate_manifest(
            {
                "schema": "czr005.g4irsf14.merge_grant_protocol.v1",
                "status": "STANDALONE_PROTOCOL_TESTED_NOT_RUNTIME_INTEGRATED",
            },
            root=ROOT,
        )


def test_committed_production_bundle_validates_independently() -> None:
    result = validator.validate_bundle(root=ROOT)
    assert result["schema"] == validator.SCHEMA
    assert result["status"] == validator.STATUS
    assert result["online_rules"] == list(protocol.ONLINE_RULES)
    assert result["negative_rules"] == list(protocol.NEGATIVE_RULES)
    assert result["segment_count"] == 144
    assert result["lifecycle_rows"] > 0
    assert result["binary_recheck"] in {
        "VERIFIED_EXACT_BYTES",
        "SEALED_DIGEST_ONLY",
    }


def test_validator_rejects_output_tamper_even_if_csv_remains_parseable(
    tmp_path: Path,
) -> None:
    _copy_artifacts(tmp_path)
    path = tmp_path / validator.RULE_AB_PATH
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 11
    rows[1] = rows[1].replace(
        "EXECUTED_PRODUCTION_E4",
        "EXECUTED_PRODUCTION_E3",
        1,
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(
        validator.ProtocolValidationError,
        match="output hash mismatch",
    ):
        validator.validate_bundle(root=ROOT, artifact_root=tmp_path)


def test_validator_rejects_manifest_self_hash_tamper(tmp_path: Path) -> None:
    _copy_artifacts(tmp_path)
    path = tmp_path / validator.CONFIG_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["promotion_status"] = "PROMOTED"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        validator.ProtocolValidationError,
        match="self_sha256 mismatch",
    ):
        validator.validate_bundle(root=ROOT, artifact_root=tmp_path)
