from __future__ import annotations

from collections.abc import Iterable

import pytest

from czr005 import cpp_backend
from czr005.datasets.decision_trace import canonicalise_decision_row
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_SHA256,
    assert_canonical_map,
    canonical_graph_records,
    canonical_map_identity,
)


def _require_cpp() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def _bags(count: int, *, task_offset: int = 0) -> list[tuple[str, int, float, float, int, int, str]]:
    """Small correctness window on real map2: source 3 to terminal 47."""

    return [
        (f"burst-{index}", task_offset + index + 1, 0.0, 10_000.0, 3, 47, "source-3")
        for index in range(count)
    ]


def _run(
    *,
    bags: Iterable[tuple[str, int, float, float, int, int, str]],
    faults: Iterable[
        tuple[int, int, float, float, float]
        | tuple[int, int, float, float, float, bool]
    ] = (),
    **kwargs: object,
) -> dict[str, object]:
    """Run only the protected canonical graph; tests cannot inject topology."""

    _require_cpp()
    assert assert_canonical_map() == CANONICAL_MAP_PATH
    assert canonical_map_identity()["sha256"] == CANONICAL_MAP_SHA256
    nodes, edges, heuristic = canonical_graph_records()
    retry_interval = float(kwargs.pop("retry_interval", 0.05))
    max_simulation_time = float(kwargs.pop("max_simulation_time", 10_000.0))
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
        scenario=str(kwargs.pop("scenario", "pytest_fixed_real_map")),
        **kwargs,
    )


def _assert_invariants(payload: dict[str, object], completed: int) -> None:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["completed_count"] == completed
    assert summary["failed_count"] == 0
    assert summary["reservation_conflicts"] == 0
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["runtime_full_cie_astar_calls"] == 0
    assert summary["global_reservation_scan_count"] == 0
    assert summary["reservation_depth"] == 1
    assert summary["two_step_reservation_count"] == 0
    assert summary["max_edges_selected_per_arrive"] <= 1
    assert summary["release_selected_edge_count"] == 0
    assert summary["bag_future_path_field_present"] is False
    assert summary["full_future_routes_stored"] == 0
    assert summary["max_history_observed"] <= 8
    assert summary["runtime_seconds"] >= 0.0
    assert 0.0 <= summary["decision_latency_us_p50"] <= summary["decision_latency_us_p95"]
    assert summary["decision_latency_us_p95"] <= summary["decision_latency_us_p99"]
    assert summary["cpp_internal_accounted_bytes"] > 0
    assert 0 <= summary["peak_active_bag_count"] <= summary["requested_count"]
    assert summary["final_active_bag_count"] == 0
    assert isinstance(summary["source_admission_enabled"], bool)
    admission_attempts = summary["source_admission_attempt_count"]
    admission_admitted = summary["source_admission_admitted_count"]
    admission_local_holds = summary["source_admission_local_resource_hold_count"]
    admission_pressure_holds = summary[
        "source_admission_downstream_pressure_hold_count"
    ]
    assert admission_attempts == (
        admission_admitted + admission_local_holds + admission_pressure_holds
    )
    assert completed <= admission_admitted <= summary["requested_count"]
    if summary["source_admission_enabled"]:
        assert summary["source_admission_beacon_read_count"] > 0
    else:
        assert admission_pressure_holds == 0
        assert summary["source_admission_beacon_read_count"] == 0
        assert summary["source_admission_max_observed_downstream_pressure"] == 0

    junction_state = payload["junction_state"]
    assert isinstance(junction_state, list) and junction_state
    final_accounted = 0
    service_reservations = 0
    for junction in junction_state:
        assert junction["final_source_queue_length"] == 0
        assert junction["final_junction_queue_length"] == 0
        assert junction["final_service_calendar_intervals"] == 0
        assert junction["scheduled_incoming"] == 0
        assert 0 < junction["final_local_state_accounted_bytes"] <= junction["peak_local_state_accounted_bytes"]
        assert junction["local_state_accounting_semantics"] == (
            "cpp_object_plus_live_deque_payload_plus_calendar_capacity_lower_bound"
        )
        assert junction["service_reservation_count"] >= 0
        assert junction["cumulative_service_reserved_seconds"] >= 0.0
        final_accounted += junction["final_local_state_accounted_bytes"]
        service_reservations += junction["service_reservation_count"]
    assert summary["cpp_internal_accounted_bytes"] >= final_accounted
    assert service_reservations >= completed

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
        candidates = set(decision["candidate_next_nodes"])
        assert decision["selected_next"] in candidates
        assert decision["model_prediction"] in candidates
        assert decision["full_astar_used"] is False
        assert "path_history" not in decision
        assert "finish_time" not in decision
        canonicalise_decision_row(decision)


