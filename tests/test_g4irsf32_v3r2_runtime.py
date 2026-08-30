from __future__ import annotations

from pathlib import Path
from typing import Any
import copy

import pytest

from czr005.cpp_backend import g4irsf11_event_runtime_from_records


ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "build_g32_v3r2" / "python" / "Release"
SCHEMA_ID = "czr005.g4irsf32.external_commit_local_virtual_slot_shadow.v3r4"

ROW_KEYS = {
    "observation_ordinal",
    "opportunity_id",
    "event_time",
    "event_seq",
    "node",
    "calendar_generation_before",
    "seam_kind_code",
    "external_path_code",
    "external_task_id",
    "external_runtime_bag_id",
    "external_upstream_node",
    "external_slot_start_seconds",
    "external_slot_end_seconds",
    "external_service_seconds",
    "external_projected_arrival",
    "has_direct_episode_identity",
    "external_direct_episode_event_seq",
    "has_j2_identity",
    "external_request_id",
    "external_request_lineage",
    "external_request_generation",
    "external_junction_queue_generation",
    "local_task_id",
    "local_runtime_bag_id",
    "local_service_seconds",
    "local_source_ready_count",
    "local_source_uncovered_service_work_seconds",
    "external_scheduled_incoming_count",
    "destination_pending_count",
    "oldest_local_wait_age_seconds",
    "oldest_external_wait_age_seconds",
    "local_source_enqueued_at",
    "local_release",
    "local_deadline",
    "local_choose_bag_index",
    "local_escape_token_runtime_bag_id",
    "local_queue_nonempty",
    "local_bag_exists",
    "local_released_live",
    "local_source_queue_at_node",
    "local_distinct_from_external",
    "local_service_required",
    "local_guards_passed",
    "L0",
    "service_calendar_next_free_seconds",
    "existing_calendar_wait_seconds",
    "L1",
    "X_insert",
    "H_gap",
    "overlap_seconds",
    "epsilon",
    "selected_action_from_node",
    "selected_action_to_node",
    "selected_action_kind_code",
    "local_origin_code",
    "external_origin_code",
    "action_changed",
    "future_release_read_count",
    "global_scan_count",
    "calendar_mutation_count",
}


def _request(*, j2: bool, mode: str = "shadow") -> dict[str, Any]:
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
            ("v3r2-local-first", 32032001, 0.0, 100.0, 1, 3, "local"),
            ("v3r2-local-winner", 32032002, 0.0, 100.0, 1, 3, "local"),
            ("v3r2-external", 32032000, 0.699, 100.0, 0, 3, "external"),
        ],
        "queue_discipline": "fifo",
        "retry_interval": 0.25,
        "minimum_service_seconds": 0.001,
        "dispatch_headway_seconds": 0.001,
        "history_limit": 8,
        "max_decisions_per_bag": 512,
        "max_events": 2_000_000,
        "max_simulation_time": -1.0,
        "trace_limit": 200_000,
        "event_trace_limit": 200_000,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
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
        "enable_opportunity_telemetry": False,
        "opportunity_trace_limit": 0,
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "complete_on_goal_arrival": True,
        "storage_source_nodes": [0, 4] if j2 else [0],
        "source_aware_destination_service_mode": mode,
        "source_aware_destination_service_trace_limit": 200_000,
        "search_path": BINDING,
    }


def _assert_census(summary: dict[str, Any]) -> None:
    considered = summary[
        "source_aware_destination_service_external_commit_considered_count"
    ]
    assert considered == sum(
        summary[key]
        for key in (
            "source_aware_destination_service_no_local_count",
            "source_aware_destination_service_local_guard_fail_count",
            "source_aware_destination_service_non_overlap_count",
            "source_aware_destination_service_staged_rollback_count",
            "source_aware_destination_service_observation_stored_count",
            "source_aware_destination_service_observation_dropped_count",
        )
    )
    assert considered == (
        summary["source_aware_destination_service_direct_external_commit_count"]
        + summary["source_aware_destination_service_j2_exact_commit_count"]
    )
    assert summary["source_aware_destination_service_staged_rollback_count"] == 0
    assert summary["source_aware_destination_service_observation_dropped_count"] == 0


