from __future__ import annotations

from collections.abc import Iterable

import pytest

from czr005 import cpp_backend
from czr005.datasets.decision_trace import canonicalise_decision_row


def _require_cpp() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def _line_records(
    *, service_time: float = 1.0, travel_time: float = 1.0
) -> tuple[list[tuple[int, int, float, int, int, list[int]]], list[tuple[int, int, float, float]], list[list[float]]]:
    nodes = [
        (0, 1, service_time, 0, 0, [1]),
        (1, 4, service_time, 1, 0, [2]),
        (2, 2, service_time, 2, 0, []),
    ]
    edges = [(0, 1, travel_time, 1.0), (1, 2, travel_time, 1.0)]
    heuristic = [[0.0, 1.0, 2.0], [1.0, 0.0, 1.0], [2.0, 1.0, 0.0]]
    return nodes, edges, heuristic


def _bags(count: int, *, task_offset: int = 0) -> list[tuple[str, int, float, float, int, int, str]]:
    return [
        (f"burst-{index}", task_offset + index + 1, 0.0, 1_000.0, 0, 2, "source-0")
        for index in range(count)
    ]


def _run(
    *,
    nodes: list[tuple[int, int, float, int, int, list[int]]],
    edges: list[tuple[int, int, float, float]],
    heuristic: list[list[float]],
    bags: Iterable[tuple[str, int, float, float, int, int, str]],
    faults: Iterable[
        tuple[int, int, float, float, float]
        | tuple[int, int, float, float, float, bool]
    ] = (),
    **kwargs: object,
) -> dict[str, object]:
    _require_cpp()
    retry_interval = float(kwargs.pop("retry_interval", 0.05))
    max_simulation_time = float(kwargs.pop("max_simulation_time", 200.0))
    trace_limit = int(kwargs.pop("trace_limit", 200_000))
    return cpp_backend.g4irsf11_event_runtime_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=list(bags),
        fault_windows=list(faults),
        retry_interval=retry_interval,
        max_simulation_time=max_simulation_time,
        trace_limit=trace_limit,
        scenario=str(kwargs.pop("scenario", "pytest_manual")),
        **kwargs,
    )


def _assert_invariants(payload: dict[str, object], completed: int) -> None:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["completed_count"] == completed
    assert summary["failed_count"] == 0
    assert summary["reservation_conflicts"] == 0
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["global_reservation_scan_count"] == 0
    assert summary["reservation_depth"] == 1
    assert summary["two_step_reservation_count"] == 0
    assert summary["max_edges_selected_per_arrive"] <= 1
    assert summary["release_selected_edge_count"] == 0
    assert summary["bag_future_path_field_present"] is False
    assert summary["full_future_routes_stored"] == 0
    assert summary["max_history_observed"] <= 8
    assert summary["runtime_seconds"] >= 0.0
    assert summary["decision_latency_us_p50"] >= 0.0
    assert summary["decision_latency_us_p50"] <= summary["decision_latency_us_p95"]
    assert summary["decision_latency_us_p95"] <= summary["decision_latency_us_p99"]
    assert summary["cpp_internal_accounted_bytes"] > 0
    assert 0 <= summary["peak_active_bag_count"] <= summary["requested_count"]
    assert summary["final_active_bag_count"] == 0

    junction_state = payload["junction_state"]
    assert isinstance(junction_state, list)
    assert junction_state
    final_junction_accounted_bytes = 0
    service_reservation_count = 0
    cumulative_service_reserved_seconds = 0.0
    for junction in junction_state:
        assert junction["final_source_queue_length"] == 0
        assert junction["final_junction_queue_length"] == 0
        assert junction["final_service_calendar_intervals"] == 0
        assert junction["scheduled_incoming"] == 0
        assert 0 <= junction["final_source_queue_length"] <= junction["peak_source_queue_length"]
        assert (
            0
            <= junction["final_junction_queue_length"]
            <= junction["peak_junction_queue_length"]
        )
        assert (
            0
            <= junction["final_service_calendar_intervals"]
            <= junction["peak_service_calendar_intervals"]
        )
        assert (
            0
            < junction["final_local_state_accounted_bytes"]
            <= junction["peak_local_state_accounted_bytes"]
        )
        assert junction["local_state_accounting_semantics"] == (
            "cpp_object_plus_live_deque_payload_plus_calendar_capacity_lower_bound"
        )
        assert junction["service_reservation_count"] >= 0
        assert junction["cumulative_service_reserved_seconds"] >= 0.0
        if junction["service_reservation_count"] == 0:
            assert junction["first_service_reservation_start_time"] == -1.0
            assert junction["last_service_reservation_end_time"] == -1.0
            assert junction["cumulative_service_reserved_seconds"] == 0.0
        else:
            reservation_span = (
                junction["last_service_reservation_end_time"]
                - junction["first_service_reservation_start_time"]
            )
            assert junction["first_service_reservation_start_time"] >= 0.0
            assert junction["last_service_reservation_end_time"] > junction[
                "first_service_reservation_start_time"
            ]
            assert (
                junction["cumulative_service_reserved_seconds"]
                <= reservation_span + 1.0e-9
            )
        final_junction_accounted_bytes += junction["final_local_state_accounted_bytes"]
        service_reservation_count += junction["service_reservation_count"]
        cumulative_service_reserved_seconds += junction[
            "cumulative_service_reserved_seconds"
        ]
    assert summary["cpp_internal_accounted_bytes"] >= final_junction_accounted_bytes
    assert service_reservation_count >= completed
    assert cumulative_service_reserved_seconds >= 0.0

    events = payload["events"]
    assert isinstance(events, list)
    assert all(
        event["selected_edge_count"] <= 1
        for event in events
        if event["event"] == "ARRIVE_JUNCTION"
    )
    assert all(
        event["selected_edge_count"] == 0
        for event in events
        if event["event"] == "BAG_RELEASE"
    )
    for decision in payload["decisions"]:
        candidate_nodes = set(decision["candidate_next_nodes"])
        assert decision["selected_next"] in candidate_nodes
        assert decision["model_prediction"] in candidate_nodes
        assert decision["full_astar_used"] is False
        assert "path_history" not in decision
        assert "finish_time" not in decision
        canonicalise_decision_row(decision)