def test_pre_release_time_limit_returns_exact_empty_junction_negative_evidence() -> None:
    payload = _run(
        bags=[("future-release", 1, 10.0, 100.0, 3, 47, "source-3")],
        max_simulation_time=0.0,
    )
    summary = payload["summary"]
    assert summary["completed_count"] == 0
    assert summary["failed_count"] == 1
    assert summary["event_count"] == 0
    assert summary["bag_release_event_count"] == 0
    assert summary["peak_active_bag_count"] == 0
    assert summary["final_active_bag_count"] == 0
    assert summary["time_limit_reached"] is True
    assert summary["event_limit_reached"] is False
    assert payload["junction_state"] == []


@pytest.mark.parametrize("count", [1, 2, 4, 8, 16])
def test_event_runtime_real_map_burst_sizes_are_online_and_conflict_free(count: int) -> None:
    payload = _run(bags=_bags(count))
    _assert_invariants(payload, count)
    summary = payload["summary"]
    assert summary["decision_count"] >= count
    assert summary["peak_active_bag_count"] == count
    if count == 16:
        assert summary["max_source_queue_length"] >= 15
        assert summary["max_source_queue_delay"] > 0.0
        assert 0.0 < summary["fairness_jain"] <= 1.0


def test_event_runtime_exposes_real_scheduler_event_vocabulary() -> None:
    payload = _run(bags=_bags(1))
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


def test_fixed_map_corridor_boundary_and_shared_directed_calendar() -> None:
    _nodes, edges, _heuristic = canonical_graph_records()
    directed = {(start, end) for start, end, _length, _speed in edges}
    # map2 has no reciprocal directed pair.  The requested opposite-direction
    # corridor case is therefore an explicit fixed-map structural boundary,
    # not permission to invent a bidirectional edge.
    assert not {(start, end) for start, end in directed if (end, start) in directed}

    payload = _run(bags=_bags(2), scenario="real_map_shared_corridor")
    _assert_invariants(payload, 2)
    first_corridor = sorted(
        (
            float(decision["event_time"]),
            float(decision["candidate_records"][0]["features"]["travel_time"]),
        )
        for decision in payload["decisions"]
        if decision["current_node"] == 3
    )
    assert len(first_corridor) == 2
    assert first_corridor[0][0] + first_corridor[0][1] <= first_corridor[1][0] + 1.0e-9
    assert payload["summary"]["shield_rejection_count"] > 0
    assert any(row["rule_reason"] == "corridor_busy" for row in payload["hold_attempts"])


def test_lower_is_better_score_contract_is_explicit_and_argmin_on_map2_branch() -> None:
    payload = _run(
        bags=[("score-contract", 201, 0.0, 1_000.0, 6, 47, "source-6")],
        scenario="real_map_score_contract",
    )
    _assert_invariants(payload, 1)
    decision = next(row for row in payload["decisions"] if row["current_node"] == 6)
    assert decision["candidate_next_nodes"] == [8, 12]
    score_by_node = {
        record["next_node"]: record["model_score"] for record in decision["candidate_records"]
    }
    assert decision["model_prediction"] == min(score_by_node, key=score_by_node.get)
    sorted_scores = sorted(score_by_node.values())
    assert decision["model_margin"] == pytest.approx(sorted_scores[1] - sorted_scores[0])
    assert decision["metadata"]["model_score_semantics"] == "lower_is_better_cost"


def test_fault_message_delay_is_shielded_and_repair_resumes_without_astar() -> None:
    payload = _run(
        bags=[("fault-wait", 301, 0.0, 1_000.0, 3, 47, "source-3")],
        faults=[(3, 16, 0.0, 1.0, 0.25)],
        retry_interval=0.1,
        deadlock_retry_threshold=2,
        enable_source_admission=False,
    )
    _assert_invariants(payload, 1)
    summary = payload["summary"]
    assert summary["stale_fault_shield_rejection_count"] > 0
    assert summary["deadlock_count"] > 0
    assert summary["resolved_deadlock_count"] > 0
    assert summary["unresolved_deadlock_count"] == 0
    assert all(row["selected_next"] is None for row in payload["hold_attempts"])


