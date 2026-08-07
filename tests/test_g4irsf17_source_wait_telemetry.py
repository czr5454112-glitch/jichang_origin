from __future__ import annotations

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records
from tests.test_g4irsf11_event_runtime import _bags


CANONICAL_REASONS = {
    "SOURCE_SERVICE_NOT_READY",
    "FIRST_EDGE_CREDIT_UNAVAILABLE",
    "DESTINATION_QUEUE_CAPACITY",
    "DESTINATION_MERGE_TOKEN",
    "PHYSICAL_FAULT_OR_GENERATION",
    "SUPERVISOR_HOLD",
    "PIBT_OR_RECOVERY_TRANSACTION",
    "OTHER_EXPLICIT_REASON",
}


def _run_native(*, bags: list[tuple], **kwargs: object) -> dict:
    nodes, edges, heuristic = canonical_graph_records()
    module = cpp_backend.load_cpp_module()
    return dict(
        module.g4irsf11_event_runtime_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bags,
            fault_windows=[],
            scenario="pytest_g4irsf17_native_binding",
            **kwargs,
        )
    )


def test_source_wait_payload_is_additive_and_identity_is_trace_only() -> None:
    payload = _run_native(
        bags=_bags(3),
        minimum_service_seconds=0.25,
        admission_mode="off",
        enable_source_admission=False,
        enable_g4irsf17_source_wait_telemetry=True,
        g4irsf17_source_wait_trace_limit=1000,
    )
    summary = payload["summary"]
    rows = payload["g4irsf17_source_wait_blockers"]

    assert summary["g4irsf17_source_wait_telemetry_enabled"] is True
    assert rows
    assert summary["g4irsf17_source_wait_interval_total_count"] == len(rows)
    assert summary["g4irsf17_source_wait_interval_stored_count"] == len(rows)
    assert summary["g4irsf17_source_wait_interval_dropped_count"] == 0
    assert summary["g4irsf17_source_wait_runtime_global_scan_count"] == 0
    assert set(summary["g4irsf17_source_wait_reason_interval_counts"]) == (
        CANONICAL_REASONS
    )
    assert sum(summary["g4irsf17_source_wait_reason_interval_counts"].values()) == len(
        rows
    )
    assert sum(summary["g4irsf17_source_wait_reason_seconds"].values()) == pytest.approx(
        summary["g4irsf17_source_wait_seconds"]
    )
    assert sum(
        summary["g4irsf17_source_wait_reason_bag_seconds"].values()
    ) == pytest.approx(summary["g4irsf17_source_wait_bag_seconds"])

    for row in rows:
        assert row["reason"] == "SOURCE_SERVICE_NOT_READY"
        assert row["source_node"] == 3
        assert row["blocker_node"] == 3
        assert row["wait_end_time"] > row["wait_start_time"]
        assert row["wait_seconds"] == pytest.approx(
            row["wait_end_time"] - row["wait_start_time"]
        )
        assert row["wait_bag_seconds"] == pytest.approx(
            row["wait_seconds"] * row["affected_bag_count"]
        )
        assert set(row) == {
            "interval_ordinal",
            "reason",
            "reason_precedence",
            "source_node",
            "blocker_node",
            "blocker_resource",
            "blocker_resource_from_node",
            "blocker_resource_to_node",
            "source_generation",
            "blocker_generation",
            "wait_start_time",
            "wait_end_time",
            "wait_seconds",
            "affected_bag_count",
            "wait_bag_seconds",
            "selected_task_id",
            "selected_runtime_bag_id",
            "selected_segment_id",
        }

    context = payload["trace_context"]
    assert context["g4irsf17_source_wait_runtime_global_scan_count"] == 0
    assert "trace_only_never_policy_or_model_input" in context[
        "g4irsf17_source_wait_identity_semantics"
    ]


def test_source_wait_storage_is_bounded_and_disabled_payload_is_unchanged() -> None:
    capped = _run_native(
        bags=_bags(3),
        minimum_service_seconds=0.25,
        admission_mode="off",
        enable_source_admission=False,
        enable_g4irsf17_source_wait_telemetry=True,
        g4irsf17_source_wait_trace_limit=0,
    )
    assert capped["g4irsf17_source_wait_blockers"] == []
    capped_summary = capped["summary"]
    assert capped_summary["g4irsf17_source_wait_interval_total_count"] > 0
    assert (
        capped_summary["g4irsf17_source_wait_interval_dropped_count"]
        == capped_summary["g4irsf17_source_wait_interval_total_count"]
    )

    disabled = _run_native(
        bags=_bags(2),
        minimum_service_seconds=0.25,
        admission_mode="off",
        enable_source_admission=False,
    )
    assert "g4irsf17_source_wait_blockers" not in disabled
    assert not any(
        key.startswith("g4irsf17_source_wait") for key in disabled["summary"]
    )
    assert not any(
        key.startswith("g4irsf17_source_wait")
        for key in disabled["trace_context"]
    )
