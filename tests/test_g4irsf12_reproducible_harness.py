from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from czr005 import cpp_backend
from czr005.datasets.decision_trace import canonicalise_decision_row
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf12_reproducible_harness as cli
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records


ROOT = Path(__file__).resolve().parents[1]


def _safe_summary(*, requested: int, completed: int) -> dict[str, object]:
    return {
        "requested_count": requested,
        "completed_count": completed,
        "failed_count": requested - completed,
        "conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "full_future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": 1,
        "hold_trace_stored_count": 0,
        "max_edges_selected_per_bag_per_decision": 1,
        "max_edges_selected_per_arrive": 1,
        "max_actions_committed_per_pibt_batch": 0,
        "bounded_local_pibt_applicability_count": 0,
        "bounded_local_pibt_attempt_count": 0,
        "bounded_local_pibt_prepare_count": 0,
        "bounded_local_pibt_validate_count": 0,
        "bounded_local_pibt_commit_count": 0,
        "bounded_local_pibt_rollback_count": 0,
        "bounded_local_pibt_backtrack_count": 0,
        "bounded_local_pibt_wait_for_cycle_count": 0,
        "bounded_local_pibt_handoff_count": 0,
        "bounded_local_pibt_same_bag_fallback_count": 0,
        "decision_trace_stored_count": 0,
        "event_count": requested * 10,
        "runtime_seconds": 0.25,
        "fault_policy_enabled": True,
        "legacy_pibt_lite_enabled": False,
        "sensor_loss_mode_used": False,
        "fault_notification_drop_count": 0,
        "physical_fault_interlock_rejection_count": 0,
        "physical_fault_interlock_hold_count": 0,
        "physical_fault_interlock_reroute_count": 0,
        "local_fault_policy_action_count": 0,
        "local_fault_policy_hold_count": 0,
        "local_fault_policy_reroute_count": 0,
    }


def _binary_echo(kwargs: dict[str, object]) -> dict[str, str]:
    path = Path(str(kwargs["expected_binary_path"])).resolve(strict=True)
    return {
        "loaded_cpp_binary_path": str(path),
        "loaded_cpp_binary_sha256": harness.file_sha256(path),
    }


def _mode_echoes(kwargs: dict[str, object]) -> dict[str, object]:
    echoes = {
        f"{name}_echo": kwargs[name]
        for name in (
            "resource_semantics",
            "scorer_mode",
            "pibt_mode",
            "pressure_mode",
            "admission_mode",
        )
    }
    if "framework_mode" in kwargs:
        echoes["framework_mode_echo"] = kwargs["framework_mode"]
    return echoes


def _successful_fake_executor(**kwargs: object) -> dict[str, object]:
    input_rows = list(kwargs["input_rows"])
    bags = []
    for index, row in enumerate(input_rows):
        release = float(row["pass_time"])
        admitted = release + 2.0
        bags.append(
            {
                "segment_id": row["segment_id"],
                "task_id": row["task_id"],
                "release_time": release,
                "admitted_time": admitted,
                "finish_time": admitted + 8.0 + index * 1.0e-6,
                "completed": True,
            }
        )
    summary = _safe_summary(requested=len(bags), completed=len(bags))
    summary.update(
        {
            "resource_semantics_id": kwargs["resource_semantics"],
            "scorer_mode": kwargs["scorer_mode"],
            "pibt_mode": kwargs["pibt_mode"],
            "pressure_mode": kwargs["pressure_mode"],
            "admission_mode": kwargs["admission_mode"],
            "pibt_max_depth": kwargs["pibt_max_depth"],
            "local_queue_capacity": kwargs.get("local_queue_capacity", 0),
            "max_events": kwargs["max_events"],
        }
    )
    summary.update(_mode_echoes(kwargs))
    summary["fault_policy_enabled"] = kwargs.get(
        "enable_fault_policy", True
    )
    summary["legacy_pibt_lite_enabled"] = kwargs["enable_pibt_lite"]
    if "framework_mode" in kwargs:
        summary["framework_mode"] = kwargs["framework_mode"]
    for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS:
        summary[name] = kwargs[name]
    binary_echo = _binary_echo(kwargs)
    summary.update(binary_echo)
    return {
        "summary": summary,
        "bags": bags,
        "decisions": [],
        "events": [],
        **binary_echo,
    }


def _valid_prior_result(
    case: harness.CaseSpec,
    size_segments: int,
    *,
    repeat_index: int = 1,
    result_hash_character: str = "a",
    binary_sha256: str = "c" * 64,
    source_bundle_sha256: str = "b" * 64,
    executor_source_sha256: str = "d" * 64,
    loaded_cpp_binary_path: str = "C:/frozen/czr005_cpp.pyd",
) -> dict[str, object]:
    prefix_hash, raw_bag_count = harness._cached_prefix_evidence(
        str(ROOT.resolve()),
        size_segments,
    )
    controls = case.runtime_controls
    row: dict[str, object] = {
        **harness.planned_result(case, size_segments),
        "repeat_index": repeat_index,
        "execution_status": "EXECUTED",
        "gate_status": "PASS",
        "evidence_status": "EXECUTED_RESULT_VALIDATED",
        "termination_reason": "DRAINED",
        "early_abort_status": "",
        "blocker": "",
        "summary_only": True,
        "summary_only_contract_pass": True,
        "decision_trace_stored_count": 0,
        "hold_trace_stored_count": 0,
        "input_prefix_sha256": prefix_hash,
        "source_bundle_sha256": source_bundle_sha256,
        "source_path_manifest_sha256": (
            harness.FORMAL_SOURCE_PATH_MANIFEST_SHA256
        ),
        "binary_sha256": binary_sha256,
        "loaded_cpp_binary_path": loaded_cpp_binary_path,
        "loaded_cpp_binary_sha256": binary_sha256,
        "binary_provenance_pass": True,
        "executor_id": harness.FORMAL_EXECUTOR_ID,
        "executor_source_sha256": executor_source_sha256,
        "deterministic_result_sha256": result_hash_character * 64,
        "repeat_consistency": "SINGLE_RESULT",
        "selected_segment_count": size_segments,
        "selected_raw_bag_count": raw_bag_count,
        "completed_segment_count": size_segments,
        "complete_raw_bag_count": raw_bag_count,
        "failed_segment_count": 0,
        "completion_rate": 1.0,
        "comparison_eligible": True,
        "denominator_scope": harness.DENOMINATOR_SCOPE,
        "survivor_metric_comparison_allowed": False,
        "resource_semantics_echo": controls["resource_semantics"],
        "scorer_mode_echo": controls["scorer_mode"],
        "pibt_mode_echo": controls["pibt_mode"],
        "pressure_mode_echo": controls["pressure_mode"],
        "admission_mode_echo": controls["admission_mode"],
        "framework_mode_echo": controls.get("framework_mode", ""),
        "pibt_max_depth_echo": controls["pibt_max_depth"],
        "max_events_echo": controls["max_events"],
        "conflict_count": 0,
        "unsafe_entry_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": controls.get("reservation_depth", 1),
        "local_queue_capacity": controls.get("local_queue_capacity", 0),
        "declared_max_events": controls["max_events"],
        "max_edges_selected_per_bag_per_decision": 1,
        "max_edges_selected_per_arrive": 1,
        "max_actions_committed_per_pibt_batch": 0,
        "pibt_applicability_count": 0,
        "pibt_attempt_count": 0,
        "pibt_prepare_count": 0,
        "pibt_validate_count": 0,
        "pibt_commit_count": 0,
        "pibt_rollback_count": 0,
        "pibt_backtrack_count": 0,
        "pibt_wait_for_cycle_count": 0,
        "pibt_handoff_count": 0,
        "pibt_same_bag_fallback_count": 0,
        "event_count": size_segments * 10,
        "legacy_pibt_lite_enabled_echo": controls["enable_pibt_lite"],
    }
    for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS:
        row[f"{name}_echo"] = controls[name]
    if case.phase == "F" and case.pibt_label != "P0":
        row.update(
            {
                "max_actions_committed_per_pibt_batch": 2,
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 2,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 5,
                "pibt_commit_count": 1,
                "pibt_rollback_count": 0,
                "pibt_backtrack_count": 0,
                "pibt_wait_for_cycle_count": 0,
                "pibt_handoff_count": 0,
            }
        )
    if case.phase == "H" and case.fault_profile != "no_fault":
        sensor_loss = case.fault_profile == "sensor_loss"
        advertised_fault = case.fault_profile in {
            "single_immediate",
            "single_delayed_30s",
        }
        policy_off = case.fault_profile == "fault_policy_off"
        row.update(
            {
                "fault_policy_enabled_echo": controls["enable_fault_policy"],
                "sensor_loss_mode_used": sensor_loss,
                "fault_notification_drop_count": 2 if sensor_loss else 0,
                "fault_physical_interlock_rejection_count": (
                    0 if advertised_fault else 1
                ),
                "fault_physical_interlock_hold_count": (
                    1 if policy_off else 0
                ),
                "fault_physical_interlock_reroute_count": (
                    1 if sensor_loss else 0
                ),
                "fault_local_action_count": 1 if advertised_fault else 0,
                "fault_local_hold_count": 0,
                "fault_reroute_count": 1 if advertised_fault else 0,
                "fault_affected_bag_count": 1,
                "fault_affected_completed_count": 1,
                "fault_recovery_seconds_available": True,
                "fault_recovery_seconds": 0.0,
                "repair_backlog_slope_available": True,
                "repair_backlog_slope": 0.0,
            }
        )
    elif case.phase == "H":
        row.update(
            {
                "fault_policy_enabled_echo": controls["enable_fault_policy"],
                "sensor_loss_mode_used": False,
                "fault_notification_drop_count": 0,
                "fault_physical_interlock_rejection_count": 0,
                "fault_physical_interlock_hold_count": 0,
                "fault_physical_interlock_reroute_count": 0,
                "fault_local_action_count": 0,
                "fault_local_hold_count": 0,
                "fault_reroute_count": 0,
                "fault_affected_bag_count": 0,
                "fault_affected_completed_count": 0,
            }
        )
    if case.phase == "J":
        row.update(
            {
                "original_entry_mean_minutes": 4.0,
                "original_entry_p95_seconds": 240.0,
                "original_entry_p99_seconds": 240.0,
                "java_release_mean_minutes": 3.5,
                "source_wait_mean_minutes": 0.5,
                "network_time_mean_minutes": 3.0,
                "total_system_time_mean_minutes": 4.0,
                **harness.evaluate_original_entry_performance(4.0),
            }
        )
    return harness.seal_evidence_row(row)


def _write_result_ledger(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=harness.RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {
                name: row.get(name, "")
                for name in harness.RESULT_COLUMNS
            }
            for row in rows
        )


def test_fixed_identity_and_strict_prefix_order() -> None:
    identity = harness.assert_fixed_identity(ROOT)
    assert identity["source_row_count"] == 43_603
    assert identity["source_bag_count"] == 28_506

    prefix_144 = harness.load_input_prefix(144, root=ROOT)
    prefix_512 = harness.load_input_prefix(512, root=ROOT)
    assert prefix_144.first_segment_id == "0:storage_in"
    assert prefix_144.rows[1]["segment_id"] == "0:storage_out"
    assert [row["segment_id"] for row in prefix_512.rows[:144]] == [
        row["segment_id"] for row in prefix_144.rows
    ]
    assert [row["input_row_index"] for row in prefix_144.rows] == list(range(144))
    assert len(prefix_144.prefix_sha256) == 64
    assert prefix_144.prefix_sha256 != prefix_512.prefix_sha256

    with pytest.raises(harness.HarnessValidationError):
        harness.load_input_prefix(145, root=ROOT)


def test_raw_bag_denominators_and_wait_decomposition() -> None:
    inputs = [
        {
            "segment_id": "7:storage_in",
            "task_id": 7,
            "original_entry_time": 5.0,
            "pass_time": 5.0,
        },
        {
            "segment_id": "7:storage_out",
            "task_id": 7,
            "original_entry_time": 5.0,
            "pass_time": 20.0,
        },
        {
            "segment_id": "8:direct",
            "task_id": 8,
            "original_entry_time": 10.0,
            "pass_time": 10.0,
        },
    ]
    results = [
        {
            "segment_id": "7:storage_in",
            "release_time": 5.0,
            "admitted_time": 7.0,
            "finish_time": 15.0,
            "completed": True,
        },
        {
            "segment_id": "7:storage_out",
            "release_time": 20.0,
            "admitted_time": 22.0,
            "finish_time": 30.0,
            "completed": True,
        },
        {
            "segment_id": "8:direct",
            "release_time": 10.0,
            "admitted_time": 11.0,
            "finish_time": 14.0,
            "completed": True,
        },
    ]
    rows = harness.aggregate_raw_bag_timings(inputs, results)
    task7 = next(row for row in rows if row["task_id"] == 7)
    assert task7["original_entry_time_tth_seconds"] == pytest.approx(35.0)
    assert task7["java_release_time_tth_seconds"] == pytest.approx(20.0)
    assert task7["scheduled_pre_release_wait_seconds"] == pytest.approx(15.0)
    assert task7["source_wait_seconds"] == pytest.approx(4.0)
    assert task7["network_time_seconds"] == pytest.approx(16.0)
    assert task7["total_system_time_seconds"] == pytest.approx(35.0)

    summary = harness.summarize_raw_bag_timings(
        rows, selected_segment_count=3
    )
    assert summary["comparison_eligible"] is True
    assert summary["original_entry_mean_minutes"] == pytest.approx(
        ((35.0 + 4.0) / 2.0) / 60.0
    )

    partial = harness.aggregate_raw_bag_timings(inputs, results[:2])
    partial_summary = harness.summarize_raw_bag_timings(
        partial, selected_segment_count=3
    )
    assert partial_summary["comparison_eligible"] is False
    assert partial_summary["original_entry_mean_minutes"] is None
    assert partial_summary["survivor_metric_comparison_allowed"] is False