def test_fault_policy_off_disables_advertised_actions_but_not_physical_interlock() -> None:
    from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics

    common = dict(
        bags=[("fault-policy", 351, 0.0, 1_000.0, 6, 47, "source-6")],
        faults=[(6, 12, 0.0, 5.0, 0.0)],
        retry_interval=0.05,
    )
    policy_on = _run(**common, enable_fault_policy=True, scenario="fault_policy_on_map2")
    policy_off = _run(**common, enable_fault_policy=False, scenario="fault_policy_off_map2")
    _assert_invariants(policy_on, 1)
    _assert_invariants(policy_off, 1)
    on_summary = policy_on["summary"]
    off_summary = policy_off["summary"]
    assert on_summary["fault_affected_bag_count"] == 1
    assert on_summary["local_fault_policy_reroute_count"] > 0
    assert off_summary["fault_affected_bag_count"] == 1
    assert off_summary["local_fault_policy_action_count"] == 0
    assert off_summary["physical_fault_interlock_rejection_count"] > 0
    assert off_summary["physical_fault_interlock_hold_count"] > 0
    assert off_summary["physical_fault_edge_entry_violation_count"] == 0
    assert all(
        candidate["features"]["advertised_fault"] is False
        for row in policy_off["hold_attempts"]
        for candidate in row["candidate_records"]
    )
    window = FaultWindow(6, 12, 0.0, 5.0, 0.0)
    on_gate = fault_window_metrics(
        policy_on["bags"], policy_on["fault_events"], on_summary, [window], max_recovery_seconds=100.0
    )[0]
    off_gate = fault_window_metrics(
        policy_off["bags"], policy_off["fault_events"], off_summary, [window], max_recovery_seconds=100.0
    )[0]
    assert on_gate["fault_recovery_pass"] is True
    assert off_gate["fault_recovery_pass"] is True


