from __future__ import annotations

from itertools import combinations
from typing import Any

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records
from tests.test_g4irsf11_event_runtime import _run


_E4_SUMMARY_KEYS = {
    "merge_grant_rule",
    "merge_grant_rule_echo",
    "merge_grant_max_pending_requests",
    "merge_grant_lifecycle_limit",
    "destination_merge_arbitration_event_count",
    "merge_grant_request_count",
    "merge_grant_issued_count",
    "merge_grant_issued_transition_count",
    "merge_grant_prepared_count",
    "merge_grant_prepared_transition_count",
    "merge_grant_committed_count",
    "merge_grant_committed_transition_count",
    "merge_grant_consumed_count",
    "merge_grant_expired_count",
    "merge_grant_request_expired_count",
    "merge_grant_grant_expired_count",
    "merge_grant_revoked_count",
    "merge_grant_post_commit_revoked_count",
    "merge_grant_post_commit_expired_count",
    "merge_grant_post_commit_rollback_count",
    "merge_grant_revoked_fault_count",
    "merge_grant_revoked_stale_state_count",
    "merge_grant_revoked_replan_current_edge_count",
    "merge_grant_rolled_back_count",
    "merge_grant_exact_slot_busy_count",
    "merge_grant_active_grant_rejection_count",
    "merge_grant_queue_capacity_block_count",
    "merge_grant_contended_loser_retry_count",
    "merge_grant_lifecycle_transition_count",
    "merge_grant_lifecycle_stored_count",
    "merge_grant_lifecycle_dropped_count",
    "merge_grant_terminal_request_count",
    "merge_grant_outstanding_request_count",
    "merge_grant_goal_exempt_bypass_count",
    "merge_grant_stale_arbitration_count",
    "merge_grant_duplicate_wakeup_prevented_count",
    "merge_grant_peak_pending_requests",
    "merge_grant_peak_active_unconsumed",
    "merge_grant_final_active_unconsumed",
    "merge_grant_conservation_holds",
    "merge_grant_active_bijection_holds",
    "merge_grant_runtime_owned_capability",
    "merge_grant_exact_slot_no_future_shift",
    "merge_grant_lifecycle_complete",
    "merge_grant_protocol_integrity_pass",
}

_LIFECYCLE_KEYS = {
    "time",
    "request_id",
    "grant_id",
    "lineage",
    "request_generation",
    "junction_queue_generation",
    "runtime_bag_id",
    "task_id",
    "segment_id",
    "upstream_node",
    "destination_node",
    "edge_from_node",
    "edge_to_node",
    "request_time",
    "fifo_request_time",
    "earliest_edge_entry",
    "exact_edge_travel_seconds",
    "projected_arrival",
    "goal",
    "route_score",
    "static_remaining",
    "destination_service_seconds",
    "downstream_queue_pressure",
    "deadline_slack",
    "wait_age",
    "task_class_code",
    "task_class",
    "storage_leg",
    "source_release_age",
    "local_queue_age",
    "enqueue_sequence",
    "request_expiry",
    "slot_start",
    "slot_end",
    "issue_time",
    "grant_expiry",
    "calendar_generation",
    "fault_generation",
    "advertised_fault_generation",
    "observed_claimed_request_generation",
    "observed_claimed_junction_queue_generation",
    "observed_claimed_calendar_generation",
    "observed_claimed_owner_runtime_bag_id",
    "observed_claimed_edge_from_node",
    "observed_claimed_edge_to_node",
    "observed_claimed_destination_node",
    "observed_event_owner_runtime_bag_id",
    "observed_event_edge_from_node",
    "observed_event_edge_to_node",
    "observed_event_destination_node",
    "observed_junction_queue_generation",
    "observed_calendar_generation",
    "observed_physical_fault_generation",
    "observed_advertised_fault_generation",
    "observed_physical_fault_active",
    "observed_exact_calendar_reservation_present",
    "state",
    "reason",
}

_RULE_ALIASES = {
    "M0_current_event_seq_earliest_known": "M0",
    "M1_fifo": "M1",
    "M2_earliest_projected_arrival": "M2",
    "M3_deadline_aging": "M3",
    "M4_fairness_progress": "M4",
    "M5_local_externality": "M5",
    "M6_thesis_local": "M6",
}