def test_capability_introspection_blocks_old_wrapper_without_execution(
    tmp_path: Path,
) -> None:
    called = False

    def limited_executor(
        *,
        bag_records: object,
        trace_limit: int = 0,
    ) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("capability-blocked executor must not run")

    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fake-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B6"
    )
    row = harness.execute_case(
        case,
        144,
        executor=limited_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert called is False
    assert row["execution_status"] == "NOT_RUN"
    assert row["gate_status"] == "PENDING"
    assert "MISSING_EXECUTOR_CAPABILITY:expected_binary_path" in row["blocker"]
    assert "MISSING_EXECUTOR_CAPABILITY:scorer_mode" in row["blocker"]
    assert "MISSING_EXECUTOR_CAPABILITY:pibt_mode" in row["blocker"]
    assert "MISSING_EXECUTOR_CAPABILITY:enable_pibt_lite" in row["blocker"]


def test_fake_executor_hashes_summary_only_and_repeat_consistency(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"deterministic-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    kwargs = {
        "executor": _successful_fake_executor,
        "executor_binary": binary,
        "source_paths": [
            Path("scripts/eval/g4irsf12_reproducible_harness.py"),
            Path("tests/test_g4irsf12_reproducible_harness.py"),
        ],
        "root": ROOT,
        "summary_only": True,
    }
    left = harness.execute_case(case, 144, **kwargs)
    right = harness.execute_case(case, 144, **kwargs)
    assert left["execution_status"] == "EXECUTED"
    assert left["gate_status"] == "PASS"
    assert left["completed_segment_count"] == 144
    assert left["complete_raw_bag_count"] == left["selected_raw_bag_count"]
    assert left["source_wait_mean_minutes"] > 0.0
    for field in (
        "input_prefix_sha256",
        "case_config_sha256",
        "source_bundle_sha256",
        "binary_sha256",
        "loaded_cpp_binary_sha256",
        "deterministic_result_sha256",
    ):
        assert len(left[field]) == 64
    assert left["deterministic_result_sha256"] == right[
        "deterministic_result_sha256"
    ]
    repeated = harness.apply_repeat_consistency([left, right])
    assert {row["repeat_consistency"] for row in repeated} == {"MATCH"}

    changed = dict(right)
    changed["deterministic_result_sha256"] = "f" * 64
    mismatch = harness.apply_repeat_consistency([left, changed])
    assert {row["gate_status"] for row in mismatch} == {"FAIL"}
    assert {row["repeat_consistency"] for row in mismatch} == {"MISMATCH"}


def test_explicit_mode_echo_survives_canonical_alias_csv_roundtrip(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"explicit-mode-echo")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )

    def aliased_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "resource_semantics_id": "canonical_resource_internal",
            "scorer_mode": "canonical_scorer_internal",
            "pibt_mode": "canonical_pibt_internal",
            "pressure_mode": "C0_off",
            "admission_mode": "C0_off",
            "framework_mode": "canonical_framework_internal",
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        144,
        executor=aliased_executor,
        executor_binary=binary,
        source_paths=harness.FORMAL_SOURCE_PATHS,
        root=ROOT,
        executor_id=harness.FORMAL_EXECUTOR_ID,
    )
    row["repeat_index"] = 1
    row = harness.apply_repeat_consistency([row])[0]
    assert row["gate_status"] == "PASS"
    for name in harness.EXPLICIT_MODE_ECHO_CONTROLS:
        if name in case.runtime_controls:
            assert row[f"{name}_echo"] == case.runtime_controls[name]
    assert row["pressure_mode_echo"] == "off"
    assert row["survivor_metric_comparison_allowed"] is False

    ledger = tmp_path / "explicit-mode-roundtrip.csv"
    _write_result_ledger(ledger, [row])
    loaded = harness.load_result_ledger(ledger, root=ROOT)
    assert len(loaded) == 1
    assert loaded[0]["pressure_mode_echo"] == "off"
    assert loaded[0]["survivor_metric_comparison_allowed"] is False
    assert harness.authorization_blockers(case, 512, loaded) == []


def test_loaded_cpp_binary_echo_is_required_and_must_match(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"expected-runtime")
    other = tmp_path / "other.pyd"
    other.write_bytes(b"other-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    common = {
        "executor_binary": binary,
        "source_paths": [
            Path("scripts/eval/g4irsf12_reproducible_harness.py")
        ],
        "root": ROOT,
    }

    def missing_echo(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.pop("loaded_cpp_binary_path")
        summary.pop("loaded_cpp_binary_sha256")
        payload.pop("loaded_cpp_binary_path")
        payload.pop("loaded_cpp_binary_sha256")
        return {**payload, "summary": summary}

    def wrong_path(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "loaded_cpp_binary_path": str(other.resolve()),
        }
        return {
            **payload,
            "summary": summary,
            "loaded_cpp_binary_path": str(other.resolve()),
        }

    def wrong_hash(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "loaded_cpp_binary_sha256": "f" * 64,
        }
        return {
            **payload,
            "summary": summary,
            "loaded_cpp_binary_sha256": "f" * 64,
        }

    def missing_payload_echo(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        payload.pop("loaded_cpp_binary_path")
        payload.pop("loaded_cpp_binary_sha256")
        return payload

    def missing_summary_echo(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.pop("loaded_cpp_binary_path")
        summary.pop("loaded_cpp_binary_sha256")
        return {**payload, "summary": summary}

    def conflicting_echoes(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        return {
            **payload,
            "loaded_cpp_binary_path": str(other.resolve()),
            "loaded_cpp_binary_sha256": "f" * 64,
        }

    missing = harness.execute_case(
        case, 144, executor=missing_echo, **common
    )
    path_mismatch = harness.execute_case(
        case, 144, executor=wrong_path, **common
    )
    hash_mismatch = harness.execute_case(
        case, 144, executor=wrong_hash, **common
    )
    payload_missing = harness.execute_case(
        case, 144, executor=missing_payload_echo, **common
    )
    summary_missing = harness.execute_case(
        case, 144, executor=missing_summary_echo, **common
    )
    conflicting = harness.execute_case(
        case, 144, executor=conflicting_echoes, **common
    )
    assert missing["gate_status"] == "FAIL"
    assert "MISSING_LOADED_CPP_BINARY_PATH" in missing["blocker"]
    assert "MISSING_OR_INVALID_LOADED_CPP_BINARY_SHA256" in missing["blocker"]
    assert path_mismatch["gate_status"] == "FAIL"
    assert "LOADED_CPP_BINARY_PATH_MISMATCH" in path_mismatch["blocker"]
    assert hash_mismatch["gate_status"] == "FAIL"
    assert "LOADED_CPP_BINARY_SHA256_MISMATCH" in hash_mismatch["blocker"]
    assert payload_missing["gate_status"] == "FAIL"
    assert "MISSING_PAYLOAD_LOADED_CPP_BINARY_PATH" in payload_missing[
        "blocker"
    ]
    assert "MISSING_PAYLOAD_LOADED_CPP_BINARY_SHA256" in payload_missing[
        "blocker"
    ]
    assert summary_missing["gate_status"] == "FAIL"
    assert "MISSING_SUMMARY_LOADED_CPP_BINARY_PATH" in summary_missing[
        "blocker"
    ]
    assert "MISSING_SUMMARY_LOADED_CPP_BINARY_SHA256" in summary_missing[
        "blocker"
    ]
    assert conflicting["gate_status"] == "FAIL"
    assert "LOADED_CPP_BINARY_PATH_ECHO_CONFLICT" in conflicting["blocker"]
    assert "LOADED_CPP_BINARY_SHA256_ECHO_CONFLICT" in conflicting["blocker"]
    for rejected in (
        missing,
        path_mismatch,
        hash_mismatch,
        payload_missing,
        summary_missing,
        conflicting,
    ):
        assert rejected["execution_status"] == "FAILED"
        assert rejected["evidence_status"] == "INVALID_EVIDENCE_REJECTED"
        assert rejected["binary_provenance_pass"] is False


def test_same_byte_binary_copy_cannot_match_current_run_provenance(
    tmp_path: Path,
) -> None:
    current = tmp_path / "current.pyd"
    copied = tmp_path / "copied.pyd"
    current.write_bytes(b"same-runtime-bytes")
    copied.write_bytes(b"same-runtime-bytes")
    digest = harness.file_sha256(current)
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(
        case,
        144,
        binary_sha256=digest,
        source_bundle_sha256="b" * 64,
        executor_source_sha256="d" * 64,
        loaded_cpp_binary_path=str(copied.resolve()),
    )
    provenance = harness.ExecutionProvenance(
        binary_path=str(current.resolve()),
        binary_sha256=digest,
        source_bundle_sha256="b" * 64,
        source_path_manifest_sha256=(
            harness.FORMAL_SOURCE_PATH_MANIFEST_SHA256
        ),
        executor_id=harness.FORMAL_EXECUTOR_ID,
        executor_source_sha256="d" * 64,
    )
    assert harness.execution_provenance_matches(row, provenance) is False
    assert (
        harness.execution_provenance_matches(
            row,
            provenance,
            require_binary_file=False,
        )
        is False
    )


def test_exact_frozen_phase_j_identity_auto_matches_absent_binary() -> None:
    binary_path = (
        r"C:\__czr005_absent_historical_fixture__\phase-j"
        r"\czr005_cpp.pyd"
    )
    lexical_echo = (
        "c:/__CZR005_ABSENT_HISTORICAL_FIXTURE__/phase-j/./czr005_cpp.pyd"
    )
    binary_sha256 = (
        "82f15f08a8cff0e887447f017f0aa03fffabe9bfb3a79a563b16d779219d8222"
    )
    source_sha256 = (
        "eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7"
    )
    executor_sha256 = (
        "e1b59eecded76f59991a9276f614aea747a573dbaffdf2139cfd9b6096b69971"
    )
    finalist = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F1"
    )
    rows = [
        _valid_prior_result(
            finalist,
            harness.FULL_SIZE_SEGMENTS,
            repeat_index=index,
            binary_sha256=binary_sha256,
            source_bundle_sha256=source_sha256,
            executor_source_sha256=executor_sha256,
            loaded_cpp_binary_path=lexical_echo,
        )
        for index in range(1, 6)
    ]
    provenance = harness.ExecutionProvenance(
        binary_path=binary_path,
        binary_sha256=binary_sha256,
        source_bundle_sha256=source_sha256,
        source_path_manifest_sha256=(
            harness.FORMAL_SOURCE_PATH_MANIFEST_SHA256
        ),
        executor_id=harness.FORMAL_EXECUTOR_ID,
        executor_source_sha256=executor_sha256,
    )

    assert not harness.execution_provenance_matches(rows[0], provenance)
    assert harness.execution_provenance_matches(
        rows[0],
        provenance,
        require_binary_file=False,
    )
    strict_bundle = harness.candidate_bundle(
        rows,
        current_provenance=provenance,
        require_binary_file=True,
    )
    historical_bundle = harness.candidate_bundle(
        rows,
        current_provenance=provenance,
    )
    strict_finalist = next(
        row
        for row in strict_bundle["finalists"]
        if row["candidate_id"] == "J_F1"
    )
    historical_finalist = next(
        row
        for row in historical_bundle["finalists"]
        if row["candidate_id"] == "J_F1"
    )
    assert strict_finalist["executed_full_repeat_count"] == 0
    assert historical_finalist["executed_full_repeat_count"] == 5
    assert historical_finalist["promotion_status"] == "PROMOTED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("binary_sha256", "0" * 64),
        ("source_bundle_sha256", "1" * 64),
        ("executor_source_sha256", "2" * 64),
        ("executor_id", "fixture:drifted_executor"),
        ("source_path_manifest_sha256", "3" * 64),
    ],
)
def test_candidate_bundle_auto_mode_rejects_any_frozen_identity_drift(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    missing_binary = str(tmp_path / "absent" / "czr005_cpp.pyd")
    identity: dict[str, str] = {
        "binary_path": missing_binary,
        "binary_sha256": (
            "82f15f08a8cff0e887447f017f0aa03fffabe9bfb3a79a563b16d779219d8222"
        ),
        "source_bundle_sha256": (
            "eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7"
        ),
        "source_path_manifest_sha256": (
            harness.FORMAL_SOURCE_PATH_MANIFEST_SHA256
        ),
        "executor_id": harness.FORMAL_EXECUTOR_ID,
        "executor_source_sha256": (
            "e1b59eecded76f59991a9276f614aea747a573dbaffdf2139cfd9b6096b69971"
        ),
    }
    identity[field] = value
    finalist = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F1"
    )
    rows = [
        _valid_prior_result(
            finalist,
            harness.FULL_SIZE_SEGMENTS,
            repeat_index=index,
            binary_sha256=identity["binary_sha256"],
            source_bundle_sha256=identity["source_bundle_sha256"],
            executor_source_sha256=identity["executor_source_sha256"],
            loaded_cpp_binary_path=missing_binary,
        )
        for index in range(1, 6)
    ]
    for row in rows:
        row["executor_id"] = identity["executor_id"]
        row["source_path_manifest_sha256"] = identity[
            "source_path_manifest_sha256"
        ]
    rows = [harness.seal_evidence_row(row) for row in rows]
    provenance = harness.ExecutionProvenance(**identity)

    bundle = harness.candidate_bundle(
        rows,
        current_provenance=provenance,
    )
    admitted = next(
        row
        for row in bundle["finalists"]
        if row["candidate_id"] == "J_F1"
    )
    assert admitted["executed_full_repeat_count"] == 0
    assert admitted["promotion_status"] == "PENDING"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "loaded_cpp_binary_path",
            r"C:\__czr005_absent_historical_fixture__\other"
            r"\czr005_cpp.pyd",
        ),
        ("loaded_cpp_binary_sha256", "f" * 64),
    ],
)
def test_historical_lexical_binary_match_still_rejects_path_or_hash_drift(
    field: str,
    value: str,
) -> None:
    binary_path = (
        r"C:\__czr005_absent_historical_fixture__\phase-j"
        r"\czr005_cpp.pyd"
    )
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(
        case,
        144,
        loaded_cpp_binary_path=binary_path,
    )
    row[field] = value
    row = harness.seal_evidence_row(row)
    provenance = harness.ExecutionProvenance(
        binary_path=binary_path,
        binary_sha256="c" * 64,
        source_bundle_sha256="b" * 64,
        source_path_manifest_sha256=(
            harness.FORMAL_SOURCE_PATH_MANIFEST_SHA256
        ),
        executor_id=harness.FORMAL_EXECUTOR_ID,
        executor_source_sha256="d" * 64,
    )

    assert not harness.execution_provenance_matches(
        row,
        provenance,
        require_binary_file=False,
    )


