from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from scripts.eval.g4irsf11_capacity_metrics import CapacityGateConfig, capacity_metrics
from scripts.eval.g4irsf11_experiment_protocol import (
    CAPACITY_SLO,
    PROTOCOL_VERSION,
    CaseSpec,
    formal_cases,
    protocol_manifest,
)
from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics
from scripts.eval.g4irsf11_result_validation import (
    EXECUTION_DESCRIPTOR_SCHEMA,
    RESULT_SCHEMA,
    ResultExpectation,
    artifact_binding,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_manifest_sha256,
    fault_binding,
    read_json_object,
    validate_event_result,
    validate_execution_descriptor,
    workload_binding,
)
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
    _measurement_cohort,
    _worker_config,
)


def _valid_bundle(tmp_path: Path) -> tuple[
    dict[str, object],
    dict[str, object],
    ResultExpectation,
    list[str],
    Path,
    dict[str, dict[str, object]],
    list[dict[str, object]],
]:
    case = CaseSpec("validator_case", "test", "time_compressed", 1.0)
    run_id = str(uuid.uuid4())
    workload_path = tmp_path / "workload.jsonl"
    fault_path = tmp_path / "fault.json"
    result_path = tmp_path / "result.json"
    rows: list[dict[str, object]] = [
        {
            "segment_id": f"segment-{index}",
            "task_id": index + 1,
            "release_time": float(index),
            "admitted_time": float(index),
            "finish_time": float(index + 10),
            "deadline": 1000.0,
            "complete": True,
            "completed": True,
            "total_wait": 0.0,
            "java_release_tth_seconds": 10.0,
        }
        for index in range(2)
    ]
    atomic_write_jsonl(workload_path, rows)
    atomic_write_json(fault_path, [])
    input_artifact = workload_binding(workload_path, rows)
    fault_artifact = fault_binding(fault_path, [])
    manifest_digest = canonical_manifest_sha256(protocol_manifest())
    args = SimpleNamespace(
        max_events=20_000_000,
        measurement_cohort="pytest_sequential1",
        concurrent_worker_target=1,
    )
    config = _worker_config(case, args)
    cohort = _measurement_cohort(args)
    summary = {
        "requested_count": 2,
        "completed_count": 2,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "max_edges_selected_per_arrive": 1,
        "release_selected_edge_count": 0,
        "two_step_reservation_count": 0,
        "full_future_routes_stored": 0,
        "event_count": 4,
        "decision_count": 2,
        "runtime_seconds": 1.0,
        "decision_latency_us_p50": 1.0,
        "decision_latency_us_p95": 2.0,
        "decision_latency_us_p99": 3.0,
        "deadlock_count": 0,
        "resolved_deadlock_count": 0,
        "unresolved_deadlock_count": 0,
        "loop_count": 0,
        "cpp_internal_accounted_bytes": 100,
        "internal_state_bytes": 100,
        "decision_trace_stored_count": 0,
        "hold_trace_stored_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "fault_policy_enabled": True,
        "fault_affected_bag_count": 0,
        "fault_target_edge_candidate_exposure_count": 0,
        "fault_target_edge_attempt_count": 0,
        "physical_fault_interlock_rejection_count": 0,
        "physical_fault_interlock_hold_count": 0,
        "physical_fault_interlock_reroute_count": 0,
        "local_fault_policy_action_count": 0,
        "local_fault_policy_hold_count": 0,
        "local_fault_policy_reroute_count": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "sensor_loss_mode_used": False,
    }
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=CAPACITY_SLO["max_backlog_slope_fraction"],
        max_drain_seconds=CAPACITY_SLO["max_drain_seconds"],
        max_p95_total_seconds=CAPACITY_SLO["max_p95_service_seconds"],
        max_p99_total_seconds=CAPACITY_SLO["max_p99_service_seconds"],
        max_deadline_miss_rate=CAPACITY_SLO["max_deadline_miss_rate"],
        starvation_seconds=CAPACITY_SLO["starvation_seconds"],
    )
    capacity = capacity_metrics(rows, summary, gate)
    environment = {
        "python_executable": str((tmp_path / "python.exe").resolve()),
        "python_version": "3.11.0",
        "python_implementation": "CPython",
        "platform": "pytest",
        "machine": "test",
        "os_name": "nt",
        "search_path": str(tmp_path.resolve()),
    }
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "run_id": run_id,
        "case": case.as_dict(),
        "protocol_version": PROTOCOL_VERSION,
        "protocol_manifest_sha256": manifest_digest,
        "input_artifact": input_artifact,
        "fault_artifact": fault_artifact,
        "map_sha256": "a" * 64,
        "source_sha256": "b" * 64,
        "implementation_sha256": "c" * 64,
        "scenario": case.case_id,
        "scale": case.scale,
        "workload_mode": case.workload_mode,
        "workload_path": str(workload_path.resolve()),
        "workload_segment_count": 2,
        "raw_bag_count": 2,
        "config": config,
        "measurement_cohort": cohort,
        "environment": environment,
        "summary": summary,
        "raw_bag_capacity_metrics": deepcopy(capacity),
        "segment_capacity_metrics": deepcopy(capacity),
        "fault_window_metrics": [],
        "resource_metrics": {
            "measurement_scope": "isolated_worker_process",
            "working_set_before_bytes": 1000,
            "peak_working_set_before_bytes": 1100,
            "working_set_after_bytes": 1200,
            "peak_working_set_bytes": 1300,
            "peak_working_set_growth_from_initial_current_bytes": 300,
            "cpp_internal_accounted_bytes": 100,
            "wall_seconds_including_pybind_materialization": 1.0,
        },
        "trace": {
            "trace_output": "",
            "outcome_output": "",
            "trace_task_output": "",
            "decision_rows_stored": 0,
            "hold_rows_stored": 0,
            "trace_context": {
                "run_id": run_id,
                "scenario": case.case_id,
                "scale": case.scale,
                "fault_mode": case.fault_profile,
            },
        },
        "event_sample": [],
        "fault_event_sample": [],
        "bag_sample": [],
        "junction_state": [],
        "event_runtime_invariant_pass": True,
        "completion_pass": True,
    }
    atomic_write_json(result_path, result)
    expectation = ResultExpectation(
        run_id=run_id,
        case=case.as_dict(),
        protocol_version=PROTOCOL_VERSION,
        protocol_manifest_sha256=manifest_digest,
        input_artifact=input_artifact,
        fault_artifact=fault_artifact,
        fault_rows=[],
        map_sha256="a" * 64,
        source_sha256="b" * 64,
        implementation_sha256="c" * 64,
        config=config,
        measurement_cohort=cohort,
    )
    argv = [environment["python_executable"], "worker.py", "--run-id", run_id]
    trace_artifacts = {
        name: artifact_binding(tmp_path / f"{name}.json", state="not_requested")
        for name in ("trace", "outcomes", "tasks")
    }
    descriptor: dict[str, object] = {
        "schema": EXECUTION_DESCRIPTOR_SCHEMA,
        "run_id": run_id,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_manifest_sha256": manifest_digest,
        "case": case.as_dict(),
        "config": config,
        "source_sha256": "b" * 64,
        "map_sha256": "a" * 64,
        "implementation_sha256": "c" * 64,
        "input_sha256": input_artifact["sha256"],
        "input_artifact": input_artifact,
        "fault_artifact": fault_artifact,
        "normalized_argv": argv,
        "command": "worker",
        "parent_timeout_seconds": 60.0,
        "measurement_cohort": cohort,
        "environment": environment,
        "result_artifact": artifact_binding(result_path),
        "trace_artifacts": trace_artifacts,
        "status": "EXECUTED",
        "return_code": 0,
        "blocker": "",
        "wall_seconds_parent": 2.0,
    }
    return descriptor, result, expectation, argv, result_path, trace_artifacts, rows