def _discover_real_equal_travel_merge() -> dict[str, Any]:
    nodes, edges, _heuristic = canonical_graph_records()
    node_by_location = {record[0]: record for record in nodes}
    incoming: dict[int, list[tuple[int, float]]] = {}
    for start, end, length, speed in edges:
        incoming.setdefault(end, []).append((start, length / speed))

    for destination in sorted(incoming):
        node = node_by_location[destination]
        service_time = float(node[2])
        outgoing = list(node[5])
        if service_time <= 0.0 or not outgoing:
            continue
        for left, right in combinations(sorted(incoming[destination]), 2):
            if abs(left[1] - right[1]) <= 1.0e-9:
                return {
                    "destination": destination,
                    "upstream_a": left[0],
                    "upstream_b": right[0],
                    "goal": outgoing[0],
                    "travel": left[1],
                    "node_by_location": node_by_location,
                }
    raise AssertionError(
        "canonical map2 must retain a real equal-travel cross-upstream merge"
    )


def _contested_bags() -> list[
    tuple[str, int, float, float, int, int, str]
]:
    motif = _discover_real_equal_travel_merge()
    nodes = motif["node_by_location"]
    common_request_time = 2.0
    upstream_a = motif["upstream_a"]
    upstream_b = motif["upstream_b"]

    def release_time(upstream: int) -> float:
        return common_request_time - max(
            float(nodes[upstream][2]),
            1.0e-3,
        )

    return [
        (
            "map2-python-e4-a",
            51001,
            release_time(upstream_a),
            100.0,
            upstream_a,
            motif["goal"],
            "real-map-upstream-a",
        ),
        (
            "map2-python-e4-b",
            51002,
            release_time(upstream_b),
            100.0,
            upstream_b,
            motif["goal"],
            "real-map-upstream-b",
        ),
    ]


def _e4_run(
    *,
    rule: str = "M1",
    lifecycle_limit: int = 4096,
    event_semantics: str = "E4",
    **overrides: object,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "bags": _contested_bags(),
        "event_semantics": event_semantics,
        "enable_opportunity_telemetry": True,
        "opportunity_trace_limit": 100_000,
        "resource_semantics": "R3",
        "enable_source_admission": False,
        "admission_mode": "off",
        "enable_backpressure": False,
        "pressure_mode": "off",
        "pibt_mode": "P2",
        "priority_mode": "Q0",
        "scorer_mode": "S1",
        "enable_pibt_lite": False,
        "local_queue_capacity": 32,
        "max_events": 200_000,
        "max_simulation_time": 200.0,
        "event_trace_limit": 100_000,
        "trace_limit": 100_000,
        "merge_grant_rule": rule,
        "merge_grant_max_pending_requests": 16,
        "merge_grant_lifecycle_limit": lifecycle_limit,
        "scenario": f"g4irsf14_python_binding_{rule}",
    }
    kwargs.update(overrides)
    return _run(**kwargs)


def _assert_merge_conservation(summary: dict[str, object]) -> None:
    assert summary["merge_grant_request_count"] == (
        summary["merge_grant_committed_count"]
        + summary["merge_grant_terminal_request_count"]
        + summary["merge_grant_outstanding_request_count"]
    )
    assert (
        summary["merge_grant_issued_count"]
        == summary["merge_grant_prepared_count"]
        == summary["merge_grant_committed_count"]
    )
    assert (
        summary["merge_grant_issued_transition_count"]
        == summary["merge_grant_prepared_transition_count"]
        == summary["merge_grant_committed_transition_count"]
    )
    assert summary["merge_grant_committed_transition_count"] == (
        summary["merge_grant_consumed_count"]
        + summary["merge_grant_post_commit_revoked_count"]
        + summary["merge_grant_post_commit_expired_count"]
        + summary["merge_grant_post_commit_rollback_count"]
        + summary["merge_grant_final_active_unconsumed"]
    )
    assert summary["merge_grant_lifecycle_transition_count"] == (
        summary["merge_grant_lifecycle_stored_count"]
        + summary["merge_grant_lifecycle_dropped_count"]
    )