def test_early_abort_retains_partial_result(tmp_path: Path) -> None:
    def early_executor(**kwargs: object) -> dict[str, object]:
        input_rows = list(kwargs["input_rows"])
        bags = []
        for row in input_rows[:12]:
            release = float(row["pass_time"])
            bags.append(
                {
                    "segment_id": row["segment_id"],
                    "release_time": release,
                    "admitted_time": release + 1.0,
                    "finish_time": release + 5.0,
                    "completed": True,
                }
            )
        summary = _safe_summary(requested=len(input_rows), completed=len(bags))
        summary["termination_reason"] = harness.EARLY_ABORT_STATUS
        summary.update(
            {
                "resource_semantics_id": kwargs["resource_semantics"],
                "scorer_mode": kwargs["scorer_mode"],
                "pibt_mode": kwargs["pibt_mode"],
                "pibt_max_depth": kwargs["pibt_max_depth"],
                "pressure_mode": kwargs["pressure_mode"],
                "admission_mode": kwargs["admission_mode"],
                "local_queue_capacity": kwargs.get("local_queue_capacity", 0),
                "max_events": kwargs["max_events"],
            }
        )
        summary.update(_mode_echoes(kwargs))
        for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS:
            summary[name] = kwargs[name]
        binary_echo = _binary_echo(kwargs)
        summary.update(binary_echo)
        return {
            "summary": summary,
            "bags": bags,
            **binary_echo,
        }

    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"early-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = harness.execute_case(
        case,
        144,
        executor=early_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["execution_status"] == harness.EARLY_ABORT_STATUS
    assert row["gate_status"] == "FAIL"
    assert row["completed_segment_count"] == 12
    assert row["original_entry_mean_minutes"] is None
    assert harness.EARLY_ABORT_STATUS in row["blocker"]


def test_control_evidence_denominators_are_explicit() -> None:
    rows = harness.load_control_evidence(ROOT)
    historical_processed = next(
        row
        for row in rows
        if row["phase"] == "B"
        and row["candidate_id"] == "historical_hca_parsed"
        and row["primary_denominator"] == "processed_segment_attempt_time_tth"
    )
    historical_original = next(
        row
        for row in rows
        if row["phase"] == "B"
        and row["candidate_id"] == "historical_hca_parsed"
        and row["primary_denominator"] == "original_entry_time_tth"
    )
    assert historical_processed["reported_mean_minutes"] == pytest.approx(
        3.9671227110082086
    )
    assert historical_original["original_entry_mean_minutes"] == pytest.approx(
        5.764936746096144
    )
    assert historical_processed["execution_status"] == "NOT_RUN"
    assert historical_processed["gate_status"] == "NOT_APPLICABLE"
    assert not any(
        row["gate_status"] == "PASS" and row["execution_status"] == "NOT_RUN"
        for row in rows
    )


def test_plan_outputs_are_pending_and_complete(tmp_path: Path) -> None:
    rows = [
        *harness.load_control_evidence(ROOT),
        *harness.planned_results(),
    ]
    paths = harness.write_harness_outputs(
        rows,
        root=tmp_path,
        identity_root=ROOT,
    )
    assert len(paths) == len(harness.OUTPUT_PATHS)
    assert all(path.is_file() for path in paths)

    framework = tmp_path / harness.OUTPUT_PATHS["framework_csv"]
    with framework.open("r", encoding="utf-8", newline="") as handle:
        framework_rows = list(csv.DictReader(handle))
    planned = [
        row
        for row in framework_rows
        if row["evidence_status"] == "PLANNED_NOT_EXECUTED"
    ]
    assert planned
    assert all(row["execution_status"] == "NOT_RUN" for row in planned)
    assert all(row["gate_status"] == "PENDING" for row in planned)

    bundle = json.loads(
        (tmp_path / harness.OUTPUT_PATHS["candidate_bundle"]).read_text(
            encoding="utf-8"
        )
    )
    assert bundle["g4j_enabled"] is False
    assert bundle["g4j_status"] == "CLOSED"
    assert bundle["phase_j_promotion_opens_g4j"] is False
    assert bundle["promotion_status"] == "PENDING"
    assert len(bundle["finalists"]) == 3
    assert all(
        finalist["promotion_status"] == "PENDING"
        for finalist in bundle["finalists"]
    )
    promotion = (
        tmp_path / harness.OUTPUT_PATHS["promotion_report"]
    ).read_text(encoding="utf-8")
    assert "A NOT_RUN/PENDING case is never PASS" in promotion
    assert "G4J remains CLOSED" in promotion

    assert (
        harness.OUTPUT_PATHS["resource_runtime_csv"]
        != "outputs/tables/g4irsf12_resource_semantics_ab.csv"
    )
    assert (
        harness.OUTPUT_PATHS["scorer_closed_loop_csv"]
        != "outputs/tables/g4irsf12_scorer_isolation_ab.csv"
    )
    assert (
        harness.OUTPUT_PATHS["pibt_wait_for_motifs_csv"]
        == "outputs/tables/g4irsf12_wait_for_cycle_motifs.csv"
    )
    assert (
        harness.OUTPUT_PATHS["pibt_atomic_commit_rollback_csv"]
        == "outputs/tables/g4irsf12_atomic_commit_rollback.csv"
    )
    for key in (
        "pibt_depth_csv",
        "pibt_wait_for_csv",
        "pibt_wait_for_motifs_csv",
        "pibt_atomic_csv",
        "pibt_atomic_commit_rollback_csv",
    ):
        with (tmp_path / harness.OUTPUT_PATHS[key]).open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        assert {row["execution_status"] for row in rows} == {"NOT_RUN"}
        assert {row["gate_status"] for row in rows} == {"PENDING"}
    assert (
        tmp_path / harness.OUTPUT_PATHS["pibt_wait_for_csv"]
    ).read_bytes() == (
        tmp_path / harness.OUTPUT_PATHS["pibt_wait_for_motifs_csv"]
    ).read_bytes()
    assert (
        tmp_path / harness.OUTPUT_PATHS["pibt_atomic_csv"]
    ).read_bytes() == (
        tmp_path / harness.OUTPUT_PATHS["pibt_atomic_commit_rollback_csv"]
    ).read_bytes()


def test_authorization_guards_large_and_fault_tiers() -> None:
    b5 = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    assert "8192 execution requires --allow-8192" in harness.authorization_blockers(
        b5, 8_192, [], allow_8192=False
    )
    assert any(
        "prior tier" in blocker
        for blocker in harness.authorization_blockers(
            b5, 8_192, [], allow_8192=True
        )
    )
    h_fault = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    assert any(
        "H_stable_no_fault" in blocker
        for blocker in harness.authorization_blockers(h_fault, 2_048, [])
    )


