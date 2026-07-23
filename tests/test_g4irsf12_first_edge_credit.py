from __future__ import annotations

from collections.abc import Sequence

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    assert_canonical_map,
    canonical_graph_records,
)


def _require_cpp() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def _real_split_and_goal() -> tuple[int, int]:
    assert assert_canonical_map() == CANONICAL_MAP_PATH
    nodes, _edges, heuristic = canonical_graph_records()
    terminals = sorted(
        int(location)
        for location, _kind, _service, _x, _y, outgoing in nodes
        if not outgoing
    )
    for location, _kind, _service, _x, _y, outgoing in sorted(nodes):
        if len(outgoing) < 2:
            continue
        finite_goals = [
            goal
            for goal in terminals
            if float(heuristic[int(location)][goal]) < float("inf")
        ]
        if finite_goals:
            goal = min(
                finite_goals,
                key=lambda item: (float(heuristic[int(location)][item]), item),
            )
            return int(location), int(goal)
    raise AssertionError("protected map2 must contain a real split")


def _run_credit(
    *,
    pressure_mode: str,
    enable_backpressure: bool,
) -> dict[str, object]:
    _require_cpp()
    nodes, edges, heuristic = canonical_graph_records()
    split, goal = _real_split_and_goal()
    return cpp_backend.g4irsf11_event_runtime_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=[
            ("g4irsf12-credit-real-split", 1, 0.0, 10_000.0, split, goal, "map2")
        ],
        resource_semantics="R3",
        pressure_mode=pressure_mode,
        enable_backpressure=enable_backpressure,
        admission_mode="expiring_first_edge_credit",
        credit_validity_seconds=2.0,
        credit_snapshot_max_age_seconds=0.5,
        credit_capacity_per_edge=2,
        credit_lifecycle_limit=32,
        minimum_service_seconds=0.1,
        retry_interval=0.05,
        enable_pibt_lite=False,
        max_decisions_per_bag=1_000,
        max_simulation_time=10_000.0,
        trace_limit=100_000,
        scenario="g4irsf12_credit_pybind",
    )


@pytest.mark.parametrize(
    ("pressure_mode", "enable_backpressure", "ablation"),
    [("C0", False, "C4"), ("C2", True, "C5")],
)
def test_c4_c5_python_boundary_exposes_closed_credit_lifecycle(
    pressure_mode: str,
    enable_backpressure: bool,
    ablation: str,
) -> None:
    payload = _run_credit(
        pressure_mode=pressure_mode,
        enable_backpressure=enable_backpressure,
    )
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["admission_mode"] == "expiring_first_edge_credit"
    assert summary["completed_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["first_edge_credit_issued_count"] >= 1
    assert summary["first_edge_credit_bound_count"] == 1
    assert summary["first_edge_credit_consumed_count"] == 1
    assert summary["first_edge_credit_active_count"] == 0
    assert summary["first_edge_credit_stored_active_count"] == 0
    assert summary["first_edge_credit_stored_lifecycle_count"] <= 32
    assert summary["first_edge_credit_lifecycle_limit"] == 32
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["global_reservation_scan_count"] == 0
    assert summary["first_edge_credit_future_route_count"] == 0
    assert summary["first_edge_credit_global_scan_count"] == 0
    assert summary["first_edge_credit_physical_interlock_bypass"] is False
    assert "one_adjacent_selected_edge" in summary["first_edge_credit_claim_boundary"]

    trace_context = payload["trace_context"]
    assert isinstance(trace_context, dict)
    assert trace_context["admission_mode"] == "expiring_first_edge_credit"
    assert trace_context["first_edge_credit_physical_interlock_bypass"] is False
    assert trace_context["first_edge_credit_future_route_count"] == 0
    assert trace_context["first_edge_credit_global_scan_count"] == 0
    assert trace_context["credit_capacity_per_edge"] == 2
    assert trace_context["credit_lifecycle_limit"] == 32

    credit_events = payload["credit_events"]
    assert isinstance(credit_events, list)
    assert {"bound", "consumed"} <= {row["action"] for row in credit_events}
    required = {
        "credit_id",
        "from",
        "to",
        "goal",
        "earliest",
        "latest",
        "generation",
        "expiry",
        "capacity",
        "owner_or_unbound",
        "fault_generation",
    }
    assert all(required <= row.keys() for row in credit_events)

    decisions = payload["decisions"]
    assert isinstance(decisions, Sequence)
    first = next(
        row for row in decisions if row["decision_source"] == "expiring_first_edge_credit"
    )
    selected = next(
        candidate
        for candidate in first["candidate_records"]
        if candidate["next_node"] == first["selected_next"]
    )
    features = selected["features"]
    assert features["first_edge_credit_required"] is True
    assert features["first_edge_credit_matches"] is True
    assert features["first_edge_credit_valid"] is True
    assert features["first_edge_credit_slack_seconds"] >= 0.0
    assert ablation in {"C4", "C5"}


def test_python_boundary_rejects_unknown_admission_mode() -> None:
    _require_cpp()
    nodes, edges, heuristic = canonical_graph_records()
    split, goal = _real_split_and_goal()
    with pytest.raises(ValueError, match="admission_mode"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=[("invalid-credit-mode", 1, 0.0, 10_000.0, split, goal, "map2")],
            admission_mode="unknown",
        )


def test_legacy_positional_binding_contract_remains_aligned() -> None:
    """The G parameters are appended; every historical positional slot is stable."""

    _require_cpp()
    module = cpp_backend.load_cpp_module()
    nodes, edges, heuristic = canonical_graph_records()
    split, goal = _real_split_and_goal()
    payload = dict(
        module.g4irsf11_event_runtime_from_records(
            nodes,
            edges,
            heuristic,
            [("legacy-positional", 1, 0.0, 10_000.0, split, goal, "map2")],
            [],
            "aging",
            0.05,
            0.1,
            0.001,
            8,
            1_000,
            2_000_000,
            10_000.0,
            100_000,
            1,
            0,
            0,
            8,
            2,
            True,
            True,
            True,
            True,
            True,
            "legacy_positional_contract",
            1.0,
            "R3",
            0.001,
            "C1",
            2.0,
            0.05,
            0.25,
        )
    )
    summary = payload["summary"]
    assert summary["admission_mode"] == "legacy_unbound"
    assert summary["source_admission_enabled"] is True
    assert summary["completed_count"] == 1
    assert summary["first_edge_credit_issue_attempt_count"] == 0
    assert payload["credit_events"] == []
