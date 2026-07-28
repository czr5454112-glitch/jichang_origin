from __future__ import annotations

from copy import deepcopy
import struct
import sys

import pytest

from tests.test_g4irsf11_event_runtime import _run


_EXTENSION_KEYS = {
    "source_admission_opportunities",
    "junction_arbitration_opportunities",
    "merge_request_visibility",
    "event_seq_ordering_audit",
    "arbitration_batch_cardinality",
}

_TELEMETRY_COUNT_PREFIXES = {
    "source_admission_opportunities": "source_opportunity",
    "junction_arbitration_opportunities": "junction_opportunity",
    "merge_request_visibility": "merge_visibility",
    "event_seq_ordering_audit": "event_seq_audit",
    "arbitration_batch_cardinality": "arbitration_batch",
}


def _bags() -> list[tuple[str, int, float, float, int, int, str]]:
    return [
        ("microphase-a", 1, 0.0, 100.0, 6, 47, "source-6"),
        ("microphase-b", 2, 0.0, 100.0, 6, 47, "source-6"),
        ("microphase-c", 3, 0.5, 100.0, 6, 47, "source-6"),
    ]


def _algorithm_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(payload)
    summary = normalized["summary"]
    assert isinstance(summary, dict)
    for key in (
        "runtime_seconds",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "event_throughput_per_second",
        "loaded_cpp_binary_path",
        "loaded_cpp_binary_sha256",
    ):
        summary.pop(key, None)
    normalized.pop("loaded_cpp_binary_path", None)
    normalized.pop("loaded_cpp_binary_sha256", None)
    return normalized


def _hard_invariants(payload: dict[str, object], completed: int) -> None:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["completed_count"] == completed
    assert summary["failed_count"] == 0
    assert summary["reservation_conflicts"] == 0
    assert summary["physical_fault_edge_entry_violation_count"] == 0
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["global_reservation_scan_count"] == 0
    assert summary["microphase_runtime_global_scan_count"] == 0
    assert summary["two_step_reservation_count"] == 0
    assert summary["max_edges_selected_per_bag_per_decision"] <= 1
    assert summary["artificial_batch_delay_seconds"] == 0.0
    assert summary["stale_arbitration_event_count"] == 0
    assert summary["event_limit_reached"] is False
    assert summary["time_limit_reached"] is False


def _assert_telemetry_count_identity(payload: dict[str, object]) -> None:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    for array_key, prefix in _TELEMETRY_COUNT_PREFIXES.items():
        stored = summary[f"{prefix}_stored_count"]
        dropped = summary[f"{prefix}_dropped_count"]
        total = summary[f"{prefix}_total_count"]
        assert stored == len(payload[array_key])
        assert total == stored + dropped
    assert summary["merge_visibility_total_count"] == summary["decision_count"]
    assert summary["arbitration_batch_total_count"] == (
        summary["source_opportunity_total_count"]
        + summary["junction_opportunity_total_count"]
    )
    assert summary["event_seq_audit_total_count"] == (
        summary["source_opportunity_total_count"]
        + summary["junction_opportunity_total_count"]
        + summary["merge_visibility_total_count"]
    )
    assert (
        summary["opportunity_event_queue_inspection_count"]
        == summary["event_seq_audit_total_count"]
    )


def test_default_e0_payload_and_algorithm_fields_are_exactly_compatible() -> None:
    common = {
        "bags": [
            ("e0-a", 1, 0.0, 100.0, 3, 47, "source-3"),
            ("e0-b", 2, 0.1, 100.0, 6, 47, "source-6"),
        ],
        "trace_limit": 100_000,
        "scenario": "g4irsf14_e0_exact",
    }
    implicit = _run(**common)
    explicit = _run(
        **common,
        event_semantics="E0_immediate_dispatch_f2",
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=200_000,
    )
    assert _algorithm_payload(implicit) == _algorithm_payload(explicit)
    assert _EXTENSION_KEYS.isdisjoint(implicit)
    assert "event_semantics" not in implicit["summary"]
    assert "source_opportunity_total_count" not in implicit["summary"]
    assert (
        "superseded_arbitration_event_rejected_count"
        not in implicit["summary"]
    )
    assert "event_semantics" not in implicit["trace_context"]
    assert "merge_grant_lifecycle" not in implicit
    assert "merge_grant_rule" not in implicit["summary"]
    assert all(
        "merge_grant_wait_seconds" not in bag
        for bag in implicit["bags"]
    )