def test_v3r2_modes_and_generic_storage_roles_fail_closed() -> None:
    with pytest.raises(ValueError, match="must be off, shadow, or closed_loop"):
        g4irsf11_event_runtime_from_records(**_request(j2=False, mode="enabled"))

    omitted = _request(j2=False)
    omitted.pop("storage_source_nodes")
    with pytest.raises(ValueError, match="explicit nonempty unique"):
        g4irsf11_event_runtime_from_records(**omitted)

    for storage in ([], [2]):
        request = _request(j2=False)
        request["storage_source_nodes"] = storage
        with pytest.raises(ValueError, match="explicit nonempty unique"):
            g4irsf11_event_runtime_from_records(**request)

    duplicate = _request(j2=False)
    duplicate["storage_source_nodes"] = [0, 0]
    with pytest.raises(ValueError, match="must not contain duplicates"):
        g4irsf11_event_runtime_from_records(**duplicate)

    assert g4irsf11_event_runtime_from_records(**_request(j2=True))["summary"][
        "source_aware_destination_service_mode"
    ] == "shadow"

    type1_start = _request(j2=False)
    type1_start["storage_source_nodes"] = [1]
    assert g4irsf11_event_runtime_from_records(**type1_start)["summary"][
        "source_aware_destination_service_mode"
    ] == "shadow"


def test_v3r2_frozen_map2_type1_storage_start_executes() -> None:
    from scripts.eval import (
        run_g4irsf32_v3r2_external_commit_local_virtual_shadow as runner,
    )

    binary = next(BINDING.glob("czr005_cpp*.pyd"))
    request, hashes = runner.map2_fixture(mode="shadow", binary=binary)
    assert request["storage_source_nodes"] == [52]
    assert next(
        row[1] for row in request["node_records"] if row[0] == 52
    ) == 1
    payload = g4irsf11_event_runtime_from_records(**request)
    assert payload["summary"][
        "source_aware_destination_service_mode"
    ] == "shadow"
    assert hashes["storage_source_nodes"] == [52]


def test_v3r2_j2_summary_uses_the_executed_request_manifest() -> None:
    from scripts.eval import (
        run_g4irsf32_v3r2_external_commit_local_virtual_shadow as runner,
    )

    case = runner.V3R2Case(1.0, 8, "simultaneous_local_first")
    binary = next(BINDING.glob("czr005_cpp*.pyd"))
    result = runner.run_case(
        case,
        executor=g4irsf11_event_runtime_from_records,
        binary=binary,
        j2=True,
    )
    assert result["shadow_request"]["bag_records"][-1][4] == 4
    summary = runner.summarize_case(case, result)
    assert summary["off_audit"]["checks"][
        "exact_request_population_identity"
    ] is True
    assert summary["shadow_audit"]["checks"][
        "exact_request_population_identity"
    ] is True
    assert summary["hard_gate_pass"] is True


def test_v3r2_census_is_bound_to_every_ordinary_commit_seam() -> None:
    from scripts.eval import (
        run_g4irsf32_v3r2_external_commit_local_virtual_shadow as runner,
    )

    case = runner.V3R2Case(1.0, 8, "simultaneous_local_first")
    binary = next(BINDING.glob("czr005_cpp*.pyd"))
    result = runner.run_case(
        case,
        executor=g4irsf11_event_runtime_from_records,
        binary=binary,
    )
    forged = copy.deepcopy(result["shadow"])
    forged[runner.ROW_KEY].pop()
    for suffix in (
        "observation_stored_count",
        "external_commit_considered_count",
        "direct_external_commit_count",
    ):
        forged["summary"][runner.NS + suffix] -= 1
    rows = runner.extract_rows(
        forged,
        case_id=case.case_id,
        request=result["shadow_request"],
    )
    census = runner._shadow_census(forged["summary"], rows, forged)
    assert census["partition"] is True
    assert census["stored_matches"] is True
    assert census["ordinary_commit_seam_binding"] is False
    assert census["pass"] is False


def test_v3r2_exact_off_omits_extension_and_keeps_call_shape() -> None:
    explicit_request = _request(j2=False, mode="off")
    explicit = g4irsf11_event_runtime_from_records(**explicit_request)
    implicit_request = dict(explicit_request)
    implicit_request.pop("source_aware_destination_service_mode")
    implicit_request.pop("source_aware_destination_service_trace_limit")
    implicit = g4irsf11_event_runtime_from_records(**implicit_request)
    for key in ("bags", "events", "decisions", "hold_attempts", "junction_state"):
        assert implicit[key] == explicit[key]
    assert "source_aware_destination_service_shadow" not in explicit
    assert "source_aware_destination_service_schema_id" not in explicit["trace_context"]
    assert not any(
        key.startswith("source_aware_destination_service_")
        for key in explicit["summary"]
    )


