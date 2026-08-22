"""Focused native checks for G25 paired rejoin/settle labels."""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "G22_S4_J2_E2"
TARGET_SCHEMA = "czr005.g4irsf21.route_action_target.v1"


def _backend() -> ModuleType:
    configured = os.environ.get("G4IRSF25_NATIVE_DIR")
    search_paths = [
        Path(configured) if configured else None,
        ROOT / "build-ci" / "python",
        ROOT / "build_g4irsf25_native" / "python" / "Release",
        ROOT / "build_g4irsf25_native" / "python",
    ]
    for search_path in search_paths:
        if search_path is None or not search_path.is_dir():
            continue
        try:
            module = cpp_backend.load_cpp_module(search_path)
        except cpp_backend.CppBackendUnavailable:
            continue
        if all(
            callable(getattr(module, name, None))
            for name in (
                "g4irsf15_scan_causal_skeletons_from_records",
                "g4irsf15_run_causal_target_pairs_from_records",
            )
        ):
            return module
    message = "a current G25-capable czr005_cpp extension is required"
    if os.environ.get("G4IRSF25_REQUIRE_NATIVE") == "1":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _arguments() -> tuple[Any, ...]:
    nodes, edges, heuristic = canonical_graph_records()
    bags = [("g25:storage_in", 0, 0.0, 1_000.0, 3, 47, "node_3")]
    # G22's S4 profile is rule-only, so scorer tensors are intentionally empty.
    return (
        nodes,
        edges,
        heuristic,
        bags,
        [],
        [],
        [],
        0.0,
        0.0,
        0.0,
        "",
        [0.0],
    )


def _branch_16_row(backend: ModuleType, arguments: tuple[Any, ...]) -> dict[str, Any]:
    census = backend.g4irsf15_scan_causal_skeletons_from_records(
        *arguments, PROFILE
    )
    return dict(next(row for row in census["skeletons"] if row["node"] == 16))


def _target(row: dict[str, Any], *, g25: bool = True) -> dict[str, Any]:
    target: dict[str, Any] = {
        "schema": TARGET_SCHEMA,
        "population_group_id": row["population_group_sha256"],
        "population_selection_id": row["skeleton_selection_sha256"],
        "event_ordinal": row["event_ordinal"],
        "horizon": "H_bag",
        "action_kind": "NEXT_EDGE",
        "selected_next_node": 21,
    }
    if g25:
        target.update(
            {
                "g4irsf25_rejoin_node": 24,
                "g4irsf25_corridor_nodes": [16, 17, 18, 22, 21, 23, 24],
                "g4irsf25_settle_seconds": 30.0,
                "g4irsf25_max_horizon_seconds": 60.0,
            }
        )
    return target


def _run(backend: ModuleType, arguments: tuple[Any, ...], target: dict[str, Any]) -> dict[str, Any]:
    payload = backend.g4irsf15_run_causal_target_pairs_from_records(
        *arguments, [target], PROFILE
    )
    assert len(payload["pairs"]) == 1
    return dict(payload["pairs"][0])