def test_pre_release_time_limit_returns_exact_empty_junction_negative_evidence() -> None:
    nodes, edges, heuristic = _line_records()
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("future-release", 1, 10.0, 100.0, 0, 2, "source-0")],
        max_simulation_time=0.0,
    )
    summary = payload["summary"]
    assert summary["completed_count"] == 0
    assert summary["failed_count"] == 1
    assert summary["event_count"] == 0
    assert summary["bag_release_event_count"] == 0
    assert summary["peak_active_bag_count"] == 0
    assert summary["final_active_bag_count"] == 0
    assert summary["end_time"] == 0.0
    assert summary["event_limit_reached"] is False
    assert summary["time_limit_reached"] is True
    assert summary["cpp_internal_accounted_bytes"] > 0
    assert payload["junction_state"] == []


@pytest.mark.parametrize("count", [1, 2, 4, 8, 16])
def test_event_runtime_burst_sizes_are_online_and_conflict_free(count: int) -> None:
    nodes, edges, heuristic = _line_records()
    payload = _run(nodes=nodes, edges=edges, heuristic=heuristic, bags=_bags(count))
    _assert_invariants(payload, count)
    summary = payload["summary"]
    assert summary["decision_count"] >= count * 2
    assert summary["max_source_queue_length"] >= count - 1
    assert summary["peak_active_bag_count"] == count
    junction_state = payload["junction_state"]
    assert sum(row["service_reservation_count"] for row in junction_state) == count * 3
    assert sum(row["cumulative_service_reserved_seconds"] for row in junction_state) == pytest.approx(
        count * 3.0
    )
    if count == 16:
        assert summary["max_source_queue_delay"] >= 14.9
        assert 0.0 < summary["fairness_jain"] <= 1.0
        source = next(row for row in junction_state if row["node"] == 0)
        assert source["peak_source_queue_length"] >= count - 1
        assert (
            source["peak_local_state_accounted_bytes"]
            > source["final_local_state_accounted_bytes"]
        )


def test_event_runtime_exposes_real_scheduler_event_vocabulary() -> None:
    nodes, edges, heuristic = _line_records(service_time=0.001)
    payload = _run(nodes=nodes, edges=edges, heuristic=heuristic, bags=_bags(1))
    names = {event["event"] for event in payload["events"]}
    assert {
        "BAG_RELEASE",
        "ARRIVE_JUNCTION",
        "JUNCTION_SERVICE_COMPLETE",
        "EDGE_ENTER",
        "EDGE_EXIT",
        "LOCAL_QUEUE_UPDATE",
        "CONGESTION_BEACON_UPDATE",
    } <= names