@pytest.mark.parametrize(
    ("mode", "source_batched", "junction_batched"),
    [
        ("E1", True, False),
        ("E2", False, True),
        ("E3", True, True),
    ],
)
def test_append_only_modes_isolate_exact_local_arbitration(
    mode: str,
    source_batched: bool,
    junction_batched: bool,
) -> None:
    payload = _run(
        bags=_bags(),
        event_semantics=mode,
        enable_opportunity_telemetry=True,
        opportunity_trace_limit=100_000,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        enable_pibt_lite=False,
        trace_limit=100_000,
        scenario=f"g4irsf14_{mode}",
    )
    _hard_invariants(payload, 3)
    summary = payload["summary"]
    assert (summary["source_arbitration_event_count"] > 0) is source_batched
    assert (
        summary["junction_arbitration_event_count"] > 0
    ) is junction_batched
    assert summary["event_semantics"].startswith(mode)
    assert summary["opportunity_telemetry_enabled"] is True
    assert summary["opportunity_event_queue_inspection_count"] > 0
    assert _EXTENSION_KEYS <= payload.keys()
    _assert_telemetry_count_identity(payload)
    assert all(
        summary[f"{prefix}_dropped_count"] == 0
        for prefix in _TELEMETRY_COUNT_PREFIXES.values()
    )
    assert payload["trace_context"]["destination_merge_grant_enabled"] is False
    assert "merge_grant_lifecycle" not in payload
    assert "merge_grant_rule" not in summary
    assert all(
        "merge_grant_wait_seconds" not in bag
        for bag in payload["bags"]
    )
    assert payload["trace_context"]["arbitration_worklist_scope"] == (
        "event_triggered_active_nodes_only_no_all_node_scan"
    )
    assert payload["trace_context"]["event_queue_inspection_scope"] == (
        "passive_opportunity_audit_only_not_runtime_feature_or_"
        "reservation_scan"
    )
    assert payload["trace_context"]["priority_comparison_semantics"] == (
        "actual_choose_bag_comparator_invocations_escape_bypass_zero"
    )