def test_valid_v3_result_and_descriptor_bundle_passes(tmp_path: Path) -> None:
    descriptor, result, expectation, argv, result_path, traces, rows = _valid_bundle(tmp_path)
    assert validate_event_result(result, expectation, workload_rows=rows) == []
    assert validate_execution_descriptor(
        descriptor,
        result,
        expectation,
        normalized_argv=argv,
        normalized_command_text="worker",
        parent_timeout_seconds=60.0,
        result_artifact=artifact_binding(result_path),
        trace_artifacts=traces,
        workload_rows=rows,
    ) == []


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (lambda result: result.__setitem__("run_id", str(uuid.uuid4())), "run_id"),
        (lambda result: result["summary"].__setitem__("requested_count", 3), "counts differ"),
        (lambda result: result.__setitem__("completion_pass", False), "completion_pass"),
        (
            lambda result: result["raw_bag_capacity_metrics"].__setitem__("capacity_pass", True),
            "capacity_pass",
        ),
        (
            lambda result: result.__setitem__("event_runtime_invariant_pass", False),
            "invariant_pass",
        ),
        (
            lambda result: result["resource_metrics"].__setitem__("peak_working_set_bytes", 999),
            "peak working set",
        ),
        (
            lambda result: result["summary"].__setitem__("decision_latency_us_p99", "INF"),
            "non-finite",
        ),
    ],
)
def test_result_semantic_mutations_fail_closed(
    tmp_path: Path, mutation: object, needle: str
) -> None:
    _, result, expectation, _, _, _, rows = _valid_bundle(tmp_path)
    mutation(result)  # type: ignore[operator]
    errors = validate_event_result(result, expectation, workload_rows=rows)
    assert errors
    assert any(needle in error for error in errors)