def test_bidirectional_competition_uses_one_shared_local_corridor_calendar() -> None:
    nodes = [(0, 1, 0.001, 0, 0, [1]), (1, 2, 0.001, 1, 0, [0])]
    edges = [(0, 1, 1.0, 1.0), (1, 0, 1.0, 1.0)]
    heuristic = [[0.0, 1.0], [1.0, 0.0]]
    bags = [
        ("east", 101, 0.0, 20.0, 0, 1, "west"),
        ("west", 102, 0.0, 20.0, 1, 0, "east"),
    ]
    payload = _run(nodes=nodes, edges=edges, heuristic=heuristic, bags=bags)
    _assert_invariants(payload, 2)
    departures = sorted(
        (
            decision["event_time"],
            decision["event_time"] + decision["candidate_records"][0]["features"]["travel_time"],
        )
        for decision in payload["decisions"]
    )
    assert departures[0][1] <= departures[1][0] + 1.0e-9
    assert payload["summary"]["shield_rejection_count"] > 0
    assert payload["hold_attempts"]


def test_lower_is_better_score_contract_is_explicit_and_argmin() -> None:
    nodes = [
        (0, 1, 0.001, 0, 0, [1, 2]),
        (1, 4, 0.001, 1, 1, []),
        (2, 2, 0.001, 1, 0, []),
    ]
    edges = [(0, 1, 1.0, 1.0), (0, 2, 1.0, 1.0)]
    heuristic = [[0.0, 0.0, 0.0], [0.0, 0.0, 10.0], [0.0, 1.0, 0.0]]
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("score-contract", 201, 0.0, 20.0, 0, 2, "source")],
        scenario="score_contract",
    )
    _assert_invariants(payload, 1)
    decision = payload["decisions"][0]
    score_by_node = {
        record["next_node"]: record["model_score"] for record in decision["candidate_records"]
    }
    assert decision["model_prediction"] == min(score_by_node, key=score_by_node.get)
    sorted_scores = sorted(score_by_node.values())
    assert decision["model_margin"] == pytest.approx(sorted_scores[1] - sorted_scores[0])
    assert decision["metadata"]["model_score_semantics"] == "lower_is_better_cost"
    assert payload["trace_context"]["model_score_semantics"] == "lower_is_better_cost"


def test_fault_message_delay_is_shielded_and_repair_resumes_without_astar() -> None:
    nodes, edges, heuristic = _line_records(service_time=0.001)
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("fault-wait", 301, 0.0, 20.0, 0, 2, "source")],
        faults=[(0, 1, 0.0, 1.0, 0.25)],
        retry_interval=0.1,
        deadlock_retry_threshold=2,
    )
    _assert_invariants(payload, 1)
    summary = payload["summary"]
    assert summary["stale_fault_shield_rejection_count"] > 0
    assert summary["deadlock_count"] > 0
    assert summary["resolved_deadlock_count"] > 0
    assert summary["unresolved_deadlock_count"] == 0
    physical = [event for event in payload["events"] if event["reason"] == "physical_state_change"]
    messages = [event for event in payload["events"] if event["reason"] == "local_message_delivery"]
    assert {event["event"] for event in physical} == {"FAULT", "REPAIR"}
    assert {event["event"] for event in messages} == {"FAULT", "REPAIR"}
    assert all(row["selected_next"] is None for row in payload["hold_attempts"])