def test_e1_source_batch_cardinality_generation_and_stale_wakeup() -> None:
    payload = _run(
        bags=_bags(),
        event_semantics="E1",
        enable_opportunity_telemetry=True,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        enable_pibt_lite=False,
        trace_limit=100_000,
        scenario="g4irsf14_e1_generation",
    )
    rows = [
        row
        for row in payload["source_admission_opportunities"]
        if row["source_node"] == 6 and row["event_time"] == 0.0
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["queue_length_before_enqueue"] == 0
    assert row["queue_length_after_enqueue"] == 2
    assert row["queue_length_before_arbitration"] == 2
    assert row["queue_length_after_arbitration"] == 1
    assert row["same_timestamp_release_batch_size"] == 2
    assert row["ready_set_size"] == 2
    assert row["priority_comparison_count"] == 1
    assert row["same_time_pending_shared_merge_releases"] == 0
    assert row["arbitration_generation"] > 0
    assert row["timestamp_bits"] == int.from_bytes(
        struct.pack("=d", 0.0), sys.byteorder
    )
    assert row["batched_arbitration"] is True
    assert min(bag["admitted_time"] for bag in payload["bags"]) == 0.0
    summary = payload["summary"]
    assert summary["max_source_arbitration_batch_size"] == 2
    assert summary["source_same_timestamp_batch_count"] >= 1
    assert summary["stale_arbitration_event_count"] == 0
    assert summary["superseded_arbitration_event_rejected_count"] >= 1
    assert summary["duplicate_same_time_arbitration_prevented_count"] >= 1

    keys = [
        (batch["boundary"], batch["node"], batch["timestamp_bits"])
        for batch in payload["arbitration_batch_cardinality"]
    ]
    assert len(keys) == len(set(keys))


def test_e0_telemetry_observes_later_same_time_competitor_passively() -> None:
    payload = _run(
        bags=[
            ("audit-a", 1, 0.0, 100.0, 6, 47, "source-6"),
            ("audit-b", 2, 0.0, 100.0, 6, 47, "source-6"),
        ],
        event_semantics="E0",
        enable_opportunity_telemetry=True,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        trace_limit=100_000,
        scenario="g4irsf14_e0_passive_audit",
    )
    _hard_invariants(payload, 2)
    opportunities = payload["source_admission_opportunities"]
    assert any(
        row["event_time"] == 0.0
        and row["ready_set_size"] == 1
        and row["same_time_pending_source_releases"] == 1
        and row["batched_arbitration"] is False
        for row in opportunities
    )
    assert any(
        row["boundary"] == "source_admission"
        and row["seq_determined_order"] is True
        and row["reason"] == "later_same_time_release_unseen_at_arbitration"
        for row in payload["event_seq_ordering_audit"]
    )


def test_destination_visibility_includes_pending_source_dispatch() -> None:
    payload = _run(
        bags=[
            ("merge-source-6", 1, 0.0, 100.0, 6, 11, "source-6"),
            ("merge-source-7", 2, 0.0, 100.0, 7, 11, "source-7"),
        ],
        event_semantics="E0",
        enable_opportunity_telemetry=True,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        trace_limit=100_000,
        scenario="g4irsf14_source_merge_visibility",
    )
    _hard_invariants(payload, 2)
    assert any(
        row["upstream_node"] == 6
        and row["destination_node"] == 8
        and row["later_same_time_competitor_exists"] is True
        and row["later_same_time_competitor_count"] >= 1
        for row in payload["merge_request_visibility"]
    )
    assert any(
        row["source_node"] == 6
        and row["event_time"] == 0.0
        and row["same_time_pending_shared_merge_releases"] >= 1
        for row in payload["source_admission_opportunities"]
    )
    assert payload["trace_context"][
        "destination_competitor_visibility_semantics"
    ] == (
        "outgoing_edge_potential_competitor_upper_bound_not_selected_route_"
        "or_grant"
    )


def test_batched_mode_without_telemetry_never_inspects_event_queue() -> None:
    payload = _run(
        bags=_bags(),
        event_semantics="E3",
        enable_opportunity_telemetry=False,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        trace_limit=100_000,
        scenario="g4irsf14_no_telemetry_inspection",
    )
    _hard_invariants(payload, 3)
    assert payload["summary"]["opportunity_event_queue_inspection_count"] == 0
    assert all(payload[key] == [] for key in _EXTENSION_KEYS)


def test_zero_opportunity_limit_is_auditable_under_summary_only() -> None:
    payload = _run(
        bags=_bags(),
        event_semantics="E3",
        enable_opportunity_telemetry=True,
        opportunity_trace_limit=0,
        summary_only=True,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        scenario="g4irsf14_zero_opportunity_limit",
    )
    _hard_invariants(payload, 3)
    _assert_telemetry_count_identity(payload)
    summary = payload["summary"]
    for array_key, prefix in _TELEMETRY_COUNT_PREFIXES.items():
        assert payload[array_key] == []
        assert summary[f"{prefix}_stored_count"] == 0
        assert summary[f"{prefix}_total_count"] > 0
        assert (
            summary[f"{prefix}_dropped_count"]
            == summary[f"{prefix}_total_count"]
        )


def test_e3_fault_repair_precedes_arbitration_and_commit_rechecks() -> None:
    payload = _run(
        bags=[
            ("fault-repair-same-time", 1, 0.0, 100.0, 3, 47, "source-3")
        ],
        faults=[(3, 16, 0.0, 0.0, 0.0)],
        event_semantics="E3",
        enable_opportunity_telemetry=True,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        trace_limit=100_000,
        scenario="g4irsf14_e3_fault_repair",
    )
    _hard_invariants(payload, 1)
    source = next(
        row
        for row in payload["source_admission_opportunities"]
        if row["source_node"] == 3 and row["event_time"] == 0.0
    )
    physical = [
        row
        for row in payload["fault_events"]
        if row["time"] == 0.0 and row["phase"] == "physical_state_change"
    ]
    assert len(physical) == 2
    assert max(row["seq"] for row in physical) < source["event_seq"]
    assert payload["summary"]["fault_generation_commit_recheck_count"] > 0
    same_time_events = [
        event for event in payload["events"] if event["time"] == 0.0
    ]
    last_physical = max(
        index
        for index, event in enumerate(same_time_events)
        if event["reason"] == "physical_state_change"
    )
    release = next(
        index
        for index, event in enumerate(same_time_events)
        if event["reason"] == "source_release_enqueue"
    )
    first_local_delivery = next(
        index
        for index, event in enumerate(same_time_events)
        if event["reason"] == "local_message_delivery"
    )
    arbitration = next(
        index
        for index, event in enumerate(same_time_events)
        if event["event"] == "SOURCE_ARBITRATION"
    )
    assert last_physical < release < first_local_delivery < arbitration


def test_p2_commit_publishes_transactional_visibility() -> None:
    payload = _run(
        bags=[
            ("p2-trigger", 52, 0.0, 50.0, 6, 11, "trigger"),
            ("p2-owner", 51, 0.0, 100.0, 8, 11, "owner"),
        ],
        event_semantics="E3",
        enable_opportunity_telemetry=True,
        opportunity_trace_limit=100_000,
        enable_source_admission=False,
        enable_backpressure=False,
        admission_mode="off",
        pressure_mode="off",
        resource_semantics="R3_java_node_window_compatible",
        pibt_mode="P2",
        pibt_max_ready_bags=8,
        pibt_max_local_resources=32,
        pibt_max_candidates_per_bag=8,
        local_queue_capacity=1,
        retry_interval=0.1,
        trace_limit=100_000,
        scenario="g4irsf14_p2_transactional_visibility",
    )
    _hard_invariants(payload, 2)
    _assert_telemetry_count_identity(payload)
    summary = payload["summary"]
    assert summary["bounded_local_pibt_commit_count"] > 0
    assert summary["bounded_local_pibt_committed_action_count"] >= 2
    assert summary["stale_arbitration_event_count"] == 0
    assert summary["superseded_arbitration_event_rejected_count"] > 0
    visibility = payload["merge_request_visibility"]
    assert any(
        row["requesting_task_id"] == 51
        and row["upstream_node"] == 8
        and row["destination_node"] == 11
        for row in visibility
    )
    assert any(
        row["requesting_task_id"] == 52
        and row["upstream_node"] == 6
        and row["destination_node"] == 8
        for row in visibility
    )


@pytest.mark.parametrize("value", ["E5", "batch", ""])
def test_backend_rejects_unknown_event_semantics(value: object) -> None:
    with pytest.raises(ValueError, match="event_semantics"):
        _run(
            bags=[("invalid", 1, 0.0, 100.0, 3, 47, "source-3")],
            event_semantics=value,
        )


@pytest.mark.parametrize("value", [True, 1, [], None])
def test_backend_rejects_non_string_event_semantics(value: object) -> None:
    with pytest.raises(TypeError, match="event_semantics must be a string"):
        _run(
            bags=[("invalid", 1, 0.0, 100.0, 3, 47, "source-3")],
            event_semantics=value,
        )


def test_backend_rejects_non_bool_telemetry_and_negative_limit() -> None:
    with pytest.raises(TypeError, match="enable_opportunity_telemetry"):
        _run(
            bags=[("invalid", 1, 0.0, 100.0, 3, 47, "source-3")],
            enable_opportunity_telemetry=1,
        )
    with pytest.raises(ValueError, match="opportunity_trace_limit"):
        _run(
            bags=[("invalid", 1, 0.0, 100.0, 3, 47, "source-3")],
            opportunity_trace_limit=-1,
        )