def test_e4_real_map_binding_exposes_complete_protocol() -> None:
    payload = _e4_run()
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["completed_count"] == 2
    assert summary["failed_count"] == 0
    assert summary["reservation_conflicts"] == 0
    assert summary["physical_fault_edge_entry_violation_count"] == 0
    assert summary["event_limit_reached"] is False
    assert summary["time_limit_reached"] is False
    assert _E4_SUMMARY_KEYS <= summary.keys()
    assert summary["merge_grant_rule"] == "M1"
    assert summary["merge_grant_rule_echo"] == "M1"
    assert summary["destination_merge_arbitration_event_count"] > 0
    assert summary["merge_grant_peak_pending_requests"] >= 2
    assert summary["merge_grant_contended_loser_retry_count"] >= 1
    assert summary["merge_grant_final_active_unconsumed"] == 0
    assert summary["merge_grant_conservation_holds"] is True
    assert summary["merge_grant_active_bijection_holds"] is True
    assert summary["merge_grant_runtime_owned_capability"] is True
    assert summary["merge_grant_exact_slot_no_future_shift"] is True
    assert summary["merge_grant_lifecycle_complete"] is True
    assert summary["merge_grant_protocol_integrity_pass"] is True
    _assert_merge_conservation(summary)

    lifecycle = payload["merge_grant_lifecycle"]
    assert isinstance(lifecycle, list) and lifecycle
    assert summary["merge_grant_lifecycle_stored_count"] == len(lifecycle)
    assert all(set(row) == _LIFECYCLE_KEYS for row in lifecycle)
    assert all(row["segment_id"] for row in lifecycle)
    assert {
        "REQUESTED",
        "ISSUED",
        "PREPARED",
        "COMMITTED",
        "CONSUMED",
    } <= {row["state"] for row in lifecycle}

    bags = payload["bags"]
    assert all("merge_grant_wait_seconds" in bag for bag in bags)
    assert any(bag["merge_grant_wait_seconds"] > 0.0 for bag in bags)
    assert all(
        0.0
        <= bag["merge_grant_wait_seconds"]
        <= bag["junction_queue_wait_seconds"] + 1.0e-9
        for bag in bags
    )

    context = payload["trace_context"]
    assert context["destination_merge_grant_enabled"] is True
    assert context["merge_grant_rule"] == "M1"
    assert context["merge_grant_max_pending_requests"] == 16
    assert context["merge_grant_lifecycle_limit"] == 4096
    assert context["destination_competitor_visibility_semantics"] == (
        "destination_owned_pending_current_one_hop_request_set"
    )
    assert context["merge_grant_wait_seconds_semantics"] == (
        "diagnostic_subset_of_junction_queue_wait_not_additive"
    )


@pytest.mark.parametrize("rule", [f"M{index}" for index in range(7)])
def test_e4_runs_every_online_rule_on_real_map(rule: str) -> None:
    payload = _e4_run(rule=rule)
    summary = payload["summary"]
    assert summary["merge_grant_rule"] == rule
    assert summary["merge_grant_rule_echo"] == rule
    assert summary["completed_count"] == 2
    assert summary["failed_count"] == 0
    assert summary["merge_grant_protocol_integrity_pass"] is True
    assert summary["merge_grant_committed_transition_count"] > 0
    _assert_merge_conservation(summary)


@pytest.mark.parametrize(("alias", "canonical"), _RULE_ALIASES.items())
def test_e4_rule_aliases_are_echoed_and_canonicalized(
    alias: str,
    canonical: str,
) -> None:
    payload = _e4_run(
        rule=alias,
        bags=[_contested_bags()[0]],
        event_semantics="E4_batch_plus_destination_merge_request",
    )
    summary = payload["summary"]
    assert summary["merge_grant_rule"] == canonical
    assert summary["merge_grant_rule_echo"] == alias
    assert summary["completed_count"] == 1


def test_e4_zero_lifecycle_limit_keeps_monotone_transition_evidence() -> None:
    payload = _e4_run(lifecycle_limit=0)
    summary = payload["summary"]
    assert payload["merge_grant_lifecycle"] == []
    assert summary["merge_grant_lifecycle_stored_count"] == 0
    assert summary["merge_grant_lifecycle_dropped_count"] > 0
    assert summary["merge_grant_lifecycle_complete"] is False
    assert summary["merge_grant_protocol_integrity_pass"] is False
    assert summary["merge_grant_committed_transition_count"] > 0
    _assert_merge_conservation(summary)