def test_b2_is_static_not_run_and_full_b_never_invokes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b_cases = {
        case.framework_label: case for case in harness.framework_delta_cases()
    }
    b2 = b_cases["B2"]
    blocker = "OLD_SCHEDULING_ORDER_ONE_STEP_EXECUTOR_NOT_IMPLEMENTED"
    assert b2.execution_blocker == blocker
    assert harness.planned_result(b2, 144)["blocker"] == blocker

    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"b2-static-blocker")
    source = tmp_path / "runtime_source.py"
    source.write_text("FROZEN = True\n", encoding="utf-8")
    binary_digest = harness.file_sha256(binary)
    source_digest = harness.source_bundle_sha256([source], root=ROOT)

    def dummy_executor(**_kwargs: object) -> dict[str, object]:
        return {}

    executor_digest = harness.inspect_executor(dummy_executor).source_sha256
    invoked: list[str] = []

    def fake_execute_case(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        invoked.append(case.case_id)
        assert case.case_id != b2.case_id
        return _valid_prior_result(
            case,
            size_segments,
            binary_sha256=binary_digest,
            source_bundle_sha256=source_digest,
            executor_source_sha256=executor_digest,
            loaded_cpp_binary_path=str(binary.resolve()),
        )

    monkeypatch.setattr(cli, "execute_case", fake_execute_case)
    monkeypatch.setattr(cli, "_executor", lambda _value: dummy_executor)
    monkeypatch.setattr(cli, "DEFAULT_SOURCE_PATHS", (source,))
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )
    output_root = tmp_path / "published"
    args = cli._parser().parse_args(
        [
            "--execute",
            "--phases",
            "B",
            "--max-segments",
            "8192",
            "--allow-8192",
            "--binary",
            str(binary),
            "--output-root",
            str(output_root),
        ]
    )
    result = cli.run(args)
    assert result["new_execution_row_count"] == 16
    assert invoked == [
        b_cases[label].case_id
        for label in ("B3", "B4", "B5", "B6")
        for _size in (144, 512, 2_048, 8_192)
    ]
    with (
        output_root / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    b2_rows = [
        row
        for row in rows
        if row["case_id"] == b2.case_id
    ]
    assert {row["size_segments"] for row in b2_rows} == {
        "144",
        "512",
        "2048",
        "8192",
    }
    assert {row["execution_status"] for row in b2_rows} == {"NOT_RUN"}
    assert {
        row["evidence_status"] for row in b2_rows
    } == {"AUTHORIZATION_BLOCKED_NOT_RUN"}
    assert all(blocker in row["blocker"] for row in b2_rows)


def test_h_fault_policy_off_progresses_on_executed_negative_evidence() -> None:
    recovery = {case.case_id: case for case in harness.fault_recovery_cases()}
    stable = recovery["H_stable_no_fault"]
    policy_off = recovery["H_fault_policy_off"]

    def retained_failure(
        size: int,
        *,
        repeat_index: int = 1,
        result_hash_character: str = "a",
    ) -> dict[str, object]:
        row = _valid_prior_result(
            policy_off,
            size,
            repeat_index=repeat_index,
            result_hash_character=result_hash_character,
        )
        row["execution_status"] = "PARTIAL"
        row["gate_status"] = "FAIL"
        row["evidence_status"] = "NEGATIVE_OR_PARTIAL_RESULT_RETAINED"
        row["termination_reason"] = "PARTIAL"
        row["blocker"] = (
            "selected prefix did not complete; survivor metrics excluded"
        )
        row["completed_segment_count"] = size - 1
        row["complete_raw_bag_count"] = int(
            row["selected_raw_bag_count"]
        ) - 1
        row["failed_segment_count"] = 1
        row["completion_rate"] = (
            int(row["complete_raw_bag_count"])
            / int(row["selected_raw_bag_count"])
        )
        row["comparison_eligible"] = False
        return harness.seal_evidence_row(row)

    stable_8192 = _valid_prior_result(stable, 8_192)
    off_2048 = retained_failure(2_048)
    assert harness.authorization_blockers(
        policy_off,
        8_192,
        [stable_8192, off_2048],
        allow_8192=True,
    ) == []
    segment_denominator = harness.seal_evidence_row(
        {
            **off_2048,
            "completion_rate": (2_048 - 1) / 2_048,
        }
    )
    assert not harness._accepted_tier_was_executed(
        policy_off.case_id,
        2_048,
        [segment_denominator],
    )
    not_applicable = harness.seal_evidence_row(
        {
            **_valid_prior_result(policy_off, 2_048),
            "gate_status": "NOT_APPLICABLE",
            "evidence_status": "EXECUTED_CONFIGURATION_NOT_APPLICABLE",
        }
    )
    assert not harness._accepted_tier_was_executed(
        policy_off.case_id,
        2_048,
        [not_applicable],
    )
    physical_reroute = harness.seal_evidence_row(
        {
            **off_2048,
            "fault_physical_interlock_hold_count": 0,
            "fault_physical_interlock_reroute_count": 1,
        }
    )
    assert harness.authorization_blockers(
        policy_off,
        8_192,
        [stable_8192, physical_reroute],
        allow_8192=True,
    ) == []

    off_not_run = harness.planned_result(policy_off, 2_048)
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [stable_8192, off_not_run],
            allow_8192=True,
        )
    )
    tampered = dict(off_2048)
    tampered["loaded_cpp_binary_sha256"] = "e" * 64
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [stable_8192, tampered],
            allow_8192=True,
        )
    )
    for field in ("event_limit_reached", "time_limit_reached"):
        limited = {**off_2048, field: True}
        assert any(
            "prior tier 2048" in blocker
            for blocker in harness.authorization_blockers(
                policy_off,
                8_192,
                [stable_8192, limited],
                allow_8192=True,
            )
        )
    bad_termination = {
        **off_2048,
        "termination_reason": "WORKER_FAILURE",
    }
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [stable_8192, bad_termination],
            allow_8192=True,
        )
    )
    for field, value in (
        ("fault_affected_bag_count", 0),
        ("unsafe_entry_count", 1),
        ("conflict_count", 1),
        ("runtime_full_astar_calls", 1),
        ("sensor_loss_mode_used", True),
        ("fault_notification_drop_count", 1),
        ("fault_physical_interlock_rejection_count", 0),
        ("fault_physical_interlock_hold_count", 0),
        ("fault_local_action_count", 1),
        ("fault_local_hold_count", 1),
        ("fault_reroute_count", 1),
        ("reservation_depth", 2),
        ("max_edges_selected_per_bag_per_decision", 2),
        (
            "max_actions_committed_per_pibt_batch",
            int(policy_off.runtime_controls["pibt_max_ready_bags"]) + 1,
        ),
        ("event_count", int(off_2048["declared_max_events"]) + 1),
        ("completed_segment_count", 2_048),
        ("failed_segment_count", 0),
        ("complete_raw_bag_count", off_2048["selected_raw_bag_count"]),
        ("comparison_eligible", True),
        ("completion_rate", 1.0),
    ):
        unsafe = {**off_2048, field: value}
        assert any(
            "prior tier 2048" in blocker
            for blocker in harness.authorization_blockers(
                policy_off,
                8_192,
                [stable_8192, unsafe],
                allow_8192=True,
            )
        )

    stable_full = _valid_prior_result(stable, harness.FULL_SIZE_SEGMENTS)
    off_8192 = retained_failure(8_192)
    assert harness.authorization_blockers(
        policy_off,
        harness.FULL_SIZE_SEGMENTS,
        [stable_full, off_8192],
        allow_full=True,
    ) == []

    stable_repeats = [
        _valid_prior_result(
            stable,
            8_192,
            repeat_index=index,
            result_hash_character="c",
        )
        for index in (1, 2)
    ]
    off_repeats = [
        retained_failure(
            2_048,
            repeat_index=index,
            result_hash_character="d",
        )
        for index in (1, 2)
    ]
    assert harness.authorization_blockers(
        policy_off,
        8_192,
        [*stable_repeats, *off_repeats],
        allow_8192=True,
        required_repeat_count=2,
    ) == []
    inconsistent_repeats = [
        off_repeats[0],
        {
            **off_repeats[1],
            "deterministic_result_sha256": "f" * 64,
        },
    ]
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [*stable_repeats, *inconsistent_repeats],
            allow_8192=True,
            required_repeat_count=2,
        )
    )
    for indexes in ((2, 3), (1, 3)):
        drifted_indexes = [
            {
                **off_repeats[offset],
                "repeat_index": index,
            }
            for offset, index in enumerate(indexes)
        ]
        assert any(
            "prior tier 2048" in blocker
            for blocker in harness.authorization_blockers(
                policy_off,
                8_192,
                [*stable_repeats, *drifted_indexes],
                allow_8192=True,
                required_repeat_count=2,
            )
        )
    extra_repeat = {
        **off_repeats[1],
        "repeat_index": 3,
    }
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [*stable_repeats, *off_repeats, extra_repeat],
            allow_8192=True,
            required_repeat_count=2,
        )
    )
    failed_repeat = {
        **off_repeats[1],
        "execution_status": "FAILED",
    }
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [*stable_repeats, off_repeats[0], failed_repeat],
            allow_8192=True,
            required_repeat_count=2,
        )
    )

    repeated = harness.apply_repeat_consistency(off_repeats)
    assert {row["repeat_consistency"] for row in repeated} == {"MATCH"}
    hash_mismatch = harness.apply_repeat_consistency(
        [off_repeats[0], inconsistent_repeats[1]]
    )
    assert {row["repeat_consistency"] for row in hash_mismatch} == {
        "MISMATCH"
    }
    status_mismatch = harness.apply_repeat_consistency(
        [
            off_repeats[0],
            {
                **off_repeats[1],
                "execution_status": "EXECUTED",
            },
        ]
    )
    assert {row["repeat_consistency"] for row in status_mismatch} == {
        "MISMATCH"
    }

    stable_five = [
        _valid_prior_result(
            stable,
            8_192,
            repeat_index=index,
            result_hash_character="1",
        )
        for index in range(1, 6)
    ]
    off_five = [
        retained_failure(
            2_048,
            repeat_index=index,
            result_hash_character="2",
        )
        for index in range(1, 6)
    ]
    assert harness.authorization_blockers(
        policy_off,
        8_192,
        [*stable_five, *off_five],
        allow_8192=True,
        required_repeat_count=5,
    ) == []
    assert {
        row["repeat_consistency"]
        for row in harness.apply_repeat_consistency(off_five)
    } == {"MATCH"}
    off_five_mismatch = [
        *off_five[:4],
        {
            **off_five[4],
            "deterministic_result_sha256": "3" * 64,
        },
    ]
    assert {
        row["repeat_consistency"]
        for row in harness.apply_repeat_consistency(off_five_mismatch)
    } == {"MISMATCH"}
    assert any(
        "prior tier 2048" in blocker
        for blocker in harness.authorization_blockers(
            policy_off,
            8_192,
            [*stable_five, *off_five_mismatch],
            allow_8192=True,
            required_repeat_count=5,
        )
    )


@pytest.mark.parametrize(
    ("field", "tampered"),
    (
        ("fault_policy_enabled_echo", False),
        ("sensor_loss_mode_used", False),
        ("fault_notification_drop_count", 1),
        ("fault_physical_interlock_rejection_count", 0),
        ("fault_physical_interlock_reroute_count", 0),
        ("fault_local_action_count", 1),
        ("fault_reroute_count", 1),
    ),
)
def test_sensor_loss_prior_evidence_is_fail_closed(
    field: str,
    tampered: object,
) -> None:
    sensor_loss = next(
        case
        for case in harness.fault_recovery_cases()
        if case.case_id == "H_notification_drop"
    )
    row = _valid_prior_result(sensor_loss, 2_048)
    row[field] = tampered
    with pytest.raises(harness.HarnessValidationError):
        harness._validate_case_ledger_row(row, sensor_loss, root=ROOT)


def test_pass_tier_requires_exact_canonical_repeat_indexes() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    canonical = [
        _valid_prior_result(
            case,
            144,
            repeat_index=index,
            result_hash_character="a",
        )
        for index in (1, 2)
    ]
    assert harness.authorization_blockers(
        case,
        512,
        canonical,
        required_repeat_count=2,
    ) == []
    for indexes in ((2, 3), (1, 3)):
        drifted = [
            {**canonical[offset], "repeat_index": index}
            for offset, index in enumerate(indexes)
        ]
        assert any(
            "prior tier 144" in blocker
            for blocker in harness.authorization_blockers(
                case,
                512,
                drifted,
                required_repeat_count=2,
            )
        )
    extra = {**canonical[1], "repeat_index": 3}
    assert any(
        "prior tier 144" in blocker
        for blocker in harness.authorization_blockers(
            case,
            512,
            [*canonical, extra],
            required_repeat_count=2,
        )
    )


def test_pressure_and_admission_values_match_runtime_canonical_names() -> None:
    cases = {case.control_label: case for case in harness.pressure_credit_cases()}
    assert cases["C0"].runtime_controls["pressure_mode"] == "off"
    assert cases["C0"].runtime_controls["admission_mode"] == "off"
    assert (
        cases["C1"].runtime_controls["pressure_mode"]
        == "absolute_downstream_queue_penalty"
    )
    assert (
        cases["C2"].runtime_controls["pressure_mode"]
        == "goal_conditioned_differential"
    )
    assert (
        cases["C3"].runtime_controls["pressure_mode"]
        == "distance_biased_differential"
    )
    assert (
        cases["C4"].runtime_controls["admission_mode"]
        == "expiring_first_edge_credit"
    )


def test_c_e_f_matrices_are_explicit_and_preserve_isolation_controls() -> None:
    c_cases = harness.resource_semantics_cases()
    e_cases = harness.scorer_closed_loop_cases()
    f_cases = harness.pibt_depth_cases()
    assert {case.resource_label for case in c_cases} == set(
        harness.RESOURCE_LABELS
    )
    assert all(case.sizes == (144, 512, 2_048, 8_192) for case in c_cases)
    assert {case.scorer_label for case in e_cases} == set(
        harness.SCORER_LABELS
    )
    assert all(case.sizes == (2_048, 8_192) for case in e_cases)
    assert {case.pibt_label for case in f_cases} == set(harness.PIBT_LABELS)
    assert all(case.sizes == (2_048, 8_192) for case in f_cases)
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in f_cases
    )
    assert all(
        case.runtime_controls["max_events"] == harness.FORMAL_MAX_EVENTS
        for case in harness.all_cases()
    )
    assert all(
        case.sizes == (144, 512, 2_048, 8_192)
        for case in harness.framework_delta_cases()
    )
    assert all(
        case.sizes == (2_048, 8_192)
        for case in harness.pressure_credit_cases()
    )


def test_finite_queue_capacity_is_frozen_for_isolated_pibt_controls() -> None:
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.framework_delta_cases()
    )
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.pressure_credit_cases()
    )
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.fault_recovery_cases()
    )
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.original_scale_cases()
    )


def test_f_runtime_requires_audit_counters_and_unlimited_is_not_applicable(
    tmp_path: Path,
) -> None:
    case = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def pibt_executor(
        *,
        reported_capacity: int,
        **kwargs: object,
    ) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.update(
            {
                "local_queue_capacity": reported_capacity,
                "max_edges_selected_per_bag_per_decision": 1,
                "max_edges_selected_per_arrive": 2,
                "max_actions_committed_per_pibt_batch": 2,
                "bounded_local_pibt_applicability_count": 1,
                "bounded_local_pibt_attempt_count": 2,
                "bounded_local_pibt_prepare_count": 1,
                "bounded_local_pibt_validate_count": 5,
                "bounded_local_pibt_commit_count": 1,
                "bounded_local_pibt_rollback_count": 0,
                "bounded_local_pibt_backtrack_count": 0,
                "bounded_local_pibt_wait_for_cycle_count": 0,
                "bounded_local_pibt_handoff_count": 0,
            }
        )
        return {**payload, "summary": summary}

    common = {
        "executor_binary": binary,
        "source_paths": [
            Path("scripts/eval/g4irsf12_reproducible_harness.py")
        ],
        "root": ROOT,
    }
    finite = harness.execute_case(
        case,
        2_048,
        executor=lambda **kwargs: pibt_executor(
            reported_capacity=harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY,
            **kwargs,
        ),
        **common,
    )
    assert finite["gate_status"] == "PASS"
    assert finite["pibt_handoff_count"] == 0
    assert finite["pibt_same_bag_fallback_count"] == 0
    assert finite["pibt_applicability_count"] == 1
    assert finite["max_edges_selected_per_bag_per_decision"] == 1
    assert finite["max_edges_selected_per_arrive"] == 2
    assert finite["max_actions_committed_per_pibt_batch"] == 2

    unlimited = harness.execute_case(
        case,
        2_048,
        executor=lambda **kwargs: pibt_executor(
            reported_capacity=0,
            **kwargs,
        ),
        **common,
    )
    assert unlimited["gate_status"] == "NOT_APPLICABLE"
    assert unlimited["evidence_status"] == (
        "EXECUTED_CONFIGURATION_NOT_APPLICABLE"
    )
    assert "unlimited local_queue_capacity" in unlimited["blocker"]

    def inactive_executor(**kwargs: object) -> dict[str, object]:
        payload = pibt_executor(
            reported_capacity=harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY,
            **kwargs,
        )
        summary = {
            **payload["summary"],
            "bounded_local_pibt_applicability_count": 0,
            "bounded_local_pibt_attempt_count": 0,
            "bounded_local_pibt_prepare_count": 0,
            "bounded_local_pibt_validate_count": 0,
            "bounded_local_pibt_commit_count": 0,
            "max_actions_committed_per_pibt_batch": 0,
        }
        return {**payload, "summary": summary}

    inactive = harness.execute_case(
        case,
        2_048,
        executor=inactive_executor,
        **common,
    )
    assert inactive["gate_status"] == "NOT_APPLICABLE"
    assert "did not exercise positive" in inactive["blocker"]


