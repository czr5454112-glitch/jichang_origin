from __future__ import annotations

from copy import deepcopy

import pytest

from tests.test_g4irsf11_event_runtime import _run


def _hard_local_invariants(payload: dict[str, object], completed: int) -> None:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["completed_count"] == completed
    assert summary["failed_count"] == 0
    assert summary["reservation_conflicts"] == 0
    assert summary["physical_fault_edge_entry_violation_count"] == 0
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["global_reservation_scan_count"] == 0
    assert summary["full_future_routes_stored"] == 0
    assert summary["reservation_depth"] == 1
    assert summary["two_step_reservation_count"] == 0
    assert summary["max_edges_selected_per_bag_per_decision"] <= 1
    assert summary["event_limit_reached"] is False
    assert summary["time_limit_reached"] is False


def test_explicit_q0_current_controls_preserve_default_result() -> None:
    common = {
        "bags": [
            ("default-a", 1, 0.0, 100.0, 3, 47, "source-3"),
            ("default-b", 2, 0.1, 80.0, 6, 47, "source-6"),
        ],
        "trace_limit": 100_000,
        "scenario": "g4irsf13_default_equivalence",
    }
    implicit = _run(**common)
    explicit = _run(
        **common,
        priority_mode="Q0",
        pibt_preference_mode="current",
        pibt_regret_prior_records=(),
        framework_mode="event_loop_one_step",
        selective_credit_contention_threshold=1,
    )
    assert implicit["bags"] == explicit["bags"]
    assert implicit["decisions"] == explicit["decisions"]
    assert implicit["events"] == explicit["events"]
    for payload in (implicit, explicit):
        _hard_local_invariants(payload, 2)
        summary = payload["summary"]
        assert summary["priority_mode"] == "Q0"
        assert summary["pibt_preference_mode"] == "current"
        assert summary["framework_diagnostic_only"] is False


@pytest.mark.parametrize("priority_mode", ["Q0", "Q1", "Q2", "Q3"])
def test_priority_modes_are_unique_local_and_record_real_storage_out(
    priority_mode: str,
) -> None:
    payload = _run(
        bags=[
            (
                f"storage-out-{priority_mode}",
                100,
                0.0,
                120.0,
                52,
                47,
                "EBS-storage-out",
            )
        ],
        priority_mode=priority_mode,
        trace_limit=100_000,
        scenario=f"g4irsf13_{priority_mode}_real_source52",
    )
    _hard_local_invariants(payload, 1)
    summary = payload["summary"]
    assert summary["priority_mode"] == priority_mode
    assert summary["priority_teacher_input_count"] == 0
    assert summary["priority_future_route_input_count"] == 0
    assert summary["priority_global_scan_count"] == 0
    decisions = payload["decisions"]
    assert decisions
    for decision in decisions:
        metadata = decision["metadata"]
        assert metadata["priority_mode"] == priority_mode
        assert metadata["task_class"] == "storage_out"
        assert metadata["priority_enqueue_sequence"] > 0
        assert metadata["priority_age_seconds"] >= 0.0


def test_legacy_order_b2_is_diagnostic_one_step_only() -> None:
    payload = _run(
        bags=[
            ("legacy-order-a", 1, 0.0, 100.0, 3, 47, "source-3"),
            ("legacy-order-b", 2, 0.4, 100.0, 3, 47, "source-3"),
        ],
        framework_mode="legacy_order_one_step_diagnostic",
        priority_mode="Q2",
        pibt_mode="P2",
        local_queue_capacity=4,
        enable_pibt_lite=False,
        trace_limit=100_000,
        scenario="g4irsf13_b2_real_map2",
    )
    _hard_local_invariants(payload, 2)
    summary = payload["summary"]
    assert summary["framework_mode"] == "legacy_order_one_step_diagnostic"
    assert summary["framework_diagnostic_only"] is True
    assert summary["max_actions_committed_per_pibt_batch"] <= 2
    assert all(
        event["selected_edge_count"] <= 1 for event in payload["events"]
    )


@pytest.mark.parametrize(
    ("admission_mode", "credit_mode"),
    [
        ("merge_only_first_edge_credit", "C7"),
        ("contention_triggered_first_edge_credit", "C8"),
    ],
)
def test_selective_credit_low_load_degrades_to_c0(
    admission_mode: str,
    credit_mode: str,
) -> None:
    payload = _run(
        bags=[("low-load", 1, 0.0, 100.0, 0, 47, "source-0")],
        admission_mode=admission_mode,
        enable_source_admission=True,
        enable_backpressure=False,
        trace_limit=100_000,
        scenario=f"g4irsf13_{credit_mode}_low_load",
    )
    _hard_local_invariants(payload, 1)
    summary = payload["summary"]
    assert summary["credit_mode"] == credit_mode
    assert summary["selective_credit_trigger_count"] == 0
    assert summary["selective_credit_low_load_bypass_count"] > 0
    assert summary["first_edge_credit_issued_count"] == 0
    assert summary["first_edge_credit_future_route_count"] == 0
    assert summary["first_edge_credit_global_scan_count"] == 0