def test_descriptor_binds_result_hash_argv_timeout_and_cohort(tmp_path: Path) -> None:
    descriptor, result, expectation, argv, result_path, traces, rows = _valid_bundle(tmp_path)
    for field, replacement in (
        ("normalized_argv", ["different"]),
        ("parent_timeout_seconds", 61.0),
        ("measurement_cohort", {"name": "wrong", "declared_concurrent_worker_target": 1}),
        ("result_artifact", {"sha256": "0" * 64}),
        ("input_sha256", "0" * 64),
        ("command", "misreported command"),
    ):
        changed = deepcopy(descriptor)
        changed[field] = replacement
        assert validate_execution_descriptor(
            changed,
            result,
            expectation,
            normalized_argv=argv,
            normalized_command_text="worker",
            parent_timeout_seconds=60.0,
            result_artifact=artifact_binding(result_path),
            trace_artifacts=traces,
            workload_rows=rows,
        )


def test_strict_json_reader_rejects_duplicate_keys_and_nonfinite(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_json_object(duplicate)
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"a":NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        read_json_object(nonfinite)


def test_atomic_json_publish_never_leaves_a_partial_document(tmp_path: Path) -> None:
    path = tmp_path / "atomic.json"
    for index in range(100):
        atomic_write_json(path, {"index": index, "payload": "x" * 1000})
        assert read_json_object(path)["index"] == index
    assert not list(tmp_path.glob(".atomic.json.*.tmp"))


@pytest.mark.parametrize("policy_enabled", [True, False])
def test_fault_validator_requires_real_exposure_and_policy_evidence(
    tmp_path: Path, policy_enabled: bool
) -> None:
    _, result, base_expectation, _, _, _, workload_rows = _valid_bundle(tmp_path)
    case_id = "fault_single_immediate" if policy_enabled else "fault_fault_policy_off"
    case = next(case for case in formal_cases() if case.case_id == case_id)
    args = SimpleNamespace(
        max_events=20_000_000,
        measurement_cohort="pytest_sequential1",
        concurrent_worker_target=1,
    )
    config = _worker_config(case, args)
    window_row = {
        "start": 22,
        "end": 24,
        "fault_time": 2.0,
        "repair_time": 3.0,
        "message_delay": 0.0,
        "drop_notification": False,
    }
    fault_path = tmp_path / f"fault-{policy_enabled}.json"
    atomic_write_json(fault_path, [window_row])
    fault_artifact = fault_binding(fault_path, [window_row])
    fault_bags = deepcopy(workload_rows)
    for runtime_bag_id, row in enumerate(fault_bags):
        row["runtime_bag_id"] = runtime_bag_id
    common = {
        "from_node": 22,
        "to_node": 24,
        "runtime_bag_id": 0,
        "task_id": 1,
        "segment_id": "segment-0",
        "current_node": 22,
        "intended_next_node": 24,
        "fault_policy_enabled": policy_enabled,
    }
    events = [
        {**common, "event": "FAULT", "phase": "physical_state_change", "time": 2.0},
        {**common, "event": "REPAIR", "phase": "physical_state_change", "time": 3.0},
        {**common, "event": "FAULT", "phase": "local_message_delivery", "time": 2.0},
        {**common, "event": "REPAIR", "phase": "local_message_delivery", "time": 3.0},
        {**common, "phase": "target_edge_candidate_exposure", "time": 2.25},
        {**common, "phase": "target_edge_attempt", "time": 2.25},
    ]
    summary = result["summary"]
    assert isinstance(summary, dict)
    summary.update(
        {
            "fault_policy_enabled": policy_enabled,
            "fault_affected_bag_count": 1,
            "fault_target_edge_candidate_exposure_count": 1,
            "fault_target_edge_attempt_count": 1,
            "sensor_loss_mode_used": False,
        }
    )
    if policy_enabled:
        events.append({**common, "phase": "local_fault_policy_reroute", "time": 2.25})
        summary.update(
            {
                "physical_fault_interlock_rejection_count": 0,
                "physical_fault_interlock_hold_count": 0,
                "physical_fault_interlock_reroute_count": 0,
                "local_fault_policy_action_count": 1,
                "local_fault_policy_hold_count": 0,
                "local_fault_policy_reroute_count": 1,
            }
        )
    else:
        events.extend(
            [
                {**common, "phase": "physical_fault_interlock_rejection", "time": 2.25},
                {**common, "phase": "physical_fault_interlock_hold", "time": 2.25},
            ]
        )
        summary.update(
            {
                "physical_fault_interlock_rejection_count": 1,
                "physical_fault_interlock_hold_count": 1,
                "physical_fault_interlock_reroute_count": 0,
                "local_fault_policy_action_count": 0,
                "local_fault_policy_hold_count": 0,
                "local_fault_policy_reroute_count": 0,
            }
        )
    metrics = fault_window_metrics(
        fault_bags,
        events,
        summary,
        [FaultWindow(22, 24, 2.0, 3.0)],
        max_recovery_seconds=1800.0,
    )
    assert metrics[0]["fault_recovery_pass"] is True
    result.update(
        {
            "case": case.as_dict(),
            "scenario": case.case_id,
            "scale": case.scale,
            "workload_mode": case.workload_mode,
            "config": config,
            "fault_artifact": fault_artifact,
            "fault_window_metrics": metrics,
        }
    )
    result["trace"]["trace_context"].update(  # type: ignore[index]
        {
            "scenario": case.case_id,
            "scale": case.scale,
            "fault_mode": case.fault_profile,
        }
    )
    expectation = ResultExpectation(
        run_id=base_expectation.run_id,
        case=case.as_dict(),
        protocol_version=base_expectation.protocol_version,
        protocol_manifest_sha256=base_expectation.protocol_manifest_sha256,
        input_artifact=base_expectation.input_artifact,
        fault_artifact=fault_artifact,
        fault_rows=[window_row],
        map_sha256=base_expectation.map_sha256,
        source_sha256=base_expectation.source_sha256,
        implementation_sha256=base_expectation.implementation_sha256,
        config=config,
        measurement_cohort=base_expectation.measurement_cohort,
    )
    assert validate_event_result(result, expectation, workload_rows=workload_rows) == []

    no_exposure = deepcopy(result)
    no_exposure["fault_window_metrics"][0]["target_edge_candidate_exposure_count"] = 0
    errors = validate_event_result(no_exposure, expectation, workload_rows=workload_rows)
    assert any("real_exposure_pass" in error or "exposure counters" in error for error in errors)

    if not policy_enabled:
        rerouted = deepcopy(result)
        rerouted["summary"]["physical_fault_interlock_hold_count"] = 0
        rerouted["summary"]["physical_fault_interlock_reroute_count"] = 1
        rerouted["fault_window_metrics"][0]["physical_interlock_hold_count"] = 0
        rerouted["fault_window_metrics"][0]["physical_interlock_reroute_count"] = 1
        errors = validate_event_result(rerouted, expectation, workload_rows=workload_rows)
        assert any("policy-off" in error for error in errors)