def test_fault_policy_off_disables_advertised_actions_but_not_physical_interlock() -> None:
    from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics

    nodes = [
        (0, 1, 0.001, 0, 0, [1, 2]),
        (1, 2, 0.001, 2, 0, []),
        (2, 4, 0.001, 1, 1, [1]),
    ]
    edges = [(0, 1, 1.0, 1.0), (0, 2, 1.0, 1.0), (2, 1, 1.0, 1.0)]
    heuristic = [[0.0, 0.0, 0.0], [1.0, 0.0, 1.0], [1.0, 1.0, 0.0]]
    common = dict(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("fault-policy", 351, 0.0, 20.0, 0, 1, "source")],
        faults=[(0, 1, 0.0, 1.0, 0.0)],
        retry_interval=0.05,
    )

    policy_on = _run(**common, enable_fault_policy=True, scenario="fault_policy_on")
    _assert_invariants(policy_on, 1)
    on_summary = policy_on["summary"]
    assert on_summary["fault_policy_enabled"] is True
    assert on_summary["fault_affected_bag_count"] == 1
    assert on_summary["fault_target_edge_candidate_exposure_count"] > 0
    assert on_summary["fault_target_edge_attempt_count"] > 0
    assert on_summary["local_fault_policy_action_count"] > 0
    assert on_summary["local_fault_policy_reroute_count"] > 0
    assert {
        row["phase"] for row in policy_on["fault_events"]
    } >= {"target_edge_candidate_exposure", "target_edge_attempt", "local_fault_policy_reroute"}

    policy_off = _run(**common, enable_fault_policy=False, scenario="fault_policy_off")
    _assert_invariants(policy_off, 1)
    off_summary = policy_off["summary"]
    assert off_summary["fault_policy_enabled"] is False
    assert off_summary["fault_affected_bag_count"] == 1
    assert off_summary["fault_target_edge_candidate_exposure_count"] > 0
    assert off_summary["fault_target_edge_attempt_count"] > 0
    assert off_summary["local_fault_policy_action_count"] == 0
    assert off_summary["local_fault_policy_hold_count"] == 0
    assert off_summary["local_fault_policy_reroute_count"] == 0
    assert off_summary["physical_fault_interlock_rejection_count"] > 0
    assert off_summary["physical_fault_interlock_hold_count"] > 0
    assert off_summary["physical_fault_interlock_reroute_count"] == 0
    assert off_summary["physical_fault_edge_entry_violation_count"] == 0
    assert all(
        candidate["features"]["advertised_fault"] is False
        for row in policy_off["hold_attempts"]
        for candidate in row["candidate_records"]
    )
    assert not [
        row
        for row in policy_off["fault_events"]
        if row["phase"].startswith("local_fault_policy_")
    ]
    assert {
        row["phase"] for row in policy_off["fault_events"]
    } >= {
        "target_edge_candidate_exposure",
        "target_edge_attempt",
        "physical_fault_interlock_rejection",
        "physical_fault_interlock_hold",
    }

    window = FaultWindow(0, 1, 0.0, 1.0, 0.0)
    on_gate = fault_window_metrics(
        policy_on["bags"],
        policy_on["fault_events"],
        policy_on["summary"],
        [window],
        max_recovery_seconds=5.0,
    )[0]
    off_gate = fault_window_metrics(
        policy_off["bags"],
        policy_off["fault_events"],
        policy_off["summary"],
        [window],
        max_recovery_seconds=5.0,
    )[0]
    assert on_gate["fault_recovery_pass"] is True
    assert on_gate["local_fault_policy_action_count"] > 0
    assert off_gate["fault_recovery_pass"] is True
    assert off_gate["local_fault_policy_action_count"] == 0
    assert off_gate["physical_interlock_rejection_count"] > 0


def test_fault_during_traversal_does_not_retroactively_create_future_replan() -> None:
    nodes = [(0, 1, 0.001, 0, 0, [1]), (1, 2, 0.001, 1, 0, [])]
    edges = [(0, 1, 5.0, 1.0)]
    heuristic = [[0.0, 5.0], [5.0, 0.0]]
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("in-flight", 401, 0.0, 20.0, 0, 1, "source")],
        faults=[(0, 1, 1.0, 3.0, 0.5)],
        trace_limit=0,
    )
    _assert_invariants(payload, 1)
    assert payload["bags"][0]["finish_time"] > 5.0
    assert payload["decisions"] == []
    assert payload["events"] == []
    assert payload["summary"]["physical_fault_window_traversal_count"] == 1
    assert payload["summary"]["physical_fault_edge_entry_violation_count"] == 0
    assert payload["summary"]["event_trace_truncated"] is True
    assert {row["phase"] for row in payload["fault_events"]} >= {
        "physical_state_change",
        "local_message_delivery",
    }
    fault_start = next(
        row
        for row in payload["fault_events"]
        if row["event"] == "FAULT" and row["phase"] == "physical_state_change"
    )
    assert fault_start["inflight_traversal_count"] == 1
    assert not [row for row in payload["fault_events"] if row["phase"] == "unsafe_edge_entry"]


def test_loop_tabu_uses_only_bounded_past_history() -> None:
    nodes = [
        (0, 1, 0.001, 0, 0, [1]),
        (1, 4, 0.001, 1, 0, [0, 2]),
        (2, 2, 0.001, 2, 0, []),
    ]
    edges = [(0, 1, 1.0, 1.0), (1, 0, 1.0, 1.0), (1, 2, 1.0, 1.0)]
    heuristic = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 10.0]]
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("tabu", 501, 0.0, 20.0, 0, 2, "source")],
    )
    _assert_invariants(payload, 1)
    assert payload["summary"]["loop_count"] == 0
    assert all(len(decision["short_history"]) <= 8 for decision in payload["decisions"])
    assert all("future_path" not in decision for decision in payload["decisions"])