def test_unlimited_capacity_not_applicable_round_trips_fail_closed(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P2"
    )
    expected_capacity = int(
        case.runtime_controls["local_queue_capacity"]
    )
    capacity_mismatch = (
        "RUNTIME_CONTROL_ECHO_MISMATCH:local_queue_capacity="
        f"0, expected {expected_capacity}"
    )
    not_applicable_reason = (
        "P2 with unlimited local_queue_capacity is NOT_APPLICABLE "
        "to bounded-local PIBT evidence"
    )
    row = harness.seal_evidence_row(
        {
            **_valid_prior_result(case, 2_048),
            "local_queue_capacity": 0,
            "gate_status": "NOT_APPLICABLE",
            "evidence_status": (
                "EXECUTED_CONFIGURATION_NOT_APPLICABLE"
            ),
            "blocker": (
                f"{capacity_mismatch} | {not_applicable_reason}"
            ),
        }
    )
    ledger = tmp_path / "capacity-not-applicable.csv"
    _write_result_ledger(ledger, [row])
    admitted = harness.load_result_ledger(ledger, root=ROOT)
    assert len(admitted) == 1
    assert admitted[0]["gate_status"] == "NOT_APPLICABLE"

    forged = harness.seal_evidence_row(
        {
            **row,
            "pressure_weight_echo": 9.0,
        }
    )
    forged_ledger = tmp_path / "capacity-not-applicable-forged.csv"
    _write_result_ledger(forged_ledger, [forged])
    with pytest.raises(
        harness.HarnessValidationError,
        match="RUNTIME_CONTROL_ECHO_MISMATCH:pressure_weight",
    ):
        harness.load_result_ledger(forged_ledger, root=ROOT)


def test_phase_j_is_independent_of_g4j_and_uses_matched_original_entry(
    tmp_path: Path,
) -> None:
    fast = harness.evaluate_original_entry_performance(4.0)
    assert fast["matched_original_entry_performance_gate"] == "PASS"
    between = harness.evaluate_original_entry_performance(4.2)
    assert between["v2_safe_original_entry_gate"] == "FAIL"
    assert between["corrected_hca_original_entry_gate"] == "PASS"
    assert between["matched_original_entry_performance_gate"] == "FAIL"
    assert "not comparable" in between["processed_attempt_warning"]

    finalist = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F1"
    )
    blockers = harness.authorization_blockers(
        finalist,
        harness.FULL_SIZE_SEGMENTS,
        [],
        allow_full=True,
        promoted_finalists=["J_F1"],
    )
    assert not any("G4J" in blocker for blocker in blockers)

    binary = tmp_path / "formal-runtime.pyd"
    binary.write_bytes(b"formal-candidate-runtime")
    binary_sha256 = harness.file_sha256(binary)
    source_sha256 = "b" * 64
    executor_sha256 = "d" * 64
    rows = [
        _valid_prior_result(
            finalist,
            harness.FULL_SIZE_SEGMENTS,
            repeat_index=index,
            result_hash_character="a",
            binary_sha256=binary_sha256,
            source_bundle_sha256=source_sha256,
            executor_source_sha256=executor_sha256,
            loaded_cpp_binary_path=str(binary.resolve()),
        )
        for index in range(1, 6)
    ]
    provenance = harness.ExecutionProvenance(
        binary_path=str(binary.resolve()),
        binary_sha256=binary_sha256,
        source_bundle_sha256=source_sha256,
        source_path_manifest_sha256=(
            harness.FORMAL_SOURCE_PATH_MANIFEST_SHA256
        ),
        executor_id=harness.FORMAL_EXECUTOR_ID,
        executor_source_sha256=executor_sha256,
    )
    bundle = harness.candidate_bundle(
        rows,
        current_provenance=provenance,
    )
    promoted = next(
        row for row in bundle["finalists"] if row["candidate_id"] == "J_F1"
    )
    assert bundle["g4j_status"] == "CLOSED"
    assert bundle["promotion_status"] == "READY"
    assert promoted["promotion_status"] == "PROMOTED"
    assert promoted["v2_safe_original_entry_gate"] == "PASS"
    assert promoted["corrected_hca_original_entry_gate"] == "PASS"
    assert "historical_engineering_target_minutes" not in bundle

    unverified = harness.candidate_bundle(rows)
    assert unverified["promotion_status"] == "PENDING"
    assert unverified["current_provenance_status"] == "UNVERIFIED"

    duplicate_indexes = [
        harness.seal_evidence_row({**row, "repeat_index": 1})
        for row in rows
    ]
    duplicate_bundle = harness.candidate_bundle(
        duplicate_indexes,
        current_provenance=provenance,
    )
    duplicate = next(
        row
        for row in duplicate_bundle["finalists"]
        if row["candidate_id"] == "J_F1"
    )
    assert duplicate_bundle["promotion_status"] == "PENDING"
    assert duplicate["promotion_status"] == "PENDING"
    assert "exact indexes 1..5" in duplicate["blocker"]

    stale_provenance = harness.ExecutionProvenance(
        **{
            **provenance.__dict__,
            "source_bundle_sha256": "e" * 64,
        }
    )
    stale_bundle = harness.candidate_bundle(
        rows,
        current_provenance=stale_provenance,
    )
    assert stale_bundle["promotion_status"] == "PENDING"


def test_j_f3_is_reserved_and_cannot_be_called_learned() -> None:
    f3 = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F3_RESERVED_NO_V3"
    )
    assert "no trained" in f3.finalist_role
    assert "not a learned v3 model" in f3.notes
    blockers = harness.authorization_blockers(
        f3,
        harness.FULL_SIZE_SEGMENTS,
        [],
        allow_full=True,
        promoted_finalists=[f3.candidate_id],
    )
    assert any("reserved" in blocker for blocker in blockers)


def test_resource_selection_and_c_e_f_prerequisites_fail_closed() -> None:
    resource = next(
        case for case in harness.resource_semantics_cases() if case.resource_label == "R3"
    )
    accepted_c_2048 = _valid_prior_result(resource, 2_048)
    blockers = harness.authorization_blockers(
        resource,
        8_192,
        [accepted_c_2048],
        allow_8192=True,
    )
    assert any("best-two selection" in blocker for blocker in blockers)
    assert harness.authorization_blockers(
        resource,
        8_192,
        [accepted_c_2048],
        allow_8192=True,
        promoted_resource_labels=["R3"],
    ) == []

    scorer = next(
        case for case in harness.scorer_closed_loop_cases() if case.scorer_label == "S0"
    )
    assert any(
        "C_R3 8192" in blocker
        for blocker in harness.authorization_blockers(scorer, 2_048, [])
    )
    pibt = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P0"
    )
    assert any(
        "E_S0 8192" in blocker
        for blocker in harness.authorization_blockers(pibt, 2_048, [])
    )


def test_cli_prior_evidence_is_deduped_preserved_and_atomically_replaced() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    planned = [
        harness.planned_result(case, 144),
        harness.planned_result(case, 512),
    ]
    prior_one = {
        **harness.planned_result(case, 144),
        "repeat_index": 1,
        "execution_status": "EXECUTED",
        "gate_status": "PASS",
        "evidence_status": "EXECUTED_RESULT_VALIDATED",
        "deterministic_result_sha256": "a" * 64,
    }
    prior_two = {
        **prior_one,
        "repeat_index": 2,
    }
    merged = cli._merge_evidence_rows(
        planned,
        [prior_one, prior_one, prior_two],
        [],
    )
    tier_144 = [row for row in merged if cli._tier_key(row)[2] == 144]
    assert len(tier_144) == 2
    assert {row["repeat_index"] for row in tier_144} == {1, 2}
    assert any(
        row["size_segments"] == 512 and row["execution_status"] == "NOT_RUN"
        for row in merged
    )

    replacement = {
        **prior_one,
        "repeat_index": 1,
        "deterministic_result_sha256": "b" * 64,
    }
    replaced = cli._merge_evidence_rows(
        planned,
        [prior_one, prior_two],
        [replacement],
    )
    tier_144 = [row for row in replaced if cli._tier_key(row)[2] == 144]
    assert tier_144 == [replacement]