@pytest.mark.parametrize("j2, seam", [(False, 1), (True, 2)])
def test_v3r2_numeric_schema_unique_publish_and_action_inert(
    j2: bool, seam: int
) -> None:
    payload = g4irsf11_event_runtime_from_records(**_request(j2=j2))
    off_payload = g4irsf11_event_runtime_from_records(
        **_request(j2=j2, mode="off")
    )
    for key in ("bags", "events", "decisions", "hold_attempts", "junction_state"):
        assert payload[key] == off_payload[key]

    rows = payload["source_aware_destination_service_shadow"]
    selected = [row for row in rows if row["seam_kind_code"] == seam]
    assert len(selected) == 1
    row = selected[0]
    assert set(row) == ROW_KEYS
    assert not any(isinstance(value, str) for value in row.values())
    assert row["external_path_code"] == seam
    assert row["local_guards_passed"] is True
    assert row["X_insert"] == pytest.approx(row["L1"] - row["L0"])
    assert row["H_gap"] == pytest.approx(
        row["L1"] - row["external_slot_start_seconds"]
    )
    assert row["X_insert"] > 0.0 and row["overlap_seconds"] > 0.0
    assert row["local_task_id"] == 32032002
    assert row["local_runtime_bag_id"] == 1
    assert row["local_choose_bag_index"] == 0
    assert row["local_escape_token_runtime_bag_id"] == -1
    assert row["local_release"] == pytest.approx(0.0)
    assert row["local_deadline"] == pytest.approx(100.0)
    assert row["local_source_enqueued_at"] == pytest.approx(0.0)
    assert row["local_source_ready_count"] == 1
    assert row["local_source_uncovered_service_work_seconds"] == pytest.approx(
        row["local_source_ready_count"] * row["local_service_seconds"]
    )
    assert row["external_scheduled_incoming_count"] >= 0
    assert row["destination_pending_count"] >= 0
    assert row["oldest_local_wait_age_seconds"] == pytest.approx(
        row["event_time"] - row["local_source_enqueued_at"]
    )
    assert row["oldest_external_wait_age_seconds"] >= 0.0
    assert row["L0"] == pytest.approx(1.0)
    assert row["service_calendar_next_free_seconds"] == pytest.approx(row["L0"])
    assert row["existing_calendar_wait_seconds"] == pytest.approx(
        row["L0"] - row["event_time"]
    )
    assert row["L1"] == pytest.approx(2.0)
    assert row["selected_action_from_node"] == row["external_upstream_node"]
    assert row["selected_action_to_node"] == row["node"]
    assert row["selected_action_kind_code"] == seam
    assert row["local_origin_code"] == 1
    assert row["external_origin_code"] == 2
    assert row["action_changed"] is False
    assert row["future_release_read_count"] == 0
    assert row["global_scan_count"] == 0
    assert row["calendar_mutation_count"] == 0
    if j2:
        assert row["destination_pending_count"] >= 1
        assert row["has_j2_identity"] is True
        assert row["has_direct_episode_identity"] is False
        assert row["external_direct_episode_event_seq"] == 0
        commits = [
            item
            for item in payload["merge_grant_lifecycle"]
            if item["state"] == "COMMITTED"
            and item["reason"] == "exact_slot_committed"
            and item["request_id"] == row["external_request_id"]
            and item["lineage"] == row["external_request_lineage"]
        ]
        assert len(commits) == 1
        assert commits[0]["calendar_generation"] == (
            row["calendar_generation_before"] + 1
        )
        assert commits[0]["observed_claimed_calendar_generation"] == commits[0][
            "calendar_generation"
        ]
    else:
        assert row["destination_pending_count"] == 0
        assert row["oldest_external_wait_age_seconds"] == pytest.approx(0.0)
        assert row["has_direct_episode_identity"] is True
        assert row["has_j2_identity"] is False
        assert row["external_direct_episode_event_seq"] == row["event_seq"]
    duplicates = [
        candidate
        for candidate in rows
        if candidate["external_runtime_bag_id"] == row["external_runtime_bag_id"]
        and candidate["node"] == row["node"]
        and candidate["external_slot_start_seconds"]
        == pytest.approx(row["external_slot_start_seconds"])
        and candidate["external_slot_end_seconds"]
        == pytest.approx(row["external_slot_end_seconds"])
    ]
    assert len(duplicates) == 1
    assert payload["trace_context"][
        "source_aware_destination_service_schema_id"
    ] == SCHEMA_ID
    assert payload["trace_context"]["schema_id"] == (
        "czr005.g4irsf11.decision_trace.v1"
    )
    summary = payload["summary"]
    _assert_census(summary)
    assert summary["source_aware_destination_service_incremental_local_state_bytes"] == 0
    assert summary["source_aware_destination_service_trace_sidecar_accounted_bytes"] > 0
    assert summary["source_aware_destination_service_total_accounted_bytes"] == summary[
        "cpp_internal_accounted_bytes"
    ]