@pytest.mark.parametrize("rule", ["M7", "M8", "M9"])
def test_e4_fails_closed_for_non_online_rules(rule: str) -> None:
    with pytest.raises(ValueError, match=rule if rule == "M7" else "M8/M9"):
        _e4_run(rule=rule)


@pytest.mark.parametrize("resource", ["R0", "R1", "R2", "R4"])
def test_e4_rejects_non_r3_resource_semantics(resource: str) -> None:
    with pytest.raises(ValueError, match="require frozen R3"):
        _e4_run(resource_semantics=resource)


@pytest.mark.parametrize("pibt_mode", ["P0", "P1", "P3", "P4"])
def test_e4_rejects_non_p2_pibt_mode(pibt_mode: str) -> None:
    with pytest.raises(ValueError, match="frozen P2"):
        _e4_run(pibt_mode=pibt_mode)


@pytest.mark.parametrize("scorer_mode", ["S2", "S3", "S4"])
def test_e4_accepts_existing_decentralized_scorers(
    scorer_mode: str,
) -> None:
    payload = _e4_run(scorer_mode=scorer_mode)
    summary = payload["summary"]
    assert summary["scorer_mode"] == scorer_mode
    assert summary["completed_count"] == 2
    assert summary["failed_count"] == 0
    assert summary["merge_grant_protocol_integrity_pass"] is True
    _assert_merge_conservation(summary)


def test_e4_still_rejects_s0_scorer() -> None:
    with pytest.raises(ValueError, match="S1/S2/S3/S4"):
        _e4_run(scorer_mode="S0")


@pytest.mark.parametrize("priority_mode", ["Q1", "Q2", "Q3"])
def test_e4_rejects_non_q0_priority(priority_mode: str) -> None:
    with pytest.raises(ValueError, match="frozen Q0"):
        _e4_run(priority_mode=priority_mode)


@pytest.mark.parametrize(
    "admission_mode",
    [
        "expiring_first_edge_credit",
        "merge_only_first_edge_credit",
        "contention_triggered_first_edge_credit",
    ],
)
@pytest.mark.parametrize("enable_source_admission", [False, True])
def test_e4_rejects_first_edge_credit_even_when_source_admission_is_off(
    admission_mode: str,
    enable_source_admission: bool,
) -> None:
    with pytest.raises(ValueError, match="frozen C0 admission"):
        _e4_run(
            admission_mode=admission_mode,
            enable_source_admission=enable_source_admission,
        )


@pytest.mark.parametrize("admission_mode", ["off", "legacy_unbound"])
def test_e4_accepts_only_canonical_c0_admission_modes(
    admission_mode: str,
) -> None:
    payload = _e4_run(
        bags=[_contested_bags()[0]],
        admission_mode=admission_mode,
    )
    assert payload["summary"]["credit_mode"] == "C0"
    assert payload["summary"]["completed_count"] == 1


def test_e4_accepts_the_audited_full_name_aliases() -> None:
    payload = _e4_run(
        bags=[_contested_bags()[0]],
        event_semantics="E4_batch_plus_destination_merge_request",
        resource_semantics="R3_java_node_window_compatible",
        scorer_mode="S1_frozen_g4e_legal_local_adapter",
        priority_mode="current_f2",
        admission_mode="legacy_unbound",
    )
    summary = payload["summary"]
    assert summary["completed_count"] == 1
    assert summary["resource_semantics_id"] == (
        "R3_java_node_window_compatible"
    )
    assert summary["scorer_mode"] == (
        "S1_frozen_g4e_legal_local_adapter"
    )
    assert summary["pibt_mode"] == "P2"
    assert summary["priority_mode"] == "Q0"
    assert summary["credit_mode"] == "C0"