def test_cli_plan_only_retains_an_admitted_prior_ledger(tmp_path: Path) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    prior = _valid_prior_result(
        case,
        144,
        result_hash_character="c",
    )
    ledger = tmp_path / "prior.csv"
    _write_result_ledger(ledger, [prior])
    output_root = tmp_path / "published"
    args = cli._parser().parse_args(
        [
            "--phases",
            "B",
            "--prior-ledger",
            str(ledger),
            "--output-root",
            str(output_root),
        ]
    )
    cli.run(args)
    with (
        output_root / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    retained = [
        row
        for row in rows
        if row["case_id"] == case.case_id and row["size_segments"] == "144"
    ]
    assert len(retained) == 1
    assert retained[0]["execution_status"] == "EXECUTED"
    assert retained[0]["deterministic_result_sha256"] == "c" * 64


def test_cli_preserves_prior_rows_from_an_unselected_phase(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.resource_semantics_cases()
        if case.resource_label == "R3"
    )
    prior = _valid_prior_result(
        case,
        8_192,
        result_hash_character="d",
    )
    ledger = tmp_path / "prior-c.csv"
    _write_result_ledger(ledger, [prior])

    output_root = tmp_path / "published"
    args = cli._parser().parse_args(
        [
            "--phases",
            "B",
            "--prior-ledger",
            str(ledger),
            "--output-root",
            str(output_root),
        ]
    )
    cli.run(args)
    with (
        output_root / harness.OUTPUT_PATHS["resource_runtime_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["case_id"] == case.case_id
    assert rows[0]["execution_status"] == "EXECUTED"
    assert rows[0]["deterministic_result_sha256"] == "d" * 64


def test_cli_cross_phase_prior_authorizes_selected_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"current-runtime")
    source = tmp_path / "current_source.py"
    source.write_text("CURRENT = True\n", encoding="utf-8")

    def dummy_executor(**_kwargs: object) -> dict[str, object]:
        return {}

    binary_digest = harness.file_sha256(binary)
    source_digest = harness.source_bundle_sha256([source], root=ROOT)
    executor_digest = harness.inspect_executor(
        dummy_executor
    ).source_sha256
    resource = next(
        case
        for case in harness.resource_semantics_cases()
        if case.resource_label == "R3"
    )
    prior = _valid_prior_result(
        resource,
        8_192,
        result_hash_character="e",
        binary_sha256=binary_digest,
        source_bundle_sha256=source_digest,
        executor_source_sha256=executor_digest,
        loaded_cpp_binary_path=str(binary.resolve()),
    )
    ledger = tmp_path / "prior-c.csv"
    _write_result_ledger(ledger, [prior])

    executed: list[tuple[str, int]] = []

    def fake_execute_case(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        executed.append((case.case_id, size_segments))
        return _valid_prior_result(
            case,
            size_segments,
            result_hash_character="f",
            binary_sha256=binary_digest,
            source_bundle_sha256=source_digest,
            executor_source_sha256=executor_digest,
            loaded_cpp_binary_path=str(binary.resolve()),
        )

    monkeypatch.setattr(cli, "execute_case", fake_execute_case)
    monkeypatch.setattr(cli, "_executor", lambda _value: dummy_executor)
    monkeypatch.setattr(cli, "DEFAULT_SOURCE_PATHS", (source,))
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )
    args = cli._parser().parse_args(
        [
            "--execute",
            "--phases",
            "E",
            "--case-id",
            "E_s0",
            "--binary",
            str(binary),
            "--prior-ledger",
            str(ledger),
            "--output-root",
            str(tmp_path / "published"),
        ]
    )
    result = cli.run(args)
    assert executed == [("E_s0", 2_048)]
    assert result["new_execution_row_count"] == 1


def test_cli_authorization_requires_current_prior_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"current-runtime")
    source = tmp_path / "current_source.py"
    source.write_text("CURRENT = True\n", encoding="utf-8")

    def dummy_executor(**_kwargs: object) -> dict[str, object]:
        return {}

    binary_digest = harness.file_sha256(binary)
    source_digest = harness.source_bundle_sha256([source], root=ROOT)
    executor_digest = harness.inspect_executor(
        dummy_executor
    ).source_sha256
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    old_prior = _valid_prior_result(case, 144)
    matching_prior = _valid_prior_result(
        case,
        144,
        binary_sha256=binary_digest,
        source_bundle_sha256=source_digest,
        executor_source_sha256=executor_digest,
        loaded_cpp_binary_path=str(binary.resolve()),
    )
    calls: list[int] = []

    def capability_blocked_low_tier(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        calls.append(size_segments)
        if size_segments == 144:
            return {
                **harness.planned_result(case, size_segments),
                "evidence_status": "EXECUTOR_CAPABILITY_BLOCKED",
            }
        return _valid_prior_result(
            case,
            size_segments,
            binary_sha256=binary_digest,
            source_bundle_sha256=source_digest,
            executor_source_sha256=executor_digest,
            loaded_cpp_binary_path=str(binary.resolve()),
        )

    monkeypatch.setattr(cli, "execute_case", capability_blocked_low_tier)
    monkeypatch.setattr(cli, "_executor", lambda _value: dummy_executor)
    monkeypatch.setattr(cli, "DEFAULT_SOURCE_PATHS", (source,))
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )

    def run_with_prior(
        prior: dict[str, object],
        name: str,
    ) -> tuple[dict[str, object], Path]:
        ledger = tmp_path / f"{name}.csv"
        output_root = tmp_path / name
        _write_result_ledger(ledger, [prior])
        args = cli._parser().parse_args(
            [
                "--execute",
                "--phases",
                "B",
                "--case-id",
                case.case_id,
                "--max-segments",
                "512",
                "--binary",
                str(binary),
                "--prior-ledger",
                str(ledger),
                "--output-root",
                str(output_root),
            ]
        )
        return cli.run(args), output_root

    old_result, old_output = run_with_prior(old_prior, "old")
    assert calls == [144]
    assert old_result["new_execution_row_count"] == 0
    with (
        old_output / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        old_rows = list(csv.DictReader(handle))
    retained = next(
        row
        for row in old_rows
        if row["case_id"] == case.case_id
        and row["size_segments"] == "144"
    )
    assert retained["binary_sha256"] == ""
    assert retained["execution_status"] == "NOT_RUN"
    assert retained["evidence_status"] == "EXECUTOR_CAPABILITY_BLOCKED"

    calls.clear()
    matching_result, _ = run_with_prior(matching_prior, "matching")
    assert calls == [144, 512]
    assert matching_result["new_execution_row_count"] == 1


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("case_config_sha256", "0" * 64, "case_config_sha256"),
        ("map_raw_sha256", "1" * 64, "map_raw_sha256"),
        ("input_prefix_sha256", "2" * 64, "input_prefix_sha256"),
        ("binary_sha256", "", "binary_sha256"),
        ("pressure_weight_echo", "9.0", "pressure_weight"),
    ],
)
def test_prior_ledger_rejects_drift_and_forged_pass_evidence(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(case, 144)
    row[field] = replacement
    ledger = tmp_path / f"drift-{field}.csv"
    _write_result_ledger(ledger, [row])
    with pytest.raises(harness.HarnessValidationError, match=message):
        harness.load_result_ledger(ledger, root=ROOT)


@pytest.mark.parametrize(
    ("pibt_label", "forged_values", "message"),
    [
        (
            "P0",
            {"pibt_commit_count": 1},
            "P0 pibt_commit_count must be 0",
        ),
        (
            "P2",
            {
                "pibt_prepare_count": 1,
                "pibt_rollback_count": 0,
                "pibt_same_bag_fallback_count": 999,
            },
            "pibt_same_bag_fallback_count cannot exceed pibt_prepare_count",
        ),
        (
            "P2",
            {
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 1,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 1,
                "pibt_commit_count": 0,
                "pibt_rollback_count": 1,
                "pibt_handoff_count": 999,
            },
            "pibt_handoff_count cannot exceed pibt_attempt_count",
        ),
        (
            "P2",
            {
                "max_actions_committed_per_pibt_batch": 2,
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 1,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 1,
                "pibt_commit_count": 0,
                "pibt_rollback_count": 1,
            },
            (
                "max_actions_committed_per_pibt_batch >0 requires "
                "pibt_commit_count >0"
            ),
        ),
        (
            "P2",
            {
                "max_actions_committed_per_pibt_batch": 2,
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 1,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 5,
                "pibt_commit_count": 1,
                "pibt_rollback_count": 0,
            },
            (
                "max_actions_committed_per_pibt_batch cannot exceed "
                "pibt_attempt_count"
            ),
        ),
        (
            "P2",
            {
                "max_actions_committed_per_pibt_batch": 2,
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 2,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 4,
                "pibt_commit_count": 1,
                "pibt_rollback_count": 0,
            },
            "pibt_validate_count is too small",
        ),
        (
            "P2",
            {
                "max_actions_committed_per_pibt_batch": 2,
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 2,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 5,
                "pibt_commit_count": 1,
                "pibt_rollback_count": 0,
                "pibt_handoff_count": 2,
            },
            (
                "pibt_handoff_count cannot exceed committed PIBT calls "
                "times max_actions_committed_per_pibt_batch minus one"
            ),
        ),
    ],
)
def test_prior_ledger_rejects_resealed_pibt_counter_forgery(
    tmp_path: Path,
    pibt_label: str,
    forged_values: dict[str, int],
    message: str,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == pibt_label
    )
    row = harness.seal_evidence_row(
        {
            **_valid_prior_result(case, 2_048),
            **forged_values,
        }
    )
    ledger = tmp_path / f"resealed-{pibt_label}.csv"
    _write_result_ledger(ledger, [row])
    with pytest.raises(harness.HarnessValidationError, match=message):
        harness.load_result_ledger(ledger, root=ROOT)


def test_prior_not_run_never_overwrites_current_plan() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    planned = harness.planned_result(case, 144)
    stale = {**planned, "blocker": "stale prior planning text"}
    merged = cli._merge_evidence_rows([planned], [stale], [])
    assert merged == [planned]


def test_frozen_parsed_control_remains_not_run_reference_evidence(
    tmp_path: Path,
) -> None:
    control = next(
        row
        for row in harness.load_control_evidence(ROOT)
        if row["case_id"]
        == "B_control_historical_hca_original_entry_time_tth"
    )
    ledger = tmp_path / "control.csv"
    _write_result_ledger(ledger, [control])
    admitted = harness.load_result_ledger(ledger, root=ROOT)
    assert len(admitted) == 1
    assert admitted[0]["execution_status"] == "NOT_RUN"
    assert admitted[0]["gate_status"] == "NOT_APPLICABLE"
    assert admitted[0]["evidence_status"] == (
        "PARSED_HISTORICAL_HCA_NOT_FRESH_RERUN"
    )


def test_repeat_mismatch_or_failed_repeat_cannot_authorize_next_tier() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    first = _valid_prior_result(
        case,
        144,
        repeat_index=1,
        result_hash_character="a",
    )
    mismatched = _valid_prior_result(
        case,
        144,
        repeat_index=2,
        result_hash_character="f",
    )
    blockers = harness.authorization_blockers(
        case,
        512,
        [first, mismatched],
        required_repeat_count=2,
    )
    assert any("prior tier 144" in blocker for blocker in blockers)

    failed = {**mismatched, "gate_status": "FAIL"}
    blockers = harness.authorization_blockers(
        case,
        512,
        [first, failed],
        required_repeat_count=2,
    )
    assert any("prior tier 144" in blocker for blocker in blockers)


def test_cli_applies_repeat_consistency_before_authorizing_next_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"repeat-runtime")
    binary_digest = harness.file_sha256(binary)
    source_digest = harness.source_bundle_sha256(
        cli.DEFAULT_SOURCE_PATHS,
        root=ROOT,
    )

    def dummy_executor(**_kwargs: object) -> dict[str, object]:
        return {}

    executor_digest = harness.inspect_executor(dummy_executor).source_sha256

    def mismatching_execute_case(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        calls.append(size_segments)
        character = "a" if len(calls) == 1 else "f"
        return _valid_prior_result(
            case,
            size_segments,
            result_hash_character=character,
            binary_sha256=binary_digest,
            source_bundle_sha256=source_digest,
            executor_source_sha256=executor_digest,
            loaded_cpp_binary_path=str(binary.resolve()),
        )

    monkeypatch.setattr(cli, "execute_case", mismatching_execute_case)
    monkeypatch.setattr(cli, "_executor", lambda _value: dummy_executor)
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )
    args = cli._parser().parse_args(
        [
            "--execute",
            "--phases",
            "B",
            "--case-id",
            "B5_event_corrected_handwritten",
            "--max-segments",
            "512",
            "--repeat",
            "2",
            "--binary",
            str(binary),
            "--output-root",
            str(tmp_path / "published"),
        ]
    )
    result = cli.run(args)
    assert calls == [144, 144]
    assert result["new_execution_row_count"] == 2
    with (
        tmp_path
        / "published"
        / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    tier_144 = [
        row
        for row in rows
        if row["case_id"] == "B5_event_corrected_handwritten"
        and row["size_segments"] == "144"
    ]
    tier_512 = [
        row
        for row in rows
        if row["case_id"] == "B5_event_corrected_handwritten"
        and row["size_segments"] == "512"
    ]
    assert {row["repeat_consistency"] for row in tier_144} == {"MISMATCH"}
    assert {row["gate_status"] for row in tier_144} == {"FAIL"}
    assert len(tier_512) == 1
    assert tier_512[0]["execution_status"] == "NOT_RUN"


def test_cross_phase_anchors_cannot_be_bypassed_at_later_tiers() -> None:
    scorer = next(
        case
        for case in harness.scorer_closed_loop_cases()
        if case.scorer_label == "S0"
    )
    scorer_2048 = _valid_prior_result(scorer, 2_048)
    assert any(
        "C_R3 8192" in blocker
        for blocker in harness.authorization_blockers(
            scorer,
            8_192,
            [scorer_2048],
            allow_8192=True,
        )
    )

    pibt = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P0"
    )
    pibt_2048 = _valid_prior_result(pibt, 2_048)
    assert any(
        "E_S0 8192" in blocker
        for blocker in harness.authorization_blockers(
            pibt,
            8_192,
            [pibt_2048],
            allow_8192=True,
        )
    )

    stable = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "no_fault"
    )
    stable_2048 = _valid_prior_result(stable, 2_048)
    assert any(
        "G_c6 8192" in blocker
        for blocker in harness.authorization_blockers(
            stable,
            8_192,
            [stable_2048],
            allow_8192=True,
        )
    )

    fault = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    fault_2048 = _valid_prior_result(fault, 2_048)
    assert any(
        "H_stable_no_fault" in blocker
        for blocker in harness.authorization_blockers(
            fault,
            8_192,
            [fault_2048],
            allow_8192=True,
        )
    )


def test_cli_rejects_more_than_two_reviewed_c_resources() -> None:
    args = cli._parser().parse_args(
        [
            "--phases",
            "C",
            "--promoted-resource",
            "R0",
            "--promoted-resource",
            "R1",
            "--promoted-resource",
            "R2",
        ]
    )
    with pytest.raises(ValueError, match="at most two"):
        cli.run(args)


def test_phase_j_requires_a_matching_8192_preflight() -> None:
    cases = {case.case_id: case for case in harness.original_scale_cases()}
    pressure = {
        case.control_label: case for case in harness.pressure_credit_cases()
    }
    framework = {
        case.framework_label: case for case in harness.framework_delta_cases()
    }
    recovery = {case.case_id: case for case in harness.fault_recovery_cases()}
    positive_h_ids = (
        "H_stable_no_fault",
        "H_immediate",
        "H_delayed_30s",
        "H_notification_drop",
    )
    positive_h = [
        _valid_prior_result(recovery[case_id], harness.FULL_SIZE_SEGMENTS)
        for case_id in positive_h_ids
    ]
    fault_policy_off = _valid_prior_result(
        recovery["H_fault_policy_off"],
        harness.FULL_SIZE_SEGMENTS,
    )
    fault_policy_off["execution_status"] = "PARTIAL"
    fault_policy_off["gate_status"] = "FAIL"
    fault_policy_off["evidence_status"] = (
        "NEGATIVE_OR_PARTIAL_RESULT_RETAINED"
    )
    fault_policy_off["termination_reason"] = "PARTIAL"
    fault_policy_off["blocker"] = (
        "selected prefix did not complete; survivor metrics excluded"
    )
    fault_policy_off["completed_segment_count"] = (
        harness.FULL_SIZE_SEGMENTS - 1
    )
    fault_policy_off["complete_raw_bag_count"] = (
        int(fault_policy_off["selected_raw_bag_count"]) - 1
    )
    fault_policy_off["failed_segment_count"] = 1
    fault_policy_off["completion_rate"] = (
        int(fault_policy_off["complete_raw_bag_count"])
        / int(fault_policy_off["selected_raw_bag_count"])
    )
    fault_policy_off["comparison_eligible"] = False
    fault_policy_off = harness.seal_evidence_row(fault_policy_off)
    h_matrix = [*positive_h, fault_policy_off]

    f1 = cases["J_F1_best_rule_bounded_pibt"]
    assert any(
        "G_c6 8192" in blocker
        for blocker in harness.authorization_blockers(
            f1,
            harness.FULL_SIZE_SEGMENTS,
            [],
            allow_full=True,
            promoted_finalists=[f1.candidate_id],
        )
    )
    assert harness.authorization_blockers(
        f1,
        harness.FULL_SIZE_SEGMENTS,
        [
            _valid_prior_result(pressure["C6"], 8_192),
            *h_matrix,
        ],
        allow_full=True,
        promoted_finalists=[f1.candidate_id],
    ) == []
    missing_notification = [
        row
        for row in h_matrix
        if row["case_id"] != "H_notification_drop"
    ]
    assert any(
        "H_notification_drop" in blocker
        for blocker in harness.authorization_blockers(
            f1,
            harness.FULL_SIZE_SEGMENTS,
            [
                _valid_prior_result(pressure["C6"], 8_192),
                *missing_notification,
            ],
            allow_full=True,
            promoted_finalists=[f1.candidate_id],
        )
    )
    assert not any(
        "H_fault_policy_off" in blocker
        for blocker in harness.authorization_blockers(
            f1,
            harness.FULL_SIZE_SEGMENTS,
            [
                _valid_prior_result(pressure["C6"], 8_192),
                *h_matrix,
            ],
            allow_full=True,
            promoted_finalists=[f1.candidate_id],
        )
    )
    fault_policy_not_run = harness.planned_result(
        recovery["H_fault_policy_off"],
        harness.FULL_SIZE_SEGMENTS,
    )
    assert any(
        "H_fault_policy_off" in blocker
        for blocker in harness.authorization_blockers(
            f1,
            harness.FULL_SIZE_SEGMENTS,
            [
                _valid_prior_result(pressure["C6"], 8_192),
                *positive_h,
                fault_policy_not_run,
            ],
            allow_full=True,
            promoted_finalists=[f1.candidate_id],
        )
    )

    f2 = cases["J_F2_frozen_scorer_bounded_pibt"]
    assert f2.control_label == "C0"
    assert harness.authorization_blockers(
        f2,
        harness.FULL_SIZE_SEGMENTS,
        [
            _valid_prior_result(framework["B6"], 8_192),
            *h_matrix,
        ],
        allow_full=True,
        promoted_finalists=[f2.candidate_id],
    ) == []

    pibt_off = cases["J_control_pibt_off"]
    assert harness.authorization_blockers(
        pibt_off,
        harness.FULL_SIZE_SEGMENTS,
        [
            _valid_prior_result(pressure["C5"], 8_192),
            *h_matrix,
        ],
        allow_full=True,
        promoted_finalists=[pibt_off.candidate_id],
    ) == []

    r0 = cases["J_control_resource_r0"]
    assert any(
        "lacks a fully matched 8192 preflight" in blocker
        for blocker in harness.authorization_blockers(
            r0,
            harness.FULL_SIZE_SEGMENTS,
            [],
            allow_full=True,
            promoted_finalists=[r0.candidate_id],
        )
    )


