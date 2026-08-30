from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from czr005.cpp_backend import g4irsf11_event_runtime_from_records


ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "build_g32_v3r13" / "python" / "Release"


def _request(
    *,
    j2: bool,
    local_deadline: float = 10.0,
    external_deadline: float = 100.0,
) -> dict[str, Any]:
    size = 5 if j2 else 4
    heuristic = [[1000.0] * size for _ in range(size)]
    for node in range(size):
        heuristic[node][node] = 0.0
    heuristic[0][3] = 1.15
    heuristic[1][3] = 0.10
    heuristic[2][3] = 0.05
    if j2:
        heuristic[4][3] = 1.15
    nodes = [
        (0, 7, 0.0, 0, 0, [1]),
        (1, 1, 1.0, 1, 0, [2]),
        (2, 4, 0.0, 2, 0, [3]),
        (3, 2, 0.0, 3, 0, []),
    ]
    edges = [(0, 1, 0.05, 1.0), (1, 2, 0.05, 1.0), (2, 3, 0.05, 1.0)]
    if j2:
        nodes.append((4, 7, 0.0, 0, 1, [1]))
        edges.append((4, 1, 0.05, 1.0))
    return {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [
            ("v3r13-external-committed", 32033001, 0.0, 100.0, 0, 3, "external"),
            ("v3r13-local", 32033002, 0.1, local_deadline, 1, 3, "local"),
            (
                "v3r13-external-contender",
                32033003,
                0.05 if j2 else 0.2,
                external_deadline,
                4 if j2 else 0,
                3,
                "external",
            ),
        ],
        "queue_discipline": "deadline",
        "retry_interval": 0.25,
        "minimum_service_seconds": 0.001,
        "dispatch_headway_seconds": 0.001,
        "history_limit": 8,
        "max_decisions_per_bag": 512,
        "max_events": 2_000_000,
        "max_simulation_time": -1.0,
        "trace_limit": 200_000,
        "event_trace_limit": 200_000,
        "local_queue_capacity": 0,
        "deadlock_retry_threshold": 8,
        "diagnostic_hops": 2,
        "enable_source_admission": False,
        "enable_backpressure": False,
        "enable_pibt_lite": False,
        "enable_deadlock_escape": True,
        "enable_fault_policy": True,
        "scale": 1.0,
        "resource_semantics": "R3_java_node_window_compatible",
        "entry_headway_seconds": 0.001,
        "pressure_mode": "off",
        "admission_mode": "off",
        "pibt_mode": "P2",
        "pibt_max_depth": 2,
        "priority_mode": "Q0",
        "pibt_preference_mode": "current",
        "scorer_mode": "S4_queue_aware_rule_only",
        "framework_mode": "event_loop_one_step",
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "g4irsf20_event_hotpath_policy": "E2",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "complete_on_goal_arrival": True,
        "storage_source_nodes": [0, 4] if j2 else [0],
        "source_aware_destination_service_mode": "closed_loop",
        "source_aware_destination_service_trace_limit": 200_000,
        "search_path": BINDING,
    }


@pytest.mark.parametrize("j2", [False, True])
def test_closed_loop_commits_one_future_local_owner(j2: bool) -> None:
    payload = g4irsf11_event_runtime_from_records(**_request(j2=j2))
    summary = payload["summary"]
    assert summary["source_aware_destination_service_mode"] == "closed_loop"
    assert summary["source_aware_destination_service_action_change_count"] == 1
    assert summary[
        "source_aware_destination_service_calendar_mutation_count"
    ] == 1
    assert summary["source_aware_destination_service_future_release_read_count"] == 0
    assert summary["source_aware_destination_service_global_scan_count"] == 0
    assert "source_aware_destination_service_shadow" not in payload
    local = next(row for row in payload["bags"] if row["segment_id"] == "v3r13-local")
    action = next(
        row
        for row in payload["events"]
        if row["segment_id"] == "v3r13-local"
        and row["reason"] == "source_closed_loop_future_slot"
    )
    assert local["completed"] is True
    assert local["admitted_time"] > local["release_time"]
    assert action["time"] == pytest.approx(local["admitted_time"])


def test_j2_reverse_priority_and_future_release_are_inert() -> None:
    request = _request(j2=True, local_deadline=100.0, external_deadline=1.0)
    baseline = g4irsf11_event_runtime_from_records(**request)
    future = copy.deepcopy(request)
    future["bag_records"].append(
        ("v3r13-future", 32033004, 50.0, 100.0, 1, 3, "local")
    )
    perturbed = g4irsf11_event_runtime_from_records(**future)
    baseline_local = next(
        row for row in baseline["bags"] if row["segment_id"] == "v3r13-local"
    )
    baseline_external = next(
        row
        for row in baseline["bags"]
        if row["segment_id"] == "v3r13-external-contender"
    )
    assert baseline_external["finish_time"] < baseline_local["finish_time"]
    perturbed_local = next(
        row for row in perturbed["bags"] if row["segment_id"] == "v3r13-local"
    )
    assert perturbed_local["admitted_time"] == pytest.approx(
        baseline_local["admitted_time"]
    )
    assert perturbed["summary"][
        "source_aware_destination_service_future_release_read_count"
    ] == 0