def test_c7_c8_trigger_only_on_real_merge_or_contention() -> None:
    # 6->8 and 7->8 are real map2 incoming edges. The 8->11 fault holds an
    # owner locally long enough to expose merge/contention triggers.
    bags = [
        ("real-merge-owner", 1, 0.0, 100.0, 8, 11, "source-8"),
        ("real-merge-trigger", 2, 0.55, 100.0, 6, 11, "source-6"),
    ]
    faults = [(8, 11, 0.0, 1.55, 0.0)]
    c7 = _run(
        bags=bags,
        faults=faults,
        admission_mode="merge_only_first_edge_credit",
        enable_source_admission=True,
        enable_backpressure=False,
        local_queue_capacity=1,
        retry_interval=0.1,
        max_simulation_time=100.0,
        trace_limit=100_000,
        scenario="g4irsf13_c7_real_merge",
    )
    c8 = _run(
        bags=bags,
        faults=faults,
        admission_mode="contention_triggered_first_edge_credit",
        enable_source_admission=True,
        enable_backpressure=False,
        local_queue_capacity=1,
        retry_interval=0.1,
        max_simulation_time=100.0,
        trace_limit=100_000,
        scenario="g4irsf13_c8_real_contention",
    )
    for payload in (c7, c8):
        _hard_local_invariants(payload, 2)
        summary = payload["summary"]
        assert summary["selective_credit_trigger_count"] > 0
        assert summary["first_edge_credit_fault_revocation_count"] >= 0
        assert summary["physical_fault_edge_entry_violation_count"] == 0
    assert c7["summary"]["selective_credit_merge_trigger_count"] > 0
    assert c8["summary"]["selective_credit_contention_trigger_count"] > 0


def test_fault_repair_reentry_gets_q3_priority_class_without_unsafe_entry() -> None:
    payload = _run(
        bags=[("repair-reentry", 1, 0.0, 100.0, 6, 47, "source-6")],
        # Both real exits of junction 6 are briefly unavailable. Disabling
        # source admission places the bag in the real local queue, where the
        # physical shield records the exposure before either repair.
        faults=[
            (6, 8, 0.0, 2.0, 0.0),
            (6, 12, 0.0, 2.0, 0.0),
        ],
        enable_source_admission=False,
        priority_mode="Q3",
        enable_fault_policy=True,
        retry_interval=0.1,
        trace_limit=100_000,
        scenario="g4irsf13_q3_repair_reentry",
    )
    _hard_local_invariants(payload, 1)
    summary = payload["summary"]
    assert summary["fault_affected_bag_count"] == 1
    assert summary["repaired_task_reentry_count"] == 1
    assert summary["repaired_task_reentry_boost_cleared_count"] == 1
    boosted = [
        decision
        for decision in payload["decisions"]
        if decision["metadata"]["task_class"] == "repaired_fault_affected"
        and decision["metadata"]["priority_fault_generation"] > 0
    ]
    assert len(boosted) == 1
    assert any(
        decision["event_time"] > boosted[0]["event_time"]
        and decision["metadata"]["task_class"] == "on_path"
        and decision["metadata"]["priority_fault_generation"] == 0
        for decision in payload["decisions"]
    )


@pytest.mark.parametrize(
    ("pibt_mode", "depth", "diagnostic"),
    [("P3", 3, False), ("P4", 4, True)],
)
def test_p3_p4_depth_and_preference_controls_remain_bounded(
    pibt_mode: str,
    depth: int,
    diagnostic: bool,
) -> None:
    payload = _run(
        bags=[
            ("owner", 1, 0.0, 100.0, 8, 11, "source-8"),
            ("trigger", 2, 0.55, 50.0, 6, 11, "source-6"),
        ],
        faults=[(8, 11, 0.0, 1.55, 0.0)],
        pibt_mode=pibt_mode,
        pibt_preference_mode="dodge_regret",
        pibt_regret_prior_records=[(6, 8, 11, 4.0)],
        local_queue_capacity=1,
        enable_source_admission=False,
        enable_backpressure=False,
        enable_pibt_lite=False,
        retry_interval=0.1,
        max_simulation_time=100.0,
        trace_limit=100_000,
        scenario=f"g4irsf13_{pibt_mode}_preference",
    )
    _hard_local_invariants(payload, 2)
    summary = payload["summary"]
    assert summary["pibt_max_depth"] == depth
    assert summary["pibt_mode_diagnostic_only"] is diagnostic
    assert summary["pibt_preference_mode"] == "dodge_regret"
    assert summary["pibt_regret_prior_record_count"] == 1
    assert summary["bounded_local_pibt_max_inheritance_depth"] <= depth
    assert summary["bounded_local_pibt_classical_completeness_claimed"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"priority_mode": "Q4"}, "priority_mode"),
        ({"pibt_preference_mode": "future_search"}, "pibt_preference_mode"),
        (
            {"pibt_regret_prior_records": [(6, 8, 11, -1.0)]},
            "non-negative",
        ),
        (
            {"selective_credit_contention_threshold": 0},
            "must be positive",
        ),
    ],
)
def test_new_control_boundary_fails_closed(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _run(
            bags=[("invalid-control", 1, 0.0, 100.0, 6, 47, "source-6")],
            **deepcopy(kwargs),
        )