def test_fault_metrics_require_true_availability_flags(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fault-runtime")

    def unavailable_fault_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "fault_affected_bag_count": 1,
            "fault_affected_completed_count": 1,
            "fault_recovery_seconds": 0.0,
            "fault_recovery_seconds_available": False,
            "repair_backlog_slope": 0.0,
            "repair_backlog_slope_available": False,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=unavailable_fault_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "fault recovery availability is missing or false" in row["blocker"]
    assert "backlog slope availability is missing or false" in row["blocker"]


def test_fault_recovery_and_backlog_metrics_must_be_finite_and_bounded(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fault-runtime")

    def invalid_fault_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "fault_affected_bag_count": 1,
            "fault_affected_completed_count": 1,
            "fault_recovery_seconds": -1.0,
            "fault_recovery_seconds_available": True,
            "repair_backlog_slope": float("inf"),
            "repair_backlog_slope_available": True,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=invalid_fault_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "fault recovery seconds must be >=0" in row["blocker"]
    assert "repair backlog slope must be finite" in row["blocker"]
    assert row["repair_backlog_slope"] == ""


def test_f_requires_every_published_audit_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def missing_handoff_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "bounded_local_pibt_applicability_count": 1,
            "bounded_local_pibt_attempt_count": 1,
            "bounded_local_pibt_prepare_count": 1,
            "bounded_local_pibt_validate_count": 1,
            "bounded_local_pibt_commit_count": 0,
            "bounded_local_pibt_rollback_count": 0,
            "bounded_local_pibt_backtrack_count": 0,
            "bounded_local_pibt_wait_for_cycle_count": 0,
        }
        summary.pop("bounded_local_pibt_handoff_count")
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=missing_handoff_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "missing required F runtime audit metric: pibt_handoff_count" in row[
        "blocker"
    ]


def test_runtime_requires_bounded_same_bag_fallback_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def missing_fallback_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.pop("bounded_local_pibt_same_bag_fallback_count")
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=missing_fallback_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert (
        "missing required bounded same-bag fallback audit metric: "
        "pibt_same_bag_fallback_count"
    ) in row["blocker"]


def test_p0_rejects_nonzero_bounded_same_bag_fallback_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P0"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def forged_p0_fallback_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "bounded_local_pibt_same_bag_fallback_count": 1,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=forged_p0_fallback_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "P0 pibt_same_bag_fallback_count must be 0" in row["blocker"]


def test_p0_rejects_nonzero_pibt_stage_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P0"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def forged_p0_commit_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "bounded_local_pibt_commit_count": 1,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=forged_p0_commit_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "P0 pibt_commit_count must be 0" in row["blocker"]


def test_runtime_rejects_unconserved_same_bag_fallback_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def forged_fallback_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "bounded_local_pibt_applicability_count": 1,
            "bounded_local_pibt_attempt_count": 1,
            "bounded_local_pibt_prepare_count": 1,
            "bounded_local_pibt_validate_count": 1,
            "bounded_local_pibt_commit_count": 0,
            "bounded_local_pibt_rollback_count": 0,
            "bounded_local_pibt_same_bag_fallback_count": 999,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=forged_fallback_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert (
        "pibt_same_bag_fallback_count cannot exceed pibt_prepare_count"
        in row["blocker"]
    )
    assert (
        "pibt_same_bag_fallback_count cannot exceed pibt_rollback_count"
        in row["blocker"]
    )


def test_runtime_rejects_unconserved_committed_handoff_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def forged_handoff_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "bounded_local_pibt_applicability_count": 1,
            "bounded_local_pibt_attempt_count": 1,
            "bounded_local_pibt_prepare_count": 1,
            "bounded_local_pibt_validate_count": 1,
            "bounded_local_pibt_commit_count": 0,
            "bounded_local_pibt_rollback_count": 1,
            "bounded_local_pibt_handoff_count": 999,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=forged_handoff_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert (
        "pibt_handoff_count cannot exceed pibt_attempt_count"
        in row["blocker"]
    )
    assert (
        "pibt_handoff_count cannot exceed committed PIBT calls "
        "times pibt_max_ready_bags"
    ) in row["blocker"]


@pytest.mark.parametrize(
    ("forged_values", "message"),
    [
        (
            {
                "bounded_local_pibt_attempt_count": 0,
                "bounded_local_pibt_prepare_count": 1,
            },
            "pibt_prepare_count cannot exceed pibt_attempt_count",
        ),
        (
            {
                "bounded_local_pibt_attempt_count": 2,
                "bounded_local_pibt_backtrack_count": 3,
            },
            "pibt_backtrack_count cannot exceed pibt_attempt_count",
        ),
        (
            {
                "bounded_local_pibt_attempt_count": 1,
            },
            (
                "max_actions_committed_per_pibt_batch cannot exceed "
                "pibt_attempt_count"
            ),
        ),
        (
            {
                "max_actions_committed_per_pibt_batch": 1,
            },
            "max_actions_committed_per_pibt_batch must be 0 or >=2",
        ),
        (
            {
                "bounded_local_pibt_validate_count": 4,
            },
            "pibt_validate_count is too small",
        ),
        (
            {
                "bounded_local_pibt_handoff_count": 2,
            },
            (
                "pibt_handoff_count cannot exceed committed PIBT calls "
                "times max_actions_committed_per_pibt_batch minus one"
            ),
        ),
        (
            {
                "bounded_local_pibt_commit_count": 0,
                "bounded_local_pibt_rollback_count": 1,
            },
            (
                "max_actions_committed_per_pibt_batch >0 requires "
                "pibt_commit_count >0"
            ),
        ),
    ],
)
def test_runtime_rejects_impossible_pibt_counter_combinations(
    tmp_path: Path,
    forged_values: dict[str, int],
    message: str,
) -> None:
    case = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def forged_counter_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "max_actions_committed_per_pibt_batch": 2,
            "bounded_local_pibt_applicability_count": 1,
            "bounded_local_pibt_attempt_count": 2,
            "bounded_local_pibt_prepare_count": 1,
            "bounded_local_pibt_validate_count": 5,
            "bounded_local_pibt_commit_count": 1,
            "bounded_local_pibt_rollback_count": 0,
            "bounded_local_pibt_backtrack_count": 0,
            "bounded_local_pibt_handoff_count": 0,
            **forged_values,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=forged_counter_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert message in row["blocker"]


def test_event_count_cannot_exceed_echoed_max_events(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"event-runtime")

    def over_limit_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "event_count": harness.FORMAL_MAX_EVENTS + 1,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        144,
        executor=over_limit_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "exceeds max_events" in row["blocker"]


def test_summary_only_rejects_fault_and_pibt_trace_arrays(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"trace-runtime")

    def trace_leaking_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        return {
            **payload,
            "summary": {
                **payload["summary"],
                "hold_trace_stored_count": 1,
                "events": [{"kind": "summary-event"}],
            },
            "fault_events": [{"kind": "fault"}],
            "pibt_events": [{"kind": "pibt"}],
            "hold_attempts": [{"kind": "hold"}],
        }

    row = harness.execute_case(
        case,
        144,
        executor=trace_leaking_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
        summary_only=True,
    )
    assert row["gate_status"] == "FAIL"
    assert "SUMMARY_ONLY_PAYLOAD_CONTAINS:fault_events" in row["blocker"]
    assert "SUMMARY_ONLY_PAYLOAD_CONTAINS:pibt_events" in row["blocker"]
    assert "SUMMARY_ONLY_PAYLOAD_CONTAINS:hold_attempts" in row["blocker"]
    assert "SUMMARY_ONLY_SUMMARY_CONTAINS:events" in row["blocker"]
    assert "SUMMARY_ONLY_REPORTED_NONZERO_HOLD_TRACE_COUNT" in row["blocker"]
    assert row["execution_status"] == "FAILED"
    assert row["summary_only_contract_pass"] is False

    trace_mode = harness.execute_case(
        case,
        144,
        executor=_successful_fake_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
        summary_only=False,
    )
    assert trace_mode["execution_status"] == "FAILED"
    assert trace_mode["summary_only_contract_pass"] is False
    assert "FORMAL_PROMOTION_REQUIRES_SUMMARY_ONLY" in trace_mode["blocker"]


@pytest.mark.parametrize("field", ["decision_trace_stored_count", "hold_trace_stored_count"])
def test_summary_only_requires_both_stored_counts(
    tmp_path: Path,
    field: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"missing-summary-count")

    def missing_count_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.pop(field)
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        144,
        executor=missing_count_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
        summary_only=True,
    )
    assert row["gate_status"] == "FAIL"
    assert f"SUMMARY_ONLY_MISSING_{field.upper()}" in row["blocker"]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("decision_trace_stored_count", False),
        ("decision_trace_stored_count", 0.0),
        ("hold_trace_stored_count", False),
        ("hold_trace_stored_count", 0.0),
    ],
)
def test_summary_only_stored_counts_must_be_native_integers(
    tmp_path: Path,
    field: str,
    invalid: object,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"invalid-summary-count")

    def invalid_count_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {**payload["summary"], field: invalid}
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        144,
        executor=invalid_count_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
        summary_only=True,
    )
    assert row["gate_status"] == "FAIL"
    assert f"SUMMARY_ONLY_INVALID_{field.upper()}" in row["blocker"]


@pytest.mark.parametrize(
    "invalid",
    [True, 1.0, 1.5, float("inf"), "1"],
)
def test_live_integer_metrics_reject_coercion(invalid: object) -> None:
    with pytest.raises(
        harness.HarnessValidationError,
        match="must be an exact integer|got boolean",
    ):
        harness._int_metric({}, {"event_count": invalid}, "event_count")


@pytest.mark.parametrize(
    "invalid",
    [0, 1, 0.0, 1.0, "false", "true", "0", "1", None],
)
def test_live_boolean_metrics_reject_coercion(invalid: object) -> None:
    with pytest.raises(harness.HarnessValidationError, match="must be boolean"):
        harness._bool_metric({}, {"flag": invalid}, "flag")
    assert harness._bool_metric({}, {"flag": True}, "flag") is True
    assert harness._bool_metric({}, {"flag": False}, "flag") is False