@pytest.mark.parametrize(
    ("name", "value", "exception", "message"),
    [
        (
            "merge_grant_max_pending_requests",
            True,
            TypeError,
            "must be an integer, not bool",
        ),
        (
            "merge_grant_max_pending_requests",
            0,
            ValueError,
            "must be positive",
        ),
        (
            "merge_grant_lifecycle_limit",
            True,
            TypeError,
            "must be an integer, not bool",
        ),
        (
            "merge_grant_lifecycle_limit",
            -1,
            ValueError,
            "must be non-negative",
        ),
    ],
)
def test_merge_grant_bounds_are_strict(
    name: str,
    value: object,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        _e4_run(**{name: value})


def test_merge_controls_are_rejected_outside_e4() -> None:
    with pytest.raises(ValueError, match="only valid with E4"):
        _run(
            bags=[_contested_bags()[0]],
            event_semantics="E3",
            merge_grant_rule="M2",
        )


def test_merge_rule_requires_string() -> None:
    with pytest.raises(TypeError, match="merge_grant_rule must be a string"):
        _e4_run(merge_grant_rule=1)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"resource_semantics": "R2"}, "frozen R3"),
        ({"pibt_mode": "P1"}, "frozen P2"),
        ({"scorer_mode": "S0"}, "S1/S2/S3/S4"),
        ({"priority_mode": "Q1"}, "frozen Q0"),
        (
            {"admission_mode": "expiring_first_edge_credit"},
            "frozen C0",
        ),
    ],
)
def test_direct_pybind_e4_entrypoint_enforces_frozen_stage_d_tuple(
    override: dict[str, object],
    message: str,
) -> None:
    nodes, edges, heuristic = canonical_graph_records()
    kwargs: dict[str, object] = {
        "event_semantics": "E4",
        "resource_semantics": "R3",
        "pibt_mode": "P2",
        "scorer_mode": "S1",
        "priority_mode": "Q0",
        "enable_source_admission": False,
        "admission_mode": "off",
    }
    kwargs.update(override)
    module = cpp_backend.load_cpp_module()
    with pytest.raises(ValueError, match=message):
        module.g4irsf11_event_runtime_from_records(
            nodes,
            edges,
            heuristic,
            [_contested_bags()[0]],
            **kwargs,
        )


@pytest.mark.parametrize("rule", ["M7", "M8", "M9"])
def test_direct_pybind_e4_fails_closed_for_non_online_rules(
    rule: str,
) -> None:
    nodes, edges, heuristic = canonical_graph_records()
    module = cpp_backend.load_cpp_module()
    with pytest.raises(
        ValueError,
        match=rule if rule == "M7" else "M8/M9",
    ):
        module.g4irsf11_event_runtime_from_records(
            nodes,
            edges,
            heuristic,
            [_contested_bags()[0]],
            event_semantics="E4",
            resource_semantics="R3",
            pibt_mode="P2",
            scorer_mode="S1",
            priority_mode="Q0",
            enable_source_admission=False,
            admission_mode="off",
            merge_grant_rule=rule,
        )


@pytest.mark.parametrize(
    ("name", "value", "exception", "message"),
    [
        (
            "merge_grant_max_pending_requests",
            True,
            TypeError,
            "must be an integer, not bool",
        ),
        (
            "merge_grant_max_pending_requests",
            0,
            ValueError,
            "must be positive",
        ),
        (
            "merge_grant_lifecycle_limit",
            True,
            TypeError,
            "must be an integer, not bool",
        ),
        (
            "merge_grant_lifecycle_limit",
            -1,
            ValueError,
            "must be non-negative",
        ),
    ],
)
def test_direct_pybind_merge_bounds_are_strict(
    name: str,
    value: object,
    exception: type[Exception],
    message: str,
) -> None:
    nodes, edges, heuristic = canonical_graph_records()
    module = cpp_backend.load_cpp_module()
    kwargs: dict[str, object] = {
        "event_semantics": "E4",
        "resource_semantics": "R3",
        "pibt_mode": "P2",
        "scorer_mode": "S1",
        "priority_mode": "Q0",
        "enable_source_admission": False,
        "admission_mode": "off",
        name: value,
    }
    with pytest.raises(exception, match=message):
        module.g4irsf11_event_runtime_from_records(
            nodes,
            edges,
            heuristic,
            [_contested_bags()[0]],
            **kwargs,
        )


def test_direct_pybind_rejects_merge_controls_outside_e4() -> None:
    nodes, edges, heuristic = canonical_graph_records()
    module = cpp_backend.load_cpp_module()
    with pytest.raises(ValueError, match="only valid with E4"):
        module.g4irsf11_event_runtime_from_records(
            nodes,
            edges,
            heuristic,
            [_contested_bags()[0]],
            event_semantics="E3",
            merge_grant_rule="M2",
        )