def test_history_limit_above_trace_contract_fails_closed() -> None:
    nodes, edges, heuristic = _line_records(service_time=0.001)
    with pytest.raises(ValueError, match="history_limit"):
        _run(
            nodes=nodes,
            edges=edges,
            heuristic=heuristic,
            bags=_bags(1),
            history_limit=9,
        )


def test_deterministic_trace_shards_are_disjoint_and_cover_all_tasks() -> None:
    nodes, edges, heuristic = _line_records(service_time=0.01)
    common = dict(nodes=nodes, edges=edges, heuristic=heuristic, bags=_bags(16))
    even = _run(**common, trace_shard_count=2, trace_shard_index=0, scenario="shard")
    odd = _run(**common, trace_shard_count=2, trace_shard_index=1, scenario="shard")
    even_tasks = {row["task_id"] for row in even["decisions"]}
    odd_tasks = {row["task_id"] for row in odd["decisions"]}
    assert even_tasks
    assert odd_tasks
    assert even_tasks.isdisjoint(odd_tasks)
    assert even_tasks | odd_tasks == set(range(1, 17))
    assert all(task_id % 2 == 0 for task_id in even_tasks)
    assert all(task_id % 2 == 1 for task_id in odd_tasks)
    assert (
        even["summary"]["decision_trace_shard_seen_count"]
        + odd["summary"]["decision_trace_shard_seen_count"]
        == even["summary"]["decision_trace_seen_count"]
    )
    assert even["trace_context"]["trace_sampling"] == (
        "deterministic_task_id_modulo_shard_then_limit"
    )


def test_trace_limit_reports_truncation_instead_of_silent_prefix_pass() -> None:
    nodes, edges, heuristic = _line_records(service_time=0.01)
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=_bags(4),
        trace_limit=1,
    )
    assert payload["summary"]["decision_trace_seen_count"] > 1
    assert payload["summary"]["decision_trace_stored_count"] + payload["summary"][
        "hold_trace_stored_count"
    ] == 1
    assert payload["summary"]["decision_trace_truncated"] is True


def test_duplicate_original_task_id_segments_keep_unique_runtime_identity() -> None:
    nodes, edges, heuristic = _line_records(service_time=0.001)
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[
            ("77:storage_in", 77, 0.0, 100.0, 0, 2, "source"),
            ("77:storage_out", 77, 10.0, 100.0, 0, 2, "source"),
        ],
    )
    _assert_invariants(payload, 2)
    assert {row["task_id"] for row in payload["bags"]} == {77}
    assert {row["segment_id"] for row in payload["bags"]} == {
        "77:storage_in",
        "77:storage_out",
    }
    assert len({row["runtime_bag_id"] for row in payload["bags"]}) == 2
    identities = {
        (row["metadata"]["runtime_bag_id"], row["task_id"], row["segment_id"])
        for row in payload["decisions"]
    }
    assert {task_id for _, task_id, _ in identities} == {77}
    assert len({runtime_id for runtime_id, _, _ in identities}) == 2
    assert payload["trace_context"]["original_task_id_rewritten"] is False


def test_explicit_dropped_fault_notifications_do_not_fake_message_delivery() -> None:
    from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics

    nodes, edges, heuristic = _line_records(service_time=0.001)
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=[("sensor-loss", 601, 0.0, 20.0, 0, 2, "source")],
        faults=[(0, 1, 0.0, 1.0, 0.25, True)],
        retry_interval=0.1,
    )
    _assert_invariants(payload, 1)
    assert payload["summary"]["sensor_loss_mode_used"] is True
    assert payload["summary"]["fault_notification_drop_count"] == 2
    assert payload["summary"]["stale_fault_shield_rejection_count"] > 0
    assert not [
        event for event in payload["events"] if event["reason"] == "local_message_delivery"
    ]
    assert {row["phase"] for row in payload["fault_events"]} >= {
        "physical_state_change",
        "notification_dropped",
        "target_edge_candidate_exposure",
        "target_edge_attempt",
        "physical_fault_interlock_rejection",
        "physical_fault_interlock_hold",
    }
    assert payload["summary"]["fault_affected_bag_count"] == 1
    assert payload["summary"]["physical_fault_interlock_rejection_count"] > 0
    assert payload["summary"]["local_fault_policy_action_count"] == 0
    assert not [
        row
        for row in payload["fault_events"]
        if row["phase"].startswith("local_fault_policy_")
    ]
    gate = fault_window_metrics(
        payload["bags"],
        payload["fault_events"],
        payload["summary"],
        [FaultWindow(0, 1, 0.0, 1.0, 0.25, True)],
        max_recovery_seconds=5.0,
    )[0]
    assert gate["sensor_loss_interlock_boundary_pass"] is True
    assert gate["physical_interlock_rejection_count"] > 0
    assert gate["fault_recovery_pass"] is True