@pytest.mark.parametrize(
    "invalid",
    [True, "1.0", float("nan"), float("inf"), float("-inf")],
)
def test_live_float_metrics_reject_coercion_and_nonfinite(
    invalid: object,
) -> None:
    with pytest.raises(harness.HarnessValidationError):
        harness._float_or_blank(invalid)
    assert harness._float_or_blank(1) == 1.0
    assert harness._float_or_blank(1.25) == 1.25
    with pytest.raises(harness.HarnessValidationError):
        harness.evaluate_original_entry_performance("4.0")


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("pibt_max_depth", "0"),
        ("max_events", 20_000_000.0),
        ("pressure_weight", "2.0"),
        ("pressure_weight", float("nan")),
        ("pressure_weight", float("inf")),
        ("resource_semantics", 3),
    ],
)
def test_control_echoes_require_exact_live_types(
    field: str,
    invalid: object,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    summary = dict(case.runtime_controls)
    missing_explicit = harness._control_echo_blockers(case, summary)
    assert all(
        any(
            blocker == f"MISSING_RUNTIME_CONTROL_ECHO:{name}"
            for blocker in missing_explicit
        )
        for name in harness.EXPLICIT_MODE_ECHO_CONTROLS
        if name in case.runtime_controls
    )
    summary.update(
        {
            f"{name}_echo": case.runtime_controls[name]
            for name in harness.EXPLICIT_MODE_ECHO_CONTROLS
            if name in case.runtime_controls
        }
    )
    summary["legacy_pibt_lite_enabled"] = case.runtime_controls[
        "enable_pibt_lite"
    ]
    assert harness._control_echo_blockers(case, summary) == []
    target = (
        f"{field}_echo"
        if field in harness.EXPLICIT_MODE_ECHO_CONTROLS
        else field
    )
    summary[target] = invalid
    assert any(
        f"RUNTIME_CONTROL_ECHO_MISMATCH:{field}=" in blocker
        for blocker in harness._control_echo_blockers(case, summary)
    )


@pytest.mark.parametrize("tamper", ["missing", "enabled"])
def test_legacy_pibt_lite_echo_is_mandatory_and_frozen_off(
    tamper: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(case, 144)
    if tamper == "missing":
        row.pop("legacy_pibt_lite_enabled_echo")
    else:
        row["legacy_pibt_lite_enabled_echo"] = True
    with pytest.raises(
        harness.HarnessValidationError,
        match="enable_pibt_lite",
    ):
        harness._validate_case_ledger_row(row, case, root=ROOT)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("max_edges_selected_per_bag_per_decision", ""),
        ("max_edges_selected_per_bag_per_decision", -1),
        ("max_edges_selected_per_bag_per_decision", 2),
        ("max_edges_selected_per_arrive", ""),
        ("max_edges_selected_per_arrive", -1),
        ("max_actions_committed_per_pibt_batch", 1),
    ],
)
def test_serialized_one_step_and_p0_batch_evidence_is_fail_closed(
    field: str,
    tampered: object,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(case, 144)
    row[field] = tampered
    with pytest.raises(harness.HarnessValidationError):
        harness._validate_case_ledger_row(row, case, root=ROOT)


def test_legacy_arrive_counter_cannot_replace_per_bag_one_step_proof(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"missing-per-bag-proof")

    def old_counter_only_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.pop("max_edges_selected_per_bag_per_decision")
        summary["max_edges_selected_per_arrive"] = 1
        return {**payload, "summary": summary}

    result = harness.execute_case(
        case,
        144,
        executor=old_counter_only_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert result["gate_status"] == "FAIL"
    assert "max_edges_selected_per_bag_per_decision" in result["blocker"]

    # The older arrive-level counter may exceed one because it is a batch
    # diagnostic; it is retained but is no longer used as the invariant.
    row = _valid_prior_result(case, 144)
    row["max_edges_selected_per_arrive"] = 2
    row = harness.seal_evidence_row(row)
    harness._validate_case_ledger_row(row, case, root=ROOT)


@pytest.mark.parametrize("offset", [-1, 1])
def test_pibt_batch_count_is_bounded_by_ready_bag_limit(offset: int) -> None:
    case = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P2"
    )
    row = _valid_prior_result(case, 2_048)
    if offset < 0:
        row["max_actions_committed_per_pibt_batch"] = -1
    else:
        row["max_actions_committed_per_pibt_batch"] = (
            int(case.runtime_controls["pibt_max_ready_bags"]) + 1
        )
    with pytest.raises(harness.HarnessValidationError):
        harness._validate_case_ledger_row(row, case, root=ROOT)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("termination_reason", "WORKER_FAILURE"),
        ("early_abort_status", harness.EARLY_ABORT_STATUS),
        ("evidence_status", "FORGED"),
        ("blocker", "PAYLOAD_LOADED_CPP_BINARY_PATH_MISMATCH"),
        ("repeat_consistency", "MISMATCH"),
    ],
)
def test_serialized_pass_state_machine_is_closed(
    field: str,
    tampered: object,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(case, 144)
    row[field] = tampered
    # Re-sealing demonstrates that state-machine validation is independent
    # of the compact accidental-drift binding.
    row = harness.seal_evidence_row(row)
    with pytest.raises(harness.HarnessValidationError):
        harness._validate_case_ledger_row(row, case, root=ROOT)


def test_j_promotion_metric_drift_breaks_row_binding_and_recomputed_gates() -> None:
    case = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F1"
    )
    row = _valid_prior_result(case, harness.FULL_SIZE_SEGMENTS)
    row["original_entry_mean_minutes"] = 1.0
    with pytest.raises(
        harness.HarnessValidationError,
        match="evidence row binding drift",
    ):
        harness._validate_case_ledger_row(row, case, root=ROOT)

    resigned = harness.seal_evidence_row(row)
    with pytest.raises(harness.HarnessValidationError):
        harness._validate_case_ledger_row(resigned, case, root=ROOT)


def test_result_ledger_deserializes_exact_scalars(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    ledger = tmp_path / "typed.csv"
    _write_result_ledger(ledger, [_valid_prior_result(case, 144)])
    loaded = harness.load_result_ledger(ledger, root=ROOT)
    assert len(loaded) == 1
    assert loaded[0]["event_count"] == 1_440
    assert isinstance(loaded[0]["event_count"], int)
    assert loaded[0]["comparison_eligible"] is True
    assert isinstance(loaded[0]["completion_rate"], float)


@pytest.mark.parametrize("header_drift", ["missing", "extra"])
def test_result_ledger_rejects_any_header_drift(
    tmp_path: Path,
    header_drift: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    columns = list(harness.RESULT_COLUMNS)
    if header_drift == "missing":
        columns.remove("notes")
    else:
        columns.append("unexpected_evidence")
    row = _valid_prior_result(case, 144)
    ledger = tmp_path / f"header-{header_drift}.csv"
    with ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({name: row.get(name, "") for name in columns})
    with pytest.raises(
        harness.HarnessValidationError,
        match="CSV header must exactly match",
    ):
        harness.load_result_ledger(ledger, root=ROOT)


@pytest.mark.parametrize("tamper", ["missing", "true"])
def test_result_ledger_requires_survivor_comparison_disabled(
    tmp_path: Path,
    tamper: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(case, 144)
    if tamper == "missing":
        row.pop("survivor_metric_comparison_allowed")
    else:
        row["survivor_metric_comparison_allowed"] = True
    ledger = tmp_path / f"survivor-{tamper}.csv"
    _write_result_ledger(ledger, [row])
    with pytest.raises(
        harness.HarnessValidationError,
        match="survivor_metric_comparison_allowed",
    ):
        harness.load_result_ledger(ledger, root=ROOT)


@pytest.mark.parametrize("tampered_integer", ["1.5", "+1", "01", "-0"])
def test_result_ledger_rejects_noncanonical_serialized_integer(
    tmp_path: Path,
    tampered_integer: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    ledger = tmp_path / "tampered-int.csv"
    _write_result_ledger(ledger, [_valid_prior_result(case, 144)])
    with ledger.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["event_count"] = tampered_integer
    with ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=harness.RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(
        harness.HarnessValidationError,
        match="event_count must be an exact serialized integer",
    ):
        harness.load_result_ledger(ledger, root=ROOT)


def test_result_row_integer_parser_preserves_canonical_negative_values() -> None:
    parsed = harness._deserialize_result_row(
        {"route_change_count": "-1"},
        context="unit",
    )
    assert parsed["route_change_count"] == -1


def test_real_cpp_control_matrix_echoes_one_step_and_canonical_decisions() -> None:
    try:
        module = cpp_backend.load_cpp_module(
            ROOT / "build_g4irsf12" / "python"
        )
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))
    module_file = getattr(module, "__file__", None)
    if not module_file:
        pytest.skip("loaded czr005_cpp module has no binary path")
    binary = Path(str(module_file)).resolve(strict=True)
    binary_sha256 = harness.file_sha256(binary)
    nodes, edges, heuristic = canonical_graph_records()
    prefix = harness.load_input_prefix(144, root=ROOT)
    bag_records = harness.binding_bag_records(prefix)[:12]
    selected_ids = (
        "B3_event_java_window_frozen",
        "B5_event_corrected_handwritten",
        "E_s2",
        "F_p2",
        "G_c4",
        "G_c5",
    )
    cases = {case.case_id: case for case in harness.all_cases()}

    for case_id in selected_ids:
        case = cases[case_id]
        runtime_controls = {
            name: value
            for name, value in case.runtime_controls.items()
            if name != "reservation_depth"
        }
        payload = cpp_backend.g4irsf11_event_runtime_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bag_records,
            fault_windows=[],
            trace_limit=50_000,
            summary_only=False,
            expected_binary_path=binary,
            search_path=binary.parent,
            scenario=f"g4irsf12_harness_contract_{case_id}",
            **runtime_controls,
        )
        summary = payload["summary"]
        assert isinstance(summary, dict)
        assert harness._control_echo_blockers(case, summary) == []
        assert Path(str(payload["loaded_cpp_binary_path"])).resolve() == binary
        assert payload["loaded_cpp_binary_sha256"] == binary_sha256
        assert (
            Path(str(summary["loaded_cpp_binary_path"])).resolve() == binary
        )
        assert summary["loaded_cpp_binary_sha256"] == binary_sha256
        per_bag = summary["max_edges_selected_per_bag_per_decision"]
        pibt_batch = summary["max_actions_committed_per_pibt_batch"]
        assert isinstance(per_bag, int) and not isinstance(per_bag, bool)
        assert 0 <= per_bag <= 1
        assert isinstance(pibt_batch, int) and not isinstance(
            pibt_batch,
            bool,
        )
        assert pibt_batch >= 0

        decisions = payload["decision_trace"]
        assert isinstance(decisions, list) and decisions
        for decision in decisions:
            canonicalise_decision_row(decision)


def test_real_cpp_b_echo_csv_roundtrip_authorizes_next_tier(
    tmp_path: Path,
) -> None:
    try:
        module = cpp_backend.load_cpp_module(
            ROOT / "build_g4irsf12" / "python"
        )
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))
    module_file = getattr(module, "__file__", None)
    if not module_file:
        pytest.skip("loaded czr005_cpp module has no binary path")
    binary = Path(str(module_file)).resolve(strict=True)
    nodes, edges, heuristic = canonical_graph_records()
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = harness.execute_case(
        case,
        144,
        executor=cpp_backend.g4irsf11_event_runtime_from_records,
        executor_binary=binary,
        source_paths=harness.FORMAL_SOURCE_PATHS,
        base_runtime_kwargs={
            "node_records": nodes,
            "edge_records": edges,
            "heuristic_time": heuristic,
            "search_path": binary.parent,
        },
        root=ROOT,
        summary_only=True,
        executor_id=harness.FORMAL_EXECUTOR_ID,
    )
    row["repeat_index"] = 1
    row = harness.apply_repeat_consistency([row])[0]
    assert row["gate_status"] == "PASS"
    assert row["pressure_mode_echo"] == "off"
    assert row["survivor_metric_comparison_allowed"] is False

    ledger = tmp_path / "real-b-roundtrip.csv"
    _write_result_ledger(ledger, [row])
    loaded = harness.load_result_ledger(ledger, root=ROOT)
    assert len(loaded) == 1
    assert loaded[0]["pressure_mode_echo"] == "off"
    assert loaded[0]["survivor_metric_comparison_allowed"] is False
    assert harness.authorization_blockers(case, 512, loaded) == []


def test_numeric_runtime_controls_and_source_bundle_are_frozen() -> None:
    for case in harness.all_cases():
        assert {
            name: case.runtime_controls[name]
            for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS
        } == dict(harness.FROZEN_NUMERIC_RUNTIME_CONTROLS)
    required_sources = {
        Path("scripts/eval/g4irsf11_experiment_protocol.py"),
        Path("src/czr005/datasets/decision_trace.py"),
        Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
        Path("cpp/ics_core/runtime/expiring_first_edge_credit.hpp"),
        Path("cpp/ics_core/graph/graph.hpp"),
        Path("artifacts/models/g4e_risk_calibrated_policy.json"),
    }
    assert required_sources <= set(cli.DEFAULT_SOURCE_PATHS)
    assert len(
        harness.source_bundle_sha256(cli.DEFAULT_SOURCE_PATHS, root=ROOT)
    ) == 64


def test_cli_surface_includes_all_planned_phases_and_keeps_g4j_closed() -> None:
    args = cli._parser().parse_args([])
    assert args.phases == "B,C,E,F,G,H,J"
    assert not hasattr(args, "enable_g4j")
    assert len(harness.planned_results()) == 94


def test_formal_cli_rejects_executor_source_and_trace_overrides(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"formal-cli-contract")
    source = tmp_path / "alternate.py"
    source.write_text("ALTERNATE = True\n", encoding="utf-8")
    base = [
        "--execute",
        "--phases",
        "B",
        "--case-id",
        "B5_event_corrected_handwritten",
        "--max-segments",
        "144",
        "--binary",
        str(binary),
        "--output-root",
        str(tmp_path / "published"),
    ]
    for override in (
        ["--source-path", str(source)],
        ["--with-trace"],
        ["--executor", "tests.fake:executor"],
    ):
        args = cli._parser().parse_args([*base, *override])
        with pytest.raises(PermissionError):
            cli.run(args)
