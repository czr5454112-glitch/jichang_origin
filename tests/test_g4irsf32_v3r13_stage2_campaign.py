from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf32_v3r13_stage2_campaign as runner


def _binary(tmp_path: Path) -> Path:
    path = (
        tmp_path
        / "build_g32_v3r13"
        / "python"
        / "Release"
        / "czr005_cpp.fake.pyd"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture")
    return path


def _summary(
    request: Mapping[str, Any], *, events_per_completed: int
) -> dict[str, Any]:
    completed = len(request["bag_records"])
    value: dict[str, Any] = {
        key: 0 for key in runner.stage01.SAFETY_ZERO_KEYS
    }
    value.update(
        {
            key: 0 for key in runner.stage01.MODEL_ZERO_KEYS
        }
    )
    value.update(
        requested_count=completed,
        completed_count=completed,
        failed_count=0,
        event_count=completed * events_per_completed,
        safe_execution_pass=True,
        max_edges_selected_per_bag_per_decision=1,
        event_limit_reached=False,
        time_limit_reached=False,
        artificial_batch_delay_seconds=0.0,
        merge_grant_conservation_holds=True,
        merge_grant_active_bijection_holds=True,
        merge_grant_protocol_integrity_pass=True,
        event_trace_truncated=False,
        full_future_routes_stored=0,
        starvation_count=0,
        bag_future_path_field_present=False,
        full_cie_astar_runtime_fallback=False,
        max_source_queue_length=10,
        max_junction_queue_length=4,
        merge_grant_peak_pending_requests=3,
    )
    if request.get("source_aware_destination_service_mode") == "closed_loop":
        value.update(
            {
                runner.stage01.NS + "mode": "closed_loop",
                runner.stage01.NS + "action_change_count": 0,
                runner.stage01.NS + "calendar_mutation_count": 0,
                runner.stage01.NS + "future_release_read_count": 0,
                runner.stage01.NS + "global_scan_count": 0,
            }
        )
    return value


def _payload(
    request: Mapping[str, Any], *, events_per_completed: int = 10
) -> dict[str, Any]:
    closed = request.get("source_aware_destination_service_mode") == "closed_loop"
    nanning = request.get("storage_source_nodes") == [53]
    total_latency = 90.0 if closed and nanning else 100.0
    bags = []
    for record in request["bag_records"]:
        segment_id, task_id, release, _deadline, start, _goal, _source = record
        source_wait = 10.0 if int(start) == 49 else 5.0
        if closed and nanning:
            source_wait *= 0.9
        bags.append(
            {
                "segment_id": segment_id,
                "task_id": task_id,
                "release_time": release,
                "admitted_time": release + source_wait,
                "finish_time": release + total_latency,
                "completed": True,
            }
        )
    return {
        "summary": _summary(
            request, events_per_completed=events_per_completed
        ),
        "bags": bags,
        "events": [],
        "junction_state": [],
        "resource_metrics": {
            "measurement_scope": "isolated_worker_process",
            "wall_seconds": 1.0,
            "peak_working_set_bytes": 100_000,
        },
    }


def _map2_stable_1x() -> tuple[Mapping[str, Any], runner.WorkloadSlice]:
    registration = runner._read_preregistration()
    case = next(
        row
        for row in registration["cases"]
        if row["case_id"] == "g4irsf32_s2_map2_1x_stable_2p5"
    )
    slices = runner._load_workload_slices(registration)
    return case, slices[(runner.map2_native.MAP_ID, 1)]


def test_injected_map2_pair_passes_with_exact_preregistered_closure(
    tmp_path: Path,
) -> None:
    binary = _binary(tmp_path).resolve()
    case, workload = _map2_stable_1x()
    modes: list[str] = []

    def executor(**request: Any) -> Mapping[str, Any]:
        mode = request.get("source_aware_destination_service_mode", "off")
        modes.append(str(mode))
        assert request["expected_binary_path"] == binary
        assert request["event_trace_limit"] == runner.EVENT_TRACE_LIMIT
        assert [str(record[0]) for record in request["bag_records"]] == list(
            workload.ordered_segment_ids
        )
        return _payload(request)

    result = runner._run_case(
        case, workload, executor=executor, binary=binary
    )

    assert modes == ["off", "closed_loop"]
    assert result["pass"] is True
    assert all(result["gates"].values())
    assert result["population"]["segment_count"] == 998
    assert result["population"]["raw_task_count"] == 540
    assert result["population"]["ordered_segment_ids_exact"] is True
    assert result["arms"]["closed_loop"]["resources"][
        "peak_rss_status"
    ] == "MEASURED_ISOLATED_WORKER_PROCESS"


def test_events_per_completed_ratio_over_1p10_is_a_real_threshold_failure(
    tmp_path: Path,
) -> None:
    binary = _binary(tmp_path).resolve()
    case, workload = _map2_stable_1x()

    def executor(**request: Any) -> Mapping[str, Any]:
        closed = request.get("source_aware_destination_service_mode") == (
            "closed_loop"
        )
        return _payload(request, events_per_completed=12 if closed else 10)

    result = runner._run_case(
        case, workload, executor=executor, binary=binary
    )

    assert result["pass"] is False
    assert result["gates"]["resources_within_1p10"] is False
    assert result["resource_ratios"][
        "events_per_completed_segment"
    ] == pytest.approx(1.2)
    assert all(
        passed
        for name, passed in result["gates"].items()
        if name != "resources_within_1p10"
    )


def test_fixed_horizon_and_stale_wakeup_are_diagnostics_not_safety_failures(
    tmp_path: Path,
) -> None:
    binary = _binary(tmp_path).resolve()
    case, workload = _map2_stable_1x()

    def executor(**request: Any) -> Mapping[str, Any]:
        payload = _payload(request)
        payload["summary"].update(
            time_limit_reached=True,
            merge_grant_stale_arbitration_count=7,
            stale_arbitration_event_count=3,
            starvation_count=2,
        )
        return payload

    result = runner._run_case(
        case, workload, executor=executor, binary=binary
    )

    assert result["gates"]["hard_safety"] is True
    assert result["gates"]["no_new_starvation_threshold_crossings"] is True
    assert result["diagnostics"]["safety_counter_deltas"][
        "starvation_count"
    ] == 0
    assert result["pass"] is True