def test_real_map_sink_sentinel_is_normalised_for_every_terminal_goal() -> None:
    from scripts.eval.g4i_runtime import _graph_records

    nodes, edges, heuristic = _graph_records()
    pairs = [(3, 47), (3, 48), (3, 49), (0, 50), (0, 51)]
    for index, (start, goal) in enumerate(pairs):
        payload = _run(
            nodes=nodes,
            edges=edges,
            heuristic=heuristic,
            bags=[(f"sink-{goal}", 700 + index, 0.0, 10_000.0, start, goal, str(start))],
            max_decisions_per_bag=128,
            # Some legal sink routes take slightly more than 200 simulated
            # seconds (for example 3 -> 48 finishes at about 220.6 s).  This
            # regression is about terminal heuristic sentinels, not the
            # generic short-test horizon used by _run().
            max_simulation_time=10_000.0,
            scenario=f"real_map_sink_{goal}_regression",
        )
        _assert_invariants(payload, 1)
        assert payload["bags"][0]["final_node"] == goal
        assert payload["summary"]["loop_count"] == 0


def test_real_map_concurrency_never_enters_a_non_goal_terminal_sink() -> None:
    from scripts.eval.g4i_runtime import _graph_records

    nodes, edges, heuristic = _graph_records()
    # Exercise both direct wrong terminals and the actual directed traps seen
    # in paper-full: 27 -> 45 -> 48 and 46 -> 35 -> 51.  Every group is
    # released simultaneously so downstream pressure cannot override the
    # bounded local topology shield.
    per_branch = 24
    bags = [
        (f"real-direct-{index}", 800 + index, 0.0, 10_000.0, 28, 49, "28")
        for index in range(per_branch)
    ]
    bags.extend(
        (f"real-trap-45-{index}", 900 + index, 0.0, 10_000.0, 27, 47, "27")
        for index in range(per_branch)
    )
    bags.extend(
        (f"real-trap-35-{index}", 1000 + index, 0.0, 10_000.0, 46, 47, "46")
        for index in range(per_branch)
    )
    payload = _run(
        nodes=nodes,
        edges=edges,
        heuristic=heuristic,
        bags=bags,
        max_decisions_per_bag=512,
        max_simulation_time=10_000.0,
        trace_limit=500_000,
        scenario="real_map_non_goal_terminal_concurrency",
    )
    _assert_invariants(payload, len(bags))
    at_branch = [
        row
        for row in payload["decisions"]
        if row["current_node"] == 28 and row["goal_node"] == 49
    ]
    assert len(at_branch) >= per_branch
    assert all(row["selected_next"] != 47 for row in at_branch)
    rejected_terminal = [
        candidate
        for row in at_branch
        for candidate in row["candidate_records"]
        if candidate["next_node"] == 47
    ]
    assert rejected_terminal
    assert all(candidate["shield_allowed"] is False for candidate in rejected_terminal)
    assert {candidate["shield_reason"] for candidate in rejected_terminal} == {
        "dead_end_not_goal"
    }

    for current, trapped_next in ((27, 45), (46, 35)):
        branch_rows = [
            row
            for row in payload["decisions"]
            if row["current_node"] == current and row["goal_node"] == 47
        ]
        assert len(branch_rows) >= per_branch
        assert all(row["selected_next"] != trapped_next for row in branch_rows)
        rejected_traps = [
            candidate
            for row in branch_rows
            for candidate in row["candidate_records"]
            if candidate["next_node"] == trapped_next
        ]
        assert rejected_traps
        assert all(candidate["shield_allowed"] is False for candidate in rejected_traps)
        assert {candidate["shield_reason"] for candidate in rejected_traps} == {
            "terminal_successor_trap_not_goal"
        }