def _s4_projection(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload["summary"]
    return {
        "completed_count": summary["completed_count"],
        "failed_count": summary["failed_count"],
        "decision_count": summary["decision_count"],
        "decisions": [
            (
                row["current_node"],
                row["selected_next"],
                row["model_prediction"],
            )
            for row in payload["decisions"]
        ],
        "bag_completion": [
            (row["completed"], row["final_node"])
            for row in payload["bags"]
        ],
    }


def test_native_g25_pair_emits_rejoin_private_and_local_system_labels() -> None:
    backend = _backend()
    arguments = _arguments()
    pair = _run(backend, arguments, _target(_branch_16_row(backend, arguments)))

    assert pair["pair_status"] == "ACTION_CHANGED_HORIZON_COMPLETE"
    assert pair["pair_complete"] is True
    assert pair["g4irsf25_short_horizon_enabled"] is True
    assert pair["g4irsf25_post_first_action_policy"] == "ORDINARY_S4_J2_E2"
    assert pair["formal_hard_gate_evaluated"] is False
    assert pair["g4irsf25_both_rejoin_arrived"] is True
    assert pair["g4irsf25_any_timeout"] is True
    assert pair["g4irsf25_both_safe"] is True

    branches = [pair["baseline"], pair["treatment"]]
    for branch in branches:
        label = branch["g4irsf25_short_horizon"]
        assert label["schema"] == "czr005.g4irsf25.short_horizon_branch.v1"
        assert label["rejoin_node"] == 24
        assert label["rejoin_arrived"] is True
        assert label["private_cost_seconds"] >= 0.0
        assert label["private_cost_seconds"] <= label["max_horizon_seconds"]
        assert label["queue_area_bag_seconds"] >= 0.0
        assert label["scheduled_incoming_area_bag_seconds"] >= 0.0
        assert label["local_system_cost"] == pytest.approx(
            label["queue_area_bag_seconds"]
            + label["scheduled_incoming_area_bag_seconds"]
        )
        assert label["local_backlog_at_horizon"] >= 0
        assert label["safety_pass"] is True
        assert branch["private_cost_seconds"] == label["private_cost_seconds"]
        assert branch["local_system_cost"] == label["local_system_cost"]
        assert branch["invariants"]["runtime_full_astar_call_count"] == 0
        assert branch["invariants"]["runtime_global_scan_count"] == 0
        assert branch["invariants"]["runtime_future_route_read_count"] == 0

    baseline, treatment = branches
    assert pair["g4irsf25_private_cost_delta_seconds"] == pytest.approx(
        treatment["private_cost_seconds"] - baseline["private_cost_seconds"]
    )
    assert pair["g4irsf25_local_system_cost_delta"] == pytest.approx(
        treatment["local_system_cost"] - baseline["local_system_cost"]
    )


def test_native_empty_and_explicit_off_artifacts_are_exact_s4_noops() -> None:
    backend = _backend()
    nodes, edges, heuristic, bags, *_ = _arguments()
    binary = Path(backend.__file__).resolve()
    common = {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": bags,
        "enable_source_admission": False,
        "admission_mode": "off",
        "resource_semantics": "R3",
        "event_semantics": "E4",
        "pibt_mode": "P2",
        "priority_mode": "Q0",
        "scorer_mode": "S4",
        "merge_grant_timing_mode": "J2",
        "g4irsf20_event_hotpath_policy": "E2",
        "scenario": "g4irsf25_native_off_noop_fixture",
        "max_simulation_time": 1_000.0,
        "trace_limit": 256,
        "event_trace_limit": 0,
        "search_path": binary.parent,
        "expected_binary_path": binary,
    }

    pure_s4 = cpp_backend.g4irsf11_event_runtime_from_records(**common)
    empty = cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf25_clcr_artifact={},
    )
    explicit_off = cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf25_clcr_artifact={
            "schema": "czr005.g4irsf25.clcr.v1",
            "mode": "off",
        },
    )

    baseline = _s4_projection(pure_s4)
    assert baseline["completed_count"] == len(bags)
    assert baseline["decisions"]
    assert _s4_projection(empty) == baseline
    assert _s4_projection(explicit_off) == baseline


def test_g25_target_fields_are_atomic_and_next_edge_only() -> None:
    backend = _backend()
    arguments = _arguments()
    row = _branch_16_row(backend, arguments)

    partial = _target(row, g25=False)
    partial["g4irsf25_rejoin_node"] = 24
    with pytest.raises(ValueError, match="all four fields"):
        _run(backend, arguments, partial)

    wait = _target(row)
    wait["action_kind"] = "WAIT"
    wait.pop("selected_next_node")
    with pytest.raises(ValueError, match="G21 NEXT_EDGE"):
        _run(backend, arguments, wait)

    overlong = _target(row)
    overlong["g4irsf25_max_horizon_seconds"] = 601.0
    with pytest.raises(ValueError, match="at most 600"):
        _run(backend, arguments, overlong)


def test_g25_nonarrival_timeout_is_retained_as_capped_private_cost() -> None:
    backend = _backend()
    arguments = _arguments()
    target = _target(_branch_16_row(backend, arguments))
    target["g4irsf25_max_horizon_seconds"] = 30.0
    pair = _run(backend, arguments, target)

    assert pair["pair_complete"] is True
    assert pair["g4irsf25_any_timeout"] is True
    labels = [
        branch["g4irsf25_short_horizon"]
        for branch in (pair["baseline"], pair["treatment"])
    ]
    nonarrivals = [label for label in labels if not label["rejoin_arrived"]]
    assert nonarrivals
    for label in nonarrivals:
        assert label["timeout"] is True
        assert label["private_cost_censored"] is True
        assert label["private_cost_seconds"] == 30.0
        assert label["coverage_complete"] is True
        assert label["stop_reason"] == "G25_MAX_HORIZON_TIMEOUT"


def test_g21_target_without_g25_fields_keeps_legacy_branch_shape() -> None:
    backend = _backend()
    arguments = _arguments()
    pair = _run(
        backend,
        arguments,
        _target(_branch_16_row(backend, arguments), g25=False),
    )

    assert pair["pair_status"] == "ACTION_CHANGED_HORIZON_COMPLETE"
    assert not any(key.startswith("g4irsf25_") for key in pair)
    for branch in (pair["baseline"], pair["treatment"]):
        assert "g4irsf25_short_horizon" not in branch
        assert "private_cost_seconds" not in branch
        assert "local_system_cost" not in branch
        # G22's pre-existing 5/15/30/60 local future seam is unchanged.
        assert "local_future_summary" in branch