def test_policy_off_long_fault_is_safe_but_uninformative_for_policy_gain() -> None:
    """The physical shield waits for repair even when advertised policy is off.

    This historical case cannot be used as negative policy evidence: its
    post-repair recovery gate passes without any advertised-policy action.
    """
    from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics

    payload = _run(
        bags=[
            (
                "fault-policy-unrecovered",
                352,
                0.0,
                10_000.0,
                6,
                47,
                "source-6",
            )
        ],
        faults=[(6, 12, 0.0, 3_600.0, 0.0)],
        retry_interval=0.25,
        max_decisions_per_bag=8,
        enable_fault_policy=False,
        scenario="fault_policy_off_unrecovered_map2",
    )
    summary = payload["summary"]
    assert summary["completed_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["local_fault_policy_action_count"] == 0
    assert summary["physical_fault_interlock_rejection_count"] > 0
    assert summary["physical_fault_interlock_hold_count"] > 0
    assert summary["physical_fault_edge_entry_violation_count"] == 0
    assert payload["bags"][0]["completed"] is True
    assert payload["bags"][0]["finish_time"] > 3_600.0

    gate = fault_window_metrics(
        payload["bags"],
        payload["fault_events"],
        summary,
        [FaultWindow(6, 12, 0.0, 3_600.0, 0.0)],
        max_recovery_seconds=1_800.0,
    )[0]
    assert gate["fault_policy_enabled"] is False
    assert gate["local_fault_policy_action_count"] == 0
    assert gate["physical_interlock_hold_count"] > 0
    assert gate["recovery_observed"] is True
    assert gate["recovery_time_seconds"] == pytest.approx(
        payload["bags"][0]["finish_time"] - 3_600.0
    )
    assert gate["recovery_time_pass"] is True
    assert gate["fault_recovery_gate_failures"] == []
    assert gate["fault_recovery_pass"] is True


def test_fault_during_real_edge_traversal_does_not_retroactively_replan() -> None:
    payload = _run(
        bags=[("in-flight", 401, 0.0, 1_000.0, 3, 17, "source-3")],
        faults=[(3, 16, 0.5, 1.5, 0.2)],
        trace_limit=1_000,
    )
    _assert_invariants(payload, 1)
    assert payload["decisions"]
    assert payload["events"]
    assert payload["summary"]["physical_fault_window_traversal_count"] == 1
    assert payload["summary"]["physical_fault_edge_entry_violation_count"] == 0
    assert {row["phase"] for row in payload["fault_events"]} >= {
        "physical_state_change",
        "local_message_delivery",
    }


def test_real_map_cycle_region_uses_only_bounded_past_history() -> None:
    payload = _run(
        bags=[("cycle-region", 501, 0.0, 10_000.0, 52, 47, "source-52")],
    )
    _assert_invariants(payload, 1)
    assert payload["summary"]["loop_count"] == 0
    assert all(len(decision["short_history"]) <= 8 for decision in payload["decisions"])
    assert all("future_path" not in decision for decision in payload["decisions"])


def test_history_limit_above_trace_contract_fails_closed() -> None:
    with pytest.raises(ValueError, match="history_limit"):
        _run(bags=_bags(1), history_limit=9)


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"max_events": True}, "max_events"),
        ({"max_events": 10.5}, "max_events"),
        ({"enable_source_admission": 1}, "enable_source_admission"),
        ({"max_simulation_time": float("nan")}, "max_simulation_time"),
    ],
)
def test_runtime_python_boundary_rejects_implicit_numeric_coercion(
    kwargs: dict[str, object],
    field: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        _run(bags=_bags(1), **kwargs)


def test_runtime_python_boundary_rejects_nonfinite_records_and_truthy_fault_flag() -> None:
    with pytest.raises(ValueError, match="release_time"):
        _run(
            bags=[
                (
                    "nan-release",
                    1201,
                    float("nan"),
                    1_000.0,
                    3,
                    47,
                    "source-3",
                )
            ]
        )
    with pytest.raises(TypeError, match="drop_notification"):
        _run(
            bags=_bags(1),
            faults=[(3, 16, 0.0, 1.0, 0.0, 1)],  # type: ignore[list-item]
        )


def test_deterministic_trace_shards_are_disjoint_and_cover_all_tasks() -> None:
    common = dict(bags=_bags(16), scenario="real_map_trace_shard")
    even = _run(**common, trace_shard_count=2, trace_shard_index=0)
    odd = _run(**common, trace_shard_count=2, trace_shard_index=1)
    even_tasks = {row["task_id"] for row in even["decisions"]}
    odd_tasks = {row["task_id"] for row in odd["decisions"]}
    assert even_tasks and odd_tasks and even_tasks.isdisjoint(odd_tasks)
    assert even_tasks | odd_tasks == set(range(1, 17))
    assert all(task_id % 2 == 0 for task_id in even_tasks)
    assert all(task_id % 2 == 1 for task_id in odd_tasks)


def test_trace_limit_reports_truncation_instead_of_silent_prefix_pass() -> None:
    payload = _run(bags=_bags(4), trace_limit=1)
    assert payload["summary"]["decision_trace_seen_count"] > 1
    assert payload["summary"]["decision_trace_stored_count"] + payload["summary"][
        "hold_trace_stored_count"
    ] == 1
    assert payload["summary"]["decision_trace_truncated"] is True
    assert payload["summary"]["event_trace_limit"] == 1
    assert payload["summary"]["event_trace_limit_inherited"] is True
    assert len(payload["events"]) <= 1


def test_independent_event_trace_limit_keeps_complete_decision_trace() -> None:
    payload = _run(
        bags=_bags(4),
        trace_limit=-1,
        event_trace_limit=0,
        scenario="real_map_decision_only_trace",
    )
    assert payload["events"] == []
    assert payload["decisions"]
    assert len(payload["decisions"]) == payload["summary"]["decision_count"]
    assert (
        len(payload["decisions"])
        == payload["summary"]["decision_trace_stored_count"]
    )
    assert (
        len(payload["decisions"]) + len(payload["hold_attempts"])
        == payload["summary"]["decision_trace_seen_count"]
    )
    assert payload["summary"]["trace_limit"] == -1
    assert payload["summary"]["event_trace_limit"] == 0
    assert payload["summary"]["event_trace_limit_inherited"] is False
    assert payload["summary"]["event_trace_truncated"] is True
    assert payload["summary"]["decision_trace_truncated"] is False
    assert payload["trace_context"]["event_trace_limit"] == 0
    assert payload["trace_context"]["event_trace_limit_inherited"] is False


def test_omitted_event_trace_limit_preserves_shared_limit_behavior() -> None:
    """The appended argument must not change any pre-existing runtime result."""

    common = {
        "bags": _bags(4),
        "trace_limit": 200_000,
        "scenario": "legacy_shared_trace_limit_equivalence",
    }
    inherited = _run(**common)
    explicit = _run(**common, event_trace_limit=200_000)

    for key in (
        "bags",
        "events",
        "decisions",
        "hold_attempts",
        "junction_state",
        "fault_events",
        "credit_events",
        "pibt_events",
    ):
        assert inherited[key] == explicit[key]

    ignored_nondeterministic = {
        "runtime_seconds",
        "event_throughput_per_second",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "event_trace_limit_inherited",
    }
    inherited_summary = {
        key: value
        for key, value in inherited["summary"].items()
        if key not in ignored_nondeterministic
    }
    explicit_summary = {
        key: value
        for key, value in explicit["summary"].items()
        if key not in ignored_nondeterministic
    }
    assert inherited_summary == explicit_summary
    assert inherited["summary"]["event_trace_limit_inherited"] is True
    assert explicit["summary"]["event_trace_limit_inherited"] is False

    inherited_context = dict(inherited["trace_context"])
    explicit_context = dict(explicit["trace_context"])
    inherited_context.pop("event_trace_limit_inherited")
    explicit_context.pop("event_trace_limit_inherited")
    assert inherited_context == explicit_context


def test_duplicate_original_task_id_segments_keep_unique_runtime_identity() -> None:
    payload = _run(
        bags=[
            ("77:storage_in", 77, 0.0, 1_000.0, 3, 47, "source-3"),
            ("77:storage_out", 77, 10.0, 1_000.0, 3, 47, "source-3"),
        ],
    )
    _assert_invariants(payload, 2)
    assert {row["task_id"] for row in payload["bags"]} == {77}
    assert len({row["runtime_bag_id"] for row in payload["bags"]}) == 2
    assert payload["trace_context"]["original_task_id_rewritten"] is False


def test_dropped_fault_notifications_rely_on_physical_interlock_only() -> None:
    from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics

    payload = _run(
        bags=[("sensor-loss", 601, 0.0, 1_000.0, 3, 47, "source-3")],
        faults=[(3, 16, 0.0, 1.0, 0.25, True)],
        retry_interval=0.1,
        enable_source_admission=False,
    )
    _assert_invariants(payload, 1)
    summary = payload["summary"]
    assert summary["sensor_loss_mode_used"] is True
    assert summary["fault_notification_drop_count"] == 2
    assert summary["physical_fault_interlock_rejection_count"] > 0
    assert summary["local_fault_policy_action_count"] == 0
    assert not [event for event in payload["events"] if event["reason"] == "local_message_delivery"]
    gate = fault_window_metrics(
        payload["bags"],
        payload["fault_events"],
        summary,
        [FaultWindow(3, 16, 0.0, 1.0, 0.25, True)],
        max_recovery_seconds=100.0,
    )[0]
    assert gate["sensor_loss_interlock_boundary_pass"] is True
    assert gate["fault_recovery_pass"] is True


def test_real_map_sink_sentinel_is_normalised_for_every_terminal_goal() -> None:
    pairs = [(3, 47), (3, 48), (3, 49), (0, 50), (0, 51)]
    for index, (start, goal) in enumerate(pairs):
        payload = _run(
            bags=[(f"sink-{goal}", 700 + index, 0.0, 10_000.0, start, goal, str(start))],
            max_decisions_per_bag=512,
            scenario=f"real_map_sink_{goal}_regression",
        )
        _assert_invariants(payload, 1)
        assert payload["bags"][0]["final_node"] == goal
        assert payload["summary"]["loop_count"] == 0


def test_real_map_concurrency_never_enters_a_non_goal_terminal_sink() -> None:
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
        bags=bags,
        max_decisions_per_bag=512,
        trace_limit=500_000,
        scenario="real_map_non_goal_terminal_concurrency",
    )
    _assert_invariants(payload, len(bags))
    at_branch = [
        row for row in payload["decisions"] if row["current_node"] == 28 and row["goal_node"] == 49
    ]
    assert len(at_branch) >= per_branch
    assert all(row["selected_next"] != 47 for row in at_branch)
    for current, trapped_next in ((27, 45), (46, 35)):
        branch_rows = [
            row for row in payload["decisions"] if row["current_node"] == current and row["goal_node"] == 47
        ]
        assert len(branch_rows) >= per_branch
        assert all(row["selected_next"] != trapped_next for row in branch_rows)
        rejected = [
            candidate
            for row in branch_rows
            for candidate in row["candidate_records"]
            if candidate["next_node"] == trapped_next
        ]
        assert rejected and all(candidate["shield_allowed"] is False for candidate in rejected)
